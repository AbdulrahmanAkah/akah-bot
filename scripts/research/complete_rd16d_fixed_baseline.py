from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

EXPECTED_BRANCH = "research/rd09b-market-level-native-chain-feasibility-v2"
IMPLEMENTATION_SUBJECT = "research(rd16d): add comprehensive fixed family baseline"
RESULT_SUBJECT = "research(rd16d): complete comprehensive fixed family baseline"
GENERATED_DATA = Path("data/research/rd16d")
GENERATED_REPORTS = (
    Path("reports/research/rd16d-fixed-family-baseline-methodology-v1.md"),
    Path("reports/research/rd16d-fixed-family-baseline-results-v1.md"),
    Path("reports/research/rd16d-family-strengths-weaknesses-v1.md"),
    Path("reports/research/rd16d-robustness-cost-concentration-audit-v1.md"),
    Path("reports/research/rd16d-benchmark-regime-capture-audit-v1.md"),
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
    path = repo / GENERATED_DATA / "rd16d-final-report-v1.json"
    if not path.is_file():
        raise CompletionError(f"Missing RD16-D final report: {path}")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CompletionError("RD16-D final report must be an object.")
    report = cast(dict[str, object], raw)
    expected = {
        "decision": ("RD16D_FIXED_INTRADAY_FAMILY_BASELINE_EVALUATION_COMPLETED"),
        "technical_status": "COMPLETED",
        "evidence_classification": "COMPREHENSIVE_DIAGNOSTIC_COMPLETE",
        "families_evaluated": 4,
        "families_total": 4,
        "winner_selected": False,
        "optimization_performed": False,
        "next_stage": ("RD16E_INTRADAY_FAMILY_REMEDIATION_AND_COMPONENT_EXTRACTION"),
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise CompletionError(f"Unexpected RD16-D report field {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise CompletionError("RD16-D technical_gates is missing.")
    required_true = (
        "all_four_families_evaluated",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "rd16c_ledgers_verified",
        "spot_only",
        "long_only",
    )
    for key in required_true:
        if technical.get(key) is not True:
            raise CompletionError(f"RD16-D technical gate failed: {key}")
    forbidden_true = (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
    )
    for key in forbidden_true:
        if technical.get(key) is True:
            raise CompletionError(f"RD16-D forbidden flag is true: {key}")
    return report


def _generated_paths(repo: Path) -> list[Path]:
    data_root = repo / GENERATED_DATA
    if not data_root.is_dir():
        raise CompletionError(f"Missing RD16-D directory: {data_root}")
    paths = sorted(path.relative_to(repo) for path in data_root.iterdir() if path.is_file())
    for report in GENERATED_REPORTS:
        if not (repo / report).is_file():
            raise CompletionError(f"Missing RD16-D report: {report}")
        paths.append(report)
    return sorted(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run, validate, commit and push RD16-D results.")
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
        raise CompletionError("Local and remote heads differ before RD16-D.")
    subject = _git(repo, "log", "-1", "--pretty=%s")
    if subject != IMPLEMENTATION_SUBJECT:
        raise CompletionError("RD16-D implementation commit is not at HEAD: " + subject)
    tracked = _git(repo, "status", "--short", "--untracked-files=no")
    if tracked:
        raise CompletionError("Tracked changes exist before RD16-D completion:\n" + tracked)

    python = _python(repo)
    targets = (
        "src/spotbot/research/rd16d_common.py",
        "src/spotbot/research/rd16d_metrics.py",
        "src/spotbot/research/rd16d_reporting.py",
        "src/spotbot/research/rd16d_baseline.py",
        "scripts/research/run_rd16d_fixed_baseline.py",
        "scripts/research/complete_rd16d_fixed_baseline.py",
        "tests/research/test_rd16d_fixed_baseline.py",
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
            "src/spotbot/research/rd16d_common.py",
            "src/spotbot/research/rd16d_metrics.py",
            "src/spotbot/research/rd16d_reporting.py",
            "src/spotbot/research/rd16d_baseline.py",
            "--strict",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16d_fixed_baseline.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "scripts/research/run_rd16d_fixed_baseline.py",
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
        for line in _git(repo, "diff", "--cached", "--name-only").splitlines()
        if line
    }
    allowed = {*data_paths, *report_paths}
    unexpected = sorted(staged.difference(allowed))
    if unexpected:
        raise CompletionError("Unexpected RD16-D staged paths:\n" + "\n".join(unexpected))
    required_staged = {
        "data/research/rd16d/family-baseline-summary.csv",
        "data/research/rd16d/family-classification.csv",
        "data/research/rd16d/family-strengths-weaknesses.csv",
        "data/research/rd16d/rd16d-final-report-v1.json",
        "data/research/rd16d/validation-report.json",
        "data/research/rd16d/output-hashes.json",
        "reports/research/rd16d-fixed-family-baseline-results-v1.md",
        "reports/research/rd16d-family-strengths-weaknesses-v1.md",
        "reports/research/rd16d-robustness-cost-concentration-audit-v1.md",
        "reports/research/rd16d-benchmark-regime-capture-audit-v1.md",
    }
    missing_required = sorted(required_staged.difference(staged))
    if missing_required:
        raise CompletionError(
            "Required RD16-D outputs were not staged:\n" + "\n".join(missing_required)
        )

    _git(repo, "commit", "-m", RESULT_SUBJECT, capture=False)
    commit = _git(repo, "rev-parse", "HEAD")
    if not arguments.no_push:
        _git(repo, "push", "origin", EXPECTED_BRANCH, capture=False)
        _git(repo, "fetch", "origin", EXPECTED_BRANCH, capture=False)
        remote_after = _git(repo, "rev-parse", f"origin/{EXPECTED_BRANCH}")
        if remote_after != commit:
            raise CompletionError("RD16-D result commit did not reach remote.")

    print(
        "\nRD16-D COMPLETE\n"
        f"commit={commit}\n"
        f"decision={report['decision']}\n"
        f"robust_positive_baselines={report['robust_positive_baselines']}\n"
        f"fragile_positive_baselines={report['fragile_positive_baselines']}\n"
        "failed_or_capital_infeasible_baselines="
        f"{report['failed_or_capital_infeasible_baselines']}\n"
        f"strategic_objective_met_count={report['strategic_objective_met_count']}\n"
        f"next_stage={report['next_stage']}"
    )


if __name__ == "__main__":
    main()
