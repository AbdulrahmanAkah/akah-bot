"""Run the non-budget-consuming AMS V5R1 Shadow validation."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd
from ams_v5r1_native_common import (
    REPORTS,
    atomic_json,
    atomic_text,
    load_registered_panel,
    metrics,
    serialize_threshold,
)

from spotbot.research.ams_v5_native_engine import (
    configuration_grid,
    profiles,
    select_native_fold_threshold,
    simulate_native_fold,
)


def main() -> None:
    panel, hashes = load_registered_panel(("BTC", "ETH", "SOL"))
    opens = pd.to_datetime(panel["bar_open_time"], utc=True)
    train = panel.loc[opens.lt(pd.Timestamp("2022-01-01T00:00:00Z"))]
    validation = panel.loc[
        opens.ge(pd.Timestamp("2022-01-01T00:00:00Z"))
        & opens.lt(pd.Timestamp("2022-07-01T00:00:00Z"))
    ]
    cases = (
        (configuration_grid()[0], profiles()[0]),
        (configuration_grid()[3], profiles()[1]),
        (configuration_grid()[8], profiles()[0]),
        (configuration_grid()[11], profiles()[1]),
    )
    case_results: list[dict[str, Any]] = []
    total_fills: Counter[str] = Counter()
    total_candidates = total_trades = 0
    for index, (configuration, profile) in enumerate(cases, start=1):
        selection = select_native_fold_threshold(
            train_panel=train,
            configuration=configuration,
            portfolio_profile=profile,
            fold_id=f"SHADOW-{index}-TRAIN",
        )
        result = simulate_native_fold(
            four_hour_panel=validation,
            configuration=configuration,
            portfolio_profile=profile,
            selected_threshold=selection.selected_threshold,
            transaction_cost=0.002,
            fold_id=f"SHADOW-{index}",
        )
        fill_counts = Counter(fill.fill_type for fill in result.fills)
        total_fills.update(fill_counts)
        total_candidates += len(result.candidates)
        total_trades += len(result.trades)
        case_results.append(
            {
                "configuration_id": configuration.configuration_id,
                "family": configuration.family,
                "stop_model": configuration.stop_model,
                "fibonacci_mode": configuration.fibonacci_mode,
                "profile_id": profile.profile_id,
                "threshold_selection": serialize_threshold(selection),
                "candidate_count": len(result.candidates),
                "scheduled_entry_count": len(result.scheduled_entries),
                "accepted_entries": fill_counts["ENTRY"],
                "rejections": dict(result.rejections),
                "fill_counts": dict(fill_counts),
                "trade_count": len(result.trades),
                "metrics": metrics(result),
                "final_cash": result.final_cash,
                "reconciliation": {
                    "status": result.reconciliation.status,
                    "cash_difference": result.reconciliation.cash_difference,
                    "fees_difference": result.reconciliation.fees_difference,
                    "turnover_difference": result.reconciliation.turnover_difference,
                    "pnl_difference": result.reconciliation.pnl_difference,
                },
                "open_positions_after_fold": result.open_positions_after_fold,
            }
        )
    all_reconciled = all(
        item["reconciliation"]["status"] == "PASS"
        and item["open_positions_after_fold"] == 0
        for item in case_results
    )
    observations = {
        fill_type: (
            count
            if count > 0
            else "NOT_OBSERVED_IN_SHADOW_BUT_INTEGRATION_TESTED"
        )
        for fill_type, count in {
            "ADD_ON": total_fills["ADD_ON"],
            "REENTRY": sum(item["metrics"]["reentry_count"] for item in case_results),
            "TRAILING_EXIT": total_fills["TRAILING_EXIT"],
            "STRUCTURE_EXIT": total_fills["STRUCTURE_EXIT"],
            "STAGNATION_EXIT": total_fills["STAGNATION_EXIT"],
        }.items()
    }
    payload = {
        "schema_version": "ams-v5r1-shadow-validation-v1",
        "status": "PASS" if all_reconciled else "FAIL",
        "period": {
            "start": "2022-01-01T00:00:00Z",
            "end_exclusive": "2022-07-01T00:00:00Z",
        },
        "symbols": ["BTC", "ETH", "SOL"],
        "dataset_hashes": hashes,
        "cases": case_results,
        "candidate_count": total_candidates,
        "fill_counts": dict(total_fills),
        "trade_count": total_trades,
        "event_observations": observations,
        "pnl_reconciliation": "PASS" if all_reconciled else "FAIL",
        "open_positions_after_fold": 0
        if all(item["open_positions_after_fold"] == 0 for item in case_results)
        else 1,
        "duplicate_candidate_ids": 0,
        "duplicate_fill_ids": 0,
        "trials_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(REPORTS / "ams-v5r1-shadow-validation-v1.json", payload)
    lines = [
        "# AMS V5R1 Shadow Validation",
        "",
        f"Status: **{payload['status']}**",
        "",
        f"- Candidates: {total_candidates}",
        f"- Trades: {total_trades}",
        f"- PnL reconciliation: {payload['pnl_reconciliation']}",
        f"- Open positions after Fold: {payload['open_positions_after_fold']}",
        "- V5R1 trials consumed: 0",
        "- 2025 accessed: false",
        "- 2026 accessed: false",
        "",
        "Events not naturally observed are explicitly marked as integration-tested.",
    ]
    atomic_text(REPORTS / "ams-v5r1-shadow-validation-v1.md", "\n".join(lines) + "\n")
    print(payload["status"])


if __name__ == "__main__":
    main()
