"""Synthetic-only V10 regressions; never load market/cache/replay outcomes."""

import ast
import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from spotbot.research.multi_school_fidelity.akah_replay_ready_detectors_v1 import event_row
from spotbot.research.multi_school_fidelity.integration_v10 import producers as prod
from spotbot.research.multi_school_fidelity.integration_v10.elliott_scope import PROFILE, check_wave
from spotbot.research.multi_school_fidelity.integration_v10.execution import ExecutionV9
from spotbot.research.multi_school_fidelity.integration_v10.pipeline import PipelineV9, RouterV9
from spotbot.research.multi_school_fidelity.integration_v10.stop_provenance import StopProof
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import (
    Binding,
    ContractError,
    Mode,
    PendingSetup,
)


@pytest.fixture
def f():
    path = Path(__file__).parents[1] / "integration_v9/test_producer_integration_v9.py"
    spec = importlib.util.spec_from_file_location("v10_synthetic_source_fixture", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.ContractProducer = prod.ContractProducer
    m.CL = "FS_CLASSICAL_FULL_LONG"
    m.PipelineV9 = PipelineV9
    m.RouterV9 = RouterV9
    m.ExecutionV9 = ExecutionV9

    def context(p, now, phase=m.StructuralPhase.BASE_CANDIDATE):
        parent = max((b for b in p.bars["1H"] if b.end <= now), key=lambda b: b.end)
        return p.source_claim(
            "router" + str(now), m.state(phase), now, "market", (p.bar_id(parent),), m.SHA
        )

    m.context = context
    # Reuse exact pre-existing source fixture, not its test/producer result.
    # Extract setup until the old test instantiates execution.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "test_wyckoff_actual_prefix_count_source_readiness_to_kernel"
    )
    body = []
    for n in fn.body:
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "e" for t in n.targets
        ):
            break
        body.append(n)
    fn.name = "wyckoff_source"
    fn.decorator_list = []
    fn.body = body + [
        ast.parse("return p, c, cause, ready, line, produced, count_bars, seg").body[0]
    ]
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(path), "exec"
        ),
        m.__dict__,
    )
    ict = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name == "test_ict_actual_source_chain_to_v8_contract_and_kernel"
    )
    body = []
    for n in ict.body:
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "e" for t in n.targets
        ):
            break
        body.append(n)
    ict.name = "ict_source"
    ict.decorator_list = []
    ict.body = body + [ast.parse("return p, c, chain, produced").body[0]]
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=[ict], type_ignores=[])), str(path), "exec"
        ),
        m.__dict__,
    )
    return m


def test_harmonic_source_to_fill_explicit_stop_not_first_parent(f):
    p, c, sid, result = f.harmonic_source()
    assert result.stop_proof.kind == "HARMONIC_FROZEN_PROFILE_STOP"
    meta = json.loads(result.event["metadata"])
    assert meta["invalidation_source"] == result.stop_claim_id != result.thesis.parents[0]
    assert result.stop_proof.evaluate(p.graph, f.at(19)) == result.thesis.initial_invalidation
    e = f.kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(result, p, f.state(), f.context(p, f.at(19)))
    before = copy.deepcopy(e.portfolio.k)
    bound, _ = pipe._bind(env, f.at(19), {f.PAIR: 213}, {f.PAIR: 100000})
    assert bound and e.portfolio.k == before
    selected, denied = pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert len(selected) == 1 and not denied and len(e.portfolio.k.fills) == 1
    assert e.managers[1].binding.invalidation_source == result.stop_claim_id


@pytest.mark.parametrize(
    "field,value",
    [
        ("invalidation_source", "WRONG"),
        ("invalidation_derivation", "LPS_LOW"),
        ("invalidation_source_ids", ["WRONG"]),
    ],
)
def test_stop_metadata_tamper_denied(f, field, value):
    p, c, sid, r = f.harmonic_source()
    event = copy.deepcopy(r.event)
    meta = json.loads(event["metadata"])
    meta[field] = value
    event["metadata"] = json.dumps(meta)
    r = replace(r, event=event)
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    with pytest.raises(ContractError, match="STOP_METADATA"):
        pipe.bind(r, p, f.state(), f.context(p, f.at(19)))


