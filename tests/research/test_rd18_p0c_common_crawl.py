"""Offline contract tests for RD18-P0C Common Crawl helpers."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime

import pytest

from spotbot.research.kucoin_rd18_p0c import (
    CC_DATA_HOST,
    CC_INDEX_HOST,
    KuCoinP0CError,
    archive_capture_is_usable,
    build_cdx_url,
    build_range_header,
    build_warc_range_url,
    classify_archived_content,
    current_registry_retention,
    decide_p0c,
    deduplicate_cdx_rows,
    parse_cdxj,
    parse_collection_listing,
    parse_warc_http_payload,
    select_launch_collections,
)


def test_collection_cutoff_and_selection() -> None:
    payload = json.dumps(
        [
            {
                "id": "CC-MAIN-2019-51",
                "name": "December 2019",
                "from": "2019-12-01",
                "to": "2019-12-31",
            },
            {"id": "CC-MAIN-2024-51", "name": "2024", "from": "2024-12-01", "to": "2024-12-31"},
        ]
    )
    rows = parse_collection_listing(payload)
    assert [row["collection_id"] for row in select_launch_collections(rows)] == ["CC-MAIN-2019-51"]


def test_post_2025_collection_is_ignored() -> None:
    assert parse_collection_listing('[{"id":"CC-MAIN-2025-30"}]') == ()


def test_bounded_cdx_url_and_allowlist() -> None:
    url = build_cdx_url("CC-MAIN-2019-51", "https://www.kucoin.com/announcement/*")
    assert url.startswith(f"https://{CC_INDEX_HOST}/CC-MAIN-2019-51-index?")
    with pytest.raises(KuCoinP0CError):
        build_cdx_url("CC-MAIN-2019-51", "https://www.kucoin.com/*")


def test_cdxj_filters_official_and_sealed_captures() -> None:
    payload = "\n".join(
        [
            json.dumps(
                {
                    "url": "https://www.kucoin.com/announcement/listing",
                    "timestamp": "20191010120000",
                    "filename": "crawl-data/CC-MAIN-2019-51/part.warc.gz",
                    "offset": "10",
                    "length": "100",
                    "digest": "sha1:A",
                    "mime": "text/html",
                    "status": "200",
                }
            ),
        ]
    )
    rows = parse_cdxj(payload)
    assert len(rows) == 1
    assert archive_capture_is_usable(rows[0])
    with pytest.raises(KuCoinP0CError):
        parse_cdxj(
            json.dumps(
                {
                    "url": "https://www.kucoin.com/announcement/future",
                    "timestamp": "20250101120000",
                    "filename": "crawl-data/x.warc.gz",
                    "offset": "0",
                    "length": "10",
                }
            )
        )


def test_cdxj_rejects_third_party_original() -> None:
    with pytest.raises(KuCoinP0CError):
        parse_cdxj(
            json.dumps(
                {
                    "url": "https://example.com/kucoin",
                    "timestamp": "20191010120000",
                    "filename": "crawl-data/x.warc.gz",
                    "offset": "0",
                    "length": "10",
                }
            )
        )


def test_warc_range_validation() -> None:
    assert build_warc_range_url("crawl-data/CC-MAIN-2019-51/part.warc.gz").startswith(
        f"https://{CC_DATA_HOST}/"
    )
    assert build_range_header(20, 10) == "bytes=20-29"
    with pytest.raises(KuCoinP0CError):
        build_warc_range_url("../outside.warc.gz")
    with pytest.raises(KuCoinP0CError):
        build_range_header(0, 9 * 1024 * 1024)


def test_warc_http_payload_and_gzip_limit() -> None:
    record = (
        b"WARC/1.0\r\nWARC-Type: response\r\n\r\n"
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n"
        b"<html>BTC/USDT ETH-USDT</html>"
    )
    parsed = parse_warc_http_payload(gzip.compress(record))
    assert parsed["status_code"] == 200
    assert b"BTC/USDT" in parsed["payload"]
    with pytest.raises(KuCoinP0CError):
        parse_warc_http_payload(gzip.compress(record), maximum_decompressed=5)


def test_archive_parser_is_candidate_only_and_spot_classified() -> None:
    rows = classify_archived_content(
        "<h1>EOS/USDT listed</h1><p>Spot market</p>",
        content_type="text/html",
        original_url="https://www.kucoin.com/announcement/eos",
    )
    assert {row["candidate_pair"] for row in rows} == {"EOS-USDT"}
    assert rows[0]["membership_proof"] == "PENDING_CLASSIC_SPOT_KLINE"
    non_spot = classify_archived_content(
        "Futures ETH/USDT perpetual",
        content_type="text/html",
        original_url="https://www.kucoin.com/announcement/futures",
    )
    assert non_spot[0]["evidence_class"] == "ARCHIVED_KUCOIN_NON_SPOT_CONTENT"


def test_capture_deduplication_is_deterministic() -> None:
    rows = [
        {
            "digest": "D",
            "capture_timestamp": "2019-02-01T00:00:00+00:00",
            "original_url": "https://kucoin.com/a",
        },
        {
            "digest": "D",
            "capture_timestamp": "2019-01-01T00:00:00+00:00",
            "original_url": "https://kucoin.com/b",
        },
    ]
    result = deduplicate_cdx_rows(rows)
    assert len(result) == 1
    assert result[0]["original_url"].endswith("/b")


def test_current_registry_retention_requires_nonempty_archive_set() -> None:
    result = current_registry_retention([], ["BTC", "ETH"], ["OLD"])
    assert result["threshold_pass"] is False
    assert current_registry_retention(["BTC"], ["BTC"], ["OLD"])["threshold_pass"] is False
    assert current_registry_retention(["BTC"], ["BTC", "OLD"], ["OLD"])["threshold_pass"] is True


def test_decision_branches_are_frozen() -> None:
    decision, next_stage = decide_p0c({"usable_pre_2020_official_capture": False})
    assert decision == "RD18_P0C_COMMON_CRAWL_COVERAGE_INSUFFICIENT"
    assert next_stage == "RD18_BLOCKED_PENDING_FREE_PRE2019_KUCOIN_INVENTORY"
    decision, _ = decide_p0c(
        {"usable_pre_2020_official_capture": True, "multi_pair_inventory_capture": False}
    )
    assert decision == "RD18_P0C_ARCHIVE_EVIDENCE_TOO_SPARSE"


def test_no_post_2024_archive_capture() -> None:
    row = {
        "capture_timestamp": datetime(2024, 12, 31, tzinfo=UTC).isoformat(),
        "original_url": "https://kucoin.com/markets",
        "status": "200",
        "mime": "text/html",
    }
    assert archive_capture_is_usable(row)
