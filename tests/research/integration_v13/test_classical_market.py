from datetime import datetime,timedelta,timezone

import pandas as pd
import pytest

from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as native
from spotbot.research.multi_school_fidelity.integration_v13.classical_source import ClassicalSource
from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import HistoricalFeed,MembershipSnapshot,MembershipSource
from spotbot.research.multi_school_fidelity.integration_v13.market_source import MarketSource
from spotbot.research.multi_school_fidelity.integration_v13.producers import HistoricalProducer
from spotbot.research.multi_school_fidelity.integration_v9.sources import SourceGraph
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Known
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar,ContractError

T=datetime(2023,1,1,tzinfo=timezone.utc)
SHA="A"*64


def setup():
    feed=HistoricalFeed("X-USDT",SHA)
    producer=HistoricalProducer(feed.prefix)
    source=ClassicalSource(producer)
    membership=MembershipSource((MembershipSnapshot(T,T+timedelta(days=365),frozenset({"X-USDT"}),SHA),))
    for h in range(40):
        b=CompletedBar(T+timedelta(hours=h),T+timedelta(hours=h+1),"1H",100,105,95,100)
        feed.close_hour(b,100)
    p=native.ClassicalPattern("synthetic","RECTANGLE",110,90,20,"RANGE",pd.Timestamp(T+timedelta(hours=40)))
    # An explicit synthetic native mature pattern, not a historical certificate.
    sid="owned-pattern"
    claim=producer._claim(sid,p,T+timedelta(hours=40),sid,(feed.prefix.bar_id(feed.prefix.bars["4H"][-1]),))
    source.runtime.mature(p)
    source.metadata[p.pattern_id]=dict(mature=9,breakout=None,sid=sid,claim=claim)
    return feed,source,membership


def close_h4(feed,source,membership,at,lo,hi,close):
    for h in range(at,at+4):
        b=CompletedBar(T+timedelta(hours=h),T+timedelta(hours=h+1),"1H",close,hi,lo,close)
        fresh=feed.close_hour(b,100)
    return source.close(feed.prefix.bars["4H"][-1],(),membership.bind(feed.prefix,b.end))


def test_native_breakout_later_retest_local_stop_and_h1_abstention():
    f,s,m=setup()
    assert not close_h4(f,s,m,40,100,116,115)
    result=close_h4(f,s,m,44,109,114,112)
    assert len(result)==1
    e=result[0]
    assert e.binding.initial_invalidation==109 # not old frozen support=90
    assert e.objectives[0].price==130
    assert e.issue.event["system_id"]=="FS_CLASSICAL_FULL_LONG"
    assert any("H1_NATIVE_MARKUP_OWNER_UNAVAILABLE" in row for row in s.diagnostics)


def test_support_failure_is_absorbing_not_fixed_by_reclaim():
    f,s,m=setup()
    assert not close_h4(f,s,m,40,100,116,115)
    assert not close_h4(f,s,m,44,89,114,112)
    assert "synthetic" not in s.runtime.pending
    assert "owned-pattern" in f.prefix.graph.terminated


def test_market_missing_daily_and_complete_pit_members_cannot_be_true():
    graph=SourceGraph()
    a=HistoricalFeed("BTC-USDT",SHA,graph)
    b=HistoricalFeed("X-USDT",SHA,graph)
    row=CompletedBar(T,T+timedelta(hours=1),"1H",100,105,95,100)
    a.close_hour(row,100)
    b.close_hour(row,100)
    source=MarketSource({"BTC-USDT":a.prefix,"X-USDT":b.prefix},"BTC-USDT",SHA)
    state,claim=source.router("X-USDT",row.end)
    assert not state.data_authority_valid and not state.major_protected_structure_valid
    assert claim.available_at==row.end
    with pytest.raises(ContractError,match="MEMBER_SOURCE_UNAVAILABLE"):
        source.dow(("BTC-USDT","X-USDT","MISSING-USDT"),row.end)
    with pytest.raises(ContractError,match="CONTEMPORANEOUS"):
        source.dow(("BTC-USDT","X-USDT"),row.end)