@pytest.mark.parametrize("dead", ["terminal", "projection", "pivot"])
def test_real_stop_parent_dead_before_next_open(f, dead):
    p, c, sid, r = f.harmonic_source()
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(19)))
    eid = {
        "terminal": r.stop_proof.source_ids[-1],
        "projection": r.stop_proof.source_ids[0],
        "pivot": c.harmonics[sid].projection.points[0].event_id,
    }[dead]
    p.graph.terminate(eid)
    selected, denied = pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and "SOURCE_PARENT" in str(denied) and not pipe.execution.portfolio.k.fills


@pytest.mark.parametrize("reaccumulation", [False, True])
@pytest.mark.parametrize(
    "dead",
    [
        "lps",
        "sos",
        "supply_test",
        "supply_reference",
        "falling_high",
        "range_swing",
        "pnf_bar",
        "market",
        "rs",
        "branch",
        "count_line",
        "segment",
        "cause",
    ],
)
def test_all_wyckoff_readiness_parents_live_through_entry(f, reaccumulation, dead):
    p, c, cause, ready, line, r, bars, seg = f.wyckoff_source(reaccumulation)
    ids = {
        "lps": p.bar_id(ready.lps.bar),
        "sos": p.bar_id(ready.sos.bar),
        "supply_test": p.bar_id(ready.supply_test.bar),
        "supply_reference": p.bar_id(ready.supply_reference.bar),
        "falling_high": ready.falling_highs[0].event_id,
        "range_swing": ready.range_swings[0].event_id,
        "pnf_bar": p.bar_id(bars[0]),
        "market": ready.market.event_id,
        "rs": ready.rs.event_id,
        "branch": ready.branch_events[0].event_id,
        "count_line": line.event_id,
        "segment": seg.event_id,
        "cause": cause.authority.event_id,
    }
    assert set(ids.values()) <= set(r.evidence_ids)
    assert r.stop_proof.source_ids == (p.bar_id(ready.lps.bar),)
    assert r.stop_proof.evaluate(p.graph, f.at(89)) == 118
    phase = (
        f.StructuralPhase.REACCUMULATION_CANDIDATE
        if reaccumulation
        else f.StructuralPhase.BASE_CANDIDATE
    )
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(phase), f.context(p, f.at(89), phase))
    p.graph.terminate(ids[dead])
    selected, denied = pipe.on_open(
        f.at(89), {f.PAIR: 123}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied and not pipe.execution.portfolio.k.fills


@pytest.mark.parametrize("reaccumulation", [False, True])
def test_wyckoff_unchanged_stop_price_source_to_fill(f, reaccumulation):
    p, c, cause, ready, line, r, bars, seg = f.wyckoff_source(reaccumulation)
    phase = (
        f.StructuralPhase.REACCUMULATION_CANDIDATE
        if reaccumulation
        else f.StructuralPhase.BASE_CANDIDATE
    )
    e = f.kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(phase), f.context(p, f.at(89), phase))
    assert pipe.on_open(
        f.at(89), {f.PAIR: 123}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]
    assert e.managers[1].hard_stop == 118


def test_elliott_actual_source_floor_and_explicit_scope(f):
    p, c, count, r = f.elliott_source()
    assert c.elliott.profile == PROFILE
    assert r.stop_proof.kind == "ELLIOTT_COMMON_PARENT_FLOOR"
    assert r.stop_proof.evaluate(p.graph, f.at(57)) == count.parent_prefix.points[0].price == 100
    e = f.kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    st = f.state(f.StructuralPhase.MARKUP)
    env = pipe.bind(r, p, st, f.context(p, f.at(57), f.StructuralPhase.MARKUP))
    assert pipe.on_open(
        f.at(57), {f.PAIR: 190}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]


@pytest.mark.parametrize("sign", [1, -1])
def test_truncated_fifth_explicit_diagnostic_scope(sign):
    w = SimpleNamespace(
        kind="IMPULSE",
        sign=sign,
        points=tuple(SimpleNamespace(price=sign * x) for x in (100, 130, 115, 150, 135, 145)),
        children=(),
    )
    with pytest.raises(ContractError, match="UNSUPPORTED_TRUNCATED_PROFILE"):
        check_wave(w)
    w.points = tuple(SimpleNamespace(price=sign * x) for x in (100, 130, 115, 150, 135, 160))
    check_wave(w)


