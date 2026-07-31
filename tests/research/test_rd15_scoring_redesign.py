from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from spotbot.core.engine import PortfolioSnapshot
from spotbot.research.rd15_scoring_redesign import _evidence
from spotbot.strategies.scored_breakout_v2 import (
    STRATEGY_ID,
    ScoredBreakoutV2Config,
    ScoredBreakoutV2Strategy,
    overextension_penalty,
    profit_floor_r,
)


def test_v2_registration_and_frozen_design() -> None:
    config = ScoredBreakoutV2Config()
    config.validate()
    assert STRATEGY_ID == "AKAH_SCORED_BREAKOUT_V2"
    assert config.entry_threshold == 60.0
    assert config.breakout_floor == 12.0
    assert config.risk_floor == 8.0
    assert config.risk_per_trade == 0.01
    assert config.initial_stop_atr == 2.0


def test_profit_floor_is_inactive_then_monotonic() -> None:
    assert profit_floor_r(1.49) is None
    floors = [profit_floor_r(value) for value in (1.5, 2.0, 3.0, 4.0, 6.0, 10.0)]
    numeric = [float(value) for value in floors if value is not None]
    assert numeric == sorted(numeric)
    assert math.isclose(float(profit_floor_r(2.0)), 0.8)
    assert math.isclose(float(profit_floor_r(4.0)), 2.2)
    assert math.isclose(float(profit_floor_r(10.0)), 6.5)


def test_profit_floor_rejects_non_finite_mfe() -> None:
    with pytest.raises(ValueError):
        profit_floor_r(float("nan"))


def test_overextension_penalty_is_zero_in_normal_zone_and_capped() -> None:
    assert overextension_penalty(extension_z=1.5, rsi=70.0, range_ratio=1.5) == 0.0
    assert 0 < overextension_penalty(extension_z=3.0, rsi=84.0, range_ratio=3.0) < 16.0
    assert overextension_penalty(extension_z=10.0, rsi=99.0, range_ratio=10.0) == 16.0


def test_market_regime_is_penalty_not_veto() -> None:
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    features = {
        "BTC/USDT": {
            timestamp: {
                "close": 90.0,
                "ema_50": 95.0,
                "ema_200": 100.0,
            }
        },
        "ETH/USDT": {},
    }
    strategy = ScoredBreakoutV2Strategy(features=features, cohort="TEST")
    regime, penalty = strategy._market_regime(timestamp)
    assert regime == "BEAR"
    assert penalty == 10.0
    assert penalty < ScoredBreakoutV2Config().entry_threshold


def test_score_remains_ranking_key_after_broad_eligibility() -> None:
    config = ScoredBreakoutV2Config()
    assert config.entry_threshold < 70.0
    assert config.breakout_floor < 15.0
    assert config.risk_floor < 10.0


def test_position_sizing_does_not_depend_on_score() -> None:
    config = ScoredBreakoutV2Config()
    assert config.risk_per_trade == 0.01
    assert config.risk_per_trade == ScoredBreakoutV2Config(entry_threshold=65.0).risk_per_trade


def test_portfolio_snapshot_api_remains_compatible() -> None:
    snapshot = PortfolioSnapshot(
        cash=100000.0,
        equity=100000.0,
        total_fees=0.0,
        realized_pnl=0.0,
        positions=(),
    )
    assert snapshot.position("BTC/USDT") is None


def test_evidence_uses_repository_closed_trade_count_schema() -> None:
    primary_metrics = {
        "net_return": 1.0,
        "expectancy": 100.0,
        "profit_factor": 2.0,
        "maximum_drawdown": 0.20,
        "closed_trade_count": 35,
        "profitable_asset_count": 3,
    }
    primary = {
        "metrics": primary_metrics,
        "deterministic_replay_match": True,
    }
    transfer = {
        "metrics": {"net_return": 0.10},
        "deterministic_replay_match": True,
    }
    classification, gates = _evidence(
        primary=primary,
        transfer=transfer,
        rd14_metrics={"maximum_drawdown": 0.30},
    )
    assert classification == "PROMISING"
    assert gates["closed_trades_gte_35"] is True
