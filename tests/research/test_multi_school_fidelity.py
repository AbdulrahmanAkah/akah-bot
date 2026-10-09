from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as rt
from spotbot.research.multi_school_fidelity import akah_native_management_adapters_v1 as mgmt
from spotbot.research.multi_school_fidelity import akah_native_replay_engine_v1 as engine
from spotbot.research.multi_school_fidelity import akah_replay_ready_detectors_v1 as det
from spotbot.research.multi_school_fidelity import akah_thesis_engine_foundation_v1 as foundation
from spotbot.research.multi_school_fidelity import fidelity_pipeline as pipeline
from spotbot.research.multi_school_fidelity import gate3_precommit as gate3
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import (
    DATA_CUTOFF,
    BroadEligibilityIndex,
    FoundationError,
    canonical_aggregate,
    raw_frame,
)
from spotbot.research.multi_school_fidelity.portfolio_kernel import PortfolioKernel

T = pd.Timestamp("2022-05-03T14:00:00Z")


def frame(n=160):
    close = 100 + np.arange(n) * 0.02 + 4 * np.sin(np.arange(n) / 4)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(T, periods=n, freq="h"),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close + 0.1,
            "volume": np.full(n, 100.0),
        }
    )


def eligibility():
    return BroadEligibilityIndex.build(
        pd.DataFrame({"decision_time": [T - pd.Timedelta(days=1)], "pair": ["BTC-USDT"]})
    )


def test_eligibility_series_root_cause_and_canonical_api():
    ranking = pd.DataFrame({"decision_time": [T], "pair": ["BTC-USDT"], "eligible": [True]})
    assert isinstance(ranking.eligible, pd.Series) and not callable(ranking.eligible)
    with pytest.raises(TypeError, match="Series.*not callable"):
        ranking.eligible("BTC-USDT", T)
    index = BroadEligibilityIndex.build(ranking)
    assert callable(index.eligible) and index.eligible("BTC-USDT", T)
    assert not index.eligible("BTC-USDT", T - pd.Timedelta(seconds=1))


def test_detector_module_attribute_api_surface():
    import ast

    for module in (det, mgmt, engine):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                target = {"rt": rt, "det": det, "eng": engine}.get(node.value.id)
                if target is not None:
                    assert hasattr(target, node.attr), (module.__name__, node.attr)


def test_detector_exceptions_are_not_swallowed(monkeypatch):
    def broken(*args):
        raise RuntimeError("DETECTOR_SENTINEL")

    monkeypatch.setattr(det, "scan_wyckoff", broken)
    with pytest.raises(RuntimeError, match="DETECTOR_SENTINEL"):
        pipeline.scan_pair("BTC-USDT", (frame(),) * 3, frame(), frame(), eligibility(), [], {})


def test_protected_reader_pre_call_and_pushdown(monkeypatch, tmp_path):
    path = tmp_path / "data/raw/rd16b/kucoin/BTC-USDT/1h.parquet"
    path.parent.mkdir(parents=True)
    path.touch()
    calls = []

    def read(*args, **kwargs):
        calls.append(kwargs)
        return frame(5)

    monkeypatch.setattr(pd, "read_parquet", read)
    with pytest.raises(FoundationError, match="WINDOW"):
        raw_frame(tmp_path, "BTC-USDT", cutoff=DATA_CUTOFF + pd.Timedelta(hours=1))
    assert not calls
    raw_frame(tmp_path, "BTC-USDT")
    assert ("timestamp", "<", DATA_CUTOFF.to_pydatetime()) in calls[0]["filters"]


def test_reader_detects_bad_backend(monkeypatch, tmp_path):
    path = tmp_path / "data/raw/rd16b/kucoin/BTC-USDT/1h.parquet"
    path.parent.mkdir(parents=True)
    path.touch()
    data = frame(1)
    data["timestamp"] = [DATA_CUTOFF]
    monkeypatch.setattr(pd, "read_parquet", lambda *a, **k: data)
    with pytest.raises(FoundationError, match="protected"):
        raw_frame(tmp_path, "BTC-USDT")


