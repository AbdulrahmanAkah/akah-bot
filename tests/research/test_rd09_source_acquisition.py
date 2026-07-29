import json
from pathlib import Path

from spotbot.research.rd09_source_acquisition import append_manifest, fetch_json


def test_resume_does_not_duplicate_download(tmp_path: Path) -> None:
    target = tmp_path / "cached.json"
    target.write_text('{"data": []}\n', encoding="utf-8")
    result = fetch_json(url="https://invalid.example", destination=target)
    assert result.resumed
    assert result.size_bytes > 0


def test_manifest_replaces_same_request(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "manifest.json"
    record = {
        "source_id": "SOURCE",
        "request_url": "https://example.test",
        "destination": "pilot.json",
        "sha256": "abc",
    }
    append_manifest(path, record)
    append_manifest(path, record)
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 1
