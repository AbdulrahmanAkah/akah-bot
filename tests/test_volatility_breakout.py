from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.volatility_breakout import (
    VolatilityBreakoutConfigurationError,
    VolatilityBreakoutPolicy,
    build_volatility_breakout_signals,
    build_volatility_breakout_weights,
)


def policy() -> VolatilityBreakoutPolicy:
    return VolatilityBreakoutPolicy(
        research_start=datetime(
            2021,
            1,
            1,
            tzinfo=UTC,
        ),
        research_end_exclusive=datetime(
            2021,
            4,
            1,
            tzinfo=UTC,
        ),
        ranking_maximum=8,
        maximum_positions=2,
        breakout_lookback_days=5,
        turnover_expansion_minimum=1.5,
        atr_expansion_minimum=1.2,
        atr_days=3,
        initial_stop_atr=2.5,
        trailing_stop_atr=3.5,
        maximum_holding_days=10,
        transaction_cost_fraction=0.002,
    )


def history(
    symbol: str,
    *,
    breakout_index: int = 15,
    periods: int = 30,
) -> pd.DataFrame:
    open_time = pd.date_range(
        "2020-12-20",
        periods=periods,
        freq="1D",
        tz="UTC",
    )

    frame = pd.DataFrame(
        {
            "symbol": symbol,
            "open_time": open_time,
            "close_time": (
                open_time
                + pd.Timedelta(days=1)
            ),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "quote_turnover": 100_000.0,
        }
    )

    frame.loc[
        breakout_index,
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        101.0,
        125.0,
        100.0,
        122.0,
    ]

    frame.loc[
        breakout_index,
        "quote_turnover",
    ] = 300_000.0

    frame.loc[
        breakout_index + 1 :,
        [
            "open",
            "high",
            "low",
            "close",
        ],
    ] = [
        122.0,
        124.0,
        120.0,
        123.0,
    ]

    return frame


def ranking(
    frame: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "snapshot_time": (
                frame["close_time"]
            ),
            "symbol": symbol,
            "composite_score": 0.9,
            "rank_within_snapshot": 1,
        }
    )


def test_breakout_uses_only_prior_high() -> None:
    frame = history(
        "BTC/USDT"
    )

    signals = (
        build_volatility_breakout_signals(
            frame,
            ranking(
                frame,
                "BTC/USDT",
            ),
            policy=policy(),
        )
    )

    candidate = signals.loc[
        signals["candidate"]
    ].iloc[0]

    assert (
        candidate[
            "prior_breakout_high"
        ]
        == pytest.approx(101.0)
    )

    assert (
        candidate["signal_close"]
        == pytest.approx(122.0)
    )


def test_future_bar_does_not_change_earlier_signals() -> None:
    frame = history(
        "BTC/USDT"
    )

    ranks = ranking(
        frame,
        "BTC/USDT",
    )

    original = (
        build_volatility_breakout_signals(
            frame,
            ranks,
            policy=policy(),
        )
    )

    future = frame.tail(1).copy()

    future["open_time"] = (
        pd.Timestamp(
            "2022-01-01",
            tz="UTC",
        )
    )

    future["close_time"] = (
        pd.Timestamp(
            "2022-01-02",
            tz="UTC",
        )
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
        build_volatility_breakout_signals(
            pd.concat(
                [
                    frame,
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


def test_weights_respect_spot_limits() -> None:
    btc = history(
        "BTC/USDT"
    )

    alt = history(
        "ALT/USDT",
        breakout_index=16,
    )

    all_history = pd.concat(
        [
            btc,
            alt,
        ],
        ignore_index=True,
    )

    ranks = pd.concat(
        [
            ranking(
                btc,
                "BTC/USDT",
            ),
            ranking(
                alt,
                "ALT/USDT",
            ),
        ],
        ignore_index=True,
    )

    signals = (
        build_volatility_breakout_signals(
            all_history,
            ranks,
            policy=policy(),
        )
    )

    weights, _ = (
        build_volatility_breakout_weights(
            all_history,
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

    counts = (
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
            counts
            <= 2
        ).all()
    )


def test_later_daily_stop_closes_position() -> None:
    frame = history(
        "BTC/USDT"
    )

    ranks = ranking(
        frame,
        "BTC/USDT",
    )

    signals = (
        build_volatility_breakout_signals(
            frame,
            ranks,
            policy=policy(),
        )
    )

    entry_time = signals.loc[
        signals["candidate"],
        "snapshot_time",
    ].iloc[0]

    stop_bar_index = frame.index[
        frame["close_time"]
        == (
            entry_time
            + pd.Timedelta(days=1)
        )
    ][0]

    frame.loc[
        stop_bar_index,
        "low",
    ] = 50.0

    signals = (
        build_volatility_breakout_signals(
            frame,
            ranks,
            policy=policy(),
        )
    )

    _, trades = (
        build_volatility_breakout_weights(
            frame,
            signals,
            policy=policy(),
        )
    )

    assert (
        "DAILY_STOP_TRIGGER"
        in set(
            trades["exit_reason"]
        )
    )


def test_naive_policy_timestamp_is_rejected() -> None:
    with pytest.raises(
        VolatilityBreakoutConfigurationError,
        match="timezone-aware",
    ):
        VolatilityBreakoutPolicy(
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