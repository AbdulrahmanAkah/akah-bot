"""Supplemental exact, one-arm recoverable harness. NOT armed by its existence.

Requires SHA-bound regression and full-scope differential certificates before
any historical portfolio is created. Frozen base strategy remains authoritative.
"""
import argparse
import gc
import json
import os
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'.akah_bot')]
from v15_checkpoints import sha,write_checkpoint,read_checkpoint,Certificates
from v15_resource_guard import ResourceGuard,resources,MIB
from scripts.research.integration_v15 import runner as base
from v15_resumable_scheduler import ResumableScheduler


def atomic(path,value):
    path=Path(path);temporary=path.with_suffix('.pending')
    temporary.write_text(json.dumps(value,indent=2,default=str)+'\n',encoding='utf-8')
    os.replace(temporary,path)


def certified():
    receipt=ROOT/'.akah_bot/v15_bounded_runtime_certificate.json'
    cert=json.loads(receipt.read_text())
    if cert.get('ready_for_frozen_recoverable_replay') is not True:
        raise RuntimeError('BOUNDED_RUNTIME_NOT_CERTIFIED_NO_REPLAY')
    for path,expected in cert['runtime_bindings'].items():
        resolved=(ROOT/path).resolve()
        if not resolved.is_relative_to(ROOT/'.akah_bot') or sha(resolved)!=expected:
            raise RuntimeError('SUPPLEMENTAL_RUNTIME_BINDING_DRIFT:'+path)
    for name,binding in cert['test_bindings'].items():
        path=ROOT/name
        if sha(path)!=binding['sha256']:raise RuntimeError('TEST_BINDING_DRIFT:'+name)
        xml=ET.parse(path).getroot()
        if (len(xml.findall('.//testcase'))<binding['minimum_tests']
                or any(xml.findall('.//'+k) for k in ('failure','error','skipped'))):
            raise RuntimeError('SUPPLEMENTAL_TESTS_NOT_CLOSED:'+name)
    if (cert.get('all_eighteen_synthetic_exact_output_parity') is not True
            or cert.get('full_301_pair_source_exact_parity') is not True
            or cert.get('open_campaign_exact_resume_all_eighteen') is not True):
        raise RuntimeError('REQUIRED_DIFFERENTIAL_CERTIFICATE_MISSING')
    for name,binding in cert['parity_bindings'].items():
        if sha(ROOT/name)!=binding:raise RuntimeError('PARITY_BINDING_DRIFT:'+name)
    return cert


