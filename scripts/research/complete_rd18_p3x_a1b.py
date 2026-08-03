from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Complete focused RD18-P3X-A1B validation and ledger build."
    )
    result.add_argument("--repo", type=Path, required=True)
    result.add_argument("--python", default=sys.executable)
    result.add_argument(
        "--a1-runtime",
        type=Path,
        default=None,
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=None,
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
    record: dict[str, Any] = {
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
    a1_runtime = (
        args.a1_runtime.resolve()
        if args.a1_runtime is not None
        else repo / "data/research/rd18_p3x_a1_runtime"
    )
    output = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else repo / "data/research/rd18_p3x_a1b_runtime"
    )

    files = [
        "src/spotbot/research/rd18_p3x_a1b_asset_gate.py",
        "scripts/research/run_rd18_p3x_a1b.py",
        "scripts/research/validate_rd18_p3x_a1b.py",
        "scripts/research/complete_rd18_p3x_a1b.py",
        "tests/research/test_rd18_p3x_a1b.py",
    ]
    commands = [
        [python, "-m", "py_compile", *files],
        [python, "-m", "ruff", "check", *files],
        [python, "-m", "ruff", "format", "--check", *files],
        [
            python,
            "-m",
            "mypy",
            "--strict",
            "src/spotbot/research/rd18_p3x_a1b_asset_gate.py",
        ],
        [
            python,
            "-m",
            "pytest",
            "-q",
            "-W",
            "error",
            "tests/research/test_rd18_p3x_a1b.py",
        ],
        [
            python,
            "scripts/research/run_rd18_p3x_a1b.py",
            "--repo-root",
            str(repo),
            "--a1-runtime",
            str(a1_runtime),
            "--output-dir",
            str(output),
            "--write-ledgers",
        ],
        [
            python,
            "scripts/research/validate_rd18_p3x_a1b.py",
            "--output-dir",
            str(output),
            "--offline",
        ],
        ["git", "diff", "--check"],
    ]
    records = [execute(command, cwd=repo) for command in commands]
    report = json.loads(
        (output / "rd18-p3x-a1b-runtime-report-v1.json").read_text(encoding="utf-8")
    )
    result = {
        "schema_version": "rd18-p3x-a1b-completion-v1",
        "passed": True,
        "commands": records,
        "output_dir": str(output),
        "symbols": report["symbols"],
        "months": report["months"],
        "eligibility_rows": report["eligibility_rows"],
        "eligible_rows": report["eligible_rows"],
        "rejection_rows": report["rejection_rows"],
        "strategy_candidate_generation_executed": False,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
        "production_authorized": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
