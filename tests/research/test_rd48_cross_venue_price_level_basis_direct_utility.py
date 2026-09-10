from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd48_cross_venue_price_level_basis_direct_utility import (
    FEATURES,
    auc_binary,
    decision_from_persistence,
    ecdf_transform,
    persistent_pairs,
    stable_prediction_halves,
    strict_join,
    subset_metrics,
)


def test_feature_registry_is_exact_rd48_axes():
    assert FEATURES == [
        "BTC_ETH_MEAN_SIGNED_CROSS_VENUE_LOG_CLOSE_PRICE_BASIS",
        "BTC_ETH_CROSS_VENUE_LOG_CLOSE_PRICE_BASIS_DISPERSION",
    ]


def test_ecdf_right_count_less_equal_ties():
    train = np.array([1.0, 1.0, 3.0, 5.0])
    got = ecdf_transform(
        train,
        np.array([1.0, 2.0, 5.0]),
    )
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
    for hour in [24, 48, 72, 96, 120, 144]:
        rows.append(
            {
                "direction": "FORWARD",
                "landmark_age_hours": hour,
                "landmark_qualified": hour in {24, 48, 96},
            }
        )
    df = pd.DataFrame(rows)
    assert persistent_pairs(df, "FORWARD") == [[24, 48]]


def test_decision_bidirectional_matching_pair():
    decision, nxt, matching = decision_from_persistence(
        [[24, 48]],
        [[24, 48]],
    )
    assert decision == (
        "RD48_CROSS_VENUE_PRICE_LEVEL_BASIS_DIRECT_UTILITY_BIDIRECTIONALLY_PERSISTENT"
    )
    assert matching == [[24, 48]]
    assert nxt == (
        "RD48_P5_PREREGISTER_ISOLATED_ACTION_MAPPING_WITH_SLOT_ESCROW_AND_NO_EARLY_CAPITAL_REUSE"
    )


def test_decision_forward_only_no_context_rescue():
    decision, nxt, matching = decision_from_persistence(
        [[48, 72]],
        [],
    )
    assert decision == (
        "RD48_CROSS_VENUE_PRICE_LEVEL_BASIS_DIRECT_UTILITY_"
        "FORWARD_ONLY_REGIME_DEPENDENT_NO_CONTEXT_RESCUE"
    )
    assert matching == []
    assert nxt == (
        "RD48_CLOSE_DIRECT_ACTION_MAPPING_FOR_THIS_SOURCE_AND_"
        "RETAIN_FORWARD_ONLY_EVIDENCE_AS_DIAGNOSTIC"
    )


def test_decision_no_forward_is_unqualified():
    decision, nxt, matching = decision_from_persistence(
        [],
        [[24, 48]],
    )
    assert decision == ("RD48_CROSS_VENUE_PRICE_LEVEL_BASIS_DIRECT_UTILITY_UNQUALIFIED_NO_RESCUE")
    assert matching == []
    assert nxt == (
        "RD48_CLOSE_OR_PREREGISTER_DISTINCT_DIRECT_UTILITY_INFORMATION_SOURCE_PRE_TARGET_EXPOSURE"
    )


def test_strict_join_full_registry_parity_synthetic():
    n = 1996
    decision_ids = [f"D{i:04d}" for i in range(n)]
    positions = [f"P{i:04d}" for i in range(n)]
    universes = ["C2"] * n
    periods = ["ROBUSTNESS_2022"] * n
    pairs = ["BTC-USDT"] * n
    decision_times = ["2022-01-02 00:00:00+00:00"] * n
    landmarks = [24] * n

    state = pd.DataFrame(
        {
            "decision_id": decision_ids,
            "control_position_id": positions,
            "universe_id": universes,
            "period_id": periods,
            "pair": pairs,
            "signal_time": ["2022-01-01 00:00:00+00:00"] * n,
            "decision_time": decision_times,
            "landmark_age_hours": landmarks,
            "feature_valid": [True] * n,
            FEATURES[0]: np.linspace(-1.0, 1.0, n),
            FEATURES[1]: np.linspace(0.0, 2.0, n),
        }
    )
    target = pd.DataFrame(
        {
            "decision_id": decision_ids,
            "control_position_id": positions,
            "universe_id": universes,
            "period_id": periods,
            "pair": pairs,
            "decision_time": decision_times,
            "landmark_age_hours": landmarks,
            "target_evaluable": [True] * n,
            "rcv_return": np.linspace(-0.1, 0.1, n),
            "right_censored": [False] * n,
        }
    )

    joined = strict_join(state, target)
    assert len(joined) == 1996
    assert joined["target_evaluable"].all()
    assert not joined["right_censored"].any()
