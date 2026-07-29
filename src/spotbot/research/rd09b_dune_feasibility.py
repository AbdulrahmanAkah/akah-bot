"""Frozen RD09B zero-spend feasibility contracts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

SELECTION_WEIGHTS: Final[dict[str, int]] = {
    "causal_integrity": 30,
    "pit_coverage": 25,
    "reproducibility": 15,
    "economic_information_independence": 15,
    "cost_licensing_suitability": 10,
    "native_frequency_latency_suitability": 5,
}
PILOT_RANGES: Final[tuple[tuple[str, str], ...]] = (
    ("2022-03-01", "2022-04-01"),
    ("2023-03-01", "2023-04-01"),
    ("2024-03-01", "2024-04-01"),
)
MAX_NAMESPACES: Final = 4


class EntityClass(StrEnum):
    NATIVE_CHAIN_ASSET = "NATIVE_CHAIN_ASSET"
    EVM_CONTRACT_TOKEN = "EVM_CONTRACT_TOKEN"
    NON_EVM_TOKEN = "NON_EVM_TOKEN"
    PROTOCOL_ENTITY = "PROTOCOL_ENTITY"
    UNSUPPORTED_CHAIN_OR_ENTITY = "UNSUPPORTED_CHAIN_OR_ENTITY"


@dataclass(frozen=True)
class NamespaceCandidate:
    namespace: str
    mapped_pit_asset_count: int
    raw_catalog_supported: bool


@dataclass(frozen=True)
class BroadCoverage:
    causally_mapped_assets: int
    overall_panel_row_coverage: float
    median_decision_share: float
    fold_coverages: tuple[float, ...]
    fold_median_usable_symbols: tuple[int, ...]
    silent_exclusions: int

    @property
    def passed(self) -> bool:
        return (
            self.causally_mapped_assets >= 20
            and self.overall_panel_row_coverage >= 0.70
            and self.median_decision_share >= 0.70
            and all(value >= 0.60 for value in self.fold_coverages)
            and all(value >= 15 for value in self.fold_median_usable_symbols)
            and self.silent_exclusions == 0
        )


@dataclass(frozen=True)
class SectorCoverage:
    causally_mapped_assets: int
    panel_row_coverage: float
    fold_coverages: tuple[float, ...]
    metric_family_count: int

    @property
    def passed(self) -> bool:
        return (
            self.causally_mapped_assets >= 15
            and self.panel_row_coverage >= 0.75
            and all(value >= 0.65 for value in self.fold_coverages)
            and self.metric_family_count >= 2
        )


def credit_budget(credits_included: float, credits_used: float) -> float:
    if credits_included < 0 or credits_used < 0:
        raise ValueError("credits cannot be negative")
    remaining = max(0.0, credits_included - credits_used)
    return min(500.0, 0.20 * credits_included, remaining)


def rank_namespaces(candidates: Iterable[NamespaceCandidate]) -> list[NamespaceCandidate]:
    supported = [candidate for candidate in candidates if candidate.raw_catalog_supported]
    return sorted(
        supported,
        key=lambda item: (-item.mapped_pit_asset_count, item.namespace),
    )[:MAX_NAMESPACES]


def validate_pilot_range(start: str, end_exclusive: str) -> None:
    if (start, end_exclusive) not in PILOT_RANGES:
        raise ValueError("unregistered pilot range")
    if end_exclusive > "2024-12-31":
        raise ValueError("pilot request crosses research lock")


def validate_weights() -> None:
    if sum(SELECTION_WEIGHTS.values()) != 100:
        raise RuntimeError("RD09 selection weights changed")
