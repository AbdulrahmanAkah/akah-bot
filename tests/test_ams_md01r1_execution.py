from __future__ import annotations

import json
from pathlib import Path


def test_partial_gate_prevents_every_dynamic_execution() -> None:
    readiness = json.loads(
        Path("reports/research/ams-md01r1-universe-readiness-v1.json").read_text(
            encoding="utf-8"
        )
    )
    ledger = json.loads(
        Path("reports/research/ams-md01r1-experiment-ledger-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert readiness["dynamic_rerun_authorized"] is False
    assert ledger["executed_paired_configurations"] == 0
    assert ledger["executed_cost_executions"] == 0


def test_survivor_reproduction_closed_every_fold_and_reconciled() -> None:
    report = json.loads(
        Path("reports/research/ams-md01r1-survivor30-reproduction-v1.json").read_text(
            encoding="utf-8"
        )
    )
    for execution in report["executions"]:
        assert execution["aggregate"]["reconciliation_status"] == "PASS"
        assert execution["aggregate"]["open_positions_after_fold"] == 0
