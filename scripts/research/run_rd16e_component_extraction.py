from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run RD16-E intraday family remediation and component extraction."
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

    from spotbot.research.rd16e_evaluation import run_rd16e

    report = run_rd16e()
    summary = {
        key: report[key]
        for key in (
            "decision",
            "evidence_classification",
            "families_evaluated",
            "variants_evaluated",
            "retained_component_count",
            "promising_component_count",
            "insufficient_sample_count",
            "rejected_component_count",
            "carry_forward_component_count",
            "strategic_objective_met_count",
            "next_stage",
            "technical_status",
        )
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
