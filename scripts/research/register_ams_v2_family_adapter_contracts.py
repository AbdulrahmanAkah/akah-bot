from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spotbot.research.ams_v2_family_adapters import (
    ADAPTER_CONTRACT_VERSION,
    AmsV2FamilyId,
    assert_no_family_adapter_is_executable,
    build_family_adapter_plan,
    default_family_adapter_registry,
)
from spotbot.research.ams_v2_walk_forward_orchestrator import (
    load_json_object,
)

ROOT = Path.cwd()

EXPECTED_BRANCH = (
    "research/"
    "ams-v2-family-adapter-contracts-v1"
)

EXPECTED_HEAD = "13b499a"

EXPERIMENT_LEDGER = (
    ROOT
    / "reports/research/"
    "ams-v2-experiment-ledger-v1.json"
)

PROJECT_LEDGER = (
    ROOT
    / "reports/research/"
    "project-research-ledger-v3.json"
)

REPORT = (
    ROOT
    / "reports/research/"
    "ams-v2-family-adapter-contracts-"
    "v1-registration.json"
)

EVENT_ID = (
    "AMS_V2_FAMILY_ADAPTER_"
    "CONTRACTS_V1_REGISTERED"
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


def now() -> str:
    return (
        datetime.now(tz=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256(
        path.read_bytes()
    )

    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(
        path.relative_to(ROOT)
    ).replace("\\", "/")


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
        EXPECTED_HEAD
    ):
        raise RuntimeError(
            f"Unexpected HEAD: {source_commit}"
        )

    experiment = load_json_object(
        EXPERIMENT_LEDGER
    )

    before = dict(
        experiment["trial_accounting"]
    )

    expected = {
        "trials_executed": 0,
        "remaining_authorized_trials": 100,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    for key, value in expected.items():
        if before[key] != value:
            raise RuntimeError(
                f"Unexpected trial accounting: {key}."
            )

    assert_no_family_adapter_is_executable()

    registry = default_family_adapter_registry()

    plan = build_family_adapter_plan(
        experiment
    )

    if len(plan) != 96:
        raise RuntimeError(
            "Adapter plan must contain 96 rows."
        )

    family_counts = Counter(
        str(item["family_id"])
        for item in plan
    )

    if (
        len(family_counts) != 6
        or set(family_counts.values()) != {16}
    ):
        raise RuntimeError(
            "Family configuration counts are invalid."
        )

    after = load_json_object(
        EXPERIMENT_LEDGER
    )["trial_accounting"]

    if after != before:
        raise RuntimeError(
            "Adapter registration changed trial accounting."
        )

    registered_at = now()

    report = {
        "schema_version": (
            "ams-v2-family-adapter-contracts-"
            "v1-registration-v1"
        ),
        "adapter_contract_version": (
            ADAPTER_CONTRACT_VERSION
        ),
        "source_commit": source_commit,
        "registered_at": registered_at,
        "status": "REGISTERED",
        "counts_as_registered_trial": False,
        "registered_trials_consumed": 0,
        "adapter_registry": [
            registry[
                family_id
            ].to_dict()
            for family_id in AmsV2FamilyId
        ],
        "configuration_count": len(plan),
        "family_configuration_counts": dict(
            sorted(family_counts.items())
        ),
        "execution_barrier": {
            "all_family_adapters_nonexecutable": True,
            "registered_trial_execution_allowed": False,
            "next_family_engine": "AMS-V2-F01",
        },
        "trial_accounting": {
            "before": before,
            "after": after,
            "changed": False,
        },
        "locked_periods": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
    }

    write_json(
        REPORT,
        report,
    )

    project = load_json_object(
        PROJECT_LEDGER
    )

    updates = project.setdefault(
        "protocol_updates",
        [],
    )

    if not isinstance(updates, list):
        raise RuntimeError(
            "protocol_updates must be a list."
        )

    if any(
        isinstance(item, dict)
        and item.get("event_id") == EVENT_ID
        for item in updates
    ):
        raise RuntimeError(
            "Adapter event already exists."
        )

    updates.append(
        {
            "event_id": EVENT_ID,
            "event_type": (
                "RESEARCH_INFRASTRUCTURE_REGISTERED"
            ),
            "recorded_at": registered_at,
            "source_commit": source_commit,
            "adapter_contract_version": (
                ADAPTER_CONTRACT_VERSION
            ),
            "report_path": relative(REPORT),
            "report_sha256": sha256(REPORT),
            "registered_trials_consumed": 0,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )

    components = project.setdefault(
        "active_components",
        [],
    )

    if not isinstance(components, list):
        raise RuntimeError(
            "active_components must be a list."
        )

    if (
        ADAPTER_CONTRACT_VERSION
        not in components
    ):
        components.append(
            ADAPTER_CONTRACT_VERSION
        )

    project["current_stage"] = (
        "AMS_V2_FAMILY_ADAPTER_CONTRACTS_V1_REGISTERED"
    )

    project["next_action"] = (
        "IMPLEMENT_AMS_V2_F01_TREND_MOMENTUM_"
        "COMPOSITE_ENGINE_WITHOUT_EXECUTING_TRIALS"
    )

    project["last_updated_at"] = (
        registered_at
    )

    write_json(
        PROJECT_LEDGER,
        project,
    )

    print(
        json.dumps(
            {
                "status": "REGISTERED",
                "family_count": len(registry),
                "configuration_count": len(plan),
                "family_configuration_counts": dict(
                    sorted(family_counts.items())
                ),
                "all_adapters_executable": False,
                "next_family_engine": "AMS-V2-F01",
                "trials_executed": (
                    after["trials_executed"]
                ),
                "remaining_authorized_trials": (
                    after[
                        "remaining_authorized_trials"
                    ]
                ),
                "test_2025_accessed": False,
                "holdout_2026_accessed": False,
                "full_report": relative(REPORT),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()