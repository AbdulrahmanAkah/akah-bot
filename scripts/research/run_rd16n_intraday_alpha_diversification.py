from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=("Run RD16-N diversified intraday alpha research.")
    )
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    source = repo / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

    from spotbot.research.rd16n_evaluation import (
        run_rd16n_research,
    )

    report = run_rd16n_research()
    all_new = report["pre_registered_all_new_overlay"]
    if not isinstance(all_new, dict):
        raise RuntimeError("RD16-N all-new overlay summary is invalid.")

    summary = {
        "decision": report["decision"],
        "technical_status": report["technical_status"],
        "evidence_classification": (report["evidence_classification"]),
        "architecture_id": report["architecture_id"],
        "hypotheses_evaluated": (report["hypotheses_evaluated"]),
        "retained_hypothesis_count": (report["retained_hypothesis_count"]),
        "promising_hypothesis_count": (report["promising_hypothesis_count"]),
        "retained_hypotheses": (report["retained_hypotheses"]),
        "promising_hypotheses": (report["promising_hypotheses"]),
        "all_new_overlay_new_trade_count": (all_new["new_trade_count"]),
        "all_new_overlay_net_return": all_new["net_return"],
        "all_new_overlay_profit_factor": (all_new["profit_factor"]),
        "all_new_overlay_two_x_capital_feasible": (all_new["two_x_capital_feasible"]),
        "strategic_objective_met_count": (report["strategic_objective_met_count"]),
        "next_stage": report["next_stage"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
