"""Validate RD19-P2B discovery execution authorization outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.rd19_p2b_authorization import (
    CANDIDATE_ID,
    DECISION,
    EXPECTED_RUNS,
    NEXT_STAGE,
    P2BAuthorizationError,
    load_json_object,
    sha256,
)

REQUIRED_FILES = {
    "lineage-hash-manifest.csv",
    "authorization-checks.csv",
    "execution-contract.json",
    "authorization-decision.json",
    "rd19-p2b-authorization-v1.md",
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
        raise P2BAuthorizationError("manifest files must be a list")
    observed: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise P2BAuthorizationError("manifest row must be an object")
        name = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str):
            raise P2BAuthorizationError("manifest row fields are invalid")
        path = output / name
        if not path.is_file():
            raise P2BAuthorizationError(f"manifest file missing: {name}")
        if sha256(path) != digest:
            raise P2BAuthorizationError(f"manifest hash drift: {name}")
        observed.add(name)
    if observed != REQUIRED_FILES:
        raise P2BAuthorizationError(f"manifest file set drift: {sorted(observed ^ REQUIRED_FILES)}")
    expected = {
        "historical_discovery_execution_authorized": True,
        "historical_discovery_execution_executed": False,
        "candidate_backtest_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "performance_reporting_executed": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": manifest.get(key)}
        for key, wanted in expected.items()
        if manifest.get(key) != wanted
    }
    if drift:
        raise P2BAuthorizationError(f"manifest semantic drift: {drift}")
    return manifest


def main() -> int:
    args = parse_args()
    if not args.offline:
        raise P2BAuthorizationError("--offline is required")
    output = args.output_dir.resolve()
    validate_manifest(output)

    decision = load_json_object(output / "authorization-decision.json")
    expected = {
        "passed": True,
        "decision": DECISION,
        "authorized": True,
        "technical_valid": True,
        "blockers": [],
        "selected_candidate_id": CANDIDATE_ID,
        "authorization_status": "AUTHORIZED_NOT_EXECUTED",
        "expected_run_count": EXPECTED_RUNS,
        "historical_discovery_execution_authorized": True,
        "historical_discovery_execution_executed": False,
        "candidate_backtest_executed": False,
        "2024_access_authorized": False,
        "2024_accessed": False,
        "post_2024_access_authorized": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
    }
    drift = {
        key: {"expected": wanted, "actual": decision.get(key)}
        for key, wanted in expected.items()
        if decision.get(key) != wanted
    }
    if drift:
        raise P2BAuthorizationError(f"authorization decision drift: {drift}")

    checks = pd.read_csv(output / "authorization-checks.csv")
    if len(checks) != 21:
        raise P2BAuthorizationError("authorization check count drifted")
    if not bool(checks["passed"].astype(bool).all()):
        raise P2BAuthorizationError("authorization checks contain failures")
    if not bool(checks["blocking"].astype(bool).all()):
        raise P2BAuthorizationError("authorization blocking policy drifted")

    lineage = pd.read_csv(output / "lineage-hash-manifest.csv")
    if len(lineage) < 80:
        raise P2BAuthorizationError("lineage manifest coverage is insufficient")
    if bool(lineage["path"].astype(str).duplicated().any()):
        raise P2BAuthorizationError("lineage manifest contains duplicate paths")

    contract = load_json_object(output / "execution-contract.json")
    if contract.get("status") != "AUTHORIZED_NOT_EXECUTED":
        raise P2BAuthorizationError("execution contract status drifted")
    scope = contract.get("authorized_scope")
    if not isinstance(scope, dict):
        raise P2BAuthorizationError("execution contract scope is missing")
    if scope.get("expected_run_count") != EXPECTED_RUNS:
        raise P2BAuthorizationError("execution contract run count drifted")
    if contract.get("2024_internal_confirmation_authorized") is not False:
        raise P2BAuthorizationError("2024 was authorized prematurely")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "authorized": True,
                "expected_run_count": EXPECTED_RUNS,
                "lineage_rows": len(lineage),
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
