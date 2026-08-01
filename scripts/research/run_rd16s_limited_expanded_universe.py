from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd16s_evaluation import (  # noqa: E402
    run_rd16s_research,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    if repo != ROOT:
        raise RuntimeError(f"Repository mismatch: expected {ROOT}, received {repo}")

    report = run_rd16s_research()
    all_overlay = report["pre_registered_all_domain_overlay"]
    payload = {
        "decision": report["decision"],
        "architecture_id": report["architecture_id"],
        "source_universe_size": report["source_universe_size"],
        "expanded_universe_size": report["expanded_universe_size"],
        "incremental_noncore_asset_count": (report["incremental_noncore_asset_count"]),
        "domains_evaluated": report["domains_evaluated"],
        "retained_domain_count": report["retained_domain_count"],
        "retained_domains": report["retained_domains"],
        "promising_domain_count": report["promising_domain_count"],
        "promising_domains": report["promising_domains"],
        "strategic_objective_met_count": (report["strategic_objective_met_count"]),
        "all_domain_overlay_new_trade_count": (all_overlay["new_trade_count"]),
        "all_domain_overlay_net_return": all_overlay["net_return"],
        "all_domain_overlay_profit_factor": (all_overlay["profit_factor"]),
        "all_domain_overlay_two_x_capital_feasible": (all_overlay["two_x_capital_feasible"]),
        "all_domain_overlay_noncore_new_trade_count": (all_overlay["noncore_new_trade_count"]),
        "all_domain_overlay_noncore_net_pnl": (all_overlay["noncore_net_pnl"]),
        "expanded_delta_net_return_vs_rd16q": (all_overlay["expanded_delta_net_return_vs_rd16q"]),
        "next_stage": report["next_stage"],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
