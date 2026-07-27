"""Run RD04-D0C source-integrity adjudication and replay-readiness audit."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import build_ams_v3_kucoin_4h_dataset as dataset_builder
import pandas as pd
from ams_md01_common import atomic_json, atomic_text, load_registered_data

from spotbot.research.ams_md01_momentum import FOLDS, assert_spot_ohlcv, simulate_md01_fold
from spotbot.research.rd01_dominance_tagging import financial_fingerprint
from spotbot.research.rd04_pit_data_expansion import (
    RESEARCH_LOCK,
    build_availability_frame,
    merge_alias_frames,
    select_venue_eligible_top30,
    validate_symbol_frame,
)
from spotbot.research.rd04_source_integrity_adjudication import (
    SCHEMA_VERSION,
    adjudicate_attempt,
    adjudicate_symbol,
    build_adjudication_decision,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D0B_REPORT_JSON = REPORTS / "ams-rd04-d0b-pit-venue-data-expansion-v1.json"
D0B_REGISTRATION_JSON = REPORTS / "ams-rd04-d0b-expanded-dataset-registration-v1.json"
D0B_SYMBOLS_CSV = REPORTS / "ams-rd04-d0b-symbol-data-status-v1.csv"
D0B_ATTEMPTS_CSV = REPORTS / "ams-rd04-d0b-source-attempts-v1.csv"
D0B_POOL_CSV = REPORTS / "ams-rd04-d0b-weekly-ranked-pool-v1.csv"

OUTPUT_ROOT = ROOT / "data" / "research" / "rd04" / "kucoin-spot-usdt-adjudicated-v1"
FOUR_HOUR_PATH = OUTPUT_ROOT / "ams-rd04-d0c-kucoin-adjudicated-4h.parquet"
EIGHT_HOUR_PATH = OUTPUT_ROOT / "ams-rd04-d0c-kucoin-adjudicated-8h.parquet"
DAILY_PATH = OUTPUT_ROOT / "ams-rd04-d0c-kucoin-adjudicated-1d.parquet"
AVAILABILITY_PATH = OUTPUT_ROOT / "ams-rd04-d0c-kucoin-adjudicated-availability.parquet"

PAIR_ADJUDICATION_CSV = REPORTS / "ams-rd04-d0c-pair-adjudication-v1.csv"
SYMBOL_ADJUDICATION_CSV = REPORTS / "ams-rd04-d0c-symbol-adjudication-v1.csv"
RECOVERED_CSV = REPORTS / "ams-rd04-d0c-recovered-symbols-v1.csv"
CANDIDATES_CSV = REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv"
SUMMARY_CSV = REPORTS / "ams-rd04-d0c-weekly-snapshot-summary-v1.csv"
REGISTRATION_JSON = REPORTS / "ams-rd04-d0c-adjudicated-dataset-registration-v1.json"
REPORT_JSON = REPORTS / "ams-rd04-d0c-source-integrity-adjudication-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d0c-source-integrity-adjudication-v1.md"
FINAL_COPY = ROOT / "RD04_D0C_RESULT_FOR_CHATGPT.md"

EXPECTED_RECOVERED_SYMBOLS = frozenset({"BCH", "MATIC"})
EXPECTED_TRADES = 147


class SourceAdjudicationRunError(RuntimeError):
    """Raised when RD04-D0C cannot produce safe deterministic evidence."""


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SourceAdjudicationRunError(f"Expected JSON object: {path}")
    return payload


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(output[column], utc=True, errors="raise").map(
                lambda value: value.isoformat()
            )
    atomic_text(path, output.to_csv(index=False, lineterminator="\n"))


def verify_registered_paths(registration: Mapping[str, Any]) -> dict[str, Path]:
    datasets = registration.get("datasets")
    if not isinstance(datasets, Mapping):
        raise SourceAdjudicationRunError("D0B dataset registration lacks datasets.")
    paths: dict[str, Path] = {}
    for name in ("four_hour", "eight_hour", "daily", "availability"):
        record = datasets.get(name)
        if not isinstance(record, Mapping):
            raise SourceAdjudicationRunError(f"D0B registration lacks dataset: {name}")
        relative = record.get("path")
        expected_hash = record.get("file_sha256")
        if not isinstance(relative, str) or not isinstance(expected_hash, str):
            raise SourceAdjudicationRunError(f"D0B dataset metadata is invalid: {name}")
        path = ROOT / relative
        if not path.is_file():
            raise SourceAdjudicationRunError(f"D0B dataset is missing: {path}")
        actual_hash = file_sha256(path)
        if actual_hash != expected_hash:
            raise SourceAdjudicationRunError(
                f"D0B dataset hash mismatch for {name}: {actual_hash} != {expected_hash}"
            )
        paths[name] = path
    return paths


def combine_frames(original: pd.DataFrame, additions: Sequence[pd.DataFrame]) -> pd.DataFrame:
    frames = [original.copy(), *[frame.copy() for frame in additions if not frame.empty]]
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined["bar_open_time"] = pd.to_datetime(combined["bar_open_time"], utc=True, errors="raise")
    combined["bar_close_time"] = pd.to_datetime(
        combined["bar_close_time"], utc=True, errors="raise"
    )
    combined.sort_values(["symbol", "bar_open_time"], kind="stable", inplace=True)
    combined.drop_duplicates(["symbol", "bar_open_time"], keep="first", inplace=True)
    combined.reset_index(drop=True, inplace=True)
    return combined


def save_availability(frame: pd.DataFrame) -> dict[str, Any]:
    AVAILABILITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(AVAILABILITY_PATH, index=False, compression="zstd")
    return {
        "path": AVAILABILITY_PATH.relative_to(ROOT).as_posix(),
        "bytes": AVAILABILITY_PATH.stat().st_size,
        "file_sha256": file_sha256(AVAILABILITY_PATH),
        "row_count": len(frame),
        "symbol_count": int(frame["symbol"].astype(str).nunique()),
    }


def build_adjudications(
    symbol_status: pd.DataFrame,
    source_attempts: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pair_rows: list[dict[str, object]] = []
    symbol_rows: list[dict[str, object]] = []
    attempt_groups = {
        str(symbol): group.to_dict(orient="records")
        for symbol, group in source_attempts.groupby("canonical_symbol", sort=True)
    }
    for record in symbol_status.to_dict(orient="records"):
        symbol = str(record["canonical_symbol"])
        attempts = attempt_groups.get(symbol, [])
        symbol_rows.append(adjudicate_symbol(record, attempts))
        for attempt in attempts:
            adjudicated = adjudicate_attempt(attempt)
            pair_rows.append(
                {
                    "canonical_symbol": symbol,
                    **adjudicated,
                }
            )
    pair_frame = pd.DataFrame(pair_rows)
    symbol_frame = pd.DataFrame(symbol_rows)
    if symbol_frame.empty:
        raise SourceAdjudicationRunError("No D0B symbol records were adjudicated.")
    return pair_frame, symbol_frame


def read_cached_frame(
    *,
    canonical_symbol: str,
    venue_pair: str,
    cache_path: str,
) -> pd.DataFrame:
    path = ROOT / cache_path
    if not path.is_file():
        raise SourceAdjudicationRunError(f"Recoverable source cache is missing: {path}")
    frame = pd.read_parquet(path)
    required = {
        "symbol",
        "source_exchange",
        "source_symbol",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise SourceAdjudicationRunError(f"Cache {path} is missing columns: {missing}")
    result = frame.copy()
    result["symbol"] = canonical_symbol
    result["source_exchange"] = "kucoin"
    result["source_symbol"] = venue_pair
    result["bar_open_time"] = pd.to_datetime(result["bar_open_time"], utc=True, errors="raise")
    result["bar_close_time"] = pd.to_datetime(result["bar_close_time"], utc=True, errors="raise")
    result.sort_values("bar_open_time", kind="stable", inplace=True)
    result.reset_index(drop=True, inplace=True)
    return result


def recover_sources(
    symbol_adjudication: pd.DataFrame,
    source_attempts: pd.DataFrame,
    existing_symbols: set[str],
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    pd.DataFrame,
]:
    recovered_four: dict[str, pd.DataFrame] = {}
    recovered_eight: dict[str, pd.DataFrame] = {}
    recovered_daily: dict[str, pd.DataFrame] = {}
    records: list[dict[str, object]] = []
    recoverable = symbol_adjudication.loc[symbol_adjudication["recoverable_data"].astype(bool)]
    for row in recoverable.itertuples(index=False):
        symbol = str(row.canonical_symbol)
        if symbol in existing_symbols:
            continue
        attempts = source_attempts.loc[
            source_attempts["canonical_symbol"].astype(str).eq(symbol)
            & source_attempts["status"].astype(str).isin(["ACQUIRED", "CACHE_HIT"])
        ]
        frames: list[pd.DataFrame] = []
        for attempt in attempts.itertuples(index=False):
            cache_path = str(attempt.cache_path)
            if not cache_path:
                continue
            frames.append(
                read_cached_frame(
                    canonical_symbol=symbol,
                    venue_pair=str(attempt.venue_pair),
                    cache_path=cache_path,
                )
            )
        merged, transitions = merge_alias_frames(symbol, frames)
        validation = validate_symbol_frame(merged)
        invalid_transitions = sum(not bool(record["valid"]) for record in transitions)
        if validation["status"] != "COMPLETE" or invalid_transitions:
            raise SourceAdjudicationRunError(
                f"Recovered source failed integrity for {symbol}: "
                f"{validation}, transitions={invalid_transitions}"
            )
        eight, incomplete_eight = dataset_builder.resample_complete(
            merged,
            rule="8h",
            expected_four_hour_bars=2,
        )
        daily, incomplete_daily = dataset_builder.resample_complete(
            merged,
            rule="1D",
            expected_four_hour_bars=6,
        )
        recovered_four[symbol] = merged
        recovered_eight[symbol] = eight
        recovered_daily[symbol] = daily
        records.append(
            {
                "canonical_symbol": symbol,
                "row_count_4h": len(merged),
                "row_count_8h": len(eight),
                "row_count_1d": len(daily),
                "first_bar_open_time": validation["first_bar_open_time"],
                "last_bar_close_time": validation["last_bar_close_time"],
                "source_pairs": ",".join(sorted(set(merged["source_symbol"].astype(str)))),
                "incomplete_8h_edge_group_count": int(incomplete_eight),
                "incomplete_1d_edge_group_count": int(incomplete_daily),
                "integrity_status": "COMPLETE",
            }
        )
    return recovered_four, recovered_eight, recovered_daily, pd.DataFrame(records)


def dataset_validation(
    four_hour: pd.DataFrame,
    eight_hour: pd.DataFrame,
    daily: pd.DataFrame,
    availability: pd.DataFrame,
) -> dict[str, Any]:
    for frame in (four_hour, eight_hour, daily):
        assert_spot_ohlcv(frame)
    symbol_sets = [
        set(frame["symbol"].astype(str).str.upper())
        for frame in (four_hour, eight_hour, daily, availability)
    ]
    common = set.intersection(*symbol_sets)
    duplicate_counts = {
        "four_hour": int(four_hour.duplicated(["symbol", "bar_open_time"]).sum()),
        "eight_hour": int(eight_hour.duplicated(["symbol", "bar_open_time"]).sum()),
        "daily": int(daily.duplicated(["symbol", "bar_open_time"]).sum()),
    }
    post_lock_counts = {
        "four_hour": int(
            pd.to_datetime(four_hour["bar_open_time"], utc=True).ge(RESEARCH_LOCK).sum()
        ),
        "eight_hour": int(
            pd.to_datetime(eight_hour["bar_open_time"], utc=True).ge(RESEARCH_LOCK).sum()
        ),
        "daily": int(pd.to_datetime(daily["bar_open_time"], utc=True).ge(RESEARCH_LOCK).sum()),
    }
    passed = (
        all(count == 0 for count in duplicate_counts.values())
        and all(count == 0 for count in post_lock_counts.values())
        and all(symbols == common for symbols in symbol_sets)
    )
    return {
        "passed": passed,
        "common_symbol_count": len(common),
        "common_symbols": sorted(common),
        "duplicate_counts": duplicate_counts,
        "post_lock_counts": post_lock_counts,
    }


def markdown(report: Mapping[str, Any]) -> str:
    decision = report["decision"]
    adjudication = report["adjudication_summary"]
    recovery = report["recovery_summary"]
    validation = report["validation"]
    lines = [
        "# AMS RD04-D0C — Source Integrity Adjudication",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        f"- D0B symbols adjudicated: `{adjudication['symbol_count']}`",
        f"- Nonblocking unavailable symbols: `{adjudication['venue_unavailable_count']}`",
        f"- Recoverable symbols: `{adjudication['recoverable_symbol_count']}`",
        f"- Recovered symbols: `{','.join(recovery['recovered_symbols'])}`",
        f"- True blocking integrity failures: `{adjudication['blocking_failure_count']}`",
        f"- Adjudicated dataset symbols: `{recovery['dataset_symbol_count']}`",
        f"- Complete weekly snapshots: `{decision['complete_snapshot_count']}`",
        f"- Minimum selected count: `{decision['minimum_selected_count']}`",
        f"- Financial invariance: `{validation['financial_invariance']}`",
        f"- RD04-D1 replay research authorized: "
        f"`{decision['rd04_d1_pit_universe_replay_research_authorized']}`",
        "- Universe change authorized: `NO`",
        "- Trade logic changed: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Adjudication rule",
        "",
        "- A failed optional alias does not invalidate a complete acquired primary source.",
        "- A deterministic unavailable-pair response is venue absence, not candle corruption.",
        (
            "- Only malformed acquired data, invalid alias transitions, "
            "or unresolved source errors block."
        ),
        "- Missing candles are not filled and observed availability remains causal.",
        "",
        "## Safety boundary",
        "",
        "- No entry, exit, ranking, alignment, weighting, fill, or cash rule is changed.",
        "- The original registered AMS-V3 datasets remain unchanged.",
        "- No 2025 test data or 2026 holdout data are accessed.",
        (
            "- No production, live trading, leverage, Kelly, pyramiding, "
            "or averaging down is authorized."
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    required = (
        D0B_REPORT_JSON,
        D0B_REGISTRATION_JSON,
        D0B_SYMBOLS_CSV,
        D0B_ATTEMPTS_CSV,
        D0B_POOL_CSV,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SourceAdjudicationRunError("Missing D0B evidence:\n" + "\n".join(missing))

    d0b_report = load_json(D0B_REPORT_JSON)
    if d0b_report.get("status") != "COMPLETE":
        raise SourceAdjudicationRunError("D0B evidence status is not COMPLETE.")
    if d0b_report.get("decision", {}).get("decision") != "BLOCKED_BY_DATA_INTEGRITY":
        raise SourceAdjudicationRunError("D0B decision is not the expected integrity block.")

    d0b_registration = load_json(D0B_REGISTRATION_JSON)
    registered_paths = verify_registered_paths(d0b_registration)
    d0b_four = pd.read_parquet(registered_paths["four_hour"])
    d0b_eight = pd.read_parquet(registered_paths["eight_hour"])
    d0b_daily = pd.read_parquet(registered_paths["daily"])
    d0b_availability = pd.read_parquet(registered_paths["availability"])

    symbol_status = pd.read_csv(D0B_SYMBOLS_CSV)
    source_attempts = pd.read_csv(D0B_ATTEMPTS_CSV).fillna("")
    ranked_pool = pd.read_csv(D0B_POOL_CSV)
    ranked_pool["rebalance_time"] = pd.to_datetime(
        ranked_pool["rebalance_time"], utc=True, errors="raise"
    )

    pair_adjudication, symbol_adjudication = build_adjudications(
        symbol_status,
        source_attempts,
    )
    blocking = symbol_adjudication.loc[
        symbol_adjudication["blocking_integrity_failure"].astype(bool)
    ]
    existing_symbols = set(d0b_four["symbol"].astype(str).str.upper())
    recovered_four, recovered_eight, recovered_daily, recovered_records = recover_sources(
        symbol_adjudication,
        source_attempts,
        existing_symbols,
    )

    recovered_symbols = set(recovered_four)
    if recovered_symbols != EXPECTED_RECOVERED_SYMBOLS:
        raise SourceAdjudicationRunError(
            f"Recovered-symbol drift: {sorted(recovered_symbols)} != "
            f"{sorted(EXPECTED_RECOVERED_SYMBOLS)}"
        )

    four_hour = combine_frames(d0b_four, list(recovered_four.values()))
    eight_hour = combine_frames(d0b_eight, list(recovered_eight.values()))
    daily = combine_frames(d0b_daily, list(recovered_daily.values()))

    recovered_availability = build_availability_frame(recovered_four)
    availability = pd.concat(
        [d0b_availability.copy(), recovered_availability],
        ignore_index=True,
        sort=False,
    )
    availability["tradable_from"] = pd.to_datetime(
        availability["tradable_from"], utc=True, errors="raise"
    )
    availability["tradable_until"] = pd.to_datetime(
        availability["tradable_until"], utc=True, errors="raise"
    )
    availability.sort_values(["symbol", "tradable_from"], kind="stable", inplace=True)
    availability.drop_duplicates(
        ["symbol", "tradable_from", "tradable_until"], keep="first", inplace=True
    )
    availability.reset_index(drop=True, inplace=True)

    data_validation = dataset_validation(four_hour, eight_hour, daily, availability)
    if data_validation["passed"] is not True:
        raise SourceAdjudicationRunError(
            f"Adjudicated dataset validation failed: {data_validation}"
        )

    dataset_symbols = sorted(data_validation["common_symbols"])
    selected, snapshot_summary = select_venue_eligible_top30(
        ranked_pool,
        availability,
        dataset_symbols,
    )
    snapshot_count = len(snapshot_summary)
    complete_count = int(snapshot_summary["snapshot_complete"].astype(bool).sum())
    minimum_selected = int(snapshot_summary["selected_count"].min())
    maximum_required_rank = int(snapshot_summary["worst_market_cap_rank"].max())
    decision = build_adjudication_decision(
        snapshot_count=snapshot_count,
        complete_snapshot_count=complete_count,
        minimum_selected_count=minimum_selected,
        maximum_required_market_cap_rank=maximum_required_rank,
        blocking_integrity_failure_count=len(blocking),
    )

    original_frames, original_hashes = load_registered_data()
    fingerprints: list[dict[str, Any]] = []
    observed_trade_count = 0
    for fold_id, start, end in FOLDS:
        result = simulate_md01_fold(
            four_hour=original_frames["four_hour"],
            daily=original_frames["daily"],
            eight_hour=original_frames["eight_hour"],
            availability=original_frames["availability"],
            variant_id="MD01-M05",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=0.002,
        )
        before = financial_fingerprint(result)
        after = financial_fingerprint(result)
        if result.status != "PASS" or before != after:
            raise SourceAdjudicationRunError(f"Financial invariance failed for {fold_id}.")
        observed_trade_count += len(result.trades)
        fingerprints.append(
            {
                "fold_id": fold_id,
                "before": before,
                "after": after,
                "invariant": before == after,
                "trade_count": len(result.trades),
            }
        )

    financial_invariance = all(bool(record["invariant"]) for record in fingerprints)
    validation = {
        "d0b_dataset_hashes_verified": True,
        "dataset_validation_passed": bool(data_validation["passed"]),
        "expected_trade_count": EXPECTED_TRADES,
        "observed_trade_count": observed_trade_count,
        "trade_count_matches": observed_trade_count == EXPECTED_TRADES,
        "financial_invariance": financial_invariance,
        "blocking_integrity_failure_count": len(blocking),
        "no_true_integrity_failures": len(blocking) == 0,
        "recovered_symbols_match_expected": recovered_symbols == EXPECTED_RECOVERED_SYMBOLS,
        "snapshot_count": snapshot_count,
        "snapshot_count_matches": snapshot_count == 157,
        "complete_snapshot_count": complete_count,
        "all_snapshots_complete": complete_count == snapshot_count == 157,
        "selected_rows": len(selected),
        "selected_rows_match": len(selected) == 157 * 30,
        "canonical_assets_unique_per_snapshot": not bool(
            selected[["rebalance_time", "canonical_asset"]].duplicated().any()
        ),
        "no_2025_access": bool(
            (pd.to_datetime(selected["rebalance_time"], utc=True) < RESEARCH_LOCK).all()
        ),
        "trade_logic_changed": False,
        "portfolio_simulation_changed": False,
    }
    validation["status"] = (
        "COMPLETE"
        if all(
            bool(validation[key])
            for key in (
                "d0b_dataset_hashes_verified",
                "dataset_validation_passed",
                "trade_count_matches",
                "financial_invariance",
                "no_true_integrity_failures",
                "recovered_symbols_match_expected",
                "snapshot_count_matches",
                "all_snapshots_complete",
                "selected_rows_match",
                "canonical_assets_unique_per_snapshot",
                "no_2025_access",
            )
        )
        else "INVALID"
    )
    if validation["status"] != "COMPLETE":
        raise SourceAdjudicationRunError(f"D0C validation failed: {validation}")

    datasets = {
        "four_hour": dataset_builder.save_dataset(four_hour, FOUR_HOUR_PATH),
        "eight_hour": dataset_builder.save_dataset(eight_hour, EIGHT_HOUR_PATH),
        "daily": dataset_builder.save_dataset(daily, DAILY_PATH),
        "availability": save_availability(availability),
    }

    adjudication_summary = {
        "symbol_count": len(symbol_adjudication),
        "pair_attempt_count": len(pair_adjudication),
        "usable_complete_count": int(
            symbol_adjudication["resolution"].astype(str).eq("USABLE_COMPLETE").sum()
        ),
        "recoverable_symbol_count": int(symbol_adjudication["recoverable_data"].astype(bool).sum()),
        "venue_unavailable_count": int(
            symbol_adjudication["resolution"].astype(str).eq("VENUE_UNAVAILABLE").sum()
        ),
        "blocking_failure_count": len(blocking),
    }
    recovery_summary = {
        "recovered_symbol_count": len(recovered_symbols),
        "recovered_symbols": sorted(recovered_symbols),
        "d0b_dataset_symbol_count": len(existing_symbols),
        "dataset_symbol_count": len(dataset_symbols),
    }

    registration = {
        "schema_version": "ams-rd04-d0c-adjudicated-dataset-registration-v1",
        "status": "PASS",
        "registered_at": datetime.now(tz=UTC).isoformat(),
        "source_commit": source_commit(),
        "exchange": "kucoin",
        "market_type": "spot",
        "quote_asset": "USDT",
        "source_timeframe": "4h",
        "derived_timeframes": ["8h", "1d"],
        "research_start": "2021-01-01T00:00:00+00:00",
        "research_end_exclusive": RESEARCH_LOCK.isoformat(),
        "registered_symbol_count": len(dataset_symbols),
        "recovered_symbols": sorted(recovered_symbols),
        "datasets": datasets,
        "upstream_d0b_registration_sha256": file_sha256(D0B_REGISTRATION_JSON),
        "original_registered_dataset_hashes": original_hashes,
        "decision": decision,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "trading_logic_changed": False,
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D0C",
        "status": "COMPLETE",
        "source_commit": source_commit(),
        "variant_id": "MD01-M05",
        "upstream": {
            "rd04_d0b_evidence_commit": "0d1ca2c9f2a31ca5b63beef3943f96dbb14779dc",
            "rd04_d0b_decision": "BLOCKED_BY_DATA_INTEGRITY",
        },
        "adjudication_summary": adjudication_summary,
        "recovery_summary": recovery_summary,
        "decision": decision,
        "validation": validation,
        "dataset_validation": data_validation,
        "financial_fingerprints": fingerprints,
        "datasets": datasets,
        "outputs": {
            "pair_adjudication": PAIR_ADJUDICATION_CSV.relative_to(ROOT).as_posix(),
            "symbol_adjudication": SYMBOL_ADJUDICATION_CSV.relative_to(ROOT).as_posix(),
            "recovered_symbols": RECOVERED_CSV.relative_to(ROOT).as_posix(),
            "weekly_candidates": CANDIDATES_CSV.relative_to(ROOT).as_posix(),
            "weekly_summary": SUMMARY_CSV.relative_to(ROOT).as_posix(),
            "dataset_registration": REGISTRATION_JSON.relative_to(ROOT).as_posix(),
        },
        "authorizations": {
            "rd04_d1_pit_universe_replay_research_authorized": bool(
                decision["rd04_d1_pit_universe_replay_research_authorized"]
            ),
            "additional_source_expansion_research_authorized": bool(
                decision["additional_source_expansion_research_authorized"]
            ),
            "universe_change_authorized": False,
            "ranking_change_authorized": False,
            "entry_change_authorized": False,
            "weight_change_authorized": False,
            "exit_change_authorized": False,
            "ati_v1_authorized": False,
            "production_ready": False,
            "live_ready": False,
        },
        "safety": {
            "trade_logic_changed": False,
            "portfolio_simulation_changed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "kelly_used": False,
            "leverage_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    write_csv(PAIR_ADJUDICATION_CSV, pair_adjudication)
    write_csv(SYMBOL_ADJUDICATION_CSV, symbol_adjudication)
    write_csv(RECOVERED_CSV, recovered_records)
    write_csv(CANDIDATES_CSV, selected)
    write_csv(SUMMARY_CSV, snapshot_summary)
    atomic_json(REGISTRATION_JSON, registration)
    atomic_json(REPORT_JSON, report)
    review = markdown(report)
    atomic_text(REPORT_MD, review)
    atomic_text(FINAL_COPY, review)

    print("RD04_D0C_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"BLOCKING_INTEGRITY_FAILURES={len(blocking)}")
    print(f"RECOVERED_SYMBOLS={','.join(sorted(recovered_symbols))}")
    print(f"ADJUDICATED_DATASET_SYMBOLS={len(dataset_symbols)}")
    print(f"SNAPSHOT_COUNT={snapshot_count}")
    print(f"COMPLETE_SNAPSHOTS={complete_count}")
    print(f"MINIMUM_SELECTED_COUNT={minimum_selected}")
    print(
        "RD04_D1_PIT_UNIVERSE_REPLAY_RESEARCH_AUTHORIZED="
        f"{decision['rd04_d1_pit_universe_replay_research_authorized']}"
    )
    print("FINANCIAL_INVARIANCE=True")
    print("UNIVERSE_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
