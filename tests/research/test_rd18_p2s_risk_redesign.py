# ruff: noqa: E501

"""Offline RD18-P2S contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.kucoin_rd18_p2s import (
    classify_dual_scenario,
    classify_liquidity_gap,
    disagreement_distribution,
    disagreement_segments,
    exact_match,
    set_jaccard,
    substitution_count,
    symmetric_difference_size,
)

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_input_counts_and_hashes() -> None:
    report = json.loads((ROOT / "data/research/rd18_p2s/input-reconciliation.json").read_text())
    assert report["passed"] is True
    assert report["counts"] == {
        "variant_c_pairs": 376,
        "variant_d_pairs": 299,
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
    }
    assert (
        report["p1r_manifest_hash"]
        == "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0"
    )
    assert (
        report["p2r_manifest_hash"]
        == "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a"
    )


def test_exact_match_and_one_week_threshold_boundary() -> None:
    assert exact_match(["A", "B"], ["B", "A"])
    assert symmetric_difference_size(["A", "B"], ["A", "C"]) == 2
    assert substitution_count(["A", "B"], ["A", "C"]) == 1
    assert set_jaccard(["A", "B"], ["A", "C"]) == pytest.approx(1 / 3)


def test_disagreement_distribution_and_duration() -> None:
    result = disagreement_distribution([0, 1, 2, 3, 4])
    assert result["zero_substitution_weeks"] == 1
    assert result["one_substitution_weeks"] == 1
    assert result["two_substitution_weeks"] == 1
    assert result["three_or_more_substitution_weeks"] == 2
    segments = disagreement_segments(
        ["d1", "d2", "d3", "d4"],
        {"d1": {"A"}, "d2": {"A"}, "d3": {"B"}, "d4": set()},
        {"d1": {"C"}, "d2": {"C"}, "d3": {"B"}, "d4": set()},
    )
    assert segments[0]["duration_weeks"] == 2
    assert segments[0]["persistent_4_weeks"] is False


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        (100.0, 95.0, "NEAR_CUTOFF"),
        (100.0, 80.0, "MODERATE_GAP"),
        (100.0, 50.0, "LARGE_LIQUIDITY_GAP"),
        (100.0, None, "ABSENT_FROM_VARIANT"),
    ],
)
def test_frozen_liquidity_gap_classes(left: float, right: float | None, expected: str) -> None:
    assert classify_liquidity_gap(left, right) == expected


def test_dual_scenario_decision_branches() -> None:
    passing = {f"gate_{index}": True for index in range(15)}
    decision, next_stage, flags = classify_dual_scenario(
        passing, consensus_complete=True, integrity_pass=True
    )
    assert decision == "RD18_P2S_DUAL_UNIVERSE_REPLAY_DESIGN_CONFIRMED"
    assert next_stage == "RD18_P3R_PREREGISTERED_DUAL_UNIVERSE_REPLAY"
    assert flags["dual_universe_replay_design_authorized"] is True
    failing = dict(passing)
    failing["gate_1"] = False
    decision, _, flags = classify_dual_scenario(
        failing, consensus_complete=True, integrity_pass=True
    )
    assert decision == "RD18_P2S_CONSENSUS_UNIVERSE_REDESIGN_REQUIRED"
    assert flags["production_authorized"] is False
    decision, _, _ = classify_dual_scenario(failing, consensus_complete=False, integrity_pass=True)
    assert decision == "RD18_P2S_UNIVERSE_UNCERTAINTY_REMAINS_UNACCEPTABLE"


def test_final_report_is_restricted_and_design_only() -> None:
    report = json.loads((ROOT / "data/research/rd18_p2s/rd18-p2s-final-report-v1.json").read_text())
    assert (
        report["restricted_claim"]
        == "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
    )
    assert report["full_inventory_claim"] is False
    assert report["no_strategy_returns"] is True
    assert report["no_trading"] is True
    assert report["network_requests"] == 0


def test_frozen_p2s_result_uses_consensus_redesign_path() -> None:
    report = json.loads((ROOT / "data/research/rd18_p2s/rd18-p2s-final-report-v1.json").read_text())
    gates = report["diagnostics"]["gates"]
    assert gates["mean_hysteresis_jaccard"] is False
    assert gates["top10_at_most_two_substitutions"] is False
    assert report["diagnostics"]["consensus_complete"] is True
    assert report["decision"] == "RD18_P2S_CONSENSUS_UNIVERSE_REDESIGN_REQUIRED"
    assert report["next_stage"] == "RD18_BLOCKED_PENDING_CONSENSUS_UNIVERSE_PROTOCOL"
    assert report["authorization"]["production_authorized"] is False


def test_threshold_brittleness_and_disagreement_outputs() -> None:
    threshold = pd.read_csv(ROOT / "data/research/rd18_p2s/exact-threshold-brittleness.csv")
    row = threshold[(threshold.metric == "TOP_6") & (threshold.period == "FULL")].iloc[0]
    assert int(row.exact_match_count) == 156
    assert int(row.additional_exact_weeks_to_reach_50pct) == 1
    assert int(row.threshold_distance_weeks) == -1
    distribution = pd.read_csv(ROOT / "data/research/rd18_p2s/set-disagreement-distribution.csv")
    row = distribution[
        (distribution.metric == "TOP_6") & (distribution.period == "POST_WARMUP")
    ].iloc[0]
    assert int(row.zero_substitution_weeks) == 148
    assert int(row.one_substitution_weeks) == 144


def test_consensus_and_current_seed_concentration_are_diagnostic_only() -> None:
    consensus = pd.read_csv(ROOT / "data/research/rd18_p2s/consensus-diagnostics.csv")
    assert bool(consensus.iloc[12:].top_6_complete.all())
    assert int(consensus.iloc[12:].core_size.min()) >= 6
    concentration = pd.read_csv(
        ROOT / "data/research/rd18_p2s/current-seed-impact-concentration.csv"
    )
    assert concentration.cumulative_slot_share.max() == pytest.approx(1.0)
    future = json.loads(
        (ROOT / "data/research/rd18_p2s/future-dual-universe-replay-requirements.json").read_text()
    )
    assert future["strategy_replay_executed"] is False
    assert future["production_authorized"] is False


def test_runner_help_is_offline() -> None:
    runner = ROOT / "scripts/research/run_rd18_p2s_risk_redesign.py"
    result = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "offline RD18-P2S" in result.stdout
