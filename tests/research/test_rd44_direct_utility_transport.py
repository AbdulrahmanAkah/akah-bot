from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from spotbot.research.rd44_direct_utility_transport import (
    DECISION_BIDIRECTIONAL,
    DECISION_REGIME_DEPENDENT,
    DECISION_UNQUALIFIED,
    apply_empirical_cdf,
    auc_binary,
    decision_from_persistence,
    design_matrix,
    empirical_cdf_reference,
    evaluate_metrics,
    fit_model,
    landmark_qualification,
    normalize_joined_ledger,
    predict,
    spearman,
    validate_constants,
)


def _joined_train() -> pd.DataFrame:
    n = 40
    axis_1 = np.linspace(0.0, 39.0, n)
    axis_2 = ((np.arange(n) * 7) % n).astype(float) / float(n - 1)
    axis_3 = ((np.arange(n) * 13) % n).astype(float) / float(n - 1)
    target = -0.08 + 0.03 * (axis_1 / 39.0) + 0.05 * axis_2 + 0.02 * axis_3
    return pd.DataFrame(
        {
            "decision_id": [f"D{i:03d}" for i in range(n)],
            "control_position_id": [f"P{i:03d}" for i in range(n)],
            "pair": [f"PAIR{i % 6}" for i in range(n)],
            "signal_time": pd.date_range(
                "2022-01-01",
                periods=n,
                freq="D",
                tz="UTC",
            ),
            "time_since_completed_high_water_hours": axis_1,
            "recent_12h_high_water_increment_atr": axis_2,
            "recent_12h_pullback_change_atr": axis_3,
            "rcv_return": target,
        }
    )


def test_constants() -> None:
    validate_constants()


def test_empirical_cdf_right_ties() -> None:
    reference = empirical_cdf_reference(np.array([1.0, 2.0, 2.0, 4.0]))
    transformed = apply_empirical_cdf(
        reference,
        np.array([0.0, 2.0, 3.0, 4.0]),
    )
    assert np.allclose(
        transformed,
        [0.0, 0.75, 0.75, 1.0],
    )


def test_design_matrix_has_four_noninteraction_columns() -> None:
    x = design_matrix(
        np.array([0.1, 0.2]),
        np.array([0.3, 0.4]),
        np.array([0.5, 0.6]),
    )
    assert x.shape == (2, 4)
    assert np.allclose(x[:, 0], 1.0)
    assert np.allclose(x[:, 1], [0.1, 0.2])
    assert np.allclose(x[:, 2], [0.3, 0.4])
    assert np.allclose(x[:, 3], [0.5, 0.6])


def test_fit_and_predict_fixed_four_coefficient_model() -> None:
    train = _joined_train()
    model = fit_model(train)
    assert model.design_rank == 4
    assert len(model.coefficients) == 4
    pred = predict(model, train)
    assert len(pred) == len(train)
    assert np.isfinite(pred).all()


def test_spearman_and_auc_direction() -> None:
    actual = np.array([-3.0, -2.0, 1.0, 2.0])
    prediction = np.array([-2.0, -1.0, 1.0, 2.0])
    assert spearman(prediction, actual) > 0.9
    event = actual < 0.0
    assert auc_binary(event, -prediction) == 1.0


def test_evaluate_metrics_recognizes_good_predictions() -> None:
    n = 24
    actual = np.linspace(-0.12, 0.12, n)
    frame = pd.DataFrame(
        {
            "decision_id": [f"D{i}" for i in range(n)],
            "control_position_id": [f"P{i}" for i in range(n)],
            "pair": [f"PAIR{i % 6}" for i in range(n)],
            "signal_time": pd.date_range(
                "2023-01-01",
                periods=n,
                freq="D",
                tz="UTC",
            ),
            "rcv_return": actual,
        }
    )
    metrics = evaluate_metrics(frame, actual.copy())
    assert metrics["continuous_point_pass"] is True
    assert metrics["classification_point_pass"] is True
    assert metrics["negative_subset_point_pass"] is True


