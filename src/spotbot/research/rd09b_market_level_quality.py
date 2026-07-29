"""Quality gates for RD09B v2 daily native-chain pilot results."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

from spotbot.research.rd09b_market_level_protocol import market_level_score

REQUIRED_COMMON_FAMILIES: Final = {"TRANSACTION_ACTIVITY", "FEES_OR_BLOCK_PRODUCTION"}


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
        )


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


def passing_namespace(
    month_passes: tuple[bool, ...],
    metric_families: set[str],
    causal_grade: str,
) -> bool:
    return (
        len(month_passes) == 3
        and all(month_passes)
        and metric_families >= REQUIRED_COMMON_FAMILIES
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
