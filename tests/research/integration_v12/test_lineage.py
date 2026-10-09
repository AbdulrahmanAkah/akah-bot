"""Synthetic authority revocation, not historical replay or profit evidence."""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from spotbot.research.multi_school_fidelity.integration_v10.producers import HARMONIC
from spotbot.research.multi_school_fidelity.integration_v10.stop_provenance import StopProof
from spotbot.research.multi_school_fidelity.integration_v11.contracts import freeze
from spotbot.research.multi_school_fidelity.integration_v12.pipeline import PipelineV12, RouterV12
from spotbot.research.multi_school_fidelity.integration_v12.producers import ContractProducer
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError


@pytest.fixture
def f():
    path = Path(__file__).parents[1] / "integration_v11/test_integrity.py"
    spec = importlib.util.spec_from_file_location("v12_native_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = module.f.__wrapped__()

    class FixtureProducer(ContractProducer):
        def _emit(self, thesis, *, pit_eligible, **kwargs):
            now = kwargs.get("add_instruction", {}).get("known_at", thesis.available_at)
            pit = (
                module.membership(base, self.prefix, now, pit_eligible)
                if type(pit_eligible) is bool
                else pit_eligible
            )
            return super()._emit(thesis, pit_eligible=pit, **kwargs)

    base.ContractProducer = FixtureProducer
    base.PipelineV9 = PipelineV12
    base.RouterV9 = RouterV12
    base.v10fixture.prod = SimpleNamespace(ContractProducer=FixtureProducer)
    base.v10fixture.PipelineV9 = PipelineV12
    base.v10fixture.RouterV9 = RouterV12
    base.v11fixture = module
    return base


def pipeline(f):
    return PipelineV12(f.kernel(), RouterV12(synthetic_fixture_execution=True))


def h3_parents(f):
    # Same original isolated composition fixture; native historical detector
    # completeness is not asserted. The Elliott count retains all ownership.
    p, c, count, r = f.elliott_source()
    points = tuple(
        next(q for q in p.points.values() if q.observed_at == f.at(h) and q.degree == "1H")
        for h in (16, 24, 32, 40)
    )
    bar = next(b for b in p.bars["1H"] if b.end == f.at(43))
    atr = p.source_claim("composition-atr", 1.0, f.at(43), "location", (p.bar_id(bar),), f.SHA)
    sid = c.start_harmonic("ABCD", points, atr, 0.01, f.at(43))
    sources = (
        c.harmonic_projection_sources[sid],
        *(p.bar_id(b) for b in p.bars["1H"] if f.at(43) <= b.start and b.end <= f.at(57)),
    )
    proof = StopProof("HARMONIC_FROZEN_PROFILE_STOP", sources)
    thesis = replace(
        r.thesis,
        grammar=HARMONIC,
        owner="HARMONIC_TYPE_I",
        structure_id=sid,
        management_degree="1H",
        initial_invalidation=proof.evaluate(p.graph, f.at(57)),
        objectives=(220, 250),
        mode="FINITE_REACTION",
        parents=sources,
    )
    location = c._emit(thesis, pit_eligible=r.membership, stop_proof=proof)
    return p, c, r, location


def type1_completed(f):
    p, c, sid, first = f.harmonic_source()
    pipe = pipeline(f)
    env = pipe.bind(first, p, f.state(), f.context(p, f.at(19)))
    assert pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]
    cid = pipe.execution.portfolio.k.positions[1]["campaign_id"]
    final = first.thesis.objectives[1]
    bar = f.bar(19, 213, final + 1, 212, final)
    p.on_close(bar, 1, bar.end)
    c.harmonic_close(sid, bar, pit_eligible=f.pit(p, f.at(20)))
    pipe.on_completed_hour({f.PAIR: bar}, capacities={f.PAIR: 100000})
    assert not pipe.execution.portfolio.k.positions
    pipe.acknowledge_harmonic_completion(c, sid, "HARMONIC_TYPE_I", f.at(20), cid)
    receipt = c.type_i_completion_receipts[sid]
    return p, c, sid, first, pipe, receipt, cid


