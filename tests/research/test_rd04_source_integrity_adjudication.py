from __future__ import annotations

from spotbot.research.rd04_source_integrity_adjudication import (
    DECISION_BLOCKED,
    DECISION_MORE_DATA,
    DECISION_READY,
    adjudicate_attempt,
    adjudicate_symbol,
    build_adjudication_decision,
    deterministic_unavailable_error,
)


def test_deterministic_400100_is_unavailable_not_corruption() -> None:
    error = "uta:2022-01-01:PitDataExpansionError:KuCoin response code is not successful: 400100"
    assert deterministic_unavailable_error(error)
    result = adjudicate_attempt(
        {"venue_pair": "MATIC-USDT", "status": "SOURCE_REQUEST_INCOMPLETE", "error": error}
    )
    assert result["classification"] == "VENUE_PAIR_UNAVAILABLE"
    assert result["blocking"] is False


def test_transient_source_error_remains_blocking() -> None:
    result = adjudicate_attempt(
        {
            "venue_pair": "ABC-USDT",
            "status": "SOURCE_REQUEST_INCOMPLETE",
            "error": "TimeoutError:timed out",
        }
    )
    assert result["classification"] == "UNRESOLVED_SOURCE_ERROR"
    assert result["blocking"] is True


def test_complete_symbol_is_usable() -> None:
    result = adjudicate_symbol(
        {"canonical_symbol": "CRO", "status": "COMPLETE", "row_count": 8766},
        [{"venue_pair": "CRO-USDT", "status": "ACQUIRED", "error": ""}],
    )
    assert result["resolution"] == "USABLE_COMPLETE"
    assert result["blocking_integrity_failure"] is False
    assert result["recoverable_data"] is False


def test_usable_primary_with_unavailable_alias_is_recoverable() -> None:
    result = adjudicate_symbol(
        {"canonical_symbol": "BCH", "status": "SOURCE_REQUEST_INCOMPLETE", "row_count": 8766},
        [
            {"venue_pair": "BCH-USDT", "status": "ACQUIRED", "error": ""},
            {
                "venue_pair": "BCHABC-USDT",
                "status": "SOURCE_REQUEST_INCOMPLETE",
                "error": "KuCoin response code is not successful: 400100",
            },
        ],
    )
    assert result["resolution"] == "USABLE_SOURCE_RECOVERY_REQUIRED"
    assert result["blocking_integrity_failure"] is False
    assert result["recoverable_data"] is True
    assert result["usable_source_pairs"] == "BCH-USDT"


def test_permanently_unavailable_symbol_is_nonblocking() -> None:
    result = adjudicate_symbol(
        {"canonical_symbol": "LEO", "status": "SOURCE_REQUEST_INCOMPLETE", "row_count": 0},
        [
            {
                "venue_pair": "LEO-USDT",
                "status": "SOURCE_REQUEST_INCOMPLETE",
                "error": "KuCoin response code is not successful: 400100",
            }
        ],
    )
    assert result["resolution"] == "VENUE_UNAVAILABLE"
    assert result["blocking_integrity_failure"] is False


def test_invalid_alias_transition_is_true_integrity_failure() -> None:
    result = adjudicate_symbol(
        {
            "canonical_symbol": "TEST",
            "status": "INVALID_ALIAS_TRANSITION",
            "row_count": 100,
            "invalid_alias_transition_count": 1,
        },
        [{"venue_pair": "TEST-USDT", "status": "ACQUIRED", "error": ""}],
    )
    assert result["resolution"] == "TRUE_DATA_INTEGRITY_FAILURE"
    assert result["blocking_integrity_failure"] is True


def test_unknown_source_failure_blocks_zero_row_symbol() -> None:
    result = adjudicate_symbol(
        {"canonical_symbol": "TEST", "status": "SOURCE_REQUEST_INCOMPLETE", "row_count": 0},
        [
            {
                "venue_pair": "TEST-USDT",
                "status": "SOURCE_REQUEST_INCOMPLETE",
                "error": "HTTPError:503",
            }
        ],
    )
    assert result["resolution"] == "UNRESOLVED_SOURCE_ERROR"
    assert result["blocking_integrity_failure"] is True


def test_ready_decision_requires_all_snapshots_and_zero_blockers() -> None:
    decision = build_adjudication_decision(
        snapshot_count=157,
        complete_snapshot_count=157,
        minimum_selected_count=30,
        maximum_required_market_cap_rank=39,
        blocking_integrity_failure_count=0,
    )
    assert decision["decision"] == DECISION_READY
    assert decision["rd04_d1_pit_universe_replay_research_authorized"] is True


def test_true_integrity_failure_overrides_complete_snapshots() -> None:
    decision = build_adjudication_decision(
        snapshot_count=157,
        complete_snapshot_count=157,
        minimum_selected_count=30,
        maximum_required_market_cap_rank=39,
        blocking_integrity_failure_count=1,
    )
    assert decision["decision"] == DECISION_BLOCKED
    assert decision["rd04_d1_pit_universe_replay_research_authorized"] is False


def test_incomplete_snapshots_require_more_data() -> None:
    decision = build_adjudication_decision(
        snapshot_count=157,
        complete_snapshot_count=156,
        minimum_selected_count=29,
        maximum_required_market_cap_rank=50,
        blocking_integrity_failure_count=0,
    )
    assert decision["decision"] == DECISION_MORE_DATA
    assert decision["additional_source_expansion_research_authorized"] is True
