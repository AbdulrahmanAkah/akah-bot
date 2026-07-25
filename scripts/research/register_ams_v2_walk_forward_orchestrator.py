from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spotbot.research.ams_v2_walk_forward_orchestrator import (
    ORCHESTRATOR_VERSION,
    AmsV2CompletedFoldMetrics,
    AmsV2TrialExecution,
    TrialTerminalStatus,
    apply_trial_execution_to_ledger,
    build_pending_alpha_execution_plan,
    default_ams_v2_fold_definitions,
    load_json_object,
    validate_ams_v2_experiment_ledger,
)

ROOT = Path.cwd()

EXPECTED_BRANCH = (
    "research/"
    "ams-v2-walk-forward-orchestrator-v1"
)

EXPECTED_HEAD_PREFIX = "2858b2e"

EXPERIMENT_LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-experiment-ledger-v1.json"
)

PROJECT_LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "project-research-ledger-v3.json"
)

REPORT_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-walk-forward-orchestrator-"
    "v1-registration.json"
)

EVENT_ID = (
    "AMS_V2_WALK_FORWARD_"
    "ORCHESTRATOR_V1_REGISTERED"
)


def git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    return result.stdout.strip()


def utc_now() -> str:
    return (
        datetime.now(tz=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def relative(path: Path) -> str:
    return str(
        path.relative_to(ROOT)
    ).replace("\\", "/")


def passing_metrics(
) -> tuple[
    AmsV2CompletedFoldMetrics,
    ...,
]:
    return tuple(
        AmsV2CompletedFoldMetrics(
            fold_name=fold.name,
            evaluation_start=fold.evaluation_start,
            evaluation_end_exclusive=(
                fold.evaluation_end_exclusive
            ),
            executed_trade_count=12,
            base_price_gross_pnl=0.30,
            net_pnl=0.20,
            total_return=0.15,
            maximum_drawdown=0.20,
            gross_profit=0.40,
            gross_loss_abs=0.15,
            total_r_multiple=2.40,
            stress_cost_total_return_0_004=0.08,
        )
        for fold
        in default_ams_v2_fold_definitions()
    )


def main() -> None:
    branch = git_output(
        "branch",
        "--show-current",
    )

    source_commit = git_output(
        "rev-parse",
        "HEAD",
    )

    if branch != EXPECTED_BRANCH:
        raise RuntimeError(
            f"Unexpected branch: {branch}"
        )

    if not source_commit.startswith(
        EXPECTED_HEAD_PREFIX
    ):
        raise RuntimeError(
            f"Unexpected source commit: {source_commit}"
        )

    experiment = load_json_object(
        EXPERIMENT_LEDGER_PATH
    )

    validate_ams_v2_experiment_ledger(
        experiment
    )

    accounting_before = dict(
        experiment["trial_accounting"]
    )

    plan = build_pending_alpha_execution_plan(
        experiment
    )

    if len(plan) != 96:
        raise RuntimeError(
            "Expected 96 pending configurations."
        )

    timestamp = datetime(
        2026,
        7,
        25,
        12,
        0,
        tzinfo=UTC,
    )

    first = plan[0]
    second = plan[1]

    completed_probe = (
        apply_trial_execution_to_ledger(
            experiment,
            AmsV2TrialExecution(
                configuration_id=first[
                    "configuration_id"
                ],
                family_id=first["family_id"],
                parameter_hash_sha256=first[
                    "parameter_hash_sha256"
                ],
                source_commit=source_commit,
                started_at=timestamp,
                completed_at=timestamp,
                terminal_status=(
                    TrialTerminalStatus.COMPLETED
                ),
                fold_metrics=passing_metrics(),
            ),
        )
    )

    failed_probe = (
        apply_trial_execution_to_ledger(
            experiment,
            AmsV2TrialExecution(
                configuration_id=second[
                    "configuration_id"
                ],
                family_id=second["family_id"],
                parameter_hash_sha256=second[
                    "parameter_hash_sha256"
                ],
                source_commit=source_commit,
                started_at=timestamp,
                completed_at=timestamp,
                terminal_status=(
                    TrialTerminalStatus.FAILED
                ),
                failure_reason=(
                    "IN_MEMORY_REGISTRATION_PROBE"
                ),
            ),
        )
    )

    accounting_after = load_json_object(
        EXPERIMENT_LEDGER_PATH
    )["trial_accounting"]

    if accounting_after != accounting_before:
        raise RuntimeError(
            "Experiment ledger changed."
        )

    project = load_json_object(
        PROJECT_LEDGER_PATH
    )

    if (
        project.get("test_accessed")
        or project.get("holdout_accessed")
    ):
        raise RuntimeError(
            "Project ledger shows locked-period access."
        )

    registered_at = utc_now()

    report = {
        "schema_version": (
            "ams-v2-walk-forward-orchestrator-"
            "v1-registration-v1"
        ),
        "protocol_id": experiment["protocol_id"],
        "orchestrator_version": (
            ORCHESTRATOR_VERSION
        ),
        "source_commit": source_commit,
        "registered_at": registered_at,
        "status": "REGISTERED",
        "counts_as_registered_trial": False,
        "pending_alpha_configurations": len(plan),
        "folds": [
            value.to_dict()
            for value
            in default_ams_v2_fold_definitions()
        ],
        "decision_contract": {
            "successful_baseline_decision": (
                "PROCEED_TO_FROZEN_TEST"
            ),
            "maximum_fold_drawdown": 0.45,
            "minimum_passing_folds": 2,
            "latest_fold_must_pass": True,
            "minimum_total_trades": 30,
            "aggregate_profit_factor": (
                "STRICTLY_ABOVE_1_1"
            ),
            "aggregate_0_004_cost_return": (
                "STRICTLY_POSITIVE"
            ),
            "latest_fold_0_004_cost_return": (
                "STRICTLY_POSITIVE"
            ),
        },
        "in_memory_validation": {
            "completed_probe_status": (
                completed_probe[
                    "alpha_configurations"
                ][0]["trial_status"]
            ),
            "failed_probe_status": (
                failed_probe[
                    "alpha_configurations"
                ][1]["trial_status"]
            ),
            "original_ledger_unchanged": True,
        },
        "trial_accounting": {
            "before": accounting_before,
            "after": accounting_after,
            "changed": False,
        },
        "locked_periods": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
        "limitations": [
            "No Alpha strategy was executed.",
            (
                "Family adapters and metric extraction "
                "remain to be implemented."
            ),
            (
                "PBO and Deflated Sharpe require the "
                "completed trial matrix."
            ),
            (
                "Historical delisting coverage remains "
                "incomplete."
            ),
        ],
    }

    write_json(
        REPORT_PATH,
        report,
    )

    updates = project.setdefault(
        "protocol_updates",
        [],
    )

    if any(
        value.get("event_id") == EVENT_ID
        for value in updates
    ):
        raise RuntimeError(
            "Registration event already exists."
        )

    updates.append(
        {
            "event_id": EVENT_ID,
            "event_type": (
                "RESEARCH_INFRASTRUCTURE_REGISTERED"
            ),
            "recorded_at": registered_at,
            "source_commit": source_commit,
            "orchestrator_version": (
                ORCHESTRATOR_VERSION
            ),
            "report_path": relative(
                REPORT_PATH
            ),
            "report_sha256": file_sha256(
                REPORT_PATH
            ),
            "registered_trials_consumed": 0,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )

    active_components = project.setdefault(
        "active_components",
        [],
    )

    if (
        ORCHESTRATOR_VERSION
        not in active_components
    ):
        active_components.append(
            ORCHESTRATOR_VERSION
        )

    project["current_stage"] = (
        "AMS_V2_WALK_FORWARD_ORCHESTRATOR_V1_REGISTERED"
    )

    project["next_action"] = (
        "IMPLEMENT_AMS_V2_FAMILY_ADAPTERS_AND_"
        "STANDARDIZED_FOLD_METRIC_EXTRACTION_"
        "WITHOUT_EXECUTING_REGISTERED_TRIALS"
    )

    project["last_updated_at"] = (
        registered_at
    )

    write_json(
        PROJECT_LEDGER_PATH,
        project,
    )

    print(
        json.dumps(
            {
                "status": "REGISTERED",
                "pending_alpha_configurations": (
                    len(plan)
                ),
                "completed_probe_status": (
                    completed_probe[
                        "alpha_configurations"
                    ][0]["trial_status"]
                ),
                "failed_probe_status": (
                    failed_probe[
                        "alpha_configurations"
                    ][1]["trial_status"]
                ),
                "trials_executed": (
                    accounting_after[
                        "trials_executed"
                    ]
                ),
                "remaining_authorized_trials": (
                    accounting_after[
                        "remaining_authorized_trials"
                    ]
                ),
                "test_2025_accessed": False,
                "holdout_2026_accessed": False,
                "report": relative(
                    REPORT_PATH
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()