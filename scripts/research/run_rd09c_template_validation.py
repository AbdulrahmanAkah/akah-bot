"""Run local-only validation for the RD09C parameterized SQL templates."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Final

from spotbot.research.rd09c_dune_templates import (
    DATA_DIRECTORY,
    PARAMETER_NAMES,
    REPOSITORY_ROOT,
    registered_templates,
    render_template_for_local_validation,
    validate_requested_range,
    write_acquisition_plan,
    write_source_reconciliation,
    write_template_manifest,
)

STAGE: Final = "RD09C-LOCAL-PARAMETERIZED-DUNE-TEMPLATE-VALIDATION"
DECISION: Final = "RD09C_DUNE_PARAMETERIZED_TEMPLATES_LOCALLY_VALIDATED"
NEXT_STAGE: Final = "RD09C_BROWSER_CANONICAL_QUERY_CREATION_PILOT"


def _current_branch() -> str:
    """Return a local branch name when git is available, without requiring it."""
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return "GIT_NOT_AVAILABLE"
    return completed.stdout.strip() or "GIT_BRANCH_NOT_AVAILABLE"


def _range_guard_passes() -> bool:
    allowed = (
        ("2021-01-01T00:00:00Z", "2021-02-01T00:00:00Z"),
        ("2022-03-01T00:00:00Z", "2022-04-01T00:00:00Z"),
        ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    )
    prohibited = (
        ("2022-03-01T00:00:00Z", "2022-03-01T00:00:00Z"),
        ("2022-04-01T00:00:00Z", "2022-03-01T00:00:00Z"),
        ("2020-12-31T00:00:00Z", "2021-01-01T00:00:00Z"),
        ("2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
        ("2024-12-31T00:00:00Z", "2025-01-02T00:00:00Z"),
        ("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"),
        ("2021-01-01T00:00:00Z", "2022-01-03T00:00:00Z"),
    )
    for start, end in allowed:
        validate_requested_range(start, end)
    for start, end in prohibited:
        try:
            validate_requested_range(start, end)
        except ValueError:
            continue
        return False
    return True


def run_validation(output_directory: Path = DATA_DIRECTORY) -> dict[str, object]:
    """Write deterministic local reports without opening a browser or network connection."""
    output_directory.mkdir(parents=True, exist_ok=True)
    templates = registered_templates()
    for spec in templates:
        render_template_for_local_validation(spec, "2022-03-01T00:00:00Z", "2022-04-01T00:00:00Z")
    reconciliation = write_source_reconciliation(
        output_directory / "template-source-reconciliation.csv"
    )
    registry = write_template_manifest(output_directory / "dune-template-registry-v1.csv")
    acquisition_plan = write_acquisition_plan(output_directory / "acquisition-plan-v1.csv")
    source_logic_passed = all(bool(row["normalized_logic_match"]) for row in reconciliation)
    all_templates_passed = all(row["status"] == "PASS" for row in reconciliation)
    range_guard_passed = _range_guard_passes()
    status = "COMPLETE" if all_templates_passed and range_guard_passed else "BLOCKED"
    report: dict[str, object] = {
        "stage": STAGE,
        "status": status,
        "decision": DECISION if status == "COMPLETE" else "RD09C_TEMPLATE_VALIDATION_BLOCKED",
        "template_count": len(templates),
        "passing_template_count": sum(row["status"] == "PASS" for row in reconciliation),
        "failing_template_count": sum(row["status"] != "PASS" for row in reconciliation),
        "parameter_names": list(PARAMETER_NAMES),
        "source_logic_reconciliation_passed": source_logic_passed,
        "range_guard_passed": range_guard_passed,
        "registry_row_count": len(registry),
        "acquisition_plan_row_count": len(acquisition_plan),
        "git_branch_observed": _current_branch(),
        "dune_opened": False,
        "dune_api_called": False,
        "credits_consumed": 0,
        "paid_spending_usd": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "signals_computed": False,
        "labels_computed": False,
        "backtests_run": False,
        "portfolio_computed": False,
        "next_stage": NEXT_STAGE if status == "COMPLETE" else "NOT_AUTHORIZED",
    }
    report_path = output_directory / "rd09c-template-validation-v1.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = run_validation()
    return 0 if report["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
