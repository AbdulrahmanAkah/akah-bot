import pytest
from v15_resource_guard import MIB
from v15_adaptive_guard import decision
from v15_resident_control import ResidentEnvelope


def sample(available=800, private=660, rss=740, resident=568, commit=2048):
    return {'available_physical_bytes': available*MIB, 'commit_available_bytes': commit*MIB,
            'process_private_bytes': private*MIB, 'process_rss_bytes': rss*MIB,
            'private_working_set_supported': True, 'process_private_working_set_bytes': resident*MIB}


def test_file_mappings_cannot_inflate_native_private_restore_requirement():
    e = ResidentEnvelope(); first = sample()
    assert e.action(first, None, resident_restore_bytes=740*MIB) == 'RUN'
    later = sample(available=620, rss=500, resident=470)
    assert decision(later, None, True, resident_restore_bytes=740*MIB) == 'WAIT'
    assert e.action(later, None, True, resident_restore_bytes=740*MIB) == 'RESUME'
    # Required native displacement 98MiB + unchanged 512MiB reserve = 610MiB.
    assert e.action(sample(available=609, rss=500, resident=470), None, True,
                    resident_restore_bytes=740*MIB) == 'WAIT'


@pytest.mark.parametrize('paused', [False, True])
def test_physical_and_commit_floors_not_relaxed(paused):
    e = ResidentEnvelope()
    for low in (sample(available=511), sample(commit=1023)):
        assert e.action(low, None, paused, resident_restore_bytes=740*MIB) == ('WAIT' if paused else 'PAUSE')


def test_growing_private_resident_peak_is_not_forgotten():
    e = ResidentEnvelope(); e.action(sample(resident=568), None, resident_restore_bytes=740*MIB)
    e.action(sample(private=700, resident=650), None, resident_restore_bytes=740*MIB)
    assert e.peak == 650*MIB
    assert e.action(sample(available=650, private=700, rss=500, resident=470), None, True,
                    resident_restore_bytes=740*MIB) == 'WAIT'


def test_any_unsupported_sample_keeps_old_conservative_rule_for_whole_run():
    e = ResidentEnvelope(); e.action(sample(), None, resident_restore_bytes=740*MIB)
    missing = sample(); missing.pop('process_private_working_set_bytes'); missing['private_working_set_supported'] = False
    e.action(missing, None, resident_restore_bytes=740*MIB)
    later = sample(available=620, rss=500, resident=470)
    assert e.action(later, None, True, resident_restore_bytes=740*MIB) == 'WAIT'
    assert e.action(later, None, True, resident_restore_bytes=740*MIB) == decision(later, None, True, resident_restore_bytes=740*MIB)


@pytest.mark.parametrize('bad', [0, -1, 661*MIB, 1.0])
def test_inconsistent_native_values_fail_closed(bad):
    e = ResidentEnvelope(); s = sample(); s['process_private_working_set_bytes'] = bad
    with pytest.raises(RuntimeError, match='INCONSISTENT'): e.action(s, None, resident_restore_bytes=740*MIB)


def test_new_owned_run_cannot_reuse_previous_workers_residency():
    first = ResidentEnvelope(); first.action(sample(resident=650), None, resident_restore_bytes=740*MIB)
    second = ResidentEnvelope(); second.action(sample(resident=100), None, resident_restore_bytes=740*MIB)
    assert first.peak == 650*MIB and second.peak == 100*MIB


def test_fixed_private_budget_is_still_enforced_before_resume():
    e = ResidentEnvelope()
    assert e.action(sample(), 192, True, resident_restore_bytes=740*MIB) == 'BUDGET_EXCEEDED'

