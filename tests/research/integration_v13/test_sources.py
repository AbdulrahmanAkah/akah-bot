from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from spotbot.research.multi_school_fidelity.integration_v12.producers import ContractProducer
from spotbot.research.multi_school_fidelity.integration_v13.auction_source import AuctionSource
from spotbot.research.multi_school_fidelity.integration_v13.harmonic_source import HarmonicSource
from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import (
    HistoricalFeed, MembershipSnapshot, MembershipSource,
)
from spotbot.research.multi_school_fidelity.integration_v13 import historical_inputs
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Point, Known
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar, ContractError

T = datetime(2023, 1, 2, 12, tzinfo=timezone.utc)
SHA = "A" * 64


def bar(h, o=100, hi=105, lo=95, c=100):
    return CompletedBar(T + timedelta(hours=h), T + timedelta(hours=h+1), "1H", o, hi, lo, c)


def feed():
    return HistoricalFeed("X-USDT", SHA)


def point(prefix, eid, kind, value, hour):
    p = Point(eid, kind, value, T + timedelta(hours=hour-2), T + timedelta(hours=hour), "1H")
    prefix.points[eid] = p
    prefix.graph.register(Known(eid, p, p.available_at, SHA, prefix.pair), origin="CONFIRMED_PIVOT")
    return p


def test_wrong_degree_is_not_an_hour():
    f = feed()
    b = CompletedBar(T, T+timedelta(hours=4), "4H",100,105,95,100)
    with pytest.raises(ContractError, match="HOURLY"):
        f.close_hour(b, 100)
    assert not f.prefix.graph.nodes


def test_auction_raid_mss_fvg_and_retrace_never_same_bar():
    f = feed()
    p = f.prefix
    producer = ContractProducer(p)
    source = AuctionSource(producer)
    membership = MembershipSource((MembershipSnapshot(T,T+timedelta(days=7),frozenset({p.pair}),SHA),))
    point(p,"LOW","L",100,3)
    point(p,"HIGH","H",110,3)
    # Completed prefix only; low raid below 100 then reclaim, later MSS >110,
    # three-bar imbalance then a *later* entry back below opposing 110.
    prices = [bar(0),bar(1),bar(2),bar(3,102,106,99,105),bar(4,106,115,105,114),
              bar(5,113,116,108,115),bar(6,111,112,107,109)]
    issued = []
    for b in prices:
        f.close_hour(b,100)
        issued.extend(source.close(b,membership.bind(p,b.end)))
        if b.start < T + timedelta(hours=6):
            assert not issued
    assert len(issued) == 1
    thesis = issued[0].thesis
    assert thesis.initial_invalidation == 99 and thesis.objectives == (110,)
    assert thesis.available_at == prices[-1].end
    a = next(iter(source.pending.values()))
    assert a.raid.end <= a.mss.start < a.fvg.available_at <= a.chain.retracement.start


def test_raid_stop_invalidates_pending_not_resurrected():
    f = feed()
    source = AuctionSource(ContractProducer(f.prefix))
    point(f.prefix,"LOW","L",100,3)
    point(f.prefix,"HIGH","H",110,3)
    membership = MembershipSource((MembershipSnapshot(T,T+timedelta(days=7),frozenset({f.prefix.pair}),SHA),))
    for b in [bar(0),bar(1),bar(2),bar(3,102,106,99,105)]:
        f.close_hour(b,100)
        source.close(b,membership.bind(f.prefix,b.end))
    sid = next(iter(source.pending))
    b = bar(4,101,103,98,99)
    f.close_hour(b,100)
    assert not source.close(b,membership.bind(f.prefix,b.end))
    assert sid in source.tombstones and sid not in source.pending


def test_harmonic_does_not_project_from_future_or_fake_completion():
    f = feed()
    producer = ContractProducer(f.prefix)
    source = HarmonicSource(producer)
    b = bar(0)
    f.close_hour(b,100)
    assert source.close(b,(),None) == []
    with pytest.raises(ContractError,match="REPEATED"):
        source.close(b,(),None)
    with pytest.raises((ContractError, AttributeError)):
        source.completed("missing","HARMONIC_TYPE_I",b.end,SimpleNamespace())


def test_precision_does_not_become_historical_tick():
    with pytest.raises(ContractError,match="PRECISION"):
        HarmonicSource(ContractProducer(feed().prefix), tick=.01)


def test_h2_auto_binding_uses_prior_confirmations_not_observed_extrema():
    from spotbot.research.multi_school_fidelity.integration_v9.sources import SourceGraph
    from spotbot.research.multi_school_fidelity.integration_v13.fast_prefix import FastCompletedPrefix
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest
    # Deliberately synthetic source graph: this verifies chronology, not a
    # historical producer/fidelity certificate.
    p=FastCompletedPrefix("X-USDT",SHA,SourceGraph())
    base=datetime(2023,1,1,tzinfo=timezone.utc)
    for n in range(1,8):
        d=CompletedBar(base+timedelta(days=n-1),base+timedelta(days=n),"1D",100,130,80,110)
        p.on_close(d,100,d.end)
    daily_points=[]
    for i,(kind,value) in enumerate((("L",90),("H",110),("L",95),("H",120))):
        at=base+timedelta(days=i+3)
        q=Point(digest((kind,i)),kind,value,at-timedelta(days=2),at,"1D")
        p.points[q.event_id]=q
        p.graph.register(Known(q.event_id,q,at,SHA,p.pair),
                         (p.bar_id(p.bars["1D"][i+2]),),origin="CONFIRMED_PIVOT")
        daily_points.append(q)
    start=base+timedelta(days=7)
    b=CompletedBar(start,start+timedelta(hours=4),"4H",110,125,105,120)
    p.on_close(b,100,b.end)
    low=Point("protected","L",100,start-timedelta(hours=8),start,"4H")
    p.points[low.event_id]=low
    p.graph.register(Known(low.event_id,low,start,SHA,p.pair),
                     (p.bar_id(p.bars["1D"][-1]),),origin="CONFIRMED_PIVOT")
    source=AuctionSource(ContractProducer(p))
    daily,protected,acceptance=source.htf_binding("owned-auction",b.end)
    assert daily.value=="UP" and protected.value==100 and acceptance==b
    assert daily.available_at<=b.start and protected.available_at==b.start
    # A future-confirmed newer low is not selected merely because its observed
    # timestamp happened before this acceptance.
    newer=Point("not-yet-known","L",108,start-timedelta(hours=4),b.end,"4H")
    p.points[newer.event_id]=newer
    p.graph.register(Known(newer.event_id,newer,b.end,SHA,p.pair),
                     (p.bar_id(b),),origin="CONFIRMED_PIVOT")
    assert source.htf_binding("owned-auction",b.end)[1].value==100


def test_repository_close_timestamp_is_not_shifted_forward(monkeypatch):
    import pandas as pd
    frame = pd.DataFrame([dict(timestamp=T,open=100.,high=105.,low=95.,close=102.,volume=10.)])
    monkeypatch.setattr(historical_inputs,"raw_frame",lambda *a,**kw:frame)
    rows = list(historical_inputs.historical_hours("unused","X-USDT",start=T-timedelta(hours=1),cutoff=T+timedelta(hours=2)))
    assert len(rows)==1
    assert rows[0][0].end==T and rows[0][0].start==T-timedelta(hours=1)
    assert not list(historical_inputs.historical_hours("unused","X-USDT",start=T,cutoff=T+timedelta(hours=2)))
