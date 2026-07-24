from __future__ import annotations

from dataclasses import dataclass, field

from spotbot.core.models import Fill, Position


@dataclass(slots=True)
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)
    total_fees: float = 0.0
    realized_pnl: float = 0.0

    def __post_init__(self) -> None:
        if self.cash < 0:
            raise ValueError("Cash cannot be negative.")

    def position(self, symbol: str) -> Position | None:
        position = self.positions.get(symbol)

        if position is None or not position.is_open:
            return None

        return position

    def owned_quantity(self, symbol: str) -> float:
        position = self.position(symbol)
        return position.quantity if position else 0.0

    def market_value(self, prices: dict[str, float]) -> float:
        value = 0.0

        for symbol, position in self.positions.items():
            if not position.is_open:
                continue

            price = prices.get(symbol)

            if price is None:
                raise KeyError(f"Missing current price for {symbol}.")

            value += position.quantity * price

        return value

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + self.market_value(prices)

    def open_positions_count(self) -> int:
        return sum(1 for position in self.positions.values() if position.is_open)

    def total_open_risk(self) -> float:
        return sum(
            position.risk_per_unit * position.quantity
            for position in self.positions.values()
            if position.is_open
        )
