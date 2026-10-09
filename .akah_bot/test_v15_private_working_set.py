import ctypes
import pytest
from v15_private_working_set import native_sample,displaced_resident
from v15_resource_guard import MIB


def test_native_current_os_returns_consistent_private_resident_counter():
    s=native_sample(ctypes.c_void_p(-1))
    assert s['private_working_set_supported'] is True
    assert 0<s['process_private_working_set_bytes']<=min(s['process_private_bytes'],s['process_rss_bytes'])


def test_native_observer_does_not_leak_ctypes_types():
    native_sample(ctypes.c_void_p(-1));count=len(ctypes._pointer_type_cache)
    for _ in range(500):native_sample(ctypes.c_void_p(-1))
    assert len(ctypes._pointer_type_cache)==count


def test_reloadable_shared_mapping_not_counted_as_private_heap():
    s=dict(process_private_bytes=260*MIB,process_rss_bytes=110*MIB,
           available_physical_bytes=680*MIB,commit_available_bytes=2048*MIB,
           private_working_set_supported=True,process_private_working_set_bytes=100*MIB)
    assert displaced_resident(s,500*MIB)==160*MIB
    from v15_adaptive_guard import decision
    assert decision(s,384,True,resident_restore_bytes=500*MIB)=='RESUME'
    assert decision(dict(s,available_physical_bytes=511*MIB),384,True,resident_restore_bytes=500*MIB)=='WAIT'
    assert decision(dict(s,commit_available_bytes=1023*MIB),384,True,resident_restore_bytes=500*MIB)=='WAIT'
    assert decision(dict(s,process_private_bytes=385*MIB),384,True,resident_restore_bytes=500*MIB)=='BUDGET_EXCEEDED'


def test_unsupported_counter_keeps_original_conservative_resume_rule():
    s=dict(process_private_bytes=260*MIB,process_rss_bytes=110*MIB,private_working_set_supported=False)
    assert displaced_resident(s,500*MIB)==390*MIB


def test_counter_inconsistency_rejected_not_guessed():
    s=dict(process_private_bytes=260*MIB,process_rss_bytes=110*MIB,
           private_working_set_supported=True,process_private_working_set_bytes=200*MIB)
    with pytest.raises(RuntimeError,match='COUNTER_INCONSISTENT'):displaced_resident(s,500*MIB)


def test_private_resident_envelope_can_never_be_negative():
    s=dict(process_private_bytes=100*MIB,process_rss_bytes=110*MIB,
           private_working_set_supported=True,process_private_working_set_bytes=90*MIB)
    assert displaced_resident(s,80*MIB)==0
