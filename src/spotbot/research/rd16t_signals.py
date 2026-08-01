from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from spotbot.research.rd16d_metrics import market_regime_from_row
from spotbot.research.rd16s_signals import ELIGIBLE_SYMBOLS

ARCHITECTURE_ID: Final = "LONG_HORIZON_ALPHA_RESEARCH_V1"
SOURCE_ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"
RESEARCH_STAGE: Final = "RD16T"


class RD16TSignalError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LongHorizonHypothesis:
    hypothesis_id: str
    engine_id: str
    role: str
    description: str
    allowed_regimes: frozenset[str]
    initial_stop_atr_multiple: float
    trail_activation_r: float
    trail_atr_multiple: float
    cooldown_hours: int
    engine_priority: int
    normal_holding_bars: int
    strong_bull_holding_bars: int
    fixed_conditions: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "engine_id": self.engine_id,
            "role": self.role,
            "description": self.description,
            "allowed_regimes": "; ".join(sorted(self.allowed_regimes)),
            "initial_stop_atr_multiple": self.initial_stop_atr_multiple,
            "trail_activation_r": self.trail_activation_r,
            "trail_atr_multiple": self.trail_atr_multiple,
            "cooldown_hours": self.cooldown_hours,
            "engine_priority": self.engine_priority,
            "normal_holding_bars": self.normal_holding_bars,
            "strong_bull_holding_bars": self.strong_bull_holding_bars,
            "fixed_conditions": "; ".join(self.fixed_conditions),
        }


