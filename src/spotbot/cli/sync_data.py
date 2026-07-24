from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from spotbot.cli.download_data import parse_utc_datetime
from spotbot.data.ccxt_adapter import CCXTExchangeAdapter
from spotbot.data.provider import CCXTSpotDataProvider
from spotbot.data.store import ParquetCandleStore
from spotbot.data.sync import DatasetSyncResult, sync_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spotbot-sync",
        description=(
            "Create or incrementally update a validated "
            "historical Spot candle dataset."
        ),
    )

    parser.add_argument(
        "--exchange",
        required=True,
        help="CCXT exchange ID, for example kucoin.",
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Unified Spot symbol, for example BTC/USDT.",
    )
    parser.add_argument(
        "--timeframe",
        required=True,
        help="Timeframe such as 1h, 4h, or 1d.",
    )
    parser.add_argument(
        "--since",
        required=True,
        type=parse_utc_datetime,
        help="Required beginning of the historical range.",
    )
    parser.add_argument(
        "--until",
        required=True,
        type=parse_utc_datetime,
        help="Exclusive UTC as-of time.",
    )
    parser.add_argument(
        "--root",
        default="data/raw",
        help="Root directory for Parquet datasets.",
    )
    parser.add_argument(
        "--page-limit",
        type=int,
        default=1_000,
        help="Maximum candles requested per API page.",
    )

    return parser


def result_to_summary(
    result: DatasetSyncResult,
) -> dict[str, object]:
    return {
        "status": result.status,
        "exchange": result.exchange_id,
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "requested_since": (
            result.requested_since.isoformat()
        ),
        "requested_until": (
            result.requested_until.isoformat()
        ),
        "fetch_since": (
            result.fetch_since.isoformat()
        ),
        "fetched_rows": result.fetched_rows,
        "total_rows": result.total_rows,
        "data_path": str(
            result.data_path.resolve()
        ),
        "metadata_path": str(
            result.metadata_path.resolve()
        ),
        "sha256": result.sha256,
    }


def main(
    argv: Sequence[str] | None = None,
) -> int:
    parser = build_parser()
    arguments = parser.parse_args(
        list(argv) if argv is not None else None
    )

    exchange_id = cast(
        str,
        arguments.exchange,
    )
    symbol = cast(
        str,
        arguments.symbol,
    )
    timeframe = cast(
        str,
        arguments.timeframe,
    )
    since = cast(
        datetime,
        arguments.since,
    )
    until = cast(
        datetime,
        arguments.until,
    )
    root = Path(
        cast(str, arguments.root)
    )
    page_limit = cast(
        int,
        arguments.page_limit,
    )

    adapter = CCXTExchangeAdapter(
        exchange_id
    )
    provider = CCXTSpotDataProvider(
        adapter
    )
    store = ParquetCandleStore(root)

    result = sync_dataset(
        provider=provider,
        store=store,
        exchange_id=adapter.id,
        symbol=symbol,
        timeframe=timeframe,
        since=since,
        until=until,
        page_limit=page_limit,
    )

    print(
        json.dumps(
            result_to_summary(result),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())