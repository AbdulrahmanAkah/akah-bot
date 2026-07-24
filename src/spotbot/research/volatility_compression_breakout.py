from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

REQUIRED_COMPRESSION_BREAKOUT_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "1h_atr",
    "1h_volume_median",
    "4h_close",
    "4h_ema_fast",
    "4h_ema_slow",
    "1d_close",
    "1d_ema_fast",
    "1d_ema_slow",
)


class VolatilityCompressionBreakoutError(
    RuntimeError
):
    pass


class VolatilityCompressionBreakoutConfigurationError(
    VolatilityCompressionBreakoutError
):
    pass


class VolatilityCompressionBreakoutDataError(
    VolatilityCompressionBreakoutError
):
    pass


@dataclass(frozen=True, slots=True)
class VolatilityCompressionBreakoutConfig:
    compression_window: int = 12
    baseline_window: int = 48
    signal_cooldown_bars: int = 12
    maximum_compression_ratio: float = 0.70
    minimum_volume_ratio: float = 1.20
    breakout_buffer_atr: float = 0.05
    maximum_breakout_extension_atr: float = 1.50
    minimum_close_location: float = 0.60
    stop_buffer_atr: float = 0.25
    require_four_hour_regime: bool = True
    require_daily_regime: bool = False

    def __post_init__(self) -> None:
        positive_integer_parameters = {
            "compression_window": (
                self.compression_window
            ),
            "baseline_window": (
                self.baseline_window
            ),
        }

        for integer_name, integer_value in (
            positive_integer_parameters.items()
        ):
            if integer_value < 1:
                raise (
                    VolatilityCompressionBreakoutConfigurationError(
                        f"{integer_name} must be at least 1."
                    )
                )

        if self.signal_cooldown_bars < 0:
            raise (
                VolatilityCompressionBreakoutConfigurationError(
                    "signal_cooldown_bars cannot be negative."
                )
            )

        if (
            self.baseline_window
            <= self.compression_window
        ):
            raise (
                VolatilityCompressionBreakoutConfigurationError(
                    "baseline_window must exceed "
                    "compression_window."
                )
            )

        numeric_parameters = {
            "maximum_compression_ratio": (
                self.maximum_compression_ratio
            ),
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
            "breakout_buffer_atr": (
                self.breakout_buffer_atr
            ),
            "maximum_breakout_extension_atr": (
                self.maximum_breakout_extension_atr
            ),
            "minimum_close_location": (
                self.minimum_close_location
            ),
            "stop_buffer_atr": (
                self.stop_buffer_atr
            ),
        }

        for numeric_name, numeric_value in (
            numeric_parameters.items()
        ):
            if not isfinite(numeric_value):
                raise (
                    VolatilityCompressionBreakoutConfigurationError(
                        f"{numeric_name} must be finite."
                    )
                )

        if not (
            0.0
            < self.maximum_compression_ratio
            <= 1.0
        ):
            raise (
                VolatilityCompressionBreakoutConfigurationError(
                    "maximum_compression_ratio must "
                    "be within (0, 1]."
                )
            )

        nonnegative_parameters = {
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
            "breakout_buffer_atr": (
                self.breakout_buffer_atr
            ),
            "stop_buffer_atr": (
                self.stop_buffer_atr
            ),
        }

        for numeric_name, numeric_value in (
            nonnegative_parameters.items()
        ):
            if numeric_value < 0.0:
                raise (
                    VolatilityCompressionBreakoutConfigurationError(
                        f"{numeric_name} cannot be negative."
                    )
                )

        if (
            self.maximum_breakout_extension_atr
            <= 0.0
        ):
            raise (
                VolatilityCompressionBreakoutConfigurationError(
                    "maximum_breakout_extension_atr "
                    "must be positive."
                )
            )

        if not (
            0.0
            <= self.minimum_close_location
            <= 1.0
        ):
            raise (
                VolatilityCompressionBreakoutConfigurationError(
                    "minimum_close_location must "
                    "be within [0, 1]."
                )
            )

    def to_dict(
        self,
    ) -> dict[str, int | float | bool]:
        return {
            "compression_window": (
                self.compression_window
            ),
            "baseline_window": (
                self.baseline_window
            ),
            "signal_cooldown_bars": (
                self.signal_cooldown_bars
            ),
            "maximum_compression_ratio": (
                self.maximum_compression_ratio
            ),
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
            "breakout_buffer_atr": (
                self.breakout_buffer_atr
            ),
            "maximum_breakout_extension_atr": (
                self.maximum_breakout_extension_atr
            ),
            "minimum_close_location": (
                self.minimum_close_location
            ),
            "stop_buffer_atr": (
                self.stop_buffer_atr
            ),
            "require_four_hour_regime": (
                self.require_four_hour_regime
            ),
            "require_daily_regime": (
                self.require_daily_regime
            ),
        }


