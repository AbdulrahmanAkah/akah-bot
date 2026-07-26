# ruff: noqa
"""AMS V5 Active Pullback & Reacceleration research adapter.

V5 is intentionally independent from the V4 protocol while reusing its
audited spot-only accounting primitive.  It changes the causal setup families,
stop construction, risk profiles and train-only threshold policy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from spotbot.research.ams_v4_active_conviction_swing import (
    AmsV4Error as AmsV5Error,
    PortfolioProfile,
    SimulationResult,
    assert_research_boundary,
    build_execution_panel as build_v4_panel,
    metrics,
    simulate_portfolio,
)
from spotbot.research.ams_v4_active_conviction_swing import specification as v4_specification


def portfolio_profiles() -> tuple[PortfolioProfile, ...]:
    return (
        PortfolioProfile("AMS-V5-PORTFOLIO-P01", "ACTIVE_BALANCED", 0.007, 0.0095, 0.045, 5),
        PortfolioProfile("AMS-V5-PORTFOLIO-P02", "CONTROLLED_CONVICTION", 0.0095, 0.013, 0.065, 6),
    )


def build_configuration_grid() -> tuple[dict[str, Any], ...]:
    variants = (
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_BALANCED", "NO_FIBONACCI"),
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_BALANCED", "SOFT_FIBONACCI_SCORE"),
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_WIDE", "NO_FIBONACCI"),
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_WIDE", "SOFT_FIBONACCI_SCORE"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_BALANCED", "NO_FIBONACCI"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_BALANCED", "SOFT_FIBONACCI_SCORE"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_WIDE", "NO_FIBONACCI"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_WIDE", "SOFT_FIBONACCI_SCORE"),
        ("MOMENTUM_REACCELERATION", "STRUCTURE_BALANCED", "NO_FIBONACCI"),
        ("MOMENTUM_REACCELERATION", "STRUCTURE_BALANCED", "SOFT_FIBONACCI_SCORE"),
        ("HYBRID_ALL_THREE", "STRUCTURE_BALANCED", "NO_FIBONACCI"),
        ("HYBRID_ALL_THREE", "STRUCTURE_BALANCED", "SOFT_FIBONACCI_SCORE"),
    )
    result: list[dict[str, Any]] = []
    for sequence, (family, stop_model, fib) in enumerate(variants, start=1):
        params = {
            "entry_family": family,
            "stop_model": stop_model,
            "fibonacci_mode": fib,
            "threshold_candidates": [50, 55],
            "execution_rule": "SIGNAL_CLOSE_NEXT_BAR_OPEN",
            "exit_model": "RUNNER_ONLY",
            "base_transaction_cost": 0.002,
            "stress_transaction_cost": 0.004,
            "spot_long_only": True,
            "leverage_allowed": False,
            "borrowing_allowed": False,
        }
        digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        result.append(
            {
                "configuration_id": f"AMS-V5-A{sequence:02d}",
                "parameters": params,
                "parameter_hash_sha256": digest,
                "trial_status": "REGISTERED_NOT_EXECUTED",
            }
        )
    return tuple(result)


def build_execution_panel(four_hour: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    """Create causal V5 setup kinds and 0-100 conviction scores."""
    panel = build_v4_panel(four_hour, availability).copy()
    assert_research_boundary(panel)
    panel = panel.sort_values(["symbol", "bar_close_time"], kind="mergesort")
    grouped = panel.groupby("symbol", sort=False)
    panel["pullback_atr"] = ((panel["ema_fast"] - panel["low"]) / panel["atr"]).clip(lower=0.0)
    trend = (panel["close"] > panel["ema_slow"]) & (panel["trend_slope"] > -0.002)
    reclaim = (panel["close"] > panel["ema_fast"]) & (panel["close"] > panel["open"])
    shallow = trend & panel["pullback_atr"].between(0.5, 1.5) & reclaim
    deep = trend & panel["pullback_atr"].between(1.5, 3.0) & reclaim & (panel["low"] >= panel["swing_low"])
    prior_high = grouped["high"].transform(lambda value: value.rolling(8, min_periods=4).max().shift(1))
    compression = grouped["high"].transform(lambda value: value.rolling(4).std()) < grouped["high"].transform(
        lambda value: value.rolling(20, min_periods=8).std()
    )
    reaccel = trend & compression.fillna(False) & (panel["close"] > prior_high) & panel["ema_distance_atr"].lt(3.2)
    panel["shallow_pullback_signal"] = shallow.fillna(False)
    panel["deep_pullback_signal"] = deep.fillna(False)
    panel["reacceleration_signal"] = reaccel.fillna(False)
    panel["setup_kind"] = np.select(
        [panel["shallow_pullback_signal"], panel["deep_pullback_signal"], panel["reacceleration_signal"]],
        ["SHALLOW_PULLBACK_RECLAIM", "DEEP_PULLBACK_RECOVERY", "MOMENTUM_REACCELERATION"],
        default="NONE",
    )
    panel["conviction_no_fib"] = (
        panel["d1_score"].clip(0, 12)
        + panel["trend_score"].clip(0, 18)
        + panel["rs_score"]
        + np.where(shallow | deep | reaccel, 25.0, 0.0)
        + panel["momentum_score"].clip(0, 12)
        + panel["structure_score"]
        + panel["liquidity_score"].clip(0, 8)
    ).clip(0, 100)
    panel["fib_score"] = panel["fib_score"].clip(-5.0, 5.0)
    panel["conviction_soft_fib"] = (panel["conviction_no_fib"] + panel["fib_score"]).clip(0, 100)
    return panel.sort_values(["bar_close_time", "symbol"], kind="mergesort").reset_index(drop=True)


def panel_for_configuration(panel: pd.DataFrame, configuration: Mapping[str, Any]) -> pd.DataFrame:
    """Map one V5 registered configuration to audited V4 execution columns."""
    params = configuration["parameters"]
    out = panel.copy()
    family = str(params["entry_family"])
    signal = {
        "SHALLOW_PULLBACK_RECLAIM": out["shallow_pullback_signal"],
        "DEEP_PULLBACK_RECOVERY": out["deep_pullback_signal"],
        "MOMENTUM_REACCELERATION": out["reacceleration_signal"],
    }
    selected = (
        signal[family]
        if family in signal
        else out["shallow_pullback_signal"] | out["deep_pullback_signal"] | out["reacceleration_signal"]
    )
    out["pullback_signal"] = selected.astype(bool)
    out["breakout_signal"] = False
    multiple = 3.0 if params["stop_model"] == "STRUCTURE_BALANCED" else 3.5
    maximum = 3.4 if params["stop_model"] == "STRUCTURE_BALANCED" else 4.0
    distance = (out["atr"] * multiple).clip(lower=out["atr"] * 2.2, upper=out["atr"] * maximum)
    out["initial_stop"] = out["close"] - distance
    out["stop_invalid"] = ~np.isfinite(out["initial_stop"])
    return out


def choose_threshold_train_only(
    panel: pd.DataFrame, configuration: Mapping[str, Any], profile: PortfolioProfile, train_end: pd.Timestamp
) -> tuple[int, dict[str, Any]]:
    """Frozen train-only policy; selects lower threshold for genuine activity scarcity.

    It uses only closed training bars and never inspects validation outcomes.
    """
    train = panel.loc[pd.to_datetime(panel["bar_open_time"], utc=True).lt(train_end)]
    prepared = panel_for_configuration(train, configuration)
    count = int(prepared["pullback_signal"].sum())
    threshold = 50 if count < 8_000 else 55
    return threshold, {
        "selection": "TRAIN_ONLY_ACTIVITY_ALIGNED_PRE_REGISTERED_RULE",
        "threshold": threshold,
        "train_raw_setup_count": count,
        "validation_inspected": False,
    }


def simulate(
    panel: pd.DataFrame, configuration: Mapping[str, Any], profile: PortfolioProfile, *, cost_mode: str, threshold: int
) -> SimulationResult:
    prepared = panel_for_configuration(panel, configuration)
    params = dict(configuration["parameters"])
    params.update(
        {
            "entry_family": "PULLBACK_CONTINUATION",
            "exit_model": "RUNNER_ONLY",
            "score_threshold": threshold,
            "fibonacci_mode": params["fibonacci_mode"],
            "minimum_stop_atr": 2.2,
            "typical_stop_atr": 3.0,
            "maximum_stop_atr": 4.0,
            "trailing_atr": 3.5,
        }
    )
    adapted = {"configuration_id": configuration["configuration_id"], "parameters": params}
    return simulate_portfolio(prepared, v4_specification(adapted, profile, cost_mode=cost_mode))


__all__ = [
    "AmsV5Error",
    "build_configuration_grid",
    "build_execution_panel",
    "choose_threshold_train_only",
    "metrics",
    "panel_for_configuration",
    "portfolio_profiles",
    "simulate",
]
