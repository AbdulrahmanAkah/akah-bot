"""Re-adjudicate RD05 P1 using the committed P1A amendment."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from spotbot.research.rd05_p1a_protocol_amendment import FOLDS, FORMULAS, validate_amendment

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, content: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    temp.replace(path)


def run() -> dict[str, object]:
    validate_amendment()
    source_audit = pd.read_csv(REPORTS / "ams-rd05-p1-source-audit-v1.csv")
    membership = pd.read_csv(REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv")
    membership_time = pd.to_datetime(membership["rebalance_time"], utc=True)
    required_covered = all(
        membership_time.min() <= pd.Timestamp(fold.train_start, tz="UTC")
        and membership_time.max() >= pd.Timestamp(fold.validation_end, tz="UTC")
        for fold in FOLDS
    )
    non_membership = source_audit.loc[source_audit.source_id != "PIT_MEMBERSHIP"]
    critical = bool(non_membership.hash_match.all() and required_covered)
    summary: dict[str, object] = {
        "schema_version": "ams-rd05-p1-re-adjudication-v1",
        "research_stage": "RD05-P1-RE-ADJUDICATION",
        "status": "COMPLETE" if critical else "BLOCKED",
        "decision": (
            "RD05_SIGNAL_DATA_CONTRACT_AND_SOURCE_FREEZE_COMPLETE"
            if critical
            else "RD05_SIGNAL_DATA_CONTRACT_BLOCKED"
        ),
        "next_stage": "RD05-P2-CAUSAL-SYMBOL-TIME-PANEL-BUILD" if critical else "BLOCKED",
        "rd05_p2_panel_build_authorized": critical,
        "signal_value_computation_for_panel_authorized": critical,
        "label_value_computation_for_panel_authorized": critical,
        "predictive_signal_evaluation_authorized": False,
        "portfolio_simulation_authorized": False,
        "source_ready_signal_count": 33 if critical else 0,
        "blocked_signal_count": 0 if critical else 33,
        "formula_ambiguity_count": 0 if critical and len(FORMULAS) == 6 else 6,
        "amendment_sha256": sha(REPORTS / "ams-rd05-p1a-protocol-amendment-v1.json"),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    out = REPORTS / "ams-rd05-p1-re-adjudication-v1.json"
    write(out, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    result = run()
    print(f"P1_RE_ADJUDICATION_STATUS={result['status']}")
    print(f"RD05_P2_PANEL_BUILD_AUTHORIZED={result['rd05_p2_panel_build_authorized']}")