def legacy(f, p, grammar, structure, now, bar, st):
    source = p.bar_id(bar)
    binding = Binding(grammar, f.CL, structure, f.SHA, "1H", now, bar.low, source)
    event = event_row(
        grammar,
        f.PAIR,
        now,
        "THROWBACK",
        "INTENT",
        True,
        {
            "owner_structure_id": structure,
            "stop": bar.low,
            "invalidation_source": source,
            "required_evidence_ids": (source,),
        },
    )
    return event, binding, PendingSetup(structure), StopProof("CLASSICAL_ACCEPTANCE_LOW", (source,))


@pytest.mark.parametrize("grammar", ["FS_CLASSICAL_FULL_LONG", "HYB_MARKUP_CONTINUATION"])
def test_classical_h1_actual_completed_bar_stop_to_kernel(f, grammar):
    p = f.CompletedPrefix(f.PAIR, f.SHA)
    b = f.bar(0)
    p.on_close(b, 1, b.end)
    st = f.state(f.StructuralPhase.MARKUP)
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    event, binding, setup, proof = legacy(f, p, grammar, "s", f.at(1), b, st)
    env = pipe.bind_legacy(
        event,
        binding,
        setup,
        st,
        context=f.context(p, f.at(1), f.StructuralPhase.MARKUP),
        graph=p.graph,
        stop_proof=proof,
        mode=Mode.TREND,
        objectives=(),
        valid_until=f.at(2),
    )
    assert pipe.on_open(f.at(1), {f.PAIR: 105}, {f.PAIR: 100000}, (env,), research_authorized=True)[
        0
    ]


def test_infeasible_same_asset_owner_filtered_before_conflict(f):
    p = f.CompletedPrefix(f.PAIR, f.SHA)
    b0 = f.bar(0, 105, 110, 90, 106)
    b1 = f.bar(1, 106, 110, 104, 106)
    for b in (b0, b1):
        p.on_close(b, 1, b.end)
    st = f.state(f.StructuralPhase.MARKUP)
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    ctx = f.context(p, f.at(2), f.StructuralPhase.MARKUP)
    envs = []
    for sid, b in [("feasible", b0), ("infeasible", b1)]:
        event, binding, setup, proof = legacy(f, p, f.CL, sid, f.at(2), b, st)
        envs.append(
            pipe.bind_legacy(
                event,
                binding,
                setup,
                st,
                context=ctx,
                graph=p.graph,
                stop_proof=proof,
                mode=Mode.TREND,
                objectives=(),
                valid_until=f.at(3),
            )
        )
    selected, denied = pipe.on_open(
        f.at(2), {f.PAIR: 104.0000001}, {f.PAIR: 49}, envs, research_authorized=True
    )
    assert not selected and all("PREBATCH_ADMISSION_INFEASIBLE" in x for x in denied.values())
    # Use an authoritative synthetic normalizer to reject one owner by stop
    # risk size, without altering the other owner's normalizer or selector.
    e = f.kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    envs = []
    for sid, b in [("feasible", b0), ("infeasible", b1)]:
        event, binding, setup, proof = legacy(f, p, f.CL, sid, f.at(2), b, st)
        envs.append(
            pipe.bind_legacy(
                event,
                binding,
                setup,
                st,
                context=ctx,
                graph=p.graph,
                stop_proof=proof,
                mode=Mode.TREND,
                objectives=(),
                valid_until=f.at(3),
            )
        )
    normal = e.portfolio.rules[f.PAIR].normalize
    e.portfolio.rules[f.PAIR].normalize = lambda pair, q, price, now, **kw: (
        normal(pair, q, price, now, **kw) if q < 100 else 0
    )
    selected, denied = pipe.on_open(
        f.at(2), {f.PAIR: 105}, {f.PAIR: 100000}, envs, research_authorized=True
    )
    assert len(selected) == 1 and selected[0].owner_structure_id == "feasible"
    assert any("PREBATCH_ADMISSION_INFEASIBLE" in x for x in denied.values())
    assert len(e.portfolio.k.fills) == 1


