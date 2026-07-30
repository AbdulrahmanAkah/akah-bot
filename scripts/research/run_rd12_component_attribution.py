from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def main() -> int:
    module = importlib.import_module("spotbot.research.rd12_component_attribution")
    run_rd12 = module.run_rd12
    result = run_rd12()
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "variant_count": result["variant_count"],
                "baseline_reproduction_match": result["baseline_reproduction_match"],
                "deterministic_replay_pass": result["deterministic_replay_pass"],
                "reconciliation_pass": result["reconciliation_pass"],
                "next_stage": result["next_stage"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
