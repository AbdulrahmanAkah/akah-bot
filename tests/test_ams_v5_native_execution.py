from __future__ import annotations

import pytest
from ams_v5_native_support import panel, row, run

from spotbot.research.ams_v5_native_engine import trailing_stop


def test_signal_executes_only_at_next_open_then_intrabar_stop_reconciles() -> None:
    result = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, open_price=100, high=102, low=96, close=101),
            row(2, open_price=101, high=102, low=94, close=96),
        )
    )
    assert [fill.fill_type for fill in result.fills] == ["ENTRY", "STOP_EXIT"]
    assert result.fills[0].timestamp == result.candidates[0].signal_close
    assert result.fills[0].timestamp > result.candidates[0].signal_open
    assert result.fills[0].timestamp == result.scheduled_entries[0].entry_time
    assert result.fills[1].price == pytest.approx(95.0)
    assert result.reconciliation.status == "PASS"


def test_gap_stop_uses_open_and_charges_both_fills() -> None:
    result = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, open_price=100, high=102, low=96, close=101),
            row(2, open_price=93, high=94, low=92, close=93),
        )
    )
    assert result.fills[-1].fill_type == "STOP_EXIT"
    assert result.fills[-1].price == 93
    assert all(fill.fee > 0 for fill in result.fills)


def test_trailing_activates_after_2_25r_and_applies_to_later_bar() -> None:
    result = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, open_price=100, high=112, low=96, close=111),
            row(2, open_price=110, high=111, low=103, close=104),
        )
    )
    assert result.fills[-1].fill_type == "TRAILING_EXIT"
    assert result.fills[-1].price > 95
    assert result.trades[0].mfe_r >= 2.25


def test_trailing_contract_has_no_early_break_even_and_is_monotonic() -> None:
    assert trailing_stop(90, 100, 2, 2.0, None) == (90, None)
    raised, reason = trailing_stop(90, 100, 2, 2.25, None, highest_price=111.25)
    assert raised >= 90
    assert reason == "MFE_2_25R"
    assert trailing_stop(raised, 100, 2, 3.0, 102)[0] >= raised


def test_two_confirmed_structure_failures_exit_at_following_open() -> None:
    result = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, low=96, overrides={"structure_failure": True}),
            row(2, low=96, overrides={"structure_failure": True}),
            row(3, open_price=99, low=96),
        )
    )
    assert result.fills[-1].fill_type == "STRUCTURE_EXIT"
    assert result.fills[-1].timestamp == result.fills[0].timestamp + 8 * (
        result.fills[0].timestamp - result.candidates[0].signal_open
    ) / 4


def test_stagnation_requires_every_condition() -> None:
    rows = [row(0, family="SHALLOW_PULLBACK_RECLAIM")]
    for index in range(1, 27):
        rows.append(
            row(
                index,
                high=102,
                low=96,
                overrides={
                    "eight_hour_weak": True,
                    "conviction_declined": True,
                    "new_bullish_structure": False,
                },
            )
        )
    result = run(panel(*rows))
    assert any(fill.fill_type == "STAGNATION_EXIT" for fill in result.fills)
    rows[-3]["new_bullish_structure"] = True
    rows[-2]["new_bullish_structure"] = True
    no_exit = run(panel(*rows))
    assert not any(fill.fill_type == "STAGNATION_EXIT" for fill in no_exit.fills)
