from __future__ import annotations

import json
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from spotbot.research.ams_v4_active_conviction_swing import (
    build_configuration_grid,
    file_sha256,
    portfolio_profiles,
)

ROOT = Path.cwd()
REPORTS = ROOT / "reports/research"
V3_REGISTRATION = REPORTS / "ams-v3-4h-dataset-registration-v1.json"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    json.loads(encoded)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected object: {path}")
    return value


def v3_diagnosis() -> dict[str, Any]:
    trials = []
    behavior_groups: dict[str, list[str]] = defaultdict(list)
    for path in sorted(REPORTS.glob("ams-v3-f01-*-trial-v1.json")):
        report = load(path)
        results = report["results"]
        folds = results["fold_results"]
        base = [fold["base_metrics"] for fold in folds]
        trades = [trade for fold in folds for trade in fold["trades"]]
        exit_reasons = Counter(str(trade["exit_reason"]) for trade in trades)
        annual_counts = {
            fold["fold"]["validation_start"][:4]: int(metrics["trade_count"])
            for fold, metrics in zip(folds, base, strict=True)
        }
        signature = json.dumps(
            {
                "candidate": sum(int(metrics["candidate_signals"]) for metrics in base),
                "accepted": sum(int(metrics["accepted_entries"]) for metrics in base),
                "return": results["aggregate_result"]["aggregate_compounded_return"],
                "trades": results["aggregate_result"]["total_trade_count"],
            },
            sort_keys=True,
        )
        behavior_groups[signature].append(str(report["configuration_id"]))
        trials.append(
            {
                "trial_id": report["trial_id"],
                "configuration_id": report["configuration_id"],
                "portfolio_profile_id": report["portfolio_profile_id"],
                "candidate_signals": sum(int(metrics["candidate_signals"]) for metrics in base),
                "accepted_entries": sum(int(metrics["accepted_entries"]) for metrics in base),
                "trade_count": len(trades),
                "trades_per_year": annual_counts,
                "rejection_reasons": {
                    key: sum(int(metrics["rejected_entries"].get(key, 0)) for metrics in base)
                    for key in sorted(
                        {key for metrics in base for key in metrics["rejected_entries"]}
                    )
                },
                "average_holding_hours": (
                    sum((trade["exit_time"] > trade["entry_time"]) for trade in trades)
                    and sum(float(metrics["average_holding_hours"]) for metrics in base) / len(base)
                ),
                "exit_reasons": dict(exit_reasons),
                "mae_r": "NOT_RECORDED_BY_V3_ARTIFACT",
                "mfe_r": "NOT_RECORDED_BY_V3_ARTIFACT",
                "exit_efficiency": "NOT_RECORDED_BY_V3_ARTIFACT",
                "post_exit_returns": "NOT_RECORDED_BY_V3_ARTIFACT",
            }
        )
    return {
        "schema_version": "ams-v4-v3-failure-diagnosis-v1",
        "status": "PASS",
        "source_protocol": "AMS-V3-F01",
        "trials": trials,
        "behaviorally_identical_named_configurations": [
            values for values in behavior_groups.values() if len(set(values)) > 1
        ],
        "c02_zero_trade_cause": (
            "The hard Fibonacci eligibility condition rejected every candidate; it was a Boolean "
            "gate, not a score contribution."
        ),
        "primary_failure": {
            "classification": "BOOLEAN_GATING_AND_STOP_DOMINANCE",
            "evidence": [
                "C02 and other hard Fibonacci configurations accepted zero entries.",
                "Active V3 reports are dominated by STOP exits.",
                "Daily profile labels produced behaviorally identical artifacts in several pairs.",
            ],
        },
        "limitations": [
            "V3 trade artifacts do not persist intratrade MAE/MFE or post-exit excursion paths.",
            "V4 records these quantities directly for future diagnosis.",
        ],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def main() -> None:
    registration = load(V3_REGISTRATION)
    datasets = registration["datasets"]
    for record in datasets.values():
        path = ROOT / str(record["path"])
        if file_sha256(path) != record["file_sha256"]:
            raise RuntimeError(f"Dataset hash mismatch: {path}")
    diagnosis = v3_diagnosis()
    diagnosis_path = REPORTS / "ams-v4-v3-failure-diagnosis-v1.json"
    write_json(diagnosis_path, diagnosis)
    configurations = list(build_configuration_grid())
    profiles = [profile.__dict__ for profile in portfolio_profiles()]
    trial_plan = [
        {
            "trial_id": f"AMS-V4-T{sequence:02d}",
            "configuration_id": configuration["configuration_id"],
            "portfolio_profile_id": profile["profile_id"],
            "trial_status": "REGISTERED_NOT_EXECUTED",
        }
        for sequence, (configuration, profile) in enumerate(
            ((configuration, profile) for configuration in configurations for profile in profiles),
            start=1,
        )
    ]
    protocol = {
        "schema_version": "ams-v4-active-conviction-protocol-v1",
        "protocol_id": "AMS-V4-ACTIVE-CONVICTION-SWING",
        "research_window": {"start": "2021-01-01", "end_exclusive": "2025-01-01"},
        "execution_rule": "SIGNAL_CLOSE_NEXT_BAR_OPEN",
        "frozen_score_threshold": 55,
        "daily_environment": {
            "STRONG_RISK_ON": 1.15,
            "RISK_ON": 1.0,
            "NEUTRAL": 0.75,
            "DEFENSIVE": 0.45,
            "CRISIS": 0.2,
        },
        "spot_constraints": {
            "spot_long_only": True,
            "short_allowed": False,
            "leverage_allowed": False,
            "borrowing_allowed": False,
            "derivatives_allowed": False,
        },
        "trial_budget": {"authorized_trials": 24, "executed_trials": 0, "remaining_trials": 24},
        "paired_fibonacci_contract": "Each adjacent pair differs only in fibonacci_mode.",
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    ledger = {
        "schema_version": "ams-v4-experiment-ledger-v1",
        "protocol_id": protocol["protocol_id"],
        "data_registration": datasets,
        "alpha_configurations": configurations,
        "portfolio_profiles": profiles,
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
        "schema_version": "ams-v4-data-readiness-v1",
        "status": "READY_FOR_AMS_V4_TRIALS",
        "dataset_hashes": {name: record["file_sha256"] for name, record in datasets.items()},
        "source_dataset_registration": str(V3_REGISTRATION.relative_to(ROOT)).replace("\\", "/"),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_action": "RUN_AMS_V4_T01",
    }
    write_json(REPORTS / "ams-v4-active-conviction-protocol-v1.json", protocol)
    write_json(REPORTS / "ams-v4-experiment-ledger-v1.json", ledger)
    write_json(REPORTS / "ams-v4-data-readiness-v1.json", readiness)
    print(
        json.dumps(
            {
                "status": "REGISTERED",
                "trial_count": len(trial_plan),
                "diagnosis": str(diagnosis_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
