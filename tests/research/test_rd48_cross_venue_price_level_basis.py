from __future__ import annotations

import math

import numpy as np
import pandas as pd

from spotbot.research.rd48_cross_venue_price_level_basis import (
    AXIS_BASIS_DISPERSION,
    AXIS_MEAN_BASIS,
    LANDMARKS,
    PERIODS,
    UNIVERSES,
    aggregate_binance_hours,
    compute_axes,
    kucoin_hour_lookup,
    price_basis,
    qualify_transport_support,
    timestamp_key,
)


def test_required_transport_qualifier_is_importable():
    assert callable(qualify_transport_support)


def test_timestamp_key_is_resolution_stable():
    stamp_us = pd.Timestamp("2023-04-01T00:00:00Z").as_unit("us")
    stamp_ms = stamp_us.as_unit("ms")
    assert timestamp_key(stamp_us) == timestamp_key(stamp_ms)


def test_price_basis_exact_formula_and_sign():
    got = price_basis(101.0, 100.0)
    assert got is not None
    assert math.isclose(got, math.log(101.0 / 100.0))
    assert got > 0.0


def test_price_basis_nonpositive_fails_closed():
    assert price_basis(0.0, 100.0) is None
    assert price_basis(100.0, 0.0) is None


def test_compute_axes_exact_preregistered_formulas():
    hour = pd.Timestamp("2022-01-02T03:00:00Z")
    key = timestamp_key(hour)

    kucoin = {
        "BTC-USDT": {key: 100.0},
        "ETH-USDT": {key: 200.0},
    }
    binance = {
        "BTCUSDT": {key: 101.0},
        "ETHUSDT": {key: 198.0},
    }

    got = compute_axes(hour, kucoin, binance)
    assert got["feature_valid"] is True

    btc = math.log(101.0 / 100.0)
    eth = math.log(198.0 / 200.0)

    assert math.isclose(
        got[AXIS_MEAN_BASIS],
        0.5 * (btc + eth),
    )
    assert math.isclose(
        got[AXIS_BASIS_DISPERSION],
        abs(btc - eth),
    )


def test_missing_component_fails_closed():
    hour = pd.Timestamp("2022-01-02T03:00:00Z")
    key = timestamp_key(hour)

    kucoin = {
        "BTC-USDT": {key: 100.0},
        "ETH-USDT": {},
    }
    binance = {
        "BTCUSDT": {key: 101.0},
        "ETHUSDT": {key: 198.0},
    }

    got = compute_axes(hour, kucoin, binance)
    assert got["feature_valid"] is False
    assert got["feature_status"] == "MISSING_SOURCE_HOUR_ETH"


def test_kucoin_lookup_requires_only_timestamp_and_close_and_keep_last():
    stamp = pd.Timestamp("2022-02-01T05:00:00Z")
    raw = pd.DataFrame(
        {
            "timestamp": [stamp, stamp],
            "close": [100.0, 101.0],
        }
    )
    lookup = kucoin_hour_lookup(raw)
    assert lookup == {timestamp_key(stamp): 101.0}


def test_binance_hour_aggregation_requires_only_open_time_and_close():
    hour = pd.Timestamp("2022-02-01T05:00:00Z")
    times = pd.date_range(hour, periods=60, freq="min")
    raw = pd.DataFrame(
        {
            "open_time": times.as_unit("ms").view("int64"),
            "close": np.linspace(100.0, 120.0, 60),
        }
    )

    lookup, stats = aggregate_binance_hours(raw)
    assert stats["valid_hours"] == 1
    assert math.isclose(
        lookup[timestamp_key(hour)],
        120.0,
    )


def test_binance_incomplete_grid_fails_hour_closed():
    hour = pd.Timestamp("2022-02-01T05:00:00Z")
    times = pd.date_range(hour, periods=59, freq="min")
    raw = pd.DataFrame(
        {
            "open_time": times.as_unit("ms").view("int64"),
            "close": [100.0] * 59,
        }
    )

    lookup, stats = aggregate_binance_hours(raw)
    assert lookup == {}
    assert stats["invalid_grid_hours"] == 1


def test_binance_maintenance_overlap_invalidates_whole_hour():
    hour = pd.Timestamp("2023-03-24T11:00:00Z")
    times = pd.date_range(hour, periods=60, freq="min")
    raw = pd.DataFrame(
        {
            "open_time": times.as_unit("ms").view("int64"),
            "close": [100.0] * 60,
        }
    )

    lookup, stats = aggregate_binance_hours(raw)
    assert lookup == {}
    assert stats["maintenance_invalidated_hours"] == 1


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


def test_feature_contract_does_not_need_open_high_low_geometry_or_returns():
    hour = pd.Timestamp("2022-01-02T03:00:00Z")
    key = timestamp_key(hour)

    got = compute_axes(
        hour,
        {
            "BTC-USDT": {key: 100.0},
            "ETH-USDT": {key: 200.0},
        },
        {
            "BTCUSDT": {key: 101.0},
            "ETHUSDT": {key: 202.0},
        },
    )

    assert got["feature_valid"] is True
    assert set(
        name for name in got if name.endswith("_kucoin_close") or name.endswith("_binance_close")
    ) == {
        "btc_kucoin_close",
        "btc_binance_close",
        "eth_kucoin_close",
        "eth_binance_close",
    }
