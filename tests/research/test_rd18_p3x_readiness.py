from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from spotbot.research.rd18_p3x_readiness import (
    DECISION_BOTH_REQUIRED,
    DECISION_DATA_REQUIRED,
    DECISION_GENERATOR_REQUIRED,
    DECISION_INPUT_FAILED,
    DECISION_READY,
    NEXT_BOTH,
    P3XReadinessError,
    acquisition_plan,
    audit_sources,
    candidate_coverage_audit,
    classify_decision,
    feature_lookback_audit,
    generator_readiness_audit,
    load_c2_requirements,
    load_committed_readiness,
    load_hourly_sources,
    pair_to_symbol,
    reconcile_input_manifests,
    report_jsonable,
    summarize,
    symbol_to_pair,
)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def c2_row(pair: str, eligible: bool = True) -> dict[str, object]:
    return {
        "applicable_end": "2024-12-31T00:00:00+00:00",
        "applicable_start": "2020-01-01T00:00:00+00:00",
        "boundary_status": "EXACT_FULL_HISTORY",
        "coverage_ratio": 1.0,
        "covered_pair_days": 1827,
        "documented_inactivity_boundary": True,
        "expected_applicable_pair_days": 1827,
        "first_valid_open": "2020-01-01T00:00:00+00:00",
        "last_valid_open": "2024-12-31T00:00:00+00:00",
        "missing_pair_days": 0,
        "pair": pair,
        "product_eligible": eligible,
    }


def source_manifest(symbol: str = "AAA/USDT", sha256: str = "deadbeef") -> dict[str, Any]:
    return {
        "assets": {
            symbol: {
                "acquisition_status": "CREATED",
                "fetched_rows": 43848,
                "first_close": "2020-01-01T01:00:00+00:00",
                "last_close": "2025-01-01T00:00:00+00:00",
                "logical_path": "kucoin/AAA-USDT/1h.parquet",
                "rows": 43848,
                "sha256": sha256,
            }
        },
        "exchange": "kucoin",
        "schema_version": "rd16b-hourly-readiness-v1",
        "sealed_cutoff": "2025-01-01T00:00:00+00:00",
        "timeframe": "1h",
    }


def readiness_row(symbol: str = "AAA/USDT") -> dict[str, object]:
    return {
        "symbol": symbol,
        "status": "PASS",
        "error_type": "",
        "error_message": "",
        "acquisition_status": "CREATED",
        "rows_1h": 43848,
        "first_close": "2020-01-01T01:00:00+00:00",
        "last_close": "2025-01-01T00:00:00+00:00",
        "coverage_days": 1827,
        "minimum_coverage_met": True,
        "duplicate_timestamps": 0,
        "missing_intervals": 0,
        "invalid_rows": 0,
        "cutoff_reached": True,
        "sealed_data_clean": True,
        "aligned_rows": 43537,
        "future_context_violations": 0,
        "stale_context_violations": 0,
        "source_sha256": "deadbeef",
    }


def test_pair_normalization() -> None:
    assert pair_to_symbol("btc-usdt") == "BTC/USDT"
    assert symbol_to_pair("btc/usdt") == "BTC-USDT"
    with pytest.raises(P3XReadinessError):
        pair_to_symbol("BTC-EUR")


def test_load_c2_requirements_filters_products(tmp_path: Path) -> None:
    path = tmp_path / "coverage.csv"
    rows = [c2_row("AAA-USDT"), c2_row("LEV2L-USDT", False)]
    write_csv(path, rows, list(rows[0]))
    requirements = load_c2_requirements(path)
    assert [row.pair for row in requirements] == ["AAA-USDT"]
    assert requirements[0].required_first_close == "2020-01-01T01:00:00+00:00"
    assert requirements[0].required_last_close == "2025-01-01T00:00:00+00:00"


def test_load_c2_rejects_post_2024(tmp_path: Path) -> None:
    path = tmp_path / "coverage.csv"
    row = c2_row("AAA-USDT")
    row["last_valid_open"] = "2025-01-01T00:00:00+00:00"
    write_csv(path, [row], list(row))
    with pytest.raises(P3XReadinessError, match="post-2024"):
        load_c2_requirements(path)


