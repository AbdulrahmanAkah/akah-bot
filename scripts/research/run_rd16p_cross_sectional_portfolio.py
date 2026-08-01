from __future__ import annotations

import argparse
import json
from pathlib import Path

from spotbot.research.rd16p_evaluation import run_rd16p_research


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()

    if not (repo / ".git").is_dir():
        raise RuntimeError(f"Not a Git repository: {repo}")

    report = run_rd16p_research()
    summary = {
        key: report[key]
        for key in (
            "decision",
            "architecture_id",
            "variants_evaluated",
            "retained_variant_count",
            "promising_variant_count",
            "retained_variants",
            "promising_variants",
            "strategic_objective_met_count",
            "next_stage",
            "technical_status",
        )
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
