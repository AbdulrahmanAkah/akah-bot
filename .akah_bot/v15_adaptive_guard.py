"""Scoped Windows suspension/working-set trim, not a trading-policy change.

Only handles to nonce-authenticated descendants of a child we just created may
be suspended/resumed/trimmed. No existing app, service or unrelated PID is
selected. The fixed 512 MiB physical / 1 GiB commit reserves remain unchanged.
The smaller child budget is compensated by a smaller launch envelope, rather
than lowering the running reserve. This does not promise system responsiveness
when other applications independently exhaust RAM.
"""
import ctypes
from datetime import datetime,timezone
import hashlib
import json
import mmap
import os
from pathlib import Path
import secrets
import queue
import subprocess
import struct
import threading
import time
from v15_resource_guard import ROOT,MIB,below_normal,resources,ProcessCounters


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda:stream.read(MIB),b''):h.update(part)
    return h.hexdigest().upper()


def atomic(path,value):
    path=Path(path);tmp=path.with_suffix('.pending')
    tmp.write_text(json.dumps(value,indent=2)+'\n')
    # Windows readers/antivirus may momentarily hold a replace-denying handle.
    # Bounded retries of the exact same bytes; never bypass a persistent error.
    for attempt in range(21):
        try:
            os.replace(tmp,path);return
        except PermissionError:
            if attempt==20:raise
            time.sleep(.025)


class GuardTelemetry:
    """Bounded non-safety I/O; never manufacture a guardian heartbeat.

    Slow console/disk consumers must not block resource observation/control.
    Ordered pause/resume events are retained; intermediate status snapshots
    may coalesce, because they are observations, not replay/decision records.
    Any writer error or event backlog overflow still fails closed.
    """
    def __init__(self, directory, *, writer=None, printer=None):
        self.directory=Path(directory)
        self.writer=atomic if writer is None else writer
        self.printer=(lambda value:print(value,flush=True)) if printer is None else printer
        self.events=queue.Queue(maxsize=256)
        self.lock=threading.Lock();self.latest=None;self.error=None
        self.stopped=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def check(self):
        if self.error is not None:raise RuntimeError('GUARD_TELEMETRY_FAILED') from self.error

    def emit(self, message):
        self.check()
        try:self.events.put_nowait(message)
        except queue.Full as exc:raise RuntimeError('GUARD_TELEMETRY_BACKLOG_EXCEEDED') from exc

    def status(self, value):
        self.check()
        with self.lock:self.latest=value

    def run(self):
        try:
            while True:
                try:message=self.events.get(timeout=.05)
                except queue.Empty:message=None
                if message is not None:self.printer(message)
                with self.lock:
                    value=self.latest;self.latest=None
                if value is not None:self.writer(self.directory/'status.json',value)
                if self.stopped.is_set() and self.events.empty():
                    with self.lock:pending=self.latest is not None
                    if not pending:return
        except BaseException as exc:self.error=exc

    def close(self):
        self.stopped.set();self.thread.join(timeout=30)
        self.check()
        if self.thread.is_alive():raise RuntimeError('GUARD_TELEMETRY_FLUSH_TIMEOUT')


def processes():
    class Entry(ctypes.Structure):
        _fields_=[('size',ctypes.c_ulong),('usage',ctypes.c_ulong),('pid',ctypes.c_ulong),
                  ('heap',ctypes.c_size_t),('module',ctypes.c_ulong),('threads',ctypes.c_ulong),
                  ('parent',ctypes.c_ulong),('priority',ctypes.c_long),('flags',ctypes.c_ulong),
                  ('exe',ctypes.c_wchar*260)]
    k=ctypes.windll.kernel32
    k.CreateToolhelp32Snapshot.argtypes=[ctypes.c_ulong,ctypes.c_ulong];k.CreateToolhelp32Snapshot.restype=ctypes.c_void_p
    for name in ('Process32FirstW','Process32NextW'):
        f=getattr(k,name);f.argtypes=[ctypes.c_void_p,ctypes.POINTER(Entry)];f.restype=ctypes.c_int
    k.CloseHandle.argtypes=[ctypes.c_void_p];k.CloseHandle.restype=ctypes.c_int
    handle=k.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:raise OSError('PROCESS_OWNERSHIP_SNAPSHOT_FAILED')
    entry=Entry();entry.size=ctypes.sizeof(entry);result={}
    try:
        valid=k.Process32FirstW(handle,ctypes.byref(entry))
        while valid:
            result[entry.pid]=(entry.parent,entry.exe)
            valid=k.Process32NextW(handle,ctypes.byref(entry))
    finally:k.CloseHandle(handle)
    return result


