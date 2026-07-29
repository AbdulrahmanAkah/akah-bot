"""Record the final RD08 closure from frozen upstream evidence."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spotbot.research.rd08_final_closure import (
    FINAL_DECISION,
    NEXT_STAGE,
    TrialSequence,
    classify_near_miss,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
UPSTREAM = REPORTS / "ams-rd08-market-timing-diagnostic-v1.json"
BLOCK7 = REPORTS / "ams-rd08-bootstrap-7d-v1.csv"
BLOCK28 = REPORTS / "ams-rd08-bootstrap-28d-v1.csv"
NEAR_MISS = "MKT_AGG_QUOTE_TURNOVER_ACCEL_6_42"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def read_adjusted(path: Path) -> float:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next(item for item in rows if item["signal_id"] == NEAR_MISS)
    key = next(name for name in row if "adjusted" in name or "bh_" in name)
    return float(row[key])


def main() -> None:
    upstream = json.loads(UPSTREAM.read_text(encoding="utf-8"))
    if upstream["decision"] != "RD08_MARKET_STATE_TIMING_EDGE_NOT_CONFIRMED":
        raise RuntimeError("RD08 upstream decision mismatch")
    if int(upstream["confirmed_signal_count"]) != 0:
        raise RuntimeError("RD08 upstream confirmed-signal mismatch")
    block_7 = read_adjusted(BLOCK7)
    block_28 = read_adjusted(BLOCK28)
    classification = classify_near_miss(block_7, block_28)
    if classification != "UNCONFIRMED_NEAR_MISS":
        raise RuntimeError("registered near-miss classification changed")
    trials = TrialSequence()
    sequence_rows = [
        {"stage": "RD05", "primitive_trials": trials.rd05, "confirmed": 0},
        {"stage": "RD06", "primitive_trials": trials.rd06, "confirmed": 0},
        {"stage": "RD07", "primitive_trials": trials.rd07, "confirmed": 0},
        {"stage": "RD08", "primitive_trials": trials.rd08, "confirmed": 0},
    ]
    spaces = [
        "CROSS_SECTIONAL_PRICE_VOLUME_FLOW_SPACE_CLOSED",
        "OHLCV_PRIMITIVE_SIGNAL_SPACE_CLOSED",
        "MARKET_STATE_TIMING_SPACE_CLOSED",
        "PUBLIC_SPOT_MARKET_DATA_SPACE_CLOSED",
    ]
    reconciliation = [
        {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            "exists": True,
            "reconciliation_pass": True,
        }
        for path in (UPSTREAM, BLOCK7, BLOCK28)
    ]
    payload: dict[str, object] = {
        "stage": "RD08-FINAL-MARKET-DATA-RESEARCH-CLOSURE",
        "status": "COMPLETE",
        "decision": FINAL_DECISION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "trial_counts": {
            "rd05": trials.rd05,
            "rd06": trials.rd06,
            "rd07": trials.rd07,
            "rd08": trials.rd08,
            "total": trials.total,
            "confirmed": 0,
        },
        "near_miss": {
            "signal_id": NEAR_MISS,
            "classification": classification,
            "bh_block_7": block_7,
            "bh_block_28": block_28,
            "registered_threshold": 0.05,
        },
        "closed_information_spaces": {name: True for name in spaces},
        "portfolio_construction_authorized": False,
        "next_stage": NEXT_STAGE,
        "prohibited_inferences": [
            "DROP_HISTORICAL_BH_TRIALS",
            "RELAX_FDR_THRESHOLD",
            "SELECT_ONLY_BLOCK_28_RESULT",
            "CONSTRUCT_EXPOSURE_RULE",
            "RETEST_PARAMETER_VARIANTS",
        ],
        "safety": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "portfolio_simulation_authorized": False,
            "production_change_authorized": False,
            "trade_logic_changed": False,
        },
    }
    write_text(
        REPORTS / "ams-rd08-final-closure-v1.json",
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    markdown = (
        "# RD08 Final Market-Data Research Closure\n\n"
        f"- Status: `COMPLETE`\n- Decision: `{FINAL_DECISION}`\n"
        f"- Registered primitive trials: `{trials.total}`\n"
        "- Confirmed primitive signals: `0`\n"
        f"- Near miss: `{NEAR_MISS}` remains `{classification}`.\n"
        f"- Block-7 BH: `{block_7:.6f}`; block-28 BH: `{block_28:.6f}`.\n"
        f"- Next stage: `{NEXT_STAGE}`.\n"
        "- No portfolio, exposure rule, production change, 2025, or 2026 access.\n"
    )
    write_text(REPORTS / "ams-rd08-final-closure-v1.md", markdown)
    write_csv(
        REPORTS / "ams-rd08-full-research-sequence-ledger-v1.csv",
        sequence_rows,
        ["stage", "primitive_trials", "confirmed"],
    )
    write_csv(
        REPORTS / "ams-rd08-closed-information-spaces-v1.csv",
        [{"information_space": name, "closed": True} for name in spaces],
        ["information_space", "closed"],
    )
    write_csv(
        REPORTS / "ams-rd08-final-reconciliation-v1.csv",
        reconciliation,
        ["path", "sha256", "exists", "reconciliation_pass"],
    )
    implementation = (
        "# RD08 Final Closure\n\n"
        "This stage reconciles frozen RD08 evidence and closes the registered public spot "
        "market-data research spaces. It performs no new statistical evaluation.\n"
    )
    result = markdown.replace("# RD08", "# RD08 Result", 1)
    write_text(ROOT / "RD08_FINAL_CLOSURE_FOR_CHATGPT.md", implementation)
    write_text(ROOT / "RD08_FINAL_CLOSURE_RESULT_FOR_CHATGPT.md", result)
    print(f"RD08_FINAL_STATUS={payload['status']}")
    print(f"RD08_FINAL_DECISION={FINAL_DECISION}")
    print(f"TOTAL_PRIMITIVE_TRIALS={trials.total}")
    print("CONFIRMED_PRIMITIVE_SIGNALS=0")


if __name__ == "__main__":
    main()
