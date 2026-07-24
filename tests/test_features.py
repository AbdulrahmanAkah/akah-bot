from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from spotbot.research.features import (
    FEATURE_NAMES,
    FeatureConfigurationError,
    TimeframeFeatureSpec,
    add_causal_features,
    average_true_range,
    build_research_feature_frame,
    relative_strength_index,
)

START = datetime(
    2026,
    1,
    1,
    tzinfo=UTC,
)


def frame(
    *,
    timeframe_hours: int,
    periods: int,
) -> pd.DataFrame:
    closes = [
        100.0 + index
        for index in range(periods)
    ]

    return pd.DataFrame(
        {
            "timestamp": [
                START
                + timedelta(
                    hours=timeframe_hours
                    * (index + 1)
                )
                for index in range(periods)
            ],
            "open": closes,
            "high": [
                value + 2.0
                for value in closes
            ],
            "low": [
                value - 2.0
                for value in closes
            ],
            "close": [
                value + 1.0
                for value in closes
            ],
            "volume": [
                1_000.0 + index
                for index in range(periods)
            ],
        }
    )


def small_specs(
) -> dict[str, TimeframeFeatureSpec]:
    return {
        "1h": TimeframeFeatureSpec(
            fast_ema=2,
            slow_ema=3,
            atr_period=2,
            rsi_period=2,
            range_period=2,
            volume_period=2,
        ),
        "4h": TimeframeFeatureSpec(
            fast_ema=2,
            slow_ema=3,
            atr_period=2,
            rsi_period=2,
            range_period=2,
            volume_period=2,
        ),
        "1d": TimeframeFeatureSpec(
            fast_ema=1,
            slow_ema=2,
            atr_period=2,
            rsi_period=2,
            range_period=1,
            volume_period=2,
        ),
    }


def source_frames(
    *,
    hours: int = 96,
) -> dict[str, pd.DataFrame]:
    return {
        "1h": frame(
            timeframe_hours=1,
            periods=hours,
        ),
        "4h": frame(
            timeframe_hours=4,
            periods=hours // 4,
        ),
        "1d": frame(
            timeframe_hours=24,
            periods=hours // 24,
        ),
    }


def test_constant_range_atr() -> None:
    source = pd.DataFrame(
        {
            "high": [101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0],
            "close": [100.0, 100.0, 100.0],
        }
    )

    atr = average_true_range(
        source,
        period=2,
    )

    assert atr.iloc[1] == pytest.approx(2.0)
    assert atr.iloc[2] == pytest.approx(2.0)


def test_rsi_of_persistent_uptrend_reaches_100() -> None:
    values = pd.Series(
        [100.0, 101.0, 102.0, 103.0]
    )

    rsi = relative_strength_index(
        values,
        period=2,
    )

    assert rsi.iloc[-1] == pytest.approx(100.0)


def test_invalid_feature_spec_is_rejected() -> None:
    with pytest.raises(
        FeatureConfigurationError,
        match="smaller",
    ):
        TimeframeFeatureSpec(
            fast_ema=20,
            slow_ema=20,
        )


def test_feature_frame_contains_all_features() -> None:
    result = build_research_feature_frame(
        frames=source_frames(),
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
        specs=small_specs(),
    )

    expected_columns = {
        f"{timeframe}_{feature}"
        for timeframe in ("1h", "4h", "1d")
        for feature in FEATURE_NAMES
    }

    assert expected_columns.issubset(
        result.columns
    )
    assert not bool(
        result[
            list(expected_columns)
        ].isna().any().any()
    )


def test_context_features_match_selected_candle() -> None:
    frames = source_frames()

    daily_features = add_causal_features(
        frames["1d"],
        symbol="BTC/USDT",
        timeframe="1d",
        spec=small_specs()["1d"],
    )

    result = build_research_feature_frame(
        frames=frames,
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
        specs=small_specs(),
    )

    selected = result.loc[
        result["timestamp"]
        == pd.Timestamp(
            START + timedelta(hours=73)
        )
    ].iloc[0]

    expected_daily = daily_features.loc[
        daily_features["timestamp"]
        == pd.Timestamp(
            START + timedelta(hours=72)
        )
    ].iloc[0]

    assert selected["1d_timestamp"] == pd.Timestamp(
        START + timedelta(hours=72)
    )
    assert selected["1d_ema_slow"] == pytest.approx(
        expected_daily["ema_slow"]
    )


def test_appending_future_data_does_not_change_past_features() -> None:
    original_frames = source_frames(
        hours=96
    )
    expanded_frames = source_frames(
        hours=120
    )

    original = build_research_feature_frame(
        frames=original_frames,
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
        specs=small_specs(),
    )

    expanded = build_research_feature_frame(
        frames=expanded_frames,
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
        specs=small_specs(),
    )

    cutoff = original["timestamp"].iloc[-1]

    expanded_past = expanded.loc[
        expanded["timestamp"] <= cutoff
    ].reset_index(drop=True)

    feature_columns = [
        column
        for column in original.columns
        if column.endswith(FEATURE_NAMES)
    ]

    pd.testing.assert_frame_equal(
        original[
            ["timestamp", *feature_columns]
        ].reset_index(drop=True),
        expanded_past[
            ["timestamp", *feature_columns]
        ].reset_index(drop=True),
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def test_missing_timeframe_spec_is_rejected() -> None:
    specs = small_specs()
    del specs["1d"]

    with pytest.raises(
        FeatureConfigurationError,
        match="missing",
    ):
        build_research_feature_frame(
            frames=source_frames(),
            symbol="BTC/USDT",
            signal_timeframe="1h",
            context_timeframes=("4h", "1d"),
            specs=specs,
        )