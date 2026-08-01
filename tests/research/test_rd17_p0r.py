from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

from scripts.research.run_rd17_p0r import (
    classify,
    metric_value,
)


def test_metric_policies_do_not_silently_mix() -> None:
    row: dict[str, object] = {
        "current_market_cap_usd": 10.0,
        "estimated_market_cap_usd": 25.0,
    }
    assert metric_value(row, "CURRENT_ONLY") == (
        10.0,
        "CapMrktCurUSD",
    )
    assert metric_value(row, "ESTIMATED_ONLY") == (
        25.0,
        "CapMrktEstUSD",
    )
    assert metric_value(
        row,
        "CURRENT_THEN_ESTIMATED_FALLBACK",
    ) == (10.0, "CapMrktCurUSD")


def test_fallback_uses_estimated_only_when_current_missing() -> None:
    row: dict[str, object] = {
        "current_market_cap_usd": None,
        "estimated_market_cap_usd": 25.0,
    }
    assert metric_value(
        row,
        "CURRENT_THEN_ESTIMATED_FALLBACK",
    ) == (25.0, "CapMrktEstUSD")
    assert metric_value(row, "CURRENT_ONLY") == (None, None)


def summary_frame(current_exact: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "policy": "CURRENT_ONLY",
                "exact_top6_match_count": current_exact,
                "mean_jaccard_similarity": 0.9,
            },
            {
                "policy": "ESTIMATED_ONLY",
                "exact_top6_match_count": 0,
                "mean_jaccard_similarity": 0.5,
            },
            {
                "policy": "CURRENT_THEN_ESTIMATED_FALLBACK",
                "exact_top6_match_count": 0,
                "mean_jaccard_similarity": 0.6,
            },
            {
                "policy": "REGISTERED_LOCAL_PANEL",
                "exact_top6_match_count": 0,
                "mean_jaccard_similarity": 0.55,
            },
        ]
    )


def test_missing_current_coverage_blocks_p1() -> None:
    coverage = pd.DataFrame({"current_metric_available": [True, False]})
    provenance = pd.DataFrame(
        {
            "inferred_registered_metric": [
                "CLOSER_TO_CURRENT",
                "CLOSER_TO_ESTIMATED",
            ]
        }
    )
    decision, next_stage, _gates = classify(
        summary_frame(3),
        coverage,
        provenance,
    )
    assert decision == ("RD17_P0R_COINMETRICS_COMMUNITY_COVERAGE_INSUFFICIENT")
    assert next_stage == ("RD17_P0S_ALTERNATE_PIT_MARKET_CAP_SOURCE_SELECTION")


def test_full_current_match_authorizes_candidate_generation() -> None:
    coverage = pd.DataFrame({"current_metric_available": [True, True]})
    provenance = pd.DataFrame(
        {
            "inferred_registered_metric": [
                "CLOSER_TO_CURRENT",
                "CLOSER_TO_CURRENT",
            ]
        }
    )
    decision, next_stage, _gates = classify(
        summary_frame(4),
        coverage,
        provenance,
    )
    assert decision == ("RD17_P0R_CURRENT_METRIC_AND_SOURCE_CONFIRMED")
    assert next_stage == ("RD17_P1_FROZEN_ENGINE_FULL_PIT_CANDIDATE_GENERATION")


def test_runner_supports_direct_execution() -> None:
    repo = Path(__file__).resolve().parents[2]
    runner = repo / "scripts" / "research" / "run_rd17_p0r.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
