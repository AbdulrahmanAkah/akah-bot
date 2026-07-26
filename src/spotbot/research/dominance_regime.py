"""Explainable multi-timeframe RD01 regime state machine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import pandas as pd


class DominanceRegime(StrEnum):
    BTC_LEADERSHIP = "BTC_LEADERSHIP"
    ETH_LEADERSHIP = "ETH_LEADERSHIP"
    LARGE_CAP_ROTATION = "LARGE_CAP_ROTATION"
    BROAD_ALT_EXPANSION = "BROAD_ALT_EXPANSION"
    CASH_FLIGHT = "CASH_FLIGHT"
    DRY_POWDER_BUILD = "DRY_POWDER_BUILD"
    FALSE_ALT_ROTATION = "FALSE_ALT_ROTATION"
    RISK_COMPRESSION = "RISK_COMPRESSION"
    MIXED_UNCONFIRMED = "MIXED_UNCONFIRMED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class RegimeDecision:
    timestamp: pd.Timestamp
    primary_regime: DominanceRegime
    secondary_regime: DominanceRegime | None
    confidence: float
    supporting_features: tuple[str, ...]
    contradicting_features: tuple[str, ...]
    reason_codes: tuple[str, ...]
    data_quality: str


def classify_regime(
    features: dict[str, Any],
    *,
    timestamp: pd.Timestamp,
    data_quality: str = "PASS",
) -> RegimeDecision:
    """Classify from signed causal slopes without fitted full-period thresholds."""
    required = (
        "btc_d_slope",
        "eth_d_slope",
        "stable_d_slope",
        "btc_market_cap_slope",
        "stable_market_cap_slope",
        "total_ex_stable_slope",
        "outside_top10_market_cap_slope",
        "outside_top10_to_btc_slope",
    )
    if data_quality != "PASS" or any(pd.isna(features.get(name)) for name in required):
        return RegimeDecision(
            pd.Timestamp(timestamp),
            DominanceRegime.INSUFFICIENT_DATA,
            None,
            0.0,
            (),
            (),
            ("INSUFFICIENT_DATA",),
            data_quality,
        )
    f = {name: float(features[name]) for name in required}
    reasons: list[str] = []
    regime = DominanceRegime.MIXED_UNCONFIRMED
    if (
        f["stable_d_slope"] > 0
        and f["total_ex_stable_slope"] < 0
        and f["btc_market_cap_slope"] < 0
    ):
        regime = DominanceRegime.CASH_FLIGHT
        reasons = ["STABLE_SHARE_RISING", "DENOMINATOR_CONTRACTION", "DAILY_CONFIRMED"]
    elif f["stable_market_cap_slope"] > 0 and f["total_ex_stable_slope"] >= 0:
        regime = DominanceRegime.DRY_POWDER_BUILD
        reasons = ["STABLE_SHARE_RISING", "STABLE_CAP_EXPANDING"]
    elif (
        f["btc_d_slope"] < 0
        and f["btc_market_cap_slope"] < 0
        and f["outside_top10_market_cap_slope"] < 0
        and f["stable_d_slope"] > 0
    ):
        regime = DominanceRegime.FALSE_ALT_ROTATION
        reasons = ["BTC_SHARE_FALLING", "DENOMINATOR_CONTRACTION"]
    elif (
        f["btc_d_slope"] < 0
        and f["stable_d_slope"] < 0
        and f["outside_top10_market_cap_slope"] > 0
        and f["outside_top10_to_btc_slope"] > 0
    ):
        regime = DominanceRegime.BROAD_ALT_EXPANSION
        reasons = [
            "OUTSIDE_TOP10_ABSOLUTE_EXPANSION",
            "OUTSIDE_TOP10_RELATIVE_EXPANSION",
        ]
    elif f["btc_d_slope"] > 0 and f["btc_market_cap_slope"] > 0:
        regime = DominanceRegime.BTC_LEADERSHIP
        reasons = ["BTC_SHARE_RISING", "BTC_ABSOLUTE_CAP_RISING"]
    elif f["eth_d_slope"] > 0 and f["btc_d_slope"] < 0:
        regime = DominanceRegime.ETH_LEADERSHIP
        reasons = ["ETH_ONLY_ROTATION"]
    confidence = min(1.0, 0.35 + 0.15 * len(reasons)) if reasons else 0.25
    return RegimeDecision(
        pd.Timestamp(timestamp),
        regime,
        None,
        confidence,
        tuple(required),
        (),
        tuple(reasons or ["TIMEFRAME_CONFLICT"]),
        data_quality,
    )


def compose_timeframes(
    daily: RegimeDecision,
    eight_hour: RegimeDecision | None,
    four_hour: RegimeDecision | None,
) -> RegimeDecision:
    """Keep Daily strategic and use intraday frames only as confirmation."""
    if daily.primary_regime is DominanceRegime.INSUFFICIENT_DATA:
        return daily
    confirmations = [
        decision
        for decision in (eight_hour, four_hour)
        if decision is not None and decision.primary_regime == daily.primary_regime
    ]
    conflict = any(
        decision is not None
        and decision.primary_regime
        not in {daily.primary_regime, DominanceRegime.MIXED_UNCONFIRMED}
        for decision in (eight_hour, four_hour)
    )
    reasons = list(daily.reason_codes)
    if eight_hour in confirmations:
        reasons.append("EIGHT_HOUR_CONFIRMED")
    if four_hour in confirmations:
        reasons.append("FOUR_HOUR_CONFIRMED")
    if conflict:
        reasons.append("TIMEFRAME_CONFLICT")
    confidence = min(1.0, daily.confidence + 0.1 * len(confirmations))
    if conflict:
        confidence = max(0.0, confidence - 0.2)
    return RegimeDecision(
        daily.timestamp,
        daily.primary_regime,
        None,
        confidence,
        daily.supporting_features,
        daily.contradicting_features,
        tuple(reasons),
        daily.data_quality,
    )

