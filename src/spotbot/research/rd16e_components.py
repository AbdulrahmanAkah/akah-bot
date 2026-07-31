from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

import pandas as pd

FAMILY_IDS: Final = (
    "MTF_TREND_BREAKOUT",
    "MTF_PULLBACK_RECLAIM",
    "MTF_COMPRESSION_EXPANSION",
    "MTF_RANGE_RECLAIM",
)

VARIANT_IDS: Final = (
    "BASELINE",
    "REGIME_GATE",
    "VOLATILITY_GATE",
    "ASSET_GATE",
    "REGIME_VOLATILITY_GATE",
    "REGIME_ASSET_GATE",
    "ALL_DIAGNOSTIC_GATES",
    "STRUCTURAL_CONFIRMATION",
    "DIAGNOSTIC_PLUS_STRUCTURE",
    "FULL_REMEDIATION_STACK",
)

ALLOWED_REGIMES: Final = {
    "MTF_TREND_BREAKOUT": frozenset({"BEAR", "BULL", "STRONG_BULL"}),
    "MTF_PULLBACK_RECLAIM": frozenset({"BEAR", "BULL", "STRONG_BULL"}),
    "MTF_COMPRESSION_EXPANSION": frozenset({"BEAR", "STRONG_BULL"}),
    "MTF_RANGE_RECLAIM": frozenset({"TRANSITION"}),
}

ALLOWED_VOLATILITY: Final = {
    "MTF_TREND_BREAKOUT": frozenset({"LOW_VOLATILITY", "NORMAL_VOLATILITY"}),
    "MTF_PULLBACK_RECLAIM": frozenset({"NORMAL_VOLATILITY"}),
    "MTF_COMPRESSION_EXPANSION": frozenset({"LOW_VOLATILITY", "NORMAL_VOLATILITY"}),
    "MTF_RANGE_RECLAIM": frozenset({"LOW_VOLATILITY", "NORMAL_VOLATILITY", "HIGH_VOLATILITY"}),
}

ALLOWED_ASSETS: Final = {
    "MTF_TREND_BREAKOUT": frozenset({"BTC/USDT", "ETH/USDT", "LINK/USDT", "SOL/USDT"}),
    "MTF_PULLBACK_RECLAIM": frozenset({"AVAX/USDT", "BTC/USDT", "ETH/USDT", "SOL/USDT"}),
    "MTF_COMPRESSION_EXPANSION": frozenset(
        {"AVAX/USDT", "BTC/USDT", "ETH/USDT", "NEAR/USDT", "SOL/USDT"}
    ),
    "MTF_RANGE_RECLAIM": frozenset({"SOL/USDT"}),
}

COOLDOWN_HOURS: Final = 24
FEE_BUFFER_FRACTION: Final = 0.002

FEATURE_COLUMNS: Final = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "ema20",
    "atr14",
    "prior_high24",
    "volume_median20",
    "4h_close",
    "4h_ema20",
    "4h_ema50",
    "prior_high12",
    "range_1h",
    "4h_atr_ratio",
    "prior_low12",
)


class RD16EComponentError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VariantSpec:
    variant_id: str
    description: str
    dimensions: tuple[str, ...]


