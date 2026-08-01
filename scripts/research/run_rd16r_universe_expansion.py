from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd16r_evaluation import run_rd16r_research  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    if Path.cwd().resolve() != repo:
        raise RuntimeError(f"Run from repository root: {repo}")

    report = run_rd16r_research()
    summary = {
        key: report[key]
        for key in (
            "decision",
            "architecture_id",
            "registered_candidate_count",
            "resolved_market_count",
            "eligible_asset_count",
            "eligible_noncore_asset_count",
            "tier_a_count",
            "tier_b_count",
            "tier_c_count",
            "research_readiness",
            "next_stage",
            "acquisition_failure_count",
        )
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
