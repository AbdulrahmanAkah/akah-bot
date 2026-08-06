from __future__ import annotations

import pandas as pd

from spotbot.research.rd18_p3e_cash_feasibility import (
    route_cash_feasible_candidates,
)


def candidate(
    *,
    candidate_id: str,
    symbol: str,
    entry: str,
    exit_time: str,
    notional: float,
    exit_price: float = 100.0,
    priority: int = 1,
) -> dict[str, object]:
    entry_price = 100.0
    quantity = notional / entry_price
    fees = quantity * (entry_price + exit_price) * 0.001
    return {
        "v3_candidate_id": candidate_id,
        "source_v2_candidate_id": candidate_id,
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "symbol": symbol,
        "pair": symbol.replace("/", "-"),
        "signal_close": pd.Timestamp(entry) - pd.Timedelta(hours=1),
        "entry_open_time": pd.Timestamp(entry),
        "entry_bar_close": pd.Timestamp(entry) + pd.Timedelta(hours=1),
        "exit_bar_close": pd.Timestamp(exit_time),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "risk_budget": 500.0,
        "quantity": quantity,
        "notional": notional,
        "gross_pnl": quantity * (exit_price - entry_price),
        "fees": fees,
        "net_pnl": quantity * (exit_price - entry_price) - fees,
        "market_regime": "BULL",
        "engine_id": "TREND_CONTINUATION_CORE_V3",
        "engine_priority": priority,
        "engine_agreement": False,
    }


def test_rejects_entry_that_exceeds_available_cash() -> None:
    frame = pd.DataFrame(
        [
            candidate(
                candidate_id="A",
                symbol="A/USDT",
                entry="2020-01-01T00:00:00Z",
                exit_time="2020-01-01T05:00:00Z",
                notional=60000.0,
            ),
            candidate(
                candidate_id="B",
                symbol="B/USDT",
                entry="2020-01-01T00:00:00Z",
                exit_time="2020-01-01T05:00:00Z",
                notional=60000.0,
                priority=2,
            ),
        ]
    )
    result = route_cash_feasible_candidates(
        frame,
        universe_id="C2",
        cost_multiplier=1.0,
    )
    assert len(result.trades) == 1
    assert result.insufficient_cash_rejections == 1
    assert result.minimum_cash >= 0.0


def test_settled_exit_releases_cash_for_later_entry() -> None:
    frame = pd.DataFrame(
        [
            candidate(
                candidate_id="A",
                symbol="A/USDT",
                entry="2020-01-01T00:00:00Z",
                exit_time="2020-01-01T02:00:00Z",
                notional=60000.0,
                exit_price=110.0,
            ),
            candidate(
                candidate_id="B",
                symbol="B/USDT",
                entry="2020-01-01T03:00:00Z",
                exit_time="2020-01-01T05:00:00Z",
                notional=60000.0,
            ),
        ]
    )
    result = route_cash_feasible_candidates(
        frame,
        universe_id="C2",
        cost_multiplier=1.0,
    )
    assert len(result.trades) == 2
    assert result.insufficient_cash_rejections == 0
    assert result.final_cash > 100000.0


def test_cost_multiplier_changes_cash_admission() -> None:
    frame = pd.DataFrame(
        [
            candidate(
                candidate_id="A",
                symbol="A/USDT",
                entry="2020-01-01T00:00:00Z",
                exit_time="2020-01-01T05:00:00Z",
                notional=100.0,
            ),
            candidate(
                candidate_id="B",
                symbol="B/USDT",
                entry="2020-01-01T00:00:00Z",
                exit_time="2020-01-01T05:00:00Z",
                notional=99701.0,
                priority=2,
            ),
        ]
    )
    one = route_cash_feasible_candidates(
        frame,
        universe_id="C2",
        cost_multiplier=1.0,
    )
    two = route_cash_feasible_candidates(
        frame,
        universe_id="C2",
        cost_multiplier=2.0,
    )
    assert len(one.trades) == 2
    assert len(two.trades) == 1
    assert two.insufficient_cash_rejections == 1
