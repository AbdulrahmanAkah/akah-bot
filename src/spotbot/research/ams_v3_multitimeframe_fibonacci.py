from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, cast

import numpy as np
import pandas as pd


class AmsV3MtfDataError(ValueError):
    """Raised when multi-timeframe input data violates the protocol."""


class AmsV3MtfParameterError(ValueError):
    """Raised when strategy parameters are invalid."""


class DailyRegime(StrEnum):
    FULL_RISK = "FULL_RISK"
    REDUCED_RISK = "REDUCED_RISK"
    DEFENSIVE = "DEFENSIVE"
    CASH = "CASH"


class EightHourState(StrEnum):
    ALIGNED = "ALIGNED"
    PARTIALLY_ALIGNED = "PARTIALLY_ALIGNED"
    MIXED = "MIXED"
    ADVERSE = "ADVERSE"
    OVEREXTENDED = "OVEREXTENDED"


class FibonacciZone(StrEnum):
    NO_ACTIVE_IMPULSE = "NO_ACTIVE_IMPULSE"
    EXTENSION = "EXTENSION"
    MINOR = "MINOR"
    SHALLOW = "SHALLOW"
    CORE = "CORE"
    DEEP = "DEEP"
    INVALIDATED = "INVALIDATED"


class FourHourSetup(StrEnum):
    NONE = "NONE"
    BREAKOUT = "BREAKOUT"
    FIBONACCI_PULLBACK = "FIBONACCI_PULLBACK"


DAILY_RISK_MULTIPLIERS: Final[
    Mapping[DailyRegime, float]
] = {
    DailyRegime.FULL_RISK: 1.0,
    DailyRegime.REDUCED_RISK: 0.70,
    DailyRegime.DEFENSIVE: 0.35,
    DailyRegime.CASH: 0.0,
}

EIGHT_HOUR_ALLOCATION_MULTIPLIERS: Final[
    Mapping[EightHourState, float]
] = {
    EightHourState.ALIGNED: 1.0,
    EightHourState.PARTIALLY_ALIGNED: 0.70,
    EightHourState.MIXED: 0.40,
    EightHourState.ADVERSE: 0.0,
    EightHourState.OVEREXTENDED: 0.50,
}

FIBONACCI_ALLOCATION_MULTIPLIERS: Final[
    Mapping[FibonacciZone, float]
] = {
    FibonacciZone.NO_ACTIVE_IMPULSE: 0.0,
    FibonacciZone.EXTENSION: 0.60,
    FibonacciZone.MINOR: 0.80,
    FibonacciZone.SHALLOW: 1.0,
    FibonacciZone.CORE: 1.0,
    FibonacciZone.DEEP: 0.50,
    FibonacciZone.INVALIDATED: 0.0,
}


@dataclass(frozen=True)
class MtfFibonacciParameters:
    daily_ema_fast: int = 50
    daily_ema_slow: int = 200
    daily_adx_period: int = 14
    daily_volatility_fast: int = 20
    daily_volatility_slow: int = 60
    daily_breadth_full_risk: float = 0.55
    daily_adx_full_risk: float = 18.0
    daily_max_volatility_ratio: float = 1.50

    eight_hour_ema_fast: int = 21
    eight_hour_ema_slow: int = 55
    eight_hour_atr_period: int = 14
    eight_hour_relative_strength_period: int = 20
    eight_hour_overextension_atr: float = 3.0

    four_hour_ema_period: int = 21
    four_hour_atr_period: int = 14
    four_hour_donchian_period: int = 20
    four_hour_compression_period: int = 20
    four_hour_expansion_multiple: float = 1.10
    four_hour_initial_stop_atr: float = 2.25
    four_hour_trailing_stop_atr: float = 3.0
    four_hour_setup_expiry_bars: int = 3

    pivot_left_bars: int = 3
    pivot_right_bars: int = 3

    fibonacci_minor: float = 0.236
    fibonacci_shallow: float = 0.382
    fibonacci_core: float = 0.618
    fibonacci_deep: float = 0.786
    fibonacci_extension_one: float = 1.272
    fibonacci_extension_two: float = 1.618

    base_risk_fraction: float = 0.01
    volatility_adjustment_floor: float = 0.40
    portfolio_heat_adjustment_floor: float = 0.25

    def validate(self) -> None:
        integer_fields = {
            "daily_ema_fast": self.daily_ema_fast,
            "daily_ema_slow": self.daily_ema_slow,
            "daily_adx_period": self.daily_adx_period,
            "daily_volatility_fast": self.daily_volatility_fast,
            "daily_volatility_slow": self.daily_volatility_slow,
            "eight_hour_ema_fast": self.eight_hour_ema_fast,
            "eight_hour_ema_slow": self.eight_hour_ema_slow,
            "eight_hour_atr_period": self.eight_hour_atr_period,
            "eight_hour_relative_strength_period": (
                self.eight_hour_relative_strength_period
            ),
            "four_hour_ema_period": self.four_hour_ema_period,
            "four_hour_atr_period": self.four_hour_atr_period,
            "four_hour_donchian_period": (
                self.four_hour_donchian_period
            ),
            "four_hour_compression_period": (
                self.four_hour_compression_period
            ),
            "four_hour_setup_expiry_bars": (
                self.four_hour_setup_expiry_bars
            ),
            "pivot_left_bars": self.pivot_left_bars,
            "pivot_right_bars": self.pivot_right_bars,
        }

        for (
            integer_name,
            integer_value,
        ) in integer_fields.items():
            if integer_value <= 0:
                raise AmsV3MtfParameterError(
                    f"{integer_name} must be positive."
                )

        if (
            self.daily_ema_fast
            >= self.daily_ema_slow
        ):
            raise AmsV3MtfParameterError(
                "Daily fast EMA must be below slow EMA."
            )

        if (
            self.eight_hour_ema_fast
            >= self.eight_hour_ema_slow
        ):
            raise AmsV3MtfParameterError(
                "8H fast EMA must be below slow EMA."
            )

        fibonacci_values = (
            self.fibonacci_minor,
            self.fibonacci_shallow,
            self.fibonacci_core,
            self.fibonacci_deep,
        )

        if not (
            0.0
            < fibonacci_values[0]
            < fibonacci_values[1]
            < fibonacci_values[2]
            < fibonacci_values[3]
            < 1.0
        ):
            raise AmsV3MtfParameterError(
                "Fibonacci retracement levels are invalid."
            )

        if not (
            1.0
            < self.fibonacci_extension_one
            < self.fibonacci_extension_two
        ):
            raise AmsV3MtfParameterError(
                "Fibonacci extension levels are invalid."
            )

        finite_positive = {
            "eight_hour_overextension_atr": (
                self.eight_hour_overextension_atr
            ),
            "four_hour_expansion_multiple": (
                self.four_hour_expansion_multiple
            ),
            "four_hour_initial_stop_atr": (
                self.four_hour_initial_stop_atr
            ),
            "four_hour_trailing_stop_atr": (
                self.four_hour_trailing_stop_atr
            ),
            "base_risk_fraction": (
                self.base_risk_fraction
            ),
        }

        for (
            numeric_name,
            numeric_value,
        ) in finite_positive.items():
            if (
                not math.isfinite(
                    numeric_value
                )
                or numeric_value <= 0.0
            ):
                raise AmsV3MtfParameterError(
                    f"{numeric_name} must be positive and finite."
                )

        if self.base_risk_fraction > 0.05:
            raise AmsV3MtfParameterError(
                "Base risk fraction may not exceed 5%."
            )



