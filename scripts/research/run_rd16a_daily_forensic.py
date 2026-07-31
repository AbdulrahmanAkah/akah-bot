from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from spotbot.research.rd16a_daily_forensic import run_rd16a


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen RD16-A daily forensic closure audit."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository root. Defaults to the active installed checkout.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    report = run_rd16a(arguments.repo)
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "technical_status": report["technical_status"],
                "rd15_engineering_status": report["rd15_engineering_status"],
                "rd15_primary_architecture_status": report["rd15_primary_architecture_status"],
                "evidence_classification": report["evidence_classification"],
                "next_stage": report["next_stage"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