HYPOTHESIS_REGISTRY: Final = (
    LongHorizonHypothesis(
        hypothesis_id="DAILY_PULLBACK_RECLAIM",
        engine_id="DAILY_PULLBACK_RECLAIM_ENGINE_V1",
        role="TREND_RESUMPTION",
        description="Daily EMA20 reclaim inside an established weekly trend.",
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        initial_stop_atr_multiple=1.60,
        trail_activation_r=1.50,
        trail_atr_multiple=2.75,
        cooldown_hours=120,
        engine_priority=50,
        normal_holding_bars=240,
        strong_bull_holding_bars=480,
        fixed_conditions=(
            "new completed daily bar",
            "previous daily close <= previous daily EMA20",
            "daily close > EMA20 > EMA50",
            "daily EMA20 five-day slope positive",
            "weekly close > EMA20 and EMA20 > 0.95 x EMA40",
            "60-day relative-strength percentile >= 60%",
            "drawdown from prior 55-day high between 3% and 20%",
            "daily volume >= 0.80 x 20-day median",
        ),
    ),
    LongHorizonHypothesis(
        hypothesis_id="DAILY_COMPRESSION_BREAKOUT",
        engine_id="DAILY_COMPRESSION_BREAKOUT_ENGINE_V1",
        role="TREND_EXPANSION",
        description="Twenty-day breakout after a causal daily volatility base.",
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        initial_stop_atr_multiple=1.80,
        trail_activation_r=1.75,
        trail_atr_multiple=3.00,
        cooldown_hours=168,
        engine_priority=51,
        normal_holding_bars=336,
        strong_bull_holding_bars=672,
        fixed_conditions=(
            "new completed daily bar",
            "daily close above prior 20-day high",
            "prior daily bandwidth <= prior 100-day 30th percentile",
            "daily volume >= 1.15 x 20-day median",
            "daily close location >= 65%",
            "daily close > EMA50",
            "weekly close > EMA20",
            "60-day relative-strength percentile >= 60%",
        ),
    ),
    LongHorizonHypothesis(
        hypothesis_id="WEEKLY_TREND_ACCELERATION",
        engine_id="WEEKLY_TREND_ACCELERATION_ENGINE_V1",
        role="STRUCTURAL_TREND",
        description="Weekly EMA20 recapture with positive medium-term slope.",
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        initial_stop_atr_multiple=2.00,
        trail_activation_r=1.50,
        trail_atr_multiple=3.25,
        cooldown_hours=336,
        engine_priority=52,
        normal_holding_bars=720,
        strong_bull_holding_bars=1_080,
        fixed_conditions=(
            "new completed weekly bar",
            "previous weekly close <= previous weekly EMA20",
            "weekly close > EMA20",
            "weekly EMA20 four-week slope positive",
            "daily close > EMA50",
            "60-day relative-strength percentile >= 60%",
            "daily close location >= 55%",
        ),
    ),
    LongHorizonHypothesis(
        hypothesis_id="CROSS_SECTIONAL_LEADER_PULLBACK",
        engine_id="CROSS_SECTIONAL_LEADER_PULLBACK_ENGINE_V1",
        role="LEADERSHIP",
        description="Top 20-day and 60-day leader buying a controlled EMA20 pullback.",
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        initial_stop_atr_multiple=1.60,
        trail_activation_r=1.50,
        trail_atr_multiple=2.75,
        cooldown_hours=120,
        engine_priority=53,
        normal_holding_bars=336,
        strong_bull_holding_bars=720,
        fixed_conditions=(
            "new completed daily bar",
            "20-day relative-strength percentile >= 80%",
            "60-day relative-strength percentile >= 80%",
            "weekly close > EMA20",
            "daily low touches within 2% above EMA20",
            "daily close > EMA20 > EMA50",
            "daily close location >= 60%",
            "daily volume >= 0.70 x 20-day median",
        ),
    ),
    LongHorizonHypothesis(
        hypothesis_id="DEEP_PULLBACK_RECOVERY",
        engine_id="DEEP_PULLBACK_RECOVERY_ENGINE_V1",
        role="RECOVERY",
        description="Deep but bounded pullback recovery inside a rising weekly trend.",
        allowed_regimes=frozenset({"BULL", "STRONG_BULL"}),
        initial_stop_atr_multiple=1.75,
        trail_activation_r=1.75,
        trail_atr_multiple=3.00,
        cooldown_hours=168,
        engine_priority=54,
        normal_holding_bars=240,
        strong_bull_holding_bars=480,
        fixed_conditions=(
            "new completed daily bar",
            "drawdown from prior 55-day high between 10% and 30%",
            "previous daily close <= previous daily EMA20",
            "daily close reclaims EMA20 and exceeds previous close",
            "weekly close > EMA20",
            "weekly EMA20 four-week slope positive",
            "60-day relative-strength percentile >= 40%",
            "daily close location >= 65%",
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


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16TSignalError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16TSignalError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16TSignalError(f"{name} must be finite.")
    return numeric


def _safe_divide(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    result = numerator / denominator.replace(0.0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise RD16TSignalError(f"Candle frame missing columns: {missing}")
    normalized = frame.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"], utc=True, errors="raise"
    ).astype("datetime64[ns, UTC]")
    for column in ("open", "high", "low", "close", "volume"):
        normalized[column] = pd.to_numeric(normalized[column], errors="raise").astype("float64")
    return normalized.sort_values("timestamp", kind="stable").reset_index(drop=True)


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
    return (
        ranges.max(axis=1)
        .ewm(
            alpha=1.0 / span,
            adjust=False,
            min_periods=span,
        )
        .mean()
    )


def _daily_features(frame: pd.DataFrame) -> pd.DataFrame:
    daily = _normalize(frame)
    close = daily["close"]
    high = daily["high"]
    low = daily["low"]
    volume = daily["volume"]
    daily["ema20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
    daily["ema50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()
    daily["ema200"] = close.ewm(span=200, adjust=False, min_periods=120).mean()
    daily["atr14"] = _atr(daily)
    daily["previous_close"] = close.shift(1)
    daily["previous_ema20"] = daily["ema20"].shift(1)
    daily["ema20_slope5"] = daily["ema20"] - daily["ema20"].shift(5)
    daily["prior_high20"] = high.rolling(20, min_periods=20).max().shift(1)
    daily["prior_high55"] = high.rolling(55, min_periods=55).max().shift(1)
    daily["drawdown55"] = _safe_divide(close, daily["prior_high55"]) - 1.0
    daily["return20"] = close / close.shift(20) - 1.0
    daily["return60"] = close / close.shift(60) - 1.0
    daily["volume_median20"] = volume.rolling(20, min_periods=20).median()
    daily["volume_ratio20"] = _safe_divide(volume, daily["volume_median20"])
    candle_range = (high - low).replace(0.0, np.nan)
    daily["close_location"] = _safe_divide(close - low, candle_range)
    mean20 = close.rolling(20, min_periods=20).mean()
    std20 = close.rolling(20, min_periods=20).std(ddof=0)
    bandwidth = _safe_divide(4.0 * std20, mean20.abs())
    daily["prior_bandwidth20"] = bandwidth.shift(1)
    daily["prior_bandwidth_q30_100"] = (
        bandwidth.shift(1).rolling(100, min_periods=60).quantile(0.30)
    )
    return daily.replace([np.inf, -np.inf], np.nan)


def _weekly_features(frame: pd.DataFrame) -> pd.DataFrame:
    weekly = _normalize(frame)
    close = weekly["close"]
    weekly["ema20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
    weekly["ema40"] = close.ewm(span=40, adjust=False, min_periods=30).mean()
    weekly["previous_close"] = close.shift(1)
    weekly["previous_ema20"] = weekly["ema20"].shift(1)
    weekly["ema20_slope4"] = weekly["ema20"] - weekly["ema20"].shift(4)
    return weekly.replace([np.inf, -np.inf], np.nan)


def _merge_context(
    hourly: pd.DataFrame,
    context: pd.DataFrame,
    *,
    right_timestamp: str,
) -> pd.DataFrame:
    left = hourly.copy()
    right = context.copy()
    left["timestamp"] = pd.to_datetime(left["timestamp"], utc=True, errors="raise").astype(
        "datetime64[ns, UTC]"
    )
    right[right_timestamp] = pd.to_datetime(
        right[right_timestamp], utc=True, errors="raise"
    ).astype("datetime64[ns, UTC]")
    return pd.merge_asof(
        left.sort_values("timestamp", kind="stable"),
        right.sort_values(right_timestamp, kind="stable"),
        left_on="timestamp",
        right_on=right_timestamp,
        direction="backward",
        allow_exact_matches=True,
    )


def build_long_horizon_feature_frames(
    base_features: Mapping[str, pd.DataFrame],
    market_frames: Mapping[str, Mapping[str, pd.DataFrame]],
) -> dict[str, pd.DataFrame]:
    expected = tuple(sorted(ELIGIBLE_SYMBOLS))
    if tuple(sorted(base_features)) != expected:
        raise RD16TSignalError("Base-feature universe differs from RD16-R eligibility.")
    if tuple(sorted(market_frames)) != expected:
        raise RD16TSignalError("Market-frame universe differs from RD16-R eligibility.")

    daily_by_symbol = {
        symbol: _daily_features(market_frames[symbol]["1d"]) for symbol in ELIGIBLE_SYMBOLS
    }
    return20 = pd.concat(
        {
            symbol: frame.set_index("timestamp")["return20"]
            for symbol, frame in daily_by_symbol.items()
        },
        axis=1,
    )
    return60 = pd.concat(
        {
            symbol: frame.set_index("timestamp")["return60"]
            for symbol, frame in daily_by_symbol.items()
        },
        axis=1,
    )
    rank20 = return20.rank(axis=1, pct=True, method="average")
    rank60 = return60.rank(axis=1, pct=True, method="average")

    result: dict[str, pd.DataFrame] = {}
    for symbol in ELIGIBLE_SYMBOLS:
        daily = daily_by_symbol[symbol].copy().set_index("timestamp")
        daily["rank20"] = rank20[symbol].reindex(daily.index)
        daily["rank60"] = rank60[symbol].reindex(daily.index)
        daily = daily.reset_index().rename(
            columns={
                "timestamp": "lh_1d_timestamp",
                "open": "lh_1d_open",
                "high": "lh_1d_high",
                "low": "lh_1d_low",
                "close": "lh_1d_close",
                "volume": "lh_1d_volume",
                "ema20": "lh_1d_ema20",
                "ema50": "lh_1d_ema50",
                "ema200": "lh_1d_ema200",
                "atr14": "lh_1d_atr14",
                "previous_close": "lh_previous_1d_close",
                "previous_ema20": "lh_previous_1d_ema20",
                "ema20_slope5": "lh_1d_ema20_slope5",
                "prior_high20": "lh_prior_high20",
                "prior_high55": "lh_prior_high55",
                "drawdown55": "lh_drawdown55",
                "return20": "lh_return20",
                "return60": "lh_return60",
                "volume_median20": "lh_volume_median20",
                "volume_ratio20": "lh_volume_ratio20",
                "close_location": "lh_close_location",
                "prior_bandwidth20": "lh_prior_bandwidth20",
                "prior_bandwidth_q30_100": "lh_prior_bandwidth_q30_100",
                "rank20": "lh_rank20",
                "rank60": "lh_rank60",
            }
        )
        weekly = (
            _weekly_features(market_frames[symbol]["1w"])
            .loc[
                :,
                [
                    "timestamp",
                    "close",
                    "ema20",
                    "ema40",
                    "previous_close",
                    "previous_ema20",
                    "ema20_slope4",
                ],
            ]
            .rename(
                columns={
                    "timestamp": "lh_1w_timestamp",
                    "close": "lh_1w_close",
                    "ema20": "lh_1w_ema20",
                    "ema40": "lh_1w_ema40",
                    "previous_close": "lh_previous_1w_close",
                    "previous_ema20": "lh_previous_1w_ema20",
                    "ema20_slope4": "lh_1w_ema20_slope4",
                }
            )
        )
        merged = _merge_context(
            base_features[symbol],
            daily,
            right_timestamp="lh_1d_timestamp",
        )
        merged = _merge_context(
            merged,
            weekly,
            right_timestamp="lh_1w_timestamp",
        )
        if bool((merged["lh_1d_timestamp"] > merged["timestamp"]).any()):
            raise RD16TSignalError(f"Future daily context detected for {symbol}.")
        if bool((merged["lh_1w_timestamp"] > merged["timestamp"]).any()):
            raise RD16TSignalError(f"Future weekly context detected for {symbol}.")
        result[symbol] = merged.replace([np.inf, -np.inf], np.nan)
    return result


def hypothesis_signal_mask(
    frame: pd.DataFrame,
    hypothesis_id: str,
) -> pd.Series:
    new_daily = frame["lh_1d_timestamp"].ne(frame["lh_1d_timestamp"].shift(1))
    new_weekly = frame["lh_1w_timestamp"].ne(frame["lh_1w_timestamp"].shift(1))

    if hypothesis_id == "DAILY_PULLBACK_RECLAIM":
        raw = (
            new_daily
            & (frame["lh_previous_1d_close"] <= frame["lh_previous_1d_ema20"])
            & (frame["lh_1d_close"] > frame["lh_1d_ema20"])
            & (frame["lh_1d_ema20"] > frame["lh_1d_ema50"])
            & (frame["lh_1d_ema20_slope5"] > 0.0)
            & (frame["lh_1w_close"] > frame["lh_1w_ema20"])
            & (frame["lh_1w_ema20"] > 0.95 * frame["lh_1w_ema40"])
            & (frame["lh_rank60"] >= 0.60)
            & (frame["lh_drawdown55"] <= -0.03)
            & (frame["lh_drawdown55"] >= -0.20)
            & (frame["lh_volume_ratio20"] >= 0.80)
        )
    elif hypothesis_id == "DAILY_COMPRESSION_BREAKOUT":
        raw = (
            new_daily
            & (frame["lh_1d_close"] > frame["lh_prior_high20"])
            & (frame["lh_prior_bandwidth20"] <= frame["lh_prior_bandwidth_q30_100"])
            & (frame["lh_volume_ratio20"] >= 1.15)
            & (frame["lh_close_location"] >= 0.65)
            & (frame["lh_1d_close"] > frame["lh_1d_ema50"])
            & (frame["lh_1w_close"] > frame["lh_1w_ema20"])
            & (frame["lh_rank60"] >= 0.60)
        )
    elif hypothesis_id == "WEEKLY_TREND_ACCELERATION":
        raw = (
            new_weekly
            & (frame["lh_previous_1w_close"] <= frame["lh_previous_1w_ema20"])
            & (frame["lh_1w_close"] > frame["lh_1w_ema20"])
            & (frame["lh_1w_ema20_slope4"] > 0.0)
            & (frame["lh_1d_close"] > frame["lh_1d_ema50"])
            & (frame["lh_rank60"] >= 0.60)
            & (frame["lh_close_location"] >= 0.55)
        )
    elif hypothesis_id == "CROSS_SECTIONAL_LEADER_PULLBACK":
        raw = (
            new_daily
            & (frame["lh_rank20"] >= 0.80)
            & (frame["lh_rank60"] >= 0.80)
            & (frame["lh_1w_close"] > frame["lh_1w_ema20"])
            & (frame["lh_1d_low"] <= 1.02 * frame["lh_1d_ema20"])
            & (frame["lh_1d_close"] > frame["lh_1d_ema20"])
            & (frame["lh_1d_ema20"] > frame["lh_1d_ema50"])
            & (frame["lh_close_location"] >= 0.60)
            & (frame["lh_volume_ratio20"] >= 0.70)
        )
    elif hypothesis_id == "DEEP_PULLBACK_RECOVERY":
        raw = (
            new_daily
            & (frame["lh_drawdown55"] <= -0.10)
            & (frame["lh_drawdown55"] >= -0.30)
            & (frame["lh_previous_1d_close"] <= frame["lh_previous_1d_ema20"])
            & (frame["lh_1d_close"] > frame["lh_1d_ema20"])
            & (frame["lh_1d_close"] > frame["lh_previous_1d_close"])
            & (frame["lh_1w_close"] > frame["lh_1w_ema20"])
            & (frame["lh_1w_ema20_slope4"] > 0.0)
            & (frame["lh_rank60"] >= 0.40)
            & (frame["lh_close_location"] >= 0.65)
        )
    else:
        raise KeyError(f"Unknown RD16-T hypothesis: {hypothesis_id}")
    return raw.fillna(False).astype(bool)


def _metadata_value(
    metadata: Mapping[str, object],
    key: str,
    *,
    symbol: str,
) -> object:
    if key not in metadata:
        raise RD16TSignalError(f"Asset metadata for {symbol} is missing {key}.")
    return metadata[key]


def build_long_horizon_candidates(
    feature_frames: Mapping[str, pd.DataFrame],
    *,
    hypothesis: LongHorizonHypothesis,
    asset_metadata: Mapping[str, Mapping[str, object]],
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for symbol in ELIGIBLE_SYMBOLS:
        frame = feature_frames[symbol]
        mask = hypothesis_signal_mask(frame, hypothesis.hypothesis_id)
        for position, active in enumerate(mask.tolist()):
            if not bool(active):
                continue
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
            if market_regime not in hypothesis.allowed_regimes:
                continue
            maximum_holding_bars = (
                hypothesis.strong_bull_holding_bars
                if market_regime == "STRONG_BULL"
                else hypothesis.normal_holding_bars
            )
            metadata = asset_metadata[symbol]
            candidate_id = (
                f"RD16T-{hypothesis.hypothesis_id}-"
                f"{symbol.replace('/', '-')}-{signal_close.isoformat()}"
            )
            records.append(
                {
                    "architecture_id": ARCHITECTURE_ID,
                    "source_architecture_id": SOURCE_ARCHITECTURE_ID,
                    "research_stage": RESEARCH_STAGE,
                    "hypothesis_id": hypothesis.hypothesis_id,
                    "engine_id": hypothesis.engine_id,
                    "engine_priority": hypothesis.engine_priority,
                    "engine_role": hypothesis.role,
                    "cooldown_hours": hypothesis.cooldown_hours,
                    "candidate_id": candidate_id,
                    "source_trade_id": candidate_id,
                    "symbol": symbol,
                    "canonical_id": str(_metadata_value(metadata, "canonical_id", symbol=symbol)),
                    "core_asset": bool(_metadata_value(metadata, "core", symbol=symbol)),
                    "liquidity_rank": int(
                        _finite(
                            _metadata_value(metadata, "liquidity_rank", symbol=symbol),
                            name=f"liquidity_rank:{symbol}",
                        )
                    ),
                    "liquidity_tier": str(
                        _metadata_value(metadata, "liquidity_tier", symbol=symbol)
                    ),
                    "signal_close": signal_close,
                    "entry_open_time": signal_close,
                    "entry_bar_close": entry_bar_close,
                    "entry_price": _finite(next_row["open"], name=f"entry_price:{symbol}"),
                    "atr14_at_signal": _finite(
                        signal_row["lh_1d_atr14"],
                        name=f"daily_atr14:{symbol}",
                    ),
                    "stop_atr_multiple": hypothesis.initial_stop_atr_multiple,
                    "trail_activation_r": hypothesis.trail_activation_r,
                    "trail_atr_multiple": hypothesis.trail_atr_multiple,
                    "maximum_holding_bars": maximum_holding_bars,
                    "market_regime": market_regime,
                    "daily_return20_rank": _finite(
                        signal_row["lh_rank20"], name=f"rank20:{symbol}"
                    ),
                    "daily_return60_rank": _finite(
                        signal_row["lh_rank60"], name=f"rank60:{symbol}"
                    ),
                    "daily_drawdown55": _finite(
                        signal_row["lh_drawdown55"],
                        name=f"drawdown55:{symbol}",
                    ),
                    "daily_volume_ratio20": _finite(
                        signal_row["lh_volume_ratio20"],
                        name=f"volume_ratio20:{symbol}",
                    ),
                    "4h_context_close": _timestamp(signal_row["4h_timestamp"]),
                    "1d_context_close": _timestamp(signal_row["lh_1d_timestamp"]),
                    "1w_context_close": _timestamp(signal_row["lh_1w_timestamp"]),
                }
            )
    if not records:
        return pd.DataFrame(
            columns=[
                "architecture_id",
                "source_architecture_id",
                "research_stage",
                "hypothesis_id",
                "engine_id",
                "engine_priority",
                "engine_role",
                "cooldown_hours",
                "candidate_id",
                "source_trade_id",
                "symbol",
                "canonical_id",
                "core_asset",
                "liquidity_rank",
                "liquidity_tier",
                "signal_close",
                "entry_open_time",
                "entry_bar_close",
                "entry_price",
                "atr14_at_signal",
                "stop_atr_multiple",
                "trail_activation_r",
                "trail_atr_multiple",
                "maximum_holding_bars",
                "market_regime",
                "daily_return20_rank",
                "daily_return60_rank",
                "daily_drawdown55",
                "daily_volume_ratio20",
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


def hypothesis_registry_rows() -> list[dict[str, object]]:
    return [hypothesis.to_record() for hypothesis in HYPOTHESIS_REGISTRY]


__all__ = [
    "ARCHITECTURE_ID",
    "HYPOTHESIS_BY_ID",
    "HYPOTHESIS_IDS",
    "HYPOTHESIS_REGISTRY",
    "LongHorizonHypothesis",
    "RD16TSignalError",
    "RESEARCH_STAGE",
    "SOURCE_ARCHITECTURE_ID",
    "build_long_horizon_candidates",
    "build_long_horizon_feature_frames",
    "hypothesis_registry_rows",
    "hypothesis_signal_mask",
]