def test_load_hourly_source_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(source_manifest()), encoding="utf-8")
    sources = load_hourly_sources(path)
    assert set(sources) == {"AAA/USDT"}
    assert sources["AAA/USDT"].rows == 43848


def test_feature_lookback_audit(tmp_path: Path) -> None:
    path = tmp_path / "features.py"
    path.write_text(
        'span=50\nmin_periods=120\nmin_periods=30\ndirection="backward"\nfuture context detected\n',
        encoding="utf-8",
    )
    result = feature_lookback_audit(path)
    assert result["all_frozen_tokens_present"] is True
    assert result["minimum_feature_warmup_hours"] == 5040


def test_generator_audit_detects_ledger_only(tmp_path: Path) -> None:
    architecture = tmp_path / "architecture.py"
    features = tmp_path / "features.py"
    architecture.write_text(
        "def prepare_v3_ledgers(candidates):\n    return candidates\n",
        encoding="utf-8",
    )
    features.write_text("def build_feature_frame(frames):\n    return frames\n", encoding="utf-8")
    result = generator_readiness_audit(architecture, features)
    assert result["raw_candidate_regeneration_capable"] is False
    assert result["classification"] == "LEDGER_REGISTRATION_ONLY_GENERATOR_EXTRACTION_REQUIRED"


def test_generator_audit_accepts_raw_entrypoint(tmp_path: Path) -> None:
    architecture = tmp_path / "architecture.py"
    features = tmp_path / "features.py"
    architecture.write_text(
        "from x import build_feature_frame\n"
        "def prepare_v3_ledgers(candidates): return candidates\n"
        "def regenerate_candidates(frames): return build_feature_frame(frames)\n",
        encoding="utf-8",
    )
    features.write_text("def build_feature_frame(frames): return frames\n", encoding="utf-8")
    result = generator_readiness_audit(architecture, features)
    assert result["raw_candidate_regeneration_capable"] is True


def test_acquisition_plan_distinguishes_absent_and_ready(tmp_path: Path) -> None:
    coverage = tmp_path / "coverage.csv"
    rows = [c2_row("AAA-USDT"), c2_row("BBB-USDT")]
    write_csv(coverage, rows, list(rows[0]))
    requirements = load_c2_requirements(coverage)
    raw = tmp_path / "data" / "raw" / "rd16b" / "kucoin" / "AAA-USDT" / "1h.parquet"
    raw.parent.mkdir(parents=True)
    payload = b"not-a-real-parquet"
    raw.write_bytes(payload)
    payload_hash = hashlib.sha256(payload).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(source_manifest(sha256=payload_hash)), encoding="utf-8")
    sources = load_hourly_sources(manifest_path)
    readiness_path = tmp_path / "readiness.csv"
    ready = readiness_row()
    write_csv(readiness_path, [ready], list(ready))
    committed = load_committed_readiness(readiness_path)
    audits = audit_sources(tmp_path, sources, committed, verify_hashes=True)
    plan = acquisition_plan(requirements, sources, audits)
    by_pair = {row["pair"]: row for row in plan}
    assert by_pair["AAA-USDT"]["coverage_status"] == "READY"
    assert by_pair["BBB-USDT"]["coverage_status"] == "SOURCE_MANIFEST_ABSENT"


def test_candidate_coverage_requires_one_explicit_decision_per_member() -> None:
    expected = [("2024-01-01", "AAA/USDT"), ("2024-01-01", "BBB/USDT")]
    decisions = [
        {
            "decision_timestamp": "2024-01-01",
            "symbol": "AAA/USDT",
            "candidate_decision": "NO_SIGNAL",
        }
    ]
    result = candidate_coverage_audit(expected, decisions)
    assert result.complete is False
    assert result.coverage_rate == 0.5
    assert result.missing_rows == 1


