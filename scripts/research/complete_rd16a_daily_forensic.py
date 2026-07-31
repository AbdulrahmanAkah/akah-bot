from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

EXPECTED_BRANCH = "research/rd09b-market-level-native-chain-feasibility-v2"
RESULT_SUBJECT = "research(rd16a): complete daily forensic closure"

GENERATED_DATA = Path("data/research/rd16a")
GENERATED_REPORTS = (
    Path("reports/research/rd16a-daily-forensic-methodology-v1.md"),
    Path("reports/research/rd16a-daily-forensic-results-v1.md"),
    Path("reports/research/rd16a-daily-forensic-trade-audit-v1.md"),
    Path("reports/research/rd15-strategic-reclassification-v1.md"),
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
    candidate = repo / ".venv" / "Scripts" / "python.exe"
    if candidate.is_file():
        return str(candidate)
    candidate = repo / ".venv" / "bin" / "python"
    if candidate.is_file():
        return str(candidate)
    return sys.executable


def _validate_report(repo: Path) -> dict[str, object]:
    path = repo / GENERATED_DATA / "rd16a-final-report-v1.json"
    if not path.is_file():
        raise CompletionError(f"Missing RD16-A final report: {path}")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CompletionError("RD16-A final report must be a JSON object.")
    report = dict(raw)
    expected = {
        "decision": "RD16A_DAILY_FORENSIC_CLOSURE_COMPLETED",
        "technical_status": "COMPLETED",
        "rd15_engineering_status": "PASS",
        "rd15_primary_architecture_status": "FAILED_FOR_STRATEGIC_OBJECTIVE",
        "evidence_classification": "USEFUL_COMPONENTS_ONLY",
        "next_stage": "RD16B_HOURLY_DATA_READINESS_AND_CAUSAL_AGGREGATION",
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise CompletionError(f"Unexpected RD16-A report field {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise CompletionError("RD16-A technical_gates is missing.")
    if technical.get("deterministic_replay_match") is not True:
        raise CompletionError("RD16-A deterministic replay did not pass.")
    if technical.get("frozen_inputs_unchanged") is not True:
        raise CompletionError("RD16-A frozen inputs changed.")
    return report


def _generated_paths(repo: Path) -> list[Path]:
    data_root = repo / GENERATED_DATA
    if not data_root.is_dir():
        raise CompletionError(f"Missing generated data directory: {data_root}")
    paths = sorted(path.relative_to(repo) for path in data_root.iterdir() if path.is_file())
    for report in GENERATED_REPORTS:
        if not (repo / report).is_file():
            raise CompletionError(f"Missing generated report: {report}")
        paths.append(report)
    return sorted(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run, validate, commit, and push the complete RD16-A closure."
    )
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--no-push", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").exists():
        raise CompletionError(f"Not a Git repository: {repo}")

    branch = _git(repo, "branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise CompletionError(f"Expected branch {EXPECTED_BRANCH}, found {branch}")

    _git(repo, "fetch", "origin", EXPECTED_BRANCH, capture=False)
    local = _git(repo, "rev-parse", "HEAD")
    remote = _git(repo, "rev-parse", f"origin/{EXPECTED_BRANCH}")
    if local != remote:
        raise CompletionError(
            "Local and remote branch heads differ. Pull or resolve the branch before RD16-A."
        )

    tracked_status = _git(repo, "status", "--short", "--untracked-files=no")
    if tracked_status:
        raise CompletionError(
            "Tracked working tree changes exist before RD16-A.\n" + tracked_status
        )

    python = _python(repo)
    targets = (
        "src/spotbot/research/rd16a_common.py",
        "src/spotbot/research/rd16a_analysis.py",
        "src/spotbot/research/rd16a_reporting.py",
        "src/spotbot/research/rd16a_daily_forensic.py",
        "scripts/research/run_rd16a_daily_forensic.py",
        "scripts/research/complete_rd16a_daily_forensic.py",
        "tests/research/test_rd16a_daily_forensic.py",
    )
    _run((python, "-m", "py_compile", *targets), cwd=repo)
    _run((python, "-m", "ruff", "check", *targets), cwd=repo)
    _run((python, "-m", "ruff", "format", "--check", *targets), cwd=repo)
    _run(
        (
            python,
            "-m",
            "mypy",
            "src/spotbot/research/rd16a_common.py",
            "src/spotbot/research/rd16a_analysis.py",
            "src/spotbot/research/rd16a_reporting.py",
            "src/spotbot/research/rd16a_daily_forensic.py",
            "--strict",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "pytest",
            "tests/research/test_rd16a_daily_forensic.py",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "scripts/research/run_rd16a_daily_forensic.py",
            "--repo",
            str(repo),
        ),
        cwd=repo,
    )
    report = _validate_report(repo)
    _run((python, "-m", "pytest", "tests/research", "-q", "-W", "error"), cwd=repo)
    _run((python, "-m", "pytest", "-q", "-W", "error"), cwd=repo)
    _git(repo, "diff", "--check", capture=False)

    generated = _generated_paths(repo)
    data_paths = [path.as_posix() for path in generated if path.parts[0] == "data"]
    report_paths = [path.as_posix() for path in generated if path.parts[0] == "reports"]
    _git(repo, "add", "--", *data_paths, capture=False)
    _git(repo, "add", "-f", "--", *report_paths, capture=False)
    _git(repo, "diff", "--cached", "--check", capture=False)

    staged = [
        line.replace("\\", "/")
        for line in _git(
            repo,
            "diff",
            "--cached",
            "--name-only",
        ).splitlines()
    ]
    allowed = set([*data_paths, *report_paths])
    unexpected = sorted(set(staged).difference(allowed))
    if unexpected:
        raise CompletionError("Unexpected staged paths:\n" + "\n".join(unexpected))
    required_staged = {
        "data/research/rd16a/rd16a-final-report-v1.json",
        "data/research/rd16a/validation-report.json",
        "data/research/rd16a/output-hashes.json",
        "data/research/rd16a/yearly-bull-capture.csv",
        "reports/research/rd16a-daily-forensic-results-v1.md",
        "reports/research/rd16a-daily-forensic-trade-audit-v1.md",
    }
    missing_required = sorted(required_staged.difference(staged))
    if missing_required:
        raise CompletionError(
            "Required RD16-A outputs were not staged:\n" + "\n".join(missing_required)
        )

    _git(repo, "commit", "-m", RESULT_SUBJECT, capture=False)
    commit = _git(repo, "rev-parse", "HEAD")
    if not arguments.no_push:
        _git(repo, "push", "origin", EXPECTED_BRANCH, capture=False)
        _git(repo, "fetch", "origin", EXPECTED_BRANCH, capture=False)
        remote_after = _git(repo, "rev-parse", f"origin/{EXPECTED_BRANCH}")
        if commit != remote_after:
            raise CompletionError("Remote branch did not reach the RD16-A result commit.")

    print(
        "\nRD16-A COMPLETE\n"
        f"commit={commit}\n"
        f"decision={report['decision']}\n"
        f"strategic_status={report['rd15_primary_architecture_status']}\n"
        f"next_stage={report['next_stage']}"
    )


if __name__ == "__main__":
    main()