def default_volatility_compression_breakout_config(
) -> VolatilityCompressionBreakoutConfig:
    return VolatilityCompressionBreakoutConfig()


def _validate_source(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing = set(
        REQUIRED_COMPRESSION_BREAKOUT_COLUMNS
    ).difference(frame.columns)

    if missing:
        raise VolatilityCompressionBreakoutDataError(
            "Compression-breakout source is missing "
            f"columns: {sorted(missing)}."
        )

    result = frame.copy()

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
        errors="coerce",
    )

    if bool(
        result["timestamp"].isna().any()
    ):
        raise VolatilityCompressionBreakoutDataError(
            "Compression-breakout source contains "
            "invalid timestamps."
        )

    if bool(
        result["timestamp"].duplicated().any()
    ):
        raise VolatilityCompressionBreakoutDataError(
            "Compression-breakout source contains "
            "duplicate timestamps."
        )

    if not bool(
        result["timestamp"]
        .is_monotonic_increasing
    ):
        raise VolatilityCompressionBreakoutDataError(
            "Compression-breakout source must be "
            "chronologically ordered."
        )

    numeric_columns = tuple(
        column
        for column in (
            REQUIRED_COMPRESSION_BREAKOUT_COLUMNS
        )
        if column != "timestamp"
    )

    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    numeric_values = result[
        list(numeric_columns)
    ].to_numpy(dtype=float)

    if not bool(
        np.isfinite(numeric_values).all()
    ):
        raise VolatilityCompressionBreakoutDataError(
            "Compression-breakout source contains "
            "non-finite numeric values."
        )

    if bool(
        (
            result["1h_atr"]
            <= 0.0
        ).any()
    ):
        raise VolatilityCompressionBreakoutDataError(
            "ATR values must be positive."
        )

    if bool(
        (
            result["1h_volume_median"]
            <= 0.0
        ).any()
    ):
        raise VolatilityCompressionBreakoutDataError(
            "Volume medians must be positive."
        )

    invalid_ohlc = (
        (result["high"] < result["low"])
        | (
            result["high"]
            < result[
                ["open", "close"]
            ].max(axis=1)
        )
        | (
            result["low"]
            > result[
                ["open", "close"]
            ].min(axis=1)
        )
    )

    if bool(invalid_ohlc.any()):
        raise VolatilityCompressionBreakoutDataError(
            "Compression-breakout source contains "
            "invalid OHLC rows."
        )

    return result



