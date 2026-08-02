from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

STAGE = "RD18_P3X_FULL_UNIVERSE_CANDIDATE_PIPELINE_AND_DATA_READINESS"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Run the complete local RD18-P3X readiness validation workflow."
    )
    result.add_argument("--repo", type=Path, required=True)
    result.add_argument("--python", default=sys.executable)
    result.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to <repo>/data/research/rd18_p3x_runtime.",
    )
    result.add_argument(
        "--skip-full-research-suite",
        action="store_true",
        help="Skip the full tests/research suite; focused P3X tests remain mandatory.",
    )
    return result


def execute(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    record = {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        print(json.dumps(record, indent=2, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(completed.returncode)
    return record


def main() -> int:
    args = parser().parse_args()
    repo = args.repo.resolve()
    python = str(args.python)
    output = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else repo / "data" / "research" / "rd18_p3x_runtime"
    )
    files = [
        "src/spotbot/research/rd18_p3x_readiness.py",
        "scripts/research/run_rd18_p3x_readiness.py",
        "scripts/research/validate_rd18_p3x_readiness.py",
        "scripts/research/complete_rd18_p3x_readiness.py",
        "tests/research/test_rd18_p3x_readiness.py",
    ]
    commands: list[list[str]] = [
        [python, "-m", "py_compile", *files],
        [python, "-m", "ruff", "check", *files],
        [python, "-m", "ruff", "format", "--check", *files],
        [python, "-m", "mypy", "--strict", "src/spotbot/research/rd18_p3x_readiness.py"],
        [
            python,
            "-m",
            "pytest",
            "-q",
            "-W",
            "error",
            "tests/research/test_rd18_p3x_readiness.py",
        ],
        [
            python,
            "scripts/research/run_rd18_p3x_readiness.py",
            "--offline",
            "--repo-root",
            str(repo),
            "--output-dir",
            str(output),
        ],
        [
            python,
            "scripts/research/validate_rd18_p3x_readiness.py",
            "--offline",
            "--output-dir",
            str(output),
        ],
    ]
    if not args.skip_full_research_suite:
        commands.append([python, "-m", "pytest", "-q", "-W", "error", "tests/research"])
    commands.append(["git", "diff", "--check"])
    records = [execute(command, cwd=repo) for command in commands]
    report = json.loads(
        (output / "rd18-p3x-runtime-report-v1.json").read_text(encoding="utf-8")
    )
    result = {
        "stage": STAGE,
        "passed": True,
        "commands": records,
        "runtime_decision": report["decision"],
        "next_stage": report["next_stage"],
        "output_dir": str(output),
        "strategy_replay_authorized": False,
        "production_authorized": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
