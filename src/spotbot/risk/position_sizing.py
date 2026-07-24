from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskConfig:
    risk_per_trade: float = 0.005
    max_position_fraction: float = 0.35
    max_open_positions: int = 3
    max_total_open_risk: float = 0.015
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    minimum_order_value: float = 10.0

    def validate(self) -> None:
        fractions = {
            "risk_per_trade": self.risk_per_trade,
            "max_position_fraction": self.max_position_fraction,
            "max_total_open_risk": self.max_total_open_risk,
            "fee_rate": self.fee_rate,
            "slippage_rate": self.slippage_rate,
        }

        for name, value in fractions.items():
            if value < 0:
                raise ValueError(f"{name} cannot be negative.")

        if self.risk_per_trade <= 0:
            raise ValueError("risk_per_trade must be positive.")

        if self.max_position_fraction <= 0 or self.max_position_fraction > 1:
            raise ValueError("max_position_fraction must be in (0, 1].")

        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1.")

        if self.minimum_order_value <= 0:
            raise ValueError("minimum_order_value must be positive.")


def calculate_position_quantity(
    *,
    equity: float,
    available_cash: float,
    entry_price: float,
    stop_price: float,
    requested_risk_fraction: float,
    config: RiskConfig,
) -> float:
    config.validate()

    if equity <= 0:
        raise ValueError("Equity must be positive.")

    if available_cash < 0:
        raise ValueError("Available cash cannot be negative.")

    if entry_price <= 0 or stop_price <= 0:
        raise ValueError("Entry and stop prices must be positive.")

    if stop_price >= entry_price:
        raise ValueError("Long-position stop must be below entry price.")

    if requested_risk_fraction <= 0:
        raise ValueError("Requested risk fraction must be positive.")

    effective_risk_fraction = min(
        requested_risk_fraction,
        config.risk_per_trade,
    )

    risk_budget = equity * effective_risk_fraction
    risk_per_unit = entry_price - stop_price
    risk_based_quantity = risk_budget / risk_per_unit

    max_position_value = equity * config.max_position_fraction
    max_position_quantity = max_position_value / entry_price

    cash_quantity = available_cash / (
        entry_price * (1 + config.fee_rate)
    )

    return max(
        0.0,
        min(
            risk_based_quantity,
            max_position_quantity,
            cash_quantity,
        ),
    )
