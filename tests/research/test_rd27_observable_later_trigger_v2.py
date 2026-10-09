from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd27_observable_later_trigger_v2 import (
    PARAMETER_COUNT,
    PROTOCOL_ID,
    LaterTriggerV2Error,
    arm_later_trigger_v2,
    contract_summary,
    evaluate_later_trigger_v2,
    new_later_trigger_v2_state,
)
from spotbot.research.rd27_observable_memory_adapter import (
    Observable4HSnapshot,
    ObservablePositionContext,
)


def ts(hour: int) -> pd.Timestamp:
    return pd.Timestamp("2022-01-01T00:00:00Z") + pd.Timedelta(hours=hour)


def snap(
    open_h: int,
    close_h: int,
    *,
    high: float,
    low: float,
    close: float,
    symbol: str = "AAAUSDT",
) -> Observable4HSnapshot:
    assert close_h - open_h == 4
    assert low <= close <= high
    open_price = (float(high) + float(low)) / 2.0
    return Observable4HSnapshot(
        symbol=symbol,
        source_exchange="KUCOIN",
        source_symbol=symbol,
        bar_open_time=ts(open_h),
        bar_close_time=ts(close_h),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=1.0,
    )


def pos(
    decision_h: int,
    *,
    symbol: str = "AAAUSDT",
    position_id: str = "p1",
    entry_h: int = 0,
) -> ObservablePositionContext:
    return ObservablePositionContext(
        position_id=position_id,
        symbol=symbol,
        entry_time=ts(entry_h),
        decision_time=ts(decision_h),
    )


def armed():
    state = new_later_trigger_v2_state(
        position_id="p1",
        symbol="AAAUSDT",
        entry_time=ts(0),
    )
    memory = snap(4, 8, high=106, low=101, close=105)
    return arm_later_trigger_v2(
        state,
        position=pos(8),
        memory_snapshot=memory,
        memory_time=ts(8),
        breakout_reference=104.0,
    )


def test_protocol_identity_and_zero_parameters():
    assert PROTOCOL_ID.endswith("FAILED_BREAKOUT_REFERENCE")
    assert PARAMETER_COUNT == 0


def test_contract_has_no_exit_authority():
    summary = contract_summary()
    assert summary["parameter_count"] == 0
    assert summary["actual_exit_authority"] is False
    assert summary["market_data_loading"] is False
    assert summary["economic_fields"] is False


def test_new_state_unarmed():
    state = new_later_trigger_v2_state(
        position_id="p1", symbol="AAAUSDT", entry_time=ts(0)
    )
    assert state.memory_time is None
    assert state.breakout_reference is None
    assert state.eligible_snapshot_count == 0


def test_arm_freezes_breakout_reference():
    state = armed()
    assert state.memory_time == ts(8)
    assert state.breakout_reference == 104.0
    assert state.memory_snapshot.close == 105


def test_identical_rearm_is_idempotent():
    state = armed()
    again = arm_later_trigger_v2(
        state,
        position=pos(8),
        memory_snapshot=state.memory_snapshot,
        memory_time=ts(8),
        breakout_reference=104.0,
    )
    assert again == state


def test_conflicting_rearm_fails():
    state = armed()
    with pytest.raises(LaterTriggerV2Error, match="MEMORY_ALREADY_ARMED_CONFLICT"):
        arm_later_trigger_v2(
            state,
            position=pos(8),
            memory_snapshot=state.memory_snapshot,
            memory_time=ts(8),
            breakout_reference=103.0,
        )


def test_arm_requires_memory_close_above_reference():
    state = new_later_trigger_v2_state(
        position_id="p1", symbol="AAAUSDT", entry_time=ts(0)
    )
    memory = snap(4, 8, high=106, low=101, close=104)
    with pytest.raises(
        LaterTriggerV2Error, match="MEMORY_EVIDENCE_DOES_NOT_BREAK_REFERENCE"
    ):
        arm_later_trigger_v2(
            state,
            position=pos(8),
            memory_snapshot=memory,
            memory_time=ts(8),
            breakout_reference=104.0,
        )


