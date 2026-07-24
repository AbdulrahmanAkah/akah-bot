from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import pandas as pd

from spotbot.data.timeframes import timeframe_to_milliseconds
from spotbot.data.validator import REQUIRED_COLUMNS, validate_candles

OHLCVValue = int | float
OHLCVRow = Sequence[OHLCVValue]


class DataProviderError(RuntimeError):
    pass


class MarketValidationError(DataProviderError):
    pass


class DataIntegrityError(DataProviderError):
    pass


class PaginationError(DataProviderError):
    pass


class ExchangeClient(Protocol):
    id: str

    def load_markets(
        self,
    ) -> Mapping[str, Mapping[str, object]]:
        ...

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[OHLCVValue]]:
        ...


@dataclass(frozen=True, slots=True)
class HistoryResult:
    exchange_id: str
    symbol: str
    timeframe: str
    since: datetime
    until: datetime
    pages: int
    frame: pd.DataFrame

    @property
    def rows(self) -> int:
        return len(self.frame)


def _require_aware_utc(
    value: datetime,
    *,
    name: str,
) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            f"{name} must be timezone-aware."
        )

    return value.astimezone(UTC)


def _datetime_to_milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1_000)


def _finite_float(
    value: object,
    *,
    field: str,
) -> float:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise DataIntegrityError(
            f"{field} must be numeric."
        )

    result = float(value)

    if not math.isfinite(result):
        raise DataIntegrityError(
            f"{field} must be finite."
        )

    return result


def _open_timestamp_ms(row: OHLCVRow) -> int:
    if len(row) < 6:
        raise DataIntegrityError(
            "OHLCV row must contain at least six values."
        )

    value = row[0]

    if isinstance(value, bool) or not isinstance(
        value,
        (int, float),
    ):
        raise DataIntegrityError(
            "OHLCV timestamp must be numeric."
        )

    timestamp = float(value)

    if not math.isfinite(timestamp):
        raise DataIntegrityError(
            "OHLCV timestamp must be finite."
        )

    return int(timestamp)


def normalize_ohlcv_rows(
    rows: Sequence[OHLCVRow],
    *,
    timeframe: str,
    since: datetime,
    until: datetime,
) -> pd.DataFrame:
    since_utc = _require_aware_utc(
        since,
        name="since",
    )
    until_utc = _require_aware_utc(
        until,
        name="until",
    )

    if until_utc <= since_utc:
        raise ValueError(
            "until must be later than since."
        )

    duration_ms = timeframe_to_milliseconds(timeframe)
    since_ms = _datetime_to_milliseconds(since_utc)
    until_ms = _datetime_to_milliseconds(until_utc)

    records: list[dict[str, object]] = []

    for row in rows:
        open_ms = _open_timestamp_ms(row)
        close_ms = open_ms + duration_ms

        if open_ms < since_ms:
            continue

        if open_ms >= until_ms:
            continue

        # The candle is incomplete at the requested as-of time.
        if close_ms > until_ms:
            continue

        records.append(
            {
                "timestamp": pd.Timestamp(
                    close_ms,
                    unit="ms",
                    tz="UTC",
                ),
                "open": _finite_float(
                    row[1],
                    field="open",
                ),
                "high": _finite_float(
                    row[2],
                    field="high",
                ),
                "low": _finite_float(
                    row[3],
                    field="low",
                ),
                "close": _finite_float(
                    row[4],
                    field="close",
                ),
                "volume": _finite_float(
                    row[5],
                    field="volume",
                ),
            }
        )

    frame = pd.DataFrame.from_records(
        records,
        columns=list(REQUIRED_COLUMNS),
    )

    if frame.empty:
        return frame

    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
    )

    return frame.sort_values(
        by="timestamp",
        kind="stable",
    ).reset_index(drop=True)


class CCXTSpotDataProvider:
    def __init__(
        self,
        exchange: ExchangeClient,
        *,
        max_pages: int = 10_000,
    ) -> None:
        if max_pages < 1:
            raise ValueError(
                "max_pages must be at least 1."
            )

        self.exchange = exchange
        self.max_pages = max_pages

    def _validate_spot_market(
        self,
        symbol: str,
    ) -> None:
        markets = self.exchange.load_markets()
        market = markets.get(symbol)

        if market is None:
            raise MarketValidationError(
                f"Market not found: {symbol}"
            )

        if market.get("spot") is not True:
            raise MarketValidationError(
                f"Market is not explicitly Spot: {symbol}"
            )

        forbidden_flags = (
            "contract",
            "swap",
            "future",
            "option",
        )

        for flag in forbidden_flags:
            if market.get(flag) is True:
                raise MarketValidationError(
                    f"Forbidden market flag {flag!r} "
                    f"detected for {symbol}."
                )

        if market.get("active") is False:
            raise MarketValidationError(
                f"Market is inactive: {symbol}"
            )

    def fetch_history(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime,
        until: datetime,
        page_limit: int = 1_000,
    ) -> HistoryResult:
        if not symbol.strip():
            raise ValueError(
                "Symbol cannot be empty."
            )

        if page_limit < 1 or page_limit > 1_000:
            raise ValueError(
                "page_limit must be between 1 and 1000."
            )

        since_utc = _require_aware_utc(
            since,
            name="since",
        )
        until_utc = _require_aware_utc(
            until,
            name="until",
        )

        if until_utc <= since_utc:
            raise ValueError(
                "until must be later than since."
            )

        self._validate_spot_market(symbol)

        duration_ms = timeframe_to_milliseconds(timeframe)
        cursor_ms = _datetime_to_milliseconds(since_utc)
        until_ms = _datetime_to_milliseconds(until_utc)

        raw_rows: list[OHLCVRow] = []
        pages = 0

        while cursor_ms < until_ms:
            if pages >= self.max_pages:
                raise PaginationError(
                    "Maximum pagination limit exceeded."
                )

            page = self.exchange.fetch_ohlcv(
                symbol,
                timeframe,
                since=cursor_ms,
                limit=page_limit,
            )
            pages += 1

            if not page:
                break

            raw_rows.extend(page)

            maximum_open_ms = max(
                _open_timestamp_ms(row)
                for row in page
            )

            next_cursor_ms = (
                maximum_open_ms + duration_ms
            )

            if next_cursor_ms <= cursor_ms:
                raise PaginationError(
                    "Exchange pagination did not advance."
                )

            cursor_ms = next_cursor_ms

        frame = normalize_ohlcv_rows(
            raw_rows,
            timeframe=timeframe,
            since=since_utc,
            until=until_utc,
        )

        if frame.empty:
            raise DataIntegrityError(
                f"No complete candles returned for "
                f"{symbol} {timeframe}."
            )

        report = validate_candles(
            frame,
            symbol=symbol,
            expected_frequency=timeframe,
        )

        if not report.is_valid:
            raise DataIntegrityError(
                "Historical data validation failed: "
                f"rows={report.rows}, "
                f"duplicates={report.duplicate_timestamps}, "
                f"missing={report.missing_intervals}, "
                f"invalid={report.invalid_rows}"
            )

        return HistoryResult(
            exchange_id=self.exchange.id,
            symbol=symbol,
            timeframe=timeframe,
            since=since_utc,
            until=until_utc,
            pages=pages,
            frame=frame,
        )