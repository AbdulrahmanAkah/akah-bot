from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run RD16-K capital-efficiency and bull-capture remediation."
    )
    parser.add_argument("--repo", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    source = repo / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

    from spotbot.research.rd16k_evaluation import run_rd16k

    report = run_rd16k()
    summary = {
        key: report[key]
        for key in (
            "decision",
            "technical_status",
            "evidence_classification",
            "variants_evaluated",
            "retained_variant_count",
            "promising_variant_count",
            "retained_variants",
            "strategic_objective_met_count",
            "next_stage",
        )
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
