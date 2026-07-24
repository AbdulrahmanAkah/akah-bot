from datetime import UTC, datetime

from spotbot.research.universe.point_in_time_universe_v2 import (
    AssetUniverseEntry,
    build_point_in_time_universe,
)


def test_point_in_time_universe_filters_future_assets() -> None:
    entries = (
        AssetUniverseEntry(
            symbol="BTC/USDT",
            first_available=datetime(
                2021,
                1,
                1,
                tzinfo=UTC,
            ),
            last_available=None,
            eligible=True,
        ),
        AssetUniverseEntry(
            symbol="NEW/USDT",
            first_available=datetime(
                2025,
                1,
                1,
                tzinfo=UTC,
            ),
            last_available=None,
            eligible=True,
        ),
    )

    result = build_point_in_time_universe(
        entries,
        datetime(
            2022,
            1,
            1,
            tzinfo=UTC,
        ),
    )

    assert [x.symbol for x in result] == [
        "BTC/USDT"
    ]
