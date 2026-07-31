from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import numpy as np
import pandas as pd

from spotbot.data.validator import REQUIRED_COLUMNS

FEATURE_COLUMNS: Final = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ema20",
    "ema50",
    "atr14",
    "prior_high12",
    "prior_high24",
    "prior_low12",
    "prior_low24",
    "previous_close",
    "previous_ema20",
    "volume_median20",
    "range_1h",
    "4h_timestamp",
    "4h_close",
    "4h_ema20",
    "4h_ema50",
    "4h_atr14",
    "4h_atr_ratio",
    "1d_timestamp",
    "1d_close",
    "1d_ema50",
    "1d_ema200",
    "1w_timestamp",
    "1w_close",
    "1w_ema20",
    "1w_ema40",
)


class FeatureDataError(RuntimeError):
    pass


def _normalize_frame(
    frame: pd.DataFrame,
    *,
    timeframe: str,
) -> pd.DataFrame:
    missing = sorted(set(REQUIRED_COLUMNS).difference(frame.columns))
    if missing:
        raise FeatureDataError(f"{timeframe} frame missing columns: {missing}")
    normalized = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    parsed = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="coerce",
    )
    if bool(parsed.isna().any()):
        raise FeatureDataError(f"{timeframe} frame has invalid timestamps.")
    normalized["timestamp"] = parsed.astype("datetime64[ns, UTC]")
    for column in REQUIRED_COLUMNS[1:]:
        normalized[column] = pd.to_numeric(
            normalized[column],
            errors="coerce",
        ).astype("float64")
    if bool(normalized[list(REQUIRED_COLUMNS[1:])].isna().any().any()):
        raise FeatureDataError(f"{timeframe} frame has invalid numeric values.")
    return normalized.sort_values(
        by="timestamp",
        kind="stable",
    ).reset_index(drop=True)


def _atr(frame: pd.DataFrame, span: int = 14) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        (
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ),
        axis=1,
    )
    true_range = ranges.max(axis=1)
    return true_range.ewm(
        alpha=1.0 / span,
        adjust=False,
        min_periods=span,
    ).mean()


def _signal_features(frame: pd.DataFrame) -> pd.DataFrame:
    featured = frame.copy()
    featured["ema20"] = (
        featured["close"]
        .ewm(
            span=20,
            adjust=False,
            min_periods=20,
        )
        .mean()
    )
    featured["ema50"] = (
        featured["close"]
        .ewm(
            span=50,
            adjust=False,
            min_periods=50,
        )
        .mean()
    )
    featured["atr14"] = _atr(featured)
    featured["prior_high12"] = featured["high"].rolling(12, min_periods=12).max().shift(1)
    featured["prior_high24"] = featured["high"].rolling(24, min_periods=24).max().shift(1)
    featured["prior_low12"] = featured["low"].rolling(12, min_periods=12).min().shift(1)
    featured["prior_low24"] = featured["low"].rolling(24, min_periods=24).min().shift(1)
    featured["previous_close"] = featured["close"].shift(1)
    featured["previous_ema20"] = featured["ema20"].shift(1)
    featured["volume_median20"] = (
        featured["volume"]
        .rolling(
            20,
            min_periods=20,
        )
        .median()
    )
    featured["range_1h"] = featured["high"] - featured["low"]
    return featured


def _four_hour_features(frame: pd.DataFrame) -> pd.DataFrame:
    featured = frame.copy()
    featured["ema20"] = (
        featured["close"]
        .ewm(
            span=20,
            adjust=False,
            min_periods=20,
        )
        .mean()
    )
    featured["ema50"] = (
        featured["close"]
        .ewm(
            span=50,
            adjust=False,
            min_periods=50,
        )
        .mean()
    )
    featured["atr14"] = _atr(featured)
    atr_median = (
        featured["atr14"]
        .rolling(
            50,
            min_periods=20,
        )
        .median()
    )
    featured["atr_ratio"] = featured["atr14"] / atr_median
    return featured.loc[
        :,
        [
            "timestamp",
            "close",
            "ema20",
            "ema50",
            "atr14",
            "atr_ratio",
        ],
    ].rename(
        columns={
            "timestamp": "4h_timestamp",
            "close": "4h_close",
            "ema20": "4h_ema20",
            "ema50": "4h_ema50",
            "atr14": "4h_atr14",
            "atr_ratio": "4h_atr_ratio",
        }
    )


