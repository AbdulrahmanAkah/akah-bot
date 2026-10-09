"""Observational launcher: no changes to the frozen replay or market decisions."""
import json
import os
import runpy
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def sample_stack(frame):
    state = {"arm": "NOT_STARTED", "phase": "IMPORT_OR_PREFLIGHT", "market_clock_sample": None}
    while frame is not None:
        path = Path(frame.f_code.co_filename)
        name = frame.f_code.co_name
        values = frame.f_locals
        if name == "execute_authorized" and path.name == "runner.py":
            state["arm"] = str(values.get("arm", "NOT_STARTED"))
            state["phase"] = "INPUT_LOAD_OR_REPLAY"
        if name == "run" and path.name == "scheduler.py" and "at" in values:
            state["market_clock_sample"] = str(values["at"])
        frame = frame.f_back
    return state


def observe(main_thread, stopped):
    began = time.monotonic()
    while not stopped.wait(20):
        try:
            frame = sys._current_frames().get(main_thread)
            state = sample_stack(frame)
            state.update(wall_seconds=round(time.monotonic() - began),
                         utc=datetime.now(timezone.utc).isoformat(), pid=os.getpid(),
                         note="STACK_SAMPLE_NOT_COMPLETED_CHECKPOINT_OR_ECONOMIC_RESULT")
            print("REPLAY_HEARTBEAT=" + json.dumps(state, sort_keys=True), flush=True)
        except Exception as exc:
            print("OBSERVER_WARNING=" + type(exc).__name__, flush=True)


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / ".akah_bot"))
    stopped = threading.Event()
    observer = threading.Thread(target=observe, args=(threading.get_ident(), stopped), daemon=True)
    print("OBSERVED_RESTART_PID=" + str(os.getpid()), flush=True)
    receipt_path = repo / '.akah_bot/v15_replay_process_receipt.json'
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        receipt.update(worker_pid=os.getpid(), launcher_pid=os.getppid(),
                       started_at_utc=datetime.now(timezone.utc).isoformat(),
                       status_at_last_check='RUNNING_NOT_COMPLETE',
                       supplemental_acceleration='Explicit separately hashed, differential-tested runtime cache; no policy changes')
        receipt_path.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    observer.start()
    try:
        runpy.run_path(str(repo / ".akah_bot/run_frozen_v15.py"), run_name="__main__")
    finally:
        stopped.set()
        observer.join(timeout=2)
