from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Register COMPOSITE_ALPHA_V3 from retained RD16-K evidence."
    )
    parser.add_argument("--repo", type=Path, required=True)
    arguments = parser.parse_args()

    repo = arguments.repo.resolve()
    source = repo / "src"
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

    from spotbot.research.rd16l_registration import register_composite_alpha_v3

    report = register_composite_alpha_v3()
    summary = {
        "decision": report["decision"],
        "technical_status": report["technical_status"],
        "architecture_id": report["architecture_id"],
        "source_variant_id": report["source_variant_id"],
        "candidate_count": report["candidate_count"],
        "admitted_trade_count": report["admitted_trade_count"],
        "maximum_positions_configured": report["maximum_positions_configured"],
        "maximum_positions_observed": report["maximum_positions_observed"],
        "maximum_open_risk_fraction_observed": report["maximum_open_risk_fraction_observed"],
        "normal_holding_bars": report["normal_holding_bars"],
        "strong_bull_holding_bars": report["strong_bull_holding_bars"],
        "evidence_classification": report["evidence_classification"],
        "next_stage": report["next_stage"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
