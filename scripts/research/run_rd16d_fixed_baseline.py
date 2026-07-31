from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from spotbot.research.rd16d_baseline import run_rd16d


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the frozen RD16-D family baseline evaluation."
    )
    parser.add_argument(
        "--repo",
        type=Path,
        required=True,
        help="Repository root; retained for a consistent research CLI.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").exists():
        raise RuntimeError(f"Not a Git repository: {repo}")
    final = run_rd16d()
    summary = {
        "decision": final["decision"],
        "technical_status": final["technical_status"],
        "evidence_classification": final["evidence_classification"],
        "families_evaluated": final["families_evaluated"],
        "robust_positive_baselines": final["robust_positive_baselines"],
        "fragile_positive_baselines": final["fragile_positive_baselines"],
        "failed_or_capital_infeasible_baselines": (final["failed_or_capital_infeasible_baselines"]),
        "strategic_objective_met_count": (final["strategic_objective_met_count"]),
        "next_stage": final["next_stage"],
    }
    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
