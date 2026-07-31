from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast

EXPECTED_BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
IMPLEMENTATION_SUBJECT: Final = "research(rd16g): add fixed composite alpha baseline"
RESULT_SUBJECT: Final = "research(rd16g): complete fixed composite alpha baseline"
GENERATED_DATA: Final = Path("data/research/rd16g")
GENERATED_REPORTS: Final = (
    Path("reports/research/rd16g-fixed-composite-baseline-methodology-v1.md"),
    Path("reports/research/rd16g-fixed-composite-baseline-results-v1.md"),
    Path("reports/research/rd16g-robustness-cost-audit-v1.md"),
    Path("reports/research/rd16g-engine-attribution-audit-v1.md"),
    Path("reports/research/rd16g-benchmark-bull-capture-audit-v1.md"),
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


def _git(repo: Path, *arguments: str, capture: bool = True) -> str:
    return _run(("git", *arguments), cwd=repo, capture=capture)


def _python(repo: Path) -> str:
    windows = repo / ".venv" / "Scripts" / "python.exe"
    if windows.is_file():
        return str(windows)
    posix = repo / ".venv" / "bin" / "python"
    if posix.is_file():
        return str(posix)
    return sys.executable


def _load_report(repo: Path) -> dict[str, object]:
    path = repo / GENERATED_DATA / "rd16g-final-report-v1.json"
    if not path.is_file():
        raise CompletionError(f"Missing RD16-G final report: {path}")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CompletionError("RD16-G final report must be an object.")
    report = cast(dict[str, object], raw)
    expected = {
        "decision": "RD16G_FIXED_COMPOSITE_ALPHA_BASELINE_EVALUATION_COMPLETED",
        "technical_status": "COMPLETED",
        "evidence_classification": "COMPREHENSIVE_COMPOSITE_BASELINE_COMPLETE",
        "architecture_id": "COMPOSITE_ALPHA_V1",
        "engines_evaluated": 2,
        "optimization_performed": False,
        "architecture_changed": False,
        "winner_selected": False,
        "production_authorized": False,
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise CompletionError(f"Unexpected RD16-G report field {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise CompletionError("RD16-G technical_gates is missing.")
    for key in (
        "rd16f_ready",
        "rd16f_outputs_verified",
        "rd16f_local_ledgers_verified",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "sealed_cutoff_respected",
        "both_engines_evaluated",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise CompletionError(f"RD16-G technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "architecture_changed",
        "winner_selected",
        "production_authorized",
    ):
        if technical.get(key) is True:
            raise CompletionError(f"RD16-G forbidden flag is true: {key}")
    return report


def _generated_paths(repo: Path) -> list[Path]:
    data_root = repo / GENERATED_DATA
    if not data_root.is_dir():
        raise CompletionError(f"Missing RD16-G directory: {data_root}")
    paths = sorted(path.relative_to(repo) for path in data_root.iterdir() if path.is_file())
    for report in GENERATED_REPORTS:
        if not (repo / report).is_file():
            raise CompletionError(f"Missing RD16-G report: {report}")
        paths.append(report)
    return sorted(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run, validate, commit and push RD16-G.")
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
    remote = _git(repo, "rev-parse", f"origin/{EXPECTED_BRANCH}")
    if local != remote:
        raise CompletionError("Local and remote heads differ before RD16-G.")
    subject = _git(repo, "log", "-1", "--pretty=%s")
    if subject != IMPLEMENTATION_SUBJECT:
        raise CompletionError("RD16-G implementation commit is not at HEAD: " + subject)
    tracked = _git(repo, "status", "--short", "--untracked-files=no")
    if tracked:
        raise CompletionError("Tracked changes exist before RD16-G completion:\n" + tracked)

    python = _python(repo)
    targets = (
        "src/spotbot/research/rd16g_evaluation.py",
        "scripts/research/run_rd16g_fixed_composite_baseline.py",
        "scripts/research/complete_rd16g_fixed_composite_baseline.py",
        "tests/research/test_rd16g_fixed_composite_baseline.py",
    )
    _run((python, "-m", "py_compile", *targets), cwd=repo)
    _run((python, "-m", "ruff", "check", *targets), cwd=repo)
    _run((python, "-m", "ruff", "format", "--check", *targets), cwd=repo)
    _run(
        (python, "-m", "mypy", "src/spotbot/research/rd16g_evaluation.py", "--strict"),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16g_fixed_composite_baseline.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "scripts/research/run_rd16g_fixed_composite_baseline.py",
            "--repo",
            str(repo),
        ),
        cwd=repo,
    )
    _run((python, "-m", "pytest", "tests/research", "-q", "-W", "error"), cwd=repo)
    _run((python, "-m", "pytest", "-q", "-W", "error"), cwd=repo)
    _git(repo, "diff", "--check", capture=False)
    report = _load_report(repo)
    generated = _generated_paths(repo)
    data_paths = [path.as_posix() for path in generated if path.as_posix().startswith("data/")]
    _git(repo, "add", "--", *data_paths, capture=False)
    reports = [path.as_posix() for path in generated if path.as_posix().startswith("reports/")]
    if reports:
        _git(repo, "add", "-f", "--", *reports, capture=False)
    _git(repo, "diff", "--cached", "--check", capture=False)
    _git(repo, "commit", "-m", RESULT_SUBJECT, capture=False)
    result_commit = _git(repo, "rev-parse", "HEAD")
    if not arguments.no_push:
        _git(repo, "push", "origin", EXPECTED_BRANCH, capture=False)
        _git(repo, "fetch", "origin", EXPECTED_BRANCH, capture=False)
        remote_after = _git(repo, "rev-parse", f"origin/{EXPECTED_BRANCH}")
        if result_commit != remote_after:
            raise CompletionError("RD16-G result commit did not reach remote.")
    tracked_after = _git(repo, "status", "--short", "--untracked-files=no")
    if tracked_after:
        raise CompletionError("Tracked changes remain after RD16-G:\n" + tracked_after)
    print("\nRD16-G COMPLETE")
    print(f"commit={result_commit}")
    for key in (
        "decision",
        "architecture_id",
        "classification",
        "trade_count",
        "net_return",
        "monthly_geometric_return",
        "profit_factor",
        "maximum_drawdown",
        "strategic_objective_met",
        "next_stage",
    ):
        print(f"{key}={report[key]}")


if __name__ == "__main__":
    main()
