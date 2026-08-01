from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.ccxt_adapter import CCXTExchangeAdapter
from spotbot.data.provider import CCXTSpotDataProvider
from spotbot.data.store import ParquetCandleStore
from spotbot.research.rd16c_common import (
    BRANCH,
    LOCAL_INPUT_ROOT,
    ROOT,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
    verify_local_dataset_hashes,
)
from spotbot.research.rd16d_common import write_csv, write_json
from spotbot.research.rd16r_universe import (
    ARCHITECTURE_ID,
    CORE_SYMBOLS,
    DOWNLOAD_SINCE,
    EXCHANGE_ID,
    SEALED_UNTIL,
    TIMEFRAMES,
    UNIVERSE_BY_ID,
    UNIVERSE_REGISTRY,
    UniverseCandidate,
    assess_symbol_coverage,
    assign_liquidity_tiers,
    candidate_registry_rows,
    classify_research_readiness,
    resolve_universe,
    validation_payload,
)

SCHEMA_VERSION: Final = "rd16r-universe-expansion-liquidity-tier-research-v1"
DECISION: Final = "RD16R_UNIVERSE_EXPANSION_AND_LIQUIDITY_TIER_RESEARCH_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "EXPANDED_SPOT_UNIVERSE_AND_LIQUIDITY_EVIDENCE_EXTRACTED"

RD16P_ROOT: Final = ROOT / "data" / "research" / "rd16p"
RD16Q_ROOT: Final = ROOT / "data" / "research" / "rd16q"
RD16R_ROOT: Final = ROOT / "data" / "research" / "rd16r"
RD16R_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16r"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

UNIVERSE_FIELDS: Final = (
    "canonical_id",
    "aliases",
    "category",
    "core",
    "rationale",
)
MARKET_FIELDS: Final = (
    "canonical_id",
    "aliases",
    "category",
    "core",
    "resolved_symbol",
    "market_status",
)
COVERAGE_FIELDS: Final = (
    "canonical_id",
    "resolved_symbol",
    "category",
    "core",
    "available_timeframe_count",
    "hourly_rows",
    "four_hour_rows",
    "daily_rows",
    "weekly_rows",
    "first_hourly_timestamp",
    "last_hourly_timestamp",
    "history_days",
    "median_daily_quote_volume",
    "sealed_cutoff_respected",
    "eligible",
    "eligibility_failures",
)
TIER_FIELDS: Final = (
    *COVERAGE_FIELDS,
    "liquidity_rank",
    "liquidity_tier",
    "tier_decision",
)
ELIGIBLE_FIELDS: Final = (
    "liquidity_rank",
    "liquidity_tier",
    "canonical_id",
    "resolved_symbol",
    "category",
    "core",
    "median_daily_quote_volume",
    "hourly_rows",
    "daily_rows",
    "first_hourly_timestamp",
    "last_hourly_timestamp",
)
FAILURE_FIELDS: Final = (
    "canonical_id",
    "resolved_symbol",
    "timeframe",
    "failure_stage",
    "attempts",
    "error_type",
    "error_message",
)


class RD16REvaluationError(RuntimeError):
    pass


