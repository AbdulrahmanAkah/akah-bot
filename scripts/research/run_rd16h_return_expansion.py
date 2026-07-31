from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from spotbot.research.rd16h_evaluation import run_rd16h


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Run RD16-H composite return expansion and bull-capture remediation.")
    )
    parser.add_argument("--repo", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"Not a Git repository: {repo}")
    report = run_rd16h()
    summary = {
        key: report[key]
        for key in (
            "decision",
            "technical_status",
            "evidence_classification",
            "variants_evaluated",
            "retained_variant_count",
            "promising_variant_count",
            "strategic_objective_met_count",
            "retained_variants",
            "next_stage",
        )
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
