"""Observable launch; no market decisions or cached economic state."""
import json
import os
import runpy
import sys
import threading
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.akah_bot')]
from observe_frozen_v15_restart import observe

receipt_path=ROOT/'.akah_bot/v15_replay_process_receipt.json'
receipt=json.loads(receipt_path.read_text())
receipt.update(worker_pid=os.getpid(),launcher_pid=os.getppid(),
               started_at_utc=datetime.now(timezone.utc).isoformat(),
               status_at_last_check='RUNNING_NOT_COMPLETE',
               observer_launcher='.akah_bot/observe_scaling_v15.py',
               supplemental_scaling='Separately hashed long-prefix parity plus synthetic regressions; no policy changes')
receipt_path.write_text(json.dumps(receipt,indent=2)+'\n')
stopped=threading.Event()
thread=threading.Thread(target=observe,args=(threading.get_ident(),stopped),daemon=True)
print('OBSERVED_SCALING_PID='+str(os.getpid()),flush=True)
thread.start()
try:
    runpy.run_path(str(ROOT/'.akah_bot/run_scaling_v15.py'),run_name='__main__')
finally:
    stopped.set();thread.join(timeout=2)
