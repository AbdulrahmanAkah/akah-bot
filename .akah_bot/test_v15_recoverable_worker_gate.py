"""No market reads: unarmed and drifted supplemental certificates fail closed."""
import json
import pytest
import v15_recoverable_worker as w


def certificate(tmp_path,monkeypatch,value):
    monkeypatch.setattr(w,'ROOT',tmp_path)
    local=tmp_path/'.akah_bot';local.mkdir()
    (local/'v15_bounded_runtime_certificate.json').write_text(json.dumps(value))


def test_unarmed_worker_cannot_get_authorized(tmp_path,monkeypatch):
    certificate(tmp_path,monkeypatch,{'ready_for_frozen_recoverable_replay':False})
    with pytest.raises(RuntimeError,match='NOT_CERTIFIED'):w.certified()


def test_ready_boolean_cannot_override_missing_differential_evidence(tmp_path,monkeypatch):
    certificate(tmp_path,monkeypatch,{'ready_for_frozen_recoverable_replay':True,'runtime_bindings':{},'test_bindings':{}})
    with pytest.raises(RuntimeError,match='DIFFERENTIAL_CERTIFICATE_MISSING'):w.certified()


def test_code_drift_rejected_before_market_reader(tmp_path,monkeypatch):
    certificate(tmp_path,monkeypatch,{'ready_for_frozen_recoverable_replay':True,
        'runtime_bindings':{'.akah_bot/code.py':'BAD'},'test_bindings':{}})
    (tmp_path/'.akah_bot/code.py').write_text('changed = True')
    with pytest.raises(RuntimeError,match='BINDING_DRIFT'):w.certified()
