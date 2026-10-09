from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from spotbot.research.multi_school_fidelity import full_replay_v5 as v5
from spotbot.research.multi_school_fidelity.lifecycle_execution_v6 import LifecycleExecution
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import (
    CL,
    EL,
    GRAMMARS,
    H1,
    H2,
    H3,
    ICT,
    Binding,
    CompletedBar,
    ContractError,
    LiveEvidence,
    Mode,
    Objective,
    OwnerFailure,
    PendingSetup,
    Phase,
    Pivot,
    StructuralManager,
    instant,
    unresolved_authorities,
)

T = datetime(2022, 1, 3, tzinfo=UTC)
SHA = "a" * 64


def binding(grammar=CL, tf="1H", stop=90.0, structure="owner"):
    return Binding(
        grammar,
        {H1: CL, H2: ICT, H3: EL}.get(grammar, grammar),
        structure,
        SHA,
        tf,
        T,
        stop,
        "owned_initial_structural_invalidation",
    )


def goal(price=120.0, ident="goal", structure="owner", at=T):
    return Objective(ident, structure, price, "CONFIRMED_RESISTANCE", at, SHA)


def bar(i, close=120.0, low=115.0, high=125.0, opened=120.0, tf="1H"):
    duration = {"1H": 1, "4H": 4, "1D": 24}[tf]
    start = T + timedelta(hours=i)
    return CompletedBar(start, start + timedelta(hours=duration), tf, opened, high, low, close)


def pivot(kind, value, observed, available, ident):
    return Pivot(
        ident, "owner", kind, value, T + timedelta(hours=observed), T + timedelta(hours=available)
    )


def first_chain():
    return (
        pivot("L", 90.0, -4, -2, "l0"),
        pivot("H", 110.0, -3, -1, "h0"),
        pivot("L", 100.0, 1, 3, "l1"),
        pivot("H", 125.0, 4, 6, "h1"),
    )


def manager(grammar=CL, mode=Mode.TREND, tf="1H", objectives=()):
    return StructuralManager(binding(grammar, tf), T, 105.0, mode, 0.0025, 0.0025, objectives)


def progressed():
    m = manager()
    for i in range(5):
        m.on_close(bar(i))
    m.on_close(bar(5, close=120.0, low=99.0), pivots=first_chain())
    assert m.protected_low == 100.0 and m.hard_stop == 90.0
    return m


def test_no_dollar_profit_target_is_manufactured():
    m = manager(objectives=(goal(106.0),))
    e = m.objective_economics(10000.0)[0]
    assert e["price"] == 106.0
    assert e["expected_profit"] == "UNKNOWN_NOT_A_FORECAST"
    assert e["net_reward"] < 100.0
    assert manager().objective_economics(10000.0) == []
    assert "meaningful_profit_floor" in unresolved_authorities()


def test_finite_native_goal_requires_positive_executable_net_not_large_imagined_goal():
    with pytest.raises(ContractError, match="UNRESOLVED"):
        manager(mode=Mode.FINITE)
    with pytest.raises(ContractError, match="CANNOT_COVER_COSTS"):
        manager(mode=Mode.FINITE, objectives=(goal(105.1),))
    m = manager(mode=Mode.FINITE, objectives=(goal(120.0), goal(115.0, "near")))
    assert m.finite_objective.price == 115.0


def test_stop_only_earned_after_full_alternating_higher_low_higher_high():
    m = manager()
    for i in range(3):
        m.on_close(bar(i))
    d = m.on_close(bar(3), pivots=first_chain()[:3])
    assert d.hard_stop_after == 90.0 and d.protected_low == 90.0
    d = m.on_close(bar(4))
    assert d.protected_low == 90.0
    d = m.on_close(bar(5), pivots=first_chain()[3:])
    assert d.protection_chain == ("l0", "h0", "l1", "h1")
    assert m.protected_low == 100.0 and m.hard_stop == 90.0


