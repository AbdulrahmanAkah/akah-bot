from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import cast

import pandas as pd

REQUIRED_TREND_PULLBACK_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "1h_ema_fast",
    "1h_ema_slow",
    "1h_atr",
    "1h_rsi",
    "1h_volume_median",
    "4h_close",
    "4h_ema_fast",
    "4h_ema_slow",
    "1d_close",
    "1d_ema_fast",
    "1d_ema_slow",
)

TREND_PULLBACK_OUTPUT_COLUMNS = (
    "daily_regime_ok",
    "four_hour_structure_ok",
    "one_hour_trend_ok",
    "pullback_ok",
    "trigger_ok",
    "momentum_ok",
    "volume_ok",
    "valid_stop",
    "raw_entry_signal",
    "stop_price",
    "stop_distance",
    "stop_distance_atr",
)


class TrendPullbackError(RuntimeError):
    pass


class TrendPullbackConfigurationError(
    TrendPullbackError
):
    pass


class TrendPullbackDataError(TrendPullbackError):
    pass


@dataclass(frozen=True, slots=True)
class TrendPullbackConfig:
    rsi_minimum: float = 45.0
    rsi_maximum: float = 68.0
    touch_tolerance_atr: float = 0.15
    maximum_close_extension_atr: float = 0.75
    minimum_volume_ratio: float = 0.80
    stop_buffer_atr: float = 0.25

    def __post_init__(self) -> None:
        if not (
            0.0
            <= self.rsi_minimum
            < self.rsi_maximum
            <= 100.0
        ):
            raise TrendPullbackConfigurationError(
                "RSI limits must satisfy "
                "0 <= minimum < maximum <= 100."
            )

        non_negative = {
            "touch_tolerance_atr": (
                self.touch_tolerance_atr
            ),
            "maximum_close_extension_atr": (
                self.maximum_close_extension_atr
            ),
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
            "stop_buffer_atr": (
                self.stop_buffer_atr
            ),
        }

        for name, value in non_negative.items():
            if value < 0.0:
                raise TrendPullbackConfigurationError(
                    f"{name} cannot be negative."
                )

        if (
            self.maximum_close_extension_atr
            < self.touch_tolerance_atr
        ):
            raise TrendPullbackConfigurationError(
                "maximum_close_extension_atr "
                "cannot be smaller than "
                "touch_tolerance_atr."
            )

    def to_dict(self) -> dict[str, float]:
        return cast(
            dict[str, float],
            asdict(self),
        )


def default_trend_pullback_config(
) -> TrendPullbackConfig:
    return TrendPullbackConfig()


