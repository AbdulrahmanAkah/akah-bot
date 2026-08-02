# ruff: noqa: E501

"""Offline contract tests for RD18-P2R structural comparison."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from spotbot.research.kucoin_rd18_p2r import (
    classify_omission_risk,
    classify_provenance,
    concentration_metrics,
    decision_for_risk,
    exact_match,
    membership_summary,
    rank_displacement,
    set_jaccard,
    spearman_common,
    turnover_summary,
)

ROOT = Path(__file__).resolve().parents[2]


def test_p1r_hash_and_exact_variants_reconcile() -> None:
    report = json.loads((ROOT / "data/research/rd18_p2r/input-reconciliation.json").read_text())
    assert report["passed"] is True
    assert report["counts"]["variant_sizes"] == {
        "A_P0": 68,
        "B_P0A": 300,
        "C_P0B": 376,
        "D_EVIDENCE_STRONG": 299,
    }
    assert report["counts"]["weekly_decisions"] == 313
    assert report["counts"]["post_warmup_decisions"] == 301


def test_provenance_distinguishes_current_seed_only() -> None:
    assert (
        classify_provenance(["current_currency_non_causal_seed"])
        == "CURRENT_SEED_ONLY_KLINE_CONFIRMED"
    )
    assert classify_provenance(["rd18_p0_historical_evidence"]) == "REPOSITORY_SEEDED_CONFIRMED"
    assert (
        classify_provenance(["announcement_listing", "rd18_p0_historical_evidence"])
        == "MULTI_CHANNEL_CONFIRMED"
    )


def test_set_and_rank_metrics_are_deterministic() -> None:
    assert exact_match(["A", "B"], ["B", "A"])
    assert set_jaccard(["A", "B"], ["B", "C"]) == pytest.approx(1 / 3)
    assert rank_displacement({"A": 1, "B": 2}, {"A": 2, "B": 1}) == 1.0
    assert spearman_common({"A": 1, "B": 2}, {"A": 1, "B": 2}) == pytest.approx(1.0)


def test_concentration_and_cutoff_metrics() -> None:
    result = concentration_metrics(
        [
            {"rank": 1, "liquidity": 100.0},
            {"rank": 2, "liquidity": 50.0},
            {"rank": 3, "liquidity": 25.0},
            {"rank": 4, "liquidity": 10.0},
            {"rank": 5, "liquidity": 9.0},
            {"rank": 6, "liquidity": 8.0},
            {"rank": 7, "liquidity": 7.0},
        ]
    )
    assert result["eligible_count"] == 7
    assert result["hhi"] > 0
    assert result["rank_6_7_margin"] == pytest.approx(0.125)


def test_membership_duration_reentry_and_turnover() -> None:
    decisions = ["d1", "d2", "d3", "d4"]
    members = {"d1": {"A"}, "d2": {"A", "B"}, "d3": {"B"}, "d4": {"A", "B"}}
    summary = {row["asset"]: row for row in membership_summary(decisions, members)}
    assert summary["A"]["entry_count"] == 2
    assert summary["A"]["reentry_count"] == 1
    turnover = turnover_summary(decisions, members)
    assert turnover[1]["one_week_turnover_count"] == 1


@pytest.mark.parametrize(
    ("risk", "expected"),
    [
        ("LOW", "RD18_P2R_SINGLE_RESTRICTED_UNIVERSE_ACCEPTABLE"),
        ("MODERATE", "RD18_P2R_DUAL_UNIVERSE_ROBUSTNESS_REQUIRED"),
        ("HIGH", "RD18_P2R_DUAL_UNIVERSE_ROBUSTNESS_REQUIRED"),
        ("SEVERE", "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE"),
    ],
)
def test_decision_branches(risk: str, expected: str) -> None:
    decision, _, _ = decision_for_risk(risk, integrity_pass=True)
    assert decision == expected


def test_severe_boundary_is_strictly_below_fifty_percent() -> None:
    assert (
        classify_omission_risk(
            d_top6_exact=0.499999,
            d_top10_exact=0.95,
            mean_top10_jaccard=0.95,
            current_seed_top6_share=0.01,
            max_year_seed_share=0.01,
            rank6_rank7_above_10_share=0.95,
            unresolved_top10=False,
            reproducible=True,
        )
        == "SEVERE"
    )
    assert (
        classify_omission_risk(
            d_top6_exact=0.50,
            d_top10_exact=0.90,
            mean_top10_jaccard=0.85,
            current_seed_top6_share=0.10,
            max_year_seed_share=0.10,
            rank6_rank7_above_10_share=0.90,
            unresolved_top10=False,
            reproducible=True,
        )
        == "HIGH"
    )


def test_final_report_has_restricted_claim_and_no_return_outputs() -> None:
    report = json.loads((ROOT / "data/research/rd18_p2r/rd18-p2r-final-report-v1.json").read_text())
    assert (
        report["restricted_claim"]
        == "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
    )
    assert report["full_historical_inventory_claim"] is False
    assert report["no_strategy_returns"] is True
    assert report["no_trading"] is True
    assert report["network_requests"] == 0


def test_runner_help_is_available_without_network() -> None:
    runner = ROOT / "scripts/research/run_rd18_p2r_structural_comparison.py"
    result = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "offline RD18-P2R" in result.stdout
