"""Opt-in research acquisition; explicit KuCoin server bounds, no replay.

KuCoin candle timestamps are opens. Native normalization stores closes. An
inclusive endAt must therefore precede the open of the first forbidden close.
Never rely on CCXT's post-response limit/filter to exclude protected candles.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from spotbot.data.provider import normalize_ohlcv_rows

START = 1640995200  # 2022-01-01T00:00:00Z
END = 1672531200  # exclusive close-time boundary
HOUR = 3600
ENDPOINT = "https://api.kucoin.com/api/v1/market/candles"


class BoundaryError(ValueError):
    """Refuse any request or response outside the frozen research window."""


@dataclass(frozen=True)
class CandlePage:
    pair: str
    start_at: int
    end_at: int
    next_since: int

    def params(self) -> dict[str, object]:
        return {"symbol": self.pair, "type": "1hour",
                "startAt": self.start_at, "endAt": self.end_at}


def plan_page(pair: str, next_since: int, *, page_limit: int = 1000) -> CandlePage | None:
    """Bounds are seconds of candle OPEN; admitted closes remain strictly < END."""
    if not pair.endswith("-USDT") or not pair.replace("-", "").isalnum():
        raise BoundaryError("invalid native pair")
    if type(next_since) is not int or next_since < START or next_since % HOUR:
        raise BoundaryError("cursor must be a 2022-or-later aligned open")
    if type(page_limit) is not int or not 1 <= page_limit <= 1000:
        raise BoundaryError("page limit must be 1..1000")
    # Open END-HOUR would close at END, which is forbidden even if dated 2022.
    stop_open_exclusive = END - HOUR
    if next_since >= stop_open_exclusive:
        return None
    next_cursor = min(next_since + page_limit * HOUR, stop_open_exclusive)
    return CandlePage(pair, next_since, next_cursor - 1, next_cursor)


def parse_page(page: CandlePage, response: dict[str, Any]) -> list[list[float | int]]:
    """Validate every timestamp before converting OHLCV; never filter bad rows."""
    if response.get("code") != "200000" or not isinstance(response.get("data"), list):
        raise BoundaryError("KuCoin request did not return successful candle data")
    rows = response["data"]
    for row in rows:
        if not isinstance(row, list) or len(row) < 7:
            raise BoundaryError("malformed KuCoin candle")
        timestamp = int(row[0])
        if (timestamp % HOUR or not page.start_at <= timestamp <= page.end_at
                or not START <= timestamp + HOUR < END):
            raise BoundaryError("remote response violates pre-request bounds")
    # Native OHLCV normalizer: [open_ms, open, high, low, close, volume].
    return [[int(r[0]) * 1000, float(r[1]), float(r[3]), float(r[4]),
             float(r[2]), float(r[5])] for r in rows]


def normalize_2022(rows: list[list[float | int]]):
    """Use native conversion; prevalidate rather than discard out-of-window rows."""
    for row in rows:
        if not START <= int(row[0]) // 1000 + HOUR < END:
            raise BoundaryError("out-of-window candle before normalization")
    frame = normalize_ohlcv_rows(
        rows, timeframe="1h", since=datetime.fromtimestamp(START, UTC),
        until=datetime.fromtimestamp(END - 1, UTC),
    )
    if frame["timestamp"].duplicated().any():
        raise BoundaryError("duplicate candle; no silent keep-last")
    return frame


def fetch_page(client: Any, page: CandlePage) -> list[list[float | int]]:
    """Call the exact public spot endpoint, no discovery/load_markets requests."""
    expected = plan_page(page.pair, page.start_at,
                         page_limit=(page.next_since - page.start_at) // HOUR)
    if page != expected:
        raise BoundaryError("page not produced by frozen planner")
    return parse_page(page, client.publicGetMarketCandles(page.params()))
