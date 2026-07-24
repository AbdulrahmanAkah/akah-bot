from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from spotbot.data.multitimeframe import (
    build_aligned_frame,
    context_column,
)
from spotbot.data.validator import (
    REQUIRED_COLUMNS,
    validate_candles,
)

FEATURE_NAMES = (
    "ema_fast",
    "ema_slow",
    "atr",
    "rsi",
    "prior_high",
    "prior_low",
    "volume_median",
)


class FeatureEngineeringError(RuntimeError):
    pass


class FeatureConfigurationError(
    FeatureEngineeringError
):
    pass


class FeatureDataError(FeatureEngineeringError):
    pass


@dataclass(frozen=True, slots=True)
class TimeframeFeatureSpec:
    fast_ema: int
    slow_ema: int
    atr_period: int = 14
    rsi_period: int = 14
    range_period: int = 20
    volume_period: int = 20

    def __post_init__(self) -> None:
        periods = {
            "fast_ema": self.fast_ema,
            "slow_ema": self.slow_ema,
            "atr_period": self.atr_period,
            "rsi_period": self.rsi_period,
            "range_period": self.range_period,
            "volume_period": self.volume_period,
        }

        for name, value in periods.items():
            if value < 1:
                raise FeatureConfigurationError(
                    f"{name} must be at least 1."
                )

        if self.fast_ema >= self.slow_ema:
            raise FeatureConfigurationError(
                "fast_ema must be smaller than "
                "slow_ema."
            )


def default_research_feature_specs(
) -> dict[str, TimeframeFeatureSpec]:
    return {
        "1h": TimeframeFeatureSpec(
            fast_ema=20,
            slow_ema=50,
        ),
        "4h": TimeframeFeatureSpec(
            fast_ema=20,
            slow_ema=50,
        ),
        "1d": TimeframeFeatureSpec(
            fast_ema=50,
            slow_ema=200,
        ),
    }


def feature_column(
    timeframe: str,
    feature_name: str,
) -> str:
    return f"{timeframe}_{feature_name}"


def exponential_moving_average(
    values: pd.Series,
    *,
    period: int,
) -> pd.Series:
    if period < 1:
        raise FeatureConfigurationError(
            "EMA period must be at least 1."
        )

    numeric = pd.to_numeric(
        values,
        errors="coerce",
    ).astype("float64")

    return numeric.ewm(
        span=period,
        adjust=False,
        min_periods=period,
    ).mean()


def true_range(frame: pd.DataFrame) -> pd.Series:
    high = pd.to_numeric(
        frame["high"],
        errors="coerce",
    ).astype("float64")

    low = pd.to_numeric(
        frame["low"],
        errors="coerce",
    ).astype("float64")

    close = pd.to_numeric(
        frame["close"],
        errors="coerce",
    ).astype("float64")

    previous_close = close.shift(1)

    components = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    )

    result = components.max(axis=1)

    if not isinstance(result, pd.Series):
        raise FeatureDataError(
            "True-range calculation did not "
            "produce a Series."
        )

    return result.astype("float64")


def average_true_range(
    frame: pd.DataFrame,
    *,
    period: int,
) -> pd.Series:
    if period < 1:
        raise FeatureConfigurationError(
            "ATR period must be at least 1."
        )

    return true_range(frame).ewm(
        alpha=1.0 / period,
        adjust=False,
        min_periods=period,
    ).mean()


