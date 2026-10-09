import pytest

from spotbot.research.rnb_bounded_2022 import (
    END,
    HOUR,
    START,
    BoundaryError,
    CandlePage,
    fetch_page,
    normalize_2022,
    parse_page,
    plan_page,
)


@pytest.mark.parametrize("cursor,limit,count", [
    (START, 1000, 1000), (END - 12 * HOUR, 1000, 11),
    (END - 1001 * HOUR, 1000, 1000), (END - 2 * HOUR, 1000, 1),
])
def test_page_boundaries(cursor, limit, count):
    page = plan_page("BTC-USDT", cursor, page_limit=limit)
    assert page.next_since == cursor + count * HOUR
    assert page.end_at == page.next_since - 1
    assert page.end_at < END - HOUR


@pytest.mark.parametrize("cursor", [END - HOUR, END, END + HOUR])
def test_no_remaining_request(cursor):
    assert plan_page("BTC-USDT", cursor) is None


def test_all_pages_exact_progression():
    cursor = START
    covered = []
    while (page := plan_page("BTC-USDT", cursor)) is not None:
        covered.extend(range(page.start_at, page.next_since, HOUR))
        assert page.next_since > cursor
        cursor = page.next_since
    assert covered == list(range(START, END - HOUR, HOUR))
    assert len(covered) == 8759


def test_remote_endpoint_receives_upper_bound():
    class Client:
        def publicGetMarketCandles(self, params):
            assert params == {"symbol": "BTC-USDT", "type": "1hour",
                              "startAt": END - 2 * HOUR, "endAt": END - HOUR - 1}
            return {"code": "200000", "data": []}
    assert fetch_page(Client(), plan_page("BTC-USDT", END - 2 * HOUR)) == []


def test_forged_page_never_calls_remote():
    class Client:
        def publicGetMarketCandles(self, params):
            pytest.fail("request must be refused")
    with pytest.raises(BoundaryError):
        fetch_page(Client(), CandlePage("BTC-USDT", START, END, END + HOUR))


def test_protected_close_is_rejected_before_prices_are_parsed():
    response = {"code": "200000", "data": [[str(END - HOUR)] + ["bad"] * 6]}
    with pytest.raises(BoundaryError, match="bounds"):
        parse_page(plan_page("BTC-USDT", END - 2 * HOUR), response)


def test_native_timestamp_conversion():
    raw = {"code": "200000", "data": [[str(START), "2", "3", "4", "1", "5", "9"]]}
    frame = normalize_2022(parse_page(plan_page("BTC-USDT", START), raw))
    assert frame.iloc[0]["timestamp"].timestamp() == START + HOUR
    assert str(frame["timestamp"].dt.tz) == "UTC"
    assert list(frame.loc[0, ["open", "high", "low", "close", "volume"]]) == [2, 4, 1, 3, 5]


def test_duplicates_fail():
    with pytest.raises(BoundaryError, match="duplicate"):
        normalize_2022([[START * 1000, 2, 4, 1, 3, 5]] * 2)


@pytest.mark.parametrize("cursor,limit", [(START - HOUR, 1), (START + 1, 1),
                                           (START, 0), (START, 1001)])
def test_invalid_request_fails(cursor, limit):
    with pytest.raises(BoundaryError):
        plan_page("BTC-USDT", cursor, page_limit=limit)
