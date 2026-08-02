from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

STAGE = "RD18_P3X_A1_FULL_C2_HOURLY_DATA_AND_GENERATOR_BUILD"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Complete focused RD18-P3X-A1 validation.")
    result.add_argument("--repo", type=Path, required=True)
    result.add_argument("--python", default=sys.executable)
    result.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to <repo>/data/research/rd18_p3x_a1_runtime.",
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
        else repo / "data/research/rd18_p3x_a1_runtime"
    )
    files = [
        "src/spotbot/research/rd18_p3x_a1.py",
        "src/spotbot/research/rd18_p3x_a1_control.py",
        "scripts/research/run_rd18_p3x_a1.py",
        "scripts/research/validate_rd18_p3x_a1.py",
        "scripts/research/complete_rd18_p3x_a1.py",
        "tests/research/test_rd18_p3x_a1.py",
    ]
    commands = [
        [python, "-m", "py_compile", *files],
        [python, "-m", "ruff", "check", *files],
        [python, "-m", "ruff", "format", "--check", *files],
        [python, "-m", "mypy", "--strict", "src/spotbot/research/rd18_p3x_a1.py"],
        [
            python,
            "-m",
            "pytest",
            "-q",
            "-W",
            "error",
            "tests/research/test_rd18_p3x_a1.py",
        ],
        [
            python,
            "scripts/research/run_rd18_p3x_a1.py",
            "--repo-root",
            str(repo),
            "--output-dir",
            str(output),
            "--offline",
            "plan",
        ],
        [
            python,
            "scripts/research/validate_rd18_p3x_a1.py",
            "--output-dir",
            str(output),
            "--offline",
        ],
        ["git", "diff", "--check"],
    ]
    records = [execute(command, cwd=repo) for command in commands]
    report = json.loads((output / "rd18-p3x-a1-runtime-report-v1.json").read_text(encoding="utf-8"))
    control_report_path = output / "control/control-parity-report.json"

    result = {
        "stage": STAGE,
        "passed": True,
        "commands": records,
        "runtime_decision": report["decision"],
        "next_stage": report["next_stage"],
        "output_dir": str(output),
        "control_parity_executed": control_report_path.is_file(),
        "control_parity_passed": bool(report.get("control_parity_passed")),
        "network_acquisition_executed": False,
        "broad_c2_generation_authorized": False,
        "strategy_replay_authorized": False,
        "production_authorized": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
