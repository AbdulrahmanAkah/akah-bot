"""Synthetic dispatch/lineage tests only; never launches a worker or reads market."""
import json
from pathlib import Path
import pytest
import v15_checkpoint_repair_lineage as lineage
import v15_incremental_launcher as launcher


def test_supervisor_retargets_only_the_explicit_authorized_worker(monkeypatch):
    observed = []
    monkeypatch.setattr(launcher, 'RUN', lambda args, *rest, **kw: observed.append((args, rest, kw)))
    args = ['python', '-B', str(launcher.ROOT / '.akah_bot/guarded_entry.py'),
            str(launcher.ROOT / '.akah_bot/v15_recoverable_worker.py'), '--arm', 'SYNTHETIC|1X']
    launcher.repaired_run(args, 'owned-fixture', budget_mib=None)
    assert Path(observed[0][0][2]).name == 'v15_incremental_guarded_entry.py'
    assert Path(observed[0][0][3]).name == 'v15_incremental_recoverable_worker.py'
    assert observed[0][0][4:] == args[4:]
    assert observed[0][2]['budget_mib'] is None
    assert Path(args[3]).name == 'v15_recoverable_worker.py'


def test_unknown_worker_is_not_silently_forwarded(monkeypatch):
    monkeypatch.setattr(launcher, 'RUN', lambda *a, **k: pytest.fail('UNAUTHORIZED_WORKER'))
    with pytest.raises(RuntimeError, match='UNEXPECTED_REPLAY_SUPERVISOR_WORKER'):
        launcher.repaired_run(['python', '-B', 'entry', 'other.py'], 'fixture')


def fixture(tmp_path):
    old = {'task_id': 'synthetic', 'head': 'a', 'source_version_sha256': 'b',
           'precommit_sha256': 'c', 'runtime_bindings': {'old.py': 'OLD'}}
    archive = tmp_path / '.akah_bot/old.json'; archive.parent.mkdir(); archive.write_text(json.dumps(old))
    digest = lineage.sha(archive)
    actual = {'arm': 'SYNTHETIC|1X', 'inputs': {'bounded': 'fixture'}, 'supplemental_certificate_sha256': digest}
    expected = dict(actual, supplemental_certificate_sha256='NEW')
    certificate = dict(old, runtime_bindings={'old.py': 'OLD', 'new.py': 'NEW'},
                       incremental_checkpoint_parity_proven=True,
                       shared_untraded_warmup_all_eighteen_proven=True,
                       full_301_pair_source_exact_parity=True,
                       checkpoint_operational_ancestors={digest: {
                           'path': '.akah_bot/old.json',
                           'migration': 'EXACT_CHUNK_STORAGE_AND_UNTRADED_WARMUP_ONLY',
                           'changed_runtime_paths': ['new.py']}})
    receipt = tmp_path / 'receipt.json'; receipt.write_text(json.dumps({'authority': actual}))
    return receipt, actual, expected, certificate


def test_exact_explicit_operational_lineage_is_accepted(tmp_path):
    receipt, actual, expected, certificate = fixture(tmp_path)
    assert lineage.checkpoint_authority(receipt, expected, certificate, tmp_path) == actual


@pytest.mark.parametrize('mutation', ['arm', 'inputs', 'missing_proof', 'undeclared_path'])
def test_frozen_or_unproven_change_fails_closed(tmp_path, mutation):
    receipt, actual, expected, certificate = fixture(tmp_path)
    if mutation == 'arm': expected['arm'] = 'SYNTHETIC|2X'
    elif mutation == 'inputs': expected['inputs'] = {'bounded': 'different'}
    elif mutation == 'missing_proof': certificate['shared_untraded_warmup_all_eighteen_proven'] = False
    else: certificate['runtime_bindings']['extra.py'] = 'UNDECLARED'
    with pytest.raises(RuntimeError):
        lineage.checkpoint_authority(receipt, expected, certificate, tmp_path)
