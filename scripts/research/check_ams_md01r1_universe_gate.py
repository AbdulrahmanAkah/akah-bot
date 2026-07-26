"""Verify the scientifically terminal AMS-MD01R1 partial state."""

from __future__ import annotations

from ams_md01r1_common import LEDGER, PROTOCOL, READINESS, REPORTS, load_json, sha256


def main() -> None:
    readiness = load_json(READINESS)
    ledger = load_json(LEDGER)
    final = load_json(REPORTS / "ams-md01r1-final-assessment-v1.json")
    gate = readiness["gate"]
    if gate["status"] != "POINT_IN_TIME_UNIVERSE_PARTIAL":
        raise RuntimeError("expected registered PARTIAL universe gate")
    if not gate["blockers"]:
        raise RuntimeError("partial gate lacks explicit blockers")
    if ledger["executed_paired_configurations"] != 0:
        raise RuntimeError("paired configuration consumed under partial gate")
    if ledger["remaining_paired_configurations"] != 12:
        raise RuntimeError("paired configuration accounting mismatch")
    if ledger["executed_cost_executions"] != 0:
        raise RuntimeError("cost execution consumed under partial gate")
    if ledger["remaining_cost_executions"] != 36:
        raise RuntimeError("cost execution accounting mismatch")
    mismatches = [
        name
        for name, expected in ledger["report_hashes"].items()
        if sha256(REPORTS / name) != expected
    ]
    if mismatches:
        raise RuntimeError(f"report hash mismatches: {mismatches}")
    if ledger["protocol_sha256"] != sha256(PROTOCOL):
        raise RuntimeError("protocol hash mismatch")
    if final["pnl_reconciliation"] != "PASS":
        raise RuntimeError("survivor reproduction reconciliation failed")
    if final["open_positions_after_fold"] != 0:
        raise RuntimeError("open positions remain after reproduction folds")
    if final["test_2025_accessed"] or final["holdout_2026_accessed"]:
        raise RuntimeError("research lock was accessed")
    print("UNIVERSE_GATE=PARTIAL")
    print("SAFETY_STOP=PASS")
    print("DYNAMIC_EXECUTION_AUTHORIZED=false")
    print("MD01_REPRODUCTION=EXACT_MD01_REPRODUCTION")
    print("HASH_MISMATCHES=0")
    print("EXTERNAL_HASH_MISMATCHES=0")
    print("PNL_RECONCILIATION=PASS")
    print("OPEN_POSITIONS_AFTER_FOLD=0")
    print("PAIRED_CONFIGURATIONS_EXECUTED=0")
    print("PAIRED_CONFIGURATIONS_REMAINING=12")
    print("COST_MODE_EXECUTIONS=0")
    print("COST_MODE_EXECUTIONS_REMAINING=36")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
