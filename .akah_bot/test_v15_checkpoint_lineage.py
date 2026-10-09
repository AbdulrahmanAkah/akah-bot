import json
import pytest
from v15_checkpoint_lineage import checkpoint_authority
from v15_checkpoints import sha


def setup(tmp_path):
    local=tmp_path/'.akah_bot';local.mkdir()
    old=dict(task_id='TASK',head='HEAD',source_version_sha256='SOURCE',precommit_sha256='PRE',runtime_bindings={'a':'OLD'})
    path=local/'ancestor.json';path.write_text(json.dumps(old));h=sha(path)
    authority=dict(task_id='TASK',arm='ARM',input_shas={'pair':'HASH'},supplemental_certificate_sha256=h)
    receipt=local/'receipt.json';receipt.write_text(json.dumps({'authority':authority}))
    expected=dict(authority,supplemental_certificate_sha256='NEW')
    cert=dict(old,runtime_bindings={'a':'NEW'},full_301_pair_source_exact_parity=True,
              storage_migration_synthetic_proven=True,checkpoint_operational_ancestors={h:{
                  'path':'.akah_bot/ancestor.json','changed_runtime_paths':['a'],
                  'migration':'LOSSLESS_HARMONIC_SEEN_AND_UNBUFFERED_VECTOR_ONLY'}})
    return receipt,expected,cert,authority,path


def test_exact_ancestry_accepts_old_checkpoint_without_rewriting_authority(tmp_path):
    receipt,expected,cert,old,path=setup(tmp_path)
    assert checkpoint_authority(receipt,expected,cert,tmp_path)==old


@pytest.mark.parametrize('field',['arm','input_shas','task_id'])
def test_frozen_or_input_drift_rejected(tmp_path,field):
    receipt,expected,cert,old,path=setup(tmp_path);expected[field]='DRIFT'
    with pytest.raises(RuntimeError,match='FROZEN_OR_INPUT_AUTHORITY_DRIFT'):
        checkpoint_authority(receipt,expected,cert,tmp_path)


def test_ancestor_tamper_rejected(tmp_path):
    receipt,expected,cert,old,path=setup(tmp_path);path.write_text('DRIFT')
    with pytest.raises(RuntimeError,match='ANCESTOR_SHA_OR_PATH_DRIFT'):
        checkpoint_authority(receipt,expected,cert,tmp_path)


def test_undeclared_change_rejected(tmp_path):
    receipt,expected,cert,old,path=setup(tmp_path);cert['runtime_bindings']['extra']='DRIFT'
    with pytest.raises(RuntimeError,match='UNDECLARED_OPERATIONAL_CODE_CHANGE'):
        checkpoint_authority(receipt,expected,cert,tmp_path)


def test_missing_proof_rejected(tmp_path):
    receipt,expected,cert,old,path=setup(tmp_path);cert['storage_migration_synthetic_proven']=False
    with pytest.raises(RuntimeError,match='MIGRATION_NOT_PROVEN'):
        checkpoint_authority(receipt,expected,cert,tmp_path)
