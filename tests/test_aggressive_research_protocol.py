from datetime import UTC, datetime

import pytest

from spotbot.research.aggressive_research_protocol import (
    REQUIRED_SPOT_CONSTRAINTS,
    AggressivePerformanceObjective,
    AggressiveProtocolError,
    AggressiveResearchProtocol,
    StrategyHypothesis,
)


def objective() -> AggressivePerformanceObjective:
    return AggressivePerformanceObjective(
        monthly_compound_target=0.24,
        bull_market_annual_multiple_minimum=10.0,
        bull_market_annual_multiple_stretch=15.0,
        sideways_market_annual_multiple_minimum=3.0,
        sideways_market_annual_multiple_stretch=4.0,
        bear_market_annual_multiple_minimum=2.0,
    )


def hypothesis(
    *,
    hypothesis_id: str = "H1",
    evaluation_order: int = 1,
) -> StrategyHypothesis:
    return StrategyHypothesis(
        hypothesis_id=hypothesis_id,
        family="BREAKOUT",
        thesis="Frozen causal test.",
        evaluation_order=evaluation_order,
        parameters=(
            ("lookback_days", 20),
            ("maximum_positions", 2),
        ),
        principal_failure_mode=(
            "False breakout."
        ),
    )


def protocol(
    *,
    constraints: tuple[str, ...] = tuple(
        REQUIRED_SPOT_CONSTRAINTS
    ),
    hypotheses: tuple[
        StrategyHypothesis,
        ...,
    ] = (
        hypothesis(),
    ),
    research_end: datetime = datetime(
        2025,
        1,
        1,
        tzinfo=UTC,
    ),
) -> AggressiveResearchProtocol:
    return AggressiveResearchProtocol(
        protocol_id=(
            "AGGRESSIVE_MULTI_STRATEGY_V1"
        ),
        research_start=datetime(
            2021,
            1,
            1,
            tzinfo=UTC,
        ),
        research_end_exclusive=(
            research_end
        ),
        test_start=datetime(
            2025,
            1,
            1,
            tzinfo=UTC,
        ),
        holdout_start=datetime(
            2026,
            1,
            1,
            tzinfo=UTC,
        ),
        objective=objective(),
        constraints=constraints,
        hypotheses=hypotheses,
    )


def test_monthly_target_converts_to_correct_annual_multiple() -> None:
    result = objective()

    assert (
        result.annual_capital_multiple
        == pytest.approx(
            13.214788658781796
        )
    )

    assert (
        result.annual_compound_return
        == pytest.approx(
            12.214788658781796
        )
    )


def test_protocol_contains_all_spot_constraints() -> None:
    result = protocol()

    assert REQUIRED_SPOT_CONSTRAINTS.issubset(
        set(result.constraints)
    )


def test_missing_spot_constraint_is_rejected() -> None:
    incomplete = tuple(
        sorted(
            REQUIRED_SPOT_CONSTRAINTS
            - {
                "NO_LEVERAGE",
            }
        )
    )

    with pytest.raises(
        AggressiveProtocolError,
        match="Missing mandatory Spot",
    ):
        protocol(
            constraints=incomplete
        )


def test_research_cannot_enter_locked_test_period() -> None:
    with pytest.raises(
        AggressiveProtocolError,
        match="locked test period",
    ):
        protocol(
            research_end=datetime(
                2025,
                1,
                2,
                tzinfo=UTC,
            )
        )


def test_duplicate_hypothesis_ids_are_rejected() -> None:
    with pytest.raises(
        AggressiveProtocolError,
        match="Hypothesis IDs",
    ):
        protocol(
            hypotheses=(
                hypothesis(
                    hypothesis_id="H1",
                    evaluation_order=1,
                ),
                hypothesis(
                    hypothesis_id="H1",
                    evaluation_order=2,
                ),
            )
        )


def test_duplicate_parameter_names_are_rejected() -> None:
    with pytest.raises(
        AggressiveProtocolError,
        match="parameter names",
    ):
        StrategyHypothesis(
            hypothesis_id="H2",
            family="ROTATION",
            thesis="Invalid duplicate.",
            evaluation_order=2,
            parameters=(
                ("top_n", 2),
                ("top_n", 3),
            ),
            principal_failure_mode=(
                "Over-rotation."
            ),
        )


def test_serialization_preserves_frozen_registration() -> None:
    serialized = protocol().to_dict()

    registered = serialized[
        "hypotheses"
    ][0]

    assert (
        registered["status"]
        == "REGISTERED"
    )

    assert (
        registered[
            "parameters_frozen"
        ]
        is True
    )

    assert (
        serialized[
            "final_model_selection_allowed"
        ]
        is False
    )
