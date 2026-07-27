"""Orchestrate RD01-D0 through RD01-D3 with research gates."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def root_path() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the gated RD01 dominance research pipeline.")
    parser.add_argument(
        "--coinmetrics-json",
        type=Path,
        default=None,
        help="Optional offline Coin Metrics dominance JSON.",
    )
    parser.add_argument(
        "--defillama-json",
        type=Path,
        default=None,
        help="Optional offline DefiLlama stablecoin JSON.",
    )
    return parser.parse_args()


def run_stage(
    root: Path,
    script: str,
    extra: list[str] | None = None,
) -> None:
    command = [
        sys.executable,
        str(root / "scripts" / "research" / script),
    ]

    if extra:
        command.extend(extra)

    completed = subprocess.run(
        command,
        cwd=root,
        check=False,
    )

    if completed.returncode != 0:
        raise SystemExit(f"{script} failed with exit code {completed.returncode}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_arguments()
    root = root_path()
    reports = root / "reports" / "research"
    d0_extra = [
        "--root",
        str(root),
    ]

    if args.coinmetrics_json is not None:
        d0_extra.extend(["--coinmetrics-json", str(args.coinmetrics_json)])

    if args.defillama_json is not None:
        d0_extra.extend(["--defillama-json", str(args.defillama_json)])

    run_stage(
        root,
        "run_rd01_d0_dominance_validation.py",
        d0_extra,
    )
    d0 = load_json(reports / "ams-rd01-d0-dominance-causality-v1.json")

    if d0["status"] == "BLOCKED_BY_DATA":
        print("RD01_PIPELINE_STATUS=BLOCKED_BY_DATA")
        print(f"DETAIL={d0.get('detail')}")
        return 0

    if d0["status"] not in {"PASS", "PARTIAL"}:
        print(f"RD01_PIPELINE_STATUS={d0['status']}")
        return 1

    run_stage(
        root,
        "run_rd01_d1_dominance_tagging.py",
    )
    run_stage(
        root,
        "run_rd01_d2_dominance_attribution.py",
    )
    run_stage(
        root,
        "run_rd01_d3_overlay_decision.py",
    )
    d3 = load_json(reports / "ams-rd01-d3-dominance-overlay-decision-v1.json")

    print("RD01_PIPELINE_STATUS=COMPLETE")
    print(f"D3_DECISION={d3['decision']}")
    print(f"ATI_V1_AUTHORIZED={d3['ati_v1_authorized']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
