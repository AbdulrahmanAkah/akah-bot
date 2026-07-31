from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from spotbot.research.rd16c_smoke import run_rd16c


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run RD16-C registered intraday strategy family smoke tests.")
    )
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--store-root", type=Path, default=None)
    parser.add_argument("--local-output-root", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    store_root = (
        arguments.store_root.resolve()
        if arguments.store_root is not None
        else repo / "data" / "raw" / "rd16b"
    )
    local_output_root = (
        arguments.local_output_root.resolve()
        if arguments.local_output_root is not None
        else repo / "data" / "raw" / "rd16c"
    )
    report = run_rd16c(
        store_root=store_root,
        local_output_root=local_output_root,
    )
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "technical_status": report["technical_status"],
                "evidence_classification": (report["evidence_classification"]),
                "families_passed": report["families_passed"],
                "families_total": report["families_total"],
                "next_stage": report["next_stage"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