def prepare_volatility_compression_breakout_simulation_frame(
    frame: pd.DataFrame,
    *,
    config: VolatilityCompressionBreakoutConfig,
) -> pd.DataFrame:
    required_columns = {
        "raw_entry_signal",
        "stop_price",
        "low",
        "1h_atr",
    }

    missing = required_columns.difference(
        frame.columns
    )

    if missing:
        raise VolatilityCompressionBreakoutDataError(
            "Simulation preparation is missing "
            f"columns: {sorted(missing)}."
        )

    result = frame.copy()

    raw_signal_values = result[
        "raw_entry_signal"
    ].tolist()

    if not all(
        isinstance(
            value,
            (bool, np.bool_),
        )
        for value in raw_signal_values
    ):
        raise VolatilityCompressionBreakoutDataError(
            "raw_entry_signal must contain "
            "Boolean values only."
        )

    signal_mask = result[
        "raw_entry_signal"
    ].astype(bool)

    fallback_stop = (
        result["low"]
        - (
            config.stop_buffer_atr
            * result["1h_atr"]
        )
    )

    # The simulator validates every numeric
    # column, including diagnostics it does not
    # consume. A finite non-signal placeholder
    # is therefore required. Signal stops remain
    # completely unchanged.
    result["stop_price"] = (
        result["stop_price"].where(
            signal_mask,
            fallback_stop,
        )
    )

    floating_columns = [
        str(column)
        for column in result.columns
        if pd.api.types.is_float_dtype(
            result[column]
        )
    ]

    if floating_columns and bool(
        signal_mask.any()
    ):
        signal_numeric_values = result.loc[
            signal_mask,
            floating_columns,
        ].to_numpy(dtype=float)

        if not bool(
            np.isfinite(
                signal_numeric_values
            ).all()
        ):
            raise VolatilityCompressionBreakoutDataError(
                "At least one signal row contains "
                "non-finite numeric data."
            )

    if floating_columns:
        result[floating_columns] = (
            result[floating_columns]
            .replace(
                [np.inf, -np.inf],
                np.nan,
            )
            .fillna(0.0)
        )

    numeric_columns = [
        str(column)
        for column in result.columns
        if (
            pd.api.types.is_numeric_dtype(
                result[column]
            )
            and not pd.api.types.is_bool_dtype(
                result[column]
            )
        )
    ]

    if numeric_columns:
        numeric_values = result[
            numeric_columns
        ].to_numpy(dtype=float)

        if not bool(
            np.isfinite(
                numeric_values
            ).all()
        ):
            raise VolatilityCompressionBreakoutDataError(
                "Simulation frame still contains "
                "non-finite numeric values."
            )

    if bool(
        (
            result.loc[
                signal_mask,
                "stop_price",
            ]
            >= result.loc[
                signal_mask,
                "close",
            ]
        ).any()
    ):
        raise VolatilityCompressionBreakoutDataError(
            "Simulation frame contains an "
            "invalid signal stop."
        )

    return result

