from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
IMPLEMENTATION_SUBJECT: Final = "research(rd16n): add diversified intraday alpha research"
RESULT_SUBJECT: Final = "research(rd16n): complete diversified intraday alpha research"

PYTHON_TARGETS: Final = (
    "src/spotbot/research/rd16n_signals.py",
    "src/spotbot/research/rd16n_evaluation.py",
    "scripts/research/run_rd16n_intraday_alpha_diversification.py",
    "scripts/research/complete_rd16n_intraday_alpha_diversification.py",
    "tests/research/test_rd16n_intraday_alpha_diversification.py",
)

DATA_OUTPUTS: Final = (
    "data/research/rd16n/hypothesis-registry.csv",
    "data/research/rd16n/family-summary.csv",
    "data/research/rd16n/component-decisions.csv",
    "data/research/rd16n/cost-stress.csv",
    "data/research/rd16n/family-coverage.csv",
    "data/research/rd16n/causality-audit.csv",
    "data/research/rd16n/routing-decision-summary.csv",
    "data/research/rd16n/annual-performance.csv",
    "data/research/rd16n/bull-window-capture.csv",
    "data/research/rd16n/new-engine-regime-attribution.csv",
    "data/research/rd16n/all-new-overlay-summary.csv",
    "data/research/rd16n/frozen-input-hashes.json",
    "data/research/rd16n/local-output-manifest-v1.json",
    "data/research/rd16n/output-hashes.json",
    "data/research/rd16n/rd16n-final-report-v1.json",
    "data/research/rd16n/validation-report.json",
)

REPORT_OUTPUTS: Final = (
    "reports/research/rd16n-intraday-alpha-diversification-results-v1.md",
    "reports/research/rd16n-new-engine-carry-forward-decisions-v1.md",
    "reports/research/rd16n-causality-capacity-audit-v1.md",
)


class CompletionError(RuntimeError):
    pass


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    capture: bool = False,
) -> str:
    print("\n>", " ".join(command), flush=True)
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        text=True,
        capture_output=capture,
    )
    if capture:
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        raise CompletionError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}"
        )
    return completed.stdout.strip() if capture else ""


def git(
    repo: Path,
    *arguments: str,
    capture: bool = True,
) -> str:
    return run(
        ("git", *arguments),
        cwd=repo,
        capture=capture,
    )


def python_executable(repo: Path) -> str:
    windows = repo / ".venv" / "Scripts" / "python.exe"
    if windows.is_file():
        return str(windows)
    posix = repo / ".venv" / "bin" / "python"
    if posix.is_file():
        return str(posix)
    return sys.executable


def verify_outputs(repo: Path) -> None:
    missing = [
        relative for relative in (*DATA_OUTPUTS, *REPORT_OUTPUTS) if not (repo / relative).is_file()
    ]
    if missing:
        raise CompletionError(f"Missing RD16-N outputs: {missing}")


def verify_staged_scope(repo: Path) -> None:
    staged = {
        line.replace("\\", "/")
        for line in git(
            repo,
            "diff",
            "--cached",
            "--name-only",
        ).splitlines()
        if line
    }
    expected = set(DATA_OUTPUTS) | set(REPORT_OUTPUTS)
    if staged != expected:
        raise CompletionError(
            "RD16-N staged scope mismatch. "
            f"missing={sorted(expected - staged)}; "
            f"unexpected={sorted(staged - expected)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    python = python_executable(repo)

    if git(repo, "branch", "--show-current") != BRANCH:
        raise CompletionError("Unexpected branch.")

    git(repo, "fetch", "origin", BRANCH, capture=False)
    local = git(repo, "rev-parse", "HEAD")
    remote = git(repo, "rev-parse", f"origin/{BRANCH}")
    if local != remote:
        raise CompletionError("Local and remote branch heads differ.")

    subject = git(repo, "log", "-1", "--pretty=%s")
    if subject != IMPLEMENTATION_SUBJECT:
        raise CompletionError(f"Unexpected implementation commit subject: {subject}")
    if git(repo, "status", "--short", "--untracked-files=no"):
        raise CompletionError("Tracked changes exist before RD16-N completion.")

    run(
        (python, "-m", "py_compile", *PYTHON_TARGETS),
        cwd=repo,
    )
    run(
        (python, "-m", "ruff", "check", *PYTHON_TARGETS),
        cwd=repo,
    )
    run(
        (
            python,
            "-m",
            "ruff",
            "format",
            "--check",
            *PYTHON_TARGETS,
        ),
        cwd=repo,
    )
    run(
        (
            python,
            "-m",
            "mypy",
            "src/spotbot/research/rd16n_signals.py",
            "src/spotbot/research/rd16n_evaluation.py",
            "--strict",
        ),
        cwd=repo,
    )
    run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16n_intraday_alpha_diversification.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    run(
        (
            python,
            "scripts/research/run_rd16n_intraday_alpha_diversification.py",
            "--repo",
            str(repo),
        ),
        cwd=repo,
    )
    run(
        (
            python,
            "-m",
            "pytest",
            "tests/research",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    run(
        (python, "-m", "pytest", "-q", "-W", "error"),
        cwd=repo,
    )
    git(repo, "diff", "--check", capture=False)

    verify_outputs(repo)

    git(
        repo,
        "add",
        "--",
        *DATA_OUTPUTS,
        capture=False,
    )
    git(
        repo,
        "add",
        "-f",
        "--",
        *REPORT_OUTPUTS,
        capture=False,
    )
    git(
        repo,
        "diff",
        "--cached",
        "--check",
        capture=False,
    )
    verify_staged_scope(repo)

    git(
        repo,
        "commit",
        "-m",
        RESULT_SUBJECT,
        capture=False,
    )
    result_commit = git(repo, "rev-parse", "HEAD")
    git(
        repo,
        "push",
        "origin",
        BRANCH,
        capture=False,
    )
    git(repo, "fetch", "origin", BRANCH, capture=False)
    if result_commit != git(
        repo,
        "rev-parse",
        f"origin/{BRANCH}",
    ):
        raise CompletionError("RD16-N result commit did not reach remote.")
    if git(repo, "status", "--short", "--untracked-files=no"):
        raise CompletionError("Tracked changes remain after RD16-N completion.")

    report_path = repo / "data/research/rd16n/rd16n-final-report-v1.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    all_new = report["pre_registered_all_new_overlay"]

    print("\nRD16-N COMPLETE")
    print(f"commit={result_commit}")
    for key in (
        "decision",
        "architecture_id",
        "hypotheses_evaluated",
        "retained_hypothesis_count",
        "promising_hypothesis_count",
        "retained_hypotheses",
        "promising_hypotheses",
        "strategic_objective_met_count",
        "next_stage",
    ):
        print(f"{key}={report[key]}")
    print(f"all_new_overlay_new_trade_count={all_new['new_trade_count']}")
    print(f"all_new_overlay_net_return={all_new['net_return']}")
    print(f"all_new_overlay_profit_factor={all_new['profit_factor']}")
    print(f"all_new_overlay_two_x_capital_feasible={all_new['two_x_capital_feasible']}")


if __name__ == "__main__":
    main()
