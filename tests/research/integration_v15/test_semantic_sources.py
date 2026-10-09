"""New V15 semantic producers tested on raw synthetic completed prefixes only."""
import importlib.util
from dataclasses import replace
from pathlib import Path
import pytest
from spotbot.research.multi_school_fidelity.integration_v13.fast_prefix import FastCompletedPrefix
from spotbot.research.multi_school_fidelity.integration_v15.wyckoff_source import WyckoffSource
from spotbot.research.multi_school_fidelity.integration_v15.elliott_source import ElliottSource, ConsecutiveProofSearch
from spotbot.research.multi_school_fidelity.integration_v15.producers import HistoricalProducer
from spotbot.research.multi_school_fidelity.integration_v15.dow_source import DowSource
from spotbot.research.multi_school_fidelity.integration_v14.authority import dow_permission
from spotbot.research.multi_school_fidelity.integration_v11.contracts import PitMembership
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Known, digest
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError, CompletedBar

ROOT = Path(__file__).parents[1]

def module(name):
    path = ROOT / "integration_v13" / name
    spec = importlib.util.spec_from_file_location("v15_source_fixture_"+name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

@pytest.mark.parametrize("mirror", (False, True))
def test_consecutive_elliott_actual_subdivision_source(mirror):
    f = module("test_elliott_source.py")
    prefix = f.w2_prefix(mirror=mirror)
    source = ElliottSource(prefix)
    result = source.search(f.at(60), legs=("W2",))
    assert result.counts
    assert all(c.correction.sign == (1 if mirror else -1) for c in result.counts)
    for count in result.counts:
        count.validate(f.at(60))
        producer = HistoricalProducer(prefix)
        producer.add_elliott_count(count, f.at(60))
        assert prefix.graph.live(count.count_id, f.at(60))
    assert source.search(f.at(60), legs=("W2",)).counts == result.counts

def test_consecutive_elliott_does_not_pad_missing_children():
    f = module("test_elliott_source.py")
    prefix = f.w2_prefix()
    point = f.point(prefix,"1H",0)
    prefix.graph.terminate(point.event_id)
    assert not ElliottSource(prefix).search(f.at(60), legs=("W2",)).counts

def wy_fixture(missing_objective=False):
    f = module("test_wyckoff_source.py")
    template, step = f.fixture(degree="4H")
    asset = FastCompletedPrefix("SYNTH-WY", f.SHA)
    leader = FastCompletedPrefix("BTC-USDT", "c"*64, asset.graph)
    source = WyckoffSource(asset, leader)
    for bar, volume in zip(template.bars["4H"], template.volumes["4H"], strict=True):
        idx = int((bar.end-f.BASE).total_seconds()/14400)
        if idx == 40:
            bar = replace(bar,open=120.,high=121.,low=111.,close=112.)
            volume = 1000.
        if idx == 48:
            bar = replace(bar,open=101.,high=103.,low=100.,close=101.)
            volume = 1200.
        if idx == 56:
            volume = 10.
        lead = replace(bar,open=100+(bar.open-100)*.001, high=100+(bar.high-100)*.001,
                       low=100+(bar.low-100)*.001, close=100+(bar.close-100)*.001)
        leader.on_close(lead, 100., lead.end)
        fresh = asset.on_close(bar, float(volume), bar.end)
        if missing_objective and idx == 48:
            for point in tuple(asset.points.values()):
                if point.kind == "H" and point.available_at < bar.start:
                    asset.graph.terminate(point.event_id)
        source.advance(bar,fresh)
    return f, asset, leader, source

def test_wyckoff_semantics_actual_raw_parents_to_native_intent():
    f, asset, leader, source = wy_fixture()
    now = f.at(96*4)
    bindings = source.bindings_at(now)
    assert bindings
    cause, market, rs, events = next(x for x in bindings if len(x[3]) == 4)
    assert tuple(e.value for e in events) == ("PS","SC","ST","DOWNSIDE_OBJECTIVE_MET")
    assert all(asset.graph.nodes[e.event_id].parents for e in events)
    projection = next(n.evidence for n in asset.graph.nodes.values()
                      if n.evidence.structure_id == asset.pair and isinstance(n.evidence.value,float)
                      and n.evidence.value < 130)
    assert projection.available_at < cause.start_at
    result = source.search(cause, now, market=market, rs=rs, branch_events=events)
    ready = [p for p in result.proofs if p.branch == "NO_SPRING_LPS"]
    assert ready
    proof = ready[0]
    producer = HistoricalProducer(asset)
    producer.start_wyckoff(cause,now)
    pit = asset.source_claim("synthetic-pit",PitMembership(asset.pair,now,True,now,f.at(100*4)),
                             now,asset.pair,(asset.bar_id(asset.bars["4H"][-1]),),f.SHA)
    issue = producer.wyckoff_intent(cause.cause_id,now,123.,proof.readiness,
        proof.bars,proof.segments,proof.count_line,branch=proof.branch,pit_eligible=pit)
    assert issue is not None
    source.recognize_markup(proof,now)
    lease = source.live_markup_at(now)
    assert lease.value == "MARKUP" and lease.valid_until == now+f.timedelta(hours=4)
    assert source.live_markup_at(now) == lease
    assert source.markup_fact is not None

def test_wyckoff_absent_objective_never_truthy_sc():
    f,asset,leader,source=wy_fixture(missing_objective=True)
    assert not source.active


def test_wyckoff_same_bar_double_extrema_abstain_not_crash(monkeypatch):
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Point
    import spotbot.research.multi_school_fidelity.integration_v15.wyckoff_source as implementation
    f,asset,leader,source=wy_fixture()
    source.active.clear()
    now=asset.bars["4H"][-1].end
    malformed=tuple(Point(str(i),kind,price,f.at(h),f.at(h+8),"4H")
        for i,(kind,price,h) in enumerate((("L",100.,12),("H",118.,16),("L",105.,16),("H",120.,20))))
    monkeypatch.setattr(implementation,"points_at",lambda *args:malformed)
    source.advance(asset.bars["4H"][-1],malformed)
    assert not source.active and source.diagnostics["NON_ORDERED_RANGE_SWINGS_ABSTAIN"]==1


def test_shared_market_context_has_exact_per_source_claim_namespace():
    f,asset,leader,source=wy_fixture()
    other=FastCompletedPrefix("SYNTH-OTHER","d"*64,asset.graph)
    second=WyckoffSource(other,leader)
    now=leader.bars["4H"][-1].end
    parents=(leader.bar_id(leader.bars["4H"][-1]),)
    first=source._claim("MARKET","UP",now,"market",parents)
    next_claim=second._claim("MARKET","UP",now,"market",parents)
    assert first.event_id!=next_claim.event_id and first.value==next_claim.value
    assert first.source_sha256==asset.sha and next_claim.source_sha256==other.sha
    assert source._claim("MARKET","UP",now,"market",parents)==first

def test_harmonic_invalidated_campaign_cannot_earn_type_ii():
    helper = module("test_guarded_driver.py")
    lineage=helper.lineage.__wrapped__()
    fixture=helper.f.__wrapped__(lineage)
    prefix,old,sid,issue=fixture.harmonic_source()
    producer=HistoricalProducer(prefix)
    producer.harmonics=old.harmonics
    pattern=producer.harmonics[sid]
    pattern.state="INVALIDATED"
    at=fixture.at(20)
    receipt=prefix.source_claim("actual-fixture-closure",("CAMPAIGN_CLOSED",issue.thesis.owner),
        at,sid,(prefix.bar_id(prefix.bars["1H"][-1]),),fixture.SHA)
    producer.acknowledge_harmonic_completion(sid,issue.thesis.owner,at,execution_receipt=receipt)
    assert pattern.state=="INVALIDATED" and sid not in producer.type_i_completion_receipts

def test_dow_actual_delayed_secondary_source_not_generic_buy():
    f=module("test_elliott_source.py")
    prefix=f.native_prefix({
        "1D":((0,100),(72,130),(144,110),(216,150),(288,120),(360,160)),
        "4H":((360,130),(376,170),(392,145),(408,180),(416,155),(432,190))})
    producer=HistoricalProducer(prefix)
    source=DowSource(producer)
    bar=next(b for b in prefix.bars["4H"] if b.end==f.at(428))
    now=bar.end
    pit=prefix.source_claim("dow-synthetic-membership",PitMembership(prefix.pair,now,True,f.at(0),f.at(500)),
        now,prefix.pair,(prefix.bar_id(bar),),f.SHA)
    permit=dow_permission({prefix.pair},{prefix.pair:now},now,"UP")
    emitted=source.close(bar,pit,permit)
    assert len(emitted)==1
    assert emitted[0].binding.initial_invalidation==155.
    assert emitted[0].binding.timeframe=="4H" and emitted[0].binding.owner==emitted[0].binding.grammar
    assert not source.close(bar,pit,permit)  # same immutable secondary structure consumed once
    assert not DowSource(producer).close(bar,pit,replace(permit,complete=False))

def test_harmonic_inside_owner_bar_completion_requires_later_retest():
    helper=module("test_guarded_driver.py")
    lineage=helper.lineage.__wrapped__()
    f=helper.f.__wrapped__(lineage)
    prefix,old,sid,issue=f.harmonic_source()
    producer=HistoricalProducer(prefix)
    producer.harmonics=old.harmonics
    pattern=producer.harmonics[sid]
    pattern.last_close=f.at(19)
    receipt=prefix.source_claim("intra-degree-closure",("CAMPAIGN_CLOSED",issue.thesis.owner),
        f.at(20),sid,(prefix.bar_id(prefix.bars["1H"][-1]),),f.SHA)
    producer.acknowledge_harmonic_completion(sid,issue.thesis.owner,f.at(20),execution_receipt=receipt)
    assert pattern.type1_complete_at==f.at(20) and pattern.last_close==f.at(19)
    assert producer.type_i_completion_receipts[sid]==receipt

def test_full_nine_source_installation_and_no_fixture_market_mode():
    from spotbot.research.multi_school_fidelity.integration_v15.source_provider import ScopedSourceProvider
    from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import MembershipSource, MembershipSnapshot
    from datetime import datetime, timezone, timedelta
    now=datetime(2022,1,1,tzinfo=timezone.utc)
    memberships=MembershipSource((MembershipSnapshot(now,now+timedelta(days=1),frozenset({"BTC-USDT"}),"a"*64),))
    provider=ScopedSourceProvider({"BTC-USDT":"a"*64},memberships,"b"*64)
    assert set(provider.sources["BTC-USDT"])=={"ict","classical","harmonic","elliott","wyckoff","dow"}
    assert isinstance(provider.producers["BTC-USDT"],HistoricalProducer)
    assert provider.sources["BTC-USDT"]["wyckoff"].leader is provider.feeds["BTC-USDT"].prefix
