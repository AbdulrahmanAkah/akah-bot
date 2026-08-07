"""Validate the frozen RD19-P2 discovery protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.rd19_p2_discovery_freeze import (
    CANDIDATE_ID,
    DECISION,
    FACTOR_ORDER,
    NEXT_STAGE,
    VARIANT_COUNT,
    P2FreezeError,
    load_json_object,
    sha256,
)

REQUIRED_FILES = {
    "parameter-levels.csv",
    "variant-matrix.csv",
    "data-partitions.csv",
    "selection-gates.csv",
    "finalist-ranking.csv",
    "internal-confirmation-gates.csv",
    "execution-order.csv",
    "rd19-p2-discovery-protocol-v1.json",
    "rd19-p2-discovery-freeze-report-v1.json",
    "rd19-p2-discovery-freeze-v1.md",
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
        raise P2FreezeError("manifest files must be a list")
    observed: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise P2FreezeError("manifest row must be an object")
        name = raw.get("path")
        digest = raw.get("sha256")
        if not isinstance(name, str) or not isinstance(digest, str):
            raise P2FreezeError("manifest row fields are invalid")
        path = output / name
        if not path.is_file():
            raise P2FreezeError(f"manifest file missing: {name}")
        if sha256(path) != digest:
            raise P2FreezeError(f"manifest hash drift: {name}")
        observed.add(name)
    if observed != REQUIRED_FILES:
        raise P2FreezeError(f"manifest file set drift: {sorted(observed ^ REQUIRED_FILES)}")
    expected_flags = {
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "candidate_backtest_executed": False,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "post_2024_accessed": False,
        "network_requests": 0,
        "production_authorized": False,
    }
    for key, expected in expected_flags.items():
        if manifest.get(key) != expected:
            raise P2FreezeError(f"manifest flag drift: {key}")
    return manifest


def validate_matrix(output: Path) -> None:
    matrix = pd.read_csv(output / "variant-matrix.csv")
    if len(matrix) != VARIANT_COUNT:
        raise P2FreezeError("variant count drifted")
    if matrix["variant_id"].nunique() != VARIANT_COUNT:
        raise P2FreezeError("variant IDs are not unique")
    sign_columns = [f"{factor}_SIGN" for factor in FACTOR_ORDER]
    signs = matrix[sign_columns].astype(int)
    if not bool(signs.isin([-1, 1]).all().all()):
        raise P2FreezeError("matrix contains non-binary signs")
    if not bool((signs.sum(axis=0) == 0).all()):
        raise P2FreezeError("factor levels are not balanced")
    gram = signs.T.dot(signs)
    for i, left in enumerate(sign_columns):
        for j, right in enumerate(sign_columns):
            expected = VARIANT_COUNT if i == j else 0
            if int(gram.loc[left, right]) != expected:
                raise P2FreezeError(f"matrix orthogonality drift: {left}/{right}")


def validate_protocol(output: Path) -> dict[str, Any]:
    value = load_json_object(output / "rd19-p2-discovery-protocol-v1.json")
    expected = {
        "decision": DECISION,
        "candidate_id": CANDIDATE_ID,
        "design_type": "PLACKETT_BURMAN_12_RUN_MAIN_EFFECT_SCREEN",
        "factor_count": 6,
        "variant_count": 12,
        "maximum_finalists": 2,
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "p2_execution_authorized_now": False,
        "implementation_and_dry_run_authorized": True,
        "post_2024_holdout_status": "SEALED",
        "candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
    }
    drift = {
        key: {"expected": wanted, "actual": value.get(key)}
        for key, wanted in expected.items()
        if value.get(key) != wanted
    }
    if drift:
        raise P2FreezeError(f"protocol semantic drift: {drift}")
    return value


def main() -> int:
    args = parse_args()
    if not args.offline:
        raise P2FreezeError("--offline is required")
    output = args.output_dir.resolve()
    validate_manifest(output)
    validate_matrix(output)
    validate_protocol(output)

    partitions = pd.read_csv(output / "data-partitions.csv")
    post = partitions.loc[partitions["partition_id"] == "EXTERNAL_HOLDOUT_POST_2024"]
    if len(post) != 1 or int(post.iloc[0]["variants_allowed"]) != 0:
        raise P2FreezeError("post-2024 holdout was not sealed")

    execution = pd.read_csv(output / "execution-order.csv")
    expected_runs = 12 * 3 * 3 * 2
    if len(execution) != expected_runs:
        raise P2FreezeError(f"execution-order row count drift: {len(execution)}")

    report = load_json_object(output / "rd19-p2-discovery-freeze-report-v1.json")
    expected_report = {
        "passed": True,
        "decision": DECISION,
        "selected_candidate_id": CANDIDATE_ID,
        "variant_count": 12,
        "maximum_finalists": 2,
        "matrix_frozen": True,
        "parameters_frozen_for_p2": True,
        "p2_execution_authorized_now": False,
        "implementation_and_dry_run_authorized": True,
        "candidate_backtest_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected_report.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P2FreezeError(f"report semantic drift: {drift}")

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "selected_candidate_id": CANDIDATE_ID,
                "variant_count": 12,
                "matrix_frozen": True,
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
