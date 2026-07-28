from __future__ import annotations

from spotbot.research.rd08_protocol_registration import LABELS, SIGNALS, protocol_payload


def test_rd08_registry_is_exact_and_unique() -> None:
    assert len(SIGNALS) == 14
    assert len({item.signal_id for item in SIGNALS}) == 14
    assert sum(item.signal_class == "CONFIRMATORY" for item in SIGNALS) == 13
    assert len(LABELS) == 9


def test_rd08_protocol_closes_cross_sectional_space() -> None:
    payload = protocol_payload()
    assert payload["cross_sectional_price_volume_flow_space_closed"] is True
    assert payload["portfolio_construction_authorized"] is False
    assert payload["test_2025_accessed"] is False
