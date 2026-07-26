from __future__ import annotations

from ams_v5_native_support import panel, row

from spotbot.research.ams_ed01_v4_t12_native import T12_PARAMS, T12_PROFILE
from spotbot.research.ams_v5_native_engine import simulate_native_fold


def test_reentry_and_addon_switches_affect_only_their_registered_actions() -> None:
    frame = panel(
        row(0, family="PULLBACK_CONTINUATION", overrides={"structure_reference": 95.0}),
        row(1, low=94, close=96),
        row(2, close=100),
        row(3, family="PULLBACK_CONTINUATION", close=102),
        row(4, close=103),
    )
    result = simulate_native_fold(
        four_hour_panel=frame,
        configuration=T12_PARAMS,
        portfolio_profile=T12_PROFILE,
        selected_threshold=55,
        transaction_cost=0.002,
        allow_reentry=False,
        allow_add_on=False,
    )
    assert not any(trade.reentry_sequence for trade in result.trades)
    assert not any(fill.fill_type == "ADD_ON" for fill in result.fills)
