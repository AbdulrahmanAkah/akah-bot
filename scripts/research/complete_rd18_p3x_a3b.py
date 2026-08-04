from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

EXPECTED_BRANCH = "research/rd18-p3x-a1-full-c2-hourly-and-generator-build-v1"
EXPECTED_HEAD = "7281dba02708ed98bb340c05a1ac155dfdf157b4"
EXPECTED_TRACKED_DIFF_SHA256 = "ca08a8caebf84327383e077b7853eb3082fcce20646706aa334a2fd56447c99d"
EXPECTED_TRACKED_PATHS = {
    "data/research/rd18_p3x_a3/rd18-p3x-a3-sealed-replay-authorization-review-v1.json",
    "scripts/research/validate_rd18_p3x_a3.py",
    "src/spotbot/research/rd18_p3x_a3_authorization.py",
}

QUALITY_FILES = (
    "scripts/research/complete_rd18_p3x_a3b.py",
    "scripts/research/run_rd18_p3x_a3b.py",
    "scripts/research/validate_rd18_p3x_a3b.py",
    "src/spotbot/research/rd18_p3x_a3b_audit.py",
    "tests/research/test_rd18_p3x_a3b.py",
)


class A3BCompletionError(RuntimeError):
    """Raised when A3B completion cannot continue safely."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo", type=Path, required=True)
    result.add_argument("--python", type=Path, required=True)
    result.add_argument("--a1-runtime", type=Path, required=True)
    result.add_argument("--a2-runtime", type=Path, required=True)
    result.add_argument("--a3-input-dir", type=Path, required=True)
    result.add_argument("--a3a-runtime", type=Path, required=True)
    result.add_argument("--output-dir", type=Path, required=True)
    return result


def run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
) -> dict[str, Any]:
    print(f"\n> {' '.join(args)}", flush=True)
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    record = {
        "command": args,
        "returncode": completed.returncode,
    }
    if check and completed.returncode != 0:
        raise A3BCompletionError(f"command failed ({completed.returncode}): {' '.join(args)}")
    return record


def git_text(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise A3BCompletionError(f"git {' '.join(args)} failed: {completed.stderr}")
    return completed.stdout.strip()


def tracked_state(repo: Path) -> tuple[set[str], str]:
    names = {
        line.strip()
        for line in git_text(
            repo,
            "diff",
            "--name-only",
            "HEAD",
            "--",
        ).splitlines()
        if line.strip()
    }
    completed = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", *sorted(names)],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise A3BCompletionError("failed to fingerprint tracked diff")
    return names, hashlib.sha256(completed.stdout).hexdigest()


def verify_repository(repo: Path) -> dict[str, object]:
    branch = git_text(repo, "branch", "--show-current")
    head = git_text(repo, "rev-parse", "HEAD")
    remote = git_text(
        repo,
        "rev-parse",
        f"refs/remotes/origin/{EXPECTED_BRANCH}",
    )
    staged = {
        line.strip()
        for line in git_text(
            repo,
            "diff",
            "--cached",
            "--name-only",
            "--",
        ).splitlines()
        if line.strip()
    }
    tracked, fingerprint = tracked_state(repo)
    if branch != EXPECTED_BRANCH:
        raise A3BCompletionError(f"branch drift: {branch}")
    if head != EXPECTED_HEAD or remote != EXPECTED_HEAD:
        raise A3BCompletionError(f"head drift: local={head}, cached_remote={remote}")
    if staged:
        raise A3BCompletionError(f"staged paths must be empty: {sorted(staged)}")
    if tracked != EXPECTED_TRACKED_PATHS:
        raise A3BCompletionError(f"tracked path set drifted: {sorted(tracked)}")
    if fingerprint != EXPECTED_TRACKED_DIFF_SHA256:
        raise A3BCompletionError(f"tracked diff fingerprint drifted: {fingerprint}")
    return {
        "branch": branch,
        "head": head,
        "cached_remote_head": remote,
        "staged_paths": sorted(staged),
        "tracked_paths": sorted(tracked),
        "tracked_diff_sha256": fingerprint,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo.resolve()
    python = args.python.resolve()
    repository_before = verify_repository(repo)
    checks: dict[str, object] = {}

    checks["py_compile"] = run(
        [
            str(python),
            "-m",
            "py_compile",
            *QUALITY_FILES,
        ],
        cwd=repo,
    )
    checks["ruff"] = run(
        [
            str(python),
            "-m",
            "ruff",
            "check",
            *QUALITY_FILES,
        ],
        cwd=repo,
    )
    checks["ruff_format"] = run(
        [
            str(python),
            "-m",
            "ruff",
            "format",
            "--check",
            *QUALITY_FILES,
        ],
        cwd=repo,
    )
    checks["pytest"] = run(
        [
            str(python),
            "-m",
            "pytest",
            "-q",
            "-W",
            "error",
            "tests/research/test_rd18_p3x_a3b.py",
        ],
        cwd=repo,
    )

    common = [
        str(python),
        "scripts/research/run_rd18_p3x_a3b.py",
        "--repo-root",
        str(repo),
        "--a1-runtime",
        str(args.a1_runtime.resolve()),
        "--a2-runtime",
        str(args.a2_runtime.resolve()),
        "--a3-input-dir",
        str(args.a3_input_dir.resolve()),
        "--a3a-runtime",
        str(args.a3a_runtime.resolve()),
        "--output-dir",
        str(args.output_dir.resolve()),
    ]
    checks["preflight"] = run(
        [*common, "--preflight-only"],
        cwd=repo,
    )
    checks["materialize"] = run(
        [
            *common,
            "--write-ledgers",
            "--replace-output",
        ],
        cwd=repo,
    )
    checks["validator"] = run(
        [
            str(python),
            "scripts/research/validate_rd18_p3x_a3b.py",
            "--output-dir",
            str(args.output_dir.resolve()),
            "--offline",
        ],
        cwd=repo,
    )

    repository_after = verify_repository(repo)
    report_path = args.output_dir.resolve() / "rd18-p3x-a3b-runtime-report-v1.json"
    validation_path = args.output_dir.resolve() / "a3b-authorization-decision.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    decision = json.loads(validation_path.read_text(encoding="utf-8"))
    passed = (
        report.get("passed") is True
        and decision.get("passed") is True
        and report.get("next_stage") == "RD18_P3X_A3_REAUTHORIZATION_REVIEW"
    )
    summary = {
        "schema_version": "rd18-p3x-a3b-completion-v1",
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "repository_before": repository_before,
        "repository_after": repository_after,
        "checks": checks,
        "runtime_report": report,
        "authorization_decision": decision,
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "next_stage": report.get("next_stage"),
    }
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except A3BCompletionError as exc:
        print(f"A3B_COMPLETION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
