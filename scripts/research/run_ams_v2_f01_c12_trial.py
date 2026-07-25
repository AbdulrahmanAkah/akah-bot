from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import traceback
from collections.abc import Mapping
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import ModuleType

import pandas as pd

from spotbot.research.ams_v2_f01_fold_harness import (
    F01FoldHarnessArtifacts,
    run_f01_fold_execution_harness,
)
from spotbot.research.ams_v2_walk_forward_orchestrator import (
    AmsV2TrialExecution,
    TrialTerminalStatus,
    apply_trial_execution_to_ledger,
    default_ams_v2_fold_definitions,
    evaluate_ams_v2_completed_trial,
    load_json_object,
    validate_ams_v2_experiment_ledger,
)

ROOT = Path.cwd()

EXPECTED_BRANCH = (
    "research/ams-v2-f01-c12-trial-v1"
)

EXPECTED_SOURCE_COMMIT = os.environ.get(
    "SIRAJ_TRIAL_SOURCE_COMMIT",
    "",
)

CONFIGURATION_ID = "AMS-V2-F01-C12"

LOADER_SCRIPT = (
    ROOT
    / "scripts/research/"
    "run_ams_v1_h01.py"
)

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
    "ams-v2-f01-c12-walk-forward-trial-v1.json"
)

PREFLIGHT_REPORT_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-f01-trade-schema-fix-v1-registration.json"
)

LOCKED_TEST_START = pd.Timestamp(
    "2025-01-01T00:00:00Z"
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


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for block in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def json_safe(value: object) -> object:
    if dataclasses.is_dataclass(value):
        return json_safe(
            dataclasses.asdict(value)
        )

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            json_safe(item)
            for item in value
        ]

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeError(
                "JSON payload contains a non-finite float."
            )

        return value

    return value


