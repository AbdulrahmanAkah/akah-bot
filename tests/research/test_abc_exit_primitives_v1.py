from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.abc_exit_primitives_v1 import (
    A_ID, B_ID, C_ID,
    CANDIDATE_A, CANDIDATE_B, CANDIDATE_C,
    build_four_hour_bars, evaluate_completed_4h, new_candidate_state,
)


def bar(open_time: str, high: float, low: float, close: float, atr=1.0, don=90.0):
    o = pd.Timestamp(open_time)
    if o.tzinfo is None:
        o = o.tz_localize("UTC")
    return pd.Series({
        "bar_open_time": o,
        "bar_close_time": o + pd.Timedelta(hours=4),
        "open": close, "high": high, "low": low, "close": close,
        "atr22_wilder": atr, "donchian10_prior_low": don,
    })


def test_c_memory_on_bar12_prevents_exit():
    st = new_candidate_state(pd.Timestamp("2020-01-01T00:00:00Z"), 100.0)
    for i in range(11):
        sig, _, _ = evaluate_completed_4h(
            candidate_id=CANDIDATE_C, state=st,
            row=bar(f"2020-01-{1 + (i // 6):02d}T{(i*4)%24:02d}:00:00Z", 100.0, 95.0, 99.0),
        )
        assert not sig
    sig, reason, _ = evaluate_completed_4h(
        candidate_id=CANDIDATE_C, state=st,
        row=bar("2020-01-03T20:00:00Z", 110.0, 98.0, 105.0),
    )
    assert not sig
    assert reason is None
    assert st.memory_seen is True


def test_c_exits_exactly_on_12_without_memory():
    st = new_candidate_state(pd.Timestamp("2020-01-01T00:00:00Z"), 100.0)
    sig = False
    reason = None
    for i in range(12):
        t = pd.Timestamp("2020-01-01T00:00:00Z") + pd.Timedelta(hours=4*i)
        sig, reason, _ = evaluate_completed_4h(
            candidate_id=CANDIDATE_C, state=st,
            row=bar(str(t), 100.0, 95.0, 99.0),
        )
    assert sig and reason == C_ID


def test_a_uses_prior_donchian_and_strict_close_break():
    st = new_candidate_state(pd.Timestamp("2020-01-01T00:00:00Z"), 100.0)
    sig, reason, _ = evaluate_completed_4h(
        candidate_id=CANDIDATE_A, state=st,
        row=bar("2020-01-01T00:00:00Z", 105.0, 80.0, 89.0, don=90.0),
    )
    assert sig and reason == A_ID
    st2 = new_candidate_state(pd.Timestamp("2020-01-01T00:00:00Z"), 100.0)
    sig2, _, _ = evaluate_completed_4h(
        candidate_id=CANDIDATE_A, state=st2,
        row=bar("2020-01-01T00:00:00Z", 105.0, 80.0, 90.0, don=90.0),
    )
    assert not sig2


def test_b_activation_bar_never_exits_and_uses_previous_stop_next_bar():
    st = new_candidate_state(pd.Timestamp("2020-01-01T00:00:00Z"), 100.0)
    sig, _, status = evaluate_completed_4h(
        candidate_id=CANDIDATE_B, state=st,
        row=bar("2020-01-01T00:00:00Z", 110.0, 99.0, 105.0, atr=2.0),
    )
    assert not sig and status == "READY_ACTIVATED_NO_EXIT"
    assert st.b_stop == pytest.approx(104.0)
    sig2, reason2, _ = evaluate_completed_4h(
        candidate_id=CANDIDATE_B, state=st,
        row=bar("2020-01-01T04:00:00Z", 111.0, 100.0, 103.0, atr=2.0),
    )
    assert sig2 and reason2 == B_ID


def test_entry_spanning_bar_is_ineligible():
    st = new_candidate_state(pd.Timestamp("2020-01-01T01:00:00Z"), 100.0)
    sig, _, status = evaluate_completed_4h(
        candidate_id=CANDIDATE_C, state=st,
        row=bar("2020-01-01T00:00:00Z", 110.0, 90.0, 105.0),
    )
    assert not sig
    assert status == "INELIGIBLE_PRE_ENTRY_OR_PARTIAL_ENTRY_BAR"
    assert st.eligible_bar_count == 0


def test_atr_wilder_seed_and_donchian_current_low_excluded():
    rows = []
    start = pd.Timestamp("2020-01-01T00:00:00Z")
    for i in range(4*25):
        t = start + pd.Timedelta(hours=i)
        rows.append({
            "timestamp": t, "open": 100+i*0.01, "high": 101+i*0.01,
            "low": 99+i*0.01, "close": 100.5+i*0.01, "volume": 10.0,
        })
    raw = pd.DataFrame(rows)
    h4 = build_four_hour_bars(raw, cutoff=pd.Timestamp("2020-01-10T00:00:00Z"))
    assert len(h4) >= 22
    assert pd.isna(h4.loc[20, "atr22_wilder"])
    assert pd.notna(h4.loc[21, "atr22_wilder"])
    i = 10
    expected = h4.loc[i-10:i-1, "low"].min()
    assert h4.loc[i, "donchian10_prior_low"] == pytest.approx(expected)