def type2_confirm(f, p, c, sid, pipe):
    pipe.on_open(f.at(20), {f.PAIR: 213}, {f.PAIR: 100000}, research_authorized=True)
    bar = f.bar(20, 213, 214, 209.95, 211)
    p.on_close(bar, 1, bar.end)
    assert c.harmonic_close(sid, bar, pit_eligible=f.pit(p, f.at(21))) is None
    pipe.on_completed_hour({f.PAIR: bar}, capacities={f.PAIR: 100000})
    pipe.on_open(f.at(21), {f.PAIR: 211}, {f.PAIR: 100000}, research_authorized=True)
    bar = f.bar(21, 211, 217, 210, 215)
    p.on_close(bar, 1, bar.end)
    second = c.harmonic_close(sid, bar, pit_eligible=f.pit(p, f.at(22)))
    pipe.on_completed_hour({f.PAIR: bar}, capacities={f.PAIR: 100000})
    assert second.thesis.owner == "HARMONIC_TYPE_II"
    return second


def admit_direct(f, pipe, env, now, entry):
    return pipe.execution.admit_owned(
        env.row,
        env.binding,
        now,
        entry,
        100000,
        env.row["identity"],
        mode=env.mode,
        objectives=env.objectives,
        partial_plan=env.partial_plan,
        staged=env.staged,
        add_evidence=env.add_evidence,
        prices={f.PAIR: entry},
        research_authorized=True,
    )


def test_h3_exact_parent_seals_in_thesis_issue_and_actual_guard(f):
    p, c, count, location = h3_parents(f)
    result = c.h3(count, location, pit_eligible=count.membership)
    pipe = pipeline(f)
    phase = f.StructuralPhase.MARKUP
    env = pipe.bind(result, p, f.state(phase), f.context(p, f.at(57), phase))
    for seal in (count.emission_id, location.emission_id):
        assert seal in result.thesis.parents and seal in result.evidence_ids
        assert seal in p.graph.nodes[result.emission_id].parents
        assert seal in env.required_events
        assert any(
            q.event_id == seal
            for q in pipe.execution.source_guards[env.row["identity"]].required_claims
        )
    assert (
        result.stop_proof == count.stop_proof
        and result.thesis.objectives == count.thesis.objectives
    )
    assert pipe.on_open(
        f.at(57), {f.PAIR: 190}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]


@pytest.mark.parametrize("parent", ["count", "location"])
@pytest.mark.parametrize("stage", ["compose", "bind", "open", "actual_kernel"])
def test_h3_revoked_exact_parent_never_fills(f, parent, stage):
    p, c, count, location = h3_parents(f)
    seal = (count if parent == "count" else location).emission_id
    if stage == "compose":
        p.graph.terminate(seal)
        with pytest.raises(ContractError, match="INVALIDATED_SOURCE"):
            c.h3(count, location, pit_eligible=count.membership)
        return
    result = c.h3(count, location, pit_eligible=count.membership)
    pipe = pipeline(f)
    phase = f.StructuralPhase.MARKUP
    context = f.context(p, f.at(57), phase)
    if stage == "bind":
        p.graph.terminate(seal)
        with pytest.raises(ContractError, match="INVALIDATED_SOURCE"):
            pipe.bind(result, p, f.state(phase), context)
    else:
        env = pipe.bind(result, p, f.state(phase), context)
        if stage == "actual_kernel":
            assert pipe._bind(env, f.at(57), {f.PAIR: 190}, {f.PAIR: 100000})[0]
        p.graph.terminate(seal)
        if stage == "actual_kernel":
            with pytest.raises(ContractError, match="INVALIDATED_SOURCE"):
                admit_direct(f, pipe, env, f.at(57), 190)
        else:
            selected, denied = pipe.on_open(
                f.at(57), {f.PAIR: 190}, {f.PAIR: 100000}, (env,), research_authorized=True
            )
            assert not selected and denied
    assert not pipe.execution.portfolio.k.fills


