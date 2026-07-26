"""Run exactly one registered ED01 ablation with atomic ledger accounting."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from ams_v5r1_native_common import atomic_json, sha256

from spotbot.research.ams_ed01_v4_t12_native import (
    build_v4_t12_panel,
    load_registered_v4_source,
    run_native,
)

ROOT = Path.cwd()
REPORTS = ROOT / "reports" / "research"
OUTSIDE = Path(r"C:\SIRAJ\Reports")
LEDGER = REPORTS / "ams-ed01-experiment-ledger-v1.json"


def run(variant_id: str) -> Path:
    ledger: dict[str, Any] = json.loads(LEDGER.read_text(encoding="utf-8"))
    accounting = ledger["trial_accounting"]
    trial = next((item for item in ledger["trial_plan"] if item["variant_id"] == variant_id), None)
    if trial is None:
        raise RuntimeError("unregistered diagnostic variant")
    if trial["status"] == "EXECUTED":
        return ROOT / trial["report_path"]
    if (
        trial["status"] != "REGISTERED_NOT_EXECUTED"
        or accounting["remaining_diagnostic_trials"] <= 0
    ):
        raise RuntimeError("diagnostic budget unavailable")
    four_hour, availability, hashes = load_registered_v4_source(ROOT)
    panel = build_v4_t12_panel(four_hour, availability)
    base = run_native(
        panel,
        transaction_cost=0.002,
        allow_reentry=trial["allow_reentry"],
        allow_add_on=trial["allow_add_on"],
    )
    stress = run_native(
        panel,
        transaction_cost=0.004,
        allow_reentry=trial["allow_reentry"],
        allow_add_on=trial["allow_add_on"],
    )
    report = {
        "schema_version": "ams-ed01-diagnostic-trial-v1",
        "status": "EXECUTED",
        "variant_id": trial["variant_id"],
        "name": trial["name"],
        "configuration_id": "AMS-V4-A06",
        "portfolio_profile_id": "AMS-V4-PORTFOLIO-P02",
        "dataset_hashes": hashes,
        "base": base,
        "stress": stress,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    path = REPORTS / f"ams-ed01-{variant_id.lower()}-diagnostic-v1.json"
    atomic_json(path, report)
    report_hash = sha256(path)
    if sha256(path) != report_hash:
        raise RuntimeError("diagnostic report hash mismatch")
    trial.update(
        {
            "status": "EXECUTED",
            "report_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "report_sha256": report_hash,
        }
    )
    accounting["executed_diagnostic_trials"] += 1
    accounting["remaining_diagnostic_trials"] -= 1
    if (
        accounting["executed_diagnostic_trials"] + accounting["remaining_diagnostic_trials"]
        != accounting["authorized_diagnostic_trials"]
    ):
        raise RuntimeError("diagnostic trial accounting invariant")
    atomic_json(LEDGER, ledger)
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, OUTSIDE / path.name)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant-id", required=True, choices=("ED01-R01", "ED01-R02", "ED01-R03", "ED01-R04")
    )
    parser.add_argument("--cost-mode", default="BOTH", choices=("BOTH",))
    args = parser.parse_args()
    print(run(args.variant_id))


if __name__ == "__main__":
    main()
