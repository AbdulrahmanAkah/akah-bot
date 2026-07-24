from datetime import UTC, datetime
from pathlib import Path

from spotbot.cli.sync_data import (
    build_parser,
    result_to_summary,
)
from spotbot.data.sync import DatasetSyncResult


def test_sync_cli_arguments_are_parsed() -> None:
    parser = build_parser()

    arguments = parser.parse_args(
        [
            "--exchange",
            "kucoin",
            "--symbol",
            "BTC/USDT",
            "--timeframe",
            "1h",
            "--since",
            "2026-07-01T00:00:00Z",
            "--until",
            "2026-07-23T00:00:00Z",
        ]
    )

    assert arguments.exchange == "kucoin"
    assert arguments.symbol == "BTC/USDT"
    assert arguments.timeframe == "1h"
    assert arguments.page_limit == 1_000


def test_sync_result_is_serialized() -> None:
    start = datetime(
        2026,
        7,
        1,
        tzinfo=UTC,
    )
    end = datetime(
        2026,
        7,
        23,
        tzinfo=UTC,
    )

    result = DatasetSyncResult(
        status="UPDATED",
        exchange_id="kucoin",
        symbol="BTC/USDT",
        timeframe="1h",
        requested_since=start,
        requested_until=end,
        fetch_since=datetime(
            2026,
            7,
            2,
            tzinfo=UTC,
        ),
        fetched_rows=504,
        total_rows=528,
        data_path=Path(
            "data/raw/kucoin/BTC-USDT/1h.parquet"
        ),
        metadata_path=Path(
            "data/raw/kucoin/BTC-USDT/1h.metadata.json"
        ),
        sha256="a" * 64,
    )

    summary = result_to_summary(result)

    assert summary["status"] == "UPDATED"
    assert summary["fetched_rows"] == 504
    assert summary["total_rows"] == 528
    assert summary["sha256"] == "a" * 64