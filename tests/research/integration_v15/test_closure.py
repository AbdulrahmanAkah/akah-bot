"""Non-economic synthetic source-to-accounting and adversarial scope closure."""
import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.research.integration_v15.precommit import build, PROTOCOL
from spotbot.research.multi_school_fidelity.integration_v13.research_bridge import ResearchScope, ApproximateRule
from spotbot.research.multi_school_fidelity.integration_v15.router import Certificate as ProducerCertificate
from spotbot.research.multi_school_fidelity.integration_v15.authority import FUNDED, QUARANTINED, ReceiptGraph, dow_permission
from spotbot.research.multi_school_fidelity.integration_v15.bridge import ScopedExecution, ScopedPipeline, ScopedRouter
from spotbot.research.multi_school_fidelity.integration_v15.driver import ScopedDriver
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
    if arm is not None:
        portfolio.k.exit_cost_rate = freeze['contract']['costs_round_trip'][arm.split('|')[1]] / 2
    portfolio.rules = {f.PAIR: ApproximateRule(f.PAIR, scope)}
    execution = ScopedExecution(portfolio)
    pipe = ScopedPipeline(execution, ScopedRouter(scope, certificates))
    consumer = ScopedDriver(REPO, freeze, pipe, source, mechanics_only=True, arm=arm,
        certificate_provider=lambda now, frozen, g: (next(c for c in certificates if c.grammar == g),))
    return consumer


def permit(source, f, h):
    source.permission = dow_permission({f.PAIR}, {f.PAIR: f.at(h)}, f.at(h), "UP")


def source_arm(f, lineage, grammar):
    if grammar != FUNDED[-1]:
        # Reuse source-based native fixtures, not labels from historical trades.
        helpers = globals().get("_HELPERS")
        if helpers is None:
            path = REPO / "tests/research/integration_v13/test_guarded_driver.py"
            spec = importlib.util.spec_from_file_location("v15_nine_native_helpers", path)
            helpers = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(helpers)
            globals()["_HELPERS"] = helpers
        return helpers.source_arm(f, lineage, grammar)
    from spotbot.research.multi_school_fidelity.integration_v15.dow_source import DowStopProof
    from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import Binding, Mode
    from spotbot.research.multi_school_fidelity.akah_replay_ready_detectors_v1 import event_row
    p = f.CompletedPrefix(f.PAIR, f.SHA)
    # Five actual complete4H bars produce a genuine delayed secondary low.
    for h, low in zip(range(0,20,4), (100,99,90,98,100)):
        b = f.bar(h,105,110,low,106,degree="4H")
        p.on_close(b,1,b.end)
    for h in range(20):
        b = f.bar(h,105,110,100,106)
        p.on_close(b,1,b.end)
    point = next(q for q in p.points.values() if q.degree=="4H" and q.kind=="L")
    p.require_point(point,f.at(20))
    c = f.ContractProducer(p)
    binding = Binding(grammar,grammar,"dow-structure",f.SHA,"4H",f.at(20),point.price,point.event_id)
    proof = DowStopProof("DOW_CONFIRMED_SECONDARY_LOW",(point.event_id,))
    event = event_row(grammar,f.PAIR,f.at(20),"SECONDARY_RECONFIRMATION","THESIS_INTENT",True,
        {"owner_structure_id":"dow-structure","stop":point.price,"invalidation_source":point.event_id,
         "required_evidence_ids":(point.event_id,)})
    issue = c.seal_legacy(event,binding,proof,f.pit(p,f.at(20)))
    options = (("mode",Mode.TREND),("objectives",()),("valid_until",f.at(21)))
    helpers = _HELPERS
    return helpers.FrozenSource(f,c,issue,f.StructuralPhase.MARKUP,options), issue,20,115

@pytest.mark.parametrize("grammar", FUNDED)
@pytest.mark.parametrize("scenario", ("1X", "2X"))
def test_eighteen_cost_arms(helpers, f, grammar, scenario):
    fixture,lineage=f
    consumer,output=run_arm(helpers,fixture,lineage,grammar,scenario)
    rate=consumer.precommit["contract"]["costs_round_trip"][scenario]/2
    assert all(abs(x["fee"]-x["qty"]*x["price"]*rate)<1e-8 for x in output["fills"])

def test_admission_lease_expiry_not_owner_loss(helpers, f):
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Known
    from spotbot.research.multi_school_fidelity.integration_v9.sources import SourceNode
    fixture,lineage=f
    source,issue,h,price=source_arm(fixture,lineage,FUNDED[3])
    # Explicit entry lease, sealed before admission. Expiry alone must not
    # destroy an already admitted campaign's historical origin.
    eid=issue.membership.event_id
    old=source.producer.graph.nodes[eid]
    source.producer.graph.nodes[eid]=SourceNode(replace(old.evidence,valid_until=fixture.at(h+1)),old.parents,old.origin)
    issue=replace(issue,membership=source.producer.graph.nodes[eid].evidence)
    # Reseal the prospective fixture using actual public producer API.
    issue=source.producer.seal_legacy(dict(issue.event),issue.binding,issue.stop_proof,issue.membership)
    source.queue=(issue,)
    permit(source,fixture,h)
    consumer=make(helpers,fixture,source,arm=FUNDED[3]+"|2X")
    assert consumer.on_open(helpers.open_packet(fixture,h,price))[0]
    consumer.on_completed_hour(helpers.close_packet(fixture,fixture.bar(h,price,price+1,price-1,price)))
    permit(source,fixture,h+1)
    assert consumer._producer(fixture.PAIR,consumer.pipeline.execution.managers[1].binding) is source.producer