VARIANT_SPECS: Final = (
    VariantSpec("BASELINE", "Frozen RD16-D baseline.", ("baseline",)),
    VariantSpec("REGIME_GATE", "Family-specific market-regime gate.", ("regime",)),
    VariantSpec(
        "VOLATILITY_GATE",
        "Family-specific volatility-regime gate.",
        ("volatility",),
    ),
    VariantSpec("ASSET_GATE", "Family-specific asset eligibility gate.", ("asset",)),
    VariantSpec(
        "REGIME_VOLATILITY_GATE",
        "Combined regime and volatility gates.",
        ("regime", "volatility"),
    ),
    VariantSpec(
        "REGIME_ASSET_GATE",
        "Combined regime and asset gates.",
        ("regime", "asset"),
    ),
    VariantSpec(
        "ALL_DIAGNOSTIC_GATES",
        "Combined regime, volatility, and asset gates.",
        ("regime", "volatility", "asset"),
    ),
    VariantSpec(
        "STRUCTURAL_CONFIRMATION",
        "Stronger causal signal confirmation only.",
        ("structure",),
    ),
    VariantSpec(
        "DIAGNOSTIC_PLUS_STRUCTURE",
        "All diagnostic gates plus stronger structural confirmation.",
        ("regime", "volatility", "asset", "structure"),
    ),
    VariantSpec(
        "FULL_REMEDIATION_STACK",
        "Diagnostic gates, structure, fee buffer, and same-symbol cooldown.",
        ("regime", "volatility", "asset", "structure", "fee_buffer", "cooldown"),
    ),
)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise RD16EComponentError(f"Missing required column: {column}")
    return pd.to_numeric(frame[column], errors="raise")


def _true_mask(frame: pd.DataFrame) -> pd.Series:
    return pd.Series(True, index=frame.index, dtype=bool)


