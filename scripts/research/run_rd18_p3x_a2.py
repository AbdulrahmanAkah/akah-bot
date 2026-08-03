from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.data.store import ParquetCandleStore  # noqa: E402
from spotbot.research.rd16c_common import dataframe_content_hash  # noqa: E402
from spotbot.research.rd18_p3x_a1 import (  # noqa: E402
    SEALED_CUTOFF,
    load_json,
    sha256_path,
    symbol_to_pair,
    write_csv,
)
from spotbot.research.rd18_p3x_a2_generator import (  # noqa: E402
    COMPRESSION_ENGINE_ID,
    STAGE,
    SUMMARY_FIELDS,
    TREND_ENGINE_ID,
    deterministic_manifest,
    generate_symbol,
    validate_eligibility_ledger,
    write_json,
)

EXPECTED_PAIRS = 364
EXPECTED_READY = 341
EXPECTED_HISTORICAL = 21
EXPECTED_CORPORATE = 2
EXPECTED_MONTHS = 73
EXPECTED_A1B_ROWS = EXPECTED_PAIRS * EXPECTED_MONTHS
TIMEFRAMES = ("1h", "4h", "1d", "1w")
ALLOWED_NONREADY_ACTIONS = {
    "NETWORK_MARKET_PROBE_REQUIRED",
    "HISTORICAL_MARKET_SOURCE_REQUIRED",
}
OUTPUT_FLAGS = {
    "network_requests": 0,
    "raw_market_data_written": False,
    "synthetic_candles_written": False,
    "normalization_executed": False,
    "strategy_candidate_generation_executed": True,
    "strategy_replay_executed": False,
    "trade_routing_executed": False,
    "return_calculation_executed": False,
    "threshold_optimization_executed": False,
    "production_authorized": False,
}


