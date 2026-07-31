from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from spotbot.research.rd16i_registration import register_composite_alpha_v2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register COMPOSITE_ALPHA_V2 from retained RD16-H evidence."
    )
    parser.add_argument("--repo", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"Not a Git repository: {repo}")
    report = register_composite_alpha_v2()
    summary = {
        key: report[key]
        for key in (
            "decision",
            "technical_status",
            "evidence_classification",
            "architecture_id",
            "source_variant_id",
            "candidate_count",
            "admitted_trade_count",
            "maximum_positions_configured",
            "maximum_positions_observed",
            "maximum_open_risk_fraction_observed",
            "next_stage",
        )
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
