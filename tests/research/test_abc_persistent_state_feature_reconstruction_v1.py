from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MODULE_PATH = Path(os.environ["AKAH_IMPL_UNDER_TEST_PATH"])
spec = importlib.util.spec_from_file_location("akah_impl_under_test", MODULE_PATH)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def bars(rows):
    frame = pd.DataFrame.from_records(rows)
    frame["bar_open_time"] = pd.to_datetime(frame["bar_open_time"], utc=True)
    frame["bar_close_time"] = pd.to_datetime(frame["bar_close_time"], utc=True)
    return frame


def row(start, *, high, close, atr=np.nan, don=np.nan):
    start = pd.Timestamp(start)
    return {
        "bar_open_time": start,
        "bar_close_time": start + pd.Timedelta(hours=4),
        "high": float(high),
        "close": float(close),
        "atr22_wilder": atr,
        "donchian10_prior_low": don,
    }


def test_feature_registry_is_exact_22():
    assert len(m.FEATURE_COLUMNS) == 22
    assert len(set(m.FEATURE_COLUMNS)) == 22
    m.validate_feature_columns(m.FEATURE_COLUMNS)


def test_trace_identity_registry_exact():
    expected = (
        "year",
        "pair",
        "entry_time",
        "native_exit_time",
        "decision_time_4h",
    )
    assert expected == m.TRACE_IDENTITY_COLUMNS
    m.validate_trace_identity_columns(expected)
    with pytest.raises(m.CausalFeatureReconstructionError):
        m.validate_trace_identity_columns(tuple(reversed(expected)))


def test_progress_R_before_after_and_deltas():
    f = bars([
        row("2020-01-01T00:00:00Z", high=105, close=99, atr=2, don=90),
        row("2020-01-01T04:00:00Z", high=110, close=106, atr=2, don=91),
    ])
    out = m.reconstruct_lifecycle_features(
        bars4h=f,
        entry_time=pd.Timestamp("2020-01-01T00:00:00Z"),
        entry_price=100,
        decision_times=f["bar_close_time"].tolist(),
    )
    assert out.loc[0, "R_before_t"] == pytest.approx(100)
    assert out.loc[0, "R_after_t"] == pytest.approx(105)
    assert pd.isna(out.loc[0, "R_delta_from_prev_decision"])
    assert out.loc[1, "R_before_t"] == pytest.approx(105)
    assert out.loc[1, "R_after_t"] == pytest.approx(110)
    assert out.loc[1, "R_delta_from_prev_decision"] == pytest.approx(5)
    assert out.loc[1, "close_minus_R_before_t"] == pytest.approx(1)


def test_A_strict_boundary_run_and_recovery():
    f = bars([
        row("2020-01-01T00:00:00Z", high=100, close=89, atr=2, don=90),
        row("2020-01-01T04:00:00Z", high=100, close=88, atr=2, don=90),
        row("2020-01-01T08:00:00Z", high=100, close=90, atr=2, don=90),
    ])
    out = m.reconstruct_lifecycle_features(
        bars4h=f,
        entry_time=pd.Timestamp("2020-01-01T00:00:00Z"),
        entry_price=100,
        decision_times=f["bar_close_time"].tolist(),
    )
    assert list(out["a_condition_now"]) == [True, True, False]
    assert list(out["a_condition_true_run_length"]) == [1, 2, 0]
    assert pd.isna(out.loc[0, "a_condition_recovered_now"])
    assert not out.loc[1, "a_condition_recovered_now"]
    assert out.loc[2, "a_condition_recovered_now"]
    assert out.loc[2, "close_minus_donchian_prev10_low"] == pytest.approx(0)