def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
) -> None:
    missing = [
        column
        for column in columns
        if column not in frame.columns
    ]

    if missing:
        raise AmsV3MtfDataError(
            f"Missing required columns: {missing}."
        )


def _numeric(
    frame: pd.DataFrame,
    column: str,
) -> pd.Series:
    values = pd.to_numeric(
        frame[column],
        errors="coerce",
    ).astype("float64")

    return values


def _utc_index(
    frame: pd.DataFrame,
) -> pd.DatetimeIndex:
    if isinstance(
        frame.index,
        pd.DatetimeIndex,
    ):
        index = pd.DatetimeIndex(
            pd.to_datetime(
                frame.index,
                utc=True,
            )
        )
    elif "bar_open_time" in frame.columns:
        index = pd.DatetimeIndex(
            pd.to_datetime(
                frame["bar_open_time"],
                utc=True,
                errors="raise",
            )
        )
    else:
        raise AmsV3MtfDataError(
            "Data must use a DatetimeIndex or bar_open_time."
        )

    if index.has_duplicates:
        raise AmsV3MtfDataError(
            "Time index contains duplicate bars."
        )

    return index


def resample_complete_ohlcv(
    four_hour_frame: pd.DataFrame,
    *,
    rule: str,
    expected_bars: int,
) -> pd.DataFrame:
    _require_columns(
        four_hour_frame,
        (
            "open",
            "high",
            "low",
            "close",
        ),
    )

    if expected_bars <= 0:
        raise AmsV3MtfParameterError(
            "expected_bars must be positive."
        )

    index = _utc_index(
        four_hour_frame
    )

    ordered = four_hour_frame.copy()
    ordered.index = index
    ordered = ordered.sort_index()

    aggregations: dict[str, str] = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }

    if "volume" in ordered.columns:
        aggregations["volume"] = "sum"

    grouped = ordered.resample(
        rule,
        origin="start_day",
        closed="left",
        label="right",
    )

    counts = grouped["close"].count()

    result: pd.DataFrame = grouped.agg(
        cast(
            Any,
            aggregations,
        )
    )

    result = result.loc[
        counts.eq(expected_bars)
    ].dropna(
        subset=[
            "open",
            "high",
            "low",
            "close",
        ]
    )

    result.index.name = "bar_close_time"

    return result


def build_timeframes_from_four_hour(
    four_hour_frame: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    index = _utc_index(
        four_hour_frame
    )

    frame_4h = four_hour_frame.copy()
    frame_4h.index = (
        index
        + pd.Timedelta(
            hours=4
        )
    )
    frame_4h.index.name = "bar_close_time"
    frame_4h = frame_4h.sort_index()

    frame_8h = resample_complete_ohlcv(
        four_hour_frame,
        rule="8h",
        expected_bars=2,
    )

    frame_1d = resample_complete_ohlcv(
        four_hour_frame,
        rule="1D",
        expected_bars=6,
    )

    return {
        "4h": frame_4h,
        "8h": frame_8h,
        "1d": frame_1d,
    }


def exponential_moving_average(
    values: pd.Series,
    span: int,
) -> pd.Series:
    if span <= 0:
        raise AmsV3MtfParameterError(
            "EMA span must be positive."
        )

    return values.ewm(
        span=span,
        adjust=False,
        min_periods=span,
    ).mean()


def true_range(
    frame: pd.DataFrame,
) -> pd.Series:
    _require_columns(
        frame,
        (
            "high",
            "low",
            "close",
        ),
    )

    high = _numeric(
        frame,
        "high",
    )
    low = _numeric(
        frame,
        "low",
    )
    close = _numeric(
        frame,
        "close",
    )

    previous_close = close.shift(1)

    components = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    )

    return components.max(
        axis=1
    ).astype("float64")