def test_non_alternating_independent_high_low_bags_cannot_earn_protection():
    m = manager()
    ps = first_chain()
    extra = pivot("L", 95.0, 2, 4, "extra-low")
    for i in range(5):
        m.on_close(bar(i))
    m.on_close(bar(5), pivots=(*ps, extra))
    assert m.protected_low == 90.0


def test_wick_under_soft_protected_low_is_not_exit():
    m = progressed()
    d = m.on_close(bar(6, close=104.0, low=98.0, opened=110.0))
    assert d.action == "HOLD" and d.phase == Phase.PULLBACK
    assert m.hard_stop == 90.0 and m.protected_low == 100.0


def test_first_close_break_then_reclaim_holds():
    m = progressed()
    d = m.on_close(bar(6, close=99.0, low=97.0, opened=110.0))
    assert d.action == "HOLD" and d.phase == Phase.BREAK_PENDING
    d = m.on_close(bar(7, close=101.0, low=98.0, opened=99.0))
    assert d.action == "HOLD" and d.reason == "PROTECTED_LEVEL_RECLAIMED"


def test_later_owner_close_failed_reclaim_requests_next_open_not_old_low():
    m = progressed()
    m.on_close(bar(6, close=99.0, low=97.0, opened=110.0))
    d = m.on_close(bar(7, close=98.0, low=96.0, opened=99.0))
    assert d.action == "EXIT_NEXT_OPEN" and d.known_at == T + timedelta(hours=8)
    assert d.applies_from >= d.known_at and d.hard_stop_after == 90.0
    assert m.on_close(bar(8)).action == "EXIT_NEXT_OPEN"


def test_second_earned_chain_raises_hard_stop_but_never_lowers_it_on_pullback():
    m = progressed()
    next_ps = (pivot("L", 110.0, 6, 8, "l2"), pivot("H", 140.0, 9, 11, "h2"))
    m.on_close(bar(6))
    m.on_close(bar(7), pivots=next_ps[:1])
    m.on_close(bar(8))
    m.on_close(bar(9))
    d = m.on_close(bar(10, close=130.0, high=140.0), pivots=next_ps[1:])
    assert d.hard_stop_before == 90.0 and d.hard_stop_after == 100.0
    assert d.protected_low == 110.0
    d = m.on_close(bar(11, close=108.0, low=107.0, opened=120.0))
    assert d.hard_stop_after == 100.0 and d.phase == Phase.BREAK_PENDING


def test_objective_checkpoint_neither_exits_nor_promotes_or_tightens_stop():
    m = manager(objectives=(goal(110.0),))
    d = m.on_close(bar(0))
    assert d.checkpoint_ids == ("goal",) and d.action == "HOLD"
    assert m.phase == Phase.ENTERED and m.hard_stop == 90.0


def test_next_known_objective_advances_without_capping_trend_or_resurrecting_old_goal():
    m = manager(objectives=(goal(110.0), goal(130.0, "g2")))
    assert m.next_checkpoint(105.0).price == 110.0
    d = m.on_close(bar(0, high=125.0))
    assert d.next_checkpoint_price == 130.0 and d.action == "HOLD"
    new = goal(150.0, "g3", at=T + timedelta(hours=2))
    d = m.on_close(bar(1, close=140.0, high=145.0, low=135.0, opened=140.0), objectives=(new,))
    assert d.next_checkpoint_price == 150.0 and d.action == "HOLD"
    assert m.next_checkpoint(108.0).price == 150.0
    assert m.next_checkpoint(151.0) is None


def test_future_bar_projection_invariance_without_market_data():
    # Two runs with identical causal prefixes, different as-yet-unobserved futures.
    left, right = progressed(), progressed()
    a = left.on_close(bar(6, close=104.0, low=98.0, opened=110.0))
    b = right.on_close(bar(6, close=104.0, low=98.0, opened=110.0))
    assert a == b
    left.on_close(bar(7, close=150.0, high=160.0, low=140.0, opened=150.0))
    right.on_close(bar(7, close=99.0, low=97.0, opened=104.0))
    assert a == b and a.hard_stop_after == 90.0


