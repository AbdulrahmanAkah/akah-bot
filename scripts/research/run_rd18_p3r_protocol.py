#!/usr/bin/env python3
"""Inspect the frozen RD18-P3R protocol; no strategy replay is performed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p3r"


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Required no-network mode.")
    parser.add_argument(
        "--show",
        choices=("protocol", "candidate", "gates", "readiness", "final"),
        default="final",
        help="Committed artifact to print.",
    )
    args = parser.parse_args()
    if not args.offline:
        parser.error("--offline is required")
    names = {
        "protocol": "rd18-p3r-protocol-v1.json",
        "candidate": "frozen-strategy-candidate.json",
        "gates": "performance-gate-registry.json",
        "readiness": "preexecution-readiness.json",
        "final": "rd18-p3r-final-report-v1.json",
    }
    payload = _read_json(OUT / names[args.show])
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
