"""Causal primitives for the RD05 P2 symbol-time panel.

This module deliberately builds features and labels only.  It never ranks a
signal, evaluates prediction, or simulates a portfolio.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import sqrt
from typing import Final

import numpy as np
import numpy.typing as npt
import pandas as pd

from spotbot.research.rd05_protocol_registration import SIGNAL_VARIANTS

SIGNAL_IDS: Final[tuple[str, ...]] = tuple(item.signal_id for item in SIGNAL_VARIANTS)
LABEL_IDS: Final[tuple[str, ...]] = (
    "FORWARD_1D_RETURN",
    "FORWARD_3D_RETURN",
    "FORWARD_7D_CLOSE_TO_CLOSE_RETURN",
    "FORWARD_14D_RETURN",
    "FORWARD_28D_RETURN",
    "FORWARD_7D_MAX_FAVOURABLE_EXCURSION",
    "FORWARD_7D_MAX_ADVERSE_EXCURSION",
)
REGIME_IDS: Final[tuple[str, ...]] = (
    "BTC_TREND_STATE",
    "BTC_REALIZED_VOLATILITY_TERCILE",
    "CROSS_SECTIONAL_DISPERSION_TERCILE",
    "AVERAGE_PAIRWISE_CORRELATION_TERCILE",
    "MARKET_BREADTH_TERCILE",
    "PIT_UNIVERSE_SIZE_TERCILE",
)
RESEARCH_LOCK: Final[pd.Timestamp] = pd.Timestamp("2025-01-01T00:00:00Z")
FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class ComputedValue:
    """A finite calculated value or a machine-readable reason for absence."""

    value: float | None
    missing_reason: str

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class MarketReturnRecord:
    daily_timestamp: pd.Timestamp
    membership_snapshot_time: pd.Timestamp | None
    eligible_member_count: int
    valid_return_count: int
    market_return: float | None
    missing_reason: str


def canonical_json_hash(payload: str) -> str:
    """Return the SHA256 digest used in deterministic lineage records."""

    return sha256(payload.encode("utf-8")).hexdigest()


def finite_or_missing(value: float, reason: str) -> ComputedValue:
    """Accept finite values only; numerical sentinels are never propagated."""

    if np.isfinite(value):
        return ComputedValue(float(value), "")
    return ComputedValue(None, reason)


def safe_ratio(numerator: float, denominator: float, reason: str) -> ComputedValue:
    """Divide only finite values by a finite non-zero denominator."""

    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator == 0.0:
        return ComputedValue(None, reason)
    return finite_or_missing(numerator / denominator, reason)


def sample_std_or_missing(values: Sequence[float], reason: str) -> ComputedValue:
    """Return sample standard deviation without NumPy warning paths."""

    array = np.asarray(values, dtype=float)
    if array.size < 2 or not np.isfinite(array).all():
        return ComputedValue(None, reason)
    value = float(np.std(array, ddof=1))
    if value <= 0.0 or not np.isfinite(value):
        return ComputedValue(None, reason)
    return ComputedValue(value, "")


def safe_correlation(left: Sequence[float], right: Sequence[float]) -> ComputedValue:
    """Pearson correlation that refuses constants and avoids runtime warnings."""

    x = np.asarray(left, dtype=float)
    y = np.asarray(right, dtype=float)
    if x.size < 2 or y.size != x.size or not np.isfinite(x).all() or not np.isfinite(y).all():
        return ComputedValue(None, "INSUFFICIENT_PAIRED_OBSERVATIONS")
    x_centered = x - float(np.mean(x))
    y_centered = y - float(np.mean(y))
    denominator = float(np.sqrt(np.dot(x_centered, x_centered) * np.dot(y_centered, y_centered)))
    if denominator <= 0.0 or not np.isfinite(denominator):
        return ComputedValue(None, "CONSTANT_INPUT")
    return finite_or_missing(
        float(np.dot(x_centered, y_centered) / denominator), "UNDEFINED_CORRELATION"
    )


def safe_ols(asset: pd.Series, benchmark: pd.Series) -> tuple[np.ndarray | None, str]:
    """Fit a causal intercept OLS using the latest 84 valid paired returns."""

    joined = pd.concat((asset.rename("asset"), benchmark.rename("benchmark")), axis=1, sort=False)
    joined = joined.replace([np.inf, -np.inf], np.nan).dropna().tail(84)
    if len(joined) < 60:
        return None, "INSUFFICIENT_PAIRED_OBSERVATIONS"
    y = joined["asset"].to_numpy(dtype=float)
    x_value = joined["benchmark"].to_numpy(dtype=float)
    design = np.column_stack((np.ones(len(joined), dtype=float), x_value))
    if np.linalg.matrix_rank(design) < 2:
        return None, "CONSTANT_BENCHMARK"
    coefficients, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ coefficients
    if not np.isfinite(residuals).all():
        return None, "NONFINITE_OLS_RESIDUAL"
    return residuals, ""


def wilder_atr(frame: pd.DataFrame) -> pd.Series:
    """Wilder ATR14, retaining missing values until fourteen complete periods."""

    previous_close = frame["close"].shift(1)
    candidates = pd.concat(
        (
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ),
        axis=1,
    )
    true_range = candidates.max(axis=1)
    return true_range.ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()


def wilder_rsi(close: pd.Series) -> ComputedValue:
    """Calculate RSI14 with the frozen explicit zero-gain/loss conventions."""

    if len(close) < 15:
        return ComputedValue(None, "INSUFFICIENT_RSI_HISTORY")
    delta = close.diff()
    average_gain = delta.clip(lower=0.0).ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    average_loss = (
        (-delta.clip(upper=0.0)).ewm(alpha=1.0 / 14.0, adjust=False, min_periods=14).mean()
    )
    gain = float(average_gain.iloc[-1])
    loss = float(average_loss.iloc[-1])
    if not np.isfinite(gain) or not np.isfinite(loss):
        return ComputedValue(None, "INVALID_RSI_INPUT")
    if gain == 0.0 and loss == 0.0:
        return ComputedValue(50.0, "")
    if loss == 0.0:
        return ComputedValue(100.0, "")
    if gain == 0.0:
        return ComputedValue(0.0, "")
    return finite_or_missing(100.0 - 100.0 / (1.0 + gain / loss), "INVALID_RSI_INPUT")


def close_return(close: pd.Series, days: int) -> ComputedValue:
    """Return the close-to-close return over an exactly registered distance."""

    if len(close) <= days:
        return ComputedValue(None, "INSUFFICIENT_CLOSE_HISTORY")
    first = float(close.iloc[-1 - days])
    last = float(close.iloc[-1])
    return (
        safe_ratio(last, first, "INVALID_CLOSE_PRICE")
        if first != 0.0
        else ComputedValue(None, "INVALID_CLOSE_PRICE")
    )


def _return_minus_one(close: pd.Series, days: int) -> ComputedValue:
    value = close_return(close, days)
    if value.value is None:
        return value
    return ComputedValue(value.value - 1.0, "")


def _latest_returns(close: pd.Series) -> pd.Series:
    values = float_array(close)
    logged = np.log(values)
    result = pd.Series(logged, index=close.index, dtype=np.float64)
    return result.diff().replace([np.inf, -np.inf], np.nan)


def float_array(series: pd.Series) -> FloatArray:
    """Convert a numeric pandas boundary to a one-dimensional float64 array."""

    if series.dtype == object:
        raise TypeError("Object dtype is prohibited at the numeric boundary")
    values = np.asarray(series.to_numpy(dtype=np.float64), dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("Expected a one-dimensional numeric series")
    return values


def required_timestamp(value: object, *, field: str) -> pd.Timestamp:
    """Convert a pandas boundary scalar to a timezone-aware UTC timestamp."""

    if value is None:
        raise ValueError(f"{field} is required")
    timestamp = pd.Timestamp(str(value))
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp


def btc_trend_state(close: FloatArray) -> str:
    """Return the frozen BTC 84-day trend state."""

    if close.ndim != 1 or close.size < 84 or not np.isfinite(close[-84:]).all():
        return "INSUFFICIENT_HISTORY"
    latest = float(close[-1])
    average = float(np.mean(close[-84:]))
    if latest > average:
        return "UP"
    if latest < average:
        return "DOWN"
    return "NEUTRAL"


def json_has_only_finite_floats(value: object) -> bool:
    """Recursively reject NaN and infinities before JSON serialization."""

    if isinstance(value, float):
        return bool(np.isfinite(value))
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and json_has_only_finite_floats(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return all(json_has_only_finite_floats(item) for item in value)
    return value is None or isinstance(value, (str, int, bool))


def _residual_score(
    asset_returns: pd.Series, benchmark: pd.Series, standardized: bool
) -> ComputedValue:
    residuals, reason = safe_ols(asset_returns, benchmark)
    if residuals is None:
        return ComputedValue(None, reason)
    if residuals.size < 28:
        return ComputedValue(None, "INSUFFICIENT_RECENT_RESIDUALS")
    total = float(np.sum(residuals[-28:]))
    if not standardized:
        return finite_or_missing(total, "NONFINITE_RESIDUAL_SUM")
    deviation = sample_std_or_missing(residuals.tolist(), "CONSTANT_RESIDUAL")
    if not deviation.available or deviation.value is None:
        return deviation
    return safe_ratio(total, deviation.value * sqrt(28.0), "CONSTANT_RESIDUAL")


def _beta_adjusted_score(asset_returns: pd.Series, btc_returns: pd.Series) -> ComputedValue:
    joined = pd.concat(
        (asset_returns.rename("asset"), btc_returns.rename("btc")), axis=1, sort=False
    )
    joined = joined.replace([np.inf, -np.inf], np.nan).dropna().tail(84)
    if len(joined) < 60:
        return ComputedValue(None, "INSUFFICIENT_PAIRED_OBSERVATIONS")
    y = joined["asset"].to_numpy(dtype=float)
    x_value = joined["btc"].to_numpy(dtype=float)
    design = np.column_stack((np.ones(len(joined), dtype=float), x_value))
    if np.linalg.matrix_rank(design) < 2:
        return ComputedValue(None, "CONSTANT_BTC_RETURN")
    beta = float(np.linalg.lstsq(design, y, rcond=None)[0][1])
    recent = joined.tail(28)
    if len(recent) < 28:
        return ComputedValue(None, "INSUFFICIENT_RECENT_PAIRED_OBSERVATIONS")
    asset_total = float(recent["asset"].sum())
    btc_total = float(recent["btc"].sum())
    return finite_or_missing(asset_total - beta * btc_total, "NONFINITE_BETA_ADJUSTED_SCORE")


def _ols_tstat(close: pd.Series) -> ComputedValue:
    if len(close) < 28:
        return ComputedValue(None, "INSUFFICIENT_TREND_HISTORY")
    y = np.log(close.tail(28).to_numpy(dtype=float))
    x = np.arange(28, dtype=float)
    design = np.column_stack((np.ones(28, dtype=float), x))
    coefficients, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ coefficients
    residual_degrees = len(y) - 2
    if residual_degrees <= 0:
        return ComputedValue(None, "INSUFFICIENT_TREND_HISTORY")
    residual_variance = float(np.dot(residuals, residuals) / residual_degrees)
    x_ss = float(np.dot(x - np.mean(x), x - np.mean(x)))
    if residual_variance <= 0.0 or x_ss <= 0.0:
        return ComputedValue(None, "CONSTANT_TREND_RESIDUAL")
    return finite_or_missing(
        float(coefficients[1] / sqrt(residual_variance / x_ss)), "INVALID_TREND_TSTAT"
    )


def _quote_turnover_score(quote_turnover: pd.Series) -> ComputedValue:
    completed = quote_turnover.replace([np.inf, -np.inf], np.nan).dropna()
    if len(completed) < 180:
        return ComputedValue(None, "INSUFFICIENT_QUOTE_TURNOVER_HISTORY")
    recent = float(completed.iloc[-42:].mean())
    baseline = float(completed.iloc[-180:].mean())
    if not np.isfinite(recent) or not np.isfinite(baseline):
        return ComputedValue(None, "NONFINITE_QUOTE_TURNOVER")
    if baseline <= 0.0:
        return ComputedValue(None, "NONPOSITIVE_QUOTE_TURNOVER_BASELINE")
    return finite_or_missing(recent / baseline - 1.0, "NONFINITE_QUOTE_TURNOVER")


def signal_values(
    history: pd.DataFrame,
    quote_turnover: pd.Series,
    btc_returns: pd.Series,
    market_returns: pd.Series,
    availability_start: pd.Timestamp | None,
    decision_time: pd.Timestamp,
) -> Mapping[str, ComputedValue]:
    """Compute all frozen P2 signal values using only closed causal inputs."""

    close = history["close"].astype(float)
    high = history["high"].astype(float)
    low = history["low"].astype(float)
    volume = history["volume"].astype(float)
    returns = _latest_returns(close)
    atr = wilder_atr(history)
    r1 = _return_minus_one(close, 1)
    r3 = _return_minus_one(close, 3)
    r7 = _return_minus_one(close, 7)
    r28 = _return_minus_one(close, 28)
    r84 = _return_minus_one(close, 84)
    result: dict[str, ComputedValue] = {}
    result["XSM_RETURN_7D"] = r7
    result["XSM_RETURN_28D"] = r28
    result["XSM_RETURN_84D"] = r84
    if len(close) >= 30:
        result["XSM_28D_SKIP_1D"] = finite_or_missing(
            float(close.iloc[-2] / close.iloc[-30] - 1.0), "INVALID_CLOSE_PRICE"
        )
    else:
        result["XSM_28D_SKIP_1D"] = ComputedValue(None, "INSUFFICIENT_CLOSE_HISTORY")
    result["TSM_RETURN_28D"] = r28
    result["TSM_RETURN_84D"] = r84
    ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
    ema50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
    result["EMA_20_50_TREND_STATE"] = finite_or_missing(
        float(ema20.iloc[-1] - ema50.iloc[-1]), "INSUFFICIENT_EMA_HISTORY"
    )
    if r7.value is not None and r28.value is not None and r84.value is not None:
        agreement = (
            float(np.sign(r7.value)) + float(np.sign(r28.value)) + float(np.sign(r84.value))
        ) / 3.0
        result["MULTI_HORIZON_TREND_AGREEMENT"] = ComputedValue(agreement, "")
    else:
        result["MULTI_HORIZON_TREND_AGREEMENT"] = ComputedValue(None, "INSUFFICIENT_CLOSE_HISTORY")
    return_std = sample_std_or_missing(
        returns.dropna().tail(28).tolist(), "INSUFFICIENT_VOLATILITY_HISTORY"
    )
    if (
        return_std.available
        and return_std.value is not None
        and r1.available
        and r1.value is not None
    ):
        result["REVERSAL_1D_VOL_NORMALIZED"] = safe_ratio(
            -r1.value, return_std.value, "ZERO_VOLATILITY"
        )
    else:
        result["REVERSAL_1D_VOL_NORMALIZED"] = ComputedValue(None, return_std.missing_reason)
    if (
        return_std.available
        and return_std.value is not None
        and r3.available
        and r3.value is not None
    ):
        result["REVERSAL_3D_VOL_NORMALIZED"] = safe_ratio(
            -r3.value, return_std.value, "ZERO_VOLATILITY"
        )
    else:
        result["REVERSAL_3D_VOL_NORMALIZED"] = ComputedValue(None, return_std.missing_reason)
    latest_atr = float(atr.iloc[-1])
    if np.isfinite(latest_atr) and latest_atr > 0.0 and np.isfinite(float(ema20.iloc[-1])):
        result["DISTANCE_FROM_EMA20_ATR"] = finite_or_missing(
            -(float(close.iloc[-1]) - float(ema20.iloc[-1])) / latest_atr, "INVALID_ATR"
        )
    else:
        result["DISTANCE_FROM_EMA20_ATR"] = ComputedValue(None, "INVALID_ATR")
    rsi = wilder_rsi(close)
    result["RSI14_OVEREXTENSION"] = (
        ComputedValue(-rsi.value, "") if rsi.available and rsi.value is not None else rsi
    )
    for window, signal_id in ((20, "DONCHIAN_20_POSITION"), (55, "DONCHIAN_55_POSITION")):
        if len(close) < window:
            result[signal_id] = ComputedValue(None, "INSUFFICIENT_DONCHIAN_HISTORY")
            continue
        upper = float(high.iloc[-window:].max())
        lower = float(low.iloc[-window:].min())
        result[signal_id] = safe_ratio(
            float(close.iloc[-1]) - lower, upper - lower, "ZERO_DONCHIAN_RANGE"
        )
    normalized_atr = atr / close
    if len(close) >= 75:
        previous_atr = float(normalized_atr.iloc[-2])
        baseline = float(normalized_atr.iloc[-61:-1].median())
        prior_high = float(high.iloc[-21:-1].max())
        if np.isfinite(previous_atr) and baseline > 0.0 and prior_high > 0.0:
            contraction = max(0.0, 1.0 - previous_atr / baseline)
            breakout = max(0.0, float(close.iloc[-1]) / prior_high - 1.0)
            result["VOLATILITY_CONTRACTION_BREAKOUT"] = ComputedValue(contraction * breakout, "")
        else:
            result["VOLATILITY_CONTRACTION_BREAKOUT"] = ComputedValue(None, "INVALID_ATR")
    else:
        result["VOLATILITY_CONTRACTION_BREAKOUT"] = ComputedValue(None, "INSUFFICIENT_ATR_HISTORY")
    if len(close) >= 35 and r1.available and r1.value is not None:
        baseline_atr = float(atr.iloc[-21:-1].mean())
        if np.isfinite(latest_atr) and baseline_atr > 0.0:
            score = max(0.0, latest_atr / baseline_atr - 1.0) * max(0.0, r1.value)
            result["ATR_EXPANSION_WITH_POSITIVE_RETURN"] = ComputedValue(score, "")
        else:
            result["ATR_EXPANSION_WITH_POSITIVE_RETURN"] = ComputedValue(None, "INVALID_ATR")
    else:
        result["ATR_EXPANSION_WITH_POSITIVE_RETURN"] = ComputedValue(
            None, "INSUFFICIENT_ATR_HISTORY"
        )
    if len(close) >= 29:
        direct = float(close.iloc[-1] - close.iloc[-29])
        path = float(close.diff().abs().iloc[-28:].sum())
        result["RETURN_PATH_EFFICIENCY_28D"] = safe_ratio(direct, path, "ZERO_RETURN_PATH_LENGTH")
    else:
        result["RETURN_PATH_EFFICIENCY_28D"] = ComputedValue(None, "INSUFFICIENT_PATH_HISTORY")
    result["OLS_TREND_TSTAT_28D"] = _ols_tstat(close)
    recent_returns = returns.dropna().tail(28)
    if len(recent_returns) == 28:
        result["POSITIVE_BAR_BREADTH_28D"] = ComputedValue(float((recent_returns > 0.0).mean()), "")
    else:
        result["POSITIVE_BAR_BREADTH_28D"] = ComputedValue(None, "INSUFFICIENT_RETURN_HISTORY")
    rolling_high = close.rolling(29, min_periods=29).max()
    drawdown = close / rolling_high - 1.0
    worst_drawdown = (
        float(drawdown.tail(28).min()) if len(drawdown.dropna()) >= 28 else float("nan")
    )
    if (
        r28.available
        and r28.value is not None
        and np.isfinite(worst_drawdown)
        and worst_drawdown != 0.0
    ):
        result["DRAWDOWN_ADJUSTED_MOMENTUM_28D"] = safe_ratio(
            r28.value, abs(worst_drawdown), "ZERO_DRAWDOWN_DENOMINATOR"
        )
    else:
        result["DRAWDOWN_ADJUSTED_MOMENTUM_28D"] = ComputedValue(
            None, "INSUFFICIENT_DRAWDOWN_HISTORY"
        )
    volume_tail = volume.tail(30)
    volume_std = sample_std_or_missing(volume_tail.tolist(), "INSUFFICIENT_VOLUME_HISTORY")
    if len(volume_tail) == 30 and volume_std.available and volume_std.value is not None:
        result["VOLUME_ZSCORE_30D"] = safe_ratio(
            float(volume.iloc[-1] - volume_tail.mean()), volume_std.value, "ZERO_VOLUME_STD"
        )
    else:
        result["VOLUME_ZSCORE_30D"] = ComputedValue(None, volume_std.missing_reason)
    volume_baseline = float(volume_tail.mean()) if len(volume_tail) == 30 else float("nan")
    recent_volume = float(volume.tail(7).mean()) if len(volume) >= 7 else float("nan")
    if np.isfinite(volume_baseline) and volume_baseline > 0.0 and np.isfinite(recent_volume):
        result["VOLUME_ACCELERATION_7D_30D"] = ComputedValue(
            recent_volume / volume_baseline - 1.0, ""
        )
        if r28.available and r28.value is not None and recent_volume > 0.0:
            result["PRICE_VOLUME_CONFIRMATION_28D"] = ComputedValue(
                float(np.sign(r28.value) * np.log(recent_volume / volume_baseline)), ""
            )
        else:
            result["PRICE_VOLUME_CONFIRMATION_28D"] = ComputedValue(
                None, "NONPOSITIVE_VOLUME_BASELINE"
            )
    else:
        result["VOLUME_ACCELERATION_7D_30D"] = ComputedValue(None, "NONPOSITIVE_VOLUME_BASELINE")
        result["PRICE_VOLUME_CONFIRMATION_28D"] = ComputedValue(None, "NONPOSITIVE_VOLUME_BASELINE")
    result["QUOTE_TURNOVER_CHANGE_7D_30D"] = _quote_turnover_score(quote_turnover)
    btc_close_return = _return_minus_one(pd.Series(np.exp(btc_returns.dropna().cumsum())), 28)
    if (
        r28.available
        and r28.value is not None
        and btc_close_return.available
        and btc_close_return.value is not None
    ):
        result["BTC_RELATIVE_RETURN_28D"] = ComputedValue(r28.value - btc_close_return.value, "")
    else:
        result["BTC_RELATIVE_RETURN_28D"] = ComputedValue(None, "INSUFFICIENT_BTC_HISTORY")
    result["MARKET_RESIDUAL_MOMENTUM_28D"] = _residual_score(returns, market_returns, False)
    result["BETA_ADJUSTED_MOMENTUM_28D"] = _beta_adjusted_score(returns, btc_returns)
    result["IDIOSYNCRATIC_STRENGTH_28D"] = _residual_score(returns, market_returns, True)
    result["REALIZED_VOLATILITY_28D"] = return_std
    downside = recent_returns[recent_returns < 0.0]
    result["DOWNSIDE_VOLATILITY_28D"] = sample_std_or_missing(
        downside.tolist(), "INSUFFICIENT_DOWNSIDE_HISTORY"
    )
    result["MAX_DRAWDOWN_28D"] = finite_or_missing(worst_drawdown, "INSUFFICIENT_DRAWDOWN_HISTORY")
    illiquidity = (returns.abs() / volume.replace(0.0, np.nan)).dropna().tail(30)
    result["ILLIQUIDITY_PROXY_30D"] = (
        finite_or_missing(float(illiquidity.mean()), "NONFINITE_ILLIQUIDITY")
        if len(illiquidity) == 30
        else ComputedValue(None, "INSUFFICIENT_ILLIQUIDITY_HISTORY")
    )
    if availability_start is not None and availability_start <= decision_time:
        elapsed = float((decision_time - availability_start).days)
        result["AGE_OR_TENURE"] = ComputedValue(max(0.0, elapsed), "")
    else:
        result["AGE_OR_TENURE"] = ComputedValue(None, "AVAILABILITY_START_UNAVAILABLE")
    missing = set(SIGNAL_IDS).difference(result)
    if missing:
        raise AssertionError(f"Missing signal definitions: {sorted(missing)}")
    return result


def build_causal_market_returns(
    daily_by_symbol: Mapping[str, pd.DataFrame],
    membership: pd.DataFrame,
) -> tuple[pd.Series, list[MarketReturnRecord]]:
    """Build the complete causal daily PIT equal-weight market-return history."""

    if membership.empty:
        return pd.Series(dtype=float), []
    normalized = membership.copy()
    normalized["decision_time"] = pd.to_datetime(normalized["decision_time"], utc=True)
    snapshots: dict[pd.Timestamp, set[str]] = {
        required_timestamp(timestamp, field="decision_time"): set(group["symbol"].astype(str))
        for timestamp, group in normalized.groupby("decision_time", sort=True)
    }
    snapshot_times = sorted(snapshots)
    all_times = sorted(
        {
            timestamp
            for frame in daily_by_symbol.values()
            for timestamp in pd.to_datetime(frame["bar_close_time"], utc=True)
            if timestamp <= RESEARCH_LOCK
        }
    )
    returns_by_symbol: dict[str, pd.Series] = {}
    for symbol, frame in daily_by_symbol.items():
        ordered = frame.reset_index(drop=True).sort_values("bar_close_time")
        index = pd.DatetimeIndex(pd.to_datetime(ordered["bar_close_time"], utc=True))
        returns_by_symbol[symbol] = pd.Series(
            np.log(ordered["close"].to_numpy(dtype=float)).astype(float), index=index
        ).diff()
    records: list[MarketReturnRecord] = []
    market_values: dict[pd.Timestamp, float] = {}
    snapshot_index = -1
    for timestamp in all_times:
        while (
            snapshot_index + 1 < len(snapshot_times)
            and snapshot_times[snapshot_index + 1] <= timestamp
        ):
            snapshot_index += 1
        if snapshot_index < 0:
            records.append(MarketReturnRecord(timestamp, None, 0, 0, None, "NO_KNOWN_MEMBERSHIP"))
            continue
        snapshot_time = snapshot_times[snapshot_index]
        members = snapshots[snapshot_time]
        values = [
            float(series.loc[timestamp])
            for symbol, series in returns_by_symbol.items()
            if symbol in members
            and timestamp in series.index
            and np.isfinite(float(series.loc[timestamp]))
        ]
        if len(values) < 2:
            records.append(
                MarketReturnRecord(
                    timestamp,
                    snapshot_time,
                    len(members),
                    len(values),
                    None,
                    "INSUFFICIENT_VALID_RETURNS",
                )
            )
            continue
        value = float(np.mean(values))
        market_values[timestamp] = value
        records.append(
            MarketReturnRecord(timestamp, snapshot_time, len(members), len(values), value, "")
        )
    return pd.Series(market_values, dtype=float).sort_index(), records


def average_pairwise_correlation(
    daily_by_symbol: Mapping[str, pd.DataFrame],
    members: Iterable[str],
    decision_time: pd.Timestamp,
) -> ComputedValue:
    """Mean Pearson correlation over valid 28-return PIT member pairs."""

    returns: dict[str, pd.Series] = {}
    for symbol in sorted(set(members)):
        frame = daily_by_symbol.get(symbol)
        if frame is None:
            continue
        causal = frame.loc[frame.index <= decision_time]
        if causal.empty:
            continue
        if "daily_log_return" in causal.columns:
            returns[symbol] = causal["daily_log_return"].copy()
        else:
            index = pd.DatetimeIndex(pd.to_datetime(causal["bar_close_time"], utc=True))
            returns[symbol] = pd.Series(
                np.log(causal["close"].to_numpy(dtype=float)), index=index
            ).diff()
    correlations: list[float] = []
    symbols = sorted(returns)
    for position, left_symbol in enumerate(symbols):
        for right_symbol in symbols[position + 1 :]:
            paired = (
                pd.concat((returns[left_symbol], returns[right_symbol]), axis=1, sort=False)
                .dropna()
                .tail(28)
            )
            if len(paired) != 28:
                continue
            correlation = safe_correlation(paired.iloc[:, 0].tolist(), paired.iloc[:, 1].tolist())
            if correlation.available and correlation.value is not None:
                correlations.append(correlation.value)
    if not correlations:
        return ComputedValue(None, "INSUFFICIENT_CROSS_SECTION")
    return ComputedValue(float(np.mean(correlations)), "")


def tercile_state(current: float | None, prior_values: Sequence[float]) -> tuple[str, int]:
    """Classify with the frozen 52 strictly-prior observations and linear quantiles."""

    valid = [value for value in prior_values if np.isfinite(value)]
    if current is None or not np.isfinite(current):
        return "INSUFFICIENT_HISTORY", len(valid)
    if len(valid) < 52:
        return "INSUFFICIENT_HISTORY", len(valid)
    history = np.asarray(valid[-52:], dtype=float)
    lower, upper = np.quantile(history, [1.0 / 3.0, 2.0 / 3.0], method="linear")
    if current <= lower:
        return "LOW", len(valid)
    if current <= upper:
        return "MID", len(valid)
    return "HIGH", len(valid)
