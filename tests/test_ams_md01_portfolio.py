from __future__ import annotations

import pandas as pd
from ams_md01_support import synthetic_registered_frames

from spotbot.research.ams_md01_momentum import simulate_md01_fold


def test_portfolio_is_spot_long_only_nonnegative_cash() -> None:
    frames = synthetic_registered_frames(("BTC", "ETH", "SOL"))
    result = simulate_md01_fold(
        four_hour=frames["four_hour"],
        daily=frames["daily"],
        eight_hour=frames["eight_hour"],
        availability=frames["availability"],
        variant_id="MD01-M03",
        fold_id="TEST",
        validation_start=pd.Timestamp("2021-04-01T00:00:00Z"),
        validation_end=pd.Timestamp("2021-05-15T00:00:00Z"),
        transaction_cost=0.004,
    )
    assert all(fill.quantity > 0 for fill in result.fills)
    assert all(fill.cash_after >= 0 for fill in result.fills)
    assert max(
        (
            sum(
                fill.fill_type == "ENTRY" and fill.timestamp == timestamp
                for fill in result.fills
            )
            for timestamp in {fill.timestamp for fill in result.fills}
        ),
        default=0,
    ) <= 3
    assert result.reconciliation.status == "PASS"


def test_flat_and_crisis_controls_do_not_mutate_registered_parameters() -> None:
    frames = synthetic_registered_frames()
    arguments = dict(
        four_hour=frames["four_hour"],
        daily=frames["daily"],
        eight_hour=frames["eight_hour"],
        availability=frames["availability"],
        variant_id="MD01-M01",
        fold_id="TEST",
        validation_start=pd.Timestamp("2021-04-01T00:00:00Z"),
        validation_end=pd.Timestamp("2021-05-15T00:00:00Z"),
    )
    registered = simulate_md01_fold(**arguments, control_mode="REGISTERED")
    flat = simulate_md01_fold(**arguments, control_mode="FLAT_ALIGNMENT")
    crisis_off = simulate_md01_fold(**arguments, control_mode="CRISIS_OFF")
    assert all(item["variant_id"] == "MD01-M01" for item in registered.candidates)
    assert all(item["variant_id"] == "MD01-M01" for item in flat.candidates)
    assert all(item["variant_id"] == "MD01-M01" for item in crisis_off.candidates)

