from datetime import UTC, datetime, timedelta

import pytest

from spotbot.core.engine import BacktestEngine, PortfolioSnapshot
from spotbot.core.models import Candle, MarketType, OrderRequest, Side
from spotbot.risk.position_sizing import RiskConfig

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def candle(
    number: int,
    *,
    symbol: str = "BTC/USDT",
    open_price: float = 100.0,
    high: float = 105.0,
    low: float = 96.0,
    close: float = 102.0,
) -> Candle:
    return Candle(
        symbol=symbol,
        timestamp=BASE_TIME + timedelta(hours=number),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1_000.0,
    )


class OneShotBuyStrategy:
    def __init__(self, *, stop: float = 95.0) -> None:
        self.stop = stop
        self.emitted = False

    def on_candle_close(
        self,
        current: Candle,
        portfolio: PortfolioSnapshot,
    ) -> list[OrderRequest]:
        del portfolio

        if self.emitted:
            return []

        self.emitted = True

        return [
            OrderRequest(
                symbol=current.symbol,
                side=Side.BUY,
                created_at=current.timestamp,
                execute_after=current.timestamp,
                market_type=MarketType.SPOT,
                stop_loss=self.stop,
                risk_fraction=0.005,
                reason="test_entry",
            )
        ]


class BuyThenSellStrategy:
    def __init__(self) -> None:
        self.step = 0

    def on_candle_close(
        self,
        current: Candle,
        portfolio: PortfolioSnapshot,
    ) -> list[OrderRequest]:
        self.step += 1

        if self.step == 1:
            return [
                OrderRequest(
                    symbol=current.symbol,
                    side=Side.BUY,
                    created_at=current.timestamp,
                    execute_after=current.timestamp,
                    stop_loss=95.0,
                    risk_fraction=0.005,
                    reason="entry",
                )
            ]

        if self.step == 2 and portfolio.position(current.symbol):
            return [
                OrderRequest(
                    symbol=current.symbol,
                    side=Side.SELL,
                    created_at=current.timestamp,
                    execute_after=current.timestamp,
                    reason="exit",
                )
            ]

        return []


class InvalidTimestampStrategy:
    def on_candle_close(
        self,
        current: Candle,
        portfolio: PortfolioSnapshot,
    ) -> list[OrderRequest]:
        del portfolio

        return [
            OrderRequest(
                symbol=current.symbol,
                side=Side.BUY,
                created_at=current.timestamp + timedelta(hours=1),
                execute_after=current.timestamp + timedelta(hours=1),
                stop_loss=95.0,
                risk_fraction=0.005,
            )
        ]


class DuplicateOrderStrategy:
    def on_candle_close(
        self,
        current: Candle,
        portfolio: PortfolioSnapshot,
    ) -> list[OrderRequest]:
        del portfolio

        order = OrderRequest(
            symbol=current.symbol,
            side=Side.BUY,
            created_at=current.timestamp,
            execute_after=current.timestamp,
            stop_loss=95.0,
            risk_fraction=0.005,
        )

        return [order, order]


def zero_cost_risk(**overrides: float | int) -> RiskConfig:
    values: dict[str, float | int] = {
        "risk_per_trade": 0.005,
        "max_position_fraction": 0.35,
        "max_open_positions": 3,
        "max_total_open_risk": 0.015,
        "fee_rate": 0.0,
        "slippage_rate": 0.0,
        "minimum_order_value": 1.0,
    }
    values.update(overrides)

    return RiskConfig(**values)


def test_signal_executes_only_on_next_candle() -> None:
    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=OneShotBuyStrategy(),
        risk=zero_cost_risk(),
    )

    engine.process_candle(candle(1))

    assert engine.portfolio.position("BTC/USDT") is None
    assert len(engine.pending_orders) == 1
    assert len(engine.portfolio.fills) == 0

    engine.process_candle(candle(2, open_price=100.0))

    position = engine.portfolio.position("BTC/USDT")

    assert position is not None
    assert len(engine.portfolio.fills) == 1
    assert engine.portfolio.fills[0].timestamp == BASE_TIME + timedelta(hours=2)
    assert engine.portfolio.fills[0].price == pytest.approx(100.0)


