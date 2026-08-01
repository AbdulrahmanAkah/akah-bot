from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest

from spotbot.research.pit_market_cap import (
    PITMarketCapRecord,
    PITMarketCapValidationError,
    raw_payload_sha256,
    reject_current_supply_lookahead,
    validate_record,
)
from spotbot.research.universe_identity import canonical, exclusion, resolve_identity


def test_identity_preserves_rd16_canonical_and_exclusion_behavior() -> None:
    assert canonical("bitcoin") == "BTC"
    assert canonical("BNB") == "BNB"
    assert canonical("USDT") is None
    assert canonical("wbtc") is None
    assert canonical("usdt_eth") is None
    assert exclusion("USDT") == "STABLECOIN_OR_CASH"
    assert exclusion("wbtc") == "WRAPPED_OR_NETWORK_REPRESENTATION"
    assert exclusion("usdt_eth") == "WRAPPED_OR_NETWORK_REPRESENTATION"
    assert exclusion("?") == "UNMAPPED_OR_INVALID_ASSET"


def test_identity_does_not_silently_merge_wrapped_or_duplicate_network_rows() -> None:
    resolved = resolve_identity(
        provider_name="fixture",
        provider_asset_id="matic-eth",
        symbol="MATIC",
        duplicate_network_representation_flag=True,
    )
    assert resolved.canonical_asset_id is None
    assert resolved.duplicate_network_representation_flag is True


def _record(**overrides: object) -> PITMarketCapRecord:
    values: dict[str, object] = {
        "provider": "fixture",
        "provider_asset_id": "asset-1",
        "canonical_asset_id": "BTC",
        "symbol_at_observation": "BTC",
        "name_at_observation": "Bitcoin",
        "observation_time": datetime(2024, 3, 10, tzinfo=UTC),
        "provider_published_at": None,
        "available_at": datetime(2024, 3, 11, tzinfo=UTC),
        "price_usd": 1.0,
        "circulating_supply": 1.0,
        "market_cap_usd": 1.0,
        "market_cap_definition": "CIRCULATING_MARKET_CAP_USD",
        "listing_status": "active",
        "source_url_or_request": "offline:fixture",
        "raw_request_id": "fixture-1",
        "raw_payload_sha256": raw_payload_sha256(b"fixture"),
        "retrieved_at": "offline_fixture",
        "identity_confidence": "HIGH",
        "quality_flags": (),
    }
    values.update(overrides)
    return PITMarketCapRecord(**cast(dict[str, object], values))


def test_pit_contract_accepts_circulating_cap_only() -> None:
    assert validate_record(_record()).canonical_asset_id == "BTC"


@pytest.mark.parametrize(
    "overrides",
    [
        {"market_cap_definition": "CapMrktEstUSD"},
        {"quality_flags": ("FULLY_DILUTED_VALUATION",)},
        {"quality_flags": ("CURRENT_SUPPLY_PROJECTED_BACKWARD",)},
        {"observation_time": datetime(2025, 1, 1, tzinfo=UTC)},
    ],
)
def test_pit_contract_rejects_non_causal_or_non_circulating_rows(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(PITMarketCapValidationError):
        validate_record(_record(**overrides))


def test_current_supply_lookahead_is_rejected() -> None:
    with pytest.raises(PITMarketCapValidationError):
        reject_current_supply_lookahead(
            observation_time=datetime(2024, 3, 10, tzinfo=UTC),
            supply_time=datetime(2024, 3, 11, tzinfo=UTC),
        )
