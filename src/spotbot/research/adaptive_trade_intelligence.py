"""Explainable scorecard for AdaptiveTradeIntelligenceV1."""

from __future__ import annotations

from spotbot.research.adaptive_position_sizing import size_position
from spotbot.research.adaptive_stops import update_long_stop
from spotbot.research.adaptive_trade_types import (
    ManagementMode,
    OpenPositionState,
    TargetMode,
    TradeManagementDecision,
    TradeMarketContext,
    TradeRegimeContext,
)


def _score(value: float) -> float:
    return min(100.0, max(0.0, value * 100.0))


class AdaptiveTradeIntelligenceV1:
    """Causal state machine; scores are ordinal, never probabilities."""

    policy_version = "ATI-V1-FROZEN-2021-2024"

    def decide(
        self,
        *,
        market: TradeMarketContext,
        regime: TradeRegimeContext,
        position: OpenPositionState,
        baseline_notional: float,
        available_cash: float,
        portfolio_exposure: float,
        suggested_structural_stop: float | None,
        maximum_holding_bars: int = 84,
    ) -> TradeManagementDecision:
        continuation = _score(
            0.45 * market.trend_persistence
            + 0.25 * market.breadth
            + 0.30 * regime.support
        )
        quality = _score(
            0.4 * market.trend_persistence
            + 0.3 * market.liquidity_quality
            + 0.3 * regime.timeframe_alignment
        )
        protection = _score(
            min(1.0, position.mfe_r / 3.0)
            * (1.0 - 0.5 * regime.support)
        )
        reasons: list[str] = []
        if regime.data_quality != "PASS" or market.data_confidence <= 0:
            mode = ManagementMode.INSUFFICIENT_DATA
            reasons.append("DATA_QUALITY_FAILURE")
        elif position.bars_held >= maximum_holding_bars:
            mode = ManagementMode.EXIT
            reasons.append("MAX_HOLD_REACHED")
        elif not position.structure_intact:
            mode = ManagementMode.EXIT
            reasons.append("STRUCTURE_INVALIDATED")
        elif regime.cash_flight_confirmed and position.mfe_r > 0:
            mode = ManagementMode.PROTECT
            reasons.append("CASH_FLIGHT_WARNING")
        elif continuation >= 70 and market.liquidity_quality >= 0.5:
            mode = ManagementMode.BREATHE
            reasons.extend(("TREND_PERSISTENCE_HIGH", "REGIME_SUPPORTIVE"))
        elif continuation < 40 or market.correlation > 0.85:
            mode = ManagementMode.PROTECT
            reasons.append("PROFIT_PROTECTION_ACTIVE")
        else:
            mode = ManagementMode.STANDARD
            reasons.append("STANDARD_MANAGEMENT")
        sizing = size_position(
            baseline_notional=baseline_notional,
            available_cash=available_cash,
            total_exposure=portfolio_exposure,
            maximum_portfolio_exposure=1.0,
            regime_quality=regime.support,
            liquidity_quality=market.liquidity_quality,
            volatility_quality=1.0 - market.volatility_percentile,
            correlation_quality=1.0 - market.correlation,
            data_confidence=market.data_confidence,
            position_cap=baseline_notional,
            liquidity_cap=baseline_notional * market.liquidity_quality,
        )
        stop = update_long_stop(
            previous_stop=position.current_stop,
            proposed_stop=suggested_structural_stop,
            hard_exit=mode is ManagementMode.EXIT,
        )
        target = (
            TargetMode.NO_FIXED_TARGET
            if mode is ManagementMode.BREATHE
            else TargetMode.TRAIL_ONLY
        )
        return TradeManagementDecision(
            market.timestamp,
            position.trade_id,
            continuation,
            quality,
            _score(regime.support),
            _score(market.liquidity_quality),
            100.0 if position.structure_intact else 0.0,
            protection,
            _score(1.0 - portfolio_exposure),
            _score(market.data_confidence),
            mode,
            sizing.relative_size_multiplier,
            position.current_stop,
            stop.selected_stop or position.current_stop,
            target,
            tuple(reasons + list(sizing.reason_codes) + list(stop.reason_codes)),
        )

