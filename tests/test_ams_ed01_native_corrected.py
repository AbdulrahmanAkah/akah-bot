from __future__ import annotations

from ams_v5_native_support import panel, row

from spotbot.research.ams_ed01_v4_t12_native import T12_PARAMS, T12_PROFILE
from spotbot.research.ams_v5_native_engine import simulate_native_fold


def test_native_corrected_uses_audited_fill_engine() -> None:
    result = simulate_native_fold(
        four_hour_panel=panel(
            row(0, family="PULLBACK_CONTINUATION", overrides={"structure_reference": 95.0}),
            row(1, open_price=100, high=103, low=96, close=102),
        ),
        configuration=T12_PARAMS,
        portfolio_profile=T12_PROFILE,
        selected_threshold=55,
        transaction_cost=0.002,
    )
    assert result.reconciliation.status == "PASS"
    assert result.open_positions_after_fold == 0
