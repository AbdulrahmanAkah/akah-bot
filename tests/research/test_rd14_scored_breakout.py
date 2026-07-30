from __future__ import annotations

import math
from dataclasses import replace

import pytest

from spotbot.research.rd14_scored_breakout import (
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    CONFIGURATIONS,
    ENTRY_WEIGHTS,
    HEALTH_WEIGHTS,
    _configuration,
    _entry_bin,
    _health_bin,
    _specification_payload,
)
from spotbot.strategies.scored_breakout import (
    ScoredBreakoutConfig,
    ScoredBreakoutStrategy,
    atr_quality_score,
    clip01,
    extension_quality_score,
    linear_score,
    rsi_entry_score,
    rsi_health_score,
)


def test_specification_registration_and_frozen_weights() -> None:
    payload = _specification_payload()
    assert payload["strategy_id"] == "AKAH_SCORED_BREAKOUT_V1"
    assert payload["status"] == "REGISTERED_FOR_RD14_CONTROLLED_VALIDATION"
    assert sum(ENTRY_WEIGHTS.values()) == 100
    assert sum(HEALTH_WEIGHTS.values()) == 100
    assert payload["optimization_performed"] is False
    assert payload["winner_selected"] is False
    assert payload["test_2025_accessed"] is False
    assert payload["holdout_2026_accessed"] is False
    assert payload["dune_api_called"] is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-1.0, 0.0), (0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (2.0, 1.0)],
)
def test_clip01(value: float, expected: float) -> None:
    assert clip01(value) == expected


def test_helpers_reject_invalid_values() -> None:
    with pytest.raises(ValueError):
        clip01(float("nan"))
    with pytest.raises(ValueError):
        linear_score(1.0, 1.0, 1.0, 2.0)
    with pytest.raises(ValueError):
        linear_score(float("inf"), 0.0, 1.0, 2.0)


def test_linear_and_piecewise_boundaries() -> None:
    assert linear_score(-1.0, 0.0, 1.0, 10.0) == 0.0
    assert linear_score(0.5, 0.0, 1.0, 10.0) == 5.0
    assert linear_score(2.0, 0.0, 1.0, 10.0) == 10.0
    assert rsi_entry_score(40.0) == 0.0
    assert rsi_entry_score(60.0) == 8.0
    assert rsi_entry_score(70.0) == 8.0
    assert rsi_entry_score(85.0) == 0.0
    assert rsi_health_score(35.0) == 0.0
    assert rsi_health_score(55.0) == 8.0
    assert atr_quality_score(0.02) == 8.0
    assert extension_quality_score(0.5) == 6.0


def test_configuration_differences_are_declared_only() -> None:
    baseline = ScoredBreakoutConfig()
    assert len(CONFIGURATIONS) == 7
    assert len({item.configuration_id for item in CONFIGURATIONS}) == 7
    for item in CONFIGURATIONS:
        configured = _configuration(item)
        changed = {
            field
            for field in item.changes
            if getattr(configured, field) != getattr(baseline, field)
        }
        assert changed == set(item.changes)
        configured.validate()


def test_score_bins_have_frozen_boundaries() -> None:
    assert [_entry_bin(value) for value in (49.9, 50, 60, 70, 80, 90)] == [
        "LT_50",
        "50_60",
        "60_70",
        "70_80",
        "80_90",
        "90_100",
    ]
    assert [_health_bin(value) for value in (20, 35, 50, 65, 80, 100)] == [
        "0_20",
        "GT20_35",
        "GT35_50",
        "GT50_65",
        "GT65_80",
        "GT80_100",
    ]


def test_position_sizing_is_independent_of_score() -> None:
    base = ScoredBreakoutConfig()
    changed = replace(base, entry_threshold=65.0)
    assert base.risk_per_trade == changed.risk_per_trade == 0.01
    assert base.initial_stop_atr == changed.initial_stop_atr == 2.0


def test_health_hysteresis_and_no_absolute_time_exit() -> None:
    assert ScoredBreakoutConfig().confirmed_health_bars == 2
    assert ScoredBreakoutConfig().health_exit_cooldown_bars == 3
    assert ScoredBreakoutConfig().stop_exit_cooldown_bars == 5
    assert ScoredBreakoutStrategy._time_score(31, 1.1, True) > 0
    assert ScoredBreakoutStrategy._time_score(80, 1.1, True) > 0


def test_bootstrap_protocol_is_frozen() -> None:
    assert BOOTSTRAP_SEED == 20260731
    assert BOOTSTRAP_RESAMPLES == 2000


def test_no_single_indicator_veto_is_in_hard_gates() -> None:
    gates = set(_specification_payload()["hard_safety_gates"])
    assert "ema50_above_ema200" not in gates
    assert "rsi_entry_range" not in gates
    assert "volume_threshold" not in gates
    assert "binary_breakout" not in gates


def test_all_floats_are_finite_at_piecewise_points() -> None:
    values = [
        rsi_entry_score(52),
        rsi_health_score(45),
        atr_quality_score(0.05),
        extension_quality_score(2.0),
    ]
    assert all(math.isfinite(value) for value in values)