@pytest.mark.parametrize("parent", ["count", "location"])
def test_h3_parent_seal_cannot_be_removed_from_composed_issue(f, parent):
    p, c, count, location = h3_parents(f)
    result = c.h3(count, location, pit_eligible=count.membership)
    seal = (count if parent == "count" else location).emission_id
    bad = replace(result, evidence_ids=tuple(e for e in result.evidence_ids if e != seal))
    phase = f.StructuralPhase.MARKUP
    pipe = pipeline(f)
    with pytest.raises(ContractError, match="EMISSION_PAYLOAD_INTEGRITY"):
        pipe.bind(bad, p, f.state(phase), f.context(p, f.at(57), phase))


def test_type2_exact_completion_receipt_reaches_actual_guard_and_fill(f):
    p, c, sid, first, pipe, receipt, cid = type1_completed(f)
    second = type2_confirm(f, p, c, sid, pipe)
    env = pipe.bind(second, p, f.state(), f.context(p, f.at(22)))
    assert receipt.event_id in second.thesis.parents
    assert receipt.event_id in second.evidence_ids
    assert receipt.event_id in p.graph.nodes[second.emission_id].parents
    assert receipt.event_id in env.required_events
    assert any(
        q == receipt for q in pipe.execution.source_guards[env.row["identity"]].required_claims
    )
    assert first.thesis.initial_invalidation == second.thesis.initial_invalidation
    assert first.thesis.objectives == second.thesis.objectives
    assert pipe.on_open(
        f.at(22), {f.PAIR: 215}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]
    assert next(iter(pipe.execution.portfolio.k.positions.values()))["campaign_id"] != cid


@pytest.mark.parametrize("stage", ["produce", "bind", "open", "actual_kernel"])
def test_type2_revoked_completion_receipt_never_fills(f, stage):
    p, c, sid, first, pipe, receipt, cid = type1_completed(f)
    fills_before = len(pipe.execution.portfolio.k.fills)
    if stage == "produce":
        p.graph.terminate(receipt.event_id)
        with pytest.raises(ContractError, match="INVALIDATED_SOURCE"):
            type2_confirm(f, p, c, sid, pipe)
    else:
        second = type2_confirm(f, p, c, sid, pipe)
        context = f.context(p, f.at(22))
        if stage == "bind":
            p.graph.terminate(receipt.event_id)
            with pytest.raises(ContractError, match="INVALIDATED_SOURCE"):
                pipe.bind(second, p, f.state(), context)
        else:
            env = pipe.bind(second, p, f.state(), context)
            if stage == "actual_kernel":
                assert pipe._bind(env, f.at(22), {f.PAIR: 215}, {f.PAIR: 100000})[0]
            p.graph.terminate(receipt.event_id)
            if stage == "actual_kernel":
                with pytest.raises(ContractError, match="INVALIDATED_SOURCE"):
                    admit_direct(f, pipe, env, f.at(22), 215)
            else:
                selected, denied = pipe.on_open(
                    f.at(22), {f.PAIR: 215}, {f.PAIR: 100000}, (env,), research_authorized=True
                )
                assert not selected and denied
    assert len(pipe.execution.portfolio.k.fills) == fills_before
    assert not pipe.execution.portfolio.k.positions


def test_type2_internal_state_alone_not_completion_authority(f):
    p, c, sid, first, pipe, receipt, cid = type1_completed(f)
    del c.type_i_completion_receipts[sid]
    with pytest.raises(ContractError, match="EXACT_COMPLETION_RECEIPT_REQUIRED"):
        type2_confirm(f, p, c, sid, pipe)
    assert not pipe.execution.portfolio.k.positions


