from datetime import UTC, datetime

import pytest

from spotbot.cli.download_data import (
    build_parser,
    parse_utc_datetime,
)


def test_parse_zulu_datetime() -> None:
    parsed = parse_utc_datetime(
        "2026-07-01T00:00:00Z"
    )

    assert parsed == datetime(
        2026,
        7,
        1,
        tzinfo=UTC,
    )


def test_offset_datetime_is_normalized_to_utc() -> None:
    parsed = parse_utc_datetime(
        "2026-07-01T03:00:00+03:00"
    )

    assert parsed == datetime(
        2026,
        7,
        1,
        tzinfo=UTC,
    )


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(
        Exception,
        match="timezone",
    ):
        parse_utc_datetime(
            "2026-07-01T00:00:00"
        )


def test_required_cli_arguments_are_parsed() -> None:
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
            "2026-07-02T00:00:00Z",
        ]
    )

    assert arguments.exchange == "kucoin"
    assert arguments.symbol == "BTC/USDT"
    assert arguments.timeframe == "1h"