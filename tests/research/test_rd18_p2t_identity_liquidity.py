"""Offline contract tests for RD18-P2T."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.kucoin_rd18_p2t import (
    IDENTITY_CLASSES,
    classify_identity,
    classify_liquidity,
    product_like,
    safe_ratio,
    set_counts,
    trailing_metrics,
)

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_inputs_reconcile() -> None:
    report = json.loads((ROOT / "data/research/rd18_p2t/input-reconciliation.json").read_text())
    assert report["passed"] is True
    assert report["counts"] == {
        "variant_c_pairs": 376,
        "variant_d_pairs": 299,
        "current_seed_only_pairs": 77,
        "weekly_decisions": 313,
        "post_warmup_decisions": 301,
    }


def test_identity_taxonomy_does_not_merge_by_symbol() -> None:
    result = classify_identity(
        pair="ABC-USDT",
        canonical_id="ABC",
        variant_d_canonical_ids={"ABC2"},
        historical_symbols={"ABC2": "ABC"},
        identity_status="RESOLVED",
        evidence_source="current_currency_non_causal_seed",
    )
    assert result["classification"] == "TEMPORALLY_DISTINCT_ASSET"
    assert result["variant_d_match"] == "false"
    assert set(IDENTITY_CLASSES) >= {result["classification"]}


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [("AGIX2L", True), ("APT2S", True), ("PEPE", False), ("BULL", True)],
)
def test_product_policy_is_diagnostic(symbol: str, expected: bool) -> None:
    assert product_like(symbol) is expected


def test_liquidity_metrics_and_flags_are_diagnostic() -> None:
    metrics = trailing_metrics([1.0, 1.0, 100.0])
    assert metrics["max_day_share"] == pytest.approx(100.0)
    flags = classify_liquidity(metrics, intraday_available=False)
    assert "EXTREME_SINGLE_DAY_CONCENTRATION" in flags
    assert "VOLUME_PATTERN_PLAUSIBLE" not in flags


def test_safe_ratio_and_set_counts() -> None:
    assert safe_ratio(2.0, 0.0) is None
    counts = set_counts(["A", "B"], ["A", "C"])
    assert counts["symmetric_difference_count"] == 2
    assert counts["jaccard"] == pytest.approx(1 / 3)


def test_output_identity_and_impact_cover_all_77() -> None:
    identity = pd.read_csv(
        ROOT / "data/research/rd18_p2t/current_seed_identity_audit.csv",
        dtype=str,
        keep_default_na=False,
    )
    impact = pd.read_csv(
        ROOT / "data/research/rd18_p2t/current_seed_impact_audit.csv",
        dtype=str,
        keep_default_na=False,
    )
    assert len(identity) == 77
    assert len(impact) == 77
    assert set(identity["asset_id"]) == set(impact["asset_id"])


def test_report_preserves_no_removal_and_no_replay() -> None:
    report = json.loads((ROOT / "data/research/rd18_p2t/rd18-p2t-final-report-v1.json").read_text())
    assert report["assets_removed"] == 0
    assert report["variant_e_created"] is False
    assert report["no_network"] is True
    assert report["no_returns"] is True
    assert report["no_trading"] is True
    assert report["no_optimization"] is True


def test_runner_help_is_offline() -> None:
    runner = ROOT / "scripts/research/run_rd18_p2t_identity_liquidity_audit.py"
    result = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "offline RD18-P2T" in result.stdout


def test_validator_help_is_offline() -> None:
    validator = ROOT / "scripts/research/validate_rd18_p2t_identity_liquidity_audit.py"
    result = subprocess.run(
        [sys.executable, str(validator), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Validate RD18-P2T" in result.stdout