def average_true_range(
    frame: pd.DataFrame,
    period: int,
) -> pd.Series:
    if period <= 0:
        raise AmsV3MtfParameterError(
            "ATR period must be positive."
        )

    return true_range(
        frame
    ).ewm(
        alpha=1.0 / period,
        adjust=False,
        min_periods=period,
    ).mean()


def average_directional_index(
    frame: pd.DataFrame,
    period: int,
) -> pd.Series:
    if period <= 0:
        raise AmsV3MtfParameterError(
            "ADX period must be positive."
        )

    _require_columns(
        frame,
        (
            "high",
            "low",
            "close",
        ),
    )

    high = _numeric(
        frame,
        "high",
    )
    low = _numeric(
        frame,
        "low",
    )

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where(
            (up_move > down_move)
            & (up_move > 0.0),
            up_move,
            0.0,
        ),
        index=frame.index,
        dtype="float64",
    )

    minus_dm = pd.Series(
        np.where(
            (down_move > up_move)
            & (down_move > 0.0),
            down_move,
            0.0,
        ),
        index=frame.index,
        dtype="float64",
    )

    atr_value = average_true_range(
        frame,
        period,
    )

    plus_di = (
        100.0
        * plus_dm.ewm(
            alpha=1.0 / period,
            adjust=False,
            min_periods=period,
        ).mean()
        / atr_value
    )

    minus_di = (
        100.0
        * minus_dm.ewm(
            alpha=1.0 / period,
            adjust=False,
            min_periods=period,
        ).mean()
        / atr_value
    )

    denominator = (
        plus_di
        + minus_di
    ).replace(
        0.0,
        np.nan,
    )

    dx = (
        100.0
        * (
            plus_di
            - minus_di
        ).abs()
        / denominator
    )

    return dx.ewm(
        alpha=1.0 / period,
        adjust=False,
        min_periods=period,
    ).mean()


def realized_volatility(
    close: pd.Series,
    *,
    period: int,
    annualization: float,
) -> pd.Series:
    if (
        period <= 1
        or annualization <= 0.0
    ):
        raise AmsV3MtfParameterError(
            "Volatility inputs are invalid."
        )

    price_ratio = (
        close
        / close.shift(
            1
        )
    )

    log_returns = pd.Series(
        np.log(
            price_ratio.to_numpy(
                dtype=np.float64
            )
        ),
        index=close.index,
        dtype="float64",
    )

    rolling_volatility = (
        log_returns.rolling(
            period,
            min_periods=period,
        ).std(
            ddof=1
        )
    )

    result = (
        rolling_volatility
        * math.sqrt(
            annualization
        )
    )

    return pd.Series(
        result,
        index=close.index,
        dtype="float64",
    )


def classify_fibonacci_ratio(
    ratio: float,
    parameters: MtfFibonacciParameters,
) -> FibonacciZone:
    if not math.isfinite(ratio):
        return FibonacciZone.NO_ACTIVE_IMPULSE

    if ratio < 0.0:
        return FibonacciZone.EXTENSION

    if ratio < parameters.fibonacci_minor:
        return FibonacciZone.MINOR

    if ratio < parameters.fibonacci_shallow:
        return FibonacciZone.SHALLOW

    if ratio <= parameters.fibonacci_core:
        return FibonacciZone.CORE

    if ratio <= parameters.fibonacci_deep:
        return FibonacciZone.DEEP

    return FibonacciZone.INVALIDATED


def causal_fibonacci_state(
    frame: pd.DataFrame,
    parameters: MtfFibonacciParameters,
) -> pd.DataFrame:
    parameters.validate()

    _require_columns(
        frame,
        (
            "high",
            "low",
            "close",
        ),
    )

    high = _numeric(
        frame,
        "high",
    )
    low = _numeric(
        frame,
        "low",
    )
    close = _numeric(
        frame,
        "close",
    )

    window = (
        parameters.pivot_left_bars
        + parameters.pivot_right_bars
        + 1
    )

    rolling_high = high.rolling(
        window,
        center=True,
        min_periods=window,
    ).max()

    rolling_low = low.rolling(
        window,
        center=True,
        min_periods=window,
    ).min()

    candidate_high = high.eq(
        rolling_high
    )

    candidate_low = low.eq(
        rolling_low
    )

    confirmed_high = high.where(
        candidate_high
    ).shift(
        parameters.pivot_right_bars
    )

    confirmed_low = low.where(
        candidate_low
    ).shift(
        parameters.pivot_right_bars
    )

    active_low: float | None = None
    active_high: float | None = None

    impulse_low_values: list[float] = []
    impulse_high_values: list[float] = []
    retracement_values: list[float] = []
    zone_values: list[str] = []

    for (
        confirmed_low_value,
        confirmed_high_value,
        close_value,
    ) in zip(
        confirmed_low.to_numpy(),
        confirmed_high.to_numpy(),
        close.to_numpy(),
        strict=True,
    ):
        if math.isfinite(
            float(
                confirmed_low_value
            )
        ):
            active_low = float(
                confirmed_low_value
            )
            active_high = None

        if (
            math.isfinite(
                float(
                    confirmed_high_value
                )
            )
            and active_low is not None
            and float(
                confirmed_high_value
            )
            > active_low
        ):
            active_high = float(
                confirmed_high_value
            )

        if (
            active_low is None
            or active_high is None
            or active_high <= active_low
        ):
            impulse_low_values.append(
                math.nan
            )
            impulse_high_values.append(
                math.nan
            )
            retracement_values.append(
                math.nan
            )
            zone_values.append(
                FibonacciZone
                .NO_ACTIVE_IMPULSE
                .value
            )
            continue

        ratio = (
            active_high
            - float(
                close_value
            )
        ) / (
            active_high
            - active_low
        )

        zone = classify_fibonacci_ratio(
            ratio,
            parameters,
        )

        impulse_low_values.append(
            active_low
        )
        impulse_high_values.append(
            active_high
        )
        retracement_values.append(
            ratio
        )
        zone_values.append(
            zone.value
        )

    return pd.DataFrame(
        {
            "confirmed_swing_low": (
                confirmed_low
            ),
            "confirmed_swing_high": (
                confirmed_high
            ),
            "active_impulse_low": (
                impulse_low_values
            ),
            "active_impulse_high": (
                impulse_high_values
            ),
            "fibonacci_retracement": (
                retracement_values
            ),
            "fibonacci_zone": (
                zone_values
            ),
        },
        index=frame.index,
    )


