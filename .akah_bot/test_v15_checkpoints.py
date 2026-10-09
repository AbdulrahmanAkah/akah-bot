from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest

import v15_bounded_storage as storage
import v15_checkpoints as checkpoints
from spotbot.research.multi_school_fidelity.integration_v15.source_provider import ScopedSourceProvider
from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import MembershipSnapshot,MembershipSource
from spotbot.research.multi_school_fidelity.integration_v13.guarded_driver import ClosePacket
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest


def provider():
    storage.install()
    start=datetime(2021,9,1,tzinfo=timezone.utc)
    members=MembershipSource((MembershipSnapshot(start,datetime(2024,1,1,tzinfo=timezone.utc),
                                  frozenset({'BTC-USDT','ETH-USDT'}),'A'*64),))
    return ScopedSourceProvider({'BTC-USDT':'B'*64,'ETH-USDT':'C'*64},members,'D'*64)


def advance(p,first,last):
    start=datetime(2021,9,1,tzinfo=timezone.utc)
    for i in range(first,last):
        at=start+timedelta(hours=i)
        price=100.+(i%12)*.5
        bar=CompletedBar(at,at+timedelta(hours=1),'1H',price,price+2.,price-2.,price+1.)
        p.on_completed_hour(ClosePacket((('BTC-USDT',bar),('ETH-USDT',bar)),
                                        (('BTC-USDT',100.),('ETH-USDT',80.))))


def signature(p):
    graph=p.feeds['BTC-USDT'].prefix.graph
    return digest((tuple(graph.nodes.items()),p.queue,p.permission,p.diagnostics,
                   tuple((name,tuple(f.prefix.points.items()),list(f.prefix.bars['1H'])) for name,f in p.feeds.items())))


def test_live_source_checkpoint_then_resume_exact_no_future_archive(tmp_path):
    p=provider();advance(p,0,24)
    authority={'precommit':'D'*64,'source':'A'*64,'arm':'SYNTHETIC_SOURCE_ONLY','completed_close':str(p.last_close)}
    path=checkpoints.write_checkpoint(tmp_path,{'source':p,'cursor':p.last_close},authority)
    expected=signature(p)
    # Further registrations in the original live graph must NOT enter the
    # checkpoint's immutable archive and cause false future duplicate IDs.
    advance(p,24,36)
    restored=checkpoints.read_checkpoint(path,authority)['source']
    assert signature(restored)==expected
    assert restored.feeds['ETH-USDT'].prefix.graph is restored.feeds['BTC-USDT'].prefix.graph
    assert restored.feeds['BTC-USDT'].prefix.graph.nodes.owner is restored.feeds['BTC-USDT'].prefix.graph
    advance(restored,24,36)
    assert signature(restored)==signature(p)
    twice=checkpoints.read_checkpoint(path,authority)['source']
    assert signature(twice)==expected


def test_checkpoint_hash_and_authority_tamper_fail_closed(tmp_path):
    path=checkpoints.write_checkpoint(tmp_path,{'clock':'test'},{'source':'A'})
    with pytest.raises(RuntimeError,match='AUTHORITY_DRIFT'):
        checkpoints.read_checkpoint(path,{'source':'B'})
    import json
    state=Path(json.loads(path.read_text())['state_path']);state.write_bytes(b'NOT_THE_SAVED_STATE')
    with pytest.raises(RuntimeError,match='CONTENT_OR_PATH_DRIFT'):
        checkpoints.read_checkpoint(path,{'source':'A'})