def run_arm(helpers, f, lineage, grammar, scenario="2X"):
    source, issue, h, price = source_arm(f, lineage, grammar)
    permit(source, f, h)
    consumer = make(helpers, f, source, arm=grammar + "|" + scenario)
    selected, denied = consumer.on_open(helpers.open_packet(f, h, price))
    assert len(selected) == 1 and not denied
    stop = consumer.pipeline.execution.managers[1].hard_stop
    # Controlled synthetic stop execution, not a historical/economic outcome.
    if grammar == FUNDED[2]:
        sid = issue.thesis.structure_id
        source.close_hook = lambda packet: (source.producer.harmonic_close(sid, packet.bars[0][1],
            pit_eligible=f.pit(source.producer.prefix, packet.bars[0][1].end)),)[:0]
        final = issue.thesis.objectives[-1]
        bar = f.bar(h, price, final+1, price-0.5, final)
    else:
        bar = f.bar(h, price, price + 1, stop - 1, stop)
    consumer.on_completed_hour(helpers.close_packet(f, bar))
    output = consumer.outputs()
    from spotbot.research.multi_school_fidelity.integration_v15.evaluation import campaign_records
    campaigns = campaign_records(consumer, output)
    assert len(campaigns) == 1 and campaigns[0]["grammar"] == grammar
    assert campaigns[0]["closed"] and campaigns[0]["final_exit_at"]
    assert set(output["fill_ledger"][0]) >= {"execution_phase", "arm", "campaign_id", "fee"}
    assert output["fill_ledger"][0]["execution_phase"] == "OPEN"
    assert output["fill_ledger"][-1]["execution_phase"] == "CLOSE"
    assert campaigns[0]["net_including_fees_and_terminal_mtm"] == pytest.approx(sum(x["cash_delta"] for x in output["fills"]))
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
    first, issue, h, price = source_arm(fixture, lineage, FUNDED[3])
    permit(first, fixture, h)
    consumer = make(helpers, fixture, first)
    for grammar in (FUNDED[3], FUNDED[1], FUNDED[6]):
        source, issue, h, price = source_arm(fixture, lineage, grammar)
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


@pytest.mark.parametrize("grammar", ("UNKNOWN", "LEGACY_UNBOUND"))
def test_unknown_scope_all_boundaries(helpers, f, grammar):
    fixture, lineage = f
    source, _, h, _ = source_arm(fixture, lineage, FUNDED[0])
    consumer = make(helpers, fixture, source)
    with pytest.raises(ContractError, match="UNBOUND"):
        consumer.pipeline.router.permission(grammar, fixture.state())
    fake = type("Fake", (), {"event": {"system_id": grammar}})()
    with pytest.raises(ContractError, match="UNBOUND"):
        consumer.pipeline.bind(fake)
    with pytest.raises(ContractError, match="UNBOUND"):
        consumer.pipeline.bind_legacy(fake)
    row = {"system_id": grammar}
    binding = type("Binding", (), {"grammar": grammar})()
    candidate = type("Candidate", (), {"row": row, "binding": binding})()
    with pytest.raises(ContractError, match="UNBOUND"):
        consumer.pipeline.on_open(fixture.at(h), {}, {}, (candidate,))
    with pytest.raises(ContractError, match="UNBOUND"):
        consumer.pipeline.execution.admit_owned(row, binding, fixture.at(h), 100, 1000, "c")
    with pytest.raises(ContractError, match="UNBOUND"):
        consumer.pipeline.execution.portfolio.k.admit(row)
    assert not consumer.pipeline.execution.portfolio.k.fills


@pytest.mark.parametrize("attack", ["receipt_death", "receipt_payload", "source_death", "source_tamper"])
def test_receipt_attack_after_bind(helpers, f, monkeypatch, attack):
    fixture, lineage = f
    source, issue, h, price = source_arm(fixture, lineage, FUNDED[0])
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
    from spotbot.research.multi_school_fidelity.integration_v15.authority import funded
    assert funded(issue.thesis.grammar)


def test_z_export_retained_receipts():
    assert set(EXPORT) == {*FUNDED, "MULTI_ARM"}
    # Authorized engineering evidence, never market/trade qualification output.
    path = REPO / "governance/all_nine_eighteen_arm_readiness_v15/e2e_receipts.json"
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(EXPORT, stream, sort_keys=True, indent=2)
        stream.write("\n")