def test_target_prices_cannot_be_rewritten_under_same_source_identity():
    m = manager(objectives=(goal(),))
    with pytest.raises(ContractError, match="MUTATED"):
        m.add_objectives((goal(200.0),), T)


@pytest.mark.parametrize(
    "field,value", [("structure_id", "other"), ("available_at", T + timedelta(hours=8))]
)
def test_future_or_other_owner_pivot_rejected_atomically(field, value):
    m = manager()
    p = replace(first_chain()[0], **{field: value})
    with pytest.raises(ContractError):
        m.on_close(bar(0), pivots=(p,))
    assert m.last_close_at is None and not m.pivots


def test_context_and_child_invalidation_no_resurrection():
    setup = PendingSetup("owner")
    setup.observe(LiveEvidence("context", "owner", T), T)
    setup.observe(LiveEvidence("location", "owner", T, ("context",)), T)
    setup.observe(LiveEvidence("trigger", "owner", T, ("location",)), T)
    setup.invalidate("context")
    assert not setup.activate(("trigger",), T)
    with pytest.raises(ContractError, match="NO_RESURRECTION"):
        setup.observe(LiveEvidence("context", "owner", T), T)
    setup.context_changed(False)
    assert setup.closed and not setup.live("location", T)


def test_expiry_and_consumption_are_absorbing_and_cycles_are_not_valid():
    s = PendingSetup("owner")
    s.observe(LiveEvidence("a", "owner", T, valid_until=T + timedelta(hours=1)), T)
    assert not s.live("a", T + timedelta(hours=1))
    s.observe(LiveEvidence("b", "owner", T, ("c",)), T)
    s.observe(LiveEvidence("c", "owner", T, ("b",)), T)
    assert not s.live("b", T)
    assert s.activate(("a",), T)
    with pytest.raises(ContractError):
        s.observe(LiveEvidence("new", "owner", T), T)


def test_gap_in_owner_close_coverage_cannot_count_as_confirmed_break():
    m = progressed()
    m.on_close(bar(6, close=99.0, low=98.0, opened=110.0))
    with pytest.raises(ContractError, match="COVERAGE_GAP"):
        m.on_close(bar(8, close=98.0, low=97.0, opened=99.0))


def test_owner_timeframe_not_child_timeframe_drives_confirmation():
    m = manager(tf="4H")
    with pytest.raises(ContractError, match="TIMEFRAME"):
        m.on_close(bar(0))
    assert m.on_close(bar(0, tf="4H")).action == "HOLD"


def test_closed_thesis_and_old_binding_cannot_be_resurrected():
    m = manager()
    m.mark_closed()
    with pytest.raises(ContractError, match="NO_RESURRECTION"):
        m.on_close(bar(0))
    with pytest.raises(ContractError, match="FUTURE_BINDING"):
        StructuralManager(
            replace(binding(), available_at=T + timedelta(hours=1)), T, 105.0, Mode.TREND, 0.0, 0.0
        )


def bridge(grammar=CL, mode=Mode.TREND, pair="X", pf=None, tf="1H"):
    pf = pf or v5.Portfolio(0.005, {pair: v5.ContinuousRule(pair, SHA)})
    exe = LifecycleExecution(pf)
    row = {
        "identity": "test-" + grammar,
        "pair": pair,
        "owner_grammar": grammar,
        "owner_structure_id": "owner",
        "management_owner": v5.HA if grammar == H3 else binding(grammar).owner,
        "count_id": "owner" if grammar == H3 else None,
        "projection_id": "legacy-projection",
    }
    ok, reason = exe.admit(
        row,
        binding(grammar, tf),
        T,
        105.0,
        10000.0,
        row["identity"],
        mode=mode,
        objectives=(goal(),),
        research_authorized=True,
    )
    assert ok, reason
    return exe, next(iter(pf.k.positions))