def relative_strength_index(
    values: pd.Series,
    *,
    period: int,
) -> pd.Series:
    if period < 1:
        raise FeatureConfigurationError(
            "RSI period must be at least 1."
        )

    close = pd.to_numeric(
        values,
        errors="coerce",
    ).astype("float64")

    change = close.diff()
    gains = change.clip(lower=0.0)
    losses = (-change).clip(lower=0.0)

    average_gain = gains.ewm(
        alpha=1.0 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    average_loss = losses.ewm(
        alpha=1.0 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    total_movement = (
        average_gain + average_loss
    )

    rsi = (
        100.0
        * average_gain
        / total_movement
    )

    no_movement = (
        (average_gain == 0.0)
        & (average_loss == 0.0)
    )
    no_losses = (
        (average_gain > 0.0)
        & (average_loss == 0.0)
    )

    rsi = rsi.mask(
        no_movement,
        50.0,
    )
    rsi = rsi.mask(
        no_losses,
        100.0,
    )

    return rsi.astype("float64")


def add_causal_features(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    spec: TimeframeFeatureSpec,
) -> pd.DataFrame:
    missing_columns = set(
        REQUIRED_COLUMNS
    ).difference(frame.columns)

    if missing_columns:
        raise FeatureDataError(
            f"{timeframe}: missing columns "
            f"{sorted(missing_columns)}."
        )

    result = frame.loc[
        :,
        list(REQUIRED_COLUMNS),
    ].copy()

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
        errors="coerce",
    )

    for column in REQUIRED_COLUMNS[1:]:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result = result.sort_values(
        by="timestamp",
        kind="stable",
    ).reset_index(drop=True)

    report = validate_candles(
        result,
        symbol=symbol,
        expected_frequency=timeframe,
    )

    if not report.is_valid:
        raise FeatureDataError(
            f"{timeframe}: invalid source candles: "
            f"rows={report.rows}, "
            f"duplicates={report.duplicate_timestamps}, "
            f"missing={report.missing_intervals}, "
            f"invalid={report.invalid_rows}."
        )

    result["ema_fast"] = (
        exponential_moving_average(
            result["close"],
            period=spec.fast_ema,
        )
    )
    result["ema_slow"] = (
        exponential_moving_average(
            result["close"],
            period=spec.slow_ema,
        )
    )
    result["atr"] = average_true_range(
        result,
        period=spec.atr_period,
    )
    result["rsi"] = relative_strength_index(
        result["close"],
        period=spec.rsi_period,
    )

    result["prior_high"] = (
        result["high"]
        .shift(1)
        .rolling(
            window=spec.range_period,
            min_periods=spec.range_period,
        )
        .max()
    )

    result["prior_low"] = (
        result["low"]
        .shift(1)
        .rolling(
            window=spec.range_period,
            min_periods=spec.range_period,
        )
        .min()
    )

    result["volume_median"] = (
        result["volume"]
        .rolling(
            window=spec.volume_period,
            min_periods=spec.volume_period,
        )
        .median()
    )

    return result


def _require_specs(
    *,
    timeframes: Sequence[str],
    specs: Mapping[
        str,
        TimeframeFeatureSpec,
    ],
) -> None:
    missing = [
        timeframe
        for timeframe in timeframes
        if timeframe not in specs
    ]

    if missing:
        raise FeatureConfigurationError(
            "Feature specifications are missing "
            f"for: {missing}."
        )


def build_research_feature_frame(
    *,
    frames: Mapping[str, pd.DataFrame],
    symbol: str,
    signal_timeframe: str,
    context_timeframes: Sequence[str],
    specs: Mapping[
        str,
        TimeframeFeatureSpec,
    ],
) -> pd.DataFrame:
    all_timeframes = (
        signal_timeframe,
        *tuple(context_timeframes),
    )

    _require_specs(
        timeframes=all_timeframes,
        specs=specs,
    )

    aligned = build_aligned_frame(
        frames=frames,
        symbol=symbol,
        signal_timeframe=signal_timeframe,
        context_timeframes=context_timeframes,
    )

    signal_source = frames.get(
        signal_timeframe
    )

    if signal_source is None:
        raise FeatureDataError(
            f"Missing signal frame: "
            f"{signal_timeframe}."
        )

    signal_features = add_causal_features(
        signal_source,
        symbol=symbol,
        timeframe=signal_timeframe,
        spec=specs[signal_timeframe],
    )

    signal_rename = {
        name: feature_column(
            signal_timeframe,
            name,
        )
        for name in FEATURE_NAMES
    }

    signal_feature_columns = [
        signal_rename[name]
        for name in FEATURE_NAMES
    ]

    signal_slice = signal_features.loc[
        :,
        [
            "timestamp",
            *FEATURE_NAMES,
        ],
    ].rename(
        columns=signal_rename
    )

    aligned = aligned.merge(
        signal_slice,
        on="timestamp",
        how="left",
        validate="one_to_one",
    )

    required_feature_columns = list(
        signal_feature_columns
    )

    for timeframe in context_timeframes:
        context_source = frames.get(timeframe)

        if context_source is None:
            raise FeatureDataError(
                f"Missing context frame: "
                f"{timeframe}."
            )

        context_features = add_causal_features(
            context_source,
            symbol=symbol,
            timeframe=timeframe,
            spec=specs[timeframe],
        )

        context_timestamp = context_column(
            timeframe,
            "timestamp",
        )

        context_rename = {
            "timestamp": context_timestamp,
            **{
                name: feature_column(
                    timeframe,
                    name,
                )
                for name in FEATURE_NAMES
            },
        }

        context_feature_columns = [
            feature_column(
                timeframe,
                name,
            )
            for name in FEATURE_NAMES
        ]

        context_slice = context_features.loc[
            :,
            [
                "timestamp",
                *FEATURE_NAMES,
            ],
        ].rename(
            columns=context_rename
        )

        aligned = aligned.merge(
            context_slice,
            on=context_timestamp,
            how="left",
            validate="many_to_one",
        )

        required_feature_columns.extend(
            context_feature_columns
        )

    aligned = aligned.dropna(
        subset=required_feature_columns
    ).reset_index(drop=True)

    if aligned.empty:
        raise FeatureDataError(
            "No rows remain after indicator warm-up."
        )

    for column in required_feature_columns:
        aligned[column] = pd.to_numeric(
            aligned[column],
            errors="raise",
        )

    return aligned