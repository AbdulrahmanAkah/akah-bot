from __future__ import annotations

import json
from pathlib import Path

from spotbot.research.rd10_smoke_backtest import OUTPUT_ROOT, run_smoke_backtest


def main() -> None:
    result = run_smoke_backtest(OUTPUT_ROOT)
    metrics = result["metrics"]
    print(
        json.dumps(
            {
                "status": "PASS",
                "signal_count": metrics["signal_count"],
                "fill_count": metrics["fill_count"],
                "closed_trade_count": metrics["closed_trade_count"],
                "output_root": Path(OUTPUT_ROOT).as_posix(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
