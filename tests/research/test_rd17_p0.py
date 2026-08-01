from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts.research.run_rd17_p0 import (
    classify,
)


def test_clean_manual_verification_pass() -> None:
    comparison = pd.DataFrame(
        {
            "comparison_gate": [True] * 4,
            "exact_set_match": [True] * 4,
            "minimum_overlap_gate": [True] * 4,
            "rank_displacement_gate": [True] * 4,
            "market_cap_unit_ratio_gate": [True] * 4,
        }
    )
    timing = pd.DataFrame({"timing_and_unit_gate": [True] * 4})
    decision, next_stage, gates = classify(comparison, timing)
    assert decision == "RD17_P0_UNIVERSE_METHOD_CONFIRMED"
    assert next_stage == ("RD17_P1_FROZEN_ENGINE_FULL_PIT_CANDIDATE_GENERATION")
    assert gates["exact_top6_set_match_all_snapshots"]


def test_source_difference_pass_requires_core_gates() -> None:
    comparison = pd.DataFrame(
        {
            "comparison_gate": [True] * 4,
            "exact_set_match": [True, True, False, True],
            "minimum_overlap_gate": [True] * 4,
            "rank_displacement_gate": [True] * 4,
            "market_cap_unit_ratio_gate": [True] * 4,
        }
    )
    timing = pd.DataFrame({"timing_and_unit_gate": [True] * 4})
    decision, next_stage, _gates = classify(comparison, timing)
    assert decision == ("RD17_P0_UNIVERSE_METHOD_CONFIRMED_WITH_SOURCE_DIFFERENCES")
    assert next_stage == ("RD17_P1_FROZEN_ENGINE_FULL_PIT_CANDIDATE_GENERATION")


def test_weak_overlap_rejects_method() -> None:
    comparison = pd.DataFrame(
        {
            "comparison_gate": [True, True, False, True],
            "exact_set_match": [True, True, False, True],
            "minimum_overlap_gate": [True, True, False, True],
            "rank_displacement_gate": [True] * 4,
            "market_cap_unit_ratio_gate": [True] * 4,
        }
    )
    timing = pd.DataFrame({"timing_and_unit_gate": [True] * 4})
    decision, next_stage, _gates = classify(comparison, timing)
    assert decision == "RD17_P0_UNIVERSE_METHOD_REJECTED"
    assert next_stage == "RD17_P0_RANKING_METHOD_REPAIR_REQUIRED"


def test_timing_failure_rejects_method() -> None:
    comparison = pd.DataFrame(
        {
            "comparison_gate": [True] * 4,
            "exact_set_match": [True] * 4,
            "minimum_overlap_gate": [True] * 4,
            "rank_displacement_gate": [True] * 4,
            "market_cap_unit_ratio_gate": [True] * 4,
        }
    )
    timing = pd.DataFrame({"timing_and_unit_gate": [True, True, False, True]})
    decision, _next_stage, _gates = classify(comparison, timing)
    assert decision == "RD17_P0_UNIVERSE_METHOD_REJECTED"


def test_runner_supports_direct_execution() -> None:
    repo = Path(__file__).resolve().parents[2]
    runner = repo / "scripts" / "research" / "run_rd17_p0.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
