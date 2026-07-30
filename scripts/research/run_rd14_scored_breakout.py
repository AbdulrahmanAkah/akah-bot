from __future__ import annotations

import json

from spotbot.research.rd14_scored_breakout import run_rd14


def main() -> None:
    report = run_rd14()
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "technical_status": report["technical_status"],
                "evidence_classification": report["evidence_classification"],
                "next_stage": report["next_stage"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