def fibonacci_extension_price(
    *,
    impulse_low: float,
    impulse_high: float,
    extension_ratio: float,
) -> float:
    values = (
        impulse_low,
        impulse_high,
        extension_ratio,
    )

    if not all(
        math.isfinite(value)
        for value in values
    ):
        return math.nan

    if (
        impulse_high <= impulse_low
        or extension_ratio <= 1.0
    ):
        raise AmsV3MtfParameterError(
            "Invalid Fibonacci extension inputs."
        )

    return (
        impulse_low
        + extension_ratio
        * (
            impulse_high
            - impulse_low
        )
    )


def build_daily_risk_features(
    frame: pd.DataFrame,
    *,
    breadth: pd.Series | None = None,
    parameters: MtfFibonacciParameters | None = None,
) -> pd.DataFrame:
    params = (
        parameters
        or MtfFibonacciParameters()
    )
    params.validate()

    _require_columns(
        frame,
        (
            "open",
            "high",
            "low",
            "close",
        ),
    )

    result = frame.copy()

    close = _numeric(
        result,
        "close",
    )

    result["daily_ema_fast"] = (
        exponential_moving_average(
            close,
            params.daily_ema_fast,
        )
    )

    result["daily_ema_slow"] = (
        exponential_moving_average(
            close,
            params.daily_ema_slow,
        )
    )

    result["daily_ema_fast_slope"] = (
        result[
            "daily_ema_fast"
        ].diff(
            5
        )
    )

    result["daily_adx"] = (
        average_directional_index(
            result,
            params.daily_adx_period,
        )
    )

    result["daily_volatility_fast"] = (
        realized_volatility(
            close,
            period=(
                params.daily_volatility_fast
            ),
            annualization=365.0,
        )
    )

    result["daily_volatility_slow"] = (
        realized_volatility(
            close,
            period=(
                params.daily_volatility_slow
            ),
            annualization=365.0,
        )
    )

    result["daily_volatility_ratio"] = (
        result[
            "daily_volatility_fast"
        ]
        / result[
            "daily_volatility_slow"
        ]
    )

    if breadth is None:
        breadth_value = pd.Series(
            0.50,
            index=result.index,
            dtype="float64",
        )
    else:
        breadth_value = pd.to_numeric(
            breadth.reindex(
                result.index
            ),
            errors="coerce",
        ).ffill().fillna(
            0.50
        )

    result["market_breadth"] = (
        breadth_value
    )

    fibonacci = causal_fibonacci_state(
        result,
        params,
    )

    for column in fibonacci.columns:
        result[column] = fibonacci[
            column
        ]

    regimes: list[str] = []
    multipliers: list[float] = []

    daily_close_values = _numeric(
        result,
        "close",
    ).to_numpy(
        dtype=np.float64
    )

    daily_ema_fast_values = _numeric(
        result,
        "daily_ema_fast",
    ).to_numpy(
        dtype=np.float64
    )

    daily_ema_slow_values = _numeric(
        result,
        "daily_ema_slow",
    ).to_numpy(
        dtype=np.float64
    )

    daily_ema_slope_values = _numeric(
        result,
        "daily_ema_fast_slope",
    ).to_numpy(
        dtype=np.float64
    )

    daily_adx_values = _numeric(
        result,
        "daily_adx",
    ).to_numpy(
        dtype=np.float64
    )

    daily_volatility_ratio_values = _numeric(
        result,
        "daily_volatility_ratio",
    ).to_numpy(
        dtype=np.float64
    )

    daily_breadth_values = _numeric(
        result,
        "market_breadth",
    ).to_numpy(
        dtype=np.float64
    )

    daily_fibonacci_zone_values = [
        str(value)
        for value in result[
            "fibonacci_zone"
        ].tolist()
    ]

    for (
        raw_close,
        raw_ema_fast,
        raw_ema_slow,
        raw_ema_slope,
        raw_adx,
        raw_volatility_ratio,
        raw_breadth,
        raw_fibonacci_zone,
    ) in zip(
        daily_close_values,
        daily_ema_fast_values,
        daily_ema_slow_values,
        daily_ema_slope_values,
        daily_adx_values,
        daily_volatility_ratio_values,
        daily_breadth_values,
        daily_fibonacci_zone_values,
        strict=True,
    ):
        close_value = float(
            raw_close
        )

        ema_fast_value = float(
            raw_ema_fast
        )

        ema_slow_value = float(
            raw_ema_slow
        )

        ema_slope_value = float(
            raw_ema_slope
        )

        adx_value = float(
            raw_adx
        )

        volatility_ratio_value = float(
            raw_volatility_ratio
        )

        breadth_scalar = float(
            raw_breadth
        )

        indicators = (
            ema_fast_value,
            ema_slow_value,
            ema_slope_value,
            adx_value,
            volatility_ratio_value,
            breadth_scalar,
        )

        if not all(
            math.isfinite(value)
            for value in indicators
        ):
            regime = DailyRegime.CASH
        elif (
            close_value
            > ema_fast_value
            > ema_slow_value
            and ema_slope_value > 0.0
            and adx_value
            >= params.daily_adx_full_risk
            and breadth_scalar
            >= params.daily_breadth_full_risk
            and volatility_ratio_value
            <= params.daily_max_volatility_ratio
        ):
            regime = DailyRegime.FULL_RISK
        elif (
            close_value > ema_slow_value
            and ema_fast_value
            >= ema_slow_value
            and ema_slope_value >= 0.0
        ):
            regime = DailyRegime.REDUCED_RISK
        elif (
            close_value
            >= 0.97 * ema_slow_value
        ):
            regime = DailyRegime.DEFENSIVE
        else:
            regime = DailyRegime.CASH

        zone = FibonacciZone(
            raw_fibonacci_zone
        )

        if zone is FibonacciZone.INVALIDATED:
            fibonacci_modifier = 0.0
        elif zone is FibonacciZone.DEEP:
            fibonacci_modifier = 0.70
        elif zone is FibonacciZone.EXTENSION:
            fibonacci_modifier = 0.80
        elif (
            zone
            is FibonacciZone.NO_ACTIVE_IMPULSE
        ):
            fibonacci_modifier = 0.75
        else:
            fibonacci_modifier = 1.0

        regimes.append(
            regime.value
        )

        multipliers.append(
            DAILY_RISK_MULTIPLIERS[
                regime
            ]
            * fibonacci_modifier
        )

    result["daily_regime"] = regimes
    result["daily_risk_multiplier"] = (
        multipliers
    )

    return result


