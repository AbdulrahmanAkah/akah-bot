"""Native synthetic fixtures, not market replay or historical PIT certification."""

import copy
import importlib.util
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from spotbot.research.multi_school_fidelity.integration_v10.producers import HARMONIC
from spotbot.research.multi_school_fidelity.integration_v10.stop_provenance import StopProof
from spotbot.research.multi_school_fidelity.integration_v11.contracts import (
    FrozenMap,
    PitMembership,
    freeze,
)
from spotbot.research.multi_school_fidelity.integration_v11.execution import ExecutionV11
from spotbot.research.multi_school_fidelity.integration_v11.pipeline import PipelineV11, RouterV11
from spotbot.research.multi_school_fidelity.integration_v11.producers import ContractProducer
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError


def membership(f, p, now, eligible=True):
    # Explicit synthetic external PIT fact. It is NOT inferred from price or
    # an adapter default; runtime ContractProducer rejects bare booleans.
    value = PitMembership(p.pair, now, eligible, f.at(-100), f.at(10000))
    eid = f"fixture-pit:{p.pair}:{now}:{eligible}"
    if eid in p.graph.nodes:
        return p.graph.nodes[eid].evidence
    parent = max((b for b in p.bars["1H"] if b.end <= now), key=lambda b: b.end)
    return p.source_claim(eid, value, now, p.pair, (p.bar_id(parent),), f.SHA)


@pytest.fixture
def f():
    path = Path(__file__).parents[1] / "integration_v10/test_repairs.py"
    spec = importlib.util.spec_from_file_location("v11_native_synthetic_fixtures", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    base = m.f.__wrapped__()

    class FixtureProducer(ContractProducer):
        def _emit(self, thesis, *, pit_eligible, **kwargs):
            when = kwargs.get("add_instruction", {}).get("known_at", thesis.available_at)
            claim = (
                membership(base, self.prefix, when, pit_eligible)
                if type(pit_eligible) is bool
                else pit_eligible
            )
            return super()._emit(thesis, pit_eligible=claim, **kwargs)

    base.ContractProducer = FixtureProducer
    base.ExecutionV9 = ExecutionV11
    base.PipelineV9 = PipelineV11
    base.RouterV9 = RouterV11
    m.prod = SimpleNamespace(ContractProducer=FixtureProducer)
    m.PipelineV9 = PipelineV11
    m.RouterV9 = RouterV11
    original_context = base.context

    def reusable_context(p, now, phase=base.StructuralPhase.BASE_CANDIDATE):
        eid = "router" + str(now)
        if eid in p.graph.nodes:
            claim = p.graph.nodes[eid].evidence
            p.graph.require(claim, now)
            assert claim.value == base.state(phase)
            return claim
        return original_context(p, now, phase)

    base.context = reusable_context
    base.v10fixture = m
    base.pit = lambda p, now, eligible=True: membership(base, p, now, eligible)
    return base


def bound_harmonic(f, eligible=True):
    p, c, sid, r = f.harmonic_source()
    if not eligible:
        r = c._emit(r.thesis, pit_eligible=f.pit(p, f.at(19), False), stop_proof=r.stop_proof)
    pipe = PipelineV11(f.kernel(), RouterV11(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(19)))
    return p, c, r, pipe, env


def staged_add(f):
    p, c, stage, r, ready, bars, seg, line = f.v10fixture.spring_source(f)
    e = f.kernel()
    pipe = PipelineV11(e, RouterV11(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(70)))
    assert pipe.on_open(
        f.at(70), {f.PAIR: 100.4}, {f.PAIR: 8000}, (env,), research_authorized=True
    )[0]
    campaign = next(iter(e.portfolio.k.campaigns))
    pipe.acknowledge_wyckoff_stage(c, "cause", f.at(70), campaign)
    for h in range(70, 89):
        b = next(b for b in p.bars["1H"] if b.start == f.at(h))
        pipe.on_completed_hour({f.PAIR: b}, capacities={f.PAIR: 100000})
        if h < 88:
            pipe.on_open(f.at(h + 1), {f.PAIR: b.close}, {f.PAIR: 100000}, research_authorized=True)
    r = c.wyckoff_add(
        "cause", f.at(89), 123, ready, bars, (seg,), line, pit_eligible=f.pit(p, f.at(89))
    )
    return p, c, r, pipe, campaign


def test_exact_native_source_to_guarded_fill(f):
    p, c, r, pipe, env = bound_harmonic(f)
    assert isinstance(r.event, FrozenMap)
    assert pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]