def descendant(pid,ancestor,tree):
    seen=set()
    while pid in tree and pid not in seen:
        if pid==ancestor:return True
        seen.add(pid);pid=tree[pid][0]
    return False


def start_ready(sample,budget_mib):
    return (sample['available_physical_bytes']>=(512+budget_mib)*MIB and
            sample['commit_available_bytes']>=(1024+budget_mib)*MIB)


def decision(sample,budget_mib,paused=False,*,resident_restore_bytes=None):
    # Explicit pressure-only mode: a private-allocation ceiling is not a
    # measure of host pressure. Retain real physical/commit reserves and
    # displaced-resident checks; do not kill a checkpoint for crossing 384MiB.
    if budget_mib is not None and sample['process_private_bytes']>budget_mib*MIB:return 'BUDGET_EXCEEDED'
    if paused:
        if resident_restore_bytes is None:
            return 'RESUME' if start_ready(sample,0 if budget_mib is None else budget_mib) else 'WAIT'
        # Already committed/resident pages do not need a second full private
        # allocation budget. Reserve the exact displaced resident high-water
        # bytes instead. The 512MiB / 1GiB running reserves remain unchanged.
        from v15_private_working_set import displaced_resident
        displaced=displaced_resident(sample,resident_restore_bytes)
        return ('RESUME' if sample['available_physical_bytes']>=512*MIB+displaced
                and sample['commit_available_bytes']>=1024*MIB else 'WAIT')
    return ('PAUSE' if sample['available_physical_bytes']<512*MIB or
            sample['commit_available_bytes']<1024*MIB else 'RUN')


class OwnedProcess:
    def __init__(self,pid,created_child_pid,guardian_pid):
        tree=processes()
        if pid==guardian_pid or not descendant(pid,created_child_pid,tree):
            raise RuntimeError('REFUSE_UNOWNED_PROCESS_CONTROL')
        self.pid=pid;self.paused=False
        k=ctypes.windll.kernel32
        k.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong];k.OpenProcess.restype=ctypes.c_void_p
        self.handle=k.OpenProcess(0x0400|0x1000|0x0010|0x0100|0x0800|0x0001,False,pid)
        if not self.handle:raise OSError('OWNED_PROCESS_HANDLE_FAILED')
        # A retained handle binds the original process even if a PID is reused.
        k.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
        k.GetExitCodeProcess.restype=ctypes.c_int
        k.TerminateProcess.argtypes=[ctypes.c_void_p,ctypes.c_uint];k.TerminateProcess.restype=ctypes.c_int
        for name in ('NtSuspendProcess','NtResumeProcess'):
            function=getattr(ctypes.windll.ntdll,name)
            function.argtypes=[ctypes.c_void_p];function.restype=ctypes.c_long
        p=ctypes.windll.psapi
        p.EmptyWorkingSet.argtypes=[ctypes.c_void_p];p.EmptyWorkingSet.restype=ctypes.c_int
        p.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
        p.GetProcessMemoryInfo.restype=ctypes.c_int
    def sample(self):
        from v15_private_working_set import native_sample
        return native_sample(self.handle)
    def suspend(self):
        if self.paused:return
        if ctypes.windll.ntdll.NtSuspendProcess(self.handle)!=0:raise OSError('OWNED_SUSPEND_FAILED')
        self.paused=True
        # Do not discard every hot page on every pause. Windows can reclaim
        # these pages when necessary. Repeated EmptyWorkingSet produced a
        # suspend/page-reload cycle even for an ~85MiB private test worker.
        return False
    def resume(self):
        if not self.paused:return
        if ctypes.windll.ntdll.NtResumeProcess(self.handle)!=0:raise OSError('OWNED_RESUME_FAILED')
        self.paused=False
    def alive(self):
        code=ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(self.handle,ctypes.byref(code)):
            raise OSError('OWNED_EXIT_QUERY_FAILED')
        return code.value==259
    def stop_failed(self,code):
        if self.alive() and not ctypes.windll.kernel32.TerminateProcess(self.handle,code):
            raise OSError('OWNED_FAILED_WORKER_STOP_FAILED')
    def close(self):ctypes.windll.kernel32.CloseHandle(self.handle)