@pytest.mark.parametrize("grammar", GRAMMARS)
def test_all_nine_real_kernel_dispatches_use_bound_owner_and_hold_above_checkpoint(grammar):
    exe, tid = bridge(grammar)
    d = exe.on_completed_hour(tid, bar(0), {"X": 100000.0}, owner_bar=bar(0))
    assert d.action == "HOLD" and tid in exe.portfolio.k.positions
    r = exe.portfolio.k.positions[tid]["episode"]
    assert r["management_owner"] == binding(grammar).owner and r["target"] is None
    assert len(exe.portfolio.k.fills) == 1
    if grammar == H3:
        assert r["management_owner"] == EL and r["owner_structure_id"] == r["count_id"]


def test_soft_wick_is_held_and_confirmed_break_actually_sells_next_open():
    exe, tid = bridge()
    m = exe.managers[tid]
    for i in range(5):
        b = bar(i)
        exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b)
    exe.on_completed_hour(
        tid, bar(5, low=99.0), {"X": 100000.0}, owner_bar=bar(5, low=99.0), pivots=first_chain()
    )
    exe.on_completed_hour(
        tid,
        bar(6, close=104.0, low=98.0, opened=110.0),
        {"X": 100000.0},
        owner_bar=bar(6, close=104.0, low=98.0, opened=110.0),
    )
    assert tid in exe.portfolio.k.positions and not exe.pending
    for i, cl in [(7, 99.0), (8, 98.0)]:
        b = bar(i, close=cl, low=96.0, opened=100.0)
        exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b)
    assert tid in exe.portfolio.k.positions and tid in exe.pending
    exe.on_open(T + timedelta(hours=9), {"X": 97.0}, {"X": 100000.0})
    assert tid not in exe.portfolio.k.positions and m.phase == Phase.CLOSED
    assert exe.portfolio.k.fills[-1]["price"] == 97.0
    assert exe.portfolio.k.fills[-1]["reason"] == "LATER_OWNER_CLOSE_FAILED_RECLAIM"


def test_initial_hard_stop_precedes_finite_target_same_bar_and_gap_price_is_actual():
    exe, tid = bridge(mode=Mode.FINITE)
    b = bar(0, close=100.0, low=89.0, high=130.0, opened=105.0)
    exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b)
    assert exe.portfolio.k.fills[-1]["price"] == 90.0
    assert exe.portfolio.k.fills[-1]["reason"] == "HARD_STRUCTURAL_STOP"
    exe, tid = bridge()
    exe.on_open(T + timedelta(hours=1), {"X": 85.0}, {"X": 100000.0})
    assert exe.portfolio.k.fills[-1]["price"] == 85.0


def test_new_stop_is_not_applied_to_old_low_and_stop_never_decreases():
    exe, tid = bridge()
    m = exe.managers[tid]
    for i in range(5):
        b = bar(i)
        exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b)
    exe.on_completed_hour(
        tid, bar(5, low=99.0), {"X": 100000.0}, owner_bar=bar(5, low=99.0), pivots=first_chain()
    )
    for i in range(6, 10):
        b = bar(i)
        exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b)
    ps = (pivot("L", 110.0, 6, 8, "l2"), pivot("H", 140.0, 9, 11, "h2"))
    b = bar(10, close=130.0, high=140.0, low=95.0)
    exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b, pivots=ps)
    assert tid in exe.portfolio.k.positions and m.hard_stop == 100.0
    assert exe.portfolio.k.positions[tid]["current_stop"] == 100.0


def test_capacity_delayed_confirmed_exit_stays_pending_and_failure_is_not_hidden():
    exe, tid = bridge()
    m = exe.managers[tid]
    fail = OwnerFailure("failure", CL, "owner", "PATTERN_CONTEXT_FAILURE", T, SHA)
    b = bar(0)
    exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b, native_failure=fail)
    exe.on_open(T + timedelta(hours=1), {"X": 110.0}, {"X": 0.0})
    assert tid in exe.portfolio.k.positions and tid in exe.pending
    assert not exe.portfolio.risk_pass
    exe.on_open(T + timedelta(hours=2), {"X": 108.0}, {"X": 100000.0})
    assert tid not in exe.portfolio.k.positions and m.phase == Phase.CLOSED