def test_false_pit_not_resurrected(f):
    p, c, r, pipe, env = bound_harmonic(f, False)
    selected, denied = pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied and not pipe.execution.portfolio.k.fills
    with pytest.raises(TypeError):
        r.event["broad_eligible"] = True
    forged = replace(r, event=freeze(dict(r.event, broad_eligible=True)))
    with pytest.raises(ContractError, match="PIT_EVENT_PARITY"):
        pipe.bind(forged, p, f.state(), f.context(p, f.at(19)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("pair", "OTHER-USDT"),
        ("timestamp", "2023-01-01T00:00:00Z"),
        ("system_id", "OTHER"),
        ("event_kind", "OTHER"),
        ("presentation_only", "EXTRA"),
        ("broad_eligible", False),
        ("metadata", "{}"),
    ],
)
def test_all_prebind_event_mutations_denied(f, field, value):
    p, c, r, pipe, env = bound_harmonic(f)
    with pytest.raises(TypeError):
        r.event[field] = value
    bad = replace(r, event=freeze(dict(r.event, **{field: value})))
    with pytest.raises((ContractError, KeyError)):
        pipe.bind(bad, p, f.state(), f.context(p, f.at(19)))
    assert not pipe.execution.portfolio.k.fills


def test_emission_receipt_termination_denies_fill(f):
    p, c, r, pipe, env = bound_harmonic(f)
    p.graph.terminate(r.emission_id)
    selected, denied = pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied


@pytest.mark.parametrize("when", ["before_bind", "before_open"])
def test_pit_source_termination_denies(f, when):
    p, c, sid, r = f.harmonic_source()
    pipe = PipelineV11(f.kernel(), RouterV11(synthetic_fixture_execution=True))
    if when == "before_bind":
        p.graph.terminate(r.membership.event_id)
        with pytest.raises(ContractError):
            pipe.bind(r, p, f.state(), f.context(p, f.at(19)))
    else:
        env = pipe.bind(r, p, f.state(), f.context(p, f.at(19)))
        p.graph.terminate(r.membership.event_id)
        selected, denied = pipe.on_open(
            f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
        )
        assert not selected and denied
    assert not pipe.execution.portfolio.k.fills


def test_bare_boolean_membership_never_accepted_by_runtime(f):
    p, c, sid, r = f.harmonic_source()
    runtime = ContractProducer(p)
    with pytest.raises(ContractError, match="TYPED_SOURCE_BOUND_PIT"):
        runtime._emit(r.thesis, pit_eligible=True, stop_proof=r.stop_proof)


@pytest.mark.parametrize(
    "change", ["wrong_pair", "wrong_checkpoint", "outside_period", "future_source"]
)
def test_pit_authority_clock_and_asset_contract(f, change):
    p, c, sid, r = f.harmonic_source()
    claim = r.membership
    values = {
        "wrong_pair": {"pair": "OTHER-USDT"},
        "wrong_checkpoint": {"checkpoint": f.at(18)},
        "outside_period": {"effective_from": f.at(20)},
        "future_source": {},
    }
    bad = replace(claim, value=replace(claim.value, **values[change]))
    if change == "future_source":
        bad = replace(bad, available_at=f.at(20))
    with pytest.raises(ContractError):
        ContractProducer(p)._emit(r.thesis, pit_eligible=bad, stop_proof=r.stop_proof)


def test_staged_add_exact_lps_and_unchanged_b0(f):
    p, c, r, pipe, campaign = staged_add(f)
    before = pipe.execution.portfolio.k.campaigns[campaign].initial_risk_budget
    assert r.add_proof.value.lps.value[0].low == 118
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(89)), existing_campaign_id=campaign)
    assert pipe.on_open(
        f.at(89), {f.PAIR: 123}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]
    assert all(m.hard_stop == 118 for m in pipe.execution.managers.values())
    assert pipe.execution.portfolio.k.campaigns[campaign].initial_risk_budget == before


