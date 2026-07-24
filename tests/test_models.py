from datetime import UTC, datetime

import pytest

from spotbot.core.models import Candle


def test_valid_candle() -> None:
    candle = Candle(
        symbol="BTC/USDT",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=1_000.0,
    )

    candle.validate()


def test_naive_timestamp_is_rejected() -> None:
    candle = Candle(
        symbol="BTC/USDT",
        timestamp=datetime(2026, 1, 1),
        open=100.0,
        high=110.0,
        low=95.0,
        close=105.0,
        volume=1_000.0,
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        candle.validate()


def test_invalid_high_is_rejected() -> None:
    candle = Candle(
        symbol="BTC/USDT",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        open=100.0,
        high=99.0,
        low=95.0,
        close=105.0,
        volume=1_000.0,
    )

    with pytest.raises(ValueError, match="High price"):
        candle.validate()
