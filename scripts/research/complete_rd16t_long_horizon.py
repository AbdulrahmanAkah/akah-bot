from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
IMPLEMENTATION_SUBJECT: Final = (
    "research(rd16t): add signal architecture reset and long horizon research"
)
RESULT_SUBJECT: Final = (
    "research(rd16t): complete signal architecture reset and long horizon research"
)

PYTHON_TARGETS: Final = (
    "src/spotbot/research/rd16t_signals.py",
    "src/spotbot/research/rd16t_evaluation.py",
    "scripts/research/run_rd16t_long_horizon.py",
    "scripts/research/complete_rd16t_long_horizon.py",
    "tests/research/test_rd16t_long_horizon.py",
)
DATA_OUTPUTS: Final = (
    "data/research/rd16t/long-horizon-registry.csv",
    "data/research/rd16t/long-horizon-summary.csv",
    "data/research/rd16t/component-decisions.csv",
    "data/research/rd16t/cost-stress.csv",
    "data/research/rd16t/signal-coverage.csv",
    "data/research/rd16t/causality-audit.csv",
    "data/research/rd16t/routing-summary.csv",
    "data/research/rd16t/annual-performance.csv",
    "data/research/rd16t/bull-window-capture.csv",
    "data/research/rd16t/symbol-performance.csv",
    "data/research/rd16t/exit-policy-summary.csv",
    "data/research/rd16t/all-hypothesis-overlay-summary.csv",
    "data/research/rd16t/frozen-input-hashes.json",
    "data/research/rd16t/local-output-manifest-v1.json",
    "data/research/rd16t/output-hashes.json",
    "data/research/rd16t/validation-report.json",
    "data/research/rd16t/rd16t-final-report-v1.json",
)
REPORT_OUTPUTS: Final = (
    "reports/research/rd16t-long-horizon-results-v1.md",
    "reports/research/rd16t-long-horizon-decisions-v1.md",
    "reports/research/rd16t-architecture-reset-causality-audit-v1.md",
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


def git(repo: Path, *arguments: str, capture: bool = True) -> str:
    return run(("git", *arguments), cwd=repo, capture=capture)


def python_executable(repo: Path) -> str:
    windows = repo / ".venv" / "Scripts" / "python.exe"
    if windows.is_file():
        return str(windows)
    posix = repo / ".venv" / "bin" / "python"
    if posix.is_file():
        return str(posix)
    return sys.executable


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
    if git(repo, "log", "-1", "--pretty=%s") != IMPLEMENTATION_SUBJECT:
        raise CompletionError("Unexpected implementation commit subject.")
    if git(repo, "status", "--short", "--untracked-files=no"):
        raise CompletionError("Tracked changes exist before completion.")

    run((python, "-m", "py_compile", *PYTHON_TARGETS), cwd=repo)
    run((python, "-m", "ruff", "check", *PYTHON_TARGETS), cwd=repo)
    run(
        (python, "-m", "ruff", "format", "--check", *PYTHON_TARGETS),
        cwd=repo,
    )
    run(
        (
            python,
            "-m",
            "mypy",
            "src/spotbot/research/rd16t_signals.py",
            "src/spotbot/research/rd16t_evaluation.py",
            "--strict",
        ),
        cwd=repo,
    )
    run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16t_long_horizon.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    run(
        (
            python,
            "scripts/research/run_rd16t_long_horizon.py",
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
    run((python, "-m", "pytest", "-q", "-W", "error"), cwd=repo)
    git(repo, "diff", "--check", capture=False)

    missing = [path for path in (*DATA_OUTPUTS, *REPORT_OUTPUTS) if not (repo / path).is_file()]
    if missing:
        raise CompletionError(f"Missing RD16-T outputs: {missing}")

    git(repo, "add", "--", *DATA_OUTPUTS, capture=False)
    git(repo, "add", "-f", "--", *REPORT_OUTPUTS, capture=False)
    git(repo, "diff", "--cached", "--check", capture=False)

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
            "RD16-T staged output mismatch. "
            f"missing={sorted(expected - staged)}; "
            f"unexpected={sorted(staged - expected)}"
        )

    git(repo, "commit", "-m", RESULT_SUBJECT, capture=False)
    result_commit = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "origin", BRANCH, capture=False)
    git(repo, "fetch", "origin", BRANCH, capture=False)
    if result_commit != git(repo, "rev-parse", f"origin/{BRANCH}"):
        raise CompletionError("RD16-T result commit did not reach remote.")
    if git(repo, "status", "--short", "--untracked-files=no"):
        raise CompletionError("Tracked changes remain after RD16-T completion.")

    report_path = repo / "data/research/rd16t/rd16t-final-report-v1.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    overlay = report["pre_registered_combined_overlay"]

    print("\nRD16-T COMPLETE")
    print(f"commit={result_commit}")
    for key in (
        "decision",
        "architecture_id",
        "source_architecture_id",
        "eligible_asset_count",
        "hypotheses_evaluated",
        "retained_hypothesis_count",
        "promising_hypothesis_count",
        "retained_hypotheses",
        "promising_hypotheses",
        "strategic_objective_met_count",
        "next_stage",
    ):
        print(f"{key}={report[key]}")
    for key in (
        "new_trade_count",
        "net_return",
        "profit_factor",
        "two_x_capital_feasible",
        "noncore_new_trade_count",
        "noncore_net_pnl",
    ):
        print(f"combined_overlay_{key}={overlay[key]}")


if __name__ == "__main__":
    main()
