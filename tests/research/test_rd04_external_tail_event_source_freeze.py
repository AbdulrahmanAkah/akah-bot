from __future__ import annotations

from dataclasses import replace

import pytest

from spotbot.research.rd04_external_tail_event_source_freeze import (
    CATEGORIES,
    DECISION_BLOCKED,
    DECISION_FROZEN,
    RESEARCH_WINDOW_END,
    TailEventSourceFreezeError,
    decision_record,
    event_rows,
    frozen_events,
    frozen_sources,
    join_contract,
    join_contract_rows,
    registry_fingerprint,
    source_rows,
    validate_registry,
    validate_report,
)


def test_registry_validates() -> None:
    validate_registry()


def test_exact_event_and_source_counts() -> None:
    assert len(frozen_events()) == 5
    assert len(frozen_sources()) == 10


def test_categories_match_d4_taxonomy() -> None:
    observed = {event.primary_category for event in frozen_events()}
    observed.update(
        category for event in frozen_events() for category in event.secondary_categories
    )
    assert observed == CATEGORIES


def test_terra_aliases_are_frozen() -> None:
    event = next(
        item for item in frozen_events() if item.event_id == "TERRA_UST_LUNA_COLLAPSE_2022"
    )
    assert event.direct_symbols == ("LUNA", "UST")
    assert event.symbol_aliases == (
        ("LUNC", "LUNA"),
        ("USTC", "UST"),
    )
    assert event.persistence_mode == "TERMINAL_IMPAIRMENT"


def test_ftt_terminal_interval_reaches_research_boundary() -> None:
    event = next(item for item in frozen_events() if item.event_id == "FTX_FTT_COLLAPSE_2022")
    assert event.direct_symbols == ("FTT",)
    assert event.association_end_utc == RESEARCH_WINDOW_END


def test_usdc_event_is_acute_and_recovered() -> None:
    event = next(item for item in frozen_events() if item.event_id == "USDC_SVB_DEPEG_2023")
    assert event.persistence_mode == "ACUTE_RECOVERED"
    assert event.association_end_utc == "2023-03-14T00:00:00Z"


def test_every_event_has_independent_publishers() -> None:
    sources = {item.source_id: item for item in frozen_sources()}
    for event in frozen_events():
        publishers = {sources[source_id].publisher for source_id in event.source_ids}
        assert len(publishers) >= 2


def test_all_urls_use_https() -> None:
    assert all(source.url.startswith("https://") for source in frozen_sources())


def test_join_contract_preserves_all_trades() -> None:
    contract = join_contract()
    assert contract["trade_rows_changed"] is False
    assert contract["trade_rows_excluded"] is False
    assert contract["outcome_based_event_selection_allowed"] is False
    assert contract["causality_claim_allowed"] is False


def test_rows_are_deterministic() -> None:
    assert event_rows() == event_rows()
    assert source_rows() == source_rows()
    assert join_contract_rows() == join_contract_rows()


def test_registry_fingerprint_is_stable_sha256() -> None:
    fingerprint = registry_fingerprint()
    assert len(fingerprint) == 64
    int(fingerprint, 16)


def test_decision_authorizes_diagnostic_only() -> None:
    decision = decision_record(upstream_valid=True)
    assert decision["decision"] == DECISION_FROZEN
    assert decision["d5c1_tail_label_join_diagnostic_authorized"] is True
    assert decision["trade_join_executed"] is False
    assert decision["production_change_authorized"] is False
    assert decision["trade_logic_changed"] is False


def test_invalid_upstream_blocks_decision() -> None:
    decision = decision_record(upstream_valid=False)
    assert decision["decision"] == DECISION_BLOCKED
    assert decision["d5c1_tail_label_join_diagnostic_authorized"] is False


def test_duplicate_source_publisher_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import spotbot.research.rd04_external_tail_event_source_freeze as module

    sources = list(module.frozen_sources())
    sources[1] = replace(
        sources[1],
        publisher=sources[0].publisher,
    )
    monkeypatch.setattr(
        module,
        "frozen_sources",
        lambda: tuple(sources),
    )
    with pytest.raises(
        TailEventSourceFreezeError,
        match="independent publishers",
    ):
        module.validate_registry()


def test_non_https_source_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import spotbot.research.rd04_external_tail_event_source_freeze as module

    sources = list(module.frozen_sources())
    sources[0] = replace(
        sources[0],
        url="http://example.invalid/source",
    )
    monkeypatch.setattr(
        module,
        "frozen_sources",
        lambda: tuple(sources),
    )
    with pytest.raises(
        TailEventSourceFreezeError,
        match="HTTPS",
    ):
        module.validate_registry()


def test_validate_report_accepts_safe_freeze() -> None:
    report = {
        "status": "COMPLETE",
        "research_stage": "RD04-D5C0",
        "registry_fingerprint": registry_fingerprint(),
        "decision": decision_record(upstream_valid=True),
        "safety": {
            "market_data_read": False,
            "trade_ledger_read": False,
            "trade_join_executed": False,
            "trade_outcomes_read": False,
            "outcome_based_event_selection_used": False,
            "symbol_exclusion_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
        },
    }
    validate_report(report)


def test_validate_report_rejects_trade_join() -> None:
    report = {
        "status": "COMPLETE",
        "research_stage": "RD04-D5C0",
        "registry_fingerprint": registry_fingerprint(),
        "decision": decision_record(upstream_valid=True),
        "safety": {
            "market_data_read": False,
            "trade_ledger_read": False,
            "trade_join_executed": True,
            "trade_outcomes_read": False,
            "outcome_based_event_selection_used": False,
            "symbol_exclusion_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
        },
    }
    with pytest.raises(TailEventSourceFreezeError):
        validate_report(report)
