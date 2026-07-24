from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class MarketType(StrEnum):
    SPOT = "spot"
    MARGIN = "margin"
    FUTURES = "futures"
    PERPETUAL = "perpetual"
    OPTIONS = "options"


@dataclass(frozen=True, slots=True)
class Candle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def validate(self) -> None:
        if not self.symbol:
            raise ValueError("Symbol cannot be empty.")

        if self.timestamp.tzinfo is None:
            raise ValueError("Candle timestamp must be timezone-aware.")

        if self.timestamp.utcoffset() != UTC.utcoffset(self.timestamp):
            raise ValueError("Candle timestamp must use UTC.")

        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC prices must be positive.")

        if self.high < max(self.open, self.close, self.low):
            raise ValueError("High price is inconsistent with OHLC values.")

        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Low price is inconsistent with OHLC values.")

        if self.volume < 0:
            raise ValueError("Volume cannot be negative.")


@dataclass(slots=True)
class Position:
    symbol: str
    quantity: float
    average_price: float
    stop_loss: float

    @property
    def is_open(self) -> bool:
        return self.quantity > 1e-12

    @property
    def risk_per_unit(self) -> float:
        return max(self.average_price - self.stop_loss, 0.0)


@dataclass(frozen=True, slots=True)
class OrderRequest:
    symbol: str
    side: Side
    created_at: datetime
    execute_after: datetime
    market_type: MarketType = MarketType.SPOT
    quantity: float | None = None
    stop_loss: float | None = None
    risk_fraction: float | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Fill:
    symbol: str
    side: Side
    timestamp: datetime
    quantity: float
    price: float
    fee: float
    reason: str
