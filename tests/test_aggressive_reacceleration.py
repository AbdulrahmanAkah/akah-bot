from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.aggressive_reacceleration import (
    AggressiveReaccelerationConfigurationError,
    AggressiveReaccelerationPolicy,
    build_aggressive_reacceleration_signals,
    build_aggressive_reacceleration_weights,
)


def policy() -> AggressiveReaccelerationPolicy:
    return AggressiveReaccelerationPolicy(
        research_start=datetime(
            2021,
            1,
            1,
            tzinfo=UTC,
        ),
        research_end_exclusive=datetime(
            2022,
            1,
            1,
            tzinfo=UTC,
        ),
        benchmark_symbol="BTC/USDT",
        momentum_days=3,
        ema_reclaim_days=10,
        relative_strength_days=60,
        ranking_maximum=5,
        maximum_positions=2,
        minimum_momentum=0.02,
        minimum_relative_strength=0.0,
        maximum_pullback=0.25,
        trailing_stop_atr=3.0,
        transaction_cost_fraction=0.002,
    )


def symbol_history(
    symbol: str,
    *,
    candidate_shape: bool,
    periods: int = 100,
) -> pd.DataFrame:
    open_time = pd.date_range(
        "2020-11-01",
        periods=periods,
        freq="1D",
        tz="UTC",
    )

    if symbol == "BTC/USDT":
        closes = [
            100.0
            for _ in range(periods)
        ]

    elif candidate_shape:
        closes = [
            80.0
            + (
                50.0
                * index
                / 59.0
            )
            if index < 60
            else 130.0
            for index in range(periods)
        ]

        replacement = {
            60: 125.0,
            61: 120.0,
            62: 115.0,
            63: 110.0,
            64: 108.0,
            65: 109.0,
            66: 116.0,
            67: 117.0,
        }

        for index, value in replacement.items():
            closes[index] = value

    else:
        closes = [
            100.0
            for _ in range(periods)
        ]

    close_series = pd.Series(
        closes,
        dtype=float,
    )

    return pd.DataFrame(
        {
            "symbol": symbol,
            "open_time": open_time,
            "close_time": (
                open_time
                + pd.Timedelta(days=1)
            ),
            "open": close_series,
            "high": (
                close_series
                * 1.01
            ),
            "low": (
                close_series
                * 0.99
            ),
            "close": close_series,
        }
    )


def ranking(
    frames: list[pd.DataFrame],
) -> pd.DataFrame:
    rows: list[
        dict[str, object]
    ] = []

    for rank_value, frame in enumerate(
        frames,
        start=1,
    ):
        symbol = str(
            frame["symbol"].iloc[0]
        )

        for snapshot in frame["close_time"]:
            rows.append(
                {
                    "snapshot_time": snapshot,
                    "symbol": symbol,
                    "composite_score": (
                        1.0
                        - rank_value / 100.0
                    ),
                    "rank_within_snapshot": (
                        rank_value
                    ),
                }
            )

    return pd.DataFrame(rows)


def full_history() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    btc = symbol_history(
        "BTC/USDT",
        candidate_shape=False,
    )

    alt = symbol_history(
        "ALT/USDT",
        candidate_shape=True,
    )

    history = pd.concat(
        [
            btc,
            alt,
        ],
        ignore_index=True,
    )

    return (
        history,
        ranking(
            [
                alt,
                btc,
            ]
        ),
    )


def test_reacceleration_candidate_is_detected() -> None:
    history, ranks = full_history()

    signals = (
        build_aggressive_reacceleration_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    candidates = signals.loc[
        signals["candidate"]
    ]

    assert not candidates.empty
    assert set(
        candidates["symbol"]
    ) == {"ALT/USDT"}

    first = candidates.iloc[0]

    assert bool(
        first["ema_reclaim_pass"]
    )

    assert (
        first["momentum_h02"]
        >= 0.02
    )

    assert (
        first[
            "relative_strength_60d_h02"
        ]
        >= 0.0
    )


def test_future_price_cannot_change_earlier_signals() -> None:
    history, ranks = full_history()

    original = (
        build_aggressive_reacceleration_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    future = history.tail(1).copy()

    future["symbol"] = "ALT/USDT"
    future["open_time"] = pd.Timestamp(
        "2023-01-01",
        tz="UTC",
    )
    future["close_time"] = pd.Timestamp(
        "2023-01-02",
        tz="UTC",
    )
    future[
        [
            "open",
            "high",
            "low",
            "close",
        ]
    ] = 1_000_000.0

    extended = (
        build_aggressive_reacceleration_signals(
            pd.concat(
                [
                    history,
                    future,
                ],
                ignore_index=True,
            ),
            ranks,
            policy=policy(),
        )
    )

    pd.testing.assert_frame_equal(
        original,
        extended,
    )


def test_weights_respect_spot_position_limits() -> None:
    btc = symbol_history(
        "BTC/USDT",
        candidate_shape=False,
    )

    alt = symbol_history(
        "ALT/USDT",
        candidate_shape=True,
    )

    eth = symbol_history(
        "ETH/USDT",
        candidate_shape=True,
    )

    history = pd.concat(
        [
            btc,
            alt,
            eth,
        ],
        ignore_index=True,
    )

    ranks = ranking(
        [
            alt,
            eth,
            btc,
        ]
    )

    signals = (
        build_aggressive_reacceleration_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    weights, _ = (
        build_aggressive_reacceleration_weights(
            history,
            signals,
            policy=policy(),
        )
    )

    exposure = (
        weights.groupby(
            "snapshot_time"
        )["target_weight"]
        .sum()
    )

    selected = (
        weights.groupby(
            "snapshot_time"
        )["selected"]
        .sum()
    )

    assert bool(
        (
            weights["target_weight"]
            >= 0.0
        ).all()
    )

    assert bool(
        (
            exposure
            <= 1.0 + 1e-12
        ).all()
    )

    assert bool(
        (
            selected
            <= 2
        ).all()
    )


def test_daily_trailing_stop_closes_position() -> None:
    history, ranks = full_history()

    initial_signals = (
        build_aggressive_reacceleration_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    candidate_time = (
        initial_signals.loc[
            initial_signals["candidate"],
            "snapshot_time",
        ]
        .iloc[0]
    )

    stop_time = (
        candidate_time
        + pd.Timedelta(days=1)
    )

    mask = (
        (
            history["symbol"]
            == "ALT/USDT"
        )
        & (
            history["close_time"]
            == stop_time
        )
    )

    assert int(mask.sum()) == 1

    history.loc[
        mask,
        "low",
    ] = 1.0

    signals = (
        build_aggressive_reacceleration_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    _, trades = (
        build_aggressive_reacceleration_weights(
            history,
            signals,
            policy=policy(),
        )
    )

    assert (
        "DAILY_TRAILING_STOP"
        in set(
            trades["exit_reason"]
        )
    )


def test_naive_policy_timestamp_is_rejected() -> None:
    with pytest.raises(
        AggressiveReaccelerationConfigurationError,
        match="timezone-aware",
    ):
        AggressiveReaccelerationPolicy(
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