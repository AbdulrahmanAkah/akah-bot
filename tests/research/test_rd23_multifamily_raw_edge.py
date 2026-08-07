from __future__ import annotations

import pandas as pd

from spotbot.research.rd23_multifamily_raw_edge import (
    DATA_CUTOFF,
    FAMILIES,
    FAMILY_BASE_RANGE_BREAKOUT,
    FAMILY_MOMENTUM_ACCELERATION,
    FAMILY_MOMENTUM_BREAKOUT,
    FAMILY_RELATIVE_STRENGTH_ROTATION,
    FAMILY_STRUCTURAL_REVERSAL,
    FAMILY_VOLATILITY_EXPANSION,
    aggregate_raw_edge,
    evaluate_family_horizons,
    evaluate_hour,
    family_overlap,
    fast_lookup,
    forward_event_rows,
    prepare_features,
    validate_constants,
)


def synthetic_bars(rows: int = 320) -> pd.DataFrame:
    timestamp = pd.date_range("2020-01-01T00:00:00Z", periods=rows, freq="h")
    close = pd.Series([100.0 + index * 0.05 for index in range(rows)], dtype=float)
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": close - 0.05,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": 1000.0,
        }
    )


def test_family_registry_is_exact() -> None:
    validate_constants()
    assert FAMILIES == (
        FAMILY_MOMENTUM_BREAKOUT,
        FAMILY_VOLATILITY_EXPANSION,
        FAMILY_STRUCTURAL_REVERSAL,
        FAMILY_RELATIVE_STRENGTH_ROTATION,
        FAMILY_MOMENTUM_ACCELERATION,
        FAMILY_BASE_RANGE_BREAKOUT,
    )


def test_momentum_breakout_excludes_current_high_from_threshold() -> None:
    raw = synthetic_bars()
    index = 150
    raw.loc[index, "open"] = 104.0
    raw.loc[index, "high"] = 120.0
    raw.loc[index, "low"] = 103.5
    raw.loc[index, "close"] = 119.0
    featured = prepare_features(raw)
    assert bool(featured.loc[index, "momentum_breakout"])
    assert float(featured.loc[index, "prior_72h_high"]) < 119.0


def test_volatility_expansion_is_fresh_and_bullish() -> None:
    raw = synthetic_bars()
    index = 160
    raw.loc[index, ["open", "high", "low", "close"]] = [106.0, 110.0, 105.0, 109.5]
    featured = prepare_features(raw)
    assert bool(featured.loc[index, "volatility_expansion"])
    assert float(featured.loc[index, "close_location"]) >= 0.75


def test_structural_reversal_requires_sweep_and_reclaim_after_weakness() -> None:
    raw = synthetic_bars()
    raw.loc[80:170, "close"] = [120.0 - (index - 80) * 0.2 for index in range(80, 171)]
    raw.loc[80:170, "open"] = raw.loc[80:170, "close"] + 0.05
    raw.loc[80:170, "high"] = raw.loc[80:170, "close"] + 0.4
    raw.loc[80:170, "low"] = raw.loc[80:170, "close"] - 0.4
    index = 171
    prior_low = float(raw.loc[index - 24 : index - 1, "low"].min())
    raw.loc[index, ["open", "high", "low", "close"]] = [
        101.0,
        103.0,
        prior_low - 1.0,
        prior_low + 0.5,
    ]
    featured = prepare_features(raw)
    assert bool(featured.loc[index, "structural_reversal"])


def test_forward_rows_use_next_bar_open_and_fixed_horizons() -> None:
    raw = synthetic_bars()
    features = {"PAIR-USDT": prepare_features(raw)}
    signal_time = pd.Timestamp(raw.loc[100, "timestamp"])
    events = pd.DataFrame(
        [
            {
                "family_id": FAMILY_MOMENTUM_BREAKOUT,
                "universe_id": "C2",
                "period_id": "DISCOVERY_2019_2020",
                "pair": "PAIR-USDT",
                "timestamp": signal_time,
            }
        ]
    )
    rows = forward_event_rows(events=events, features=features)
    assert set(rows["horizon_hours"]) == {24, 72, 168}
    assert set(rows["cost_multiplier"]) == {1.0, 2.0}
    expected_entry = float(raw.loc[101, "open"])
    expected_exit = float(raw.loc[124, "close"])
    gross = expected_exit / expected_entry - 1.0
    observed = rows.loc[
        (rows["horizon_hours"] == 24) & (rows["cost_multiplier"] == 1.0),
        "gross_forward_return",
    ].iloc[0]
    assert abs(float(observed) - gross) < 1e-12


