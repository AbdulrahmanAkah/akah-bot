from datetime import UTC

import pandas as pd
import pytest

from spotbot.research.trend_pullback_v2 import (
    EntryFilterConfig,
    EntryFilterConfigurationError,
    apply_entry_filter,
)


def source_frame(
    *,
    periods: int = 4,
) -> pd.DataFrame:
    timestamps = pd.date_range(
        "2023-01-01 01:00:00",
        periods=periods,
        freq="1h",
        tz=UTC,
    )

    close = [
        101.0 + index
        for index in range(periods)
    ]

    extension_values = [
        0.5,
        0.5,
        0.4,
        0.6,
        0.7,
        0.8,
    ][:periods]

    rsi_values = [
        55.0,
        60.0,
        56.0,
        61.0,
        58.0,
        59.0,
    ][:periods]

    stop_values = [
        1.5,
        1.8,
        1.4,
        1.6,
        1.7,
        1.9,
    ][:periods]

    raw_signals = [
        True,
        False,
        True,
        True,
        False,
        True,
    ][:periods]

    atr = [2.0] * periods

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "close": close,
            "volume": [
                1_000.0
            ]
            * periods,
            "raw_entry_signal": (
                raw_signals
            ),
            "1h_ema_fast": [
                close_value
                - extension
                * atr_value
                for (
                    close_value,
                    extension,
                    atr_value,
                ) in zip(
                    close,
                    extension_values,
                    atr,
                    strict=True,
                )
            ],
            "1h_atr": atr,
            "1h_rsi": rsi_values,
            "1h_volume_median": [
                900.0
            ]
            * periods,
            "stop_distance_atr": (
                stop_values
            ),
        }
    )


def test_invalid_filter_bounds_are_rejected() -> None:
    with pytest.raises(
        EntryFilterConfigurationError,
        match="greater",
    ):
        EntryFilterConfig(
            minimum_rsi=60.0,
            maximum_rsi=55.0,
        )


def test_filter_never_creates_new_signal() -> None:
    source = source_frame()

    result = apply_entry_filter(
        source,
        config=EntryFilterConfig(
            minimum_rsi=55.0,
        ),
    )

    created_signal = (
        result["v2_entry_signal"]
        & ~result["v1_raw_entry_signal"]
    )

    assert not bool(
        created_signal.any()
    )


def test_filter_thresholds_are_inclusive() -> None:
    result = apply_entry_filter(
        source_frame(),
        config=EntryFilterConfig(
            minimum_rsi=55.0,
            minimum_stop_distance_atr=1.5,
            minimum_entry_extension_atr=0.5,
        ),
    )

    assert bool(
        result.iloc[0]["v2_entry_signal"]
    )
    assert not bool(
        result.iloc[2]["v2_entry_signal"]
    )
    assert bool(
        result.iloc[3]["v2_entry_signal"]
    )


def test_original_signal_is_preserved_for_audit() -> None:
    source = source_frame()

    result = apply_entry_filter(
        source,
        config=EntryFilterConfig(
            minimum_rsi=60.0,
        ),
    )

    pd.testing.assert_series_equal(
        result["v1_raw_entry_signal"],
        source["raw_entry_signal"],
        check_names=False,
    )


def test_future_rows_do_not_change_past_filter() -> None:
    original = source_frame(
        periods=4
    )
    expanded = source_frame(
        periods=6
    )

    config = EntryFilterConfig(
        minimum_rsi=55.0,
        minimum_stop_distance_atr=1.5,
        minimum_entry_extension_atr=0.5,
    )

    original_result = apply_entry_filter(
        original,
        config=config,
    )

    expanded_result = apply_entry_filter(
        expanded,
        config=config,
    )

    cutoff = original_result[
        "timestamp"
    ].iloc[-1]

    expanded_past = expanded_result.loc[
        expanded_result["timestamp"]
        <= cutoff
    ].reset_index(drop=True)

    columns = [
        "timestamp",
        "v1_raw_entry_signal",
        "entry_extension_atr",
        "volume_ratio",
        "entry_filter_ok",
        "v2_entry_signal",
        "raw_entry_signal",
    ]

    pd.testing.assert_frame_equal(
        original_result[
            columns
        ].reset_index(drop=True),
        expanded_past[columns],
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )