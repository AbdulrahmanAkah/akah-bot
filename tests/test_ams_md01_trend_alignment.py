from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.ams_md01_momentum import (
    build_daily_crisis,
    build_trend_features,
    classify_alignment,
)


def _trend_frame(close: np.ndarray, frequency: str = "1D") -> pd.DataFrame:
    opens = pd.date_range("2021-01-01", periods=len(close), freq=frequency, tz="UTC")
    delta = pd.Timedelta(frequency)
    return pd.DataFrame(
        {
            "symbol": "BTC",
            "bar_open_time": opens,
            "bar_close_time": opens + delta,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        }
    )


def test_uptrend_and_downtrend_are_transparent() -> None:
    up = build_trend_features(_trend_frame(np.arange(100.0, 200.0)))
    down = build_trend_features(_trend_frame(np.arange(200.0, 100.0, -1.0)))
    assert up.iloc[-1]["trend_state"] == "UPTREND"
    assert down.iloc[-1]["trend_state"] == "DOWNTREND"


def test_recovery_and_neutral_states() -> None:
    close = np.r_[np.linspace(100, 70, 60), np.linspace(70, 92, 12)]
    recovered = build_trend_features(_trend_frame(close))
    assert recovered.iloc[-1]["trend_state"] in {"RECOVERY", "UPTREND"}
    flat = build_trend_features(_trend_frame(np.full(80, 100.0)))
    assert flat.iloc[-1]["trend_state"] == "NEUTRAL"


def test_alignment_tiers_and_crisis_override() -> None:
    assert classify_alignment(
        daily_positive=True, eight_hour_positive=True, four_hour_positive=True
    ) == ("FULL", 1.0)
    assert classify_alignment(
        daily_positive=True, eight_hour_positive=False, four_hour_positive=True
    ) == ("MEDIUM", 0.67)
    assert classify_alignment(
        daily_positive=False, eight_hour_positive=False, four_hour_positive=True
    ) == ("FOUR_HOUR_ONLY", 0.33)
    assert classify_alignment(
        daily_positive=True, eight_hour_positive=True, four_hour_positive=False
    ) == ("NONE", 0.0)
    assert classify_alignment(
        daily_positive=True,
        eight_hour_positive=True,
        four_hour_positive=True,
        crisis=True,
    ) == ("NONE", 0.0)


def test_crisis_is_causal_and_requires_drawdown_and_downtrend() -> None:
    close = np.r_[np.linspace(100, 160, 100), np.linspace(160, 90, 60)]
    features = build_trend_features(_trend_frame(close))
    crisis = build_daily_crisis(features)
    assert crisis.iloc[-1]["daily_market_regime"] == "CRISIS"
    original = crisis.loc[crisis["bar_close_time"] <= pd.Timestamp("2021-05-01", tz="UTC")]
    mutated = _trend_frame(close.copy())
    mutated.loc[mutated["bar_close_time"] > pd.Timestamp("2021-05-01", tz="UTC"), "close"] *= 10
    after = build_daily_crisis(build_trend_features(mutated))
    after = after.loc[after["bar_close_time"] <= pd.Timestamp("2021-05-01", tz="UTC")]
    pd.testing.assert_series_equal(
        original["daily_market_regime"].reset_index(drop=True),
        after["daily_market_regime"].reset_index(drop=True),
    )


def test_four_hour_reclaim_breakout_and_overextension() -> None:
    close = np.r_[np.linspace(100, 130, 60), [125, 124, 126, 132]]
    frame = _trend_frame(close, "4h")
    features = build_trend_features(frame, four_hour=True)
    assert features.iloc[-1]["entry_trigger"] in {"EMA20_RECLAIM", "THREE_BAR_BREAKOUT"}
    stretched = frame.copy()
    stretched.loc[stretched.index[-1], ["open", "high", "low", "close"]] = [
        250,
        251,
        249,
        250,
    ]
    stretched_features = build_trend_features(stretched, four_hour=True)
    assert bool(stretched_features.iloc[-1]["overextended"])
    assert not bool(stretched_features.iloc[-1]["four_hour_positive"])

