from __future__ import annotations

import pandas as pd

from spotbot.research.rd07_coverage_audit import (
    CoverageGate,
    attach_match_flags,
    decision_metrics,
    evaluate_gate,
)


def test_match_requires_exact_causal_decision_close() -> None:
    decision = pd.Timestamp("2024-01-01T00:00:00Z")
    index = pd.DataFrame(
        {
            "decision_time": [decision, decision],
            "grid_id": ["PRIMARY_GRID", "PRIMARY_GRID"],
            "symbol": ["BTC", "ETH"],
        }
    )
    matched = attach_match_flags(index, {"BTC": {decision}, "ETH": set()})
    assert matched["matched"].tolist() == [True, False]


def test_gate_fails_without_minimum_symbols() -> None:
    matched = pd.DataFrame({"matched": [True] * 19})
    decisions = pd.DataFrame({"matched_symbol_share": [1.0], "matched_symbol_count": [19]})
    fold_grid = pd.DataFrame({"matched_row_share": [1.0]})
    passed, reasons = evaluate_gate(matched, decisions, fold_grid, CoverageGate())
    assert not passed
    assert reasons == ["MINIMUM_MATCHED_SYMBOLS_PER_DECISION"]


def test_decision_metrics_are_deterministic() -> None:
    frame = pd.DataFrame(
        {
            "decision_time": [pd.Timestamp("2024-01-01T00:00:00Z")] * 2,
            "grid_id": ["PRIMARY_GRID"] * 2,
            "matched": [True, False],
        }
    )
    result = decision_metrics(frame)
    assert result.loc[0, "matched_symbol_share"] == 0.5