@pytest.mark.parametrize("scan", [det.scan_harmonic, det.scan_classical])
def test_prefix_and_future_mutation_event_identity(scan):
    f = frame(160)
    prefix = f.iloc[:110].copy()
    end = prefix.timestamp.iloc[-1]
    p = scan("BTC-USDT", prefix, eligibility())
    full = scan("BTC-USDT", f, eligibility())
    mutated = f.copy()
    mutated.loc[110:, ["open", "high", "low", "close"]] *= 5
    m = scan("BTC-USDT", mutated, eligibility())
    for index in (0, 1, 2):
        assert p[index] == [r for r in full[index] if r["timestamp"] <= end]
        assert p[index] == [r for r in m[index] if r["timestamp"] <= end]


def test_ict_prefix_invariance_after_raid_protection_repair():
    complete = frame(320)
    past = complete.iloc[:200].copy()
    mutated = complete.copy()
    mutated.loc[200:, ["open", "high", "low", "close"]] *= 3

    def run(f):
        return det.scan_ict(
            "BTC-USDT",
            f,
            canonical_aggregate(Path.cwd(), "BTC-USDT", f, "4h"),
            canonical_aggregate(Path.cwd(), "BTC-USDT", f, "1d"),
            f,
            f,
            eligibility(),
        )

    original = run(past)
    for result in (run(complete), run(mutated)):
        for index in (0, 1, 2):
            assert original[index] == [
                r for r in result[index] if r["timestamp"] <= past.timestamp.iloc[-1]
            ]


def test_pivot_ledger_immutable_and_available_before_collapse():
    p = [
        rt.Pivot("H", 1, 105, T, T + pd.Timedelta(hours=2)),
        rt.Pivot("H", 4, 115, T + pd.Timedelta(hours=3), T + pd.Timedelta(hours=5)),
    ]
    before = tuple(p)
    visible = rt.collapse_same_kind(rt.available_pivots(p, T + pd.Timedelta(hours=2)))
    assert visible[0].price == 105 and tuple(p) == before


@pytest.mark.parametrize("with_fvg", [False, True])
def test_ict_raid_invalidation_before_activation_is_absorbing(with_fvg):
    runtime = rt.ICT2022CoreRuntime("BTC-USDT")
    runtime.pending = rt.ICTPending(T, 90.0, 100.0, 130.0)
    if with_fvg:
        runtime.pending.fvg = (101.0, 103.0)
        runtime.pending.fvg_created_at = T + pd.Timedelta(hours=1)
    assert not runtime.invalidate_pending_raid(T, 89.0)
    assert not runtime.invalidate_pending_raid(T + pd.Timedelta(hours=1), 90.1)
    assert runtime.invalidate_pending_raid(T + pd.Timedelta(hours=2), 90.0)
    assert runtime.pending is None
    assert runtime.transitions[-1].to_state == "INVALIDATED"
    assert not runtime.register_mss_displacement(
        T + pd.Timedelta(hours=3), 105.0, 100.0, 2.0, (101.0, 103.0), None
    )
    assert runtime.retracement_intent(T + pd.Timedelta(hours=4), 102.0, 104.0, 103.0) is None
    import inspect

    assert "ict.invalidate_pending_raid(t, lows[i])" in inspect.getsource(det.scan_ict)


def test_ict_ordering_and_provenance():
    runtime = rt.ICT2022CoreRuntime("BTC-USDT")
    assert runtime.register_raid(
        T,
        90,
        100,
        130,
        htf_bias="BULLISH_DRAW",
        dealing_state="DISCOUNT",
        reclaimed=True,
        session_state="POST_NY_0830",
    )
    assert not runtime.register_mss_displacement(T, 105, 100, 2, (98, 101), None)
    t1, t2 = T + pd.Timedelta(hours=1), T + pd.Timedelta(hours=2)
    assert runtime.register_mss_displacement(t1, 105, 100, 2, (98, 101), None)
    assert runtime.retracement_intent(t1, 99, 105, 102) is None
    intent = runtime.retracement_intent(t2, 99, 105, 102)
    assert intent is not None
    assert (
        pd.Timestamp(intent.metadata["raid_time"])
        < pd.Timestamp(intent.metadata["mss_time"])
        < pd.Timestamp(intent.metadata["retrace_time"])
    )
    assert intent.metadata["execution_array"] == "FVG"


