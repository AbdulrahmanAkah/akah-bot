"""Synthetic native pivots/activity; supplied semantic labels are fixture facts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from spotbot.research.multi_school_fidelity.integration_v9.sources import CompletedPrefix
from spotbot.research.multi_school_fidelity.integration_v11.contracts import PitMembership
from spotbot.research.multi_school_fidelity.integration_v12.producers import ContractProducer
from spotbot.research.multi_school_fidelity.integration_v13.wyckoff_source import (
    WyckoffSource,
)
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Known, digest
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar, ContractError
from spotbot.research.multi_school_fidelity.wyckoff_contract_v8 import (
    Readiness,
    SpringStage,
    WyckoffContract,
    pnf_cause,
)

BASE = datetime(2022, 2, 1, tzinfo=UTC)
SHA = "b" * 64


def at(hour):
    return BASE + timedelta(hours=hour)


def fixture(*, staged=False, negative=None, degree="1H"):
    step = 1 if degree == "1H" else 4
    prefix = CompletedPrefix("SYNTH-WYCKOFF", SHA)
    anchors = ((-2, 148), (0, 150), (12, 130), (24, 140),
               (48, 100), (52, 118), (56, 105), (60, 120), (62, 112))
    for end in range(-2, 97):
        if end <= 62:
            for (a, va), (b, vb) in zip(anchors[:-1], anchors[1:], strict=True):
                if a <= end <= b:
                    value = va + (vb - va) * (end - a) / (b - a)
                    break
        else:
            value = 112 if end % 2 == 0 else 119
        op, hi, lo, cl, volume = value, value + .001, value - .001, value, 100
        if end in {0, 24, 52, 60}:
            hi = value
        if end in {48, 56}:
            lo = value
        if end == 88:
            op, hi, lo, cl, volume = 117, 120, 107, 112, 1000
        if end in {89, 90, 91}:
            op, hi, lo, cl, volume = 112, 113, 110, 112, 50
        if end == 92:
            op, hi, lo, cl, volume = 119, 125, 118, 123, 200
        if end in {93, 94, 95, 96}:
            op, hi, lo, cl, volume = 122, 124, 118, 123, 80
        if staged:
            if end == 84:
                op, hi, lo, cl, volume = 103, 113, 99, 112, 1000
            if end == 86:
                op, hi, lo, cl, volume = 119, 119.5, 118, 119, 50
            if end == 88:
                op, hi, lo, cl, volume = 119, 120, 118.5, 119.8, 60
        if negative == "outside_close" and end == 75:
            op, hi, lo, cl = 130, 131, 129, 130
        if negative == "lps_low" and end == 96:
            lo = 99
        if negative == "lps_volume" and end == 96:
            volume = 5000
        if negative == "sos_result" and end == 92:
            op, hi, lo, cl = 123, 125, 118, 119
        if negative == "no_supply_diminution":
            volume = 100
        bar = CompletedBar(at((end - 1) * step), at(end * step), degree, op, hi, lo, cl)
        prefix.on_close(bar, volume, bar.end)
    return prefix, step


def pivot(prefix, hour, step=1):
    return next(p for p in prefix.points.values() if p.observed_at == at(hour * step))


def fact(prefix, value, hour, sid, name, *, step=1):
    bar = next(b for b in prefix.bars["1H" if step == 1 else "4H"] if b.end == at(hour * step))
    return prefix.source_claim(digest(("SUPPLIED_SYNTHETIC_FIXTURE", sid, name)), value,
                               bar.end, sid, (prefix.bar_id(bar),), SHA)


def setup(prefix, *, reaccum=False, step=1):
    source = WyckoffSource(prefix)
    markup = fact(prefix, "MARKUP", 26, "separate-historical-fixture-range", "markup", step=step)
    swings = tuple(pivot(prefix, h, step) for h in (48, 52, 56, 60))
    cause = source.range_from_swings(swings, at(80 * step),
                                    branch="REACCUMULATION" if reaccum else "ACCUMULATION",
                                    prior_markup=markup if reaccum else None)
    market = fact(prefix, "UP", 70, "market", "market", step=step)
    rs = fact(prefix, 1.1, 70, cause.cause_id, "rs", step=step)
    # Explicit EXTERNAL fixture authorities, not outputs of any SC/price rule.
    events = tuple(fact(prefix, name, 70, cause.cause_id, name, step=step)
                   for name in ("PS", "SC", "ST", "DOWNSIDE_OBJECTIVE_MET")) if not reaccum else ()
    return source, cause, market, rs, events


def membership(prefix, hour, step=1):
    now = at(hour * step)
    value = PitMembership(prefix.pair, now, True, now, now + timedelta(hours=step))
    return fact(prefix, value, hour, prefix.pair, f"pit-{hour}", step=step)


@pytest.mark.parametrize("reaccum", (False, True))
@pytest.mark.parametrize("degree", ("1H", "4H"))
def test_complete_native_readiness_whole_cause_and_v12_binding(reaccum, degree):
    prefix, step = fixture(degree=degree)
    source, cause, market, rs, events = setup(prefix, reaccum=reaccum, step=step)
    now = at(96 * step)
    result = source.search(cause, now, market=market, rs=rs, branch_events=events)
    assert result.proofs
    intended = [p for p in result.proofs if isinstance(p.readiness, Readiness)
                and p.readiness.sos.bar.end == at(92 * step)
                and p.readiness.supply_test.bar.end == at(90 * step)]
    assert intended
    proof = intended[0]
    assert all(proof.readiness.evaluate(cause, now).values())
    assert proof.segments[0].start_at == cause.start_at == at(48 * step)
    assert proof.segments[-1].end_at == at(90 * step)
    assert proof.segments[0].available_at == at(90 * step)
    assert proof.bars[0].start == cause.start_at
    assert proof.bars[-1].end == at(90 * step)
    assert proof.count_line.available_at == now and proof.count_line.value == 118
    assert dict(proof.pnf) == pnf_cause(cause, proof.bars, proof.segments, proof.count_line, now)
    assert dict(proof.pnf)["minimum_objective"] > 138
    assert all(prefix.graph.live(s.event_id, now) for s in proof.segments)
    assert prefix.graph.nodes[proof.proof_id].evidence.value == proof
    if reaccum:
        event, = proof.readiness.branch_events
        assert event.value == "NEW_RANGE_SUPPLY_TEST"
        assert prefix.graph.nodes[event.event_id].origin == "DETECTOR_GEOMETRY"
        assert prefix.bar_id(proof.readiness.supply_test.bar) in prefix.graph.nodes[event.event_id].parents
        assert not any(prefix.graph.nodes[e].evidence.value == "SC"
                       for e in prefix.graph.nodes[event.event_id].parents)
    producer = ContractProducer(prefix)
    producer.start_wyckoff(cause, now)
    emission = producer.wyckoff_intent(cause.cause_id, now, 123, proof.readiness,
                                      proof.bars, proof.segments, proof.count_line,
                                      branch=proof.branch, pit_eligible=membership(prefix, 96, step))
    assert emission and emission.thesis.structure_id == cause.cause_id


def test_missing_downside_authority_does_not_turn_sc_into_true_or_block_reaccum():
    prefix, _ = fixture()
    source, cause, market, rs, events = setup(prefix)
    size = len(prefix.graph.nodes)
    result = source.search(cause, at(96), market=market, rs=rs, branch_events=events[:-1])
    assert not result.proofs
    assert dict(result.diagnostics)["MISSING_SEMANTIC_AUTHORITY:DOWNSIDE_OBJECTIVE_MET"] == 1
    assert dict(result.diagnostics)["ACCUMULATION_UNRESOLVED_SEMANTIC_AUTHORITY"] == 1
    assert len(prefix.graph.nodes) == size
    markup = fact(prefix, "MARKUP", 26, "historical-other", "markup-other")
    fresh = source.range_from_swings(tuple(pivot(prefix, h) for h in (48, 52, 56, 60)), at(96),
                                    branch="REACCUMULATION", prior_markup=markup)
    own_rs = fact(prefix, 1.1, 70, fresh.cause_id, "fresh-rs")
    assert source.search(fresh, at(96), market=market, rs=own_rs).proofs


def test_missing_market_rs_and_accumulation_labels_are_precise_diagnostics():
    prefix, _ = fixture()
    source, cause, _, _, _ = setup(prefix)
    result = source.search(cause, at(96))
    assert not result.proofs
    diagnostics = dict(result.diagnostics)
    for name in ("MARKET", "RS", "PS", "SC", "ST", "DOWNSIDE_OBJECTIVE_MET"):
        assert diagnostics[f"MISSING_SEMANTIC_AUTHORITY:{name}"] == 1


def test_reaccum_range_requires_bound_historical_markup_not_an_invented_parent():
    prefix, _ = fixture()
    source = WyckoffSource(prefix)
    result = source.range_candidates(at(80), start_at=at(48), branch="REACCUMULATION")
    assert result == type(result)((), (("MISSING_SEMANTIC_AUTHORITY:MARKUP", 1),))
    with pytest.raises(ContractError, match="PRIOR_MARKUP_REQUIRED"):
        source.range_from_swings(tuple(pivot(prefix, h) for h in (48, 52, 56, 60)), at(80),
                                 branch="REACCUMULATION")


def test_range_start_bounds_native_confirmation_and_idempotence():
    prefix, _ = fixture()
    source = WyckoffSource(prefix)
    assert not source.range_candidates(at(61), start_at=at(48)).causes
    with pytest.raises(ContractError, match="ACTUAL_BOUNDED_PREFIX_START_REQUIRED"):
        source.range_candidates(at(62), start_at=at(48) + timedelta(minutes=1))
    result = source.range_candidates(at(62), start_at=at(48))
    assert result.causes and all(c.start_at >= at(48) for c in result.causes)
    assert source.range_candidates(at(62), start_at=at(48)).causes == result.causes
    assert all(c.authority.available_at <= at(62) for c in result.causes)


@pytest.mark.parametrize("negative", ("outside_close", "lps_low", "lps_volume",
                                       "sos_result", "no_supply_diminution"))
def test_native_gates_and_whole_segment_coverage_are_not_weakened(negative):
    prefix, _ = fixture(negative=negative)
    source, cause, market, rs, events = setup(prefix)
    result = source.search(cause, at(96), market=market, rs=rs, branch_events=events)
    assert not result.proofs
    assert result.diagnostics


def test_actual_spring_stage_then_native_same_cause_add_without_fake_fill():
    prefix, _ = fixture(staged=True)
    source, cause, market, rs, events = setup(prefix)
    spring = source.search(cause, at(88), market=market, rs=rs, branch_events=events)
    intended = [p for p in spring.proofs if isinstance(p.readiness, SpringStage)
                and p.readiness.spring.bar.end == at(84) and p.readiness.test.bar.end == at(86)]
    assert intended
    proof = intended[0]
    contract = WyckoffContract(cause)
    assert contract.spring_intent(at(88), 119.8, proof.readiness, proof.bars,
                                  proof.segments, proof.count_line)
    later = source.search(cause, at(96), market=market, rs=rs, branch_events=events)
    readiness = next(p for p in later.proofs if isinstance(p.readiness, Readiness)
                     and p.readiness.sos.bar.end == at(92))
    instruction = contract.lps_add(at(96), 123, readiness.readiness, readiness.bars,
                                   readiness.segments, readiness.count_line)
    assert instruction["remaining_initial_fraction"] == .5
    assert instruction["campaign_initial_risk_budget_must_not_increase"]
    # Native instruction is NOT a V12 funded add; an actual receipt is still required.
    producer = ContractProducer(prefix)
    producer.start_wyckoff(cause, at(96))
    with pytest.raises(ContractError, match="WYCKOFF_ACTUAL_STAGE_FILL_RECEIPT_REQUIRED"):
        producer.wyckoff_add(cause.cause_id, at(96), 123, readiness.readiness,
                            readiness.bars, readiness.segments, readiness.count_line,
                            pit_eligible=membership(prefix, 96))


def test_repeat_memoized_sos_frames_and_proof_registration_are_idempotent():
    prefix, _ = fixture()
    source, cause, market, rs, events = setup(prefix)
    first = source.search(cause, at(96), market=market, rs=rs, branch_events=events)
    size, builds = len(prefix.graph.nodes), source.frame_builds
    assert source.search(cause, at(96), market=market, rs=rs, branch_events=events) == first
    assert len(prefix.graph.nodes) == size and source.frame_builds == builds


def test_immutable_range_activity_volume_and_supplied_semantic_lineage():
    prefix, _ = fixture()
    source, cause, market, rs, events = setup(prefix)
    with pytest.raises(ContractError, match="IMMUTABLE_OWNED_RANGE_CONSTRUCTION_REQUIRED"):
        source.search(replace(cause, support=99), at(96), market=market, rs=rs, branch_events=events)
    prefix.volumes["1H"][-1] += 1
    with pytest.raises(ContractError, match="SOURCE_BAR_OR_VOLUME_MUTATED"):
        source.search(cause, at(96), market=market, rs=rs, branch_events=events)
    prefix.volumes["1H"][-1] -= 1
    unsupported = Known("bare-label", "UP", at(70), SHA, "market")
    prefix.graph.register(unsupported, origin="SUPPLIED_SEMANTIC_PRODUCER")
    with pytest.raises(ContractError, match="ACTUAL_SOURCE_PARENTS_REQUIRED"):
        source.search(cause, at(96), market=unsupported, rs=rs, branch_events=events)


def test_branch_revocation_and_protected_clock_fail_closed():
    prefix, _ = fixture()
    source, cause, market, rs, events = setup(prefix)
    first = source.search(cause, at(96), market=market, rs=rs, branch_events=events)
    assert first.proofs
    prefix.graph.terminate(events[-1].event_id)
    assert not prefix.graph.live(first.proofs[0].proof_id, at(96))
    with pytest.raises(ContractError, match="UNBOUND_MUTATED_OR_INVALIDATED_SOURCE"):
        source.search(cause, at(96), market=market, rs=rs, branch_events=events)
    with pytest.raises(ContractError, match="PROTECTED_PERIOD"):
        source.search(cause, datetime(2024, 1, 1, tzinfo=UTC))


def test_historical_markup_revocation_propagates_without_inheriting_old_columns():
    prefix, _ = fixture()
    source, cause, market, rs, events = setup(prefix, reaccum=True)
    result = source.search(cause, at(96), market=market, rs=rs)
    assert result.proofs
    proof = result.proofs[0]
    assert all(b.start >= cause.start_at for b in proof.bars)
    assert cause.prior_markup.available_at < cause.start_at
    prefix.graph.terminate(cause.prior_markup.event_id)
    assert not prefix.graph.live(proof.proof_id, at(96))
    with pytest.raises(ContractError, match="UNBOUND_MUTATED_OR_INVALIDATED_SOURCE"):
        source.search(cause, at(96), market=market, rs=rs, branch_events=events)
