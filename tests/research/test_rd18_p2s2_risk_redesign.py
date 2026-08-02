"""Offline tests for RD18-P2S2 corrected-universe risk redesign."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from spotbot.research.kucoin_rd18_p2s2 import (
    classify_boundary_opportunity,
    classify_liquidity_gap,
    confidence_aware_decision,
    disagreement_segments,
    dual_scenario_decision,
    leave_one_out_rate,
    set_jaccard,
    substitution_count,
    symmetric_difference_size,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2s2"
PRODUCTS = (
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
)


def load_json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((OUT / name).read_text(encoding="utf-8")))


def load_csv(name: str) -> list[dict[str, str]]:
    with (OUT / name).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def summary(name: str, metric: str, period: str) -> dict[str, str]:
    return next(
        row
        for row in load_csv(name)
        if row.get("diagnostic_type") == "SUMMARY"
        and row.get("metric") == metric
        and row.get("period") == period
    )


def test_input_reconciliation_and_corrected_counts() -> None:
    final = load_json("rd18-p2s2-final-report-v1.json")
    reconciliation = cast(dict[str, Any], final["input_reconciliation"])
    assert reconciliation["passed"] is True
    counts = cast(dict[str, Any], reconciliation["counts"])
    assert counts["raw_inventory_pairs"] == 376
    assert counts["c2_pairs"] == 364
    assert counts["d2_pairs"] == 299
    assert counts["c2_minus_d2_pairs"] == 65
    assert counts["weekly_decisions"] == 313
    assert counts["post_warmup_decisions"] == 301
    assert set(cast(dict[str, Any], reconciliation["hashes"])) == {
        "p1r",
        "p1r2",
        "p2r",
        "p2s",
        "p2t",
        "p2u",
        "p2r2",
    }


def test_product_exclusion_and_prohibited_outputs() -> None:
    final = load_json("rd18-p2s2-final-report-v1.json")
    assert final["variant_e_constructed"] is False
    assert final["p2u2_executed"] is False
    assert final["no_intersection_universe"] is True
    assert final["network_requests"] == 0
    for name in OUT.glob("*.csv"):
        text = name.read_text(encoding="utf-8")
        assert not any(product in text for product in PRODUCTS)
        assert not any(
            token in text.lower() for token in ("return", "trade", "signal", "candidate")
        )


def test_full_and_post_warmup_exact_match_counts() -> None:
    full = summary("corrected-exact-threshold-brittleness.csv", "TOP_6", "FULL")
    post = summary("corrected-exact-threshold-brittleness.csv", "TOP_6", "POST_WARMUP")
    assert (int(full["decision_count"]), int(full["exact_match_count"])) == (313, 158)
    assert (int(post["decision_count"]), int(post["exact_match_count"])) == (301, 148)
    assert full["old_50pct_threshold_above"] == "True"
    assert post["old_50pct_threshold_above"] == "False"


def test_substitution_distributions_and_hysteresis() -> None:
    rows = {
        (row["metric"], row["period"]): row
        for row in load_csv("corrected-substitution-distribution.csv")
    }
    top6 = rows[("TOP_6", "POST_WARMUP")]
    top10 = rows[("TOP_10", "POST_WARMUP")]
    hyst = rows[("HYSTERESIS", "POST_WARMUP")]
    assert (
        int(top6["zero_substitution_weeks"]),
        int(top6["one_substitution_weeks"]),
        int(top6["two_substitution_weeks"]),
    ) == (148, 144, 9)
    assert (
        int(top10["zero_substitution_weeks"]),
        int(top10["one_substitution_weeks"]),
        int(top10["two_substitution_weeks"]),
    ) == (69, 83, 81)
    assert (int(hyst["zero_substitution_weeks"]), int(hyst["one_substitution_weeks"])) == (117, 162)
    assert float(hyst["at_most_one_substitution_share"]) == pytest.approx(
        (162 + 117) / 301, rel=1e-12
    )


def test_set_distance_and_gap_boundaries() -> None:
    assert symmetric_difference_size({"a", "b"}, {"b", "c"}) == 2
    assert substitution_count({"a", "b"}, {"b", "c"}) == 1.0
    assert set_jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert classify_liquidity_gap(100.0, 90.0) == "NEAR_CUTOFF"
    assert classify_liquidity_gap(100.0, 75.0) == "MODERATE_GAP"
    assert classify_liquidity_gap(100.0, 74.0) == "LARGE_LIQUIDITY_GAP"
    assert classify_liquidity_gap(None, 10.0) == "ABSENT_FROM_VARIANT"
    assert classify_boundary_opportunity(0.05) == "UP_TO_5_PERCENT"
    assert classify_boundary_opportunity(0.10) == "ABOVE_5_THROUGH_10_PERCENT"
    assert classify_boundary_opportunity(0.15) == "ABOVE_10_THROUGH_15_PERCENT"
    assert classify_boundary_opportunity(0.151) == "ABOVE_15_PERCENT"


def test_leave_one_out_and_disagreement_duration() -> None:
    result = leave_one_out_rate([True, False, True, False])
    assert result["count"] == 2
    assert result["rate"] == 0.5
    segments = disagreement_segments(
        ["w1", "w2", "w3", "w4", "w5"],
        {"w1": {"a"}, "w2": {"a"}, "w3": set(), "w4": {"b"}, "w5": {"b"}},
        {"w1": set(), "w2": set(), "w3": set(), "w4": {"c"}, "w5": {"c"}},
    )
    assert [segment["duration_weeks"] for segment in segments] == [2, 2]
    assert segments[0]["persistent_4_weeks"] is False


def test_dual_and_confidence_decision_branches() -> None:
    passing = {"a": True, "b": True}
    decision, next_stage, auth = dual_scenario_decision(passing, integrity_pass=True)
    assert decision == "RD18_P2S2_DUAL_UNIVERSE_REPLAY_DESIGN_CONFIRMED"
    assert next_stage == "RD18_P3R_PREREGISTERED_DUAL_UNIVERSE_REPLAY_PROTOCOL"
    assert auth["dual_universe_protocol_design_authorized"] is True
    decision, next_stage, auth = confidence_aware_decision(passing, integrity_pass=True)
    assert decision == "RD18_P2S2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_REQUIRED"
    assert next_stage == "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN"
    assert auth["confidence_aware_design_authorized"] is True
    blocked, _, blocked_auth = confidence_aware_decision({"a": False}, integrity_pass=True)
    assert blocked == "RD18_P2S2_CORRECTED_UNIVERSE_UNCERTAINTY_REMAINS_UNACCEPTABLE"
    assert not any(blocked_auth.values())


def test_current_seed_concentration_and_boundary_audit() -> None:
    impact = load_csv("corrected-current-seed-asset-impact.csv")
    concentration = load_csv("corrected-current-seed-impact-concentration.csv")
    assert len(impact) == 65 * 2
    assert any(
        row.get("asset") == "BCHSV-USDT" and row.get("period") == "POST_WARMUP" for row in impact
    )
    assert int(concentration[0]["top6_slot_contribution"]) == 65
    assert int(concentration[1]["top6_slot_contribution"]) == 33
    boundary = load_csv("boundary-local-intervention-opportunity.csv")
    assert boundary
    assert all(row["swap_executed"] == "False" for row in boundary)


def test_dual_feasibility_and_final_authorization() -> None:
    dual = load_json("corrected-dual-scenario-feasibility.json")
    assert dual["feasible"] is False
    assert any(value is False for value in cast(dict[str, Any], dual["gates"]).values())
    confidence = load_json("confidence-aware-design-necessity.json")
    assert confidence["justified"] is True
    final = load_json("rd18-p2s2-final-report-v1.json")
    assert final["decision"] == "RD18_P2S2_CONFIDENCE_AWARE_UNIVERSE_DESIGN_REQUIRED"
    assert final["next_stage"] == "RD18_P2U2_CONFIDENCE_AWARE_UNIVERSE_DESIGN"
    authorization = cast(dict[str, Any], final["authorization"])
    assert authorization["confidence_aware_design_authorized"] is True
    assert authorization["strategy_replay_authorized"] is False
    assert authorization["production_authorized"] is False


def test_zero_network_validator_and_runner_help() -> None:
    validator = subprocess.run(
        [sys.executable, "scripts/research/validate_rd18_p2s2_risk_redesign.py", "--offline"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"network_requests": 0' in validator.stdout
    help_result = subprocess.run(
        [sys.executable, "scripts/research/run_rd18_p2s2_risk_redesign.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--offline" in help_result.stdout