def test_real_mode_never_self_certifies_new_source(f):
    p, c, sid, r = f.harmonic_source()
    pipe = PipelineV9(f.kernel(), RouterV9())
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(19)))
    selected, denied = pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied and not pipe.execution.portfolio.k.fills


@pytest.mark.parametrize("mode", ["SESSION", "H2"])
def test_ict_h2_source_stop_ownership_and_fill(f, mode):
    p, c, chain, r = f.ict_source()
    if mode == "H2":
        for h in range(5, 8):
            b = f.bar(h, 110, 112, 105, 111)
            p.on_close(b, 1, b.end)
        acceptance = f.bar(4, 110, 113, 104, 111, degree="4H")
        p.on_close(acceptance, 4, acceptance.end)
        base = p.bars["1H"][0]
        parent = (p.bar_id(base),)
        daily = p.source_claim("daily", "UP", f.at(1), "market", parent, f.SHA)
        protected = p.source_claim("protected", 99.0, f.at(1), "s", parent, f.SHA)
        r = c.ict_intent(
            chain,
            f.at(8),
            111,
            f.TREND,
            pit_eligible=True,
            daily=daily,
            protected=protected,
            acceptance=acceptance,
        )
        now = f.at(8)
        entry = 111
        phase = f.StructuralPhase.MARKUP
        assert r.stop_proof.source_ids == (protected.event_id,)
    else:
        now = f.at(5)
        entry = 110
        phase = f.StructuralPhase.BASE_CANDIDATE
        assert r.stop_proof.source_ids == (p.bar_id(chain.raid),)
    assert json.loads(r.event["metadata"])["invalidation_source"] != chain.liquidity.event_id
    e = f.kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(
        r,
        p,
        f.state(phase),
        f.context(p, now, phase),
        session_end=chain.session_end if mode == "SESSION" else None,
    )
    assert pipe.on_open(now, {f.PAIR: entry}, {f.PAIR: 100000}, (env,), research_authorized=True)[0]
    assert e.managers[1].binding.invalidation_source == r.stop_claim_id


