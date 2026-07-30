from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from spotbot.core.engine import BacktestEngine, PortfolioSnapshot, PositionSnapshot
from spotbot.core.models import Candle, MarketType, OrderRequest, Side
from spotbot.research.rd10_smoke_backtest import (
    INITIAL_CASH,
    deterministic_artifact_hashes,
    run_smoke_backtest,
    validate_allowed_timestamp,
)
from spotbot.risk.position_sizing import RiskConfig, calculate_position_quantity
from spotbot.risk.sharia_guard import ShariaGuard
from spotbot.strategies.regime_momentum_breakout import (
    STRATEGY_ID,
    RegimeMomentumBreakoutStrategy,
)

BASE = datetime(2022, 1, 1, tzinfo=UTC)


def make_candle(
    index: int,
    *,
    close: float,
    volume: float = 100.0,
    open_price: float | None = None,
    low: float | None = None,
    high: float | None = None,
) -> Candle:
    opened = close if open_price is None else open_price
    return Candle(
        symbol="BTC/USDT",
        timestamp=BASE + timedelta(days=index),
        open=opened,
        high=max(opened, close) + 1.0 if high is None else high,
        low=min(opened, close) - 1.0 if low is None else low,
        close=close,
        volume=volume,
    )


def empty_portfolio() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        cash=INITIAL_CASH,
        equity=INITIAL_CASH,
        total_fees=0.0,
        realized_pnl=0.0,
        positions=(),
    )


def warm_strategy() -> tuple[RegimeMomentumBreakoutStrategy, int]:
    strategy = RegimeMomentumBreakoutStrategy()
    for index in range(219):
        strategy.on_candle_close(
            make_candle(
                index,
                close=100.0 + index * 0.1 + (1.0 if index % 2 == 0 else -1.0),
            ),
            empty_portfolio(),
        )
    return strategy, 219


