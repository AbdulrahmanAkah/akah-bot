"""Give only the tiny AKAH control loop scheduling priority over its worker.

No heartbeat deadline, reserve, suspension or ownership rule is weakened.
No unrelated app's priority or memory is changed. Not a liveness guarantee.
"""
import ctypes
import json
import os
from pathlib import Path
import tempfile
import v15_adaptive_guard as guard

INSTALLED = False


def publish_observation(path, value, *, writer=None):
    """A reader's delete-denying handle is not loss of memory protection.

    Only best-effort status observations may use this alternate DURABLE record.
    Runtime manifests, handshakes, economic files, or failure to write the
    alternate record still fail closed. No observation is fabricated as fresh.
    """
    writer = guard.atomic if writer is None else writer
    try:
        return writer(path, value)
    except PermissionError as exc:
        if Path(path).name != 'status.json' or getattr(exc, 'winerror', None) not in (5, 32, 33):
            raise
        fd, name = tempfile.mkstemp(prefix='status-observation-', suffix='.json', dir=Path(path).parent)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(dict(value, telemetry_canonical_replace_deferred=True,
                           telemetry_deferred_winerror=exc.winerror), stream, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        return Path(name)


def control_priority():
    if os.environ.get('AKAH_DELEGATED_GUARD_MANIFEST'):
        from v15_resource_guard import below_normal
        return below_normal()
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.GetCurrentThread.restype = ctypes.c_void_p
    kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
    if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x20):
        raise OSError('CONTROL_NORMAL_PRIORITY_FAILED')
    if not kernel.SetThreadPriority(kernel.GetCurrentThread(), 1):
        raise OSError('CONTROL_THREAD_PRIORITY_FAILED')


def install():
    global INSTALLED
    if INSTALLED: return
    old_atomic = guard.atomic
    def atomic(path, value):
        if Path(path).name == 'guardian_manifest.json':
            value = dict(value)
            value['runtime_bindings'] = dict(value['runtime_bindings'])
            value['runtime_bindings']['.akah_bot/v15_control_priority.py'] = guard.sha(__file__)
            value['control_priority_policy'] = 'NORMAL_PROCESS_ABOVE_NORMAL_CONTROL_THREAD_BELOW_NORMAL_WORKER'
        if Path(path).name == 'status.json':
            return publish_observation(path, value, writer=old_atomic)
        return old_atomic(path, value)
    guard.below_normal = control_priority; guard.atomic = atomic
    INSTALLED = True

