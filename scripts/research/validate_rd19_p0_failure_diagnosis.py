"""Validate RD19-P0 failure diagnosis outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.rd19_p0_failure_diagnosis import (
    CANDIDATE_ID,
    DECISION,
    NEXT_STAGE,
    P0DiagnosisError,
    load_json_object,
    sha256,
)

REQUIRED_FILES = {
    "input-evidence-ledger.csv",
    "cost-friction-diagnosis.csv",
    "engine-attribution.csv",
    "market-regime-attribution.csv",
    "volatility-regime-attribution.csv",
    "exit-attribution.csv",
    "holding-attribution.csv",
    "asset-attribution.csv",
    "year-attribution.csv",
    "tail-concentration.csv",
    "candidate-hypothesis-ledger.json",
    "rd19-p0-failure-diagnosis-report-v1.json",
    "rd19-p0-failure-diagnosis-v1.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    return parser.parse_args()


def validate_manifest(output: Path) -> dict[str, Any]:
    manifest = load_json_object(output / "output-manifest.json")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise P0DiagnosisError("manifest files must be a list")
    observed: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise P0DiagnosisError("manifest row must be an object")
        name = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str):
            raise P0DiagnosisError("manifest row fields are invalid")
        path = output / name
        if not path.is_file():
            raise P0DiagnosisError(f"manifest file missing: {name}")
        if sha256(path) != digest:
            raise P0DiagnosisError(f"manifest hash drift: {name}")
        observed.add(name)
    if observed != REQUIRED_FILES:
        raise P0DiagnosisError(f"manifest file set drift: {sorted(observed ^ REQUIRED_FILES)}")
    expected_flags = {
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "new_candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
    for key, expected in expected_flags.items():
        if manifest.get(key) != expected:
            raise P0DiagnosisError(f"manifest flag drift: {key}")
    return manifest


def main() -> int:
    args = parse_args()
    if not args.offline:
        raise P0DiagnosisError("--offline is required")
    output = args.output_dir.resolve()
    validate_manifest(output)
    report = load_json_object(output / "rd19-p0-failure-diagnosis-report-v1.json")
    expected = {
        "passed": True,
        "decision": DECISION,
        "selected_candidate_id": CANDIDATE_ID,
        "selected_candidate_rank": 1,
        "next_stage": NEXT_STAGE,
        "thresholds_selected": False,
        "parameters_frozen": False,
        "new_candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "holdout_2025_accessed": False,
        "holdout_2026_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": value, "actual": report.get(key)}
        for key, value in expected.items()
        if report.get(key) != value
    }
    if drift:
        raise P0DiagnosisError(f"report semantic drift: {drift}")

    inputs = pd.read_csv(output / "input-evidence-ledger.csv")
    if len(inputs) != 6:
        raise P0DiagnosisError("exactly six sealed input runs required")
    if int(inputs["maximum_entry_year"].max()) > 2024:
        raise P0DiagnosisError("post-2024 input detected")
    costs = pd.read_csv(output / "cost-friction-diagnosis.csv")
    if len(costs) != 3:
        raise P0DiagnosisError("three cost-friction rows required")
    if not bool((costs["two_x_net_return"] < 0.0).all()):
        raise P0DiagnosisError("expected all two-x returns to be negative")

    ledger = load_json_object(output / "candidate-hypothesis-ledger.json")
    if ledger.get("selected_candidate_id") != CANDIDATE_ID:
        raise P0DiagnosisError("selected candidate drifted")
    if ledger.get("post_2024_holdout_status") != "SEALED":
        raise P0DiagnosisError("post-2024 holdout is not sealed")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "selected_candidate_id": CANDIDATE_ID,
                "next_stage": NEXT_STAGE,
                "output_dir": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
