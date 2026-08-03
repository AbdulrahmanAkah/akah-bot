from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--repo", type=Path, required=True)
    result.add_argument("--python", required=True)
    result.add_argument("--a1-runtime", type=Path, required=True)
    result.add_argument("--a2-runtime", type=Path, required=True)
    result.add_argument("--input-dir", type=Path, required=True)
    result.add_argument("--output-dir", type=Path, required=True)
    return result


def run(command: list[str], *, cwd: Path) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): "
            f"{' '.join(command)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo.resolve()
    generation = run(
        [
            args.python,
            "scripts/research/run_rd18_p3x_a3a.py",
            "--repo-root",
            str(repo),
            "--a1-runtime",
            str(args.a1_runtime.resolve()),
            "--a2-runtime",
            str(args.a2_runtime.resolve()),
            "--input-dir",
            str(args.input_dir.resolve()),
            "--output-dir",
            str(args.output_dir.resolve()),
            "--write-inputs",
        ],
        cwd=repo,
    )
    validation = run(
        [
            args.python,
            "scripts/research/validate_rd18_p3x_a3a.py",
            "--input-dir",
            str(args.input_dir.resolve()),
            "--output-dir",
            str(args.output_dir.resolve()),
            "--offline",
        ],
        cwd=repo,
    )
    response = {
        "schema_version": "rd18-p3x-a3a-completion-v1",
        "generation": json.loads(str(generation["stdout"])),
        "validation": json.loads(str(validation["stdout"])),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