def build_eight_hour_allocation_features(
    frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame,
    *,
    parameters: MtfFibonacciParameters | None = None,
) -> pd.DataFrame:
    params = (
        parameters
        or MtfFibonacciParameters()
    )
    params.validate()

    _require_columns(
        frame,
        (
            "open",
            "high",
            "low",
            "close",
        ),
    )

    _require_columns(
        benchmark_frame,
        (
            "close",
        ),
    )

    result = frame.copy()

    close = _numeric(
        result,
        "close",
    )

    benchmark_close = pd.to_numeric(
        benchmark_frame[
            "close"
        ].reindex(
            result.index
        ),
        errors="coerce",
    ).ffill()

    result["eight_hour_ema_fast"] = (
        exponential_moving_average(
            close,
            params.eight_hour_ema_fast,
        )
    )

    result["eight_hour_ema_slow"] = (
        exponential_moving_average(
            close,
            params.eight_hour_ema_slow,
        )
    )

    result["eight_hour_atr"] = (
        average_true_range(
            result,
            params.eight_hour_atr_period,
        )
    )

    result["relative_strength_vs_benchmark"] = (
        close.pct_change(
            params.eight_hour_relative_strength_period
        )
        - benchmark_close.pct_change(
            params.eight_hour_relative_strength_period
        )
    )

    result["distance_from_fast_ema_atr"] = (
        close
        - result[
            "eight_hour_ema_fast"
        ]
    ) / result[
        "eight_hour_atr"
    ]

    fibonacci = causal_fibonacci_state(
        result,
        params,
    )

    for column in fibonacci.columns:
        result[column] = fibonacci[
            column
        ]

    states: list[str] = []
    multipliers: list[float] = []

    eight_close_values = _numeric(
        result,
        "close",
    ).to_numpy(
        dtype=np.float64
    )

    eight_ema_fast_values = _numeric(
        result,
        "eight_hour_ema_fast",
    ).to_numpy(
        dtype=np.float64
    )

    eight_ema_slow_values = _numeric(
        result,
        "eight_hour_ema_slow",
    ).to_numpy(
        dtype=np.float64
    )

    eight_atr_values = _numeric(
        result,
        "eight_hour_atr",
    ).to_numpy(
        dtype=np.float64
    )

    eight_relative_strength_values = _numeric(
        result,
        "relative_strength_vs_benchmark",
    ).to_numpy(
        dtype=np.float64
    )

    eight_extension_values = _numeric(
        result,
        "distance_from_fast_ema_atr",
    ).to_numpy(
        dtype=np.float64
    )

    eight_fibonacci_zone_values = [
        str(value)
        for value in result[
            "fibonacci_zone"
        ].tolist()
    ]

    for (
        raw_close,
        raw_ema_fast,
        raw_ema_slow,
        raw_atr,
        raw_relative_strength,
        raw_extension,
        raw_fibonacci_zone,
    ) in zip(
        eight_close_values,
        eight_ema_fast_values,
        eight_ema_slow_values,
        eight_atr_values,
        eight_relative_strength_values,
        eight_extension_values,
        eight_fibonacci_zone_values,
        strict=True,
    ):
        close_value = float(
            raw_close
        )

        ema_fast_value = float(
            raw_ema_fast
        )

        ema_slow_value = float(
            raw_ema_slow
        )

        atr_value = float(
            raw_atr
        )

        relative_strength_value = float(
            raw_relative_strength
        )

        extension_value = float(
            raw_extension
        )

        indicators = (
            ema_fast_value,
            ema_slow_value,
            atr_value,
            relative_strength_value,
            extension_value,
        )

        if not all(
            math.isfinite(value)
            for value in indicators
        ):
            state = EightHourState.ADVERSE
        elif (
            extension_value
            > params.eight_hour_overextension_atr
        ):
            state = (
                EightHourState.OVEREXTENDED
            )
        elif (
            close_value
            > ema_fast_value
            > ema_slow_value
            and relative_strength_value > 0.0
        ):
            state = EightHourState.ALIGNED
        elif (
            close_value > ema_slow_value
            and ema_fast_value
            >= ema_slow_value
        ):
            state = (
                EightHourState
                .PARTIALLY_ALIGNED
            )
        elif (
            close_value < ema_slow_value
            or relative_strength_value < -0.05
        ):
            state = EightHourState.ADVERSE
        else:
            state = EightHourState.MIXED

        zone = FibonacciZone(
            raw_fibonacci_zone
        )

        multiplier = (
            EIGHT_HOUR_ALLOCATION_MULTIPLIERS[
                state
            ]
            * FIBONACCI_ALLOCATION_MULTIPLIERS[
                zone
            ]
        )

        states.append(
            state.value
        )

        multipliers.append(
            multiplier
        )

    result["eight_hour_state"] = states

    result[
        "eight_hour_allocation_multiplier"
    ] = multipliers

    return result


