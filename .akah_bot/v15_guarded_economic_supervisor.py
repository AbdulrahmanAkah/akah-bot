"""Existing frozen mission, one guarded exact arm at a time. Unarmed by default."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import time
from v15_adaptive_guard import ROOT,run_guarded,sha,atomic


def main():
    path=ROOT/'.akah_bot/v15_bounded_runtime_certificate.json'
    cert=json.loads(path.read_text())
    if cert.get('ready_for_frozen_recoverable_replay') is not True:
        raise RuntimeError('BOUNDED_RUNTIME_NOT_CERTIFIED_NO_REPLAY')
    for relative,binding in cert['runtime_bindings'].items():
        if sha(ROOT/relative)!=binding:raise RuntimeError('SUPPLEMENTAL_SOURCE_DRIFT:'+relative)
    freeze_path=ROOT/'governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json'
    freeze=json.loads(freeze_path.read_text())
    authorization=json.loads((ROOT/'.akah_bot/v15_replay_authorization.json').read_text())
    active=json.loads((ROOT/'.akah_bot/active_task.json').read_text())
    if (authorization.get('explicit_user_replay_authorization') is not True
        or active['task_id']!=authorization['task_id']
        or active['task_id']!='AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15'
        or authorization['precommit_sha256']!=freeze['precommit_sha256']):
        raise RuntimeError('EXISTING_FROZEN_REPLAY_TASK_AUTHORIZATION_REQUIRED')
    arms=freeze['contract']['arms']
    if len(arms)!=18 or len(set(arms))!=18:raise RuntimeError('EXACT_EIGHTEEN_ARMS_REQUIRED')
    directory=ROOT/'.akah_bot'/('economic-guarded-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    directory.mkdir(exist_ok=False)
    handoff_path=ROOT/'.akah_bot/v15_live_recovery_handoff.json'
    if handoff_path.is_file():
        handoff=json.loads(handoff_path.read_text())
        if handoff.get('task_id')!=active['task_id']:
            raise RuntimeError('LIVE_HANDOFF_TASK_DRIFT')
        handoff.update(live_status_directory=directory.relative_to(ROOT).as_posix(),
                       status='CERTIFIED_RESUME_SUPERVISOR_STARTED_NOT_COMPLETED',
                       initial_supervisor_pid_observed=os.getpid(),
                       first_worker_pid_observed=None,
                       certificate_sha256=sha(path),economic_results_complete=False)
        atomic(handoff_path,handoff)
    env=dict(os.environ,PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
        MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    completed=[];failures={}
    for i,arm in enumerate(arms):
        # No source drift may be concealed between independent arms.
        for relative,binding in cert['runtime_bindings'].items():
            if sha(ROOT/relative)!=binding:raise RuntimeError('RUNTIME_SOURCE_CHANGED_BETWEEN_ARMS')
        atomic(directory/'status.json',{'arm':arm,'index':i+1,'requested':18,'completed':completed,
            'failures':failures,'status':'ARM_START_REQUESTED_NOT_COMPLETED'})
        receipt=run_guarded([str(ROOT/'.venv/Scripts/python.exe'),'-B',str(ROOT/'.akah_bot/guarded_entry.py'),
            str(ROOT/'.akah_bot/v15_recoverable_worker.py'),'--arm',arm],directory/f'arm-{i+1:02d}',env,
            budget_mib=cert['economic_worker_private_budget_mib'],startup_allowance_mib=cert['bootstrap_allowance_mib'])
        if receipt['os_exit_code']!=0:
            failures[arm]={'status':'INCOMPLETE_OPERATIONAL_OR_TECHNICAL_STOP_NOT_ECONOMIC_RESULT',
                           'receipt':receipt}
            if receipt['os_exit_code'] in (75,76):
                # Resource/guardian failure is shared infrastructure, not an
                # arm-specific market conclusion. Do not repeat the known
                # unsafe infrastructure on all remaining arms.
                atomic(directory/'status.json',{'status':'SHARED_INFRASTRUCTURE_REPAIR_REQUIRED_NO_QUALIFICATION',
                    'completed':completed,'failures':failures,'requested':arms})
                raise RuntimeError('SHARED_RESOURCE_GUARD_REPAIR_BEFORE_NEXT_ARM')
        else:
            key=arm.replace('|','_')
            complete=ROOT/'.akah_bot/v15_recoverable_session'/(key+'_complete.json')
            if not complete.is_file():raise RuntimeError('EXIT_ZERO_WITHOUT_COMPLETE_ARM_RECEIPT')
            completed.append(arm)
        print('ARM_PROGRESS='+json.dumps({'arm':arm,'complete':arm in completed,'completed_arms':len(completed)}),flush=True)
        # Independent technical failures cannot shrink the frozen family.
        # Their complete guards/logs remain available for exact repair/resume.
    if failures:
        atomic(directory/'status.json',{'status':'INCOMPLETE_REPAIR_REQUIRED_NO_QUALIFICATION',
            'completed':completed,'failures':failures,'requested':arms})
        raise RuntimeError('EIGHTEEN_ARM_REPAIR_OR_RESUME_REQUIRED')
    collected=run_guarded([str(ROOT/'.venv/Scripts/python.exe'),'-B',str(ROOT/'.akah_bot/guarded_entry.py'),
        str(ROOT/'.akah_bot/v15_recoverable_worker.py'),'--collect'],directory/'collection',env,budget_mib=192,startup_allowance_mib=128)
    if collected['os_exit_code']!=0:raise RuntimeError('SAVED_COLLECTION_FAILED_RETRY_WITHOUT_REPLAY')
    atomic(directory/'status.json',{'status':'ALL_EIGHTEEN_ARMS_COMPLETE_AND_COLLECTED','completed':completed,
        'qualification_is_not_production_authorization':True})


if __name__=='__main__':main()
