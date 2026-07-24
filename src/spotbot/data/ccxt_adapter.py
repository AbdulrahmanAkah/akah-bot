from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

import ccxt  # type: ignore[import-untyped]

from spotbot.data.provider import (
    DataProviderError,
    OHLCVValue,
)


class UnknownExchangeError(DataProviderError):
    pass


class ExchangeResponseError(DataProviderError):
    pass


class CCXTExchangeAdapter:
    """
    Restricts CCXT to public Spot market-data operations.

    No credentials or trading methods are exposed by this adapter.
    """

    def __init__(
        self,
        exchange_id: str,
        *,
        enable_rate_limit: bool = True,
    ) -> None:
        normalized_id = exchange_id.strip().lower()

        if not normalized_id:
            raise ValueError("Exchange ID cannot be empty.")

        supported = cast(
            Sequence[str],
            ccxt.exchanges,
        )

        if normalized_id not in supported:
            raise UnknownExchangeError(
                f"Exchange is not supported by CCXT: {normalized_id}"
            )

        constructor = getattr(
            ccxt,
            normalized_id,
            None,
        )

        if constructor is None or not callable(constructor):
            raise UnknownExchangeError(
                f"Exchange constructor was not found: {normalized_id}"
            )

        configuration: dict[str, object] = {
            "enableRateLimit": enable_rate_limit,
            "options": {
                "defaultType": "spot",
            },
        }

        self._exchange: Any = constructor(
            configuration
        )
        self.id = normalized_id

    def load_markets(
        self,
    ) -> Mapping[str, Mapping[str, object]]:
        raw_markets: object = (
            self._exchange.load_markets()
        )

        if not isinstance(raw_markets, dict):
            raise ExchangeResponseError(
                "Exchange returned an invalid market collection."
            )

        return cast(
            Mapping[str, Mapping[str, object]],
            raw_markets,
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[OHLCVValue]]:
        raw_rows: object = self._exchange.fetch_ohlcv(
            symbol,
            timeframe,
            since=since,
            limit=limit,
        )

        if not isinstance(raw_rows, list):
            raise ExchangeResponseError(
                "Exchange returned an invalid OHLCV response."
            )

        result: list[list[OHLCVValue]] = []

        for raw_row in raw_rows:
            if not isinstance(
                raw_row,
                (list, tuple),
            ):
                raise ExchangeResponseError(
                    "OHLCV row must be a sequence."
                )

            values = cast(
                Sequence[object],
                raw_row,
            )

            if len(values) < 6:
                raise ExchangeResponseError(
                    "OHLCV row contains fewer than six values."
                )

            normalized_row: list[OHLCVValue] = []

            for value in values[:6]:
                if isinstance(value, bool) or not isinstance(
                    value,
                    (int, float),
                ):
                    raise ExchangeResponseError(
                        "OHLCV values must be numeric."
                    )

                normalized_row.append(value)

            result.append(normalized_row)

        return result