def test_ict_raid_invalidation_after_binding_denies_fill(f):
    p, c, chain, r = f.ict_source()
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(5)), session_end=chain.session_end)
    p.graph.terminate(p.bar_id(chain.raid))
    selected, denied = pipe.on_open(
        f.at(5), {f.PAIR: 110}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied and not pipe.execution.portfolio.k.fills


def test_harmonic_native_type2_closure_and_stop_proof(f):
    f.test_harmonic_type2_requires_real_kernel_closure_acknowledgement()


def test_dow_kept_context_only(f):
    f.test_dow_context_uses_bound_observations_not_entry_owner()


def spring_source(f):
    from spotbot.research.multi_school_fidelity.wyckoff_contract_v8 import (
        ActivityBar,
        Segment,
        SpringStage,
    )

    old, _, cause, ready, line, _, bars, seg = f.wyckoff_source(False)
    p = f.CompletedPrefix(f.PAIR, f.SHA)
    overrides = {
        62: (100, 100.1, 99.9, 100, 1),
        63: (119.6, 119.7, 119.5, 119.6, 1),
        64: (100, 100.1, 99.9, 100, 1),
        65: (100.1, 100.5, 99, 100.2, 100),
        67: (100.2, 100.3, 100, 100.2, 50),
        69: (100.2, 100.6, 100.1, 100.4, 60),
    }
    for b, v in zip(old.bars["1H"], old.volumes["1H"], strict=True):
        h = int((b.start - f.T).total_seconds() / 3600)
        if h in overrides:
            o, high, low, close, v = overrides[h]
            b = f.bar(h, o, high, low, close)
        p.on_close(b, v, b.end)
    for node in old.graph.nodes.values():
        if node.origin == "SUPPLIED_SEMANTIC_PRODUCER":
            e = node.evidence
            p.source_claim(
                e.event_id,
                e.value,
                e.available_at,
                e.structure_id,
                node.parents,
                e.source_sha256,
                e.valid_until,
            )

    def activity(h):
        b = next(b for b in p.bars["1H"] if b.start == f.at(h))
        return ActivityBar(b, overrides[h][-1])

    stage = SpringStage(
        cause.cause_id,
        activity(65),
        activity(67),
        activity(69),
        ready.market,
        ready.rs,
        ready.branch_events,
    )
    bs = [b for b in p.bars["1H"] if f.at(48) <= b.start < f.at(70)]
    sg = Segment("spring-whole", f.at(48), f.at(70), f.at(70), "cause")
    parent = (p.bar_id(stage.confirmation.bar),)
    p.source_claim(sg.event_id, sg, f.at(70), "cause", parent, f.SHA)
    ln = p.source_claim("spring-line", 100.0, f.at(70), "cause", parent, f.SHA)
    c = prod.ContractProducer(p)
    c.start_wyckoff(cause, f.at(70))
    r = c.wyckoff_intent(
        "cause", f.at(70), 100.4, stage, bs, (sg,), ln, branch="SPRING_TEST", pit_eligible=True
    )
    from spotbot.research.multi_school_fidelity.wyckoff_contract_v8 import pnf_cause

    assert r is not None, (
        stage.validate(cause, f.at(70)),
        pnf_cause(cause, bs, (sg,), ln, f.at(70)),
    )
    # Count the exact replaced synthetic prefix, never the old fixture bars.
    bars = [b for b in p.bars["1H"] if f.at(48) <= b.start < f.at(80)]
    return p, c, stage, r, ready, bars, seg, line


@pytest.mark.parametrize("source", ["spring", "test", "confirmation"])
def test_spring_dependency_killed_before_next_open(f, source):
    p, c, stage, r, ready, bars, seg, line = spring_source(f)
    assert r.stop_proof.kind == "SPRING_LOW"
    assert r.stop_proof.evaluate(p.graph, f.at(70)) == 99
    for a in (stage.spring, stage.test, stage.confirmation):
        assert p.bar_id(a.bar) in r.evidence_ids
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(70)))
    p.graph.terminate(p.bar_id(getattr(stage, source).bar))
    selected, denied = pipe.on_open(
        f.at(70), {f.PAIR: 100.4}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied and not pipe.execution.portfolio.k.fills


def test_spring_then_lps_add_same_binding_b0_and_full_graph(f):
    p, c, stage, r, ready, bars, seg, line = spring_source(f)
    e = f.kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(70)))
    # Smaller first-fill capacity keeps this positive-path fixture below the
    # unchanged per-asset MTM cap during its later upswing. Risk reduction
    # correctly forbids an add and must not be bypassed by the source adapter.
    assert pipe.on_open(
        f.at(70), {f.PAIR: 100.4}, {f.PAIR: 8000}, (env,), research_authorized=True
    )[0]
    # Kernel campaign lineage is the immutable selected intent, while source
    # cause lineage is separate. Source adapter must use actual campaign ID.
    actual = next(iter(e.portfolio.k.campaigns))
    pipe.acknowledge_wyckoff_stage(c, "cause", f.at(70), actual)
    initial = e.portfolio.k.campaigns[actual].initial_risk_budget
    for h in range(70, 89):
        b = next(b for b in p.bars["1H"] if b.start == f.at(h))
        pipe.on_completed_hour({f.PAIR: b}, capacities={f.PAIR: 100000})
        if h < 88:
            pipe.on_open(f.at(h + 1), {f.PAIR: b.close}, {f.PAIR: 100000}, research_authorized=True)
    add = c.wyckoff_add("cause", f.at(89), 123, ready, bars, (seg,), line, pit_eligible=True)
    assert actual == env.row["identity"]
    assert add.add_instruction["source_campaign_id"] == "cause"
    assert add.add_instruction["campaign_id"] == actual
    context = f.context(p, f.at(89))
    env_add = pipe.bind(add, p, f.state(), context, existing_campaign_id=actual)
    assert env_add.binding == env.binding
    selected, denied = pipe.on_open(
        f.at(89), {f.PAIR: 123}, {f.PAIR: 100000}, (env_add,), research_authorized=True
    )
    assert selected, denied
    assert e.portfolio.k.campaigns[actual].initial_risk_budget == initial
    assert e.portfolio.k.campaigns[actual].add_count == 1
    assert all(m.hard_stop >= 118 for m in e.managers.values())