def test_harmonic_absorbing_invalidation():
    candidate = rt.HarmonicCandidate("BAT", 90, 120, 100, 115, 95, 94, 96, 90, {})
    lifecycle = rt.HarmonicLifecycle(candidate)
    assert lifecycle.test_prz(T, 93, 97)
    assert lifecycle.type1_confirm(True, False)
    lifecycle.complete_type1()
    assert not lifecycle.type2_retest(89, 97, True)
    assert lifecycle.state == "INVALIDATED"
    assert not lifecycle.type2_retest(94, 97, True)
    assert not lifecycle.test_prz(T, 94, 97)


def test_hard_harmonic_invalidation_before_activation(monkeypatch):
    f = frame(10)
    pivots = [
        rt.Pivot(k, i, p, f.timestamp.iloc[i], f.timestamp.iloc[i + 2])
        for i, (k, p) in enumerate(zip(["L", "H", "L", "H"], [90, 120, 100, 115], strict=True))
    ]
    monkeypatch.setattr(rt, "confirmed_pivots_2l2r", lambda *a: pivots)
    monkeypatch.setattr(det, "_regular_projection_allowed", lambda *a: True)
    monkeypatch.setattr(
        rt,
        "project_harmonic_prz",
        lambda *a: {"prz_low": 95.0, "prz_high": 99.0, "make_or_break": 94.0},
    )
    monkeypatch.setattr(rt, "project_five_zero_prz", lambda *a: None)
    monkeypatch.setattr(rt, "project_shark_prz", lambda *a: None)
    f.loc[7, ["low", "high"]] = [93.0, 101.0]
    _, events, intents, _ = det.scan_harmonic("BTC-USDT", f, eligibility())
    assert any("PROJECTION_INVALIDATED" in r["event"] for r in events)
    assert not intents


def test_elliott_tombstone_never_resurrects():
    count = rt.ElliottCount("same", "1H", "IMPULSE", "BULLISH", (), 90, 130, T, 2)
    alive, tombstones = rt.invalidate_elliott_counts_persistent({"1H": [count]}, 89, set())
    assert not alive["1H"] and "same" in tombstones
    alive, _ = rt.invalidate_elliott_counts_persistent({"1H": [count]}, 110, tombstones)
    assert not alive["1H"]


def test_classical_context_not_from_name_and_later_retest():
    runtime = rt.ClassicalRuntime("BTC-USDT")
    pattern = rt.ClassicalPattern("id", "DOUBLE_BOTTOM", 105, 90, 15, "UNKNOWN", T)
    runtime.mature(pattern)
    assert runtime.pending["id"]["pattern"].prior_trend == "UNKNOWN"
    assert runtime.update_breakout(T, "id", 106, 100, 90)
    assert runtime.entry_intent(T, "id", 104, 106) is None
    assert runtime.entry_intent(T + pd.Timedelta(hours=4), "id", 104, 106) is not None
    pats = rt.continuation_patterns_from_bars(frame(25), 3, [])
    assert all(p.prior_trend == "UNKNOWN" for p in pats if p.kind == "BASE_BREAKOUT")


def test_evidence_future_parent_and_expiry():
    record = foundation.EvidenceRecord(
        "x",
        "RAID",
        "s",
        T,
        T + pd.Timedelta(hours=1),
        "h",
        parent_edges=(foundation.ParentEdge("p", foundation.ParentEdgeType.LIVE_REQUIREMENT),),
    )
    assert not record.is_live(T)
    assert not record.is_live(T + pd.Timedelta(hours=2))
    assert record.is_live(T + pd.Timedelta(hours=2), {"p": foundation.EvidenceStatus.ACTIVE})
    record.invalidate()
    assert not record.is_live(T + pd.Timedelta(hours=2), {"p": foundation.EvidenceStatus.ACTIVE})


def test_mtm_risk_arithmetic_partial_and_campaign_b0():
    position = foundation.PositionMark("BTC-USDT", 2, 110, 95, 0.0025)
    assert foundation.equity(100, [position]) == 320
    assert foundation.gross_mtm([position]) == 220
    assert position.open_stop_risk == pytest.approx(30.475)
    c = foundation.CampaignRecord("c", "t", "BTC-USDT", 500)
    c.commit(250, 100000, 250)
    c.commit(250, 100000, 250, is_add=True)
    assert c.committed_risk == 500
    with pytest.raises(ValueError, match="MAXIMUM_ONE"):
        c.commit(1, 100000, 250, is_add=True)
    assert not c.can_commit(1, 200000, 250)


