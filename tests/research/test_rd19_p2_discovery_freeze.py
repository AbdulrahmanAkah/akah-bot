"""Tests for the frozen RD19-P2 discovery design."""

from __future__ import annotations

import numpy as np

from spotbot.research.rd19_p2_discovery_freeze import (
    FACTOR_ORDER,
    VARIANT_COUNT,
    common_parameters,
    data_partition_rows,
    parameter_levels,
    plackett_burman_sign_matrix,
    protocol,
    selection_gate_rows,
    variant_rows,
)


def test_plackett_burman_matrix_is_balanced_and_orthogonal() -> None:
    matrix = np.asarray(plackett_burman_sign_matrix(), dtype=int)
    assert matrix.shape == (VARIANT_COUNT, len(FACTOR_ORDER))
    assert np.array_equal(matrix.sum(axis=0), np.zeros(len(FACTOR_ORDER)))
    gram = matrix.T @ matrix
    assert np.array_equal(
        gram,
        np.eye(len(FACTOR_ORDER), dtype=int) * VARIANT_COUNT,
    )


def test_variant_ids_and_factor_levels_are_unique() -> None:
    rows = variant_rows()
    assert len(rows) == 12
    assert len({row["variant_id"] for row in rows}) == 12
    for factor in FACTOR_ORDER:
        values = {row[factor] for row in rows}
        assert len(values) == 2


def test_parameter_levels_are_complete() -> None:
    levels = parameter_levels()
    assert set(levels) == set(FACTOR_ORDER)
    assert all(set(value) == {"LOW", "HIGH"} for value in levels.values())


def test_common_parameters_preserve_research_constraints() -> None:
    common = common_parameters()
    assert common["negative_cash_allowed"] is False
    assert common["leverage_allowed"] is False
    assert common["pyramiding_allowed"] is False
    assert common["post_2024_access"] is False
    assert common["cost_multipliers"] == [1.0, 2.0]


def test_post_2024_partition_is_sealed() -> None:
    post = next(
        row for row in data_partition_rows() if row["partition_id"] == "EXTERNAL_HOLDOUT_POST_2024"
    )
    assert post["variants_allowed"] == 0
    assert post["selection_use"] == "SEALED_UNTIL_P3_PREREGISTRATION"


def test_gates_include_two_x_and_turnover_requirements() -> None:
    gates = {row["gate_id"]: row for row in selection_gate_rows()}
    assert gates["TWO_X_NET_RETURN"]["threshold"] == "0.0"
    assert gates["TWO_X_WORST_UNIVERSE_MONTHLY_RETURN"]["threshold"] == "0.02"
    assert gates["TURNOVER_MATERIAL_REDUCTION"]["threshold"] == "240.0"


def test_protocol_does_not_authorize_execution() -> None:
    value = protocol()
    assert value["matrix_frozen"] is True
    assert value["parameters_frozen_for_p2"] is True
    assert value["p2_execution_authorized_now"] is False
    assert value["candidate_backtest_executed"] is False
