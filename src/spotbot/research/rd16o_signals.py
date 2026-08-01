from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from spotbot.research.rd16d_metrics import market_regime_from_row
from spotbot.research.rd16n_signals import (
    NORMAL_HOLDING_BARS,
    STRONG_BULL_HOLDING_BARS,
    SignalHypothesis,
    build_extended_feature_frames,
)

ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"


class RD16OSignalError(RuntimeError):
    pass


HYPOTHESIS_REGISTRY: Final = (
    SignalHypothesis(
        hypothesis_id="QUALITY_MOMENTUM_BREAKOUT_V2",
        engine_id="QUALITY_MOMENTUM_BREAKOUT_ENGINE_V2",
        role="OFFENSIVE",
        description=(
            "Strong-Bull 12H breakout with breadth, relative-strength rank, "
            "volume quality, and anti-extension gates."
        ),
        stop_atr_multiple=1.25,
        cooldown_hours=24,
        engine_priority=30,
        fixed_conditions=(
            "Strong-Bull regime only",
            "close above prior 12H high",
            "EMA20 > EMA50 with positive EMA50 slope",
            "market breadth >= 67%",
            "24H relative-strength percentile >= 67%",
            "volume >= 1.50 x 20H median",
            "close location >= 0.75",
            "distance above EMA20 <= 2.50 ATR",
            "4H, 1D and 1W trend aligned",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="PULLBACK_REACCELERATION_V2",
        engine_id="PULLBACK_REACCELERATION_ENGINE_V2",
        role="DIVERSIFIER",
        description=(
            "Bull-regime low-volume pullback followed by EMA20 and VWAP "
            "reclaim with renewed participation."
        ),
        stop_atr_multiple=1.20,
        cooldown_hours=24,
        engine_priority=31,
        fixed_conditions=(
            "Bull or Strong-Bull regime",
            "previous close at or below EMA20 or VWAP24",
            "current close above EMA20 and VWAP24",
            "EMA20 > EMA50 with positive EMA50 slope",
            "prior 6H mean volume <= 20H median",
            "current volume >= 1.10 x 20H median",
            "market breadth >= 50%",
            "72H relative-strength percentile >= 50%",
            "4H, 1D and 1W trend aligned",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="SQUEEZE_TREND_RELEASE_V2",
        engine_id="SQUEEZE_TREND_RELEASE_ENGINE_V2",
        role="OFFENSIVE",
        description=(
            "Strong-Bull release from a rarer causal volatility squeeze with "
            "breadth, volume, and expansion confirmation."
        ),
        stop_atr_multiple=1.50,
        cooldown_hours=36,
        engine_priority=32,
        fixed_conditions=(
            "Strong-Bull regime only",
            "prior bandwidth <= causal 200H 15th percentile",
            "close above prior upper band and prior 12H high",
            "1H range >= 1.25 ATR",
            "volume >= 1.50 x 20H median",
            "market breadth >= 67%",
            "4H ATR ratio <= 0.85",
            "distance above EMA20 <= 3.00 ATR",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="BULL_LIQUIDITY_SWEEP_RECLAIM_V2",
        engine_id="BULL_LIQUIDITY_SWEEP_RECLAIM_ENGINE_V2",
        role="DIVERSIFIER",
        description=(
            "Bull-regime downside liquidity sweep that reclaims local "
            "structure, EMA20, and rolling VWAP."
        ),
        stop_atr_multiple=1.10,
        cooldown_hours=24,
        engine_priority=33,
        fixed_conditions=(
            "Bull or Strong-Bull regime",
            "low below prior 12H low",
            "close back above prior 12H low",
            "close above EMA20 and VWAP24",
            "lower wick ratio >= 0.45",
            "close location >= 0.65",
            "volume >= 1.25 x 20H median",
            "market breadth >= 50%",
            "4H and 1D trend aligned",
        ),
    ),
    SignalHypothesis(
        hypothesis_id="RELATIVE_STRENGTH_ROTATION_RECLAIM_V2",
        engine_id="RELATIVE_STRENGTH_ROTATION_RECLAIM_ENGINE_V2",
        role="OFFENSIVE",
        description=(
            "Top-ranked relative-strength asset reclaiming VWAP inside a "
            "broad Bull market without chasing extension."
        ),
        stop_atr_multiple=1.25,
        cooldown_hours=24,
        engine_priority=34,
        fixed_conditions=(
            "Bull or Strong-Bull regime",
            "24H relative-strength percentile >= 83%",
            "72H relative-strength percentile >= 67%",
            "previous close at or below VWAP24",
            "current close above VWAP24 and EMA20",
            "market breadth >= 67%",
            "volume >= 20H median",
            "distance above EMA20 <= 2.00 ATR",
            "4H and 1D trend aligned",
        ),
    ),
)

HYPOTHESIS_BY_ID: Final = {
    hypothesis.hypothesis_id: hypothesis for hypothesis in HYPOTHESIS_REGISTRY
}
HYPOTHESIS_IDS: Final = tuple(hypothesis.hypothesis_id for hypothesis in HYPOTHESIS_REGISTRY)

ALLOWED_REGIMES: Final = {
    "QUALITY_MOMENTUM_BREAKOUT_V2": frozenset({"STRONG_BULL"}),
    "PULLBACK_REACCELERATION_V2": frozenset({"BULL", "STRONG_BULL"}),
    "SQUEEZE_TREND_RELEASE_V2": frozenset({"STRONG_BULL"}),
    "BULL_LIQUIDITY_SWEEP_RECLAIM_V2": frozenset({"BULL", "STRONG_BULL"}),
    "RELATIVE_STRENGTH_ROTATION_RECLAIM_V2": frozenset({"BULL", "STRONG_BULL"}),
}


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


def _extend_second_gen_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    close = pd.to_numeric(working["close"], errors="raise")
    high = pd.to_numeric(working["high"], errors="raise")
    low = pd.to_numeric(working["low"], errors="raise")
    volume = pd.to_numeric(working["volume"], errors="raise")
    atr = pd.to_numeric(working["atr14"], errors="raise")
    ema20 = pd.to_numeric(working["ema20"], errors="raise")
    ema50 = pd.to_numeric(working["ema50"], errors="raise")
    volume_median = pd.to_numeric(
        working["volume_median20"],
        errors="raise",
    )

    working["previous_ema20"] = ema20.shift(1)
    working["ema50_slope12_v2"] = ema50 - ema50.shift(12)
    working["prior_low12_v2"] = low.rolling(12, min_periods=12).min().shift(1)
    working["prior_high12_v2"] = high.rolling(12, min_periods=12).max().shift(1)
    working["volume_ratio20_v2"] = _safe_divide(volume, volume_median)
    working["prior_volume_mean6_ratio_v2"] = _safe_divide(
        volume.shift(1).rolling(6, min_periods=6).mean(),
        volume_median,
    )
    working["ema20_distance_atr_v2"] = _safe_divide(
        close - ema20,
        atr,
    )
    working["prior_band_width_q15_200_v2"] = (
        pd.to_numeric(
            working["prior_band_width20"],
            errors="raise",
        )
        .rolling(200, min_periods=120)
        .quantile(0.15)
    )
    working = working.replace([np.inf, -np.inf], np.nan)
    return working


def build_second_gen_feature_frames(
    feature_frames: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    extended = build_extended_feature_frames(feature_frames)
    working = {symbol: _extend_second_gen_frame(frame) for symbol, frame in extended.items()}

    indexed: dict[str, pd.DataFrame] = {}
    for symbol, frame in working.items():
        local = frame.copy()
        local["timestamp"] = pd.to_datetime(
            local["timestamp"],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
        indexed[symbol] = local.set_index("timestamp")

    return24 = pd.concat(
        {
            symbol: pd.to_numeric(frame["return24"], errors="raise")
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    return72 = pd.concat(
        {
            symbol: pd.to_numeric(frame["return72"], errors="raise")
            for symbol, frame in indexed.items()
        },
        axis=1,
    )
    rank24 = return24.rank(axis=1, pct=True, method="average")
    rank72 = return72.rank(axis=1, pct=True, method="average")

    breadth_components: list[pd.DataFrame] = []
    for symbol, frame in indexed.items():
        breadth_components.append(
            pd.DataFrame(
                {
                    (symbol, "1h"): (
                        pd.to_numeric(frame["close"], errors="raise")
                        > pd.to_numeric(frame["ema20"], errors="raise")
                    ),
                    (symbol, "4h"): (
                        pd.to_numeric(frame["4h_close"], errors="raise")
                        > pd.to_numeric(frame["4h_ema20"], errors="raise")
                    ),
                    (symbol, "1d"): (
                        pd.to_numeric(frame["1d_close"], errors="raise")
                        > pd.to_numeric(frame["1d_ema50"], errors="raise")
                    ),
                },
                index=frame.index,
            )
        )
    breadth_matrix = pd.concat(breadth_components, axis=1)
    breadth = breadth_matrix.astype(float).mean(axis=1, skipna=True)

    result: dict[str, pd.DataFrame] = {}
    for symbol, frame in indexed.items():
        local = frame.copy()
        local["return24_rank_pct_v2"] = rank24[symbol].reindex(local.index)
        local["return72_rank_pct_v2"] = rank72[symbol].reindex(local.index)
        local["market_breadth_v2"] = breadth.reindex(local.index)
        result[symbol] = local.reset_index()
    return result


def second_gen_signal_mask(
    frame: pd.DataFrame,
    hypothesis_id: str,
) -> pd.Series:
    if hypothesis_id == "QUALITY_MOMENTUM_BREAKOUT_V2":
        raw = (
            (frame["close"] > frame["prior_high12_v2"])
            & (frame["ema20"] > frame["ema50"])
            & (frame["ema50_slope12_v2"] > 0.0)
            & (frame["market_breadth_v2"] >= 0.67)
            & (frame["return24_rank_pct_v2"] >= 0.67)
            & (frame["return72_rank_pct_v2"] >= 0.50)
            & (frame["volume_ratio20_v2"] >= 1.50)
            & (frame["close_location"] >= 0.75)
            & (frame["ema20_distance_atr_v2"] >= 0.0)
            & (frame["ema20_distance_atr_v2"] <= 2.50)
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > frame["1d_ema50"])
            & (frame["1w_close"] > frame["1w_ema40"])
        )
    elif hypothesis_id == "PULLBACK_REACCELERATION_V2":
        prior_pullback = (frame["previous_close"] <= frame["previous_ema20"]) | (
            frame["previous_close"] <= frame["previous_vwap24"]
        )
        raw = (
            prior_pullback
            & (frame["close"] > frame["ema20"])
            & (frame["close"] > frame["vwap24"])
            & (frame["ema20"] > frame["ema50"])
            & (frame["ema50_slope12_v2"] > 0.0)
            & (frame["prior_volume_mean6_ratio_v2"] <= 1.00)
            & (frame["volume_ratio20_v2"] >= 1.10)
            & (frame["close_location"] >= 0.65)
            & (frame["market_breadth_v2"] >= 0.50)
            & (frame["return72_rank_pct_v2"] >= 0.50)
            & (frame["4h_close"] > frame["4h_ema50"])
            & (frame["1d_close"] > frame["1d_ema50"])
            & (frame["1w_close"] > 0.95 * frame["1w_ema40"])
        )
    elif hypothesis_id == "SQUEEZE_TREND_RELEASE_V2":
        raw = (
            (frame["prior_band_width20"] <= frame["prior_band_width_q15_200_v2"])
            & (frame["close"] > frame["prior_band_upper20"])
            & (frame["close"] > frame["prior_high12_v2"])
            & (frame["range_1h"] >= 1.25 * frame["atr14"])
            & (frame["volume_ratio20_v2"] >= 1.50)
            & (frame["market_breadth_v2"] >= 0.67)
            & (frame["return24_rank_pct_v2"] >= 0.50)
            & (frame["4h_atr_ratio"] <= 0.85)
            & (frame["ema20_distance_atr_v2"] <= 3.00)
            & (frame["1d_close"] > frame["1d_ema50"])
            & (frame["1w_close"] > frame["1w_ema40"])
        )
    elif hypothesis_id == "BULL_LIQUIDITY_SWEEP_RECLAIM_V2":
        raw = (
            (frame["low"] < frame["prior_low12_v2"])
            & (frame["close"] > frame["prior_low12_v2"])
            & (frame["close"] > frame["ema20"])
            & (frame["close"] > frame["vwap24"])
            & (frame["lower_wick_ratio"] >= 0.45)
            & (frame["close_location"] >= 0.65)
            & (frame["volume_ratio20_v2"] >= 1.25)
            & (frame["market_breadth_v2"] >= 0.50)
            & (frame["return72_rank_pct_v2"] >= 0.40)
            & (frame["4h_close"] > frame["4h_ema50"])
            & (frame["1d_close"] > frame["1d_ema50"])
        )
    elif hypothesis_id == "RELATIVE_STRENGTH_ROTATION_RECLAIM_V2":
        raw = (
            (frame["return24_rank_pct_v2"] >= 0.83)
            & (frame["return72_rank_pct_v2"] >= 0.67)
            & (frame["previous_close"] <= frame["previous_vwap24"])
            & (frame["close"] > frame["vwap24"])
            & (frame["close"] > frame["ema20"])
            & (frame["market_breadth_v2"] >= 0.67)
            & (frame["volume_ratio20_v2"] >= 1.00)
            & (frame["ema20_distance_atr_v2"] >= 0.0)
            & (frame["ema20_distance_atr_v2"] <= 2.00)
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["1d_close"] > frame["1d_ema50"])
        )
    else:
        raise KeyError(f"Unknown RD16-O hypothesis ID: {hypothesis_id}")

    normalized = raw.fillna(False).astype(bool)
    previous = normalized.shift(1, fill_value=False).astype(bool)
    return normalized & ~previous


def build_second_gen_candidates(
    feature_frames: Mapping[str, pd.DataFrame],
    *,
    hypothesis: SignalHypothesis,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    allowed = ALLOWED_REGIMES[hypothesis.hypothesis_id]

    for symbol in sorted(feature_frames):
        frame = feature_frames[symbol]
        mask = second_gen_signal_mask(frame, hypothesis.hypothesis_id)
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
            if market_regime not in allowed:
                continue

            holding_bars = (
                STRONG_BULL_HOLDING_BARS if market_regime == "STRONG_BULL" else NORMAL_HOLDING_BARS
            )
            symbol_token = symbol.replace("/", "-")
            candidate_id = (
                f"RD16O-{hypothesis.hypothesis_id}-{symbol_token}-{signal_close.isoformat()}"
            )
            records.append(
                {
                    "architecture_id": ARCHITECTURE_ID,
                    "research_stage": "RD16O",
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
                    "market_breadth_at_signal": float(signal_row["market_breadth_v2"]),
                    "return24_rank_at_signal": float(signal_row["return24_rank_pct_v2"]),
                    "return72_rank_at_signal": float(signal_row["return72_rank_pct_v2"]),
                    "volume_ratio_at_signal": float(signal_row["volume_ratio20_v2"]),
                    "ema20_distance_atr_at_signal": float(signal_row["ema20_distance_atr_v2"]),
                    "4h_context_close": _timestamp(signal_row["4h_timestamp"]),
                    "1d_context_close": _timestamp(signal_row["1d_timestamp"]),
                    "1w_context_close": _timestamp(signal_row["1w_timestamp"]),
                }
            )

    columns = [
        "architecture_id",
        "research_stage",
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
        "market_breadth_at_signal",
        "return24_rank_at_signal",
        "return72_rank_at_signal",
        "volume_ratio_at_signal",
        "ema20_distance_atr_at_signal",
        "4h_context_close",
        "1d_context_close",
        "1w_context_close",
    ]
    if not records:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame.from_records(records, columns=columns)
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
    "ALLOWED_REGIMES",
    "ARCHITECTURE_ID",
    "HYPOTHESIS_BY_ID",
    "HYPOTHESIS_IDS",
    "HYPOTHESIS_REGISTRY",
    "RD16OSignalError",
    "build_second_gen_candidates",
    "build_second_gen_feature_frames",
    "second_gen_signal_mask",
]
