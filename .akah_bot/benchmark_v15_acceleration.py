"""Fixed differential correctness/performance probe, no model or policy search."""
import cProfile
import hashlib
import importlib.util
import json
import pstats
import sys
import time
from pathlib import Path

import v15_exact_acceleration as acceleration

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def synthetic_arms():
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest
    f = module(ROOT/'tests/research/integration_v15/test_closure.py', 'v15_accel_arm_fixture')
    helpers = module(ROOT/'tests/research/integration_v13/test_guarded_driver.py', 'v15_accel_fixture_helpers')
    results = {}
    for g in f.FUNDED:
        for scenario in ('1X','2X'):
            lineage = helpers.lineage.__wrapped__()
            fixture = helpers.f.__wrapped__(lineage)
            consumer, output = f.run_arm(helpers, fixture, lineage, g, scenario)
            results[g+'|'+scenario] = digest(output)
    return results


def prefix_probe(frames, hashes, memberships, source_sha):
    from scripts.research.integration_v15.runner import hours, merged
    from spotbot.research.multi_school_fidelity.integration_v15.source_provider import ScopedSourceProvider
    from spotbot.research.multi_school_fidelity.integration_v13.guarded_driver import ClosePacket
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest
    provider = ScopedSourceProvider(hashes, memberships, source_sha)
    for at, items in merged({p: hours(f, '2021-09-01','2021-09-08') for p,f in frames.items()}):
        packet = ClosePacket(tuple((p,x[0]) for p,x in sorted(items.items())),
                             tuple((p,x[1]) for p,x in sorted(items.items())))
        provider.on_completed_hour(packet)
    return digest((tuple(provider.feeds['BTC-USDT'].prefix.graph.nodes.items()), provider.queue,
                   provider.diagnostics, provider.permission))


def main():
    report = {'scope':'SUPPLEMENTAL_RUNTIME_PARITY_NOT_ECONOMIC_QUALIFICATION', '2024_rows_accessed':False,
              '2025_rows_accessed':False, 'trading_rules_changed':False}
    synthetic = {}
    for mode in ('baseline','accelerated'):
        acceleration.install() if mode == 'accelerated' else acceleration.uninstall()
        start = time.perf_counter()
        synthetic[mode] = synthetic_arms()
        report[mode+'_eighteen_synthetic_seconds'] = time.perf_counter()-start
        print(mode.upper()+'_SYNTHETIC_ARMS=18', flush=True)
    assert synthetic['baseline'] == synthetic['accelerated'], 'SYNTHETIC_ARM_DIFFERENTIAL_MISMATCH'
    report['synthetic_eighteen_exact_output_parity'] = True
    from scripts.research.integration_v15.runner import membership, INPUT_MANIFEST, OUT
    from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import raw_frame, utc
    manifest = json.loads((ROOT/INPUT_MANIFEST).read_text())
    frozen = json.loads((ROOT/OUT/'gate3_precommit.json').read_text())
    memberships = membership(ROOT, manifest)
    pairs = ('BTC-USDT','ETH-USDT','TRX-USDT')
    hashes = {r['pair']:r['bounded_sha256'] for r in manifest['pairs'] if r['pair'] in pairs}
    # Canonical predicate reader only. No protected boundary candle.
    frames = {p:raw_frame(ROOT,p,start=utc('2021-09-01'),cutoff=utc('2021-09-08')) for p in pairs}
    report['probe'] = {'pairs':list(pairs),'start':'2021-09-01','end_exclusive':'2021-09-08',
                       'purpose':'CAUSAL_SOURCE_WARMUP_PARITY_NO_PORTFOLIO_CREATED'}
    signatures = {}
    for mode in ('baseline','accelerated'):
        acceleration.install() if mode == 'accelerated' else acceleration.uninstall()
        profiler = cProfile.Profile()
        start = time.perf_counter()
        signatures[mode] = profiler.runcall(prefix_probe, frames, hashes, memberships, frozen['source_version_sha256'])
        report[mode+'_source_seconds'] = time.perf_counter()-start
        profiler.dump_stats(str(ROOT/'.akah_bot'/('v15_'+mode+'_source_profile.pstats')))
        pstats.Stats(profiler).sort_stats('cumtime').print_stats(12)
        print(mode.upper()+'_PREFIX_PROBE_DONE',flush=True)
    assert signatures['baseline'] == signatures['accelerated'], 'SOURCE_DIFFERENTIAL_MISMATCH'
    report['source_graph_diagnostics_permission_exact_parity'] = True
    report['source_speedup'] = report['baseline_source_seconds']/report['accelerated_source_seconds']
    report['arm_output_hashes'] = synthetic['baseline']
    report['prefix_output_hash'] = signatures['baseline']
    report['accelerator_sha256'] = hashlib.sha256((ROOT/'.akah_bot/v15_exact_acceleration.py').read_bytes()).hexdigest().upper()
    (ROOT/'.akah_bot/v15_acceleration_parity.json').write_text(json.dumps(report,indent=2)+'\n')
    print('EXACT_DIFFERENTIAL_PARITY=PASS',flush=True)
    print('MEASURED_SOURCE_SPEEDUP='+str(report['source_speedup']),flush=True)


if __name__=='__main__':
    main()
