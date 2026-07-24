import pytest

from spotbot.risk.position_sizing import (
    RiskConfig,
    calculate_position_quantity,
)


def test_position_size_uses_risk_budget() -> None:
    config = RiskConfig(
        risk_per_trade=0.005,
        max_position_fraction=0.35,
        fee_rate=0.001,
    )

    quantity = calculate_position_quantity(
        equity=1_000.0,
        available_cash=1_000.0,
        entry_price=100.0,
        stop_price=98.0,
        requested_risk_fraction=0.005,
        config=config,
    )

    # Risk model gives 2.5 units, but the 35% position cap permits 3.5.
    assert quantity == pytest.approx(2.5)


def test_stop_above_entry_is_rejected() -> None:
    with pytest.raises(ValueError, match="below entry"):
        calculate_position_quantity(
            equity=1_000.0,
            available_cash=1_000.0,
            entry_price=100.0,
            stop_price=101.0,
            requested_risk_fraction=0.005,
            config=RiskConfig(),
        )
