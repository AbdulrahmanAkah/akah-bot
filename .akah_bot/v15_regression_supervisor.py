"""Foreground, sequential, resource-gated synthetic regression groups.

Independent completed groups are durable test evidence. Safety-aborted groups
are NOT passes. No economics, timers/automations, or other-application kills.
"""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.akah_bot'),str(ROOT/'src'),str(ROOT)]
from v15_adaptive_guard import sha,run_guarded
LOCK=ROOT/'.akah_bot/v15_regression_supervisor.lock'
STATUS=ROOT/'.akah_bot/v15_regression_suite_status.json'
GROUPS={
    'native_v9_v10':['tests/research/integration_v9','tests/research/integration_v10'],
    'integrity_v11':['tests/research/integration_v11'],
    'lineage_v12':['tests/research/integration_v12'],
    'provider_v13':['tests/research/integration_v13'],
    'scope_v14':['tests/research/integration_v14'],
    'scope_v15':['tests/research/integration_v15'],
    'ownership_lifecycle':['tests/research/test_school_ownership_bundle_v8.py','tests/research/test_structural_lifecycle_v6.py'],
    'supplemental':['.akah_bot/test_v15_scaling.py','.akah_bot/test_v15_storage.py',
        '.akah_bot/test_v15_checkpoints.py','.akah_bot/test_v15_input_memorymap.py',
        '.akah_bot/test_v15_resume.py','.akah_bot/test_v15_disk_history.py','.akah_bot/test_v15_indexed.py',
        '.akah_bot/test_v15_adaptive_guard.py'],
}


def stamp(status,**details):
    payload=dict(status=status,utc=datetime.now(timezone.utc).isoformat(),supervisor_pid=os.getpid(),
                 economic_replay_executed=False,**details)
    temporary=STATUS.with_suffix('.pending');temporary.write_text(json.dumps(payload,indent=2)+'\n')
    os.replace(temporary,STATUS)
    print(json.dumps({k:v for k,v in payload.items() if k!='completed'}|{
        'completed_tests':sum(r['tests'] for r in details.get('completed',{}).values())}),flush=True)


