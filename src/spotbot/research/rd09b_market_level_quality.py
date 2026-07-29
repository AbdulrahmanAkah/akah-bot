"""Quality gates for RD09B v2 daily native-chain pilot results."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from spotbot.research.rd09b_market_level_protocol import (
    METRIC_FIELDS,
    market_level_score,
)

REQUIRED_COMMON_FAMILIES: Final = {"TRANSACTION_ACTIVITY", "FEES_OR_BLOCK_PRODUCTION"}
TRANSACTION_FIELDS: Final = {"successful_transaction_count", "native_transfer_count"}
ADDRESS_FIELDS: Final = {
    "unique_sending_addresses",
    "unique_receiving_addresses",
    "unique_active_addresses",
}


@dataclass(frozen=True)
class MonthQuality:
    expected_days: int
    actual_distinct_days: int
    duplicate_days: int
    missing_days: int
    largest_missing_run: int
    impossible_negative_count: int
    unexpected_zero_block_days: int
    active_address_inconsistencies: int
    nonfinite_count: int = 0

    @property
    def coverage(self) -> float:
        return self.actual_distinct_days / self.expected_days

    @property
    def passed(self) -> bool:
        return (
            self.coverage >= 0.90
            and self.duplicate_days == 0
            and self.largest_missing_run <= 3
            and self.impossible_negative_count == 0
            and self.unexpected_zero_block_days == 0
            and self.active_address_inconsistencies == 0
            and self.nonfinite_count == 0
        )


@dataclass(frozen=True)
class MonthDiagnostics:
    quality: MonthQuality
    null_count_by_metric: dict[str, int]
    negative_transaction_count: int
    negative_address_count: int
    negative_fee_count: int
    negative_block_count: int
    first_day: str
    last_day: str
    observed_metrics: frozenset[str]


def expected_days(start: str, end_exclusive: str) -> tuple[date, ...]:
    first = date.fromisoformat(start[:10])
    end = date.fromisoformat(end_exclusive[:10])
    return tuple(first + timedelta(days=offset) for offset in range((end - first).days))


def largest_missing_run(expected: tuple[date, ...], observed: set[date]) -> int:
    largest = 0
    current = 0
    for day in expected:
        if day in observed:
            current = 0
        else:
            current += 1
            largest = max(largest, current)
    return largest


def validate_numeric(value: object, *, allow_null: bool) -> bool:
    if value is None:
        return allow_null
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value)) and float(value) >= 0


def _parse_optional_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean metric value is invalid")
    if not isinstance(value, (str, int, float)):
        raise ValueError("metric value is not numeric")
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError("metric value is not numeric") from exc
    return number


def evaluate_month_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    start: str,
    end_exclusive: str,
) -> MonthDiagnostics:
    expected = expected_days(start, end_exclusive)
    expected_set = set(expected)
    observed_days: list[date] = []
    null_counts = {metric: 0 for metric in METRIC_FIELDS}
    observed_metrics: set[str] = set()
    nonfinite = 0
    negative_transactions = 0
    negative_addresses = 0
    negative_fees = 0
    negative_blocks = 0
    zero_block_days = 0
    active_inconsistencies = 0

    for row in rows:
        raw_day = row.get("day")
        if raw_day is None or str(raw_day).strip() == "":
            raise ValueError("pilot row lacks day")
        day = date.fromisoformat(str(raw_day)[:10])
        if day not in expected_set:
            raise ValueError("pilot row day is outside registered month")
        observed_days.append(day)

        parsed: dict[str, float | None] = {}
        for metric in METRIC_FIELDS:
            number = _parse_optional_number(row.get(metric))
            parsed[metric] = number
            if number is None:
                null_counts[metric] += 1
                continue
            observed_metrics.add(metric)
            if not math.isfinite(number):
                nonfinite += 1
                continue
            if number < 0:
                if metric in TRANSACTION_FIELDS:
                    negative_transactions += 1
                elif metric in ADDRESS_FIELDS:
                    negative_addresses += 1
                elif metric == "native_fees_paid":
                    negative_fees += 1
                elif metric == "block_count":
                    negative_blocks += 1

        block_count = parsed["block_count"]
        if block_count is not None and math.isfinite(block_count) and block_count == 0:
            zero_block_days += 1

        senders = parsed["unique_sending_addresses"]
        receivers = parsed["unique_receiving_addresses"]
        active = parsed["unique_active_addresses"]
        if (
            senders is not None
            and receivers is not None
            and active is not None
            and all(math.isfinite(value) for value in (senders, receivers, active))
            and active > senders + receivers
        ):
            active_inconsistencies += 1

    observed_set = set(observed_days)
    duplicate_days = len(observed_days) - len(observed_set)
    missing_days = len(expected_set - observed_set)
    negative_total = negative_transactions + negative_addresses + negative_fees + negative_blocks
    quality = MonthQuality(
        expected_days=len(expected),
        actual_distinct_days=len(observed_set),
        duplicate_days=duplicate_days,
        missing_days=missing_days,
        largest_missing_run=largest_missing_run(expected, observed_set),
        impossible_negative_count=negative_total,
        unexpected_zero_block_days=zero_block_days,
        active_address_inconsistencies=active_inconsistencies,
        nonfinite_count=nonfinite,
    )
    ordered_days = sorted(observed_set)
    return MonthDiagnostics(
        quality=quality,
        null_count_by_metric=null_counts,
        negative_transaction_count=negative_transactions,
        negative_address_count=negative_addresses,
        negative_fee_count=negative_fees,
        negative_block_count=negative_blocks,
        first_day=ordered_days[0].isoformat() if ordered_days else "",
        last_day=ordered_days[-1].isoformat() if ordered_days else "",
        observed_metrics=frozenset(observed_metrics),
    )


def metric_families(observed_metrics: set[str] | frozenset[str]) -> set[str]:
    families: set[str] = set()
    if observed_metrics & TRANSACTION_FIELDS:
        families.add("TRANSACTION_ACTIVITY")
    if observed_metrics & {"native_fees_paid", "block_count"}:
        families.add("FEES_OR_BLOCK_PRODUCTION")
    return families


def passing_namespace(
    month_passes: tuple[bool, ...],
    metric_families_available: set[str],
    causal_grade: str,
) -> bool:
    return (
        len(month_passes) == 3
        and all(month_passes)
        and metric_families_available >= REQUIRED_COMMON_FAMILIES
        and causal_grade == "B_RECONSTRUCTABLE_FROM_RAW_CHAIN"
    )


def feasibility_decision(
    *,
    passing_namespace_count: int,
    common_family_namespace_count: int,
    zero_paid_spend: bool,
    conflicts: int,
) -> tuple[str, int, bool]:
    score = market_level_score(
        passing_namespace_count=passing_namespace_count,
        causal_integrity_passed=passing_namespace_count > 0,
        reproducibility_passed=passing_namespace_count > 0,
        independent_information=True,
        zero_paid_spend=zero_paid_spend,
        daily_frequency_suitable=passing_namespace_count > 0,
    )
    gate = (
        passing_namespace_count >= 4
        and common_family_namespace_count >= 4
        and zero_paid_spend
        and conflicts == 0
        and score >= 70
    )
    if gate:
        return "RD09B_DUNE_MARKET_LEVEL_FEASIBILITY_CONFIRMED", score, True
    return "RD09B_DUNE_MARKET_LEVEL_FEASIBILITY_INSUFFICIENT", score, False
