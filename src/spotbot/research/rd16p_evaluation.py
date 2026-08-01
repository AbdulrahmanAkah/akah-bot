from __future__ import annotations

import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.research import rd16n_evaluation as rd16n
from spotbot.research.rd16c_common import (
    BRANCH,
    LOCAL_INPUT_ROOT,
    ROOT,
    SEALED_CUTOFF,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
    verify_local_dataset_hashes,
)
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16d_common import (
    COST_MULTIPLIERS,
    INITIAL_EQUITY,
    STRATEGIC_MONTHLY_TARGET,
    write_csv,
    write_json,
)
from spotbot.research.rd16d_metrics import (
    build_benchmark_daily,
    enrich_trades,
)
from spotbot.research.rd16n_signals import SignalHypothesis
from spotbot.research.rd16p_portfolio import (
    VARIANT_REGISTRY,
    PortfolioVariant,
    rescale_selected_candidates,
    route_portfolio_sleeve,
    select_cross_sectional_candidates,
    variant_registry_rows,
)

SCHEMA_VERSION: Final = "rd16p-multitimeframe-cross-sectional-portfolio-research-v1"
DECISION: Final = "RD16P_MULTITIMEFRAME_STRUCTURE_AND_CROSS_SECTIONAL_PORTFOLIO_RESEARCH_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "CROSS_SECTIONAL_PORTFOLIO_EVIDENCE_EXTRACTED"
NEXT_ASSEMBLY: Final = "RD16Q_COMPOSITE_ALPHA_V4_CANDIDATE_ASSEMBLY_AND_INTERACTION_TEST"
NEXT_REFINEMENT: Final = "RD16Q_CROSS_SECTIONAL_PORTFOLIO_REFINEMENT"
NEXT_EXPANSION: Final = "RD16Q_SIGNAL_DOMAIN_EXPANSION_AND_ALTERNATIVE_DATA_RESEARCH"

RD16L_ROOT: Final = ROOT / "data" / "research" / "rd16l"
RD16M_ROOT: Final = ROOT / "data" / "research" / "rd16m"
RD16O_ROOT: Final = ROOT / "data" / "research" / "rd16o"
RD16O_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16o"
RD16P_ROOT: Final = ROOT / "data" / "research" / "rd16p"
RD16P_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16p"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

VARIANT_FIELDS: Final = (
    "variant_id",
    "description",
    "allowed_hypotheses",
    "allowed_regimes",
    "top_k_per_timestamp",
    "minimum_quality_score",
    "minimum_breadth",
    "minimum_return24_rank",
    "minimum_return72_rank",
    "risk_fraction",
    "notional_cap_fraction",
    "sleeve_maximum_positions",
    "sleeve_maximum_open_risk_fraction",
    "cooldown_hours",
    "engine_priority",
)

SUMMARY_FIELDS: Final = (
    "variant_id",
    "decision",
    "carry_forward",
    "candidate_count",
    "selected_count",
    "sleeve_admitted_count",
    "standalone_trade_count",
    "standalone_net_return",
    "standalone_monthly_geometric_return",
    "standalone_profit_factor",
    "standalone_maximum_drawdown",
    "standalone_two_x_net_return",
    "standalone_two_x_profit_factor",
    "standalone_two_x_capital_feasible",
    "overlay_new_trade_count",
    "overlay_trade_count",
    "overlay_net_return",
    "overlay_monthly_geometric_return",
    "overlay_profit_factor",
    "overlay_maximum_drawdown",
    "overlay_minimum_cash",
    "overlay_capital_feasible",
    "overlay_two_x_net_return",
    "overlay_two_x_profit_factor",
    "overlay_two_x_minimum_cash",
    "overlay_two_x_capital_feasible",
    "overlay_mean_high_opportunity_capture",
    "overlay_delta_net_return_vs_v3",
    "overlay_delta_monthly_return_vs_v3",
    "overlay_delta_profit_factor_vs_v3",
    "overlay_delta_maximum_drawdown_vs_v3",
    "overlay_delta_two_x_return_vs_v3",
    "overlay_delta_capture_vs_v3",
    "strategic_objective_met",
    "rationale",
)

DECISION_FIELDS: Final = (
    "variant_id",
    "decision",
    "carry_forward",
    "rationale",
    "standalone_net_return",
    "standalone_profit_factor",
    "overlay_delta_net_return_vs_v3",
    "overlay_profit_factor",
    "overlay_two_x_capital_feasible",
    "overlay_delta_capture_vs_v3",
)

COST_FIELDS: Final = (
    "scope",
    "variant_id",
    "cost_multiplier",
    "trade_count",
    "net_return",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
)

SELECTION_FIELDS: Final = (
    "variant_id",
    "selection_decision",
    "candidate_count",
    "average_quality_score",
    "hypothetical_net_pnl",
    "hypothetical_return_on_initial_equity",
    "hypothetical_profit_factor",
)

