from __future__ import annotations

from pathlib import Path

import pandas as pd

from spotbot.research.rd16e_components import (
    FAMILY_IDS,
    VARIANT_IDS,
    apply_same_symbol_cooldown,
    apply_variant,
    component_masks,
)
from spotbot.research.rd16e_evaluation import _decision


def _trades() -> pd.DataFrame:
    timestamps = pd.to_datetime(
        [
            "2024-01-01T00:00:00Z",
            "2024-01-01T12:00:00Z",
            "2024-01-03T00:00:00Z",
            "2024-01-04T00:00:00Z",
        ],
        utc=True,
    )
    return pd.DataFrame(
        {
            "trade_id": ["t1", "t2", "t3", "t4"],
            "symbol": ["BTC/USDT", "BTC/USDT", "NEAR/USDT", "SOL/USDT"],
            "signal_close": timestamps,
            "entry_open_time": timestamps,
            "market_regime": ["STRONG_BULL", "TRANSITION", "STRONG_BULL", "BEAR"],
            "volatility_regime": [
                "NORMAL_VOLATILITY",
                "NORMAL_VOLATILITY",
                "HIGH_VOLATILITY",
                "LOW_VOLATILITY",
            ],
            "f_open": [100.0, 100.0, 100.0, 100.0],
            "f_high": [104.0, 103.0, 102.0, 105.0],
            "f_low": [99.0, 99.0, 98.0, 99.0],
            "f_close": [103.0, 102.0, 101.0, 104.0],
            "f_volume": [120.0, 90.0, 100.0, 120.0],
            "f_ema20": [101.0, 101.0, 100.0, 101.0],
            "f_atr14": [4.0, 4.0, 4.0, 4.0],
            "f_prior_high24": [101.5, 101.5, 100.5, 102.0],
            "f_volume_median20": [100.0, 100.0, 100.0, 100.0],
            "f_4h_close": [104.0, 103.0, 102.0, 105.0],
            "f_4h_ema20": [102.0, 102.0, 101.0, 103.0],
            "f_4h_ema50": [100.0, 101.0, 100.0, 101.0],
            "f_prior_high12": [101.5, 101.5, 100.5, 102.0],
            "f_range_1h": [5.0, 4.0, 4.0, 6.0],
            "f_4h_atr_ratio": [0.80, 0.95, 1.30, 0.75],
            "f_prior_low12": [99.0, 99.0, 98.0, 100.0],
        }
    )


def test_registered_matrix_has_four_by_ten() -> None:
    assert len(FAMILY_IDS) == 4
    assert len(VARIANT_IDS) == 10
    assert len(FAMILY_IDS) * len(VARIANT_IDS) == 40


def test_trend_diagnostic_gates_remove_transition_high_vol_and_near() -> None:
    frame = _trades()
    filtered = apply_variant(
        frame,
        family_id="MTF_TREND_BREAKOUT",
        variant_id="ALL_DIAGNOSTIC_GATES",
    )
    assert filtered["trade_id"].tolist() == ["t1", "t4"]


def test_pullback_asset_gate_keeps_registered_core_assets() -> None:
    frame = _trades()
    filtered = apply_variant(
        frame,
        family_id="MTF_PULLBACK_RECLAIM",
        variant_id="ASSET_GATE",
    )
    assert filtered["trade_id"].tolist() == ["t1", "t2", "t4"]


def test_range_component_salvage_is_transition_and_sol_specific() -> None:
    frame = _trades()
    masks = component_masks(frame, "MTF_RANGE_RECLAIM")
    assert masks["regime"].tolist() == [False, True, False, False]
    assert masks["asset"].tolist() == [False, False, False, True]


def test_same_symbol_cooldown_is_causal_and_stable() -> None:
    frame = _trades()
    cooled = apply_same_symbol_cooldown(frame, hours=24)
    assert cooled["trade_id"].tolist() == ["t1", "t3", "t4"]


def test_components_do_not_filter_on_realized_outcomes() -> None:
    source = Path("src/spotbot/research/rd16e_components.py").read_text(encoding="utf-8")
    for forbidden in ("net_pnl", "gross_pnl", "mfe_r", "mae_r", "exit_reason"):
        assert forbidden not in source


def test_retention_decision_requires_all_fixed_gates() -> None:
    metrics: dict[str, object] = {
        "trade_count": 120,
        "net_return": 0.50,
        "profit_factor": 1.30,
        "maximum_drawdown": 0.20,
        "capital_feasible": True,
    }
    cost_2x: dict[str, object] = {
        "net_return": 0.10,
        "profit_factor": 1.05,
        "capital_feasible": True,
    }
    decision, carry, _ = _decision(
        variant_id="FULL_REMEDIATION_STACK",
        metrics=metrics,
        cost_2x=cost_2x,
        positive_year_fraction=0.60,
        delta_profit_factor=0.20,
        drawdown_reduction=0.10,
        delta_two_x_return=0.30,
    )
    assert decision == "RETAIN_FOR_COMPOSITE_RESEARCH"
    assert carry is True


def test_small_component_is_not_carried_forward() -> None:
    metrics: dict[str, object] = {
        "trade_count": 20,
        "net_return": 0.50,
        "profit_factor": 2.00,
        "maximum_drawdown": 0.10,
        "capital_feasible": True,
    }
    cost_2x: dict[str, object] = {
        "net_return": 0.20,
        "profit_factor": 1.30,
        "capital_feasible": True,
    }
    decision, carry, _ = _decision(
        variant_id="REGIME_GATE",
        metrics=metrics,
        cost_2x=cost_2x,
        positive_year_fraction=1.0,
        delta_profit_factor=1.0,
        drawdown_reduction=0.2,
        delta_two_x_return=1.0,
    )
    assert decision == "INSUFFICIENT_SAMPLE"
    assert carry is False
