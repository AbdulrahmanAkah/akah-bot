"""Independent, hidden local host for the existing certified replay.

No policy modifications or new guard bypass. The supervisor still authenticates
and owns its child job; only the outer launch no longer needs a live terminal.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'.akah_bot')]


def atomic(path, value):
    temp=path.with_suffix('.pending')
    temp.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    os.replace(temp,path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--probe',action='store_true')
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--directory',required=True)
    args=parser.parse_args()
    if args.probe==args.run:raise RuntimeError('EXACT_PROBE_OR_AUTHORIZED_RUN_REQUIRED')
    directory=Path(args.directory).resolve()
    if not directory.is_relative_to(ROOT/'.akah_bot'):raise RuntimeError('LAUNCH_DIRECTORY_ESCAPE')
    directory.mkdir(exist_ok=True)
    os.chdir(ROOT)
    os.environ.update(PYTHONPATH='src;.akah_bot;.',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',
                      MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1')
    def status(state,**extra):
        atomic(directory/'launcher_status.json',{'status':state,'pid':os.getpid(),
             'utc':datetime.now(timezone.utc).isoformat(),'other_apps_controlled':False,**extra})
    if args.probe:
        status('SYNTHETIC_LIFETIME_PROBE_RUNNING_NO_MARKET_ACCESS')
        for _ in range(8):
            time.sleep(1)
            status('SYNTHETIC_LIFETIME_PROBE_RUNNING_NO_MARKET_ACCESS')
        status('SYNTHETIC_LIFETIME_PROBE_COMPLETE_NO_MARKET_ACCESS')
        return
    kernel=ctypes.windll.kernel32
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
    kernel.CreateMutexW.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.WaitForSingleObject.restype=ctypes.c_ulong
    kernel.ReleaseMutex.argtypes=[ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.CreateMutexW(None,False,'Local\\AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15')
    if not handle:raise OSError('INDEPENDENT_LAUNCH_MUTEX_UNAVAILABLE')
    if kernel.WaitForSingleObject(handle,0) not in (0,128):
        kernel.CloseHandle(handle)
        status('DUPLICATE_INDEPENDENT_REPLAY_REFUSED')
        return
    with (directory/'stdout.log').open('x',encoding='utf-8',buffering=1) as out, \
         (directory/'stderr.log').open('x',encoding='utf-8',buffering=1) as err:
        sys.stdout=out;sys.stderr=err
        try:
            from v15_recoverable_worker import certified
            from v15_checkpoints import sha
            cert=certified()
            if cert.get('allocation_policy')!='HOST_PRESSURE_NO_FIXED_PRIVATE_CEILING':
                raise RuntimeError('USER_AUTHORIZED_PRESSURE_ONLY_MODE_REQUIRED')
            status('CERTIFIED_INDEPENDENT_REPLAY_DISPATCHED_NOT_COMPLETED',
                   certificate_sha256=sha(ROOT/'.akah_bot/v15_bounded_runtime_certificate.json'))
            from v15_guarded_economic_supervisor import main as replay
            replay()
            status('ALL_EIGHTEEN_ARMS_COMPLETE_AND_COLLECTED')
        except BaseException as exc:
            traceback.print_exc()
            status('INCOMPLETE_REPAIR_REQUIRED_NOT_ECONOMIC_CONCLUSION',error=repr(exc))
            raise
        finally:
            kernel.ReleaseMutex(handle);kernel.CloseHandle(handle)


if __name__=='__main__':main()
