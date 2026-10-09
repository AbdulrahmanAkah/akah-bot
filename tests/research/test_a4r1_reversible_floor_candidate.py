from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

import spotbot.research.a4r1_reversible_floor_candidate as candidate
import spotbot.research.rd27_adaptive_lifecycle as rd27


def make_position(
    *,
    protection_floor: float | None = None,
    high_water_prior: float | None = None,
) -> rd27.LifecyclePosition:
    entry_time = pd.Timestamp("2030-01-01T00:00:00Z")
    position = rd27.new_lifecycle_position(
        pair="AAA-USDT",
        entry_time=entry_time,
        entry_price=100.0,
        atr24_at_signal=1.0,
    )
    updates: dict[str, float | None] = {
        "protection_floor": protection_floor,
    }
    if high_water_prior is not None:
        updates["high_water_prior"] = high_water_prior
    return replace(position, **updates)


@pytest.mark.parametrize(
    ("previous_state", "current_state", "expected"),
    [
        (None, rd27.RISK_OFF, candidate.UNAVAILABLE_AT_INITIAL_OBSERVATION),
        (rd27.RISK_ON, rd27.RISK_ON, candidate.UNCHANGED),
        (rd27.RISK_OFF, rd27.TRANSITION, candidate.IMPROVING),
        (rd27.RISK_OFF, rd27.RISK_ON, candidate.IMPROVING),
        (rd27.TRANSITION, rd27.RISK_ON, candidate.IMPROVING),
        (rd27.RISK_ON, rd27.TRANSITION, candidate.DETERIORATING),
        (rd27.RISK_ON, rd27.RISK_OFF, candidate.DETERIORATING),
        (rd27.TRANSITION, rd27.RISK_OFF, candidate.DETERIORATING),
    ],
)
def test_transition_direction_is_frozen_and_causal(
    previous_state: str | None,
    current_state: str,
    expected: str,
) -> None:
    assert (
        candidate.transition_direction(
            previous_market_state=previous_state,
            current_market_state=current_state,
        )
        == expected
    )


def test_contemporaneous_floor_excludes_historical_prior_floor() -> None:
    position = make_position(protection_floor=97.0)
    floor, source = candidate.contemporaneous_floor(
        position,
        current_market_state=rd27.RISK_ON,
    )
    assert floor == 95.0
    assert source == "ADVERSE_GUARD"


def test_improving_context_can_relax_below_historical_floor() -> None:
    position = make_position(protection_floor=97.0)
    current_time = position.entry_time + pd.Timedelta(hours=1)

    repaired = candidate.evaluate_candidate_exit(
        position,
        current_open_time=current_time,
        current_open=100.0,
        current_low=98.0,
        prior_asset_close=100.0,
        previous_market_state=rd27.TRANSITION,
        current_market_state=rd27.RISK_ON,
    )
    control = rd27.evaluate_adaptive_exit(
        position,
        current_open_time=current_time,
        current_open=100.0,
        current_low=98.0,
        prior_asset_close=100.0,
        market_state=rd27.RISK_ON,
    )

    assert repaired.lifecycle_channel == candidate.CONTINUATION_PRESERVATION
    assert repaired.transition_direction == candidate.IMPROVING
    assert repaired.contemporaneous_floor == 95.0
    assert repaired.effective_floor == 95.0
    assert control.effective_floor == 97.0
    assert repaired.effective_floor < control.effective_floor


def test_risk_on_unchanged_is_continuation_context() -> None:
    position = make_position(protection_floor=97.0)
    floor, _source, c_now, _c_source, direction, channel = (
        candidate.selected_floor(
            position,
            previous_market_state=rd27.RISK_ON,
            current_market_state=rd27.RISK_ON,
        )
    )
    assert direction == candidate.UNCHANGED
    assert channel == candidate.CONTINUATION_PRESERVATION
    assert floor == c_now == 95.0


@pytest.mark.parametrize(
    ("previous_state", "current_state"),
    [
        (rd27.RISK_OFF, rd27.TRANSITION),
        (rd27.RISK_OFF, rd27.RISK_ON),
        (rd27.TRANSITION, rd27.RISK_ON),
    ],
)
def test_every_improving_transition_uses_continuation(
    previous_state: str,
    current_state: str,
) -> None:
    position = make_position(protection_floor=99.0)
    (
        floor,
        _source,
        c_now,
        _c_source,
        direction,
        channel,
    ) = candidate.selected_floor(
        position,
        previous_market_state=previous_state,
        current_market_state=current_state,
    )
    assert direction == candidate.IMPROVING
    assert channel == candidate.CONTINUATION_PRESERVATION
    assert floor == c_now


def test_deteriorating_context_preserves_defensive_max_carry() -> None:
    position = make_position(protection_floor=97.0)
    (
        floor,
        source,
        c_now,
        _c_source,
        direction,
        channel,
    ) = candidate.selected_floor(
        position,
        previous_market_state=rd27.RISK_ON,
        current_market_state=rd27.TRANSITION,
    )
    assert direction == candidate.DETERIORATING
    assert channel == candidate.ADVERSE_RESCUE
    assert c_now == 96.0
    assert floor == 97.0
    assert source == "MONOTONIC_PRIOR_FLOOR"


