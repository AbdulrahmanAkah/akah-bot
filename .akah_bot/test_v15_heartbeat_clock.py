"""No market/replay: heartbeat clock and five-second safety remain exact."""
from v15_adaptive_guard import heartbeat_failure, observe_heartbeat


def test_monotonic_clock_accepts_fresh_exact_guardian():
    assert heartbeat_failure((120.,11),11,124.999) is None
    assert heartbeat_failure((120.,11),11,125.) is None


def test_clock_changes_do_not_change_monotonic_freshness(monkeypatch):
    import time
    for unix in (0.,1e12,-1e12):
        monkeypatch.setattr(time,'time',lambda:unix)
        assert heartbeat_failure((120.,11),11,124.) is None


def test_stale_missing_drifted_and_future_beats_still_fail_closed():
    assert heartbeat_failure((120.,11),11,125.001)=='HEARTBEAT_STALE'
    assert heartbeat_failure(None,11,124.)=='SEQUENCE_READ_NOT_STABLE'
    assert heartbeat_failure((120.,12),11,124.)=='GUARDIAN_ID_DRIFT'
    assert heartbeat_failure((126.,11),11,124.)=='HEARTBEAT_FROM_FUTURE'


def test_descheduled_reader_rechecks_new_current_beat_not_old_snapshot():
    beats=iter([(120.,11),(130.,11)])
    times=iter([130.,130.1])
    reason,beat,now=observe_heartbeat(None,11,reader=lambda _:next(beats),clock=lambda:next(times))
    assert reason is None and beat==(130.,11) and now==130.1


def test_recheck_does_not_extend_five_second_deadline():
    reason,beat,now=observe_heartbeat(None,11,reader=lambda _:(120.,11),clock=lambda:125.001)
    assert reason=='HEARTBEAT_STALE'


def test_recheck_requires_current_exact_guardian_identity():
    beats=iter([(120.,11),(130.,12)])
    reason,_,_=observe_heartbeat(None,11,reader=lambda _:next(beats),clock=lambda:130.1)
    assert reason=='GUARDIAN_ID_DRIFT'


def test_non_stale_identity_error_is_not_retried():
    calls=[]
    def read(_):calls.append(1);return 120.,12
    reason,_,_=observe_heartbeat(None,11,reader=read,clock=lambda:124.)
    assert reason=='GUARDIAN_ID_DRIFT' and len(calls)==1
