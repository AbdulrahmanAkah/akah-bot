"""Register RD07 cross-venue spot-flow research without authorizing a portfolio."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spotbot.research.rd07_cross_venue_protocol import SIGNALS, validate_protocol

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def main() -> None:
    validate_protocol()
    rd06 = json.loads((REPORTS / "ams-rd06-final-adjudication-v1.json").read_text(encoding="utf-8"))
    if rd06["next_stage"] != "RD07_CROSS_VENUE_SPOT_DATA_PROTOCOL":
        raise RuntimeError("RD07 is not authorized")
    signal_rows: list[dict[str, object]] = [
        {
            "signal_id": item.signal_id,
            "family": item.family,
            "signal_class": item.signal_class,
            "minimum_bars": item.minimum_bars,
            "higher_score_preferred": True,
        }
        for item in SIGNALS
    ]
    payload: dict[str, object] = {
        "stage": "RD07-CROSS-VENUE-SPOT-FLOW-PROTOCOL",
        "status": "COMPLETE",
        "decision": "RD07_CROSS_VENUE_SPOT_FLOW_PROTOCOL_REGISTERED",
        "next_stage": "RD07-BINANCE-SPOT-SOURCE-FREEZE",
        "official_source": "https://data.binance.vision",
        "market": "SPOT",
        "interval": "4h",
        "start_month": "2021-01",
        "end_month": "2024-12",
        "confirmatory_trials": 13,
        "post_hoc_trials": 1,
        "bh_family_count": 14,
        "additional_parameter_variants": 0,
        "coverage_gate": {
            "overall_panel_row_coverage": 0.80,
            "median_decision_symbol_share": 0.80,
            "minimum_fold_grid_coverage": 0.70,
            "minimum_symbols_per_decision": 20,
        },
        "portfolio_construction_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    write_text(
        REPORTS / "ams-rd07-protocol-registration-v1.json",
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        REPORTS / "ams-rd07-protocol-registration-v1.md",
        "# RD07 Cross-Venue Spot-Flow Protocol\n\n"
        "- Binance official spot archive only\n"
        "- 14 frozen trials\n"
        "- Portfolio construction not authorized\n",
    )
    write_csv(REPORTS / "ams-rd07-signal-registry-v1.csv", signal_rows)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
