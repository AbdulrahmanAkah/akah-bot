from __future__ import annotations

import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.research import rd16n_evaluation as rd16n
from spotbot.research import rd16q_evaluation as rd16q
from spotbot.research.rd16c_common import (
    BRANCH,
    ROOT,
    SEALED_CUTOFF,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
)
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16d_common import (
    INITIAL_EQUITY,
    STRATEGIC_MONTHLY_TARGET,
    write_csv,
    write_json,
)
from spotbot.research.rd16d_metrics import (
    build_benchmark_daily,
    enrich_trades,
)
from spotbot.research.rd16q_domains import (
    DOMAIN_REGISTRY,
    SignalDomain,
)
from spotbot.research.rd16s_signals import (
    CORE_SYMBOLS,
    ELIGIBLE_SYMBOLS,
    EXPANDED_UNIVERSE_SIZE,
    NONCORE_SYMBOLS,
    SOURCE_UNIVERSE_SIZE,
    build_expanded_domain_candidates,
    build_expanded_internal_frames,
    expanded_domain_registry_rows,
)

SCHEMA_VERSION: Final = "rd16s-limited-expanded-universe-signal-research-v1"
DECISION: Final = "RD16S_LIMITED_EXPANDED_UNIVERSE_SIGNAL_RESEARCH_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "LIMITED_EXPANDED_UNIVERSE_SIGNAL_EVIDENCE_EXTRACTED"
NEXT_ASSEMBLY: Final = "RD16T_COMPOSITE_ALPHA_V4_CANDIDATE_ASSEMBLY_AND_INTERACTION_TEST"
NEXT_REFINEMENT: Final = "RD16T_LIMITED_EXPANDED_UNIVERSE_SIGNAL_REFINEMENT"
NEXT_RESET: Final = "RD16T_SIGNAL_ARCHITECTURE_RESET_AND_LONG_HORIZON_RESEARCH"
ALL_DOMAIN_OVERLAY_ID: Final = "ALL_RD16S_EXPANDED_UNIVERSE_DOMAINS_OVERLAY"

RD16L_ROOT: Final = ROOT / "data" / "research" / "rd16l"
RD16M_ROOT: Final = ROOT / "data" / "research" / "rd16m"
RD16Q_ROOT: Final = ROOT / "data" / "research" / "rd16q"
RD16R_ROOT: Final = ROOT / "data" / "research" / "rd16r"
RD16R_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16r"
RD16S_ROOT: Final = ROOT / "data" / "research" / "rd16s"
RD16S_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16s"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

TIMEFRAMES: Final = ("1h", "4h", "1d", "1w")
LOCAL_DATASET_KEYS: Final = rd16q.LOCAL_DATASET_KEYS

REGISTRY_FIELDS: Final = (
    *rd16q.REGISTRY_FIELDS,
    "source_stage",
    "research_stage",
    "source_universe_size",
    "expanded_universe_size",
    "evaluation_scope",
    "incremental_noncore_assets",
)

SUMMARY_FIELDS: Final = (
    *rd16q.SUMMARY_FIELDS,
    "source_rd16q_candidate_count",
    "source_rd16q_overlay_new_trade_count",
    "source_rd16q_overlay_net_return",
    "source_rd16q_overlay_profit_factor",
    "expanded_delta_candidate_count_vs_rd16q",
    "expanded_delta_overlay_new_trades_vs_rd16q",
    "expanded_delta_overlay_return_vs_rd16q",
    "expanded_delta_overlay_profit_factor_vs_rd16q",
    "noncore_candidate_count",
    "noncore_candidate_assets",
    "noncore_overlay_trade_count",
    "noncore_overlay_net_pnl",
    "noncore_overlay_return_on_initial_equity",
    "noncore_overlay_profit_factor",
    "noncore_overlay_win_rate",
    "tier_a_overlay_trade_count",
    "tier_b_overlay_trade_count",
    "universe_expansion_evidence",
)

DECISION_FIELDS: Final = (
    "domain_id",
    "information_domain",
    "decision",
    "carry_forward",
    "rationale",
    "overlay_delta_net_return_vs_v3",
    "expanded_delta_overlay_return_vs_rd16q",
    "noncore_overlay_trade_count",
    "noncore_overlay_net_pnl",
    "noncore_overlay_profit_factor",
    "universe_expansion_evidence",
)

COMPARISON_FIELDS: Final = (
    "domain_id",
    "source_universe_size",
    "expanded_universe_size",
    "source_candidate_count",
    "expanded_candidate_count",
    "delta_candidate_count",
    "source_overlay_new_trade_count",
    "expanded_overlay_new_trade_count",
    "delta_overlay_new_trade_count",
    "source_overlay_net_return",
    "expanded_overlay_net_return",
    "delta_overlay_net_return",
    "source_overlay_profit_factor",
    "expanded_overlay_profit_factor",
    "delta_overlay_profit_factor",
    "noncore_candidate_count",
    "noncore_overlay_trade_count",
    "noncore_overlay_net_pnl",
    "noncore_overlay_profit_factor",
)

SYMBOL_FIELDS: Final = (
    "scope",
    "domain_id",
    "symbol",
    "canonical_id",
    "core_asset",
    "liquidity_rank",
    "liquidity_tier",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
)

ALL_OVERLAY_FIELDS: Final = (
    *rd16q.ALL_OVERLAY_FIELDS,
    "source_rd16q_new_trade_count",
    "source_rd16q_net_return",
    "source_rd16q_profit_factor",
    "expanded_delta_new_trades_vs_rd16q",
    "expanded_delta_net_return_vs_rd16q",
    "expanded_delta_profit_factor_vs_rd16q",
    "noncore_new_trade_count",
    "noncore_net_pnl",
    "noncore_return_on_initial_equity",
    "noncore_profit_factor",
    "noncore_win_rate",
)


class RD16SEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExpandedDomainDecision:
    decision: str
    carry_forward: bool
    rationale: str
    strategic_objective_met: bool
    universe_expansion_evidence: bool
    gates: dict[str, bool]


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    raw_records = frame.to_dict(orient="records")
    return [{str(key): value for key, value in raw.items()} for raw in raw_records]


