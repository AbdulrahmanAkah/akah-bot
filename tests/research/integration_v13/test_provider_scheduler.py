from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest

from spotbot.research.multi_school_fidelity.integration_v13.source_provider import SourceProvider
from spotbot.research.multi_school_fidelity.integration_v13.scheduler import BoundedScheduler
from spotbot.research.multi_school_fidelity.integration_v13 import scheduler
from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import MembershipSource,MembershipSnapshot
from spotbot.research.multi_school_fidelity.integration_v13.guarded_driver import ClosePacket
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar,ContractError

T=datetime(2022,1,1,tzinfo=timezone.utc)
SHA="A"*64

def bar(h,o=100,c=100):
    return CompletedBar(T+timedelta(hours=h),T+timedelta(hours=h+1),"1H",
                        o,max(o,c)+1,min(o,c)-1,c)

def provider(missing=False):
    members={"BTC-USDT","X-USDT"}|({"MISSING-USDT"} if missing else set())
    pit=MembershipSource((MembershipSnapshot(T,T+timedelta(days=365),frozenset(members),SHA),))
    return SourceProvider({"BTC-USDT":SHA,"X-USDT":SHA},pit,SHA)

def test_real_graph_provider_missing_semantics_never_become_positive():
    p=provider(True)
    for h in range(4):
        b=bar(h)
        packet=ClosePacket(tuple((x,b) for x in p.feeds),tuple((x,100.) for x in p.feeds))
        assert p.on_completed_hour(packet)==()
        assert p.issues_at_open(b.end)==()
    assert p.diagnostics["WYCKOFF_ACTUAL_BRANCH_AUTHORITIES_UNAVAILABLE"]==8
    assert any("DOW_PIT_MEMBER_SOURCE_UNAVAILABLE" in str(x) for x in p.dow_gaps)
    assert all(f.prefix.bars["4H"][-1].end==bar(3).end for f in p.feeds.values())

def test_provider_gap_and_reversed_clock_are_hard_failures():
    p=provider()
    def packet(h):
        return ClosePacket(tuple((x,bar(h)) for x in p.feeds),tuple((x,100.) for x in p.feeds))
    p.on_completed_hour(packet(0))
    with pytest.raises(ContractError,match="CLOCK_REVERSED"):
        p.on_completed_hour(packet(0))
    with pytest.raises(ContractError,match="GAP"):
        p.on_completed_hour(packet(2))

def test_owner_management_does_not_use_partly_pre_entry_htf_bucket():
    p=provider()
    binding=SimpleNamespace(structure_id="actual-owner",timeframe="4H",owner="CLASSICAL_PATTERN_OWNER")
    p.attach_execution(SimpleNamespace(
        managers={1:SimpleNamespace(binding=binding,entry_at=T+timedelta(hours=2))},
        portfolio=SimpleNamespace(k=SimpleNamespace(positions={1:{"episode":{"pair":"X-USDT"}}}))))
    updates=[]
    for h in range(8):
        packet=ClosePacket(tuple((x,bar(h)) for x in p.feeds),tuple((x,100.) for x in p.feeds))
        current=p.on_completed_hour(packet)
        if h<=3:assert current==()
        updates.extend(current)
    assert len(updates)==1 and updates[0].bar.start==T+timedelta(hours=4)

def test_scheduler_open_hides_current_path_and_uses_prior_capacity(monkeypatch):
    monkeypatch.setattr(scheduler,"LAST_OPEN",T)
    class Driver:
        source=SimpleNamespace(on_completed_hour=lambda p:None)
        def on_open(self,p):
            self.open=p
            assert not hasattr(p,"volumes") and not hasattr(p,"bars")
            assert dict(p.prices)=={"X-USDT":100}
            assert dict(p.capacity)=={"X-USDT":.005*24*10*100}
        def on_completed_hour(self,p):self.close=p
        def outputs(self):return "synthetic"
    # The current completed path is deliberately huge; it cannot affect open capacity.
    d=Driver()
    assert BoundedScheduler({"X-USDT":[*((bar(h),10.) for h in range(-24,0)),
                                        (bar(0,c=200),999999.)]}).run(d)=="synthetic"
    assert dict(d.close.volumes)["X-USDT"]==999999

@pytest.mark.parametrize("attack",["gap","protected","negative_volume"])
def test_scheduler_rejects_source_violations_before_callback(attack):
    rows=[(bar(0),10.),(bar(2),10.)] if attack=="gap" else (
         [(CompletedBar(scheduler.CUTOFF-timedelta(hours=1),scheduler.CUTOFF,"1H",100,101,99,100),10.)]
         if attack=="protected" else [(bar(0),-1.)])
    s=BoundedScheduler({"X-USDT":rows})
    if attack=="gap":s._next("X-USDT")
    with pytest.raises(ContractError):s._next("X-USDT")
