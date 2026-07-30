from __future__ import annotations

import json

from spotbot.research.rd13_sample_expansion import run_rd13


def main() -> int:
    result = run_rd13()
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "next_stage": result["next_stage"],
                "baseline_closed_trades": result["baseline_metrics"]["closed_trade_count"],
                "deterministic_replay_pass": result["deterministic_replay_pass"],
                "reconciliation_pass": result["reconciliation_pass"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
