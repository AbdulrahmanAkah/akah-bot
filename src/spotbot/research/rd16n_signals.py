from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from spotbot.research.rd16d_metrics import market_regime_from_row

ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"
NORMAL_HOLDING_BARS: Final = 48
STRONG_BULL_HOLDING_BARS: Final = 96


class RD16NSignalError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SignalHypothesis:
    hypothesis_id: str
    engine_id: str
    role: str
    description: str
    stop_atr_multiple: float
    cooldown_hours: int
    engine_priority: int
    fixed_conditions: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "engine_id": self.engine_id,
            "role": self.role,
            "description": self.description,
            "stop_atr_multiple": self.stop_atr_multiple,
            "cooldown_hours": self.cooldown_hours,
            "engine_priority": self.engine_priority,
            "normal_holding_bars": NORMAL_HOLDING_BARS,
            "strong_bull_holding_bars": STRONG_BULL_HOLDING_BARS,
            "fixed_conditions": "; ".join(self.fixed_conditions),
        }


HYPOTHESIS_REGISTRY: Final = (
    SignalHypothesis(
        hypothesis_id="FAST_MOMENTUM_BREAKOUT",
        engine_id="FAST_MOMENTUM_BREAKOUT_ENGINE_V1",
        role="OFFENSIVE",
        description="Fast 1H momentum breakout with aligned multi-timeframe trend.",
        stop_atr_multiple=1.25,
        cooldown_hours=12,
        engine_priority=30,
        fixed_conditions=(
            "1H close above prior 6H high",
            "EMA8 > EMA21 > EMA50",
            "EMA8 rising",
            "volume >= 1.25 x 20H median",
            "close location >= 0.70",
            "4H close > EMA20",
            "1D close > 0.95 x EMA50",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="TREND_REACCELERATION",
        engine_id="TREND_REACCELERATION_ENGINE_V1",
        role="OFFENSIVE",
        description="Bullish EMA8/EMA21 recross inside established higher-timeframe trend.",
        stop_atr_multiple=1.25,
        cooldown_hours=12,
        engine_priority=31,
        fixed_conditions=(
            "previous EMA8 <= previous EMA21",
            "current EMA8 > EMA21",
            "close > EMA20",
            "EMA50 positive 12H slope",
            "4H close > EMA50",
            "1D close > EMA50",
            "1W close > 0.95 x EMA40",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="VWAP_RECLAIM_CONTINUATION",
        engine_id="VWAP_RECLAIM_CONTINUATION_ENGINE_V1",
        role="DIVERSIFIER",
        description="Rolling 24H VWAP reclaim inside a constructive trend context.",
        stop_atr_multiple=1.15,
        cooldown_hours=12,
        engine_priority=32,
        fixed_conditions=(
            "previous close <= previous rolling VWAP24",
            "current low <= rolling VWAP24",
            "current close > rolling VWAP24",
            "close > EMA20 > EMA50",
            "volume >= 0.80 x 20H median",
            "4H close > EMA50",
            "1D close > 0.95 x EMA50",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="VOLATILITY_SQUEEZE_RELEASE",
        engine_id="VOLATILITY_SQUEEZE_RELEASE_ENGINE_V1",
        role="OFFENSIVE",
        description="Breakout from a causal low-bandwidth and low-4H-volatility state.",
        stop_atr_multiple=1.50,
        cooldown_hours=24,
        engine_priority=33,
        fixed_conditions=(
            "prior Bollinger width <= prior 100H rolling 25th percentile",
            "close above prior 20H upper band",
            "1H range >= ATR14",
            "volume >= 20H median",
            "4H ATR ratio <= 0.90",
            "1D close > 0.90 x EMA50",
            "1W close > 0.85 x EMA40",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="RELATIVE_STRENGTH_LEADER_BREAKOUT",
        engine_id="RELATIVE_STRENGTH_LEADER_BREAKOUT_ENGINE_V1",
        role="OFFENSIVE",
        description="Cross-sectional 24H/72H relative-strength leader breaking 12H high.",
        stop_atr_multiple=1.50,
        cooldown_hours=12,
        engine_priority=34,
        fixed_conditions=(
            "24H return >= equal-weight market return + 5 percentage points",
            "72H return > equal-weight market return",
            "close above prior 12H high",
            "close > EMA20",
            "volume >= 0.80 x 20H median",
            "4H close > EMA20",
            "1D close > 0.95 x EMA50",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="DEFENSIVE_SWEEP_REVERSAL",
        engine_id="DEFENSIVE_SWEEP_REVERSAL_ENGINE_V1",
        role="DEFENSIVE",
        description="Long-only downside sweep reversal in weak daily context.",
        stop_atr_multiple=1.00,
        cooldown_hours=24,
        engine_priority=35,
        fixed_conditions=(
            "1H low below prior 24H low",
            "close back above prior 24H low",
            "bullish candle",
            "lower wick ratio >= 0.40",
            "volume >= 1.25 x 20H median",
            "1D close <= EMA50",
            "1W close > 0.70 x EMA40",
        ),
    ),
)

HYPOTHESIS_BY_ID: Final = {
    hypothesis.hypothesis_id: hypothesis for hypothesis in HYPOTHESIS_REGISTRY
}
HYPOTHESIS_IDS: Final = tuple(hypothesis.hypothesis_id for hypothesis in HYPOTHESIS_REGISTRY)


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    result = numerator / denominator.replace(0.0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def _extend_single_frame(frame: pd.DataFrame) -> pd.DataFrame:
    extended = frame.copy()
    close = pd.to_numeric(extended["close"], errors="raise")
    high = pd.to_numeric(extended["high"], errors="raise")
    low = pd.to_numeric(extended["low"], errors="raise")
    open_price = pd.to_numeric(extended["open"], errors="raise")
    volume = pd.to_numeric(extended["volume"], errors="raise")

    extended["ema8"] = close.ewm(
        span=8,
        adjust=False,
        min_periods=8,
    ).mean()
    extended["ema21"] = close.ewm(
        span=21,
        adjust=False,
        min_periods=21,
    ).mean()
    extended["previous_ema8"] = extended["ema8"].shift(1)
    extended["previous_ema21"] = extended["ema21"].shift(1)
    extended["ema8_previous"] = extended["ema8"].shift(1)
    extended["ema50_slope12"] = extended["ema50"] - extended["ema50"].shift(12)
    extended["prior_high6"] = high.rolling(6, min_periods=6).max().shift(1)

    typical = (high + low + close) / 3.0
    volume_sum = volume.rolling(24, min_periods=24).sum()
    typical_volume_sum = (
        (typical * volume)
        .rolling(
            24,
            min_periods=24,
        )
        .sum()
    )
    extended["vwap24"] = _safe_divide(
        typical_volume_sum,
        volume_sum,
    )
    extended["previous_vwap24"] = extended["vwap24"].shift(1)

    prior_close = close.shift(1)
    prior_mean20 = prior_close.rolling(20, min_periods=20).mean()
    prior_std20 = prior_close.rolling(20, min_periods=20).std(ddof=0)
    extended["prior_band_upper20"] = prior_mean20 + 2.0 * prior_std20
    extended["prior_band_width20"] = _safe_divide(
        4.0 * prior_std20,
        prior_mean20.abs(),
    )
    extended["prior_band_width_q25_100"] = (
        extended["prior_band_width20"].rolling(100, min_periods=60).quantile(0.25)
    )

    candle_range = (high - low).replace(0.0, np.nan)
    lower_body = pd.concat((open_price, close), axis=1).min(axis=1)
    extended["close_location"] = _safe_divide(
        close - low,
        candle_range,
    )
    extended["lower_wick_ratio"] = _safe_divide(
        lower_body - low,
        candle_range,
    )
    extended["return24"] = close / close.shift(24) - 1.0
    extended["return72"] = close / close.shift(72) - 1.0

    extended = extended.replace([np.inf, -np.inf], np.nan)
    return extended


def build_extended_feature_frames(
    feature_frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    if not feature_frames:
        raise RD16NSignalError("Feature-frame mapping cannot be empty.")

    extended = {symbol: _extend_single_frame(frame) for symbol, frame in feature_frames.items()}

    returns24: dict[str, pd.Series] = {}
    returns72: dict[str, pd.Series] = {}
    for symbol, frame in extended.items():
        indexed = frame.set_index("timestamp")
        returns24[symbol] = pd.to_numeric(
            indexed["return24"],
            errors="raise",
        )
        returns72[symbol] = pd.to_numeric(
            indexed["return72"],
            errors="raise",
        )

    market24 = pd.concat(returns24, axis=1).mean(
        axis=1,
        skipna=True,
    )
    market72 = pd.concat(returns72, axis=1).mean(
        axis=1,
        skipna=True,
    )

    result: dict[str, pd.DataFrame] = {}
    for symbol, frame in extended.items():
        working = frame.copy()
        timestamp_index = pd.DatetimeIndex(
            pd.to_datetime(
                working["timestamp"],
                utc=True,
                errors="raise",
            )
        )
        working["market_return24"] = market24.reindex(timestamp_index).to_numpy()
        working["market_return72"] = market72.reindex(timestamp_index).to_numpy()
        result[symbol] = working.reset_index(drop=True)
    return result


def hypothesis_signal_mask(
    frame: pd.DataFrame,
    hypothesis_id: str,
) -> pd.Series:
    if hypothesis_id == "FAST_MOMENTUM_BREAKOUT":
        raw = (
            (frame["close"] > frame["prior_high6"])
            & (frame["ema8"] > frame["ema21"])
            & (frame["ema21"] > frame["ema50"])
            & (frame["ema8"] > frame["ema8_previous"])
            & (frame["volume"] >= 1.25 * frame["volume_median20"])
            & (frame["close_location"] >= 0.70)
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > 0.95 * frame["1d_ema50"])
        )
    elif hypothesis_id == "TREND_REACCELERATION":
        raw = (
            (frame["previous_ema8"] <= frame["previous_ema21"])
            & (frame["ema8"] > frame["ema21"])
            & (frame["close"] > frame["ema20"])
            & (frame["ema50_slope12"] > 0.0)
            & (frame["4h_close"] > frame["4h_ema50"])
            & (frame["1d_close"] > frame["1d_ema50"])
            & (frame["1w_close"] > 0.95 * frame["1w_ema40"])
        )
    elif hypothesis_id == "VWAP_RECLAIM_CONTINUATION":
        raw = (
            (frame["previous_close"] <= frame["previous_vwap24"])
            & (frame["low"] <= frame["vwap24"])
            & (frame["close"] > frame["vwap24"])
            & (frame["close"] > frame["ema20"])
            & (frame["ema20"] > frame["ema50"])
            & (frame["volume"] >= 0.80 * frame["volume_median20"])
            & (frame["4h_close"] > frame["4h_ema50"])
            & (frame["1d_close"] > 0.95 * frame["1d_ema50"])
        )
    elif hypothesis_id == "VOLATILITY_SQUEEZE_RELEASE":
        raw = (
            (frame["prior_band_width20"] <= frame["prior_band_width_q25_100"])
            & (frame["close"] > frame["prior_band_upper20"])
            & (frame["range_1h"] >= frame["atr14"])
            & (frame["volume"] >= frame["volume_median20"])
            & (frame["4h_atr_ratio"] <= 0.90)
            & (frame["1d_close"] > 0.90 * frame["1d_ema50"])
            & (frame["1w_close"] > 0.85 * frame["1w_ema40"])
        )
    elif hypothesis_id == "RELATIVE_STRENGTH_LEADER_BREAKOUT":
        raw = (
            (frame["return24"] >= frame["market_return24"] + 0.05)
            & (frame["return72"] > frame["market_return72"])
            & (frame["close"] > frame["prior_high12"])
            & (frame["close"] > frame["ema20"])
            & (frame["volume"] >= 0.80 * frame["volume_median20"])
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > 0.95 * frame["1d_ema50"])
        )
    elif hypothesis_id == "DEFENSIVE_SWEEP_REVERSAL":
        raw = (
            (frame["low"] < frame["prior_low24"])
            & (frame["close"] > frame["prior_low24"])
            & (frame["close"] > frame["open"])
            & (frame["lower_wick_ratio"] >= 0.40)
            & (frame["volume"] >= 1.25 * frame["volume_median20"])
            & (frame["1d_close"] <= frame["1d_ema50"])
            & (frame["1w_close"] > 0.70 * frame["1w_ema40"])
        )
    else:
        raise KeyError(f"Unknown hypothesis ID: {hypothesis_id}")

    normalized = raw.fillna(False).astype(bool)
    previous = normalized.shift(1, fill_value=False).astype(bool)
    return normalized & ~previous


def build_hypothesis_candidates(
    feature_frames: Mapping[str, pd.DataFrame],
    *,
    hypothesis: SignalHypothesis,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []

    for symbol in sorted(feature_frames):
        frame = feature_frames[symbol]
        mask = hypothesis_signal_mask(
            frame,
            hypothesis.hypothesis_id,
        )
        positions = [position for position, active in enumerate(mask.tolist()) if bool(active)]
        for position in positions:
            next_position = position + 1
            if next_position >= len(frame):
                continue
            signal_row = frame.iloc[position]
            next_row = frame.iloc[next_position]
            signal_close = _timestamp(signal_row["timestamp"])
            entry_bar_close = _timestamp(next_row["timestamp"])
            if entry_bar_close - signal_close != pd.Timedelta(hours=1):
                continue
            signal_mapping = {str(key): value for key, value in signal_row.to_dict().items()}
            market_regime = market_regime_from_row(signal_mapping)
            holding_bars = (
                STRONG_BULL_HOLDING_BARS if market_regime == "STRONG_BULL" else NORMAL_HOLDING_BARS
            )
            symbol_token = symbol.replace("/", "-")
            candidate_id = (
                f"RD16N-{hypothesis.hypothesis_id}-{symbol_token}-{signal_close.isoformat()}"
            )
            records.append(
                {
                    "architecture_id": ARCHITECTURE_ID,
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "engine_id": hypothesis.engine_id,
                    "engine_priority": hypothesis.engine_priority,
                    "engine_role": hypothesis.role,
                    "cooldown_hours": hypothesis.cooldown_hours,
                    "candidate_id": candidate_id,
                    "source_trade_id": candidate_id,
                    "symbol": symbol,
                    "signal_close": signal_close,
                    "entry_open_time": signal_close,
                    "entry_bar_close": entry_bar_close,
                    "entry_price": float(next_row["open"]),
                    "atr14_at_signal": float(signal_row["atr14"]),
                    "stop_atr_multiple": hypothesis.stop_atr_multiple,
                    "maximum_holding_bars": holding_bars,
                    "market_regime": market_regime,
                    "4h_context_close": _timestamp(signal_row["4h_timestamp"]),
                    "1d_context_close": _timestamp(signal_row["1d_timestamp"]),
                    "1w_context_close": _timestamp(signal_row["1w_timestamp"]),
                }
            )

    if not records:
        return pd.DataFrame(
            columns=[
                "architecture_id",
                "hypothesis_id",
                "engine_id",
                "engine_priority",
                "engine_role",
                "cooldown_hours",
                "candidate_id",
                "source_trade_id",
                "symbol",
                "signal_close",
                "entry_open_time",
                "entry_bar_close",
                "entry_price",
                "atr14_at_signal",
                "stop_atr_multiple",
                "maximum_holding_bars",
                "market_regime",
                "4h_context_close",
                "1d_context_close",
                "1w_context_close",
            ]
        )

    return (
        pd.DataFrame.from_records(records)
        .sort_values(
            by=[
                "entry_open_time",
                "engine_priority",
                "symbol",
                "signal_close",
                "candidate_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )


__all__ = [
    "ARCHITECTURE_ID",
    "HYPOTHESIS_BY_ID",
    "HYPOTHESIS_IDS",
    "HYPOTHESIS_REGISTRY",
    "NORMAL_HOLDING_BARS",
    "RD16NSignalError",
    "STRONG_BULL_HOLDING_BARS",
    "SignalHypothesis",
    "build_extended_feature_frames",
    "build_hypothesis_candidates",
    "hypothesis_signal_mask",
]
