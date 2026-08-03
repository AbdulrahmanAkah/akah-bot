from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Complete focused RD18-P3X-A2 generator build and validation."
    )
    result.add_argument("--repo", type=Path, required=True)
    result.add_argument("--python", default=sys.executable)
    result.add_argument("--a1-runtime", type=Path, default=None)
    result.add_argument("--a1b-runtime", type=Path, default=None)
    result.add_argument("--a1c-runtime", type=Path, default=None)
    result.add_argument("--output-dir", type=Path, default=None)
    return result


def execute(
    command: list[str],
    *,
    cwd: Path,
    stream: bool = False,
) -> dict[str, Any]:
    if stream:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            check=False,
        )
        record: dict[str, Any] = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": "STREAMED",
            "stderr": "STREAMED",
        }
    else:
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
    a1 = (
        args.a1_runtime.resolve()
        if args.a1_runtime is not None
        else repo / "data/research/rd18_p3x_a1_runtime"
    )
    a1b = (
        args.a1b_runtime.resolve()
        if args.a1b_runtime is not None
        else repo / "data/research/rd18_p3x_a1b_runtime"
    )
    a1c = (
        args.a1c_runtime.resolve()
        if args.a1c_runtime is not None
        else repo / "data/research/rd18_p3x_a1c_runtime"
    )
    output = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else repo / "data/research/rd18_p3x_a2_runtime"
    )

    files = [
        "src/spotbot/research/rd18_p3x_a2_generator.py",
        "scripts/research/run_rd18_p3x_a2.py",
        "scripts/research/validate_rd18_p3x_a2.py",
        "scripts/research/complete_rd18_p3x_a2.py",
        "tests/research/test_rd18_p3x_a2.py",
    ]
    records: list[dict[str, Any]] = []
    commands = [
        [python, "-m", "py_compile", *files],
        [python, "-m", "ruff", "check", *files],
        [python, "-m", "ruff", "format", "--check", *files],
        [
            python,
            "-m",
            "mypy",
            "--strict",
            "src/spotbot/research/rd18_p3x_a2_generator.py",
        ],
        [
            python,
            "-m",
            "pytest",
            "-q",
            "-W",
            "error",
            "tests/research/test_rd18_p3x_a2.py",
        ],
        [
            python,
            "scripts/research/run_rd18_p3x_a2.py",
            "--repo-root",
            str(repo),
            "--a1-runtime",
            str(a1),
            "--a1b-runtime",
            str(a1b),
            "--a1c-runtime",
            str(a1c),
            "--output-dir",
            str(output),
            "--preflight-only",
        ],
    ]
    for command in commands:
        records.append(execute(command, cwd=repo))

    print("A2 quality and preflight passed.", flush=True)
    records.append(
        execute(
            [
                python,
                "scripts/research/run_rd18_p3x_a2.py",
                "--repo-root",
                str(repo),
                "--a1-runtime",
                str(a1),
                "--a1b-runtime",
                str(a1b),
                "--a1c-runtime",
                str(a1c),
                "--output-dir",
                str(output),
                "--write-ledgers",
                "--resume",
                "--progress-every",
                "10",
            ],
            cwd=repo,
            stream=True,
        )
    )
    records.append(
        execute(
            [
                python,
                "scripts/research/validate_rd18_p3x_a2.py",
                "--output-dir",
                str(output),
                "--a1b-runtime",
                str(a1b),
                "--a1c-runtime",
                str(a1c),
                "--offline",
            ],
            cwd=repo,
        )
    )
    records.append(execute(["git", "diff", "--check"], cwd=repo))

    report = json.loads((output / "rd18-p3x-a2-runtime-report-v1.json").read_text(encoding="utf-8"))
    validation = json.loads(records[-2]["stdout"])
    result = {
        "schema_version": "rd18-p3x-a2-completion-v1",
        "passed": True,
        "commands": records,
        "output_dir": str(output),
        "ready_symbols_processed": report["ready_symbols_processed"],
        "raw_signal_rows": report["raw_signal_rows"],
        "selected_candidate_rows": report["selected_candidate_rows"],
        "engine_candidate_counts": report["engine_candidate_counts"],
        "next_stage": report["next_stage"],
        "validation_passed": validation["passed"],
        "network_requests": 0,
        "strategy_candidate_generation_executed": True,
        "strategy_replay_executed": False,
        "trade_routing_executed": False,
        "return_calculation_executed": False,
        "production_authorized": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
