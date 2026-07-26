from __future__ import annotations

from spotbot.research.ams_ed01_v4_t12_native import fee_overlay


def test_fixed_ledger_fee_overlay_is_deterministic_and_zero_cost_is_gross() -> None:
    fills = [
        {"fill_type": "ENTRY", "notional": 100.0},
        {"fill_type": "END_OF_FOLD_EXIT", "notional": 120.0},
    ]
    overlay = fee_overlay(fills, 1000.0, [0.0, 0.004])
    assert overlay[0]["final_equity"] == 1020.0
    assert overlay[1]["fee_drag"] == 0.88
    assert overlay[1]["net_return"] < overlay[0]["net_return"]
