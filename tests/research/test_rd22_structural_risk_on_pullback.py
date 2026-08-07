from __future__ import annotations

import pandas as pd

from spotbot.research.rd22_structural_risk_on_pullback import (
    HORIZON_HOURS,
    build_btc_daily_ema200_regime,
    regime_state_at,
    replay_fixed_horizon,
    validate_constants,
)


def synthetic_features() -> dict[str, pd.DataFrame]:
    times = pd.date_range("2019-08-01T00:00:00Z", periods=220, freq="h")
    close = pd.Series([100.0 + 0.05 * i for i in range(len(times))])
    frame = pd.DataFrame(
        {
            "timestamp": times,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close + 0.1,
            "volume": 1_000_000.0,
            "trailing_24h_quote_turnover_proxy": 1_000_000_000.0,
        }
    )
    return {"AAA-USDT": frame}


def synthetic_events() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "universe_id": "C2",
                "partition_id": "DISCOVERY_2019_2021",
                "timestamp": pd.Timestamp("2019-08-01T00:00:00Z"),
                "candidate_rank": 1,
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "score": 0.75,
                "initial_stop_reference": 95.0,
            }
        ]
    )


def synthetic_regime(on: bool = True) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2019-07-30T00:00:00Z"),
                "available_time": pd.Timestamp("2019-07-31T00:00:00Z"),
                "close": 100.0,
                "ema200": 90.0 if on else 110.0,
                "hourly_bar_count": 24,
                "regime_ready": True,
                "regime_on": on,
            }
        ]
    )


def btc_hourly_for_regime() -> pd.DataFrame:
    times = pd.date_range("2018-01-01T00:00:00Z", periods=210 * 24, freq="h")
    day = ((times - times[0]) / pd.Timedelta(days=1)).astype(int)
    close = 100.0 + day * 0.1
    return pd.DataFrame({"timestamp": times, "close": close})


def test_constants_are_frozen() -> None:
    validate_constants()
    assert HORIZON_HOURS == (168,)


def test_daily_regime_requires_200_completed_days() -> None:
    regime = build_btc_daily_ema200_regime(btc_hourly_for_regime())
    ready = regime.loc[regime["regime_ready"]]
    assert len(ready) > 0
    assert int(ready.index.min()) == 199


def test_daily_regime_is_only_available_next_midnight() -> None:
    regime = build_btc_daily_ema200_regime(btc_hourly_for_regime())
    ready = regime.loc[regime["regime_ready"]].iloc[0]
    daily_start = pd.Timestamp(ready["timestamp"])
    available = pd.Timestamp(ready["available_time"])
    assert available == daily_start + pd.Timedelta(days=1)
    assert regime_state_at(regime, available - pd.Timedelta(seconds=1)) is None
    assert regime_state_at(regime, available) is True


def test_risk_off_regime_rejects_signal_before_later_risk_on_signal() -> None:
    events = synthetic_events()
    second = events.iloc[0].copy()
    second["timestamp"] = pd.Timestamp("2019-08-02T00:00:00Z")
    events = pd.concat([events, second.to_frame().T], ignore_index=True)
    regime = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2019-07-30T00:00:00Z"),
                "available_time": pd.Timestamp("2019-07-31T00:00:00Z"),
                "close": 90.0,
                "ema200": 100.0,
                "hourly_bar_count": 24,
                "regime_ready": True,
                "regime_on": False,
            },
            {
                "timestamp": pd.Timestamp("2019-08-01T00:00:00Z"),
                "available_time": pd.Timestamp("2019-08-02T00:00:00Z"),
                "close": 110.0,
                "ema200": 100.0,
                "hourly_bar_count": 24,
                "regime_ready": True,
                "regime_on": True,
            },
        ]
    )
    trades, _equity, route = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=1.0,
        horizon_hours=168,
        events=events,
        features=synthetic_features(),
        regime=regime,
    )
    assert len(trades) == 1
    assert route["regime_off_rejections"] == 1
    assert route["regime_ready_on_candidates"] == 1
    assert route["admitted_entries"] == 1


def test_risk_on_horizon_exit_occurs_at_168h_open() -> None:
    trades, _equity, route = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=1.0,
        horizon_hours=168,
        events=synthetic_events(),
        features=synthetic_features(),
        regime=synthetic_regime(on=True),
    )
    assert route["regime_ready_on_candidates"] == 1
    assert route["fixed_horizon_exits"] == 1
    assert len(trades) == 1
    row = trades.iloc[0]
    assert row["exit_reason"] == "FIXED_HORIZON_168H_OPEN"
    assert pd.Timestamp(row["entry_time"]) == pd.Timestamp("2019-08-01T01:00:00Z")
    assert pd.Timestamp(row["exit_time"]) == pd.Timestamp("2019-08-08T01:00:00Z")


def test_static_stop_is_unchanged() -> None:
    features = synthetic_features()
    frame = features["AAA-USDT"].copy()
    frame.loc[3, "low"] = 94.0
    features["AAA-USDT"] = frame
    trades, _equity, route = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=1.0,
        horizon_hours=168,
        events=synthetic_events(),
        features=features,
        regime=synthetic_regime(on=True),
    )
    assert route["hard_stop_exits"] == 1
    assert route["fixed_horizon_exits"] == 0
    assert trades.iloc[0]["exit_reason"] == "HARD_STOP_STATIC"
    assert float(trades.iloc[0]["exit_price"]) == 95.0


def test_two_x_cost_does_not_change_entry_or_exit_time() -> None:
    one, _eq1, _route1 = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=1.0,
        horizon_hours=168,
        events=synthetic_events(),
        features=synthetic_features(),
        regime=synthetic_regime(on=True),
    )
    two, _eq2, _route2 = replay_fixed_horizon(
        universe_id="C2",
        cost_multiplier=2.0,
        horizon_hours=168,
        events=synthetic_events(),
        features=synthetic_features(),
        regime=synthetic_regime(on=True),
    )
    assert one.iloc[0]["entry_time"] == two.iloc[0]["entry_time"]
    assert one.iloc[0]["exit_time"] == two.iloc[0]["exit_time"]
    assert float(two.iloc[0]["net_pnl"]) < float(one.iloc[0]["net_pnl"])
