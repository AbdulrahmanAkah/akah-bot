from __future__ import annotations

import pandas as pd
import pytest
from ams_v5_native_support import panel, row, run

from spotbot.research import ams_v5_native_engine
from spotbot.research.ams_v5_native_engine import (
    V5PortfolioProfile,
    correlation_clusters,
    drawdown_multiplier,
    profiles,
)


def test_add_on_is_next_open_one_quarter_initial_quantity_and_reconciles() -> None:
    result = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, family="SHALLOW_PULLBACK_RECLAIM", high=107, low=96, close=107),
            row(2, open_price=107, high=108, low=101, close=106),
            row(3, open_price=106, high=107, low=94, close=95),
        )
    )
    entry, add_on = result.fills[:2]
    assert add_on.fill_type == "ADD_ON"
    assert add_on.timestamp == result.candidates[1].signal_close
    assert add_on.timestamp > result.candidates[1].signal_open
    assert add_on.quantity == pytest.approx(entry.quantity * 0.25)
    assert len([fill for fill in result.fills if fill.fill_type == "ADD_ON"]) == 1
    assert result.reconciliation.status == "PASS"
    assert result.final_cash >= 0


def test_add_on_is_rejected_for_loser_and_second_use() -> None:
    loser = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, family="SHALLOW_PULLBACK_RECLAIM", high=102, low=96, close=101),
            row(2, open_price=101, high=102, low=96, close=101),
        )
    )
    assert loser.rejections["ADD_ON_BELOW_1_25R"] >= 1
    winner = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, family="SHALLOW_PULLBACK_RECLAIM", high=107, low=96, close=107),
            row(2, family="SHALLOW_PULLBACK_RECLAIM", open_price=107, high=108, low=101, close=107),
            row(3, open_price=107, high=108, low=101, close=107),
        )
    )
    assert winner.rejections["ADD_ON_ALREADY_USED"] >= 1


def test_reentry_requires_two_full_bars_and_is_a_new_trade() -> None:
    result = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, family="SHALLOW_PULLBACK_RECLAIM", open_price=100, high=101, low=94, close=100),
            row(2, family="SHALLOW_PULLBACK_RECLAIM", high=102, low=96, close=101),
            row(3, family="SHALLOW_PULLBACK_RECLAIM", high=102, low=96, close=101),
            row(4, open_price=101, high=103, low=96, close=102),
        )
    )
    entries = [fill for fill in result.fills if fill.fill_type == "ENTRY"]
    assert result.rejections["REENTRY_COOLDOWN"] >= 1
    assert len(entries) == 2
    assert entries[0].position_id != entries[1].position_id
    assert len(result.trades) == 2
    assert result.trades[1].reentry_sequence == 1


def test_causal_cluster_snapshot_ignores_future_mutation() -> None:
    rows = []
    for day in range(25):
        for symbol in ("AAA", "BBB", "CCC"):
            price = 100 + day
            rows.append(
                row(
                    day * 6,
                    symbol=symbol,
                    open_price=price,
                    high=price + 1,
                    low=price - 1,
                    close=price,
                )
            )
    frame = panel(*rows)
    as_of = pd.Timestamp("2022-01-26T00:00:00Z")
    first = correlation_clusters(frame, as_of)
    mutated = frame.copy()
    mutated.loc[mutated["bar_close_time"] >= as_of, "close"] *= 50
    assert correlation_clusters(mutated, as_of) == first
    assert len(set(first.values())) == 1


def test_drawdown_throttle_and_profiles_are_literal() -> None:
    p01, p02 = profiles()
    assert (p01.base_risk, p01.max_heat, p01.max_positions) == (0.007, 0.045, 5)
    assert (p02.base_risk, p02.max_heat, p02.max_positions) == (0.0095, 0.065, 6)
    assert drawdown_multiplier(0.08) == 0.85
    assert drawdown_multiplier(0.241) == 0.0


def test_third_simultaneous_candidate_in_same_cluster_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ams_v5_native_engine,
        "correlation_clusters",
        lambda _frame, _as_of: {"AAA": "ONE", "BBB": "ONE", "CCC": "ONE"},
    )
    frame = panel(
        *(
            row(0, symbol=symbol, family="SHALLOW_PULLBACK_RECLAIM")
            for symbol in ("AAA", "BBB", "CCC")
        ),
        *(row(1, symbol=symbol) for symbol in ("AAA", "BBB", "CCC")),
    )
    profile = V5PortfolioProfile("CLUSTER", 0.007, 0.0095, 0.012, 0.045, 5, 2)
    result = run(frame, profile=profile)
    assert len([fill for fill in result.fills if fill.fill_type == "ENTRY"]) == 2
    assert result.rejections["ENTRY_CLUSTER_LIMIT"] == 1
