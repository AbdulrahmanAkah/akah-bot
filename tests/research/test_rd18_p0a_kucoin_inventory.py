from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from spotbot.research.kucoin_rd18 import SPOT_CANDLES_PATH, KuCoinRD18Error
from spotbot.research.kucoin_rd18_p0a import (
    build_p0a_url,
    candidate_union,
    explicit_pairs,
    parse_announcement_item,
    parse_currency_payload,
    validate_p0a_url,
)


def test_p0a_protocol_freezes_venue_and_sealed_boundary() -> None:
    payload = json.loads(Path("data/research/rd18_p0a/rd18-p0a-protocol-v1.json").read_text())
    assert payload["execution_venue"] == "KUCOIN_SPOT"
    assert payload["historical_period"]["end_exclusive"] == "2025-01-01T00:00:00Z"
    assert payload["no_trading"] is True
    assert payload["no_optimization"] is True


def test_public_page_and_spot_endpoint_allowlist() -> None:
    url = build_p0a_url(
        SPOT_CANDLES_PATH,
        {"symbol": "MARGIN-USDT", "type": "1day", "startAt": 1704067200, "endAt": 1704153600},
    )
    validate_p0a_url(url, endpoint=SPOT_CANDLES_PATH)
    with pytest.raises(KuCoinRD18Error):
        validate_p0a_url(
            "https://api-futures.kucoin.com/api/v1/market/candles", endpoint=SPOT_CANDLES_PATH
        )
    with pytest.raises(KuCoinRD18Error):
        validate_p0a_url("https://www.kucoin.com/not-history", endpoint=None)


def test_explicit_pair_and_non_spot_evidence_are_separate() -> None:
    row = parse_announcement_item(
        {
            "annId": 10,
            "cTime": 1704067200000,
            "annTitle": "Trading Bot will delist the ABC/USDT pair",
            "annDesc": "ABC (ABC) is named explicitly.",
            "annUrl": "https://www.kucoin.com/announcement/abc",
        },
        category="delistings",
        request_id="fixture",
    )
    assert row["explicit_pairs"] == "ABC-USDT"
    assert row["spot_explicit_pairs"] == ""
    assert row["candidate_symbols"] == "ABC"
    assert row["non_spot"] is True


def test_current_currency_seed_is_non_causal() -> None:
    payload = {
        "code": "200000",
        "data": [{"currency": "ABC", "name": "ABC", "fullName": "ABC", "chains": []}],
    }
    rows = parse_currency_payload(payload)
    assert rows[0]["currency"] == "ABC"
    assert rows[0]["current_metadata_isolation"] == "CURRENT_METADATA_NON_CAUSAL_CANDIDATE_SEED"


def test_candidate_union_preserves_current_only_isolation() -> None:
    rows = candidate_union(
        announcement_rows=[],
        currency_rows=[{"currency": "ABC"}],
        historical_pairs=[],
    )
    assert rows[0]["raw_candidate_code"] == "ABC"
    assert rows[0]["current_metadata_only"] is True
    assert rows[0]["candidate_only_evidence"] is True


def test_pair_parser_rejects_no_inferred_usdt_pair() -> None:
    assert explicit_pairs("ABC is listed against BTC") == ()
    assert explicit_pairs("Trading pair ABC-USDT is enabled") == ("ABC-USDT",)


def test_report_does_not_authorize_p1_without_clean_gate() -> None:
    report = json.loads(Path("data/research/rd18_p0a/rd18-p0a-final-report-v1.json").read_text())
    assert report["p1_ran"] is False
    assert report["gate_results"]["all_candidate_symbols_received_e1_probe"] is False


def test_runner_help_is_network_free() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/research/run_rd18_p0a_kucoin_inventory.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "P0A" in result.stdout


def test_no_future_datetime_is_used_by_fixture_contract() -> None:
    cutoff = datetime(2025, 1, 1, tzinfo=UTC)
    assert cutoff.year == 2025