def test_common_lambda_and_capacity_failure():
    positions = {
        1: {
            "episode": {"pair": "BTC-USDT"},
            "qty_current": 800,
            "current_stop": 90,
            "campaign_id": "c",
        },
        2: {
            "episode": {"pair": "ETH-USDT"},
            "qty_current": 800,
            "current_stop": 90,
            "campaign_id": "d",
        },
    }
    p = PortfolioKernel(10000, positions, {}, 0.00125)

    def marks(pair, now):
        return 100.0

    lam, _ = engine.proportional_risk_reduction_lambda(p.cash, p.positions, marks, T, 0.00125)
    assert 0 < lam < 1
    assert not p.reduce_common(marks, T, {}, lambda *a: a[1])
    assert p.cash == 10000 and p.positions[1]["qty_current"] == 800
    p.risk_breach_unresolved = False
    assert p.reduce_common(marks, T, {"BTC-USDT": 100000, "ETH-USDT": 100000}, lambda *a: a[1])
    assert p.positions[1]["qty_current"] / 800 == pytest.approx(lam)
    assert p.positions[2]["qty_current"] / 800 == pytest.approx(lam)


def test_entry_unknown_capacity_owner_conflict_and_partial_risk_no_release():
    p = PortfolioKernel(100000, {}, {}, 0.00125)
    row = {"pair": "BTC-USDT", "entry_open": 100.0, "stop": 90.0, "identity": "id"}
    kwargs = {"normalizer": lambda *a: a[1], "campaign_id": "c", "funded_ready": True}
    assert not p.admit(row, lambda *a: 100.0, T, None, **kwargs)[0]
    assert p.admit(row, lambda *a: 100.0, T, 20000, **kwargs)[0]
    committed = p.campaigns["c"].committed_risk
    assert not p.admit(row, lambda *a: 100.0, T, 20000, **{**kwargs, "campaign_id": "other"})[0]
    p.partial_exit(1, p.positions[1]["qty_current"] / 2, 110)
    assert p.campaigns["c"].committed_risk == committed
    assert p.snapshot(lambda *a: 110.0, T)["gross"] == pytest.approx(
        p.positions[1]["qty_current"] * 110
    )


@pytest.mark.parametrize("mode", ["ICT", "CLASSICAL"])
def test_management_helper_consumption(monkeypatch, mode):
    f = frame(4)
    r = SimpleNamespace(
        entry_time=f.timestamp.iloc[0],
        stop=80.0,
        targets_json="[150]",
        metadata={"raid_time": str(T - pd.Timedelta(hours=1)), "pattern_kind": "RECTANGLE"},
    )
    calls = []
    if mode == "ICT":
        monkeypatch.setattr(rt, "ict_manage_active", lambda **kw: calls.append(kw) or "HOLD")
        outcome = mgmt.evaluate_ict_native(r, f, [])
    else:
        monkeypatch.setattr(
            rt,
            "classical_management_update",
            lambda **kw: calls.append(kw) or {"action": "HOLD", "stop": 80.0},
        )
        outcome = mgmt.evaluate_classical_native(r, f, f, [])
    assert calls and outcome["management_trace"]


def test_dow_clock_episode_record_and_reversal_priority():
    runtime = rt.DowRuntime("PRIMARY_BULL")
    assert runtime.update("DOWN", "DOWN", {"confirmed": False}, False) == "DEFINITE_REVERSAL"
    assert runtime.update("UP", "UP", {"confirmed": True}, False) == "PRIMARY_BULL"
    runtime.update("UP", "RANGE", {"confirmed": True}, False)
    assert runtime.update("UP", "UP", {"confirmed": True}, False) == "RECONFIRMED_BULL"
    row = pd.Series({"entry_time": T, "pair": "BTC-USDT"})
    record = engine.episode_record(
        row, {"exit_time": T, "exit_price": 100.0, "exit_reason": "x", "fills": []}, 500.0
    )
    assert record["entry_time"] == T - pd.Timedelta(hours=1)
    assert not engine.size_notional(SimpleNamespace(entry_open=100, stop=np.nan), 100000, 20000)


def test_next_open_and_cache_all_bindings():
    assert pipeline.next_open_intent_valid(T, T)
    assert not pipeline.next_open_intent_valid(T, T + pd.Timedelta(hours=1))
    assert not pipeline.next_open_intent_valid(DATA_CUTOFF, DATA_CUTOFF)
    k = pipeline.cache_key("s", "c", "i")
    assert all(
        k != pipeline.cache_key(*a) for a in [("s2", "c", "i"), ("s", "c2", "i"), ("s", "c", "i2")]
    )


