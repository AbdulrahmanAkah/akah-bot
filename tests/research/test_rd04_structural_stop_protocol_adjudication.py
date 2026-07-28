from __future__ import annotations

import math

import pytest

from spotbot.research.rd04_structural_stop_protocol_adjudication import (
    DECISION_BLOCKED,
    DECISION_REGISTERED,
    MAXIMUM_ATR,
    MINIMUM_ATR,
    StopProtocolAdjudicationError,
    adjudicated_contract,
    conflict_resolutions,
    contract_rows,
    derive_exit_only_stop,
    execute_known_stop,
    report_decision,
    validate_contract,
    validate_report,
)


def test_minimum_floor_is_applied() -> None:
    level = derive_exit_only_stop(
        signal_close=100.0,
        atr=10.0,
        structural_reference=90.0,
    )
    assert level.raw_distance_atr == pytest.approx(1.0)
    assert level.applied_distance_atr == MINIMUM_ATR
    assert level.stop_price == pytest.approx(78.0)
    assert level.classification == "MINIMUM_ATR_FLOOR"


def test_structure_within_bounds_is_preserved() -> None:
    level = derive_exit_only_stop(
        signal_close=100.0,
        atr=10.0,
        structural_reference=72.0,
    )
    assert level.raw_distance_atr == pytest.approx(2.8)
    assert level.applied_distance_atr == pytest.approx(2.8)
    assert level.stop_price == pytest.approx(72.0)
    assert level.classification == "STRUCTURE_WITHIN_BOUNDS"


def test_maximum_cap_is_applied() -> None:
    level = derive_exit_only_stop(
        signal_close=100.0,
        atr=10.0,
        structural_reference=50.0,
    )
    assert level.raw_distance_atr == pytest.approx(5.0)
    assert level.applied_distance_atr == MAXIMUM_ATR
    assert level.stop_price == pytest.approx(66.0)
    assert level.classification == "MAXIMUM_ATR_CAP"


def test_nonpositive_structural_distance_uses_floor() -> None:
    level = derive_exit_only_stop(
        signal_close=100.0,
        atr=10.0,
        structural_reference=105.0,
    )
    assert level.raw_distance_atr == pytest.approx(-0.5)
    assert level.applied_distance_atr == MINIMUM_ATR
    assert level.classification == "NONPOSITIVE_STRUCTURE_FLOOR_FALLBACK"


@pytest.mark.parametrize(
    ("signal_close", "atr", "structure"),
    [
        (math.nan, 1.0, 90.0),
        (100.0, 0.0, 90.0),
        (100.0, -1.0, 90.0),
        (100.0, 1.0, 0.0),
    ],
)
def test_invalid_stop_inputs_are_rejected(
    signal_close: float,
    atr: float,
    structure: float,
) -> None:
    with pytest.raises(StopProtocolAdjudicationError):
        derive_exit_only_stop(
            signal_close=signal_close,
            atr=atr,
            structural_reference=structure,
        )


def test_gap_stop_uses_bar_open() -> None:
    execution = execute_known_stop(
        bar_open=79.0,
        bar_low=75.0,
        stop_price=80.0,
    )
    assert execution.hit is True
    assert execution.exit_price == 79.0
    assert execution.reason == "STRUCTURAL_ATR_GAP_STOP"


def test_intrabar_stop_uses_stop_price() -> None:
    execution = execute_known_stop(
        bar_open=85.0,
        bar_low=79.0,
        stop_price=80.0,
    )
    assert execution.hit is True
    assert execution.exit_price == 80.0
    assert execution.reason == "STRUCTURAL_ATR_STOP"


def test_non_hit_returns_no_exit() -> None:
    execution = execute_known_stop(
        bar_open=85.0,
        bar_low=81.0,
        stop_price=80.0,
    )
    assert execution.hit is False
    assert execution.exit_price is None
    assert execution.reason is None


def test_invalid_bar_is_rejected() -> None:
    with pytest.raises(StopProtocolAdjudicationError):
        execute_known_stop(
            bar_open=80.0,
            bar_low=81.0,
            stop_price=75.0,
        )


def test_exactly_four_conflicts_are_registered() -> None:
    conflicts = conflict_resolutions()
    assert len(conflicts) == 4
    assert len({item["conflict_id"] for item in conflicts}) == 4


def test_contract_is_exit_only_and_frozen() -> None:
    contract = adjudicated_contract()
    validate_contract(contract)
    treatment = contract["treatment"]
    formula = contract["stop_formula"]
    execution = contract["execution_contract"]
    assert treatment["entry_logic_changed"] is False
    assert treatment["position_weights_changed"] is False
    assert treatment["stop_only_exit_change"] is True
    assert formula["minimum_atr"] == 2.2
    assert formula["maximum_atr"] == 3.4
    assert formula["entry_rejection_allowed"] is False
    assert execution["fixed_stop"] is True
    assert execution["trailing_allowed"] is False


def test_contract_excludes_v5r1_bundle_components() -> None:
    excluded = set(adjudicated_contract()["excluded_v5r1_components"])
    assert {
        "V5R1_RISK_SIZING",
        "ADD_ON",
        "V5R1_REENTRY",
        "TRAILING_STOP",
        "STRUCTURE_EXIT",
        "STAGNATION_EXIT",
    }.issubset(excluded)


def test_contract_rows_are_deterministic() -> None:
    first = contract_rows(adjudicated_contract())
    second = contract_rows(adjudicated_contract())
    assert first == second
    assert first
    assert all(set(row) == {"section", "field", "value"} for row in first)


def test_report_decision_authorizes_research_only() -> None:
    decision = report_decision(upstream_valid=True, contract_valid=True)
    assert decision["decision"] == DECISION_REGISTERED
    assert decision["d5b2_stop_execution_research_authorized"] is True
    assert decision["legacy_exact_v5r1_bundle_execution_authorized"] is False
    assert decision["production_exit_change_authorized"] is False
    assert decision["trade_logic_changed"] is False


def test_report_decision_blocks_invalid_upstream() -> None:
    decision = report_decision(upstream_valid=False, contract_valid=True)
    assert decision["decision"] == DECISION_BLOCKED
    assert decision["d5b2_stop_execution_research_authorized"] is False


def test_validate_report_accepts_safe_registration() -> None:
    report = {
        "status": "COMPLETE",
        "research_stage": "RD04-D5B1",
        "decision": report_decision(
            upstream_valid=True,
            contract_valid=True,
        ),
        "safety": {
            "portfolio_simulation_executed": False,
            "market_data_read": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "outcome_based_stop_selection_used": False,
            "trade_logic_changed": False,
        },
    }
    validate_report(report)


def test_validate_report_rejects_simulation() -> None:
    report = {
        "status": "COMPLETE",
        "research_stage": "RD04-D5B1",
        "decision": report_decision(
            upstream_valid=True,
            contract_valid=True,
        ),
        "safety": {
            "portfolio_simulation_executed": True,
            "market_data_read": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "parameter_optimisation_used": False,
            "outcome_based_stop_selection_used": False,
            "trade_logic_changed": False,
        },
    }
    with pytest.raises(StopProtocolAdjudicationError):
        validate_report(report)
