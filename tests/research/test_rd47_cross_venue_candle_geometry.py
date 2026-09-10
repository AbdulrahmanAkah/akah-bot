from __future__ import annotations

import math

import numpy as np
import pandas as pd

from spotbot.research.rd47_cross_venue_candle_geometry import (
    AXIS_CLOSE_LOCATION,
    AXIS_LOG_RANGE,
    LANDMARKS,
    PERIODS,
    UNIVERSES,
    aggregate_binance_hours,
    candle_geometry,
    compute_axes,
    qualify_transport_support,
)


def test_required_transport_qualifier_is_importable():
    assert callable(qualify_transport_support)


def test_candle_geometry_zero_range_fails_closed():
    assert candle_geometry((100.0, 100.0, 100.0)) is None


def test_candle_geometry_normal_case():
    clv, lr = candle_geometry((120.0, 80.0, 110.0))
    assert math.isclose(clv, 0.75)
    assert math.isclose(lr, math.log(1.5))


def test_compute_axes_exact_preregistered_formulas():
    h = pd.Timestamp("2022-01-02T03:00:00Z")
    key = int(h.value)
    kucoin = {
        "BTC-USDT": {key: (110.0, 90.0, 100.0)},
        "ETH-USDT": {key: (220.0, 180.0, 210.0)},
    }
    binance = {
        "BTCUSDT": {key: (120.0, 80.0, 110.0)},
        "ETHUSDT": {key: (230.0, 170.0, 200.0)},
    }
    got = compute_axes(h, kucoin, binance)
    assert got["feature_valid"] is True
    btc_cg = 0.75 - 0.5
    eth_cg = ((200 - 170) / (230 - 170)) - ((210 - 180) / (220 - 180))
    btc_rg = math.log(120 / 80) - math.log(110 / 90)
    eth_rg = math.log(230 / 170) - math.log(220 / 180)
    assert math.isclose(got[AXIS_CLOSE_LOCATION], 0.5 * (btc_cg + eth_cg))
    assert math.isclose(got[AXIS_LOG_RANGE], 0.5 * (abs(btc_rg) + abs(eth_rg)))


def test_missing_component_fails_closed():
    h = pd.Timestamp("2022-01-02T03:00:00Z")
    key = int(h.value)
    kucoin = {"BTC-USDT": {key: (110.0, 90.0, 100.0)}, "ETH-USDT": {}}
    binance = {"BTCUSDT": {key: (120.0, 80.0, 110.0)}, "ETHUSDT": {key: (230.0, 170.0, 200.0)}}
    got = compute_axes(h, kucoin, binance)
    assert got["feature_valid"] is False
    assert got["feature_status"] == "MISSING_SOURCE_HOUR_ETH"


def test_binance_hour_aggregation_uses_max_high_min_low_last_close():
    h = pd.Timestamp("2022-02-01T05:00:00Z")
    times = pd.date_range(h, periods=60, freq="min", tz="UTC")
    raw = pd.DataFrame(
        {
            "open_time": times.as_unit("ms").view("int64").astype(np.int64),
            "high": np.linspace(101.0, 160.0, 60),
            "low": np.linspace(99.0, 40.0, 60),
            "close": np.linspace(100.0, 120.0, 60),
        }
    )
    lookup, stats = aggregate_binance_hours(raw)
    assert stats["valid_hours"] == 1
    high, low, close = lookup[int(h.value)]
    assert math.isclose(high, 160.0)
    assert math.isclose(low, 40.0)
    assert math.isclose(close, 120.0)


def test_binance_incomplete_grid_fails_hour_closed():
    h = pd.Timestamp("2022-02-01T05:00:00Z")
    times = pd.date_range(h, periods=59, freq="min", tz="UTC")
    raw = pd.DataFrame(
        {
            "open_time": times.as_unit("ms").view("int64").astype(np.int64),
            "high": [110.0] * 59,
            "low": [90.0] * 59,
            "close": [100.0] * 59,
        }
    )
    lookup, stats = aggregate_binance_hours(raw)
    assert lookup == {}
    assert stats["invalid_grid_hours"] == 1


def test_transport_support_requires_two_of_three_in_both_years():
    rows = []
    for period in PERIODS:
        for universe in UNIVERSES:
            for age in LANDMARKS:
                passed = age == 24 and universe in {"C2", "D2"}
                if period == "ROBUSTNESS_2023" and universe == "D2":
                    passed = False
                rows.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": age,
                        "support_pass": passed,
                    }
                )
    result = qualify_transport_support(pd.DataFrame(rows))
    assert 24 not in result["qualified_landmarks_hours"]
    assert result["qualified_landmark_count"] == 0
