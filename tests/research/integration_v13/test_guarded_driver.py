"""Frozen synthetic packets only; no historical scheduler, data or economics."""

from __future__ import annotations

import copy
import importlib.util
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from scripts.research.integration_v13.economic_precommit import (
    GRAMMARS,
    ReadinessError,
    build_precommit,
)
from spotbot.research.multi_school_fidelity.integration_v11.contracts import Produced
from spotbot.research.multi_school_fidelity.integration_v12.pipeline import PipelineV12, RouterV12
from spotbot.research.multi_school_fidelity.integration_v13 import guarded_driver as driver
from spotbot.research.multi_school_fidelity.integration_v13.research_bridge import (
    ResearchPipeline,
    ResearchRouter,
    ResearchScope,
)
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError, Mode

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def lineage():
    path = Path(__file__).parents[1] / "integration_v12/test_lineage.py"
    spec = importlib.util.spec_from_file_location("v13_driver_frozen_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def f(lineage):
    return lineage.f.__wrapped__()


class FrozenSource:
    """Explicit synthetic packet injector, NOT a historical semantic generator."""

    def __init__(self, f, producer, issue=None, phase=None, options=()):
        self.f, self.producer = f, producer
        self.phase = phase or f.StructuralPhase.BASE_CANDIDATE
        self.options = options
        self.queue = () if issue is None else (issue,)
        self.feedback, self.calls = [], []
        self.close_hook = None

    def issues_at_open(self, at):
        self.calls.append(("OPEN", at))
        pending, self.queue = self.queue, ()
        return tuple(driver.SourceIssue(
            self.producer, issue, self.f.state(self.phase),
            self.f.context(self.producer.prefix, at, self.phase), self.options,
        ) for issue in pending)

    def on_completed_hour(self, packet):
        self.calls.append(("CLOSE", packet.bars[0][1].end))
        p = self.producer.prefix
        for (_, bar), (_, volume) in zip(packet.bars, packet.volumes, strict=True):
            if p.bar_id(bar) not in p.graph.nodes:
                p.on_close(bar, volume, bar.end)
        return () if self.close_hook is None else self.close_hook(packet)

    def producer_for(self, pair, structure_id):
        assert pair == self.producer.prefix.pair
        return self.producer

    def on_execution_receipt(self, receipt):
        self.calls.append(("RECEIPT", receipt.at))
        self.feedback.append(receipt)


def make_driver(f, source, **kwargs):
    pipe = PipelineV12(f.kernel(), RouterV12(synthetic_fixture_execution=True))
    return driver.GuardedDriver(
        REPO, build_precommit(REPO), pipe, source, synthetic_certification=True, **kwargs
    )


def open_packet(f, h, price, capacity=100000):
    return driver.OpenPacket(f.at(h), ((f.PAIR, price),), ((f.PAIR, capacity),))


def close_packet(f, bar):
    return driver.ClosePacket(((f.PAIR, bar),), ((f.PAIR, 1),))


def source_arm(f, lineage, grammar):
    phase, options = f.StructuralPhase.BASE_CANDIDATE, ()
    if grammar == GRAMMARS[0]:
        p, c, _, _, _, issue, _, _ = f.wyckoff_source(False)
        h, price = 89, 123
    elif grammar == GRAMMARS[1]:
        p, c, chain, issue = f.ict_source()
        options = (("session_end", chain.session_end),)
        h, price = 5, 110
    elif grammar == GRAMMARS[2]:
        p, c, _, issue = f.harmonic_source()
        h, price = 19, 213
    elif grammar == GRAMMARS[4]:
        p, c, _, issue = f.elliott_source()
        phase, h, price = f.StructuralPhase.MARKUP, 57, 190
    elif grammar == GRAMMARS[6]:
        p, c, chain, _ = f.ict_source()
        for h in range(5, 8):
            b = f.bar(h, 110, 112, 105, 111)
            p.on_close(b, 1, b.end)
        acceptance = f.bar(4, 110, 113, 104, 111, degree="4H")
        p.on_close(acceptance, 4, acceptance.end)
        parents = (p.bar_id(p.bars["1H"][0]),)
        daily = p.source_claim("daily", "UP", f.at(1), "market", parents, f.SHA)
        protected = p.source_claim("protected", 99.0, f.at(1), "s", parents, f.SHA)
        issue = c.ict_intent(
            chain, f.at(8), 111, f.TREND, pit_eligible=f.pit(p, f.at(8)),
            daily=daily, protected=protected, acceptance=acceptance,
        )
        phase, h, price = f.StructuralPhase.MARKUP, 8, 111
    elif grammar == GRAMMARS[7]:
        p, c, count, location = lineage.h3_parents(f)
        issue = c.h3(count, location, pit_eligible=count.membership)
        phase, h, price = f.StructuralPhase.MARKUP, 57, 190
    else:
        assert grammar in {GRAMMARS[3], GRAMMARS[5]}
        p = f.CompletedPrefix(f.PAIR, f.SHA)
        b = f.bar(0)
        p.on_close(b, 1, b.end)
        phase = f.StructuralPhase.MARKUP
        event, binding, _, proof = f.v10fixture.legacy(
            f, p, grammar, "s", f.at(1), b, f.state(phase)
        )
        c = f.ContractProducer(p)
        issue = c.seal_legacy(event, binding, proof, f.pit(p, f.at(1)))
        options = (("mode", Mode.TREND), ("objectives", ()), ("valid_until", f.at(2)))
        h, price = 1, 105
    return FrozenSource(f, c, issue, phase, options), issue, h, price


@pytest.mark.parametrize("grammar", GRAMMARS)
def test_all_eight_exact_source_issues_reach_actual_v12_guard(f, lineage, grammar):
    source, issue, h, price = source_arm(f, lineage, grammar)
    consumer = make_driver(f, source, arm=grammar + "|2X")
    selected, denied = consumer.on_open(open_packet(f, h, price))
    assert len(selected) == 1 and not denied
    execution = consumer.pipeline.execution
    assert len(execution.portfolio.k.fills) == 1
    guard = next(iter(execution.source_guards.values()))
    assert guard.issue is issue and guard.graph is source.producer.graph
    binding = execution.managers[1].binding
    assert binding.grammar == grammar and guard.binding == binding
    output = consumer.outputs()
    assert output["disposition"] == "SYNTHETIC_ONLY_NOT_ECONOMIC_EVIDENCE"
    assert not output["historical_exchange_rules_closed"]
    assert not output["independent_review_pass"]
    output["fills"].clear()
    assert execution.portfolio.k.fills


def test_elliott_derived_proof_sha_owner_update_not_raw_prefix_sha(f, lineage):
    source, issue, h, price = source_arm(f, lineage, GRAMMARS[4])
    assert issue.thesis.source_sha256 != source.producer.prefix.sha
    consumer = make_driver(f, source)
    assert consumer.on_open(open_packet(f, h, price))[0]
    updates = []

    def completed_owner(packet):
        end = packet.bars[0][1].end
        if end not in {f.at(60), f.at(64)}:
            return ()
        p = source.producer.prefix
        owner_bar = f.aggregate_completed(p.bars["1H"][-4:], "4H", end)
        p.on_close(owner_bar, 4, owner_bar.end)
        if end == f.at(60):
            # This bucket starts before admission: not an owned post-entry bar.
            return ()
        update = driver.OwnerUpdate(source.producer, issue.thesis.structure_id, owner_bar)
        updates.append(update)
        return (update,)

    source.close_hook = completed_owner
    for offset in range(7):
        b = f.bar(h + offset, price + offset, 192 + offset, 189 + offset, 191 + offset)
        if offset:
            consumer.on_open(open_packet(f, h + offset, b.open))
        consumer.on_completed_hour(close_packet(f, b))
    assert consumer.last_close == f.at(64) and len(updates) == 1
    assert consumer.pipeline.execution.managers[1].binding.source_sha256 == (
        issue.thesis.source_sha256
    )


@pytest.mark.parametrize("attack", ["wrong_producer", "forged_digest", "removed_emission"])
def test_owner_requires_exact_registered_producer_issue_guard(f, lineage, attack):
    source, issue, h, price = source_arm(f, lineage, GRAMMARS[4])
    consumer = make_driver(f, source)
    consumer.on_open(open_packet(f, h, price))
    b = f.bar(h, price, 192, 189, 191)
    original = source.producer
    if attack == "wrong_producer":
        # Even sharing prefix and copying emissions cannot replace the issuer.
        replacement = f.ContractProducer(original.prefix)
        replacement.emitted.update(original.emitted)
        source.producer = replacement
    elif attack == "forged_digest":
        guard = next(iter(consumer.pipeline.execution.source_guards.values()))
        identity = next(iter(consumer._entry_sources))
        bad = replace(guard.binding, source_sha256="b" * 64)
        consumer.pipeline.execution.managers[1].binding = bad
        consumer._entry_sources[identity] = (original, issue, bad)
    else:
        original.emitted.pop(digest(issue))
    source.close_hook = lambda packet: (
        driver.OwnerUpdate(source.producer, issue.thesis.structure_id, b),
    )
    before = copy.deepcopy(consumer.pipeline.execution.portfolio.k.fills)
    with pytest.raises(ContractError, match="ISSUED|GUARD"):
        consumer.on_completed_hour(close_packet(f, b))
    assert consumer.failed and consumer.pipeline.execution.portfolio.k.fills == before


def test_wyckoff_receipt_requires_actual_first_fill_clock_and_original_b0(f):
    p, c, _, issue, _, _, _, _ = f.v10fixture.spring_source(f)
    source = FrozenSource(f, c, issue)
    consumer = make_driver(f, source)
    assert not c.stage_campaign_receipts
    assert consumer.on_open(open_packet(f, 70, 100.4, 8000))[0]
    campaign = next(iter(consumer.pipeline.execution.portfolio.k.campaigns.values()))
    b0 = campaign.initial_risk_budget
    assert b0 > 0 and len(source.feedback) == 1
    receipt = c.stage_campaign_receipts[issue.thesis.structure_id]
    assert receipt == source.feedback[0].receipt and receipt.available_at == f.at(70)
    assert receipt.value == ("WYCKOFF_STAGE1_FILLED", source.feedback[0].campaign_id)
    consumer._feedback(f.at(70))
    assert len(source.feedback) == 1 and campaign.initial_risk_budget == b0


def test_harmonic_actual_closure_feedback_precedes_type_ii_issue(f):
    p, c, sid, first = f.harmonic_source()
    source = FrozenSource(f, c, first)
    consumer = make_driver(f, source)

    def harmonic_close(packet):
        b = packet.bars[0][1]
        emitted = c.harmonic_close(sid, b, pit_eligible=f.pit(p, b.end))
        if emitted is not None:
            source.queue = (emitted,)
        return ()

    source.close_hook = harmonic_close
    consumer.on_open(open_packet(f, 19, 213))
    assert not source.feedback and not c.type_i_completion_receipts
    final = first.thesis.objectives[1]
    consumer.on_completed_hour(close_packet(f, f.bar(19, 213, final + 1, 212, final)))
    assert not consumer.pipeline.execution.portfolio.k.positions
    assert len(source.feedback) == 1
    receipt = c.type_i_completion_receipts[sid]
    assert source.feedback[0].receipt == receipt and receipt.available_at == f.at(20)
    assert source.calls[-2:] == [("CLOSE", f.at(20)), ("RECEIPT", f.at(20))]
    consumer.on_open(open_packet(f, 20, 213))
    consumer.on_completed_hour(close_packet(f, f.bar(20, 213, 214, 209.95, 211)))
    consumer.on_open(open_packet(f, 21, 211))
    consumer.on_completed_hour(close_packet(f, f.bar(21, 211, 217, 210, 215)))
    second = source.queue[0]
    assert second.thesis.owner == "HARMONIC_TYPE_II"
    assert receipt.event_id in second.thesis.parents
    assert consumer.on_open(open_packet(f, 22, 215))[0]
    assert first.thesis.initial_invalidation == second.thesis.initial_invalidation


def test_shared_capacity_close_never_recredits_open_budget_or_fake_receipt(f):
    p, c, sid, first = f.harmonic_source()
    source = FrozenSource(f, c, first)
    consumer = make_driver(f, source)
    consumer.on_open(open_packet(f, 19, 213, 8000))
    opening = consumer.pipeline.execution.portfolio.k.fills[0]
    assert opening["qty"] * opening["price"] <= 8000
    assert consumer.remaining_capacity[f.PAIR] < 1e-8
    final = first.thesis.objectives[1]
    consumer.on_completed_hour(close_packet(f, f.bar(19, 213, final + 1, 212, final)))
    assert not source.feedback  # Target touch with no capacity is NOT actual closure.
    assert not c.type_i_completion_receipts
    assert consumer.pipeline.execution.portfolio.k.positions
    assert len(consumer.pipeline.execution.portfolio.k.fills) == 1


@pytest.mark.parametrize("attack", ["repeat_open", "future_open", "protected", "missing_bar",
                                      "wrong_open", "wrong_owner_degree", "repeat_close"])
def test_invalid_clock_or_owner_packet_fails_before_execution(f, lineage, attack):
    source, issue, h, price = source_arm(f, lineage, GRAMMARS[4])
    consumer = make_driver(f, source)
    consumer.on_open(open_packet(f, h, price))
    b = f.bar(h, price, 192, 189, 191)
    before = copy.deepcopy(consumer.pipeline.execution.portfolio.k.fills)
    if attack == "repeat_close":
        consumer.on_completed_hour(close_packet(f, b))
    with pytest.raises(ContractError):
        if attack == "repeat_open":
            consumer.on_open(open_packet(f, h, price))
        elif attack == "future_open":
            consumer.on_open(open_packet(f, h + 2, price))
        elif attack == "protected":
            consumer.on_open(replace(open_packet(f, h, price), at=f.at(h).replace(year=2024)))
        elif attack == "missing_bar":
            consumer.on_completed_hour(driver.ClosePacket((), ()))
        elif attack == "wrong_open":
            consumer.on_completed_hour(close_packet(f, replace(b, open=191)))
        elif attack == "wrong_owner_degree":
            source.close_hook = lambda packet: (
                driver.OwnerUpdate(source.producer, issue.thesis.structure_id, b),
            )
            consumer.on_completed_hour(close_packet(f, b))
        else:
            consumer.on_completed_hour(close_packet(f, b))
    assert consumer.failed and consumer.pipeline.execution.portfolio.k.fills == before
    with pytest.raises(ContractError, match="NO_AUTOMATIC_RETRY"):
        consumer.outputs()


def test_actual_kernel_rechecks_source_after_successful_preview(f, monkeypatch):
    p, c, _, issue = f.harmonic_source()
    consumer = make_driver(f, FrozenSource(f, c, issue))
    original = consumer.pipeline._bind

    def revoke_after_preview(candidate, now, prices, capacities):
        result = original(candidate, now, prices, capacities)
        assert result[0]
        p.graph.terminate(issue.emission_id)
        return result

    monkeypatch.setattr(consumer.pipeline, "_bind", revoke_after_preview)
    with pytest.raises(ContractError, match="INVALIDATED_SOURCE"):
        consumer.on_open(open_packet(f, 19, 213))
    assert not consumer.pipeline.execution.portfolio.k.fills


def test_forged_thesis_digest_fails_seal_before_fill(f):
    p, c, _, issue = f.elliott_source()
    forged = replace(issue, thesis=replace(issue.thesis, source_sha256="b" * 64))
    assert isinstance(forged, Produced)
    consumer = make_driver(f, FrozenSource(f, c, forged, f.StructuralPhase.MARKUP))
    with pytest.raises(ContractError, match="INTEGRITY|INVALIDATED_SOURCE"):
        consumer.on_open(open_packet(f, 57, 190))
    assert not consumer.pipeline.execution.portfolio.k.fills


def test_hash_scan_only_init_final_with_stat_check_every_event(f, monkeypatch):
    p, c, _, issue = f.harmonic_source()
    calls = []
    original = driver.verify_precommit

    def verified(*args):
        calls.append("full")
        return original(*args)

    monkeypatch.setattr(driver, "verify_precommit", verified)
    consumer = make_driver(f, FrozenSource(f, c, issue))
    consumer.on_open(open_packet(f, 19, 213))
    consumer.on_completed_hour(close_packet(f, f.bar(19, 213, 214, 212, 213)))
    assert calls == ["full"]
    consumer.outputs()
    assert calls == ["full", "full"]


@pytest.mark.parametrize("drift", ["size", "mtime", "replacement", "addition", "deletion"])
def test_any_source_stat_drift_full_verifies_then_denies_before_callback(f, monkeypatch, drift):
    p, c, _, issue = f.harmonic_source()
    source = FrozenSource(f, c, issue)
    consumer = make_driver(f, source)
    snapshot = dict(consumer._source_snapshot)
    key = next(iter(snapshot))
    if drift == "addition":
        snapshot["src/spotbot/new_source.py"] = (1, 2, 3, 4, 5)
    elif drift == "deletion":
        del snapshot[key]
    else:
        values = list(snapshot[key])
        values[{"size": 0, "mtime": 1, "replacement": 2}[drift]] += 1
        snapshot[key] = tuple(values)
    calls = []
    original = driver.verify_precommit
    monkeypatch.setattr(consumer, "_stat_sources", lambda: snapshot)
    monkeypatch.setattr(driver, "verify_precommit",
                        lambda *args: (calls.append("full"), original(*args))[1])
    with pytest.raises(ContractError, match="SOURCE_SNAPSHOT_DRIFT"):
        consumer.on_open(open_packet(f, 19, 213))
    assert calls == ["full"] and not source.calls
    assert not consumer.pipeline.execution.portfolio.k.fills


def test_final_full_hash_drift_cannot_be_hidden_by_unchanged_stat(f, monkeypatch):
    p, c, _, issue = f.harmonic_source()
    consumer = make_driver(f, FrozenSource(f, c, issue))
    monkeypatch.setattr(driver, "verify_precommit", lambda *args: {
        "valid": False, "blockers": ["RECURSIVE_SOURCE_HASH_DRIFT"],
    })
    with pytest.raises(ContractError, match="RECURSIVE_SOURCE_HASH_DRIFT"):
        consumer.outputs()


def test_real_market_path_never_accepts_fixture_router(f):
    p, c, _, issue = f.harmonic_source()
    pipe = PipelineV12(f.kernel(), RouterV12(synthetic_fixture_execution=True))
    with pytest.raises(ContractError, match="SEPARATE_RESEARCH_PIPELINE"):
        driver.GuardedDriver(REPO, build_precommit(REPO), pipe, FrozenSource(f, c, issue),
                             arm=GRAMMARS[2] + "|2X", certificate_provider=lambda *a: ())
    assert not pipe.execution.portfolio.k.fills


def test_real_research_missing_readiness_denied_before_producer_or_certificate(f):
    p, c, _, issue = f.harmonic_source()
    freeze = build_precommit(REPO)
    scope = ResearchScope(freeze["source_hashes"][driver.PROTOCOL_PATH],
                          freeze["source_version_sha256"])
    pipe = ResearchPipeline(f.kernel(), ResearchRouter(scope))
    source = FrozenSource(f, c, issue)
    certificates = []
    with pytest.raises(ReadinessError, match="ECONOMICS_DENIED"):
        driver.GuardedDriver(REPO, freeze, pipe, source, arm=GRAMMARS[2] + "|2X",
                             certificate_provider=lambda *a: certificates.append(a))
    assert not source.calls and not certificates and not pipe.execution.portfolio.k.fills


def test_frozen_arm_costs_cannot_be_swapped(f):
    p, c, _, issue = f.harmonic_source()
    with pytest.raises(ContractError, match="FROZEN_ARM_COST_PARITY"):
        make_driver(f, FrozenSource(f, c, issue), arm=GRAMMARS[2] + "|1X")


def test_packets_are_frozen_and_context_only_dow_has_no_arm(f):
    p, c, _, issue = f.harmonic_source()
    with pytest.raises(ContractError, match="ARM_NOT_IN_FIXED_PRECOMMIT"):
        make_driver(f, FrozenSource(f, c, issue), arm="DOW|2X")
    packet = open_packet(f, 19, 213)
    with pytest.raises(AttributeError):
        packet.at = f.at(20)
    consumer = make_driver(f, FrozenSource(f, c, issue))
    with pytest.raises(ContractError, match="FROZEN_PACKET_TUPLES"):
        consumer.on_open(replace(packet, prices=[(f.PAIR, 213)]))


def test_last_close_23utc_no_2024_hlc_or_invented_terminal_mark(f):
    at = f.T.replace(month=12, day=31, hour=22)
    p = f.CompletedPrefix(f.PAIR, f.SHA)
    previous = replace(f.bar(19, 213, 214, 212, 213),
                       start=at - timedelta(hours=1), end=at)
    p.on_close(previous, 1, at)
    source = FrozenSource(f, f.ContractProducer(p))
    consumer = make_driver(f, source)
    packet = driver.OpenPacket(at, ((f.PAIR, 213),), ((f.PAIR, 100000),))
    consumer.on_open(packet)
    b = replace(f.bar(19, 213, 214, 212, 213), start=at, end=at.replace(hour=23))
    consumer.on_completed_hour(close_packet(f, b))
    output = consumer.outputs()
    assert output["terminal_coverage"]["bounded_terminal_close_observed"] is True
    assert output["terminal_coverage"]["full_2023_terminal_hour_coverage"] is False
    assert output["equity"][-1]["time"] == at.replace(hour=23)
    calls_before = list(source.calls)
    with pytest.raises(ContractError, match="MISSING_TERMINAL_HOUR_NOT_EXECUTABLE"):
        consumer.on_open(replace(packet, at=at.replace(hour=23)))
    assert source.calls == calls_before
