"""Bounded all-pair source profiling, never an economic outcome calculation."""
import cProfile
import ctypes
import json
import hashlib
import os
import gc
import pstats
import sys
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src'), str(ROOT/'.akah_bot')]
import v15_scaling_acceleration as scaling
scaling.install()
from scripts.research.integration_v15.runner import INPUT_MANIFEST, OUT, membership, hours, merged
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import raw_frame, utc
from spotbot.research.multi_school_fidelity.integration_v15.source_provider import ScopedSourceProvider
from spotbot.research.multi_school_fidelity.integration_v13.guarded_driver import ClosePacket
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest


def streamed_signature(nodes,queue,diagnostics,permission):
    """Exact json.dumps(tuple(nodes.items()),...) bytes, without a giant tuple.

    Separate from all source/economic code. Each record is fully retained and
    evaluated in original insertion order. Not a sampled authority signature.
    """
    h=hashlib.sha256();h.update(b'[[')
    for i,item in enumerate(nodes.items()):
        if i:h.update(b', ')
        h.update(json.dumps(item,sort_keys=True,default=str).encode())
    h.update(b']')
    for value in (queue,diagnostics,permission):
        h.update(b', ');h.update(json.dumps(value,sort_keys=True,default=str).encode())
    h.update(b']');return h.hexdigest()


