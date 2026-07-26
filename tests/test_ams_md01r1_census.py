from __future__ import annotations

from spotbot.research.ams_md01r1_universe import build_point_in_time_census


def test_current_market_is_not_backfilled_into_historical_membership() -> None:
    census = build_point_in_time_census(
        current_symbols=[
            {
                "baseCurrency": "BTC",
                "quoteCurrency": "USDT",
                "enableTrading": True,
                "tradingStartTime": None,
            }
        ],
        listing_announcements=[],
        delisting_announcements=[],
    )
    assert census[0]["currently_listed"] is True
    assert census[0]["membership_resolved"] is False
    assert census[0]["membership_start"] is None


def test_census_is_deterministic_and_detects_duplicate_mapping() -> None:
    market = {
        "baseCurrency": "BTC",
        "quoteCurrency": "USDT",
        "enableTrading": True,
        "tradingStartTime": 1_609_459_200_000,
    }
    first = build_point_in_time_census(
        current_symbols=[market, market],
        listing_announcements=[],
        delisting_announcements=[],
    )
    second = build_point_in_time_census(
        current_symbols=[market, market],
        listing_announcements=[],
        delisting_announcements=[],
    )
    assert first == second
    assert first[0]["mapping_conflict"] is True
