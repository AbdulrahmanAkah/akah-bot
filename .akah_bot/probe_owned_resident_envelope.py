"""Read-only counters from an existing nonce/ancestry-bound AKAH child."""
import json
from pathlib import Path
import sys
from v15_adaptive_guard import ROOT,OwnedProcess,sha
from v15_private_working_set import native_sample,displaced_resident


def main(directory):
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'.akah_bot'):raise RuntimeError('GUARD_SCOPE_ESCAPE')
    manifest=json.loads((directory/'guardian_manifest.json').read_text())
    handshake=json.loads((directory/'worker_handshake.json').read_text())
    if (handshake['nonce']!=manifest['nonce'] or handshake['guardian_pid']!=manifest['guardian_pid']):
        raise RuntimeError('OWNERSHIP_NONCE_DRIFT')
    for path,binding in manifest['runtime_bindings'].items():
        if sha(ROOT/path)!=binding:raise RuntimeError('GUARD_SOURCE_DRIFT')
    from v15_adaptive_guard import processes,descendant
    tree=processes();pid=handshake['worker_pid'];guardian=manifest['guardian_pid']
    if not descendant(pid,guardian,tree):raise RuntimeError('WORKER_ANCESTRY_DRIFT')
    observed=[]
    for line in (directory/'stdout.log').read_text().splitlines():
        if line.startswith('REPLAY_PROGRESS='):
            observed.append(json.loads(line.split('=',1)[1])['resources']['process_rss_bytes'])
    if not observed:raise RuntimeError('OWN_RESIDENT_HIGHWATER_OBSERVATION_MISSING')
    owned=OwnedProcess(pid,guardian,guardian)
    try:sample=native_sample(owned.handle)
    finally:owned.close()
    highwater=max(observed)
    report={'scope':'OWNED_WORKER_MEMORY_COUNTERS_ONLY_NO_MARKET_OR_ECONOMIC_ROWS',
        'worker_pid':pid,'guardian_pid':guardian,'sample':sample,'observed_rss_highwater':highwater,
        'old_displaced_reserve_bytes':max(0,highwater-sample['process_rss_bytes']),
        'private_displaced_reserve_bytes':displaced_resident(sample,highwater),
        'running_physical_floor_mib_unchanged':512,'commit_floor_mib_unchanged':1024,
        'worker_control_executed':False,'other_apps_controlled':False,'trading_rules_changed':False}
    (ROOT/'.akah_bot/v15_resident_envelope_forensic.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main(sys.argv[1])