def test_stop_is_processed_using_intrabar_low() -> None:
    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=OneShotBuyStrategy(stop=95.0),
        risk=zero_cost_risk(),
    )

    engine.process_candle(candle(1))

    engine.process_candle(
        candle(
            2,
            open_price=100.0,
            high=103.0,
            low=94.0,
            close=102.0,
        )
    )

    assert engine.portfolio.position("BTC/USDT") is None
    assert len(engine.portfolio.fills) == 2
    assert engine.portfolio.fills[-1].reason == "stop_loss"
    assert engine.portfolio.fills[-1].price == pytest.approx(95.0)


def test_gap_below_stop_executes_at_worse_open_price() -> None:
    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=OneShotBuyStrategy(stop=95.0),
        risk=zero_cost_risk(),
    )

    engine.process_candle(candle(1))

    engine.process_candle(
        candle(
            2,
            open_price=100.0,
            high=104.0,
            low=96.0,
            close=101.0,
        )
    )

    assert engine.portfolio.position("BTC/USDT") is not None

    engine.process_candle(
        candle(
            3,
            open_price=90.0,
            high=93.0,
            low=88.0,
            close=91.0,
        )
    )

    assert engine.portfolio.position("BTC/USDT") is None
    assert engine.portfolio.fills[-1].reason == "stop_loss"
    assert engine.portfolio.fills[-1].price == pytest.approx(90.0)


def test_entry_and_exit_fees_are_included() -> None:
    risk = RiskConfig(
        risk_per_trade=0.005,
        max_position_fraction=0.35,
        max_open_positions=3,
        max_total_open_risk=0.015,
        fee_rate=0.001,
        slippage_rate=0.0,
        minimum_order_value=1.0,
    )

    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=BuyThenSellStrategy(),
        risk=risk,
    )

    engine.process_candle(candle(1))
    engine.process_candle(candle(2, open_price=100.0, low=96.0))
    engine.process_candle(
        candle(
            3,
            open_price=110.0,
            high=112.0,
            low=108.0,
            close=111.0,
        )
    )

    assert engine.portfolio.position("BTC/USDT") is None
    assert len(engine.portfolio.fills) == 2
    assert engine.portfolio.total_fees > 0
    assert engine.portfolio.realized_pnl > 0
    assert engine.portfolio.cash > 1_000.0


def test_position_value_is_capped() -> None:
    risk = zero_cost_risk(
        risk_per_trade=0.01,
        max_position_fraction=0.35,
    )

    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=OneShotBuyStrategy(stop=99.9),
        risk=risk,
    )

    engine.process_candle(candle(1))

    engine.process_candle(
        candle(
            2,
            open_price=100.0,
            high=102.0,
            low=99.95,
            close=101.0,
        )
    )

    position = engine.portfolio.position("BTC/USDT")

    assert position is not None
    assert position.quantity == pytest.approx(3.5)
    assert engine.portfolio.cash == pytest.approx(650.0)


def test_out_of_order_candle_is_rejected() -> None:
    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=OneShotBuyStrategy(),
        risk=zero_cost_risk(),
    )

    engine.process_candle(candle(2))

    with pytest.raises(ValueError, match="Out-of-order"):
        engine.process_candle(candle(1))


def test_future_creation_timestamp_is_rejected() -> None:
    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=InvalidTimestampStrategy(),
        risk=zero_cost_risk(),
    )

    with pytest.raises(ValueError, match="creation time"):
        engine.process_candle(candle(1))


def test_duplicate_pending_orders_are_rejected() -> None:
    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=DuplicateOrderStrategy(),
        risk=zero_cost_risk(),
    )

    with pytest.raises(ValueError, match="pending order"):
        engine.process_candle(candle(1))


def test_equity_curve_is_recorded_after_every_candle() -> None:
    engine = BacktestEngine(
        initial_cash=1_000.0,
        strategy=OneShotBuyStrategy(),
        risk=zero_cost_risk(),
    )

    engine.process_candle(candle(1))
    engine.process_candle(candle(2, close=103.0))

    assert len(engine.equity_curve) == 2
    assert engine.equity_curve[0].equity == pytest.approx(1_000.0)
    assert engine.equity_curve[1].timestamp == BASE_TIME + timedelta(hours=2)