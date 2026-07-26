"""Monotonic, risk-reducing position sizing without Kelly or leverage."""

from __future__ import annotations

import math

from spotbot.research.adaptive_trade_types import PositionSizingDecision


def _bounded_quality(value: float, *, floor: float = 0.0) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(floor, value))


def size_position(
    *,
    baseline_notional: float,
    available_cash: float,
    total_exposure: float,
    maximum_portfolio_exposure: float,
    regime_quality: float,
    liquidity_quality: float,
    volatility_quality: float,
    correlation_quality: float,
    data_confidence: float,
    position_cap: float,
    liquidity_cap: float,
) -> PositionSizingDecision:
    """Reduce a frozen baseline size through bounded multipliers only."""
    if baseline_notional < 0 or available_cash < 0:
        raise ValueError("negative notional or cash")
    multipliers = (
        _bounded_quality(regime_quality),
        _bounded_quality(liquidity_quality),
        _bounded_quality(volatility_quality),
        _bounded_quality(correlation_quality),
        _bounded_quality(data_confidence),
    )
    multiplier = math.prod(multipliers)
    remaining_exposure = max(0.0, maximum_portfolio_exposure - total_exposure)
    caps = (
        baseline_notional * multiplier,
        available_cash,
        position_cap,
        liquidity_cap,
        remaining_exposure,
    )
    effective = max(0.0, min(caps))
    reasons: list[str] = []
    if multiplier < 1.0:
        reasons.append("RISK_MULTIPLIERS_REDUCED_SIZE")
    if effective <= 0:
        reasons.append("BLOCK_NEW_ENTRY")
    return PositionSizingDecision(
        baseline_notional,
        effective,
        effective / baseline_notional if baseline_notional > 0 else 0.0,
        effective <= 0,
        tuple(reasons),
    )

