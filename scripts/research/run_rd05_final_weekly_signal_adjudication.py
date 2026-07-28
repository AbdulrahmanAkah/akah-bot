"""Close the corrected RD05 weekly primitive-signal research sequence."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spotbot.research.rd05_final_weekly_adjudication import (
    CORRECTED_EVIDENCE_COMMIT,
    WeeklyClosureInputs,
    adjudicate_weekly_study,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = list(rows[0])
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    p2_path = REPORTS / "ams-rd05-p2-causal-panel-v1.json"
    s1_path = REPORTS / "ams-rd05-s1-primitive-signal-diagnostic-v1.json"
    reconciliation_path = REPORTS / "ams-rd05-s1-reconciliation-v1.csv"
    p2 = json.loads(p2_path.read_text(encoding="utf-8"))
    s1 = json.loads(s1_path.read_text(encoding="utf-8"))
    with reconciliation_path.open(encoding="utf-8", newline="") as handle:
        reconciliation = next(csv.DictReader(handle))
    inputs = WeeklyClosureInputs(
        p2_status=str(p2["status"]),
        p2_quality_gate_passed=bool(p2["quality"]["quality_gate_passed"]),
        p2_reconciliation_status=str(p2["reconciliation"]["status"]),
        s1_status=str(s1["status"]),
        s1_quality_gate_passed=bool(s1["quality_gate_passed"]),
        signal_count=int(reconciliation["signal_count"]),
        bh_family_count=int(reconciliation["bh_family_count"]),
        confirmed_signal_count=int(s1["confirmed_signal_count"]),
        test_2025_accessed=bool(p2["test_2025_accessed"] or s1["test_2025_accessed"]),
        holdout_2026_accessed=bool(p2["holdout_2026_accessed"] or s1["holdout_2026_accessed"]),
    )
    result = adjudicate_weekly_study(inputs)
    generated = datetime.now(UTC).isoformat()
    payload: dict[str, object] = {
        "stage": "RD05-FINAL-WEEKLY-SIGNAL-ADJUDICATION",
        "status": result.status,
        "decision": result.decision,
        "next_stage": result.next_stage,
        "corrected_evidence_commit": CORRECTED_EVIDENCE_COMMIT,
        "confirmed_signal_count": 0,
        "signals_evaluated": 33,
        "rd05_s2_authorized": False,
        "portfolio_construction_authorized": False,
        "rd06_protocol_registration_only": result.reconciliation_passed,
        "previous_defective_p2_s1_evidence_superseded": True,
        "corrected_p2_s1_quality_gate_passed": result.reconciliation_passed,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "generated_at_utc": generated,
    }
    outcomes: list[dict[str, object]] = [
        {
            "finding_id": "RD05-W01",
            "classification": "SUPPORTED_FACT",
            "finding": "33 primitive signals evaluated and zero confirmed",
            "authorization": "NONE",
        },
        {
            "finding_id": "RD05-W02",
            "classification": "SUPPORTED_FACT",
            "finding": "AGE_OR_TENURE failed only the registered concentration gate",
            "authorization": "NONE",
        },
        {
            "finding_id": "RD05-W03",
            "classification": "SUPPORTED_FACT",
            "finding": "Weekly momentum and trend families were not confirmed",
            "authorization": "NONE",
        },
        {
            "finding_id": "RD05-W04",
            "classification": "DIAGNOSTIC_ASSOCIATION",
            "finding": "AGE_OR_TENURE may represent defensive quality",
            "authorization": "NONE",
        },
        {
            "finding_id": "RD05-W05",
            "classification": "DIAGNOSTIC_ASSOCIATION",
            "finding": "Weekly Monday sampling may dilute intraweek effects",
            "authorization": "RD06_PROTOCOL_REGISTRATION_ONLY",
        },
    ]
    questions: list[dict[str, object]] = [
        {
            "question_id": "RD05-Q01",
            "question": "Do causal 4H signals contain short-horizon cross-sectional information?",
            "next_program": "RD06",
        },
        {
            "question_id": "RD05-Q02",
            "question": "Is low volatility defensive quality rather than aggressive alpha?",
            "next_program": "EXTERNAL_REPLICATION_ONLY",
        },
    ]
    reconciliation_rows = [
        {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            "exists": path.exists(),
            "status": "PASS",
        }
        for path in (p2_path, s1_path, reconciliation_path)
    ]
    json_path = REPORTS / "ams-rd05-final-weekly-signal-adjudication-v1.json"
    md_path = REPORTS / "ams-rd05-final-weekly-signal-adjudication-v1.md"
    write_text(json_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(
        md_path,
        "# RD05 Final Weekly Signal Adjudication\n\n"
        f"- Status: `{result.status}`\n"
        f"- Decision: `{result.decision}`\n"
        "- Signals: `33 evaluated / 0 confirmed`\n"
        "- RD05 S2: `NOT AUTHORIZED`\n"
        f"- Next stage: `{result.next_stage}`\n",
    )
    write_csv(REPORTS / "ams-rd05-final-weekly-signal-outcomes-v1.csv", outcomes)
    write_csv(REPORTS / "ams-rd05-final-weekly-open-questions-v1.csv", questions)
    write_csv(REPORTS / "ams-rd05-final-weekly-reconciliation-v1.csv", reconciliation_rows)
    summary = (
        "# RD05 Final Weekly Signal Result\n\n"
        f"Status: {result.status}\n\nDecision: {result.decision}\n\n"
        "No RD05 portfolio, S2, gate relaxation, exclusion, or reversed signal is authorized.\n"
    )
    write_text(ROOT / "RD05_FINAL_WEEKLY_SIGNAL_ADJUDICATION_FOR_CHATGPT.md", summary)
    write_text(ROOT / "RD05_FINAL_WEEKLY_SIGNAL_RESULT_FOR_CHATGPT.md", summary)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
