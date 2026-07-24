from spotbot.core.models import Position
from spotbot.core.portfolio import Portfolio


def test_portfolio_equity() -> None:
    portfolio = Portfolio(cash=700.0)
    portfolio.positions["BTC/USDT"] = Position(
        symbol="BTC/USDT",
        quantity=0.003,
        average_price=100_000.0,
        stop_loss=98_000.0,
    )

    assert portfolio.equity({"BTC/USDT": 100_000.0}) == 1_000.0


def test_owned_quantity() -> None:
    portfolio = Portfolio(cash=900.0)
    portfolio.positions["ETH/USDT"] = Position(
        symbol="ETH/USDT",
        quantity=0.025,
        average_price=4_000.0,
        stop_loss=3_900.0,
    )

    assert portfolio.owned_quantity("ETH/USDT") == 0.025
    assert portfolio.owned_quantity("BTC/USDT") == 0.0
