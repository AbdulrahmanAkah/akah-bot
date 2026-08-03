from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd16c_common import dataframe_content_hash  # noqa: E402
from spotbot.research.rd18_p3x_a1 import (  # noqa: E402
    SEALED_CUTOFF,
    load_json,
    sha256_path,
)
from spotbot.research.rd18_p3x_a2_generator import (  # noqa: E402
    CANDIDATE_FIELDS,
    COMPRESSION_ENGINE_ID,
    FORBIDDEN_OUTCOME_COLUMNS,
    SUMMARY_FIELDS,
    TREND_ENGINE_ID,
)

EXPECTED_READY = 341
EXPECTED_EXCLUSIONS = frozenset({"ETN-USDT", "STRAX-USDT"})


class A2ValidationError(RuntimeError):
    """Raised when A2 runtime evidence fails validation."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Validate RD18-P3X-A2 pre-router C2 generator outputs."
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a2_runtime",
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
    result.add_argument("--offline", action="store_true")
    return result


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise A2ValidationError(f"required CSV is missing: {path}")
    return pd.read_csv(path)


def _manifest_checks(output: Path) -> tuple[dict[str, object], dict[str, bool]]:
    path = output / "output-manifest.json"
    manifest = load_json(path)
    checks: dict[str, bool] = {
        "manifest_schema": manifest.get("schema_version") == "rd18-p3x-a2-output-manifest-v1",
        "manifest_network_zero": manifest.get("network_requests") == 0,
        "manifest_raw_zero": manifest.get("raw_market_data_written") is False,
        "manifest_synthetic_zero": manifest.get("synthetic_candles_written") is False,
        "manifest_normalization_zero": manifest.get("normalization_executed") is False,
        "manifest_generation_true": manifest.get("strategy_candidate_generation_executed") is True,
        "manifest_replay_zero": manifest.get("strategy_replay_executed") is False,
        "manifest_routing_zero": manifest.get("trade_routing_executed") is False,
        "manifest_returns_zero": manifest.get("return_calculation_executed") is False,
        "manifest_optimization_zero": manifest.get("threshold_optimization_executed") is False,
        "manifest_production_zero": manifest.get("production_authorized") is False,
    }
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise A2ValidationError("manifest files object is invalid")
    aggregate = hashlib.sha256()
    names: list[str] = []
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise A2ValidationError("manifest file row is invalid")
        row = cast(dict[str, object], raw)
        name = str(row.get("path", ""))
        file_path = output / name
        names.append(name)
        checks[f"file:{name}"] = file_path.is_file()
        expected_bytes = row.get("bytes")
        checks[f"bytes:{name}"] = (
            isinstance(expected_bytes, int)
            and file_path.is_file()
            and file_path.stat().st_size == expected_bytes
        )
        expected_hash = row.get("sha256")
        checks[f"hash:{name}"] = (
            isinstance(expected_hash, str)
            and file_path.is_file()
            and sha256_path(file_path) == expected_hash
        )
        if isinstance(expected_hash, str):
            aggregate.update(name.encode("utf-8"))
            aggregate.update(b"\0")
            aggregate.update(expected_hash.encode("ascii"))
            aggregate.update(b"\n")
    checks["manifest_paths_unique"] = len(names) == len(set(names))
    checks["manifest_deterministic_hash"] = (
        manifest.get("deterministic_hash") == aggregate.hexdigest()
    )
    return manifest, checks


def _bool_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    if bool(~normalized.isin({"true", "false", "1", "0"}).any()):
        raise A2ValidationError("boolean column contains invalid values")
    return normalized.isin({"true", "1"})


def _normalize_candidate_times(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "4h_context_close",
        "1d_context_close",
        "1w_context_close",
    ):
        if column not in working.columns:
            raise A2ValidationError(f"candidate timestamp column missing: {column}")
        working[column] = pd.to_datetime(
            working[column],
            utc=True,
            errors="raise",
        )
    return working


def _load_eligibility(runtime: Path) -> pd.DataFrame:
    ledger = _read_csv(runtime / "monthly-asset-eligibility-ledger.csv")
    required = {"month_start", "symbol", "eligible"}
    missing = sorted(required.difference(ledger.columns))
    if missing:
        raise A2ValidationError(f"A1B validation columns missing: {missing}")
    ledger = ledger.loc[:, ["month_start", "symbol", "eligible"]].copy()
    ledger["month_start"] = pd.to_datetime(
        ledger["month_start"],
        utc=True,
        errors="raise",
    )
    ledger["eligible"] = _bool_series(ledger["eligible"])
    if bool(ledger.duplicated(["month_start", "symbol"]).any()):
        raise A2ValidationError("A1B validation ledger is not unique")
    return ledger


def _load_exclusions(runtime: Path) -> frozenset[str]:
    terminal = _read_csv(runtime / "corporate-action-terminal-classification.csv")
    if "pair" not in terminal.columns:
        raise A2ValidationError("A1C terminal pair column is missing")
    pairs = frozenset(terminal["pair"].astype(str).tolist())
    if pairs != EXPECTED_EXCLUSIONS:
        raise A2ValidationError(f"A1C exclusions differ: {sorted(pairs)}")
    return pairs


def _candidate_month(values: pd.Series) -> pd.Series:
    return (
        pd.to_datetime(values, utc=True, errors="raise")
        .dt.tz_localize(None)
        .dt.to_period("M")
        .dt.to_timestamp()
        .dt.tz_localize("UTC")
    )


def _validate_candidate_partition(
    candidates: pd.DataFrame,
    *,
    eligibility: pd.DataFrame,
    exclusions: frozenset[str],
    global_ids: set[str],
) -> tuple[
    Counter[tuple[str, str, str, str]],
    list[str],
]:
    if set(candidates.columns) != set(CANDIDATE_FIELDS):
        missing = sorted(set(CANDIDATE_FIELDS).difference(candidates.columns))
        extra = sorted(set(candidates.columns).difference(CANDIDATE_FIELDS))
        raise A2ValidationError(f"candidate schema mismatch; missing={missing}, extra={extra}")
    leaked = sorted(FORBIDDEN_OUTCOME_COLUMNS.intersection(candidates.columns))
    if leaked:
        raise A2ValidationError(f"outcome columns leaked: {leaked}")
    if candidates.empty:
        return Counter(), []

    working = _normalize_candidate_times(candidates)
    ids = working["candidate_id"].astype(str).tolist()
    if len(ids) != len(set(ids)):
        raise A2ValidationError("duplicate candidate IDs inside partition")
    overlap = global_ids.intersection(ids)
    if overlap:
        raise A2ValidationError(f"duplicate candidate IDs across partitions: {sorted(overlap)[:3]}")
    global_ids.update(ids)

    pairs = set(working["pair"].astype(str).tolist())
    if pairs.intersection(exclusions):
        raise A2ValidationError("A1C excluded pair appears in candidates")
    if len(pairs) > 1:
        raise A2ValidationError("candidate partition contains multiple pairs")

    cutoff = pd.Timestamp(SEALED_CUTOFF)
    if bool((working["signal_close"] >= cutoff).any()):
        raise A2ValidationError("candidate signal reaches sealed cutoff")
    if bool((working["entry_bar_close"] > cutoff).any()):
        raise A2ValidationError("candidate entry bar exceeds sealed cutoff")
    for context in (
        "4h_context_close",
        "1d_context_close",
        "1w_context_close",
    ):
        if bool((working[context] > working["signal_close"]).any()):
            raise A2ValidationError(f"future context in {context}")

    for column in (
        "a1b_eligible",
        "a1c_identity_ready",
        "regime_ready",
        "volatility_ready",
        "structure_ready",
        "cooldown_ready",
    ):
        if not bool(_bool_series(working[column]).all()):
            raise A2ValidationError(f"selected candidates fail {column}")

    fee = _bool_series(working["fee_buffer_ready"])
    compression = working["engine_id"].astype(str) == COMPRESSION_ENGINE_ID
    trend = working["engine_id"].astype(str) == TREND_ENGINE_ID
    if bool((compression & ~fee).any()):
        raise A2ValidationError("compression candidate lacks fee buffer")
    if bool((trend & (working["market_regime"].astype(str) != "STRONG_BULL") & ~fee).any()):
        raise A2ValidationError("non-STRONG_BULL trend candidate lacks fee buffer")
    if bool((~(compression | trend)).any()):
        raise A2ValidationError("unknown engine in candidate partition")

    compression_times = working.loc[
        compression,
        "signal_close",
    ].sort_values(kind="stable")
    if len(compression_times) > 1:
        deltas = compression_times.diff().dropna()
        if bool((deltas < pd.Timedelta(hours=24)).any()):
            raise A2ValidationError("compression candidates violate the 24-hour signal cooldown")

    keys = working.loc[:, ["symbol", "signal_close"]].copy()
    keys["month_start"] = _candidate_month(keys["signal_close"])
    merged = keys.merge(
        eligibility,
        on=["month_start", "symbol"],
        how="left",
        validate="many_to_one",
    )
    if bool(merged["eligible"].isna().any()):
        raise A2ValidationError("candidate lacks A1B month decision")
    if not bool(merged["eligible"].astype(bool).all()):
        raise A2ValidationError("candidate month is not A1B eligible")

    monthly: Counter[tuple[str, str, str, str]] = Counter()
    for raw_month, raw_engine, raw_family, raw_regime in working.loc[
        :,
        ["signal_month", "engine_id", "family_id", "market_regime"],
    ].itertuples(index=False, name=None):
        monthly[
            (
                str(raw_month),
                str(raw_engine),
                str(raw_family),
                str(raw_regime),
            )
        ] += 1
    return monthly, ids


def _validate_audit_partition(
    audit: pd.DataFrame,
    candidates: pd.DataFrame,
) -> Counter[tuple[str, str, str]]:
    required = {
        *CANDIDATE_FIELDS,
        "selected_pre_router",
        "rejection_reason",
    }
    if set(audit.columns) != required:
        missing = sorted(required.difference(audit.columns))
        extra = sorted(set(audit.columns).difference(required))
        raise A2ValidationError(f"audit schema mismatch; missing={missing}, extra={extra}")
    if audit.empty:
        if not candidates.empty:
            raise A2ValidationError("nonempty candidates with empty audit")
        return Counter()

    selected = _bool_series(audit["selected_pre_router"])
    reasons = audit["rejection_reason"].astype(str)
    if bool((selected != (reasons == "SELECTED_PRE_ROUTER")).any()):
        raise A2ValidationError("audit selected/reason mismatch")

    audit_selected_ids = set(audit.loc[selected, "candidate_id"].astype(str).tolist())
    candidate_ids = set(candidates["candidate_id"].astype(str).tolist())
    if audit_selected_ids != candidate_ids:
        raise A2ValidationError("candidate partition differs from audit selection")

    working = audit.copy()
    working["signal_month"] = _candidate_month(working["signal_close"]).map(
        lambda value: pd.Timestamp(value).isoformat()
    )
    counts: Counter[tuple[str, str, str]] = Counter()
    for raw_month, raw_family, raw_reason in working.loc[
        :,
        ["signal_month", "family_id", "rejection_reason"],
    ].itertuples(index=False, name=None):
        counts[(str(raw_month), str(raw_family), str(raw_reason))] += 1
    return counts


def _read_counter(
    path: Path,
    *,
    key_fields: tuple[str, ...],
    value_field: str,
) -> Counter[tuple[str, ...]]:
    frame = _read_csv(path)
    required = {*key_fields, value_field}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise A2ValidationError(f"summary columns missing: {missing}")
    result: Counter[tuple[str, ...]] = Counter()
    for raw in frame.to_dict(orient="records"):
        row = cast(dict[str, object], raw)
        key = tuple(str(row[field]) for field in key_fields)
        result[key] += int(row[value_field])
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("A2 validator requires --offline")

    output = args.output_dir.resolve()
    report = load_json(output / "rd18-p3x-a2-runtime-report-v1.json")
    _, checks = _manifest_checks(output)

    checks.update(
        {
            "report_schema": report.get("schema_version") == "rd18-p3x-a2-runtime-report-v1",
            "report_passed": report.get("passed") is True,
            "report_stage": report.get("stage") == "RD18_P3X_A2_C2_GENERATOR_BUILD",
            "report_scope": report.get("generator_scope") == "PRE_ROUTER_SIGNAL_CANDIDATES",
            "report_ready_symbols": report.get("ready_symbols_processed") == EXPECTED_READY,
            "report_a1b_applied": report.get("a1b_gate_applied") is True,
            "report_a1c_applied": set(cast(list[object], report.get("a1c_exclusions_applied", [])))
            == EXPECTED_EXCLUSIONS,
            "report_next_stage": report.get("next_stage")
            == "RD18_P3X_A3_SEALED_REPLAY_AUTHORIZATION_REVIEW",
        }
    )
    authorizations = report.get("authorizations")
    if not isinstance(authorizations, dict):
        raise A2ValidationError("report authorizations object is missing")
    checks.update(
        {
            "generation_authorized": authorizations.get("strategy_candidate_generation") is True,
            "replay_blocked": authorizations.get("strategy_replay") is False,
            "routing_blocked": authorizations.get("trade_routing") is False,
            "returns_blocked": authorizations.get("return_calculation") is False,
            "optimization_blocked": authorizations.get("threshold_optimization") is False,
            "production_blocked": authorizations.get("production") is False,
            "post_2024_blocked": authorizations.get("post_2024_access") is False,
        }
    )

    symbol_summary = _read_csv(output / "symbol-generation-summary.csv")
    summary_missing = sorted(set(SUMMARY_FIELDS).difference(symbol_summary.columns))
    summary_extra = sorted(set(symbol_summary.columns).difference(SUMMARY_FIELDS))
    if summary_missing or summary_extra:
        raise A2ValidationError(
            f"symbol summary schema mismatch; missing={summary_missing}, extra={summary_extra}"
        )
    checks["symbol_summary_rows"] = len(symbol_summary) == EXPECTED_READY
    checks["symbol_summary_pairs_unique"] = not bool(symbol_summary["pair"].duplicated().any())

    statuses = symbol_summary["generation_status"].astype(str)
    reasons = symbol_summary["generation_reason"].fillna("").astype(str)
    valid_statuses = {
        "GENERATED",
        "NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP",
    }
    checks["generation_status_values"] = set(statuses).issubset(valid_statuses)
    generated = statuses == "GENERATED"
    no_feature = statuses == "NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP"
    checks["generated_reason_empty"] = bool((reasons.loc[generated] == "").all())
    checks["no_feature_reason_fixed"] = bool(
        (reasons.loc[no_feature] == "NO_ROWS_AFTER_RD16C_CAUSAL_FEATURE_WARMUP").all()
    )

    count_columns = [
        "raw_signal_rows",
        "selected_candidate_rows",
        "trend_raw_rows",
        "trend_selected_rows",
        "compression_raw_rows",
        "compression_selected_rows",
    ]
    no_feature_counts = symbol_summary.loc[
        no_feature,
        count_columns,
    ].apply(pd.to_numeric, errors="raise")
    checks["no_feature_counts_zero"] = bool((no_feature_counts == 0).all().all())
    checks["no_feature_signal_times_empty"] = bool(
        symbol_summary.loc[
            no_feature,
            ["first_signal_close", "last_signal_close"],
        ]
        .fillna("")
        .astype(str)
        .eq("")
        .all()
        .all()
    )

    observed_status_counts = {
        str(key): int(value) for key, value in statuses.value_counts().to_dict().items()
    }
    report_status_counts = report.get("generation_status_counts")
    checks["generation_status_counts_match"] = isinstance(report_status_counts, dict) and dict(
        sorted(observed_status_counts.items())
    ) == {str(key): int(value) for key, value in sorted(report_status_counts.items())}
    observed_no_feature_pairs = sorted(symbol_summary.loc[no_feature, "pair"].astype(str).tolist())
    report_no_feature_pairs = report.get("no_feature_pairs")
    checks["no_feature_pairs_match"] = isinstance(
        report_no_feature_pairs, list
    ) and observed_no_feature_pairs == sorted(str(value) for value in report_no_feature_pairs)
    checks["no_feature_count_match"] = report.get("no_feature_symbol_count") == len(
        observed_no_feature_pairs
    )

    index = _read_csv(output / "candidate-partition-index.csv")
    required_index = {
        "pair",
        "symbol",
        "candidate_path",
        "audit_path",
        "candidate_rows",
        "audit_rows",
        "candidate_content_sha256",
        "audit_content_sha256",
        "candidate_file_sha256",
        "audit_file_sha256",
    }
    missing_index = sorted(required_index.difference(index.columns))
    if missing_index:
        raise A2ValidationError(f"partition index columns missing: {missing_index}")
    checks["partition_rows"] = len(index) == EXPECTED_READY
    checks["partition_pairs_unique"] = not bool(index["pair"].duplicated().any())

    eligibility = _load_eligibility(args.a1b_runtime.resolve())
    exclusions = _load_exclusions(args.a1c_runtime.resolve())
    global_ids: set[str] = set()
    monthly: Counter[tuple[str, str, str, str]] = Counter()
    rejections: Counter[tuple[str, str, str]] = Counter()
    total_candidates = 0
    total_audit = 0

    for raw in index.to_dict(orient="records"):
        row = cast(dict[str, object], raw)
        candidate_path = output / str(row["candidate_path"])
        audit_path = output / str(row["audit_path"])
        if sha256_path(candidate_path) != str(row["candidate_file_sha256"]):
            raise A2ValidationError(f"candidate file hash mismatch: {candidate_path}")
        if sha256_path(audit_path) != str(row["audit_file_sha256"]):
            raise A2ValidationError(f"audit file hash mismatch: {audit_path}")

        candidates = pd.read_parquet(candidate_path)
        audit = pd.read_parquet(audit_path)
        if len(candidates) != int(row["candidate_rows"]):
            raise A2ValidationError("candidate row count differs from index")
        if len(audit) != int(row["audit_rows"]):
            raise A2ValidationError("audit row count differs from index")
        if dataframe_content_hash(candidates) != str(row["candidate_content_sha256"]):
            raise A2ValidationError("candidate content hash mismatch")
        if dataframe_content_hash(audit) != str(row["audit_content_sha256"]):
            raise A2ValidationError("audit content hash mismatch")

        partition_monthly, _ = _validate_candidate_partition(
            candidates,
            eligibility=eligibility,
            exclusions=exclusions,
            global_ids=global_ids,
        )
        monthly.update(partition_monthly)
        rejections.update(_validate_audit_partition(audit, candidates))
        total_candidates += len(candidates)
        total_audit += len(audit)

    expected_monthly = _read_counter(
        output / "monthly-candidate-summary.csv",
        key_fields=(
            "signal_month",
            "engine_id",
            "family_id",
            "market_regime",
        ),
        value_field="candidate_count",
    )
    expected_rejections = _read_counter(
        output / "monthly-rejection-summary.csv",
        key_fields=(
            "signal_month",
            "family_id",
            "rejection_reason",
        ),
        value_field="row_count",
    )
    checks["monthly_summary_match"] = monthly == expected_monthly
    checks["rejection_summary_match"] = rejections == expected_rejections
    checks["candidate_total_match"] = report.get("selected_candidate_rows") == total_candidates
    checks["audit_total_match"] = report.get("raw_signal_rows") == total_audit
    checks["candidate_ids_unique"] = len(global_ids) == total_candidates

    engine_counts = Counter()
    for (_, engine, _, _), count in monthly.items():
        engine_counts[engine] += count
    report_engine_counts = report.get("engine_candidate_counts")
    checks["engine_counts_match"] = isinstance(report_engine_counts, dict) and dict(
        sorted(engine_counts.items())
    ) == {str(key): int(value) for key, value in sorted(report_engine_counts.items())}
    checks["only_frozen_engines"] = set(engine_counts).issubset(
        {TREND_ENGINE_ID, COMPRESSION_ENGINE_ID}
    )

    passed = all(checks.values())
    response: dict[str, Any] = {
        "schema_version": "rd18-p3x-a2-runtime-validation-v1",
        "passed": passed,
        "output_dir": str(output),
        "checks": dict(sorted(checks.items())),
        "partitions": len(index),
        "candidate_rows": total_candidates,
        "audit_rows": total_audit,
        "unique_candidate_ids": len(global_ids),
        "network_requests": 0,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
