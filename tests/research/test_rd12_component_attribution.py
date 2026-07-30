from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

from spotbot.research.rd11_multi_asset_backtest import (
    SPEC_PATH,
    SPEC_SHA256,
    _classification,
)
from spotbot.research.rd12_component_attribution import (
    FLAG_NAMES,
    RD11_CONFIG_PATH,
    RD11_CONFIG_SHA256,
    RD12_ROOT,
    VARIANTS,
    _config,
    _flags,
)
from spotbot.strategies.regime_momentum_breakout import RegimeMomentumBreakoutConfig


def load_final() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((RD12_ROOT / "rd12-final-report-v1.json").read_text(encoding="utf-8")),
    )


def test_rd11_classification_correction_is_registered() -> None:
    report = json.loads(
        Path("data/research/rd11/rd11-final-report-v1.json").read_text(encoding="utf-8")
    )
    assert report["evidence_classification"] == "MIXED"
    correction = report["evidence_classification_correction"]
    assert correction["decision"] == "RD11_EVIDENCE_CLASSIFICATION_CORRECTED_TO_MIXED"
    assert correction["original_classification"] == "POSITIVE"


def test_net_profit_concentration_prevents_false_positive() -> None:
    metrics: dict[str, Any] = {
        "initial_equity": 100_000.0,
        "final_equity": 107_347.24,
        "net_return": 0.0734724,
        "expectancy": 306.0,
        "profit_factor": 1.57,
        "maximum_drawdown": 0.056,
        "benchmark_maximum_drawdown": 0.50,
        "closed_trade_count": 24,
        "pnl_contribution_by_asset": {
            "BTC/USDT": 8_316.35,
            "ADA/USDT": 2_141.96,
            "ETH/USDT": -1_686.04,
            "DOT/USDT": -1_001.31,
            "AVAX/USDT": -423.72,
        },
    }
    per_asset = {
        "BTC/USDT": {"metrics": {"net_return": 0.08}},
        "ADA/USDT": {"metrics": {"net_return": 0.02}},
        "ETH/USDT": {"metrics": {"net_return": -0.01}},
    }
    assert _classification(metrics, per_asset) == "MIXED"


def test_strategy_and_rd11_config_hashes_are_unchanged() -> None:
    assert hashlib.sha256(SPEC_PATH.read_bytes()).hexdigest() == SPEC_SHA256
    assert hashlib.sha256(RD11_CONFIG_PATH.read_bytes()).hexdigest() == RD11_CONFIG_SHA256
    final = load_final()
    assert final["strategy_unchanged"] is True
    assert final["strategy_specification_hash_before"] == final["strategy_specification_hash_after"]
    assert final["rd11_config_hash_before"] == final["rd11_config_hash_after"]


def test_twelve_unique_preregistered_configurations() -> None:
    assert len(VARIANTS) == 12
    assert len({variant.variant_id for variant in VARIANTS}) == 12
    final = load_final()
    assert final["variant_count"] == 12
    assert final["executed_variants"] == [variant.variant_id for variant in VARIANTS]


def test_each_variant_changes_only_declared_component_flags() -> None:
    baseline = _flags(RegimeMomentumBreakoutConfig())
    diffs = json.loads((RD12_ROOT / "rd12-config-diffs-v1.json").read_text(encoding="utf-8"))
    for variant in VARIANTS:
        flags = _flags(_config(variant))
        changed = {name for name in FLAG_NAMES if flags[name] != baseline[name]}
        assert changed == set(variant.changes)
        assert diffs[variant.variant_id]["observed_changed_fields"] == sorted(variant.changes)
        assert diffs[variant.variant_id]["all_other_component_flags_unchanged"] is True


def test_grouped_variants_match_declared_states() -> None:
    grouped = {variant.variant_id: _flags(_config(variant)) for variant in VARIANTS[-2:]}
    core = grouped["RD12_G01_BREAKOUT_CORE_ONLY"]
    assert core["enable_long_term_trend"] is False
    assert core["enable_medium_term_alignment"] is False
    assert core["enable_rsi_entry_filter"] is False
    assert core["enable_volume_confirmation"] is False
    assert core["enable_volatility_sanity"] is True
    exits = grouped["RD12_G02_INITIAL_STOP_AND_TIME_EXIT_ONLY"]
    assert exits["enable_trailing_stop"] is False
    assert exits["enable_ema50_exit"] is False
    assert exits["enable_rsi_exit"] is False
    assert exits["enable_time_stop"] is True


def test_baseline_reproduction_and_all_replays_pass() -> None:
    final = load_final()
    assert final["baseline_reproduction_match"] is True
    assert final["deterministic_replay_pass"] is True
    assert final["no_lookahead_pass"] is True
    assert final["reconciliation_pass"] is True
    for path in RD12_ROOT.rglob("validation-report.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["status"] == "PASS"
        assert report["no_lookahead"] is True
        assert report["next_bar_execution"] is True
        assert report["negative_cash_observed"] is False
        assert report["spot_only"] is True
        assert report["long_only"] is True
        assert report["no_leverage"] is True
        assert report["no_margin"] is True
        assert report["no_short"] is True
        assert report["no_dca"] is True
        assert report["no_kelly"] is True
        assert report["no_pyramiding"] is True
        assert report["no_averaging_down"] is True


def test_classification_thresholds_and_results_are_frozen() -> None:
    config = json.loads((RD12_ROOT / "rd12-config-v1.json").read_text(encoding="utf-8"))
    thresholds = config["classification_thresholds"]
    assert thresholds["supportive_return_delta"] == 0.01
    assert thresholds["risk_control_drawdown_delta"] == 0.02
    assert thresholds["harmful_return_improvement"] == 0.02
    assert thresholds["minimum_closed_trade_sample"] == 30
    rows = pd.read_csv(RD12_ROOT / "rd12-component-classification-v1.csv")
    individual = rows.loc[rows["kind"] != "GROUPED_DIAGNOSTIC"]
    assert set(individual["classification"]) == {"INCONCLUSIVE"}
    assert set(individual["classification_reason"]) == {"insufficient_trade_sample"}


def test_contribution_concentration_records_over_one_ratio() -> None:
    rows = pd.read_csv(RD12_ROOT / "rd12-concentration-analysis-v1.csv")
    baseline = rows.loc[rows["variant_id"] == "RD12_BASELINE"].iloc[0]
    assert baseline["largest_asset"] == "BTC/USDT"
    assert baseline["largest_asset_to_portfolio_net_profit"] == pytest.approx(1.131901450671518)


def test_no_forbidden_access_optimization_or_winner_selection() -> None:
    final = load_final()
    assert final["test_2025_accessed"] is False
    assert final["holdout_2026_accessed"] is False
    assert final["dune_api_called"] is False
    assert final["optimization_performed"] is False
    assert final["winner_selected"] is False
    assert final["decision"] == "RD12_REGIME_AND_COMPONENT_ATTRIBUTION_COMPLETED"
    assert final["next_stage"] == "RD13_SAMPLE_EXPANSION_WITH_FROZEN_RULES"
    for path in RD12_ROOT.rglob("*.csv"):
        frame = pd.read_csv(path)
        for column in ("timestamp", "entry_timestamp", "exit_timestamp", "period"):
            if column not in frame or frame.empty:
                continue
            timestamps = pd.to_datetime(frame[column], utc=True, errors="coerce").dropna()
            assert (timestamps.dt.year < 2025).all()