def resources():
    class M(ctypes.Structure):
        _fields_ = [('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in
            ('total','available','page_total','page_available','virtual_total','virtual_available','extended')]
    m=M();m.length=ctypes.sizeof(m);ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return {'available_physical_bytes':m.available,'total_physical_bytes':m.total,
            'committed_bytes':m.page_total-m.page_available}


def main():
    from v15_resource_guard import ResourceGuard
    guard=ResourceGuard('v15_full_scope_probe').start()
    if '--indexed' in sys.argv:
        import v15_indexed_acceleration
        v15_indexed_acceleration.install()
    if '--storage' in sys.argv:
        import v15_bounded_storage
        v15_bounded_storage.install()
    if '--disk' in sys.argv:
        import v15_disk_history
        v15_disk_history.install()
    if '--cache256' in sys.argv:
        import cache_budget_v15
        cache_budget_v15.install()
    if '--native-epoch' in sys.argv:
        import v15_native_epoch_candidate
        v15_native_epoch_candidate.install()
    from v15_resource_guard import below_normal
    below_normal()
    import pyarrow as pa
    pa.set_cpu_count(1);pa.set_io_thread_count(1)
    manifest=json.loads((ROOT/INPUT_MANIFEST).read_text())
    frozen=json.loads((ROOT/OUT/'gate3_precommit.json').read_text())
    hashes={r['pair']:r['bounded_sha256'] for r in manifest['pairs']}
    days=int(sys.argv[1]) if len(sys.argv)>1 else 1
    if not 1<=days<=14:raise ValueError('BOUNDED_DIAGNOSTIC_DAYS')
    end=utc('2021-09-01')+timedelta(days=days)
    frames={}
    for p in hashes:
        frames[p]=raw_frame(ROOT,p,start=utc('2021-09-01'),cutoff=end)
        # Retain every exact input row; release only unused allocator buffers.
        gc.collect(0);pa.default_memory_pool().release_unused()
    provider=ScopedSourceProvider(hashes,membership(ROOT,manifest),frozen['source_version_sha256'])
    if '--cache256' in sys.argv:
        from v15_bounded_storage import EvidenceArchive
        for graph in {id(f.prefix.graph):f.prefix.graph for f in provider.feeds.values()}.values():
            if not isinstance(graph.nodes,EvidenceArchive):raise RuntimeError('EXACT_ARCHIVE_CACHE_REQUIRED')
            # Pure immutable-node retrieval cache. No evidence is discarded,
            # expired, rounded or hidden; misses decode the exact SQLite row.
            graph.nodes.capacity=256;graph.nodes.cache.clear()
    profiler=None if '--no-profile' in sys.argv else cProfile.Profile()
    began=time.monotonic();ticks=0
    trace_started=False
    traced_allocations=[]
    trace_finished=False
    if profiler is not None:profiler.enable()
    for at,items in merged({p:hours(f,'2021-09-01',end) for p,f in frames.items()}):
        if '--allocation-diagnostic' in sys.argv and not trace_started and not trace_finished and at>=utc('2021-09-04'):
            import tracemalloc
            tracemalloc.start(1);trace_started=True
        if trace_started and at>=utc('2021-09-05'):
            traced_allocations=[{'location':str(s.traceback),'bytes':s.size,'count':s.count}
                               for s in tracemalloc.take_snapshot().statistics('lineno')[:30]]
            tracemalloc.stop();trace_started=False;trace_finished=True
            # Persist diagnostic evidence before continuing the parity scope.
            (ROOT/'.akah_bot/v15_allocation_diagnostic.json').write_text(json.dumps({
                'scope':'SOURCE_ONLY_ALLOCATIONS_2021_09_04_TO_2021_09_05',
                'locations':traced_allocations,'economic_replay_executed':False},indent=2)+'\n')
        provider.on_completed_hour(ClosePacket(tuple((p,x[0]) for p,x in sorted(items.items())),
            tuple((p,x[1]) for p,x in sorted(items.items()))))
        ticks+=len(items)
        if '--cache256' in sys.argv and at.hour==0:
            cache_budget_v15.release_validation_caches(provider)
            # Collect unreachable temporary copies only; retain all live state.
            gc.collect();pa.default_memory_pool().release_unused()
        if at.hour==0:
            from v15_resource_guard import resources as process_resources
            current=process_resources()
            archive=provider.feeds['BTC-USDT'].prefix.graph.nodes
            searches=[s['elliott']._search for s in provider.sources.values() if s['elliott']._search is not None]
            print(json.dumps(dict(clock=str(at),wall_seconds=time.monotonic()-began,
                graph_nodes=len(archive),archive_mutable_nodes=len(getattr(archive,'mutable',{})),
                archive_cached_nodes=len(getattr(archive,'cache',{})),
                prefix_points=sum(len(f.prefix.points) for f in provider.feeds.values()),
                harmonic_contracts=sum(len(p.harmonics) for p in provider.producers.values()),
                proof_cache_entries=sum(len(s._proofs) for s in searches),
                wave_cache_entries=sum(len(s._waves) for s in searches),
                parent_cache_entries=sum(len(s._parents) for s in searches),
                process_private_bytes=current['process_private_bytes'],
                process_rss_bytes=current['process_rss_bytes'],**resources())),flush=True)
    mode='disk_cache256' if '--cache256' in sys.argv else ('disk' if '--disk' in sys.argv else ('storage' if '--storage' in sys.argv else ('indexed' if '--indexed' in sys.argv else 'scaling')))
    if '--seen-storage' in sys.argv:mode+='_seen'
    if '--native-epoch' in sys.argv:mode+='_native_epoch'
    if trace_started:
        traced_allocations=[{'location':str(s.traceback),'bytes':s.size,'count':s.count}
                           for s in tracemalloc.take_snapshot().statistics('lineno')[:30]]
        tracemalloc.stop()
    if profiler is not None:
        profiler.disable();profiler.dump_stats(str(ROOT/f'.akah_bot/v15_full_scope_{days}d_{mode}_source.pstats'))
        pstats.Stats(profiler).sort_stats('cumtime').print_stats(25)
    nodes=provider.feeds['BTC-USDT'].prefix.graph.nodes
    report={'scope':'FULL_301_PAIR_BOUNDED_SOURCE_ONLY_WARMUP','days':days,'mode':mode,'pairs':len(hashes),'pair_ticks':ticks,
            'wall_seconds':time.monotonic()-began,'pid':os.getpid(),'resources':resources(),
            'graph_nodes':len(nodes),'node_origins':dict(Counter(n.origin for n in nodes.values())),
            'prefix_bars':sum(len(v) for f in provider.feeds.values() for v in f.prefix.bars.values()),
            'prefix_points':sum(len(f.prefix.points) for f in provider.feeds.values()),
            'harmonic_contracts':sum(len(p.harmonics) for p in provider.producers.values()),
            'harmonic_active':sum(len(s['harmonic'].active) for s in provider.sources.values()),
            'source_probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper(),
            'operational_storage_bindings':{name:hashlib.sha256((ROOT/'.akah_bot'/name).read_bytes()).hexdigest().upper()
                for name in ('v15_disk_seen.py','v15_disk_history.py','cache_budget_v15.py')},
            'native_epoch_binding':hashlib.sha256((ROOT/'.akah_bot/v15_native_epoch_candidate.py').read_bytes()).hexdigest().upper() if '--native-epoch' in sys.argv else None,
            'immutable_retrieval_cache_capacity':nodes.capacity if '--disk' in sys.argv else None,
            'arrow_cpu_threads':pa.cpu_count(),'arrow_io_threads':pa.io_thread_count(),
            'instrumented_with_cprofile':profiler is not None,
            'new_allocations_after_2021_09_04':traced_allocations,
            'mutable_node_value_types':dict(Counter(n.origin+'|'+type(n.evidence.value).__module__+'.'+type(n.evidence.value).__qualname__ for n in getattr(nodes,'mutable',{}).values())),
            'mutable_value_field_shapes':[
                {'origin':n.origin,'type':type(n.evidence.value).__qualname__,
                 'fields':{k:type(v).__module__+'.'+type(v).__qualname__ for k,v in getattr(n.evidence.value,'__dict__',{}).items()}}
                for n in list(getattr(nodes,'mutable',{}).values())[:8]],
            'full_source_signature':streamed_signature(nodes,provider.queue,provider.diagnostics,provider.permission),
            'economic_replay_executed':False,'2024_rows_accessed':False,'2025_rows_accessed':False}
    (ROOT/f'.akah_bot/v15_full_scope_{days}d_{mode}_source_report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    guard.close()


if __name__=='__main__':main()
