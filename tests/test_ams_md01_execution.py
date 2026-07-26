from __future__ import annotations

import pandas as pd
from ams_md01_support import synthetic_registered_frames

from spotbot.research.ams_md01_momentum import simulate_md01_fold


def _run() -> object:
    frames = synthetic_registered_frames()
    return simulate_md01_fold(
        four_hour=frames["four_hour"],
        daily=frames["daily"],
        eight_hour=frames["eight_hour"],
        availability=frames["availability"],
        variant_id="MD01-M01",
        fold_id="TEST",
        validation_start=pd.Timestamp("2021-04-01T00:00:00Z"),
        validation_end=pd.Timestamp("2021-05-15T00:00:00Z"),
        transaction_cost=0.002,
    )


def test_next_open_scheduling_and_no_same_bar_entry() -> None:
    result = _run()
    candidates = {item["candidate_id"]: item for item in result.candidates}
    entries = [fill for fill in result.fills if fill.fill_type == "ENTRY"]
    assert entries
    for fill in entries:
        candidate = candidates[fill.candidate_id]
        assert fill.timestamp == pd.Timestamp(candidate["scheduled_entry"])
        assert fill.timestamp > pd.Timestamp(candidate["signal_bar_open"])


def test_no_tactical_exit_or_add_on_and_end_fold_closes() -> None:
    result = _run()
    fill_types = {fill.fill_type for fill in result.fills}
    assert "ADD_ON" not in fill_types
    assert "STOP_EXIT" not in fill_types
    assert "TRAILING_EXIT" not in fill_types
    assert "END_OF_FOLD_EXIT" in fill_types
    assert result.open_positions_after_fold == 0


def test_fees_cash_and_fill_reconstruction() -> None:
    result = _run()
    assert result.status == "PASS"
    assert result.final_cash >= 0
    assert result.reconciliation.status == "PASS"
    assert result.reconciliation.fees > 0
    assert abs(result.reconciliation.cash_difference) <= 1e-7

