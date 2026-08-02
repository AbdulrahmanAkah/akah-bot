"""Offline regression tests for RD18-P2U2."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from spotbot.research.kucoin_rd18_p2u2 import (
    CURRENT_SEED,
    EVIDENCE_STRONG,
    confidence_swap_pair,
    hysteresis_membership,
    relative_gap,
    set_metrics,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2u2"
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


def ranking_rows(gap: float = 0.05) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank in range(1, 11):
        confidence = EVIDENCE_STRONG
        if rank in {6, 8}:
            confidence = CURRENT_SEED
        liquidity = 100.0 - rank
        if rank == 7:
            liquidity = 94.0 * (1.0 - gap)
        if rank == 8:
            liquidity = 80.0
        if rank == 9:
            liquidity = 80.0 * (1.0 - gap)
        rows.append(
            {
                "pair": f"ASSET{rank}-USDT",
                "canonical_asset_id": f"ASSET{rank}",
                "original_c_rank": rank,
                "liquidity": liquidity,
                "confidence_class": confidence,
            }
        )
    return rows


def test_relative_gap_threshold_boundaries() -> None:
    assert relative_gap(100.0, 95.0) == pytest.approx(0.05)
    assert relative_gap(100.0, 90.0) == pytest.approx(0.10)
    assert relative_gap(100.0, 85.0) == pytest.approx(0.15)
    assert relative_gap(100.0, 84.999) > 0.15
    assert relative_gap(0.0, 1.0) is None


def test_adjacent_entry_and_retention_swaps_only() -> None:
    adjusted, audits = confidence_swap_pair(ranking_rows(0.05), 0.05)
    by_rank = {int(row["adjusted_rank"]): row["canonical_asset_id"] for row in adjusted}
    assert by_rank[6] == "ASSET7"
    assert by_rank[7] == "ASSET6"
    assert by_rank[8] == "ASSET9"
    assert by_rank[9] == "ASSET8"
    assert len(audits) == 2
    assert all(row["intervention_applied"] for row in audits)
    assert all(
        abs(int(row["adjusted_rank"]) - int(row["original_c_rank"])) <= 1 for row in adjusted
    )


def test_gap_above_threshold_and_same_class_do_not_swap() -> None:
    adjusted, audits = confidence_swap_pair(ranking_rows(0.10), 0.05)
    assert [row["canonical_asset_id"] for row in adjusted] == [f"ASSET{i}" for i in range(1, 11)]
    assert all(not row["intervention_applied"] for row in audits)
    ordinary = ranking_rows(0.01)
    ordinary[5]["confidence_class"] = EVIDENCE_STRONG
    ordinary[6]["confidence_class"] = EVIDENCE_STRONG
    ordinary[7]["confidence_class"] = EVIDENCE_STRONG
    ordinary[8]["confidence_class"] = EVIDENCE_STRONG
    adjusted, audits = confidence_swap_pair(ordinary, 0.15)
    assert [row["canonical_asset_id"] for row in adjusted] == [f"ASSET{i}" for i in range(1, 11)]
    assert audits[0]["reason_code"] == "SAME_CONFIDENCE_CLASS"


def test_no_non_adjacent_or_iterative_movement() -> None:
    adjusted, _ = confidence_swap_pair(ranking_rows(0.01), 0.10)
    movements = {
        row["canonical_asset_id"]: abs(int(row["adjusted_rank"]) - int(row["original_c_rank"]))
        for row in adjusted
    }
    assert max(movements.values()) == 1
    assert movements["ASSET6"] == 1
    assert movements["ASSET7"] == 1
    assert movements["ASSET8"] == 1
    assert movements["ASSET9"] == 1
    assert movements["ASSET5"] == 0
    assert movements["ASSET10"] == 0


def test_hysteresis_and_set_metrics() -> None:
    adjusted, _ = confidence_swap_pair(ranking_rows(0.01), 0.10)
    members = hysteresis_membership(adjusted, previous=("ASSET9",), capacity=6, retention_rank=8)
    assert len(members) == 6
    assert "ASSET9" in members
    metrics = set_metrics({"A", "B"}, {"B", "C"})
    assert metrics["exact_match"] is False
    assert metrics["symmetric_difference_size"] == 2
    assert metrics["substitution_count"] == 1.0
    assert metrics["jaccard"] == pytest.approx(1 / 3)


def test_reconciled_output_counts_and_product_exclusion() -> None:
    report = cast(
        dict[str, Any],
        json.loads((OUT / "rd18-p2u2-final-report-v1.json").read_text(encoding="utf-8")),
    )
    assert report["decision"] == "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_CONFIRMED"
    assert report["input_reconciliation"]["counts"]["c2_pairs"] == 364
    assert report["input_reconciliation"]["counts"]["d2_pairs"] == 299
    assert report["input_reconciliation"]["counts"]["c2_minus_d2_pairs"] == 65
    assert report["interventions"]["E10"] > 0
    for filename in (
        "weekly-e05-ranking.csv",
        "weekly-e10-ranking.csv",
        "weekly-e15-ranking.csv",
        "weekly-e-topn.csv",
        "e05-hysteresis.csv",
        "e10-hysteresis.csv",
        "e15-hysteresis.csv",
    ):
        with (OUT / filename).open("r", encoding="utf-8", newline="") as handle:
            assert not any(row.get("pair") in PRODUCTS for row in csv.DictReader(handle))


def test_zero_network_validator_and_runner_help() -> None:
    validator = subprocess.run(
        [sys.executable, "scripts/research/validate_rd18_p2u2_confidence_universe.py", "--offline"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"passed": true' in validator.stdout
    help_result = subprocess.run(
        [sys.executable, "scripts/research/run_rd18_p2u2_confidence_universe.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--offline" in help_result.stdout