def test_arm_rejects_future_memory():
    state = new_later_trigger_v2_state(
        position_id="p1", symbol="AAAUSDT", entry_time=ts(0)
    )
    memory = snap(4, 8, high=106, low=101, close=105)
    with pytest.raises(LaterTriggerV2Error, match="MEMORY_NOT_YET_OBSERVABLE"):
        arm_later_trigger_v2(
            state,
            position=pos(4),
            memory_snapshot=memory,
            memory_time=ts(8),
            breakout_reference=104.0,
        )


def test_arm_rejects_spanning_entry():
    state = new_later_trigger_v2_state(
        position_id="p1", symbol="AAAUSDT", entry_time=ts(2)
    )
    memory = snap(0, 4, high=106, low=101, close=105)
    with pytest.raises(LaterTriggerV2Error, match="MEMORY_SNAPSHOT_SPANS_ENTRY"):
        arm_later_trigger_v2(
            state,
            position=pos(4, entry_h=2),
            memory_snapshot=memory,
            memory_time=ts(4),
            breakout_reference=104.0,
        )


def test_before_memory_returns_not_established():
    state = new_later_trigger_v2_state(
        position_id="p1", symbol="AAAUSDT", entry_time=ts(0)
    )
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(4),
        snapshot=snap(0, 4, high=103, low=99, close=100),
    )
    assert ev.trigger_candidate is None
    assert ev.status == "MEMORY_NOT_ESTABLISHED"


def test_same_time_memory_bar_cannot_trigger():
    state = armed()
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(8),
        snapshot=state.memory_snapshot,
    )
    assert ev.trigger_candidate is None
    assert ev.status == "NOT_STRICTLY_LATER"


def test_strictly_later_close_below_reference_true():
    state = armed()
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(12),
        snapshot=snap(8, 12, high=105, low=102, close=103.5),
    )
    assert ev.trigger_candidate is True
    assert ev.status == "ELIGIBLE"
    assert ev.breakout_reference == 104.0


def test_equal_reference_false():
    state = armed()
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(12),
        snapshot=snap(8, 12, high=105, low=103, close=104),
    )
    assert ev.trigger_candidate is False


def test_above_reference_false():
    state = armed()
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(12),
        snapshot=snap(8, 12, high=106, low=103, close=105),
    )
    assert ev.trigger_candidate is False


def test_wick_below_reference_close_above_false():
    state = armed()
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(12),
        snapshot=snap(8, 12, high=106, low=100, close=105),
    )
    assert ev.trigger_candidate is False


def test_reference_never_advances_after_memory():
    state = armed()
    ev1 = evaluate_later_trigger_v2(
        state,
        position=pos(12),
        snapshot=snap(8, 12, high=120, low=104, close=110),
    )
    ev2 = evaluate_later_trigger_v2(
        ev1.state,
        position=pos(16),
        snapshot=snap(12, 16, high=111, low=102, close=103),
    )
    assert ev1.state.breakout_reference == 104.0
    assert ev2.breakout_reference == 104.0
    assert ev2.trigger_candidate is True


def test_duplicate_idempotent():
    state = armed()
    snapshot = snap(8, 12, high=106, low=103, close=105)
    ev1 = evaluate_later_trigger_v2(state, position=pos(12), snapshot=snapshot)
    ev2 = evaluate_later_trigger_v2(
        ev1.state, position=pos(12), snapshot=snapshot
    )
    assert ev2.status == "DUPLICATE"
    assert ev2.trigger_candidate is None
    assert ev2.state == ev1.state


def test_out_of_order_fails():
    state = armed()
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(16),
        snapshot=snap(12, 16, high=106, low=103, close=105),
    )
    with pytest.raises(LaterTriggerV2Error, match="OUT_OF_ORDER_SNAPSHOT"):
        evaluate_later_trigger_v2(
            ev.state,
            position=pos(18),
            snapshot=snap(8, 12, high=105, low=102, close=103),
        )


