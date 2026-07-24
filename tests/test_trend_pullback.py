from datetime import UTC

import pandas as pd
import pytest

from spotbot.research.trend_pullback import (
    TrendPullbackConfig,
    TrendPullbackConfigurationError,
    TrendPullbackDataError,
    default_trend_pullback_config,
    generate_trend_pullback_setups,
)


def source_frame(
    *,
    periods: int = 4,
) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2023-01-01",
        periods=periods,
        freq="1h",
        tz=UTC,
    )

    high = [
        100.5 + index
        for index in range(periods)
    ]
    low = [
        98.5 + index
        for index in range(periods)
    ]
    close = [
        100.0 + index
        for index in range(periods)
    ]

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [
                value - 0.5
                for value in close
            ],
            "high": high,
            "low": low,
            "close": close,
            "volume": [1_000.0] * periods,
            "1h_ema_fast": [
                value - 0.8
                for value in close
            ],
            "1h_ema_slow": [
                value - 2.0
                for value in close
            ],
            "1h_atr": [2.0] * periods,
            "1h_rsi": [55.0] * periods,
            "1h_volume_median": [
                900.0
            ]
            * periods,
            "4h_close": [120.0] * periods,
            "4h_ema_fast": [115.0] * periods,
            "4h_ema_slow": [110.0] * periods,
            "1d_close": [130.0] * periods,
            "1d_ema_fast": [120.0] * periods,
            "1d_ema_slow": [110.0] * periods,
        }
    )


def test_invalid_rsi_limits_are_rejected() -> None:
    with pytest.raises(
        TrendPullbackConfigurationError,
        match="RSI",
    ):
        TrendPullbackConfig(
            rsi_minimum=70.0,
            rsi_maximum=60.0,
        )


def test_bullish_pullback_produces_signal() -> None:
    frame = source_frame()

    result = generate_trend_pullback_setups(
        frame,
        config=default_trend_pullback_config(),
    )

    assert not bool(
        result.iloc[0]["raw_entry_signal"]
    )
    assert bool(
        result.iloc[1]["raw_entry_signal"]
    )


def test_failed_daily_regime_blocks_signal() -> None:
    frame = source_frame()
    frame["1d_close"] = 100.0
    frame["1d_ema_fast"] = 110.0
    frame["1d_ema_slow"] = 120.0

    result = generate_trend_pullback_setups(
        frame,
        config=default_trend_pullback_config(),
    )

    assert not bool(
        result["raw_entry_signal"].any()
    )


def test_signal_stop_is_below_close() -> None:
    result = generate_trend_pullback_setups(
        source_frame(),
        config=default_trend_pullback_config(),
    )

    signals = result.loc[
        result["raw_entry_signal"]
    ]

    assert not signals.empty
    assert bool(
        (
            signals["stop_price"]
            < signals["close"]
        ).all()
    )
    assert bool(
        (
            signals["stop_distance"]
            > 0.0
        ).all()
    )


def test_future_rows_do_not_change_past_signals() -> None:
    original = source_frame(
        periods=4
    )
    expanded = source_frame(
        periods=8
    )

    original_result = (
        generate_trend_pullback_setups(
            original,
            config=(
                default_trend_pullback_config()
            ),
        )
    )

    expanded_result = (
        generate_trend_pullback_setups(
            expanded,
            config=(
                default_trend_pullback_config()
            ),
        )
    )

    cutoff = original_result[
        "timestamp"
    ].iloc[-1]

    expanded_past = expanded_result.loc[
        expanded_result["timestamp"]
        <= cutoff
    ].reset_index(drop=True)

    comparison_columns = [
        "timestamp",
        "raw_entry_signal",
        "stop_price",
        "stop_distance",
        "stop_distance_atr",
    ]

    pd.testing.assert_frame_equal(
        original_result[
            comparison_columns
        ].reset_index(drop=True),
        expanded_past[
            comparison_columns
        ],
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_missing_required_column_is_rejected() -> None:
    frame = source_frame().drop(
        columns=["4h_ema_slow"]
    )

    with pytest.raises(
        TrendPullbackDataError,
        match="missing",
    ):
        generate_trend_pullback_setups(
            frame,
            config=(
                default_trend_pullback_config()
            ),
        )