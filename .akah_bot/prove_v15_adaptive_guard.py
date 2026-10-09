"""Real owned-process suspension proof with identical synthetic counter output."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from v15_adaptive_guard import ROOT,run_guarded,sha,atomic


def main():
    folder=ROOT/'.akah_bot'/('adaptive-proof-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    folder.mkdir(exist_ok=False)
    output=folder/'fixture.json'
    args=[str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'.akah_bot/v15_guard_fixture.py'),str(output)]
    env=dict(os.environ,PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
    # Artificial pressure only REDUCES actual observed availability; cannot
    # manufacture safe headroom or bypass physical/commit reserve checks.
    receipt=run_guarded(args,folder/'run',env,budget_mib=32,
                         pressure_test=lambda elapsed:0 if 1.<=elapsed<2. else None)
    if receipt['os_exit_code']!=0:raise RuntimeError('SYNTHETIC_GUARD_FIXTURE_FAILED:'+str(receipt))
    actual=json.loads(output.read_text())
    expected=[[i,i*i] for i in range(80)]
    if actual['values']!=expected or actual['sha256']!=hashlib.sha256(json.dumps(expected).encode()).hexdigest():
        raise RuntimeError('SUSPENSION_CHANGED_SYNTHETIC_OUTPUT')
    if receipt['pauses']<1:raise RuntimeError('REAL_SUSPENSION_NOT_EXERCISED')
    proof={'status':'EXACT_SYNTHETIC_PAUSE_RESUME_PASS','receipt':receipt,'exact_counter_output':True,
           'other_applications_controlled':False,'market_rows_read':0,'economic_replay_executed':False,
           'runtime_sha256':sha(ROOT/'.akah_bot/v15_adaptive_guard.py'),'fixture_sha256':sha(ROOT/'.akah_bot/v15_guard_fixture.py')}
    atomic(folder/'proof.json',proof);print(json.dumps(proof),flush=True)


if __name__=='__main__':main()
