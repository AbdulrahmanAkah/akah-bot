"""Execute the finite six-variant MD01 matrix, controls, and gated cost runs."""

from __future__ import annotations

import json
from typing import Any

from ams_md01_common import LEDGER, atomic_json, load_registered_data
from run_ams_md01_variant import execute_variant

from spotbot.research.ams_md01_momentum import VARIANTS


def gross_edge_status(aggregate: dict[str, Any]) -> str:
    """Apply the immutable registered portfolio gate."""
    pf = aggregate["profit_factor"]
    full = (
        aggregate["compounded_return"] > 0
        and aggregate["positive_folds"] >= 2
        and pf is not None
        and pf > 1.05
        and aggregate["expectancy"] > 0
        and aggregate["trade_count"] >= 20
        and aggregate["top_1_symbol_contribution"] <= 0.60
        and aggregate["reconciliation_status"] == "PASS"
        and aggregate["open_positions_after_fold"] == 0
    )
    if full:
        return "PORTFOLIO_GROSS_EDGE_PASS"
    weak = (
        aggregate["compounded_return"] > 0
        and pf is not None
        and pf > 1.0
        and aggregate["expectancy"] > 0
    )
    return "PORTFOLIO_GROSS_EDGE_WEAK" if weak else "PORTFOLIO_GROSS_EDGE_FAIL"


def main() -> None:
    frames, hashes = load_registered_data()
    primary_reports: dict[str, dict[str, Any]] = {}
    for variant_id in VARIANTS:
        report, _ = execute_variant(
            variant_id=variant_id,
            cost_mode="ZERO_COST",
            control_mode="REGISTERED",
            frames=frames,
            hashes=hashes,
            consume_primary_budget=True,
        )
        report["gross_edge_status"] = gross_edge_status(report["aggregate"])
        primary_reports[variant_id] = report
        print(f"{variant_id}={report['gross_edge_status']}")
    # Diagnostic controls are pre-registered and do not consume primary budget.
    for variant_id in VARIANTS:
        for control_mode in ("FLAT_ALIGNMENT", "CRISIS_OFF"):
            execute_variant(
                variant_id=variant_id,
                cost_mode="ZERO_COST",
                control_mode=control_mode,
                frames=frames,
                hashes=hashes,
            )
    # Base/stress are conditional on the zero-cost gate and change no policy.
    costed: dict[str, list[str]] = {}
    for variant_id, report in primary_reports.items():
        if report["gross_edge_status"] != "PORTFOLIO_GROSS_EDGE_PASS":
            costed[variant_id] = []
            continue
        costed[variant_id] = []
        for cost_mode in ("BASE_COST", "STRESS_0_4_PERCENT"):
            _, output = execute_variant(
                variant_id=variant_id,
                cost_mode=cost_mode,
                control_mode="REGISTERED",
                frames=frames,
                hashes=hashes,
            )
            costed[variant_id].append(output.name)
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    for record in ledger["trial_plan"]:
        variant_id = record["variant_id"]
        report = primary_reports[variant_id]
        record["gross_edge_status"] = report["gross_edge_status"]
        record["costed_reports"] = costed[variant_id]
    ledger["conditional_cost_runs"] = {
        "rule": "ONLY_PORTFOLIO_GROSS_EDGE_PASS",
        "executed": costed,
    }
    accounting = ledger["trial_accounting"]
    if accounting != {
        "authorized_primary_variants": 6,
        "executed_primary_variants": 6,
        "remaining_primary_variants": 0,
    }:
        raise RuntimeError("final primary budget is not 6/6")
    atomic_json(LEDGER, ledger)
    print("PRIMARY_VARIANTS_EXECUTED=6")
    print("PRIMARY_VARIANTS_REMAINING=0")


if __name__ == "__main__":
    main()