def _numeric_series(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    result = pd.to_numeric(
        frame[column],
        errors="coerce",
    )

    if not isinstance(result, pd.Series):
        raise TrendPullbackDataError(
            f"Column did not produce a Series: "
            f"{column}."
        )

    return result.astype("float64")


def _validate_source_frame(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing_columns = set(
        REQUIRED_TREND_PULLBACK_COLUMNS
    ).difference(frame.columns)

    if missing_columns:
        raise TrendPullbackDataError(
            "Trend Pullback source is missing "
            f"columns: {sorted(missing_columns)}."
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
        raise TrendPullbackDataError(
            "Trend Pullback source contains "
            "invalid timestamps."
        )

    if bool(
        result["timestamp"].duplicated().any()
    ):
        raise TrendPullbackDataError(
            "Trend Pullback source contains "
            "duplicate timestamps."
        )

    if not bool(
        result["timestamp"].is_monotonic_increasing
    ):
        raise TrendPullbackDataError(
            "Trend Pullback source must be "
            "chronologically ordered."
        )

    for column in (
        REQUIRED_TREND_PULLBACK_COLUMNS[1:]
    ):
        result[column] = _numeric_series(
            result,
            column,
        )

    if bool(
        result[
            list(
                REQUIRED_TREND_PULLBACK_COLUMNS[
                    1:
                ]
            )
        ]
        .isna()
        .any()
        .any()
    ):
        raise TrendPullbackDataError(
            "Trend Pullback source contains "
            "missing numeric values."
        )

    atr = _numeric_series(
        result,
        "1h_atr",
    )

    if bool((atr <= 0.0).any()):
        raise TrendPullbackDataError(
            "ATR values must be positive."
        )

    volume_median = _numeric_series(
        result,
        "1h_volume_median",
    )

    if bool((volume_median < 0.0).any()):
        raise TrendPullbackDataError(
            "Volume median cannot be negative."
        )

    return result


def generate_trend_pullback_setups(
    frame: pd.DataFrame,
    *,
    config: TrendPullbackConfig,
) -> pd.DataFrame:
    result = _validate_source_frame(frame)

    close = _numeric_series(
        result,
        "close",
    )
    high = _numeric_series(
        result,
        "high",
    )
    low = _numeric_series(
        result,
        "low",
    )
    volume = _numeric_series(
        result,
        "volume",
    )

    one_hour_fast = _numeric_series(
        result,
        "1h_ema_fast",
    )
    one_hour_slow = _numeric_series(
        result,
        "1h_ema_slow",
    )
    atr = _numeric_series(
        result,
        "1h_atr",
    )
    rsi = _numeric_series(
        result,
        "1h_rsi",
    )
    volume_median = _numeric_series(
        result,
        "1h_volume_median",
    )

    four_hour_close = _numeric_series(
        result,
        "4h_close",
    )
    four_hour_fast = _numeric_series(
        result,
        "4h_ema_fast",
    )
    four_hour_slow = _numeric_series(
        result,
        "4h_ema_slow",
    )

    daily_close = _numeric_series(
        result,
        "1d_close",
    )
    daily_fast = _numeric_series(
        result,
        "1d_ema_fast",
    )
    daily_slow = _numeric_series(
        result,
        "1d_ema_slow",
    )

    previous_high = high.shift(1)
    previous_low = low.shift(1)

    daily_regime_ok = (
        (daily_close > daily_fast)
        & (daily_fast > daily_slow)
    )

    four_hour_structure_ok = (
        (four_hour_close > four_hour_fast)
        & (four_hour_fast > four_hour_slow)
    )

    one_hour_trend_ok = (
        one_hour_fast > one_hour_slow
    )

    touch_ceiling = (
        one_hour_fast
        + config.touch_tolerance_atr
        * atr
    )

    extension_ceiling = (
        one_hour_fast
        + config.maximum_close_extension_atr
        * atr
    )

    pullback_ok = (
        (low <= touch_ceiling)
        & (close >= one_hour_fast)
        & (close <= extension_ceiling)
    )

    trigger_ok = (
        previous_high.notna()
        & (close > previous_high)
    )

    momentum_ok = rsi.between(
        config.rsi_minimum,
        config.rsi_maximum,
        inclusive="both",
    )

    volume_ok = (
        volume
        >= volume_median
        * config.minimum_volume_ratio
    )

    structural_low = pd.concat(
        [
            low,
            previous_low,
        ],
        axis=1,
    ).min(axis=1)

    if not isinstance(
        structural_low,
        pd.Series,
    ):
        raise TrendPullbackDataError(
            "Structural-low calculation failed."
        )

    stop_price = (
        structural_low.astype("float64")
        - config.stop_buffer_atr
        * atr
    )

    stop_distance = close - stop_price

    valid_stop = (
        previous_low.notna()
        & (stop_price > 0.0)
        & (stop_price < close)
        & (stop_distance > 0.0)
    )

    raw_entry_signal = (
        daily_regime_ok
        & four_hour_structure_ok
        & one_hour_trend_ok
        & pullback_ok
        & trigger_ok
        & momentum_ok
        & volume_ok
        & valid_stop
    )

    result["daily_regime_ok"] = (
        daily_regime_ok.astype(bool)
    )
    result["four_hour_structure_ok"] = (
        four_hour_structure_ok.astype(bool)
    )
    result["one_hour_trend_ok"] = (
        one_hour_trend_ok.astype(bool)
    )
    result["pullback_ok"] = (
        pullback_ok.astype(bool)
    )
    result["trigger_ok"] = (
        trigger_ok.astype(bool)
    )
    result["momentum_ok"] = (
        momentum_ok.astype(bool)
    )
    result["volume_ok"] = (
        volume_ok.astype(bool)
    )
    result["valid_stop"] = (
        valid_stop.astype(bool)
    )
    result["raw_entry_signal"] = (
        raw_entry_signal.astype(bool)
    )
    result["stop_price"] = (
        stop_price.astype("float64")
    )
    result["stop_distance"] = (
        stop_distance.astype("float64")
    )
    result["stop_distance_atr"] = (
        stop_distance / atr
    ).astype("float64")

    return result