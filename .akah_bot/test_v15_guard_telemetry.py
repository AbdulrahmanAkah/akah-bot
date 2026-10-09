"""Synthetic blocked I/O tests; no market rows, policies or economics."""
import threading
import time
import pytest
from v15_adaptive_guard import GuardTelemetry


def test_slow_status_sink_cannot_block_control_thread_and_latest_is_retained(tmp_path):
    entered=threading.Event();release=threading.Event();values=[]
    def write(path,value):
        entered.set()
        assert release.wait(5)
        values.append(value)
    t=GuardTelemetry(tmp_path,writer=write,printer=lambda _:None)
    try:
        t.status({'n':0});assert entered.wait(2)
        begin=time.monotonic()
        for n in range(1,101):t.status({'n':n});t.check()
        assert time.monotonic()-begin<1
        release.set();t.close()
        assert values==[{'n':0},{'n':100}]
    finally:release.set();t.stopped.set();t.thread.join(2)


def test_pause_resume_events_are_ordered_not_dropped(tmp_path):
    values=[];t=GuardTelemetry(tmp_path,writer=lambda *_:None,printer=values.append)
    for n in range(100):t.emit(str(n))
    t.close()
    assert values==[str(n) for n in range(100)]


def test_writer_failure_is_visible_and_fails_closed(tmp_path):
    failed=threading.Event()
    def write(*_):failed.set();raise OSError('synthetic writer failure')
    t=GuardTelemetry(tmp_path,writer=write,printer=lambda _:None)
    t.status({});assert failed.wait(2);t.thread.join(2)
    with pytest.raises(RuntimeError,match='TELEMETRY_FAILED'):t.check()


def test_bounded_event_backlog_overflow_fails_closed(tmp_path):
    entered=threading.Event();release=threading.Event()
    def print_blocked(_):entered.set();release.wait(5)
    t=GuardTelemetry(tmp_path,writer=lambda *_:None,printer=print_blocked)
    try:
        t.emit('first');assert entered.wait(2)
        for n in range(256):t.emit(str(n))
        with pytest.raises(RuntimeError,match='BACKLOG_EXCEEDED'):t.emit('overflow')
    finally:release.set();t.close()