def build_four_hour_execution_features(
    frame: pd.DataFrame,
    *,
    parameters: MtfFibonacciParameters | None = None,
) -> pd.DataFrame:
    params = (
        parameters
        or MtfFibonacciParameters()
    )
    params.validate()

    _require_columns(
        frame,
        (
            "open",
            "high",
            "low",
            "close",
        ),
    )

    result = frame.copy()

    open_value = _numeric(
        result,
        "open",
    )
    high = _numeric(
        result,
        "high",
    )
    close = _numeric(
        result,
        "close",
    )

    result["four_hour_ema"] = (
        exponential_moving_average(
            close,
            params.four_hour_ema_period,
        )
    )

    result["four_hour_atr"] = (
        average_true_range(
            result,
            params.four_hour_atr_period,
        )
    )

    result["donchian_breakout_level"] = (
        high.rolling(
            params.four_hour_donchian_period,
            min_periods=(
                params.four_hour_donchian_period
            ),
        ).max().shift(
            1
        )
    )

    range_value = true_range(
        result
    )

    result["atr_compression_ratio"] = (
        result[
            "four_hour_atr"
        ]
        / result[
            "four_hour_atr"
        ].rolling(
            params.four_hour_compression_period,
            min_periods=(
                params.four_hour_compression_period
            ),
        ).median()
    )

    fibonacci = causal_fibonacci_state(
        result,
        params,
    )

    for column in fibonacci.columns:
        result[column] = fibonacci[
            column
        ]

    breakout_signal = (
        close
        > result[
            "donchian_breakout_level"
        ]
    ) & (
        range_value
        > result[
            "four_hour_atr"
        ].shift(
            1
        )
        * params.four_hour_expansion_multiple
    ) & (
        close
        > result[
            "four_hour_ema"
        ]
    )

    fibonacci_pullback_zone = (
        result[
            "fibonacci_zone"
        ].isin(
            [
                FibonacciZone.SHALLOW.value,
                FibonacciZone.CORE.value,
                FibonacciZone.DEEP.value,
            ]
        )
    )

    reacceleration = (
        close
        > high.shift(
            1
        )
    ) & (
        close
        > open_value
    ) & (
        close
        > result[
            "four_hour_ema"
        ]
    )

    fibonacci_signal = (
        fibonacci_pullback_zone
        & reacceleration
    )

    setup_kind = np.select(
        [
            breakout_signal,
            fibonacci_signal,
        ],
        [
            FourHourSetup.BREAKOUT.value,
            (
                FourHourSetup
                .FIBONACCI_PULLBACK
                .value
            ),
        ],
        default=FourHourSetup.NONE.value,
    )

    setup_valid = (
        breakout_signal
        | fibonacci_signal
    )

    atr_stop = (
        close
        - params.four_hour_initial_stop_atr
        * result[
            "four_hour_atr"
        ]
    )

    structural_stop = (
        result[
            "active_impulse_low"
        ]
        - 0.25
        * result[
            "four_hour_atr"
        ]
    )

    initial_stop = pd.Series(
        np.where(
            structural_stop.notna(),
            np.maximum(
                atr_stop,
                structural_stop,
            ),
            atr_stop,
        ),
        index=result.index,
        dtype="float64",
    )

    impulse_range = (
        result[
            "active_impulse_high"
        ]
        - result[
            "active_impulse_low"
        ]
    )

    result["four_hour_setup"] = (
        setup_kind
    )

    result["four_hour_setup_valid"] = (
        setup_valid
        & initial_stop.lt(
            close
        )
    )

    result["initial_stop_price"] = (
        initial_stop
    )

    result["trailing_stop_distance"] = (
        params.four_hour_trailing_stop_atr
        * result[
            "four_hour_atr"
        ]
    )

    result["fibonacci_target_1272"] = (
        result[
            "active_impulse_low"
        ]
        + params.fibonacci_extension_one
        * impulse_range
    )

    result["fibonacci_target_1618"] = (
        result[
            "active_impulse_low"
        ]
        + params.fibonacci_extension_two
        * impulse_range
    )

    return result


