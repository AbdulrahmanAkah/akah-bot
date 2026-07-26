from __future__ import annotations

import pandas as pd

from spotbot.research.dominance_features import build_dominance_features
from spotbot.research.dominance_regime import (
    DominanceRegime,
    classify_regime,
    compose_timeframes,
)


def _features(**overrides: float) -> dict[str, float]:
    values = {
        "btc_d_slope": 0.01,
        "eth_d_slope": -0.01,
        "stable_d_slope": -0.01,
        "btc_market_cap_slope": 1.0,
        "stable_market_cap_slope": 0.0,
        "total_ex_stable_slope": 1.0,
        "outside_top10_market_cap_slope": -0.1,
        "outside_top10_to_btc_slope": -0.1,
    }
    values.update(overrides)
    return values


def test_btc_leadership_has_explainable_reason_codes() -> None:
    result = classify_regime(
        _features(), timestamp=pd.Timestamp("2024-01-01T00:00:00Z")
    )
    assert result.primary_regime is DominanceRegime.BTC_LEADERSHIP
    assert "BTC_SHARE_RISING" in result.reason_codes


def test_cash_flight_requires_absolute_risk_weakness() -> None:
    result = classify_regime(
        _features(
            stable_d_slope=0.02,
            total_ex_stable_slope=-1.0,
            btc_market_cap_slope=-1.0,
        ),
        timestamp=pd.Timestamp("2024-01-01T00:00:00Z"),
    )
    assert result.primary_regime is DominanceRegime.CASH_FLIGHT


def test_missing_data_fails_closed() -> None:
    result = classify_regime(
        {}, timestamp=pd.Timestamp("2024-01-01T00:00:00Z")
    )
    assert result.primary_regime is DominanceRegime.INSUFFICIENT_DATA


def test_daily_remains_primary_when_intraday_conflicts() -> None:
    timestamp = pd.Timestamp("2024-01-01T00:00:00Z")
    daily = classify_regime(_features(), timestamp=timestamp)
    intraday = classify_regime(
        _features(
            stable_d_slope=0.02,
            total_ex_stable_slope=-1.0,
            btc_market_cap_slope=-1.0,
        ),
        timestamp=timestamp,
    )
    composite = compose_timeframes(daily, intraday, intraday)
    assert composite.primary_regime is DominanceRegime.BTC_LEADERSHIP
    assert "TIMEFRAME_CONFLICT" in composite.reason_codes


def test_future_mutation_does_not_change_past_features() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC"),
            "btc_d": range(20),
            "btc_market_cap": range(100, 120),
        }
    )
    cutoff = pd.Timestamp("2024-01-15T00:00:00Z")
    before = build_dominance_features(frame.loc[frame["timestamp"] <= cutoff])
    mutated = frame.copy()
    mutated.loc[mutated["timestamp"] > cutoff, "btc_d"] = 10_000
    after = build_dominance_features(mutated.loc[mutated["timestamp"] <= cutoff])
    pd.testing.assert_frame_equal(before, after)