def test_future_snapshot_fails():
    state = armed()
    with pytest.raises(LaterTriggerV2Error, match="SNAPSHOT_NOT_YET_OBSERVABLE"):
        evaluate_later_trigger_v2(
            state,
            position=pos(10),
            snapshot=snap(8, 12, high=105, low=102, close=103),
        )


def test_decision_time_regression_fails():
    state = armed()
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(16),
        snapshot=snap(8, 12, high=106, low=103, close=105),
    )
    with pytest.raises(LaterTriggerV2Error, match="DECISION_TIME_REGRESSION"):
        evaluate_later_trigger_v2(
            ev.state,
            position=pos(14),
            snapshot=snap(10, 14, high=106, low=103, close=105),
        )


@pytest.mark.parametrize(
    "bad_position",
    [
        pos(12, position_id="other"),
        pos(12, symbol="BBBUSDT"),
        pos(12, entry_h=4),
    ],
)
def test_position_binding_fail_closed(bad_position):
    state = armed()
    with pytest.raises(LaterTriggerV2Error):
        evaluate_later_trigger_v2(
            state,
            position=bad_position,
            snapshot=snap(8, 12, high=105, low=102, close=103),
        )


def test_snapshot_symbol_mismatch_fails():
    state = armed()
    with pytest.raises(LaterTriggerV2Error, match="SNAPSHOT_SYMBOL_MISMATCH"):
        evaluate_later_trigger_v2(
            state,
            position=pos(12),
            snapshot=snap(
                8, 12, high=105, low=102, close=103, symbol="BBBUSDT"
            ),
        )


def test_entry_spanning_snapshot_excluded():
    state = new_later_trigger_v2_state(
        position_id="p1", symbol="AAAUSDT", entry_time=ts(2)
    )
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(4, entry_h=2),
        snapshot=snap(0, 4, high=105, low=99, close=101),
    )
    assert ev.status == "EXCLUDED_ENTRY_BOUNDARY"
    assert ev.trigger_candidate is None


def test_strict_comparison_is_parameter_free():
    state = armed()
    ev = evaluate_later_trigger_v2(
        state,
        position=pos(12),
        snapshot=snap(8, 12, high=105, low=103, close=103.999999),
    )
    assert ev.trigger_candidate is True
    assert PARAMETER_COUNT == 0


def test_separate_positions_isolated():
    first = armed()
    second = new_later_trigger_v2_state(
        position_id="p2", symbol="AAAUSDT", entry_time=ts(0)
    )
    memory = snap(4, 8, high=206, low=201, close=205)
    second = arm_later_trigger_v2(
        second,
        position=pos(8, position_id="p2"),
        memory_snapshot=memory,
        memory_time=ts(8),
        breakout_reference=204,
    )
    current = snap(8, 12, high=205, low=102, close=203)
    ev1 = evaluate_later_trigger_v2(first, position=pos(12), snapshot=current)
    ev2 = evaluate_later_trigger_v2(
        second, position=pos(12, position_id="p2"), snapshot=current
    )
    assert ev1.trigger_candidate is False
    assert ev2.trigger_candidate is True
    assert ev1.breakout_reference == 104
    assert ev2.breakout_reference == 204


def test_later_false_then_true():
    state = armed()
    ev1 = evaluate_later_trigger_v2(
        state,
        position=pos(12),
        snapshot=snap(8, 12, high=106, low=104, close=105),
    )
    ev2 = evaluate_later_trigger_v2(
        ev1.state,
        position=pos(16),
        snapshot=snap(12, 16, high=105, low=102, close=103),
    )
    assert ev1.trigger_candidate is False
    assert ev2.trigger_candidate is True


def test_multiple_true_evaluations_are_deterministic_predicate_facts():
    state = armed()
    ev1 = evaluate_later_trigger_v2(
        state,
        position=pos(12),
        snapshot=snap(8, 12, high=105, low=102, close=103),
    )
    ev2 = evaluate_later_trigger_v2(
        ev1.state,
        position=pos(16),
        snapshot=snap(12, 16, high=104, low=101, close=102),
    )
    assert ev1.trigger_candidate is True
    assert ev2.trigger_candidate is True