def test_elliott_floor_point_invalidation_not_just_count(f):
    p, c, count, r = f.elliott_source()
    floor = count.parent_prefix.points[0]
    assert floor.event_id in r.stop_proof.source_ids
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    st = f.state(f.StructuralPhase.MARKUP)
    env = pipe.bind(r, p, st, f.context(p, f.at(57), f.StructuralPhase.MARKUP))
    p.graph.terminate(floor.event_id)
    selected, denied = pipe.on_open(
        f.at(57), {f.PAIR: 190}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied


@pytest.mark.parametrize("dead_location", [False, True])
def test_h3_isolated_composition_retains_count_stop(f, dead_location):
    # Composition evidence only: native XABC projection from this same
    # synthetic prefix. This does NOT claim a native confirmed entry detector.
    p, c, count, r = f.elliott_source()
    ps = tuple(
        next(q for q in p.points.values() if q.observed_at == f.at(h) and q.degree == "1H")
        for h in (16, 24, 32, 40)
    )
    parent = next(b for b in p.bars["1H"] if b.end == f.at(43))
    atr = p.source_claim("composition-atr", 1.0, f.at(43), "location", (p.bar_id(parent),), f.SHA)
    sid = c.start_harmonic("ABCD", ps, atr, 0.01, f.at(43))
    sources = (
        c.harmonic_projection_sources[sid],
        *(p.bar_id(b) for b in p.bars["1H"] if f.at(43) <= b.start and b.end <= f.at(57)),
    )
    proof = StopProof("HARMONIC_FROZEN_PROFILE_STOP", sources)
    h = replace(
        r.thesis,
        grammar=prod.HARMONIC,
        owner="HARMONIC_TYPE_I",
        structure_id=sid,
        management_degree="1H",
        initial_invalidation=proof.evaluate(p.graph, f.at(57)),
        objectives=(220, 250),
        mode="FINITE_REACTION",
        parents=sources,
    )
    location = c._emit(h, pit_eligible=True, stop_proof=proof)
    hybrid = c.h3(r, location, pit_eligible=True)
    assert hybrid.stop_proof == r.stop_proof and hybrid.thesis.initial_invalidation == 100
    assert hybrid.thesis.owner == "ELLIOTT_COMMON_COUNT_OWNER"
    assert hybrid.stop_claim_id != location.stop_claim_id
    e = f.kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    phase = f.StructuralPhase.MARKUP
    env = pipe.bind(hybrid, p, f.state(phase), f.context(p, f.at(57), phase))
    if dead_location:
        p.graph.terminate(sources[0])
    selected, denied = pipe.on_open(
        f.at(57), {f.PAIR: 190}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert bool(selected) is not dead_location
    assert bool(denied) == dead_location
    if selected:
        assert e.managers[1].hard_stop == 100


def test_wyckoff_add_without_actual_fill_receipt_denied(f):
    p, c, stage, r, ready, bars, seg, line = spring_source(f)
    with pytest.raises(ContractError, match="ACTUAL_STAGE_FILL_RECEIPT"):
        c.wyckoff_add("cause", f.at(89), 123, ready, bars, (seg,), line, pit_eligible=True)


def test_wyckoff_wrong_campaign_receipt_denied(f):
    p, c, stage, r, ready, bars, seg, line = spring_source(f)
    pipe = PipelineV9(f.kernel(), RouterV9(synthetic_fixture_execution=True))
    with pytest.raises(ContractError, match="ACTUAL_KERNEL_WYCKOFF_STAGE_FILL"):
        pipe.acknowledge_wyckoff_stage(c, "cause", f.at(70), "missing")


def test_wrong_owner_stop_derivation_denied(f):
    p, c, chain, r = f.ict_source()
    with pytest.raises(ContractError, match="STOP_DERIVATION_WRONG_OWNER"):
        replace(r.stop_proof, kind="LPS_LOW").validate_owner(r.thesis)


def test_full_kernel_prebatch_preview_never_changes_rejected_state(f):
    p, c, chain, r = f.ict_source()
    e = f.kernel()
    pipe = PipelineV9(e, RouterV9(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(5)), session_end=chain.session_end)
    original = copy.deepcopy(e.portfolio.k)
    result, reason = pipe._bind(env, f.at(5), {f.PAIR: 110}, {f.PAIR: 49})
    assert result is None and "PREBATCH_ADMISSION_INFEASIBLE" in reason
    assert e.portfolio.k == original