def json_bytes(
    payload: Mapping[str, object],
) -> bytes:
    safe_payload = json_safe(payload)

    return (
        json.dumps(
            safe_payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def enum_member_containing(
    enum_type: type[Enum],
    token: str,
) -> Enum:
    normalized_token = token.upper()

    matches = [
        member
        for member
        in enum_type.__members__.values()
        if (
            normalized_token
            in member.name.upper()
            or normalized_token
            in str(member.value).upper()
        )
    ]

    unique_matches = list(
        dict.fromkeys(matches)
    )

    if len(unique_matches) != 1:
        observed = {
            name: str(member.value)
            for name, member
            in enum_type.__members__.items()
        }

        raise RuntimeError(
            f"Could not uniquely resolve {token} "
            f"from {observed}."
        )

    return unique_matches[0]


def load_module_from_path(
    path: Path,
) -> ModuleType:
    module_name = (
        "_siraj_ams_v1_h01_trial_loader"
    )

    specification = (
        importlib.util.spec_from_file_location(
            module_name,
            path,
        )
    )

    if (
        specification is None
        or specification.loader is None
    ):
        raise RuntimeError(
            "Could not create data-loader specification."
        )

    module = importlib.util.module_from_spec(
        specification
    )

    sys.modules[module_name] = module

    specification.loader.exec_module(
        module
    )

    return module


def frame_time_columns(
    frame: pd.DataFrame,
) -> list[str]:
    candidates = (
        "snapshot_time",
        "open_time",
        "close_time",
        "timestamp",
        "date",
        "entry_time",
        "exit_time",
    )

    return [
        column
        for column in candidates
        if column in frame.columns
    ]


def assert_no_locked_data(
    frame: pd.DataFrame,
    *,
    frame_name: str,
) -> None:
    columns = frame_time_columns(
        frame
    )

    if not columns:
        raise RuntimeError(
            f"{frame_name} has no recognized "
            "time column."
        )

    for column in columns:
        timestamps = pd.to_datetime(
            frame[column],
            utc=True,
            errors="coerce",
        ).dropna()

        if (
            timestamps
            >= LOCKED_TEST_START
        ).any():
            raise RuntimeError(
                f"{frame_name}.{column} reaches "
                f"locked 2025 data: "
                f"{timestamps.max()}."
            )


def compact_frame_profile(
    frame: pd.DataFrame,
) -> dict[str, object]:
    output: dict[str, object] = {
        "rows": int(len(frame)),
        "columns": [
            str(column)
            for column in frame.columns
        ],
    }

    if "symbol" in frame.columns:
        output["unique_symbols"] = int(
            frame["symbol"]
            .astype(str)
            .nunique()
        )

    ranges: dict[
        str,
        dict[str, str | None],
    ] = {}

    for column in frame_time_columns(
        frame
    ):
        converted = pd.to_datetime(
            frame[column],
            utc=True,
            errors="coerce",
        ).dropna()

        ranges[column] = {
            "minimum": (
                converted.min().isoformat()
                if not converted.empty
                else None
            ),
            "maximum": (
                converted.max().isoformat()
                if not converted.empty
                else None
            ),
        }

    output["time_ranges"] = ranges

    return output


def input_manifest(
    loader_module: ModuleType,
) -> dict[str, object]:
    raw_history_directory = getattr(
        loader_module,
        "HISTORY_DIRECTORY",
        None,
    )

    raw_ranking_path = getattr(
        loader_module,
        "RANKING_PATH",
        None,
    )

    history_directory = Path(
        raw_history_directory
    )

    ranking_path = Path(
        raw_ranking_path
    )

    if not history_directory.is_absolute():
        history_directory = (
            ROOT / history_directory
        )

    if not ranking_path.is_absolute():
        ranking_path = (
            ROOT / ranking_path
        )

    history_files = sorted(
        history_directory.glob(
            "*.parquet"
        )
    )

    if not history_files:
        raise RuntimeError(
            "No history Parquet files were found."
        )

    if not ranking_path.is_file():
        raise RuntimeError(
            f"Ranking file was not found: {ranking_path}"
        )

    return {
        "history_directory": str(
            history_directory.resolve()
        ),
        "history_file_count": len(
            history_files
        ),
        "history_files": [
            {
                "path": str(
                    path.relative_to(ROOT)
                ).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in history_files
        ],
        "ranking_file": {
            "path": str(
                ranking_path.relative_to(ROOT)
            ).replace("\\", "/"),
            "bytes": (
                ranking_path.stat().st_size
            ),
            "sha256": file_sha256(
                ranking_path
            ),
        },
    }


def fold_artifact_summary(
    result: F01FoldHarnessArtifacts,
) -> dict[str, object]:
    metrics = (
        result.completed_fold_metrics
    )

    return {
        "fold_name": result.fold.name,
        "evaluation_start": (
            result.fold
            .evaluation_start
            .isoformat()
        ),
        "evaluation_end_exclusive": (
            result.fold
            .evaluation_end_exclusive
            .isoformat()
        ),
        "baseline_transaction_cost_fraction": (
            result.baseline_policy
            .transaction_cost_fraction
        ),
        "stress_transaction_cost_fraction": (
            result.stress_policy
            .transaction_cost_fraction
        ),
        "baseline_engine": dict(
            result.baseline_engine_summary
        ),
        "stress_engine": dict(
            result.stress_engine_summary
        ),
        "canonical_baseline": (
            result.baseline_canonical.to_summary()
        ),
        "canonical_stress": (
            result.stress_canonical.to_summary()
        ),
        "metrics": json_safe(metrics),
    }


def write_transactionally(
    payloads: Mapping[Path, bytes],
) -> None:
    backups: dict[
        Path,
        bytes | None,
    ] = {}

    temporary_paths: dict[
        Path,
        Path,
    ] = {}

    try:
        for path, content in payloads.items():
            backups[path] = (
                path.read_bytes()
                if path.exists()
                else None
            )

            temporary_path = path.with_name(
                path.name
                + ".tmp-"
                + os.urandom(8).hex()
            )

            temporary_path.write_bytes(
                content
            )

            temporary_paths[path] = (
                temporary_path
            )

        for path, temporary_path in (
            temporary_paths.items()
        ):
            temporary_path.replace(path)

    except BaseException:
        for path, original in backups.items():
            if original is None:
                path.unlink(
                    missing_ok=True
                )
            else:
                path.write_bytes(
                    original
                )

        raise

    finally:
        for temporary_path in (
            temporary_paths.values()
        ):
            temporary_path.unlink(
                missing_ok=True
            )


branch = git_output(
    "branch",
    "--show-current",
)

source_commit = git_output(
    "rev-parse",
    "HEAD",
)

git_status = git_output(
    "status",
    "--porcelain",
)

if branch != EXPECTED_BRANCH:
    raise RuntimeError(
        f"Unexpected branch: {branch}"
    )

if not EXPECTED_SOURCE_COMMIT:
    raise RuntimeError(
        "SIRAJ_TRIAL_SOURCE_COMMIT is required."
    )

if source_commit != EXPECTED_SOURCE_COMMIT:
    raise RuntimeError(
        "Unexpected source commit: "
        f"{source_commit}; expected "
        f"{EXPECTED_SOURCE_COMMIT}."
    )

if git_status:
    raise RuntimeError(
        "Working tree must be clean before the trial."
    )

if REPORT_PATH.exists():
    raise RuntimeError(
        "C02 trial report already exists."
    )

experiment_before = load_json_object(
    EXPERIMENT_LEDGER_PATH
)

project_before = load_json_object(
    PROJECT_LEDGER_PATH
)

validate_ams_v2_experiment_ledger(
    experiment_before
)

accounting_before = dict(
    experiment_before[
        "trial_accounting"
    ]
)

expected_accounting = {
    "trials_executed": 11,
    "remaining_authorized_trials": 89,
    "test_2025_accessed": False,
    "holdout_2026_accessed": False,
}

for key, expected_value in (
    expected_accounting.items()
):
    if (
        accounting_before[key]
        != expected_value
    ):
        raise RuntimeError(
            f"Unexpected trial accounting: "
            f"{key}={accounting_before[key]!r}."
        )

configuration = next(
    item
    for item in experiment_before[
        "alpha_configurations"
    ]
    if item["configuration_id"]
    == CONFIGURATION_ID
)

if configuration["family_id"] != "AMS-V2-F01":
    raise RuntimeError(
        "C02 is not an F01 configuration."
    )

loader_module = load_module_from_path(
    LOADER_SCRIPT
)

load_history = getattr(
    loader_module,
    "load_history",
    None,
)

load_ranking = getattr(
    loader_module,
    "load_ranking",
    None,
)

if not callable(load_history):
    raise RuntimeError(
        "H01 load_history is unavailable."
    )

if not callable(load_ranking):
    raise RuntimeError(
        "H01 load_ranking is unavailable."
    )

manifest = input_manifest(
    loader_module
)

history = load_history()
ranking = load_ranking()

if not isinstance(
    history,
    pd.DataFrame,
):
    raise RuntimeError(
        "load_history did not return a DataFrame."
    )

if not isinstance(
    ranking,
    pd.DataFrame,
):
    raise RuntimeError(
        "load_ranking did not return a DataFrame."
    )

if history.empty or ranking.empty:
    raise RuntimeError(
        "History or ranking is empty."
    )

assert_no_locked_data(
    history,
    frame_name="History",
)

assert_no_locked_data(
    ranking,
    frame_name="Ranking",
)

completed_terminal_status = (
    enum_member_containing(
        TrialTerminalStatus,
        "COMPLETED",
    )
)

failed_terminal_status = (
    enum_member_containing(
        TrialTerminalStatus,
        "FAILED",
    )
)

started_at = datetime.now(
    tz=UTC
)

fold_results: list[
    F01FoldHarnessArtifacts
] = []

fold_metrics: list[object] = []

trial_error: BaseException | None = None
trial_traceback: str | None = None

try:
    for fold in (
        default_ams_v2_fold_definitions()
    ):
        result = (
            run_f01_fold_execution_harness(
                history,
                ranking,
                configuration=configuration,
                fold=fold,
            )
        )

        fold_results.append(result)

        fold_metrics.append(
            result.completed_fold_metrics
        )

except BaseException as error:
    trial_error = error
    trial_traceback = (
        traceback.format_exc()
    )

completed_at = datetime.now(
    tz=UTC
)

if trial_error is None:
    decision = (
        evaluate_ams_v2_completed_trial(
            fold_metrics
        )
    )

    execution = AmsV2TrialExecution(
        configuration_id=CONFIGURATION_ID,
        family_id=configuration[
            "family_id"
        ],
        parameter_hash_sha256=(
            configuration[
                "parameter_hash_sha256"
            ]
        ),
        source_commit=source_commit,
        started_at=started_at,
        completed_at=completed_at,
        terminal_status=(
            completed_terminal_status
        ),
        fold_metrics=tuple(
            fold_metrics
        ),
    )

    terminal_result = "COMPLETED"
    failure_payload: (
        dict[str, object] | None
    ) = None

else:
    decision = None

    execution = AmsV2TrialExecution(
        configuration_id=CONFIGURATION_ID,
        family_id=configuration[
            "family_id"
        ],
        parameter_hash_sha256=(
            configuration[
                "parameter_hash_sha256"
            ]
        ),
        source_commit=source_commit,
        started_at=started_at,
        completed_at=completed_at,
        terminal_status=(
            failed_terminal_status
        ),
        fold_metrics=tuple(
            fold_metrics
        ),
        failure_reason=(
            f"{type(trial_error).__name__}: "
            f"{trial_error}"
        ),
    )

    terminal_result = "FAILED_CONSUMED"

    failure_payload = {
        "type": (
            type(trial_error).__name__
        ),
        "message": str(trial_error),
        "traceback": trial_traceback,
    }

experiment_after = (
    apply_trial_execution_to_ledger(
        experiment_before,
        execution,
    )
)

validate_ams_v2_experiment_ledger(
    experiment_after
)

accounting_after = dict(
    experiment_after[
        "trial_accounting"
    ]
)

if (
    accounting_after[
        "trials_executed"
    ]
    != accounting_before[
        "trials_executed"
    ]
    + 1
):
    raise RuntimeError(
        "Trial execution count did not increase by one."
    )

if (
    accounting_after[
        "remaining_authorized_trials"
    ]
    != accounting_before[
        "remaining_authorized_trials"
    ]
    - 1
):
    raise RuntimeError(
        "Remaining trial budget did not decrease by one."
    )

if accounting_after[
    "test_2025_accessed"
]:
    raise RuntimeError(
        "Trial ledger claims 2025 test access."
    )

if accounting_after[
    "holdout_2026_accessed"
]:
    raise RuntimeError(
        "Trial ledger claims 2026 holdout access."
    )

preflight_evidence: (
    dict[str, object] | None
) = None

if PREFLIGHT_REPORT_PATH.is_file():
    preflight_evidence = {
        "path": str(
            PREFLIGHT_REPORT_PATH
        ),
        "bytes": (
            PREFLIGHT_REPORT_PATH
            .stat()
            .st_size
        ),
        "sha256": file_sha256(
            PREFLIGHT_REPORT_PATH
        ),
    }

report: dict[str, object] = {
    "schema_version": (
        "ams-v2-f01-c12-walk-forward-trial-v1"
    ),
    "configuration_id": CONFIGURATION_ID,
    "family_id": configuration[
        "family_id"
    ],
    "parameter_hash_sha256": (
        configuration[
            "parameter_hash_sha256"
        ]
    ),
    "parameters": configuration[
        "parameters"
    ],
    "source_commit": source_commit,
    "branch": branch,
    "started_at": started_at,
    "completed_at": completed_at,
    "terminal_result": terminal_result,
    "counts_as_registered_trial": True,
    "registered_trials_consumed": 1,
    "input_manifest": manifest,
    "input_profiles": {
        "history": compact_frame_profile(
            history
        ),
        "ranking": compact_frame_profile(
            ranking
        ),
    },
    "preflight_evidence": (
        preflight_evidence
    ),
    "fold_results": [
        fold_artifact_summary(result)
        for result in fold_results
    ],
    "completed_fold_count": len(
        fold_results
    ),
    "trial_decision": (
        json_safe(decision)
        if decision is not None
        else None
    ),
    "failure": failure_payload,
    "trial_execution": (
        json_safe(execution)
    ),
    "trial_accounting": {
        "before": accounting_before,
        "after": accounting_after,
    },
    "locked_periods": {
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    },
    "known_limitations": [
        (
            "The research universe retains unresolved "
            "survivorship bias because complete delisted-asset "
            "history is unavailable."
        ),
        (
            "Daily bars cannot establish intraday stop ordering "
            "or exact intraday execution prices."
        ),
        (
            "Four-hour and one-hour validation remain separate "
            "promotion gates."
        ),
    ],
}

decision_value = (
    str(
        getattr(
            decision,
            "decision",
            "",
        )
    )
    if decision is not None
    else terminal_result
)

project_after = dict(
    project_before
)

updates = project_after.setdefault(
    "protocol_updates",
    [],
)

if not isinstance(updates, list):
    raise RuntimeError(
        "project protocol_updates must be a list."
    )

event_id = (
    "AMS_V2_F01_C12_"
    + terminal_result
)

if any(
    isinstance(item, dict)
    and item.get("event_id")
    == event_id
    for item in updates
):
    raise RuntimeError(
        "C02 trial event already exists."
    )

report_content = json_bytes(
    report
)

report_hash = sha256_bytes(
    report_content
)

updates.append(
    {
        "event_id": event_id,
        "event_type": (
            "REGISTERED_ALPHA_TRIAL"
        ),
        "recorded_at": (
            completed_at.isoformat()
        ),
        "configuration_id": (
            CONFIGURATION_ID
        ),
        "family_id": (
            configuration[
                "family_id"
            ]
        ),
        "source_commit": source_commit,
        "terminal_result": (
            terminal_result
        ),
        "decision": decision_value,
        "completed_fold_count": len(
            fold_results
        ),
        "registered_trials_consumed": 1,
        "report_path": (
            "reports/research/"
            "ams-v2-f01-c12-walk-forward-trial-v1.json"
        ),
        "report_sha256": report_hash,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
)

project_after["current_stage"] = (
    "AMS_V2_F01_C12_"
    + terminal_result
)

project_after["next_action"] = (
    "EXECUTE_AMS_V2_F01_C13_"
    "WALK_FORWARD_TRIAL"
)

project_after["last_updated_at"] = (
    completed_at.isoformat()
)

payloads = {
    REPORT_PATH: report_content,
    EXPERIMENT_LEDGER_PATH: (
        json_bytes(
            experiment_after
        )
    ),
    PROJECT_LEDGER_PATH: (
        json_bytes(
            project_after
        )
    ),
}

write_transactionally(
    payloads
)

persisted_experiment = load_json_object(
    EXPERIMENT_LEDGER_PATH
)

validate_ams_v2_experiment_ledger(
    persisted_experiment
)

persisted_accounting = (
    persisted_experiment[
        "trial_accounting"
    ]
)

if (
    persisted_accounting
    != accounting_after
):
    raise RuntimeError(
        "Persisted trial accounting differs "
        "from the validated result."
    )

fold_summaries = [
    {
        "fold_name": (
            result.fold.name
        ),
        "trade_count": (
            result
            .completed_fold_metrics
            .executed_trade_count
        ),
        "total_return": (
            result
            .completed_fold_metrics
            .total_return
        ),
        "maximum_drawdown": (
            result
            .completed_fold_metrics
            .maximum_drawdown
        ),
        "stress_return_0_004": (
            result
            .completed_fold_metrics
            .stress_cost_total_return_0_004
        ),
    }
    for result in fold_results
]

print(
    json.dumps(
        {
            "configuration_id": (
                CONFIGURATION_ID
            ),
            "terminal_result": (
                terminal_result
            ),
            "decision": decision_value,
            "completed_fold_count": (
                len(fold_results)
            ),
            "folds": fold_summaries,
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
            "report": str(
                REPORT_PATH
            ),
        },
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
)