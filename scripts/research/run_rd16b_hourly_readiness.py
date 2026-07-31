from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from spotbot.research.rd16b_common import (
    DEFAULT_SINCE,
    SEALED_CUTOFF,
    parse_utc,
)
from spotbot.research.rd16b_hourly_readiness import run_rd16b


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run RD16-B hourly data readiness and causal aggregation.")
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
        "--since",
        default=DEFAULT_SINCE.isoformat(),
    )
    parser.add_argument(
        "--until",
        default=SEALED_CUTOFF.isoformat(),
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    store_root = (
        arguments.store_root.resolve()
        if arguments.store_root is not None
        else repo / "data" / "raw" / "rd16b"
    )
    report = run_rd16b(
        store_root=store_root,
        since=parse_utc(arguments.since),
        until=parse_utc(arguments.until),
        download=not arguments.no_download,
    )
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "technical_status": (report["technical_status"]),
                "evidence_classification": (report["evidence_classification"]),
                "assets_passed": report["assets_passed"],
                "assets_total": report["assets_total"],
                "next_stage": report["next_stage"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