def main(arm):
    cert=certified() # No market input before certification.
    guard=ResourceGuard('v15_recoverable_worker').start()
    import v15_disk_history as history
    import v15_input_memorymap as memorymap
    history.install();memorymap.install()
    import cache_budget_v15
    import source_scan_acceleration
    import v15_scalar_hour_stream
    cache_budget_v15.install();source_scan_acceleration.install();v15_scalar_hour_stream.install()
    import v15_native_epoch_candidate
    v15_native_epoch_candidate.install()
    base.preflight(ROOT)
    frozen=json.loads((ROOT/base.OUT/'gate3_precommit.json').read_text())
    ready=json.loads((ROOT/base.OUT/'readiness_certificate.json').read_text())
    active=json.loads((ROOT/'.akah_bot/active_task.json').read_text())
    authorization=json.loads((ROOT/'.akah_bot/v15_replay_authorization.json').read_text())
    if (authorization['task_id']!=active['task_id'] or
            active['task_id']!='AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15' or
            authorization.get('explicit_user_replay_authorization') is not True or
            authorization['precommit_sha256']!=frozen['precommit_sha256'] or
            arm not in frozen['contract']['arms']):
        raise RuntimeError('EXACT_ACTIVE_FROZEN_TASK_ARM_AUTHORIZATION_REQUIRED')
    manifest=json.loads((ROOT/base.INPUT_MANIFEST).read_text())
    inputs={r['pair']:r['bounded_sha256'] for r in manifest['pairs']}
    memberships=base.membership(ROOT,manifest)
    authority={'task_id':active['task_id'],'precommit_sha256':frozen['precommit_sha256'],
        'source_version_sha256':frozen['source_version_sha256'],'arm':arm,
        'input_shas':inputs,'membership_sha256':manifest['membership_bounded_sha256'],
        'supplemental_certificate_sha256':sha(ROOT/'.akah_bot/v15_bounded_runtime_certificate.json')}
    output=ROOT/'governance/single_frozen_all_nine_gate3_replay_v15'
    session=ROOT/'.akah_bot/v15_recoverable_session';session.mkdir(exist_ok=True)
    key=arm.replace('|','_')
    latest=session/(key+'_checkpoint.json')
    arm_receipt=session/(key+'_complete.json')
    publication=session/(key+'_publication.json')
    import replay_output_transactions as transaction
    # An interrupted publication is recovered from the exact already-computed
    # bytes before any market read or recreation of a portfolio.
    if publication.exists() and not arm_receipt.exists():
        published=transaction.publish(json.loads(publication.read_text()),session,output,authority)
        atomic(arm_receipt,{'authority':authority,'outputs':[{'path':Path(b['path']).relative_to(ROOT).as_posix(),
            'sha256':b['sha256']} for b in published['outputs']],
            'status':'FULL_FROZEN_ARM_COMPLETED','utc':datetime.now(timezone.utc).isoformat()})
    if arm_receipt.exists():
        receipt=json.loads(arm_receipt.read_text())
        if receipt['authority']!=authority:raise RuntimeError('COMPLETED_ARM_AUTHORITY_DRIFT')
        for binding in receipt['outputs']:
            path=(ROOT/binding['path']).resolve()
            if not path.is_relative_to(output) or sha(path)!=binding['sha256']:
                raise RuntimeError('COMPLETED_ARM_CONTENT_DRIFT')
        print('ARM_STATUS='+arm+':ALREADY_COMPLETED_EXACT_SHA_VERIFIED',flush=True)
        guard.close();return
    restored=None
    if latest.exists():
        link=json.loads(latest.read_text());path=Path(link['receipt'])
        if not path.resolve().is_relative_to(session) or sha(path)!=link['sha256']:
            raise RuntimeError('CHECKPOINT_POINTER_DRIFT')
        from v15_checkpoint_lineage import checkpoint_authority
        saved=read_checkpoint(path,checkpoint_authority(path,authority,cert,ROOT))
        consumer=saved['driver'];restored=saved['scheduler']
        if (consumer.arm!=arm or consumer.source.last_close!=restored['cursor']
                or restored['cursor'].year>=2024 or consumer.failed):
            raise RuntimeError('CHECKPOINT_DRIVER_CLOCK_ARM_FAILED_STATE_DRIFT')
        consumer._assert_current(full=True)
        import v15_disk_seen
        v15_disk_seen.migrate(consumer.source)
        print('EXACT_ARM_RESUMED='+arm+'@'+str(restored['cursor']),flush=True)
    else:
        scope=base.ResearchScope(frozen['source_hashes'][base.PROTOCOL],frozen['source_version_sha256'])
        certificates=tuple(base.ProducerCertificate(g,scope.source_version_sha256,scope.protocol_sha256,
            ready['evidence']['synthetic_results.xml']['sha256'],'SOURCE_BOUND_RESEARCH_IMPLEMENTATION_PASS',
            'SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION') for g in base.FUNDED)
        provider=base.ScopedSourceProvider(inputs,memberships,frozen['source_version_sha256'])
        scenario=arm.split('|')[1]
        execution=base.ScopedExecution(base.Portfolio(frozen['contract']['costs_round_trip'][scenario],
                                       {p:base.ApproximateRule(p,scope) for p in inputs}))
        provider.attach_execution(execution)
        pipeline=base.ScopedPipeline(execution,base.ScopedRouter(scope,certificates))
        consumer=base.ScopedDriver(ROOT,frozen,pipeline,provider,arm=arm,readiness_receipt=ready,
                                   certificate_provider=Certificates(certificates))
    for graph in {id(f.prefix.graph):f.prefix.graph for f in consumer.source.feeds.values()}.values():
        graph.nodes.capacity=256;graph.nodes.cache.clear()
    def stream(record):
        frame=base.raw_frame(ROOT,record['pair'])
        if base.bounded_sha(frame)!=record['bounded_sha256']:raise RuntimeError('BOUNDED_SOURCE_DRIFT')
        yield from base.hours(frame,'2021-09-01','2024-01-01')
    streams={r['pair']:stream(r) for r in manifest['pairs']}
    began=time.monotonic();last_snapshot=began;last_progress=0
    # A bounded MAIN-thread performance observation, never a strategy probe.
    # Start after stream/bootstrap loading; stop after two completed warmup
    # hours. The profiler is not part of the saved driver/scheduler state.
    profiler=None;profile_start=None;profile_done=False
    if restored is not None and restored['cursor'].year==2021:
        import cProfile
        profiler=cProfile.Profile()
    def checkpoint(driver,state):
        nonlocal last_snapshot,last_progress,profile_start,profile_done
        now=time.monotonic()
        if profiler is not None and not profile_done:
            if profile_start is None:
                profile_start=state['cursor'];profiler.enable()
            elif (state['cursor']-profile_start).total_seconds()>=7200:
                profiler.disable();profile_done=True
                profile_path=session/(key+'_warmup_cpu.pstats')
                profiler.dump_stats(str(profile_path))
                print('TWO_COMPLETED_WARMUP_HOUR_PROFILE='+str(profile_path),flush=True)
        if state['cursor'].hour==0:
            cache_budget_v15.release_validation_caches(driver.source)
            gc.collect()
        if now-last_progress>=10:
            sample=resources()
            status={'status':'RUNNING_FROZEN_ARM_NOT_COMPLETED','arm':arm,'completed_close':str(state['cursor']),
                    'wall_seconds':now-began,'resources':sample,'utc':datetime.now(timezone.utc).isoformat()}
            atomic(session/'progress.json',status)
            print('REPLAY_PROGRESS='+json.dumps(status),flush=True);last_progress=now
        # Wall-time only operational interval; does not create signals/rules.
        if now-last_snapshot>=600:
            cache_budget_v15.release_validation_caches(driver.source)
            gc.collect()
            save_began=time.monotonic()
            path=write_checkpoint(session/key,{'driver':driver,'scheduler':state},authority)
            atomic(latest,{'receipt':str(path),'sha256':sha(path),'cursor':str(state['cursor'])})
            print('DURABLE_COMPLETED_HOUR_CHECKPOINT='+str(state['cursor']),flush=True)
            print('CHECKPOINT_WALL_SECONDS='+str(time.monotonic()-save_began),flush=True)
            last_snapshot=time.monotonic()
    result=ResumableScheduler(streams).run(consumer,restored=restored,checkpoint=checkpoint)
    from spotbot.research.multi_school_fidelity.integration_v15.evaluation import summarize_arm
    summary=summarize_arm(consumer,result)
    result['campaign_ledger']=summary['campaigns']
    result['daily_equity_ledger']=[dict(row,arm=arm) for row in summary['daily_equity']]
    # Results are never silently overwritten or partially promoted.
    binding=transaction.prepare(session,output,{key+'.json':result,
        key+'_metrics.json':{k:v for k,v in summary.items() if k!='daily_log'}},authority)
    atomic(publication,binding)
    published=transaction.publish(binding,session,output,authority)
    atomic(arm_receipt,{'authority':authority,'outputs':[{'path':Path(b['path']).relative_to(ROOT).as_posix(),
        'sha256':b['sha256']} for b in published['outputs']],
        'status':'FULL_FROZEN_ARM_COMPLETED','utc':datetime.now(timezone.utc).isoformat()})
    print('ARM_STATUS='+arm+':COMPLETE',flush=True)
    guard.close()


def collect_all():
    certified()
    guard=ResourceGuard('v15_completed_arm_collection').start()
    try:
        base.preflight(ROOT)
        frozen=json.loads((ROOT/base.OUT/'gate3_precommit.json').read_text())
        authorization=json.loads((ROOT/'.akah_bot/v15_replay_authorization.json').read_text())
        active=json.loads((ROOT/'.akah_bot/active_task.json').read_text())
        if active['task_id']!=authorization['task_id'] or authorization.get('explicit_user_replay_authorization') is not True:
            raise RuntimeError('EXACT_ACTIVE_REPLAY_AUTHORIZATION_REQUIRED')
        from v15_replay_collection import collect
        result=collect(ROOT,frozen,authorization,sha(ROOT/'.akah_bot/v15_bounded_runtime_certificate.json'))
        print('EXACT_EIGHTEEN_SAVED_ARM_COLLECTION='+json.dumps(result),flush=True)
    finally:guard.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--arm');group.add_argument('--collect',action='store_true')
    args=parser.parse_args()
    if args.collect:collect_all()
    else:main(args.arm)
