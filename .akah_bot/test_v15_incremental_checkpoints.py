"""Synthetic exact-state differential; never opens raw market files."""
import json
from pathlib import Path
import pytest
import v15_incremental_checkpoints as incremental
import v15_checkpoints as baseline
import test_v15_checkpoints as source_fixture
import test_v15_resume as resume_fixture


def test_source_roundtrip_independent_reloads_and_future_registration(tmp_path):
    p = source_fixture.provider()
    source_fixture.advance(p, 0, 24)
    expected = source_fixture.signature(p)
    authority = {'purpose': 'SYNTHETIC_CHUNK_SOURCE'}
    path = incremental.write_checkpoint(tmp_path, {'source': p, 'cursor': p.last_close}, authority)
    source_fixture.advance(p, 24, 36)
    restored = incremental.read_checkpoint(path, authority)['source']
    assert source_fixture.signature(restored) == expected
    assert restored.feeds['BTC-USDT'].prefix.graph is restored.feeds['ETH-USDT'].prefix.graph
    assert restored.feeds['BTC-USDT'].prefix.graph.nodes.owner is restored.feeds['BTC-USDT'].prefix.graph
    source_fixture.advance(restored, 24, 36)
    assert source_fixture.signature(restored) == source_fixture.signature(p)
    twice = incremental.read_checkpoint(path, authority)['source']
    assert source_fixture.signature(twice) == expected


def test_old_checkpoint_format_remains_usable_without_migration(tmp_path):
    authority = {'purpose': 'SYNTHETIC_OLD_FORMAT'}
    path = baseline.write_checkpoint(tmp_path, {'clock': 'synthetic', 'sequence': (1, 2)}, authority)
    assert incremental.read_checkpoint(path, authority) == {'clock': 'synthetic', 'sequence': (1, 2)}


def test_authority_and_chunk_tamper_fail_before_unpickle(tmp_path, monkeypatch):
    p = source_fixture.provider(); source_fixture.advance(p, 0, 5)
    path = incremental.write_checkpoint(tmp_path, {'source': p}, {'purpose': 'fixture'})
    with pytest.raises(RuntimeError, match='AUTHORITY_DRIFT'):
        incremental.read_checkpoint(path, {'purpose': 'different'})
    receipt = json.loads(path.read_text())
    manifest = json.loads(Path(receipt['archives'][0]['path']).read_text())
    chunk = Path(receipt['chunk_store']) / 'chunks' / (manifest['chunks'][0]['sha256'] + '.bin')
    chunk.write_bytes(b'corrupt')
    monkeypatch.setattr(incremental.pickle, 'load', lambda *a, **k: pytest.fail('UNVERIFIED_UNPICKLE'))
    with pytest.raises(RuntimeError, match='CHUNK_CONTENT_DRIFT'):
        incremental.read_checkpoint(path, {'purpose': 'fixture'})


@pytest.mark.parametrize('index', range(9))
@pytest.mark.parametrize('scenario', ['1X', '2X'])
def test_open_campaign_exact_resume_all_eighteen(tmp_path, monkeypatch, index, scenario):
    monkeypatch.setattr(resume_fixture, 'checkpoints', incremental)
    resume_fixture.test_open_campaign_state_resume_exact_all_eighteen(tmp_path, index, scenario)


@pytest.mark.parametrize('hour', [24, 48, 60])
def test_scheduler_exact_resume(tmp_path, monkeypatch, hour):
    monkeypatch.setattr(resume_fixture, 'checkpoints', incremental)
    resume_fixture.test_scheduler_continuous_vs_checkpoint_resume_exact(tmp_path, monkeypatch, hour)
