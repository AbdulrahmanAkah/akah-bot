"""Offline tests for the RD18-P2U fail-closed confidence design."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from spotbot.research.kucoin_rd18_p2u import (
    P2UError,
    confidence_swap_pair,
    hysteresis_membership,
    relative_gap,
    set_metrics,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2u"
RUNNER = ROOT / "scripts" / "research" / "run_rd18_p2u_confidence_universe.py"
VALIDATOR = ROOT / "scripts" / "research" / "validate_rd18_p2u_confidence_universe.py"
PRODUCTS = {
    "AGIX2L-USDT",
    "AGIX2S-USDT",
    "APT2L-USDT",
    "APT2S-USDT",
    "BLUR2L-USDT",
    "BLUR2S-USDT",
    "CFX2L-USDT",
    "CFX2S-USDT",
    "GRT2L-USDT",
    "GRT2S-USDT",
    "OP2L-USDT",
    "OP2S-USDT",
}


def row(pair: str, rank: int, liquidity: float, confidence: str) -> dict[str, object]:
    return {
        "pair": pair,
        "rank_num": rank,
        "liquidity_num": liquidity,
        "confidence_class": confidence,
    }


def test_relative_gap_boundary_is_inclusive() -> None:
    assert relative_gap(100.0, 90.0) == pytest.approx(0.10)
    assert relative_gap(100.0, 0.0) is None


def test_entry_boundary_swaps_only_one_adjacent_pair() -> None:
    rows = [row(f"P{i}", i, 1000 - i, "EVIDENCE_STRONG") for i in range(1, 7)] + [
        row("CURRENT", 7, 900.0, "CURRENT_SEED_KLINE_CONFIRMED"),
        row("STRONG7", 8, 890.0, "EVIDENCE_STRONG"),
    ]
    adjusted, audits = confidence_swap_pair(rows)
    assert [item["pair"] for item in adjusted][5:8] == ["P6", "CURRENT", "STRONG7"]
    assert audits[0]["intervention_applied"] is False

    rows[5]["liquidity_num"] = 1000.0
    rows[6]["liquidity_num"] = 950.0
    rows[5]["confidence_class"] = "CURRENT_SEED_KLINE_CONFIRMED"
    rows[6]["confidence_class"] = "EVIDENCE_STRONG"
    adjusted, audits = confidence_swap_pair(rows)
    assert [item["pair"] for item in adjusted][5:8] == ["CURRENT", "P6", "STRONG7"]
    assert audits[0]["intervention_applied"] is True


def test_gap_above_threshold_and_nonadjacent_rows_do_not_move() -> None:
    rows = [row(f"P{i}", i, 1000 - i, "EVIDENCE_STRONG") for i in range(1, 7)] + [
        row("CURRENT", 7, 100.0, "CURRENT_SEED_KLINE_CONFIRMED"),
        row("STRONG7", 8, 90.0, "EVIDENCE_STRONG"),
    ]
    adjusted, audits = confidence_swap_pair(rows)
    assert [item["pair"] for item in adjusted] == [item["pair"] for item in rows]
    assert audits[0]["intervention_applied"] is False


def test_retention_boundary_and_hysteresis_are_deterministic() -> None:
    rows = [
        *[row(f"P{i}", i, 1000 - i, "EVIDENCE_STRONG") for i in range(1, 8)],
        row("CURRENT8", 8, 98.0, "CURRENT_SEED_KLINE_CONFIRMED"),
        row("STRONG9", 9, 97.0, "EVIDENCE_STRONG"),
    ]
    adjusted, audits = confidence_swap_pair(rows)
    assert audits[1]["intervention_applied"] is True
    assert [item["pair"] for item in adjusted][7:9] == ["STRONG9", "CURRENT8"]
    assert hysteresis_membership(rows, previous=("STRONG9",)) == [
        "P1",
        "P2",
        "P3",
        "P4",
        "P5",
        "P6",
    ]


def test_excluded_product_fails_closed() -> None:
    rows = [row("PRODUCT", 1, 100.0, "EXCLUDED_LEVERAGED_OR_SYNTHETIC")]
    with pytest.raises(P2UError):
        confidence_swap_pair(rows)


def test_set_metrics_and_no_intersection_construction() -> None:
    metrics = set_metrics(["A", "B", "C"], ["B", "C", "D"])
    assert metrics["symmetric_difference_size"] == 2
    assert metrics["jaccard"] == pytest.approx(0.5)


def test_runner_help_and_fail_closed_outputs() -> None:
    help_result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "offline RD18-P2U" in help_result.stdout
    run_result = subprocess.run(
        [sys.executable, str(RUNNER), "--offline"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run_result.returncode == 0, run_result.stderr
    report = json.loads((OUT / "rd18-p2u-final-report-v1.json").read_text(encoding="utf-8"))
    assert report["decision"] == "RD18_P2U_EXCLUDED_PRODUCT_CONTAMINATION"
    assert report["variant_e_generated"] is False
    with (OUT / "excluded-product-audit.csv").open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {item["pair"] for item in rows} == PRODUCTS


def test_validator_help_and_passes_stop_record() -> None:
    help_result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