def test_hard_gate_can_select_one_family_horizon() -> None:
    rows = []
    for family in FAMILIES:
        for universe in ("C2", "D2", "E2"):
            for period in ("DISCOVERY_2019_2020", "TEMPORAL_REPLICATION_2021"):
                for horizon in (24, 72, 168):
                    passed = family == FAMILY_MOMENTUM_BREAKOUT and horizon == 72
                    rows.append(
                        {
                            "family_id": family,
                            "universe_id": universe,
                            "period_id": period,
                            "horizon_hours": horizon,
                            "cost_multiplier": 2.0,
                            "event_count": 100,
                            "pair_count": 5,
                            "signal_day_count": 50,
                            "mean_net_forward_return": 0.01 if passed else -0.01,
                            "median_net_forward_return": 0.0,
                            "trimmed_1pct_mean_net_forward_return": 0.009 if passed else -0.01,
                            "positive_net_forward_share": 0.5,
                            "leave_one_pair_out_min_mean_net_return": 0.008 if passed else -0.01,
                            "largest_pair_event_share": 0.3,
                            "pf1_break_even_cost_multiplier_raw_mean": 3.0 if passed else 1.0,
                        }
                    )
    metrics = pd.DataFrame(rows)
    _gates, selection = evaluate_family_horizons(metrics)
    breakout = selection.loc[selection["family_id"] == FAMILY_MOMENTUM_BREAKOUT].iloc[0]
    assert bool(breakout["raw_edge_confirmed"])
    assert int(breakout["selected_horizon_hours"]) == 72
    others = selection.loc[selection["family_id"] != FAMILY_MOMENTUM_BREAKOUT]
    assert not bool(others["raw_edge_confirmed"].any())


def test_relative_strength_suppressed_on_snapshot_first_hour() -> None:
    previous = pd.Timestamp("2020-06-01T00:00:00Z")
    current = previous + pd.Timedelta(hours=1)

    def frame(previous_return: float, current_return: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "timestamp": [previous, current],
                "feature_ready": [True, True],
                "return_72h": [previous_return, current_return],
                "close": [100.0, 101.0],
                "momentum_breakout": [False, False],
                "volatility_expansion": [False, False],
                "structural_reversal": [False, False],
                "momentum_acceleration": [False, False],
                "base_range_breakout": [False, False],
                "prior_72h_high": [99.0, 99.0],
                "atr24_prior": [1.0, 1.0],
                "volatility_expansion_ratio": [1.0, 1.0],
                "close_location": [0.5, 0.5],
                "prior_24h_low": [95.0, 95.0],
                "return_6h": [0.01, 0.01],
                "previous_6h_return": [0.01, 0.01],
                "prior_48h_high": [99.0, 99.0],
                "base_width_atr": [6.0, 6.0],
            }
        )

    features = {
        "A-USDT": frame(0.05, 0.20),
        "B-USDT": frame(0.10, 0.10),
    }
    lookups = {pair: fast_lookup(value) for pair, value in features.items()}
    members = (("A-USDT", 1), ("B-USDT", 2))

    suppressed, _ = evaluate_hour(
        timestamp=current,
        members=members,
        features=features,
        lookups=lookups,
        allow_relative_strength=False,
    )
    allowed, _ = evaluate_hour(
        timestamp=current,
        members=members,
        features=features,
        lookups=lookups,
        allow_relative_strength=True,
    )
    assert not any(row["family_id"] == FAMILY_RELATIVE_STRENGTH_ROTATION for row in suppressed)
    assert any(row["family_id"] == FAMILY_RELATIVE_STRENGTH_ROTATION for row in allowed)


def test_overlap_reports_shared_event_keys() -> None:
    timestamp = pd.Timestamp("2020-06-01T00:00:00Z")
    events = pd.DataFrame(
        [
            {
                "family_id": FAMILY_MOMENTUM_BREAKOUT,
                "universe_id": "C2",
                "timestamp": timestamp,
                "pair": "A-USDT",
            },
            {
                "family_id": FAMILY_VOLATILITY_EXPANSION,
                "universe_id": "C2",
                "timestamp": timestamp,
                "pair": "A-USDT",
            },
        ]
    )
    matrix, summary = family_overlap(events)
    assert summary["multi_family_event_keys"] == 1
    row = matrix.loc[
        (matrix["family_a"] == FAMILY_MOMENTUM_BREAKOUT)
        & (matrix["family_b"] == FAMILY_VOLATILITY_EXPANSION)
    ].iloc[0]
    assert int(row["intersection"]) == 1


def test_no_2022_or_later_bars_allowed() -> None:
    raw = synthetic_bars()
    raw.loc[len(raw)] = {
        "timestamp": DATA_CUTOFF,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 1000.0,
    }
    try:
        prepare_features(raw)
    except Exception as exc:
        assert "2022" in str(exc)
    else:
        raise AssertionError("2022 bar should be rejected")


def test_aggregate_raw_edge_computes_lopo() -> None:
    rows = []
    for pair, value in (("A-USDT", 0.02), ("B-USDT", 0.01), ("C-USDT", 0.015)):
        for index in range(40):
            rows.append(
                {
                    "family_id": FAMILY_MOMENTUM_BREAKOUT,
                    "universe_id": "C2",
                    "period_id": "DISCOVERY_2019_2020",
                    "horizon_hours": 72,
                    "cost_multiplier": 2.0,
                    "pair": pair,
                    "signal_time": pd.Timestamp("2020-01-01T00:00:00Z") + pd.Timedelta(hours=index),
                    "gross_forward_return": value + 0.005,
                    "net_forward_return": value,
                    "base_cost_weight": 0.0025,
                }
            )
    metrics = aggregate_raw_edge(pd.DataFrame(rows))
    assert len(metrics) == 1
    assert float(metrics.iloc[0]["leave_one_pair_out_min_mean_net_return"]) > 0.0
