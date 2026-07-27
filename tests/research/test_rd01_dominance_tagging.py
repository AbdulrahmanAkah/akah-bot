from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pandas as pd

from spotbot.research.rd01_dominance_tagging import (
    dominance_quadrant,
    financial_fingerprint,
    tag_candidate_ledger,
    tag_fold_result,
    tag_trade_ledger,
)


@dataclass(frozen=True)
class Fill:
    fill_id: str
    candidate_id: str
    position_id: str
    symbol: str
    timestamp: pd.Timestamp
    fill_type: str
    price: float
    quantity: float
    notional: float
    fee: float
    cash_before: float
    cash_after: float
    position_quantity_before: float
    position_quantity_after: float
    portfolio_heat_before: float
    portfolio_heat_after: float
    reason: str


@dataclass(frozen=True)
class Trade:
    trade_id: str
    position_id: str
    candidate_id: str
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    return_fraction: float
    exit_reason: str
    alignment_tier: str
    holding_hours: float
    mfe: float
    mae: float
    natural_reselection_sequence: int
    previous_position_id: str | None


@dataclass(frozen=True)
class Reconciliation:
    status: str
    final_cash: float
    fees: float
    turnover: float
    realised_pnl: float
    open_quantities: dict[str, float]
    cash_difference: float
    fee_difference: float
    turnover_difference: float
    pnl_difference: float


def dominance_frame() -> pd.DataFrame:
    days = pd.date_range(
        "2021-01-01T00:00:00Z",
        periods=120,
        freq="1D",
    )
    frame = pd.DataFrame(
        {
            "day": days,
            "available_at": days + pd.Timedelta(days=1),
            "btc_dominance_pct": 40.0,
            "eth_dominance_pct": 20.0,
            "stablecoin_dominance_pct": 10.0,
            "altcoin_share_pct": 60.0,
        }
    )

    for window in (7, 28, 84):
        frame[f"btc_dominance_change_{window}d_pp"] = (
            pd.Series(range(len(frame)), dtype=float).sub(60.0) / window
        )
        frame[f"stablecoin_dominance_change_{window}d_pp"] = (
            60.0 - pd.Series(range(len(frame)), dtype=float)
        ) / window

    return frame


def fold_result() -> Any:
    entry = pd.Timestamp("2021-03-05T00:00:00Z")
    exit_time = pd.Timestamp("2021-03-12T00:00:00Z")
    fill_entry = Fill(
        "F1",
        "C1",
        "P1",
        "BTC",
        entry,
        "ENTRY",
        10.0,
        5.0,
        50.0,
        0.1,
        100.0,
        49.9,
        0.0,
        5.0,
        0.0,
        0.0,
        "ENTRY",
    )
    fill_exit = Fill(
        "F2",
        "C1",
        "P1",
        "BTC",
        exit_time,
        "REBALANCE_EXIT",
        12.0,
        5.0,
        60.0,
        0.1,
        49.9,
        109.8,
        5.0,
        0.0,
        0.0,
        0.0,
        "REBALANCE_EXIT",
    )
    trade = Trade(
        "T1",
        "P1",
        "C1",
        "BTC",
        entry,
        exit_time,
        10.0,
        12.0,
        5.0,
        10.0,
        9.8,
        0.1956,
        "REBALANCE_EXIT",
        "FULL",
        168.0,
        0.25,
        -0.05,
        0,
        None,
    )
    reconciliation = Reconciliation(
        "PASS",
        109.8,
        0.2,
        110.0,
        9.8,
        {},
        0.0,
        0.0,
        0.0,
        0.0,
    )

    return SimpleNamespace(
        fold_id="WF01",
        status="PASS",
        initial_capital=100.0,
        final_cash=109.8,
        fills=(fill_entry, fill_exit),
        trades=(trade,),
        candidates=(
            {
                "candidate_id": "C1",
                "fold_id": "WF01",
                "variant_id": "MD01-M05",
                "symbol": "BTC",
                "signal_bar_open": "2021-03-04T20:00:00+00:00",
                "signal_bar_close": entry.isoformat(),
                "scheduled_entry": entry.isoformat(),
                "alignment_tier": "FULL",
                "accepted": True,
            },
        ),
        selections=(
            {
                "timestamp": "2021-03-01T00:00:00+00:00",
                "fold_id": "WF01",
                "variant_id": "MD01-M05",
                "selected_symbols": ["BTC"],
            },
        ),
        equity_curve=((entry, 100.0), (exit_time, 109.8)),
        reconciliation=reconciliation,
        open_positions_after_fold=0,
    )


def test_quadrants_are_directional_and_outcome_independent() -> None:
    assert dominance_quadrant(1.0, 1.0) == "BTC_UP_STABLE_UP"
    assert dominance_quadrant(1.0, -1.0) == "BTC_UP_STABLE_DOWN"
    assert dominance_quadrant(-1.0, 1.0) == "BTC_DOWN_STABLE_UP"
    assert dominance_quadrant(-1.0, -1.0) == "BTC_DOWN_STABLE_DOWN"
    assert dominance_quadrant(float("nan"), 1.0) == "INSUFFICIENT_LOOKBACK"


def test_candidate_tags_use_prior_available_day() -> None:
    result = fold_result()
    tagged = tag_candidate_ledger(
        tuple(result.candidates),
        dominance_frame(),
    )

    assert tagged.loc[0, "signal_available_at"] <= pd.Timestamp(tagged.loc[0, "signal_bar_close"])
    assert tagged.loc[0, "signal_day"] == pd.Timestamp("2021-03-04T00:00:00Z")
    assert tagged.loc[0, "signal_dominance_tag_status"] == "TAGGED"


def test_trade_ledger_has_entry_and_exit_tags() -> None:
    result = fold_result()
    tagged = tag_trade_ledger(
        tuple(result.trades),
        dominance_frame(),
    )

    assert len(tagged) == 1
    assert tagged.loc[0, "entry_dominance_tag_status"] == "TAGGED"
    assert tagged.loc[0, "exit_dominance_tag_status"] == "TAGGED"
    assert tagged.loc[0, "entry_available_at"] <= tagged.loc[0, "entry_time"]
    assert tagged.loc[0, "exit_available_at"] <= tagged.loc[0, "exit_time"]


def test_fold_tagging_preserves_exact_financial_fingerprint() -> None:
    result = fold_result()
    before = financial_fingerprint(result)
    tagged = tag_fold_result(
        result,
        dominance_frame(),
    )
    after = financial_fingerprint(result)

    assert before == after
    assert tagged["financial_invariance"]
    assert not tagged["trade_logic_changed"]
    assert len(tagged["ledgers"]["fills"]) == 2
    assert len(tagged["ledgers"]["trades"]) == 1
