"""Metrics, parity checks, and decision gates for RD04-D5B2."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from spotbot.research.ams_md01_momentum import MD01FoldResult, MD01Trade

SCHEMA_VERSION = "ams-rd04-d5b2-structural-stop-evaluation-v1"
RESEARCH_STAGE = "RD04-D5B2"

DECISION_CONFIRMED = "STRUCTURAL_STOP_EDGE_CONFIRMED"
DECISION_COST_FRAGILE = "STRUCTURAL_STOP_EDGE_COST_FRAGILE"
DECISION_NOT_CONFIRMED = "STRUCTURAL_STOP_EDGE_NOT_CONFIRMED"
DECISION_BLOCKED = "STRUCTURAL_STOP_DATA_CONTRACT_BLOCKED"


class StructuralStopEvaluationError(RuntimeError):
    """Raised when D5B2 evidence is inconsistent or unsafe."""


def trade_cvar_10(trades: tuple[MD01Trade, ...] | list[MD01Trade]) -> float:
    if not trades:
        return 0.0
    returns = sorted(float(trade.return_fraction) for trade in trades)
    count = max(1, math.ceil(len(returns) * 0.10))
    return sum(returns[:count]) / count


def _canonical(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return "__NAN__"
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def full_result_equal(
    original: MD01FoldResult,
    generated_control: MD01FoldResult,
) -> bool:
    return bool(_canonical(asdict(original)) == _canonical(asdict(generated_control)))


def entry_fill_signature(result: MD01FoldResult) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        (
            fill.candidate_id,
            fill.position_id,
            fill.symbol,
            fill.timestamp,
            fill.price,
            fill.quantity,
            fill.notional,
            fill.fee,
            fill.cash_before,
            fill.cash_after,
        )
        for fill in result.fills
        if fill.fill_type == "ENTRY"
    )


def fold_improved(
    control: MD01FoldResult,
    treatment: MD01FoldResult,
) -> bool:
    control_return = control.final_cash / control.initial_capital - 1.0
    treatment_return = treatment.final_cash / treatment.initial_capital - 1.0
    return treatment_return > control_return


def comparison_metrics(
    *,
    control_aggregate: dict[str, Any],
    treatment_aggregate: dict[str, Any],
    control_results: list[MD01FoldResult],
    treatment_results: list[MD01FoldResult],
) -> dict[str, Any]:
    control_trades = [trade for result in control_results for trade in result.trades]
    treatment_trades = [trade for result in treatment_results for trade in result.trades]
    control_cvar = trade_cvar_10(control_trades)
    treatment_cvar = trade_cvar_10(treatment_trades)
    return {
        "compounded_return_delta": (
            float(treatment_aggregate["compounded_return"])
            - float(control_aggregate["compounded_return"])
        ),
        "expectancy_delta": (
            float(treatment_aggregate["expectancy"]) - float(control_aggregate["expectancy"])
        ),
        "maximum_drawdown_reduction": (
            float(control_aggregate["mean_maximum_drawdown"])
            - float(treatment_aggregate["mean_maximum_drawdown"])
        ),
        "trade_cvar_10_control": control_cvar,
        "trade_cvar_10_treatment": treatment_cvar,
        "trade_cvar_10_improvement": treatment_cvar - control_cvar,
        "improved_folds": sum(
            fold_improved(control, treatment)
            for control, treatment in zip(
                control_results,
                treatment_results,
                strict=True,
            )
        ),
        "control_trade_count": len(control_trades),
        "treatment_trade_count": len(treatment_trades),
        "stop_exit_count": sum(
            trade.exit_reason in {"STRUCTURAL_ATR_GAP_STOP", "STRUCTURAL_ATR_STOP"}
            for trade in treatment_trades
        ),
        "same_bar_stop_count": sum(
            trade.exit_reason in {"STRUCTURAL_ATR_GAP_STOP", "STRUCTURAL_ATR_STOP"}
            and trade.entry_time == trade.exit_time
            for trade in treatment_trades
        ),
    }


def build_decision(
    *,
    data_contract_passed: bool,
    control_replay_passed: bool,
    base_metrics: dict[str, Any],
    zero_metrics: dict[str, Any],
    stress_metrics: dict[str, Any],
) -> dict[str, Any]:
    structurally_valid = data_contract_passed and control_replay_passed
    if not structurally_valid:
        decision = DECISION_BLOCKED
    else:
        base_requirements = (
            float(base_metrics["compounded_return_delta"]) > 0.0
            and float(base_metrics["expectancy_delta"]) > 0.0
            and float(base_metrics["maximum_drawdown_reduction"]) > 0.0
            and float(base_metrics["trade_cvar_10_improvement"]) > 0.0
            and int(base_metrics["improved_folds"]) >= 2
        )
        stress_passed = float(stress_metrics["compounded_return_delta"]) >= 0.0
        if base_requirements and stress_passed:
            decision = DECISION_CONFIRMED
        elif base_requirements and float(zero_metrics["compounded_return_delta"]) > 0.0:
            decision = DECISION_COST_FRAGILE
        else:
            decision = DECISION_NOT_CONFIRMED

    complete = decision != DECISION_BLOCKED
    return {
        "decision": decision,
        "reason": {
            DECISION_CONFIRMED: "ALL_REGISTERED_PIT_STOP_GATES_PASSED",
            DECISION_COST_FRAGILE: ("BASE_AND_ZERO_COST_GATES_PASSED_BUT_STRESS_RETURN_FAILED"),
            DECISION_NOT_CONFIRMED: "REGISTERED_STOP_EDGE_GATES_NOT_MET",
            DECISION_BLOCKED: "DATA_OR_CONTROL_REPLAY_CONTRACT_FAILED",
        }[decision],
        "structural_pass": complete,
        "d5c_event_source_freeze_research_authorized": complete,
        "point_in_time_universe_research_baseline_authorized": False,
        "production_exit_change_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "entry_change_authorized": False,
        "weight_change_authorized": False,
        "live_ready": False,
        "production_ready": False,
        "ati_v1_authorized": False,
        "trade_logic_changed": False,
    }


def validate_report(report: dict[str, Any]) -> None:
    if report.get("status") != "COMPLETE":
        raise StructuralStopEvaluationError("D5B2 report is not COMPLETE.")
    if report.get("research_stage") != RESEARCH_STAGE:
        raise StructuralStopEvaluationError("D5B2 stage drifted.")
    decision = report.get("decision")
    if not isinstance(decision, dict):
        raise StructuralStopEvaluationError("D5B2 decision is missing.")
    if decision.get("decision") not in {
        DECISION_CONFIRMED,
        DECISION_COST_FRAGILE,
        DECISION_NOT_CONFIRMED,
    }:
        raise StructuralStopEvaluationError("D5B2 decision is invalid.")
    forbidden = (
        "point_in_time_universe_research_baseline_authorized",
        "production_exit_change_authorized",
        "universe_change_authorized",
        "ranking_change_authorized",
        "entry_change_authorized",
        "weight_change_authorized",
        "live_ready",
        "production_ready",
        "ati_v1_authorized",
        "trade_logic_changed",
    )
    if any(decision.get(field) is not False for field in forbidden):
        raise StructuralStopEvaluationError("D5B2 unsafe authorization.")
    validation = report.get("validation")
    if not isinstance(validation, dict):
        raise StructuralStopEvaluationError("D5B2 validation is missing.")
    required_true = (
        "data_contract_passed",
        "original_vs_generated_control_exact",
        "generated_control_matches_d1",
        "all_reconciliations_passed",
        "entry_logic_source_parity_passed",
        "position_weight_source_parity_passed",
    )
    if any(validation.get(field) is not True for field in required_true):
        raise StructuralStopEvaluationError("D5B2 required validation did not pass.")
    safety = report.get("safety")
    if not isinstance(safety, dict):
        raise StructuralStopEvaluationError("D5B2 safety is missing.")
    for field in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "parameter_optimisation_used",
        "outcome_based_stop_selection_used",
        "leverage_used",
        "margin_used",
        "shorting_used",
        "trade_logic_changed",
    ):
        if safety.get(field) is not False:
            raise StructuralStopEvaluationError(f"D5B2 unsafe field: {field}")


__all__ = [
    "DECISION_BLOCKED",
    "DECISION_CONFIRMED",
    "DECISION_COST_FRAGILE",
    "DECISION_NOT_CONFIRMED",
    "RESEARCH_STAGE",
    "SCHEMA_VERSION",
    "StructuralStopEvaluationError",
    "build_decision",
    "comparison_metrics",
    "entry_fill_signature",
    "fold_improved",
    "full_result_equal",
    "trade_cvar_10",
    "validate_report",
]
