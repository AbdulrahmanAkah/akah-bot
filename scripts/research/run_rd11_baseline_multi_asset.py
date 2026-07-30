from __future__ import annotations

import json

from spotbot.research.rd11_multi_asset_backtest import RD11_ROOT, run_rd11


def main() -> None:
    result = run_rd11(RD11_ROOT)
    final = result["final"]
    print(
        json.dumps(
            {
                "decision": final["decision"],
                "evidence_classification": final["evidence_classification"],
                "eligible_asset_count": len(final["eligible_assets"]),
                "deterministic_replay_match": final["deterministic_replay_match"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