def test_decision_contracts() -> None:
    decision, _next, matching = decision_from_persistence(
        [],
        [],
    )
    assert decision == DECISION_UNQUALIFIED
    assert matching == []

    decision, _next, matching = decision_from_persistence(
        [[24, 48]],
        [],
    )
    assert decision == DECISION_REGIME_DEPENDENT
    assert matching == []

    decision, _next, matching = decision_from_persistence(
        [[24, 48], [48, 72]],
        [[48, 72]],
    )
    assert decision == DECISION_BIDIRECTIONAL
    assert matching == [[48, 72]]


def test_landmark_qualification_requires_two_universes_same_cell() -> None:
    rows = []
    for universe, passed in (
        ("C2", True),
        ("D2", True),
        ("E2", False),
    ):
        rows.append(
            {
                "transport_direction": ("CALIBRATE_2022_EVALUATE_2023"),
                "universe_id": universe,
                "landmark_age_hours": 24,
                "continuous_gate_pass": passed,
                "classification_gate_pass": passed,
                "negative_subset_gate_pass": passed,
            }
        )
    frame = pd.DataFrame(rows)
    continuous = frame[
        [
            "transport_direction",
            "universe_id",
            "landmark_age_hours",
            "continuous_gate_pass",
        ]
    ]
    classification = frame[
        [
            "transport_direction",
            "universe_id",
            "landmark_age_hours",
            "classification_gate_pass",
        ]
    ]
    subset = frame[
        [
            "transport_direction",
            "universe_id",
            "landmark_age_hours",
            "negative_subset_gate_pass",
        ]
    ]

    # Supply false rows for the other frozen cells.
    filler = []
    for direction in (
        "CALIBRATE_2022_EVALUATE_2023",
        "CALIBRATE_2023_EVALUATE_2022",
    ):
        for landmark in (24, 48, 72, 96, 120, 144):
            for universe in ("C2", "D2", "E2"):
                if direction == "CALIBRATE_2022_EVALUATE_2023" and landmark == 24:
                    continue
                filler.append(
                    {
                        "transport_direction": direction,
                        "universe_id": universe,
                        "landmark_age_hours": landmark,
                    }
                )
    filler_frame = pd.DataFrame(filler)
    continuous = pd.concat(
        [
            continuous,
            filler_frame.assign(continuous_gate_pass=False),
        ],
        ignore_index=True,
    )
    classification = pd.concat(
        [
            classification,
            filler_frame.assign(classification_gate_pass=False),
        ],
        ignore_index=True,
    )
    subset = pd.concat(
        [
            subset,
            filler_frame.assign(negative_subset_gate_pass=False),
        ],
        ignore_index=True,
    )

    qualification = landmark_qualification(
        continuous,
        classification,
        subset,
    )
    row = qualification.loc[
        (qualification["transport_direction"] == "CALIBRATE_2022_EVALUATE_2023")
        & (qualification["landmark_age_hours"] == 24)
    ].iloc[0]
    assert bool(row["landmark_qualified"]) is True
    assert int(row["joint_qualified_universe_count"]) == 2


def test_join_registry_mismatch_fails_closed() -> None:
    state = pd.DataFrame(
        {
            "decision_id": ["A"],
            "control_position_id": ["P"],
            "universe_id": ["C2"],
            "period_id": ["ROBUSTNESS_2022"],
            "pair": ["X"],
            "signal_time": ["2022-01-01T00:00:00Z"],
            "decision_time": ["2022-01-02T00:00:00Z"],
            "landmark_age_hours": [24],
            "data_quality_class": ["RECONSTRUCTED_VALID"],
            "time_since_completed_high_water_hours": [1.0],
            "recent_12h_high_water_increment_atr": [0.1],
            "recent_12h_pullback_change_atr": [0.2],
        }
    )
    target = pd.DataFrame(
        {
            "decision_id": ["B"],
            "control_position_id": ["P"],
            "universe_id": ["C2"],
            "period_id": ["ROBUSTNESS_2022"],
            "pair": ["X"],
            "decision_time": ["2022-01-02T00:00:00Z"],
            "landmark_age_hours": [24],
            "target_evaluable": [True],
            "rcv_return": [0.1],
            "right_censored": [False],
        }
    )
    with pytest.raises(
        Exception,
        match="decision registry mismatch",
    ):
        normalize_joined_ledger(state, target)