def calculate_final_risk_fraction(
    *,
    base_risk_fraction: float,
    daily_multiplier: float,
    eight_hour_multiplier: float,
    volatility_adjustment: float,
    portfolio_heat_adjustment: float,
) -> float:
    values = (
        base_risk_fraction,
        daily_multiplier,
        eight_hour_multiplier,
        volatility_adjustment,
        portfolio_heat_adjustment,
    )

    if not all(
        math.isfinite(value)
        for value in values
    ):
        raise AmsV3MtfParameterError(
            "Risk inputs must be finite."
        )

    if base_risk_fraction < 0.0:
        raise AmsV3MtfParameterError(
            "Base risk may not be negative."
        )

    multipliers = values[1:]

    if any(
        value < 0.0
        or value > 1.0
        for value in multipliers
    ):
        raise AmsV3MtfParameterError(
            "Risk multipliers must be between zero and one."
        )

    return (
        base_risk_fraction
        * daily_multiplier
        * eight_hour_multiplier
        * volatility_adjustment
        * portfolio_heat_adjustment
    )


def compose_multitimeframe_execution_state(
    four_hour_features: pd.DataFrame,
    daily_features: pd.DataFrame,
    eight_hour_features: pd.DataFrame,
    *,
    base_risk_fraction: float = 0.01,
) -> pd.DataFrame:
    required_four = (
        "four_hour_setup_valid",
        "four_hour_setup",
        "initial_stop_price",
    )

    required_daily = (
        "daily_regime",
        "daily_risk_multiplier",
    )

    required_eight = (
        "eight_hour_state",
        "eight_hour_allocation_multiplier",
    )

    _require_columns(
        four_hour_features,
        required_four,
    )

    _require_columns(
        daily_features,
        required_daily,
    )

    _require_columns(
        eight_hour_features,
        required_eight,
    )

    execution = four_hour_features.copy()
    execution.index = pd.to_datetime(
        execution.index,
        utc=True,
    )
    execution = execution.sort_index()

    daily = daily_features.loc[
        :,
        list(
            required_daily
        ),
    ].copy()

    daily.index = pd.to_datetime(
        daily.index,
        utc=True,
    )

    eight = eight_hour_features.loc[
        :,
        list(
            required_eight
        ),
    ].copy()

    eight.index = pd.to_datetime(
        eight.index,
        utc=True,
    )

    execution_reset = (
        execution.reset_index()
    )

    execution_reset = (
        execution_reset.rename(
            columns={
                execution_reset.columns[0]:
                    "bar_close_time"
            }
        )
    )

    daily_reset = daily.reset_index()
    daily_reset = daily_reset.rename(
        columns={
            daily_reset.columns[0]:
                "bar_close_time"
        }
    )

    eight_reset = eight.reset_index()
    eight_reset = eight_reset.rename(
        columns={
            eight_reset.columns[0]:
                "bar_close_time"
        }
    )

    combined = pd.merge_asof(
        execution_reset.sort_values(
            "bar_close_time"
        ),
        daily_reset.sort_values(
            "bar_close_time"
        ),
        on="bar_close_time",
        direction="backward",
        allow_exact_matches=True,
    )

    combined = pd.merge_asof(
        combined.sort_values(
            "bar_close_time"
        ),
        eight_reset.sort_values(
            "bar_close_time"
        ),
        on="bar_close_time",
        direction="backward",
        allow_exact_matches=True,
    )

    combined[
        "daily_risk_multiplier"
    ] = combined[
        "daily_risk_multiplier"
    ].fillna(
        0.0
    )

    combined[
        "eight_hour_allocation_multiplier"
    ] = combined[
        "eight_hour_allocation_multiplier"
    ].fillna(
        0.0
    )

    combined[
        "position_risk_fraction"
    ] = (
        base_risk_fraction
        * combined[
            "daily_risk_multiplier"
        ]
        * combined[
            "eight_hour_allocation_multiplier"
        ]
    )

    combined[
        "entry_allowed"
    ] = (
        combined[
            "four_hour_setup_valid"
        ].astype(
            bool
        )
        & combined[
            "position_risk_fraction"
        ].gt(
            0.0
        )
    )

    return combined.set_index(
        "bar_close_time"
    )


def _parameter_hash(
    payload: Mapping[str, Any],
) -> str:
    encoded = json.dumps(
        dict(
            payload
        ),
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        allow_nan=False,
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        encoded
    ).hexdigest()


