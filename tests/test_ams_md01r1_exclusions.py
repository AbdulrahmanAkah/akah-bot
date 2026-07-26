from __future__ import annotations

import pytest

from spotbot.research.ams_md01r1_universe import exclusion_reason


@pytest.mark.parametrize("symbol", ["USDC", "DAI", "USDD", "FRAX"])
def test_stablecoins_are_excluded(symbol: str) -> None:
    assert exclusion_reason(symbol) == "STABLECOIN"


@pytest.mark.parametrize("symbol", ["BTC3L", "ETH2S", "ADAUP", "XRPDOWN"])
def test_leveraged_tokens_are_excluded(symbol: str) -> None:
    assert exclusion_reason(symbol) == "LEVERAGED_TOKEN"


def test_plain_spot_asset_is_included() -> None:
    assert exclusion_reason("BTC") is None
    assert exclusion_reason("BTC", market_kind="FUTURES") == "NON_SPOT"