class A2RunnerError(RuntimeError):
    """Raised when A2 local generation cannot continue safely."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Build resumable RD18-P3X-A2 pre-router C2 signal candidates "
            "from local sealed data, A1B monthly eligibility, and A1C exclusions."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--a1-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1_runtime",
    )
    result.add_argument(
        "--a1b-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1b_runtime",
    )
    result.add_argument(
        "--a1c-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1c_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a2_runtime",
    )
    result.add_argument(
        "--write-ledgers",
        action="store_true",
        help="Required acknowledgement for local deterministic runtime writes.",
    )
    result.add_argument(
        "--resume",
        action="store_true",
        help="Reuse verified completed symbol partitions from the A2 checkpoint.",
    )
    result.add_argument(
        "--preflight-only",
        action="store_true",
        help="Validate all upstream contracts without generating partitions.",
    )
    result.add_argument(
        "--progress-every",
        type=int,
        default=10,
    )
    return result


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise A2RunnerError(f"required CSV is missing: {path}")
    return pd.read_csv(path)


def _read_plan(path: Path) -> pd.DataFrame:
    frame = _read_csv(path)
    required = {"pair", "symbol", "logical_path", "action"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise A2RunnerError(f"A1 plan columns missing: {missing}")
    if len(frame) != EXPECTED_PAIRS:
        raise A2RunnerError(f"expected {EXPECTED_PAIRS} A1 plan rows, found {len(frame)}")
    if bool(frame["pair"].duplicated().any()):
        raise A2RunnerError("A1 plan pairs are not unique")
    return frame.sort_values("pair", kind="stable").reset_index(drop=True)


def _plan_contract(plan: pd.DataFrame) -> dict[str, object]:
    counts = Counter(plan["action"].astype(str).tolist())
    ready = int(counts.get("READY_LOCAL", 0))
    corporate = int(counts.get("CORPORATE_ACTION_POLICY_REQUIRED", 0))
    nonready = sum(int(counts.get(action, 0)) for action in ALLOWED_NONREADY_ACTIONS)
    unsupported = sorted(
        action
        for action in counts
        if action
        not in {
            "READY_LOCAL",
            "CORPORATE_ACTION_POLICY_REQUIRED",
            *ALLOWED_NONREADY_ACTIONS,
        }
    )
    if unsupported:
        raise A2RunnerError(f"unsupported A1 plan actions: {unsupported}")
    if ready != EXPECTED_READY or corporate != EXPECTED_CORPORATE:
        raise A2RunnerError(f"A1 plan count mismatch: ready={ready}, corporate={corporate}")
    if nonready != EXPECTED_HISTORICAL:
        raise A2RunnerError(f"expected {EXPECTED_HISTORICAL} historical blocks, found {nonready}")
    return {
        "action_counts": dict(sorted(counts.items())),
        "ready_pairs": ready,
        "historical_pairs": nonready,
        "corporate_action_pairs": corporate,
    }


def _validate_a1b(
    runtime: Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    report_path = runtime / "rd18-p3x-a1b-runtime-report-v1.json"
    ledger_path = runtime / "monthly-asset-eligibility-ledger.csv"
    report = load_json(report_path)
    if report.get("passed") is not True:
        raise A2RunnerError("A1B report is not passed")
    if report.get("symbols") != EXPECTED_PAIRS:
        raise A2RunnerError("A1B symbol count differs from 364")
    if report.get("months") != EXPECTED_MONTHS:
        raise A2RunnerError("A1B month count differs from 73")
    authorizations = report.get("authorizations")
    if not isinstance(authorizations, dict):
        raise A2RunnerError("A1B authorizations are missing")
    if authorizations.get("strategy_replay") is not False:
        raise A2RunnerError("A1B replay authorization drifted")
    ledger = validate_eligibility_ledger(
        _read_csv(ledger_path),
        expected_symbols=EXPECTED_PAIRS,
        expected_months=EXPECTED_MONTHS,
    )
    if len(ledger) != EXPECTED_A1B_ROWS:
        raise A2RunnerError(f"expected {EXPECTED_A1B_ROWS} A1B rows, found {len(ledger)}")
    return ledger, report


def _validate_a1c(
    runtime: Path,
) -> tuple[frozenset[str], dict[str, object]]:
    report_path = runtime / "rd18-p3x-a1c-runtime-report-v1.json"
    terminal_path = runtime / "corporate-action-terminal-classification.csv"
    report = load_json(report_path)
    if report.get("passed") is not True:
        raise A2RunnerError("A1C report is not passed")
    if report.get("decision") != ("RD18_P3X_A1C_COMPLETE_WITH_EXPLICIT_EXCLUSIONS"):
        raise A2RunnerError("A1C decision differs from explicit exclusions")
    terminal = _read_csv(terminal_path)
    required = {"pair", "strategy_use_authorized"}
    missing = sorted(required.difference(terminal.columns))
    if missing:
        raise A2RunnerError(f"A1C terminal columns missing: {missing}")
    pairs = frozenset(terminal["pair"].astype(str).tolist())
    if pairs != frozenset({"ETN-USDT", "STRAX-USDT"}):
        raise A2RunnerError(f"A1C excluded pair set mismatch: {sorted(pairs)}")
    authorized = terminal["strategy_use_authorized"].astype(str).str.lower()
    if bool(authorized.isin({"true", "1", "yes"}).any()):
        raise A2RunnerError("A1C terminal pair is strategy authorized")
    return pairs, report


def _input_hashes(
    repo: Path,
    a1: Path,
    a1b: Path,
    a1c: Path,
) -> dict[str, str]:
    paths = {
        "a1_plan": a1 / "full-c2-hourly-acquisition-plan.csv",
        "a1b_eligibility": a1b / "monthly-asset-eligibility-ledger.csv",
        "a1b_report": a1b / "rd18-p3x-a1b-runtime-report-v1.json",
        "a1c_terminal": a1c / "corporate-action-terminal-classification.csv",
        "a1c_report": a1c / "rd18-p3x-a1c-runtime-report-v1.json",
        "generator_module": (repo / "src/spotbot/research/rd18_p3x_a2_generator.py"),
        "rd16c_features": repo / "src/spotbot/research/rd16c_features.py",
        "rd16c_families": repo / "src/spotbot/research/rd16c_families.py",
        "rd16d_metrics": repo / "src/spotbot/research/rd16d_metrics.py",
        "rd16e_components": repo / "src/spotbot/research/rd16e_components.py",
    }
    result: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise A2RunnerError(f"input hash path missing: {path}")
        result[name] = sha256_path(path)
    return dict(sorted(result.items()))


def _digest_mapping(values: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for key, value in sorted(values.items()):
        digest.update(key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _checkpoint_path(output: Path) -> Path:
    return output / "generation-checkpoint.json"


def _load_checkpoint(
    output: Path,
    *,
    input_digest: str,
    resume: bool,
) -> dict[str, Any]:
    path = _checkpoint_path(output)
    if not path.is_file():
        return {
            "schema_version": "rd18-p3x-a2-generation-checkpoint-v1",
            "input_digest": input_digest,
            "completed": {},
        }
    if not resume:
        raise A2RunnerError("A2 checkpoint already exists; use --resume or choose a new output")
    checkpoint = load_json(path)
    if checkpoint.get("schema_version") != ("rd18-p3x-a2-generation-checkpoint-v1"):
        raise A2RunnerError("A2 checkpoint schema mismatch")
    if checkpoint.get("input_digest") != input_digest:
        raise A2RunnerError("A2 checkpoint input digest mismatch")
    completed = checkpoint.get("completed")
    if not isinstance(completed, dict):
        raise A2RunnerError("A2 checkpoint completed object is invalid")
    return checkpoint


def _atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    write_json(temporary, payload)
    os.replace(temporary, path)


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    frame.to_parquet(temporary, index=False, engine="pyarrow")
    os.replace(temporary, path)


def _partition_paths(
    output: Path,
    pair: str,
) -> tuple[Path, Path, Path]:
    root = output / "partitions" / pair
    return (
        root / "candidates.parquet",
        root / "audit.parquet",
        root / "summary.json",
    )


def _source_hashes(
    store: ParquetCandleStore,
    *,
    symbol: str,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for timeframe in TIMEFRAMES:
        path = store.dataset_path(
            exchange_id="kucoin",
            symbol=symbol,
            timeframe=timeframe,
        )
        if not path.is_file():
            raise A2RunnerError(f"READY_LOCAL dataset is missing: {symbol} {timeframe}")
        result[timeframe] = sha256_path(path)
    return result


def _completed_entry_valid(
    entry: dict[str, object],
    *,
    source_hashes: dict[str, str],
    candidate_path: Path,
    audit_path: Path,
    summary_path: Path,
) -> bool:
    if entry.get("source_hashes") != source_hashes:
        return False
    for path, key in (
        (candidate_path, "candidate_file_sha256"),
        (audit_path, "audit_file_sha256"),
        (summary_path, "summary_file_sha256"),
    ):
        expected = entry.get(key)
        if not isinstance(expected, str) or not path.is_file():
            return False
        if sha256_path(path) != expected:
            return False
    return True


def _process_symbol(
    *,
    repo: Path,
    output: Path,
    store: ParquetCandleStore,
    row: dict[str, object],
    eligibility: pd.DataFrame,
    excluded_pairs: frozenset[str],
) -> dict[str, object]:
    pair = str(row["pair"])
    symbol = str(row["symbol"])
    if symbol_to_pair(symbol) != pair:
        raise A2RunnerError(f"plan pair/symbol mismatch: {pair}, {symbol}")
    if pair in excluded_pairs:
        raise A2RunnerError(f"A1C excluded pair marked READY_LOCAL: {pair}")

    frames = {
        timeframe: store.load(
            exchange_id="kucoin",
            symbol=symbol,
            timeframe=timeframe,
            verify_integrity=True,
        )
        for timeframe in TIMEFRAMES
    }
    for timeframe, frame in frames.items():
        timestamps = pd.to_datetime(
            frame["timestamp"],
            utc=True,
            errors="raise",
        )
        if bool((timestamps > pd.Timestamp(SEALED_CUTOFF)).any()):
            raise A2RunnerError(f"post-2024 rows detected: {symbol} {timeframe}")

    symbol_eligibility = eligibility.loc[eligibility["symbol"].astype(str) == symbol].copy()
    if len(symbol_eligibility) != EXPECTED_MONTHS:
        raise A2RunnerError(
            f"{symbol}: expected {EXPECTED_MONTHS} A1B rows, found {len(symbol_eligibility)}"
        )

    result = generate_symbol(
        frames,
        symbol=symbol,
        eligibility=symbol_eligibility,
        excluded_pairs=excluded_pairs,
    )
    candidate_path, audit_path, summary_path = _partition_paths(
        output,
        pair,
    )
    _atomic_parquet(candidate_path, result.candidates)
    _atomic_parquet(audit_path, result.audit)
    _atomic_json(summary_path, result.summary)

    source_hashes = _source_hashes(store, symbol=symbol)
    return {
        "pair": pair,
        "symbol": symbol,
        "source_hashes": source_hashes,
        "candidate_path": candidate_path.relative_to(output).as_posix(),
        "audit_path": audit_path.relative_to(output).as_posix(),
        "summary_path": summary_path.relative_to(output).as_posix(),
        "candidate_rows": len(result.candidates),
        "audit_rows": len(result.audit),
        "candidate_content_sha256": dataframe_content_hash(result.candidates),
        "audit_content_sha256": dataframe_content_hash(result.audit),
        "candidate_file_sha256": sha256_path(candidate_path),
        "audit_file_sha256": sha256_path(audit_path),
        "summary_file_sha256": sha256_path(summary_path),
    }


def _aggregate(
    output: Path,
    completed: dict[str, object],
    *,
    input_hashes: dict[str, str],
    preflight: dict[str, object],
) -> dict[str, object]:
    symbol_rows: list[dict[str, object]] = []
    candidate_index_rows: list[dict[str, object]] = []
    monthly_counter: Counter[tuple[str, str, str, str]] = Counter()
    rejection_counter: Counter[tuple[str, str, str]] = Counter()
    total_candidates = 0
    total_audit = 0
    generation_status_counts: Counter[str] = Counter()
    no_feature_pairs: list[str] = []

    for pair in sorted(completed):
        raw_entry = completed[pair]
        if not isinstance(raw_entry, dict):
            raise A2RunnerError(f"invalid completed checkpoint row: {pair}")
        entry = cast(dict[str, object], raw_entry)
        summary_path = output / str(entry["summary_path"])
        candidate_path = output / str(entry["candidate_path"])
        audit_path = output / str(entry["audit_path"])
        summary = load_json(summary_path)
        status = str(summary.get("generation_status", ""))
        reason = str(summary.get("generation_reason", ""))
        if status not in {
            "GENERATED",
            "NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP",
        }:
            raise A2RunnerError(f"invalid generation status for {pair}: {status!r}")
        if status == "GENERATED" and reason:
            raise A2RunnerError(f"generated symbol has a rejection reason: {pair}")
        if status == "NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP":
            if reason != "NO_ROWS_AFTER_RD16C_CAUSAL_FEATURE_WARMUP":
                raise A2RunnerError(f"no-feature reason differs for {pair}: {reason!r}")
            no_feature_pairs.append(pair)
        generation_status_counts[status] += 1
        symbol_rows.append(summary)

        candidates = pd.read_parquet(candidate_path)
        audit = pd.read_parquet(audit_path)
        total_candidates += len(candidates)
        total_audit += len(audit)

        candidate_index_rows.append(
            {
                "pair": pair,
                "symbol": str(entry["symbol"]),
                "candidate_path": str(entry["candidate_path"]),
                "audit_path": str(entry["audit_path"]),
                "summary_path": str(entry["summary_path"]),
                "candidate_rows": len(candidates),
                "audit_rows": len(audit),
                "candidate_content_sha256": str(entry["candidate_content_sha256"]),
                "audit_content_sha256": str(entry["audit_content_sha256"]),
                "candidate_file_sha256": str(entry["candidate_file_sha256"]),
                "audit_file_sha256": str(entry["audit_file_sha256"]),
                "summary_file_sha256": str(entry["summary_file_sha256"]),
            }
        )

        if not candidates.empty:
            for raw_month, raw_engine, raw_family, raw_regime in candidates.loc[
                :,
                [
                    "signal_month",
                    "engine_id",
                    "family_id",
                    "market_regime",
                ],
            ].itertuples(index=False, name=None):
                monthly_counter[
                    (
                        str(raw_month),
                        str(raw_engine),
                        str(raw_family),
                        str(raw_regime),
                    )
                ] += 1

        if not audit.empty:
            working = audit.copy()
            working["signal_month"] = (
                pd.to_datetime(
                    working["signal_close"],
                    utc=True,
                    errors="raise",
                )
                .dt.tz_localize(None)
                .dt.to_period("M")
                .dt.to_timestamp()
                .dt.tz_localize("UTC")
                .map(lambda value: pd.Timestamp(value).isoformat())
            )
            for raw_month, raw_family, raw_reason in working.loc[
                :,
                ["signal_month", "family_id", "rejection_reason"],
            ].itertuples(index=False, name=None):
                rejection_counter[
                    (
                        str(raw_month),
                        str(raw_family),
                        str(raw_reason),
                    )
                ] += 1

    symbol_summary_path = output / "symbol-generation-summary.csv"
    write_csv(
        symbol_summary_path,
        symbol_rows,
        SUMMARY_FIELDS,
    )

    candidate_index_fields = (
        "pair",
        "symbol",
        "candidate_path",
        "audit_path",
        "summary_path",
        "candidate_rows",
        "audit_rows",
        "candidate_content_sha256",
        "audit_content_sha256",
        "candidate_file_sha256",
        "audit_file_sha256",
        "summary_file_sha256",
    )
    candidate_index_path = output / "candidate-partition-index.csv"
    write_csv(
        candidate_index_path,
        candidate_index_rows,
        candidate_index_fields,
    )

    monthly_rows = [
        {
            "signal_month": month,
            "engine_id": engine,
            "family_id": family,
            "market_regime": regime,
            "candidate_count": count,
        }
        for (month, engine, family, regime), count in sorted(monthly_counter.items())
    ]
    monthly_path = output / "monthly-candidate-summary.csv"
    write_csv(
        monthly_path,
        monthly_rows,
        (
            "signal_month",
            "engine_id",
            "family_id",
            "market_regime",
            "candidate_count",
        ),
    )

    rejection_rows = [
        {
            "signal_month": month,
            "family_id": family,
            "rejection_reason": reason,
            "row_count": count,
        }
        for (month, family, reason), count in sorted(rejection_counter.items())
    ]
    rejection_path = output / "monthly-rejection-summary.csv"
    write_csv(
        rejection_path,
        rejection_rows,
        (
            "signal_month",
            "family_id",
            "rejection_reason",
            "row_count",
        ),
    )

    report = {
        "schema_version": "rd18-p3x-a2-runtime-report-v1",
        "stage": STAGE,
        "passed": True,
        "sealed_cutoff": pd.Timestamp(SEALED_CUTOFF).isoformat(),
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "generator_scope": "PRE_ROUTER_SIGNAL_CANDIDATES",
        "ready_symbols_processed": len(completed),
        "expected_ready_symbols": EXPECTED_READY,
        "raw_signal_rows": total_audit,
        "selected_candidate_rows": total_candidates,
        "generation_status_counts": dict(sorted(generation_status_counts.items())),
        "no_feature_pairs": sorted(no_feature_pairs),
        "no_feature_symbol_count": len(no_feature_pairs),
        "engine_candidate_counts": {
            TREND_ENGINE_ID: sum(
                count
                for (month, engine, family, regime), count in monthly_counter.items()
                if engine == TREND_ENGINE_ID
            ),
            COMPRESSION_ENGINE_ID: sum(
                count
                for (month, engine, family, regime), count in monthly_counter.items()
                if engine == COMPRESSION_ENGINE_ID
            ),
        },
        "a1b_gate_applied": True,
        "a1c_exclusions_applied": ["ETN-USDT", "STRAX-USDT"],
        "upstream_preflight": preflight,
        "input_hashes": input_hashes,
        "authorizations": {
            "strategy_candidate_generation": True,
            "strategy_replay": False,
            "trade_routing": False,
            "return_calculation": False,
            "threshold_optimization": False,
            "production": False,
            "post_2024_access": False,
        },
        "next_stage": "RD18_P3X_A3_SEALED_REPLAY_AUTHORIZATION_REVIEW",
    }
    report_path = output / "rd18-p3x-a2-runtime-report-v1.json"
    write_json(report_path, report)

    manifest_names = [
        "symbol-generation-summary.csv",
        "candidate-partition-index.csv",
        "monthly-candidate-summary.csv",
        "monthly-rejection-summary.csv",
        "rd18-p3x-a2-runtime-report-v1.json",
        "generation-checkpoint.json",
    ]
    for entry in candidate_index_rows:
        manifest_names.extend(
            [
                str(entry["candidate_path"]),
                str(entry["audit_path"]),
                str(entry["summary_path"]),
            ]
        )
    manifest = deterministic_manifest(
        output,
        manifest_names,
        flags=OUTPUT_FLAGS,
    )
    manifest_path = output / "output-manifest.json"
    write_json(manifest_path, manifest)

    return {
        **report,
        "output_dir": str(output),
        "output_manifest": str(manifest_path),
        "partition_index": str(candidate_index_path),
    }


def main() -> int:
    args = parser().parse_args()
    if not args.preflight_only and not args.write_ledgers:
        raise SystemExit("A2 generation requires --write-ledgers")
    if args.progress_every <= 0:
        raise SystemExit("--progress-every must be positive")

    repo = args.repo_root.resolve()
    a1 = args.a1_runtime.resolve()
    a1b = args.a1b_runtime.resolve()
    a1c = args.a1c_runtime.resolve()
    output = args.output_dir.resolve()

    plan = _read_plan(a1 / "full-c2-hourly-acquisition-plan.csv")
    plan_summary = _plan_contract(plan)
    eligibility, a1b_report = _validate_a1b(a1b)
    excluded_pairs, a1c_report = _validate_a1c(a1c)
    ready = plan.loc[plan["action"].astype(str) == "READY_LOCAL"].copy()
    ready_pairs = frozenset(ready["pair"].astype(str).tolist())
    if ready_pairs.intersection(excluded_pairs):
        raise A2RunnerError("A1 READY_LOCAL intersects A1C explicit exclusions")

    eligible_symbols = frozenset(
        eligibility.loc[eligibility["eligible"], "symbol"].astype(str).tolist()
    )
    unknown_eligible = sorted(
        symbol_to_pair(symbol)
        for symbol in eligible_symbols
        if symbol_to_pair(symbol) not in ready_pairs
    )
    if unknown_eligible:
        raise A2RunnerError("A1B marks non-ready symbols eligible: " + ", ".join(unknown_eligible))

    preflight = {
        "plan": plan_summary,
        "a1b": {
            "rows": len(eligibility),
            "eligible_rows": int(eligibility["eligible"].sum()),
            "symbols": int(eligibility["symbol"].nunique()),
            "months": int(eligibility["month_start"].nunique()),
            "report_schema": a1b_report.get("schema_version"),
        },
        "a1c": {
            "excluded_pairs": sorted(excluded_pairs),
            "report_schema": a1c_report.get("schema_version"),
        },
        "frozen_engines": [
            TREND_ENGINE_ID,
            COMPRESSION_ENGINE_ID,
        ],
        "scope": "PRE_ROUTER_SIGNAL_CANDIDATES",
        "network_requests": 0,
        "strategy_replay": False,
        "return_calculation": False,
    }

    if args.preflight_only:
        print(json.dumps(preflight, indent=2, sort_keys=True))
        return 0

    output.mkdir(parents=True, exist_ok=True)
    input_hashes = _input_hashes(repo, a1, a1b, a1c)
    input_digest = _digest_mapping(input_hashes)
    checkpoint = _load_checkpoint(
        output,
        input_digest=input_digest,
        resume=args.resume,
    )
    completed_raw = checkpoint["completed"]
    if not isinstance(completed_raw, dict):
        raise A2RunnerError("checkpoint completed object is invalid")
    completed = cast(dict[str, object], completed_raw)

    store = ParquetCandleStore(repo / "data/raw/rd16b")
    rows = ready.to_dict(orient="records")
    for index, raw_row in enumerate(rows, start=1):
        row = cast(dict[str, object], raw_row)
        pair = str(row["pair"])
        symbol = str(row["symbol"])
        candidate_path, audit_path, summary_path = _partition_paths(
            output,
            pair,
        )
        source_hashes = _source_hashes(store, symbol=symbol)

        raw_existing = completed.get(pair)
        existing = cast(dict[str, object], raw_existing) if isinstance(raw_existing, dict) else None
        if existing is not None and _completed_entry_valid(
            existing,
            source_hashes=source_hashes,
            candidate_path=candidate_path,
            audit_path=audit_path,
            summary_path=summary_path,
        ):
            if index % args.progress_every == 0 or index == len(rows):
                print(
                    f"[{index}/{len(rows)}] resume verified: {pair}",
                    flush=True,
                )
            continue

        entry = _process_symbol(
            repo=repo,
            output=output,
            store=store,
            row=row,
            eligibility=eligibility,
            excluded_pairs=excluded_pairs,
        )
        completed[pair] = entry
        checkpoint["completed"] = completed
        checkpoint["input_digest"] = input_digest
        checkpoint["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
        _atomic_json(_checkpoint_path(output), checkpoint)

        if index % args.progress_every == 0 or index == 1 or index == len(rows):
            print(
                f"[{index}/{len(rows)}] {pair}: "
                f"signals={entry['audit_rows']} "
                f"selected={entry['candidate_rows']}",
                flush=True,
            )

    if len(completed) != EXPECTED_READY:
        raise A2RunnerError(f"expected {EXPECTED_READY} completed symbols, found {len(completed)}")

    response = _aggregate(
        output,
        completed,
        input_hashes=input_hashes,
        preflight=preflight,
    )
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
