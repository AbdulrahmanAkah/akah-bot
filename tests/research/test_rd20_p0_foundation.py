from spotbot.research.rd20_p0_foundation import (
    COMPONENT_REGISTRY,
    PRE_ECONOMIC_GATES,
    RESEARCH_OBJECTIVE,
    TRADING_CONSTRAINTS,
    VALIDATION_PARTITIONS,
    first_candidate_components,
    validate_foundation_contract,
)


def test_foundation_contract_passes() -> None:
    validate_foundation_contract()


def test_first_candidate_is_minimal_trend_pullback() -> None:
    components = set(first_candidate_components())
    assert "TREND_PULLBACK_CONTINUATION" in components
    assert "MOMENTUM_BREAKOUT" not in components
    assert "VOLATILITY_EXPANSION" not in components
    assert "STRUCTURAL_REVERSAL_RECLAIM" not in components
    assert "ADAPTIVE_POSITION_SIZER" not in components
    assert "ADAPTIVE_FIVE_STATE_TRAILING" not in components
    assert "DYNAMIC_PARTIAL_SELLING" not in components


def test_objective_does_not_force_return_or_cap_winners() -> None:
    assert RESEARCH_OBJECTIVE["daily_growth_is_hard_gate"] is False
    assert RESEARCH_OBJECTIVE["monthly_growth_is_hard_gate"] is False
    assert RESEARCH_OBJECTIVE["forced_daily_trading"] is False
    assert RESEARCH_OBJECTIVE["upside_cap"] is None
    assert RESEARCH_OBJECTIVE["preferred_maximum_drawdown"] == 0.15
    assert RESEARCH_OBJECTIVE["hard_maximum_drawdown"] == 0.20


def test_execution_constraints_are_preserved() -> None:
    assert TRADING_CONSTRAINTS["spot_only"] is True
    assert TRADING_CONSTRAINTS["long_only"] is True
    assert TRADING_CONSTRAINTS["leverage"] is False
    assert TRADING_CONSTRAINTS["margin"] is False
    assert TRADING_CONSTRAINTS["negative_cash"] is False
    assert TRADING_CONSTRAINTS["maximum_simultaneous_positions"] == 5


def test_pre_pnl_conformance_is_blocking() -> None:
    gates = {row["gate_id"]: row for row in PRE_ECONOMIC_GATES}
    for gate_id in (
        "PARAMETER_UTILIZATION_COMPLETE",
        "ENGINE_EQUIVALENCE_OR_SINGLE_ENGINE",
        "COMPLETED_BAR_CAUSALITY",
        "HORIZON_ALIGNMENT_PASS",
        "SURVIVAL_BUDGET_REPORTED",
        "CONCENTRATION_DIAGNOSTICS_DEFINED",
        "SEALED_DATA_GUARD_PASS",
    ):
        assert gates[gate_id]["blocking"] is True


def test_holdouts_remain_sealed() -> None:
    partitions = {row["partition_id"]: row for row in VALIDATION_PARTITIONS}
    assert partitions["INTERNAL_CONFIRMATION_2024"]["sealed"] is True
    assert partitions["FINAL_HOLDOUT_2025_PLUS"]["sealed"] is True


def test_adaptive_complexity_is_reserved_but_deferred() -> None:
    status = {row["component_id"]: row["initial_status"] for row in COMPONENT_REGISTRY}
    assert status["ADAPTIVE_POSITION_SIZER"].startswith("DEFERRED")
    assert status["ADAPTIVE_FIVE_STATE_TRAILING"].startswith("DEFERRED")
    assert status["DYNAMIC_PARTIAL_SELLING"].startswith("DEFERRED")
    assert status["CAPITAL_REPLACEMENT_ARBITRATION"].startswith("DEFERRED")
    assert status["QUANTITATIVE_REENTRY_POLICY"].startswith("DEFERRED")
