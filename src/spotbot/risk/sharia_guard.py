from __future__ import annotations

from spotbot.core.models import MarketType, OrderRequest, Side
from spotbot.core.portfolio import Portfolio


class ShariaGuard:
    """
    حارس تقني يفرض قيود المشروع التشغيلية.

    لا يصدر حكمًا فقهيًا على أصل بعينه، بل يمنع أنواع التداول
    والعمليات المحظورة في إعدادات المشروع.
    """

    @staticmethod
    def validate_market(order: OrderRequest) -> None:
        if order.market_type is not MarketType.SPOT:
            raise PermissionError(
                f"Non-spot order blocked: {order.market_type.value}"
            )

    @staticmethod
    def validate_entry(order: OrderRequest) -> None:
        ShariaGuard.validate_market(order)

        if order.side is not Side.BUY:
            raise ValueError("Entry order must be a buy order.")

        if order.stop_loss is None or order.stop_loss <= 0:
            raise ValueError("Every entry must have a positive stop loss.")

        if order.risk_fraction is None or order.risk_fraction <= 0:
            raise ValueError("Every entry must have a positive risk fraction.")

    @staticmethod
    def validate_sell(
        order: OrderRequest,
        portfolio: Portfolio,
        quantity: float,
    ) -> None:
        ShariaGuard.validate_market(order)

        if order.side is not Side.SELL:
            raise ValueError("Exit order must be a sell order.")

        if quantity <= 0:
            raise ValueError("Sell quantity must be positive.")

        owned_quantity = portfolio.owned_quantity(order.symbol)

        if quantity > owned_quantity + 1e-12:
            raise PermissionError(
                "Selling more than the owned quantity is prohibited. "
                f"Requested={quantity}, owned={owned_quantity}"
            )
