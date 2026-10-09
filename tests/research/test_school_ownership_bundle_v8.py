"""Synthetic-only ownership fixtures: no raw prices, outcomes, model or replay."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from spotbot.research.multi_school_fidelity.elliott_contract_v8 import (
    ElliottBook,
    ParentPrefix,
    ResumeCount,
    Wave,
)
from spotbot.research.multi_school_fidelity.harmonic_contract_v8 import (
    FAMILIES,
    HarmonicContract,
    project,
)
from spotbot.research.multi_school_fidelity.ict_h2_contract_v8 import (
    SESSION,
    TREND,
    AuctionChain,
    OwnedCampaign,
    bind_entry,
)
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import (
    Known,
    Point,
    clock,
    validate_points,
)
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import (
    CompletedBar,
    ContractError,
    Pivot,
)
from spotbot.research.multi_school_fidelity.wyckoff_contract_v8 import (
    ActivityBar,
    RangeCause,
    Readiness,
    Segment,
    SpringStage,
    WyckoffContract,
    pnf_cause,
)

T = datetime(2023, 1, 1, tzinfo=UTC)
SHA = "a" * 64


def at(h):
    return T + timedelta(hours=h)


def k(value, h, sid="s", name="e", until=None):
    return Known(name, value, at(h), SHA, sid, at(until) if until else None)


def pt(v, h, kind, degree="1H", name=None):
    right = {"1H": 2, "4H": 8, "1D": 48}[degree]
    return Point(name or f"p{h}{degree}", kind, v, at(h), at(h + right), degree)


def bar(h, o, hi, lo, c, degree="1H"):
    step = {"1H": 1, "4H": 4, "1D": 24}[degree]
    return CompletedBar(at(h), at(h + step), degree, o, hi, lo, c)


def harmonic(family, short=False):
    ratios = {
        "GARTLEY": 0.618,
        "BAT": 0.5,
        "ALTERNATE_BAT": 0.3,
        "BUTTERFLY": 0.786,
        "CRAB": 0.5,
        "DEEP_CRAB": 0.886,
        "ABCD": 0.6,
    }
    if family == "FIVE_ZERO":
        vals = [100.0, 150.0, 85.0, 215.0]
    elif family == "SHARK":
        vals = [200.0, 300.0, 250.0, 310.0]
    else:
        r = ratios[family]
        vals = [200.0, 300.0, 300.0 - 100 * r, 300.0 - 50 * r]
    if short:
        vals = [1000 - v for v in vals]
    kinds = ("H", "L", "H", "L") if short else ("L", "H", "L", "H")
    points = tuple(pt(v, i * 3, kind) for i, (v, kind) in enumerate(zip(vals, kinds, strict=True)))
    return project(family, points, at(12), k(1000.0, 12, name="atr"), 0.01)


@pytest.mark.parametrize("family", list(FAMILIES))
@pytest.mark.parametrize("short", [False, True])
def test_every_harmonic_family_later_terminal_confirmation(family, short):
    p = harmonic(family, short)
    m = HarmonicContract(p)
    if not short:
        b = bar(12, p.high + 1, p.high + 2, p.low - 0.1, p.high + 1)
        assert m.on_close(b) is None
        assert m.state == "TERMINAL_COMPLETE"
        c = bar(13, b.close, b.high + 2, p.low + 0.2, b.high + 1)
    else:
        b = bar(12, p.low - 1, p.high + 0.1, p.low - 2, p.low - 1)
        assert m.on_close(b) is None
        assert m.state == "TERMINAL_COMPLETE"
        c = bar(13, b.close, p.high - 0.2, b.low - 2, b.low - 1)
    t = m.on_close(c)
    assert t and t.owner == "HARMONIC_TYPE_I"
    assert t.side == ("SHORT_DIAGNOSTIC" if short else "LONG")
    assert not t.manifest()["funded_ready"]
    with pytest.raises(ContractError, match="REUSE"):
        m.thesis(c.end, "TYPE_I")


def test_harmonic_type2_requires_completed_type1_later_retest_then_confirm():
    p = harmonic("ABCD")
    m = HarmonicContract(p)
    m.on_close(bar(12, 211, 212, 209.9, 211))
    assert m.on_close(bar(13, 211, 214, 210, 213))
    with pytest.raises(ContractError, match="COMPLETION_ORDER"):
        m.complete_type1(at(15))
    m.complete_type1(at(14))
    assert m.on_close(bar(14, 213, 213, 209.995, 211)) is None
    assert m.state == "TYPE_II_RETEST"
    assert m.on_close(bar(15, 211, 215, 210, 214)).owner == "HARMONIC_TYPE_II"
    m.complete_type2()
    with pytest.raises(ContractError, match="NO_RESURRECTION"):
        m.on_close(bar(16, 214, 216, 212, 215))


def test_harmonic_gap_is_not_zone_traversal():
    p = harmonic("GARTLEY")
    m = HarmonicContract(p)
    assert m.on_close(bar(12, p.low - 2, p.low - 1, p.low - 3, p.low - 2)) is None
    assert m.state == "PROJECTED"


@pytest.mark.parametrize("family", list(FAMILIES))
def test_harmonic_future_projection_evidence_and_zero_tick_rejected(family):
    p = harmonic(family)
    with pytest.raises(ContractError, match="CAUSAL"):
        project(family, p.points, at(12), k(1000.0, 13), 0.01)
    with pytest.raises(ContractError, match="POSITIVE"):
        project(family, p.points, at(12), k(1000.0, 12), 0.0)


def elliott_count(cid="count", bullish=True):
    # Parent W1 and lower-degree 5-wave proof have exactly identical endpoints.
    vals = [100, 130, 120, 175, 160, 200]
    times = [0, 2, 4, 6, 8, 12]
    corr = [200, 170, 185, 160]
    ctimes = [12, 16, 20, 24]
    if not bullish:
        vals = [400 - v for v in vals]
        corr = [400 - v for v in corr]
    kinds = ("L", "H", "L", "H", "L", "H") if bullish else ("H", "L", "H", "L", "H", "L")
    mot = Wave(
        "w1" + cid,
        "IMPULSE",
        "1H",
        tuple(pt(v, h, t, name=f"{cid}m{h}") for v, h, t in zip(vals, times, kinds, strict=True)),
        (),
        SHA,
    )
    ck = ("H", "L", "H", "L") if bullish else ("L", "H", "L", "H")
    cor = Wave(
        "w2" + cid,
        "ZIGZAG",
        "1H",
        tuple(pt(v, h, t, name=f"{cid}c{h}") for v, h, t in zip(corr, ctimes, ck, strict=True)),
        (),
        SHA,
    )
    origin = pt(vals[0], 0, kinds[0], "4H", name="parent-origin")
    start = pt(corr[0], 12, ck[0], "4H", name="parent-correction-start")
    end = pt(corr[-1], 24, ck[-1], "4H", name="parent-correction-end")
    prefix = ParentPrefix("parent", "4H", (origin, start), (mot,))
    return ResumeCount(
        cid,
        "parent",
        "4H",
        "W2",
        start,
        end,
        cor,
        100 if bullish else 300,
        k(250 if bullish else 150, 32, "parent"),
        prefix,
    )


def test_elliott_proof_owner_later_confirmation_and_consumption():
    c = elliott_count()
    b = ElliottBook()
    b.add(c, at(32))
    assert b.decide(at(32), 190, c.claim) is None
    t = b.decide(at(33), 205, c.claim)
    assert t and t.owner == "ELLIOTT_COMMON_COUNT_OWNER" and t.initial_invalidation == 100
    assert b.decide(at(34), 210, c.claim) is None


def test_elliott_keeps_bearish_count_veto_not_latest_bullish():
    bull, bear = elliott_count(), elliott_count("bear", False)
    b = ElliottBook()
    b.add(bull, at(32))
    b.add(bear, at(32))
    assert b.decide(at(33), 205, bull.claim) is None
    assert len(b.counts) == 2


def test_elliott_child_invalidation_propagates_and_cannot_resurrect():
    c = elliott_count()
    b = ElliottBook()
    b.add(c, at(32))
    b.invalidate_wave(c.correction.wave_id)
    assert b.decide(at(33), 205, c.claim) is None
    with pytest.raises(ContractError, match="NO_RESURRECTION"):
        b.add(c, at(34))


def test_elliott_wrong_parent_endpoint_or_no_child_proof_rejected():
    c = elliott_count()
    with pytest.raises(ContractError, match="NAMED_PARENT"):
        replace(c, parent_end=replace(c.parent_end, price=161)).validate(at(32))
    with pytest.raises(ContractError, match="SUBDIVISION"):
        replace(c, parent_prefix=replace(c.parent_prefix, children=())).validate(at(32))


def wyckoff(reaccum=False):
    sid = "new-range"
    branch = "REACCUMULATION" if reaccum else "ACCUMULATION"
    cause = RangeCause(
        sid,
        at(48),
        100.0,
        120.0,
        "1H",
        k("RANGE", 48, sid),
        branch,
        k("MARKUP", 24, "old-range") if reaccum else None,
    )
    bars = []
    for i in range(16):
        close = 100.0 * 1.01 ** (0 if i % 2 == 0 else 18)
        bars.append(bar(48 + i, close, close + 0.1, close - 0.1, close))
    segments = (Segment("whole", at(48), at(64), at(64), sid),)
    lps = ActivityBar(bar(72, 122, 124, 118, 123), 80)
    events = (
        (k("NEW_RANGE_SUPPLY_TEST", 60, sid, "retest"),)
        if reaccum
        else tuple(
            k(v, 50 + i * 3, sid, v)
            for i, v in enumerate(("PS", "SC", "ST", "DOWNSIDE_OBJECTIVE_MET"))
        )
    )
    ready = Readiness(
        sid,
        (pt(150, 0, "H"), pt(140, 24, "H")),
        (pt(101, 48, "L"), pt(118, 52, "H"), pt(105, 56, "L"), pt(119, 60, "H")),
        ActivityBar(bar(64, 110, 119, 107, 109), 100),
        ActivityBar(bar(66, 110, 111, 108, 110), 50),
        ActivityBar(bar(68, 118, 125, 117, 123), 200),
        lps,
        k("UP", 60, "market"),
        k(1.1, 60, sid, "rs"),
        events,
    )
    line = k(118.0, 73, sid, "lps-line")
    return cause, bars, segments, ready, line


@pytest.mark.parametrize("reaccum", [False, True])
def test_wyckoff_new_cause_full_readiness_and_count_line(reaccum):
    cause, bars, segs, ready, line = wyckoff(reaccum)
    assert all(ready.evaluate(cause, at(73)).values())
    result = pnf_cause(cause, bars, segs, line, at(73))
    assert result["count"] > 0 and result["minimum_objective"] > 150
    m = WyckoffContract(cause)
    branch = "REACCUMULATION_LPS" if reaccum else "NO_SPRING_LPS"
    t = m.intent(at(73), 123, ready, bars, segs, line, branch)
    assert t and t.mode == "TREND_CHECKPOINTS"
    assert "NOT_TAKE_PROFIT" in t.management_rule
    with pytest.raises(ContractError, match="REUSE"):
        m.intent(at(73), 123, ready, bars, segs, line, branch)


def test_wyckoff_historical_range_cannot_pass_fresh_readiness():
    c, bs, ss, r, ln = wyckoff(True)
    with pytest.raises(ContractError, match="OTHER_CAUSE"):
        replace(r, cause_id="old-range").evaluate(c, at(73))
    with pytest.raises(ContractError, match="OTHER_STRUCTURE"):
        pnf_cause(c, bs, ss, replace(ln, structure_id="old-range"), at(73))
    with pytest.raises(ContractError, match="STALE_LPS"):
        r.evaluate(c, at(74))


def test_wyckoff_missing_segment_and_future_bar_fail_closed():
    c, bs, ss, r, ln = wyckoff()
    with pytest.raises(ContractError, match="COVERAGE"):
        pnf_cause(c, bs[1:], ss, ln, at(73))
    with pytest.raises(ContractError, match="FUTURE"):
        pnf_cause(c, bs + [bar(74, 110, 111, 109, 110)], ss, ln, at(73))


def test_wyckoff_spring_50_then_lps_same_campaign():
    c, bs, ss, r, ln = wyckoff()
    stage = SpringStage(
        c.cause_id,
        ActivityBar(bar(65, 101, 104, 99, 102), 100),
        ActivityBar(bar(67, 102, 103, 100, 102), 50),
        ActivityBar(bar(69, 102, 105, 101, 104), 60),
        r.market,
        r.rs,
        r.branch_events,
    )
    m = WyckoffContract(c)
    spring_line = k(100.0, 70, c.cause_id, "spring-line")
    with pytest.raises(ContractError, match="COUNT_LINE_NOT_THIS_SPRING_TEST"):
        m.spring_intent(at(70), 104, stage, bs, ss, replace(spring_line, value=108.0))
    assert m.spring_intent(at(70), 104, stage, bs, ss, spring_line)
    add = m.lps_add(at(73), 123, r, bs, ss, ln)
    assert add["remaining_initial_fraction"] == 0.5
    assert add["campaign_initial_risk_budget_must_not_increase"]
    with pytest.raises(ContractError, match="DUPLICATE"):
        m.lps_add(at(73), 123, r, bs, ss, ln)


def ict():
    return AuctionChain(
        "s",
        k(100.0, 0, name="liquidity"),
        bar(1, 102, 104, 98, 102),
        bar(3, 102, 110, 101, 109),
        k(105.0, 2, name="internal"),
        k((103.0, 105.0), 4, name="fvg"),
        bar(5, 107, 108, 104, 107),
        k(125.0, 0, name="target"),
        k(at(16), 0, name="session"),
    )


def htf():
    return bind_entry(
        ict(),
        at(8),
        108,
        TREND,
        daily=k("UP", 0, "market"),
        acceptance=bar(4, 103, 110, 102, 109, "4H"),
        protected=k(99.0, 0, name="protected"),
    )


def test_ict_native_session_exit_vs_htf_diagnostic_ownership():
    session = bind_entry(ict(), at(6), 108, SESSION)
    sm = OwnedCampaign(session, at(6), 108, at(16))
    tm = OwnedCampaign(htf(), at(8), 108, at(16))
    assert tm.on_owner_close(bar(8, 108, 112, 105, 110, "4H")).action == "HOLD"
    ev = k("NY16", 16, name="ny-close")
    assert sm.on_event(ev) == "EXIT_NEXT_OPEN"
    assert tm.on_event(ev) == "DIAGNOSTIC_ONLY_OWNER_UNCHANGED"


def test_ict_same_bar_fvg_creation_retrace_rejected():
    c = ict()
    with pytest.raises(ContractError, match="LATER"):
        replace(c, retracement=c.mss).validate(at(8))


def test_h2_two_owner_closes_failed_reclaim_not_internal_mss():
    m = OwnedCampaign(htf(), at(8), 108, at(16))
    assert m.on_owner_close(bar(8, 105, 110, 100, 105, "4H")).action == "HOLD"
    assert m.on_event(k("BEARISH_MSS", 12, name="noise")) == "DIAGNOSTIC_ONLY_OWNER_UNCHANGED"
    assert m.on_owner_close(bar(12, 101, 104, 96, 98, "4H")).action == "HOLD"
    assert m.on_owner_close(bar(16, 98, 100, 95, 97, "4H")).action == "EXIT_NEXT_OPEN"


def test_h2_owner_conversion_and_future_context_rejected():
    m = OwnedCampaign(htf(), at(8), 108, at(16))
    m.thesis = replace(m.thesis, owner="ICT_SESSION")
    with pytest.raises(ContractError, match="CONVERSION"):
        m.on_event(k("NY16", 16))
    with pytest.raises(ContractError, match="CAUSAL"):
        bind_entry(
            ict(),
            at(8),
            108,
            TREND,
            daily=k("UP", 9, "market"),
            acceptance=bar(4, 103, 110, 102, 109, "4H"),
            protected=k(99.0, 0),
        )


@pytest.mark.parametrize("year", [2024, 2025])
def test_all_contracts_protected_clock(year):
    with pytest.raises(ContractError, match="PROTECTED"):
        clock(datetime(year, 1, 1, tzinfo=UTC))


def test_common_pivots_two_right_closes_and_price_geometry():
    with pytest.raises(ContractError, match="TWO_RIGHT"):
        replace(pt(100, 0, "L"), available_at=at(1)).validate(at(3))
    with pytest.raises(ContractError, match="ALTERNATING"):
        validate_points((pt(110, 0, "L"), pt(100, 3, "H")), at(6))


def leaf(kind, start=100.0, end=200.0, h=0, span=12, degree="1H", name="leaf"):
    fractions = {
        "IMPULSE": (0.0, 0.3, 0.2, 0.75, 0.6, 1.0),
        "ZIGZAG": (0.0, 0.7, 0.3, 1.0),
        "FLAT": (0.0, 0.5, 0.0, 1.0),
        "DOUBLE_THREE": (0.0, 0.7, 0.3, 1.0),
        "TRIPLE_THREE": (0.0, 0.4, 0.2, 0.7, 0.5, 1.0),
    }
    if kind == "TRIANGLE":
        values = (200.0, 100.0, 180.0, 120.0, 160.0, 140.0)
    else:
        values = tuple(start + f * (end - start) for f in fractions[kind])
    first = "L" if values[1] > values[0] else "H"
    n = len(values) - 1
    times = [h + int(span * i / n) for i in range(n + 1)]
    # Use 4H-aligned endpoints and spacing for parent recursive proofs.
    if degree == "4H":
        times = [h + i * 32 for i in range(n + 1)]
    points = tuple(
        pt(v, t, first if i % 2 == 0 else ("H" if first == "L" else "L"), degree, f"{name}{i}")
        for i, (v, t) in enumerate(zip(values, times, strict=True))
    )
    if degree == "1H":
        return Wave(name, kind, degree, points, (), SHA)
    roles = {
        "IMPULSE": ("IMPULSE", "ZIGZAG", "IMPULSE", "ZIGZAG", "IMPULSE"),
        "ZIGZAG": ("IMPULSE", "ZIGZAG", "IMPULSE"),
        "FLAT": ("ZIGZAG", "ZIGZAG", "IMPULSE"),
    }.get(kind, ("ZIGZAG",) * n)
    children = tuple(
        leaf(role, a.price, b.price, times[i], times[i + 1] - times[i], name=f"{name}child{i}")
        for i, (a, b, role) in enumerate(zip(points[:-1], points[1:], roles, strict=True))
    )
    return Wave(name, kind, degree, points, children, SHA)


@pytest.mark.parametrize(
    "kind", ["IMPULSE", "ZIGZAG", "FLAT", "TRIANGLE", "DOUBLE_THREE", "TRIPLE_THREE"]
)
def test_every_elliott_grammar_recursive_named_subdivision(kind):
    w = leaf(kind, degree="4H")
    w.validate(at(200))
    with pytest.raises(ContractError, match="SUBDIVISION"):
        replace(w, children=()).validate(at(200))
    wrong = replace(w.children[0], degree="4H")
    with pytest.raises(ContractError):
        replace(w, children=(wrong, *w.children[1:])).validate(at(200))


@pytest.mark.parametrize("kind", ["IMPULSE", "ZIGZAG", "FLAT", "TRIANGLE"])
def test_minor_degree_leaf_is_explicit_bounded_profile(kind):
    leaf(kind).validate(at(32))


def test_elliott_wave3_shortest_and_wave4_overlap_are_not_votes():
    w = leaf("IMPULSE")
    overlap = replace(w.points[4], price=125.0)
    with pytest.raises(ContractError, match="OVERLAP"):
        replace(w, points=(*w.points[:4], overlap, w.points[5])).validate(at(32))
    vals = (100, 150, 140, 170, 160, 220)
    bad = tuple(replace(p, price=v) for p, v in zip(w.points, vals, strict=True))
    with pytest.raises(ContractError, match="THREE_SHORTEST"):
        replace(w, points=bad).validate(at(32))


def test_elliott_source_count_mutation_is_rejected():
    c = elliott_count()
    b = ElliottBook()
    b.add(c, at(32))
    with pytest.raises(ContractError, match="MUTATED"):
        b.add(replace(c, objective=k(260.0, 32, "parent")), at(32))


@pytest.mark.parametrize("failure", ["rs", "market", "supply", "demand", "lps"])
def test_wyckoff_each_numeric_readiness_gate_can_block(failure):
    c, bs, ss, r, ln = wyckoff()
    if failure == "rs":
        r = replace(r, rs=k(0.9, 60, c.cause_id))
    elif failure == "market":
        r = replace(r, market=k("DOWN", 60, "market"))
    elif failure == "supply":
        r = replace(r, supply_test=replace(r.supply_test, volume=200.0))
    elif failure == "demand":
        r = replace(r, sos=replace(r.sos, volume=30.0))
    else:
        r = replace(r, lps=replace(r.lps, volume=300.0))
    assert WyckoffContract(c).intent(at(73), 123, r, bs, ss, ln) is None


def test_wyckoff_readiness_booleans_cannot_replace_causal_activity():
    c, bs, ss, r, ln = wyckoff()
    with pytest.raises(ContractError, match="TYPED_READINESS"):
        WyckoffContract(c).intent(at(73), 123, {"all": True}, bs, ss, ln)


def test_wyckoff_whole_segment_ownership_and_log_target_identity():
    c, bs, ss, r, ln = wyckoff()
    a = pnf_cause(c, bs, ss, ln, at(73))
    assert a["minimum_objective"] == pytest.approx(100 * 1.01 ** (3 * a["count"]))
    with pytest.raises(ContractError, match="OWNERSHIP"):
        pnf_cause(c, bs, (replace(ss[0], cause_id="old"),), ln, at(73))
    with pytest.raises(ContractError, match="OWNERSHIP"):
        pnf_cause(c, bs, (replace(ss[0], available_at=at(74)),), ln, at(73))
    m = WyckoffContract(c)
    m.invalidate()
    with pytest.raises(ContractError, match="NO_RESURRECTION"):
        m.intent(at(73), 123, r, bs, ss, ln)


def test_harmonic_owner_and_frozen_projection_cannot_mutate():
    p = harmonic("ABCD")
    m = HarmonicContract(p)
    m.projection = replace(p, family="BAT")
    with pytest.raises(ContractError, match="OWNER_MUTATED"):
        m.on_close(bar(12, 211, 212, 209.9, 211))


def test_harmonic_stop_and_terminal_invalidation_absorbing():
    p = harmonic("GARTLEY")
    m = HarmonicContract(p)
    m.on_close(bar(12, 211, 250, 199, 211))
    assert m.state == "INVALIDATED"
    with pytest.raises(ContractError, match="NO_RESURRECTION"):
        m.on_close(bar(13, 211, 251, 210, 250))


def test_h2_stop_ratcheting_does_not_apply_to_formation_bar():
    m = OwnedCampaign(htf(), at(8), 108, at(16))
    raw = [
        ("l0", "L", 105, 8),
        ("h0", "H", 112, 12),
        ("l1", "L", 108, 16),
        ("h1", "H", 118, 20),
        ("l2", "L", 115, 24),
        ("h2", "H", 125, 28),
    ]
    pivots = tuple(Pivot(i, "s", kind, val, at(h), at(h + 8)) for i, kind, val, h in raw)
    for h in range(8, 36):
        if (h + 1) % 4 == 0:
            end = h + 1
            ps = tuple(p for p in pivots if p.available_at <= at(end))
            c = 126 if end == 36 else 120 if end >= 28 else 110
            m.on_owner_close(bar(end - 4, c, c + 2, 104, c, "4H"), ps)
        # Even when owner-close comes first, current hourly bar sees prior stop.
        assert m.on_execution_bar(bar(h, 110, 130, 104, 110)) == "HOLD"
    assert m.manager.protected_low == 115
    assert m.manager.hard_stop == 108
    assert m.on_execution_bar(bar(36, 110, 115, 104, 110)).startswith("HARD_STOP")


def test_ict_pending_exit_is_not_resurrected_by_later_close():
    t = bind_entry(ict(), at(6), 108, SESSION)
    m = OwnedCampaign(t, at(6), 108, at(16))
    assert m.on_event(k("BEARISH_MSS", 6, name="exit-event")) == "EXIT_NEXT_OPEN"
    assert m.on_execution_bar(bar(6, 108, 110, 107, 109)) == "PENDING_EXIT_EXECUTION_REQUIRED"
    m.mark_closed()
    with pytest.raises(ContractError, match="RESURRECTION"):
        m.on_execution_bar(bar(7, 109, 111, 108, 110))


def test_next_open_never_same_bar_or_late_entry():
    t = bind_entry(ict(), at(6), 108, SESSION)
    t.executable_at(at(6), at(6), 108)
    with pytest.raises(ContractError, match="SAME_BAR"):
        t.executable_at(at(5), at(6), 108)
    with pytest.raises(ContractError, match="NEXT_HOURLY"):
        t.executable_at(at(7), at(6), 108)


def test_prefix_harmonic_decision_cannot_depend_on_later_unseen_bars():
    p = harmonic("ABCD")
    a, b = HarmonicContract(p), HarmonicContract(p)
    prefix = [bar(12, 211, 212, 209.9, 211), bar(13, 211, 214, 210, 213)]
    out_a = [a.on_close(x) for x in prefix]
    out_b = [b.on_close(x) for x in prefix]
    assert out_a == out_b
    a.on_close(bar(14, 213, 1000, 1, 500))
    b.on_close(bar(14, 213, 215, 210, 214))
    assert out_a[1] == out_b[1]


@pytest.mark.parametrize("leg", ["W4", "ABC"])
def test_elliott_w4_and_completed_motive_parent_not_just_w2(leg):
    vals = (100, 130, 120, 175) if leg == "W4" else (100, 130, 120, 175, 160, 200)
    points = tuple(
        pt(v, i * 12, "L" if i % 2 == 0 else "H", "4H", f"parent{i}") for i, v in enumerate(vals)
    )
    children = tuple(
        leaf("IMPULSE" if i % 2 == 0 else "ZIGZAG", a.price, b.price, i * 12, name=f"child{i}")
        for i, (a, b) in enumerate(zip(points[:-1], points[1:], strict=True))
    )
    h = (len(vals) - 1) * 12
    cor = leaf("ZIGZAG", vals[-1], vals[-1] - 30, h, name="correction")
    end = pt(vals[-1] - 30, h + 12, "L", "4H", "parent-end")
    prefix = ParentPrefix("parent", "4H", points, children)
    stop = vals[1] if leg == "W4" else vals[0]
    c = ResumeCount(
        "count", "parent", "4H", leg, points[-1], end, cor, stop, k(250.0, h + 20, "parent"), prefix
    )
    c.validate(at(h + 20))
    b = ElliottBook()
    b.add(c, at(h + 20))
    assert b.decide(at(h + 21), vals[-1] + 1, c.claim)


def test_elliott_nan_and_parent_invalidation_outside_all_child_prices_rejected():
    b = ElliottBook()
    c = elliott_count()
    b.add(c, at(32))
    with pytest.raises(ContractError, match="POSITIVE"):
        b.decide(at(33), float("nan"), c.claim)
    with pytest.raises(ContractError, match="PARENT_INVALIDATION"):
        replace(c, invalidation=90).validate(at(32))


def test_expired_context_and_source_sha_required():
    with pytest.raises(ContractError, match="EXPIRED"):
        k("UP", 0, until=8).validate(at(8))
    with pytest.raises(ContractError, match="SHA"):
        replace(k("UP", 0), source_sha256="not-a-hash").validate(at(8))


def test_h2_context_reversal_not_session_event_owns_exit():
    m = OwnedCampaign(htf(), at(8), 108, at(16))
    assert m.on_event(k("CONFIRMED_1D_DOWN", 12, name="daily")) == "EXIT_NEXT_OPEN"
    assert m.on_event(k("NY16", 16, name="session-end")) == "PENDING_EXIT_EXECUTION_REQUIRED"


def test_wyckoff_lps_cannot_relabel_count_line_and_reaccumulation_cannot_reuse_cause():
    c, bs, ss, r, ln = wyckoff()
    with pytest.raises(ContractError, match="COUNT_LINE_NOT_THIS_LPS"):
        WyckoffContract(c).intent(at(73), 123, r, bs, ss, replace(ln, value=110))
    rc, *_ = wyckoff(True)
    with pytest.raises(ContractError, match="NEW_CAUSE"):
        replace(rc, prior_markup=k("MARKUP", 24, rc.cause_id)).validate(at(73))


def test_h2_session_target_not_forced_take_profit_of_trend_campaign():
    m = OwnedCampaign(htf(), at(8), 108, at(16))
    assert m.on_execution_bar(bar(8, 108, 150, 107, 140)) == "HOLD"


def test_harmonic_projection_complement_fixed_before_d_and_no_convergence_fails():
    p = harmonic("GARTLEY")
    with pytest.raises(ContractError, match="CONVERGENCE"):
        project(p.family, p.points, at(12), k(0.1, 12), 0.01)
    assert p.levels == harmonic("GARTLEY").levels


def test_clock_noncanonical_bars_do_not_silently_shift_htf_boundaries():
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import completed

    with pytest.raises(ContractError, match="BOUNDARY"):
        completed(bar(1, 100, 110, 99, 105, "4H"), at(5), "4H")


def test_elliott_last_internal_high_not_original_start_high():
    c = elliott_count()
    b = ElliottBook()
    b.add(c, at(32))
    assert b.decide(at(32), 190.0, c.claim) is None  # same parent confirmation checkpoint
    assert b.decide(at(33), 190.0, c.claim)  # 185 internal high; not 200 origin high


def test_elliott_future_objective_or_child_evidence_cannot_be_prefix_certified():
    c = elliott_count()
    with pytest.raises(ContractError, match="CAUSAL"):
        replace(c, objective=k(250.0, 33, "parent")).validate(at(32))
    future = replace(c.correction.points[-1], available_at=at(33))
    with pytest.raises(ContractError, match="CAUSAL_CLOCK"):
        replace(
            c, correction=replace(c.correction, points=(*c.correction.points[:-1], future))
        ).validate(at(32))


def test_ict_execution_stream_missing_bar_and_repeated_event_fail_closed():
    m = OwnedCampaign(htf(), at(8), 108, at(16))
    with pytest.raises(ContractError, match="COVERAGE_GAP"):
        m.on_execution_bar(bar(9, 108, 109, 107, 108))
    ev = k("BEARISH_MSS", 10, name="noise")
    assert m.on_event(ev).startswith("DIAGNOSTIC")
    with pytest.raises(ContractError, match="REPEATED"):
        m.on_event(ev)


def test_wyckoff_missing_branch_readiness_not_invented_and_no_new_risk_budget():
    c, bs, ss, r, ln = wyckoff(True)
    with pytest.raises(ContractError, match="BRANCH_APPLICABLE"):
        replace(r, branch_events=()).evaluate(c, at(73))
    m = WyckoffContract(c)
    m.cause = replace(c, resistance=125.0)
    with pytest.raises(ContractError, match="OWNER_MUTATED"):
        m.intent(at(73), 123, r, bs, ss, ln, "REACCUMULATION_LPS")
