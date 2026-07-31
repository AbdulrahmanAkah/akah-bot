from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

EXPECTED_BRANCH = "research/rd09b-market-level-native-chain-feasibility-v2"
IMPLEMENTATION_SUBJECT = "research(rd16e): add causal component extraction"
RESULT_SUBJECT = "research(rd16e): complete causal component extraction"
GENERATED_DATA = Path("data/research/rd16e")
GENERATED_REPORTS = (
    Path("reports/research/rd16e-component-extraction-results-v1.md"),
    Path("reports/research/rd16e-component-carry-forward-decisions-v1.md"),
    Path("reports/research/rd16e-remediation-causality-audit-v1.md"),
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
    path = repo / GENERATED_DATA / "rd16e-final-report-v1.json"
    if not path.is_file():
        raise CompletionError(f"Missing RD16-E final report: {path}")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CompletionError("RD16-E final report must be an object.")
    report = cast(dict[str, object], raw)
    expected = {
        "decision": ("RD16E_INTRADAY_FAMILY_REMEDIATION_AND_COMPONENT_EXTRACTION_COMPLETED"),
        "technical_status": "COMPLETED",
        "evidence_classification": "COMPONENT_EVIDENCE_EXTRACTED",
        "families_evaluated": 4,
        "variants_per_family": 10,
        "variants_evaluated": 40,
        "winner_selected": False,
        "optimization_performed": False,
        "production_authorized": False,
        "next_stage": "RD16F_REGISTERED_INTRADAY_COMPOSITE_ALPHA_ARCHITECTURE",
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise CompletionError(f"Unexpected RD16-E report field {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise CompletionError("RD16-E technical_gates is missing.")
    required_true = (
        "all_four_families_evaluated",
        "all_ten_variants_evaluated_per_family",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "rd16d_outputs_verified",
        "rd16d_local_enriched_ledgers_verified",
        "causal_signal_time_filters_only",
        "spot_only",
        "long_only",
    )
    for key in required_true:
        if technical.get(key) is not True:
            raise CompletionError(f"RD16-E technical gate failed: {key}")
    forbidden_true = (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
    )
    for key in forbidden_true:
        if technical.get(key) is True:
            raise CompletionError(f"RD16-E forbidden flag is true: {key}")
    return report


def _generated_paths(repo: Path) -> list[Path]:
    data_root = repo / GENERATED_DATA
    if not data_root.is_dir():
        raise CompletionError(f"Missing RD16-E directory: {data_root}")
    paths = sorted(path.relative_to(repo) for path in data_root.iterdir() if path.is_file())
    for report in GENERATED_REPORTS:
        if not (repo / report).is_file():
            raise CompletionError(f"Missing RD16-E report: {report}")
        paths.append(report)
    return sorted(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run, validate, commit and push RD16-E results.")
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
        raise CompletionError("Local and remote heads differ before RD16-E.")
    subject = _git(repo, "log", "-1", "--pretty=%s")
    if subject != IMPLEMENTATION_SUBJECT:
        raise CompletionError("RD16-E implementation commit is not at HEAD: " + subject)
    tracked = _git(repo, "status", "--short", "--untracked-files=no")
    if tracked:
        raise CompletionError("Tracked changes exist before RD16-E completion:\n" + tracked)

    python = _python(repo)
    targets = (
        "src/spotbot/research/rd16e_components.py",
        "src/spotbot/research/rd16e_evaluation.py",
        "scripts/research/run_rd16e_component_extraction.py",
        "scripts/research/complete_rd16e_component_extraction.py",
        "tests/research/test_rd16e_component_extraction.py",
    )
    _run((python, "-m", "py_compile", *targets), cwd=repo)
    _run((python, "-m", "ruff", "check", *targets), cwd=repo)
    _run((python, "-m", "ruff", "format", "--check", *targets), cwd=repo)
    _run(
        (
            python,
            "-m",
            "mypy",
            "src/spotbot/research/rd16e_components.py",
            "src/spotbot/research/rd16e_evaluation.py",
            "--strict",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16e_component_extraction.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "scripts/research/run_rd16e_component_extraction.py",
            "--repo",
            str(repo),
        ),
        cwd=repo,
    )
    report = _load_report(repo)
    _run((python, "-m", "pytest", "tests/research", "-q", "-W", "error"), cwd=repo)
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
        raise CompletionError("Unexpected RD16-E staged paths:\n" + "\n".join(unexpected))
    required_staged = {
        "data/research/rd16e/component-variant-summary.csv",
        "data/research/rd16e/component-decisions.csv",
        "data/research/rd16e/rd16e-final-report-v1.json",
        "data/research/rd16e/validation-report.json",
        "data/research/rd16e/output-hashes.json",
        "reports/research/rd16e-component-extraction-results-v1.md",
        "reports/research/rd16e-component-carry-forward-decisions-v1.md",
        "reports/research/rd16e-remediation-causality-audit-v1.md",
    }
    missing_required = sorted(required_staged.difference(staged))
    if missing_required:
        raise CompletionError(
            "Required RD16-E outputs were not staged:\n" + "\n".join(missing_required)
        )

    _git(repo, "commit", "-m", RESULT_SUBJECT, capture=False)
    commit = _git(repo, "rev-parse", "HEAD")
    if not arguments.no_push:
        _git(repo, "push", "origin", EXPECTED_BRANCH, capture=False)
        _git(repo, "fetch", "origin", EXPECTED_BRANCH, capture=False)
        remote_after = _git(repo, "rev-parse", f"origin/{EXPECTED_BRANCH}")
        if remote_after != commit:
            raise CompletionError("RD16-E result commit did not reach remote.")

    print(
        "\nRD16-E COMPLETE\n"
        f"commit={commit}\n"
        f"decision={report['decision']}\n"
        f"retained_component_count={report['retained_component_count']}\n"
        f"promising_component_count={report['promising_component_count']}\n"
        f"carry_forward_component_count={report['carry_forward_component_count']}\n"
        f"strategic_objective_met_count={report['strategic_objective_met_count']}\n"
        f"next_stage={report['next_stage']}"
    )


if __name__ == "__main__":
    main()