def _daily_features(frame: pd.DataFrame) -> pd.DataFrame:
    featured = frame.copy()
    featured["ema50"] = (
        featured["close"]
        .ewm(
            span=50,
            adjust=False,
            min_periods=50,
        )
        .mean()
    )
    featured["ema200"] = (
        featured["close"]
        .ewm(
            span=200,
            adjust=False,
            min_periods=120,
        )
        .mean()
    )
    return featured.loc[
        :,
        ["timestamp", "close", "ema50", "ema200"],
    ].rename(
        columns={
            "timestamp": "1d_timestamp",
            "close": "1d_close",
            "ema50": "1d_ema50",
            "ema200": "1d_ema200",
        }
    )


def _weekly_features(frame: pd.DataFrame) -> pd.DataFrame:
    featured = frame.copy()
    featured["ema20"] = (
        featured["close"]
        .ewm(
            span=20,
            adjust=False,
            min_periods=20,
        )
        .mean()
    )
    featured["ema40"] = (
        featured["close"]
        .ewm(
            span=40,
            adjust=False,
            min_periods=30,
        )
        .mean()
    )
    return featured.loc[
        :,
        ["timestamp", "close", "ema20", "ema40"],
    ].rename(
        columns={
            "timestamp": "1w_timestamp",
            "close": "1w_close",
            "ema20": "1w_ema20",
            "ema40": "1w_ema40",
        }
    )


def _merge_context(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    right_timestamp: str,
) -> pd.DataFrame:
    working_left = left.copy()
    working_right = right.copy()
    working_left["timestamp"] = pd.to_datetime(
        working_left["timestamp"],
        utc=True,
    ).astype("datetime64[ns, UTC]")
    working_right[right_timestamp] = pd.to_datetime(
        working_right[right_timestamp],
        utc=True,
    ).astype("datetime64[ns, UTC]")
    return pd.merge_asof(
        working_left.sort_values("timestamp", kind="stable"),
        working_right.sort_values(
            right_timestamp,
            kind="stable",
        ),
        left_on="timestamp",
        right_on=right_timestamp,
        direction="backward",
        allow_exact_matches=True,
    )


def build_feature_frame(
    frames: Mapping[str, pd.DataFrame],
    *,
    symbol: str,
) -> pd.DataFrame:
    required = {"1h", "4h", "1d", "1w"}
    missing = sorted(required.difference(frames))
    if missing:
        raise FeatureDataError(f"{symbol}: missing timeframes: {missing}")

    signal = _signal_features(_normalize_frame(frames["1h"], timeframe="1h"))
    four_hour = _four_hour_features(_normalize_frame(frames["4h"], timeframe="4h"))
    daily = _daily_features(_normalize_frame(frames["1d"], timeframe="1d"))
    weekly = _weekly_features(_normalize_frame(frames["1w"], timeframe="1w"))

    aligned = _merge_context(
        signal,
        four_hour,
        right_timestamp="4h_timestamp",
    )
    aligned = _merge_context(
        aligned,
        daily,
        right_timestamp="1d_timestamp",
    )
    aligned = _merge_context(
        aligned,
        weekly,
        right_timestamp="1w_timestamp",
    )

    aligned = aligned.replace([np.inf, -np.inf], np.nan)
    aligned = aligned.dropna(subset=list(FEATURE_COLUMNS)).reset_index(drop=True)
    if aligned.empty:
        raise FeatureDataError(f"{symbol}: no rows remain after feature warm-up.")

    for context_column in (
        "4h_timestamp",
        "1d_timestamp",
        "1w_timestamp",
    ):
        if bool((aligned[context_column] > aligned["timestamp"]).any()):
            raise FeatureDataError(f"{symbol}: future context detected in {context_column}.")

    return aligned.loc[:, list(FEATURE_COLUMNS)].copy()
