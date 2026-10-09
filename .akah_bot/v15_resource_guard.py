"""Operational safety only; no trading state or economic-rule modifications."""
import ctypes
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIB=1024**2

# ctypes caches POINTER(Structure) globally. Defining a new Counters class
# every sample retained thousands of distinct types in a long-lived monitor.
# Keep the same exact Windows layouts as stable module-level types.
class SystemMemory(ctypes.Structure):
    _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[
        (n,ctypes.c_ulonglong) for n in ('total','available','page_total','page_available',
                                       'virtual_total','virtual_available','extended')]


class ProcessCounters(ctypes.Structure):
    _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[
        (n,ctypes.c_size_t) for n in ('peak','rss','peak_paged','paged','peak_nonpaged',
                                   'nonpaged','pagefile','peak_pagefile','private')]


def below_normal():
    kernel=ctypes.windll.kernel32
    kernel.GetCurrentProcess.argtypes=[]
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.SetPriorityClass.restype=ctypes.c_int
    if not kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x4000):
        raise OSError('BELOW_NORMAL_PROCESS_PRIORITY_FAILED')


def resources():
    memory=SystemMemory();memory.length=ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise OSError('SYSTEM_MEMORY_OBSERVATION_FAILED')
    counters=ProcessCounters();counters.cb=ctypes.sizeof(counters)
    function=ctypes.windll.psapi.GetProcessMemoryInfo
    function.argtypes=[ctypes.c_void_p,ctypes.POINTER(ProcessCounters),ctypes.c_ulong]
    if not function(ctypes.c_void_p(-1),ctypes.byref(counters),counters.cb):
        raise OSError('PROCESS_MEMORY_OBSERVATION_FAILED')
    return {'available_physical_bytes':memory.available,'total_physical_bytes':memory.total,
            'commit_available_bytes':memory.page_available,'committed_bytes':memory.page_total-memory.page_available,
            'process_private_bytes':counters.private,'process_rss_bytes':counters.rss,'pid':os.getpid()}


class ResourceGuard:
    def __init__(self, name, *, max_private_mib=384, min_available_mib=512):
        self.name=name
        self.maximum=max_private_mib*MIB
        self.minimum=min_available_mib*MIB
        self.stopped=threading.Event()
        self.thread=None

    def breach(self, sample):
        return (sample['process_private_bytes']>self.maximum or
                sample['available_physical_bytes']<self.minimum or
                sample['commit_available_bytes']<1024*MIB)

    def start(self):
        if os.environ.get('AKAH_DELEGATED_GUARD_MANIFEST'):
            from v15_adaptive_guard import delegated_guard
            return delegated_guard()
        # Below-normal scheduling, one worker, no BLAS nested parallelism.
        below_normal()
        sample=resources()
        if self.breach(sample):
            self.record(sample, 'RESOURCE_PREFLIGHT_BLOCKED_NO_RUN')
            raise RuntimeError('RESOURCE_PREFLIGHT_BLOCKED_NO_RUN')
        self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start()
        return self

    def record(self, sample, status):
        payload=dict(sample,status=status,utc=datetime.now(timezone.utc).isoformat(),
            max_private_bytes=self.maximum,min_available_bytes=self.minimum,
            note='OPERATIONAL_SAFETY_ABORT_NOT_STRATEGY_OR_ECONOMIC_FAILURE')
        path=ROOT/'.akah_bot'/(self.name+'_resource_status.json')
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload,indent=2)+'\n')
        os.replace(temporary,path)
        return payload

    def watch(self):
        last_record=0.
        while not self.stopped.wait(1):
            try:
                sample=resources()
                if self.breach(sample):
                    print('RESOURCE_SAFETY_ABORT='+json.dumps(self.record(sample,'RESOURCE_SAFETY_ABORT')),flush=True)
                    # Abort this explicitly bound worker, never other apps.
                    # Partial profiling is not reused as parity/completion proof.
                    os._exit(75)
                if time.monotonic()-last_record>=10:
                    self.record(sample,'RUNNING_RESOURCE_BOUNDED')
                    last_record=time.monotonic()
            except Exception as exc:
                print('RESOURCE_MONITOR_FAILED='+repr(exc),flush=True)
                os._exit(76)

    def close(self):
        self.stopped.set()
        if self.thread is not None:self.thread.join(timeout=2)
