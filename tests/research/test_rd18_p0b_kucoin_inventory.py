"""Offline tests for RD18-P0B closure helpers and report gates."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from spotbot.research.kucoin_rd18 import SPOT_CANDLES_PATH
from spotbot.research.kucoin_rd18_p0b import (
    KuCoinP0BError,
    boundary_metrics,
    deduplicate_captures,
    gate_decision,
    normalize_kline_rows,
    parse_archived_symbols,
    parse_cdx_rows,
    terminal_resolution,
    validate_archive_original,
)


def test_cdx_rejects_post_2024_capture() -> None:
    payload = json.dumps(
        [
            ["urlkey", "timestamp", "original", "mimetype", "status", "digest", "length"],
            [
                "x",
                "20250101000000",
                "https://api.kucoin.com/api/v1/symbols",
                "application/json",
                "200",
                "abc",
                "2",
            ],
        ]
    )
    with pytest.raises(KuCoinP0BError):
        parse_cdx_rows(payload)


def test_cdx_accepts_official_capture_and_deduplicates_digest() -> None:
    row = [
        "x",
        "20191201000000",
        "https://api.kucoin.com/api/v1/symbols",
        "application/json",
        "200",
        "abc",
        "2",
    ]
    captures = parse_cdx_rows(json.dumps([row, [*row[:1], "20200101000000", *row[2:]]]))
    assert len(deduplicate_captures(captures)) == 1
    assert captures[0].original_host == "api.kucoin.com"


def test_archive_original_host_is_allowlisted() -> None:
    assert validate_archive_original("https://www.kucoin.com/markets") == "www.kucoin.com"
    with pytest.raises(KuCoinP0BError):
        validate_archive_original("https://example.com/markets")


def test_archived_symbol_parser_does_not_accept_leveraged_products() -> None:
    payload = '{"symbol":"BTC-USDT"}<div>ETH/USDT</div><div>BTCDOWN-USDT</div>'
    pairs = parse_archived_symbols(payload)
    assert {row["candidate_pair"] for row in pairs} == {"BTC-USDT", "ETH-USDT"}


def test_boundary_metrics_and_duplicate_normalization() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2020, 1, 4, tzinfo=UTC)
    payload = {
        "code": "200000",
        "data": [
            [1578009600, "1", "1.1", "1.2", "0.9", "2", "3"],
            [1577923200, "1", "1.0", "1.1", "0.9", "2", "3"],
        ],
    }
    rows = normalize_kline_rows(
        [(payload, SPOT_CANDLES_PATH)], symbol="X-USDT", start=start, end=end
    )
    assert len(rows) == 2
    metrics = boundary_metrics(rows, symbol="X-USDT", start=start, end=end)
    assert metrics["first_valid_open"] == "2020-01-02T00:00:00+00:00"
    assert metrics["maximum_internal_gap_days"] == 0


def test_terminal_resolution_and_gate_order() -> None:
    row = {
        "candidate_pair": "X-USDT",
        "discovery_channels": "current_currency_non_causal_seed",
        "identity_status": "HIGH",
    }
    assert terminal_resolution(row, confirmed=True) == "CONFIRMED_CURRENT_SEED_KLINE_VERIFIED_PAIR"
    assert (
        gate_decision({"all_candidates_terminal": False})[0]
        == "RD18_P0B_CANDIDATE_RESOLUTION_INCOMPLETE"
    )
    assert (
        gate_decision(
            {
                "all_candidates_terminal": True,
                "candidate_probe_completion_100pct": True,
                "exact_boundary_completion_100pct": False,
            }
        )[0]
        == "RD18_P0B_HISTORICAL_BOUNDARIES_INCOMPLETE"
    )
    assert (
        gate_decision(
            {
                "all_candidates_terminal": True,
                "candidate_probe_completion_100pct": True,
                "exact_boundary_completion_100pct": True,
                "pre_2020_archive_capture": False,
            }
        )[0]
        == "RD18_P0B_EXTERNAL_ARCHIVE_INSUFFICIENT"
    )