def test_initial_observation_defaults_to_defensive_carry() -> None:
    position = make_position(protection_floor=97.0)
    floor, source, c_now, _c_source, direction, channel = (
        candidate.selected_floor(
            position,
            previous_market_state=None,
            current_market_state=rd27.RISK_ON,
        )
    )
    assert direction == candidate.UNAVAILABLE_AT_INITIAL_OBSERVATION
    assert channel == candidate.ADVERSE_RESCUE
    assert c_now == 95.0
    assert floor == 97.0
    assert source == "MONOTONIC_PRIOR_FLOOR"


def test_post_survival_storage_has_no_unconditional_second_max() -> None:
    position = make_position(protection_floor=97.0)
    decision = candidate.evaluate_candidate_exit(
        position,
        current_open_time=position.entry_time + pd.Timedelta(hours=1),
        current_open=100.0,
        current_low=98.0,
        prior_asset_close=100.0,
        previous_market_state=rd27.TRANSITION,
        current_market_state=rd27.RISK_ON,
    )
    assert decision.should_exit is False
    assert decision.effective_floor == 95.0

    updated = candidate.apply_candidate_completed_bar_update(
        position,
        decision=decision,
        completed_high=101.0,
    )
    assert updated.protection_floor == 95.0
    assert updated.high_water_prior == 101.0


def test_current_bar_high_cannot_tighten_same_bar_candidate_floor() -> None:
    position = make_position()
    first = candidate.evaluate_candidate_exit(
        position,
        current_open_time=position.entry_time + pd.Timedelta(hours=1),
        current_open=100.0,
        current_low=99.0,
        prior_asset_close=100.0,
        previous_market_state=rd27.RISK_ON,
        current_market_state=rd27.RISK_ON,
    )
    assert first.should_exit is False
    assert first.effective_floor == 95.0

    updated = candidate.apply_candidate_completed_bar_update(
        position,
        decision=first,
        completed_high=110.0,
    )
    second = candidate.evaluate_candidate_exit(
        updated,
        current_open_time=position.entry_time + pd.Timedelta(hours=2),
        current_open=109.0,
        current_low=107.0,
        prior_asset_close=109.0,
        previous_market_state=rd27.RISK_ON,
        current_market_state=rd27.RISK_ON,
    )
    assert second.contemporaneous_floor == 106.0
    assert second.effective_floor == 106.0


def test_defensive_branch_matches_frozen_rd27_floor() -> None:
    position = make_position(protection_floor=97.0)
    current_time = position.entry_time + pd.Timedelta(hours=1)

    repaired = candidate.evaluate_candidate_exit(
        position,
        current_open_time=current_time,
        current_open=100.0,
        current_low=98.0,
        prior_asset_close=100.0,
        previous_market_state=rd27.RISK_ON,
        current_market_state=rd27.TRANSITION,
    )
    control = rd27.evaluate_adaptive_exit(
        position,
        current_open_time=current_time,
        current_open=100.0,
        current_low=98.0,
        prior_asset_close=100.0,
        market_state=rd27.TRANSITION,
    )

    assert repaired.lifecycle_channel == candidate.ADVERSE_RESCUE
    assert repaired.effective_floor == control.effective_floor
    assert repaired.floor_source == control.floor_source
    assert repaired.should_exit == control.should_exit


def test_max_hold_and_stagnation_constants_are_reused_from_rd27() -> None:
    assert candidate.MAX_HOLD_HOURS == rd27.MAX_HOLD_HOURS
    assert candidate.STAGNATION_HOURS_BY_STATE is rd27.STAGNATION_HOURS_BY_STATE
    assert (
        candidate.ADVERSE_GUARD_ATR_BY_STATE
        is rd27.ADVERSE_GUARD_ATR_BY_STATE
    )
    assert (
        candidate.PROFIT_TRAIL_GAP_ATR_BY_STATE
        is rd27.PROFIT_TRAIL_GAP_ATR_BY_STATE
    )
    assert candidate.PROFIT_ARM_ATR == rd27.PROFIT_ARM_ATR

    position = make_position()
    decision = candidate.evaluate_candidate_exit(
        position,
        current_open_time=(
            position.entry_time
            + pd.Timedelta(hours=rd27.MAX_HOLD_HOURS)
        ),
        current_open=100.0,
        current_low=99.0,
        prior_asset_close=101.0,
        previous_market_state=rd27.RISK_ON,
        current_market_state=rd27.RISK_ON,
    )
    assert decision.should_exit is True
    assert decision.exit_reason == f"MAX_HOLD_{rd27.MAX_HOLD_HOURS}H"


def test_contract_declares_shadow_only_and_no_replay() -> None:
    summary = candidate.contract_summary()
    assert summary["candidate_is_shadow_only"] is True
    assert summary["rd27_control_mutated"] is False
    assert summary["market_replay_performed"] is False
    assert summary["current_bar_high_can_tighten_same_bar_floor"] is False
    assert summary["maximum_hold_hours"] == rd27.MAX_HOLD_HOURS
