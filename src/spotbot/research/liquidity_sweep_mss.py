from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

REQUIRED_LIQUIDITY_SWEEP_COLUMNS = (
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


class LiquiditySweepMssError(RuntimeError):
    pass


class LiquiditySweepMssConfigurationError(
    LiquiditySweepMssError
):
    pass


class LiquiditySweepMssDataError(
    LiquiditySweepMssError
):
    pass


@dataclass(frozen=True, slots=True)
class LiquiditySweepMssConfig:
    liquidity_lookback: int = 24
    structure_lookback: int = 6
    confirmation_window: int = 8
    minimum_sweep_depth_atr: float = 0.10
    maximum_sweep_depth_atr: float = 1.25
    minimum_volume_ratio: float = 0.80
    stop_buffer_atr: float = 0.25
    require_four_hour_regime: bool = True
    require_daily_regime: bool = True

    def __post_init__(self) -> None:
        integer_parameters = {
            "liquidity_lookback": (
                self.liquidity_lookback
            ),
            "structure_lookback": (
                self.structure_lookback
            ),
            "confirmation_window": (
                self.confirmation_window
            ),
        }

        for integer_name, integer_value in (
            integer_parameters.items()
        ):
            if integer_value < 1:
                raise (
                    LiquiditySweepMssConfigurationError(
                        f"{integer_name} must be at least 1."
                    )
                )

        numeric_parameters = {
            "minimum_sweep_depth_atr": (
                self.minimum_sweep_depth_atr
            ),
            "maximum_sweep_depth_atr": (
                self.maximum_sweep_depth_atr
            ),
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
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
                    LiquiditySweepMssConfigurationError(
                        f"{numeric_name} must be finite."
                    )
                )

            if numeric_value < 0.0:
                raise (
                    LiquiditySweepMssConfigurationError(
                        f"{numeric_name} cannot be negative."
                    )
                )

        if (
            self.minimum_sweep_depth_atr
            > self.maximum_sweep_depth_atr
        ):
            raise (
                LiquiditySweepMssConfigurationError(
                    "Minimum sweep depth cannot "
                    "exceed maximum sweep depth."
                )
            )

    def to_dict(
        self,
    ) -> dict[str, int | float | bool]:
        return {
            "liquidity_lookback": (
                self.liquidity_lookback
            ),
            "structure_lookback": (
                self.structure_lookback
            ),
            "confirmation_window": (
                self.confirmation_window
            ),
            "minimum_sweep_depth_atr": (
                self.minimum_sweep_depth_atr
            ),
            "maximum_sweep_depth_atr": (
                self.maximum_sweep_depth_atr
            ),
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
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


def default_liquidity_sweep_mss_config(
) -> LiquiditySweepMssConfig:
    return LiquiditySweepMssConfig()


def _validate_source(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing = set(
        REQUIRED_LIQUIDITY_SWEEP_COLUMNS
    ).difference(frame.columns)

    if missing:
        raise LiquiditySweepMssDataError(
            "Liquidity-sweep source is missing "
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
        raise LiquiditySweepMssDataError(
            "Liquidity-sweep source contains "
            "invalid timestamps."
        )

    if bool(
        result["timestamp"].duplicated().any()
    ):
        raise LiquiditySweepMssDataError(
            "Liquidity-sweep source contains "
            "duplicate timestamps."
        )

    if not bool(
        result["timestamp"]
        .is_monotonic_increasing
    ):
        raise LiquiditySweepMssDataError(
            "Liquidity-sweep source must be "
            "chronologically ordered."
        )

    numeric_columns = tuple(
        column
        for column in (
            REQUIRED_LIQUIDITY_SWEEP_COLUMNS
        )
        if column != "timestamp"
    )

    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    values = result[
        list(numeric_columns)
    ].to_numpy(dtype=float)

    if not bool(
        np.isfinite(values).all()
    ):
        raise LiquiditySweepMssDataError(
            "Liquidity-sweep source contains "
            "non-finite numeric values."
        )

    if bool(
        (
            result["1h_atr"]
            <= 0.0
        ).any()
    ):
        raise LiquiditySweepMssDataError(
            "ATR values must be positive."
        )

    if bool(
        (
            result["1h_volume_median"]
            <= 0.0
        ).any()
    ):
        raise LiquiditySweepMssDataError(
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
        raise LiquiditySweepMssDataError(
            "Liquidity-sweep source contains "
            "invalid OHLC rows."
        )

    return result


def generate_liquidity_sweep_mss_setups(
    frame: pd.DataFrame,
    *,
    config: LiquiditySweepMssConfig,
) -> pd.DataFrame:
    result = _validate_source(frame)

    prior_liquidity_low = (
        result["low"]
        .shift(1)
        .rolling(
            config.liquidity_lookback,
            min_periods=(
                config.liquidity_lookback
            ),
        )
        .min()
    )

    prior_structure_high = (
        result["high"]
        .shift(1)
        .rolling(
            config.structure_lookback,
            min_periods=(
                config.structure_lookback
            ),
        )
        .max()
    )

    sweep_depth_atr = (
        (
            prior_liquidity_low
            - result["low"]
        )
        / result["1h_atr"]
    )

    volume_ratio = (
        result["volume"]
        / result["1h_volume_median"]
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

    sweep_geometry_ok = (
        prior_liquidity_low.notna()
        & prior_structure_high.notna()
        & (
            result["low"]
            < prior_liquidity_low
        )
        & (
            result["close"]
            > prior_liquidity_low
        )
        & (
            sweep_depth_atr
            >= config.minimum_sweep_depth_atr
        )
        & (
            sweep_depth_atr
            <= config.maximum_sweep_depth_atr
        )
    )

    volume_ok = (
        volume_ratio
        >= config.minimum_volume_ratio
    )

    liquidity_sweep = (
        regime_ok
        & sweep_geometry_ok
        & volume_ok
    ).astype(bool)

    row_count = len(result)

    raw_entry_signal = np.zeros(
        row_count,
        dtype=bool,
    )

    mss_confirmed = np.zeros(
        row_count,
        dtype=bool,
    )

    setup_active_after_close = np.zeros(
        row_count,
        dtype=bool,
    )

    stop_prices = np.full(
        row_count,
        np.nan,
        dtype=float,
    )

    active_mss_levels = np.full(
        row_count,
        np.nan,
        dtype=float,
    )

    bars_from_sweep = np.full(
        row_count,
        np.nan,
        dtype=float,
    )

    sweep_source_indices = np.full(
        row_count,
        -1,
        dtype=int,
    )

    low_values = result["low"].to_numpy(
        dtype=float
    )
    close_values = result["close"].to_numpy(
        dtype=float
    )
    atr_values = result["1h_atr"].to_numpy(
        dtype=float
    )
    structure_values = (
        prior_structure_high.to_numpy(
            dtype=float
        )
    )
    regime_values = regime_ok.to_numpy(
        dtype=bool
    )
    sweep_values = liquidity_sweep.to_numpy(
        dtype=bool
    )

    active_sweep_index: int | None = None
    active_sweep_low = 0.0
    active_mss_level = 0.0
    active_stop_price = 0.0

    for index in range(row_count):
        if active_sweep_index is not None:
            elapsed_bars = (
                index - active_sweep_index
            )

            bars_from_sweep[index] = float(
                elapsed_bars
            )
            active_mss_levels[index] = (
                active_mss_level
            )
            sweep_source_indices[index] = (
                active_sweep_index
            )

            expired = (
                elapsed_bars
                > config.confirmation_window
            )

            invalidated = (
                low_values[index]
                <= active_stop_price
            )

            regime_failed = (
                not regime_values[index]
            )

            if (
                expired
                or invalidated
                or regime_failed
            ):
                active_sweep_index = None

            elif (
                close_values[index]
                > active_mss_level
            ):
                raw_entry_signal[index] = True
                mss_confirmed[index] = True
                stop_prices[index] = (
                    active_stop_price
                )

                active_sweep_index = None

        if (
            active_sweep_index is None
            and sweep_values[index]
        ):
            active_sweep_index = index
            active_sweep_low = (
                low_values[index]
            )
            active_mss_level = (
                structure_values[index]
            )
            active_stop_price = (
                active_sweep_low
                - (
                    config.stop_buffer_atr
                    * atr_values[index]
                )
            )

            bars_from_sweep[index] = 0.0
            active_mss_levels[index] = (
                active_mss_level
            )
            sweep_source_indices[index] = (
                index
            )

            if (
                close_values[index]
                > active_mss_level
            ):
                raw_entry_signal[index] = True
                mss_confirmed[index] = True
                stop_prices[index] = (
                    active_stop_price
                )

                active_sweep_index = None

        setup_active_after_close[index] = (
            active_sweep_index is not None
        )

    source_timestamps: list[
        pd.Timestamp | None
    ] = [
        (
            None
            if source_index < 0
            else pd.Timestamp(
                result.iloc[
                    source_index
                ]["timestamp"]
            )
        )
        for source_index in (
            sweep_source_indices
        )
    ]

    result["prior_liquidity_low"] = (
        prior_liquidity_low.astype(
            "float64"
        )
    )
    result["prior_structure_high"] = (
        prior_structure_high.astype(
            "float64"
        )
    )
    result["sweep_depth_atr"] = (
        sweep_depth_atr.astype(
            "float64"
        )
    )
    result["volume_ratio"] = (
        volume_ratio.astype(
            "float64"
        )
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
    result["sweep_geometry_ok"] = (
        sweep_geometry_ok.astype(bool)
    )
    result["volume_ok"] = (
        volume_ok.astype(bool)
    )
    result["liquidity_sweep"] = (
        liquidity_sweep.astype(bool)
    )
    result["mss_level"] = (
        active_mss_levels
    )
    result["bars_from_sweep"] = (
        bars_from_sweep
    )
    result["setup_sweep_timestamp"] = (
        pd.Series(
            source_timestamps,
            index=result.index,
            dtype="datetime64[ns, UTC]",
        )
    )
    result["mss_confirmed"] = (
        mss_confirmed
    )
    result["setup_active_after_close"] = (
        setup_active_after_close
    )
    result["stop_price"] = (
        stop_prices
    )
    result["raw_entry_signal"] = (
        raw_entry_signal
    )

    signal_stop_distance_atr = (
        (
            result["close"]
            - result["stop_price"]
        )
        / result["1h_atr"]
    )

    result["signal_stop_distance_atr"] = (
        signal_stop_distance_atr
        .where(
            result["raw_entry_signal"]
        )
        .astype("float64")
    )

    invalid_signal_stop = (
        result["raw_entry_signal"]
        & (
            (
                result["stop_price"]
                >= result["close"]
            )
            | result["stop_price"].isna()
        )
    )

    if bool(invalid_signal_stop.any()):
        raise LiquiditySweepMssDataError(
            "Generated signal contains an "
            "invalid stop price."
        )

    return result