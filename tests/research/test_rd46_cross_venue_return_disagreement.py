from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd46_cross_venue_return_disagreement import (
    AXIS_DISPERSION,
    AXIS_MEAN,
    aggregate_binance_hours,
    compute_axes,
    hour_overlaps_maintenance,
    kucoin_hour_lookup,
    qualify_transport_support,
    support_census,
)


def minute_frame(hour: str, count: int = 60) -> pd.DataFrame:
    h = pd.Timestamp(hour)
    times = pd.date_range(h, periods=count, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "open_time": [int(t.timestamp() * 1000) for t in times],
            "open": [100.0 + i for i in range(count)],
            "close": [100.5 + i for i in range(count)],
        }
    )


def test_binance_hour_requires_exact_60_minute_grid_and_uses_first_open_last_close() -> None:
    lookup, stats = aggregate_binance_hours(minute_frame("2022-01-01T00:00:00Z"))
    key = int(pd.Timestamp("2022-01-01T00:00:00Z").value)
    assert stats["valid_hours"] == 1
    assert lookup[key] == (100.0, 159.5)

    bad = minute_frame("2022-01-01T01:00:00Z", 59)
    lookup, stats = aggregate_binance_hours(bad)
    assert lookup == {}
    assert stats["invalid_grid_hours"] == 1


def test_duplicate_minute_invalidates_whole_binance_hour() -> None:
    frame = minute_frame("2022-01-02T00:00:00Z")
    frame.loc[59, "open_time"] = frame.loc[58, "open_time"]
    lookup, stats = aggregate_binance_hours(frame)
    assert lookup == {}
    assert stats["invalid_grid_hours"] == 1


def test_maintenance_overlap_invalidates_whole_hour() -> None:
    assert hour_overlaps_maintenance(pd.Timestamp("2023-03-24T11:00:00Z"))
    assert hour_overlaps_maintenance(pd.Timestamp("2023-03-24T12:00:00Z"))
    assert hour_overlaps_maintenance(pd.Timestamp("2023-03-24T13:00:00Z"))
    assert not hour_overlaps_maintenance(pd.Timestamp("2023-03-24T14:00:00Z"))
    lookup, stats = aggregate_binance_hours(minute_frame("2023-03-24T13:00:00Z"))
    assert lookup == {}
    assert stats["maintenance_invalidated_hours"] == 1


def test_kucoin_duplicate_timestamp_keeps_last() -> None:
    raw = pd.DataFrame(
        {
            "timestamp": ["2022-01-01T00:00:00Z", "2022-01-01T00:00:00Z"],
            "open": [100.0, 200.0],
            "close": [110.0, 220.0],
        }
    )
    lookup = kucoin_hour_lookup(raw)
    assert lookup[int(pd.Timestamp("2022-01-01T00:00:00Z").value)] == (200.0, 220.0)


def test_axes_are_preregistered_open_to_close_binance_minus_kucoin() -> None:
    h = pd.Timestamp("2022-01-01T00:00:00Z")
    key = int(h.value)
    kucoin = {
        "BTC-USDT": {key: (100.0, 101.0)},
        "ETH-USDT": {key: (200.0, 198.0)},
    }
    binance = {
        "BTCUSDT": {key: (100.0, 102.0)},
        "ETHUSDT": {key: (200.0, 202.0)},
    }
    result = compute_axes(h, kucoin, binance)
    g_btc = math.log(102 / 100) - math.log(101 / 100)
    g_eth = math.log(202 / 200) - math.log(198 / 200)
    assert result["feature_valid"] is True
    assert math.isclose(result[AXIS_MEAN], 0.5 * (g_btc + g_eth))
    assert math.isclose(result[AXIS_DISPERSION], 0.5 * abs(g_btc - g_eth))


def test_missing_any_symbol_venue_hour_fails_closed() -> None:
    h = pd.Timestamp("2022-01-01T00:00:00Z")
    key = int(h.value)
    kucoin = {"BTC-USDT": {key: (100.0, 101.0)}, "ETH-USDT": {key: (200.0, 201.0)}}
    binance = {"BTCUSDT": {key: (100.0, 101.0)}, "ETHUSDT": {}}
    result = compute_axes(h, kucoin, binance)
    assert result["feature_valid"] is False


def _base_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        year = 2022 if period.endswith("2022") else 2023
        for universe in ("C2", "D2", "E2"):
            for age in (24, 48, 72, 96, 120, 144):
                for i in range(20):
                    rows.append(
                        {
                            "period_id": period,
                            "universe_id": universe,
                            "landmark_age_hours": age,
                            "control_position_id": f"{period}:{universe}:{age}:{i}",
                            "pair": f"P{i % 5}",
                            "signal_time": pd.Timestamp(f"{year}-01-01T00:00:00Z")
                            + pd.Timedelta(days=i % 10),
                            "feature_valid": True,
                        }
                    )
    return rows


def test_support_gate_is_positions_pairs_signal_days_only() -> None:
    census = support_census(pd.DataFrame(_base_rows()))
    assert len(census) == 36
    assert bool(census["support_pass"].all())


def test_transport_requires_two_of_three_universes_in_both_years() -> None:
    records = []
    for period in ("ROBUSTNESS_2022", "ROBUSTNESS_2023"):
        for ui, universe in enumerate(("C2", "D2", "E2")):
            for age in (24, 48, 72, 96, 120, 144):
                records.append(
                    {
                        "period_id": period,
                        "universe_id": universe,
                        "landmark_age_hours": age,
                        "support_pass": age == 24 and ui < 2,
                    }
                )
    q = qualify_transport_support(pd.DataFrame(records))
    assert q["qualified_landmarks_hours"] == [24]
