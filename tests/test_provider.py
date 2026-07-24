from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from spotbot.data.provider import (
    CCXTSpotDataProvider,
    DataIntegrityError,
    MarketValidationError,
    PaginationError,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
HOUR_MS = 60 * 60 * 1_000


def open_ms(hour: int) -> int:
    return int(
        (
            START + timedelta(hours=hour)
        ).timestamp()
        * 1_000
    )


def row(
    hour: int,
    *,
    open_price: float = 100.0,
) -> list[int | float]:
    return [
        open_ms(hour),
        open_price,
        open_price + 3.0,
        open_price - 2.0,
        open_price + 1.0,
        1_000.0,
    ]


class FakeExchange:
    id = "fake"

    def __init__(
        self,
        rows: list[list[int | float]],
        *,
        spot: bool = True,
        contract: bool = False,
    ) -> None:
        self.rows = rows
        self.markets: dict[
            str,
            Mapping[str, object],
        ] = {
            "BTC/USDT": {
                "spot": spot,
                "contract": contract,
                "swap": False,
                "future": False,
                "option": False,
                "active": True,
            }
        }

    def load_markets(
        self,
    ) -> Mapping[
        str,
        Mapping[str, object],
    ]:
        return self.markets

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[int | float]]:
        del symbol, timeframe

        effective_since = (
            0 if since is None else since
        )
        effective_limit = (
            len(self.rows)
            if limit is None
            else limit
        )

        eligible = [
            item
            for item in self.rows
            if int(item[0]) >= effective_since
        ]

        return eligible[:effective_limit]


class StalledExchange(FakeExchange):
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[int | float]]:
        del symbol, timeframe, since

        effective_limit = (
            len(self.rows)
            if limit is None
            else limit
        )

        return self.rows[:effective_limit]


def test_history_is_paginated_and_normalized() -> None:
    exchange = FakeExchange(
        [row(0), row(1), row(2), row(3)]
    )
    provider = CCXTSpotDataProvider(
        exchange
    )

    result = provider.fetch_history(
        symbol="BTC/USDT",
        timeframe="1h",
        since=START,
        until=START + timedelta(hours=4),
        page_limit=2,
    )

    assert result.rows == 4
    assert result.pages == 2

    expected_first_close = (
        START + timedelta(hours=1)
    )
    expected_last_close = (
        START + timedelta(hours=4)
    )

    assert (
        result.frame.iloc[0]["timestamp"]
        .to_pydatetime()
        == expected_first_close
    )
    assert (
        result.frame.iloc[-1]["timestamp"]
        .to_pydatetime()
        == expected_last_close
    )


def test_incomplete_candle_is_removed() -> None:
    exchange = FakeExchange(
        [row(0), row(1), row(2), row(3)]
    )
    provider = CCXTSpotDataProvider(
        exchange
    )

    result = provider.fetch_history(
        symbol="BTC/USDT",
        timeframe="1h",
        since=START,
        until=START + timedelta(
            hours=3,
            minutes=30,
        ),
    )

    assert result.rows == 3
    assert (
        result.frame.iloc[-1]["timestamp"]
        .to_pydatetime()
        == START + timedelta(hours=3)
    )


def test_non_spot_market_is_rejected() -> None:
    provider = CCXTSpotDataProvider(
        FakeExchange(
            [row(0)],
            spot=False,
            contract=True,
        )
    )

    with pytest.raises(
        MarketValidationError,
        match="Spot",
    ):
        provider.fetch_history(
            symbol="BTC/USDT",
            timeframe="1h",
            since=START,
            until=START + timedelta(hours=1),
        )


def test_gap_in_history_is_rejected() -> None:
    provider = CCXTSpotDataProvider(
        FakeExchange(
            [row(0), row(2)]
        )
    )

    with pytest.raises(
        DataIntegrityError,
        match="missing=1",
    ):
        provider.fetch_history(
            symbol="BTC/USDT",
            timeframe="1h",
            since=START,
            until=START + timedelta(hours=3),
        )


def test_stalled_pagination_is_rejected() -> None:
    provider = CCXTSpotDataProvider(
        StalledExchange(
            [row(0), row(1)]
        )
    )

    with pytest.raises(
        PaginationError,
        match="did not advance",
    ):
        provider.fetch_history(
            symbol="BTC/USDT",
            timeframe="1h",
            since=START,
            until=START + timedelta(hours=4),
            page_limit=2,
        )