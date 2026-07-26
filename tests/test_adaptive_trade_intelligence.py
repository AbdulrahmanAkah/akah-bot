from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.adaptive_position_sizing import size_position
from spotbot.research.adaptive_stops import (
    execute_long_stop,
    select_initial_stop,
    update_long_stop,
)
from spotbot.research.adaptive_trade_intelligence import (
    AdaptiveTradeIntelligenceV1,
)
from spotbot.research.adaptive_trade_replay import policy_hash, shadow_replay
from spotbot.research.adaptive_trade_types import (
    ManagementMode,
    OpenPositionState,
    TradeMarketContext,
    TradeRegimeContext,
)
from spotbot.research.portfolio_risk_coordinator import coordinate_portfolio_risk


def _market(**overrides: float) -> TradeMarketContext:
    values = {
        "trend_persistence": 0.9,
        "volatility_percentile": 0.2,
        "liquidity_quality": 0.9,
        "gap_risk": 0.1,
        "breadth": 0.8,
        "correlation": 0.2,
        "data_confidence": 1.0,
    }
    values.update(overrides)
    return TradeMarketContext(
        pd.Timestamp("2024-01-01T00:00:00Z"),
        **values,
    )


def _position(**overrides: object) -> OpenPositionState:
    values: dict[str, object] = {
        "trade_id": "T1",
        "entry_price": 100.0,
        "current_price": 110.0,
        "initial_stop": 90.0,
        "current_stop": 95.0,
        "mfe_r": 1.0,
        "mae_r": -0.2,
        "bars_held": 5,
        "structure_intact": True,
    }
    values.update(overrides)
    return OpenPositionState(**values)  # type: ignore[arg-type]


def test_worse_inputs_cannot_increase_position_size() -> None:
    common = {
        "baseline_notional": 100.0,
        "available_cash": 100.0,
        "total_exposure": 0.0,
        "maximum_portfolio_exposure": 100.0,
        "regime_quality": 1.0,
        "volatility_quality": 1.0,
        "correlation_quality": 1.0,
        "data_confidence": 1.0,
        "position_cap": 100.0,
        "liquidity_cap": 100.0,
    }
    good = size_position(liquidity_quality=1.0, **common)
    poor = size_position(liquidity_quality=0.4, **common)
    assert poor.effective_notional <= good.effective_notional
    assert good.relative_size_multiplier <= 1.0


def test_long_stop_never_widens() -> None:
    decision = update_long_stop(previous_stop=95.0, proposed_stop=90.0)
    assert decision.action == "KEEP"
    assert decision.selected_stop == 95.0


def test_initial_stop_uses_structure_without_exceeding_cap() -> None:
    decision = select_initial_stop(
        entry_price=100.0,
        candidates={"structure": 92.0, "atr": 94.0, "noise": 93.0},
        maximum_distance_fraction=0.10,
    )
    assert decision.action == "SET"
    assert decision.selected_stop == 92.0


def test_gap_and_intrabar_stop_execution_are_conservative() -> None:
    assert execute_long_stop(active_stop=95, bar_open=90, bar_low=89) == (
        True,
        90,
        "GAP_STOP",
    )
    assert execute_long_stop(active_stop=95, bar_open=100, bar_low=94) == (
        True,
        95,
        "INTRABAR_STOP",
    )


def test_breathe_is_explainable_and_does_not_increase_risk() -> None:
    decision = AdaptiveTradeIntelligenceV1().decide(
        market=_market(),
        regime=TradeRegimeContext(0.9, False, 0.9, "PASS"),
        position=_position(),
        baseline_notional=100.0,
        available_cash=100.0,
        portfolio_exposure=0.2,
        suggested_structural_stop=96.0,
    )
    assert decision.management_mode is ManagementMode.BREATHE
    assert decision.suggested_size_multiplier <= 1.0
    assert decision.suggested_stop >= decision.current_stop


def test_maximum_holding_forces_exit() -> None:
    decision = AdaptiveTradeIntelligenceV1().decide(
        market=_market(),
        regime=TradeRegimeContext(0.9, False, 0.9, "PASS"),
        position=_position(bars_held=84),
        baseline_notional=100.0,
        available_cash=100.0,
        portfolio_exposure=0.2,
        suggested_structural_stop=96.0,
    )
    assert decision.management_mode is ManagementMode.EXIT
    assert "MAX_HOLD_REACHED" in decision.reason_codes


def test_emergency_requires_confirmed_or_hard_portfolio_condition() -> None:
    normal = coordinate_portfolio_risk(
        total_exposure=0.5,
        drawdown=0.05,
        correlation_spike_confirmed=False,
        cash_flight_confirmed=False,
        liquidity_shock_confirmed=False,
        data_quality_pass=True,
    )
    assert normal.allow_entries
    emergency = coordinate_portfolio_risk(
        total_exposure=0.5,
        drawdown=0.25,
        correlation_spike_confirmed=False,
        cash_flight_confirmed=False,
        liquidity_shock_confirmed=False,
        data_quality_pass=True,
    )
    assert not emergency.allow_entries


def test_exposure_above_one_is_rejected() -> None:
    with pytest.raises(ValueError):
        coordinate_portfolio_risk(
            total_exposure=1.01,
            drawdown=0.0,
            correlation_spike_confirmed=False,
            cash_flight_confirmed=False,
            liquidity_shock_confirmed=False,
            data_quality_pass=True,
        )


def test_shadow_mode_does_not_change_trade_count_or_pnl() -> None:
    result = shadow_replay([{"net_pnl": 10.0}], [])
    assert result["pnl_changed"] is False
    assert result["baseline_net_pnl"] == result["shadow_net_pnl"]
    assert result["baseline_trade_count"] == result["shadow_trade_count"]


def test_policy_hash_is_reproducible() -> None:
    assert policy_hash({"b": 2, "a": 1}) == policy_hash({"a": 1, "b": 2})

