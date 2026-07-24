from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.bootstrap_point_in_time_universe import (
    BootstrapUniverseConfigurationError,
    BootstrapUniversePolicy,
    build_bootstrap_point_in_time_universe,
)


def policy(
    *,
    start: datetime,
    end: datetime,
) -> BootstrapUniversePolicy:
    return BootstrapUniversePolicy(
        research_start=start,
        research_end_exclusive=end,
        listing_age_days=90,
        liquidity_lookback_days=30,
        minimum_observations=20,
        minimum_median_quote_turnover=100_000.0,
        maximum_staleness_days=3,
    )


def history_frame(
    *,
    symbol: str,
    start: str,
    periods: int,
    turnover: float,
) -> pd.DataFrame:
    close_times = pd.date_range(
        start=start,
        periods=periods,
        freq="1D",
        tz="UTC",
    )

    return pd.DataFrame(
        {
            "symbol": [
                symbol
            ] * periods,
            "close_time": close_times,
            "quote_turnover": [
                turnover
            ] * periods,
        }
    )


def test_asset_becomes_eligible_after_age_and_liquidity() -> None:
    history = history_frame(
        symbol="BTC/USDT",
        start="2020-09-01",
        periods=122,
        turnover=500_000.0,
    )

    result = build_bootstrap_point_in_time_universe(
        history,
        policy=policy(
            start=datetime(
                2021,
                1,
                1,
                tzinfo=UTC,
            ),
            end=datetime(
                2021,
                1,
                2,
                tzinfo=UTC,
            ),
        ),
    )

    row = result.iloc[0]

    assert bool(row["listing_age_pass"])
    assert bool(row["recent_history_pass"])
    assert bool(row["liquidity_pass"])
    assert bool(row["eligible"])


def test_future_turnover_cannot_change_earlier_snapshot() -> None:
    historical = history_frame(
        symbol="LOW/USDT",
        start="2020-09-01",
        periods=122,
        turnover=50_000.0,
    )

    future = pd.DataFrame(
        {
            "symbol": [
                "LOW/USDT",
            ],
            "close_time": pd.to_datetime(
                [
                    "2021-01-02T00:00:00Z",
                ],
                utc=True,
            ),
            "quote_turnover": [
                100_000_000.0,
            ],
        }
    )

    result = build_bootstrap_point_in_time_universe(
        pd.concat(
            [
                historical,
                future,
            ],
            ignore_index=True,
        ),
        policy=policy(
            start=datetime(
                2021,
                1,
                1,
                tzinfo=UTC,
            ),
            end=datetime(
                2021,
                1,
                2,
                tzinfo=UTC,
            ),
        ),
    )

    row = result.iloc[0]

    assert not bool(row["liquidity_pass"])
    assert not bool(row["eligible"])


def test_insufficient_listing_age_is_rejected() -> None:
    history = history_frame(
        symbol="NEW/USDT",
        start="2020-11-01",
        periods=61,
        turnover=500_000.0,
    )

    result = build_bootstrap_point_in_time_universe(
        history,
        policy=policy(
            start=datetime(
                2021,
                1,
                1,
                tzinfo=UTC,
            ),
            end=datetime(
                2021,
                1,
                2,
                tzinfo=UTC,
            ),
        ),
    )

    row = result.iloc[0]

    assert not bool(row["listing_age_pass"])
    assert not bool(row["eligible"])


def test_stale_asset_is_rejected() -> None:
    history = history_frame(
        symbol="STALE/USDT",
        start="2020-08-01",
        periods=143,
        turnover=500_000.0,
    )

    result = build_bootstrap_point_in_time_universe(
        history,
        policy=policy(
            start=datetime(
                2021,
                1,
                1,
                tzinfo=UTC,
            ),
            end=datetime(
                2021,
                1,
                2,
                tzinfo=UTC,
            ),
        ),
    )

    row = result.iloc[0]

    assert not bool(row["recent_history_pass"])
    assert not bool(row["eligible"])


def test_naive_policy_timestamp_is_rejected() -> None:
    with pytest.raises(
        BootstrapUniverseConfigurationError,
        match="timezone-aware",
    ):
        BootstrapUniversePolicy(
            research_start=datetime(
                2021,
                1,
                1,
            ),
            research_end_exclusive=datetime(
                2022,
                1,
                1,
                tzinfo=UTC,
            ),
        )
