import math

import pandas as pd
import pytest

from spotbot.research.universe import (
    PointInTimeUniverseConfig,
    PointInTimeUniverseDataError,
    build_point_in_time_spot_universe,
)


def universe_source(
    *,
    periods: int = 3,
) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2022-01-01",
        periods=periods,
        freq="1D",
        tz="UTC",
    )

    volume_by_day = (
        {
            "BTC/USDT": 100_000_000.0,
            "ETH/USDT": 90_000_000.0,
            "SOL/USDT": 80_000_000.0,
            "USDC/USDT": 200_000_000.0,
            "BTC3L/USDT": 300_000_000.0,
        },
        {
            "BTC/USDT": 110_000_000.0,
            "ETH/USDT": 50_000_000.0,
            "SOL/USDT": 120_000_000.0,
            "USDC/USDT": 210_000_000.0,
            "BTC3L/USDT": 310_000_000.0,
        },
        {
            "BTC/USDT": 70_000_000.0,
            "ETH/USDT": 130_000_000.0,
            "SOL/USDT": 125_000_000.0,
            "USDC/USDT": 220_000_000.0,
            "BTC3L/USDT": 320_000_000.0,
        },
    )

    rows: list[
        dict[str, object]
    ] = []

    symbols = (
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "USDC/USDT",
        "BTC3L/USDT",
    )

    for day_index, timestamp in enumerate(
        timestamps
    ):
        for symbol in symbols:
            rows.append(
                {
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "quote_asset": "USDT",
                    "close": 100.0,
                    "quote_volume": (
                        volume_by_day[
                            day_index
                        ][symbol]
                    ),
                    "listing_age_days": 500,
                    "is_spot": True,
                    "is_stablecoin": (
                        symbol == "USDC/USDT"
                    ),
                    "is_leveraged_token": (
                        symbol == "BTC3L/USDT"
                    ),
                    "is_suspended": False,
                }
            )

    return pd.DataFrame(rows)


def test_universe_selects_highest_liquidity_assets() -> None:
    result = (
        build_point_in_time_spot_universe(
            universe_source(),
            config=PointInTimeUniverseConfig(
                top_n=2,
            ),
        )
    )

    first_timestamp = result[
        "timestamp"
    ].min()

    selected = result.loc[
        (
            result["timestamp"]
            == first_timestamp
        )
        & result[
            "selected_at_snapshot"
        ],
        "symbol",
    ].tolist()

    assert selected == [
        "BTC/USDT",
        "ETH/USDT",
    ]


def test_stablecoins_and_leveraged_tokens_are_excluded() -> None:
    result = (
        build_point_in_time_spot_universe(
            universe_source(),
            config=PointInTimeUniverseConfig(
                top_n=5,
            ),
        )
    )

    excluded = result.loc[
        result["symbol"].isin(
            [
                "USDC/USDT",
                "BTC3L/USDT",
            ]
        )
    ]

    assert not bool(
        excluded["eligible"].any()
    )

    assert not bool(
        excluded[
            "selected_at_snapshot"
        ].any()
    )


def test_selection_activates_on_next_snapshot() -> None:
    result = (
        build_point_in_time_spot_universe(
            universe_source(),
            config=PointInTimeUniverseConfig(
                top_n=2,
            ),
        )
    )

    timestamps = sorted(
        result["timestamp"].unique()
    )

    day_two_tradable = result.loc[
        (
            result["timestamp"]
            == timestamps[1]
        )
        & result["tradable"],
        "symbol",
    ].tolist()

    assert day_two_tradable == [
        "BTC/USDT",
        "ETH/USDT",
    ]

    day_three_tradable = result.loc[
        (
            result["timestamp"]
            == timestamps[2]
        )
        & result["tradable"],
        "symbol",
    ].tolist()

    assert day_three_tradable == [
        "BTC/USDT",
        "SOL/USDT",
    ]


def test_future_snapshot_does_not_change_past_universe() -> None:
    two_days = (
        build_point_in_time_spot_universe(
            universe_source(
                periods=2
            ),
            config=PointInTimeUniverseConfig(
                top_n=2,
            ),
        )
    )

    three_days = (
        build_point_in_time_spot_universe(
            universe_source(
                periods=3
            ),
            config=PointInTimeUniverseConfig(
                top_n=2,
            ),
        )
    )

    cutoff = two_days[
        "timestamp"
    ].max()

    three_day_past = three_days.loc[
        three_days["timestamp"]
        <= cutoff
    ].reset_index(drop=True)

    comparison_columns = [
        "timestamp",
        "symbol",
        "eligible",
        "liquidity_rank",
        "selected_at_snapshot",
        "tradable",
    ]

    pd.testing.assert_frame_equal(
        two_days[
            comparison_columns
        ].reset_index(drop=True),
        three_day_past[
            comparison_columns
        ],
    )


def test_duplicate_timestamp_symbol_is_rejected() -> None:
    frame = universe_source()

    duplicated = pd.concat(
        [
            frame,
            frame.iloc[[0]],
        ],
        ignore_index=True,
    )

    with pytest.raises(
        PointInTimeUniverseDataError,
        match="duplicate",
    ):
        build_point_in_time_spot_universe(
            duplicated,
            config=PointInTimeUniverseConfig(),
        )


def test_nonfinite_volume_is_rejected() -> None:
    frame = universe_source()

    frame.loc[
        frame.index[0],
        "quote_volume",
    ] = math.inf

    with pytest.raises(
        PointInTimeUniverseDataError,
        match="non-finite",
    ):
        build_point_in_time_spot_universe(
            frame,
            config=PointInTimeUniverseConfig(),
        )