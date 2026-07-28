from __future__ import annotations

from pathlib import Path


def test_rd07_final_runner_has_fail_closed_decision() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts/research/run_rd07_final_adjudication.py").read_text(encoding="utf-8")
    assert "RD07_CROSS_VENUE_SPOT_FLOW_EDGE_NOT_CONFIRMED" in text
    assert '"portfolio_construction_authorized": False' in text
    assert '"test_2025_accessed": False' in text
