"""Read one SHA-bound owned warmup checkpoint; no market/replay/economics."""
from v15_resource_guard import ResourceGuard, ROOT, resources
guard=ResourceGuard('saved_v15_warmup_heap_forensic').start()
import json
import sys
from collections import Counter, deque
from types import ModuleType, FunctionType
from pathlib import Path
import v15_disk_history
v15_disk_history.install()
import cache_budget_v15
cache_budget_v15.install()
from v15_checkpoints import read_checkpoint, sha


def measure(value):
    stack=[value];seen=set();sizes=Counter();counts=Counter()
    while stack:
        v=stack.pop()
        if id(v) in seen:continue
        seen.add(id(v))
        if isinstance(v,(type,ModuleType,FunctionType)):continue
        name=type(v).__module__+'.'+type(v).__qualname__
        sizes[name]+=sys.getsizeof(v);counts[name]+=1
        if isinstance(v,dict):
            for k,x in v.items():stack.extend((k,x))
        elif isinstance(v,(tuple,list,set,frozenset,deque)):stack.extend(v)
        elif hasattr(v,'__dict__'):stack.append(v.__dict__)
    return {'python_bytes':sum(sizes.values()),'unique_objects':len(seen),
        'types':[{'type':t,'bytes':s,'objects':counts[t]} for t,s in sizes.most_common(20)]}


def main():
    pointer=json.loads((ROOT/'.akah_bot/v15_recoverable_session/FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json').read_text())
    path=Path(pointer['receipt']).resolve()
    if (not path.is_relative_to(ROOT/'.akah_bot/v15_recoverable_session') or sha(path)!=pointer['sha256']):
        raise RuntimeError('TRUSTED_CHECKPOINT_POINTER_REQUIRED')
    receipt=json.loads(path.read_text())
    a=receipt['authority']
    if (a['task_id']!='AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15' or
        a['supplemental_certificate_sha256']!='54F33506031847D794BBF40CB81D19BA03E41D5DA1E11EB1084DDE1A5E86D77A'):
        raise RuntimeError('EXACT_OWNED_CHECKPOINT_AUTHORITY_REQUIRED')
    before=resources()
    saved=read_checkpoint(path,a)
    driver=saved['driver'];provider=driver.source
    if saved['scheduler']['cursor'].year!=2021 or driver.pipeline.execution.portfolio.k.positions:
        raise RuntimeError('ONLY_WARMUP_BEFORE_ECONOMIC_DECISIONS_ALLOWED')
    after=resources()
    overall=measure(provider)
    graph=provider.feeds['BTC-USDT'].prefix.graph
    searches=[s['elliott']._search for s in provider.sources.values() if s['elliott']._search is not None]
    report={'scope':'SHA_BOUND_SAVED_WARMUP_HEAP_ONLY_NO_NEW_MARKET_OR_ECONOMIC_ROWS',
        'cursor':str(saved['scheduler']['cursor']),'checkpoint_sha256':pointer['sha256'],
        'before_restore':before,'after_restore':after,'overall_provider_python_heap':overall,
        'source_nodes':len(graph.nodes),'mutable_nodes':len(graph.nodes.mutable),
        'prefix_points':sum(len(f.prefix.points) for f in provider.feeds.values()),
        'groups_overlap_not_additive':True,'groups':{
            'mutable_archive_nodes':measure(graph.nodes.mutable),
            'prefix_point_stores':measure([f.prefix.points for f in provider.feeds.values()]),
            'elliott_searches':measure(searches),
            'harmonic_contracts':measure([p.harmonics for p in provider.producers.values()]),
            'harmonic_seen_keys':measure([s['harmonic'].seen for s in provider.sources.values()]),
            'volume_histories':measure([f.prefix.volumes for f in provider.feeds.values()])},
        'economic_replay_executed':False,'2024_rows_accessed':False,'2025_rows_accessed':False}
    (ROOT/'.akah_bot/v15_saved_warmup_heap_forensic.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'groups','overall_provider_python_heap'}}),flush=True)
    print('TOP_PROVIDER_TYPES='+json.dumps(overall['types'][:8]),flush=True)
    guard.close()


if __name__=='__main__':main()
