"""Validate RD19-P2A engine technical dry-run outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd19_p2a_engine import (  # noqa: E402
    CANDIDATE_ID,
    DECISION,
    NEXT_STAGE,
    P2AEngineError,
    load_json_object,
    sha256,
)

REQUIRED_FILES = {
    "implementation-contract.json",
    "variant-contract-ledger.csv",
    "real-source-preflight.csv",
    "feature-integration-preflight.csv",
    "fixture-dry-run-summary.csv",
    "fixture-candidates.parquet",
    "fixture-trades.parquet",
    "technical-checks.csv",
    "rd19-p2a-technical-dry-run-report-v1.json",
    "rd19-p2a-technical-dry-run-v1.md",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def validate_manifest(output: Path) -> dict[str, Any]:
    manifest = load_json_object(output / "output-manifest.json")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise P2AEngineError("manifest files must be a list")
    observed: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise P2AEngineError("manifest row must be an object")
        name = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str):
            raise P2AEngineError("manifest row fields are invalid")
        path = output / name
        if not path.is_file():
            raise P2AEngineError(f"manifest file missing: {name}")
        if sha256(path) != digest:
            raise P2AEngineError(f"manifest hash drift: {name}")
        observed.add(name)
    if observed != REQUIRED_FILES:
        raise P2AEngineError(f"manifest file set drift: {sorted(observed ^ REQUIRED_FILES)}")

    expected = {
        "engine_implementation_executed": True,
        "synthetic_fixture_executed": True,
        "real_historical_feature_preflight_executed": True,
        "candidate_backtest_executed": False,
        "real_historical_strategy_replay_executed": False,
        "real_historical_portfolio_routing_executed": False,
        "real_historical_exit_simulation_executed": False,
        "performance_reporting_executed": False,
        "portfolio_return_calculation_executed": False,
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
        raise P2AEngineError(f"manifest semantic drift: {drift}")
    return manifest


def validate_report(output: Path) -> dict[str, Any]:
    report = load_json_object(output / "rd19-p2a-technical-dry-run-report-v1.json")
    expected = {
        "passed": True,
        "decision": DECISION,
        "selected_candidate_id": CANDIDATE_ID,
        "variant_count": 12,
        "fixture_run_count": 24,
        "engine_implementation_executed": True,
        "synthetic_fixture_executed": True,
        "real_historical_feature_preflight_executed": True,
        "candidate_backtest_executed": False,
        "real_historical_strategy_replay_executed": False,
        "real_historical_portfolio_routing_executed": False,
        "real_historical_exit_simulation_executed": False,
        "performance_reporting_executed": False,
        "portfolio_return_calculation_executed": False,
        "p2_execution_authorized": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P2AEngineError(f"report semantic drift: {drift}")
    return report


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise P2AEngineError("--offline is required")
    output = args.output_dir.resolve()
    validate_manifest(output)
    report = validate_report(output)

    variants = pd.read_csv(output / "variant-contract-ledger.csv")
    if len(variants) != 12 or variants["variant_id"].nunique() != 12:
        raise P2AEngineError("variant contract ledger drifted")
    if set(variants["entry_family"].astype(str)) != {
        "CONFIRMED_PULLBACK",
        "VOLATILITY_CONTRACTION_BREAKOUT",
    }:
        raise P2AEngineError("entry-family coverage drifted")

    fixture = pd.read_csv(output / "fixture-dry-run-summary.csv")
    if len(fixture) != 24:
        raise P2AEngineError("fixture run count drifted")
    if set(pd.to_numeric(fixture["cost_multiplier"])) != {1.0, 2.0}:
        raise P2AEngineError("fixture cost coverage drifted")
    if not bool((fixture["candidate_rows"] > 0).all()):
        raise P2AEngineError("fixture contains an empty candidate run")
    if not bool((fixture["trade_rows"] > 0).all()):
        raise P2AEngineError("fixture contains an empty trade run")
    if not bool((fixture["minimum_cash"] >= 0.0).all()):
        raise P2AEngineError("fixture contains negative cash")
    if not bool(fixture["next_bar_execution"].astype(bool).all()):
        raise P2AEngineError("fixture next-bar execution drifted")

    checks = pd.read_csv(output / "technical-checks.csv")
    if checks.empty or not bool(checks["passed"].astype(bool).all()):
        raise P2AEngineError("technical check ledger contains failures")

    features = pd.read_csv(output / "feature-integration-preflight.csv")
    if len(features) != 12:
        raise P2AEngineError("real feature preflight coverage drifted")
    maximum = pd.to_datetime(
        features["maximum_timestamp"],
        utc=True,
        errors="raise",
    ).max()
    if maximum >= pd.Timestamp("2025-01-01T00:00:00Z"):
        raise P2AEngineError("feature preflight crossed the cutoff")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "selected_candidate_id": CANDIDATE_ID,
                "variant_count": 12,
                "fixture_run_count": 24,
                "real_source_count": report["real_source_count"],
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
