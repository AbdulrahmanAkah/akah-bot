"""Re-run the immutable MD01 survivor-30 specification without consuming R1 trials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ams_md01_common import load_registered_data
from ams_md01r1_common import REPORTS, atomic_json, atomic_text, copy_external, sha256

from spotbot.research.ams_md01_momentum import (
    FOLDS,
    VARIANTS,
    aggregate_fold_metrics,
    simulate_md01_fold,
)
from spotbot.research.ams_md01r1_universe import reproduction_status, stable_hash

COSTS = {
    "ZERO_COST": 0.0,
    "BASE_COST": 0.002,
    "STRESS_0_4_PERCENT": 0.004,
}
SUFFIX = {
    "ZERO_COST": "zero-cost",
    "BASE_COST": "base-cost",
    "STRESS_0_4_PERCENT": "stress-cost",
}


def _historical_path(variant_id: str, cost_mode: str) -> Path:
    return REPORTS / (
        f"ams-{variant_id.lower()}-{SUFFIX[cost_mode]}-v1.json"
    )


def _reference_metrics(path: Path) -> dict[str, float] | None:
    if not path.exists():
        return None
    aggregate = json.loads(path.read_text(encoding="utf-8"))["aggregate"]
    return {
        "trade_count": float(aggregate["trade_count"]),
        "compounded_return": float(aggregate["compounded_return"]),
        "mean_maximum_drawdown": float(aggregate["mean_maximum_drawdown"]),
    }


def _observed_metrics(aggregate: dict[str, Any]) -> dict[str, float]:
    return {
        "trade_count": float(aggregate["trade_count"]),
        "compounded_return": float(aggregate["compounded_return"]),
        "mean_maximum_drawdown": float(aggregate["mean_maximum_drawdown"]),
    }


def main() -> None:
    frames, dataset_hashes = load_registered_data()
    executions: list[dict[str, Any]] = []
    for variant_id in sorted(VARIANTS):
        for cost_mode, cost in COSTS.items():
            fold_results = [
                simulate_md01_fold(
                    four_hour=frames["four_hour"],
                    daily=frames["daily"],
                    eight_hour=frames["eight_hour"],
                    availability=frames["availability"],
                    variant_id=variant_id,
                    fold_id=fold_id,
                    validation_start=start,
                    validation_end=end,
                    transaction_cost=cost,
                )
                for fold_id, start, end in FOLDS
            ]
            aggregate = aggregate_fold_metrics(fold_results)
            if (
                aggregate["reconciliation_status"] != "PASS"
                or aggregate["open_positions_after_fold"] != 0
            ):
                raise RuntimeError("survivor reproduction reconciliation failed")
            reference_path = _historical_path(variant_id, cost_mode)
            expected = _reference_metrics(reference_path)
            observed = _observed_metrics(aggregate)
            status = (
                reproduction_status(expected=expected, observed=observed)
                if expected is not None
                else "EXECUTED_NO_HISTORICAL_REFERENCE"
            )
            candidate_count = sum(len(result.candidates) for result in fold_results)
            fill_count = sum(len(result.fills) for result in fold_results)
            trade_ids = [
                trade.trade_id for result in fold_results for trade in result.trades
            ]
            report = {
                "schema_version": "ams-md01r1-survivor30-reproduction-execution-v1",
                "universe_id": "SURVIVOR_30",
                "variant_id": variant_id,
                "cost_mode": cost_mode,
                "transaction_cost": cost,
                "status": status,
                "aggregate": aggregate,
                "folds": [
                    {
                        "fold_id": result.fold_id,
                        "status": result.status,
                        "candidate_count": len(result.candidates),
                        "fill_count": len(result.fills),
                        "trade_count": len(result.trades),
                        "final_cash": result.final_cash,
                        "reconciliation_status": result.reconciliation.status,
                        "open_positions_after_fold": result.open_positions_after_fold,
                    }
                    for result in fold_results
                ],
                "candidate_count": candidate_count,
                "fill_count": fill_count,
                "trade_id_hash": stable_hash(tuple(sorted(trade_ids))),
                "historical_reference": (
                    {
                        "path": str(reference_path.relative_to(REPORTS.parent.parent)),
                        "sha256": sha256(reference_path),
                        "metrics": expected,
                    }
                    if expected is not None
                    else None
                ),
                "metric_differences": (
                    {
                        key: observed[key] - expected[key]
                        for key in sorted(observed)
                    }
                    if expected is not None
                    else None
                ),
                "dataset_hashes": dataset_hashes,
                "alpha_changed": False,
                "dynamic_trial_consumed": False,
                "test_2025_accessed": False,
                "holdout_2026_accessed": False,
            }
            name = (
                f"ams-md01r1-survivor30-{variant_id.lower()}-"
                f"{SUFFIX[cost_mode]}-reproduction-v1.json"
            )
            atomic_json(REPORTS / name, report)
            executions.append(
                {
                    "variant_id": variant_id,
                    "cost_mode": cost_mode,
                    "status": status,
                    "report": name,
                    "report_sha256": sha256(REPORTS / name),
                    "aggregate": aggregate,
                    "metric_differences": report["metric_differences"],
                }
            )
    referenced = [item for item in executions if item["metric_differences"] is not None]
    exact = all(item["status"] == "EXACT_REPRODUCTION" for item in referenced)
    summary = {
        "schema_version": "ams-md01r1-survivor30-reproduction-v1",
        "status": "EXACT_REPRODUCTION" if exact else "FAILED_REPRODUCTION",
        "execution_count": len(executions),
        "historically_referenced_execution_count": len(referenced),
        "exact_execution_count": sum(
            item["status"] == "EXACT_REPRODUCTION" for item in executions
        ),
        "unreferenced_execution_count": sum(
            item["status"] == "EXECUTED_NO_HISTORICAL_REFERENCE"
            for item in executions
        ),
        "executions": executions,
        "paired_dynamic_configurations_consumed": 0,
        "cost_execution_budget_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    json_name = "ams-md01r1-survivor30-reproduction-v1.json"
    md_name = "ams-md01r1-survivor30-reproduction-v1.md"
    atomic_json(REPORTS / json_name, summary)
    lines = [
        "# AMS-MD01R1 Survivor-30 Reproduction",
        "",
        f"- Status: **{summary['status']}**",
        f"- Executions: {len(executions)}",
        f"- Exact historical comparisons: {summary['exact_execution_count']}",
        (
            "- Executions without a historical cost reference: "
            f"{summary['unreferenced_execution_count']}"
        ),
        "- Dynamic paired configurations consumed: 0",
        "",
        "| Variant | Cost | Return | Trades | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for item in executions:
        aggregate = item["aggregate"]
        lines.append(
            f"| {item['variant_id']} | {item['cost_mode']} | "
            f"{aggregate['compounded_return']:.4%} | {aggregate['trade_count']} | "
            f"{item['status']} |"
        )
    lines.append("")
    atomic_text(REPORTS / md_name, "\n".join(lines))
    copy_external([json_name, md_name])
    print(f"SURVIVOR_30_REPRODUCTION={summary['status']}")
    print(f"REPRODUCTION_EXECUTIONS={len(executions)}")
    print("PAIRED_CONFIGURATIONS_EXECUTED=0")
    print("COST_EXECUTIONS_COMPLETED=0")


if __name__ == "__main__":
    main()
