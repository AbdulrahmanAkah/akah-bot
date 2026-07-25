from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.ams_v2_regime_features import (
    build_ams_v2_regime_feature_frame,
    default_ams_v2_regime_feature_policy,
)
from spotbot.research.ams_v2_regime_router import (
    REGIME_ENGINE_MAP,
    ROUTER_VERSION,
    RegimeLabel,
    build_ams_v2_regime_routing_frame,
    default_ams_v2_regime_router_policy,
)

ROOT = Path.cwd()

EXPECTED_BRANCH = (
    "research/"
    "ams-v2-regime-router-v1-profile"
)

HISTORY_DIRECTORY = (
    ROOT
    / "data/research/"
    "multi_asset_daily/"
    "kucoin_direct_v3"
)

UNIVERSE_DIRECTORY = (
    ROOT
    / "data/research/"
    "universe_snapshots/"
    "bootstrap_v1"
)

OUTPUT_DIRECTORY = (
    ROOT
    / "data/research/"
    "ams_v2/"
    "regime_router_v1"
)

FEATURE_PATH = (
    OUTPUT_DIRECTORY
    / "ams-v2-regime-features-v1.parquet"
)

ROUTING_PATH = (
    OUTPUT_DIRECTORY
    / "ams-v2-regime-routing-v1.parquet"
)

REPORT_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-regime-router-v1-profile.json"
)

PROJECT_LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "project-research-ledger-v3.json"
)

EXPERIMENT_LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-experiment-ledger-v1.json"
)

EVENT_ID = (
    "AMS_V2_REGIME_ROUTER_V1_PROFILED"
)


def git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    return completed.stdout.strip()


def utc_now() -> str:
    return (
        datetime.now(tz=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)

    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Expected JSON object: {path}"
        )

    return payload


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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


def file_set_sha256(
    paths: list[Path],
) -> str:
    digest = hashlib.sha256()

    for path in sorted(
        paths,
        key=lambda item: str(item),
    ):
        relative_path = str(
            path.relative_to(ROOT)
        ).replace("\\", "/")

        digest.update(
            relative_path.encode("utf-8")
        )

        digest.update(
            b"\0"
        )

        digest.update(
            file_sha256(path).encode(
                "ascii"
            )
        )

        digest.update(
            b"\n"
        )

    return digest.hexdigest()


def relative(path: Path) -> str:
    return str(
        path.relative_to(ROOT)
    ).replace("\\", "/")


