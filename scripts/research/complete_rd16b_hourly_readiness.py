from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

EXPECTED_BRANCH = "research/rd09b-market-level-native-chain-feasibility-v2"
IMPLEMENTATION_SUBJECT = "research(rd16b): add hourly readiness and causal aggregation"
RESULT_SUBJECT = "research(rd16b): complete hourly readiness and causal aggregation"
GENERATED_DATA = Path("data/research/rd16b")
GENERATED_REPORTS = (
    Path("reports/research/rd16b-hourly-readiness-methodology-v1.md"),
    Path("reports/research/rd16b-hourly-readiness-results-v1.md"),
    Path("reports/research/rd16b-causal-aggregation-audit-v1.md"),
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
            print(
                completed.stderr,
                end="",
                file=sys.stderr,
            )
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
    path = repo / GENERATED_DATA / "rd16b-final-report-v1.json"
    if not path.is_file():
        raise CompletionError(f"Missing RD16-B final report: {path}")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CompletionError("RD16-B final report must be a JSON object.")
    report = dict(raw)
    if report.get("technical_status") != "COMPLETED":
        raise CompletionError("RD16-B technical status is not COMPLETED.")
    classification = report.get("evidence_classification")
    if classification not in {
        "READY",
        "PARTIAL",
        "BLOCKED",
    }:
        raise CompletionError(f"Unexpected RD16-B evidence classification: {classification!r}")
    decision = report.get("decision")
    if decision not in {
        ("RD16B_HOURLY_DATA_READINESS_AND_CAUSAL_AGGREGATION_COMPLETED"),
        "RD16B_DATA_REMEDIATION_REQUIRED",
    }:
        raise CompletionError(f"Unexpected RD16-B decision: {decision!r}")
    gates = report.get("technical_gates")
    if not isinstance(gates, dict):
        raise CompletionError("RD16-B technical_gates is missing.")
    if gates.get("frozen_inputs_unchanged") is not True:
        raise CompletionError("RD16-B frozen inputs changed.")
    return report


def _generated_paths(repo: Path) -> list[Path]:
    data_root = repo / GENERATED_DATA
    if not data_root.is_dir():
        raise CompletionError(f"Missing generated directory: {data_root}")
    paths = sorted(
        path.relative_to(repo)
        for path in data_root.iterdir()
        if path.is_file() and path.name != "rd16b-protocol-v1.json"
    )
    for report in GENERATED_REPORTS:
        if not (repo / report).is_file():
            raise CompletionError(f"Missing generated report: {report}")
        paths.append(report)
    return sorted(paths)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run, validate, commit and push complete RD16-B.")
    )
    parser.add_argument(
        "--repo",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--store-root",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").is_dir():
        raise CompletionError(f"Not a Git repository: {repo}")

    branch = _git(repo, "branch", "--show-current")
    if branch != EXPECTED_BRANCH:
        raise CompletionError(f"Expected branch {EXPECTED_BRANCH}, found {branch}")

    _git(
        repo,
        "fetch",
        "origin",
        EXPECTED_BRANCH,
        capture=False,
    )
    local = _git(repo, "rev-parse", "HEAD")
    remote = _git(
        repo,
        "rev-parse",
        f"origin/{EXPECTED_BRANCH}",
    )
    if local != remote:
        raise CompletionError("Local and remote branch heads differ.")
    subject = _git(
        repo,
        "log",
        "-1",
        "--pretty=%s",
    )
    if subject == RESULT_SUBJECT:
        print(f"\nRD16-B IS ALREADY COMPLETE\ncommit={local}")
        return
    if subject != IMPLEMENTATION_SUBJECT:
        raise CompletionError(f"RD16-B implementation commit is not at HEAD: {subject}")

    tracked = _git(
        repo,
        "status",
        "--short",
        "--untracked-files=no",
    )
    if tracked:
        raise CompletionError("Tracked changes exist before RD16-B:\n" + tracked)

    python = _python(repo)
    targets = (
        "src/spotbot/data/aggregation.py",
        "src/spotbot/research/rd16b_common.py",
        "src/spotbot/research/rd16b_reporting.py",
        ("src/spotbot/research/rd16b_hourly_readiness.py"),
        ("scripts/research/run_rd16b_hourly_readiness.py"),
        ("scripts/research/complete_rd16b_hourly_readiness.py"),
        "tests/test_causal_aggregation.py",
        ("tests/research/test_rd16b_hourly_readiness.py"),
    )
    _run(
        (python, "-m", "py_compile", *targets),
        cwd=repo,
    )
    _run(
        (python, "-m", "ruff", "check", *targets),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "ruff",
            "format",
            "--check",
            *targets,
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "mypy",
            "src/spotbot/data/aggregation.py",
            "src/spotbot/research/rd16b_common.py",
            ("src/spotbot/research/rd16b_reporting.py"),
            ("src/spotbot/research/rd16b_hourly_readiness.py"),
            "--strict",
        ),
        cwd=repo,
    )
    _run(
        (
            python,
            "-m",
            "pytest",
            "tests/test_causal_aggregation.py",
            ("tests/research/test_rd16b_hourly_readiness.py"),
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )

    command = [
        python,
        ("scripts/research/run_rd16b_hourly_readiness.py"),
        "--repo",
        str(repo),
    ]
    if arguments.store_root is not None:
        command.extend(
            [
                "--store-root",
                str(arguments.store_root.resolve()),
            ]
        )
    if arguments.no_download:
        command.append("--no-download")
    _run(tuple(command), cwd=repo)

    report = _load_report(repo)
    _run(
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
    _run(
        (
            python,
            "-m",
            "pytest",
            "-q",
            "-W",
            "error",
        ),
        cwd=repo,
    )
    _git(repo, "diff", "--check", capture=False)

    generated = _generated_paths(repo)
    data_paths = [path.as_posix() for path in generated if path.parts[0] == "data"]
    report_paths = [path.as_posix() for path in generated if path.parts[0] == "reports"]
    _git(
        repo,
        "add",
        "--",
        *data_paths,
        capture=False,
    )
    _git(
        repo,
        "add",
        "-f",
        "--",
        *report_paths,
        capture=False,
    )
    _git(
        repo,
        "diff",
        "--cached",
        "--check",
        capture=False,
    )

    staged = {
        line.replace("\\", "/")
        for line in _git(
            repo,
            "diff",
            "--cached",
            "--name-only",
        ).splitlines()
        if line.strip()
    }
    allowed = set(data_paths).union(report_paths)
    unexpected = sorted(staged.difference(allowed))
    if unexpected:
        raise CompletionError("Unexpected staged paths:\n" + "\n".join(unexpected))
    required = {
        ("data/research/rd16b/rd16b-final-report-v1.json"),
        ("data/research/rd16b/validation-report.json"),
        ("data/research/rd16b/output-hashes.json"),
        ("data/research/rd16b/data-readiness.csv"),
        ("data/research/rd16b/aggregation-audit.csv"),
        ("data/research/rd16b/causal-alignment-audit.csv"),
        ("reports/research/rd16b-hourly-readiness-results-v1.md"),
        ("reports/research/rd16b-causal-aggregation-audit-v1.md"),
    }
    missing = sorted(required.difference(staged))
    if missing:
        raise CompletionError("Required RD16-B outputs were not staged:\n" + "\n".join(missing))

    _git(
        repo,
        "commit",
        "-m",
        RESULT_SUBJECT,
        capture=False,
    )
    commit = _git(repo, "rev-parse", "HEAD")
    if not arguments.no_push:
        _git(
            repo,
            "push",
            "origin",
            EXPECTED_BRANCH,
            capture=False,
        )
        _git(
            repo,
            "fetch",
            "origin",
            EXPECTED_BRANCH,
            capture=False,
        )
        remote_after = _git(
            repo,
            "rev-parse",
            f"origin/{EXPECTED_BRANCH}",
        )
        if remote_after != commit:
            raise CompletionError("Remote did not reach RD16-B result commit.")

    print(
        "\nRD16-B COMPLETE\n"
        f"commit={commit}\n"
        f"decision={report['decision']}\n"
        "evidence_classification="
        f"{report['evidence_classification']}\n"
        f"assets_passed={report['assets_passed']}/"
        f"{report['assets_total']}\n"
        f"next_stage={report['next_stage']}"
    )


if __name__ == "__main__":
    main()
