from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast

EXPECTED_BRANCH: Final = "research/rd09b-market-level-native-chain-feasibility-v2"
IMPLEMENTATION_SUBJECT: Final = "research(rd16k): add capital efficiency bull capture remediation"
RESULT_SUBJECT: Final = "research(rd16k): complete capital efficiency bull capture remediation"
GENERATED_DATA: Final = Path("data/research/rd16k")
GENERATED_REPORTS: Final = (
    Path("reports/research/rd16k-capital-efficiency-bull-capture-methodology-v1.md"),
    Path("reports/research/rd16k-capital-efficiency-bull-capture-results-v1.md"),
    Path("reports/research/rd16k-capital-cost-audit-v1.md"),
    Path("reports/research/rd16k-bull-capture-audit-v1.md"),
    Path("reports/research/rd16k-carry-forward-decisions-v1.md"),
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
    path = repo / GENERATED_DATA / "rd16k-final-report-v1.json"
    if not path.is_file():
        raise CompletionError(f"Missing RD16-K final report: {path}")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CompletionError("RD16-K final report must be an object.")
    report = cast(dict[str, object], raw)
    expected = {
        "decision": (
            "RD16K_COMPOSITE_ALPHA_V2_CAPITAL_EFFICIENCY_AND_BULL_CAPTURE_REMEDIATION_COMPLETED"
        ),
        "technical_status": "COMPLETED",
        "evidence_classification": ("CAPITAL_EFFICIENCY_AND_BULL_CAPTURE_EVIDENCE_EXTRACTED"),
        "architecture_id": "COMPOSITE_ALPHA_V2",
        "variants_evaluated": 10,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "baseline_replay_match": True,
        "baseline_economic_match": True,
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise CompletionError(f"Unexpected RD16-K report field {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise CompletionError("RD16-K technical_gates is missing.")
    for key in (
        "rd16j_ready",
        "rd16j_outputs_verified",
        "rd16i_local_candidates_verified",
        "all_ten_variants_evaluated",
        "baseline_exit_replay_match",
        "baseline_economic_match",
        "deterministic_inputs_unchanged",
        "sealed_cutoff_respected",
        "same_symbol_overlap_prohibited",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise CompletionError(f"RD16-K technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
        "production_authorized",
    ):
        if technical.get(key) is True:
            raise CompletionError(f"RD16-K forbidden flag is true: {key}")
    return report


def _generated_paths(repo: Path) -> list[Path]:
    data_root = repo / GENERATED_DATA
    if not data_root.is_dir():
        raise CompletionError(f"Missing RD16-K directory: {data_root}")
    paths = sorted(path.relative_to(repo) for path in data_root.iterdir() if path.is_file())
    for report in GENERATED_REPORTS:
        if not (repo / report).is_file():
            raise CompletionError(f"Missing RD16-K report: {report}")
        paths.append(report)
    return sorted(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run, validate, commit and push RD16-K.")
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
        raise CompletionError("Local and remote heads differ before RD16-K.")

    subject = _git(repo, "log", "-1", "--pretty=%s")
    if subject != IMPLEMENTATION_SUBJECT:
        raise CompletionError("RD16-K implementation commit is not at HEAD: " + subject)

    tracked = _git(repo, "status", "--short", "--untracked-files=no")
    if tracked:
        raise CompletionError("Tracked changes exist before RD16-K completion:\n" + tracked)

    python = _python(repo)
    targets = (
        "src/spotbot/research/rd16k_remediation.py",
        "src/spotbot/research/rd16k_evaluation.py",
        "scripts/research/run_rd16k_capital_efficiency_bull_capture.py",
        "scripts/research/complete_rd16k_capital_efficiency_bull_capture.py",
        "tests/research/test_rd16k_capital_efficiency_bull_capture.py",
    )
    _run((python, "-m", "py_compile", *targets), cwd=repo)
    _run((python, "-m", "ruff", "check", *targets), cwd=repo)
    _run((python, "-m", "ruff", "format", "--check", *targets), cwd=repo)
    _run(
        (
            python,
            "-m",
            "mypy",
            "src/spotbot/research/rd16k_remediation.py",
            "src/spotbot/research/rd16k_evaluation.py",
            "--strict",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16k_capital_efficiency_bull_capture.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "scripts/research/run_rd16k_capital_efficiency_bull_capture.py",
            "--repo",
            str(repo),
        ),
        cwd=repo,
    )
    _run(
        (python, "-m", "pytest", "tests/research", "-q", "-W", "error"),
        cwd=repo,
    )
    _run((python, "-m", "pytest", "-q", "-W", "error"), cwd=repo)
    _git(repo, "diff", "--check", capture=False)

    report = _load_report(repo)
    generated = _generated_paths(repo)
    data_paths = [path.as_posix() for path in generated if path.as_posix().startswith("data/")]
    report_paths = [path.as_posix() for path in generated if path.as_posix().startswith("reports/")]
    if not data_paths:
        raise CompletionError("RD16-K generated data path list is empty.")
    _git(repo, "add", "--", *data_paths, capture=False)
    if report_paths:
        _git(repo, "add", "-f", "--", *report_paths, capture=False)
    _git(repo, "diff", "--cached", "--check", capture=False)

    staged = _git(repo, "diff", "--cached", "--name-only").replace("\\", "/")
    if "data/research/rd16k/rd16k-final-report-v1.json" not in staged:
        raise CompletionError("RD16-K final report was not staged.")

    _git(repo, "commit", "-m", RESULT_SUBJECT, capture=False)
    result_commit = _git(repo, "rev-parse", "HEAD")
    if not arguments.no_push:
        _git(repo, "push", "origin", EXPECTED_BRANCH, capture=False)
        _git(repo, "fetch", "origin", EXPECTED_BRANCH, capture=False)
        remote_after = _git(repo, "rev-parse", f"origin/{EXPECTED_BRANCH}")
        if result_commit != remote_after:
            raise CompletionError("RD16-K result commit did not reach remote.")

    tracked_after = _git(repo, "status", "--short", "--untracked-files=no")
    if tracked_after:
        raise CompletionError("Tracked changes remain after RD16-K:\n" + tracked_after)

    print("\nRD16-K COMPLETE")
    print(f"commit={result_commit}")
    for key in (
        "decision",
        "architecture_id",
        "variants_evaluated",
        "retained_variant_count",
        "promising_variant_count",
        "retained_variants",
        "strategic_objective_met_count",
        "next_stage",
    ):
        print(f"{key}={report[key]}")


if __name__ == "__main__":
    main()
