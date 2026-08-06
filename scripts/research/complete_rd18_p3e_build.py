from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

FILES = (
    "src/spotbot/research/rd18_p3e_replay.py",
    "scripts/research/run_rd18_p3e.py",
    "scripts/research/validate_rd18_p3e.py",
    "scripts/research/complete_rd18_p3e_build.py",
    "tests/research/test_rd18_p3e.py",
)


class P3ECompletionError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo", type=Path, default=ROOT)
    result.add_argument("--python", type=Path, required=True)
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3e_build_runtime",
    )
    return result


def run(
    command: list[str],
    *,
    repo: Path,
) -> dict[str, object]:
    print(f"\n> {' '.join(command)}", flush=True)
    completed = subprocess.run(
        command,
        cwd=repo,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise P3ECompletionError(f"command failed ({completed.returncode}): {' '.join(command)}")
    return {"command": command, "returncode": completed.returncode}


def main() -> int:
    args = parser().parse_args()
    repo = args.repo.resolve()
    python = str(args.python.resolve())
    output = args.output_dir.resolve()
    checks: dict[str, Any] = {}

    checks["py_compile"] = run(
        [python, "-m", "py_compile", *FILES],
        repo=repo,
    )
    checks["ruff"] = run(
        [python, "-m", "ruff", "check", *FILES],
        repo=repo,
    )
    checks["ruff_format"] = run(
        [python, "-m", "ruff", "format", "--check", *FILES],
        repo=repo,
    )
    checks["pytest"] = run(
        [
            python,
            "-m",
            "pytest",
            "-q",
            "-W",
            "error",
            "tests/research/test_rd18_p3e.py",
        ],
        repo=repo,
    )
    common = [
        "--repo-root",
        str(repo),
        "--a2-runtime",
        str(repo / "data/research/rd18_p3x_a2_runtime"),
        "--a3-runtime",
        str(repo / "data/research/rd18_p3x_a3_runtime"),
        "--a3b-runtime",
        str(repo / "data/research/rd18_p3x_a3b_runtime"),
        "--output-dir",
        str(output),
    ]
    checks["preflight"] = run(
        [
            python,
            "scripts/research/run_rd18_p3e.py",
            *common,
            "--preflight-only",
        ],
        repo=repo,
    )
    checks["materialize"] = run(
        [
            python,
            "scripts/research/run_rd18_p3e.py",
            *common,
            "--write-ledgers",
        ],
        repo=repo,
    )
    checks["validator"] = run(
        [
            python,
            "scripts/research/validate_rd18_p3e.py",
            "--output-dir",
            str(output),
            "--offline",
        ],
        repo=repo,
    )

    report = json.loads(
        (output / "rd18-p3e-implementation-build-report-v1.json").read_text(encoding="utf-8-sig")
    )
    response = {
        "schema_version": "rd18-p3e-build-completion-v1",
        "status": "PASS",
        "passed": True,
        "decision": report.get("decision"),
        "next_stage": report.get("next_stage"),
        "checks": checks,
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except P3ECompletionError as exc:
        print(f"P3E_COMPLETION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
