from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd


@dataclass(frozen=True, slots=True)
class FamilyRegistration:
    family_id: str
    description: str
    stop_atr_multiple: float
    maximum_holding_bars: int
    fixed_parameters: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "family_id": self.family_id,
            "description": self.description,
            "stop_atr_multiple": self.stop_atr_multiple,
            "maximum_holding_bars": self.maximum_holding_bars,
            "fixed_parameters": "; ".join(self.fixed_parameters),
        }


FAMILY_REGISTRY: Final = (
    FamilyRegistration(
        family_id="MTF_TREND_BREAKOUT",
        description=("1H breakout with aligned bullish 4H, 1D and 1W context."),
        stop_atr_multiple=1.5,
        maximum_holding_bars=48,
        fixed_parameters=(
            "1H close above prior 24H high",
            "1H volume >= 0.8 x 20H median",
            "4H close > EMA20 > EMA50",
            "1D close > EMA50",
            "1W close > EMA20",
        ),
    ),
    FamilyRegistration(
        family_id="MTF_PULLBACK_RECLAIM",
        description=("1H EMA20 reclaim inside aligned higher-timeframe uptrend."),
        stop_atr_multiple=1.25,
        maximum_holding_bars=48,
        fixed_parameters=(
            "previous 1H close <= previous EMA20",
            "current 1H low <= EMA20 and close > EMA20",
            "4H close > EMA50",
            "1D close > EMA50",
            "1W close > 0.95 x EMA40",
        ),
    ),
    FamilyRegistration(
        family_id="MTF_COMPRESSION_EXPANSION",
        description=("1H range expansion from non-expanding 4H volatility."),
        stop_atr_multiple=1.5,
        maximum_holding_bars=48,
        fixed_parameters=(
            "4H ATR14 <= rolling median ATR",
            "1H close above prior 12H high",
            "1H range >= 0.8 x ATR14",
            "1D close > 0.95 x EMA50",
            "1W close > 0.90 x EMA40",
        ),
    ),
    FamilyRegistration(
        family_id="MTF_RANGE_RECLAIM",
        description=("1H downside sweep and reclaim with non-bearish daily/weekly context."),
        stop_atr_multiple=1.25,
        maximum_holding_bars=48,
        fixed_parameters=(
            "1H low below prior 12H low",
            "1H close back above prior 12H low",
            "1H bullish close",
            "1D close > 0.85 x EMA50",
            "1W close > 0.85 x EMA40",
        ),
    ),
)

REGISTRY_BY_ID: Final = {registration.family_id: registration for registration in FAMILY_REGISTRY}


def family_signal_mask(
    frame: pd.DataFrame,
    family_id: str,
) -> pd.Series:
    if family_id == "MTF_TREND_BREAKOUT":
        raw = (
            (frame["close"] > frame["prior_high24"])
            & (frame["volume"] >= 0.8 * frame["volume_median20"])
            & (frame["4h_close"] > frame["4h_ema20"])
            & (frame["4h_ema20"] > frame["4h_ema50"])
            & (frame["1d_close"] > frame["1d_ema50"])
            & (frame["1w_close"] > frame["1w_ema20"])
        )
    elif family_id == "MTF_PULLBACK_RECLAIM":
        raw = (
            (frame["previous_close"] <= frame["previous_ema20"])
            & (frame["low"] <= frame["ema20"])
            & (frame["close"] > frame["ema20"])
            & (frame["4h_close"] > frame["4h_ema50"])
            & (frame["1d_close"] > frame["1d_ema50"])
            & (frame["1w_close"] > 0.95 * frame["1w_ema40"])
        )
    elif family_id == "MTF_COMPRESSION_EXPANSION":
        raw = (
            (frame["4h_atr_ratio"] <= 1.0)
            & (frame["close"] > frame["prior_high12"])
            & (frame["range_1h"] >= 0.8 * frame["atr14"])
            & (frame["1d_close"] > 0.95 * frame["1d_ema50"])
            & (frame["1w_close"] > 0.90 * frame["1w_ema40"])
        )
    elif family_id == "MTF_RANGE_RECLAIM":
        raw = (
            (frame["low"] < frame["prior_low12"])
            & (frame["close"] > frame["prior_low12"])
            & (frame["close"] > frame["open"])
            & (frame["1d_close"] > 0.85 * frame["1d_ema50"])
            & (frame["1w_close"] > 0.85 * frame["1w_ema40"])
        )
    else:
        raise KeyError(f"Unknown family ID: {family_id}")

    raw = raw.fillna(False).astype(bool)
    previous = raw.shift(1, fill_value=False).astype(bool)
    return raw & ~previous


def build_candidate_frame(
    frame: pd.DataFrame,
    *,
    symbol: str,
    registration: FamilyRegistration,
) -> pd.DataFrame:
    signal_mask = family_signal_mask(
        frame,
        registration.family_id,
    )
    records: list[dict[str, object]] = []
    signal_positions = [
        position for position, active in enumerate(signal_mask.tolist()) if bool(active)
    ]
    for position in signal_positions:
        next_position = position + 1
        if next_position >= len(frame):
            continue
        signal_row = frame.iloc[position]
        next_row = frame.iloc[next_position]
        signal_close = pd.Timestamp(signal_row["timestamp"])
        entry_bar_close = pd.Timestamp(next_row["timestamp"])
        if entry_bar_close - signal_close != pd.Timedelta(hours=1):
            continue
        records.append(
            {
                "family_id": registration.family_id,
                "symbol": symbol,
                "signal_close": signal_close,
                "entry_open_time": signal_close,
                "entry_bar_close": entry_bar_close,
                "entry_price": float(next_row["open"]),
                "atr14_at_signal": float(signal_row["atr14"]),
                "signal_low": float(signal_row["low"]),
                "signal_high": float(signal_row["high"]),
                "4h_context_close": pd.Timestamp(signal_row["4h_timestamp"]),
                "1d_context_close": pd.Timestamp(signal_row["1d_timestamp"]),
                "1w_context_close": pd.Timestamp(signal_row["1w_timestamp"]),
            }
        )
    return pd.DataFrame.from_records(records)
