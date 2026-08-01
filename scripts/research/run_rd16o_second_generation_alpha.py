from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=("Run RD16-O second-generation intraday alpha redesign.")
    )
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    source = repo / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

    from spotbot.research.rd16o_evaluation import run_rd16o_research

    report = run_rd16o_research()
    all_overlay = report["pre_registered_all_second_gen_overlay"]
    if not isinstance(all_overlay, dict):
        raise TypeError("RD16-O all-overlay report is invalid.")

    summary = {
        "decision": report["decision"],
        "technical_status": report["technical_status"],
        "architecture_id": report["architecture_id"],
        "hypotheses_evaluated": report["hypotheses_evaluated"],
        "retained_hypothesis_count": (report["retained_hypothesis_count"]),
        "promising_hypothesis_count": (report["promising_hypothesis_count"]),
        "retained_hypotheses": report["retained_hypotheses"],
        "promising_hypotheses": report["promising_hypotheses"],
        "strategic_objective_met_count": (report["strategic_objective_met_count"]),
        "all_second_gen_overlay_new_trade_count": (all_overlay["new_trade_count"]),
        "all_second_gen_overlay_net_return": (all_overlay["net_return"]),
        "all_second_gen_overlay_profit_factor": (all_overlay["profit_factor"]),
        "all_second_gen_overlay_two_x_capital_feasible": (all_overlay["two_x_capital_feasible"]),
        "next_stage": report["next_stage"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
