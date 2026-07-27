"""RD04-D0C source-attempt adjudication and replay-readiness gates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

SCHEMA_VERSION: Final = "ams-rd04-d0c-source-integrity-adjudication-v1"
EXPECTED_SNAPSHOTS: Final = 157
TARGET_UNIVERSE_SIZE: Final = 30

DECISION_READY: Final = "PIT_UNIVERSE_REPLAY_READY"
DECISION_MORE_DATA: Final = "PIT_UNIVERSE_SOURCE_EXPANSION_REQUIRED"
DECISION_BLOCKED: Final = "BLOCKED_BY_TRUE_DATA_INTEGRITY"

USABLE_ATTEMPT_STATUSES: Final[frozenset[str]] = frozenset({"ACQUIRED", "CACHE_HIT"})
UNAVAILABLE_ATTEMPT_STATUSES: Final[frozenset[str]] = frozenset(
    {"NO_KUCOIN_HISTORY", "VENUE_PAIR_UNAVAILABLE"}
)
TRUE_INTEGRITY_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "INCOMPLETE",
        "INVALID_ALIAS_TRANSITION",
        "INVALID_DATA",
        "CACHE_INTEGRITY_FAILURE",
    }
)
PERMANENT_UNAVAILABLE_SIGNATURES: Final[tuple[str, ...]] = (
    "kucoin response code is not successful: 400100",
    "kucoin kline data must be a list",
)


def error_segments(error: str) -> tuple[str, ...]:
    """Split one compact attempt error into normalized non-empty segments."""

    return tuple(part.strip() for part in str(error).split("|") if part.strip())


def deterministic_unavailable_error(error: str) -> bool:
    """Return whether every observed failure is a permanent unavailable-pair signal."""

    segments = error_segments(error)
    if not segments:
        return False
    return all(
        any(signature in segment.lower() for signature in PERMANENT_UNAVAILABLE_SIGNATURES)
        for segment in segments
    )


def adjudicate_attempt(attempt: Mapping[str, object]) -> dict[str, object]:
    """Classify one venue-pair attempt without treating pair absence as data corruption."""

    status = str(attempt.get("status", "")).strip().upper()
    error = str(attempt.get("error", ""))
    deterministic_absence = (
        status == "SOURCE_REQUEST_INCOMPLETE" and deterministic_unavailable_error(error)
    )
    unavailable_attempt = status in UNAVAILABLE_ATTEMPT_STATUSES or deterministic_absence
    if status in USABLE_ATTEMPT_STATUSES:
        classification = "USABLE_SOURCE"
        blocking = False
    elif unavailable_attempt:
        classification = "VENUE_PAIR_UNAVAILABLE"
        blocking = False
    elif status == "SOURCE_REQUEST_INCOMPLETE":
        classification = "UNRESOLVED_SOURCE_ERROR"
        blocking = True
    else:
        classification = "UNRESOLVED_ATTEMPT_STATUS"
        blocking = True
    return {
        "venue_pair": str(attempt.get("venue_pair", "")),
        "attempt_status": status,
        "classification": classification,
        "blocking": blocking,
        "error": error,
    }


def _integer(record: Mapping[str, object], key: str) -> int:
    value = record.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def adjudicate_symbol(
    symbol_record: Mapping[str, object],
    attempts: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Resolve whether one symbol is usable, unavailable, recoverable, or truly unsafe."""

    symbol = str(symbol_record.get("canonical_symbol", "")).strip().upper()
    status = str(symbol_record.get("status", "")).strip().upper()
    row_count = _integer(symbol_record, "row_count")
    integrity_counter_keys = (
        "duplicate_count",
        "invalid_price_count",
        "invalid_ohlc_count",
        "invalid_volume_count",
        "invalid_duration_count",
        "misaligned_count",
        "invalid_alias_transition_count",
    )
    integrity_counter_total = sum(_integer(symbol_record, key) for key in integrity_counter_keys)
    attempt_results = [adjudicate_attempt(attempt) for attempt in attempts]
    usable_pairs = sorted(
        str(result["venue_pair"])
        for result in attempt_results
        if result["classification"] == "USABLE_SOURCE"
    )
    unavailable_pairs = sorted(
        str(result["venue_pair"])
        for result in attempt_results
        if result["classification"] == "VENUE_PAIR_UNAVAILABLE"
    )
    unresolved_pairs = sorted(
        str(result["venue_pair"]) for result in attempt_results if bool(result["blocking"])
    )

    true_integrity_failure = status in TRUE_INTEGRITY_STATUSES or integrity_counter_total > 0
    recoverable_data = False
    if true_integrity_failure:
        resolution = "TRUE_DATA_INTEGRITY_FAILURE"
        blocking = True
    elif row_count > 0 and usable_pairs and not unresolved_pairs:
        recoverable_data = status != "COMPLETE"
        resolution = "USABLE_SOURCE_RECOVERY_REQUIRED" if recoverable_data else "USABLE_COMPLETE"
        blocking = False
    elif row_count == 0 and not unresolved_pairs:
        resolution = "VENUE_UNAVAILABLE"
        blocking = False
    else:
        resolution = "UNRESOLVED_SOURCE_ERROR"
        blocking = True

    return {
        "canonical_symbol": symbol,
        "d0b_status": status,
        "row_count": row_count,
        "resolution": resolution,
        "blocking_integrity_failure": blocking,
        "recoverable_data": recoverable_data,
        "usable_source_pairs": ",".join(usable_pairs),
        "unavailable_source_pairs": ",".join(unavailable_pairs),
        "unresolved_source_pairs": ",".join(unresolved_pairs),
        "true_integrity_counter_total": integrity_counter_total,
    }


def build_adjudication_decision(
    *,
    snapshot_count: int,
    complete_snapshot_count: int,
    minimum_selected_count: int,
    maximum_required_market_cap_rank: int,
    blocking_integrity_failure_count: int,
) -> dict[str, object]:
    """Authorize replay only after true integrity failures are zero and all snapshots fill."""

    snapshots_complete = (
        snapshot_count == EXPECTED_SNAPSHOTS
        and complete_snapshot_count == snapshot_count
        and minimum_selected_count == TARGET_UNIVERSE_SIZE
    )
    if blocking_integrity_failure_count > 0:
        decision = DECISION_BLOCKED
        reason = "TRUE_ACQUIRED_DATA_OR_UNRESOLVED_SOURCE_INTEGRITY_FAILURE"
    elif snapshots_complete:
        decision = DECISION_READY
        reason = "ALL_WEEKLY_TOP_30_DATASETS_COMPLETE_AFTER_SOURCE_ADJUDICATION"
    else:
        decision = DECISION_MORE_DATA
        reason = "ADJUDICATED_KUCOIN_HISTORY_DID_NOT_FILL_EVERY_WEEKLY_TOP_30"
    return {
        "decision": decision,
        "reason": reason,
        "snapshot_count": snapshot_count,
        "complete_snapshot_count": complete_snapshot_count,
        "minimum_selected_count": minimum_selected_count,
        "maximum_required_market_cap_rank": maximum_required_market_cap_rank,
        "blocking_integrity_failure_count": blocking_integrity_failure_count,
        "rd04_d1_pit_universe_replay_research_authorized": decision == DECISION_READY,
        "additional_source_expansion_research_authorized": decision == DECISION_MORE_DATA,
        "universe_change_authorized": False,
    }