def longest_runs(
    values: list[str],
) -> dict[str, int]:
    longest: dict[str, int] = {}

    current_label: str | None = None
    current_length = 0

    for label in values:
        if label == current_label:
            current_length += 1
        else:
            if current_label is not None:
                longest[current_label] = max(
                    longest.get(
                        current_label,
                        0,
                    ),
                    current_length,
                )

            current_label = label
            current_length = 1

    if current_label is not None:
        longest[current_label] = max(
            longest.get(
                current_label,
                0,
            ),
            current_length,
        )

    return dict(
        sorted(
            longest.items()
        )
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

    if REPORT_PATH.exists():
        raise RuntimeError(
            "Regime profile report already exists."
        )

    if OUTPUT_DIRECTORY.exists():
        raise RuntimeError(
            "Regime profile output directory exists."
        )

    history_paths = sorted(
        HISTORY_DIRECTORY.glob(
            "*.parquet"
        )
    )

    universe_paths = sorted(
        UNIVERSE_DIRECTORY.glob(
            "*.parquet"
        )
    )

    if len(history_paths) != 40:
        raise RuntimeError(
            "Expected exactly 40 daily history files; "
            f"observed {len(history_paths)}."
        )

    if len(universe_paths) != 1:
        raise RuntimeError(
            "Expected exactly one universe snapshot file; "
            f"observed {len(universe_paths)}."
        )

    experiment_ledger = load_json(
        EXPERIMENT_LEDGER_PATH
    )

    accounting_before = dict(
        experiment_ledger[
            "trial_accounting"
        ]
    )

    expected_accounting = {
        "alpha_configurations_registered": 96,
        "portfolio_variants_registered": 4,
        "total_unique_variants_registered": 100,
        "trials_executed": 0,
        "trials_invalidated": 0,
        "remaining_authorized_trials": 100,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    if accounting_before != expected_accounting:
        raise RuntimeError(
            "Experiment accounting is not pristine."
        )

    print(
        "[1/6] Loading research-only daily inputs..."
    )

    history = pd.concat(
        [
            pd.read_parquet(path)
            for path in history_paths
        ],
        ignore_index=True,
    )

    universe = pd.read_parquet(
        universe_paths[0]
    )

    print(
        f"history rows={len(history):,}, "
        f"universe rows={len(universe):,}"
    )

    print(
        "[2/6] Building causal regime features..."
    )

    feature_policy = (
        default_ams_v2_regime_feature_policy()
    )

    features = (
        build_ams_v2_regime_feature_frame(
            history,
            universe,
            policy=feature_policy,
        )
    )

    print(
        "[3/6] Applying frozen regime router V1..."
    )

    router_policy = (
        default_ams_v2_regime_router_policy()
    )

    routing = (
        build_ams_v2_regime_routing_frame(
            features,
            policy=router_policy,
        )
    )

    complete_mask = routing[
        "router_complete"
    ].astype(bool)

    complete = routing.loc[
        complete_mask
    ].copy()

    incomplete = routing.loc[
        ~complete_mask
    ].copy()

    if complete.empty:
        raise RuntimeError(
            "Router produced no complete observations."
        )

    locked_start = pd.Timestamp(
        "2025-01-01",
        tz="UTC",
    )

    snapshot_time = pd.to_datetime(
        routing["snapshot_time"],
        utc=True,
        errors="raise",
    )

    feature_cutoff = pd.to_datetime(
        routing[
            "feature_information_cutoff"
        ],
        utc=True,
        errors="raise",
    )

    no_locked_dates = bool(
        (
            snapshot_time
            < locked_start
        ).all()
    )

    causal_cutoff = bool(
        (
            feature_cutoff
            < snapshot_time
        ).all()
    )

    incomplete_routes_to_cash = bool(
        incomplete.empty
        or (
            incomplete["routing_action"]
            == "CASH"
        ).all()
    )

    bear = complete.loc[
        complete["regime"]
        == RegimeLabel.BEAR_TREND.value
    ]

    bear_routes_to_cash = bool(
        bear.empty
        or (
            (
                bear["routing_action"]
                == "CASH"
            ).all()
            and (
                pd.to_numeric(
                    bear[
                        "regime_risk_multiplier"
                    ],
                    errors="raise",
                )
                == 0.0
            ).all()
            and (
                bear[
                    "active_engine_ids"
                ]
                == ""
            ).all()
        )
    )

    valid_engine_ids = {
        engine_id
        for engine_ids
        in REGIME_ENGINE_MAP.values()
        for engine_id in engine_ids
    }

    observed_engine_ids: set[str] = set()

    for value in complete[
        "active_engine_ids"
    ].astype(str):
        observed_engine_ids.update(
            engine_id
            for engine_id in value.split("|")
            if engine_id
        )

    known_engines_only = (
        observed_engine_ids
        .issubset(
            valid_engine_ids
        )
    )

    technical_validation = {
        "feature_rows_nonempty": (
            not features.empty
        ),
        "routing_rows_nonempty": (
            not routing.empty
        ),
        "feature_and_routing_row_counts_match": (
            len(features)
            == len(routing)
        ),
        "complete_observations_exist": (
            not complete.empty
        ),
        "no_locked_2025_or_later_dates": (
            no_locked_dates
        ),
        "feature_cutoff_precedes_snapshot": (
            causal_cutoff
        ),
        "incomplete_rows_route_to_cash": (
            incomplete_routes_to_cash
        ),
        "bear_regime_routes_to_zero_risk_cash": (
            bear_routes_to_cash
        ),
        "only_registered_engine_ids_enabled": (
            known_engines_only
        ),
        "test_2025_not_accessed": (
            not accounting_before[
                "test_2025_accessed"
            ]
        ),
        "holdout_2026_not_accessed": (
            not accounting_before[
                "holdout_2026_accessed"
            ]
        ),
        "experiment_count_unchanged": (
            accounting_before[
                "trials_executed"
            ]
            == 0
        ),
    }

    if not all(
        technical_validation.values()
    ):
        failed = [
            key
            for key, passed
            in technical_validation.items()
            if not passed
        ]

        raise RuntimeError(
            "Regime profile technical checks failed: "
            f"{failed}"
        )

    print(
        "[4/6] Computing empirical routing profile..."
    )

    regime_values = complete[
        "regime"
    ].astype(str)

    regime_counts = {
        str(key): int(value)
        for key, value
        in regime_values
        .value_counts()
        .sort_index()
        .items()
    }

    complete_count = len(
        complete
    )

    regime_fractions = {
        key: (
            value
            / complete_count
        )
        for key, value in regime_counts.items()
    }

    action_counts = {
        str(key): int(value)
        for key, value
        in routing[
            "routing_action"
        ]
        .astype(str)
        .value_counts()
        .sort_index()
        .items()
    }

    matched_rule_counts = {
        str(key): int(value)
        for key, value
        in routing[
            "matched_rule"
        ]
        .astype(str)
        .value_counts()
        .sort_index()
        .items()
    }

    engine_activation_counts: Counter[
        str
    ] = Counter()

    for value in complete[
        "active_engine_ids"
    ].astype(str):
        for engine_id in value.split("|"):
            if engine_id:
                engine_activation_counts[
                    engine_id
                ] += 1

    complete_labels = (
        regime_values.tolist()
    )

    transition_count = sum(
        current != previous
        for previous, current in zip(
            complete_labels,
            complete_labels[1:],
            strict=False,
        )
    )

    concentration = max(
        regime_fractions.values()
    )

    all_labels = (
        routing["regime"]
        .astype("string")
        .fillna(
            "INSUFFICIENT_HISTORY"
        )
        .astype(str)
        .tolist()
    )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=False,
    )

    features.to_parquet(
        FEATURE_PATH,
        index=False,
    )

    routing.to_parquet(
        ROUTING_PATH,
        index=False,
    )

    print(
        "[5/6] Writing profile report..."
    )

    generated_at = utc_now()

    report = {
        "schema_version": (
            "ams-v2-regime-router-v1-profile-v1"
        ),
        "protocol_id": (
            "AGGRESSIVE_MULTI_STRATEGY_"
            "RESEARCH_PROTOCOL_V2"
        ),
        "router_version": ROUTER_VERSION,
        "source_commit": source_commit,
        "generated_at": generated_at,
        "binding": False,
        "counts_as_registered_trial": False,
        "technical_status": "PASS",
        "decision": (
            "INFRASTRUCTURE_PROFILE_ONLY_NOT_A_TRIAL"
        ),
        "research_window": {
            "start": (
                snapshot_time.min().isoformat()
            ),
            "end_inclusive": (
                snapshot_time.max().isoformat()
            ),
            "locked_test_start": (
                "2025-01-01T00:00:00+00:00"
            ),
        },
        "inputs": {
            "history_directory": relative(
                HISTORY_DIRECTORY
            ),
            "history_file_count": len(
                history_paths
            ),
            "history_row_count": len(
                history
            ),
            "history_file_set_sha256": (
                file_set_sha256(
                    history_paths
                )
            ),
            "universe_path": relative(
                universe_paths[0]
            ),
            "universe_row_count": len(
                universe
            ),
            "universe_sha256": file_sha256(
                universe_paths[0]
            ),
        },
        "artifacts": {
            "feature_frame": relative(
                FEATURE_PATH
            ),
            "feature_frame_sha256": (
                file_sha256(
                    FEATURE_PATH
                )
            ),
            "routing_frame": relative(
                ROUTING_PATH
            ),
            "routing_frame_sha256": (
                file_sha256(
                    ROUTING_PATH
                )
            ),
        },
        "coverage": {
            "snapshot_count": len(
                routing
            ),
            "complete_snapshot_count": (
                complete_count
            ),
            "incomplete_snapshot_count": len(
                incomplete
            ),
            "complete_snapshot_fraction": (
                complete_count
                / len(routing)
            ),
            "first_complete_snapshot": (
                pd.to_datetime(
                    complete[
                        "snapshot_time"
                    ],
                    utc=True,
                )
                .min()
                .isoformat()
            ),
            "last_complete_snapshot": (
                pd.to_datetime(
                    complete[
                        "snapshot_time"
                    ],
                    utc=True,
                )
                .max()
                .isoformat()
            ),
        },
        "regime_distribution": {
            "counts": regime_counts,
            "fractions": regime_fractions,
            "dominant_regime": max(
                regime_counts,
                key=regime_counts.get,
            ),
            "dominant_regime_fraction": (
                concentration
            ),
            "distinct_regime_count": len(
                regime_counts
            ),
            "transition_count": (
                transition_count
            ),
            "longest_consecutive_runs": (
                longest_runs(
                    all_labels
                )
            ),
        },
        "routing_distribution": {
            "action_counts": action_counts,
            "matched_rule_counts": (
                matched_rule_counts
            ),
            "engine_activation_counts": dict(
                sorted(
                    engine_activation_counts.items()
                )
            ),
            "average_regime_risk_multiplier": (
                float(
                    pd.to_numeric(
                        complete[
                            "regime_risk_multiplier"
                        ],
                        errors="raise",
                    ).mean()
                )
            ),
            "average_routing_confidence": (
                float(
                    pd.to_numeric(
                        complete[
                            "routing_confidence"
                        ],
                        errors="raise",
                    ).mean()
                )
            ),
        },
        "diagnostic_flags": {
            "all_five_regimes_observed": (
                len(regime_counts)
                == len(RegimeLabel)
            ),
            "dominant_regime_fraction_above_0_70": (
                concentration > 0.70
            ),
            "dominant_regime_fraction_above_0_85": (
                concentration > 0.85
            ),
            "zero_regime_transitions": (
                transition_count == 0
            ),
            "manual_review_required_before_alpha_trials": (
                True
            ),
        },
        "technical_validation": (
            technical_validation
        ),
        "trial_accounting": {
            "before": accounting_before,
            "after": accounting_before,
            "changed": False,
        },
        "limitations": [
            (
                "This is an infrastructure profile, "
                "not an Alpha or portfolio trial."
            ),
            (
                "Daily data cannot validate four-hour "
                "portfolio decisions or one-hour execution."
            ),
            (
                "Historical delisting coverage remains "
                "incomplete and blocks final selection."
            ),
            (
                "The router thresholds are deterministic "
                "rules, not learned probabilities."
            ),
            (
                "The 2025 test and 2026 holdout "
                "were not accessed."
            ),
        ],
    }

    write_json(
        REPORT_PATH,
        report,
    )

    project_ledger = load_json(
        PROJECT_LEDGER_PATH
    )

    if project_ledger.get(
        "test_accessed"
    ):
        raise RuntimeError(
            "Project ledger shows 2025 access."
        )

    if project_ledger.get(
        "holdout_accessed"
    ):
        raise RuntimeError(
            "Project ledger shows 2026 access."
        )

    updates = project_ledger.setdefault(
        "protocol_updates",
        [],
    )

    if any(
        item.get("event_id")
        == EVENT_ID
        for item in updates
    ):
        raise RuntimeError(
            "Regime profile event already exists."
        )

    updates.append(
        {
            "event_id": EVENT_ID,
            "event_type": (
                "RESEARCH_INFRASTRUCTURE_PROFILE"
            ),
            "recorded_at": generated_at,
            "source_commit": source_commit,
            "router_version": ROUTER_VERSION,
            "report_path": relative(
                REPORT_PATH
            ),
            "report_sha256": file_sha256(
                REPORT_PATH
            ),
            "feature_frame_path": relative(
                FEATURE_PATH
            ),
            "feature_frame_sha256": (
                file_sha256(
                    FEATURE_PATH
                )
            ),
            "routing_frame_path": relative(
                ROUTING_PATH
            ),
            "routing_frame_sha256": (
                file_sha256(
                    ROUTING_PATH
                )
            ),
            "snapshot_count": len(
                routing
            ),
            "complete_snapshot_count": (
                complete_count
            ),
            "registered_trials_consumed": 0,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )

    active_components = (
        project_ledger.setdefault(
            "active_components",
            [],
        )
    )

    for component in (
        "AMS_V2_REGIME_FEATURE_FRAME_V1",
        "AMS_V2_REGIME_ROUTER_V1",
    ):
        if component not in active_components:
            active_components.append(
                component
            )

    project_ledger["current_stage"] = (
        "AMS_V2_REGIME_ROUTER_V1_PROFILED"
    )

    project_ledger["next_action"] = (
        "REVIEW_ROUTER_V1_EMPIRICAL_DISTRIBUTION_"
        "BEFORE_IMPLEMENTING_ALPHA_WALK_FORWARD"
    )

    project_ledger[
        "last_updated_at"
    ] = generated_at

    write_json(
        PROJECT_LEDGER_PATH,
        project_ledger,
    )

    accounting_after = load_json(
        EXPERIMENT_LEDGER_PATH
    )["trial_accounting"]

    if accounting_after != accounting_before:
        raise RuntimeError(
            "Experiment accounting changed."
        )

    print(
        "[6/6] Regime profile complete."
    )

    print(
        json.dumps(
            {
                "technical_status": (
                    report["technical_status"]
                ),
                "decision": report["decision"],
                "snapshot_count": (
                    report["coverage"][
                        "snapshot_count"
                    ]
                ),
                "complete_snapshot_count": (
                    report["coverage"][
                        "complete_snapshot_count"
                    ]
                ),
                "regime_counts": regime_counts,
                "regime_fractions": (
                    regime_fractions
                ),
                "dominant_regime": (
                    report[
                        "regime_distribution"
                    ]["dominant_regime"]
                ),
                "dominant_regime_fraction": (
                    concentration
                ),
                "transition_count": (
                    transition_count
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
                "test_2025_accessed": (
                    accounting_after[
                        "test_2025_accessed"
                    ]
                ),
                "holdout_2026_accessed": (
                    accounting_after[
                        "holdout_2026_accessed"
                    ]
                ),
            },
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()