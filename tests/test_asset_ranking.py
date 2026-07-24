from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.asset_ranking import (
    AssetRankingConfigurationError,
    AssetRankingPolicy,
    build_asset_ranking,
)


def make_policy(
    *,
    start: datetime,
    end: datetime,
) -> AssetRankingPolicy:
    return AssetRankingPolicy(
        research_start=start,
        research_end_exclusive=end,
        momentum_short_days=5,
        momentum_long_days=10,
        volatility_days=5,
        turnover_short_days=3,
        turnover_long_days=5,
        drawdown_days=10,
        minimum_volatility_observations=3,
        minimum_turnover_short_observations=2,
        minimum_turnover_long_observations=3,
        minimum_drawdown_observations=5,
        minimum_cross_section_size=2,
    )


def make_history(
    symbol: str,
    *,
    daily_growth: float,
    turnover: float,
    periods: int = 40,
) -> pd.DataFrame:
    times = pd.date_range(
        start="2020-12-01",
        periods=periods,
        freq="1D",
        tz="UTC",
    )

    prices: list[float] = []
    price = 100.0

    for _ in range(periods):
        prices.append(price)
        price *= 1.0 + daily_growth

    return pd.DataFrame(
        {
            "symbol": [
                symbol
            ] * periods,
            "close_time": times,
            "close": prices,
            "quote_turnover": [
                turnover
            ] * periods,
        }
    )


def make_universe(
    symbols: list[str],
    *,
    snapshot: str,
    ineligible_symbol: str | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "snapshot_time": pd.to_datetime(
                [
                    snapshot
                ] * len(symbols),
                utc=True,
            ),
            "symbol": symbols,
            "eligible": [
                symbol != ineligible_symbol
                for symbol in symbols
            ],
        }
    )


def test_strongest_asset_ranks_first() -> None:
    history = pd.concat(
        [
            make_history(
                "BTC/USDT",
                daily_growth=0.001,
                turnover=1_000_000.0,
            ),
            make_history(
                "FAST/USDT",
                daily_growth=0.010,
                turnover=2_000_000.0,
            ),
            make_history(
                "MID/USDT",
                daily_growth=0.005,
                turnover=1_500_000.0,
            ),
        ],
        ignore_index=True,
    )

    universe = make_universe(
        [
            "BTC/USDT",
            "FAST/USDT",
            "MID/USDT",
        ],
        snapshot="2021-01-09T00:00:00Z",
    )

    result = build_asset_ranking(
        history,
        universe,
        policy=make_policy(
            start=datetime(
                2021,
                1,
                9,
                tzinfo=UTC,
            ),
            end=datetime(
                2021,
                1,
                10,
                tzinfo=UTC,
            ),
        ),
    )

    first = result.iloc[0]

    assert first["symbol"] == "FAST/USDT"
    assert (
        first["rank_within_snapshot"]
        == 1
    )


def test_ineligible_asset_is_not_ranked() -> None:
    history = pd.concat(
        [
            make_history(
                "BTC/USDT",
                daily_growth=0.001,
                turnover=1_000_000.0,
            ),
            make_history(
                "FAST/USDT",
                daily_growth=0.010,
                turnover=2_000_000.0,
            ),
            make_history(
                "MID/USDT",
                daily_growth=0.005,
                turnover=1_500_000.0,
            ),
        ],
        ignore_index=True,
    )

    universe = make_universe(
        [
            "BTC/USDT",
            "FAST/USDT",
            "MID/USDT",
        ],
        snapshot="2021-01-09T00:00:00Z",
        ineligible_symbol="FAST/USDT",
    )

    result = build_asset_ranking(
        history,
        universe,
        policy=make_policy(
            start=datetime(
                2021,
                1,
                9,
                tzinfo=UTC,
            ),
            end=datetime(
                2021,
                1,
                10,
                tzinfo=UTC,
            ),
        ),
    )

    assert "FAST/USDT" not in set(
        result["symbol"]
    )


def test_future_price_cannot_change_earlier_rank() -> None:
    base_history = pd.concat(
        [
            make_history(
                "BTC/USDT",
                daily_growth=0.001,
                turnover=1_000_000.0,
            ),
            make_history(
                "FAST/USDT",
                daily_growth=0.010,
                turnover=2_000_000.0,
            ),
            make_history(
                "MID/USDT",
                daily_growth=0.005,
                turnover=1_500_000.0,
            ),
        ],
        ignore_index=True,
    )

    universe = make_universe(
        [
            "BTC/USDT",
            "FAST/USDT",
            "MID/USDT",
        ],
        snapshot="2021-01-09T00:00:00Z",
    )

    policy = make_policy(
        start=datetime(
            2021,
            1,
            9,
            tzinfo=UTC,
        ),
        end=datetime(
            2021,
            1,
            10,
            tzinfo=UTC,
        ),
    )

    original = build_asset_ranking(
        base_history,
        universe,
        policy=policy,
    )

    future = pd.DataFrame(
        {
            "symbol": [
                "MID/USDT",
            ],
            "close_time": pd.to_datetime(
                [
                    "2021-01-20T00:00:00Z",
                ],
                utc=True,
            ),
            "close": [
                1_000_000.0,
            ],
            "quote_turnover": [
                100_000_000.0,
            ],
        }
    )

    extended = build_asset_ranking(
        pd.concat(
            [
                base_history,
                future,
            ],
            ignore_index=True,
        ),
        universe,
        policy=policy,
    )

    pd.testing.assert_frame_equal(
        original.reset_index(drop=True),
        extended.reset_index(drop=True),
    )


def test_feature_times_never_exceed_snapshot() -> None:
    history = pd.concat(
        [
            make_history(
                "BTC/USDT",
                daily_growth=0.001,
                turnover=1_000_000.0,
            ),
            make_history(
                "FAST/USDT",
                daily_growth=0.010,
                turnover=2_000_000.0,
            ),
        ],
        ignore_index=True,
    )

    universe = make_universe(
        [
            "BTC/USDT",
            "FAST/USDT",
        ],
        snapshot="2021-01-09T00:00:00Z",
    )

    result = build_asset_ranking(
        history,
        universe,
        policy=make_policy(
            start=datetime(
                2021,
                1,
                9,
                tzinfo=UTC,
            ),
            end=datetime(
                2021,
                1,
                10,
                tzinfo=UTC,
            ),
        ),
    )

    assert bool(
        (
            result["feature_time"]
            <= result["snapshot_time"]
        ).all()
    )

    assert bool(
        (
            result["benchmark_feature_time"]
            <= result["snapshot_time"]
        ).all()
    )


def test_naive_policy_timestamp_is_rejected() -> None:
    with pytest.raises(
        AssetRankingConfigurationError,
        match="timezone-aware",
    ):
        AssetRankingPolicy(
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
