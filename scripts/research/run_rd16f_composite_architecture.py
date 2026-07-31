from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run RD16-F registered composite alpha architecture smoke tests."
    )
    parser.add_argument("--repo", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"Not a Git repository: {repo}")
    source = repo / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

    from spotbot.research.rd16f_registration import run_rd16f

    report = run_rd16f()
    summary = {
        key: report[key]
        for key in (
            "decision",
            "evidence_classification",
            "architecture_id",
            "engines_registered",
            "source_components_verified",
            "candidate_count",
            "admitted_trade_count",
            "maximum_positions_observed",
            "maximum_open_risk_fraction",
            "next_stage",
            "technical_status",
        )
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
