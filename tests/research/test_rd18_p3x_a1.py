from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from spotbot.research.rd18_p3x_a1 import (
    DECISION_ASSET_GATE_BLOCKED,
    DECISION_CONTROL_PARITY_REQUIRED,
    DECISION_DATA_ACQUISITION_REQUIRED,
    DECISION_ENVIRONMENT_BLOCKED,
    DECISION_INPUT_FAILED,
    DECISION_TOOLING_READY,
    EXPECTED_C2_PAIRS,
    EXPECTED_P3X_HASH,
    NEXT_ASSET_GATE,
    NEXT_EXECUTION,
    NEXT_INPUT_REPAIR,
    PLAN_FIELDS,
    A1Error,
    asset_gate_audit,
    build_acquisition_plan,
    decision_for_plan,
    deterministic_manifest,
    load_c2_requirements,
    load_checkpoint,
    load_source_manifest,
    pair_to_symbol,
    reconcile_inputs,
    summarize_plan,
    symbol_to_pair,
    write_csv,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/research/run_rd18_p3x_a1.py"
VALIDATOR = ROOT / "scripts/research/validate_rd18_p3x_a1.py"


def _coverage_rows(count: int = EXPECTED_C2_PAIRS) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        pair = f"T{index:03d}-USDT"
        rows.append(
            {
                "pair": pair,
                "product_eligible": True,
                "first_valid_open": "2020-01-01T00:00:00+00:00",
                "last_valid_open": "2024-12-31T00:00:00+00:00",
            }
        )
    return rows


def _write_coverage(path: Path, count: int = EXPECTED_C2_PAIRS) -> None:
    write_csv(
        path,
        _coverage_rows(count),
        ("pair", "product_eligible", "first_valid_open", "last_valid_open"),
    )


def _source_manifest(symbols: list[str] | None = None) -> dict[str, object]:
    symbols = symbols or []
    return {
        "assets": {
            symbol: {
                "first_close": "2020-01-01T01:00:00+00:00",
                "last_close": "2025-01-01T00:00:00+00:00",
                "logical_path": f"kucoin/{symbol_to_pair(symbol)}/1h.parquet",
                "sha256": "deadbeef",
            }
            for symbol in symbols
        },
        "exchange": "kucoin",
        "schema_version": "rd16b-hourly-readiness-v1",
        "sealed_cutoff": "2025-01-01T00:00:00+00:00",
        "timeframe": "1h",
    }


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write_coverage(repo / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv")
    write_json(repo / "data/research/rd16b/source-manifest-v1.json", _source_manifest())
    write_json(
        repo / "data/research/rd18_p3x/output-manifest.json",
        {"deterministic_hash": EXPECTED_P3X_HASH},
    )
    write_json(
        repo / "data/research/rd18_p3r/frozen-strategy-candidate.json",
        {
            "architecture_id": "COMPOSITE_ALPHA_V3",
            "source_variant_id": "STRONG_BULL_HOLD_96",
            "registered_ledger": {"candidate_count": 688, "trade_count": 567},
            "fixed_configuration": {"signal_timeframe": "1h"},
        },
    )
    lineage = (
        "rd16c_common.py",
        "rd16c_features.py",
        "rd16c_families.py",
        "rd16c_smoke.py",
        "rd16d_metrics.py",
        "rd16e_components.py",
        "rd16h_expansion.py",
        "rd16i_architecture.py",
        "rd16k_remediation.py",
        "rd16l_architecture.py",
    )
    for name in lineage:
        path = repo / "src/spotbot/research" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name == "rd16e_components.py":
            path.write_text(
                "ALLOWED_ASSETS = {}\n"
                'TOKENS = ("BTC/USDT", "LINK/USDT", "NEAR/USDT", '
                '"FULL_REMEDIATION_STACK")\n'
                "def asset_mask():\n    return None\n",
                encoding="utf-8",
            )
        else:
            path.write_text(f"# {name}\n", encoding="utf-8")
    return repo


def test_pair_symbol_roundtrip() -> None:
    assert pair_to_symbol("BTC-USDT") == "BTC/USDT"
    assert symbol_to_pair("BTC/USDT") == "BTC-USDT"
    with pytest.raises(A1Error):
        pair_to_symbol("BTC-USDC")


def test_load_c2_requirements_requires_exact_corrected_scope(tmp_path: Path) -> None:
    path = tmp_path / "coverage.csv"
    _write_coverage(path)
    requirements = load_c2_requirements(path)
    assert len(requirements) == EXPECTED_C2_PAIRS
    assert requirements[0].required_since_open == datetime(2020, 1, 1, tzinfo=UTC)
    assert requirements[0].required_until_exclusive == datetime(2025, 1, 1, tzinfo=UTC)

    _write_coverage(path, EXPECTED_C2_PAIRS - 1)
    with pytest.raises(A1Error, match="expected 364"):
        load_c2_requirements(path)


def test_source_manifest_requires_kucoin_hourly_cutoff(tmp_path: Path) -> None:
    path = tmp_path / "source.json"
    write_json(path, _source_manifest(["T000/USDT"]))
    sources = load_source_manifest(path)
    assert set(sources) == {"T000/USDT"}
    bad = _source_manifest()
    bad["timeframe"] = "1d"
    write_json(path, bad)
    with pytest.raises(A1Error, match="KuCoin Spot 1h"):
        load_source_manifest(path)


def test_checkpoint_rejects_unknown_state(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    write_json(path, {"pairs": {"T000-USDT": {"state": "UNKNOWN"}}})
    with pytest.raises(A1Error, match="unknown checkpoint state"):
        load_checkpoint(path)


def test_acquisition_plan_separates_current_and_historical_sources(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    requirements = load_c2_requirements(
        repo / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv"
    )
    sources = load_source_manifest(repo / "data/research/rd16b/source-manifest-v1.json")
    rows = build_acquisition_plan(
        repo,
        requirements,
        sources,
        {},
        current_market_symbols={"T000/USDT", "T001/USDT"},
    )
    summary = summarize_plan(rows)
    assert summary["action_counts"]["DOWNLOAD_OR_BACKFILL_CURRENT_API"] == 2
    assert summary["action_counts"]["HISTORICAL_MARKET_SOURCE_REQUIRED"] == 362
    assert summary["ready_pairs"] == 0


def test_unprobed_plan_never_assumes_current_market_availability(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    requirements = load_c2_requirements(
        repo / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv"
    )
    rows = build_acquisition_plan(
        repo,
        requirements,
        {},
        {},
        current_market_symbols=None,
    )
    assert {row["action"] for row in rows} == {"NETWORK_MARKET_PROBE_REQUIRED"}


def test_complete_checkpoint_is_revalidated_as_ready_local(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    requirements = load_c2_requirements(
        repo / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv"
    )
    requirement = requirements[0]
    store = repo / "data/raw/rd16b"
    one_hour = store / requirement.logical_path
    one_hour.parent.mkdir(parents=True, exist_ok=True)
    one_hour.write_bytes(b"hourly")
    derived: dict[str, str] = {}
    for timeframe in ("4h", "1d", "1w"):
        path = store / f"kucoin/{requirement.pair}/{timeframe}.parquet"
        path.write_bytes(timeframe.encode())
        derived[timeframe] = hashlib.sha256(path.read_bytes()).hexdigest()
    stale_manifest = _source_manifest([requirement.symbol])
    stale_manifest["assets"][requirement.symbol]["first_close"] = "2021-01-01T01:00:00+00:00"
    write_json(repo / "data/research/rd16b/source-manifest-v1.json", stale_manifest)
    sources = load_source_manifest(repo / "data/research/rd16b/source-manifest-v1.json")
    checkpoint = {
        requirement.pair: {
            "state": "COMPLETE",
            "logical_path": requirement.logical_path,
            "sha256": hashlib.sha256(one_hour.read_bytes()).hexdigest(),
            "first_close": "2020-01-01T01:00:00+00:00",
            "last_close": "2025-01-01T00:00:00+00:00",
            "derived_sha256": derived,
        }
    }
    rows = build_acquisition_plan(
        repo,
        requirements,
        sources,
        checkpoint,
        current_market_symbols=None,
    )
    row = next(item for item in rows if item["pair"] == requirement.pair)
    assert row["action"] == "READY_LOCAL"
    assert row["evidence_source"] == "A1_VERIFIED_CHECKPOINT"
    assert row["derived_context_complete"] is True


def test_complete_checkpoint_with_missing_context_requires_revalidation(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)
    requirements = load_c2_requirements(
        repo / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv"
    )
    requirement = requirements[0]
    one_hour = repo / "data/raw/rd16b" / requirement.logical_path
    one_hour.parent.mkdir(parents=True, exist_ok=True)
    one_hour.write_bytes(b"hourly")
    checkpoint = {
        requirement.pair: {
            "state": "COMPLETE",
            "logical_path": requirement.logical_path,
            "sha256": hashlib.sha256(one_hour.read_bytes()).hexdigest(),
            "first_close": "2020-01-01T01:00:00+00:00",
            "last_close": "2025-01-01T00:00:00+00:00",
            "derived_sha256": {},
        }
    }
    rows = build_acquisition_plan(
        repo,
        requirements,
        {},
        checkpoint,
        current_market_symbols=None,
    )
    row = next(item for item in rows if item["pair"] == requirement.pair)
    assert row["action"] == "CHECKPOINT_REVALIDATION_REQUIRED"
    assert row["derived_context_complete"] is False


def test_input_reconciliation_and_asset_gate_audit(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    assert reconcile_inputs(repo)["passed"] is True
    audit = asset_gate_audit(repo)
    assert audit["pilot_static_asset_gate_present"] is True
    assert audit["broad_c2_policy"] == "BLOCK_UNTIL_CAUSAL_GENERALIZATION_IS_PREREGISTERED"


def test_decision_order_is_fail_closed() -> None:
    assert decision_for_plan(
        input_ready=False,
        environment_ready=True,
        control_parity_passed=True,
        all_data_ready=True,
        broad_asset_gate_ready=True,
    ) == (DECISION_INPUT_FAILED, NEXT_INPUT_REPAIR)
    assert decision_for_plan(
        input_ready=True,
        environment_ready=False,
        control_parity_passed=True,
        all_data_ready=True,
        broad_asset_gate_ready=True,
    ) == (DECISION_ENVIRONMENT_BLOCKED, NEXT_EXECUTION)
    assert decision_for_plan(
        input_ready=True,
        environment_ready=True,
        control_parity_passed=False,
        all_data_ready=True,
        broad_asset_gate_ready=True,
    ) == (DECISION_CONTROL_PARITY_REQUIRED, NEXT_EXECUTION)
    assert decision_for_plan(
        input_ready=True,
        environment_ready=True,
        control_parity_passed=True,
        all_data_ready=False,
        broad_asset_gate_ready=True,
    ) == (DECISION_DATA_ACQUISITION_REQUIRED, NEXT_EXECUTION)
    assert decision_for_plan(
        input_ready=True,
        environment_ready=True,
        control_parity_passed=True,
        all_data_ready=True,
        broad_asset_gate_ready=False,
    ) == (DECISION_ASSET_GATE_BLOCKED, NEXT_ASSET_GATE)
    assert (
        decision_for_plan(
            input_ready=True,
            environment_ready=True,
            control_parity_passed=True,
            all_data_ready=True,
            broad_asset_gate_ready=True,
        )[0]
        == DECISION_TOOLING_READY
    )


def test_deterministic_manifest_tracks_hashes_and_sizes(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("x\n1\n", encoding="utf-8")
    first = deterministic_manifest(tmp_path, ["b.csv", "a.json"])
    second = deterministic_manifest(tmp_path, ["a.json", "b.csv"])
    assert first == second
    assert len(first["files"]) == 2


def test_plan_csv_field_contract(tmp_path: Path) -> None:
    path = tmp_path / "plan.csv"
    row = {field: "" for field in PLAN_FIELDS}
    write_csv(path, [row], PLAN_FIELDS)
    with path.open("r", encoding="utf-8", newline="") as handle:
        assert tuple(next(csv.reader(handle))) == PLAN_FIELDS


def test_offline_runner_and_validator_on_synthetic_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    output = repo / "runtime"
    run = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--repo-root",
            str(repo),
            "--output-dir",
            str(output),
            "--offline",
            "plan",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["acquisition"]["c2_pairs"] == 364
    assert report["authorizations"]["strategy_replay"] is False
    validate = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--output-dir",
            str(output),
            "--offline",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert validate.returncode == 0, validate.stdout + validate.stderr
    assert json.loads(validate.stdout)["passed"] is True


def test_control_source_is_fail_closed_for_breadth() -> None:
    text = (ROOT / "src/spotbot/research/rd18_p3x_a1_control.py").read_text(encoding="utf-8")
    assert "reject_broad_generation" in text
    assert "PILOT_STATIC_ASSET_GATE" in text
    assert "prepare_v3_ledgers" in text
    assert "route_remediation_candidates" in text
    assert "registered_content_hash_match" in text
    assert "rd16l_manifest_content_hash_match" in text
    assert "p3r_hash_erratum" in text
    assert "legacy control file hash mismatch" in text


def test_committed_a1_manifest_matches_files() -> None:
    manifest_path = ROOT / "data/research/rd18_p3x_a1/output-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["network_requests"] == 0
    assert manifest["strategy_replay_executed"] is False
    assert manifest["return_calculation_executed"] is False
    for item in manifest["files"]:
        path = ROOT / item["path"]
        payload = path.read_bytes()
        assert len(payload) == item["bytes"]
        assert hashlib.sha256(payload).hexdigest() == item["sha256"]


def test_committed_p3r_hash_erratum_is_fail_closed() -> None:
    path = ROOT / "data/research/rd18_p3x_a1/p3r-ledger-hash-erratum.json"
    erratum = json.loads(path.read_text(encoding="utf-8"))
    assert (
        erratum["classification"]
        == "P3R_LEDGER_HASH_METADATA_UNREPRODUCIBLE_FROM_DOCUMENTED_CONTRACT"
    )
    assert erratum["resolution"]["modify_upstream_p3r_bundle"] is False
    assert erratum["resolution"]["change_strategy_or_market_data"] is False
    assert erratum["resolution"]["fail_if_rd16l_manifest_or_complete_value_parity_mismatch"] is True
    assert set(erratum["ledgers"]) == {
        "candidates",
        "evaluated",
        "trades",
    }


def test_download_provider_uses_supported_constructor() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "CCXTSpotDataProvider(adapter, page_limit=" not in text
    assert "provider = CCXTSpotDataProvider(adapter)" in text


def test_historical_checkpoint_prevents_current_api_retry(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)
    requirements = load_c2_requirements(
        repo / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv"
    )
    requirement = requirements[0]
    checkpoint = {
        requirement.pair: {
            "state": "HISTORICAL_SOURCE_REQUIRED",
            "error": ("current API history begins after the required boundary"),
        }
    }

    rows = build_acquisition_plan(
        repo,
        requirements,
        {},
        checkpoint,
        current_market_symbols={requirement.symbol},
    )
    row = next(item for item in rows if item["pair"] == requirement.pair)

    assert row["checkpoint_state"] == "HISTORICAL_SOURCE_REQUIRED"
    assert row["current_market_state"] == "CURRENT_SPOT_MARKET_PRESENT"
    assert row["action"] == "HISTORICAL_MARKET_SOURCE_REQUIRED"
    assert "required boundary" in str(row["blocking_reason"])


def test_historical_download_checkpoint_preserves_partial_metadata() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert '"partial_current_api": True' in text
    assert '"discovered_first_open": acquisition[' in text
    assert '"sha256": acquisition["sha256"]' in text


def test_a1_history_discovery_uses_contiguous_page_windows() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "DISCOVERY_PAGE_LIMIT = 1_000" in text
    assert "step = timedelta(hours=DISCOVERY_PAGE_LIMIT)" in text
    assert "limit=DISCOVERY_PAGE_LIMIT" in text
    assert "timedelta(days=90)" not in text


def test_a1_acquisition_starts_at_exact_discovered_boundary() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    discovery_call = "_discover_current_api_first_open("
    acquire_call = "frame, acquisition = _acquire_hourly("
    assert discovery_call in text
    assert acquire_call in text
    assert text.index(discovery_call) < text.index(acquire_call)
    assert "since=discovered_first_open" in text
    assert "required_since_open + timedelta(hours=1)" in text


def _write_checkpoint_ready_files(
    repo: Path,
    *,
    pair: str,
) -> tuple[str, dict[str, str]]:
    logical_path = f"kucoin/{pair}/1h.parquet"
    data_path = repo / "data/raw/rd16b" / logical_path
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(b"hourly")
    derived: dict[str, str] = {}
    for timeframe in ("4h", "1d", "1w"):
        derived_path = repo / "data/raw/rd16b/kucoin" / pair / f"{timeframe}.parquet"
        derived_path.write_bytes(timeframe.encode("ascii"))
        derived[timeframe] = hashlib.sha256(derived_path.read_bytes()).hexdigest()
    return (
        hashlib.sha256(data_path.read_bytes()).hexdigest(),
        derived,
    )


def test_same_day_intraday_start_is_window_compatible(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)
    requirements = load_c2_requirements(
        repo / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv"
    )
    requirement = requirements[0]
    source_hash, derived = _write_checkpoint_ready_files(
        repo,
        pair=requirement.pair,
    )
    checkpoint = {
        requirement.pair: {
            "state": "COMPLETE",
            "logical_path": requirement.logical_path,
            "sha256": source_hash,
            "first_close": "2020-01-01T11:00:00+00:00",
            "last_close": "2025-01-01T00:00:00+00:00",
            "derived_sha256": derived,
        }
    }

    rows = build_acquisition_plan(
        repo,
        requirements,
        {},
        checkpoint,
        current_market_symbols={requirement.symbol},
    )
    row = next(item for item in rows if item["pair"] == requirement.pair)

    assert row["source_window_complete"] is True
    assert row["action"] == "READY_LOCAL"


def test_next_day_start_is_not_window_compatible(
    tmp_path: Path,
) -> None:
    repo = _make_repo(tmp_path)
    requirements = load_c2_requirements(
        repo / "data/research/rd18_p1r2/corrected-daily-coverage-audit.csv"
    )
    requirement = requirements[0]
    source_hash, derived = _write_checkpoint_ready_files(
        repo,
        pair=requirement.pair,
    )
    checkpoint = {
        requirement.pair: {
            "state": "COMPLETE",
            "logical_path": requirement.logical_path,
            "sha256": source_hash,
            "first_close": "2020-01-02T01:00:00+00:00",
            "last_close": "2025-01-01T00:00:00+00:00",
            "derived_sha256": derived,
        }
    }

    rows = build_acquisition_plan(
        repo,
        requirements,
        {},
        checkpoint,
        current_market_symbols={requirement.symbol},
    )
    row = next(item for item in rows if item["pair"] == requirement.pair)

    assert row["source_window_complete"] is False
    assert row["action"] == "CHECKPOINT_REVALIDATION_REQUIRED"


def test_intraday_listing_boundary_is_explicitly_recorded() -> None:
    runner_text = RUNNER.read_text(encoding="utf-8")
    protocol = json.loads(
        (ROOT / "data/research/rd18_p3x_a1/rd18-p3x-a1-protocol-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert "INTRADAY_LISTING_WITHIN_DAILY_APPLICABLE_START" in runner_text
    assert '"leading_inactive_hours"' in runner_text
    assert protocol["acquisition_contract"]["daily_applicable_start_granularity"] == "UTC_DAY"
    assert protocol["boundary_semantics_amendment"]["optimization_or_strategy_change"] is False
