from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.research import run_rd17_p0s
from spotbot.research.providers import (
    ProviderRequestError,
    bounded_retry_delays,
    validate_public_url,
)
from spotbot.research.providers.cmc_public import parse_snapshot_fixture
from spotbot.research.providers.coingecko import validate_url as validate_coingecko_url
from spotbot.research.providers.coinpaprika import validate_url as validate_coinpaprika_url
from spotbot.research.providers.cryptocompare import validate_url as validate_cryptocompare_url

ROOT = Path(__file__).resolve().parents[2]
P0S_ROOT = ROOT / "data" / "research" / "rd17_p0s"


def test_cmc_public_url_policy_rejects_sealed_and_unregistered_paths() -> None:
    with pytest.raises(ProviderRequestError):
        validate_public_url(
            "https://coinmarketcap.com/historical/20250101/",
            allowed_hosts=frozenset({"coinmarketcap.com"}),
            allowed_path_prefixes=("/historical/",),
        )
    with pytest.raises(ProviderRequestError):
        validate_public_url(
            "https://example.com/historical/20240310/",
            allowed_hosts=frozenset({"coinmarketcap.com"}),
            allowed_path_prefixes=("/historical/",),
        )


def test_provider_retry_bound_is_deterministic() -> None:
    assert bounded_retry_delays(4) == (1.0, 2.0, 4.0, 8.0)
    with pytest.raises(ProviderRequestError):
        bounded_retry_delays(7)


def test_candidate_adapters_allow_only_registered_hosts_and_paths() -> None:
    validate_coingecko_url("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart")
    validate_coinpaprika_url("https://api.coinpaprika.com/v1/coins/btc-bitcoin/ohlcv/historical")
    validate_cryptocompare_url("https://min-api.cryptocompare.com/data/v2/histoday")
    with pytest.raises(ProviderRequestError):
        validate_coingecko_url(
            "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?date=2026"
        )


def test_cmc_fixture_parser_is_deterministic_and_excludes_stablecoins() -> None:
    path = ROOT / "data" / "research" / "rd17_p0" / "independent-cmc-snapshots.csv"
    first = parse_snapshot_fixture(path)
    second = parse_snapshot_fixture(path)
    pd.testing.assert_frame_equal(first, second)
    assert int(first["eligible_after_exclusions"].sum()) > 0
    assert "STABLECOIN_OR_CASH" in set(first["exclusion_reason"].dropna())


def test_p0s_probe_outputs_no_source_decision_and_four_reference_matches() -> None:
    report = run_rd17_p0s.run_probe()
    assert report["decision"] == "RD17_P0S_NO_FREE_SOURCE_MEETS_PIT_REQUIREMENTS"
    assert report["next_stage"] == "RD17_BLOCKED_PENDING_FREE_PIT_SOURCE"
    assert report["reference_top6_exact_set_matches"] == 4
    assert report["candidate_generation_stage_authorized"] is False
    assert report["trading_run_authorized"] is False
    assert report["test_2025_accessed"] is False
    assert report["holdout_2026_accessed"] is False


def test_p0s_output_manifest_hashes_are_correct() -> None:
    manifest_path = P0S_ROOT / "output-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
        assert path.stat().st_size == item["bytes"]


def test_runner_help_is_available_without_network() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/research/run_rd17_p0s.py", "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "offline RD17-P0S" in result.stdout
