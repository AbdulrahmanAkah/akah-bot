"""Validate RD19-P2C frozen discovery execution outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd19_p2c_discovery import (  # noqa: E402
    DECISION,
    EXPECTED_RUNS,
    P2CExecutionError,
    load_json_object,
    sha256,
    verify_checkpoint,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise P2CExecutionError("--offline is required")
    output = args.output_dir.resolve()

    report = load_json_object(output / "rd19-p2c-discovery-report-v1.json")
    expected = {
        "passed": True,
        "decision": DECISION,
        "authorized_run_count": EXPECTED_RUNS,
        "completed_run_count": EXPECTED_RUNS,
        "variant_count": 12,
        "combined_metric_rows": 72,
        "2024_internal_confirmation_executed": False,
        "2024_market_data_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P2CExecutionError(f"P2C report semantic drift: {drift}")

    checkpoints = sorted(output.glob("runs/*/*/checkpoint.json"))
    if len(checkpoints) != EXPECTED_RUNS:
        raise P2CExecutionError(f"checkpoint count drifted: {len(checkpoints)}")
    for checkpoint in checkpoints:
        verify_checkpoint(checkpoint.parent)

    run_metrics = pd.read_csv(output / "run-metrics.csv")
    combined = pd.read_csv(output / "combined-2019-2023-metrics.csv")
    gates = pd.read_csv(output / "variant-gate-evaluation.csv")
    finalists = pd.read_csv(output / "finalist-ranking.csv")

    if len(run_metrics) != EXPECTED_RUNS:
        raise P2CExecutionError("run-metrics row count drifted")
    if len(combined) != 72:
        raise P2CExecutionError("combined metric row count drifted")
    if len(gates) != 12 or gates["variant_id"].nunique() != 12:
        raise P2CExecutionError("variant gate coverage drifted")
    if bool((combined["minimum_cash"] < -1e-7).any()):
        raise P2CExecutionError("combined results contain negative cash")

    selected = (
        finalists.loc[
            finalists["selected_for_2024"].astype(bool),
            "variant_id",
        ]
        .astype(str)
        .tolist()
        if not finalists.empty
        else []
    )
    if selected != report["selected_for_2024_variants"]:
        raise P2CExecutionError("selected finalist identity drifted")
    if len(selected) > 2:
        raise P2CExecutionError("more than two finalists selected")

    manifest = load_json_object(output / "output-manifest.json")
    if manifest.get("completed_run_count") != EXPECTED_RUNS:
        raise P2CExecutionError("manifest completed-run count drifted")
    if manifest.get("2024_market_data_accessed") is not False:
        raise P2CExecutionError("manifest reports 2024 market-data access")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise P2CExecutionError("manifest files invalid")
    for raw in files:
        if not isinstance(raw, dict):
            raise P2CExecutionError("manifest row invalid")
        path = output / str(raw["path"])
        if not path.is_file():
            raise P2CExecutionError(f"manifest file missing: {path}")
        if sha256(path) != str(raw["sha256"]):
            raise P2CExecutionError(f"manifest hash drift: {path}")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "completed_run_count": EXPECTED_RUNS,
                "hard_gate_pass_variant_count": report["hard_gate_pass_variant_count"],
                "selected_for_2024_variants": selected,
                "next_stage": report["next_stage"],
                "output_dir": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
