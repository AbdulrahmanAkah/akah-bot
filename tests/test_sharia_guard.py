from datetime import UTC, datetime

import pytest

from spotbot.core.models import (
    MarketType,
    OrderRequest,
    Position,
    Side,
)
from spotbot.core.portfolio import Portfolio
from spotbot.risk.sharia_guard import ShariaGuard

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_futures_order_is_blocked() -> None:
    order = OrderRequest(
        symbol="BTC/USDT",
        side=Side.BUY,
        created_at=NOW,
        execute_after=NOW,
        market_type=MarketType.FUTURES,
        stop_loss=95_000.0,
        risk_fraction=0.005,
    )

    with pytest.raises(PermissionError, match="Non-spot"):
        ShariaGuard.validate_entry(order)


def test_overselling_is_blocked() -> None:
    portfolio = Portfolio(cash=500.0)
    portfolio.positions["BTC/USDT"] = Position(
        symbol="BTC/USDT",
        quantity=0.005,
        average_price=100_000.0,
        stop_loss=98_000.0,
    )

    order = OrderRequest(
        symbol="BTC/USDT",
        side=Side.SELL,
        created_at=NOW,
        execute_after=NOW,
        market_type=MarketType.SPOT,
        quantity=0.01,
    )

    with pytest.raises(PermissionError, match="owned quantity"):
        ShariaGuard.validate_sell(order, portfolio, 0.01)