class OwnedJob:
    """Fail-safe lifetime for freshly created children, never existing apps."""
    def __init__(self):
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
                      ('flags',ctypes.c_ulong),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),
                      ('active',ctypes.c_ulong),('affinity',ctypes.c_size_t),
                      ('priority',ctypes.c_ulong),('scheduling',ctypes.c_ulong)]
        class IO(ctypes.Structure):
            _fields_=[(name,ctypes.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read','write','other')]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO)]+[(name,ctypes.c_size_t) for name in
                ('process_memory','job_memory','peak_process_memory','peak_job_memory')]
        k=ctypes.windll.kernel32
        k.CreateJobObjectW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p];k.CreateJobObjectW.restype=ctypes.c_void_p
        k.SetInformationJobObject.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong]
        k.SetInformationJobObject.restype=ctypes.c_int
        k.AssignProcessToJobObject.argtypes=[ctypes.c_void_p,ctypes.c_void_p];k.AssignProcessToJobObject.restype=ctypes.c_int
        k.IsProcessInJob.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]
        k.IsProcessInJob.restype=ctypes.c_int
        self.handle=k.CreateJobObjectW(None,None)
        if not self.handle:raise OSError('OWNED_JOB_CREATE_FAILED')
        info=Extended();info.basic.flags=0x2000 # KILL_ON_JOB_CLOSE, no inheritance.
        if not k.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)):
            self.close();raise OSError('OWNED_JOB_LIFETIME_BINDING_FAILED')
    def assign(self,owned):
        present=ctypes.c_int();k=ctypes.windll.kernel32
        if not k.IsProcessInJob(owned.handle,self.handle,ctypes.byref(present)):
            raise OSError('OWNED_JOB_QUERY_FAILED')
        if not present.value and not k.AssignProcessToJobObject(self.handle,owned.handle):
            raise OSError('OWNED_JOB_ASSIGN_FAILED')
    def close(self):
        if self.handle:
            ctypes.windll.kernel32.CloseHandle(self.handle);self.handle=None


