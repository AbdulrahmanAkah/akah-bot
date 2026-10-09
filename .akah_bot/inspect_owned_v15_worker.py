"""Read-only process telemetry for the nonce-bound research child only."""
import ctypes
import json
import time
from pathlib import Path
from v15_adaptive_guard import ROOT,processes,descendant
from v15_resource_guard import ProcessCounters

directory=ROOT/'.akah_bot/guarded-suite-20261007T165549/provider_v13-guardian'
manifest=json.loads((directory/'guardian_manifest.json').read_text())
receipt=json.loads((directory/'worker_handshake.json').read_text())
if receipt['nonce']!=manifest['nonce'] or not descendant(receipt['worker_pid'],manifest['guardian_pid'],processes()):
    raise RuntimeError('OWNED_WORKER_READ_AUTHORITY_REQUIRED')
k=ctypes.windll.kernel32
k.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];k.OpenProcess.restype=ctypes.c_void_p
k.GetProcessTimes.argtypes=[ctypes.c_void_p]+[ctypes.POINTER(ctypes.c_ulonglong)]*4
k.GetProcessTimes.restype=ctypes.c_int
k.CloseHandle.argtypes=[ctypes.c_void_p]
p=ctypes.windll.psapi
p.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
p.GetProcessMemoryInfo.restype=ctypes.c_int
handle=k.OpenProcess(0x0410,False,receipt['worker_pid'])
if not handle:raise OSError('READ_ONLY_OWNED_WORKER_HANDLE_FAILED')
samples=[]
try:
    for _ in range(3):
        c=ProcessCounters();c.cb=ctypes.sizeof(c)
        times=[ctypes.c_ulonglong() for _ in range(4)]
        if not p.GetProcessMemoryInfo(handle,ctypes.byref(c),c.cb) or not k.GetProcessTimes(handle,*map(ctypes.byref,times)):
            raise OSError('READ_ONLY_TELEMETRY_FAILED')
        samples.append({'unix_time':time.time(),'worker_pid':receipt['worker_pid'],
            'cpu_seconds':(times[2].value+times[3].value)/10000000,'page_fault_count':c.faults,
            'private_bytes':c.private,'resident_bytes':c.rss})
        time.sleep(1)
finally:k.CloseHandle(handle)
print(json.dumps({'samples':samples,'page_faults_are_not_hard_faults_alone':True}),flush=True)
