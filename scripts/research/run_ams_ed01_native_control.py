"""Run the fixed V4 T12 alpha through the audited Native engine only."""

from __future__ import annotations

import shutil
from pathlib import Path

from ams_v5r1_native_common import atomic_json

from spotbot.research.ams_ed01_v4_t12_native import (
    build_v4_t12_panel,
    load_registered_v4_source,
    run_native,
)

ROOT = Path.cwd()
REPORTS = ROOT / "reports" / "research"
OUTSIDE = Path(r"C:\SIRAJ\Reports")


def main() -> None:
    four_hour, availability, hashes = load_registered_v4_source(ROOT)
    panel = build_v4_t12_panel(four_hour, availability)
    base = run_native(panel, transaction_cost=0.002)
    stress = run_native(panel, transaction_cost=0.004)
    base_metrics = base["aggregate"]
    stress_metrics = stress["aggregate"]
    if (
        base_metrics["pnl_reconciliation"] != "PASS"
        or stress_metrics["pnl_reconciliation"] != "PASS"
    ):
        raise RuntimeError("Native control reconciliation failed")
    status = (
        "EDGE_SURVIVES_NATIVE_EXECUTION"
        if base_metrics["aggregate_compounded_return"] > 0
        and stress_metrics["aggregate_compounded_return"] > 0
        and base_metrics["mean_profit_factor"] > 1
        and stress_metrics["mean_profit_factor"] > 1
        else "EDGE_WEAKENS_BUT_REMAINS_POSITIVE"
        if base_metrics["aggregate_compounded_return"] > 0
        and stress_metrics["aggregate_compounded_return"] > 0
        else "EDGE_DISAPPEARS_UNDER_NATIVE_EXECUTION"
    )
    report = {
        "schema_version": "ams-ed01-native-control-v1",
        "status": "PASS",
        "native_edge_status": status,
        "dataset_hashes": hashes,
        "base": base,
        "stress": stress,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    path = REPORTS / "ams-ed01-v4-t12-native-control-v1.json"
    atomic_json(path, report)
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, OUTSIDE / path.name)
    print(path)


if __name__ == "__main__":
    main()
