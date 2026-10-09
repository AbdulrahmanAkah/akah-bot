"""Long-prefix exact performance/differential test, source-only pre-2024."""
import cProfile
import hashlib
import inspect
import json
import pstats
import time
from pathlib import Path
from types import SimpleNamespace

import benchmark_v15_acceleration as original
import v15_scaling_acceleration as scaling
from scripts.research.integration_v15.runner import membership, INPUT_MANIFEST, OUT
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import raw_frame, utc

ROOT=Path(__file__).resolve().parents[1]


def main():
    report={'scope':'EXACT_SCALING_PARITY_NOT_ECONOMIC_QUALIFICATION',
            '2024_rows_accessed':False,'2025_rows_accessed':False,'policy_changed':False}
    m=json.loads((ROOT/INPUT_MANIFEST).read_text())
    f=json.loads((ROOT/OUT/'gate3_precommit.json').read_text())
    ms=membership(ROOT,m)
    pairs=('BTC-USDT','ETH-USDT','TRX-USDT')
    hashes={r['pair']:r['bounded_sha256'] for r in m['pairs'] if r['pair'] in pairs}
    frames={p:raw_frame(ROOT,p,start=utc('2021-09-01'),cutoff=utc('2021-11-13')) for p in pairs}
    source=inspect.getsource(original.prefix_probe).replace('2021-09-08','2021-11-13')
    exec(source,original.__dict__)
    # Original first acceleration's SAME-prefix signature and profile, measured
    # immediately before this change; no newly generated economic outcomes.
    baseline='18aa731c60d32daea5600dc143a3f394f351229a4546bd29ac070a25a5172b72'
    before=pstats.Stats(str(ROOT/'.akah_bot/v15_late_prefix_profile.pstats')).total_tt
    scaling.install()
    profiler=cProfile.Profile()
    at=time.perf_counter()
    sig=profiler.runcall(original.prefix_probe,frames,hashes,ms,f['source_version_sha256'])
    report['accelerated_wall_seconds']=time.perf_counter()-at
    profiler.dump_stats(str(ROOT/'.akah_bot/v15_scaling_profile.pstats'))
    stats=pstats.Stats(profiler)
    report['previous_profile_seconds']=before
    report['new_profile_seconds']=stats.total_tt
    report['measured_long_prefix_source_speedup']=before/stats.total_tt
    report['exact_long_prefix_graph_diagnostics_permission_parity']=(sig==baseline)
    assert sig==baseline,'LONG_PREFIX_OUTPUT_DIFFERENTIAL_FAILED'
    print('LONG_PREFIX_EXACT_PARITY=PASS',flush=True)
    stats.sort_stats('cumtime').print_stats(16)
    expected=json.loads((ROOT/'.akah_bot/v15_acceleration_parity.json').read_text())['arm_output_hashes']
    actual=original.synthetic_arms()
    assert actual==expected,'EIGHTEEN_SYNTHETIC_ARMS_DIFFERENTIAL_FAILED'
    report['eighteen_exact_synthetic_output_parity']=True
    report['long_prefix_signature']=sig
    report['probe']={'pairs':pairs,'start':'2021-09-01','end_exclusive':'2021-11-13',
                     'portfolio_created':False,'purpose':'LONG_PREFIX_CAUSAL_SOURCE_SCALING'}
    driver=SimpleNamespace(repo=ROOT)
    for name,fn in [('original',scaling.STAT),('accelerated',scaling.stat_sources)]:
        start=time.perf_counter()
        results=[fn(driver) for _ in range(8)]
        report[name+'_guard_seconds']=time.perf_counter()-start
        if name=='original':guard=results
        else:assert results==guard,'FULL_FILE_GUARD_METADATA_DIFFERENTIAL_FAILED'
    report['full_source_enumeration_and_metadata_parity']=True
    report['guard_speedup']=report['original_guard_seconds']/report['accelerated_guard_seconds']
    report['scaling_source_sha256']=hashlib.sha256((ROOT/'.akah_bot/v15_scaling_acceleration.py').read_bytes()).hexdigest().upper()
    report['full_replay_speedup_not_measured']=True
    (ROOT/'.akah_bot/v15_scaling_parity.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
