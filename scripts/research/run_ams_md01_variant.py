"""Run one registered AMS-MD01 variant or one diagnostic control."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from ams_md01_common import (
    LEDGER,
    REPORTS,
    atomic_json,
    load_ledger,
    load_protocol,
    load_registered_data,
    sha256,
)

from spotbot.research.ams_md01_momentum import (
    FOLDS,
    VARIANTS,
    aggregate_fold_metrics,
    serialise_fold,
    simulate_md01_fold,
)

COSTS = {
    "ZERO_COST": 0.0,
    "BASE_COST": 0.002,
    "STRESS_0_4_PERCENT": 0.004,
}
CONTROLS = {"REGISTERED", "FLAT_ALIGNMENT", "CRISIS_OFF"}


def result_name(variant_id: str, cost_mode: str, control_mode: str) -> str:
    suffix = {
        "ZERO_COST": "zero-cost",
        "BASE_COST": "base-cost",
        "STRESS_0_4_PERCENT": "stress-cost",
    }[cost_mode]
    control = "" if control_mode == "REGISTERED" else f"-{control_mode.lower().replace('_', '-')}"
    return f"ams-{variant_id.lower()}-{suffix}{control}-v1.json"


def _validate_protocol(
    variant_id: str,
    cost_mode: str,
    control_mode: str,
) -> None:
    protocol = load_protocol()
    if variant_id not in VARIANTS:
        raise RuntimeError(f"unregistered variant: {variant_id}")
    if cost_mode not in COSTS:
        raise RuntimeError(f"unregistered cost mode: {cost_mode}")
    if control_mode not in CONTROLS:
        raise RuntimeError(f"unregistered control mode: {control_mode}")
    registered = {record["variant_id"] for record in protocol["variants"]}
    if variant_id not in registered:
        raise RuntimeError("variant absent from immutable protocol")


def execute_variant(
    *,
    variant_id: str,
    cost_mode: str,
    control_mode: str,
    frames: dict[str, pd.DataFrame] | None = None,
    hashes: dict[str, str] | None = None,
    consume_primary_budget: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Execute one immutable specification and atomically record it."""
    _validate_protocol(variant_id, cost_mode, control_mode)
    output = REPORTS / result_name(variant_id, cost_mode, control_mode)
    ledger = load_ledger()
    plan_record = next(
        record for record in ledger["trial_plan"] if record["variant_id"] == variant_id
    )
    if consume_primary_budget:
        if cost_mode != "ZERO_COST" or control_mode != "REGISTERED":
            raise RuntimeError("only registered zero-cost runs consume primary budget")
        if plan_record["status"] == "EXECUTED":
            if not output.exists():
                raise RuntimeError("executed ledger record lacks result artifact")
            return json.loads(output.read_text(encoding="utf-8")), output
        accounting = ledger["trial_accounting"]
        if accounting["remaining_primary_variants"] <= 0:
            raise RuntimeError("primary variant budget exhausted")
    if frames is None or hashes is None:
        frames, hashes = load_registered_data()
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
            transaction_cost=COSTS[cost_mode],
            control_mode=control_mode,
        )
        for fold_id, start, end in FOLDS
    ]
    if any(result.status != "PASS" for result in fold_results):
        raise RuntimeError("invalid fold cannot be recorded")
    aggregate = aggregate_fold_metrics(fold_results)
    if (
        aggregate["reconciliation_status"] != "PASS"
        or aggregate["open_positions_after_fold"] != 0
    ):
        raise RuntimeError("fill-ledger reconciliation failed")
    report: dict[str, Any] = {
        "schema_version": "ams-md01-variant-result-v1",
        "variant_id": variant_id,
        "school": VARIANTS[variant_id][0],
        "horizon_days": VARIANTS[variant_id][1],
        "cost_mode": cost_mode,
        "transaction_cost": COSTS[cost_mode],
        "control_mode": control_mode,
        "status": "EXECUTED",
        "aggregate": aggregate,
        "fold_results": [serialise_fold(result) for result in fold_results],
        "dataset_hashes": hashes,
        "execution_contract": {
            "spot_long_only": True,
            "next_four_hour_open": True,
            "tactical_stop": False,
            "add_on": False,
            "mid_week_reentry": False,
            "fill_ledger_source_of_truth": True,
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(output, report)
    report_hash = sha256(output)
    if report_hash != sha256(output):
        raise RuntimeError("variant report hash verification failed")
    ledger = load_ledger()
    ledger["report_hashes"][output.name] = report_hash
    if consume_primary_budget:
        record = next(
            item for item in ledger["trial_plan"] if item["variant_id"] == variant_id
        )
        if record["status"] != "REGISTERED_NOT_EXECUTED":
            raise RuntimeError("primary variant is not executable")
        record["status"] = "EXECUTED"
        record["zero_cost_report"] = output.name
        record["zero_cost_report_sha256"] = report_hash
        accounting = ledger["trial_accounting"]
        accounting["executed_primary_variants"] += 1
        accounting["remaining_primary_variants"] -= 1
        if (
            accounting["executed_primary_variants"]
            + accounting["remaining_primary_variants"]
            != accounting["authorized_primary_variants"]
        ):
            raise RuntimeError("primary budget accounting invariant failed")
    atomic_json(LEDGER, ledger)
    return report, output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant-id", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--cost-mode", choices=sorted(COSTS), required=True)
    parser.add_argument("--control-mode", choices=sorted(CONTROLS), required=True)
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    report, output = execute_variant(
        variant_id=arguments.variant_id,
        cost_mode=arguments.cost_mode,
        control_mode=arguments.control_mode,
        consume_primary_budget=(
            arguments.cost_mode == "ZERO_COST"
            and arguments.control_mode == "REGISTERED"
        ),
    )
    print(f"RESULT={output.name}")
    print(f"RETURN={report['aggregate']['compounded_return']:.8f}")
    print(f"PNL_RECONCILIATION={report['aggregate']['reconciliation_status']}")


if __name__ == "__main__":
    main()