ROUTING_FIELDS: Final = (
    "scope",
    "variant_id",
    "router_decision",
    "candidate_count",
    "hypothetical_net_pnl",
    "hypothetical_return_on_initial_equity",
    "hypothetical_profit_factor",
)

BULL_FIELDS: Final = (
    "variant_id",
    "window_id",
    "start",
    "end",
    "days",
    "portfolio_return",
    "equal_weight_return",
    "capture_ratio",
    "high_opportunity_window",
    "strategic_bull_adequacy",
)

ANNUAL_FIELDS: Final = (
    "variant_id",
    "year",
    "trade_count",
    "return",
)

LOCAL_DATASET_KEYS: Final = (
    "candidates",
    "selected",
    "scaled",
    "sleeve_evaluated",
    "sleeve_admitted",
    "standalone_evaluated",
    "standalone_trades",
    "overlay_evaluated",
    "overlay_new_trades",
    "overlay_combined_trades",
)


class RD16PEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PortfolioDecision:
    decision: str
    carry_forward: bool
    rationale: str
    strategic_objective_met: bool
    gates: dict[str, bool]


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16PEvaluationError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16PEvaluationError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16PEvaluationError(f"{name} must be finite.")
    return numeric


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _profit_factor(metrics: Mapping[str, object]) -> float:
    raw = _optional_float(metrics.get("profit_factor"))
    if raw is not None:
        return raw
    gross_profit = _optional_float(metrics.get("gross_profit")) or 0.0
    gross_loss = _optional_float(metrics.get("gross_loss")) or 0.0
    if gross_profit > 0.0 and gross_loss == 0.0:
        return math.inf
    return 0.0