def build_ams_v3_configuration_grid() -> tuple[
    dict[str, Any],
    ...,
]:
    fibonacci_modes = (
        "NO_FIBONACCI_CONTROL",
        "CORE_382_618",
        "SHALLOW_236_500",
        "DEEP_500_786",
    )

    daily_risk_profiles = (
        "BALANCED",
        "DEFENSIVE",
    )

    trigger_modes = (
        "BREAKOUT",
        "PULLBACK_REACCELERATION",
    )

    configurations: list[
        dict[str, Any]
    ] = []

    sequence = 1

    for fibonacci_mode in fibonacci_modes:
        for daily_risk_profile in daily_risk_profiles:
            for trigger_mode in trigger_modes:
                configuration_id = (
                    "AMS-V3-F01-C"
                    f"{sequence:02d}"
                )

                parameters = {
                    "fibonacci_mode": fibonacci_mode,
                    "daily_risk_profile": (
                        daily_risk_profile
                    ),
                    "trigger_mode": trigger_mode,
                    "daily_timeframe": "1D",
                    "allocation_timeframe": "8H",
                    "execution_timeframe": "4H",
                    "spot_long_only": True,
                    "leverage_allowed": False,
                    "borrowing_allowed": False,
                    "base_transaction_cost": 0.002,
                    "stress_transaction_cost": 0.004,
                }

                configurations.append(
                    {
                        "configuration_id": (
                            configuration_id
                        ),
                        "family_id": (
                            "AMS-V3-F01"
                        ),
                        "family": (
                            "MULTI_TIMEFRAME_"
                            "FIBONACCI_TREND"
                        ),
                        "parameters": parameters,
                        "parameter_hash_sha256": (
                            _parameter_hash(
                                parameters
                            )
                        ),
                        "trial_status": (
                            "REGISTERED_NOT_EXECUTED"
                        ),
                        "fold_results": [],
                        "aggregate_result": None,
                    }
                )

                sequence += 1

    if len(
        configurations
    ) != 16:
        raise RuntimeError(
            "AMS V3 grid must contain 16 configurations."
        )

    return tuple(
        configurations
    )


def build_ams_v3_experiment_ledger(
    *,
    source_commit: str,
) -> dict[str, Any]:
    configurations = list(
        build_ams_v3_configuration_grid()
    )

    portfolio_profiles = [
        {
            "profile_id": (
                "AMS-V3-PORTFOLIO-P01"
            ),
            "name": "CONSERVATIVE",
            "maximum_positions": 2,
            "base_risk_fraction": 0.005,
            "maximum_portfolio_heat": 0.015,
            "status": "REGISTERED_NOT_EXECUTED",
        },
        {
            "profile_id": (
                "AMS-V3-PORTFOLIO-P02"
            ),
            "name": "BALANCED",
            "maximum_positions": 3,
            "base_risk_fraction": 0.0075,
            "maximum_portfolio_heat": 0.025,
            "status": "REGISTERED_NOT_EXECUTED",
        },
        {
            "profile_id": (
                "AMS-V3-PORTFOLIO-P03"
            ),
            "name": "AGGRESSIVE",
            "maximum_positions": 4,
            "base_risk_fraction": 0.01,
            "maximum_portfolio_heat": 0.035,
            "status": "REGISTERED_NOT_EXECUTED",
        },
        {
            "profile_id": (
                "AMS-V3-PORTFOLIO-P04"
            ),
            "name": "CORRELATION_REDUCED",
            "maximum_positions": 3,
            "base_risk_fraction": 0.0075,
            "maximum_portfolio_heat": 0.02,
            "status": "REGISTERED_NOT_EXECUTED",
        },
    ]

    return {
        "schema_version": (
            "ams-v3-mtf-fibonacci-ledger-v1"
        ),
        "protocol_id": (
            "AMS-V3-MTF-FIBONACCI"
        ),
        "source_commit": source_commit,
        "research_window": {
            "start": "2021-01-01",
            "end": "2024-12-31",
        },
        "walk_forward_folds": [
            {
                "fold_name": "WF_2022",
                "training_start": "2021-07-20",
                "training_end": "2022-01-01",
                "evaluation_start": "2022-01-01",
                "evaluation_end": "2023-01-01",
            },
            {
                "fold_name": "WF_2023",
                "training_start": "2021-07-20",
                "training_end": "2023-01-01",
                "evaluation_start": "2023-01-01",
                "evaluation_end": "2024-01-01",
            },
            {
                "fold_name": "WF_2024",
                "training_start": "2021-07-20",
                "training_end": "2024-01-01",
                "evaluation_start": "2024-01-01",
                "evaluation_end": "2025-01-01",
            },
        ],
        "trial_accounting": {
            "total_authorized_trials": 20,
            "trials_executed": 0,
            "remaining_authorized_trials": 20,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
        "alpha_configurations": configurations,
        "portfolio_profiles": portfolio_profiles,
        "promotion_gates": {
            "minimum_total_executed_trades": 60,
            "minimum_executed_trades_per_active_fold": 12,
            "maximum_fold_drawdown": 0.45,
            "minimum_aggregate_profit_factor": 1.10,
            "positive_stress_cost_return": True,
            "minimum_passing_folds": 2,
            "latest_fold_must_pass": True,
            "minimum_geometric_monthly_return": 0.08,
            "pbo_maximum": 0.20,
            "dsr_minimum": 0.95,
        },
        "data_gate": {
            "four_hour_dataset_required": True,
            "eight_hour_resampled_from_four_hour": True,
            "daily_resampled_from_four_hour": True,
            "bar_boundaries_utc": True,
            "execution_blocked_until_validated": True,
        },
        "family_decisions": [],
        "ensemble_result": None,
    }