class DelegatedGuard:
    def __init__(self,manifest):
        self.manifest=manifest;self.stopped=threading.Event();self.thread=None
    def start(self):
        below_normal()
        tree=processes();guardian=self.manifest['guardian_pid']
        if (not descendant(os.getpid(),guardian,tree) or guardian==os.getpid() or
                self.manifest['minimum_physical_mib']!=512 or self.manifest['minimum_commit_mib']!=1024 or
                self.manifest.get('heartbeat_clock')!='SYSTEM_MONOTONIC'):
            raise RuntimeError('EXACT_INDEPENDENT_PARENT_GUARDIAN_REQUIRED')
        for path,binding in self.manifest['runtime_bindings'].items():
            if sha(ROOT/path)!=binding:raise RuntimeError('GUARDIAN_RUNTIME_BINDING_DRIFT')
        self.heartbeat_memory=mmap.mmap(-1,32,tagname=self.manifest['heartbeat_tag'])
        atomic(self.manifest['handshake'],{'worker_pid':os.getpid(),'nonce':self.manifest['nonce'],
               'guardian_pid':guardian,'utc':datetime.now(timezone.utc).isoformat()})
        self.thread=threading.Thread(target=self.watch,daemon=True);self.thread.start();return self
    def watch(self):
        while not self.stopped.wait(1):
            try:
                # A suspended reader must not hold a replace-denying file
                # handle needed by its guardian. Use nonce-bound shared memory
                # and a sequence lock, not a replaceable heartbeat JSON.
                reason,beat,now=observe_heartbeat(self.heartbeat_memory,self.manifest['guardian_pid'])
                if reason:
                    print('GUARDIAN_HEARTBEAT_FORENSIC='+json.dumps({'reason':reason,
                        'beat':beat,'observed_monotonic':now,'worker_pid':os.getpid(),
                        'expected_guardian':self.manifest['guardian_pid'],
                        'observed_utc':datetime.now(timezone.utc).isoformat()}),flush=True)
                    raise RuntimeError('INDEPENDENT_GUARDIAN_LOST:'+reason)
            except Exception as exc:
                print('GUARDIAN_SAFETY_FAILURE='+repr(exc),flush=True);os._exit(76)
    def close(self):
        self.stopped.set()
        if self.thread is not None:self.thread.join(timeout=2)
        if hasattr(self,'heartbeat_memory'):self.heartbeat_memory.close()


def delegated_guard():
    path=Path(os.environ['AKAH_DELEGATED_GUARD_MANIFEST']).resolve()
    if not path.is_relative_to(ROOT/'.akah_bot'):raise RuntimeError('UNBOUND_GUARDIAN_MANIFEST_PATH')
    manifest=json.loads(path.read_text())
    for key in ('heartbeat','handshake'):
        if not Path(manifest[key]).resolve().is_relative_to(path.parent):raise RuntimeError('GUARDIAN_PATH_ESCAPE')
    return DelegatedGuard(manifest).start()


def heartbeat_failure(beat, guardian_pid, now):
    """Cross-process monotonic clock, unaffected by wall-clock corrections."""
    if beat is None:return 'SEQUENCE_READ_NOT_STABLE'
    if beat[1]!=guardian_pid:return 'GUARDIAN_ID_DRIFT'
    if beat[0]>now+1:return 'HEARTBEAT_FROM_FUTURE'
    if now-beat[0]>5:return 'HEARTBEAT_STALE'
    return None


def read_heartbeat(memory):
    for _ in range(10):
        first=memory[:24]
        version,at,guardian=struct.unpack('<QdQ',first)
        if not version%2 and first==memory[:24]:return at,guardian
        time.sleep(.001)
    return None


def observe_heartbeat(memory, guardian_pid, *, reader=None, clock=None):
    """Re-read a stale snapshot once after reader descheduling/page faults.

    The five-second deadline stays exact: a genuinely stale CURRENT beat
    fails. A new valid beat, not a longer timeout, is needed to clear failure.
    Other identity/sequence/future errors never get softened by a retry.
    """
    reader=read_heartbeat if reader is None else reader
    clock=time.monotonic if clock is None else clock
    beat=reader(memory);now=clock();reason=heartbeat_failure(beat,guardian_pid,now)
    if reason=='HEARTBEAT_STALE':
        beat=reader(memory);now=clock();reason=heartbeat_failure(beat,guardian_pid,now)
    return reason,beat,now


