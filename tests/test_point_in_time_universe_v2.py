from datetime import UTC, datetime

import pytest

from spotbot.research.point_in_time_universe_v2 import (
    AssetUniverseEntry,
    PointInTimeUniverseV2ConfigurationError,
    build_point_in_time_universe,
)

UTC = UTC


def make_entry(
    symbol: str,
    *,
    first_year: int,
    last_year: int | None = None,
    eligible: bool = True,
) -> AssetUniverseEntry:
    return AssetUniverseEntry(
        symbol=symbol,
        first_available=datetime(
            first_year,
            1,
            1,
            tzinfo=UTC,
        ),
        last_available=(
            datetime(
                last_year,
                1,
                1,
                tzinfo=UTC,
            )
            if last_year is not None
            else None
        ),
        eligible=eligible,
    )


def test_future_assets_are_excluded() -> None:
    result = build_point_in_time_universe(
        (
            make_entry(
                "BTC/USDT",
                first_year=2020,
            ),
            make_entry(
                "NEW/USDT",
                first_year=2024,
            ),
        ),
        timestamp=datetime(
            2022,
            1,
            1,
            tzinfo=UTC,
        ),
    )

    assert tuple(
        entry.symbol
        for entry in result
    ) == (
        "BTC/USDT",
    )


def test_ineligible_assets_are_excluded() -> None:
    result = build_point_in_time_universe(
        (
            make_entry(
                "BTC/USDT",
                first_year=2020,
            ),
            make_entry(
                "BAD/USDT",
                first_year=2020,
                eligible=False,
            ),
        ),
        timestamp=datetime(
            2022,
            1,
            1,
            tzinfo=UTC,
        ),
    )

    assert tuple(
        entry.symbol
        for entry in result
    ) == (
        "BTC/USDT",
    )


def test_last_available_is_exclusive() -> None:
    asset = make_entry(
        "OLD/USDT",
        first_year=2020,
        last_year=2023,
    )

    before_delisting = (
        build_point_in_time_universe(
            (asset,),
            timestamp=datetime(
                2022,
                12,
                31,
                tzinfo=UTC,
            ),
        )
    )

    at_delisting = (
        build_point_in_time_universe(
            (asset,),
            timestamp=datetime(
                2023,
                1,
                1,
                tzinfo=UTC,
            ),
        )
    )

    assert len(before_delisting) == 1
    assert at_delisting == ()


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(
        PointInTimeUniverseV2ConfigurationError,
        match="timezone-aware",
    ):
        build_point_in_time_universe(
            (
                make_entry(
                    "BTC/USDT",
                    first_year=2020,
                ),
            ),
            timestamp=datetime(
                2022,
                1,
                1,
            ),
        )


def test_duplicate_symbols_are_rejected() -> None:
    entries = (
        make_entry(
            "btc/usdt",
            first_year=2020,
        ),
        make_entry(
            "BTC/USDT",
            first_year=2021,
        ),
    )

    with pytest.raises(
        PointInTimeUniverseV2ConfigurationError,
        match="Duplicate",
    ):
        build_point_in_time_universe(
            entries,
            timestamp=datetime(
                2022,
                1,
                1,
                tzinfo=UTC,
            ),
        )
