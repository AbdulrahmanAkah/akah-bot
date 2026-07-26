"""Register the independent AMS V5R1 correction protocol and 24-trial matrix."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from ams_v5r1_native_common import (
    REGISTRATION,
    REPORTS,
    ROOT,
    atomic_json,
    atomic_text,
    sha256,
)

from spotbot.research.ams_v5_native_engine import configuration_grid, profiles


def main() -> None:
    audit = json.loads((REPORTS / "ams-v5r1-conformance-audit-v1.json").read_text())
    integration = json.loads(
        (REPORTS / "ams-v5r1-native-engine-integration-v1.json").read_text()
    )
    shadow = json.loads((REPORTS / "ams-v5r1-shadow-validation-v1.json").read_text())
    if not (
        audit["status"] == integration["status"] == shadow["status"] == "PASS"
        and audit["critical_requirements_not_full"] == 0
    ):
        raise RuntimeError("V5R1 conformance gate has not passed")
    registration = json.loads(REGISTRATION.read_text())
    dataset_hashes: dict[str, str] = {}
    for name, record in registration["datasets"].items():
        actual = sha256(ROOT / record["path"])
        if actual != record["file_sha256"]:
            raise RuntimeError(f"dataset hash mismatch: {name}")
        dataset_hashes[name] = actual
    configurations = []
    for configuration in configuration_grid():
        parameters = {
            "entry_family": configuration.family,
            "stop_model": configuration.stop_model,
            "fibonacci_mode": configuration.fibonacci_mode,
            "threshold_candidates": [50, 55],
            "exit_model": "RUNNER_ONLY",
            "correlation_lookback_days": 90,
            "base_transaction_cost": 0.002,
            "stress_transaction_cost": 0.004,
        }
        configurations.append(
            {
                "configuration_id": configuration.configuration_id,
                "parameters": parameters,
                "parameter_hash_sha256": hashlib.sha256(
                    json.dumps(parameters, sort_keys=True).encode()
                ).hexdigest(),
            }
        )
    profile_records = [asdict(profile) for profile in profiles()]
    trial_plan = []
    sequence = 1
    for configuration in configurations:
        for profile in profile_records:
            trial_plan.append(
                {
                    "trial_id": f"AMS-V5R1-T{sequence:02d}",
                    "configuration_id": configuration["configuration_id"],
                    "portfolio_profile_id": profile["profile_id"],
                    "trial_status": "REGISTERED_NOT_EXECUTED",
                }
            )
            sequence += 1
    protocol = {
        "schema_version": "ams-v5r1-native-protocol-v1",
        "protocol_id": "AMS-V5R1-NATIVE-ENGINE-CONFORMANCE-RERUN",
        "parent_protocol": "AMS_V5",
        "correction_type": "NATIVE_ENGINE_CONFORMANCE_RERUN",
        "legacy_results_preserved": True,
        "legacy_v5_scientific_status": "IMPLEMENTATION_INCOMPLETE",
        "native_engine_status": "VERIFIED",
        "conformance_gate": "PASS",
        "research_window": {
            "start": "2021-01-01T00:00:00Z",
            "end_exclusive": "2025-01-01T00:00:00Z",
        },
        "execution_rule": "SIGNAL_CLOSE_NEXT_BAR_OPEN",
        "threshold_selection": "TRAIN_ONLY_50_OR_55_FROZEN_OBJECTIVE",
        "trial_budget": {
            "authorized_trials": 24,
            "executed_trials": 0,
            "remaining_trials": 24,
        },
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    ledger = {
        "schema_version": "ams-v5r1-experiment-ledger-v1",
        "protocol_id": protocol["protocol_id"],
        "dataset_registration": registration["datasets"],
        "dataset_hashes": dataset_hashes,
        "alpha_configurations": configurations,
        "portfolio_profiles": profile_records,
        "trial_plan": trial_plan,
        "trial_accounting": {
            "authorized_trials": 24,
            "executed_trials": 0,
            "remaining_trials": 24,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
    }
    readiness = {
        "schema_version": "ams-v5r1-data-readiness-v1",
        "status": "REGISTERED_NOT_EXECUTED",
        "native_engine_status": "VERIFIED",
        "conformance_gate": "PASS",
        "dataset_hashes": dataset_hashes,
        "authorized_trials": 24,
        "executed_trials": 0,
        "remaining_trials": 24,
        "next_action": "RUN_AMS_V5R1_T01",
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    difference = {
        "schema_version": "ams-v5r1-legacy-native-difference-v1",
        "legacy_v5_status": "IMPLEMENTATION_INCOMPLETE",
        "native_v5r1_status": "VERIFIED_REGISTERED_NOT_EXECUTED",
        "legacy_results_modified": False,
        "corrected_native_policies": [
            "FILL_LEDGER_SOURCE_OF_TRUTH",
            "NATIVE_ADD_ON",
            "NATIVE_REENTRY",
            "CAUSAL_CORRELATION_CLUSTERS",
            "NATIVE_TRAILING_AND_CONFIRMED_EXITS",
            "TRAIN_ONLY_THRESHOLD_OBJECTIVE",
        ],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(REPORTS / "ams-v5r1-native-protocol-v1.json", protocol)
    atomic_json(REPORTS / "ams-v5r1-experiment-ledger-v1.json", ledger)
    atomic_json(REPORTS / "ams-v5r1-data-readiness-v1.json", readiness)
    atomic_json(REPORTS / "ams-v5r1-legacy-native-difference-v1.json", difference)
    atomic_text(
        REPORTS / "ams-v5r1-legacy-native-difference-v1.md",
        "# AMS V5R1 Legacy to Native Difference\n\n"
        "- V5 Legacy scientific status: IMPLEMENTATION_INCOMPLETE\n"
        "- V5R1 Native engine status: VERIFIED_REGISTERED_NOT_EXECUTED\n"
        "- Historical V5 artifacts modified: false\n"
        "- Strategic V4 dependencies: 0\n"
        "- 2025 accessed: false\n"
        "- 2026 accessed: false\n",
    )
    print("REGISTERED_NOT_EXECUTED")


if __name__ == "__main__":
    main()
