from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.ams_md01_momentum import (
    MD01Error,
    momentum_at,
    rank_buckets,
    select_assets,
    variant_spec,
)


def _daily(symbol: str, multiplier: float = 1.0) -> pd.DataFrame:
    opens = pd.date_range("2021-01-01", periods=120, freq="1D", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": symbol,
            "bar_open_time": opens,
            "bar_close_time": opens + pd.Timedelta(days=1),
            "close": [(100 + index) * multiplier for index in range(120)],
        }
    )


def test_4w_and_12w_returns_are_exact() -> None:
    frame = _daily("BTC")
    timestamp = pd.Timestamp("2021-04-30T00:00:00Z")
    current = frame.loc[frame["bar_close_time"] <= timestamp].iloc[-1]["close"]
    prior_28 = frame.loc[
        frame["bar_close_time"] <= timestamp - pd.Timedelta(days=28)
    ].iloc[-1]["close"]
    prior_84 = frame.loc[
        frame["bar_close_time"] <= timestamp - pd.Timedelta(days=84)
    ].iloc[-1]["close"]
    assert momentum_at(frame, timestamp, 28) == pytest.approx(current / prior_28 - 1)
    assert momentum_at(frame, timestamp, 84) == pytest.approx(current / prior_84 - 1)


def test_only_registered_horizons_and_variants() -> None:
    with pytest.raises(MD01Error):
        momentum_at(_daily("BTC"), pd.Timestamp("2021-04-30", tz="UTC"), 42)
    with pytest.raises(MD01Error):
        variant_spec("MD01-M07")


def test_cross_sectional_ties_are_deterministic_and_dual_filters_negative() -> None:
    ranked = pd.DataFrame(
        {
            "symbol": ["ADA", "BTC", "ETH", "SOL"],
            "momentum_return": [0.2, 0.2, -0.1, 0.1],
            "percentile_rank": [1.0, 0.66, 0.0, 0.33],
        }
    ).sort_values(["momentum_return", "symbol"], ascending=[False, True])
    selected, _ = select_assets(
        ranked,
        variant=variant_spec("MD01-M05"),
        clusters={symbol: f"CL-{symbol}" for symbol in ranked["symbol"]},
    )
    assert selected == ["ADA", "BTC", "SOL"]
    assert "ETH" not in selected


def test_rank_buckets_are_exhaustive_nonoverlapping() -> None:
    frame = pd.DataFrame(
        {"momentum_return": [0.5, 0.4, 0.3, 0.2, 0.1], "symbol": list("ABCDE")}
    )
    buckets = rank_buckets(frame)
    assert buckets.notna().all()
    assert sorted(buckets.tolist()) == [0, 1, 2, 3, 4]