def test_multiasset_admission_requires_all_current_marks_not_new_entry_price_for_every_asset():
    exe, tid = bridge()
    pf = exe.portfolio
    pf.rules["Y"] = v5.ContinuousRule("Y", SHA)
    row = {"identity": "y", "pair": "Y", "owner_grammar": CL, "owner_structure_id": "owner"}
    with pytest.raises(ContractError, match="ALL_ASSET_MARKS"):
        exe.admit(
            row,
            binding(),
            T,
            1000.0,
            10000.0,
            "y",
            mode=Mode.TREND,
            objectives=(),
            research_authorized=True,
        )
    assert len(pf.k.positions) == 1


def test_targeted_asset_cap_repair_does_not_sell_unaffected_asset():
    pf = v5.Portfolio(0.005, {p: v5.ContinuousRule(p, SHA) for p in ("X", "Y")})
    exe, tid = bridge(pf=pf)
    # Admitted close-to-stop to reach asset cap; test another independently held asset.
    row = {"identity": "y", "pair": "Y", "owner_grammar": CL, "owner_structure_id": "owner"}
    assert exe.admit(
        row,
        replace(binding(), initial_invalidation=99.0),
        T,
        100.0,
        50000.0,
        "y",
        mode=Mode.TREND,
        objectives=(),
        research_authorized=True,
        prices={"X": 105.0},
    )[0]
    original_x = pf.k.positions[tid]["qty_current"]
    prices = {"X": 105.0, "Y": 110.0}
    cap = {"X": 100000.0, "Y": 100000.0}
    assert exe.restore_risk_at_open(T + timedelta(hours=1), prices, cap)
    assert pf.k.positions[tid]["qty_current"] == original_x
    assert all(f["pair"] == "Y" for f in pf.k.fills if f["side"] == "SELL")


def test_no_default_arming_or_wrong_h3_owner_binding():
    pf = v5.Portfolio(0.005, {"X": v5.ContinuousRule("X", SHA)})
    exe = LifecycleExecution(pf)
    with pytest.raises(ContractError, match="NOT_AUTOMATICALLY_ARMED"):
        exe.admit({}, binding(), T, 105.0, 10000.0, "x", mode=Mode.TREND, objectives=())
    with pytest.raises(ContractError, match="OWNER_MISMATCH"):
        StructuralManager(replace(binding(H3), owner=v5.HA), T, 105.0, Mode.TREND, 0.0, 0.0)


def test_naive_clock_and_invalid_bars_rejected():
    with pytest.raises(ContractError):
        instant(datetime(2022, 1, 1))
    with pytest.raises(ContractError):
        manager().on_close(bar(0, low=130.0))


def test_synthetic_cash_fee_and_realized_pnl_reconcile():
    exe, tid = bridge(mode=Mode.FINITE)
    pf = exe.portfolio
    exe.on_open(T + timedelta(hours=1), {"X": 130.0}, {"X": 100000.0})
    assert not pf.k.positions
    assert pf.k.fills[-1]["price"] == 120.0
    assert pf.k.cash == pytest.approx(100000.0 + sum(f["cash_delta"] for f in pf.k.fills))
    assert sum(f["fee"] for f in pf.k.fills) > 0


def test_failure_event_requires_owner_source_and_causal_clock():
    m = manager()
    for fail in [
        "COUNT_INVALIDATED",
        OwnerFailure("f", EL, "owner", "COUNT_INVALIDATED", T, SHA),
        OwnerFailure("f", CL, "owner", "PATTERN_CONTEXT_FAILURE", T + timedelta(hours=2), SHA),
    ]:
        with pytest.raises(ContractError):
            m.on_close(bar(0), native_failure=fail)
    assert m.last_close_at is None


