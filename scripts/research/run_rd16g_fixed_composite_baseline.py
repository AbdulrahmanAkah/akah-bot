from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from spotbot.research.rd16g_evaluation import run_rd16g


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the fixed RD16-G composite baseline.")
    parser.add_argument("--repo", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(list(argv) if argv is not None else None)
    repo = arguments.repo.resolve()
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"Not a Git repository: {repo}")
    report = cast(dict[str, object], run_rd16g())
    fields = (
        "decision",
        "technical_status",
        "evidence_classification",
        "architecture_id",
        "classification",
        "trade_count",
        "net_return",
        "monthly_geometric_return",
        "profit_factor",
        "maximum_drawdown",
        "strategic_objective_met",
        "next_stage",
    )
    print(json.dumps({key: report[key] for key in fields}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
