"""Test exact repairs serially, certify, resume existing authorized frozen run.

No restart from the beginning, no parameter/strategy changes, no other apps.
An unproven runtime must never be armed just to satisfy a deadline.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'.akah_bot')]
from v15_adaptive_guard import atomic, run_guarded


def stage(name, **detail):
    payload={'stage':name,'utc':datetime.now(timezone.utc).isoformat(),**detail}
    atomic(ROOT/'.akah_bot/v15_host_pressure_repair_status.json',payload)
    print('REPAIR_MILESTONE='+json.dumps(payload),flush=True)


def validation(script, prefix):
    before={p.name for p in (ROOT/'.akah_bot').glob(prefix+'*') if p.is_dir()}
    try:runpy.run_path(str(ROOT/'.akah_bot'/script),run_name='__main__')
    except SystemExit as exc:
        if exc.code not in (None,0):raise RuntimeError('VALIDATION_FAILED:'+script)
    new=[p for p in (ROOT/'.akah_bot').glob(prefix+'*') if p.is_dir() and p.name not in before]
    if len(new)!=1:raise RuntimeError('EXACT_NEW_TEST_RECEIPT_REQUIRED')
    r=json.loads((new[0]/'receipt.json').read_text())
    if r['os_exit_code']!=0:raise RuntimeError('VALIDATION_NOT_COMPLETE')
    return new[0]


def main():
    os.environ.update(PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
                      MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    stage('HOST_PRESSURE_TESTS_RUNNING_NO_ECONOMIC_REPLAY')
    harness=validation('guarded_harness_validation.py','harness-validation-')
    stage('HOST_PRESSURE_TESTS_PASS_NATIVE_EPOCH_TESTS_RUNNING',harness=str(harness))
    configuration=validation('guarded_cache_validation.py','cache-validation-')
    stage('SYNTHETIC_TESTS_PASS_FULL_SOURCE_DIFFERENTIAL_RUNNING',configuration=str(configuration))
    directory=ROOT/'.akah_bot'/('guarded-source-native-epoch-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    env=dict(os.environ)
    receipt=run_guarded([str(ROOT/'.venv/Scripts/python.exe'),'-B',str(ROOT/'.akah_bot/guarded_entry.py'),
        str(ROOT/'.akah_bot/profile_v15_full_scope.py'),'7','--indexed','--disk','--cache256',
        '--seen-storage','--native-epoch','--no-profile'],directory,env,budget_mib=None,startup_allowance_mib=128)
    if receipt['os_exit_code']!=0:raise RuntimeError('NATIVE_EPOCH_FULL_SOURCE_DIFFERENTIAL_FAILED')
    from certify_v15_recoverable_runtime import main as certify
    certify(harness,configuration,directory)
    from v15_checkpoints import sha
    link=json.loads((ROOT/'.akah_bot/v15_recoverable_session/FS_WYCKOFF_FRESH_CAUSE_V8_1X_checkpoint.json').read_text())
    cert=ROOT/'.akah_bot/v15_bounded_runtime_certificate.json'
    handoff=json.loads((ROOT/'.akah_bot/v15_live_recovery_handoff.json').read_text())
    handoff.update(status='PRESSURE_ONLY_EXACT_NATIVE_EPOCH_CERTIFIED_RESUME_DISPATCHED_NOT_COMPLETED',
        certificate_sha256=sha(cert),last_verified_durable_cursor=link['cursor'],
        last_verified_durable_receipt_sha256=link['sha256'],
        allocation_policy='HOST_PRESSURE_NO_FIXED_PRIVATE_CEILING',
        fixed_384_mib_kill_removed=True,economic_results_complete=False)
    atomic(ROOT/'.akah_bot/v15_live_recovery_handoff.json',handoff)
    stage('REPAIRS_CERTIFIED_EXACT_CHECKPOINT_RESUME_DISPATCHED',cursor=link['cursor'],certificate_sha256=sha(cert))
    from v15_guarded_economic_supervisor import main as replay
    replay()
    stage('ALL_EIGHTEEN_ARMS_COMPLETE_AND_COLLECTED')


if __name__=='__main__':
    try:main()
    except BaseException as exc:
        stage('REPAIR_REQUIRES_CORRECTION_NOT_ECONOMIC_CONCLUSION',error=repr(exc))
        raise
