from __future__ import annotations

import pandas as pd

from spotbot.research.ams_md01r1_universe import calculate_liquidity_history


def _four_hour(turnover: float, periods: int = 600) -> pd.DataFrame:
    opens = pd.date_range("2021-01-01", periods=periods, freq="4h", tz="UTC")
    close = pd.Series([100.0] * periods)
    return pd.DataFrame(
        {
            "bar_open_time": opens,
            "bar_close_time": opens + pd.Timedelta(hours=4),
            "close": close,
            "volume": turnover / close,
        }
    )


def test_liquidity_uses_causal_trailing_history() -> None:
    frame = _four_hour(300_000.0)
    cutoff = pd.Timestamp(frame["bar_close_time"].iloc[-1])
    result = calculate_liquidity_history(frame, timestamp=cutoff)
    assert result["median_quote_turnover_30d"] == 300_000.0
    assert result["eligible"] is True


def test_liquidity_threshold_rejects_thin_asset() -> None:
    frame = _four_hour(249_999.0)
    result = calculate_liquidity_history(
        frame, timestamp=pd.Timestamp(frame["bar_close_time"].iloc[-1])
    )
    assert result["eligible"] is False
