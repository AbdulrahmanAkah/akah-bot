from __future__ import annotations

import math

import pandas as pd

from spotbot.research.rd20_p3_core_edge import (
    contribution_diagnostics,
    fixed_path_pf1_break_even_multiplier,
    prepare_economic_frame,
    replay_universe,
)


def _feature_frame_for_stop_test() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2023-12-31T20:00:00Z",
        periods=4,
        freq="h",
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [101.0, 102.0, 101.0, 101.0],
            "low": [99.0, 94.0, 99.0, 99.0],
            "close": [100.0, 100.0, 100.0, 100.0],
            "ema24": [99.0, 99.0, 99.0, 99.0],
            "trailing_24h_quote_turnover_proxy": [10_000_000.0] * 4,
        }
    )


def test_replay_enters_next_bar_and_static_stop_same_bar() -> None:
    events = pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "partition_id": "STRESS_2023",
                "timestamp": pd.Timestamp("2023-12-31T20:00:00Z"),
                "candidate_rank": 1,
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "score": 0.8,
                "initial_stop_reference": 95.0,
            }
        ]
    )
    trades, _, route = replay_universe(
        universe_id="C2",
        cost_multiplier=1.0,
        events=events,
        features={"AAA-USDT": _feature_frame_for_stop_test()},
    )

    assert len(trades) == 1
    trade = trades.iloc[0]
    assert pd.Timestamp(trade["entry_time"]) == pd.Timestamp("2023-12-31T21:00:00Z")
    assert pd.Timestamp(trade["exit_time"]) == pd.Timestamp("2023-12-31T21:00:00Z")
    assert trade["exit_reason"] == "HARD_STOP_STATIC"
    assert float(trade["exit_price"]) == 95.0
    assert math.isclose(float(trade["mae_return"]), -0.05)
    assert route["negative_cash_observed"] is False


def test_replay_thesis_exit_executes_next_bar_open() -> None:
    frame = _feature_frame_for_stop_test()
    frame.loc[:, "low"] = 98.0
    frame.loc[:, "ema24"] = 99.0
    frame.loc[2, "close"] = 98.5
    frame.loc[3, "open"] = 98.0
    events = pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "partition_id": "STRESS_2023",
                "timestamp": pd.Timestamp("2023-12-31T20:00:00Z"),
                "candidate_rank": 1,
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "score": 0.8,
                "initial_stop_reference": 90.0,
            }
        ]
    )
    trades, _, _ = replay_universe(
        universe_id="C2",
        cost_multiplier=1.0,
        events=events,
        features={"AAA-USDT": frame},
    )
    assert len(trades) == 1
    trade = trades.iloc[0]
    assert trade["exit_reason"] == "THESIS_INVALIDATION_NEXT_BAR_OPEN"
    assert pd.Timestamp(trade["exit_time"]) == pd.Timestamp("2023-12-31T23:00:00Z")
    assert float(trade["exit_price"]) == 98.0


def test_prepare_economic_frame_requires_volume() -> None:
    timestamps = pd.date_range("2023-12-01", periods=100, freq="h", tz="UTC")
    raw = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
        }
    )
    try:
        prepare_economic_frame(raw)
    except Exception as exc:
        assert "volume" in str(exc)
    else:
        raise AssertionError("missing volume must fail")


def test_prepare_economic_frame_capacity_uses_completed_24h_sum() -> None:
    timestamps = pd.date_range("2023-12-01", periods=100, freq="h", tz="UTC")
    raw = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + index * 0.01 for index in range(100)],
            "high": [101.0 + index * 0.01 for index in range(100)],
            "low": [99.0 + index * 0.01 for index in range(100)],
            "close": [100.0 + index * 0.01 for index in range(100)],
            "volume": [10_000.0] * 100,
        }
    )
    frame = prepare_economic_frame(raw)
    assert math.isclose(
        float(frame.iloc[30]["trailing_24h_quote_turnover_proxy"]),
        float((raw.loc[7:30, "volume"] * raw.loc[7:30, "close"]).sum()),
    )


def test_pf1_break_even_cost_multiplier_is_finite_and_positive() -> None:
    trades = pd.DataFrame(
        {
            "gross_pnl": [100.0, 50.0, -40.0],
            "base_cost_dollars_per_multiplier": [10.0, 10.0, 10.0],
        }
    )
    value = fixed_path_pf1_break_even_multiplier(trades)
    assert value > 0.0
    assert math.isfinite(value)


def test_concentration_diagnostics_reports_leave_one_out() -> None:
    trades = pd.DataFrame(
        {
            "pair": ["A-USDT", "A-USDT", "B-USDT"],
            "entry_time": pd.to_datetime(
                [
                    "2021-01-01T00:00:00Z",
                    "2022-01-01T00:00:00Z",
                    "2022-02-01T00:00:00Z",
                ],
                utc=True,
            ),
            "net_pnl": [100.0, -10.0, 50.0],
        }
    )
    diagnostics, loao, loyo = contribution_diagnostics(trades)
    assert diagnostics["net_pnl_without_largest_winner"] == 40.0
    assert set(loao["removed_asset"]) == {"A-USDT", "B-USDT"}
    assert set(loyo["removed_year"]) == {2021, 2022}
