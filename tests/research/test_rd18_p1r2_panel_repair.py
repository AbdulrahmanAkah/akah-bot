"""Offline tests for the RD18-P1R2 excluded-product panel repair."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.kucoin_rd18_p1r2 import (
    PRODUCT_CLASSIFICATION,
    REGISTERED_PRODUCTS,
    classify_product_pair,
    contiguous_ranks,
    corrected_pairs,
    set_jaccard,
    symmetric_difference_size,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p1r2"
RUNNER = ROOT / "scripts" / "research" / "run_rd18_p1r2_panel_repair.py"
VALIDATOR = ROOT / "scripts" / "research" / "validate_rd18_p1r2_panel_repair.py"


def test_registered_product_classifier_and_false_positive_controls() -> None:
    assert len(REGISTERED_PRODUCTS) == 12
    for pair in REGISTERED_PRODUCTS:
        info = classify_product_pair(pair)
        assert info["is_product"] is True
        assert info["classification"] == PRODUCT_CLASSIFICATION
        assert info["registered"] is True
    for ordinary in (
        "BTC-USDT",
        "APT2-USDT",
        "MATIC-USDT",
        "TOKEN123-USDT",
        "SETUP-USDT",
        "BULL-USDT",
    ):
        assert classify_product_pair(ordinary)["is_product"] is False


def test_corrected_pairs_removes_only_registered_product_policy_matches() -> None:
    raw = {"BTC-USDT", "ETH-USDT", *REGISTERED_PRODUCTS}
    assert corrected_pairs(raw) == ("BTC-USDT", "ETH-USDT")


def test_rank_and_set_helpers() -> None:
    assert contiguous_ranks([{"liquidity_rank": 1}, {"liquidity_rank": 2}])
    assert not contiguous_ranks([{"liquidity_rank": 1}, {"liquidity_rank": 3}])
    assert set_jaccard({"A", "B"}, {"B", "C"}) == pytest.approx(1 / 3)
    assert symmetric_difference_size({"A", "B"}, {"B", "C"}) == 2


def test_runner_help_and_repaired_outputs() -> None:
    help_result = subprocess.run(
        [sys.executable, str(RUNNER), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "offline RD18-P1R2" in help_result.stdout
    run_result = subprocess.run(
        [sys.executable, str(RUNNER), "--offline"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run_result.returncode == 0, run_result.stderr
    report = json.loads((OUT / "rd18-p1r2-final-report-v1.json").read_text(encoding="utf-8"))
    assert report["decision"] == "RD18_P1R2_RESTRICTED_PANEL_REPAIRED"
    assert report["counts"]["raw_inventory_pairs"] == 376
    assert report["counts"]["corrected_c2_pairs"] == 364
    assert report["counts"]["corrected_d2_pairs"] == 299
    assert report["counts"]["corrected_c2_minus_d2_pairs"] == 65


def test_products_are_absent_before_corrected_aggregation() -> None:
    def read_rows(name: str) -> list[dict[str, str]]:
        with (OUT / name).open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    ranking = read_rows("corrected-weekly-rankings.csv")
    topn = read_rows("corrected-weekly-topn.csv")
    hyst = read_rows("corrected-hysteresis.csv")
    assert not any(row["pair"] in REGISTERED_PRODUCTS for row in ranking)
    assert not any(row["pair"] in REGISTERED_PRODUCTS for row in topn)
    assert not any(
        row["canonical_asset_id"] in {p.removesuffix("-USDT") for p in REGISTERED_PRODUCTS}
        for row in hyst
    )


def test_corrected_panel_retains_raw_provenance_and_marks_products() -> None:
    panel = pd.read_parquet(OUT / "corrected-daily-liquidity-panel.parquet")
    assert panel["pair"].nunique() == 376
    products = panel[panel["pair"].isin(REGISTERED_PRODUCTS)]
    assert not products["product_eligible"].any()
    assert set(products["exclusion_reason"]) == {"LEVERAGED_OR_SYNTHETIC_PRODUCT"}
    assert panel["open_time"].max() < pd.Timestamp("2025-01-01T00:00:00Z")


def test_validator_help_and_passes() -> None:
    help_result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