def _verify_rd16q_ready() -> dict[str, Any]:
    report = read_json_object(RD16Q_ROOT / "rd16q-final-report-v1.json")
    expected = {
        "decision": "RD16Q_SIGNAL_DOMAIN_EXPANSION_AND_ALTERNATIVE_DATA_RESEARCH_COMPLETED",
        "architecture_id": ARCHITECTURE_ID,
        "domains_evaluated": 5,
        "retained_domain_count": 0,
        "promising_domain_count": 0,
        "strategic_objective_met_count": 0,
        "next_stage": "RD16R_UNIVERSE_EXPANSION_AND_LIQUIDITY_TIER_RESEARCH",
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16REvaluationError(f"RD16-Q readiness mismatch for {key}: {report.get(key)!r}")
    return report


def _verify_rd16q_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16Q_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16REvaluationError("RD16-Q output hash manifest is invalid.")
        data_path = RD16Q_ROOT / raw_name
        report_path = REPORTS_ROOT / raw_name
        path = data_path if data_path.is_file() else report_path
        if not path.is_file():
            raise RD16REvaluationError(f"Missing RD16-Q output: {raw_name}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16REvaluationError(f"RD16-Q output hash mismatch: {raw_name}")
        verified[f"rd16q:{raw_name}"] = actual
    return verified


def _frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16q/rd16q-final-report-v1.json": RD16Q_ROOT / "rd16q-final-report-v1.json",
        "rd16q/validation-report.json": RD16Q_ROOT / "validation-report.json",
        "rd16q/output-hashes.json": RD16Q_ROOT / "output-hashes.json",
        "rd16q/domain-summary.csv": RD16Q_ROOT / "domain-summary.csv",
        "rd16p/rd16p-final-report-v1.json": RD16P_ROOT / "rd16p-final-report-v1.json",
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16REvaluationError(f"Frozen RD16-R input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16q_outputs())
    hashes.update(verify_local_dataset_hashes(LOCAL_INPUT_ROOT))
    return dict(sorted(hashes.items()))


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _dataset_manifest_entry(
    *,
    candidate: UniverseCandidate,
    symbol: str,
    timeframe: str,
    frame: pd.DataFrame,
    store: ParquetCandleStore,
    acquisition_source: str,
) -> dict[str, object]:
    data_path = store.dataset_path(
        exchange_id=EXCHANGE_ID,
        symbol=symbol,
        timeframe=timeframe,
    )
    metadata_path = store.metadata_path(data_path)
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    return {
        "canonical_id": candidate.canonical_id,
        "resolved_symbol": symbol,
        "timeframe": timeframe,
        "acquisition_source": acquisition_source,
        "logical_data_path": data_path.relative_to(RD16R_LOCAL_ROOT).as_posix(),
        "logical_metadata_path": metadata_path.relative_to(RD16R_LOCAL_ROOT).as_posix(),
        "rows": len(frame),
        "first_timestamp": _timestamp(timestamps.iloc[0]).isoformat(),
        "last_timestamp": _timestamp(timestamps.iloc[-1]).isoformat(),
        "file_sha256": sha256_path(data_path),
        "metadata_sha256": sha256_path(metadata_path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _reuse_target_dataset(
    *,
    store: ParquetCandleStore,
    symbol: str,
    timeframe: str,
) -> pd.DataFrame | None:
    try:
        frame = store.load(
            exchange_id=EXCHANGE_ID,
            symbol=symbol,
            timeframe=timeframe,
            verify_integrity=True,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return None
    if frame.empty:
        return None
    maximum = _timestamp(frame["timestamp"].max())
    if maximum > pd.Timestamp(SEALED_UNTIL):
        return None
    return frame


def _copy_core_dataset(
    *,
    candidate: UniverseCandidate,
    symbol: str,
    timeframe: str,
    source_store: ParquetCandleStore,
    target_store: ParquetCandleStore,
) -> tuple[pd.DataFrame, str]:
    frame = source_store.load(
        exchange_id=EXCHANGE_ID,
        symbol=symbol,
        timeframe=timeframe,
        verify_integrity=True,
    )
    target_store.save(
        frame,
        exchange_id=EXCHANGE_ID,
        symbol=symbol,
        timeframe=timeframe,
        overwrite=True,
    )
    verified = target_store.load(
        exchange_id=EXCHANGE_ID,
        symbol=symbol,
        timeframe=timeframe,
        verify_integrity=True,
    )
    if len(verified) != len(frame):
        raise RD16REvaluationError(
            f"Core dataset row mismatch for {candidate.canonical_id} {timeframe}."
        )
    return verified, "COPIED_FROZEN_RD16B_CORE"


def _download_dataset(
    *,
    symbol: str,
    timeframe: str,
    provider: CCXTSpotDataProvider,
    target_store: ParquetCandleStore,
) -> tuple[pd.DataFrame, str, int]:
    reused = _reuse_target_dataset(
        store=target_store,
        symbol=symbol,
        timeframe=timeframe,
    )
    if reused is not None:
        return reused, "REUSED_VERIFIED_RD16R_LOCAL", 0

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            history = provider.fetch_history(
                symbol=symbol,
                timeframe=timeframe,
                since=DOWNLOAD_SINCE,
                until=SEALED_UNTIL,
                page_limit=1_000,
            )
            target_store.save(
                history.frame,
                exchange_id=EXCHANGE_ID,
                symbol=symbol,
                timeframe=timeframe,
                overwrite=True,
            )
            verified = target_store.load(
                exchange_id=EXCHANGE_ID,
                symbol=symbol,
                timeframe=timeframe,
                verify_integrity=True,
            )
            return verified, "DOWNLOADED_PUBLIC_KUCOIN_SPOT", attempt
        except Exception as error:  # noqa: BLE001 - per-market failure is evidence, not stage failure.
            last_error = error
            if attempt < 3:
                time.sleep(float(attempt))
    if last_error is None:
        raise RD16REvaluationError(f"Unknown download failure for {symbol} {timeframe}.")
    raise last_error


def _unavailable_coverage(
    candidate: UniverseCandidate,
    *,
    resolved_symbol: str | None,
    failure: str,
) -> dict[str, object]:
    return {
        "canonical_id": candidate.canonical_id,
        "resolved_symbol": resolved_symbol,
        "category": candidate.category,
        "core": candidate.core,
        "available_timeframe_count": 0,
        "hourly_rows": 0,
        "four_hour_rows": 0,
        "daily_rows": 0,
        "weekly_rows": 0,
        "first_hourly_timestamp": None,
        "last_hourly_timestamp": None,
        "history_days": None,
        "median_daily_quote_volume": None,
        "sealed_cutoff_respected": True,
        "eligible": False,
        "eligibility_failures": failure,
    }


def _output_hashes(paths: Sequence[Path]) -> dict[str, str]:
    return {path.name: sha256_path(path) for path in paths}


def _write_reports(
    *,
    final_report: Mapping[str, object],
    tier_rows: Sequence[Mapping[str, object]],
    failure_rows: Sequence[Mapping[str, object]],
) -> list[Path]:
    results_path = REPORTS_ROOT / "rd16r-universe-expansion-results-v1.md"
    tiers_path = REPORTS_ROOT / "rd16r-liquidity-tier-decisions-v1.md"
    audit_path = REPORTS_ROOT / "rd16r-data-acquisition-causality-audit-v1.md"

    results_lines = [
        "# RD16-R Universe Expansion Results",
        "",
        f"- Decision: `{final_report['decision']}`",
        f"- Registered candidates: {final_report['registered_candidate_count']}",
        f"- Resolved active Spot markets: {final_report['resolved_market_count']}",
        f"- Eligible assets: {final_report['eligible_asset_count']}",
        f"- Eligible non-core assets: {final_report['eligible_noncore_asset_count']}",
        f"- Readiness: `{final_report['research_readiness']}`",
        f"- Next: `{final_report['next_stage']}`",
        "",
    ]
    results_path.write_text("\n".join(results_lines), encoding="utf-8", newline="\n")

    tiers_lines = ["# RD16-R Liquidity Tier Decisions", ""]
    for tier in ("A", "B", "C"):
        rows = [row for row in tier_rows if row.get("liquidity_tier") == tier]
        tiers_lines.extend([f"## Tier {tier}", ""])
        if not rows:
            tiers_lines.append("- No eligible assets.")
        for row in rows:
            tiers_lines.append(
                "- "
                f"{row['canonical_id']} (`{row['resolved_symbol']}`), "
                f"rank {row['liquidity_rank']}, median daily quote volume "
                f"{float(cast(float, row['median_daily_quote_volume'])):,.2f} USDT."
            )
        tiers_lines.append("")
    tiers_path.write_text("\n".join(tiers_lines), encoding="utf-8", newline="\n")

    audit_lines = [
        "# RD16-R Data Acquisition and Causality Audit",
        "",
        "- Public KuCoin Spot OHLCV only.",
        "- No credentials or trading methods are used.",
        "- Download range begins 2020-01-01 UTC and ends exclusively at 2025-01-01 UTC.",
        "- 2025 test data and 2026 holdout data remain sealed.",
        "- Core six datasets are copied from the verified frozen RD16-B store.",
        (
            "- Non-core acquisition failures are classified per market and "
            "timeframe rather than aborting the stage."
        ),
        "- Liquidity tiers use fixed ranks from median daily approximate quote volume.",
        f"- Recorded acquisition failure rows: {len(failure_rows)}.",
        "",
    ]
    audit_path.write_text("\n".join(audit_lines), encoding="utf-8", newline="\n")
    return [results_path, tiers_path, audit_path]


def run_rd16r_research() -> dict[str, object]:
    source_report = _verify_rd16q_ready()
    frozen_hashes = _frozen_input_hashes()

    RD16R_ROOT.mkdir(parents=True, exist_ok=True)
    RD16R_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    adapter = CCXTExchangeAdapter(EXCHANGE_ID)
    provider = CCXTSpotDataProvider(adapter)
    source_store = ParquetCandleStore(LOCAL_INPUT_ROOT)
    target_store = ParquetCandleStore(RD16R_LOCAL_ROOT)

    market_discovery_error: Exception | None = None
    try:
        markets = adapter.load_markets()
    except Exception as error:  # noqa: BLE001 - core research can still complete offline.
        market_discovery_error = error
        markets = {}

    market_rows = resolve_universe(markets)
    if market_discovery_error is not None:
        for row in market_rows:
            canonical = str(row["canonical_id"])
            candidate = UNIVERSE_BY_ID[canonical]
            if candidate.core:
                row["resolved_symbol"] = candidate.aliases[0]
                row["market_status"] = "FROZEN_CORE_AVAILABLE_WITHOUT_MARKET_DISCOVERY"

    coverage_rows: list[dict[str, object]] = []
    failure_rows: list[dict[str, object]] = []
    dataset_manifest_rows: list[dict[str, object]] = []

    if market_discovery_error is not None:
        failure_rows.append(
            {
                "canonical_id": "__MARKET_DISCOVERY__",
                "resolved_symbol": None,
                "timeframe": "ALL",
                "failure_stage": "LOAD_MARKETS",
                "attempts": 1,
                "error_type": type(market_discovery_error).__name__,
                "error_message": str(market_discovery_error),
            }
        )

    market_by_id = {str(row["canonical_id"]): row for row in market_rows}
    for candidate in UNIVERSE_REGISTRY:
        market_row = market_by_id[candidate.canonical_id]
        raw_symbol = market_row.get("resolved_symbol")
        symbol = str(raw_symbol) if isinstance(raw_symbol, str) else None
        if symbol is None:
            coverage_rows.append(
                _unavailable_coverage(
                    candidate,
                    resolved_symbol=None,
                    failure="market_unavailable_or_inactive",
                )
            )
            continue

        frames: dict[str, pd.DataFrame] = {}
        for timeframe in TIMEFRAMES:
            try:
                if candidate.core and symbol in CORE_SYMBOLS:
                    frame, acquisition_source = _copy_core_dataset(
                        candidate=candidate,
                        symbol=symbol,
                        timeframe=timeframe,
                        source_store=source_store,
                        target_store=target_store,
                    )
                    attempts = 1
                else:
                    frame, acquisition_source, attempts = _download_dataset(
                        symbol=symbol,
                        timeframe=timeframe,
                        provider=provider,
                        target_store=target_store,
                    )
                frames[timeframe] = frame
                entry = _dataset_manifest_entry(
                    candidate=candidate,
                    symbol=symbol,
                    timeframe=timeframe,
                    frame=frame,
                    store=target_store,
                    acquisition_source=acquisition_source,
                )
                entry["attempts"] = attempts
                dataset_manifest_rows.append(entry)
            except Exception as error:  # noqa: BLE001 - classify each failed dataset.
                failure_rows.append(
                    {
                        "canonical_id": candidate.canonical_id,
                        "resolved_symbol": symbol,
                        "timeframe": timeframe,
                        "failure_stage": (
                            "COPY_FROZEN_CORE" if candidate.core else "DOWNLOAD_OR_VERIFY"
                        ),
                        "attempts": 1 if candidate.core else 3,
                        "error_type": type(error).__name__,
                        "error_message": str(error),
                    }
                )

        if frames:
            coverage_rows.append(
                assess_symbol_coverage(
                    candidate=candidate,
                    resolved_symbol=symbol,
                    frames=frames,
                )
            )
        else:
            coverage_rows.append(
                _unavailable_coverage(
                    candidate,
                    resolved_symbol=symbol,
                    failure="no_verified_timeframes",
                )
            )

    tier_rows = assign_liquidity_tiers(coverage_rows)
    readiness, next_stage = classify_research_readiness(tier_rows)
    eligible_rows = [row for row in tier_rows if row.get("eligible") is True]
    noncore_rows = [row for row in eligible_rows if row.get("core") is not True]
    resolved_count = sum(isinstance(row.get("resolved_symbol"), str) for row in market_rows)
    tier_counts = {
        tier: sum(row.get("liquidity_tier") == tier for row in eligible_rows)
        for tier in ("A", "B", "C")
    }

    registry_path = RD16R_ROOT / "universe-registry.csv"
    market_path = RD16R_ROOT / "market-availability.csv"
    coverage_path = RD16R_ROOT / "data-coverage.csv"
    tier_path = RD16R_ROOT / "liquidity-tier-summary.csv"
    eligible_path = RD16R_ROOT / "eligible-universe.csv"
    failures_path = RD16R_ROOT / "acquisition-failures.csv"
    frozen_path = RD16R_ROOT / "frozen-input-hashes.json"
    local_manifest_path = RD16R_ROOT / "local-data-manifest-v1.json"
    validation_path = RD16R_ROOT / "validation-report.json"
    final_path = RD16R_ROOT / "rd16r-final-report-v1.json"
    output_hashes_path = RD16R_ROOT / "output-hashes.json"

    eligible_output_rows = [
        {field: row.get(field) for field in ELIGIBLE_FIELDS}
        for row in sorted(
            eligible_rows,
            key=lambda item: int(cast(int, item["liquidity_rank"])),
        )
    ]

    write_csv(registry_path, candidate_registry_rows(), fieldnames=UNIVERSE_FIELDS)
    write_csv(market_path, market_rows, fieldnames=MARKET_FIELDS)
    write_csv(coverage_path, coverage_rows, fieldnames=COVERAGE_FIELDS)
    write_csv(tier_path, tier_rows, fieldnames=TIER_FIELDS)
    write_csv(eligible_path, eligible_output_rows, fieldnames=ELIGIBLE_FIELDS)
    write_csv(failures_path, failure_rows, fieldnames=FAILURE_FIELDS)
    write_json(frozen_path, frozen_hashes)
    write_json(
        local_manifest_path,
        {
            "schema_version": SCHEMA_VERSION,
            "root_committed": False,
            "local_root": RD16R_LOCAL_ROOT.relative_to(ROOT).as_posix(),
            "datasets": dataset_manifest_rows,
        },
    )

    validation = validation_payload(
        registered_count=len(UNIVERSE_REGISTRY),
        resolved_count=resolved_count,
        eligible_count=len(eligible_rows),
        all_outputs_classified=len(tier_rows) == len(UNIVERSE_REGISTRY),
    )
    validation.update(
        {
            "frozen_inputs_verified": True,
            "rd16q_ready": True,
            "rd16q_outputs_verified": True,
            "frozen_core_dataset_count": sum(
                row.get("acquisition_source") == "COPIED_FROZEN_RD16B_CORE"
                for row in dataset_manifest_rows
            ),
            "downloaded_or_reused_noncore_dataset_count": sum(
                row.get("acquisition_source") != "COPIED_FROZEN_RD16B_CORE"
                for row in dataset_manifest_rows
            ),
        }
    )
    write_json(validation_path, validation)

    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "technical_status": "COMPLETED",
        "architecture_id": ARCHITECTURE_ID,
        "source_stage_decision": source_report["decision"],
        "registered_candidate_count": len(UNIVERSE_REGISTRY),
        "resolved_market_count": resolved_count,
        "eligible_asset_count": len(eligible_rows),
        "eligible_noncore_asset_count": len(noncore_rows),
        "tier_a_count": tier_counts["A"],
        "tier_b_count": tier_counts["B"],
        "tier_c_count": tier_counts["C"],
        "eligible_symbols": [str(row["resolved_symbol"]) for row in eligible_rows],
        "unavailable_or_ineligible_candidates": [
            str(row["canonical_id"]) for row in tier_rows if row.get("eligible") is not True
        ],
        "research_readiness": readiness,
        "next_stage": next_stage,
        "acquisition_failure_count": len(failure_rows),
        "download_since": DOWNLOAD_SINCE.isoformat(),
        "sealed_until": SEALED_UNTIL.isoformat(),
        "strategy_performance_evaluated": False,
        "strategic_objective_evaluated": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "technical_gates": {
            "rd16q_ready": True,
            "rd16q_outputs_verified": True,
            "frozen_inputs_verified": True,
            "all_candidates_classified": len(tier_rows) == len(UNIVERSE_REGISTRY),
            "sealed_cutoff_respected": all(
                row.get("sealed_cutoff_respected") is True for row in coverage_rows
            ),
            "spot_only": True,
            "long_only": True,
            "derivatives_used": False,
            "dune_api_called": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
        },
    }
    write_json(final_path, final_report)

    report_paths = _write_reports(
        final_report=final_report,
        tier_rows=tier_rows,
        failure_rows=failure_rows,
    )
    hashed_paths = [
        registry_path,
        market_path,
        coverage_path,
        tier_path,
        eligible_path,
        failures_path,
        frozen_path,
        local_manifest_path,
        validation_path,
        final_path,
        *report_paths,
    ]
    write_json(output_hashes_path, _output_hashes(hashed_paths))
    return final_report


__all__ = [
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "RD16REvaluationError",
    "SCHEMA_VERSION",
    "run_rd16r_research",
]
