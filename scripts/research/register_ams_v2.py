from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from spotbot.research.ams_v2_protocol import (
    PREDECESSOR_PROTOCOL_ID,
    PROTOCOL_ID,
    build_experiment_ledger,
    build_protocol,
    validate_experiment_ledger,
    validate_protocol,
)

ROOT = Path.cwd()

EXPECTED_BRANCH = (
    "research/ams-v2-protocol-registration"
)

EXPECTED_BASE_PREFIX = "29206d2"

HYPOTHESIS_LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "aggressive-multi-strategy-"
    "hypothesis-ledger-v1.json"
)

V1_PROTOCOL_PATH = (
    ROOT
    / "reports/research/"
    "aggressive-multi-strategy-"
    "research-protocol-v1.json"
)

PROJECT_LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "project-research-ledger-v3.json"
)

CLOSURE_PATH = (
    ROOT
    / "reports/research/"
    "ams-v1-closure-report.json"
)

V2_PROTOCOL_PATH = (
    ROOT
    / "reports/research/"
    "aggressive-multi-strategy-"
    "research-protocol-v2.json"
)

EXPERIMENT_LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-experiment-ledger-v1.json"
)

RESULT_PATHS = (
    ROOT
    / "reports/research/"
    "ams-v1-h01-volatility-breakout.json",
    ROOT
    / "reports/research/"
    "ams-v1-h02-aggressive-reacceleration.json",
    ROOT
    / "reports/research/"
    "ams-v1-h03-liquidity-sweep-reversal.json",
    ROOT
    / "reports/research/"
    "ams-v1-h04-cross-sectional-rotation.json",
    ROOT
    / "reports/research/"
    "ams-v1-h05-compression-expansion.json",
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


def compact_result(
    report: dict[str, Any],
    *,
    path: Path,
) -> dict[str, Any]:
    performance = report[
        "performance"
    ]

    trades = report[
        "trade_statistics"
    ]

    return {
        "hypothesis_id": (
            report["hypothesis_id"]
        ),
        "family": report["family"],
        "technical_status": (
            report["technical_status"]
        ),
        "decision": report["decision"],
        "final_equity": (
            performance["final_equity"]
        ),
        "total_return": (
            performance["total_return"]
        ),
        "geometric_monthly_return": (
            performance[
                "geometric_monthly_return"
            ]
        ),
        "annual_capital_multiple": (
            performance[
                "annual_capital_multiple"
            ]
        ),
        "maximum_drawdown": (
            performance[
                "maximum_drawdown"
            ]
        ),
        "sharpe_ratio": (
            performance["sharpe_ratio"]
        ),
        "trade_count": (
            trades["trade_count"]
        ),
        "report_path": str(
            path.relative_to(ROOT)
        ).replace("\\", "/"),
    }


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
        EXPECTED_BASE_PREFIX
    ):
        raise RuntimeError(
            f"Unexpected base commit: {source_commit}"
        )

    for generated_path in (
        CLOSURE_PATH,
        V2_PROTOCOL_PATH,
        EXPERIMENT_LEDGER_PATH,
    ):
        if generated_path.exists():
            raise RuntimeError(
                f"Generated report already exists: "
                f"{generated_path}"
            )

    hypothesis_ledger = load_json(
        HYPOTHESIS_LEDGER_PATH
    )

    v1_protocol = load_json(
        V1_PROTOCOL_PATH
    )

    project_ledger = load_json(
        PROJECT_LEDGER_PATH
    )

    if (
        hypothesis_ledger.get("status")
        != "IN_PROGRESS"
    ):
        raise RuntimeError(
            "AMS V1 hypothesis ledger is not IN_PROGRESS."
        )

    if (
        v1_protocol.get("status")
        != "ACTIVE"
    ):
        raise RuntimeError(
            "AMS V1 protocol is not ACTIVE."
        )

    if project_ledger.get(
        "test_accessed"
    ):
        raise RuntimeError(
            "2025 test access flag is already true."
        )

    if project_ledger.get(
        "holdout_accessed"
    ):
        raise RuntimeError(
            "2026 holdout access flag is already true."
        )

    reports = [
        load_json(path)
        for path in RESULT_PATHS
    ]

    if len(reports) != 5:
        raise RuntimeError(
            "Expected five AMS V1 reports."
        )

    if any(
        report.get("technical_status")
        != "PASS"
        for report in reports
    ):
        raise RuntimeError(
            "Not every AMS V1 result technically passed."
        )

    if any(
        not str(
            report.get("decision", "")
        ).startswith("REJECT_")
        for report in reports
    ):
        raise RuntimeError(
            "Not every AMS V1 hypothesis was rejected."
        )

    if any(
        not report.get("binding")
        for report in reports
    ):
        raise RuntimeError(
            "A non-binding AMS V1 report was found."
        )

    compact_results = [
        compact_result(
            report,
            path=path,
        )
        for report, path
        in zip(
            reports,
            RESULT_PATHS,
            strict=True,
        )
    ]

    best_return = max(
        compact_results,
        key=lambda item: item[
            "geometric_monthly_return"
        ],
    )

    lowest_drawdown = max(
        compact_results,
        key=lambda item: item[
            "maximum_drawdown"
        ],
    )

    registered_at = utc_now()

    closure = {
        "schema_version": (
            "ams-v1-closure-report-v1"
        ),
        "protocol_id": (
            PREDECESSOR_PROTOCOL_ID
        ),
        "status": (
            "CLOSED_ALL_HYPOTHESES_REJECTED"
        ),
        "closed_at": registered_at,
        "source_commit": source_commit,
        "binding_result_count": 5,
        "technical_pass_count": 5,
        "rejected_count": 5,
        "promoted_count": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "final_model_selected": False,
        "best_geometric_return_result": {
            "hypothesis_id": (
                best_return["hypothesis_id"]
            ),
            "geometric_monthly_return": (
                best_return[
                    "geometric_monthly_return"
                ]
            ),
            "maximum_drawdown": (
                best_return[
                    "maximum_drawdown"
                ]
            ),
        },
        "lowest_drawdown_result": {
            "hypothesis_id": (
                lowest_drawdown[
                    "hypothesis_id"
                ]
            ),
            "geometric_monthly_return": (
                lowest_drawdown[
                    "geometric_monthly_return"
                ]
            ),
            "maximum_drawdown": (
                lowest_drawdown[
                    "maximum_drawdown"
                ]
            ),
        },
        "results": compact_results,
        "conclusions": [
            (
                "No independent AMS V1 family met "
                "the registered monthly objective."
            ),
            (
                "High-return families suffered "
                "catastrophic drawdowns."
            ),
            (
                "Lower-drawdown reversal logic "
                "did not produce sufficient growth."
            ),
            (
                "Fast cross-sectional rotation "
                "created excessive turnover and loss."
            ),
            (
                "A regime-aware multi-engine "
                "architecture is required."
            ),
        ],
        "selection_blockers": [
            (
                "All five registered hypotheses "
                "were rejected."
            ),
            (
                "Historical delisting coverage "
                "remains incomplete."
            ),
            (
                "Four-hour and one-hour validation "
                "has not been completed."
            ),
            (
                "The 2025 test and 2026 holdout "
                "remain locked."
            ),
        ],
    }

    protocol = build_protocol(
        base_commit=source_commit,
        registered_at=registered_at,
    )

    experiment_ledger = (
        build_experiment_ledger(
            base_commit=source_commit,
            registered_at=registered_at,
        )
    )

    validate_protocol(
        protocol
    )

    validate_experiment_ledger(
        experiment_ledger
    )

    write_json(
        CLOSURE_PATH,
        closure,
    )

    write_json(
        V2_PROTOCOL_PATH,
        protocol,
    )

    write_json(
        EXPERIMENT_LEDGER_PATH,
        experiment_ledger,
    )

    hypothesis_ledger["status"] = (
        "COMPLETED_ALL_REJECTED"
    )

    hypothesis_ledger[
        "closed_at"
    ] = registered_at

    hypothesis_ledger[
        "closure_decision"
    ] = "NO_HYPOTHESIS_PROMOTED"

    hypothesis_ledger[
        "closure_report_path"
    ] = str(
        CLOSURE_PATH.relative_to(ROOT)
    ).replace("\\", "/")

    hypothesis_ledger[
        "last_updated_at"
    ] = registered_at

    write_json(
        HYPOTHESIS_LEDGER_PATH,
        hypothesis_ledger,
    )

    v1_protocol["status"] = (
        "CLOSED_NO_PROMOTION"
    )

    v1_protocol["closed_at"] = (
        registered_at
    )

    v1_protocol[
        "closure_decision"
    ] = "ALL_REGISTERED_HYPOTHESES_REJECTED"

    v1_protocol[
        "closure_report_path"
    ] = str(
        CLOSURE_PATH.relative_to(ROOT)
    ).replace("\\", "/")

    write_json(
        V1_PROTOCOL_PATH,
        v1_protocol,
    )

    event_id = (
        "AMS_V1_CLOSED_AND_"
        "AMS_V2_REGISTERED"
    )

    updates = project_ledger.setdefault(
        "protocol_updates",
        [],
    )

    if any(
        item.get("event_id")
        == event_id
        for item in updates
    ):
        raise RuntimeError(
            "AMS V2 registration event already exists."
        )

    closure_hash = file_sha256(
        CLOSURE_PATH
    )

    protocol_hash = file_sha256(
        V2_PROTOCOL_PATH
    )

    experiment_hash = file_sha256(
        EXPERIMENT_LEDGER_PATH
    )

    updates.append(
        {
            "event_id": event_id,
            "event_type": (
                "RESEARCH_PROTOCOL_TRANSITION"
            ),
            "recorded_at": registered_at,
            "base_commit": source_commit,
            "closed_protocol_id": (
                PREDECESSOR_PROTOCOL_ID
            ),
            "closure_status": (
                "CLOSED_ALL_HYPOTHESES_REJECTED"
            ),
            "closure_report_path": str(
                CLOSURE_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
            "closure_report_sha256": (
                closure_hash
            ),
            "successor_protocol_id": (
                PROTOCOL_ID
            ),
            "successor_protocol_path": str(
                V2_PROTOCOL_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
            "successor_protocol_sha256": (
                protocol_hash
            ),
            "experiment_ledger_path": str(
                EXPERIMENT_LEDGER_PATH.relative_to(
                    ROOT
                )
            ).replace("\\", "/"),
            "experiment_ledger_sha256": (
                experiment_hash
            ),
            "registered_alpha_configurations": 96,
            "registered_portfolio_profiles": 4,
            "maximum_total_unique_variants": 100,
            "test_2025_locked": True,
            "holdout_2026_locked": True,
            "final_model_selection_allowed": False,
        }
    )

    active_components = project_ledger.setdefault(
        "active_components",
        [],
    )

    for component in (
        "AGGRESSIVE_MULTI_STRATEGY_RESEARCH_PROTOCOL_V2",
        "AMS_V2_EXPERIMENT_LEDGER_V1",
    ):
        if component not in active_components:
            active_components.append(
                component
            )

    project_ledger["current_stage"] = (
        "AMS_V2_PROTOCOL_REGISTERED"
    )

    project_ledger["next_action"] = (
        "IMPLEMENT_AMS_V2_REGIME_FEATURE_FRAME_"
        "AND_WALK_FORWARD_ORCHESTRATOR_WITHOUT_"
        "ACCESSING_2025_OR_2026"
    )

    project_ledger[
        "last_updated_at"
    ] = registered_at

    if project_ledger.get(
        "test_accessed"
    ):
        raise RuntimeError(
            "2025 test access changed unexpectedly."
        )

    if project_ledger.get(
        "holdout_accessed"
    ):
        raise RuntimeError(
            "2026 holdout access changed unexpectedly."
        )

    write_json(
        PROJECT_LEDGER_PATH,
        project_ledger,
    )

    print(
        json.dumps(
            {
                "ams_v1_status": (
                    hypothesis_ledger["status"]
                ),
                "ams_v1_protocol_status": (
                    v1_protocol["status"]
                ),
                "ams_v2_protocol_id": (
                    protocol["protocol_id"]
                ),
                "ams_v2_status": (
                    protocol["status"]
                ),
                "alpha_configurations": len(
                    experiment_ledger[
                        "alpha_configurations"
                    ]
                ),
                "portfolio_profiles": len(
                    experiment_ledger[
                        "portfolio_profiles"
                    ]
                ),
                "maximum_total_unique_variants": (
                    experiment_ledger[
                        "trial_accounting"
                    ][
                        "total_unique_variants_registered"
                    ]
                ),
                "trials_executed": (
                    experiment_ledger[
                        "trial_accounting"
                    ][
                        "trials_executed"
                    ]
                ),
                "test_2025_accessed": (
                    experiment_ledger[
                        "trial_accounting"
                    ][
                        "test_2025_accessed"
                    ]
                ),
                "holdout_2026_accessed": (
                    experiment_ledger[
                        "trial_accounting"
                    ][
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