def test_specification_registration() -> None:
    path = Path("data/research/rd10/strategy-specification-v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["strategy_id"] == STRATEGY_ID
    assert payload["status"] == "REGISTERED_FOR_RD10_SMOKE_TEST"
    assert payload["source_authorization"] == "USER_AUTHORIZED_RD10_REGISTRATION"
    assert payload["optimization_performed"] is False


def test_entry_uses_prior_breakout_and_volume_windows() -> None:
    strategy, index = warm_strategy()
    previous_high = max(strategy._highs)
    order = strategy.on_candle_close(
        make_candle(
            index,
            close=previous_high + 2.0,
            high=previous_high + 100.0,
            volume=111.0,
        ),
        empty_portfolio(),
    )
    assert len(order) == 1
    assert order[0].side is Side.BUY
    snapshot = strategy.signals[-1].indicators
    assert snapshot.previous_high_20 == previous_high
    assert snapshot.previous_volume_mean_20 == pytest.approx(100.0)


def test_volume_window_excludes_current_bar() -> None:
    strategy, index = warm_strategy()
    previous_high = max(strategy._highs)
    strategy.on_candle_close(
        make_candle(index, close=previous_high + 2.0, volume=1_000.0),
        empty_portfolio(),
    )
    assert strategy.signals[-1].indicators.previous_volume_mean_20 == pytest.approx(100.0)


def test_open_position_blocks_second_entry_and_dca() -> None:
    strategy, index = warm_strategy()
    previous_high = max(strategy._highs)
    position = PositionSnapshot(
        symbol="BTC/USDT",
        quantity=1.0,
        average_price=150.0,
        stop_loss=140.0,
    )
    portfolio = PortfolioSnapshot(
        cash=50_000.0,
        equity=100_000.0,
        total_fees=0.0,
        realized_pnl=0.0,
        positions=(position,),
    )
    orders = strategy.on_candle_close(
        make_candle(index, close=previous_high + 2.0, volume=1_000.0),
        portfolio,
    )
    assert all(order.side is not Side.BUY for order in orders)


def test_position_sizing_obeys_risk_cash_and_25_percent_caps() -> None:
    config = RiskConfig(
        risk_per_trade=0.01,
        max_position_fraction=0.25,
        max_open_positions=2,
        max_total_open_risk=0.02,
        fee_rate=0.001,
        slippage_rate=0.0005,
        minimum_order_value=10.0,
    )
    quantity = calculate_position_quantity(
        equity=100_000.0,
        available_cash=100_000.0,
        entry_price=100.0,
        stop_price=99.0,
        requested_risk_fraction=0.01,
        config=config,
    )
    assert quantity * 100.0 == pytest.approx(25_000.0)
    cash_limited = calculate_position_quantity(
        equity=100_000.0,
        available_cash=1_000.0,
        entry_price=100.0,
        stop_price=90.0,
        requested_risk_fraction=0.01,
        config=config,
    )
    assert cash_limited * 100.0 * 1.001 <= 1_000.0 + 1e-9


def test_fee_slippage_next_bar_and_initial_stop() -> None:
    strategy, index = warm_strategy()
    risk = RiskConfig(
        risk_per_trade=0.01,
        max_position_fraction=0.25,
        max_open_positions=2,
        max_total_open_risk=0.02,
        fee_rate=0.001,
        slippage_rate=0.0005,
        minimum_order_value=10.0,
    )
    engine = BacktestEngine(initial_cash=100_000.0, strategy=strategy, risk=risk)
    previous_high = max(strategy._highs)
    signal_candle = make_candle(index, close=previous_high + 2.0, volume=1_000.0)
    engine.last_prices["BTC/USDT"] = signal_candle.close
    engine.last_timestamp_by_symbol["BTC/USDT"] = signal_candle.timestamp - timedelta(days=1)
    engine.process_candle(signal_candle)
    assert not engine.portfolio.fills
    next_candle = make_candle(
        index + 1,
        close=signal_candle.close + 1.0,
        open_price=signal_candle.close,
        low=signal_candle.close - 0.5,
    )
    engine.process_candle(next_candle)
    assert engine.portfolio.fills[0].timestamp == next_candle.timestamp
    assert engine.portfolio.fills[0].price == pytest.approx(next_candle.open * 1.0005)
    assert engine.portfolio.fills[0].fee > 0


def test_spot_long_only_guard_rejects_non_spot_and_naked_sell() -> None:
    order = OrderRequest(
        symbol="BTC/USDT",
        side=Side.BUY,
        created_at=BASE,
        execute_after=BASE,
        market_type=MarketType.MARGIN,
        stop_loss=90.0,
        risk_fraction=0.01,
    )
    with pytest.raises(PermissionError, match="Non-spot"):
        ShariaGuard.validate_market(order)
    naked_sell = OrderRequest(
        symbol="BTC/USDT",
        side=Side.SELL,
        created_at=BASE,
        execute_after=BASE,
    )
    engine = BacktestEngine(
        initial_cash=100_000.0,
        strategy=RegimeMomentumBreakoutStrategy(),
    )
    with pytest.raises(PermissionError, match="owned"):
        ShariaGuard.validate_sell(naked_sell, engine.portfolio, 1.0)


def test_forbidden_year_rejection_without_accessing_dataset() -> None:
    validate_allowed_timestamp(pd.Timestamp("2024-12-31T00:00:00Z"))
    with pytest.raises(ValueError, match="Forbidden"):
        validate_allowed_timestamp(pd.Timestamp("2025-01-01T00:00:00Z"))
    with pytest.raises(ValueError, match="Forbidden"):
        validate_allowed_timestamp(pd.Timestamp("2026-01-01T00:00:00Z"))


def test_no_negative_shift_or_centered_window_in_strategy_source() -> None:
    source = Path("src/spotbot/strategies/regime_momentum_breakout.py").read_text(encoding="utf-8")
    assert "shift(-" not in source
    assert "center=True" not in source
    assert ".bfill(" not in source


def test_smoke_replay_is_deterministic_and_reconciled(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_result = run_smoke_backtest(first)
    second_result = run_smoke_backtest(second)
    assert deterministic_artifact_hashes(first) == deterministic_artifact_hashes(second)
    assert first_result["metrics"] == second_result["metrics"]
    validation = first_result["validation"]
    assert validation["trade_pnl_reconciliation"] is True
    assert validation["equity_reconciliation"] is True
    assert validation["next_bar_execution"] is True
    assert first_result["metrics"]["closed_trade_count"] >= 1


def test_end_of_period_policy_closes_owned_position() -> None:
    class BuyOnce:
        emitted = False

        def on_candle_close(
            self,
            candle: Candle,
            portfolio: PortfolioSnapshot,
        ) -> list[OrderRequest]:
            del portfolio
            if self.emitted:
                return []
            self.emitted = True
            return [
                OrderRequest(
                    symbol=candle.symbol,
                    side=Side.BUY,
                    created_at=candle.timestamp,
                    execute_after=candle.timestamp,
                    stop_loss=candle.close * 0.8,
                    risk_fraction=0.01,
                )
            ]

    engine = BacktestEngine(
        initial_cash=10_000.0,
        strategy=BuyOnce(),
        risk=RiskConfig(max_position_fraction=0.25),
    )
    first = make_candle(0, close=100.0)
    second = make_candle(1, close=102.0, open_price=101.0)
    engine.process_candle(first)
    engine.process_candle(second)
    engine.close_open_positions_at_end(second)
    assert engine.portfolio.open_positions_count() == 0
    assert engine.portfolio.fills[-1].reason == "forced_end_of_period_exit"
