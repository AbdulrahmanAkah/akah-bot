from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spotbot.research.kucoin_rd18 import (
    SPOT_CANDLES_PATH,
    UTA_KLINE_PATH,
    KuCoinRD18Error,
    apply_hysteresis,
    build_public_url,
    extract_explicit_pairs,
    median_liquidity,
    parse_announcements,
    parse_kline_payload,
    rank_snapshot,
    validate_public_url,
    write_immutable_raw,
)


def _classic_payload(*, start: datetime, count: int = 3) -> dict[str, object]:
    rows: list[list[object]] = []
    for index in range(count):
        open_time = int((start + timedelta(days=index)).timestamp())
        rows.append(
            [
                str(open_time),
                "100",
                "101",
                "105",
                "95",
                "10",
                str(1000 + index),
            ]
        )
    rows.reverse()
    return {"code": "200000", "data": rows}


def test_protocol_freezes_kucoin_spot_and_sealed_period() -> None:
    path = Path("data/research/rd18_p0/rd18-p0-protocol-v1.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["execution_venue"] == "KUCOIN_SPOT"
    assert payload["research_period"]["end_exclusive"] == "2025-01-01T00:00:00Z"
    assert payload["quote_currency"] == "USDT"
    assert payload["no_trading"] is True
    assert payload["no_optimization"] is True


def test_public_host_and_endpoint_allowlist_rejects_futures_and_sealed_dates() -> None:
    valid = build_public_url(
        SPOT_CANDLES_PATH,
        {
            "symbol": "BTC-USDT",
            "type": "1day",
            "startAt": 1704067200,
            "endAt": 1704153600,
        },
    )
    validate_public_url(valid, endpoint=SPOT_CANDLES_PATH)
    with pytest.raises(KuCoinRD18Error):
        validate_public_url(
            "https://api-futures.kucoin.com/api/v1/kline/query?symbol=XBTUSDTM",
            endpoint=SPOT_CANDLES_PATH,
        )
    with pytest.raises(KuCoinRD18Error):
        build_public_url(
            SPOT_CANDLES_PATH,
            {"symbol": "BTC-USDT", "type": "1day", "startAt": 1735776000},
        )


def test_classic_kline_parser_normalizes_descending_o_c_h_l_rows() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rows = parse_kline_payload(
        _classic_payload(start=start),
        symbol="BTC-USDT",
        start=start,
        end=start + timedelta(days=3),
    )
    assert [row.open_time for row in rows] == [start + timedelta(days=i) for i in range(3)]
    assert rows[0].high == 105
    assert rows[0].low == 95
    assert rows[0].close == 101
    assert rows[0].quote_volume == 1000


def test_uta_parser_uses_open_high_low_close_order() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    payload = {
        "code": "200000",
        "data": {
            "tradeType": "SPOT",
            "list": [[int(start.timestamp()), "100", "105", "95", "101", "10", "1000"]],
        },
    }
    rows = parse_kline_payload(
        payload,
        symbol="BTC-USDT",
        endpoint=UTA_KLINE_PATH,
        start=start,
        end=start + timedelta(days=1),
    )
    assert rows[0].high == 105
    assert rows[0].low == 95
    assert rows[0].close == 101


def test_sealed_response_row_is_rejected() -> None:
    payload = {
        "code": "200000",
        "data": [[1735689600, "100", "101", "105", "95", "1", "100"]],
    }
    with pytest.raises(KuCoinRD18Error, match="sealed"):
        parse_kline_payload(
            payload,
            symbol="BTC-USDT",
            start=datetime(2024, 12, 1, tzinfo=UTC),
            end=datetime(2025, 2, 1, tzinfo=UTC),
        )


def test_duplicate_conflicting_kline_is_rejected() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    payload = _classic_payload(start=start, count=1)
    payload["data"] = [
        payload["data"][0],
        [payload["data"][0][0], "100", "102", "105", "95", "10", "1000"],
    ]
    with pytest.raises(KuCoinRD18Error, match="duplicate"):
        parse_kline_payload(
            payload,
            symbol="BTC-USDT",
            start=start,
            end=start + timedelta(days=1),
        )


def test_announcement_parser_requires_explicit_pair_and_preserves_id() -> None:
    payload = {
        "code": "200000",
        "data": {
            "totalPage": 1,
            "items": [
                {
                    "annId": 12,
                    "cTime": 1704067200000,
                    "annTitle": "ABC Gets Listed",
                    "annDesc": "Trading pair ABC-USDT opens at 12:00 UTC.",
                    "annUrl": "https://www.kucoin.com/announcement/abc",
                },
                {
                    "annId": 13,
                    "cTime": 1704067200000,
                    "annTitle": "XYZ (XYZ) Gets Listed",
                    "annDesc": "No explicit quote pair.",
                    "annUrl": "https://www.kucoin.com/announcement/xyz",
                },
            ],
        },
    }
    parsed = parse_announcements(payload, category="new-listings", request_id="fixture")
    assert parsed[0].explicit_pairs == ("ABC-USDT",)
    assert parsed[1].explicit_pairs == ()
    assert extract_explicit_pairs("Do not infer XYZ-USDC") == ()


def test_median_liquidity_requires_26_of_28_and_excludes_sunday() -> None:
    start = datetime(2023, 12, 31, tzinfo=UTC)
    payload = _classic_payload(start=start, count=28)
    rows = parse_kline_payload(
        payload, symbol="BTC-USDT", start=start, end=start + timedelta(days=28)
    )
    metrics = median_liquidity(
        rows,
        decision_time=datetime(2024, 1, 29, tzinfo=UTC),
        listing_start=datetime(2023, 1, 1, tzinfo=UTC),
    )
    assert metrics["valid_day_count"] == 28
    assert metrics["eligible"] is True
    assert metrics["trailing_28d_median_daily_quote_volume_usdt"] == 1013.5


def test_ranking_and_hysteresis_are_deterministic() -> None:
    start = datetime(2023, 12, 31, tzinfo=UTC)
    payload = _classic_payload(start=start, count=28)
    rows = parse_kline_payload(
        payload, symbol="BTC-USDT", start=start, end=start + timedelta(days=28)
    )
    ranked = rank_snapshot(
        {"BTC-USDT": rows, "ETH-USDT": rows},
        decision_time=datetime(2024, 1, 29, tzinfo=UTC),
        listing_starts={
            "BTC-USDT": datetime(2023, 1, 1, tzinfo=UTC),
            "ETH-USDT": datetime(2023, 1, 1, tzinfo=UTC),
        },
    )
    assert [row["canonical_asset_id"] for row in ranked] == ["BTC", "ETH"]
    assert apply_hysteresis(ranked, incumbent_ids=("ETH",)) == ("BTC", "ETH")


def test_raw_response_is_immutable(tmp_path: Path) -> None:
    path = tmp_path / "raw.json"
    write_immutable_raw(path, b"first")
    write_immutable_raw(path, b"first")
    with pytest.raises(KuCoinRD18Error, match="Immutable"):
        write_immutable_raw(path, b"second")


def test_runner_help_is_available_without_network() -> None:
    runner = Path("scripts/research/run_rd18_p0_kucoin.py")
    result = subprocess.run(
        [sys.executable, str(runner), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "bounded RD18-P0" in result.stdout
