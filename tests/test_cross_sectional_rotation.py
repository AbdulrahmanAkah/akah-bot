from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.cross_sectional_rotation import (
    CrossSectionalRotationConfigurationError,
    CrossSectionalRotationPolicy,
    build_cross_sectional_rotation_signals,
    build_cross_sectional_rotation_weights,
)


def policy() -> CrossSectionalRotationPolicy:
    return CrossSectionalRotationPolicy(
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
        ranking_return_days=14,
        ranking_relative_strength_days=30,
        ranking_turnover_days=7,
        minimum_liquidity_rank_percentile=0.5,
        minimum_rank_improvement=3,
        maximum_positions=2,
        rebalance_frequency="EVERY_3_DAYS",
        transaction_cost_fraction=0.002,
    )


def symbol_history(
    symbol: str,
    *,
    closes: list[float],
    quote_turnover: float,
) -> pd.DataFrame:
    open_time = pd.date_range(
        "2021-01-01",
        periods=len(closes),
        freq="1D",
        tz="UTC",
    )

    close = pd.Series(
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
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "quote_turnover": (
                quote_turnover
            ),
        }
    )


def trend(
    *,
    start: float,
    end: float,
    periods: int,
) -> list[float]:
    return (
        pd.Series(
            range(periods),
            dtype=float,
        )
        .map(
            lambda index: (
                start
                + (
                    end - start
                )
                * index
                / (
                    periods - 1
                )
            )
        )
        .tolist()
    )


def test_frames(
    *,
    low_liquidity_leader: bool = False,
) -> list[pd.DataFrame]:
    periods = 70

    leader = [
        100.0
        for _ in range(50)
    ] + [
        160.0
        for _ in range(
            periods - 50
        )
    ]

    return [
        symbol_history(
            "ALT/USDT",
            closes=leader,
            quote_turnover=(
                10.0
                if low_liquidity_leader
                else 200.0
            ),
        ),
        symbol_history(
            "BETA/USDT",
            closes=trend(
                start=100.0,
                end=145.0,
                periods=periods,
            ),
            quote_turnover=400.0,
        ),
        symbol_history(
            "GAMMA/USDT",
            closes=trend(
                start=100.0,
                end=130.0,
                periods=periods,
            ),
            quote_turnover=300.0,
        ),
        symbol_history(
            "DELTA/USDT",
            closes=trend(
                start=100.0,
                end=115.0,
                periods=periods,
            ),
            quote_turnover=100.0,
        ),
    ]


def ranking(
    frames: list[pd.DataFrame],
) -> pd.DataFrame:
    rows: list[
        dict[str, object]
    ] = []

    for static_rank, frame in enumerate(
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
                        - static_rank / 100.0
                    ),
                    "rank_within_snapshot": (
                        static_rank
                    ),
                }
            )

    return pd.DataFrame(rows)


def history_and_ranking(
    *,
    low_liquidity_leader: bool = False,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    frames = test_frames(
        low_liquidity_leader=(
            low_liquidity_leader
        )
    )

    return (
        pd.concat(
            frames,
            ignore_index=True,
        ),
        ranking(frames),
    )


def test_rank_improvement_candidate_is_detected() -> None:
    history, ranks = history_and_ranking()

    signals = (
        build_cross_sectional_rotation_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    candidates = signals.loc[
        signals["candidate"]
    ]

    assert not candidates.empty
    assert (
        "ALT/USDT"
        in set(
            candidates["symbol"]
        )
    )

    alt_candidates = candidates.loc[
        candidates["symbol"]
        == "ALT/USDT"
    ]

    assert bool(
        (
            alt_candidates[
                "rank_improvement_h04"
            ]
            >= 3.0
        ).all()
    )

    assert bool(
        alt_candidates[
            "rebalance_day"
        ].all()
    )


def test_liquidity_filter_rejects_leader() -> None:
    history, ranks = history_and_ranking(
        low_liquidity_leader=True
    )

    signals = (
        build_cross_sectional_rotation_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    alt_candidates = signals.loc[
        (
            signals["symbol"]
            == "ALT/USDT"
        )
        & signals["candidate"]
    ]

    assert alt_candidates.empty


def test_future_bar_cannot_change_earlier_signals() -> None:
    history, ranks = history_and_ranking()

    original = (
        build_cross_sectional_rotation_signals(
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
            "quote_turnover",
        ]
    ] = [
        1_000_000.0,
        1_100_000.0,
        900_000.0,
        1_000_000.0,
        1_000_000_000.0,
    ]

    extended = (
        build_cross_sectional_rotation_signals(
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


def test_weights_respect_rotation_and_spot_limits() -> None:
    history, ranks = history_and_ranking()

    signals = (
        build_cross_sectional_rotation_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    weights, trades = (
        build_cross_sectional_rotation_weights(
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

    rebalance_snapshots = (
        weights.loc[
            weights["rebalance_day"],
            "snapshot_time",
        ]
        .drop_duplicates()
        .sort_values()
    )

    differences = (
        rebalance_snapshots
        .diff()
        .dropna()
    )

    assert bool(
        (
            differences
            == pd.Timedelta(days=3)
        ).all()
    )

    assert not trades.empty


def test_base_volume_can_supply_turnover() -> None:
    history, ranks = history_and_ranking()

    history["base_volume"] = (
        history["quote_turnover"]
        / history["close"]
    )

    history = history.drop(
        columns=["quote_turnover"]
    )

    signals = (
        build_cross_sectional_rotation_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    assert not signals.empty


def test_naive_policy_timestamp_is_rejected() -> None:
    with pytest.raises(
        CrossSectionalRotationConfigurationError,
        match="timezone-aware",
    ):
        CrossSectionalRotationPolicy(
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