"""Strict operational-certificate ancestry; no frozen/input/arm authority drift."""
import json
from pathlib import Path
from v15_checkpoints import sha


def checkpoint_authority(receipt_path, expected, cert, root):
    root=Path(root).resolve()
    actual=json.loads(Path(receipt_path).read_text())['authority']
    if actual==expected:return expected
    field='supplemental_certificate_sha256'
    if {k:v for k,v in actual.items() if k!=field}!={k:v for k,v in expected.items() if k!=field}:
        raise RuntimeError('CHECKPOINT_FROZEN_OR_INPUT_AUTHORITY_DRIFT')
    ancestor=cert.get('checkpoint_operational_ancestors',{}).get(actual.get(field))
    if ancestor is None:raise RuntimeError('CHECKPOINT_CERTIFICATE_ANCESTRY_NOT_BOUND')
    path=(root/ancestor['path']).resolve()
    if not path.is_relative_to(root/'.akah_bot') or sha(path)!=actual[field]:
        raise RuntimeError('CHECKPOINT_ANCESTOR_SHA_OR_PATH_DRIFT')
    old=json.loads(path.read_text())
    for key in ('task_id','head','source_version_sha256','precommit_sha256'):
        if old[key]!=cert[key]:raise RuntimeError('CHECKPOINT_ANCESTOR_FROZEN_IDENTITY_DRIFT')
    migration=ancestor.get('migration')
    if (migration not in {'LOSSLESS_HARMONIC_SEEN_AND_UNBUFFERED_VECTOR_ONLY',
                         'EXACT_NATIVE_LEAF_EPOCH_AND_HOST_PRESSURE_ONLY'}
        or cert.get('storage_migration_synthetic_proven') is not True
        or cert.get('full_301_pair_source_exact_parity') is not True):
        raise RuntimeError('CHECKPOINT_OPERATIONAL_MIGRATION_NOT_PROVEN')
    if migration=='EXACT_NATIVE_LEAF_EPOCH_AND_HOST_PRESSURE_ONLY' and (
            cert.get('source_native_epoch_parity') is not True or
            cert.get('host_pressure_policy_tests_passed') is not True):
        raise RuntimeError('NATIVE_EPOCH_PRESSURE_MIGRATION_NOT_PROVEN')
    changed={p for p in set(old['runtime_bindings'])|set(cert['runtime_bindings'])
             if old['runtime_bindings'].get(p)!=cert['runtime_bindings'].get(p)}
    if changed!=set(ancestor['changed_runtime_paths']):
        raise RuntimeError('CHECKPOINT_UNDECLARED_OPERATIONAL_CODE_CHANGE')
    return actual
