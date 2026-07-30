from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from spotbot.core.models import Candle, Fill, OrderRequest, Position, Side
from spotbot.core.portfolio import Portfolio
from spotbot.risk.position_sizing import RiskConfig, calculate_position_quantity
from spotbot.risk.sharia_guard import ShariaGuard


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    symbol: str
    quantity: float
    average_price: float
    stop_loss: float


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    cash: float
    equity: float
    total_fees: float
    realized_pnl: float
    positions: tuple[PositionSnapshot, ...]

    def position(self, symbol: str) -> PositionSnapshot | None:
        for position in self.positions:
            if position.symbol == symbol:
                return position

        return None

    def owned_quantity(self, symbol: str) -> float:
        position = self.position(symbol)
        return position.quantity if position else 0.0


@dataclass(frozen=True, slots=True)
class EquityPoint:
    timestamp: datetime
    equity: float
    cash: float
    market_value: float


@dataclass(frozen=True, slots=True)
class OrderRejection:
    timestamp: datetime
    order: OrderRequest
    reason: str


class Strategy(Protocol):
    def on_candle_close(
        self,
        candle: Candle,
        portfolio: PortfolioSnapshot,
    ) -> Sequence[OrderRequest]:
        """
        Called only after the candle has fully closed.

        Returned orders cannot execute inside the candle that produced them.
        """
        ...


