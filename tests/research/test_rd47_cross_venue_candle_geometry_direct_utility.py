from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd47_cross_venue_candle_geometry_direct_utility import (
    FEATURES,
    auc_binary,
    decision_from_persistence,
    ecdf_transform,
    persistent_pairs,
    stable_prediction_halves,
    subset_metrics,
)


def test_feature_registry_is_exact_rd47_axes():
    assert FEATURES == [
        "BTC_ETH_MEAN_SIGNED_CROSS_VENUE_CLOSE_LOCATION_GAP",
        "BTC_ETH_MEAN_ABSOLUTE_CROSS_VENUE_LOG_RANGE_GAP",
    ]


def test_ecdf_right_count_less_equal_ties():
    train = np.array([1.0, 1.0, 3.0, 5.0])
    got = ecdf_transform(train, np.array([1.0, 2.0, 5.0]))
    assert np.allclose(got, [0.5, 0.5, 1.0])


def test_auc_adverse_orientation():
    labels = np.array([True, True, False, False])
    scores = np.array([4.0, 3.0, 2.0, 1.0])
    assert auc_binary(labels, scores) == 1.0


def test_stable_halves_tie_break_by_decision_id():
    df = pd.DataFrame(
        {
            "decision_id": ["b", "a", "d", "c"],
            "rcv_return": [0, 0, 0, 0],
        }
    )
    bottom, top = stable_prediction_halves(df, np.zeros(4))
    assert list(bottom["decision_id"]) == ["a", "b"]
    assert list(top["decision_id"]) == ["c", "d"]


def test_negative_subset_threshold_is_strictly_below_zero():
    df = pd.DataFrame(
        {
            "decision_id": [str(i) for i in range(10)],
            "pair": [f"P{i}" for i in range(10)],
            "signal_time": pd.date_range(
                "2022-01-01",
                periods=10,
                freq="D",
                tz="UTC",
            ),
            "rcv_return": [-1.0] * 10,
        }
    )
    pred = np.array([-0.1] * 9 + [0.0])
    metrics = subset_metrics(df, pred)
    assert metrics["subset_row_count"] == 9


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
    decision, nxt, matching = decision_from_persistence([[24, 48]], [[24, 48]])
    assert decision == (
        "RD47_CROSS_VENUE_CANDLE_GEOMETRY_DIRECT_UTILITY_BIDIRECTIONALLY_PERSISTENT"
    )
    assert matching == [[24, 48]]
    assert nxt == (
        "RD47_P5_PREREGISTER_ISOLATED_ACTION_MAPPING_WITH_SLOT_ESCROW_AND_NO_EARLY_CAPITAL_REUSE"
    )


def test_decision_forward_only_no_context_rescue():
    decision, nxt, matching = decision_from_persistence([[48, 72]], [])
    assert decision == (
        "RD47_CROSS_VENUE_CANDLE_GEOMETRY_DIRECT_UTILITY_"
        "FORWARD_ONLY_REGIME_DEPENDENT_NO_CONTEXT_RESCUE"
    )
    assert matching == []
    assert nxt == (
        "RD47_CLOSE_DIRECT_ACTION_MAPPING_FOR_THIS_SOURCE_AND_"
        "RETAIN_FORWARD_ONLY_EVIDENCE_AS_DIAGNOSTIC"
    )


def test_decision_no_forward_is_unqualified():
    decision, nxt, matching = decision_from_persistence([], [[24, 48]])
    assert decision == ("RD47_CROSS_VENUE_CANDLE_GEOMETRY_DIRECT_UTILITY_UNQUALIFIED_NO_RESCUE")
    assert matching == []
    assert nxt == (
        "RD47_CLOSE_OR_PREREGISTER_DISTINCT_DIRECT_UTILITY_INFORMATION_SOURCE_PRE_TARGET_EXPOSURE"
    )
