from __future__ import annotations

import pandas as pd

from spotbot.research.ams_md01_momentum import (
    causal_cluster_snapshot,
    eligible_universe_at,
)


def _bars(symbol: str, periods: int, frequency: str) -> pd.DataFrame:
    opens = pd.date_range("2021-01-01", periods=periods, freq=frequency, tz="UTC")
    delta = pd.Timedelta(frequency)
    close = pd.Series(range(100, 100 + periods), dtype=float)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "bar_open_time": opens,
            "bar_close_time": opens + delta,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1000.0,
        }
    )


def test_point_in_time_eligibility_and_history_minimum() -> None:
    daily = pd.concat([_bars("BTC", 150, "1D"), _bars("ETH", 150, "1D")])
    eight = pd.concat([_bars("BTC", 450, "8h"), _bars("ETH", 450, "8h")])
    four = pd.concat([_bars("BTC", 900, "4h"), _bars("ETH", 900, "4h")])
    availability = pd.DataFrame(
        {
            "symbol": ["BTC", "ETH"],
            "tradable_from": pd.to_datetime(
                ["2021-01-01T00:00:00Z", "2021-04-15T00:00:00Z"], utc=True
            ),
            "tradable_until": pd.to_datetime(
                ["2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"], utc=True
            ),
        }
    )
    ranked, audit = eligible_universe_at(
        timestamp=pd.Timestamp("2021-04-01T00:00:00Z"),
        horizon_days=84,
        daily=daily,
        eight_hour=eight,
        four_hour=four,
        availability=availability,
    )
    assert ranked["symbol"].tolist() == ["BTC"]
    assert audit["tradable_count"] == 1
    ranked_after, _ = eligible_universe_at(
        timestamp=pd.Timestamp("2021-05-01T00:00:00Z"),
        horizon_days=84,
        daily=daily,
        eight_hour=eight,
        four_hour=four,
        availability=availability,
    )
    assert set(ranked_after["symbol"]) == {"BTC", "ETH"}


def test_future_availability_mutation_does_not_change_historical_membership() -> None:
    daily = _bars("BTC", 150, "1D")
    eight = _bars("BTC", 450, "8h")
    four = _bars("BTC", 900, "4h")
    availability = pd.DataFrame(
        {
            "symbol": ["BTC"],
            "tradable_from": pd.to_datetime(["2021-01-01T00:00:00Z"], utc=True),
            "tradable_until": pd.to_datetime(["2025-01-01T00:00:00Z"], utc=True),
        }
    )
    baseline, _ = eligible_universe_at(
        timestamp=pd.Timestamp("2021-04-01T00:00:00Z"),
        horizon_days=84,
        daily=daily,
        eight_hour=eight,
        four_hour=four,
        availability=availability,
    )
    mutated = availability.copy()
    mutated.loc[0, "tradable_until"] = pd.Timestamp("2024-01-01T00:00:00Z")
    after, _ = eligible_universe_at(
        timestamp=pd.Timestamp("2021-04-01T00:00:00Z"),
        horizon_days=84,
        daily=daily,
        eight_hour=eight,
        four_hour=four,
        availability=mutated,
    )
    assert baseline["symbol"].tolist() == after["symbol"].tolist()


def test_causal_clusters_ignore_future_price_mutation() -> None:
    btc = _bars("BTC", 200, "1D")
    eth = _bars("ETH", 200, "1D")
    eth["close"] = btc["close"].to_numpy() * 2
    daily = pd.concat([btc, eth], ignore_index=True)
    cutoff = pd.Timestamp("2021-05-01T00:00:00Z")
    baseline, _, _, _ = causal_cluster_snapshot(
        daily, timestamp=cutoff, symbols=["BTC", "ETH"]
    )
    daily.loc[daily["bar_close_time"] > cutoff, "close"] *= 100
    after, _, _, _ = causal_cluster_snapshot(
        daily, timestamp=cutoff, symbols=["BTC", "ETH"]
    )
    assert baseline == after
    assert baseline["BTC"] == baseline["ETH"]