def test_B_activation_uses_previous_stop_and_shadow_continues_after_signal():
    f = bars([
        row("2020-01-01T00:00:00Z", high=110, close=105, atr=2, don=90),
        row("2020-01-01T04:00:00Z", high=111, close=103, atr=2, don=90),
        row("2020-01-01T08:00:00Z", high=120, close=112, atr=2, don=90),
        row("2020-01-01T12:00:00Z", high=120, close=115, atr=2, don=90),
    ])
    out = m.reconstruct_lifecycle_features(
        bars4h=f,
        entry_time=pd.Timestamp("2020-01-01T00:00:00Z"),
        entry_price=100,
        decision_times=f["bar_close_time"].tolist(),
    )
    # Activation bar: no previous stop, therefore no B condition.
    assert pd.isna(out.loc[0, "ratchet_stop_before_t"])
    assert pd.isna(out.loc[0, "b_condition_now"])
    # Frozen activation: 110 - 3*2 = 104; next bar compares close 103 to 104.
    assert out.loc[1, "ratchet_stop_before_t"] == pytest.approx(104)
    assert out.loc[1, "b_condition_now"]
    assert out.loc[1, "close_minus_ratchet_stop_before_t"] == pytest.approx(-1)
    # Shadow continuation occurs despite the prior row being a legacy B signal.
    # Row index 2 sees the previous stop=105 and close=112, so B recovers here
    # (True -> False). That same row then updates hpeak to 120 and next stop to 114.
    assert out.loc[2, "ratchet_stop_before_t"] == pytest.approx(105)
    assert not out.loc[2, "b_condition_now"]
    assert out.loc[2, "b_condition_recovered_now"]
    assert out.loc[2, "b_condition_true_run_length"] == 0

    # Row index 3 remains false against previous stop=114, so this is False -> False,
    # not another recovery.
    assert out.loc[3, "ratchet_stop_before_t"] == pytest.approx(114)
    assert not out.loc[3, "b_condition_now"]
    assert not out.loc[3, "b_condition_recovered_now"]
    assert out.loc[3, "b_condition_true_run_length"] == 0


def test_B_memory_before_atr_ready_is_unevaluable_forever():
    f = bars([
        row("2020-01-01T00:00:00Z", high=110, close=105, atr=np.nan, don=90),
        row("2020-01-01T04:00:00Z", high=111, close=106, atr=2, don=90),
        row("2020-01-01T08:00:00Z", high=112, close=107, atr=2, don=90),
    ])
    out = m.reconstruct_lifecycle_features(
        bars4h=f,
        entry_time=pd.Timestamp("2020-01-01T00:00:00Z"),
        entry_price=100,
        decision_times=f["bar_close_time"].tolist(),
    )
    assert out["ratchet_stop_before_t"].isna().all()
    assert out["b_condition_now"].isna().all()


def test_readiness_nulls_and_alias_deltas():
    f = bars([
        row("2020-01-01T00:00:00Z", high=101, close=99, atr=np.nan, don=np.nan),
        row("2020-01-01T04:00:00Z", high=102, close=98, atr=2, don=90),
        row("2020-01-01T08:00:00Z", high=103, close=89, atr=2, don=90),
    ])
    out = m.reconstruct_lifecycle_features(
        bars4h=f,
        entry_time=pd.Timestamp("2020-01-01T00:00:00Z"),
        entry_price=100,
        decision_times=f["bar_close_time"].tolist(),
    )
    assert pd.isna(out.loc[0, "a_condition_now"])
    assert pd.isna(out.loc[0, "a_condition_true_run_length"])
    assert pd.isna(out.loc[1, "a_condition_recovered_now"])
    assert (
        out["a_margin_delta_from_prev"].fillna(9999)
        == out["structural_break_margin_delta_from_prev"].fillna(9999)
    ).all()
    assert (
        out["b_margin_delta_from_prev"].fillna(9999)
        == out["volatility_damage_margin_delta_from_prev"].fillna(9999)
    ).all()


def test_partial_entry_bar_is_rejected():
    f = bars([
        row("2020-01-01T00:00:00Z", high=110, close=105, atr=2, don=90),
    ])
    with pytest.raises(
        m.CausalFeatureReconstructionError,
        match="partial-entry",
    ):
        m.reconstruct_lifecycle_features(
            bars4h=f,
            entry_time=pd.Timestamp("2020-01-01T01:00:00Z"),
            entry_price=100,
            decision_times=f["bar_close_time"].tolist(),
        )


def test_prepare_four_hour_bars_delegates_exact_frozen_builder():
    raw_rows = []
    start = pd.Timestamp("2020-01-01T00:00:00Z")
    for i in range(4 * 25):
        t = start + pd.Timedelta(hours=i)
        raw_rows.append({
            "timestamp": t,
            "open": 100 + i * 0.01,
            "high": 101 + i * 0.01,
            "low": 99 + i * 0.01,
            "close": 100.5 + i * 0.01,
            "volume": 10.0,
        })
    raw = pd.DataFrame(raw_rows)
    cutoff = pd.Timestamp("2020-01-10T00:00:00Z")
    actual = m.prepare_four_hour_bars(raw, cutoff=cutoff)

    from spotbot.research.abc_exit_primitives_v1 import build_four_hour_bars
    expected = build_four_hour_bars(raw, cutoff=cutoff)
    pd.testing.assert_frame_equal(actual, expected)