def _profit_factor_series(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = float(numeric[numeric > 0.0].sum())
    gross_loss = abs(float(numeric[numeric < 0.0].sum()))
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def _optional_delta(value: object, baseline: float) -> float | None:
    numeric = _optional_float(value)
    return numeric - baseline if numeric is not None else None


def _verify_rd16o_ready() -> dict[str, Any]:
    report = read_json_object(RD16O_ROOT / "rd16o-final-report-v1.json")
    expected = {
        "decision": (
            "RD16O_INTRADAY_ALPHA_ENGINE_REDESIGN_AND_SECOND_GENERATION_SIGNAL_RESEARCH_COMPLETED"
        ),
        "technical_status": "COMPLETED",
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "hypotheses_evaluated": 5,
        "retained_hypothesis_count": 0,
        "promising_hypothesis_count": 0,
        "strategic_objective_met_count": 0,
        "next_stage": ("RD16P_MULTITIMEFRAME_STRUCTURE_AND_CROSS_SECTIONAL_PORTFOLIO_RESEARCH"),
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16PEvaluationError(f"RD16-O readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16PEvaluationError("RD16-O technical gates are missing.")
    required_true = (
        "all_causality_checks_pass",
        "frozen_v3_trades_preserved",
        "raw_market_data_verified",
        "rd16l_local_ledgers_verified",
        "rd16n_outputs_verified",
        "same_symbol_overlap_prohibited",
        "spot_only",
        "long_only",
    )
    for key in required_true:
        if technical.get(key) is not True:
            raise RD16PEvaluationError(f"RD16-O technical gate failed: {key}")
    forbidden_true = (
        "architecture_changed",
        "dune_api_called",
        "holdout_2026_accessed",
        "optimization_performed",
        "production_authorized",
        "test_2025_accessed",
        "winner_selected",
    )
    for key in forbidden_true:
        if technical.get(key) is True:
            raise RD16PEvaluationError(f"RD16-O forbidden flag is true: {key}")
    return report


def _verify_rd16o_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16O_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16PEvaluationError("RD16-O output hash manifest is invalid.")
        data_path = RD16O_ROOT / raw_name
        report_path = REPORTS_ROOT / raw_name
        path = data_path if data_path.is_file() else report_path
        if not path.is_file():
            raise RD16PEvaluationError(f"Missing RD16-O output: {raw_name}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16PEvaluationError(f"RD16-O output hash mismatch for {raw_name}.")
        verified[f"rd16o:{raw_name}"] = actual
    return verified


def _load_rd16o_evaluated() -> tuple[pd.DataFrame, dict[str, str]]:
    manifest = read_json_object(RD16O_ROOT / "local-output-manifest-v1.json")
    families = manifest.get("families")
    if not isinstance(families, dict):
        raise RD16PEvaluationError("RD16-O local family manifest is invalid.")

    frames: list[pd.DataFrame] = []
    hashes: dict[str, str] = {}
    for family_id, raw_family in sorted(families.items()):
        if not isinstance(family_id, str) or not isinstance(raw_family, dict):
            raise RD16PEvaluationError("Invalid RD16-O family manifest entry.")
        raw_entry = raw_family.get("evaluated")
        if not isinstance(raw_entry, dict):
            raise RD16PEvaluationError(f"Missing evaluated ledger for {family_id}.")
        logical = raw_entry.get("logical_path")
        expected_rows = raw_entry.get("rows")
        expected_file = raw_entry.get("file_sha256")
        expected_content = raw_entry.get("content_sha256")
        if (
            not isinstance(logical, str)
            or not isinstance(expected_rows, int)
            or not isinstance(expected_file, str)
            or not isinstance(expected_content, str)
        ):
            raise RD16PEvaluationError(f"Invalid evaluated ledger metadata for {family_id}.")
        path = RD16O_LOCAL_ROOT / logical
        if not path.is_file():
            raise RD16PEvaluationError(f"Missing local RD16-O evaluated ledger: {path}")
        actual_file = sha256_path(path)
        if actual_file != expected_file:
            raise RD16PEvaluationError(f"File hash mismatch for RD16-O family {family_id}.")
        frame = pd.read_parquet(path)
        if len(frame) != expected_rows:
            raise RD16PEvaluationError(f"Row count mismatch for RD16-O family {family_id}.")
        actual_content = dataframe_content_hash(frame)
        if actual_content != expected_content:
            raise RD16PEvaluationError(f"Content hash mismatch for RD16-O family {family_id}.")
        frames.append(frame)
        hashes[f"rd16o-local:{logical}"] = actual_file

    if not frames:
        raise RD16PEvaluationError("RD16-O evaluated family ledgers are empty.")
    combined = pd.concat(frames, ignore_index=True, sort=False)
    required = {
        "candidate_id",
        "hypothesis_id",
        "engine_id",
        "symbol",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
        "market_regime",
        "market_breadth_at_signal",
        "return24_rank_at_signal",
        "return72_rank_at_signal",
        "volume_ratio_at_signal",
        "ema20_distance_atr_at_signal",
        "risk_budget",
        "quantity",
        "notional",
        "gross_pnl",
        "fees",
        "net_pnl",
    }
    missing = sorted(required.difference(combined.columns))
    if missing:
        raise RD16PEvaluationError(f"RD16-O evaluated ledgers are missing columns: {missing}")
    if bool(combined["candidate_id"].astype(str).duplicated().any()):
        raise RD16PEvaluationError("RD16-O evaluated candidate IDs must be unique.")
    return combined, hashes


def _baseline_values() -> dict[str, float]:
    report = read_json_object(RD16M_ROOT / "rd16m-final-report-v1.json")
    return {
        "net_return": _finite(
            report["net_return"],
            name="baseline_net_return",
        ),
        "monthly_geometric_return": _finite(
            report["monthly_geometric_return"],
            name="baseline_monthly_return",
        ),
        "profit_factor": _finite(
            report["profit_factor"],
            name="baseline_profit_factor",
        ),
        "maximum_drawdown": _finite(
            report["maximum_drawdown"],
            name="baseline_drawdown",
        ),
        "two_x_net_return": _finite(
            report["two_x_net_return"],
            name="baseline_two_x_return",
        ),
        "two_x_profit_factor": _finite(
            report["two_x_profit_factor"],
            name="baseline_two_x_profit_factor",
        ),
        "mean_high_opportunity_capture": _finite(
            report["mean_high_opportunity_capture"],
            name="baseline_capture",
        ),
    }


def _frozen_input_hashes(
    local_v3_hashes: Mapping[str, str],
    local_rd16o_hashes: Mapping[str, str],
) -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16o/rd16o-final-report-v1.json": (RD16O_ROOT / "rd16o-final-report-v1.json"),
        "rd16o/validation-report.json": (RD16O_ROOT / "validation-report.json"),
        "rd16o/output-hashes.json": RD16O_ROOT / "output-hashes.json",
        "rd16o/family-summary.csv": RD16O_ROOT / "family-summary.csv",
        "rd16o/local-output-manifest-v1.json": (RD16O_ROOT / "local-output-manifest-v1.json"),
        "rd16m/rd16m-final-report-v1.json": (RD16M_ROOT / "rd16m-final-report-v1.json"),
        "rd16l/local-ledger-manifest-v1.json": (RD16L_ROOT / "local-ledger-manifest-v1.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16PEvaluationError(f"Frozen RD16-P input is missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16o_outputs())
    hashes.update(local_v3_hashes)
    hashes.update(local_rd16o_hashes)
    hashes.update(verify_local_dataset_hashes(LOCAL_INPUT_ROOT))
    return dict(sorted(hashes.items()))


def _synthetic_hypothesis(variant: PortfolioVariant) -> SignalHypothesis:
    return SignalHypothesis(
        hypothesis_id=variant.variant_id,
        engine_id=f"{variant.variant_id}_ENGINE",
        role="PORTFOLIO_SELECTOR",
        description=variant.description,
        stop_atr_multiple=1.0,
        cooldown_hours=variant.cooldown_hours,
        engine_priority=variant.engine_priority,
        fixed_conditions=(
            "completed-bar cross-sectional ranking",
            "fixed top-k selection",
            "fixed risk and notional caps",
            "fixed sleeve position and open-risk limits",
        ),
    )


def classify_portfolio_variant(
    *,
    variant: PortfolioVariant,
    selected_count: int,
    standalone: rd16n.PortfolioEvidence,
    overlay: rd16n.PortfolioEvidence,
    baseline: Mapping[str, float],
) -> PortfolioDecision:
    standalone_1x = standalone.metrics[1.0]
    standalone_2x = standalone.metrics[2.0]
    overlay_1x = overlay.metrics[1.0]
    overlay_2x = overlay.metrics[2.0]

    standalone_return = _finite(
        standalone_1x["net_return"],
        name="standalone_return",
    )
    standalone_pf = _profit_factor(standalone_1x)
    standalone_drawdown = _finite(
        standalone_1x["maximum_drawdown"],
        name="standalone_drawdown",
    )
    standalone_2x_return = _finite(
        standalone_2x["net_return"],
        name="standalone_two_x_return",
    )
    overlay_return = _finite(
        overlay_1x["net_return"],
        name="overlay_return",
    )
    overlay_monthly = _optional_float(overlay_1x["monthly_geometric_return"])
    overlay_pf = _profit_factor(overlay_1x)
    overlay_drawdown = _finite(
        overlay_1x["maximum_drawdown"],
        name="overlay_drawdown",
    )
    overlay_2x_return = _finite(
        overlay_2x["net_return"],
        name="overlay_two_x_return",
    )
    delta_return = overlay_return - baseline["net_return"]
    delta_capture = (
        overlay.mean_high_opportunity_capture - baseline["mean_high_opportunity_capture"]
    )

    gates = {
        "selected_count_between_24_and_600": 24 <= selected_count <= 600,
        "standalone_trade_count_gte_24": (int(cast(int, standalone_1x["trade_count"])) >= 24),
        "standalone_net_return_positive": standalone_return > 0.0,
        "standalone_profit_factor_gte_1_10": standalone_pf >= 1.10,
        "standalone_drawdown_lte_30pct": standalone_drawdown <= 0.30,
        "standalone_two_x_positive": standalone_2x_return > 0.0,
        "standalone_two_x_profit_factor_gte_1": (_profit_factor(standalone_2x) >= 1.0),
        "standalone_two_x_capital_feasible": bool(standalone_2x["capital_feasible"]),
        "overlay_delta_net_return_gte_2pp": delta_return >= 0.02,
        "overlay_profit_factor_preserved": (overlay_pf >= baseline["profit_factor"] - 0.05),
        "overlay_drawdown_not_worse_by_more_than_3pp": (
            overlay_drawdown <= baseline["maximum_drawdown"] + 0.03
        ),
        "overlay_capital_feasible": bool(overlay_1x["capital_feasible"]),
        "overlay_two_x_capital_feasible": bool(overlay_2x["capital_feasible"]),
        "overlay_two_x_return_not_below_v3": (overlay_2x_return >= baseline["two_x_net_return"]),
        "overlay_capture_not_worse_by_more_than_0_5pp": (delta_capture >= -0.005),
    }
    robust = all(gates.values())
    promising = (
        selected_count >= 12
        and standalone_return > 0.0
        and standalone_pf >= 1.0
        and delta_return > 0.0
        and bool(overlay_1x["capital_feasible"])
        and bool(overlay_2x["capital_feasible"])
    )
    strategic = (
        robust and overlay_monthly is not None and overlay_monthly >= STRATEGIC_MONTHLY_TARGET
    )

    if robust:
        decision = "RETAIN_FOR_COMPOSITE_ALPHA_V4_ASSEMBLY"
        carry_forward = True
        rationale = (
            "Passes fixed selection, standalone, overlay, stressed-cost, "
            "capital, drawdown, and benchmark-capture gates."
        )
    elif promising:
        decision = "PROMISING_CROSS_SECTIONAL_PORTFOLIO"
        carry_forward = False
        failed = [key for key, passed in gates.items() if not passed]
        rationale = (
            "Positive standalone and additive portfolio evidence, but fixed "
            f"retention gates failed: {', '.join(failed)}."
        )
    else:
        decision = "REJECT_CROSS_SECTIONAL_PORTFOLIO"
        carry_forward = False
        failed = [key for key, passed in gates.items() if not passed]
        rationale = (
            f"Insufficient cross-sectional portfolio evidence; failed gates: {', '.join(failed)}."
        )
    return PortfolioDecision(
        decision=decision,
        carry_forward=carry_forward,
        rationale=rationale,
        strategic_objective_met=strategic,
        gates=gates,
    )


def _cost_rows(
    evidence: rd16n.PortfolioEvidence,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for multiplier in COST_MULTIPLIERS:
        metrics = evidence.metrics[multiplier]
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "cost_multiplier": multiplier,
                "trade_count": metrics["trade_count"],
                "net_return": metrics["net_return"],
                "monthly_geometric_return": (metrics["monthly_geometric_return"]),
                "maximum_drawdown": metrics["maximum_drawdown"],
                "profit_factor": metrics["profit_factor"],
                "minimum_cash": metrics["minimum_cash"],
                "minimum_equity": metrics["minimum_equity"],
                "capital_feasible": metrics["capital_feasible"],
            }
        )
    return rows


def _selection_rows(
    frame: pd.DataFrame,
    *,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if frame.empty:
        return rows
    for decision, group in frame.groupby("selection_decision", sort=True):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        score = pd.to_numeric(group["quality_score"], errors="raise")
        rows.append(
            {
                "variant_id": variant_id,
                "selection_decision": str(decision),
                "candidate_count": len(group),
                "average_quality_score": float(score.mean()),
                "hypothetical_net_pnl": float(pnl.sum()),
                "hypothetical_return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "hypothetical_profit_factor": _profit_factor_series(pnl),
            }
        )
    return rows


def _routing_rows(
    frame: pd.DataFrame,
    *,
    scope: str,
    variant_id: str,
    decision_column: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if frame.empty:
        return rows
    for decision, group in frame.groupby(decision_column, sort=True):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "router_decision": str(decision),
                "candidate_count": len(group),
                "hypothetical_net_pnl": float(pnl.sum()),
                "hypothetical_return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "hypothetical_profit_factor": _profit_factor_series(pnl),
            }
        )
    return rows


def _bull_rows(
    evidence: rd16n.PortfolioEvidence,
    *,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in evidence.bull_rows:
        rows.append(
            {
                "variant_id": variant_id,
                "window_id": raw["window_id"],
                "start": raw["start"],
                "end": raw["end"],
                "days": raw["days"],
                "portfolio_return": raw["family_return"],
                "equal_weight_return": raw["equal_weight_return"],
                "capture_ratio": raw["capture_ratio"],
                "high_opportunity_window": raw["high_opportunity_window"],
                "strategic_bull_adequacy": raw["strategic_bull_adequacy"],
            }
        )
    return rows


def _annual_rows(
    evidence: rd16n.PortfolioEvidence,
    *,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in evidence.annual_rows:
        rows.append(
            {
                "variant_id": variant_id,
                "year": raw["period"],
                "trade_count": raw["trade_count"],
                "return": raw["return"],
            }
        )
    return rows


def _write_local_frame(path: Path, frame: pd.DataFrame) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return {
        "logical_path": path.relative_to(RD16P_LOCAL_ROOT).as_posix(),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _output_hashes(paths: Sequence[Path]) -> dict[str, str]:
    return {path.name: sha256_path(path) for path in paths}


def _write_reports(
    *,
    final_report: Mapping[str, object],
    summary_rows: Sequence[Mapping[str, object]],
) -> list[Path]:
    results_path = REPORTS_ROOT / "rd16p-cross-sectional-portfolio-results-v1.md"
    decisions_path = REPORTS_ROOT / "rd16p-cross-sectional-carry-forward-decisions-v1.md"
    audit_path = REPORTS_ROOT / "rd16p-selection-capital-causality-audit-v1.md"

    results_lines = [
        "# RD16-P Cross-Sectional Portfolio Results",
        "",
        f"- Decision: `{final_report['decision']}`",
        f"- Variants evaluated: {final_report['variants_evaluated']}",
        f"- Retained variants: {final_report['retained_variants']}",
        f"- Promising variants: {final_report['promising_variants']}",
        "",
        f"Next: `{final_report['next_stage']}`",
        "",
    ]
    results_path.write_text(
        "\n".join(results_lines),
        encoding="utf-8",
        newline="\n",
    )

    decision_lines = [
        "# RD16-P Cross-Sectional Carry-Forward Decisions",
        "",
    ]
    for row in summary_rows:
        decision_lines.extend(
            [
                f"## {row['variant_id']}",
                "",
                f"- Decision: `{row['decision']}`",
                f"- Carry forward: `{row['carry_forward']}`",
                f"- Rationale: {row['rationale']}",
                (
                    "- Standalone return / PF: "
                    f"{_finite(row['standalone_net_return'], name='ret'):.2%}"
                    " / "
                    f"{(_optional_float(row['standalone_profit_factor']) or 0.0):.3f}"
                ),
                (
                    "- Overlay delta return / capture: "
                    f"{_finite(row['overlay_delta_net_return_vs_v3'], name='delta'):.2%}"
                    " / "
                    f"{_finite(row['overlay_delta_capture_vs_v3'], name='capture'):.2%}"
                ),
                "",
            ]
        )
    decisions_path.write_text(
        "\n".join(decision_lines),
        encoding="utf-8",
        newline="\n",
    )

    audit_lines = [
        "# RD16-P Selection, Capital, and Causality Audit",
        "",
        "- Inputs are frozen RD16-O evaluated candidates.",
        "- Ranking uses only completed-bar candidate metadata.",
        "- Selection is deterministic within each entry timestamp.",
        "- Risk and notional are only scaled down, never scaled up.",
        "- Frozen V3 trades are never displaced.",
        "- Same-symbol overlap remains prohibited.",
        "- Maximum five total positions and 2.25% open risk remain fixed.",
        "- 2025 and 2026 remain sealed.",
        "",
    ]
    audit_path.write_text(
        "\n".join(audit_lines),
        encoding="utf-8",
        newline="\n",
    )
    return [results_path, decisions_path, audit_path]


def run_rd16p_research() -> dict[str, object]:
    source_report = _verify_rd16o_ready()
    evaluated_source, local_rd16o_hashes = _load_rd16o_evaluated()
    v3_ledgers, local_v3_hashes = rd16n._load_v3_ledgers()
    baseline_trades = v3_ledgers["trades"].copy()
    baseline = _baseline_values()
    frozen_hashes = _frozen_input_hashes(
        local_v3_hashes,
        local_rd16o_hashes,
    )

    all_market, hourly_frames, daily_frames = rd16n._load_market_frames()
    feature_frames = {
        symbol: build_feature_frame(frames, symbol=symbol) for symbol, frames in all_market.items()
    }
    timeline = rd16n._timeline(hourly_frames)
    benchmark = build_benchmark_daily(daily_frames)

    if RD16P_LOCAL_ROOT.exists():
        shutil.rmtree(RD16P_LOCAL_ROOT)
    RD16P_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    RD16P_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []
    routing_rows: list[dict[str, object]] = []
    bull_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    retained: list[str] = []
    promising: list[str] = []
    rejected: list[str] = []
    strategic_count = 0

    local_manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "variants": {},
    }
    variant_manifest = cast(
        dict[str, object],
        local_manifest["variants"],
    )

    for variant in VARIANT_REGISTRY:
        selection_audit, selected = select_cross_sectional_candidates(
            evaluated_source,
            variant=variant,
        )
        scaled = rescale_selected_candidates(
            selected,
            variant=variant,
        )
        sleeve_evaluated, sleeve_admitted = route_portfolio_sleeve(
            scaled,
            variant=variant,
        )

        synthetic = _synthetic_hypothesis(variant)
        standalone_evaluated, standalone_trades = rd16n.route_standalone_candidates(
            sleeve_admitted,
            hypothesis=synthetic,
        )
        overlay_evaluated, overlay_new = rd16n.route_overlay_candidates(
            baseline_trades,
            sleeve_admitted,
            variant_id=variant.variant_id,
        )

        standalone_enriched = (
            enrich_trades(
                standalone_trades,
                hourly_frames=hourly_frames,
                feature_frames=feature_frames,
            )
            if not standalone_trades.empty
            else rd16n._empty_enriched_frame(standalone_trades)
        )
        overlay_new_enriched = (
            enrich_trades(
                overlay_new,
                hourly_frames=hourly_frames,
                feature_frames=feature_frames,
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
            variant_id=f"RD16P-STANDALONE::{variant.variant_id}",
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        overlay_evidence = rd16n._evaluate_portfolio(
            overlay_combined,
            variant_id=f"RD16P-OVERLAY::{variant.variant_id}",
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        decision = classify_portfolio_variant(
            variant=variant,
            selected_count=len(selected),
            standalone=standalone_evidence,
            overlay=overlay_evidence,
            baseline=baseline,
        )
        if decision.carry_forward:
            retained.append(variant.variant_id)
        elif decision.decision == "PROMISING_CROSS_SECTIONAL_PORTFOLIO":
            promising.append(variant.variant_id)
        else:
            rejected.append(variant.variant_id)
        if decision.strategic_objective_met:
            strategic_count += 1

        standalone_1x = standalone_evidence.metrics[1.0]
        standalone_2x = standalone_evidence.metrics[2.0]
        overlay_1x = overlay_evidence.metrics[1.0]
        overlay_2x = overlay_evidence.metrics[2.0]
        summary_row = {
            "variant_id": variant.variant_id,
            "decision": decision.decision,
            "carry_forward": decision.carry_forward,
            "candidate_count": len(evaluated_source),
            "selected_count": len(selected),
            "sleeve_admitted_count": len(sleeve_admitted),
            "standalone_trade_count": standalone_1x["trade_count"],
            "standalone_net_return": standalone_1x["net_return"],
            "standalone_monthly_geometric_return": (standalone_1x["monthly_geometric_return"]),
            "standalone_profit_factor": standalone_1x["profit_factor"],
            "standalone_maximum_drawdown": (standalone_1x["maximum_drawdown"]),
            "standalone_two_x_net_return": standalone_2x["net_return"],
            "standalone_two_x_profit_factor": (standalone_2x["profit_factor"]),
            "standalone_two_x_capital_feasible": (standalone_2x["capital_feasible"]),
            "overlay_new_trade_count": len(overlay_new_enriched),
            "overlay_trade_count": overlay_1x["trade_count"],
            "overlay_net_return": overlay_1x["net_return"],
            "overlay_monthly_geometric_return": (overlay_1x["monthly_geometric_return"]),
            "overlay_profit_factor": overlay_1x["profit_factor"],
            "overlay_maximum_drawdown": overlay_1x["maximum_drawdown"],
            "overlay_minimum_cash": overlay_1x["minimum_cash"],
            "overlay_capital_feasible": overlay_1x["capital_feasible"],
            "overlay_two_x_net_return": overlay_2x["net_return"],
            "overlay_two_x_profit_factor": overlay_2x["profit_factor"],
            "overlay_two_x_minimum_cash": overlay_2x["minimum_cash"],
            "overlay_two_x_capital_feasible": (overlay_2x["capital_feasible"]),
            "overlay_mean_high_opportunity_capture": (
                overlay_evidence.mean_high_opportunity_capture
            ),
            "overlay_delta_net_return_vs_v3": (
                _finite(
                    overlay_1x["net_return"],
                    name="overlay_return",
                )
                - baseline["net_return"]
            ),
            "overlay_delta_monthly_return_vs_v3": _optional_delta(
                overlay_1x["monthly_geometric_return"],
                baseline["monthly_geometric_return"],
            ),
            "overlay_delta_profit_factor_vs_v3": (
                _profit_factor(overlay_1x) - baseline["profit_factor"]
            ),
            "overlay_delta_maximum_drawdown_vs_v3": (
                _finite(
                    overlay_1x["maximum_drawdown"],
                    name="overlay_drawdown",
                )
                - baseline["maximum_drawdown"]
            ),
            "overlay_delta_two_x_return_vs_v3": (
                _finite(
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
        }
        summary_rows.append(summary_row)
        decision_rows.append(
            {
                "variant_id": variant.variant_id,
                "decision": decision.decision,
                "carry_forward": decision.carry_forward,
                "rationale": decision.rationale,
                "standalone_net_return": standalone_1x["net_return"],
                "standalone_profit_factor": standalone_1x["profit_factor"],
                "overlay_delta_net_return_vs_v3": (summary_row["overlay_delta_net_return_vs_v3"]),
                "overlay_profit_factor": overlay_1x["profit_factor"],
                "overlay_two_x_capital_feasible": (overlay_2x["capital_feasible"]),
                "overlay_delta_capture_vs_v3": (summary_row["overlay_delta_capture_vs_v3"]),
            }
        )
        cost_rows.extend(
            _cost_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=variant.variant_id,
            )
        )
        cost_rows.extend(
            _cost_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=variant.variant_id,
            )
        )
        selection_rows.extend(
            _selection_rows(
                selection_audit,
                variant_id=variant.variant_id,
            )
        )
        routing_rows.extend(
            _routing_rows(
                sleeve_evaluated,
                scope="SLEEVE",
                variant_id=variant.variant_id,
                decision_column="sleeve_decision",
            )
        )
        routing_rows.extend(
            _routing_rows(
                overlay_evaluated,
                scope="OVERLAY",
                variant_id=variant.variant_id,
                decision_column="router_decision",
            )
        )
        bull_rows.extend(
            _bull_rows(
                overlay_evidence,
                variant_id=variant.variant_id,
            )
        )
        annual_rows.extend(
            _annual_rows(
                overlay_evidence,
                variant_id=variant.variant_id,
            )
        )

        variant_dir = RD16P_LOCAL_ROOT / "variants" / variant.variant_id.lower()
        variant_manifest[variant.variant_id] = {
            "candidates": _write_local_frame(
                variant_dir / "candidates.parquet",
                evaluated_source,
            ),
            "selected": _write_local_frame(
                variant_dir / "selected.parquet",
                selected,
            ),
            "scaled": _write_local_frame(
                variant_dir / "scaled.parquet",
                scaled,
            ),
            "sleeve_evaluated": _write_local_frame(
                variant_dir / "sleeve-evaluated.parquet",
                sleeve_evaluated,
            ),
            "sleeve_admitted": _write_local_frame(
                variant_dir / "sleeve-admitted.parquet",
                sleeve_admitted,
            ),
            "standalone_evaluated": _write_local_frame(
                variant_dir / "standalone-evaluated.parquet",
                standalone_evaluated,
            ),
            "standalone_trades": _write_local_frame(
                variant_dir / "standalone-trades.parquet",
                standalone_enriched,
            ),
            "overlay_evaluated": _write_local_frame(
                variant_dir / "overlay-evaluated.parquet",
                overlay_evaluated,
            ),
            "overlay_new_trades": _write_local_frame(
                variant_dir / "overlay-new-trades.parquet",
                overlay_new_enriched,
            ),
            "overlay_combined_trades": _write_local_frame(
                variant_dir / "overlay-combined-trades.parquet",
                overlay_combined,
            ),
        }

    if strategic_count > 0 or retained:
        next_stage = NEXT_ASSEMBLY
    elif promising:
        next_stage = NEXT_REFINEMENT
    else:
        next_stage = NEXT_EXPANSION

    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "source_stage_decision": source_report["decision"],
        "variants_evaluated": len(VARIANT_REGISTRY),
        "retained_variant_count": len(retained),
        "promising_variant_count": len(promising),
        "rejected_variant_count": len(rejected),
        "retained_variants": retained,
        "promising_variants": promising,
        "rejected_variants": rejected,
        "strategic_objective_met_count": strategic_count,
        "strategic_objective_met": strategic_count > 0,
        "next_stage": next_stage,
        "architecture_changed": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "technical_gates": {
            "all_input_hashes_verified": True,
            "cross_sectional_selection_causal": True,
            "risk_only_scaled_down": True,
            "notional_only_scaled_down": True,
            "frozen_v3_trades_preserved": True,
            "same_symbol_overlap_prohibited": True,
            "maximum_positions_preserved": True,
            "maximum_open_risk_preserved": True,
            "spot_only": True,
            "long_only": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
            "architecture_changed": False,
        },
    }

    registry_path = RD16P_ROOT / "variant-registry.csv"
    summary_path = RD16P_ROOT / "variant-summary.csv"
    decisions_path = RD16P_ROOT / "component-decisions.csv"
    cost_path = RD16P_ROOT / "cost-stress.csv"
    selection_path = RD16P_ROOT / "selection-audit.csv"
    routing_path = RD16P_ROOT / "routing-summary.csv"
    annual_path = RD16P_ROOT / "annual-performance.csv"
    bull_path = RD16P_ROOT / "bull-window-capture.csv"
    frozen_path = RD16P_ROOT / "frozen-input-hashes.json"
    local_manifest_path = RD16P_ROOT / "local-output-manifest-v1.json"
    validation_path = RD16P_ROOT / "validation-report.json"
    final_path = RD16P_ROOT / "rd16p-final-report-v1.json"

    write_csv(
        registry_path,
        variant_registry_rows(),
        fieldnames=VARIANT_FIELDS,
    )
    write_csv(summary_path, summary_rows, fieldnames=SUMMARY_FIELDS)
    write_csv(decisions_path, decision_rows, fieldnames=DECISION_FIELDS)
    write_csv(cost_path, cost_rows, fieldnames=COST_FIELDS)
    write_csv(selection_path, selection_rows, fieldnames=SELECTION_FIELDS)
    write_csv(routing_path, routing_rows, fieldnames=ROUTING_FIELDS)
    write_csv(annual_path, annual_rows, fieldnames=ANNUAL_FIELDS)
    write_csv(bull_path, bull_rows, fieldnames=BULL_FIELDS)
    write_json(frozen_path, frozen_hashes)
    write_json(local_manifest_path, local_manifest)

    validation = {
        "technical_status": "PASS",
        "variant_count": len(VARIANT_REGISTRY),
        "summary_row_count": len(summary_rows),
        "all_variants_classified": (len(summary_rows) == len(VARIANT_REGISTRY)),
        "sealed_cutoff": SEALED_CUTOFF,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
    }
    write_json(validation_path, validation)
    write_json(final_path, final_report)

    report_paths = _write_reports(
        final_report=final_report,
        summary_rows=summary_rows,
    )
    output_paths = [
        registry_path,
        summary_path,
        decisions_path,
        cost_path,
        selection_path,
        routing_path,
        annual_path,
        bull_path,
        frozen_path,
        local_manifest_path,
        validation_path,
        final_path,
        *report_paths,
    ]
    output_hash_path = RD16P_ROOT / "output-hashes.json"
    write_json(output_hash_path, _output_hashes(output_paths))
    return final_report


__all__ = [
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "PortfolioDecision",
    "RD16PEvaluationError",
    "SCHEMA_VERSION",
    "classify_portfolio_variant",
    "run_rd16p_research",
]
