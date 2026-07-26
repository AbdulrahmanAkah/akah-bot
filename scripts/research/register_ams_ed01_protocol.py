"""Register the finite, non-development AMS ED01 diagnostic study."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ams_v5r1_native_common import atomic_json, sha256

ROOT = Path.cwd()
REPORTS = ROOT / "reports" / "research"
OUTSIDE = Path(r"C:\SIRAJ\Reports")


def main() -> None:
    registration = json.loads(
        (REPORTS / "ams-v3-4h-dataset-registration-v1.json").read_text(encoding="utf-8")
    )
    variants = (
        ("ED01-R01", "CONTROL", True, True),
        ("ED01-R02", "NO_REENTRY", False, True),
        ("ED01-R03", "NO_ADDON", True, False),
        ("ED01-R04", "NO_REENTRY_NO_ADDON", False, False),
    )
    protocol: dict[str, Any] = {
        "schema_version": "ams-ed01-protocol-v1",
        "protocol_id": "AMS-ED01-V4-T12-NATIVE-EDGE-VERIFICATION",
        "study_type": "DIAGNOSTIC",
        "strategy_development": False,
        "new_alpha_parameters": False,
        "historical_reference": "AMS-V4-T12 / AMS-V4-A06 / AMS-V4-PORTFOLIO-P02",
        "native_execution": "ams_v5_native_engine.simulate_native_fold",
        "alpha_frozen": {
            "family": "HYBRID",
            "exit": "RUNNER_ONLY",
            "fibonacci": "SOFT_FIBONACCI_SCORE",
            "threshold": 55,
        },
        "cost_modes": {"BASE": 0.002, "STRESS": 0.004, "ZERO_COST": 0.0},
        "research_boundary": {
            "bar_open_time": "< 2025-01-01T00:00:00Z",
            "bar_close_time": "<= 2025-01-01T00:00:00Z",
        },
        "variants": [
            {"variant_id": identity, "name": name, "allow_reentry": reentry, "allow_add_on": addon}
            for identity, name, reentry, addon in variants
        ],
        "authorized_diagnostic_trials": 4,
        "executed_diagnostic_trials": 0,
        "remaining_diagnostic_trials": 4,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    ledger = {
        "schema_version": "ams-ed01-experiment-ledger-v1",
        "protocol_id": protocol["protocol_id"],
        "trial_accounting": {
            "authorized_diagnostic_trials": 4,
            "executed_diagnostic_trials": 0,
            "remaining_diagnostic_trials": 4,
        },
        "data_registration": {
            name: registration["datasets"][name] for name in ("four_hour", "availability")
        },
        "trial_plan": [
            {
                "variant_id": identity,
                "name": name,
                "allow_reentry": reentry,
                "allow_add_on": addon,
                "status": "REGISTERED_NOT_EXECUTED",
            }
            for identity, name, reentry, addon in variants
        ],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    readiness = {
        "schema_version": "ams-ed01-data-readiness-v1",
        "status": "REGISTERED_NOT_EXECUTED",
        "dataset_hashes": {
            name: value["file_sha256"] for name, value in ledger["data_registration"].items()
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    for name, value in (
        ("ams-ed01-protocol-v1.json", protocol),
        ("ams-ed01-experiment-ledger-v1.json", ledger),
        ("ams-ed01-data-readiness-v1.json", readiness),
    ):
        path = REPORTS / name
        atomic_json(path, value)
        if sha256(path) != sha256(path):
            raise RuntimeError(f"hash verification failed: {path}")
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPORTS / "ams-ed01-protocol-v1.json", OUTSIDE / "ams-ed01-protocol-v1.json")
    print("REGISTERED_NOT_EXECUTED")


if __name__ == "__main__":
    main()