def attach_signal_features(
    trades: pd.DataFrame,
    *,
    feature_frames: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    if "symbol" not in trades.columns or "signal_close" not in trades.columns:
        raise RD16EComponentError("Trades require symbol and signal_close columns.")

    feature_parts: list[pd.DataFrame] = []
    for symbol, raw in feature_frames.items():
        missing = sorted(set(("timestamp", *FEATURE_COLUMNS)).difference(raw.columns))
        if missing:
            raise RD16EComponentError(f"Feature frame missing {symbol} columns: {missing}")
        selected = raw.loc[:, ["timestamp", *FEATURE_COLUMNS]].copy()
        selected["timestamp"] = pd.to_datetime(
            selected["timestamp"], utc=True, errors="raise"
        ).astype("datetime64[ns, UTC]")
        selected.insert(0, "symbol", symbol)
        selected = selected.rename(
            columns={
                "timestamp": "signal_close",
                **{column: f"f_{column}" for column in FEATURE_COLUMNS},
            }
        )
        feature_parts.append(selected)

    features = pd.concat(feature_parts, ignore_index=True)
    working = trades.copy()
    working["signal_close"] = pd.to_datetime(
        working["signal_close"], utc=True, errors="raise"
    ).astype("datetime64[ns, UTC]")
    merged = working.merge(
        features,
        on=["symbol", "signal_close"],
        how="left",
        validate="many_to_one",
    )
    if bool(merged["f_close"].isna().any()):
        missing_rows = int(merged["f_close"].isna().sum())
        raise RD16EComponentError(f"Signal features missing for {missing_rows} trades.")
    return merged


def regime_mask(frame: pd.DataFrame, family_id: str) -> pd.Series:
    allowed = ALLOWED_REGIMES[family_id]
    return frame["market_regime"].astype(str).isin(allowed)


def volatility_mask(frame: pd.DataFrame, family_id: str) -> pd.Series:
    allowed = ALLOWED_VOLATILITY[family_id]
    return frame["volatility_regime"].astype(str).isin(allowed)


def asset_mask(frame: pd.DataFrame, family_id: str) -> pd.Series:
    allowed = ALLOWED_ASSETS[family_id]
    return frame["symbol"].astype(str).isin(allowed)


def structural_mask(frame: pd.DataFrame, family_id: str) -> pd.Series:
    close = _numeric(frame, "f_close")
    open_price = _numeric(frame, "f_open")
    high = _numeric(frame, "f_high")
    low = _numeric(frame, "f_low")
    atr = _numeric(frame, "f_atr14")
    safe_range = (high - low).where((high - low) > 0.0, other=float("nan"))

    if family_id == "MTF_TREND_BREAKOUT":
        prior_high = _numeric(frame, "f_prior_high24")
        volume = _numeric(frame, "f_volume")
        median_volume = _numeric(frame, "f_volume_median20")
        ema20_4h = _numeric(frame, "f_4h_ema20")
        ema50_4h = _numeric(frame, "f_4h_ema50")
        return (
            (close - prior_high >= 0.25 * atr)
            & (volume >= median_volume)
            & ((ema20_4h - ema50_4h) / ema50_4h >= 0.002)
        ).fillna(False)

    if family_id == "MTF_PULLBACK_RECLAIM":
        ema20 = _numeric(frame, "f_ema20")
        ema20_4h = _numeric(frame, "f_4h_ema20")
        ema50_4h = _numeric(frame, "f_4h_ema50")
        return (
            (close > open_price) & (close - ema20 >= 0.10 * atr) & (ema20_4h > ema50_4h)
        ).fillna(False)

    if family_id == "MTF_COMPRESSION_EXPANSION":
        prior_high = _numeric(frame, "f_prior_high12")
        range_1h = _numeric(frame, "f_range_1h")
        atr_ratio = _numeric(frame, "f_4h_atr_ratio")
        return (
            (range_1h >= atr) & (atr_ratio <= 0.90) & (close - prior_high >= 0.10 * atr)
        ).fillna(False)

    if family_id == "MTF_RANGE_RECLAIM":
        prior_low = _numeric(frame, "f_prior_low12")
        close_location = (close - low) / safe_range
        return (
            (close > open_price) & (close_location >= 0.70) & (close - prior_low >= 0.25 * atr)
        ).fillna(False)

    raise KeyError(f"Unknown family ID: {family_id}")


def fee_buffer_mask(frame: pd.DataFrame, family_id: str) -> pd.Series:
    close = _numeric(frame, "f_close")
    if family_id == "MTF_TREND_BREAKOUT":
        trigger = _numeric(frame, "f_prior_high24")
    elif family_id == "MTF_PULLBACK_RECLAIM":
        trigger = _numeric(frame, "f_ema20")
    elif family_id == "MTF_COMPRESSION_EXPANSION":
        trigger = _numeric(frame, "f_prior_high12")
    elif family_id == "MTF_RANGE_RECLAIM":
        trigger = _numeric(frame, "f_prior_low12")
    else:
        raise KeyError(f"Unknown family ID: {family_id}")
    return (((close - trigger) / close) >= FEE_BUFFER_FRACTION).fillna(False)


def apply_same_symbol_cooldown(
    frame: pd.DataFrame,
    *,
    hours: int = COOLDOWN_HOURS,
) -> pd.DataFrame:
    if hours <= 0:
        raise ValueError("Cooldown hours must be positive.")
    ordered = frame.sort_values(
        by=["signal_close", "symbol", "trade_id"],
        kind="stable",
    )
    kept_indices: list[object] = []
    last_by_symbol: dict[str, pd.Timestamp] = {}
    minimum_delta = pd.Timedelta(hours=hours)
    for raw_index, raw_symbol, raw_time in ordered.loc[:, ["symbol", "signal_close"]].itertuples(
        index=True, name=None
    ):
        symbol = str(raw_symbol)
        signal_time = pd.Timestamp(cast(Any, raw_time))
        if signal_time.tzinfo is None:
            signal_time = signal_time.tz_localize("UTC")
        else:
            signal_time = signal_time.tz_convert("UTC")
        previous = last_by_symbol.get(symbol)
        if previous is not None and signal_time - previous < minimum_delta:
            continue
        kept_indices.append(raw_index)
        last_by_symbol[symbol] = signal_time
    return (
        frame.loc[kept_indices]
        .sort_values(
            by=["entry_open_time", "symbol", "signal_close"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def component_masks(frame: pd.DataFrame, family_id: str) -> dict[str, pd.Series]:
    return {
        "regime": regime_mask(frame, family_id),
        "volatility": volatility_mask(frame, family_id),
        "asset": asset_mask(frame, family_id),
        "structure": structural_mask(frame, family_id),
        "fee_buffer": fee_buffer_mask(frame, family_id),
    }


def apply_variant(
    frame: pd.DataFrame,
    *,
    family_id: str,
    variant_id: str,
) -> pd.DataFrame:
    if family_id not in FAMILY_IDS:
        raise KeyError(f"Unknown family ID: {family_id}")
    if variant_id not in VARIANT_IDS:
        raise KeyError(f"Unknown variant ID: {variant_id}")

    masks = component_masks(frame, family_id)
    selected = _true_mask(frame)
    if variant_id in {
        "REGIME_GATE",
        "REGIME_VOLATILITY_GATE",
        "REGIME_ASSET_GATE",
        "ALL_DIAGNOSTIC_GATES",
        "DIAGNOSTIC_PLUS_STRUCTURE",
        "FULL_REMEDIATION_STACK",
    }:
        selected &= masks["regime"]
    if variant_id in {
        "VOLATILITY_GATE",
        "REGIME_VOLATILITY_GATE",
        "ALL_DIAGNOSTIC_GATES",
        "DIAGNOSTIC_PLUS_STRUCTURE",
        "FULL_REMEDIATION_STACK",
    }:
        selected &= masks["volatility"]
    if variant_id in {
        "ASSET_GATE",
        "REGIME_ASSET_GATE",
        "ALL_DIAGNOSTIC_GATES",
        "DIAGNOSTIC_PLUS_STRUCTURE",
        "FULL_REMEDIATION_STACK",
    }:
        selected &= masks["asset"]
    if variant_id in {
        "STRUCTURAL_CONFIRMATION",
        "DIAGNOSTIC_PLUS_STRUCTURE",
        "FULL_REMEDIATION_STACK",
    }:
        selected &= masks["structure"]
    if variant_id == "FULL_REMEDIATION_STACK":
        selected &= masks["fee_buffer"]

    result = frame.loc[selected].copy().reset_index(drop=True)
    if variant_id == "FULL_REMEDIATION_STACK":
        result = apply_same_symbol_cooldown(result)
    return result


def gate_audit_rows(frame: pd.DataFrame, *, family_id: str) -> list[dict[str, object]]:
    masks = component_masks(frame, family_id)
    rows: list[dict[str, object]] = []
    total = len(frame)
    for component, mask in masks.items():
        kept = int(mask.sum())
        rows.append(
            {
                "family_id": family_id,
                "component": component,
                "input_trades": total,
                "kept_trades": kept,
                "removed_trades": total - kept,
                "kept_fraction": kept / total if total else None,
            }
        )
    cooldown_input = frame.loc[
        masks["regime"]
        & masks["volatility"]
        & masks["asset"]
        & masks["structure"]
        & masks["fee_buffer"]
    ].copy()
    cooldown_output = apply_same_symbol_cooldown(cooldown_input)
    rows.append(
        {
            "family_id": family_id,
            "component": "cooldown_after_full_stack",
            "input_trades": len(cooldown_input),
            "kept_trades": len(cooldown_output),
            "removed_trades": len(cooldown_input) - len(cooldown_output),
            "kept_fraction": (
                len(cooldown_output) / len(cooldown_input) if len(cooldown_input) else None
            ),
        }
    )
    return rows


__all__ = [
    "ALLOWED_ASSETS",
    "ALLOWED_REGIMES",
    "ALLOWED_VOLATILITY",
    "COOLDOWN_HOURS",
    "FAMILY_IDS",
    "FEE_BUFFER_FRACTION",
    "RD16EComponentError",
    "VARIANT_IDS",
    "VARIANT_SPECS",
    "VariantSpec",
    "apply_same_symbol_cooldown",
    "apply_variant",
    "attach_signal_features",
    "component_masks",
    "gate_audit_rows",
]
