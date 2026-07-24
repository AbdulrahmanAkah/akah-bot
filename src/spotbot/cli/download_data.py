from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from spotbot.data.ccxt_adapter import (
    CCXTExchangeAdapter,
)
from spotbot.data.provider import (
    CCXTSpotDataProvider,
)
from spotbot.data.store import (
    ParquetCandleStore,
)


def parse_utc_datetime(value: str) -> datetime:
    normalized = value.strip()

    if normalized.endswith("Z"):
        normalized = (
            normalized[:-1] + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Invalid ISO-8601 datetime: {value}"
        ) from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "Datetime must include a timezone, such as Z or +00:00."
        )

    return parsed.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spotbot-download",
        description=(
            "Download complete historical Spot candles, "
            "validate them, and store them as Parquet."
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
        help="Inclusive ISO-8601 start time.",
    )
    parser.add_argument(
        "--until",
        required=True,
        type=parse_utc_datetime,
        help="Exclusive as-of time.",
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
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing dataset.",
    )

    return parser


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
    overwrite = cast(
        bool,
        arguments.overwrite,
    )

    adapter = CCXTExchangeAdapter(
        exchange_id
    )
    provider = CCXTSpotDataProvider(
        adapter
    )

    history = provider.fetch_history(
        symbol=symbol,
        timeframe=timeframe,
        since=since,
        until=until,
        page_limit=page_limit,
    )

    store = ParquetCandleStore(root)

    stored = store.save(
        history.frame,
        exchange_id=history.exchange_id,
        symbol=history.symbol,
        timeframe=history.timeframe,
        overwrite=overwrite,
    )

    summary: dict[str, object] = {
        "status": "PASS",
        "exchange": history.exchange_id,
        "symbol": history.symbol,
        "timeframe": history.timeframe,
        "since": history.since.isoformat(),
        "until": history.until.isoformat(),
        "pages": history.pages,
        "rows": stored.rows,
        "data_path": str(
            stored.data_path.resolve()
        ),
        "metadata_path": str(
            stored.metadata_path.resolve()
        ),
        "sha256": stored.sha256,
    }

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())