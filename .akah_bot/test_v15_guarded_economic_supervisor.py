"""Only orchestration mocks; no worker, market reader, replay or trading."""
import json
import pytest
import v15_guarded_economic_supervisor as s


def setup(tmp_path,monkeypatch,ready=True):
    monkeypatch.setattr(s,'ROOT',tmp_path)
    local=tmp_path/'.akah_bot';local.mkdir()
    task='AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15'
    (local/'v15_bounded_runtime_certificate.json').write_text(json.dumps({
        'ready_for_frozen_recoverable_replay':ready,'runtime_bindings':{},'economic_worker_private_budget_mib':192,'bootstrap_allowance_mib':128}))
    (local/'v15_replay_authorization.json').write_text(json.dumps({'task_id':task,'explicit_user_replay_authorization':True,'precommit_sha256':'P'}))
    (local/'active_task.json').write_text(json.dumps({'task_id':task}))
    frozen=tmp_path/'governance/all_nine_eighteen_arm_readiness_v15';frozen.mkdir(parents=True)
    arms=[f'SYNTHETIC_{i}|{c}' for i in range(9) for c in ('1X','2X')]
    (frozen/'gate3_precommit.json').write_text(json.dumps({'precommit_sha256':'P','contract':{'arms':arms}}))
    return local,arms


def test_unarmed_never_launches(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,False)
    monkeypatch.setattr(s,'run_guarded',lambda *a,**k:pytest.fail('UNARMED_MUST_NOT_LAUNCH'))
    with pytest.raises(RuntimeError,match='NOT_CERTIFIED'):s.main()


def test_exact_eighteen_then_saved_collection(tmp_path,monkeypatch):
    local,arms=setup(tmp_path,monkeypatch)
    session=local/'v15_recoverable_session';session.mkdir()
    calls=[]
    def guarded(args,directory,env,**kwargs):
        calls.append(args[-2:] if '--arm' in args else args[-1:])
        if '--arm' in args:
            (session/(args[-1].replace('|','_')+'_complete.json')).write_text('{}')
        return {'os_exit_code':0}
    monkeypatch.setattr(s,'run_guarded',guarded)
    s.main()
    assert calls==[['--arm',a] for a in arms]+[['--collect']]


def test_shared_resource_failure_does_not_repeat_eighteen_times(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch)
    calls=[]
    monkeypatch.setattr(s,'run_guarded',lambda *a,**k:(calls.append(a) or {'os_exit_code':75}))
    with pytest.raises(RuntimeError,match='SHARED_RESOURCE_GUARD_REPAIR'):s.main()
    assert len(calls)==1
