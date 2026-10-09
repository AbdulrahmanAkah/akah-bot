import pytest
from v15_adaptive_guard import decision, launch_allowance, MIB


@pytest.mark.parametrize('private', [385, 512, 1024, 2048])
def test_allocation_alone_does_not_kill_pressure_only_replay(private):
    sample={'available_physical_bytes':900*MIB,'commit_available_bytes':2048*MIB,
            'process_private_bytes':private*MIB,'process_rss_bytes':private*MIB}
    assert decision(sample,None)=='RUN'
    assert decision(dict(sample,available_physical_bytes=511*MIB),None)=='PAUSE'
    assert decision(dict(sample,commit_available_bytes=1023*MIB),None)=='PAUSE'


def test_displaced_resident_floor_remains_real():
    sample={'available_physical_bytes':700*MIB,'commit_available_bytes':2048*MIB,
            'process_private_bytes':800*MIB,'process_rss_bytes':100*MIB}
    assert decision(sample,None,True,resident_restore_bytes=500*MIB)=='WAIT'
    assert decision(dict(sample,available_physical_bytes=1000*MIB),None,True,
                    resident_restore_bytes=500*MIB)=='RESUME'


def test_bootstrap_cannot_silently_disable_reserve():
    assert launch_allowance(None,128)==128
    with pytest.raises(ValueError):launch_allowance(None)
    with pytest.raises(ValueError):launch_allowance(None,0)


def test_existing_bounded_diagnostic_mode_not_weakened():
    sample={'available_physical_bytes':900*MIB,'commit_available_bytes':2048*MIB,
            'process_private_bytes':385*MIB,'process_rss_bytes':300*MIB}
    assert decision(sample,384)=='BUDGET_EXCEEDED'
