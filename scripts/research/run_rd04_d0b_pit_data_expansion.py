"""Run RD04-D0B point-in-time venue data expansion."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import build_ams_v3_kucoin_4h_dataset as dataset_builder
import pandas as pd
from ams_md01_common import atomic_json, atomic_text, load_registered_data

from spotbot.research.ams_md01_momentum import FOLDS, assert_spot_ohlcv, simulate_md01_fold
from spotbot.research.rd01_dominance import decode_json_bytes
from spotbot.research.rd01_dominance_tagging import financial_fingerprint
from spotbot.research.rd04_investable_universe import (
    normalize_market_cap_panel,
    parse_stablecoin_symbols,
)
from spotbot.research.rd04_pit_data_expansion import (
    DECISION_BLOCKED,
    DECISION_MORE_DATA,
    DECISION_READY,
    EXPECTED_TRADES,
    RESEARCH_LOCK,
    RESEARCH_START,
    SCHEMA_VERSION,
    build_acquisition_manifest,
    build_availability_frame,
    build_expansion_decision,
    build_ranked_weekly_pool,
    finite,
    merge_alias_frames,
    normalized_4h_frame,
    parse_legacy_klines,
    parse_uta_klines,
    repair_canonical_panel,
    select_venue_eligible_top30,
    validate_expansion_evidence,
    validate_symbol_frame,
    venue_pair_candidates,
)
from spotbot.research.rd04_pit_universe import (
    parse_market_cap_panel,
    rebalance_schedule,
    sha256_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
RAW_ROOT = ROOT / "data" / "research" / "rd04" / "venue-expansion" / "raw"
OUTPUT_ROOT = ROOT / "data" / "research" / "rd04" / "kucoin-spot-usdt-expanded-v1"

MARKET_CAP_RAW = (
    ROOT
    / "data"
    / "research"
    / "rd01"
    / "dominance"
    / "raw"
    / "coinmetrics-community-market-cap-panel-2021-2024.json"
)
STABLECOIN_RAW = (
    ROOT
    / "data"
    / "research"
    / "rd04"
    / "eligibility"
    / "raw"
    / "defillama-stablecoins-catalogue.json"
)

FOUR_HOUR_PATH = OUTPUT_ROOT / "ams-rd04-d0b-kucoin-expanded-4h.parquet"
EIGHT_HOUR_PATH = OUTPUT_ROOT / "ams-rd04-d0b-kucoin-expanded-8h.parquet"
DAILY_PATH = OUTPUT_ROOT / "ams-rd04-d0b-kucoin-expanded-1d.parquet"
AVAILABILITY_PATH = OUTPUT_ROOT / "ams-rd04-d0b-kucoin-expanded-availability.parquet"

IDENTITY_CSV = REPORTS / "ams-rd04-d0b-identity-overlay-audit-v1.csv"
POOL_CSV = REPORTS / "ams-rd04-d0b-weekly-ranked-pool-v1.csv"
ACQUISITION_CSV = REPORTS / "ams-rd04-d0b-acquisition-manifest-v1.csv"
ATTEMPTS_CSV = REPORTS / "ams-rd04-d0b-source-attempts-v1.csv"
SYMBOLS_CSV = REPORTS / "ams-rd04-d0b-symbol-data-status-v1.csv"
AVAILABILITY_CSV = REPORTS / "ams-rd04-d0b-expanded-availability-v1.csv"
CANDIDATES_CSV = REPORTS / "ams-rd04-d0b-venue-eligible-weekly-candidates-v1.csv"
SUMMARY_CSV = REPORTS / "ams-rd04-d0b-weekly-snapshot-summary-v1.csv"
REGISTRATION_JSON = REPORTS / "ams-rd04-d0b-expanded-dataset-registration-v1.json"
REPORT_JSON = REPORTS / "ams-rd04-d0b-pit-venue-data-expansion-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d0b-pit-venue-data-expansion-v1.md"
FINAL_COPY = ROOT / "RD04_D0B_RESULT_FOR_CHATGPT.md"

LEGACY_ENDPOINT = "https://api.kucoin.com/api/v1/market/candles"
UTA_ENDPOINT = "https://api.kucoin.com/api/ua/v1/market/kline"
WINDOW_DAYS = 240
MAX_ATTEMPTS = 5


class LiveExpansionError(RuntimeError):
    """Raised when the live D0B acquisition cannot produce safe evidence."""


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


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(output[column], utc=True, errors="raise").map(
                lambda value: value.isoformat()
            )
    atomic_text(path, output.to_csv(index=False, lineterminator="\n"))


def request_json(endpoint: str, parameters: Mapping[str, str]) -> Any:
    query = urlencode(dict(parameters))
    request = Request(
        f"{endpoint}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "spot-speculation-bot-rd04-d0b/1.0",
        },
        method="GET",
    )
    observed: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(request, timeout=60) as response:
                payload = response.read()
            return json.loads(payload.decode("utf-8"))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            observed.append(f"HTTPError:{error.code}:{body[-500:]}")
            if error.code not in {429, 500, 502, 503, 504}:
                break
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            observed.append(f"{type(error).__name__}:{error}")
        if attempt < MAX_ATTEMPTS:
            time.sleep(float(min(16, 2 ** (attempt - 1))))
    raise LiveExpansionError(f"KuCoin request failed for {endpoint}: {' | '.join(observed[-5:])}")


def endpoint_parameters(
    endpoint_kind: str,
    venue_pair: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, str]:
    common = {
        "symbol": venue_pair,
        "startAt": str(int(start.timestamp())),
        "endAt": str(int(end.timestamp())),
    }
    if endpoint_kind == "legacy":
        return {**common, "type": "4hour"}
    if endpoint_kind == "uta":
        return {
            **common,
            "tradeType": "SPOT",
            "interval": "4hour",
        }
    raise LiveExpansionError(f"Unknown endpoint kind: {endpoint_kind}")


def parse_endpoint_payload(endpoint_kind: str, payload: Any) -> list[list[int | float]]:
    if endpoint_kind == "legacy":
        return parse_legacy_klines(payload)
    if endpoint_kind == "uta":
        return parse_uta_klines(payload)
    raise LiveExpansionError(f"Unknown endpoint kind: {endpoint_kind}")


def probe_endpoint(
    venue_pair: str,
    endpoint_kind: str,
) -> tuple[list[list[int | float]], str | None]:
    endpoint = LEGACY_ENDPOINT if endpoint_kind == "legacy" else UTA_ENDPOINT
    try:
        payload = request_json(
            endpoint,
            endpoint_parameters(
                endpoint_kind,
                venue_pair,
                RESEARCH_START,
                RESEARCH_LOCK,
            ),
        )
        return parse_endpoint_payload(endpoint_kind, payload), None
    except Exception as error:
        return [], f"{type(error).__name__}:{error}"


def pair_cache_path(venue_pair: str) -> Path:
    slug = venue_pair.replace("/", "-").replace(":", "-")
    return RAW_ROOT / slug / "4h.parquet"


def read_cached_pair(
    path: Path,
    *,
    canonical_symbol: str,
    venue_pair: str,
) -> pd.DataFrame:
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
        raise LiveExpansionError(f"Cached pair {path} is missing columns: {missing}")
    frame["symbol"] = str(canonical_symbol).upper()
    frame["source_symbol"] = venue_pair
    frame["bar_open_time"] = pd.to_datetime(frame["bar_open_time"], utc=True)
    frame["bar_close_time"] = pd.to_datetime(frame["bar_close_time"], utc=True)
    return frame.sort_values("bar_open_time", kind="stable").reset_index(drop=True)


def fetch_pair_history(
    *,
    canonical_symbol: str,
    venue_pair: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    path = pair_cache_path(venue_pair)
    if path.is_file():
        cached = read_cached_pair(
            path,
            canonical_symbol=canonical_symbol,
            venue_pair=venue_pair,
        )
        return cached, {
            "canonical_symbol": canonical_symbol,
            "venue_pair": venue_pair,
            "status": "CACHE_HIT",
            "endpoint_kind": "cached",
            "row_count": len(cached),
            "cache_path": path.relative_to(ROOT).as_posix(),
            "error": "",
        }

    selected_endpoint_kind: str | None = None
    selected_rows: dict[int, list[int | float]] = {}
    endpoint_errors: list[str] = []
    successful_empty_endpoint_count = 0

    for candidate_kind in ("legacy", "uta"):
        endpoint = LEGACY_ENDPOINT if candidate_kind == "legacy" else UTA_ENDPOINT
        rows_by_timestamp: dict[int, list[int | float]] = {}
        window_errors: list[str] = []
        window_start = RESEARCH_START
        while window_start < RESEARCH_LOCK:
            window_end = min(
                RESEARCH_LOCK,
                window_start + pd.Timedelta(days=WINDOW_DAYS),
            )
            try:
                payload = request_json(
                    endpoint,
                    endpoint_parameters(
                        candidate_kind,
                        venue_pair,
                        window_start,
                        window_end,
                    ),
                )
                rows = parse_endpoint_payload(candidate_kind, payload)
                for row in rows:
                    rows_by_timestamp[int(row[0])] = row
            except Exception as error:
                window_errors.append(
                    f"{candidate_kind}:{window_start.isoformat()}:{type(error).__name__}:{error}"
                )
            window_start = window_end
            time.sleep(0.08)

        if window_errors:
            endpoint_errors.extend(window_errors)
            continue
        if rows_by_timestamp:
            selected_endpoint_kind = candidate_kind
            selected_rows = rows_by_timestamp
            break
        successful_empty_endpoint_count += 1

    if selected_endpoint_kind is None:
        status = (
            "NO_KUCOIN_HISTORY" if successful_empty_endpoint_count else "SOURCE_REQUEST_INCOMPLETE"
        )
        return pd.DataFrame(), {
            "canonical_symbol": canonical_symbol,
            "venue_pair": venue_pair,
            "status": status,
            "endpoint_kind": "",
            "row_count": 0,
            "cache_path": "",
            "error": " | ".join(endpoint_errors[-5:]),
        }

    ordered_rows = [selected_rows[key] for key in sorted(selected_rows)]
    frame = normalized_4h_frame(
        ordered_rows,
        canonical_symbol=canonical_symbol,
        source_symbol=venue_pair,
    )
    if frame.empty:
        return frame, {
            "canonical_symbol": canonical_symbol,
            "venue_pair": venue_pair,
            "status": "NO_KUCOIN_HISTORY",
            "endpoint_kind": selected_endpoint_kind,
            "row_count": 0,
            "cache_path": "",
            "error": "",
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, compression="zstd")
    return frame, {
        "canonical_symbol": canonical_symbol,
        "venue_pair": venue_pair,
        "status": "ACQUIRED",
        "endpoint_kind": selected_endpoint_kind,
        "row_count": len(frame),
        "cache_path": path.relative_to(ROOT).as_posix(),
        "error": "",
    }


def acquire_symbol(
    canonical_symbol: str,
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
    pair_frames: list[pd.DataFrame] = []
    attempts: list[dict[str, Any]] = []
    for venue_pair in venue_pair_candidates(canonical_symbol):
        frame, attempt = fetch_pair_history(
            canonical_symbol=canonical_symbol,
            venue_pair=venue_pair,
        )
        attempts.append(attempt)
        if attempt["status"] in {"ACQUIRED", "CACHE_HIT"} and not frame.empty:
            pair_frames.append(frame)
    merged, transitions = merge_alias_frames(canonical_symbol, pair_frames)
    validation = validate_symbol_frame(merged)
    invalid_transition_count = sum(not bool(record["valid"]) for record in transitions)
    status = str(validation["status"])
    if any(attempt["status"] == "SOURCE_REQUEST_INCOMPLETE" for attempt in attempts):
        status = "SOURCE_REQUEST_INCOMPLETE"
    if invalid_transition_count:
        status = "INVALID_ALIAS_TRANSITION"
    record = {
        "canonical_symbol": canonical_symbol,
        "status": status,
        "row_count": int(validation["row_count"]),
        "first_bar_open_time": validation["first_bar_open_time"],
        "last_bar_close_time": validation["last_bar_close_time"],
        "missing_internal_bar_count": int(validation["missing_internal_bar_count"]),
        "source_pairs": ",".join(sorted(set(merged["source_symbol"].astype(str))))
        if not merged.empty
        else "",
        "alias_transition_count": len(transitions),
        "invalid_alias_transition_count": invalid_transition_count,
    }
    return merged, record, attempts


def combine_frames(
    original: pd.DataFrame,
    additions: Sequence[pd.DataFrame],
) -> pd.DataFrame:
    frames = [original.copy(), *[frame.copy() for frame in additions if not frame.empty]]
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined["bar_open_time"] = pd.to_datetime(combined["bar_open_time"], utc=True, errors="raise")
    combined["bar_close_time"] = pd.to_datetime(
        combined["bar_close_time"], utc=True, errors="raise"
    )
    combined = combined.sort_values(["symbol", "bar_open_time"], kind="stable").drop_duplicates(
        ["symbol", "bar_open_time"], keep="first"
    )
    return combined.reset_index(drop=True)


def save_availability(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, compression="zstd")
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "file_sha256": file_sha256(path),
        "row_count": len(frame),
        "symbol_count": int(frame["symbol"].astype(str).nunique()),
    }


def markdown(report: Mapping[str, Any]) -> str:
    decision = report["decision"]
    acquisition = report["acquisition_summary"]
    validation = report["validation"]
    lines = [
        "# AMS RD04-D0B — Point-in-Time Venue Data Expansion",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        f"- Weekly snapshots: `{decision['snapshot_count']}`",
        f"- Complete venue-eligible top-30 snapshots: `{decision['complete_snapshot_count']}`",
        f"- Minimum selected count: `{decision['minimum_selected_count']}`",
        f"- Acquisition symbols attempted: `{acquisition['attempted_symbol_count']}`",
        f"- Complete acquired symbols: `{acquisition['complete_symbol_count']}`",
        f"- Symbols without KuCoin history: `{acquisition['no_data_symbol_count']}`",
        f"- Expanded dataset symbols: `{acquisition['expanded_symbol_count']}`",
        f"- Financial invariance: `{validation['financial_invariance']}`",
        f"- RD04-D1 replay research authorized: "
        f"`{decision['rd04_d1_pit_universe_replay_research_authorized']}`",
        "- Universe change authorized: `NO`",
        "- Trade logic changed: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Source contract",
        "",
        "- KuCoin Spot 4H public candles are requested directly by venue pair.",
        "- Both the legacy Spot candle endpoint and the UTA Spot kline endpoint are supported.",
        "- Current market-list membership is not required before probing historical candles.",
        "- Missing candles are never forward-filled or price-filled.",
        "- Disconnected candle segments become separate observed availability intervals.",
        "- The original registered AMS-V3 dataset is not overwritten.",
        "",
        "## Decision meaning",
        "",
        f"- `{DECISION_READY}` authorizes only RD04-D1 full-portfolio replay research.",
        f"- `{DECISION_MORE_DATA}` authorizes only another source-expansion stage.",
        f"- `{DECISION_BLOCKED}` means acquired data failed an immutable integrity gate.",
        "",
        "## Safety boundary",
        "",
        (
            "- No ranking, alignment, weight, entry, exit, fill, or "
            "portfolio cash decision is changed."
        ),
        "- No 2025 test data or 2026 holdout data are accessed.",
        (
            "- No production, live trading, MD02, Kelly, leverage, "
            "pyramiding, or averaging down is authorized."
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    frames, original_hashes = load_registered_data()
    if not MARKET_CAP_RAW.is_file():
        raise LiveExpansionError("Frozen Coin Metrics market-cap payload is missing.")
    if not STABLECOIN_RAW.is_file():
        raise LiveExpansionError("Frozen stablecoin catalogue is missing.")

    market_cap_bytes = MARKET_CAP_RAW.read_bytes()
    market_cap_payload = decode_json_bytes(market_cap_bytes, source="Coin Metrics RD04-D0B")
    raw_panel = parse_market_cap_panel(market_cap_payload)

    stablecoin_bytes = STABLECOIN_RAW.read_bytes()
    stablecoin_payload = decode_json_bytes(stablecoin_bytes, source="DefiLlama RD04-D0B")
    stablecoin_symbols = parse_stablecoin_symbols(stablecoin_payload)

    d0a_panel, _ = normalize_market_cap_panel(raw_panel, stablecoin_symbols)
    repaired_panel, identity_audit = repair_canonical_panel(d0a_panel)
    ranked_pool, pool_summary = build_ranked_weekly_pool(
        repaired_panel,
        list(rebalance_schedule()),
    )

    registered_symbols = sorted(
        set(frames["four_hour"]["symbol"].astype(str).str.upper())
        & set(frames["eight_hour"]["symbol"].astype(str).str.upper())
        & set(frames["daily"]["symbol"].astype(str).str.upper())
        & set(frames["availability"]["symbol"].astype(str).str.upper())
    )
    acquisition_manifest = build_acquisition_manifest(
        ranked_pool,
        registered_symbols,
    )

    acquired_frames: dict[str, pd.DataFrame] = {}
    acquired_eight_hour: dict[str, pd.DataFrame] = {}
    acquired_daily: dict[str, pd.DataFrame] = {}
    symbol_records: list[dict[str, Any]] = []
    attempt_records: list[dict[str, Any]] = []
    incomplete_8h_groups = 0
    incomplete_1d_groups = 0
    total_symbols = len(acquisition_manifest)
    for position, row in enumerate(
        acquisition_manifest.itertuples(index=False),
        start=1,
    ):
        symbol = str(row.canonical_symbol)
        print(
            f"RD04_D0B_SYMBOL={position}/{total_symbols}:{symbol}",
            flush=True,
        )
        frame, record, attempts = acquire_symbol(symbol)
        attempt_records.extend(attempts)
        if record["status"] == "COMPLETE":
            try:
                eight, incomplete_8h = dataset_builder.resample_complete(
                    frame,
                    rule="8h",
                    expected_four_hour_bars=2,
                )
                daily, incomplete_1d = dataset_builder.resample_complete(
                    frame,
                    rule="1D",
                    expected_four_hour_bars=6,
                )
            except Exception as error:
                record["status"] = "INSUFFICIENT_DERIVED_BARS"
                record["derivation_error"] = f"{type(error).__name__}:{error}"
            else:
                acquired_frames[symbol] = frame
                acquired_eight_hour[symbol] = eight
                acquired_daily[symbol] = daily
                incomplete_8h_groups += int(incomplete_8h)
                incomplete_1d_groups += int(incomplete_1d)
        symbol_records.append(record)

    new_four_hour_frames = list(acquired_frames.values())
    expanded_four_hour = combine_frames(
        frames["four_hour"],
        new_four_hour_frames,
    )
    assert_spot_ohlcv(expanded_four_hour)

    new_eight_hour_frames = list(acquired_eight_hour.values())
    new_daily_frames = list(acquired_daily.values())

    expanded_eight_hour = combine_frames(
        frames["eight_hour"],
        new_eight_hour_frames,
    )
    expanded_daily = combine_frames(
        frames["daily"],
        new_daily_frames,
    )
    assert_spot_ohlcv(expanded_eight_hour)
    assert_spot_ohlcv(expanded_daily)

    acquired_availability = build_availability_frame(acquired_frames)
    original_availability = frames["availability"].copy()
    original_availability["tradable_from"] = pd.to_datetime(
        original_availability["tradable_from"], utc=True, errors="raise"
    )
    original_availability["tradable_until"] = pd.to_datetime(
        original_availability["tradable_until"], utc=True, errors="raise"
    )
    expanded_availability = (
        pd.concat(
            [original_availability, acquired_availability],
            ignore_index=True,
            sort=False,
        )
        .sort_values(["symbol", "tradable_from"], kind="stable")
        .reset_index(drop=True)
    )

    dataset_symbols = sorted(
        set(expanded_four_hour["symbol"].astype(str).str.upper())
        & set(expanded_eight_hour["symbol"].astype(str).str.upper())
        & set(expanded_daily["symbol"].astype(str).str.upper())
        & set(expanded_availability["symbol"].astype(str).str.upper())
    )
    selected, snapshot_summary = select_venue_eligible_top30(
        ranked_pool,
        expanded_availability,
        dataset_symbols,
    )

    integrity_failures = [
        record
        for record in symbol_records
        if record["status"] not in {"COMPLETE", "NO_DATA", "INSUFFICIENT_DERIVED_BARS"}
    ]
    decision = build_expansion_decision(
        snapshot_summary,
        integrity_failure_count=len(integrity_failures),
    )

    fingerprints: list[dict[str, Any]] = []
    observed_trade_count = 0
    for fold_id, start, end in FOLDS:
        result = simulate_md01_fold(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id="MD01-M05",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=0.002,
        )
        before = financial_fingerprint(result)
        after = financial_fingerprint(result)
        if result.status != "PASS":
            raise LiveExpansionError(f"Fold {fold_id} is not reconciled.")
        if before != after:
            raise LiveExpansionError(f"RD04-D0B mutated fold {fold_id}.")
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

    financial_invariance = all(bool(item["invariant"]) for item in fingerprints)
    validation = validate_expansion_evidence(
        selected,
        snapshot_summary,
        expected_trade_count=EXPECTED_TRADES,
        observed_trade_count=observed_trade_count,
        financial_invariance=financial_invariance,
        decision=str(decision["decision"]),
    )
    if validation["status"] != "COMPLETE":
        raise LiveExpansionError(f"RD04-D0B evidence validation failed: {validation}")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    datasets = {
        "four_hour": dataset_builder.save_dataset(
            expanded_four_hour,
            FOUR_HOUR_PATH,
        ),
        "eight_hour": dataset_builder.save_dataset(
            expanded_eight_hour,
            EIGHT_HOUR_PATH,
        ),
        "daily": dataset_builder.save_dataset(
            expanded_daily,
            DAILY_PATH,
        ),
        "availability": save_availability(
            expanded_availability,
            AVAILABILITY_PATH,
        ),
    }

    symbols_frame = pd.DataFrame(symbol_records)
    attempts_frame = pd.DataFrame(attempt_records)
    complete_symbol_count = (
        int(symbols_frame["status"].eq("COMPLETE").sum()) if not symbols_frame.empty else 0
    )
    no_data_symbol_count = (
        int(symbols_frame["status"].eq("NO_DATA").sum()) if not symbols_frame.empty else 0
    )
    acquisition_summary = {
        "attempted_symbol_count": len(symbols_frame),
        "complete_symbol_count": complete_symbol_count,
        "no_data_symbol_count": no_data_symbol_count,
        "integrity_failure_count": len(integrity_failures),
        "expanded_symbol_count": len(dataset_symbols),
        "incomplete_8h_group_count": incomplete_8h_groups,
        "incomplete_1d_group_count": incomplete_1d_groups,
    }

    registration = {
        "schema_version": "ams-rd04-d0b-expanded-dataset-registration-v1",
        "status": "PASS",
        "source_commit": source_commit(),
        "registered_at": datetime.now(tz=UTC).isoformat(),
        "exchange": "kucoin",
        "market_type": "spot",
        "quote_asset": "USDT",
        "source_timeframe": "4h",
        "derived_timeframes": ["8h", "1d"],
        "research_start": RESEARCH_START.isoformat(),
        "research_end_exclusive": RESEARCH_LOCK.isoformat(),
        "registered_symbol_count": len(dataset_symbols),
        "datasets": datasets,
        "original_registered_dataset_hashes": original_hashes,
        "decision": decision,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "trading_logic_changed": False,
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D0B",
        "status": "COMPLETE",
        "source_commit": source_commit(),
        "variant_id": "MD01-M05",
        "upstream": {
            "rd04_d0a_evidence_commit": "be06c32cc3b7ae4647040e1d505a7e9d2be38576",
            "rd04_d0a_decision": "NORMALIZED_PIT_UNIVERSE_DATA_EXPANSION_REQUIRED",
        },
        "raw_sources": {
            "coinmetrics_market_cap": {
                "path": MARKET_CAP_RAW.relative_to(ROOT).as_posix(),
                "bytes": len(market_cap_bytes),
                "sha256": sha256_bytes(market_cap_bytes),
            },
            "defillama_stablecoin_catalogue": {
                "path": STABLECOIN_RAW.relative_to(ROOT).as_posix(),
                "bytes": len(stablecoin_bytes),
                "sha256": sha256_bytes(stablecoin_bytes),
            },
            "kucoin_legacy_endpoint": LEGACY_ENDPOINT,
            "kucoin_uta_endpoint": UTA_ENDPOINT,
        },
        "identity_summary": {
            "overlay_audit_rows": len(identity_audit),
            "excluded_identity_rows": int(identity_audit["identity_excluded"].astype(bool).sum()),
            "aliased_identity_rows": int(
                identity_audit["identity_overlay_rule"].eq("D0B_EXPLICIT_ALIAS").sum()
            ),
            "repaired_canonical_assets": int(repaired_panel["canonical_asset"].nunique()),
        },
        "ranked_pool_summary": {
            "weekly_snapshots": len(pool_summary),
            "minimum_ranked_assets": int(pool_summary["ranked_asset_count"].min()),
            "maximum_ranked_assets": int(pool_summary["ranked_asset_count"].max()),
            "ranked_pool_rows": len(ranked_pool),
        },
        "acquisition_summary": acquisition_summary,
        "decision": decision,
        "validation": validation,
        "financial_fingerprints": fingerprints,
        "datasets": datasets,
        "outputs": {
            "identity_overlay_audit": IDENTITY_CSV.relative_to(ROOT).as_posix(),
            "weekly_ranked_pool": POOL_CSV.relative_to(ROOT).as_posix(),
            "acquisition_manifest": ACQUISITION_CSV.relative_to(ROOT).as_posix(),
            "source_attempts": ATTEMPTS_CSV.relative_to(ROOT).as_posix(),
            "symbol_data_status": SYMBOLS_CSV.relative_to(ROOT).as_posix(),
            "expanded_availability": AVAILABILITY_CSV.relative_to(ROOT).as_posix(),
            "venue_eligible_weekly_candidates": CANDIDATES_CSV.relative_to(ROOT).as_posix(),
            "weekly_snapshot_summary": SUMMARY_CSV.relative_to(ROOT).as_posix(),
            "expanded_dataset_registration": REGISTRATION_JSON.relative_to(ROOT).as_posix(),
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

    write_csv(IDENTITY_CSV, identity_audit)
    write_csv(POOL_CSV, ranked_pool)
    write_csv(ACQUISITION_CSV, acquisition_manifest)
    write_csv(ATTEMPTS_CSV, attempts_frame)
    write_csv(SYMBOLS_CSV, symbols_frame)
    write_csv(AVAILABILITY_CSV, expanded_availability)
    write_csv(CANDIDATES_CSV, selected)
    write_csv(SUMMARY_CSV, snapshot_summary)
    atomic_json(REGISTRATION_JSON, finite(registration))
    atomic_json(REPORT_JSON, finite(report))
    review = markdown(report)
    atomic_text(REPORT_MD, review)
    atomic_text(FINAL_COPY, review)

    print("RD04_D0B_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"SNAPSHOT_COUNT={decision['snapshot_count']}")
    print(f"COMPLETE_SNAPSHOTS={decision['complete_snapshot_count']}")
    print(f"MINIMUM_SELECTED_COUNT={decision['minimum_selected_count']}")
    print(f"ACQUISITION_SYMBOLS_ATTEMPTED={acquisition_summary['attempted_symbol_count']}")
    print(f"COMPLETE_ACQUIRED_SYMBOLS={acquisition_summary['complete_symbol_count']}")
    print(f"NO_DATA_SYMBOLS={acquisition_summary['no_data_symbol_count']}")
    print(f"EXPANDED_DATASET_SYMBOLS={acquisition_summary['expanded_symbol_count']}")
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
