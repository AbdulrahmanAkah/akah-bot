"""Fail-closed portfolio emergency coordination for ATI V1."""

from __future__ import annotations

from dataclasses import dataclass

from spotbot.research.adaptive_trade_types import PortfolioRiskState


@dataclass(frozen=True)
class PortfolioRiskDecision:
    state: PortfolioRiskState
    allow_entries: bool
    maximum_new_size_multiplier: float
    reason_codes: tuple[str, ...]


def coordinate_portfolio_risk(
    *,
    total_exposure: float,
    drawdown: float,
    correlation_spike_confirmed: bool,
    cash_flight_confirmed: bool,
    liquidity_shock_confirmed: bool,
    data_quality_pass: bool,
) -> PortfolioRiskDecision:
    if not 0.0 <= total_exposure <= 1.0:
        raise ValueError("portfolio exposure outside spot-only bounds")
    if not data_quality_pass:
        return PortfolioRiskDecision(
            PortfolioRiskState.DATA_BLOCKED, False, 0.0, ("DATA_QUALITY_FAILURE",)
        )
    if drawdown >= 0.24 or liquidity_shock_confirmed:
        return PortfolioRiskDecision(
            PortfolioRiskState.EMERGENCY,
            False,
            0.0,
            ("PORTFOLIO_EMERGENCY",),
        )
    if cash_flight_confirmed and correlation_spike_confirmed:
        return PortfolioRiskDecision(
            PortfolioRiskState.DEFENSIVE,
            False,
            0.0,
            ("CONFIRMED_CASH_FLIGHT", "CORRELATION_SPIKE"),
        )
    if cash_flight_confirmed or correlation_spike_confirmed or drawdown >= 0.12:
        return PortfolioRiskDecision(
            PortfolioRiskState.CAUTIOUS,
            True,
            0.5,
            ("CAUTIOUS_EXPOSURE",),
        )
    return PortfolioRiskDecision(PortfolioRiskState.NORMAL, True, 1.0, ())

