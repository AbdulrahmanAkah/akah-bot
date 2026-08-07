"""Validate the RD19-P2C-R1 no-finalists discovery closure."""

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

from spotbot.research.rd19_p2c_r1_closure import (  # noqa: E402
    CANDIDATE_DISPOSITION,
    DECISION,
    EXPECTED_RUN_COUNT,
    EXPECTED_VARIANT_COUNT,
    NEXT_STAGE,
    RECOMMENDED_FOLLOWUP,
    P2CR1ClosureError,
    load_json_object,
    sha256,
)

REQUIRED_FILES = {
    "variant-disposition.csv",
    "closure-checks.csv",
    "closure-lineage.json",
    "closure-decision.json",
    "rd19-p2c-r1-closure-v1.md",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise P2CR1ClosureError("--offline is required")

    output = args.output_dir.resolve()
    report = load_json_object(output / "closure-decision.json")
    expected = {
        "passed": True,
        "decision": DECISION,
        "candidate_disposition": CANDIDATE_DISPOSITION,
        "p2c_r1_closed": True,
        "corrected_replay_authoritative": True,
        "completed_run_count": EXPECTED_RUN_COUNT,
        "variant_count": EXPECTED_VARIANT_COUNT,
        "hard_gate_pass_variant_count": 0,
        "ranked_finalist_count": 0,
        "selected_for_2024_count": 0,
        "selected_for_2024_variants": [],
        "final_advancement_eligible": False,
        "closure_backtest_executed": False,
        "closure_portfolio_routing_executed": False,
        "closure_exit_simulation_executed": False,
        "parameter_changes": 0,
        "matrix_changes": 0,
        "hard_gate_changes": 0,
        "2024_authorized": False,
        "2024_accessed": False,
        "post_2024_authorized": False,
        "post_2024_accessed": False,
        "production_authorized": False,
        "next_stage": NEXT_STAGE,
        "recommended_followup": RECOMMENDED_FOLLOWUP,
    }
    drift = {
        key: {"expected": wanted, "actual": report.get(key)}
        for key, wanted in expected.items()
        if report.get(key) != wanted
    }
    if drift:
        raise P2CR1ClosureError(f"closure decision semantic drift: {drift}")

    dispositions = pd.read_csv(output / "variant-disposition.csv")
    if len(dispositions) != EXPECTED_VARIANT_COUNT:
        raise P2CR1ClosureError("variant disposition count drifted")
    if dispositions["variant_id"].astype(str).nunique() != EXPECTED_VARIANT_COUNT:
        raise P2CR1ClosureError("variant disposition identities drifted")
    if set(dispositions["disposition"].astype(str)) != {"REJECTED_HARD_GATES"}:
        raise P2CR1ClosureError("variant disposition state drifted")
    if bool(dispositions["advancement_eligible"].astype(bool).any()):
        raise P2CR1ClosureError("a rejected variant is marked advancement eligible")

    checks = pd.read_csv(output / "closure-checks.csv")
    if len(checks) != 18:
        raise P2CR1ClosureError("closure check count drifted")
    if not bool(checks["passed"].astype(bool).all()):
        raise P2CR1ClosureError("closure checks contain a failure")
    if not bool(checks["blocking"].astype(bool).all()):
        raise P2CR1ClosureError("closure blocking policy drifted")

    lineage = load_json_object(output / "closure-lineage.json")
    files = lineage.get("authoritative_files")
    if not isinstance(files, list) or len(files) != 10:
        raise P2CR1ClosureError("closure lineage coverage drifted")

    manifest = load_json_object(output / "output-manifest.json")
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list):
        raise P2CR1ClosureError("closure manifest files must be a list")
    observed: set[str] = set()
    for raw in manifest_files:
        if not isinstance(raw, dict):
            raise P2CR1ClosureError("closure manifest row is invalid")
        name = str(raw["path"])
        path = output / name
        if not path.is_file():
            raise P2CR1ClosureError(f"closure manifest file missing: {name}")
        if sha256(path) != str(raw["sha256"]):
            raise P2CR1ClosureError(f"closure manifest hash drift: {name}")
        observed.add(name)
    if observed != REQUIRED_FILES:
        raise P2CR1ClosureError(
            f"closure manifest file set drift: {sorted(observed ^ REQUIRED_FILES)}"
        )

    print(
        json.dumps(
            {
                "status": "PASS",
                "decision": DECISION,
                "candidate_disposition": CANDIDATE_DISPOSITION,
                "p2c_r1_closed": True,
                "final_advancement_eligible": False,
                "variant_count": EXPECTED_VARIANT_COUNT,
                "completed_run_count": EXPECTED_RUN_COUNT,
                "next_stage": NEXT_STAGE,
                "recommended_followup": RECOMMENDED_FOLLOWUP,
                "output_dir": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
