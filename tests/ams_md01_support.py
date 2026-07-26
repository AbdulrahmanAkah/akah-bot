from __future__ import annotations

import numpy as np
import pandas as pd


def bars(
    symbol: str,
    *,
    start: str,
    periods: int,
    frequency: str,
    drift: float = 0.15,
    offset: float = 0.0,
) -> pd.DataFrame:
    opens = pd.date_range(start, periods=periods, freq=frequency, tz="UTC")
    values = 100.0 + offset + np.arange(periods) * drift
    if frequency == "4h":
        values = values + np.sin(np.arange(periods) / 3.0) * 1.5
    delta = pd.Timedelta(frequency)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "bar_open_time": opens,
            "bar_close_time": opens + delta,
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values + 0.2,
            "volume": 1000.0,
        }
    )


def synthetic_registered_frames(symbols: tuple[str, ...] = ("BTC",)) -> dict[str, pd.DataFrame]:
    daily = pd.concat(
        [
            bars(
                symbol,
                start="2021-01-01",
                periods=250,
                frequency="1D",
                drift=0.25 + index * 0.03,
                offset=index * 2,
            )
            for index, symbol in enumerate(symbols)
        ],
        ignore_index=True,
    )
    eight = pd.concat(
        [
            bars(
                symbol,
                start="2021-01-01",
                periods=750,
                frequency="8h",
                drift=0.08 + index * 0.01,
                offset=index * 2,
            )
            for index, symbol in enumerate(symbols)
        ],
        ignore_index=True,
    )
    four = pd.concat(
        [
            bars(
                symbol,
                start="2021-01-01",
                periods=1500,
                frequency="4h",
                drift=0.04 + index * 0.005,
                offset=index * 2,
            )
            for index, symbol in enumerate(symbols)
        ],
        ignore_index=True,
    )
    availability = pd.DataFrame(
        {
            "symbol": list(symbols),
            "tradable_from": pd.to_datetime(["2021-01-01"] * len(symbols), utc=True),
            "tradable_until": pd.to_datetime(["2025-01-01"] * len(symbols), utc=True),
        }
    )
    return {
        "daily": daily,
        "eight_hour": eight,
        "four_hour": four,
        "availability": availability,
    }