def test_candidate_coverage_rejects_duplicates_and_invalid_decisions() -> None:
    expected = [("2024-01-01", "AAA/USDT")]
    decisions = [
        {
            "decision_timestamp": "2024-01-01",
            "symbol": "AAA/USDT",
            "candidate_decision": "UNKNOWN",
        },
        {
            "decision_timestamp": "2024-01-01",
            "symbol": "AAA/USDT",
            "candidate_decision": "NO_SIGNAL",
        },
    ]
    result = candidate_coverage_audit(expected, decisions)
    assert result.duplicate_rows == 1
    assert result.invalid_decisions == 1
    assert result.complete is False


def test_decision_classification_branches() -> None:
    assert (
        classify_decision(
            c2_count=364, ready_source_pairs=364, generator_ready=True, feature_tokens_ready=True
        )[0]
        == DECISION_READY
    )
    assert (
        classify_decision(
            c2_count=364, ready_source_pairs=6, generator_ready=True, feature_tokens_ready=True
        )[0]
        == DECISION_DATA_REQUIRED
    )
    assert (
        classify_decision(
            c2_count=364, ready_source_pairs=364, generator_ready=False, feature_tokens_ready=True
        )[0]
        == DECISION_GENERATOR_REQUIRED
    )
    decision, next_stage = classify_decision(
        c2_count=364, ready_source_pairs=6, generator_ready=False, feature_tokens_ready=True
    )
    assert decision == DECISION_BOTH_REQUIRED
    assert next_stage == NEXT_BOTH
    assert (
        classify_decision(
            c2_count=363, ready_source_pairs=363, generator_ready=True, feature_tokens_ready=True
        )[0]
        == DECISION_INPUT_FAILED
    )


def test_summary_is_json_safe_and_never_authorizes_replay() -> None:
    requirements = []
    sources = {}
    generator = {"raw_candidate_regeneration_capable": False}
    lookback = {"all_frozen_tokens_present": True}
    report = summarize(requirements, sources, [], generator, lookback)
    safe = report_jsonable(report)
    assert safe["authorizations"]["strategy_replay_authorized"] is False
    assert safe["constraints"]["returns_calculated"] is False


def test_committed_p3x_manifest_matches_files() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "data" / "research" / "rd18_p3x" / "output-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["network_requests"] == 0
    assert manifest["schema_version"] == "rd18-p3x-output-manifest-v1"
    for item in manifest["files"]:
        path = root / item["path"]
        assert path.is_file(), item["path"]
        assert path.stat().st_size == item["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_input_manifest_reconciliation(tmp_path: Path) -> None:
    expected = {
        "rd18_p1r2": "0cc3d273e55aa1d1425de97b47fb5cad7610c6c2c7da6aec348850a635947048",
        "rd18_p2u2": "f61ed396977e8b85faaad5e670e193d216a5d6e1c87bee8406301cbe0666b227",
        "rd18_p3r": "df4644d52cbcf60b878d5b6f979846cc756139b329a23c58ed0f068dfd50e4cb",
    }
    for directory, digest in expected.items():
        path = tmp_path / "data" / "research" / directory / "output-manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema_version": directory, "deterministic_hash": digest}),
            encoding="utf-8",
        )
    result = reconcile_input_manifests(tmp_path)
    assert result["all_inputs_match"] is True
    p3r = tmp_path / "data" / "research" / "rd18_p3r" / "output-manifest.json"
    p3r.write_text(json.dumps({"deterministic_hash": "wrong"}), encoding="utf-8")
    assert reconcile_input_manifests(tmp_path)["all_inputs_match"] is False


def test_atomic_json_writer_does_not_import_pandas(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    destination = tmp_path / "lazy-atomic-output.json"
    script = """
import builtins
import json
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[1])

real_import = builtins.__import__


def guarded_import(name, *args, **kwargs):
    if name == "pandas" or name.startswith("pandas."):
        raise RuntimeError("pandas import was attempted")
    return real_import(name, *args, **kwargs)


builtins.__import__ = guarded_import

from spotbot.research.atomic_output import atomic_write_json

destination = Path(sys.argv[2])
atomic_write_json(destination, {"ok": True})
assert json.loads(destination.read_text(encoding="utf-8")) == {"ok": True}
"""

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(root / "src"),
            str(destination),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert destination.is_file()
