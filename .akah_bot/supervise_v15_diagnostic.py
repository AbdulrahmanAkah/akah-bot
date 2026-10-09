"""Single resource-bounded diagnostic supervisor. Does not arm economic replay.

Captures OS child exit status and refuses duplicate workers. A failed child is
never automatically retried; a future investigation must bind the new cause.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.akah_bot'),str(ROOT/'src'),str(ROOT)]
from v15_resource_guard import resources, MIB
LOCK=ROOT/'.akah_bot/v15_diagnostic_supervisor.lock'
STATUS=ROOT/'.akah_bot/v15_diagnostic_supervisor_status.json'


def stamp(payload):
    value=dict(payload,utc=datetime.now(timezone.utc).isoformat(),
               economic_replay_executed=False,requested_economic_arms=18,
               protected_rows_accessed=False,supervisor_pid=os.getpid())
    temporary=STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n')
    os.replace(temporary,STATUS)
    print(json.dumps(value),flush=True)


def main():
    if LOCK.exists():
        raise RuntimeError('EXISTING_DIAGNOSTIC_LOCK_CHECK_OWNING_PID_BEFORE_RECOVERY')
    # Exclusive creation is also the race guard against scheduler duplication.
    with LOCK.open('x') as stream:stream.write(str(os.getpid()))
    try:
        sample=resources()
        if sample['available_physical_bytes']<1024*MIB or sample['commit_available_bytes']<2048*MIB:
            stamp(dict(status='WAITING_FOR_SAFE_RESOURCE_HEADROOM_NO_CHILD_LAUNCHED',resources=sample,
                       minimum_start_available_bytes=1024*MIB))
            return
        environment=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
                         NUMEXPR_NUM_THREADS='1',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
        outcomes=[]
        for mode in ('scaling','indexed'):
            sample=resources()
            if sample['available_physical_bytes']<1024*MIB:
                stamp(dict(status='WAITING_FOR_SAFE_RESOURCE_HEADROOM_NO_NEXT_CHILD',resources=sample,outcomes=outcomes))
                return
            args=[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'.akah_bot/profile_v15_full_scope.py'),'7']
            if mode=='indexed':args.append('--indexed')
            out=ROOT/f'.akah_bot/v15_guarded_7d_{mode}.stdout.log'
            err=ROOT/f'.akah_bot/v15_guarded_7d_{mode}.stderr.log'
            with out.open('a') as stdout,err.open('a') as stderr:
                process=subprocess.Popen(args,cwd=ROOT,env=environment,stdout=stdout,stderr=stderr,
                    creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
                stamp(dict(status='GUARDED_SOURCE_ONLY_DIAGNOSTIC_RUNNING',child_pid=process.pid,mode=mode))
                exitcode=process.wait()
            outcomes.append({'mode':mode,'child_pid':process.pid,'os_exit_code':exitcode,
                'stdout':str(out),'stderr':str(err)})
            if exitcode!=0:
                stamp(dict(status='CHILD_EXIT_CAPTURED_DIAGNOSTIC_NOT_COMPLETE_NO_AUTO_RETRY',outcomes=outcomes))
                return
        before=json.loads((ROOT/'.akah_bot/v15_full_scope_7d_scaling_source_report.json').read_text())
        after=json.loads((ROOT/'.akah_bot/v15_full_scope_7d_indexed_source_report.json').read_text())
        exact=before['full_source_signature']==after['full_source_signature']
        speedup=before['wall_seconds']/after['wall_seconds']
        stamp(dict(status='DIAGNOSTIC_COMPLETE_NOT_REPLAY_AUTHORIZATION',exact_full_scope_parity=exact,
                   measured_full_scope_7d_speedup=speedup,outcomes=outcomes,
                   full_history_memory_scaling_still_requires_closure=True))
    finally:
        if LOCK.exists() and LOCK.read_text()==str(os.getpid()):LOCK.unlink()


if __name__=='__main__':main()
