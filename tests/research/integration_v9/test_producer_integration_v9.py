"""Synthetic source, graph, kernel integration; never reads a market dataset."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as native
from spotbot.research.multi_school_fidelity import full_replay_v5 as v5
from spotbot.research.multi_school_fidelity.akah_thesis_engine_foundation_v1 import (
    Activity,
    Direction,
    RouterState,
    StructuralPhase,
)
from spotbot.research.multi_school_fidelity.campaign_execution_v7 import AddEvidence
from spotbot.research.multi_school_fidelity.elliott_contract_v8 import (
    ParentPrefix,
    ResumeCount,
    Wave,
)
from spotbot.research.multi_school_fidelity.ict_h2_contract_v8 import SESSION, TREND, AuctionChain
from spotbot.research.multi_school_fidelity.integration_v9.execution import (
    PROFILES,
    ContractBinding,
    ExecutionV9,
    NativeFailureV9,
)
from spotbot.research.multi_school_fidelity.integration_v9.pipeline import (
    PHASES,
    PipelineV9,
    RouterV9,
)
from spotbot.research.multi_school_fidelity.integration_v9.producers import (
    ELLIOTT,
    H3,
    HARMONIC,
    WYCKOFF,
    ContractProducer,
)
from spotbot.research.multi_school_fidelity.integration_v9.sources import (
    CompletedPrefix,
    SourceGraph,
    aggregate_completed,
    live_market_observations,
)
from spotbot.research.multi_school_fidelity.live_dow_context_v7 import KnownObservation
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Known, SchoolThesis
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import (
    CompletedBar,
    ContractError,
    Mode,
    Objective,
)
from spotbot.research.multi_school_fidelity.wyckoff_contract_v8 import (
    ActivityBar,
    RangeCause,
    Readiness,
    Segment,
)

T = datetime(2023, 1, 1, tzinfo=UTC)
SHA = "a" * 64
PAIR = "X-USDT"


def at(h):
    return T + timedelta(hours=h)


def bar(h, o=105, high=110, low=100, close=106, degree="1H"):
    step = {"1H": 1, "4H": 4, "1D": 24}[degree]
    return CompletedBar(at(h), at(h + step), degree, o, high, low, close)


def state(phase=StructuralPhase.BASE_CANDIDATE):
    return RouterState(Direction.UP, Direction.UP, phase, Activity.NORMAL)


def kernel():
    return ExecutionV9(v5.Portfolio(0.005, {PAIR: v5.ContinuousRule(PAIR, SHA)}))


def thesis(
    grammar=SESSION,
    owner=None,
    degree=None,
    when=0,
    stop=90,
    goals=(130,),
    mode=None,
    rule="OWNER_STRUCTURE",
):
    owners, expected = PROFILES[grammar]
    owner = owner or sorted(owners)[0]
    return SchoolThesis(
        grammar,
        owner,
        "s",
        at(when),
        degree or ("4H" if grammar == TREND else "1H"),
        "LONG",
        stop,
        goals,
        mode or expected,
        SHA,
        ("parent",),
        rule,
        "SYNTHETIC",
    )


def binding(t):
    return ContractBinding(
        t.grammar,
        t.owner,
        t.structure_id,
        t.source_sha256,
        t.management_degree,
        t.available_at,
        t.initial_invalidation,
        "parent",
        t,
    )


def row(t):
    return dict(
        identity="intent",
        pair=PAIR,
        owner_grammar=t.grammar,
        owner_structure_id=t.structure_id,
        pit_eligible=True,
        session_end=at(3),
    )


def admit(e, t, **kwargs):
    b = binding(t)
    goals = tuple(
        Objective(f"goal{i}", "s", p, "CONFIRMED_RESISTANCE", t.available_at, SHA)
        for i, p in enumerate(t.objectives)
    )
    return e.admit_owned(
        row(t),
        b,
        t.available_at,
        105,
        100000,
        "s",
        research_authorized=True,
        mode=Mode.FINITE if t.mode == "FINITE_REACTION" else Mode.TREND,
        objectives=goals,
        **kwargs,
    )


def test_native_pivots_same_geometry_but_close_clock_two_right_bars():
    prefix = CompletedPrefix(PAIR, SHA)
    bars = [
        bar(i, high=h, low=lo)
        for i, (h, lo) in enumerate([(110, 100), (111, 101), (120, 102), (113, 101), (112, 100)])
    ]
    for b in bars[:-1]:
        assert not prefix.on_close(b, 1, b.end)
    points = prefix.on_close(bars[-1], 1, bars[-1].end)
    expected = native.confirmed_pivots_2l2r(
        pd.DataFrame([dict(timestamp=b.start, high=b.high, low=b.low) for b in bars])
    )
    assert [(p.kind, p.price) for p in points] == [(p.kind, p.price) for p in expected]
    assert points[0].observed_at == at(3) and points[0].available_at == at(5)
    assert prefix.graph.live(points[0].event_id, at(5))
    assert not prefix.graph.live(points[0].event_id, at(4))


@pytest.mark.parametrize("degree", ["1H", "4H", "1D"])
def test_prefix_rejects_duplicate_gap_future_misalignment_without_mutation(degree):
    p = CompletedPrefix(PAIR, SHA)
    b = bar(0, degree=degree)
    p.on_close(b, 1, b.end)
    saved = len(p.graph.nodes)
    for bad, now in [(b, b.end), (bar(48, degree=degree), at(48) + (b.end - b.start))]:
        with pytest.raises(ContractError, match="PREFIX"):
            p.on_close(bad, 1, now)
    with pytest.raises(ContractError):
        p.on_close(bar(0, degree=degree), 1, at(0))
    assert len(p.graph.nodes) == saved


@pytest.mark.parametrize("year", [2024, 2025])
def test_protected_bar_not_opened_or_added(year):
    p = CompletedPrefix(PAIR, SHA)
    b = replace(
        bar(0), start=datetime(year, 1, 1, tzinfo=UTC), end=datetime(year, 1, 1, 1, tzinfo=UTC)
    )
    with pytest.raises(ContractError, match="PROTECTED"):
        p.on_close(b, 1, b.end)
    assert not p.graph.nodes


def test_aggregate_is_complete_canonical_bucket():
    hs = [bar(i) for i in range(4)]
    assert aggregate_completed(hs, "4H", at(4)) == bar(0, degree="4H")
    with pytest.raises(ContractError, match="INCOMPLETE"):
        aggregate_completed(hs[:-1], "4H", at(4))
    with pytest.raises(ContractError):
        aggregate_completed([bar(i) for i in range(1, 5)], "4H", at(5))


def test_source_graph_invalidation_cascades_and_no_resurrection():
    g = SourceGraph()
    a = g.register(Known("a", 1, at(0), SHA, "s"), origin="DETECTOR_GEOMETRY")
    g.register(Known("b", 2, at(1), SHA, "s"), ("a",), origin="DETECTOR_GEOMETRY")
    assert g.live("b", at(1))
    g.terminate("a")
    assert not g.live("b", at(1))
    with pytest.raises(ContractError):
        g.register(a, origin="DETECTOR_GEOMETRY")


def test_current_bar_mutation_cannot_change_completed_prefix_points():
    p = CompletedPrefix(PAIR, SHA)
    for i in range(5):
        b = bar(i, high=120 if i == 2 else 110)
        p.on_close(b, 1, b.end)
    original = dict(p.points)
    with pytest.raises(ContractError):
        p.on_close(bar(5, high=999, low=1, close=500), 999, at(5))
    assert original == p.points


def harmonic_source():
    p = CompletedPrefix(PAIR, SHA)
    # Actual detector output: L200 H300 L240 H270 with two-right completeness.
    values = [220, 210, 201, 230, 260, 280, 299, 280, 260, 250, 241, 250, 260, 265, 269, 260, 250]
    for i, v in enumerate(values):
        low, hi = v - 1, v + 1
        b = bar(i, v, hi, low, v)
        p.on_close(b, 1, b.end)
    ps = tuple(sorted(p.points.values(), key=lambda x: x.observed_at))
    assert [q.price for q in ps] == [200, 300, 240, 270]
    c = ContractProducer(p)
    atr = p.atr("1H", "projection", at(17))
    sid = c.start_harmonic("ABCD", ps, atr, 0.01, at(17))
    b = bar(17, 211, 212, 209.9, 211)
    p.on_close(b, 1, b.end)
    assert c.harmonic_close(sid, b, pit_eligible=True) is None
    b = bar(18, 211, 214, 210, 213)
    p.on_close(b, 1, b.end)
    produced = c.harmonic_close(sid, b, pit_eligible=True)
    assert produced.thesis.owner == "HARMONIC_TYPE_I"
    return p, c, sid, produced


def context(p, now, phase=StructuralPhase.BASE_CANDIDATE):
    st = state(phase)
    parent = p.bar_id(p.bars["1H"][-1])
    return p.source_claim("router" + str(now), st, now, "market", (parent,), SHA)


def test_actual_harmonic_detector_to_contract_router_kernel_partial_cash():
    p, c, sid, produced = harmonic_source()
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(produced, p, state(), context(p, at(19)))
    selected, denied = pipe.on_open(
        at(19), {PAIR: 213}, {PAIR: 100000}, (env,), research_authorized=True
    )
    assert selected and not denied
    q = e.portfolio.k.positions[1]["qty_current"]
    assert e.managers[1].binding.owner == "HARMONIC_TYPE_I"
    first_goal = produced.thesis.objectives[0]
    pipe.on_completed_hour(
        {PAIR: bar(19, 213, first_goal + 1, 212, first_goal + 0.5)}, capacities={PAIR: 100000}
    )
    assert e.partial[1].first_sold == pytest.approx(q / 2)
    assert e.portfolio.k.positions[1]["qty_current"] == pytest.approx(q / 2)
    # Cash breakeven may lie BELOW existing protection after half realization.
    assert e.managers[1].hard_stop >= produced.thesis.initial_invalidation
    assert not produced.thesis.manifest()["funded_ready"]


def test_source_invalidated_between_intent_and_open_no_fill():
    p, _, _, produced = harmonic_source()
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(produced, p, state(), context(p, at(19)))
    p.graph.terminate(produced.evidence_ids[0])
    _, denied = pipe.on_open(at(19), {PAIR: 213}, {PAIR: 100000}, (env,), research_authorized=True)
    assert denied[env.row["identity"]] == "SOURCE_PARENT_INVALIDATED_BEFORE_EXECUTION"
    assert not e.portfolio.k.fills


def test_real_mode_stays_unfunded_without_independent_and_quantity_authority():
    p, _, _, produced = harmonic_source()
    e = kernel()
    pipe = PipelineV9(e, RouterV9())
    env = pipe.bind(produced, p, state(), context(p, at(19)))
    _, denied = pipe.on_open(at(19), {PAIR: 213}, {PAIR: 100000}, (env,), research_authorized=True)
    assert denied[env.row["identity"]] == "HISTORICAL_QUANTITY_AUTHORITY_REQUIRED"
    assert not e.portfolio.k.fills
    assert "INDEPENDENT" in pipe.router.permission(HARMONIC, state())[1]


@pytest.mark.parametrize("grammar", list(PROFILES))
def test_all_new_profiles_preserve_distinct_owner_kernel_admission(grammar):
    e = kernel()
    t = thesis(grammar)
    assert admit(e, t)[0]
    assert e.managers[1].binding.grammar == grammar
    assert e.managers[1].binding.owner == t.owner
    assert e.portfolio.k.positions[1]["episode"]["owner_grammar"] == grammar


@pytest.mark.parametrize("grammar", list(PROFILES))
def test_wrong_owner_or_mode_cannot_alias_old_grammar(grammar):
    e = kernel()
    with pytest.raises(ContractError):
        admit(e, replace(thesis(grammar), owner="FS_ICT_2022_CORE_CRYPTO_LONG"))
    assert not e.portfolio.k.fills


def test_native_session_automatic_exit_next_open_not_silently_disabled():
    e = kernel()
    assert admit(e, thesis())[0]
    for i in range(3):
        e.on_completed_hour(1, bar(i), {PAIR: 100000})
    assert 1 in e.pending
    e.on_open(at(3), {PAIR: 106}, {PAIR: 100000})
    assert not e.portfolio.k.positions
    assert "NY16" in e.portfolio.k.fills[-1]["reason"]


def test_h2_target_is_checkpoint_and_session_is_not_its_owner():
    e = kernel()
    assert admit(e, thesis(TREND, goals=(107,)))[0]
    e.on_completed_hour(1, bar(0, high=140), {PAIR: 100000})
    assert e.portfolio.k.positions
    assert e.managers[1].finite_objective is None
    f = NativeFailureV9("bad", "H2_4H_STRUCTURE", "s", "NY16", at(1), SHA)
    with pytest.raises(ContractError):
        e.preview_close(1, bar(1), native_failure=f)
    assert e.portfolio.k.positions


@pytest.mark.parametrize("grammar", list(PROFILES))
def test_gap_stop_actual_open_price_and_samebar_target_collision(grammar):
    e = kernel()
    assert admit(e, thesis(grammar))[0]
    e.on_completed_hour(1, bar(0, 85, 140, 80, 100), {PAIR: 100000})
    assert not e.portfolio.k.positions
    assert e.portfolio.k.fills[-1]["price"] == 85
    assert e.portfolio.k.fills[-1]["reason"] == "HARD_STOP_GAP"


def test_new_wyckoff_staging_reuses_original_kernel_risk_budget():
    e = kernel()
    t = thesis(WYCKOFF, rule="STAGE_50_PERCENT_SPRING_THEN_LPS_ADD_WITHIN_SAME_RISK_BUDGET")
    assert admit(e, t, staged=True)[0]
    first = e.portfolio.k.positions[1]["qty_current"]
    before = e.portfolio.k.campaigns["s"].initial_risk_budget
    e.on_completed_hour(1, bar(0), {PAIR: 100000})
    evidence = AddEvidence("lps", "s", at(1), 95, SHA)
    assert e.admit_owned(
        row(t),
        binding(t),
        at(1),
        105,
        100000,
        "s",
        research_authorized=True,
        mode=Mode.TREND,
        add_evidence=evidence,
    )[0]
    assert len(e.portfolio.k.positions) == 2
    assert e.managers[1].hard_stop == 95
    assert e.portfolio.k.campaigns["s"].initial_risk_budget == before
    assert e.portfolio.k.positions[2]["qty_current"] > 0 and first > 0
    with pytest.raises(ContractError):
        e.admit_owned(
            row(t),
            binding(t),
            at(1),
            105,
            100000,
            "s",
            research_authorized=True,
            mode=Mode.TREND,
            add_evidence=evidence,
        )


@pytest.mark.parametrize("grammar", list(PHASES))
def test_router_never_self_certifies_gate2(grammar):
    phase = sorted(PHASES[grammar], key=str)[0]
    assert not RouterV9().permission(grammar, state(phase))[0]
    assert RouterV9(synthetic_fixture_execution=True).permission(grammar, state(phase))[0]
    down = replace(state(phase), market_direction_1d=Direction.DOWN)
    assert not RouterV9(synthetic_fixture_execution=True).permission(grammar, down)[0]


def test_source_event_row_mutation_before_fill_fails_without_trade():
    p, _, _, produced = harmonic_source()
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(produced, p, state(), context(p, at(19)))
    env.row["pair"] = "Y-USDT"
    with pytest.raises(ContractError, match="IMMUTABLE"):
        pipe.on_open(at(19), {PAIR: 213}, {PAIR: 100000}, (env,), research_authorized=True)
    assert not e.portfolio.k.fills


def test_fvg_from_actual_completed_three_bar_source_not_claim_label():
    p = CompletedPrefix(PAIR, SHA)
    bs = [bar(0, 100, 102, 99, 101), bar(1, 101, 110, 100, 109), bar(2, 108, 112, 105, 111)]
    for b in bs:
        p.on_close(b, 1, b.end)
    fvg = p.fvg("s", at(3))
    assert fvg.value == (102, 105)
    assert p.graph.nodes[fvg.event_id].origin == "DETECTOR_GEOMETRY"
    assert p.fvg("s", at(3)) == fvg
    with pytest.raises(ContractError):
        p.fvg("s", at(4))


def test_ict_actual_source_chain_to_v8_contract_and_kernel():
    p = CompletedPrefix(PAIR, SHA)
    p.on_close(bar(0, 100, 102, 99, 101), 1, at(1))

    def claim(eid, value, when, parent):
        return p.source_claim(eid, value, at(when), "s", (p.bar_id(parent),), SHA)

    base = p.bars["1H"][0]
    liquidity = claim("liq", 99.5, 1, base)
    internal = claim("internal", 103, 1, base)
    opposing = claim("opp", 130, 1, base)
    endpoint = claim("end", at(8), 1, base)
    raid = bar(1, 101, 102, 98, 101)
    mss = bar(2, 101, 110, 100, 109)
    third = bar(3, 108, 112, 105, 111)
    for b in (raid, mss, third):
        p.on_close(b, 1, b.end)
    fvg = p.fvg("s", at(4))
    retest = bar(4, 110, 111, 103, 110)
    p.on_close(retest, 1, retest.end)
    c = ContractProducer(p)
    chain = AuctionChain("s", liquidity, raid, mss, internal, fvg, retest, opposing, endpoint)
    produced = c.ict_intent(chain, at(5), 110, SESSION, pit_eligible=True)
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(produced, p, state(), context(p, at(5)), session_end=endpoint)
    assert pipe.on_open(at(5), {PAIR: 110}, {PAIR: 100000}, (env,), research_authorized=True)[0]
    assert e.session_ends[1] == at(8)
    bad = replace(chain, fvg=replace(fvg, value=(1, 2)))
    with pytest.raises(ContractError, match="SOURCE"):
        c.ict_intent(bad, at(5), 110, SESSION, pit_eligible=True)


def test_no_unbound_legacy_wave_or_wyckoff_boolean_fabrication():
    c = ContractProducer(CompletedPrefix(PAIR, SHA))
    with pytest.raises(ContractError, match="BAR_NOT"):
        c.elliott_close(bar(0), ("fake",), pit_eligible=True)
    assert not c.elliott.counts and not c.wyckoff


@pytest.mark.parametrize("badkey", ["pnl", "label_end", "outcome", "exit_market_state"])
def test_nested_outcome_payload_rejected(badkey):
    from spotbot.research.multi_school_fidelity.integration_v9.pipeline import _no_outcomes

    with pytest.raises(ContractError, match="OUTCOME"):
        _no_outcomes({"metadata": [{"nested": {badkey: 123}}]})


def elliott_source():
    p = CompletedPrefix(PAIR, SHA)
    anchors = [
        (-16, 116),
        (-8, 108),
        (0, 100),
        (4, 130),
        (8, 120),
        (12, 175),
        (16, 160),
        (24, 200),
        (32, 170),
        (40, 185),
        (48, 160),
        (56, 180),
        (57, 190),
    ]
    hourly = []
    for end in range(-15, 58):
        for (a, va), (b, vb) in zip(anchors[:-1], anchors[1:], strict=True):
            if a < end <= b:
                value = va + (vb - va) * (end - a) / (b - a)
                break
        kinds = {h: ("L" if j % 2 == 0 else "H") for j, (h, _) in enumerate(anchors[2:])}
        kind = kinds.get(end)
        low = value if kind == "L" else value - 0.01
        hi = value if kind == "H" else value + 0.01
        hour = bar(end - 1, value, hi, low, value)
        p.on_close(hour, 1, hour.end)
        hourly.append(hour)
        if end % 4 == 0 and len(hourly) >= 4:
            higher = aggregate_completed(hourly[-4:], "4H", at(end))
            p.on_close(higher, 4, at(end))

    def point(h, degree):
        ps = [q for q in p.points.values() if q.observed_at == at(h) and q.degree == degree]
        assert len(ps) == 1, (h, degree, ps)
        return ps[0]

    motive = Wave(
        "motive", "IMPULSE", "1H", tuple(point(h, "1H") for h in (0, 4, 8, 12, 16, 24)), (), SHA
    )
    correction = Wave(
        "correction", "ZIGZAG", "1H", tuple(point(h, "1H") for h in (24, 32, 40, 48)), (), SHA
    )
    start, end = point(24, "4H"), point(48, "4H")
    prefix = ParentPrefix("parent", "4H", (point(0, "4H"), start), (motive,))
    source = p.source_claim("objective", 250.0, at(56), "parent", (end.event_id,), SHA)
    count = ResumeCount("count", "parent", "4H", "W2", start, end, correction, 100, source, prefix)
    c = ContractProducer(p)
    c.add_elliott_count(count, at(56))
    produced = c.elliott_close(p.bars["1H"][-1], count.claim, pit_eligible=True)
    assert produced and produced.thesis.grammar == ELLIOTT
    return p, c, count, produced


def test_elliott_actual_multi_degree_pivots_recursive_proof_to_kernel():
    p, c, count, produced = elliott_source()
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    st = state(StructuralPhase.MARKUP)
    env = pipe.bind(produced, p, st, context(p, at(57), StructuralPhase.MARKUP))
    assert pipe.on_open(at(57), {PAIR: 190}, {PAIR: 100000}, (env,), research_authorized=True)[0]
    assert e.managers[1].binding.owner == "ELLIOTT_COMMON_COUNT_OWNER"
    assert e.managers[1].finite_objective is None
    p.graph.terminate(count.correction.points[1].event_id)
    assert not p.graph.live(count.count_id, at(57))


def test_h3_count_owner_kept_and_dead_location_rejected():
    p, c, count, produced = elliott_source()
    # A typed location fixture is not itself an empirical Harmonic certificate.
    # Every dependency must still be in the same live source graph.
    from spotbot.research.multi_school_fidelity.integration_v9.producers import Produced

    h = replace(
        produced.thesis,
        grammar=HARMONIC,
        owner="HARMONIC_TYPE_I",
        initial_invalidation=150,
        mode="FINITE_REACTION",
        objectives=(220, 250),
    )
    location = Produced(h, {}, produced.evidence_ids)
    with pytest.raises(ContractError, match="PRODUCER_EMITTED"):
        c.h3(produced, location, pit_eligible=True)
    # Isolated composition fixture; not source-detector fidelity evidence.
    location = c._emit(h, pit_eligible=True, extra=produced.evidence_ids)
    result = c.h3(produced, location, pit_eligible=True)
    assert result.thesis.grammar == H3
    assert result.thesis.owner == "ELLIOTT_COMMON_COUNT_OWNER"
    assert result.thesis.initial_invalidation == 100
    assert result.thesis.mode == "TREND_CHECKPOINTS"
    p.graph.terminate(count.count_id)
    with pytest.raises(ContractError, match="LIVE"):
        c.h3(produced, location, pit_eligible=True)


def test_dow_context_uses_bound_observations_not_entry_owner():
    p = CompletedPrefix(PAIR, SHA)
    p.on_close(bar(0, degree="4H"), 4, at(4))
    parent = p.bar_id(p.bars["4H"][-1])
    obs = {}
    for key, value in {
        "primary": "UP",
        "secondary": "UP",
        "broad_confirmation": True,
        "volume": True,
    }.items():
        p.source_claim(key, value, at(4), "market", (parent,), SHA)
        obs[key] = KnownObservation(value, at(4), at(4), SHA)
    c = ContractProducer(p)
    c.dow_close(at(4), **obs)
    assert c.dow.trace[-1]["funded_entry"] is False
    with pytest.raises(ContractError, match="SOURCE"):
        c.dow_close(at(8), **dict(obs, primary=replace(obs["primary"], value="DOWN")))


def test_h2_failure_diagnostic_not_session_exit_and_daily_reversal_is_owned():
    e = kernel()
    t = thesis(TREND)
    admit(e, t)
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    g = SourceGraph()
    for i, kind in enumerate(("NY16", "BEARISH_MSS", "CONFIRMED_1D_DOWN")):
        evidence = g.register(Known(str(i), kind, at(1), SHA, "s"), origin="DETECTOR_GEOMETRY")
        failure = pipe.source_failure(1, evidence, g, at(1))
        if i < 2:
            assert failure is None
        else:
            assert failure.kind == "CONFIRMED_1D_DOWN"
            e.on_completed_hour(1, bar(0), {PAIR: 100000}, native_failure=failure)
            assert 1 in e.pending


def test_absent_open_price_or_capacity_fails_closed_with_no_cash_changes():
    p, _, _, produced = harmonic_source()
    ctx = context(p, at(19))
    for prices, capacities in [({}, {PAIR: 100000}), ({PAIR: 213}, {})]:
        e = kernel()
        pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
        env = pipe.bind(produced, p, state(), ctx)
        _, denied = pipe.on_open(at(19), prices, capacities, (env,), research_authorized=True)
        assert denied and not e.portfolio.k.fills


@pytest.mark.parametrize("reaccumulation", [False, True])
def test_wyckoff_actual_prefix_count_source_readiness_to_kernel(reaccumulation):
    p = CompletedPrefix(PAIR, SHA)
    custom = {
        0: (149, 150, 148, 149),
        24: (139, 140, 138, 139),
        48: (102, 103, 101, 102),
        52: (117, 118, 116, 117),
        56: (106, 107, 105, 106),
        60: (118, 119, 117, 118),
    }
    activities = {
        80: (110, 119, 107, 109, 100),
        82: (110, 111, 108, 110, 50),
        84: (118, 125, 117, 123, 200),
        88: (122, 124, 118, 123, 80),
    }
    for h in range(-3, 89):
        if h in activities:
            o, hi, lo, close, volume = activities[h]
        elif h + 1 in custom:
            o, hi, lo, close = custom[h + 1]
            volume = 1
        elif 64 <= h < 80:
            close = 100 * 1.01 ** (0 if h % 2 == 0 else 18)
            o, hi, lo, volume = close, close + 0.1, close - 0.1, 1
        else:
            o, hi, lo, close, volume = 110, 111, 109, 110, 1
        b = bar(h, o, hi, lo, close)
        p.on_close(b, volume, b.end)

    def point(h, kind):
        return next(q for q in p.points.values() if q.observed_at == at(h) and q.kind == kind)

    def source(eid, value, h, sid="cause", parent=None):
        parent = parent or p.bar_id(next(b for b in p.bars["1H"] if b.end == at(h)))
        return p.source_claim(eid, value, at(h), sid, (parent,), SHA)

    authority = source("range", "RANGE", 48)
    prior = source("markup", "MARKUP", 24, "old") if reaccumulation else None
    cause = RangeCause(
        "cause",
        at(48),
        100,
        120,
        "1H",
        authority,
        "REACCUMULATION" if reaccumulation else "ACCUMULATION",
        prior,
    )
    count_bars = [b for b in p.bars["1H"] if at(48) <= b.start < at(80)]
    seg = Segment("whole", at(48), at(80), at(80), "cause")
    source("whole", seg, 80)
    events = (
        (source("new-test", "NEW_RANGE_SUPPLY_TEST", 62),)
        if reaccumulation
        else tuple(
            source(name, name, 50 + i * 3)
            for i, name in enumerate(("PS", "SC", "ST", "DOWNSIDE_OBJECTIVE_MET"))
        )
    )
    market, rs = source("market", "UP", 62, "market"), source("rs", 1.1, 62)

    def activity(h):
        b = next(b for b in p.bars["1H"] if b.start == at(h))
        return ActivityBar(b, activities[h][-1])

    ready = Readiness(
        "cause",
        (point(0, "H"), point(24, "H")),
        (point(48, "L"), point(52, "H"), point(56, "L"), point(60, "H")),
        activity(80),
        activity(82),
        activity(84),
        activity(88),
        market,
        rs,
        events,
    )
    line = source("line", 118.0, 89)
    c = ContractProducer(p)
    c.start_wyckoff(cause, at(89))
    branch = "REACCUMULATION_LPS" if reaccumulation else "NO_SPRING_LPS"
    produced = c.wyckoff_intent(
        "cause", at(89), 123, ready, count_bars, (seg,), line, branch=branch, pit_eligible=True
    )
    assert produced and produced.thesis.owner == "WYCKOFF_RANGE_OWNER"
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    phase = (
        StructuralPhase.REACCUMULATION_CANDIDATE
        if reaccumulation
        else StructuralPhase.BASE_CANDIDATE
    )
    env = pipe.bind(produced, p, state(phase), context(p, at(89), phase))
    assert pipe.on_open(at(89), {PAIR: 123}, {PAIR: 100000}, (env,), research_authorized=True)[0]
    assert e.managers[1].finite_objective is None
    with pytest.raises(ContractError, match="TYPED"):
        c.wyckoff_intent(
            "cause",
            at(89),
            123,
            {"all": True},
            count_bars,
            (seg,),
            line,
            branch=branch,
            pit_eligible=True,
        )


def test_live_breadth_actual_complete_pit_prefix_source_and_missing_member_veto():
    graph = SourceGraph()
    prefixes = {pair: CompletedPrefix(pair, SHA, graph) for pair in (PAIR, "Y-USDT")}
    for p in prefixes.values():
        daily = bar(-24, 100, 110, 99, 105, "1D")
        p.on_close(daily, 24, daily.end)
        for h in (-4, 0):
            b = bar(h, 100 if h == -4 else 105, 111, 99, 105 if h == -4 else 110, "4H")
            p.on_close(b, 4, b.end)
    mem = graph.register(
        Known("membership", tuple(prefixes), at(0), SHA, "market"),
        origin="SUPPLIED_SEMANTIC_PRODUCER",
    )
    obs, broad = live_market_observations(prefixes, PAIR, mem, at(4))
    assert broad["confirmed"] and broad["breadth"] == 1
    assert obs["primary"].value == "UNKNOWN"  # no fabricated primary trend
    with pytest.raises(ContractError, match="COMPLETE_PIT"):
        live_market_observations({PAIR: prefixes[PAIR]}, PAIR, mem, at(4))
    c = ContractProducer(prefixes[PAIR])
    c.dow_close(at(4), **obs)
    assert c.dow.trace[-1]["funded_entry"] is False


def test_harmonic_type2_requires_real_kernel_closure_acknowledgement():
    p, c, sid, produced = harmonic_source()
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(produced, p, state(), context(p, at(19)))
    pipe.on_open(at(19), {PAIR: 213}, {PAIR: 100000}, (env,), research_authorized=True)
    cid = e.portfolio.k.positions[1]["campaign_id"]
    with pytest.raises(ContractError, match="STILL_OPEN"):
        pipe.acknowledge_harmonic_completion(c, sid, "HARMONIC_TYPE_I", at(19), cid)
    final = produced.thesis.objectives[1]
    hour = bar(19, 213, final + 1, 212, final)
    p.on_close(hour, 1, hour.end)
    c.harmonic_close(sid, hour, pit_eligible=True)
    pipe.on_completed_hour({PAIR: hour}, capacities={PAIR: 100000})
    assert not e.portfolio.k.positions
    pipe.acknowledge_harmonic_completion(c, sid, "HARMONIC_TYPE_I", at(20), cid)
    assert c.harmonics[sid].state == "TYPE_I_COMPLETE"
    retest = bar(20, 213, 214, 209.95, 211)
    p.on_close(retest, 1, retest.end)
    assert c.harmonic_close(sid, retest, pit_eligible=True) is None
    confirm = bar(21, 211, 217, 210, 215)
    p.on_close(confirm, 1, confirm.end)
    second = c.harmonic_close(sid, confirm, pit_eligible=True)
    assert second.thesis.owner == "HARMONIC_TYPE_II"
    with pytest.raises(ContractError, match="SOURCE"):
        c.acknowledge_harmonic_completion(
            sid,
            "HARMONIC_TYPE_II",
            at(22),
            execution_receipt=Known(
                "fake", ("CAMPAIGN_CLOSED", "HARMONIC_TYPE_II"), at(22), SHA, sid
            ),
        )


@pytest.mark.parametrize("field", ["mode", "objectives", "staged", "required_events", "state"])
def test_bound_envelope_decision_fields_cannot_mutate_after_source_binding(field):
    p, _, _, produced = harmonic_source()
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(produced, p, state(), context(p, at(19)))
    changes = {
        "mode": Mode.TREND,
        "objectives": (),
        "staged": True,
        "required_events": (),
        "state": state(StructuralPhase.MARKUP),
    }
    env = replace(env, **{field: changes[field]})
    with pytest.raises(ContractError, match="IMMUTABLE"):
        pipe.on_open(at(19), {PAIR: 213}, {PAIR: 100000}, (env,), research_authorized=True)
    assert not e.portfolio.k.fills


@pytest.mark.parametrize("grammar", ["FS_CLASSICAL_FULL_LONG", "HYB_MARKUP_CONTINUATION"])
def test_classical_h1_exact_legacy_route_without_owner_impersonation(grammar):
    from spotbot.research.multi_school_fidelity.akah_replay_ready_detectors_v1 import event_row
    from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import (
        Binding,
        LiveEvidence,
        PendingSetup,
    )

    p = CompletedPrefix(PAIR, SHA)
    b = bar(0)
    p.on_close(b, 1, b.end)
    proof = p.source_claim("acceptance", "CLASSICAL_ACCEPTANCE", at(1), "s", (p.bar_id(b),), SHA)
    setup = PendingSetup("s")
    setup.observe(LiveEvidence(proof.event_id, "s", at(1)), at(1))
    owner = "FS_CLASSICAL_FULL_LONG"
    bind = Binding(grammar, owner, "s", SHA, "1H", at(1), 90, "acceptance")
    event = event_row(
        grammar,
        PAIR,
        at(1),
        "THROWBACK",
        "INTENT",
        True,
        {
            "owner_structure_id": "s",
            "stop": 90,
            "invalidation_source": "acceptance",
            "required_evidence_ids": ("acceptance",),
        },
    )
    e = kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    st = state(StructuralPhase.MARKUP)
    env = pipe.bind_legacy(
        event,
        bind,
        setup,
        st,
        context=context(p, at(1), StructuralPhase.MARKUP),
        graph=p.graph,
        mode=Mode.TREND,
        objectives=(),
        valid_until=at(2),
    )
    assert pipe.on_open(at(1), {PAIR: 105}, {PAIR: 100000}, (env,), research_authorized=True)[0]
    assert e.managers[1].binding.owner == owner and e.managers[1].binding.grammar == grammar


def test_reused_kernel_position_id_does_not_inherit_old_session_expiry():
    e = kernel()
    admit(e, thesis())
    for i in range(3):
        e.on_completed_hour(1, bar(i), {PAIR: 100000})
    e.on_open(at(3), {PAIR: 106}, {PAIR: 100000})
    assert not e.portfolio.k.positions
    t = replace(thesis(TREND, when=4), structure_id="new", parents=("new-parent",))
    b = replace(
        binding(thesis(TREND, when=4)),
        structure_id="new",
        invalidation_source="new-parent",
        thesis=t,
    )
    r = dict(row(t), owner_structure_id="new", identity="second")
    assert e.admit_owned(
        r, b, at(4), 105, 100000, "new", research_authorized=True, mode=Mode.TREND
    )[0]
    assert 1 in e.portfolio.k.positions  # kernel IDs may be reused after closure
    e.on_completed_hour(1, bar(4), {PAIR: 100000})
    assert 1 not in e.pending


def test_atr_market_series_idempotent_shared_across_projections():
    p, _, _, _ = harmonic_source()
    first = p.atr("1H", "pattern-one", at(19))
    second = p.atr("1H", "pattern-two", at(19))
    assert first == second and first.structure_id == PAIR


def test_reused_position_id_cannot_inherit_previous_harmonic_partial_plan():
    from spotbot.research.multi_school_fidelity.integration_v9.execution import PartialPlanV9

    e = kernel()
    t = thesis(HARMONIC, goals=(110, 130))
    first = Objective("first", "s", 110, "FAMILY_REACTION", at(0), SHA)
    last = Objective("last", "s", 130, "FAMILY_REACTION", at(0), SHA)
    plan = PartialPlanV9(first, last, "TYPE_I")
    assert admit(e, t, partial_plan=plan)[0]
    e.on_completed_hour(1, bar(0, high=140), {PAIR: 100000})
    assert not e.portfolio.k.positions and 1 in e.partial
    t = replace(thesis(SESSION, when=1), structure_id="new", parents=("new-parent",))
    b = replace(
        binding(thesis(SESSION, when=1)),
        structure_id="new",
        invalidation_source="new-parent",
        thesis=t,
    )
    r = dict(row(t), owner_structure_id="new", identity="second")
    goals = (Objective("new-goal", "new", 130, "CONFIRMED_RESISTANCE", at(1), SHA),)
    assert e.admit_owned(
        r,
        b,
        at(1),
        105,
        100000,
        "new",
        mode=Mode.FINITE,
        objectives=goals,
        research_authorized=True,
    )[0]
    assert 1 not in e.partial
    before = len(e.portfolio.k.fills)
    e.on_completed_hour(1, bar(1, high=120), {PAIR: 100000})
    assert e.portfolio.k.positions and len(e.portfolio.k.fills) == before