def test_missing_first_owner_bar_and_duplicate_execution_hour_fail_closed():
    with pytest.raises(ContractError, match="COVERAGE_GAP"):
        manager().on_close(bar(2))
    exe, tid = bridge()
    b = bar(0)
    exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b)
    with pytest.raises(ContractError, match="REPEATED_OR_COVERAGE_GAP"):
        exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b)


def test_bridge_rejected_owner_event_does_not_mutate_clock_or_cash():
    exe, tid = bridge()
    b = bar(0)
    cash = exe.portfolio.k.cash
    with pytest.raises(ContractError):
        exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=replace(b, timeframe="4H"))
    assert tid not in exe.last_execution_close and exe.portfolio.k.cash == cash
    assert exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b).action == "HOLD"


def test_native_source_failure_is_dispatched_between_owner_bar_closes():
    exe, tid = bridge(tf="4H")
    fail = OwnerFailure("f", CL, "owner", "PATTERN_CONTEXT_FAILURE", T + timedelta(hours=1), SHA)
    d = exe.on_completed_hour(tid, bar(0), {"X": 100000.0}, native_failure=fail)
    assert d.action == "EXIT_NEXT_OPEN"
    exe.on_open(T + timedelta(hours=1), {"X": 110.0}, {"X": 100000.0})
    assert tid not in exe.portfolio.k.positions


def test_open_cannot_execute_retroactively_and_failure_identity_is_immutable():
    exe, tid = bridge()
    b = bar(0)
    exe.on_completed_hour(tid, b, {"X": 100000.0}, owner_bar=b)
    with pytest.raises(ContractError, match="CLOCK_REVERSED"):
        exe.on_open(T, {"X": 85.0}, {"X": 100000.0})
    m = manager()
    fail = OwnerFailure("f", CL, "owner", "PATTERN_CONTEXT_FAILURE", T, SHA)
    m.on_native_failure(fail, T)
    with pytest.raises(ContractError, match="MUTATED"):
        m.on_native_failure(replace(fail, source_sha256="b" * 64), T)


def test_hard_stop_pending_is_absorbing_and_blocks_new_risk():
    exe, tid = bridge()
    b = bar(0, close=95.0, low=89.0, opened=105.0)
    exe.on_completed_hour(tid, b, {"X": 0.0}, owner_bar=b)
    assert exe.managers[tid].phase == Phase.BROKEN and tid in exe.pending
    pf = exe.portfolio
    pf.rules["Y"] = v5.ContinuousRule("Y", SHA)
    row = {"identity": "new", "pair": "Y", "owner_grammar": CL, "owner_structure_id": "owner"}
    ok, reason = exe.admit(
        row,
        binding(),
        T + timedelta(hours=1),
        105.0,
        10000.0,
        "new",
        mode=Mode.TREND,
        objectives=(),
        research_authorized=True,
        prices={"X": 95.0},
    )
    assert not ok and reason == "PENDING_EXIT_NO_NEW_RISK"


def test_owner_structure_cannot_be_resurrected_under_a_new_intent_digest():
    exe, tid = bridge(mode=Mode.FINITE)
    exe.on_open(T + timedelta(hours=1), {"X": 130.0}, {"X": 100000.0})
    row = {
        "identity": "different-digest",
        "pair": "X",
        "owner_grammar": CL,
        "owner_structure_id": "owner",
    }
    ok, reason = exe.admit(
        row,
        binding(),
        T + timedelta(hours=1),
        105.0,
        10000.0,
        "different-campaign",
        mode=Mode.TREND,
        objectives=(),
        research_authorized=True,
    )
    assert not ok and reason == "OWNER_STRUCTURE_NO_RESURRECTION"


@pytest.mark.parametrize(
    "field,value",
    [("mode", Mode.FINITE), ("entry_price", 100.0), ("binding", binding(H1)), ("hard_stop", 80.0)],
)
def test_entry_owner_mode_and_standing_risk_cannot_be_rewritten_after_profit(field, value):
    m = progressed()
    setattr(m, field, value)
    with pytest.raises(ContractError):
        m.on_close(bar(6))
