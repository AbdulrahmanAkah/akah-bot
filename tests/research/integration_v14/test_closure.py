"""Non-economic synthetic source-to-accounting and adversarial scope closure."""
import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.research.integration_v14.precommit import build, PROTOCOL
from spotbot.research.multi_school_fidelity.integration_v13.research_bridge import ResearchScope, ApproximateRule, ProducerCertificate
from spotbot.research.multi_school_fidelity.integration_v14.authority import FUNDED, QUARANTINED, ReceiptGraph, dow_permission
from spotbot.research.multi_school_fidelity.integration_v14.bridge import ScopedExecution, ScopedPipeline, ScopedRouter
from spotbot.research.multi_school_fidelity.integration_v14.driver import ScopedDriver
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError

REPO = Path(__file__).resolve().parents[3]
EXPORT = {}


@pytest.fixture
def helpers():
    path = REPO / "tests/research/integration_v13/test_guarded_driver.py"
    spec = importlib.util.spec_from_file_location("v14_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def f(helpers):
    lineage = helpers.lineage.__wrapped__()
    return helpers.f.__wrapped__(lineage), lineage


def make(helpers, f, source, *, arm=None):
    freeze = build(REPO)
    scope = ResearchScope(freeze["source_hashes"][PROTOCOL], freeze["source_version_sha256"])
    certificates = tuple(ProducerCertificate(g, scope.source_version_sha256, scope.protocol_sha256,
        "a" * 64, "SOURCE_BOUND_RESEARCH_IMPLEMENTATION_PASS",
        "SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION") for g in FUNDED)
    portfolio = f.kernel().portfolio
    portfolio.rules = {f.PAIR: ApproximateRule(f.PAIR, scope)}
    execution = ScopedExecution(portfolio)
    pipe = ScopedPipeline(execution, ScopedRouter(scope, certificates))
    consumer = ScopedDriver(REPO, freeze, pipe, source, mechanics_only=True, arm=arm,
        certificate_provider=lambda now, frozen, g: (next(c for c in certificates if c.grammar == g),))
    return consumer


def permit(source, f, h):
    source.permission = dow_permission({f.PAIR}, {f.PAIR: f.at(h)}, f.at(h), "UP")


def run_arm(helpers, f, lineage, grammar):
    source, issue, h, price = helpers.source_arm(f, lineage, grammar)
    permit(source, f, h)
    consumer = make(helpers, f, source, arm=grammar + "|2X")
    selected, denied = consumer.on_open(helpers.open_packet(f, h, price))
    assert len(selected) == 1 and not denied
    stop = consumer.pipeline.execution.managers[1].hard_stop
    # Controlled synthetic stop execution, not a historical/economic outcome.
    bar = f.bar(h, price, price + 1, stop - 1, stop)
    consumer.on_completed_hour(helpers.close_packet(f, bar))
    output = consumer.outputs()
    assert not consumer.pipeline.execution.portfolio.k.positions
    assert {x["side"] for x in output["fills"]} == {"BUY", "SELL"}
    return consumer, output


@pytest.mark.parametrize("grammar", FUNDED)
def test_funded_e2e(helpers, f, grammar):
    fixture, lineage = f
    consumer, output = run_arm(helpers, fixture, lineage, grammar)
    kinds = {r.kind for r in consumer.trace.nodes.values()}
    assert {"SOURCE_EVIDENCE", "SEMANTIC_PRODUCER", "EMISSION_SEAL", "SELECTOR_ADMISSION",
            "EXECUTION_FILL", "OWNER_UPDATE", "LIFECYCLE_EXECUTION", "ACCOUNTING_OUTPUT"} <= kinds
    EXPORT[grammar] = {"graph": output["receipt_graph"], "terminal_receipt": output["accounting_receipt"]}
    restored = ReceiptGraph.restore(output["receipt_graph"])
    assert restored.verify(output["accounting_receipt"], fixture.at(100))


def test_multi_arm_e2e(helpers, f):
    # One portfolio, three sequential campaigns, never a sum of independent books.
    fixture, lineage = f
    first, issue, h, price = helpers.source_arm(fixture, lineage, FUNDED[1])
    permit(first, fixture, h)
    consumer = make(helpers, fixture, first)
    for grammar in (FUNDED[1], FUNDED[0], FUNDED[2]):
        source, issue, h, price = helpers.source_arm(fixture, lineage, grammar)
        permit(source, fixture, h)
        consumer.source = source
        # Fill empty hours with no candidate; the injected fixture remains explicit.
        if consumer.last_close is not None:
            while consumer.last_close < fixture.at(h):
                at = int((consumer.last_close - fixture.T).total_seconds() / 3600)
                saved = source.queue
                source.queue = ()
                permit(source, fixture, at)
                consumer.on_open(helpers.open_packet(fixture, at, price))
                consumer.on_completed_hour(helpers.close_packet(fixture, fixture.bar(at, price, price+1, price-1, price)))
                source.queue = saved
        permit(source, fixture, h)
        assert consumer.on_open(helpers.open_packet(fixture, h, price))[0]
        manager = next(iter(consumer.pipeline.execution.managers.values()))
        stop = manager.hard_stop
        consumer.on_completed_hour(helpers.close_packet(fixture, fixture.bar(h, price, price+1, stop-1, stop)))
    output = consumer.outputs()
    assert len(consumer.pipeline.execution.portfolio.k.campaigns) == 3
    assert len(output["fills"]) == 6
    EXPORT["MULTI_ARM"] = {"graph": output["receipt_graph"], "terminal_receipt": output["accounting_receipt"]}


@pytest.mark.parametrize("grammar", tuple(QUARANTINED) + ("UNKNOWN",))
def test_quarantine_all_boundaries(helpers, f, grammar):
    fixture, lineage = f
    source, _, h, _ = helpers.source_arm(fixture, lineage, FUNDED[0])
    consumer = make(helpers, fixture, source)
    with pytest.raises(ContractError, match="QUARANTINED"):
        consumer.pipeline.router.permission(grammar, fixture.state())
    fake = type("Fake", (), {"event": {"system_id": grammar}})()
    with pytest.raises(ContractError, match="QUARANTINED"):
        consumer.pipeline.bind(fake)
    with pytest.raises(ContractError, match="QUARANTINED"):
        consumer.pipeline.bind_legacy(fake)
    row = {"system_id": grammar}
    binding = type("Binding", (), {"grammar": grammar})()
    candidate = type("Candidate", (), {"row": row, "binding": binding})()
    with pytest.raises(ContractError, match="QUARANTINED"):
        consumer.pipeline.on_open(fixture.at(h), {}, {}, (candidate,))
    with pytest.raises(ContractError, match="QUARANTINED"):
        consumer.pipeline.execution.admit_owned(row, binding, fixture.at(h), 100, 1000, "c")
    with pytest.raises(ContractError, match="QUARANTINED"):
        consumer.pipeline.execution.portfolio.k.admit(row)
    assert not consumer.pipeline.execution.portfolio.k.fills


@pytest.mark.parametrize("attack", ["receipt_death", "receipt_payload", "source_death", "source_tamper"])
def test_receipt_attack_after_bind(helpers, f, monkeypatch, attack):
    fixture, lineage = f
    source, issue, h, price = helpers.source_arm(fixture, lineage, FUNDED[0])
    permit(source, fixture, h)
    consumer = make(helpers, fixture, source)
    original = consumer.pipeline._bind
    def attacked(candidate, now, *args, **kwargs):
        result = original(candidate, now, *args, **kwargs)
        assert result[0]
        rid = consumer.pipeline.execution.admission_receipts[candidate.row["identity"]]
        if attack == "receipt_death":
            consumer.trace.terminate(consumer.trace.nodes[rid].parents[0])
        elif attack == "receipt_payload":
            consumer.trace.nodes[rid] = replace(consumer.trace.nodes[rid], payload_json="{}")
        elif attack == "source_death":
            source.producer.graph.terminate(issue.emission_id)
        else:
            source.producer.emitted.clear()
            guard = consumer.pipeline.execution.source_guards[candidate.row["identity"]]
            consumer.pipeline.execution.source_guards[candidate.row["identity"]] = replace(guard, row=())
        return result
    monkeypatch.setattr(consumer.pipeline, "_bind", attacked)
    with pytest.raises(ContractError):
        consumer.on_open(helpers.open_packet(fixture, h, price))
    assert not consumer.pipeline.execution.portfolio.k.fills


@pytest.mark.parametrize("kind", ["OWNER_UPDATE", "ACCOUNTING_OUTPUT"])
def test_owner_accounting_tamper(helpers, f, kind):
    fixture, lineage = f
    consumer, output = run_arm(helpers, fixture, lineage, FUNDED[0])
    rid = next(k for k, r in consumer.trace.nodes.items() if r.kind == kind)
    consumer.trace.nodes[rid] = replace(consumer.trace.nodes[rid], payload_json="{}");
    with pytest.raises(ContractError, match="TAMPER"):
        consumer.trace.verify(output["accounting_receipt"], fixture.at(100))


def test_incomplete_dow_never_permissive():
    from datetime import datetime, timezone
    at = datetime(2023, 1, 1, tzinfo=timezone.utc)
    frame = {"BTC-USDT": at, "X-USDT": at}
    assert dow_permission(set(frame), frame, at, "UP").permits(at)
    assert not dow_permission(set(frame), {"BTC-USDT": at}, at, "UP").permits(at)
    assert dow_permission(set(frame), {"BTC-USDT": at}, at, "BALANCED").direction == "UNKNOWN"


def test_abc_parent_death(f):
    # Existing named motive proof path stays unchanged; the entire uncertified
    # Elliott/ABC funded path is denied in this freeze, including after parent death.
    fixture, _ = f
    prefix, producer, count, issue = fixture.elliott_source()
    from spotbot.research.multi_school_fidelity.integration_v11.contracts import verify_issue
    verify_issue(issue, prefix.graph, issue.thesis.available_at)
    parent = prefix.graph.nodes[issue.emission_id].parents[0]
    prefix.graph.terminate(parent)
    with pytest.raises(ContractError):
        verify_issue(issue, prefix.graph, issue.thesis.available_at)
    from spotbot.research.multi_school_fidelity.integration_v14.authority import funded
    with pytest.raises(ContractError, match="QUARANTINED"):
        funded(issue.thesis.grammar)


def test_z_export_retained_receipts():
    assert set(EXPORT) == {*FUNDED, "MULTI_ARM"}
    # Authorized engineering evidence, never market/trade qualification output.
    path = REPO / "governance/final_authority_gaps_to_replay_ready_v1/e2e_receipts.json"
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(EXPORT, stream, sort_keys=True, indent=2)
        stream.write("\n")
