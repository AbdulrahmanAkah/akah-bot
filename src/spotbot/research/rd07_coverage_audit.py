"""Deterministic RD07 cross-venue coverage gate."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class CoverageGate:
    overall_panel_row_coverage: float = 0.80
    median_decision_symbol_share: float = 0.80
    minimum_fold_grid_coverage: float = 0.70
    minimum_symbols_per_decision: int = 20


DEFAULT_GATE = CoverageGate()


def attach_match_flags(
    index: pd.DataFrame,
    close_times_by_symbol: dict[str, set[pd.Timestamp]],
) -> pd.DataFrame:
    """Mark a row matched only when the Binance decision-close bar exists."""
    result = index.copy()
    decisions = pd.to_datetime(result["decision_time"], utc=True)
    result["matched"] = [
        decision in close_times_by_symbol.get(str(symbol), set())
        for decision, symbol in zip(decisions, result["symbol"], strict=True)
    ]
    return result


def decision_metrics(matched: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        matched.groupby(["decision_time", "grid_id"], observed=True)["matched"]
        .agg(["count", "sum", "mean"])
        .reset_index()
    )
    return grouped.rename(
        columns={
            "count": "pit_symbol_count",
            "sum": "matched_symbol_count",
            "mean": "matched_symbol_share",
        }
    )


def evaluate_gate(
    matched: pd.DataFrame,
    decisions: pd.DataFrame,
    fold_grid: pd.DataFrame,
    gate: CoverageGate = DEFAULT_GATE,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    overall = float(matched["matched"].mean())
    median_share = float(decisions["matched_symbol_share"].median())
    if overall < gate.overall_panel_row_coverage:
        reasons.append("OVERALL_MATCHED_PANEL_ROW_COVERAGE")
    if median_share < gate.median_decision_symbol_share:
        reasons.append("MEDIAN_DECISION_MATCHED_SYMBOL_SHARE")
    if bool((fold_grid["matched_row_share"] < gate.minimum_fold_grid_coverage).any()):
        reasons.append("FOLD_GRID_MATCHED_COVERAGE")
    evaluable = decisions["matched_symbol_count"] >= gate.minimum_symbols_per_decision
    if not bool(evaluable.all()):
        reasons.append("MINIMUM_MATCHED_SYMBOLS_PER_DECISION")
    return not reasons, reasons