def launch_allowance(budget_mib, startup_allowance_mib=None):
    """Maximum allocation is not an up-front allocation by a fresh interpreter.

    The optional tested bootstrap envelope affects launch only. The live
    physical/commit floors, process budget and pressure pause are unchanged.
    """
    if budget_mib is None:
        if startup_allowance_mib is None or not 16<=int(startup_allowance_mib)<=384:
            raise ValueError('PRESSURE_ONLY_REQUIRES_EXPLICIT_BOOTSTRAP_ENVELOPE')
        return int(startup_allowance_mib)
    budget_mib=int(budget_mib)
    if not 16<=budget_mib<=384:raise ValueError('EXPLICIT_SMALL_WORKER_BUDGET_REQUIRED')
    value=budget_mib if startup_allowance_mib is None else int(startup_allowance_mib)
    if not 16<=value<=budget_mib:raise ValueError('BOOTSTRAP_ENVELOPE_OUTSIDE_PROCESS_BUDGET')
    return value


def run_guarded(args,directory,environment,*,budget_mib=192,pressure_test=None,startup_allowance_mib=None):
    """One authenticated child. Test injection may LOWER availability only."""
    directory=Path(directory).resolve()
    if not directory.is_relative_to(ROOT/'.akah_bot'):raise RuntimeError('GUARD_RUN_DIRECTORY_OUT_OF_SCOPE')
    directory.mkdir(exist_ok=False)
    below_normal()
    budget_mib=None if budget_mib is None else int(budget_mib)
    bootstrap_mib=launch_allowance(budget_mib,startup_allowance_mib)
    started=time.monotonic();last_print=0;stable=0
    while True:
        sample=resources()
        stable=stable+1 if start_ready(sample,bootstrap_mib) else 0
        if stable>=3:break
        if time.monotonic()-last_print>=30:
            print('WAITING_SMALL_WORKER_RESERVE='+json.dumps(sample),flush=True);last_print=time.monotonic()
        time.sleep(.2)
    nonce=secrets.token_hex(32)
    manifest={'guardian_pid':os.getpid(),'nonce':nonce,'worker_private_budget_mib':budget_mib,
        'allocation_policy':'HOST_PRESSURE_NO_FIXED_PRIVATE_CEILING' if budget_mib is None else 'FIXED_PRIVATE_CEILING',
        'bootstrap_allowance_mib':bootstrap_mib,
        'heartbeat_clock':'SYSTEM_MONOTONIC',
        'resident_resume_policy':'NATIVE_PRIVATE_RESIDENT_ENVELOPE_IF_SUPPORTED_ELSE_CONSERVATIVE_TOTAL_RSS',
        'minimum_physical_mib':512,'minimum_commit_mib':1024,
        'heartbeat':str(directory/'guardian_heartbeat.json'),'handshake':str(directory/'worker_handshake.json'),
        'heartbeat_tag':'AKAH_V15_GUARD_'+nonce,
        'runtime_bindings':{'.akah_bot/v15_adaptive_guard.py':sha(__file__),
                            '.akah_bot/v15_resource_guard.py':sha(ROOT/'.akah_bot/v15_resource_guard.py'),
                            '.akah_bot/v15_private_working_set.py':sha(ROOT/'.akah_bot/v15_private_working_set.py')}}
    manifest_path=directory/'guardian_manifest.json';atomic(manifest_path,manifest)
    memory=mmap.mmap(-1,32,tagname=manifest['heartbeat_tag']);generation=0
    def heartbeat():
        nonlocal generation
        generation+=2
        memory[:8]=struct.pack('<Q',generation-1)
        memory[8:24]=struct.pack('<dQ',time.monotonic(),os.getpid())
        memory[:8]=struct.pack('<Q',generation)
    heartbeat();env=dict(environment,AKAH_DELEGATED_GUARD_MANIFEST=str(manifest_path))
    owned=None;launcher=None;job=OwnedJob();paused_seconds=0.;pauses=0;pause_at=None;max_private=0;max_rss=0
    telemetry=GuardTelemetry(directory)
    try:
        with (directory/'stdout.log').open('x') as out,(directory/'stderr.log').open('x') as err:
            child=subprocess.Popen(args,cwd=ROOT,env=env,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            launched=time.monotonic()
            launcher=OwnedProcess(child.pid,child.pid,os.getpid())
            job.assign(launcher)
            handshake_deadline=time.monotonic()+30;last_heartbeat=0;last_status=0;resume_stable=0
            while child.poll() is None:
                telemetry.check()
                now=time.monotonic()
                if now-last_heartbeat>=1:heartbeat();last_heartbeat=now
                if owned is None:
                    if Path(manifest['handshake']).exists():
                        receipt=json.loads(Path(manifest['handshake']).read_text())
                        if receipt['nonce']!=manifest['nonce'] or receipt['guardian_pid']!=os.getpid():
                            raise RuntimeError('WORKER_HANDSHAKE_DRIFT')
                        owned=OwnedProcess(receipt['worker_pid'],child.pid,os.getpid())
                        job.assign(owned)
                    elif now>handshake_deadline:raise RuntimeError('NO_WORKER_HANDSHAKE')
                if owned is not None:
                    if not owned.alive():break
                    sample=dict(resources(),**owned.sample())
                    max_private=max(max_private,sample['process_private_bytes']);max_rss=max(max_rss,sample['process_rss_bytes'])
                    if pressure_test is not None:
                        requested=pressure_test(now-launched)
                        if requested is not None:sample['available_physical_bytes']=min(sample['available_physical_bytes'],requested)
                    action=decision(sample,budget_mib,owned.paused,resident_restore_bytes=max_rss)
                    if action=='BUDGET_EXCEEDED':
                        owned.stop_failed(75);break
                    if action=='PAUSE':
                        trimmed=owned.suspend();pause_at=now;pauses+=1;resume_stable=0
                        telemetry.emit('OWN_WORKER_PAUSED='+json.dumps(dict(sample,forced_working_set_trim=trimmed,worker_pid=owned.pid)))
                    elif action=='RESUME':
                        resume_stable+=1
                        if resume_stable>=3:
                            owned.resume();paused_seconds+=now-pause_at;pause_at=None;resume_stable=0
                            telemetry.emit('OWN_WORKER_RESUMED='+str(owned.pid))
                    elif action=='WAIT':resume_stable=0
                    if now-last_status>=2 or action=='PAUSE':
                        telemetry.status({'status':'PAUSED_PRESSURE_NO_PROGRESS_LOST' if owned.paused else 'RUNNING_SMALL_OWNED_WORKER',
                            'worker_pid':owned.pid,'guardian_pid':os.getpid(),'pauses':pauses,'resources':sample,
                            'utc':datetime.now(timezone.utc).isoformat()})
                        last_status=now
                time.sleep(.2)
            exitcode=child.wait()
        telemetry.close()
        if pause_at is not None:paused_seconds+=time.monotonic()-pause_at
        receipt={'os_exit_code':exitcode,'worker_pid':None if owned is None else owned.pid,'wrapper_pid':child.pid,
            'allocation_policy':manifest['allocation_policy'],
            'guardian_pid':os.getpid(),'pauses':pauses,'paused_seconds':paused_seconds,'budget_mib':budget_mib,
            'bootstrap_allowance_mib':bootstrap_mib,
            'peak_sampled_private_bytes':max_private,'peak_sampled_rss_bytes':max_rss,'wall_seconds':time.monotonic()-started,
            'forced_working_set_trim':False,'resume_reserve':'512MiB plus conservative private resident displacement if native counter valid; unsupported uses old total-RSS bound; commit>=1GiB',
            'stdout':str(directory/'stdout.log'),'stderr':str(directory/'stderr.log'),'other_apps_controlled':False}
        receipt['kill_on_guardian_loss_job_bound']=True
        atomic(directory/'exit_receipt.json',receipt);return receipt
    except BaseException:
        if owned is not None:owned.stop_failed(76)
        raise
    finally:
        if owned is not None:owned.close()
        job.close()
        if launcher is not None:launcher.close()
        telemetry.stopped.set()
        memory.close()
