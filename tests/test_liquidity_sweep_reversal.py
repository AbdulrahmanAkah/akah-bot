from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.liquidity_sweep_reversal import (
    LiquiditySweepConfigurationError,
    LiquiditySweepReversalPolicy,
    build_liquidity_sweep_signals,
    build_liquidity_sweep_weights,
)


def policy() -> LiquiditySweepReversalPolicy:
    return LiquiditySweepReversalPolicy(
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
        sweep_lookback_days=20,
        ranking_maximum=15,
        maximum_positions=3,
        recovery_close_fraction=0.65,
        minimum_turnover_expansion=1.25,
        initial_stop_atr=2.0,
        profit_trail_atr=2.5,
        maximum_holding_days=14,
        transaction_cost_fraction=0.002,
    )


def symbol_history(
    symbol: str,
    *,
    candidate_shape: bool,
    periods: int = 50,
) -> pd.DataFrame:
    open_time = pd.date_range(
        "2021-01-01",
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
            "turnover": 100.0,
        }
    )

    if candidate_shape:
        candidate_index = 25

        frame.loc[
            candidate_index,
            [
                "open",
                "high",
                "low",
                "close",
                "turnover",
            ],
        ] = [
            100.0,
            110.0,
            90.0,
            104.0,
            130.0,
        ]

        frame.loc[
            candidate_index + 1:,
            [
                "open",
                "high",
                "low",
                "close",
            ],
        ] = [
            104.0,
            106.0,
            102.0,
            105.0,
        ]

    return frame


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


def history_and_ranking() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    alt = symbol_history(
        "ALT/USDT",
        candidate_shape=True,
    )

    btc = symbol_history(
        "BTC/USDT",
        candidate_shape=False,
    )

    history = pd.concat(
        [
            alt,
            btc,
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


def test_liquidity_sweep_candidate_is_detected() -> None:
    history, ranks = history_and_ranking()

    signals = (
        build_liquidity_sweep_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    candidates = signals.loc[
        signals["candidate"]
    ]

    assert len(candidates) == 1
    assert (
        candidates.iloc[0]["symbol"]
        == "ALT/USDT"
    )

    candidate = candidates.iloc[0]

    assert bool(
        candidate["sweep_pass"]
    )

    assert bool(
        candidate["level_recovery_pass"]
    )

    assert (
        candidate["recovery_fraction"]
        >= 0.65
    )

    assert (
        candidate["turnover_expansion"]
        >= 1.25
    )


def test_close_below_swept_level_is_rejected() -> None:
    history, ranks = history_and_ranking()

    mask = (
        (
            history["symbol"]
            == "ALT/USDT"
        )
        & (
            history["low"]
            == 90.0
        )
    )

    history.loc[
        mask,
        "close",
    ] = 95.0

    signals = (
        build_liquidity_sweep_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    assert not bool(
        signals["candidate"].any()
    )


def test_future_bar_cannot_change_earlier_signals() -> None:
    history, ranks = history_and_ranking()

    original = (
        build_liquidity_sweep_signals(
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
            "turnover",
        ]
    ] = [
        1_000_000.0,
        1_100_000.0,
        1.0,
        500_000.0,
        1_000_000_000.0,
    ]

    extended = (
        build_liquidity_sweep_signals(
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
    frames = [
        symbol_history(
            f"ALT{index}/USDT",
            candidate_shape=True,
        )
        for index in range(1, 5)
    ]

    history = pd.concat(
        frames,
        ignore_index=True,
    )

    ranks = ranking(
        frames
    )

    signals = (
        build_liquidity_sweep_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    weights, _ = (
        build_liquidity_sweep_weights(
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
            <= 3
        ).all()
    )


def test_daily_stop_closes_position() -> None:
    history, ranks = history_and_ranking()

    original_signals = (
        build_liquidity_sweep_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    candidate_time = (
        original_signals.loc[
            original_signals["candidate"],
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
        build_liquidity_sweep_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    _, trades = (
        build_liquidity_sweep_weights(
            history,
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
        LiquiditySweepConfigurationError,
        match="timezone-aware",
    ):
        LiquiditySweepReversalPolicy(
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


def test_base_volume_is_converted_to_quote_turnover() -> None:
    history, ranks = history_and_ranking()

    history["base_volume"] = (
        history["turnover"]
        / history["close"]
    )

    history = history.drop(
        columns=["turnover"]
    )

    signals = (
        build_liquidity_sweep_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    assert bool(
        signals["candidate"].any()
    )


def test_missing_volume_reports_available_columns() -> None:
    history, ranks = history_and_ranking()

    history = history.drop(
        columns=["turnover"]
    )

    with pytest.raises(
        LiquiditySweepConfigurationError,
        match="Available columns",
    ):
        build_liquidity_sweep_signals(
            history,
            ranks,
            policy=policy(),
        )