def _bool_value(value: object, *, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    raise RD16SEvaluationError(f"{name} must be boolean.")


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _verify_rd16r_ready() -> dict[str, Any]:
    report = read_json_object(RD16R_ROOT / "rd16r-final-report-v1.json")
    expected = {
        "decision": ("RD16R_UNIVERSE_EXPANSION_AND_LIQUIDITY_TIER_RESEARCH_COMPLETED"),
        "technical_status": "COMPLETED",
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "registered_candidate_count": 18,
        "resolved_market_count": 18,
        "eligible_asset_count": EXPANDED_UNIVERSE_SIZE,
        "eligible_noncore_asset_count": len(NONCORE_SYMBOLS),
        "tier_a_count": 6,
        "tier_b_count": 4,
        "tier_c_count": 0,
        "research_readiness": "LIMITED_EXPANDED_UNIVERSE_READY",
        "next_stage": ("RD16S_LIMITED_EXPANDED_UNIVERSE_SIGNAL_RESEARCH"),
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16SEvaluationError(f"RD16-R readiness mismatch for {key}: {report.get(key)!r}")

    eligible = report.get("eligible_symbols")
    if not isinstance(eligible, list):
        raise RD16SEvaluationError("RD16-R eligible symbol list is missing.")
    if tuple(eligible) != ELIGIBLE_SYMBOLS:
        raise RD16SEvaluationError(
            "RD16-R eligible symbols differ from the frozen RD16-S universe."
        )

    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16SEvaluationError("RD16-R technical gates are missing.")
    for key in (
        "all_candidates_classified",
        "frozen_inputs_verified",
        "rd16q_outputs_verified",
        "rd16q_ready",
        "sealed_cutoff_respected",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16SEvaluationError(f"RD16-R technical gate failed: {key}")
    for key in (
        "derivatives_used",
        "dune_api_called",
        "holdout_2026_accessed",
        "optimization_performed",
        "production_authorized",
        "test_2025_accessed",
        "winner_selected",
    ):
        if technical.get(key) is True:
            raise RD16SEvaluationError(f"RD16-R forbidden flag is true: {key}")
    return report


def _verify_output_manifest(
    root: Path,
    *,
    prefix: str,
) -> dict[str, str]:
    manifest = read_json_object(root / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16SEvaluationError(f"{prefix} output hash manifest is invalid.")
        data_path = root / raw_name
        report_path = REPORTS_ROOT / raw_name
        path = data_path if data_path.is_file() else report_path
        if not path.is_file():
            raise RD16SEvaluationError(f"Missing {prefix} output: {raw_name}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16SEvaluationError(f"{prefix} output hash mismatch: {raw_name}")
        verified[f"{prefix.lower()}:{raw_name}"] = actual
    return verified


def _eligible_asset_metadata() -> dict[str, dict[str, object]]:
    path = RD16R_ROOT / "eligible-universe.csv"
    frame = pd.read_csv(path)
    required = {
        "liquidity_rank",
        "liquidity_tier",
        "canonical_id",
        "resolved_symbol",
        "core",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise RD16SEvaluationError(f"RD16-R eligible universe columns missing: {missing}")
    if len(frame) != EXPANDED_UNIVERSE_SIZE:
        raise RD16SEvaluationError("RD16-R eligible universe row count changed.")

    metadata: dict[str, dict[str, object]] = {}
    for row in _records(frame):
        symbol = str(row["resolved_symbol"])
        metadata[symbol] = {
            "canonical_id": str(row["canonical_id"]),
            "core": _bool_value(
                row["core"],
                name=f"core:{symbol}",
            ),
            "liquidity_rank": int(
                rd16q._finite(
                    row["liquidity_rank"],
                    name=f"liquidity_rank:{symbol}",
                )
            ),
            "liquidity_tier": str(row["liquidity_tier"]),
        }

    if tuple(metadata) != ELIGIBLE_SYMBOLS:
        raise RD16SEvaluationError("Eligible-universe ordering or membership changed.")
    return metadata


def _load_expanded_market_frames() -> tuple[
    dict[str, dict[str, pd.DataFrame]],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
    dict[str, str],
    dict[str, dict[str, object]],
]:
    metadata = _eligible_asset_metadata()
    manifest = read_json_object(RD16R_ROOT / "local-data-manifest-v1.json")
    raw_entries = manifest.get("datasets")
    if not isinstance(raw_entries, list):
        raise RD16SEvaluationError("RD16-R local data manifest is invalid.")

    entries: dict[tuple[str, str], dict[str, object]] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise RD16SEvaluationError("RD16-R local data entry is invalid.")
        symbol = raw_entry.get("resolved_symbol")
        timeframe = raw_entry.get("timeframe")
        if isinstance(symbol, str) and isinstance(timeframe, str):
            entries[(symbol, timeframe)] = {str(key): value for key, value in raw_entry.items()}

    store = ParquetCandleStore(RD16R_LOCAL_ROOT)
    all_frames: dict[str, dict[str, pd.DataFrame]] = {}
    hourly_frames: dict[str, pd.DataFrame] = {}
    daily_frames: dict[str, pd.DataFrame] = {}
    verified_hashes: dict[str, str] = {}

    for symbol in ELIGIBLE_SYMBOLS:
        symbol_frames: dict[str, pd.DataFrame] = {}
        for timeframe in TIMEFRAMES:
            entry = entries.get((symbol, timeframe))
            if entry is None:
                raise RD16SEvaluationError(f"Missing RD16-R manifest entry: {symbol} {timeframe}")
            relative_data = entry.get("logical_data_path")
            relative_metadata = entry.get("logical_metadata_path")
            if not isinstance(relative_data, str):
                raise RD16SEvaluationError(f"Invalid data path: {symbol} {timeframe}")
            if not isinstance(relative_metadata, str):
                raise RD16SEvaluationError(f"Invalid metadata path: {symbol} {timeframe}")

            data_path = RD16R_LOCAL_ROOT / relative_data
            metadata_path = RD16R_LOCAL_ROOT / relative_metadata
            expected_file = entry.get("file_sha256")
            expected_metadata = entry.get("metadata_sha256")
            expected_content = entry.get("content_sha256")
            expected_rows = entry.get("rows")
            if not isinstance(expected_file, str):
                raise RD16SEvaluationError("Missing dataset file hash.")
            if not isinstance(expected_metadata, str):
                raise RD16SEvaluationError("Missing metadata file hash.")
            if not isinstance(expected_content, str):
                raise RD16SEvaluationError("Missing dataset content hash.")
            if not isinstance(expected_rows, int):
                raise RD16SEvaluationError("Missing dataset row count.")
            if sha256_path(data_path) != expected_file:
                raise RD16SEvaluationError(f"RD16-R file hash mismatch: {symbol} {timeframe}")
            if sha256_path(metadata_path) != expected_metadata:
                raise RD16SEvaluationError(f"RD16-R metadata hash mismatch: {symbol} {timeframe}")

            frame = store.load(
                exchange_id="kucoin",
                symbol=symbol,
                timeframe=timeframe,
                verify_integrity=True,
            )
            if len(frame) != expected_rows:
                raise RD16SEvaluationError(f"RD16-R row mismatch: {symbol} {timeframe}")
            if dataframe_content_hash(frame) != expected_content:
                raise RD16SEvaluationError(f"RD16-R content hash mismatch: {symbol} {timeframe}")
            maximum = _timestamp(frame["timestamp"].max())
            if maximum > pd.Timestamp(SEALED_CUTOFF):
                raise RD16SEvaluationError(f"Sealed cutoff violation: {symbol} {timeframe}")

            symbol_frames[timeframe] = frame
            verified_hashes[f"local:rd16r:{symbol}:{timeframe}:file"] = expected_file
            verified_hashes[f"local:rd16r:{symbol}:{timeframe}:content"] = expected_content

        all_frames[symbol] = symbol_frames
        hourly_frames[symbol] = symbol_frames["1h"]
        daily_frames[symbol] = symbol_frames["1d"]

    return (
        all_frames,
        hourly_frames,
        daily_frames,
        dict(sorted(verified_hashes.items())),
        metadata,
    )


def _source_rd16q_rows() -> dict[str, dict[str, object]]:
    frame = pd.read_csv(RD16Q_ROOT / "domain-summary.csv")
    rows = {str(row["domain_id"]): row for row in _records(frame)}
    expected = {domain.domain_id for domain in DOMAIN_REGISTRY}
    if set(rows) != expected:
        raise RD16SEvaluationError("RD16-Q source domain summary identities changed.")
    return rows


def _source_rd16q_all_overlay() -> dict[str, object]:
    frame = pd.read_csv(RD16Q_ROOT / "all-domain-overlay-summary.csv")
    if len(frame) != 1:
        raise RD16SEvaluationError("RD16-Q combined overlay summary must have one row.")
    return _records(frame)[0]


def _frozen_input_hashes(
    local_v3_hashes: Mapping[str, str],
    local_rd16r_hashes: Mapping[str, str],
) -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16r/rd16r-final-report-v1.json": (RD16R_ROOT / "rd16r-final-report-v1.json"),
        "rd16r/validation-report.json": (RD16R_ROOT / "validation-report.json"),
        "rd16r/output-hashes.json": RD16R_ROOT / "output-hashes.json",
        "rd16r/eligible-universe.csv": (RD16R_ROOT / "eligible-universe.csv"),
        "rd16r/local-data-manifest-v1.json": (RD16R_ROOT / "local-data-manifest-v1.json"),
        "rd16q/domain-summary.csv": RD16Q_ROOT / "domain-summary.csv",
        "rd16q/all-domain-overlay-summary.csv": (RD16Q_ROOT / "all-domain-overlay-summary.csv"),
        "rd16q/output-hashes.json": RD16Q_ROOT / "output-hashes.json",
        "rd16m/rd16m-final-report-v1.json": (RD16M_ROOT / "rd16m-final-report-v1.json"),
        "rd16l/local-ledger-manifest-v1.json": (RD16L_ROOT / "local-ledger-manifest-v1.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16SEvaluationError(f"Frozen RD16-S input is missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_output_manifest(RD16R_ROOT, prefix="RD16R"))
    hashes.update(_verify_output_manifest(RD16Q_ROOT, prefix="RD16Q"))
    hashes.update(local_v3_hashes)
    hashes.update(local_rd16r_hashes)
    return dict(sorted(hashes.items()))


def _trade_subset_metrics(frame: pd.DataFrame) -> dict[str, object]:
    if frame.empty:
        return {
            "trade_count": 0,
            "net_pnl": 0.0,
            "return_on_initial_equity": 0.0,
            "profit_factor": None,
            "profit_factor_gate": 0.0,
            "win_rate": None,
        }
    pnl = pd.to_numeric(frame["net_pnl"], errors="raise")
    gross_profit = float(pnl[pnl > 0.0].sum())
    gross_loss = abs(float(pnl[pnl < 0.0].sum()))
    output_pf = gross_profit / gross_loss if gross_loss > 0.0 else None
    gate_pf = output_pf if output_pf is not None else (math.inf if gross_profit > 0.0 else 0.0)
    net_pnl = float(pnl.sum())
    return {
        "trade_count": len(frame),
        "net_pnl": net_pnl,
        "return_on_initial_equity": net_pnl / INITIAL_EQUITY,
        "profit_factor": output_pf,
        "profit_factor_gate": gate_pf,
        "win_rate": float((pnl > 0.0).mean()),
    }


def _gate_profit_factor(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16SEvaluationError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16SEvaluationError(f"{name} must be numeric.") from error
    if math.isnan(numeric):
        raise RD16SEvaluationError(f"{name} cannot be NaN.")
    return numeric


def _metadata_columns_present(frame: pd.DataFrame) -> bool:
    required = {
        "canonical_id",
        "core_asset",
        "liquidity_rank",
        "liquidity_tier",
    }
    return required.issubset(frame.columns)


def _symbol_rows(
    frame: pd.DataFrame,
    *,
    scope: str,
    domain_id: str,
) -> list[dict[str, object]]:
    if frame.empty:
        return []
    if not _metadata_columns_present(frame):
        raise RD16SEvaluationError("Trade frame is missing expanded-universe metadata.")

    rows: list[dict[str, object]] = []
    for symbol, group in frame.groupby("symbol", sort=True):
        metrics = _trade_subset_metrics(group)
        first = group.iloc[0]
        rows.append(
            {
                "scope": scope,
                "domain_id": domain_id,
                "symbol": str(symbol),
                "canonical_id": str(first["canonical_id"]),
                "core_asset": bool(first["core_asset"]),
                "liquidity_rank": int(first["liquidity_rank"]),
                "liquidity_tier": str(first["liquidity_tier"]),
                "trade_count": metrics["trade_count"],
                "net_pnl": metrics["net_pnl"],
                "return_on_initial_equity": (metrics["return_on_initial_equity"]),
                "win_rate": metrics["win_rate"],
                "profit_factor": metrics["profit_factor"],
            }
        )
    return rows


def classify_expanded_domain(
    *,
    domain: SignalDomain,
    candidate_count: int,
    standalone: rd16n.PortfolioEvidence,
    overlay: rd16n.PortfolioEvidence,
    baseline: Mapping[str, float],
    source_rd16q: Mapping[str, object],
    noncore_metrics: Mapping[str, object],
) -> ExpandedDomainDecision:
    standalone_1x = standalone.metrics[1.0]
    standalone_2x = standalone.metrics[2.0]
    overlay_1x = overlay.metrics[1.0]
    overlay_2x = overlay.metrics[2.0]

    standalone_return = rd16q._finite(
        standalone_1x["net_return"],
        name="standalone_return",
    )
    standalone_pf = rd16q._metric_profit_factor(standalone_1x)
    standalone_drawdown = rd16q._finite(
        standalone_1x["maximum_drawdown"],
        name="standalone_drawdown",
    )
    standalone_two_x_return = rd16q._finite(
        standalone_2x["net_return"],
        name="standalone_two_x_return",
    )
    overlay_return = rd16q._finite(
        overlay_1x["net_return"],
        name="overlay_return",
    )
    overlay_monthly = rd16q._optional_float(overlay_1x["monthly_geometric_return"])
    overlay_pf = rd16q._metric_profit_factor(overlay_1x)
    overlay_drawdown = rd16q._finite(
        overlay_1x["maximum_drawdown"],
        name="overlay_drawdown",
    )
    overlay_two_x_return = rd16q._finite(
        overlay_2x["net_return"],
        name="overlay_two_x_return",
    )
    source_overlay_return = rd16q._finite(
        source_rd16q["overlay_net_return"],
        name="source_rd16q_overlay_return",
    )
    expanded_delta = overlay_return - source_overlay_return
    delta_v3 = overlay_return - baseline["net_return"]
    delta_capture = (
        overlay.mean_high_opportunity_capture - baseline["mean_high_opportunity_capture"]
    )
    top_three = rd16q._optional_float(standalone.concentration.get("top_3_trade_profit_share"))
    noncore_count = int(
        rd16q._finite(
            noncore_metrics["trade_count"],
            name="noncore_trade_count",
        )
    )
    noncore_pnl = rd16q._finite(
        noncore_metrics["net_pnl"],
        name="noncore_net_pnl",
    )
    noncore_pf = _gate_profit_factor(
        noncore_metrics["profit_factor_gate"],
        name="noncore_profit_factor_gate",
    )
    expansion_evidence = expanded_delta >= 0.02 or (
        noncore_count >= 12 and noncore_pnl > 0.0 and noncore_pf >= 1.05
    )

    gates = {
        "candidate_count_between_24_and_1000": (24 <= candidate_count <= 1_000),
        "standalone_trade_count_gte_24": (int(cast(int, standalone_1x["trade_count"])) >= 24),
        "standalone_net_return_positive": standalone_return > 0.0,
        "standalone_profit_factor_gte_1_15": standalone_pf >= 1.15,
        "standalone_drawdown_lte_30pct": standalone_drawdown <= 0.30,
        "standalone_two_x_positive": standalone_two_x_return > 0.0,
        "standalone_two_x_profit_factor_gte_1": (rd16q._metric_profit_factor(standalone_2x) >= 1.0),
        "standalone_two_x_capital_feasible": bool(standalone_2x["capital_feasible"]),
        "standalone_positive_active_year_fraction_gte_50pct": (
            standalone.positive_active_year_fraction >= 0.50
        ),
        "standalone_top_3_profit_share_lte_35pct": (top_three is not None and top_three <= 0.35),
        "overlay_delta_net_return_vs_v3_gte_2pp": delta_v3 >= 0.02,
        "overlay_profit_factor_preserved": (overlay_pf >= baseline["profit_factor"] - 0.05),
        "overlay_drawdown_not_worse_by_more_than_3pp": (
            overlay_drawdown <= baseline["maximum_drawdown"] + 0.03
        ),
        "overlay_capital_feasible": bool(overlay_1x["capital_feasible"]),
        "overlay_two_x_capital_feasible": bool(overlay_2x["capital_feasible"]),
        "overlay_two_x_return_not_below_v3": (overlay_two_x_return >= baseline["two_x_net_return"]),
        "overlay_capture_not_worse_by_more_than_0_5pp": (delta_capture >= -0.005),
        "universe_expansion_evidence": expansion_evidence,
    }
    robust = all(gates.values())
    promising = (
        candidate_count >= 12
        and standalone_return > 0.0
        and standalone_pf >= 1.0
        and bool(overlay_1x["capital_feasible"])
        and bool(overlay_2x["capital_feasible"])
        and (
            expanded_delta > 0.0 or (noncore_count >= 8 and noncore_pnl > 0.0 and noncore_pf >= 1.0)
        )
    )
    strategic = (
        robust and overlay_monthly is not None and overlay_monthly >= STRATEGIC_MONTHLY_TARGET
    )

    failed = [key for key, passed in gates.items() if not passed]
    if robust:
        decision = "RETAIN_EXPANDED_UNIVERSE_DOMAIN_FOR_V4_ASSEMBLY"
        carry_forward = True
        rationale = (
            "Passes fixed expanded-universe, standalone, overlay, cost, "
            "capital, concentration, capture, and incremental evidence gates."
        )
    elif promising:
        decision = "PROMISING_EXPANDED_UNIVERSE_SIGNAL_DOMAIN"
        carry_forward = False
        rationale = (
            "Positive expanded-universe evidence, but fixed retention gates "
            f"failed: {', '.join(failed)}."
        )
    else:
        decision = "REJECT_EXPANDED_UNIVERSE_SIGNAL_DOMAIN"
        carry_forward = False
        rationale = (
            f"Insufficient expanded-universe signal evidence; failed gates: {', '.join(failed)}."
        )

    return ExpandedDomainDecision(
        decision=decision,
        carry_forward=carry_forward,
        rationale=rationale,
        strategic_objective_met=strategic,
        universe_expansion_evidence=expansion_evidence,
        gates=gates,
    )


def _write_local_frame(
    path: Path,
    frame: pd.DataFrame,
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return {
        "logical_path": path.relative_to(RD16S_LOCAL_ROOT).as_posix(),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _validation_payload(
    *,
    summary_row_count: int,
    deterministic_replay_match: bool,
    causal_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    causality_pass = all(
        int(cast(int, row[field])) == 0
        for row in causal_rows
        for field in (
            "next_bar_violations",
            "future_4h_context_violations",
            "future_1d_context_violations",
            "future_1w_context_violations",
            "sealed_cutoff_violations",
        )
    )
    return {
        "technical_status": "PASS",
        "domain_count": len(DOMAIN_REGISTRY),
        "summary_row_count": summary_row_count,
        "eligible_asset_count": EXPANDED_UNIVERSE_SIZE,
        "eligible_noncore_asset_count": len(NONCORE_SYMBOLS),
        "all_domains_classified": (summary_row_count == len(DOMAIN_REGISTRY)),
        "exact_eligible_universe_loaded": True,
        "deterministic_replay_match": deterministic_replay_match,
        "causality_audit_pass": causality_pass,
        "sealed_cutoff": pd.Timestamp(SEALED_CUTOFF).isoformat(),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "derivatives_data_used": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
    }


def _write_reports(
    *,
    final_report: Mapping[str, object],
    summary_rows: Sequence[Mapping[str, object]],
    all_overlay: Mapping[str, object],
) -> list[Path]:
    results_path = REPORTS_ROOT / "rd16s-limited-expanded-universe-results-v1.md"
    decisions_path = REPORTS_ROOT / "rd16s-expanded-universe-carry-forward-decisions-v1.md"
    audit_path = REPORTS_ROOT / "rd16s-universe-contribution-causality-audit-v1.md"

    results_lines = [
        "# RD16-S Limited Expanded-Universe Signal Results",
        "",
        f"- Decision: `{final_report['decision']}`",
        f"- Eligible assets: {EXPANDED_UNIVERSE_SIZE}",
        f"- Incremental assets: {len(NONCORE_SYMBOLS)}",
        f"- Domains evaluated: {final_report['domains_evaluated']}",
        f"- Retained: {final_report['retained_domain_count']}",
        f"- Promising: {final_report['promising_domain_count']}",
        f"- Next: `{final_report['next_stage']}`",
        "",
        "## Pre-registered combined overlay",
        "",
        f"- New trades: {all_overlay['new_trade_count']}",
        f"- Net return: {all_overlay['net_return']}",
        f"- Profit factor: {all_overlay['profit_factor']}",
        f"- Non-core new trades: {all_overlay['noncore_new_trade_count']}",
        f"- Non-core net PnL: {all_overlay['noncore_net_pnl']}",
        "",
    ]
    results_path.write_text(
        "\n".join(results_lines),
        encoding="utf-8",
        newline="\n",
    )

    decisions_lines = [
        "# RD16-S Expanded-Universe Carry-Forward Decisions",
        "",
    ]
    for row in summary_rows:
        decisions_lines.extend(
            [
                f"## {row['domain_id']}",
                "",
                f"- Decision: `{row['decision']}`",
                (
                    "- Expanded delta versus RD16-Q: "
                    f"{row['expanded_delta_overlay_return_vs_rd16q']}"
                ),
                (f"- Non-core overlay trades: {row['noncore_overlay_trade_count']}"),
                f"- Rationale: {row['rationale']}",
                "",
            ]
        )
    decisions_path.write_text(
        "\n".join(decisions_lines),
        encoding="utf-8",
        newline="\n",
    )

    audit_lines = [
        "# RD16-S Universe Contribution and Causality Audit",
        "",
        "- The frozen RD16-R ten-asset eligible universe is used exactly.",
        "- No network acquisition occurs in RD16-S.",
        "- Every local dataset is verified against the RD16-R manifest.",
        "- Signals are the fixed RD16-Q domains without threshold changes.",
        "- Cross-sectional internals are recomputed across ten assets.",
        "- Entry remains the next hourly bar open.",
        "- Frozen V3 trades retain routing priority.",
        "- 2025 test and 2026 holdout data remain sealed.",
        "- Spot-only and long-only constraints remain enforced.",
        "",
    ]
    audit_path.write_text(
        "\n".join(audit_lines),
        encoding="utf-8",
        newline="\n",
    )
    return [results_path, decisions_path, audit_path]


def run_rd16s_research() -> dict[str, object]:
    source_report = _verify_rd16r_ready()
    v3_ledgers, local_v3_hashes = rd16n._load_v3_ledgers()
    baseline_trades = v3_ledgers["trades"].copy()
    baseline = rd16q._baseline_values()

    (
        all_market,
        hourly_frames,
        daily_frames,
        local_rd16r_hashes,
        asset_metadata,
    ) = _load_expanded_market_frames()
    frozen_hashes = _frozen_input_hashes(
        local_v3_hashes,
        local_rd16r_hashes,
    )
    source_rows = _source_rd16q_rows()
    source_all_overlay = _source_rd16q_all_overlay()

    base_features = {
        symbol: build_feature_frame(frames, symbol=symbol) for symbol, frames in all_market.items()
    }
    internal_frames = build_expanded_internal_frames(base_features)
    timeline = rd16n._timeline(hourly_frames)
    bar_positions = rd16n._bar_position_maps(hourly_frames)
    core_daily: dict[str, pd.DataFrame] = {
        symbol: daily_frames[symbol] for symbol in ELIGIBLE_SYMBOLS if symbol in CORE_SYMBOLS
    }
    benchmark = build_benchmark_daily(core_daily)

    if RD16S_LOCAL_ROOT.exists():
        shutil.rmtree(RD16S_LOCAL_ROOT)
    RD16S_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    RD16S_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    comparison_rows: list[dict[str, object]] = []
    symbol_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    causal_rows: list[dict[str, object]] = []
    routing_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    bull_rows: list[dict[str, object]] = []
    retained: list[str] = []
    promising: list[str] = []
    rejected: list[str] = []
    strategic_count = 0
    deterministic_replay_match = True

    local_manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "eligible_symbols": list(ELIGIBLE_SYMBOLS),
        "domains": {},
        "combined": {},
    }
    domain_manifest = cast(
        dict[str, object],
        local_manifest["domains"],
    )
    all_evaluated_frames: list[pd.DataFrame] = []

    for domain in DOMAIN_REGISTRY:
        candidates = build_expanded_domain_candidates(
            internal_frames,
            domain=domain,
            asset_metadata=asset_metadata,
        )
        replay = build_expanded_domain_candidates(
            internal_frames,
            domain=domain,
            asset_metadata=asset_metadata,
        )
        if dataframe_content_hash(candidates) != dataframe_content_hash(replay):
            deterministic_replay_match = False

        evaluated = rd16n.evaluate_candidates(
            candidates,
            hourly_frames=hourly_frames,
            bar_positions=bar_positions,
        )
        standalone_evaluated, standalone_trades = rd16n.route_standalone_candidates(
            evaluated,
            hypothesis=domain.hypothesis,
        )
        overlay_evaluated, overlay_new = rd16n.route_overlay_candidates(
            baseline_trades,
            evaluated,
            variant_id=domain.domain_id,
        )

        standalone_enriched = (
            enrich_trades(
                standalone_trades,
                hourly_frames=hourly_frames,
                feature_frames=base_features,
            )
            if not standalone_trades.empty
            else rd16n._empty_enriched_frame(standalone_trades)
        )
        overlay_new_enriched = (
            enrich_trades(
                overlay_new,
                hourly_frames=hourly_frames,
                feature_frames=base_features,
            )
            if not overlay_new.empty
            else rd16n._empty_enriched_frame(overlay_new)
        )
        overlay_combined = (
            pd.concat(
                [baseline_trades, overlay_new_enriched],
                ignore_index=True,
                sort=False,
            )
            .sort_values(
                by=[
                    "entry_open_time",
                    "symbol",
                    "signal_close",
                    "trade_id",
                ],
                kind="stable",
            )
            .reset_index(drop=True)
        )

        standalone_evidence = rd16n._evaluate_portfolio(
            standalone_enriched,
            variant_id=f"RD16S-STANDALONE::{domain.domain_id}",
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        overlay_evidence = rd16n._evaluate_portfolio(
            overlay_combined,
            variant_id=f"RD16S-OVERLAY::{domain.domain_id}",
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )

        noncore_candidates = candidates[~candidates["core_asset"].astype(bool)]
        noncore_overlay = overlay_new_enriched[~overlay_new_enriched["core_asset"].astype(bool)]
        noncore_metrics = _trade_subset_metrics(noncore_overlay)
        source_row = source_rows[domain.domain_id]
        decision = classify_expanded_domain(
            domain=domain,
            candidate_count=len(candidates),
            standalone=standalone_evidence,
            overlay=overlay_evidence,
            baseline=baseline,
            source_rd16q=source_row,
            noncore_metrics=noncore_metrics,
        )

        if decision.carry_forward:
            retained.append(domain.domain_id)
        elif decision.decision == ("PROMISING_EXPANDED_UNIVERSE_SIGNAL_DOMAIN"):
            promising.append(domain.domain_id)
        else:
            rejected.append(domain.domain_id)
        if decision.strategic_objective_met:
            strategic_count += 1

        standalone_1x = standalone_evidence.metrics[1.0]
        standalone_2x = standalone_evidence.metrics[2.0]
        overlay_1x = overlay_evidence.metrics[1.0]
        overlay_2x = overlay_evidence.metrics[2.0]
        top_three = rd16q._optional_float(
            standalone_evidence.concentration.get("top_3_trade_profit_share")
        )
        source_candidate_count = int(
            rd16q._finite(
                source_row["candidate_count"],
                name="source_candidate_count",
            )
        )
        source_overlay_trade_count = int(
            rd16q._finite(
                source_row["overlay_new_trade_count"],
                name="source_overlay_trade_count",
            )
        )
        source_overlay_return = rd16q._finite(
            source_row["overlay_net_return"],
            name="source_overlay_return",
        )
        source_overlay_pf = rd16q._finite(
            source_row["overlay_profit_factor"],
            name="source_overlay_profit_factor",
        )
        expanded_overlay_return = rd16q._finite(
            overlay_1x["net_return"],
            name="expanded_overlay_return",
        )
        expanded_overlay_pf = rd16q._metric_profit_factor(overlay_1x)
        tier_a_count = int((overlay_new_enriched["liquidity_tier"].astype(str) == "A").sum())
        tier_b_count = int((overlay_new_enriched["liquidity_tier"].astype(str) == "B").sum())

        summary_row = {
            "domain_id": domain.domain_id,
            "information_domain": domain.information_domain,
            "decision": decision.decision,
            "carry_forward": decision.carry_forward,
            "candidate_count": len(candidates),
            "candidate_assets": (
                int(candidates["symbol"].nunique()) if not candidates.empty else 0
            ),
            "standalone_trade_count": standalone_1x["trade_count"],
            "standalone_net_return": standalone_1x["net_return"],
            "standalone_monthly_geometric_return": (standalone_1x["monthly_geometric_return"]),
            "standalone_profit_factor": standalone_1x["profit_factor"],
            "standalone_maximum_drawdown": (standalone_1x["maximum_drawdown"]),
            "standalone_two_x_net_return": standalone_2x["net_return"],
            "standalone_two_x_profit_factor": (standalone_2x["profit_factor"]),
            "standalone_two_x_capital_feasible": (standalone_2x["capital_feasible"]),
            "standalone_positive_active_year_fraction": (
                standalone_evidence.positive_active_year_fraction
            ),
            "standalone_top_3_trade_profit_share": top_three,
            "overlay_new_trade_count": len(overlay_new_enriched),
            "overlay_net_return": overlay_1x["net_return"],
            "overlay_monthly_geometric_return": (overlay_1x["monthly_geometric_return"]),
            "overlay_profit_factor": overlay_1x["profit_factor"],
            "overlay_maximum_drawdown": (overlay_1x["maximum_drawdown"]),
            "overlay_capital_feasible": overlay_1x["capital_feasible"],
            "overlay_two_x_net_return": overlay_2x["net_return"],
            "overlay_two_x_profit_factor": overlay_2x["profit_factor"],
            "overlay_two_x_minimum_cash": overlay_2x["minimum_cash"],
            "overlay_two_x_capital_feasible": (overlay_2x["capital_feasible"]),
            "overlay_mean_high_opportunity_capture": (
                overlay_evidence.mean_high_opportunity_capture
            ),
            "overlay_delta_net_return_vs_v3": (expanded_overlay_return - baseline["net_return"]),
            "overlay_delta_monthly_return_vs_v3": (
                rd16q._optional_delta(
                    overlay_1x["monthly_geometric_return"],
                    baseline["monthly_geometric_return"],
                )
            ),
            "overlay_delta_profit_factor_vs_v3": (expanded_overlay_pf - baseline["profit_factor"]),
            "overlay_delta_maximum_drawdown_vs_v3": (
                rd16q._finite(
                    overlay_1x["maximum_drawdown"],
                    name="overlay_drawdown",
                )
                - baseline["maximum_drawdown"]
            ),
            "overlay_delta_two_x_return_vs_v3": (
                rd16q._finite(
                    overlay_2x["net_return"],
                    name="overlay_two_x_return",
                )
                - baseline["two_x_net_return"]
            ),
            "overlay_delta_capture_vs_v3": (
                overlay_evidence.mean_high_opportunity_capture
                - baseline["mean_high_opportunity_capture"]
            ),
            "strategic_objective_met": (decision.strategic_objective_met),
            "rationale": decision.rationale,
            "source_rd16q_candidate_count": source_candidate_count,
            "source_rd16q_overlay_new_trade_count": (source_overlay_trade_count),
            "source_rd16q_overlay_net_return": source_overlay_return,
            "source_rd16q_overlay_profit_factor": source_overlay_pf,
            "expanded_delta_candidate_count_vs_rd16q": (len(candidates) - source_candidate_count),
            "expanded_delta_overlay_new_trades_vs_rd16q": (
                len(overlay_new_enriched) - source_overlay_trade_count
            ),
            "expanded_delta_overlay_return_vs_rd16q": (
                expanded_overlay_return - source_overlay_return
            ),
            "expanded_delta_overlay_profit_factor_vs_rd16q": (
                expanded_overlay_pf - source_overlay_pf
            ),
            "noncore_candidate_count": len(noncore_candidates),
            "noncore_candidate_assets": (
                int(noncore_candidates["symbol"].nunique()) if not noncore_candidates.empty else 0
            ),
            "noncore_overlay_trade_count": (noncore_metrics["trade_count"]),
            "noncore_overlay_net_pnl": noncore_metrics["net_pnl"],
            "noncore_overlay_return_on_initial_equity": (
                noncore_metrics["return_on_initial_equity"]
            ),
            "noncore_overlay_profit_factor": (noncore_metrics["profit_factor"]),
            "noncore_overlay_win_rate": noncore_metrics["win_rate"],
            "tier_a_overlay_trade_count": tier_a_count,
            "tier_b_overlay_trade_count": tier_b_count,
            "universe_expansion_evidence": (decision.universe_expansion_evidence),
        }
        summary_rows.append(summary_row)
        decision_rows.append(
            {
                "domain_id": domain.domain_id,
                "information_domain": domain.information_domain,
                "decision": decision.decision,
                "carry_forward": decision.carry_forward,
                "rationale": decision.rationale,
                "overlay_delta_net_return_vs_v3": (summary_row["overlay_delta_net_return_vs_v3"]),
                "expanded_delta_overlay_return_vs_rd16q": (
                    summary_row["expanded_delta_overlay_return_vs_rd16q"]
                ),
                "noncore_overlay_trade_count": (noncore_metrics["trade_count"]),
                "noncore_overlay_net_pnl": noncore_metrics["net_pnl"],
                "noncore_overlay_profit_factor": (noncore_metrics["profit_factor"]),
                "universe_expansion_evidence": (decision.universe_expansion_evidence),
            }
        )
        comparison_rows.append(
            {
                "domain_id": domain.domain_id,
                "source_universe_size": SOURCE_UNIVERSE_SIZE,
                "expanded_universe_size": EXPANDED_UNIVERSE_SIZE,
                "source_candidate_count": source_candidate_count,
                "expanded_candidate_count": len(candidates),
                "delta_candidate_count": (len(candidates) - source_candidate_count),
                "source_overlay_new_trade_count": (source_overlay_trade_count),
                "expanded_overlay_new_trade_count": (len(overlay_new_enriched)),
                "delta_overlay_new_trade_count": (
                    len(overlay_new_enriched) - source_overlay_trade_count
                ),
                "source_overlay_net_return": source_overlay_return,
                "expanded_overlay_net_return": expanded_overlay_return,
                "delta_overlay_net_return": (expanded_overlay_return - source_overlay_return),
                "source_overlay_profit_factor": source_overlay_pf,
                "expanded_overlay_profit_factor": expanded_overlay_pf,
                "delta_overlay_profit_factor": (expanded_overlay_pf - source_overlay_pf),
                "noncore_candidate_count": len(noncore_candidates),
                "noncore_overlay_trade_count": (noncore_metrics["trade_count"]),
                "noncore_overlay_net_pnl": noncore_metrics["net_pnl"],
                "noncore_overlay_profit_factor": (noncore_metrics["profit_factor"]),
            }
        )
        symbol_rows.extend(
            _symbol_rows(
                standalone_enriched,
                scope="STANDALONE",
                domain_id=domain.domain_id,
            )
        )
        symbol_rows.extend(
            _symbol_rows(
                overlay_new_enriched,
                scope="OVERLAY_NEW",
                domain_id=domain.domain_id,
            )
        )
        cost_rows.extend(
            rd16q._cost_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=domain.domain_id,
            )
        )
        cost_rows.extend(
            rd16q._cost_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=domain.domain_id,
            )
        )
        coverage_rows.extend(
            rd16q._coverage_rows(
                domain_id=domain.domain_id,
                candidates=candidates,
                evaluated=evaluated,
                standalone=standalone_enriched,
                overlay_new=overlay_new_enriched,
            )
        )
        causal_rows.extend(
            rd16q._causality_rows(
                candidates,
                domain_id=domain.domain_id,
            )
        )
        routing_rows.extend(
            rd16q._routing_rows(
                standalone_evaluated,
                scope="STANDALONE",
                variant_id=domain.domain_id,
            )
        )
        routing_rows.extend(
            rd16q._routing_rows(
                overlay_evaluated,
                scope="OVERLAY",
                variant_id=domain.domain_id,
            )
        )
        annual_rows.extend(
            rd16q._annual_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=domain.domain_id,
            )
        )
        annual_rows.extend(
            rd16q._annual_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=domain.domain_id,
            )
        )
        bull_rows.extend(
            rd16q._bull_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=domain.domain_id,
            )
        )
        bull_rows.extend(
            rd16q._bull_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=domain.domain_id,
            )
        )

        domain_root = RD16S_LOCAL_ROOT / domain.domain_id
        local_entries = {
            "candidates": _write_local_frame(
                domain_root / "candidates.parquet",
                candidates,
            ),
            "evaluated": _write_local_frame(
                domain_root / "evaluated.parquet",
                evaluated,
            ),
            "standalone_evaluated": _write_local_frame(
                domain_root / "standalone-evaluated.parquet",
                standalone_evaluated,
            ),
            "standalone_trades": _write_local_frame(
                domain_root / "standalone-trades.parquet",
                standalone_enriched,
            ),
            "overlay_evaluated": _write_local_frame(
                domain_root / "overlay-evaluated.parquet",
                overlay_evaluated,
            ),
            "overlay_new_trades": _write_local_frame(
                domain_root / "overlay-new-trades.parquet",
                overlay_new_enriched,
            ),
            "overlay_combined_trades": _write_local_frame(
                domain_root / "overlay-combined-trades.parquet",
                overlay_combined,
            ),
        }
        if set(local_entries) != set(LOCAL_DATASET_KEYS):
            raise RD16SEvaluationError(f"Local ledger keys mismatch for {domain.domain_id}.")
        domain_manifest[domain.domain_id] = local_entries
        all_evaluated_frames.append(evaluated)

    combined_evaluated = (
        pd.concat(
            all_evaluated_frames,
            ignore_index=True,
            sort=False,
        )
        .sort_values(
            by=[
                "entry_open_time",
                "engine_priority",
                "symbol",
                "signal_close",
                "candidate_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
        if all_evaluated_frames
        else pd.DataFrame()
    )
    combined_routing, combined_new = rd16n.route_overlay_candidates(
        baseline_trades,
        combined_evaluated,
        variant_id=ALL_DOMAIN_OVERLAY_ID,
    )
    combined_new_enriched = (
        enrich_trades(
            combined_new,
            hourly_frames=hourly_frames,
            feature_frames=base_features,
        )
        if not combined_new.empty
        else rd16n._empty_enriched_frame(combined_new)
    )
    combined_trades = (
        pd.concat(
            [baseline_trades, combined_new_enriched],
            ignore_index=True,
            sort=False,
        )
        .sort_values(
            by=[
                "entry_open_time",
                "symbol",
                "signal_close",
                "trade_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    combined_evidence = rd16n._evaluate_portfolio(
        combined_trades,
        variant_id=ALL_DOMAIN_OVERLAY_ID,
        hourly_frames=hourly_frames,
        timeline=timeline,
        benchmark=benchmark,
    )
    combined_noncore = combined_new_enriched[~combined_new_enriched["core_asset"].astype(bool)]
    combined_noncore_metrics = _trade_subset_metrics(combined_noncore)
    combined_1x = combined_evidence.metrics[1.0]
    combined_2x = combined_evidence.metrics[2.0]
    source_combined_return = rd16q._finite(
        source_all_overlay["net_return"],
        name="source_combined_return",
    )
    source_combined_pf = rd16q._finite(
        source_all_overlay["profit_factor"],
        name="source_combined_profit_factor",
    )
    source_combined_trades = int(
        rd16q._finite(
            source_all_overlay["new_trade_count"],
            name="source_combined_new_trades",
        )
    )
    combined_return = rd16q._finite(
        combined_1x["net_return"],
        name="combined_return",
    )
    combined_pf = rd16q._metric_profit_factor(combined_1x)
    all_overlay = {
        "variant_id": ALL_DOMAIN_OVERLAY_ID,
        "new_trade_count": len(combined_new_enriched),
        "trade_count": combined_1x["trade_count"],
        "net_return": combined_1x["net_return"],
        "monthly_geometric_return": (combined_1x["monthly_geometric_return"]),
        "profit_factor": combined_1x["profit_factor"],
        "maximum_drawdown": combined_1x["maximum_drawdown"],
        "minimum_cash": combined_1x["minimum_cash"],
        "capital_feasible": combined_1x["capital_feasible"],
        "two_x_net_return": combined_2x["net_return"],
        "two_x_profit_factor": combined_2x["profit_factor"],
        "two_x_minimum_cash": combined_2x["minimum_cash"],
        "two_x_capital_feasible": combined_2x["capital_feasible"],
        "mean_high_opportunity_capture": (combined_evidence.mean_high_opportunity_capture),
        "delta_net_return_vs_v3": (combined_return - baseline["net_return"]),
        "delta_capture_vs_v3": (
            combined_evidence.mean_high_opportunity_capture
            - baseline["mean_high_opportunity_capture"]
        ),
        "source_rd16q_new_trade_count": source_combined_trades,
        "source_rd16q_net_return": source_combined_return,
        "source_rd16q_profit_factor": source_combined_pf,
        "expanded_delta_new_trades_vs_rd16q": (len(combined_new_enriched) - source_combined_trades),
        "expanded_delta_net_return_vs_rd16q": (combined_return - source_combined_return),
        "expanded_delta_profit_factor_vs_rd16q": (combined_pf - source_combined_pf),
        "noncore_new_trade_count": (combined_noncore_metrics["trade_count"]),
        "noncore_net_pnl": combined_noncore_metrics["net_pnl"],
        "noncore_return_on_initial_equity": (combined_noncore_metrics["return_on_initial_equity"]),
        "noncore_profit_factor": (combined_noncore_metrics["profit_factor"]),
        "noncore_win_rate": combined_noncore_metrics["win_rate"],
    }
    cost_rows.extend(
        rd16q._cost_rows(
            combined_evidence,
            scope="OVERLAY",
            variant_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    routing_rows.extend(
        rd16q._routing_rows(
            combined_routing,
            scope="OVERLAY",
            variant_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    annual_rows.extend(
        rd16q._annual_rows(
            combined_evidence,
            scope="OVERLAY",
            variant_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    bull_rows.extend(
        rd16q._bull_rows(
            combined_evidence,
            scope="OVERLAY",
            variant_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    symbol_rows.extend(
        _symbol_rows(
            combined_new_enriched,
            scope="OVERLAY_NEW",
            domain_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    combined_manifest = cast(
        dict[str, object],
        local_manifest["combined"],
    )
    combined_manifest.update(
        {
            "evaluated": _write_local_frame(
                RD16S_LOCAL_ROOT / "combined" / "evaluated.parquet",
                combined_evaluated,
            ),
            "overlay_evaluated": _write_local_frame(
                RD16S_LOCAL_ROOT / "combined" / "overlay-evaluated.parquet",
                combined_routing,
            ),
            "overlay_new_trades": _write_local_frame(
                RD16S_LOCAL_ROOT / "combined" / "overlay-new-trades.parquet",
                combined_new_enriched,
            ),
            "overlay_combined_trades": _write_local_frame(
                RD16S_LOCAL_ROOT / "combined" / "overlay-combined-trades.parquet",
                combined_trades,
            ),
        }
    )

    if retained:
        next_stage = NEXT_ASSEMBLY
    elif promising:
        next_stage = NEXT_REFINEMENT
    else:
        next_stage = NEXT_RESET

    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "branch": BRANCH,
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "source_stage_decision": source_report["decision"],
        "source_universe_size": SOURCE_UNIVERSE_SIZE,
        "expanded_universe_size": EXPANDED_UNIVERSE_SIZE,
        "incremental_noncore_asset_count": len(NONCORE_SYMBOLS),
        "eligible_symbols": list(ELIGIBLE_SYMBOLS),
        "domains_evaluated": len(DOMAIN_REGISTRY),
        "retained_domain_count": len(retained),
        "retained_domains": retained,
        "promising_domain_count": len(promising),
        "promising_domains": promising,
        "rejected_domain_count": len(rejected),
        "rejected_domains": rejected,
        "strategic_objective_met_count": strategic_count,
        "strategic_objective_met": strategic_count > 0,
        "pre_registered_all_domain_overlay": all_overlay,
        "next_stage": next_stage,
        "technical_gates": {
            "all_input_hashes_verified": True,
            "rd16r_ready": True,
            "rd16r_outputs_verified": True,
            "rd16r_local_data_verified": True,
            "rd16q_outputs_verified": True,
            "rd16l_local_ledgers_verified": True,
            "exact_eligible_universe_loaded": True,
            "deterministic_replay_match": deterministic_replay_match,
            "all_causality_checks_pass": all(
                int(cast(int, row[field])) == 0
                for row in causal_rows
                for field in (
                    "next_bar_violations",
                    "future_4h_context_violations",
                    "future_1d_context_violations",
                    "future_1w_context_violations",
                    "sealed_cutoff_violations",
                )
            ),
            "frozen_v3_trades_preserved": True,
            "same_symbol_overlap_prohibited": True,
            "maximum_positions_preserved": True,
            "maximum_open_risk_preserved": True,
            "spot_only": True,
            "long_only": True,
            "network_accessed": False,
            "derivatives_data_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
            "architecture_changed": False,
        },
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "architecture_changed": False,
    }

    registry_path = RD16S_ROOT / "expanded-domain-registry.csv"
    summary_path = RD16S_ROOT / "expanded-domain-summary.csv"
    decisions_path = RD16S_ROOT / "component-decisions.csv"
    comparison_path = RD16S_ROOT / "universe-comparison.csv"
    symbol_path = RD16S_ROOT / "symbol-performance.csv"
    cost_path = RD16S_ROOT / "cost-stress.csv"
    coverage_path = RD16S_ROOT / "domain-coverage.csv"
    causal_path = RD16S_ROOT / "causality-audit.csv"
    routing_path = RD16S_ROOT / "routing-summary.csv"
    annual_path = RD16S_ROOT / "annual-performance.csv"
    bull_path = RD16S_ROOT / "bull-window-capture.csv"
    internal_path = RD16S_ROOT / "market-internals-summary.csv"
    all_overlay_path = RD16S_ROOT / "all-domain-overlay-summary.csv"
    frozen_path = RD16S_ROOT / "frozen-input-hashes.json"
    local_manifest_path = RD16S_ROOT / "local-output-manifest-v1.json"
    validation_path = RD16S_ROOT / "validation-report.json"
    final_path = RD16S_ROOT / "rd16s-final-report-v1.json"
    output_hash_path = RD16S_ROOT / "output-hashes.json"

    write_csv(
        registry_path,
        expanded_domain_registry_rows(),
        fieldnames=REGISTRY_FIELDS,
    )
    write_csv(summary_path, summary_rows, fieldnames=SUMMARY_FIELDS)
    write_csv(
        decisions_path,
        decision_rows,
        fieldnames=DECISION_FIELDS,
    )
    write_csv(
        comparison_path,
        comparison_rows,
        fieldnames=COMPARISON_FIELDS,
    )
    write_csv(symbol_path, symbol_rows, fieldnames=SYMBOL_FIELDS)
    write_csv(cost_path, cost_rows, fieldnames=rd16q.COST_FIELDS)
    write_csv(
        coverage_path,
        coverage_rows,
        fieldnames=rd16q.COVERAGE_FIELDS,
    )
    write_csv(
        causal_path,
        causal_rows,
        fieldnames=rd16q.CAUSAL_FIELDS,
    )
    write_csv(
        routing_path,
        routing_rows,
        fieldnames=rd16q.ROUTING_FIELDS,
    )
    write_csv(
        annual_path,
        annual_rows,
        fieldnames=rd16q.ANNUAL_FIELDS,
    )
    write_csv(bull_path, bull_rows, fieldnames=rd16q.BULL_FIELDS)
    write_csv(
        internal_path,
        rd16q._internal_summary_rows(internal_frames),
        fieldnames=rd16q.INTERNAL_SUMMARY_FIELDS,
    )
    write_csv(
        all_overlay_path,
        [all_overlay],
        fieldnames=ALL_OVERLAY_FIELDS,
    )
    write_json(frozen_path, frozen_hashes)
    write_json(local_manifest_path, local_manifest)
    validation = _validation_payload(
        summary_row_count=len(summary_rows),
        deterministic_replay_match=deterministic_replay_match,
        causal_rows=causal_rows,
    )
    write_json(validation_path, validation)
    write_json(final_path, final_report)

    report_paths = _write_reports(
        final_report=final_report,
        summary_rows=summary_rows,
        all_overlay=all_overlay,
    )
    output_paths = [
        registry_path,
        summary_path,
        decisions_path,
        comparison_path,
        symbol_path,
        cost_path,
        coverage_path,
        causal_path,
        routing_path,
        annual_path,
        bull_path,
        internal_path,
        all_overlay_path,
        frozen_path,
        local_manifest_path,
        validation_path,
        final_path,
        *report_paths,
    ]
    write_json(output_hash_path, rd16q._output_hashes(output_paths))

    frozen_after = _frozen_input_hashes(
        local_v3_hashes,
        local_rd16r_hashes,
    )
    if frozen_after != frozen_hashes:
        raise RD16SEvaluationError("Frozen RD16-S inputs changed during evaluation.")
    if not deterministic_replay_match:
        raise RD16SEvaluationError("RD16-S deterministic replay mismatch.")
    if validation["causality_audit_pass"] is not True:
        raise RD16SEvaluationError("RD16-S causality audit failed.")
    return final_report


__all__ = [
    "ALL_DOMAIN_OVERLAY_ID",
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "ExpandedDomainDecision",
    "RD16SEvaluationError",
    "SCHEMA_VERSION",
    "_symbol_rows",
    "_trade_subset_metrics",
    "_validation_payload",
    "classify_expanded_domain",
    "run_rd16s_research",
]
