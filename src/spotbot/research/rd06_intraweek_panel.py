"""Typed computations for the causal RD06 4H panel."""

from __future__ import annotations

from hashlib import sha256
from typing import Final

import numpy as np
import pandas as pd

from spotbot.research.rd06_protocol_registration import LABEL_IDS, SIGNAL_IDS

LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")


def fingerprint_keys(frame: pd.DataFrame) -> str:
    payload = frame[["decision_time", "symbol"]].to_csv(index=False, lineterminator="\n")
    return sha256(payload.encode()).hexdigest()


def add_signal_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute the frozen 15 signals from closed 4H bars."""

    result = frame.sort_values(["symbol", "bar_close_time"]).copy()
    groups = result.groupby("symbol", sort=False)
    result["log_return"] = groups["close"].transform(lambda value: np.log(value).diff())
    result["std42"] = groups["log_return"].transform(
        lambda value: value.rolling(42, min_periods=42).std(ddof=1)
    )
    for bars in (1, 3, 6):
        summed = groups["log_return"].transform(
            lambda value, count=bars: value.rolling(count, min_periods=count).sum()
        )
        result[f"REVERSAL_{bars}BAR_VOL_NORMALIZED"] = -summed / result["std42"]
    result["ema20"] = groups["close"].transform(
        lambda value: value.ewm(span=20, adjust=False, min_periods=20).mean()
    )
    previous_close = groups["close"].shift(1)
    true_range = pd.concat(
        (
            result["high"] - result["low"],
            (result["high"] - previous_close).abs(),
            (result["low"] - previous_close).abs(),
        ),
        axis=1,
    ).max(axis=1)
    result["atr14"] = true_range.groupby(result["symbol"]).transform(
        lambda value: value.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    )
    result["DISTANCE_FROM_EMA20_ATR_4H"] = -(result["close"] - result["ema20"]) / result["atr14"]
    for bars in (6, 18, 42):
        result[f"RETURN_{bars}BAR"] = result["close"] / groups["close"].shift(bars) - 1
    result["BTC_TREND_84D"] = result["close"] / groups["close"].shift(504) - 1
    result["XSM_18BAR_SKIP_1BAR"] = groups["close"].shift(1) / groups["close"].shift(19) - 1
    prior_high = groups["high"].transform(
        lambda value: value.shift(1).rolling(42, min_periods=42).max()
    )
    prior_low = groups["low"].transform(
        lambda value: value.shift(1).rolling(42, min_periods=42).min()
    )
    result["DONCHIAN_42_POSITION"] = (result["close"] - prior_low) / (prior_high - prior_low)
    absolute_path = groups["close"].transform(
        lambda value: value.diff().abs().rolling(42, min_periods=42).sum()
    )
    result["PATH_EFFICIENCY_42BAR"] = (result["close"] - groups["close"].shift(42)) / absolute_path
    normalized_atr = result["atr14"] / result["close"]
    previous_normalized = normalized_atr.groupby(result["symbol"]).shift(1)
    baseline = previous_normalized.groupby(result["symbol"]).transform(
        lambda value: value.rolling(126, min_periods=126).median()
    )
    contraction = (1 - previous_normalized / baseline).clip(lower=0)
    breakout = (result["close"] / prior_high - 1).clip(lower=0)
    result["VOLATILITY_CONTRACTION_BREAKOUT_4H"] = breakout * contraction
    turnover6 = groups["quote_turnover_usdt"].transform(
        lambda value: value.rolling(6, min_periods=6).mean()
    )
    turnover42 = groups["quote_turnover_usdt"].transform(
        lambda value: value.rolling(42, min_periods=42).mean()
    )
    result["QUOTE_TURNOVER_ACCELERATION_6_42"] = turnover6 / turnover42 - 1
    result["PRICE_TURNOVER_CONFIRMATION_18"] = np.sign(result["RETURN_18BAR"]) * np.log(
        turnover6 / turnover42
    )
    result["LOW_REALIZED_VOLATILITY_42"] = -result["std42"]
    running_high = groups["close"].transform(lambda value: value.rolling(42, min_periods=1).max())
    drawdown = result["close"] / running_high - 1
    result["DRAWDOWN_RESILIENCE_42"] = drawdown.groupby(result["symbol"]).transform(
        lambda value: value.rolling(42, min_periods=42).min()
    )
    first_close = groups["bar_close_time"].transform("min")
    result["AGE_OR_TENURE"] = (result["bar_close_time"] - first_close).dt.total_seconds() / 86400
    return result


def add_label_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute future-only labels; no value is imputed at the research lock."""

    result = frame.sort_values(["symbol", "bar_close_time"]).copy()
    groups = result.groupby("symbol", sort=False)
    for label, bars in (
        ("FORWARD_24H_RETURN", 6),
        ("FORWARD_72H_RETURN", 18),
        ("FORWARD_7D_RETURN", 42),
    ):
        result[label] = groups["close"].shift(-bars) / result["close"] - 1
    future_high = pd.concat([groups["high"].shift(-step) for step in range(1, 7)], axis=1)
    future_low = pd.concat([groups["low"].shift(-step) for step in range(1, 7)], axis=1)
    result["FORWARD_24H_MFE"] = future_high.max(axis=1, skipna=False) / result["close"] - 1
    result["FORWARD_24H_MAE"] = future_low.min(axis=1, skipna=False) / result["close"] - 1
    if tuple(label for label in LABEL_IDS if label not in result) != ():
        raise RuntimeError("label registry mismatch")
    return result


def attach_availability(frame: pd.DataFrame, value_columns: tuple[str, ...]) -> pd.DataFrame:
    result = frame.copy()
    for column in value_columns:
        numeric = pd.to_numeric(result[column], errors="coerce")
        finite = np.isfinite(numeric)
        result[column] = numeric.where(finite)
        result[f"{column}_available"] = finite
        result[f"{column}_missing_reason"] = np.where(finite, "", "INSUFFICIENT_HISTORY")
    return result


def validate_panel(index: pd.DataFrame, features: pd.DataFrame, labels: pd.DataFrame) -> None:
    keys = ["decision_time", "symbol"]
    if any(frame.duplicated(keys).any() for frame in (index, features, labels)):
        raise ValueError("duplicate panel key")
    if not index[keys].equals(features[keys]) or not index[keys].equals(labels[keys]):
        raise ValueError("panel keys do not reconcile")
    if len(SIGNAL_IDS) != 15:
        raise ValueError("signal registry changed")
    if index["decision_time"].max() >= LOCK:
        raise ValueError("research lock violated")
