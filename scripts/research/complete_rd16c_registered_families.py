from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

EXPECTED_BRANCH = "research/rd09b-market-level-native-chain-feasibility-v2"
IMPLEMENTATION_SUBJECT = "research(rd16c): add registered intraday family smoke tests"
RESULT_SUBJECT = "research(rd16c): complete registered intraday family smoke tests"
GENERATED_DATA = Path("data/research/rd16c")
GENERATED_REPORTS = (
    Path("reports/research/rd16c-registered-families-methodology-v1.md"),
    Path("reports/research/rd16c-registered-families-results-v1.md"),
    Path("reports/research/rd16c-frozen-family-registry-v1.md"),
    Path("reports/research/rd16c-execution-constraint-audit-v1.md"),
)


class CompletionError(RuntimeError):
    pass


def _run(
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


def _git(
    repo: Path,
    *arguments: str,
    capture: bool = True,
) -> str:
    return _run(
        ("git", *arguments),
        cwd=repo,
        capture=capture,
    )


def _python(repo: Path) -> str:
    windows = repo / ".venv" / "Scripts" / "python.exe"
    if windows.is_file():
        return str(windows)
    posix = repo / ".venv" / "bin" / "python"
    if posix.is_file():
        return str(posix)
    return sys.executable


def _load_report(repo: Path) -> dict[str, object]:
    path = repo / GENERATED_DATA / "rd16c-final-report-v1.json"
    if not path.is_file():
        raise CompletionError(f"Missing RD16-C final report: {path}")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CompletionError("RD16-C final report must be a JSON object.")
    report = cast(dict[str, object], raw)
    expected = {
        "decision": ("RD16C_REGISTERED_INTRADAY_STRATEGY_FAMILIES_SMOKE_TESTS_COMPLETED"),
        "technical_status": "COMPLETED",
        "evidence_classification": ("READY_FOR_FIXED_BASELINE"),
        "families_passed": 4,
        "families_total": 4,
        "next_stage": ("RD16D_FIXED_INTRADAY_FAMILY_BASELINE_EVALUATION"),
        "performance_used_as_gate": False,
        "winner_selected": False,
        "optimization_performed": False,
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise CompletionError(f"Unexpected RD16-C report field {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise CompletionError("RD16-C technical_gates is missing.")
    required_true = (
        "all_four_families_registered",
        "all_four_families_smoke_pass",
        "all_constraints_pass",
        "all_causal_checks_pass",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "spot_only",
        "long_only",
    )
    for key in required_true:
        if technical.get(key) is not True:
            raise CompletionError(f"RD16-C technical gate failed: {key}")
    forbidden_true = (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
    )
    for key in forbidden_true:
        if technical.get(key) is True:
            raise CompletionError(f"RD16-C forbidden flag is true: {key}")
    return report


def _generated_paths(repo: Path) -> list[Path]:
    data_root = repo / GENERATED_DATA
    if not data_root.is_dir():
        raise CompletionError(f"Missing RD16-C generated directory: {data_root}")
    paths = sorted(path.relative_to(repo) for path in data_root.iterdir() if path.is_file())
    for report in GENERATED_REPORTS:
        if not (repo / report).is_file():
            raise CompletionError(f"Missing RD16-C report: {report}")
        paths.append(report)
    return sorted(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run, validate, commit and push RD16-C smoke results.")
    )
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--no-push", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").is_dir():
        raise CompletionError(f"Not a Git repository: {repo}")

    branch = _git(repo, "branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise CompletionError(f"Expected branch {EXPECTED_BRANCH}, found {branch}")
    _git(repo, "fetch", "origin", EXPECTED_BRANCH, capture=False)
    local = _git(repo, "rev-parse", "HEAD")
    remote = _git(
        repo,
        "rev-parse",
        f"origin/{EXPECTED_BRANCH}",
    )
    if local != remote:
        raise CompletionError("Local and remote branch heads differ before RD16-C.")
    subject = _git(repo, "log", "-1", "--pretty=%s")
    if subject != IMPLEMENTATION_SUBJECT:
        raise CompletionError(f"RD16-C implementation commit is not at HEAD: {subject}")
    tracked_status = _git(
        repo,
        "status",
        "--short",
        "--untracked-files=no",
    )
    if tracked_status:
        raise CompletionError("Tracked changes exist before RD16-C completion:\n" + tracked_status)

    python = _python(repo)
    targets = (
        "src/spotbot/research/rd16c_common.py",
        "src/spotbot/research/rd16c_features.py",
        "src/spotbot/research/rd16c_families.py",
        "src/spotbot/research/rd16c_reporting.py",
        "src/spotbot/research/rd16c_smoke.py",
        "scripts/research/run_rd16c_registered_families.py",
        "scripts/research/complete_rd16c_registered_families.py",
        "tests/research/test_rd16c_registered_families.py",
    )
    _run((python, "-m", "py_compile", *targets), cwd=repo)
    _run((python, "-m", "ruff", "check", *targets), cwd=repo)
    _run(
        (python, "-m", "ruff", "format", "--check", *targets),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "mypy",
            "src/spotbot/research/rd16c_common.py",
            "src/spotbot/research/rd16c_features.py",
            "src/spotbot/research/rd16c_families.py",
            "src/spotbot/research/rd16c_reporting.py",
            "src/spotbot/research/rd16c_smoke.py",
            "--strict",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16c_registered_families.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "scripts/research/run_rd16c_registered_families.py",
            "--repo",
            str(repo),
        ),
        cwd=repo,
    )
    report = _load_report(repo)
    _run(
        (python, "-m", "pytest", "tests/research", "-q", "-W", "error"),
        cwd=repo,
    )
    _run((python, "-m", "pytest", "-q", "-W", "error"), cwd=repo)
    _git(repo, "diff", "--check", capture=False)

    generated = _generated_paths(repo)
    data_paths = [path.as_posix() for path in generated if path.parts[0] == "data"]
    report_paths = [path.as_posix() for path in generated if path.parts[0] == "reports"]
    _git(repo, "add", "--", *data_paths, capture=False)
    _git(repo, "add", "-f", "--", *report_paths, capture=False)
    _git(repo, "diff", "--cached", "--check", capture=False)

    staged = {
        line.replace("\\", "/")
        for line in _git(
            repo,
            "diff",
            "--cached",
            "--name-only",
        ).splitlines()
        if line
    }
    allowed = set([*data_paths, *report_paths])
    unexpected = sorted(staged.difference(allowed))
    if unexpected:
        raise CompletionError("Unexpected staged RD16-C paths:\n" + "\n".join(unexpected))
    required = {
        "data/research/rd16c/family-smoke-summary.csv",
        "data/research/rd16c/asset-family-coverage.csv",
        "data/research/rd16c/causality-audit.csv",
        "data/research/rd16c/constraint-audit.csv",
        "data/research/rd16c/local-ledger-manifest-v1.json",
        "data/research/rd16c/rd16c-final-report-v1.json",
        "data/research/rd16c/validation-report.json",
        "data/research/rd16c/output-hashes.json",
        "reports/research/rd16c-registered-families-results-v1.md",
        "reports/research/rd16c-frozen-family-registry-v1.md",
        "reports/research/rd16c-execution-constraint-audit-v1.md",
    }
    missing = sorted(required.difference(staged))
    if missing:
        raise CompletionError("Required RD16-C outputs were not staged:\n" + "\n".join(missing))

    _git(repo, "commit", "-m", RESULT_SUBJECT, capture=False)
    commit = _git(repo, "rev-parse", "HEAD")
    if not arguments.no_push:
        _git(repo, "push", "origin", EXPECTED_BRANCH, capture=False)
        _git(repo, "fetch", "origin", EXPECTED_BRANCH, capture=False)
        remote_after = _git(
            repo,
            "rev-parse",
            f"origin/{EXPECTED_BRANCH}",
        )
        if remote_after != commit:
            raise CompletionError("RD16-C result commit did not reach remote.")

    print(
        "\nRD16-C COMPLETE\n"
        f"commit={commit}\n"
        f"decision={report['decision']}\n"
        "evidence_classification="
        f"{report['evidence_classification']}\n"
        f"families_passed={report['families_passed']}/"
        f"{report['families_total']}\n"
        f"next_stage={report['next_stage']}"
    )


if __name__ == "__main__":
    main()
