from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd43_direct_utility_transport import (
    DECISION_BIDIRECTIONAL,
    DECISION_REGIME_DEPENDENT,
    DECISION_UNQUALIFIED,
    apply_empirical_cdf,
    auc_binary,
    design_matrix,
    empirical_cdf_reference,
    fit_model,
    landmark_qualification,
    normalize_joined_ledger,
    predict,
    spearman,
    temporal_persistence,
    validate_constants,
)


def test_constants() -> None:
    validate_constants()


def test_training_empirical_cdf_uses_right_count() -> None:
    ref = empirical_cdf_reference(np.array([1.0, 2.0, 2.0, 4.0]))
    values = apply_empirical_cdf(
        ref,
        np.array([0.0, 1.0, 2.0, 3.0, 5.0]),
    )
    assert np.allclose(values, [0.0, 0.25, 0.75, 0.75, 1.0])


def test_design_matrix_is_fixed_four_columns() -> None:
    x = design_matrix(
        np.array([0.2, 0.8]),
        np.array([0.3, 0.7]),
    )
    assert x.shape == (2, 4)
    assert np.allclose(x[:, 3], x[:, 1] * x[:, 2])


def test_ols_round_trip_on_fixed_basis() -> None:
    rows = []
    for i in range(1, 41):
        h = float(i)
        p = float((i * 7) % 41)
        rows.append(
            {
                "high_water_gain_atr": h,
                "pullback_from_high_water_atr": p,
            }
        )
    train = pd.DataFrame(rows)
    h_ref = empirical_cdf_reference(train["high_water_gain_atr"].to_numpy())
    p_ref = empirical_cdf_reference(train["pullback_from_high_water_atr"].to_numpy())
    h = apply_empirical_cdf(h_ref, train["high_water_gain_atr"].to_numpy())
    p = apply_empirical_cdf(
        p_ref,
        train["pullback_from_high_water_atr"].to_numpy(),
    )
    x = design_matrix(h, p)
    beta = np.array([0.1, 0.2, -0.4, 0.3])
    train["rcv_return"] = x @ beta
    model = fit_model(train)
    pred = predict(model, train)
    assert model.design_rank == 4
    assert np.allclose(pred, train["rcv_return"].to_numpy(), atol=1e-10)


def test_spearman_and_auc_direction() -> None:
    actual = np.array([-3.0, -2.0, 1.0, 2.0])
    pred = np.array([-2.5, -1.5, 0.5, 1.5])
    assert spearman(pred, actual) > 0.99
    event = actual < 0.0
    assert auc_binary(event, -pred) > 0.99


def test_join_requires_exact_decision_registry() -> None:
    state = pd.DataFrame(
        {
            "decision_id": ["A"],
            "control_position_id": ["P"],
            "universe_id": ["C2"],
            "period_id": ["ROBUSTNESS_2022"],
            "pair": ["BTC-USDT"],
            "signal_time": ["2022-01-01T00:00:00Z"],
            "decision_time": ["2022-01-02T00:00:00Z"],
            "landmark_age_hours": [24],
            "data_quality_class": ["RECONSTRUCTED_VALID"],
            "high_water_gain_atr": [2.0],
            "pullback_from_high_water_atr": [1.0],
        }
    )
    target = pd.DataFrame(
        {
            "decision_id": ["B"],
            "control_position_id": ["P"],
            "universe_id": ["C2"],
            "period_id": ["ROBUSTNESS_2022"],
            "pair": ["BTC-USDT"],
            "decision_time": ["2022-01-02T00:00:00Z"],
            "landmark_age_hours": [24],
            "target_evaluable": [True],
            "rcv_return": [-0.1],
            "right_censored": [False],
        }
    )
    try:
        normalize_joined_ledger(state, target)
    except Exception as exc:
        assert "registry mismatch" in str(exc)
    else:
        raise AssertionError("decision registry mismatch should fail")


def _landmarks(
    forward: set[int],
    reverse: set[int],
) -> pd.DataFrame:
    rows = []
    for age in (24, 48, 72, 96, 120, 144):
        rows.append(
            {
                "landmark_age_hours": age,
                "forward_landmark_qualified": age in forward,
                "reverse_landmark_qualified": age in reverse,
            }
        )
    return pd.DataFrame(rows)


def test_persistence_unqualified_without_adjacent_forward_pair() -> None:
    result = temporal_persistence(_landmarks({24, 72}, {24, 72}))
    assert result["decision"] == DECISION_UNQUALIFIED


def test_persistence_regime_dependent_without_matching_reverse_pair() -> None:
    result = temporal_persistence(_landmarks({24, 48}, {72, 96}))
    assert result["decision"] == DECISION_REGIME_DEPENDENT


def test_persistence_bidirectional_when_matching_pair_exists() -> None:
    result = temporal_persistence(_landmarks({24, 48, 72}, {48, 72}))
    assert result["decision"] == DECISION_BIDIRECTIONAL
    assert result["matching_forward_reverse_persistent_pairs"] == [[48, 72]]


def test_landmark_qualification_needs_two_same_direction_universes() -> None:
    rows = []
    for direction in (
        "CALIBRATE_2022_EVALUATE_2023",
        "CALIBRATE_2023_EVALUATE_2022",
    ):
        for universe in ("C2", "D2", "E2"):
            for landmark in (24, 48, 72, 96, 120, 144):
                rows.append(
                    {
                        "transport_direction": direction,
                        "universe_id": universe,
                        "landmark_age_hours": landmark,
                        "joint_cell_qualified": bool(
                            landmark == 24
                            and universe in {"C2", "D2"}
                            and direction == "CALIBRATE_2022_EVALUATE_2023"
                        ),
                    }
                )
    result = landmark_qualification(pd.DataFrame(rows))
    row24 = result.loc[result["landmark_age_hours"] == 24].iloc[0]
    assert bool(row24["forward_landmark_qualified"]) is True
    assert int(row24["forward_qualified_universe_count"]) == 2
    assert bool(row24["reverse_landmark_qualified"]) is False
