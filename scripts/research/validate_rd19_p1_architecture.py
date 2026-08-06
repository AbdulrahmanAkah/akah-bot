"""Validate RD19-P1 architecture outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.rd19_p1_architecture import (
    CANDIDATE_ID,
    DECISION,
    NEXT_STAGE,
    P1ArchitectureError,
    load_json_object,
    sha256,
)

REQUIRED_FILES = {
    "evidence-to-design-traceability.csv",
    "signal-pipeline.csv",
    "portfolio-state-machine.csv",
    "discovery-dimensions.csv",
    "prohibited-designs.csv",
    "rd19-p1-architecture-specification-v1.json",
    "rd19-p1-architecture-report-v1.json",
    "rd19-p1-architecture-publication-v1.md",
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
        raise P1ArchitectureError("manifest files must be a list")
    observed: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise P1ArchitectureError("manifest row must be an object")
        name = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str):
            raise P1ArchitectureError("manifest row fields are invalid")
        path = output / name
        if not path.is_file():
            raise P1ArchitectureError(f"manifest file missing: {name}")
        if sha256(path) != digest:
            raise P1ArchitectureError(f"manifest hash drift: {name}")
        observed.add(name)
    if observed != REQUIRED_FILES:
        raise P1ArchitectureError(f"manifest file set drift: {sorted(observed ^ REQUIRED_FILES)}")

    expected_flags = {
        "architecture_specification_executed": True,
        "candidate_backtest_executed": False,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "thresholds_selected": False,
        "parameters_frozen": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
    for key, expected in expected_flags.items():
        if manifest.get(key) != expected:
            raise P1ArchitectureError(f"manifest flag drift: {key}")
    return manifest


def validate_specification(output: Path) -> dict[str, Any]:
    spec = load_json_object(output / "rd19-p1-architecture-specification-v1.json")
    if spec.get("candidate_id") != CANDIDATE_ID:
        raise P1ArchitectureError("candidate ID drifted")
    if spec.get("architecture_status") != "SPECIFIED_NOT_TESTED":
        raise P1ArchitectureError("architecture status drifted")
    constraints = cast(
        dict[str, Any],
        spec.get("research_constraints"),
    )
    expected_constraints = {
        "spot_only": True,
        "long_only": True,
        "cash_only": True,
        "leverage": False,
        "margin": False,
        "derivatives": False,
        "shorting": False,
        "post_2024_access": False,
        "production_authorized": False,
    }
    drift = {
        key: {"expected": wanted, "actual": constraints.get(key)}
        for key, wanted in expected_constraints.items()
        if constraints.get(key) != wanted
    }
    if drift:
        raise P1ArchitectureError(f"research constraint drift: {drift}")

    sleeve = cast(dict[str, Any], spec["single_sleeve_rule"])
    if sleeve.get("secondary_sleeves_allowed_in_p2") is not False:
        raise P1ArchitectureError("secondary sleeve unexpectedly allowed")
    if sleeve.get("compression_engine_carried_forward") is not False:
        raise P1ArchitectureError("compression engine was carried forward")

    discovery = cast(dict[str, Any], spec["discovery_contract"])
    if discovery.get("maximum_candidate_variants") != 12:
        raise P1ArchitectureError("discovery budget drifted")
    if discovery.get("variant_matrix_frozen_before_first_p2_run") is not True:
        raise P1ArchitectureError("variant matrix freeze is absent")
    if discovery.get("post_2024_access") is not False:
        raise P1ArchitectureError("P2 post-2024 access is enabled")

    authorization = cast(dict[str, Any], spec["stage_authorization"])
    if authorization.get("p2_execution_authorized_now") is not False:
        raise P1ArchitectureError("P2 execution was authorized too early")
    return spec


def main() -> int:
    args = parse_args()
    if not args.offline:
        raise P1ArchitectureError("--offline is required")
    output = args.output_dir.resolve()
    validate_manifest(output)
    validate_specification(output)

    report = load_json_object(output / "rd19-p1-architecture-report-v1.json")
    expected = {
        "passed": True,
        "decision": DECISION,
        "selected_candidate_id": CANDIDATE_ID,
        "architecture_status": "SPECIFIED_NOT_TESTED",
        "single_sleeve": True,
        "compression_engine_carried_forward": False,
        "maximum_p2_candidate_variants": 12,
        "p2_protocol_and_matrix_freeze_authorized": True,
        "p2_execution_authorized_now": False,
        "thresholds_selected": False,
        "parameters_frozen": False,
        "candidate_backtest_executed": False,
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
        raise P1ArchitectureError(f"report semantic drift: {drift}")

    pipeline = pd.read_csv(output / "signal-pipeline.csv")
    if pipeline["order"].tolist() != list(range(1, 10)):
        raise P1ArchitectureError("signal pipeline order drifted")
    states = pd.read_csv(output / "portfolio-state-machine.csv")
    required_states = {
        "OFF",
        "OBSERVE",
        "CANDIDATE",
        "QUEUED",
        "OPEN",
        "PROTECTED",
        "TRAILING",
        "EXIT_PENDING",
        "CLOSED",
    }
    if set(states["state"].astype(str)) != required_states:
        raise P1ArchitectureError("portfolio state set drifted")

    dimensions = pd.read_csv(output / "discovery-dimensions.csv")
    if len(dimensions) != 6:
        raise P1ArchitectureError("six discovery dimensions required")
    if not bool((dimensions["status"] == "UNSELECTED").all()):
        raise P1ArchitectureError("P1 selected a discovery dimension")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "selected_candidate_id": CANDIDATE_ID,
                "architecture_status": "SPECIFIED_NOT_TESTED",
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
