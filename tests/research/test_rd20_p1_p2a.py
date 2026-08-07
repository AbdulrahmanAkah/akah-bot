from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from spotbot.research.rd20_p1_reconciliation import EXPECTED_MOVE_CONTRACT
from spotbot.research.rd20_p2_minimal_pullback import (
    BASE_ROUND_TRIP_COST,
    FROZEN_CONTRACT,
    SCORE_WEIGHTS,
    STRESS_2X_ROUND_TRIP_COST,
    MinimalPullbackError,
    evaluate_snapshot_hour,
    fast_lookup,
    fixed_risk_notional,
    load_membership,
    percentile,
    prepare_features,
    validate_frozen_contract,
)


def synthetic_bars() -> pd.DataFrame:
    times = pd.date_range("2020-01-01T00:00:00Z", periods=120, freq="h")
    base = np.linspace(100.0, 130.0, len(times))
    close = base.copy()
    high = close + 0.8
    low = close - 0.8

    # Create a prior pullback below the EMA and then a clean reclaim.
    close[100:104] -= np.array([2.0, 4.0, 6.0, 4.0])
    low[100:104] = close[100:104] - 2.0
    high[100:104] = close[100:104] + 0.5
    close[104] = base[104] + 1.5
    high[104] = close[104] + 0.5
    low[104] = close[104] - 0.5

    return pd.DataFrame(
        {
            "timestamp": times,
            "open": close - 0.2,
            "high": high,
            "low": low,
            "close": close,
        }
    )


def test_contract_is_minimal_and_cost_not_signal_hurdle() -> None:
    validate_frozen_contract()
    assert FROZEN_CONTRACT["binary_setup_gate_count"] == 3
    assert FROZEN_CONTRACT["score_component_count"] == 2
    assert sum(SCORE_WEIGHTS.values()) == pytest.approx(1.0)
    assert FROZEN_CONTRACT["costs"]["cost_hurdle_in_signal_generation"] is False
    assert pytest.approx(BASE_ROUND_TRIP_COST * 2.0) == STRESS_2X_ROUND_TRIP_COST


def test_expected_move_contract_does_not_reuse_prior_alpha() -> None:
    assert EXPECTED_MOVE_CONTRACT["confirmed_prior_expected_move_alpha"] is False
    assert EXPECTED_MOVE_CONTRACT["ex_ante_expected_move_hard_filter_authorized"] is False
    assert EXPECTED_MOVE_CONTRACT["future_labels_used_for_signal_generation"] is False
    assert EXPECTED_MOVE_CONTRACT["mandatory_evaluation_horizons_hours"] == [24, 72, 168]


def test_feature_builder_is_causal_to_decision_prefix() -> None:
    raw = synthetic_bars()
    full = prepare_features(raw)
    prefix = prepare_features(raw.iloc[:106].copy())
    columns = [
        "ema24",
        "atr24",
        "past_72h_return",
        "touch_prior_12h",
        "ema24_reclaim",
        "recovery_impulse_atr",
        "initial_stop_reference",
    ]
    for column in columns:
        left = full.loc[105, column]
        right = prefix.loc[105, column]
        if isinstance(left, (bool, np.bool_)):
            assert bool(left) == bool(right)
        else:
            assert float(left) == pytest.approx(float(right), nan_ok=True)


def test_current_bar_touch_is_not_counted_as_prior_touch() -> None:
    raw = synthetic_bars()

    # Find an early feature-ready bar and force only the current low to touch.
    index = 90
    raw2 = raw.copy()
    before = prepare_features(raw2)
    ema = float(before.loc[index, "ema24"])
    raw2.loc[: index - 1, "low"] = raw2.loc[: index - 1, "close"] + 10.0
    raw2.loc[index, "low"] = ema - 1.0
    result = prepare_features(raw2)
    assert bool(result.loc[index, "touch_prior_12h"]) is False


def test_percentile_uses_midrank_for_ties() -> None:
    assert percentile([1.0, 2.0, 2.0, 4.0], 2.0) == pytest.approx(0.5)


def test_fixed_risk_sizing_respects_single_asset_cap() -> None:
    notional = fixed_risk_notional(equity=100_000.0, entry_price=100.0, stop_price=99.0)
    assert notional == pytest.approx(40_000.0)


def test_fixed_risk_sizing_rejects_invalid_stop() -> None:
    with pytest.raises(MinimalPullbackError):
        fixed_risk_notional(equity=100_000.0, entry_price=100.0, stop_price=101.0)


