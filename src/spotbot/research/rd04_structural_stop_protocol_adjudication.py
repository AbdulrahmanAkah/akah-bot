"""RD04-D5B1 adjudication for a V5R1-derived exit-only stop overlay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "ams-rd04-d5b1-stop-protocol-adjudication-v1"
RESEARCH_STAGE = "RD04-D5B1"

DECISION_REGISTERED = "V5R1_DERIVED_EXIT_ONLY_STOP_OVERLAY_REGISTERED"
DECISION_BLOCKED = "STOP_PROTOCOL_ADJUDICATION_BLOCKED"

MINIMUM_ATR = 2.2
MAXIMUM_ATR = 3.4
ATR_PERIOD = 14
STRUCTURE_LOOKBACK_BARS = 12
STRUCTURE_MIN_PERIODS = 6


class StopProtocolAdjudicationError(RuntimeError):
    """Raised when the D5B1 protocol contract is invalid."""


@dataclass(frozen=True)
class StopLevel:
    signal_close: float
    atr: float
    structural_reference: float
    raw_distance_atr: float
    applied_distance_atr: float
    stop_price: float
    classification: str


@dataclass(frozen=True)
class StopExecution:
    hit: bool
    exit_price: float | None
    reason: str | None


def derive_exit_only_stop(
    *,
    signal_close: float,
    atr: float,
    structural_reference: float,
) -> StopLevel:
    """Derive the frozen D5B1 stop without rejecting or resizing an M05 entry."""
    values = (signal_close, atr, structural_reference)
    if not all(math.isfinite(value) for value in values):
        raise StopProtocolAdjudicationError("stop inputs must be finite")
    if signal_close <= 0 or atr <= 0 or structural_reference <= 0:
        raise StopProtocolAdjudicationError("stop inputs must be positive")

    raw_distance_atr = (signal_close - structural_reference) / atr
    applied_distance_atr = min(max(raw_distance_atr, MINIMUM_ATR), MAXIMUM_ATR)

    if raw_distance_atr <= 0:
        classification = "NONPOSITIVE_STRUCTURE_FLOOR_FALLBACK"
    elif raw_distance_atr < MINIMUM_ATR:
        classification = "MINIMUM_ATR_FLOOR"
    elif raw_distance_atr <= MAXIMUM_ATR:
        classification = "STRUCTURE_WITHIN_BOUNDS"
    else:
        classification = "MAXIMUM_ATR_CAP"

    stop_price = signal_close - applied_distance_atr * atr
    if not math.isfinite(stop_price) or stop_price <= 0:
        raise StopProtocolAdjudicationError("derived stop price is invalid")
    if stop_price >= signal_close:
        raise StopProtocolAdjudicationError("derived stop must be below signal close")

    return StopLevel(
        signal_close=signal_close,
        atr=atr,
        structural_reference=structural_reference,
        raw_distance_atr=raw_distance_atr,
        applied_distance_atr=applied_distance_atr,
        stop_price=stop_price,
        classification=classification,
    )


def execute_known_stop(
    *,
    bar_open: float,
    bar_low: float,
    stop_price: float,
) -> StopExecution:
    """Apply a stop known before the bar using the V5R1 gap/intrabar convention."""
    values = (bar_open, bar_low, stop_price)
    if not all(math.isfinite(value) for value in values):
        raise StopProtocolAdjudicationError("execution inputs must be finite")
    if min(values) <= 0:
        raise StopProtocolAdjudicationError("execution prices must be positive")
    if bar_low > bar_open:
        raise StopProtocolAdjudicationError("bar low cannot exceed bar open")

    if bar_open <= stop_price:
        return StopExecution(True, bar_open, "STRUCTURAL_ATR_GAP_STOP")
    if bar_low <= stop_price:
        return StopExecution(True, stop_price, "STRUCTURAL_ATR_STOP")
    return StopExecution(False, None, None)


def conflict_resolutions() -> tuple[dict[str, str], ...]:
    """Return the four frozen resolutions required to isolate the stop exit."""
    return (
        {
            "conflict_id": "ENTRY_REJECTION_VS_ENTRY_PARITY",
            "legacy_v5r1": (
                "Reject a candidate when structural distance is nonpositive, "
                "exceeds 3.4 ATR, or the next-open gap invalidates the stop."
            ),
            "d4_constraint": "Same M05 entry logic.",
            "resolution": (
                "Never reject an otherwise valid M05 entry. Clip the signal-time "
                "structural distance to the closed interval [2.2, 3.4] ATR."
            ),
        },
        {
            "conflict_id": "RISK_SIZING_VS_WEIGHT_PARITY",
            "legacy_v5r1": "Size quantity from requested risk divided by stop distance.",
            "d4_constraint": "Same M05 position weights.",
            "resolution": (
                "Preserve the exact M05 entry fill quantity and cash accounting. "
                "The stop may alter exits only."
            ),
        },
        {
            "conflict_id": "V5R1_EXIT_BUNDLE_VS_SINGLE_ABLATION",
            "legacy_v5r1": (
                "Includes initial stop, trailing stop, structural exit, stagnation "
                "exit, add-ons, and one re-entry."
            ),
            "d4_constraint": "Test the structural ATR stop in isolation.",
            "resolution": (
                "Enable one fixed initial stop only. Disable all other V5R1 exits, "
                "trailing, add-ons, risk throttles, and V5R1 re-entry."
            ),
        },
        {
            "conflict_id": "SIGNAL_STOP_VS_NEXT_OPEN_GAP",
            "legacy_v5r1": (
                "Freeze the structural reference at signal close, then reject an "
                "entry if the next-open gap invalidates the bounded distance."
            ),
            "d4_constraint": "Preserve the M05 entry fill.",
            "resolution": (
                "Freeze the stop price at signal close. Fill M05 at the normal "
                "next open; if that open is at or below the stop, exit immediately "
                "at the same open and charge both entry and exit costs."
            ),
        },
    )


def adjudicated_contract() -> dict[str, Any]:
    """Build the complete frozen protocol for the later D5B2 execution."""
    return {
        "identity": {
            "contract_id": "RD04-D5B1-V5R1-DERIVED-EXIT-ONLY-OVERLAY",
            "source_model": "V5R1_STRUCTURE_BALANCED",
            "derivation_status": "AMENDED_FOR_D4_ENTRY_AND_WEIGHT_PARITY",
            "not_exact_legacy_v5r1_bundle": True,
        },
        "control": {
            "portfolio": "MD01_M05",
            "universes": ["FIXED", "PIT"],
            "tactical_stop": "NONE",
            "entry_logic_changed": False,
            "position_weights_changed": False,
        },
        "treatment": {
            "portfolio": "MD01_M05",
            "universes": ["FIXED", "PIT"],
            "overlay": "V5R1_DERIVED_BOUNDED_STRUCTURAL_FIXED_STOP",
            "entry_logic_changed": False,
            "position_weights_changed": False,
            "stop_only_exit_change": True,
        },
        "feature_contract": {
            "timeframe": "4H",
            "signal_information_cutoff": "COMPLETED_SIGNAL_BAR_CLOSE",
            "atr_definition": "SMA_TRUE_RANGE",
            "atr_period": ATR_PERIOD,
            "structure_definition": "PRIOR_12_COMPLETED_4H_BAR_LOW_MINIMUM",
            "structure_lookback_bars": STRUCTURE_LOOKBACK_BARS,
            "structure_min_periods": STRUCTURE_MIN_PERIODS,
            "signal_bar_excluded_from_structure": True,
            "future_data_allowed": False,
        },
        "stop_formula": {
            "raw_distance_atr": "(signal_close - prior_12_bar_low) / atr14",
            "applied_distance_atr": "clip(raw_distance_atr, 2.2, 3.4)",
            "minimum_atr": MINIMUM_ATR,
            "maximum_atr": MAXIMUM_ATR,
            "stop_price": "signal_close - applied_distance_atr * atr14",
            "entry_rejection_allowed": False,
            "position_resizing_allowed": False,
        },
        "execution_order": [
            "VENUE_EXIT_AT_BAR_OPEN",
            "KNOWN_STOP_GAP_CHECK_AT_BAR_OPEN",
            "SCHEDULED_M05_EXIT_AT_BAR_OPEN",
            "NORMAL_M05_ENTRY_AT_BAR_OPEN",
            "KNOWN_STOP_INTRABAR_LOW_CHECK",
            "M05_SIGNAL_GENERATION_AFTER_BAR_CLOSE",
        ],
        "execution_contract": {
            "stop_active_from_entry_bar": True,
            "gap_rule": "OPEN_IF_OPEN_LE_STOP",
            "intrabar_rule": "STOP_PRICE_IF_LOW_LE_STOP",
            "fixed_stop": True,
            "trailing_allowed": False,
            "same_bar_entry_and_stop_allowed": True,
            "same_bar_round_trip_costs_charged": True,
            "stop_exit_reason": "STRUCTURAL_ATR_STOP_EXIT",
        },
        "excluded_v5r1_components": [
            "V5R1_RISK_SIZING",
            "DRAWDOWN_THROTTLE",
            "PORTFOLIO_HEAT",
            "ADD_ON",
            "V5R1_REENTRY",
            "TRAILING_STOP",
            "STRUCTURE_EXIT",
            "STAGNATION_EXIT",
            "V5R1_SIGNAL_FAMILIES",
            "V5R1_FIBONACCI_SCORING",
        ],
        "comparison_contract": {
            "cost_modes": {
                "ZERO_COST": 0.0,
                "BASE_COST": 0.002,
                "STRESS_0_4_PERCENT": 0.004,
            },
            "folds": ["WF01", "WF02", "WF03"],
            "control_replay_must_match_d1": True,
            "same_market_data": True,
            "same_universe_schedule": True,
            "same_entry_logic": True,
            "same_entry_weight": True,
            "full_costed_fold_liquidation": True,
        },
        "metrics": {
            "primary": [
                "pit_base_cost_compounded_return_delta",
                "pit_base_cost_expectancy_delta",
                "pit_maximum_drawdown_reduction",
                "pit_trade_cvar_10_improvement",
            ],
            "secondary": [
                "fixed_vs_pit_stop_delta",
                "stress_cost_compounded_return_delta",
                "stopped_trade_recovery_mfe",
                "stop_exit_count",
                "same_bar_stop_count",
                "minimum_floor_count",
                "within_bounds_count",
                "maximum_cap_count",
            ],
            "trade_cvar_10": (
                "Mean return_fraction of the worst max(1, ceil(10 percent of "
                "trade_count)) closed trades, calculated separately per portfolio "
                "and cost mode."
            ),
            "stopped_trade_recovery_mfe": (
                "For a stopped treatment trade matched to the control entry by "
                "fold, universe, symbol, candidate_id, and entry_time: maximum high "
                "after stop exit through the matched control exit, divided by the "
                "treatment stop-exit price, minus one."
            ),
        },
        "decision_gate": {
            "confirmed": {
                "decision": "STRUCTURAL_STOP_EDGE_CONFIRMED",
                "requirements": [
                    "PIT base compounded return delta > 0",
                    "PIT base expectancy delta > 0",
                    "PIT maximum drawdown reduction > 0",
                    "PIT trade CVaR10 improvement > 0",
                    "At least 2 of 3 PIT base folds improve",
                    "PIT stress compounded return delta >= 0",
                ],
            },
            "cost_fragile": {
                "decision": "STRUCTURAL_STOP_EDGE_COST_FRAGILE",
                "requirements": [
                    "All confirmed requirements except stress return pass",
                    "PIT zero-cost compounded return delta > 0",
                ],
            },
            "not_confirmed": {
                "decision": "STRUCTURAL_STOP_EDGE_NOT_CONFIRMED",
                "requirements": ["Confirmed and cost-fragile gates both fail"],
            },
            "blocked": {
                "decision": "STRUCTURAL_STOP_DATA_CONTRACT_BLOCKED",
                "requirements": ["Any causal, replay, reconciliation, or data gate fails"],
            },
        },
        "safety": {
            "spot_only": True,
            "long_only": True,
            "leverage_allowed": False,
            "margin_allowed": False,
            "shorting_allowed": False,
            "test_2025_allowed": False,
            "holdout_2026_allowed": False,
            "parameter_search_allowed": False,
            "outcome_based_stop_selection_allowed": False,
        },
        "conflict_resolutions": list(conflict_resolutions()),
    }


def validate_contract(contract: dict[str, Any]) -> None:
    """Reject any drift from the registered D5B1 exit-only protocol."""
    identity = contract.get("identity")
    treatment = contract.get("treatment")
    formula = contract.get("stop_formula")
    execution = contract.get("execution_contract")
    comparison = contract.get("comparison_contract")
    safety = contract.get("safety")
    conflicts = contract.get("conflict_resolutions")

    if not isinstance(identity, dict) or not identity.get("not_exact_legacy_v5r1_bundle"):
        raise StopProtocolAdjudicationError("contract identity is invalid")
    if not isinstance(treatment, dict) or treatment.get("stop_only_exit_change") is not True:
        raise StopProtocolAdjudicationError("treatment is not exit-only")
    if treatment.get("entry_logic_changed") is not False:
        raise StopProtocolAdjudicationError("entry logic changed")
    if treatment.get("position_weights_changed") is not False:
        raise StopProtocolAdjudicationError("position weights changed")
    if not isinstance(formula, dict):
        raise StopProtocolAdjudicationError("stop formula is missing")
    if formula.get("minimum_atr") != MINIMUM_ATR:
        raise StopProtocolAdjudicationError("minimum ATR drifted")
    if formula.get("maximum_atr") != MAXIMUM_ATR:
        raise StopProtocolAdjudicationError("maximum ATR drifted")
    if formula.get("entry_rejection_allowed") is not False:
        raise StopProtocolAdjudicationError("entry rejection was enabled")
    if formula.get("position_resizing_allowed") is not False:
        raise StopProtocolAdjudicationError("position resizing was enabled")
    if not isinstance(execution, dict) or execution.get("fixed_stop") is not True:
        raise StopProtocolAdjudicationError("fixed-stop contract is missing")
    if execution.get("trailing_allowed") is not False:
        raise StopProtocolAdjudicationError("trailing was enabled")
    if not isinstance(comparison, dict):
        raise StopProtocolAdjudicationError("comparison contract is missing")
    if comparison.get("control_replay_must_match_d1") is not True:
        raise StopProtocolAdjudicationError("D1 replay gate is missing")
    if not isinstance(safety, dict):
        raise StopProtocolAdjudicationError("safety contract is missing")
    prohibited = (
        "leverage_allowed",
        "margin_allowed",
        "shorting_allowed",
        "test_2025_allowed",
        "holdout_2026_allowed",
        "parameter_search_allowed",
        "outcome_based_stop_selection_allowed",
    )
    if any(safety.get(field) is not False for field in prohibited):
        raise StopProtocolAdjudicationError("a prohibited capability was enabled")
    if not isinstance(conflicts, list) or len(conflicts) != 4:
        raise StopProtocolAdjudicationError("conflict resolution set is incomplete")


def contract_rows(contract: dict[str, Any]) -> list[dict[str, str]]:
    """Flatten the frozen contract into deterministic audit rows."""
    rows: list[dict[str, str]] = []

    def visit(section: str, value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                next_path = f"{path}.{key}" if path else str(key)
                visit(section, value[key], next_path)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                next_path = f"{path}[{index}]"
                visit(section, item, next_path)
            return
        rows.append(
            {
                "section": section,
                "field": path,
                "value": str(value),
            }
        )

    for section in sorted(contract):
        if section == "conflict_resolutions":
            continue
        visit(section, contract[section])
    return rows


def conflict_rows() -> list[dict[str, str]]:
    """Return CSV-ready conflict-resolution records."""
    return [dict(item) for item in conflict_resolutions()]


def report_decision(*, upstream_valid: bool, contract_valid: bool) -> dict[str, Any]:
    """Build the D5B1 registration decision without executing a simulation."""
    passed = upstream_valid and contract_valid
    return {
        "decision": DECISION_REGISTERED if passed else DECISION_BLOCKED,
        "reason": (
            "EXIT_ONLY_OVERLAY_RESOLVES_D4_V5R1_CONFLICTS_WITHOUT_OUTCOME_SELECTION"
            if passed
            else "UPSTREAM_OR_CONTRACT_VALIDATION_FAILED"
        ),
        "structural_pass": passed,
        "d5b2_stop_execution_research_authorized": passed,
        "legacy_exact_v5r1_bundle_execution_authorized": False,
        "point_in_time_universe_research_baseline_authorized": False,
        "entry_change_authorized": False,
        "weight_change_authorized": False,
        "production_exit_change_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "live_ready": False,
        "production_ready": False,
        "ati_v1_authorized": False,
        "trade_logic_changed": False,
    }


def validate_report(report: dict[str, Any]) -> None:
    """Validate the final D5B1 evidence report."""
    if report.get("status") != "COMPLETE":
        raise StopProtocolAdjudicationError("report status is not COMPLETE")
    if report.get("research_stage") != RESEARCH_STAGE:
        raise StopProtocolAdjudicationError("research stage drifted")
    decision = report.get("decision")
    if not isinstance(decision, dict):
        raise StopProtocolAdjudicationError("report decision is missing")
    if decision.get("decision") != DECISION_REGISTERED:
        raise StopProtocolAdjudicationError("registration decision failed")
    if decision.get("d5b2_stop_execution_research_authorized") is not True:
        raise StopProtocolAdjudicationError("D5B2 research was not authorized")
    forbidden_true = (
        "legacy_exact_v5r1_bundle_execution_authorized",
        "point_in_time_universe_research_baseline_authorized",
        "entry_change_authorized",
        "weight_change_authorized",
        "production_exit_change_authorized",
        "universe_change_authorized",
        "ranking_change_authorized",
        "live_ready",
        "production_ready",
        "ati_v1_authorized",
        "trade_logic_changed",
    )
    if any(decision.get(field) is not False for field in forbidden_true):
        raise StopProtocolAdjudicationError("unsafe report authorization")
    safety = report.get("safety")
    if not isinstance(safety, dict):
        raise StopProtocolAdjudicationError("report safety record is missing")
    for field in (
        "portfolio_simulation_executed",
        "market_data_read",
        "test_2025_accessed",
        "holdout_2026_accessed",
        "parameter_optimisation_used",
        "outcome_based_stop_selection_used",
        "trade_logic_changed",
    ):
        if safety.get(field) is not False:
            raise StopProtocolAdjudicationError(f"unsafe report field: {field}")


__all__ = [
    "ATR_PERIOD",
    "DECISION_BLOCKED",
    "DECISION_REGISTERED",
    "MAXIMUM_ATR",
    "MINIMUM_ATR",
    "RESEARCH_STAGE",
    "SCHEMA_VERSION",
    "STRUCTURE_LOOKBACK_BARS",
    "STRUCTURE_MIN_PERIODS",
    "StopExecution",
    "StopLevel",
    "StopProtocolAdjudicationError",
    "adjudicated_contract",
    "conflict_resolutions",
    "conflict_rows",
    "contract_rows",
    "derive_exit_only_stop",
    "execute_known_stop",
    "report_decision",
    "validate_contract",
    "validate_report",
]