def test_completion_cannot_rebind_or_resurrect(f):
    p, c, sid, first, pipe, receipt, cid = type1_completed(f)
    with pytest.raises(ContractError, match="NO_REBINDING"):
        c.acknowledge_harmonic_completion(
            sid, "HARMONIC_TYPE_I", f.at(20), execution_receipt=receipt
        )
    p.graph.terminate(receipt.event_id)
    with pytest.raises(ContractError, match="NO_RESURRECTION"):
        p.graph.register(
            receipt, p.graph.nodes[receipt.event_id].parents, origin="DETECTOR_GEOMETRY"
        )
    assert c.type_i_completion_receipts[sid] == receipt


@pytest.mark.parametrize("field", ["structure_id", "source_sha256", "available_at", "value"])
def test_type2_receipt_state_substitution_not_authority(f, field):
    p, c, sid, first, pipe, receipt, cid = type1_completed(f)
    replacements = dict(
        structure_id="wrong",
        source_sha256="b" * 64,
        available_at=f.at(21),
        value=("CAMPAIGN_CLOSED", "HARMONIC_TYPE_II"),
    )
    c.type_i_completion_receipts[sid] = replace(receipt, **{field: replacements[field]})
    with pytest.raises(ContractError, match="INVALIDATED_SOURCE"):
        type2_confirm(f, p, c, sid, pipe)


def test_type2_receipt_cannot_be_removed_by_prebind_mutation(f):
    p, c, sid, first, pipe, receipt, cid = type1_completed(f)
    second = type2_confirm(f, p, c, sid, pipe)
    bad = replace(
        second,
        thesis=replace(
            second.thesis, parents=tuple(e for e in second.thesis.parents if e != receipt.event_id)
        ),
    )
    with pytest.raises(ContractError, match="EMISSION_PAYLOAD_INTEGRITY"):
        pipe.bind(bad, p, f.state(), f.context(p, f.at(22)))


def test_old_mutable_payload_and_false_pit_attacks_still_denied(f):
    p, c, sid, first = f.harmonic_source()
    pipe = pipeline(f)
    with pytest.raises(TypeError):
        first.event["broad_eligible"] = False
    bad = replace(first, event=freeze(dict(first.event, broad_eligible=False)))
    with pytest.raises(ContractError, match="PIT_EVENT_PARITY"):
        pipe.bind(bad, p, f.state(), f.context(p, f.at(19)))


def test_real_mode_stays_unfunded(f):
    p, c, count, location = h3_parents(f)
    result = c.h3(count, location, pit_eligible=count.membership)
    pipe = PipelineV12(f.kernel(), RouterV12())
    phase = f.StructuralPhase.MARKUP
    env = pipe.bind(result, p, f.state(phase), f.context(p, f.at(57), phase))
    selected, denied = pipe.on_open(
        f.at(57), {f.PAIR: 190}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied and not pipe.execution.portfolio.k.fills


def test_completion_receipt_clock_cannot_relabel_closed_campaign(f):
    p, c, sid, first, pipe, receipt, cid = type1_completed(f)
    before = c.harmonics[sid].type1_complete_at
    with pytest.raises(ContractError, match="EXACT_CLOCK_REQUIRED"):
        c.acknowledge_harmonic_completion(
            sid, "HARMONIC_TYPE_I", f.at(21), execution_receipt=receipt
        )
    assert c.harmonics[sid].type1_complete_at == before == f.at(20)


@pytest.mark.parametrize("floor", [100.0, 119.0])
def test_v10_add_stop_attacks_still_denied_with_v12_producer(f, floor):
    f.v11fixture.test_add_stop_weaker_or_tighter_forgery_denied(f, floor)


def test_v10_false_to_true_pit_attack_still_denied_with_v12_producer(f):
    f.v11fixture.test_false_pit_not_resurrected(f)
