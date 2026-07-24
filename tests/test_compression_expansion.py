from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.compression_expansion import (
    CompressionExpansionConfigurationError,
    CompressionExpansionPolicy,
    build_compression_expansion_signals,
    build_compression_expansion_weights,
)


def policy() -> CompressionExpansionPolicy:
    return CompressionExpansionPolicy(
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
        breakout_lookback_days=20,
        compression_lookback_days=60,
        compression_percentile_maximum=0.2,
        ranking_maximum=10,
        maximum_positions=2,
        minimum_turnover_expansion=1.5,
        initial_stop_atr=2.5,
        trailing_stop_atr=4.0,
        maximum_holding_days=30,
        transaction_cost_fraction=0.002,
    )


def symbol_history(
    symbol: str,
    *,
    compressed: bool,
    turnover_expansion: bool = True,
    periods: int = 130,
) -> pd.DataFrame:
    open_time = pd.date_range(
        "2021-01-01",
        periods=periods,
        freq="1D",
        tz="UTC",
    )

    close = pd.Series(
        100.0,
        index=range(periods),
        dtype=float,
    )

    range_fraction = pd.Series(
        0.05,
        index=range(periods),
        dtype=float,
    )

    if compressed:
        for index in range(
            70,
            120,
        ):
            range_fraction.iloc[index] = (
                0.05
                - (
                    0.045
                    * (
                        index - 70
                    )
                    / 49.0
                )
            )
    else:
        range_fraction[:] = 0.02

    candidate_index = 120

    close.iloc[candidate_index] = 110.0

    high = (
        close
        * (
            1.0
            + range_fraction
        )
    )

    low = (
        close
        * (
            1.0
            - range_fraction
        )
    )

    high.iloc[candidate_index] = 111.0
    low.iloc[candidate_index] = 99.0

    quote_turnover = pd.Series(
        100.0,
        index=range(periods),
        dtype=float,
    )

    quote_turnover.iloc[
        candidate_index
    ] = (
        160.0
        if turnover_expansion
        else 120.0
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
            "high": high,
            "low": low,
            "close": close,
            "quote_turnover": (
                quote_turnover
            ),
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


def history_and_ranking(
    *,
    compressed: bool = True,
    turnover_expansion: bool = True,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    alt = symbol_history(
        "ALT/USDT",
        compressed=compressed,
        turnover_expansion=(
            turnover_expansion
        ),
    )

    btc = symbol_history(
        "BTC/USDT",
        compressed=False,
        turnover_expansion=False,
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


def test_compression_breakout_candidate_is_detected() -> None:
    history, ranks = history_and_ranking()

    signals = (
        build_compression_expansion_signals(
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
        candidate["compression_pass"]
    )

    assert bool(
        candidate["breakout_pass"]
    )

    assert bool(
        candidate["turnover_pass"]
    )

    assert (
        candidate[
            "compression_percentile_h05"
        ]
        <= 0.2
    )


def test_noncompressed_breakout_is_rejected() -> None:
    history, ranks = history_and_ranking(
        compressed=False
    )

    signals = (
        build_compression_expansion_signals(
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


def test_insufficient_turnover_expansion_is_rejected() -> None:
    history, ranks = history_and_ranking(
        turnover_expansion=False
    )

    signals = (
        build_compression_expansion_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    assert not bool(
        signals["candidate"].any()
    )


def test_current_breakout_range_does_not_define_compression() -> None:
    history, ranks = history_and_ranking()

    original = (
        build_compression_expansion_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    candidate_time = (
        original.loc[
            original["candidate"],
            "snapshot_time",
        ]
        .iloc[0]
    )

    mask = (
        (
            history["symbol"]
            == "ALT/USDT"
        )
        & (
            history["close_time"]
            == candidate_time
        )
    )

    history.loc[
        mask,
        "high",
    ] = 200.0

    history.loc[
        mask,
        "low",
    ] = 1.0

    changed = (
        build_compression_expansion_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    original_value = (
        original.loc[
            (
                original["symbol"]
                == "ALT/USDT"
            )
            & (
                original["snapshot_time"]
                == candidate_time
            ),
            "compression_percentile_h05",
        ]
        .iloc[0]
    )

    changed_value = (
        changed.loc[
            (
                changed["symbol"]
                == "ALT/USDT"
            )
            & (
                changed["snapshot_time"]
                == candidate_time
            ),
            "compression_percentile_h05",
        ]
        .iloc[0]
    )

    assert changed_value == original_value


def test_future_bar_cannot_change_earlier_signals() -> None:
    history, ranks = history_and_ranking()

    original = (
        build_compression_expansion_signals(
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
        1.0,
        500_000.0,
        1_000_000_000.0,
    ]

    extended = (
        build_compression_expansion_signals(
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
            compressed=True,
        )
        for index in range(1, 4)
    ]

    history = pd.concat(
        frames,
        ignore_index=True,
    )

    ranks = ranking(
        frames
    )

    signals = (
        build_compression_expansion_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    weights, _ = (
        build_compression_expansion_weights(
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


def test_daily_stop_closes_position() -> None:
    history, ranks = history_and_ranking()

    original_signals = (
        build_compression_expansion_signals(
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
        build_compression_expansion_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    _, trades = (
        build_compression_expansion_weights(
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
        build_compression_expansion_signals(
            history,
            ranks,
            policy=policy(),
        )
    )

    assert not signals.empty


def test_naive_policy_timestamp_is_rejected() -> None:
    with pytest.raises(
        CompressionExpansionConfigurationError,
        match="timezone-aware",
    ):
        CompressionExpansionPolicy(
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