def test_snapshot_evaluation_emits_only_after_reclaim_and_touch() -> None:
    raw = synthetic_bars()
    feature_a = prepare_features(raw)
    feature_b = prepare_features(
        raw.assign(
            open=raw["open"] * 0.9,
            high=raw["high"] * 0.9,
            low=raw["low"] * 0.9,
            close=raw["close"] * 0.9,
        )
    )

    # Locate a bar satisfying all three gates for A.
    candidate_indices = feature_a.index[
        feature_a["feature_ready"]
        & (feature_a["past_72h_return"] > 0)
        & feature_a["touch_prior_12h"]
        & feature_a["ema24_reclaim"]
    ].tolist()
    assert candidate_indices
    index = candidate_indices[0]
    timestamp = pd.Timestamp(feature_a.loc[index, "timestamp"])

    features = {"AAA-USDT": feature_a, "BBB-USDT": feature_b}
    lookups = {
        pair: {int(ts.value): int(i) for i, ts in enumerate(frame["timestamp"])}
        for pair, frame in features.items()
    }
    events, counters = evaluate_snapshot_hour(
        timestamp=timestamp,
        members=(("AAA-USDT", 1), ("BBB-USDT", 2)),
        features=features,
        lookups=lookups,
    )
    assert counters["asset_checks"] == 2
    assert counters["candidate_events"] >= 1
    assert all(0.0 <= float(row["score"]) <= 1.0 for row in events)


def test_effective_membership_loader_uses_replacement_pair(tmp_path) -> None:
    rows = []
    decision = "2020-01-06T00:00:00Z"
    end = "2020-01-13T00:00:00Z"
    for rank in range(1, 7):
        original = f"ORIGINAL{rank}-USDT"
        effective = "REPLACEMENT-USDT" if rank == 2 else original
        effective_rank = 8 if rank == 2 else rank
        rows.append(
            {
                "universe_id": "C2",
                "decision_time": decision,
                "effective_end": end,
                "original_pair": original,
                "original_canonical_asset_id": f"asset-{rank}",
                "original_rank": rank,
                "top6": True,
                "effective_pair": effective,
                "effective_canonical_asset_id": (
                    "replacement-asset" if rank == 2 else f"asset-{rank}"
                ),
                "effective_rank": effective_rank,
                "replacement_applied": rank == 2,
                "replacement_reason": "TEST" if rank == 2 else "",
                "completed_bar_count": 24,
            }
        )
    path = tmp_path / "effective-operational-membership.csv"
    pd.DataFrame.from_records(rows).to_csv(path, index=False)

    snapshots = load_membership(path)

    assert len(snapshots) == 1
    members = dict(snapshots[0].members)
    assert "ORIGINAL2-USDT" not in members
    assert members["REPLACEMENT-USDT"] == 8
    assert len(members) == 6


def test_effective_membership_accepts_top6_false_and_zero_completed_domain(
    tmp_path,
) -> None:
    rows = []
    decision = "2020-02-03T00:00:00Z"
    end = "2020-02-10T00:00:00Z"
    for rank in range(1, 7):
        rows.append(
            {
                "universe_id": "D2",
                "decision_time": decision,
                "effective_end": end,
                "original_pair": f"PAIR{rank}-USDT",
                "original_canonical_asset_id": f"asset-{rank}",
                "original_rank": rank,
                "top6": rank != 6,
                "effective_pair": f"PAIR{rank}-USDT",
                "effective_canonical_asset_id": f"asset-{rank}",
                "effective_rank": rank,
                "replacement_applied": False,
                "replacement_reason": (
                    "ORIGINAL_GENERATED_EMPTY_COMPLETED_BAR_DOMAIN"
                    if rank == 6
                    else "ORIGINAL_INTERVAL_READY"
                ),
                "completed_bar_count": 0 if rank == 6 else 24,
            }
        )

    path = tmp_path / "effective-operational-membership.csv"
    pd.DataFrame.from_records(rows).to_csv(path, index=False)

    snapshots = load_membership(path)

    assert len(snapshots) == 1
    assert len(snapshots[0].members) == 6
    assert ("PAIR6-USDT", 6) in snapshots[0].members


def test_fast_lookup_normalizes_microsecond_timestamps_to_ns_keys() -> None:
    raw = synthetic_bars()
    raw["timestamp"] = raw["timestamp"].dt.as_unit("us")
    featured = prepare_features(raw)

    lookup = fast_lookup(featured)
    target_index = 100
    target = pd.Timestamp(featured.loc[target_index, "timestamp"])

    assert target.value in lookup
    assert lookup[target.value] == target_index


def test_fast_lookup_keys_match_for_ns_and_us_sources() -> None:
    raw_ns = synthetic_bars()
    raw_us = raw_ns.copy()
    raw_us["timestamp"] = raw_us["timestamp"].dt.as_unit("us")

    keys_ns = set(fast_lookup(prepare_features(raw_ns)))
    keys_us = set(fast_lookup(prepare_features(raw_us)))

    assert keys_ns == keys_us