def main():
    with LOCK.open('x') as stream:stream.write(str(os.getpid()))
    try:
        # Bind every runtime/test file, not solely the frozen base source.
        files=sorted((ROOT/'.akah_bot').glob('v15_*.py'))+sorted((ROOT/'.akah_bot').glob('test_v15*.py'))
        bindings={str(p.relative_to(ROOT)):sha(p) for p in files}
        suite=ROOT/'.akah_bot'/('guarded-suite-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
        suite.mkdir(exist_ok=False);completed={}
        (suite/'runtime_bindings.json').write_text(json.dumps(bindings,indent=2)+'\n')
        if len(sys.argv)>1:
            if len(sys.argv)!=3 or sys.argv[1]!='--resume-suite':raise RuntimeError('EXACT_RESUME_SUITE_ARGUMENT_REQUIRED')
            prior=Path(sys.argv[2]).resolve()
            if not prior.is_relative_to(ROOT/'.akah_bot'):raise RuntimeError('PRIOR_SUITE_PATH_ESCAPE')
            old=json.loads((prior/'bindings_before_operational_repair.json').read_text())
            allowed={'.akah_bot/v15_adaptive_guard.py','.akah_bot/v15_regression_supervisor.py',
                     '.akah_bot/v15_safety_pytest.py','.akah_bot/test_v15_adaptive_guard.py'}
            changed={p for p in set(old)|set(bindings) if old.get(p)!=bindings.get(p)}
            if any(p.replace('\\','/') not in allowed for p in changed):
                raise RuntimeError('CANNOT_REUSE_GROUP_AFTER_TRADING_RUNTIME_CHANGE:'+str(changed))
            previous=json.loads(STATUS.read_text())
            if Path(previous['suite']).resolve()!=prior:raise RuntimeError('PRIOR_STATUS_AUTHORITY_MISMATCH')
            # Passed reports may already have been reused from an earlier
            # suite. Follow only the explicit SHA-bound recovery lineage.
            report_scopes=[prior]
            ancestor=prior
            while (ancestor/'operational_rebind.json').exists():
                link=json.loads((ancestor/'operational_rebind.json').read_text())
                parent=Path(link['prior_suite']).resolve()
                if (not parent.is_relative_to(ROOT/'.akah_bot') or parent in report_scopes
                    or not parent.name.startswith('guarded-suite-')
                    or sha(parent/'bindings_before_operational_repair.json')!=link['prior_bindings_sha256']):
                    raise RuntimeError('PRIOR_REPORT_LINEAGE_NOT_SHA_BOUND')
                report_scopes.append(parent);ancestor=parent
            for group,result in previous['completed'].items():
                path=(ROOT/result['path']).resolve()
                if not any(path.is_relative_to(scope) for scope in report_scopes) or sha(path)!=result['sha256']:
                    raise RuntimeError('PRIOR_XML_AUTHORITY_DRIFT')
                xml=ET.parse(path).getroot()
                if (result['os_exit_code']!=0 or len(xml.findall('.//testcase'))!=result['tests']
                    or any(xml.findall('.//'+k) for k in ('failure','error','skipped'))):
                    raise RuntimeError('PRIOR_GROUP_NOT_PASSED')
                completed[group]=dict(result,reused_identical_trading_logic=True,
                    prior_operational_guard_bindings=old,guard_policy_not_retroactively_relabelled=True)
            (suite/'operational_rebind.json').write_text(json.dumps({'prior_suite':str(prior),
                'changed_operational_files':sorted(changed),'unchanged_trading_bindings_verified':True,
                'prior_bindings_sha256':sha(prior/'bindings_before_operational_repair.json')},indent=2)+'\n')
        environment=dict(os.environ,PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',
            OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
        for group,paths in GROUPS.items():
            if group in completed:continue
            for name,binding in bindings.items():
                if sha(ROOT/name)!=binding:raise RuntimeError('SOURCE_CHANGED_DURING_GROUPED_REGRESSION:'+name)
            xml=suite/(group+'.xml')
            args=[str(ROOT/'.venv/Scripts/python.exe'),'-m','pytest','-p','v15_safety_pytest',*paths,
                '-k','not test_z_export_retained_receipts','--import-mode=importlib','-q',
                '--basetemp='+str(suite/(group+'-temp')),'--junitxml='+str(xml)]
            stamp('SYNTHETIC_GROUP_RESOURCE_ADAPTIVE',group=group,completed=completed,suite=str(suite))
            try:
                # The native V9/V10 group previously measured <90MiB private;
                # constrain it more tightly instead of reducing the reserve.
                budget=128 if group=='native_v9_v10' else 192
                child_receipt=run_guarded(args,suite/(group+'-guardian'),
                    dict(environment,AKAH_SYNTHETIC_PROGRESS_PATH=str(suite/(group+'-test-progress.json'))),budget_mib=budget)
            except BaseException as exc:
                stamp('GROUP_GUARDIAN_ERROR_NOT_PASSED',group=group,error=repr(exc),
                      completed=completed,suite=str(suite))
                raise
            exitcode=child_receipt['os_exit_code']
            if exitcode!=0:
                stamp('GROUP_NOT_PASSED_NO_AUTO_RETRY',group=group,os_exit_code=exitcode,
                      child_receipt=child_receipt,completed=completed,suite=str(suite))
                return
            tree=ET.parse(xml).getroot()
            if any(tree.findall('.//'+k) for k in ('failure','error','skipped')):
                raise RuntimeError('INVALID_TEST_REPORT:'+group)
            completed[group]={'path':str(xml.relative_to(ROOT)),'sha256':sha(xml),
                              'tests':len(tree.findall('.//testcase')),'os_exit_code':exitcode,
                              'guardian_receipt':child_receipt}
            stamp('SYNTHETIC_GROUP_COMPLETE',group=group,completed=completed,suite=str(suite))
        for name,binding in bindings.items():
            if sha(ROOT/name)!=binding:raise RuntimeError('SOURCE_CHANGED_DURING_GROUPED_REGRESSION:'+name)
        receipt={'status':'ALL_DECLARED_SYNTHETIC_GROUPS_PASS','runtime_bindings':bindings,'groups':completed,
                 'total_tests':sum(x['tests'] for x in completed.values()),'economic_replay_executed':False}
        (suite/'certificate.json').write_text(json.dumps(receipt,indent=2)+'\n')
        stamp('SYNTHETIC_REGRESSION_COMPLETE_NOT_HISTORICAL_SPEED_CERTIFICATION',receipt=str(suite/'certificate.json'),
              total_tests=receipt['total_tests'],completed=completed)
    finally:
        if LOCK.exists() and LOCK.read_text()==str(os.getpid()):LOCK.unlink()


if __name__=='__main__':main()
