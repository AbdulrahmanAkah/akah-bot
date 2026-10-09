"""Native owned-process counters: shared/mapped RSS is not private heap.

EX2 is used only when the OS returns positive, internally consistent private
working-set bytes. Unsupported/zero/inconsistent counters fail closed to the
older conservative total-RSS resume rule. Stable ctypes types do not leak.
"""
import ctypes
from v15_resource_guard import ProcessCounters


class ExtendedCounters(ctypes.Structure):
    _fields_=list(ProcessCounters._fields_)+[
        ('private_working_set',ctypes.c_size_t),('shared_commit',ctypes.c_size_t)]


def native_sample(handle):
    f=ctypes.windll.psapi.GetProcessMemoryInfo
    f.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong];f.restype=ctypes.c_int
    extended=ExtendedCounters();extended.cb=ctypes.sizeof(extended)
    ok=f(handle,ctypes.byref(extended),extended.cb)
    supported=bool(ok and 0<extended.private_working_set<=min(extended.private,extended.rss))
    if not ok:
        extended=ProcessCounters();extended.cb=ctypes.sizeof(extended)
        if not f(handle,ctypes.byref(extended),extended.cb):raise OSError('OWNED_MEMORY_SAMPLE_FAILED')
    result={'process_private_bytes':extended.private,'process_rss_bytes':extended.rss,
            'private_working_set_supported':supported}
    if supported:result['process_private_working_set_bytes']=extended.private_working_set
    return result


def displaced_resident(sample, resident_highwater):
    if sample.get('private_working_set_supported') is True:
        current=sample.get('process_private_working_set_bytes')
        if type(current) is not int or not 0<current<=min(sample['process_private_bytes'],sample['process_rss_bytes']):
            raise RuntimeError('PRIVATE_WORKING_SET_COUNTER_INCONSISTENT')
        # Every private resident page is bounded by both total historical RSS
        # and current private committed capacity. Subtract ONLY actual private
        # resident pages, never shared image or reloadable file mappings.
        required=min(resident_highwater,sample['process_private_bytes'])
        return max(0,required-current)
    return max(0,resident_highwater-sample['process_rss_bytes'])


if __name__=='__main__':
    import json
    print(json.dumps(native_sample(ctypes.c_void_p(-1))))