@pytest.mark.parametrize("floor", [100.0, 119.0])
def test_add_stop_weaker_or_tighter_forgery_denied(f, floor):
    p, c, r, pipe, campaign = staged_add(f)
    with pytest.raises(TypeError):
        r.add_instruction["stop_floor"] = floor
    bad = replace(r, add_instruction=freeze(dict(r.add_instruction, stop_floor=floor)))
    with pytest.raises(ContractError):
        pipe.bind(bad, p, f.state(), f.context(p, f.at(89)), existing_campaign_id=campaign)
    assert len(pipe.execution.portfolio.k.fills) == 1


@pytest.mark.parametrize("source", ["lps", "stage_stop", "receipt", "add_proof"])
def test_add_source_dead_at_actual_open_denied(f, source):
    p, c, r, pipe, campaign = staged_add(f)
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(89)), existing_campaign_id=campaign)
    proof = r.add_proof.value
    ids = {
        "lps": proof.lps.event_id,
        "stage_stop": proof.stage_stop.event_id,
        "receipt": proof.fill_receipt.event_id,
        "add_proof": r.add_proof.event_id,
    }
    p.graph.terminate(ids[source])
    selected, denied = pipe.on_open(
        f.at(89), {f.PAIR: 123}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied and len(pipe.execution.portfolio.k.fills) == 1


def test_kernel_rechecks_membership_after_prebatch(f):
    p, c, r, pipe, env = bound_harmonic(f)
    assert pipe._bind(env, f.at(19), {f.PAIR: 213}, {f.PAIR: 100000})[0]
    p.graph.terminate(r.membership.event_id)
    with pytest.raises(ContractError):
        pipe.execution.admit_owned(
            env.row,
            env.binding,
            f.at(19),
            213,
            100000,
            env.row["identity"],
            mode=env.mode,
            objectives=env.objectives,
            partial_plan=env.partial_plan,
            staged=env.staged,
            add_evidence=env.add_evidence,
            prices={f.PAIR: 213},
            research_authorized=True,
        )
    assert not pipe.execution.portfolio.k.fills


def test_kernel_rechecks_add_stop_after_prebatch(f):
    p, c, r, pipe, campaign = staged_add(f)
    env = pipe.bind(r, p, f.state(), f.context(p, f.at(89)), existing_campaign_id=campaign)
    assert pipe._bind(env, f.at(89), {f.PAIR: 123}, {f.PAIR: 100000})[0]
    bad = replace(env.add_evidence, lps_low=100)
    with pytest.raises(ContractError):
        pipe.execution.admit_owned(
            env.row,
            env.binding,
            f.at(89),
            123,
            100000,
            campaign,
            mode=env.mode,
            objectives=env.objectives,
            partial_plan=env.partial_plan,
            staged=env.staged,
            add_evidence=bad,
            prices={f.PAIR: 123},
            research_authorized=True,
        )
    assert len(pipe.execution.portfolio.k.fills) == 1


def test_router_remains_real_mode_unfunded(f):
    p, c, r, pipe, env = bound_harmonic(f)
    pipe.router = RouterV11()
    selected, denied = pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert not selected and denied and not pipe.execution.portfolio.k.fills


def test_deep_freeze_copies_mutable_input():
    raw = {"nested": {"a": [1, 2]}}
    sealed = freeze(raw)
    raw["nested"]["a"][0] = 9
    assert sealed["nested"]["a"] == (1, 2)
    assert copy.deepcopy(sealed) is sealed


@pytest.mark.parametrize(
    "field",
    [
        "grammar",
        "owner",
        "structure_id",
        "available_at",
        "management_degree",
        "side",
        "initial_invalidation",
        "objectives",
        "mode",
        "source_sha256",
        "parents",
        "management_rule",
        "adaptation",
    ],
)
def test_thesis_mutation_rejected_by_emission_seal(f, field):
    p, c, r, pipe, env = bound_harmonic(f)
    value = getattr(r.thesis, field)
    badvalue = (
        value + 1
        if isinstance(value, (int, float))
        else value + ("FORGED",)
        if isinstance(value, tuple)
        else f.at(18)
        if field == "available_at"
        else str(value) + "FORGED"
    )
    bad = replace(r, thesis=replace(r.thesis, **{field: badvalue}))
    with pytest.raises(ContractError, match="EMISSION_PAYLOAD_INTEGRITY"):
        pipe.bind(bad, p, f.state(), f.context(p, f.at(19)))


@pytest.mark.parametrize("field", ["staged", "stop_claim_id", "evidence_ids", "emission_id"])
def test_non_event_producer_fields_sealed(f, field):
    p, c, r, pipe, env = bound_harmonic(f)
    values = dict(
        staged=True, stop_claim_id="wrong", evidence_ids=r.evidence_ids[:-1], emission_id="wrong"
    )
    bad = replace(r, **{field: values[field]})
    with pytest.raises(ContractError):
        pipe.bind(bad, p, f.state(), f.context(p, f.at(19)))


@pytest.mark.parametrize(
    "field",
    [
        "known_at",
        "owner",
        "campaign_id",
        "source_campaign_id",
        "remaining_risk_budget_fraction",
        "extra",
    ],
)
def test_add_instruction_fields_are_integrity_bound(f, field):
    p, c, r, pipe, campaign = staged_add(f)
    values = dict(
        known_at=f.at(88),
        owner="wrong",
        campaign_id="wrong",
        source_campaign_id="wrong",
        remaining_risk_budget_fraction=0.9,
        extra="wrong",
    )
    bad = replace(r, add_instruction=freeze(dict(r.add_instruction, **{field: values[field]})))
    with pytest.raises(ContractError, match="EMISSION_PAYLOAD_INTEGRITY"):
        pipe.bind(bad, p, f.state(), f.context(p, f.at(89)), existing_campaign_id=campaign)


@pytest.mark.parametrize("mutation", ["context_dead", "mode", "objectives", "row_pit", "no_guard"])
def test_actual_kernel_rechecks_all_binding_authority(f, mutation):
    p, c, r, pipe, env = bound_harmonic(f)
    assert pipe._bind(env, f.at(19), {f.PAIR: 213}, {f.PAIR: 100000})[0]
    row = env.row.copy()
    mode = env.mode
    objectives = env.objectives
    if mutation == "context_dead":
        p.graph.terminate(f.context(p, f.at(19)).event_id)
    elif mutation == "mode":
        mode = "OTHER"
    elif mutation == "objectives":
        objectives = ()
    elif mutation == "row_pit":
        row["pit_eligible"] = False
    else:
        pipe.execution.source_guards.clear()
    with pytest.raises(ContractError):
        pipe.execution.admit_owned(
            row,
            env.binding,
            f.at(19),
            213,
            100000,
            row["identity"],
            mode=mode,
            objectives=objectives,
            partial_plan=env.partial_plan,
            staged=env.staged,
            prices={f.PAIR: 213},
            research_authorized=True,
        )
    assert not pipe.execution.portfolio.k.fills


@pytest.mark.parametrize("reaccumulation", [False, True])
def test_wyckoff_no_spring_positive_native_controls(f, reaccumulation):
    p, c, cause, ready, line, r, bars, seg = f.wyckoff_source(reaccumulation)
    phase = (
        f.StructuralPhase.REACCUMULATION_CANDIDATE
        if reaccumulation
        else f.StructuralPhase.BASE_CANDIDATE
    )
    pipe = PipelineV11(f.kernel(), RouterV11(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(phase), f.context(p, f.at(89), phase))
    assert pipe.on_open(
        f.at(89), {f.PAIR: 123}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]
    assert pipe.execution.managers[1].hard_stop == 118


def test_elliott_positive_native_control(f):
    p, c, count, r = f.elliott_source()
    phase = f.StructuralPhase.MARKUP
    pipe = PipelineV11(f.kernel(), RouterV11(synthetic_fixture_execution=True))
    env = pipe.bind(r, p, f.state(phase), f.context(p, f.at(57), phase))
    assert pipe.on_open(
        f.at(57), {f.PAIR: 190}, {f.PAIR: 100000}, (env,), research_authorized=True
    )[0]


@pytest.mark.parametrize("mode", ["SESSION", "H2"])
def test_ict_and_h2_native_positive_controls(f, mode):
    # Existing native setup and assertions; explicit fixture adapter supplies
    # synthetic typed PIT facts instead of changing the runtime API contract.
    f.v10fixture.test_ict_h2_source_stop_ownership_and_fill(f, mode)


@pytest.mark.parametrize("grammar", ["FS_CLASSICAL_FULL_LONG", "HYB_MARKUP_CONTINUATION"])
def test_sealed_legacy_source_to_kernel(f, grammar):
    p = f.CompletedPrefix(f.PAIR, f.SHA)
    bar = f.bar(0)
    p.on_close(bar, 1, bar.end)
    phase = f.StructuralPhase.MARKUP
    state = f.state(phase)
    event, binding, setup, proof = f.v10fixture.legacy(f, p, grammar, "s", f.at(1), bar, state)
    producer = ContractProducer(p)
    issue = producer.seal_legacy(event, binding, proof, f.pit(p, f.at(1)))
    pipe = PipelineV11(f.kernel(), RouterV11(synthetic_fixture_execution=True))
    args = dict(
        context=f.context(p, f.at(1), phase),
        graph=p.graph,
        stop_proof=proof,
        mode=f.v10fixture.Mode.TREND,
        objectives=(),
        valid_until=f.at(2),
    )
    with pytest.raises(ContractError, match="SEALED_LEGACY"):
        pipe.bind_legacy(event, binding, setup, state, **args)
    bad = replace(issue, event=freeze(dict(issue.event, broad_eligible=False)))
    with pytest.raises(ContractError, match="PIT_EVENT_PARITY"):
        pipe.bind_legacy(bad, binding, setup, state, **args)
    env = pipe.bind_legacy(issue, binding, setup, state, **args)
    assert pipe.on_open(f.at(1), {f.PAIR: 105}, {f.PAIR: 100000}, (env,), research_authorized=True)[
        0
    ]


@pytest.mark.parametrize("dead_location", [False, True])
def test_h3_sealed_isolated_composition(f, dead_location):
    # Composition fixture only: no claim of full historical joint detector.
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
    t = replace(
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
    location = c._emit(t, pit_eligible=r.membership, stop_proof=proof)
    hybrid = c.h3(r, location, pit_eligible=r.membership)
    assert hybrid.stop_proof == r.stop_proof
    pipe = PipelineV11(f.kernel(), RouterV11(synthetic_fixture_execution=True))
    phase = f.StructuralPhase.MARKUP
    env = pipe.bind(hybrid, p, f.state(phase), f.context(p, f.at(57), phase))
    if dead_location:
        p.graph.terminate(sources[0])
    selected, denied = pipe.on_open(
        f.at(57), {f.PAIR: 190}, {f.PAIR: 100000}, (env,), research_authorized=True
    )
    assert bool(selected) is not dead_location and bool(denied) == dead_location


def test_pit_cannot_be_self_asserted_as_detector_geometry(f):
    p, c, sid, r = f.harmonic_source()
    claim = replace(r.membership, event_id="self-pit")
    p.graph.register(claim, (), origin="DETECTOR_GEOMETRY")
    with pytest.raises(ContractError, match="PIT_PAIR_CHECKPOINT_PERIOD_OR_SOURCE"):
        ContractProducer(p)._emit(r.thesis, pit_eligible=claim, stop_proof=r.stop_proof)


def test_h3_cannot_compose_mutated_parent_issue(f):
    p, c, count, r = f.elliott_source()
    bad = replace(r, event=freeze(dict(r.event, extra="forged")))
    with pytest.raises(ContractError, match="EMISSION_PAYLOAD_INTEGRITY"):
        c.h3(bad, r, pit_eligible=r.membership)


def test_graph_lps_original_value_not_scalar_is_required(f):
    p, c, r, pipe, campaign = staged_add(f)
    from spotbot.research.multi_school_fidelity.integration_v11.contracts import LpsAddProof

    original = r.add_proof.value
    scalar = p.source_claim(
        "forged-scalar-lps", 118.0, f.at(89), p.pair, (original.lps.event_id,), f.SHA
    )
    proof = LpsAddProof(
        scalar, original.stage_stop, original.fill_receipt, f.at(89), "cause", campaign
    )
    with pytest.raises(ContractError, match="TYPED_COMPLETED_LPS_BAR"):
        proof.evaluate(p.graph, r.thesis, p.pair, f.at(89))
