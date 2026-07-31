from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from spotbot.research.rd16j_evaluation import run_rd16j


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the fixed COMPOSITE_ALPHA_V2 economic baseline."
    )
    parser.add_argument("--repo", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"Not a Git repository: {repo}")
    report = run_rd16j()
    keys = (
        "decision",
        "architecture_id",
        "classification",
        "trade_count",
        "net_return",
        "monthly_geometric_return",
        "profit_factor",
        "maximum_drawdown",
        "maximum_positions_configured",
        "maximum_positions_observed",
        "two_x_net_return",
        "two_x_capital_feasible",
        "strategic_objective_met",
        "next_stage",
    )
    print(
        json.dumps(
            {key: report[key] for key in keys},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