class BacktestEngine:
    """
    Event-driven long-only Spot backtest engine.

    Candle timestamps are treated as candle-close timestamps. Orders generated
    from a closed candle may execute only on a later candle.
    """

    def __init__(
        self,
        *,
        initial_cash: float,
        strategy: Strategy,
        risk: RiskConfig | None = None,
    ) -> None:
        if initial_cash <= 0:
            raise ValueError("Initial cash must be positive.")

        self.risk = risk or RiskConfig()
        self.risk.validate()

        self.strategy = strategy
        self.portfolio = Portfolio(cash=initial_cash)

        self.pending_orders: list[OrderRequest] = []
        self.rejections: list[OrderRejection] = []
        self.equity_curve: list[EquityPoint] = []

        self.last_prices: dict[str, float] = {}
        self.last_timestamp_by_symbol: dict[str, datetime] = {}

    def _execution_prices(self, candle: Candle) -> dict[str, float]:
        prices = dict(self.last_prices)
        prices[candle.symbol] = candle.open
        return prices

    def _snapshot(self) -> PortfolioSnapshot:
        equity = self.portfolio.equity(self.last_prices)

        positions = tuple(
            PositionSnapshot(
                symbol=position.symbol,
                quantity=position.quantity,
                average_price=position.average_price,
                stop_loss=position.stop_loss,
            )
            for position in sorted(
                self.portfolio.positions.values(),
                key=lambda item: item.symbol,
            )
            if position.is_open
        )

        return PortfolioSnapshot(
            cash=self.portfolio.cash,
            equity=equity,
            total_fees=self.portfolio.total_fees,
            realized_pnl=self.portfolio.realized_pnl,
            positions=positions,
        )

    def _reject(
        self,
        *,
        order: OrderRequest,
        timestamp: datetime,
        reason: str,
    ) -> None:
        self.rejections.append(
            OrderRejection(
                timestamp=timestamp,
                order=order,
                reason=reason,
            )
        )

    def _validate_chronology(self, candle: Candle) -> None:
        previous = self.last_timestamp_by_symbol.get(candle.symbol)

        if previous is not None and candle.timestamp <= previous:
            raise ValueError(
                f"Out-of-order or duplicate candle for {candle.symbol}: "
                f"{candle.timestamp.isoformat()} <= {previous.isoformat()}"
            )

    def _validate_new_order(
        self,
        *,
        order: OrderRequest,
        candle: Candle,
    ) -> None:
        if order.symbol != candle.symbol:
            raise ValueError(
                "A strategy may currently create orders only for the "
                "symbol of the candle being processed."
            )

        if order.created_at != candle.timestamp:
            raise ValueError("Order creation time must equal the closed candle timestamp.")

        if order.execute_after < order.created_at:
            raise ValueError("execute_after cannot be earlier than created_at.")

        ShariaGuard.validate_market(order)

        if order.side is Side.BUY:
            ShariaGuard.validate_entry(order)

        if any(pending.symbol == order.symbol for pending in self.pending_orders):
            raise ValueError(f"A pending order already exists for {order.symbol}.")

    def _buy_fill_price(self, candle: Candle) -> float:
        return candle.open * (1 + self.risk.slippage_rate)

    def _sell_fill_price(self, reference_price: float) -> float:
        return reference_price * (1 - self.risk.slippage_rate)

    def _execute_buy(
        self,
        *,
        order: OrderRequest,
        candle: Candle,
    ) -> None:
        if self.portfolio.position(order.symbol) is not None:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="position_already_open",
            )
            return

        if self.portfolio.open_positions_count() >= self.risk.max_open_positions:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="max_open_positions",
            )
            return

        if order.stop_loss is None or order.risk_fraction is None:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="missing_risk_parameters",
            )
            return

        fill_price = self._buy_fill_price(candle)

        if order.stop_loss >= fill_price:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="stop_not_below_fill_price",
            )
            return

        execution_prices = self._execution_prices(candle)
        equity = self.portfolio.equity(execution_prices)

        total_risk_limit = equity * self.risk.max_total_open_risk
        remaining_open_risk = max(
            total_risk_limit - self.portfolio.total_open_risk(),
            0.0,
        )

        if remaining_open_risk <= 0:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="max_total_open_risk",
            )
            return

        quantity = calculate_position_quantity(
            equity=equity,
            available_cash=self.portfolio.cash,
            entry_price=fill_price,
            stop_price=order.stop_loss,
            requested_risk_fraction=order.risk_fraction,
            config=self.risk,
        )

        risk_per_unit = fill_price - order.stop_loss
        remaining_risk_quantity = remaining_open_risk / risk_per_unit
        quantity = min(quantity, remaining_risk_quantity)

        order_value = quantity * fill_price
        fee = order_value * self.risk.fee_rate
        total_cost = order_value + fee

        if quantity <= 0:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="zero_quantity",
            )
            return

        if order_value < self.risk.minimum_order_value:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="below_minimum_order_value",
            )
            return

        if total_cost > self.portfolio.cash + 1e-9:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="insufficient_cash",
            )
            return

        average_cost = total_cost / quantity

        self.portfolio.cash -= total_cost
        self.portfolio.total_fees += fee

        self.portfolio.positions[order.symbol] = Position(
            symbol=order.symbol,
            quantity=quantity,
            average_price=average_cost,
            stop_loss=order.stop_loss,
        )

        self.portfolio.fills.append(
            Fill(
                symbol=order.symbol,
                side=Side.BUY,
                timestamp=candle.timestamp,
                quantity=quantity,
                price=fill_price,
                fee=fee,
                reason=order.reason or "entry",
            )
        )

    def _close_position(
        self,
        *,
        symbol: str,
        quantity: float,
        fill_price: float,
        timestamp: datetime,
        reason: str,
    ) -> None:
        position = self.portfolio.position(symbol)

        if position is None:
            return

        gross_proceeds = quantity * fill_price
        fee = gross_proceeds * self.risk.fee_rate
        net_proceeds = gross_proceeds - fee

        cost_basis = quantity * position.average_price

        self.portfolio.cash += net_proceeds
        self.portfolio.total_fees += fee
        self.portfolio.realized_pnl += net_proceeds - cost_basis

        position.quantity -= quantity

        self.portfolio.fills.append(
            Fill(
                symbol=symbol,
                side=Side.SELL,
                timestamp=timestamp,
                quantity=quantity,
                price=fill_price,
                fee=fee,
                reason=reason,
            )
        )

        if not position.is_open:
            del self.portfolio.positions[symbol]

    def _execute_sell(
        self,
        *,
        order: OrderRequest,
        candle: Candle,
    ) -> None:
        position = self.portfolio.position(order.symbol)

        if position is None:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason="no_owned_position",
            )
            return

        quantity = position.quantity if order.quantity is None else order.quantity

        try:
            ShariaGuard.validate_sell(
                order,
                self.portfolio,
                quantity,
            )
        except (PermissionError, ValueError) as error:
            self._reject(
                order=order,
                timestamp=candle.timestamp,
                reason=str(error),
            )
            return

        fill_price = self._sell_fill_price(candle.open)

        self._close_position(
            symbol=order.symbol,
            quantity=quantity,
            fill_price=fill_price,
            timestamp=candle.timestamp,
            reason=order.reason or "strategy_exit",
        )

    def _execute_pending_orders(self, candle: Candle) -> None:
        remaining: list[OrderRequest] = []

        for order in self.pending_orders:
            if order.symbol != candle.symbol:
                remaining.append(order)
                continue

            if candle.timestamp <= order.execute_after:
                remaining.append(order)
                continue

            if order.side is Side.BUY:
                self._execute_buy(order=order, candle=candle)
            else:
                self._execute_sell(order=order, candle=candle)

        self.pending_orders = remaining

    def _process_stop_loss(self, candle: Candle) -> None:
        position = self.portfolio.position(candle.symbol)

        if position is None:
            return

        if candle.low > position.stop_loss:
            return

        stop_reference = min(candle.open, position.stop_loss)
        fill_price = self._sell_fill_price(stop_reference)

        self._close_position(
            symbol=candle.symbol,
            quantity=position.quantity,
            fill_price=fill_price,
            timestamp=candle.timestamp,
            reason="stop_loss",
        )

    def _record_equity(self, candle: Candle) -> None:
        market_value = self.portfolio.market_value(self.last_prices)
        equity = self.portfolio.cash + market_value

        self.equity_curve.append(
            EquityPoint(
                timestamp=candle.timestamp,
                equity=equity,
                cash=self.portfolio.cash,
                market_value=market_value,
            )
        )

    def process_candle(self, candle: Candle) -> None:
        candle.validate()
        self._validate_chronology(candle)

        # Orders created from earlier candles execute at this candle's open.
        self._execute_pending_orders(candle)

        # A newly opened or existing position may hit its stop intrabar.
        self._process_stop_loss(candle)

        # The closing price becomes available only after intrabar execution.
        self.last_prices[candle.symbol] = candle.close
        self.last_timestamp_by_symbol[candle.symbol] = candle.timestamp

        snapshot = self._snapshot()

        new_orders = self.strategy.on_candle_close(
            candle,
            snapshot,
        )

        for order in new_orders:
            self._validate_new_order(
                order=order,
                candle=candle,
            )
            self.pending_orders.append(order)

        self._record_equity(candle)

    def process_candle_batch(
        self,
        candles: Sequence[Candle],
        *,
        buy_rank_key: Callable[[OrderRequest], tuple[float, ...]] | None = None,
    ) -> None:
        """Process one global timestamp across symbols without symbol-order leakage."""
        if not candles:
            return
        ordered = sorted(candles, key=lambda item: item.symbol)
        timestamps = {candle.timestamp for candle in ordered}
        symbols = {candle.symbol for candle in ordered}
        if len(timestamps) != 1:
            raise ValueError("A candle batch must share one timestamp.")
        if len(symbols) != len(ordered):
            raise ValueError("A candle batch cannot repeat a symbol.")

        candle_by_symbol = {candle.symbol: candle for candle in ordered}
        for candle in ordered:
            candle.validate()
            self._validate_chronology(candle)

        executable: list[OrderRequest] = []
        remaining: list[OrderRequest] = []
        batch_timestamp = ordered[0].timestamp
        for order in self.pending_orders:
            if order.symbol in candle_by_symbol and batch_timestamp > order.execute_after:
                executable.append(order)
            else:
                remaining.append(order)
        self.pending_orders = remaining
        for order in sorted(
            executable,
            key=lambda item: (item.side is Side.BUY, item.symbol),
        ):
            candle = candle_by_symbol[order.symbol]
            if order.side is Side.SELL:
                self._execute_sell(order=order, candle=candle)
            else:
                self._execute_buy(order=order, candle=candle)

        for candle in ordered:
            self._process_stop_loss(candle)

        for candle in ordered:
            self.last_prices[candle.symbol] = candle.close
            self.last_timestamp_by_symbol[candle.symbol] = candle.timestamp

        snapshot = self._snapshot()
        candidate_orders: list[OrderRequest] = []
        for candle in ordered:
            new_orders = self.strategy.on_candle_close(candle, snapshot)
            for order in new_orders:
                self._validate_new_order(order=order, candle=candle)
                candidate_orders.append(order)

        sell_orders = [order for order in candidate_orders if order.side is Side.SELL]
        buy_orders = [order for order in candidate_orders if order.side is Side.BUY]
        buy_orders.sort(key=lambda order: order.symbol)
        if buy_rank_key is not None:
            buy_orders.sort(key=buy_rank_key, reverse=True)

        available_slots = min(
            self.risk.max_open_positions - self.portfolio.open_positions_count() + len(sell_orders),
            self.risk.max_open_positions,
        )
        accepted_buys = buy_orders[: max(available_slots, 0)]
        rejected_buys = buy_orders[max(available_slots, 0) :]
        for order in rejected_buys:
            self._reject(
                order=order,
                timestamp=ordered[0].timestamp,
                reason="simultaneous_signal_slot_limit",
            )

        self.pending_orders.extend(sell_orders)
        self.pending_orders.extend(accepted_buys)
        self._record_equity(ordered[0])

    def close_open_positions_at_end(self, candle: Candle) -> None:
        """Close the candle symbol at its final close using normal sell costs."""
        candle.validate()
        position = self.portfolio.position(candle.symbol)
        if position is None:
            return
        fill_price = self._sell_fill_price(candle.close)
        self._close_position(
            symbol=candle.symbol,
            quantity=position.quantity,
            fill_price=fill_price,
            timestamp=candle.timestamp,
            reason="forced_end_of_period_exit",
        )
        self.last_prices[candle.symbol] = candle.close
        if self.equity_curve and self.equity_curve[-1].timestamp == candle.timestamp:
            self.equity_curve.pop()
        self._record_equity(candle)

    def cancel_pending_orders_at_end(self, timestamp: datetime) -> None:
        """Cancel orders that cannot receive a causally later bar."""
        for order in self.pending_orders:
            self._reject(
                order=order,
                timestamp=timestamp,
                reason="end_of_period_unfilled",
            )
        self.pending_orders.clear()
