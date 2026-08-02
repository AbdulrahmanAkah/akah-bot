"""Offline RD18-P2R2 corrected structural-comparison contract tests."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.kucoin_rd18_p2r2 import (
    classify_omission_risk,
    concentration_metrics,
    decision_for_risk,
    persistence_summary,
    rank_displacement,
    set_jaccard,
    spearman_common,
    substitution_count,
    symmetric_difference_size,
    turnover_rows,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2r2"
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


def test_reconciled_counts_and_hashes() -> None:
    reconciliation = json.loads((OUT / "input-reconciliation.json").read_text())
    assert reconciliation["passed"] is True
    assert reconciliation["counts"]["raw_inventory_unique_pairs"] == 376
    assert reconciliation["counts"]["c2_pairs"] == 364
    assert reconciliation["counts"]["d2_pairs"] == 299
    assert reconciliation["counts"]["c2_minus_d2_pairs"] == 65
    assert reconciliation["counts"]["excluded_products"] == 12
    assert reconciliation["counts"]["weekly_decisions"] == 313
    assert reconciliation["counts"]["post_warmup_decisions"] == 301
    assert reconciliation["hashes"]["p1r2"] == (
        "0cc3d273e55aa1d1425de97b47fb5cad7610c6c2c7da6aec348850a635947048"
    )


def test_excluded_products_absent_from_corrected_membership_outputs() -> None:
    for name, column in (
        ("corrected-weekly-universe-growth.csv", "first_time_entrants"),
        ("corrected-weekly-rankings.csv", "pair"),
        ("corrected-weekly-topn.csv", "pair"),
    ):
        path = (
            ROOT / "data" / "research" / "rd18_p1r2" / name
            if "weekly-universe" not in name
            else OUT / name
        )
        if not path.is_file():
            continue
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        values = set(frame[column].astype(str)) if column in frame else set()
        assert not values & PRODUCTS


def test_set_distance_rank_and_spearman_primitives() -> None:
    assert set_jaccard({"A", "B"}, {"A", "C"}) == pytest.approx(1 / 3)
    assert symmetric_difference_size({"A", "B"}, {"A", "C"}) == 2
    assert substitution_count({"A", "B"}, {"A", "C"}) == 1
    assert rank_displacement({"A": 1, "B": 2}, {"A": 2, "B": 4}) == pytest.approx(1.5)
    assert spearman_common({"A": 1, "B": 2}, {"A": 1, "B": 2}) == pytest.approx(1.0)


def test_persistence_turnover_and_concentration() -> None:
    decisions = ["d1", "d2", "d3", "d4"]
    members = {"d1": {"A"}, "d2": {"A", "B"}, "d3": {"B"}, "d4": {"B"}}
    rows = persistence_summary(decisions, members)
    assert next(row for row in rows if row["asset"] == "A")["reentry_count"] == 0
    turnover = turnover_rows(decisions, members)
    assert turnover[1]["one_week_turnover_count"] == 1
    ranking = [
        {"liquidity_rank": 1, "trailing_28d_median_daily_quote_turnover_usdt": 100.0},
        {"liquidity_rank": 2, "trailing_28d_median_daily_quote_turnover_usdt": 50.0},
        {"liquidity_rank": 3, "trailing_28d_median_daily_quote_turnover_usdt": 25.0},
    ]
    concentration = concentration_metrics(ranking)
    assert concentration["eligible_count"] == 3
    assert concentration["hhi"] == pytest.approx(
        (100 / 175) ** 2 + (50 / 175) ** 2 + (25 / 175) ** 2
    )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((0.95, 0.90, 0.95, 0.05, 0.10, 0.90), "LOW"),
        ((0.80, 0.80, 0.85, 0.15, 0.25, 0.50), "MODERATE"),
        ((0.80, 0.80, 0.84, 0.15, 0.25, 0.50), "HIGH"),
        ((0.499999, 0.90, 0.95, 0.05, 0.10, 0.90), "SEVERE"),
    ],
)
def test_frozen_risk_boundaries(values: tuple[float, ...], expected: str) -> None:
    assert (
        classify_omission_risk(
            top6_exact=values[0],
            top10_exact=values[1],
            mean_top10_jaccard=values[2],
            current_seed_top6_share=values[3],
            max_year_seed_share=values[4],
            rank6_margin_above_10_share=values[5],
            unresolved_top10=False,
            unresolved_liquidity_top10=False,
            reproducible=True,
        )
        == expected
    )


def test_corrected_decision_and_restricted_flags() -> None:
    decision, next_stage, flags = decision_for_risk("HIGH", integrity_pass=True)
    assert decision == "RD18_P2R2_CORRECTED_UNIVERSE_ROBUSTNESS_REDESIGN_REQUIRED"
    assert next_stage == "RD18_P2S2_CORRECTED_UNIVERSE_RISK_REDESIGN"
    assert flags["strategy_replay_authorized"] is False
    report = json.loads((OUT / "rd18-p2r2-final-report-v1.json").read_text())
    assert report["risk_classification"] == "HIGH"
    assert (
        report["restricted_claim"]
        == "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
    )
    assert report["returns"] == report["trades"] == report["signals"] == report["candidates"] == 0


def test_corrected_comparison_and_current_seed_outputs() -> None:
    comparison = pd.read_csv(OUT / "corrected-variant-weekly-comparison.csv")
    d6 = comparison[(comparison.comparison == "D2_vs_C2") & (comparison.top_n.astype(str) == "6")]
    assert len(d6) == 313
    assert d6.exact_match.astype(str).str.lower().eq("true").mean() == pytest.approx(
        0.5047923322683706
    )
    seed = pd.read_csv(OUT / "corrected-current-seed-influence.csv")
    assert set(seed[seed.record_type == "ASSET"].asset) >= {
        "BCHSV-USDT",
        "PEPE-USDT",
        "NEO-USDT",
        "VET-USDT",
        "GRAM-USDT",
        "TEL-USDT",
        "SUI-USDT",
    }


def test_zero_network_and_no_sealed_period_markers() -> None:
    request = json.loads((OUT / "request-manifest.json").read_text())
    assert request["network_requests"] == 0
    report = json.loads((OUT / "rd18-p2r2-final-report-v1.json").read_text())
    assert report["post_2024_observations"] == 0
    assert report["futures"] == report["margin"] == 0
    for path in OUT.glob("*.csv"):
        text = path.read_text(encoding="utf-8")
        assert re.search(r"(?:^|[,;])202(?:5|6)(?:[-T,;]|$)", text) is None


def test_output_manifest_and_reports() -> None:
    manifest = json.loads((OUT / "output-manifest.json").read_text())
    encoded = "\n".join(f"{item['path']}:{item['sha256']}" for item in manifest["files"]).encode()
    assert hashlib.sha256(encoded).hexdigest() == manifest["deterministic_hash"]
    for name in (
        "rd18-p2r2-methodology-v1.md",
        "rd18-p2r2-results-v1.md",
        "rd18-p2r2-decisions-v1.md",
    ):
        text = (ROOT / "reports" / "research" / name).read_text(encoding="utf-8")
        assert "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS" in text


def test_runner_help_is_offline() -> None:
    runner = ROOT / "scripts" / "research" / "run_rd18_p2r2_structural_comparison.py"
    result = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "offline RD18-P2R2" in result.stdout