def generate_volatility_compression_breakout_setups(
    frame: pd.DataFrame,
    *,
    config: VolatilityCompressionBreakoutConfig,
) -> pd.DataFrame:
    result = _validate_source(frame)

    prior_range_high = (
        result["high"]
        .shift(1)
        .rolling(
            config.compression_window,
            min_periods=(
                config.compression_window
            ),
        )
        .max()
    )

    prior_range_low = (
        result["low"]
        .shift(1)
        .rolling(
            config.compression_window,
            min_periods=(
                config.compression_window
            ),
        )
        .min()
    )

    prior_atr = result["1h_atr"].shift(1)

    compression_width = (
        prior_range_high
        - prior_range_low
    )

    compression_width_atr = (
        compression_width
        / prior_atr
    )

    baseline_width_atr = (
        compression_width_atr
        .shift(1)
        .rolling(
            config.baseline_window,
            min_periods=(
                config.baseline_window
            ),
        )
        .median()
    )

    compression_ratio = (
        compression_width_atr
        / baseline_width_atr
    )

    compression_ok = (
        prior_range_high.notna()
        & prior_range_low.notna()
        & prior_atr.notna()
        & baseline_width_atr.notna()
        & (
            baseline_width_atr
            > 0.0
        )
        & (
            compression_ratio
            <= config.maximum_compression_ratio
        )
    )

    volume_ratio = (
        result["volume"]
        / result["1h_volume_median"]
    )

    volume_ok = (
        volume_ratio
        >= config.minimum_volume_ratio
    )

    candle_range = (
        result["high"]
        - result["low"]
    )

    close_location = pd.Series(
        np.where(
            candle_range.to_numpy(
                dtype=float
            )
            > 0.0,
            (
                (
                    result["close"]
                    - result["low"]
                )
                / candle_range
            ).to_numpy(dtype=float),
            0.0,
        ),
        index=result.index,
        dtype="float64",
    )

    breakout_extension_atr = (
        (
            result["close"]
            - prior_range_high
        )
        / result["1h_atr"]
    )

    breakout_geometry_ok = (
        prior_range_high.notna()
        & (
            result["close"]
            > (
                prior_range_high
                + (
                    config.breakout_buffer_atr
                    * result["1h_atr"]
                )
            )
        )
        & (
            breakout_extension_atr
            <= (
                config
                .maximum_breakout_extension_atr
            )
        )
        & (
            close_location
            >= config.minimum_close_location
        )
    )

    four_hour_regime_ok = (
        (
            result["4h_close"]
            > result["4h_ema_fast"]
        )
        & (
            result["4h_ema_fast"]
            > result["4h_ema_slow"]
        )
    )

    daily_regime_ok = (
        (
            result["1d_close"]
            > result["1d_ema_fast"]
        )
        & (
            result["1d_ema_fast"]
            > result["1d_ema_slow"]
        )
    )

    regime_ok = pd.Series(
        True,
        index=result.index,
        dtype=bool,
    )

    if config.require_four_hour_regime:
        regime_ok &= four_hour_regime_ok

    if config.require_daily_regime:
        regime_ok &= daily_regime_ok

    breakout_candidate = (
        compression_ok
        & breakout_geometry_ok
        & volume_ok
        & regime_ok
    ).astype(bool)

    candidate_values = (
        breakout_candidate.to_numpy(
            dtype=bool
        )
    )

    raw_entry_signal = np.zeros(
        len(result),
        dtype=bool,
    )

    cooldown_suppressed = np.zeros(
        len(result),
        dtype=bool,
    )

    last_signal_index: int | None = None

    for index, is_candidate in enumerate(
        candidate_values
    ):
        if not is_candidate:
            continue

        cooldown_complete = (
            last_signal_index is None
            or (
                index - last_signal_index
                > config.signal_cooldown_bars
            )
        )

        if cooldown_complete:
            raw_entry_signal[index] = True
            last_signal_index = index

        else:
            cooldown_suppressed[index] = True

    stop_price = (
        prior_range_low
        - (
            config.stop_buffer_atr
            * result["1h_atr"]
        )
    ).where(raw_entry_signal)

    signal_stop_distance_atr = (
        (
            result["close"]
            - stop_price
        )
        / result["1h_atr"]
    ).where(raw_entry_signal)

    invalid_signal_stop = (
        raw_entry_signal
        & (
            stop_price.isna()
            | (
                stop_price
                >= result["close"]
            )
        )
    )

    if bool(invalid_signal_stop.any()):
        raise VolatilityCompressionBreakoutDataError(
            "Generated signal contains an "
            "invalid stop price."
        )

    result["prior_compression_high"] = (
        prior_range_high.astype(
            "float64"
        )
    )
    result["prior_compression_low"] = (
        prior_range_low.astype(
            "float64"
        )
    )
    result["compression_width"] = (
        compression_width.astype(
            "float64"
        )
    )
    result["compression_width_atr"] = (
        compression_width_atr.astype(
            "float64"
        )
    )
    result["baseline_width_atr"] = (
        baseline_width_atr.astype(
            "float64"
        )
    )
    result["compression_ratio"] = (
        compression_ratio.astype(
            "float64"
        )
    )
    result["compression_ok"] = (
        compression_ok.astype(bool)
    )
    result["volume_ratio"] = (
        volume_ratio.astype(
            "float64"
        )
    )
    result["volume_ok"] = (
        volume_ok.astype(bool)
    )
    result["close_location"] = (
        close_location
    )
    result["breakout_extension_atr"] = (
        breakout_extension_atr.astype(
            "float64"
        )
    )
    result["breakout_geometry_ok"] = (
        breakout_geometry_ok.astype(bool)
    )
    result["four_hour_regime_ok"] = (
        four_hour_regime_ok.astype(bool)
    )
    result["daily_regime_ok"] = (
        daily_regime_ok.astype(bool)
    )
    result["regime_ok"] = (
        regime_ok.astype(bool)
    )
    result["breakout_candidate"] = (
        breakout_candidate.astype(bool)
    )
    result["cooldown_suppressed"] = (
        cooldown_suppressed
    )
    result["stop_price"] = (
        stop_price.astype("float64")
    )
    result["signal_stop_distance_atr"] = (
        signal_stop_distance_atr.astype(
            "float64"
        )
    )
    result["raw_entry_signal"] = (
        raw_entry_signal
    )

    return result