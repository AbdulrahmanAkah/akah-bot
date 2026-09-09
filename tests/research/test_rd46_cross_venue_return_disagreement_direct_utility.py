from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd46_cross_venue_return_disagreement_direct_utility import (
    auc_binary,
    decision_from_persistence,
    ecdf_transform,
    persistent_pairs,
    stable_prediction_halves,
    subset_metrics,
)


def test_ecdf_right_count_less_equal_ties():
    train = np.array([1.0, 1.0, 3.0, 5.0])
    got = ecdf_transform(train, np.array([1.0, 2.0, 5.0]))
    assert np.allclose(got, [0.5, 0.5, 1.0])


def test_auc_adverse_orientation():
    labels = np.array([True, True, False, False])
    scores = np.array([4.0, 3.0, 2.0, 1.0])
    assert auc_binary(labels, scores) == 1.0


def test_stable_halves_tie_break_by_decision_id():
    df = pd.DataFrame({"decision_id": ["b", "a", "d", "c"], "rcv_return": [0, 0, 0, 0]})
    bottom, top = stable_prediction_halves(df, np.zeros(4))
    assert list(bottom["decision_id"]) == ["a", "b"]
    assert list(top["decision_id"]) == ["c", "d"]


def test_negative_subset_threshold_is_strictly_below_zero():
    df = pd.DataFrame(
        {
            "decision_id": [str(i) for i in range(10)],
            "pair": [f"P{i}" for i in range(10)],
            "signal_time": pd.date_range("2022-01-01", periods=10, freq="D", tz="UTC"),
            "rcv_return": [-1.0] * 10,
        }
    )
    pred = np.array([-0.1] * 9 + [0.0])
    m = subset_metrics(df, pred)
    assert m["subset_row_count"] == 9


def test_persistence_requires_adjacent_landmarks():
    rows = []
    for h in [24, 48, 72, 96, 120, 144]:
        rows.append(
            {
                "direction": "FORWARD",
                "landmark_age_hours": h,
                "landmark_qualified": h in {24, 48, 96},
            }
        )
    df = pd.DataFrame(rows)
    assert persistent_pairs(df, "FORWARD") == [[24, 48]]


def test_decision_bidirectional_matching_pair():
    d, nxt, matching = decision_from_persistence([[24, 48]], [[24, 48]])
    assert "BIDIRECTIONALLY_PERSISTENT" in d
    assert matching == [[24, 48]]
    assert "P5_PREREGISTER_ISOLATED_ACTION_MAPPING" in nxt


def test_decision_forward_only_no_context_rescue():
    d, nxt, matching = decision_from_persistence([[48, 72]], [])
    assert "FORWARD_ONLY_REGIME_DEPENDENT_NO_CONTEXT_RESCUE" in d
    assert matching == []
    assert "CLOSE_DIRECT_ACTION_MAPPING" in nxt


def test_decision_no_forward_is_unqualified():
    d, nxt, matching = decision_from_persistence([], [[24, 48]])
    assert d == "RD46_CROSS_VENUE_RETURN_DISAGREEMENT_DIRECT_UTILITY_UNQUALIFIED_NO_RESCUE"
    assert matching == []
    assert "DISTINCT_DIRECT_UTILITY_INFORMATION_SOURCE" in nxt
