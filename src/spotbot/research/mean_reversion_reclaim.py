from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

REQUIRED_MEAN_REVERSION_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "1h_atr",
    "1h_rsi",
    "1h_ema_fast",
    "1h_ema_slow",
    "1h_volume_median",
    "4h_close",
    "4h_ema_fast",
    "4h_ema_slow",
    "1d_close",
    "1d_ema_fast",
    "1d_ema_slow",
)


class MeanReversionReclaimError(
    RuntimeError
):
    pass


class MeanReversionReclaimConfigurationError(
    MeanReversionReclaimError
):
    pass


class MeanReversionReclaimDataError(
    MeanReversionReclaimError
):
    pass


@dataclass(frozen=True, slots=True)
class MeanReversionReclaimConfig:
    oversold_lookback: int = 8
    signal_cooldown_bars: int = 12
    oversold_rsi: float = 35.0
    reclaim_rsi: float = 42.0
    minimum_volume_ratio: float = 0.80
    maximum_reclaim_extension_atr: float = 0.75
    stop_buffer_atr: float = 0.25
    require_four_hour_regime: bool = True
    require_daily_regime: bool = False

    def __post_init__(self) -> None:
        if self.oversold_lookback < 1:
            raise (
                MeanReversionReclaimConfigurationError(
                    "oversold_lookback must be "
                    "at least 1."
                )
            )

        if self.signal_cooldown_bars < 0:
            raise (
                MeanReversionReclaimConfigurationError(
                    "signal_cooldown_bars cannot "
                    "be negative."
                )
            )

        numeric_parameters = {
            "oversold_rsi": self.oversold_rsi,
            "reclaim_rsi": self.reclaim_rsi,
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
            "maximum_reclaim_extension_atr": (
                self.maximum_reclaim_extension_atr
            ),
            "stop_buffer_atr": (
                self.stop_buffer_atr
            ),
        }

        for name, value in (
            numeric_parameters.items()
        ):
            if not isfinite(value):
                raise (
                    MeanReversionReclaimConfigurationError(
                        f"{name} must be finite."
                    )
                )

        if not (
            0.0 <= self.oversold_rsi < 100.0
        ):
            raise (
                MeanReversionReclaimConfigurationError(
                    "oversold_rsi must be within "
                    "[0, 100)."
                )
            )

        if not (
            self.oversold_rsi
            < self.reclaim_rsi
            <= 100.0
        ):
            raise (
                MeanReversionReclaimConfigurationError(
                    "reclaim_rsi must exceed "
                    "oversold_rsi and be at most 100."
                )
            )

        nonnegative_parameters = {
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
            "maximum_reclaim_extension_atr": (
                self.maximum_reclaim_extension_atr
            ),
            "stop_buffer_atr": (
                self.stop_buffer_atr
            ),
        }

        for name, value in (
            nonnegative_parameters.items()
        ):
            if value < 0.0:
                raise (
                    MeanReversionReclaimConfigurationError(
                        f"{name} cannot be negative."
                    )
                )

    def to_dict(
        self,
    ) -> dict[str, int | float | bool]:
        return {
            "oversold_lookback": (
                self.oversold_lookback
            ),
            "signal_cooldown_bars": (
                self.signal_cooldown_bars
            ),
            "oversold_rsi": self.oversold_rsi,
            "reclaim_rsi": self.reclaim_rsi,
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
            "maximum_reclaim_extension_atr": (
                self.maximum_reclaim_extension_atr
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


def default_mean_reversion_reclaim_config(
) -> MeanReversionReclaimConfig:
    return MeanReversionReclaimConfig()


def _validate_source(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing = set(
        REQUIRED_MEAN_REVERSION_COLUMNS
    ).difference(frame.columns)

    if missing:
        raise MeanReversionReclaimDataError(
            "Mean-reversion source is missing "
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
        raise MeanReversionReclaimDataError(
            "Mean-reversion source contains "
            "invalid timestamps."
        )

    if bool(
        result["timestamp"].duplicated().any()
    ):
        raise MeanReversionReclaimDataError(
            "Mean-reversion source contains "
            "duplicate timestamps."
        )

    if not bool(
        result["timestamp"]
        .is_monotonic_increasing
    ):
        raise MeanReversionReclaimDataError(
            "Mean-reversion source must be "
            "chronologically ordered."
        )

    numeric_columns = tuple(
        column
        for column in (
            REQUIRED_MEAN_REVERSION_COLUMNS
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
        raise MeanReversionReclaimDataError(
            "Mean-reversion source contains "
            "non-finite numeric values."
        )

    if bool(
        (
            result["1h_atr"]
            <= 0.0
        ).any()
    ):
        raise MeanReversionReclaimDataError(
            "ATR values must be positive."
        )

    if bool(
        (
            result["1h_volume_median"]
            <= 0.0
        ).any()
    ):
        raise MeanReversionReclaimDataError(
            "Volume medians must be positive."
        )

    invalid_rsi = (
        (result["1h_rsi"] < 0.0)
        | (result["1h_rsi"] > 100.0)
    )

    if bool(invalid_rsi.any()):
        raise MeanReversionReclaimDataError(
            "RSI values must be within "
            "[0, 100]."
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
        raise MeanReversionReclaimDataError(
            "Mean-reversion source contains "
            "invalid OHLC rows."
        )

    return result


def generate_mean_reversion_reclaim_setups(
    frame: pd.DataFrame,
    *,
    config: MeanReversionReclaimConfig,
) -> pd.DataFrame:
    result = _validate_source(frame)

    previous_rsi = result[
        "1h_rsi"
    ].shift(1)

    prior_oversold_rsi = (
        result["1h_rsi"]
        .shift(1)
        .rolling(
            config.oversold_lookback,
            min_periods=(
                config.oversold_lookback
            ),
        )
        .min()
    )

    oversold_seen = (
        prior_oversold_rsi
        <= config.oversold_rsi
    )

    rsi_reclaim_ok = (
        previous_rsi.notna()
        & (
            previous_rsi
            < config.reclaim_rsi
        )
        & (
            result["1h_rsi"]
            >= config.reclaim_rsi
        )
    )

    price_reclaim_ok = (
        (
            result["close"].shift(1)
            <= result[
                "1h_ema_fast"
            ].shift(1)
        )
        & (
            result["close"]
            > result["1h_ema_fast"]
        )
    )

    reclaim_extension_atr = (
        (
            result["close"]
            - result["1h_ema_fast"]
        )
        / result["1h_atr"]
    )

    extension_ok = (
        (reclaim_extension_atr > 0.0)
        & (
            reclaim_extension_atr
            <= (
                config
                .maximum_reclaim_extension_atr
            )
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

    four_hour_regime_ok = (
        (
            result["4h_close"]
            > result["4h_ema_slow"]
        )
        & (
            result["4h_ema_fast"]
            >= result["4h_ema_slow"]
        )
    )

    daily_regime_ok = (
        (
            result["1d_close"]
            > result["1d_ema_slow"]
        )
        & (
            result["1d_ema_fast"]
            >= result["1d_ema_slow"]
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

    reclaim_candidate = (
        oversold_seen
        & rsi_reclaim_ok
        & price_reclaim_ok
        & extension_ok
        & volume_ok
        & regime_ok
    ).astype(bool)

    candidate_values = (
        reclaim_candidate.to_numpy(
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

    setup_reference_low = (
        result["low"]
        .rolling(
            config.oversold_lookback + 1,
            min_periods=(
                config.oversold_lookback + 1
            ),
        )
        .min()
    )

    stop_price = (
        setup_reference_low
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
        raise MeanReversionReclaimDataError(
            "Generated signal contains an "
            "invalid stop price."
        )

    result["prior_oversold_rsi"] = (
        prior_oversold_rsi.astype(
            "float64"
        )
    )
    result["oversold_seen"] = (
        oversold_seen.astype(bool)
    )
    result["rsi_reclaim_ok"] = (
        rsi_reclaim_ok.astype(bool)
    )
    result["price_reclaim_ok"] = (
        price_reclaim_ok.astype(bool)
    )
    result["reclaim_extension_atr"] = (
        reclaim_extension_atr.astype(
            "float64"
        )
    )
    result["extension_ok"] = (
        extension_ok.astype(bool)
    )
    result["volume_ratio"] = (
        volume_ratio.astype("float64")
    )
    result["volume_ok"] = (
        volume_ok.astype(bool)
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
    result["reclaim_candidate"] = (
        reclaim_candidate.astype(bool)
    )
    result["cooldown_suppressed"] = (
        cooldown_suppressed
    )
    result["setup_reference_low"] = (
        setup_reference_low.astype(
            "float64"
        )
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


def prepare_mean_reversion_reclaim_simulation_frame(
    frame: pd.DataFrame,
    *,
    config: MeanReversionReclaimConfig,
) -> pd.DataFrame:
    required_columns = {
        "raw_entry_signal",
        "stop_price",
        "low",
        "close",
        "1h_atr",
    }

    missing = required_columns.difference(
        frame.columns
    )

    if missing:
        raise MeanReversionReclaimDataError(
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
        raise MeanReversionReclaimDataError(
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
            raise MeanReversionReclaimDataError(
                "A signal row contains "
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
            raise MeanReversionReclaimDataError(
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
        raise MeanReversionReclaimDataError(
            "Simulation frame contains an "
            "invalid signal stop."
        )

    return result