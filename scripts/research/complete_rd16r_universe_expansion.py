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
    "research(rd16r): add universe expansion and liquidity tier research"
)
RESULT_SUBJECT: Final = "research(rd16r): complete universe expansion and liquidity tier research"

PYTHON_TARGETS: Final = (
    "src/spotbot/research/rd16r_universe.py",
    "src/spotbot/research/rd16r_evaluation.py",
    "scripts/research/run_rd16r_universe_expansion.py",
    "scripts/research/complete_rd16r_universe_expansion.py",
    "tests/research/test_rd16r_universe_expansion.py",
)
DATA_OUTPUTS: Final = (
    "data/research/rd16r/universe-registry.csv",
    "data/research/rd16r/market-availability.csv",
    "data/research/rd16r/data-coverage.csv",
    "data/research/rd16r/liquidity-tier-summary.csv",
    "data/research/rd16r/eligible-universe.csv",
    "data/research/rd16r/acquisition-failures.csv",
    "data/research/rd16r/frozen-input-hashes.json",
    "data/research/rd16r/local-data-manifest-v1.json",
    "data/research/rd16r/output-hashes.json",
    "data/research/rd16r/validation-report.json",
    "data/research/rd16r/rd16r-final-report-v1.json",
)
REPORT_OUTPUTS: Final = (
    "reports/research/rd16r-universe-expansion-results-v1.md",
    "reports/research/rd16r-liquidity-tier-decisions-v1.md",
    "reports/research/rd16r-data-acquisition-causality-audit-v1.md",
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
            "src/spotbot/research/rd16r_universe.py",
            "src/spotbot/research/rd16r_evaluation.py",
            "--strict",
        ),
        cwd=repo,
    )
    run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16r_universe_expansion.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    run(
        (
            python,
            "scripts/research/run_rd16r_universe_expansion.py",
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
        raise CompletionError(f"Missing RD16-R outputs: {missing}")

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
            "RD16-R staged output mismatch. "
            f"missing={sorted(expected - staged)}; "
            f"unexpected={sorted(staged - expected)}"
        )

    git(repo, "commit", "-m", RESULT_SUBJECT, capture=False)
    result_commit = git(repo, "rev-parse", "HEAD")
    git(repo, "push", "origin", BRANCH, capture=False)
    git(repo, "fetch", "origin", BRANCH, capture=False)
    if result_commit != git(repo, "rev-parse", f"origin/{BRANCH}"):
        raise CompletionError("Result commit did not reach remote.")
    if git(repo, "status", "--short", "--untracked-files=no"):
        raise CompletionError("Tracked changes remain after RD16-R completion.")

    report_path = repo / "data/research/rd16r/rd16r-final-report-v1.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    print("\nRD16-R COMPLETE")
    print(f"commit={result_commit}")
    for key in (
        "decision",
        "architecture_id",
        "registered_candidate_count",
        "resolved_market_count",
        "eligible_asset_count",
        "eligible_noncore_asset_count",
        "tier_a_count",
        "tier_b_count",
        "tier_c_count",
        "research_readiness",
        "acquisition_failure_count",
        "next_stage",
    ):
        print(f"{key}={report[key]}")


if __name__ == "__main__":
    main()