def test_selection_repeatable_cross_category_week_uniqueness():
    pools = {}
    for kind in ("POSITIVE", "INTERMEDIATE", "NO_INTENT"):
        pools[(pipeline.SYSTEMS[0], 2022, kind)] = [
            {
                "system_id": pipeline.SYSTEMS[0],
                "pair": "BTC-USDT",
                "time": T + pd.Timedelta(days=8 * k),
                "kind": kind,
                "engine_row": None,
            }
            for k in range(50)
        ]
    selected, audit = pipeline.select_cases(pools, reserve=True)
    again, _ = pipeline.select_cases({k: list(reversed(v)) for k, v in pools.items()}, reserve=True)
    assert selected == again
    assert len({pipeline.week_key(r) for r in selected}) == len(selected)
    assert audit[0]["categories"]["POSITIVE"]["selected"] == 5


def test_selector_precedence_and_no_school_score():
    thesis = foundation.ThesisRecord(
        "id", "g", "s", "BTC-USDT", T, "entry", "invalid", "manage", 500, (), 0.1, funded_ready=True
    )
    add = replace(thesis, thesis_id="add", action_class="ADD", ready_at=T + pd.Timedelta(days=1))
    assert foundation.order_eligible_theses([thesis, add]) == [add, thesis]


def test_gate3_freeze_and_replay_kill_switch(tmp_path):
    assert gate3.config_hash(gate3.specification()) == gate3.config_hash(gate3.specification())
    assert gate3.validate_preconditions({}, {}, tmp_path)
    with pytest.raises(PermissionError, match="DISABLED"):
        gate3.replay()
    with pytest.raises(engine.Gate1ContractError):
        engine.simulate_portfolio(pd.DataFrame(), None, 0.0025)
    assert not hasattr(engine, "simulate_portfolio_legacy_initial_equity")
    assert gate3.concentration(np.array([5.0, 5.0, -1.0]), np.array([5.0, 4.0]))
    assert not gate3.concentration(np.array([5.0, -4.0]), np.array([1.0]))
    assert gate3.basic_lcb(1.0, np.full(9999, 1.0), 2) == 1.0
    a = gate3.stationary_indices(100, 5.0, np.random.default_rng(1))
    b = gate3.stationary_indices(100, 5.0, np.random.default_rng(1))
    assert np.array_equal(a, b)


def test_management_ny_boundary_never_backdates_open(monkeypatch):
    data = frame(4)
    row = SimpleNamespace(
        entry_time=data.timestamp.iloc[0],
        stop=80.0,
        targets_json="[150]",
        metadata={"raid_time": str(T - pd.Timedelta(hours=1))},
    )
    monkeypatch.setattr(
        rt,
        "ict_manage_active",
        lambda **kw: "NY_1600_DAY_BOUNDARY" if kw["t"] == data.timestamp.iloc[2] else "HOLD",
    )
    outcome = mgmt.evaluate_ict_native(row, data, [])
    assert outcome["exit_time"] == data.timestamp.iloc[2]
    assert outcome["exit_price"] == data.open.iloc[3]


def test_invalid_stop_and_six_assets_common_reduction():
    assert engine.size_notional(SimpleNamespace(entry_open=100.0, stop=-1), 100000.0, 1000.0) == 0
    assert engine.size_notional(SimpleNamespace(entry_open=100.0, stop=0), 100000.0, 1000.0) == 0
    positions = {
        i: {"episode": {"pair": str(i)}, "qty_current": 1.0, "current_stop": 90.0} for i in range(6)
    }

    def marks(*a):
        return 100.0

    state = engine.current_mtm_state(100000, positions, marks, T, 0.00125)
    assert not engine.current_mtm_limits_ok(state)
    assert engine.proportional_risk_reduction_lambda(100000, positions, marks, T, 0.00125)[0] == 0


def test_malformed_management_authority_fails_visibly():
    with pytest.raises(ValueError):
        engine.parse_json("not-json")
    with pytest.raises(ValueError):
        mgmt.evaluate_ict_native(SimpleNamespace(metadata="not-json"), frame(4))
