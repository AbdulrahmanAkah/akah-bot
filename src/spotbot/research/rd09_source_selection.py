"""Typed, non-predictive source-selection contracts for RD09."""

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
SELECTION_THRESHOLD: Final = 70
PILOT_RANGES: Final[tuple[tuple[str, str], ...]] = (
    ("2022-03-01", "2022-03-31"),
    ("2023-03-01", "2023-03-31"),
    ("2024-03-01", "2024-03-31"),
)
RESEARCH_END: Final = "2024-12-31"


class CausalGrade(StrEnum):
    A_RAW_IMMUTABLE_EVENT_TIME = "A_RAW_IMMUTABLE_EVENT_TIME"
    B_RECONSTRUCTABLE_FROM_RAW_CHAIN = "B_RECONSTRUCTABLE_FROM_RAW_CHAIN"
    C_DERIVED_WITH_KNOWN_LATENCY_AND_REVISION_POLICY = (
        "C_DERIVED_WITH_KNOWN_LATENCY_AND_REVISION_POLICY"
    )
    D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION = (
        "D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION"
    )
    E_NOT_CAUSALLY_USABLE = "E_NOT_CAUSALLY_USABLE"


class CostClass(StrEnum):
    FREE = "FREE"
    FREE_WITH_RATE_LIMIT = "FREE_WITH_RATE_LIMIT"
    CREDENTIAL_REQUIRED_NO_KNOWN_CHARGE = "CREDENTIAL_REQUIRED_NO_KNOWN_CHARGE"
    PAID_APPROVAL_REQUIRED = "PAID_APPROVAL_REQUIRED"
    COST_UNKNOWN = "COST_UNKNOWN"


class CoverageStatus(StrEnum):
    MAPPED_AND_CAUSAL = "MAPPED_AND_CAUSAL"
    MAPPED_DIAGNOSTIC_ONLY = "MAPPED_DIAGNOSTIC_ONLY"
    MAPPED_BUT_PAID = "MAPPED_BUT_PAID"
    UNMAPPED = "UNMAPPED"
    NO_HISTORICAL_DATA = "NO_HISTORICAL_DATA"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    UNKNOWN_PUBLICATION_TIME = "UNKNOWN_PUBLICATION_TIME"


@dataclass(frozen=True)
class SelectionScore:
    source_id: str
    causal_integrity: int
    pit_coverage: int
    reproducibility: int
    economic_information_independence: int
    cost_licensing_suitability: int
    native_frequency_latency_suitability: int
    causal_grade: CausalGrade
    coverage_gate_passed: bool
    unresolved_critical_mapping_conflicts: int
    paid_purchase_required: bool

    def dimensions(self) -> dict[str, int]:
        return {
            "causal_integrity": self.causal_integrity,
            "pit_coverage": self.pit_coverage,
            "reproducibility": self.reproducibility,
            "economic_information_independence": self.economic_information_independence,
            "cost_licensing_suitability": self.cost_licensing_suitability,
            "native_frequency_latency_suitability": self.native_frequency_latency_suitability,
        }

    @property
    def total(self) -> int:
        return sum(self.dimensions().values())

    @property
    def selected(self) -> bool:
        return (
            self.total >= SELECTION_THRESHOLD
            and self.causal_grade
            in {
                CausalGrade.A_RAW_IMMUTABLE_EVENT_TIME,
                CausalGrade.B_RECONSTRUCTABLE_FROM_RAW_CHAIN,
                CausalGrade.C_DERIVED_WITH_KNOWN_LATENCY_AND_REVISION_POLICY,
            }
            and self.coverage_gate_passed
            and self.unresolved_critical_mapping_conflicts == 0
            and not self.paid_purchase_required
        )

    def validate(self) -> None:
        for name, value in self.dimensions().items():
            maximum = SELECTION_WEIGHTS[name]
            if value < 0 or value > maximum:
                raise ValueError(f"{name} must be between zero and {maximum}")


@dataclass(frozen=True)
class AssetCoverage:
    total_panel_rows: int
    causal_panel_rows: int
    median_decision_share: float
    fold_coverages: tuple[float, ...]
    causal_symbol_count: int
    median_usable_symbols_by_fold: tuple[int, ...]

    @property
    def gate_passed(self) -> bool:
        return (
            self.total_panel_rows > 0
            and self.causal_panel_rows / self.total_panel_rows >= 0.70
            and self.median_decision_share >= 0.70
            and all(value >= 0.60 for value in self.fold_coverages)
            and self.causal_symbol_count >= 20
            and all(value >= 15 for value in self.median_usable_symbols_by_fold)
        )


def validate_selection_weights() -> None:
    if sum(SELECTION_WEIGHTS.values()) != 100:
        raise RuntimeError("selection weights must sum to 100")


def validate_pilot_range(start: str, end: str) -> None:
    if (start, end) not in PILOT_RANGES:
        raise ValueError("pilot range is not preregistered")
    if end > RESEARCH_END:
        raise ValueError("pilot range exceeds research lock")


def unknown_publication_grade(
    *,
    event_time_available: bool,
    publication_time_available: bool,
    raw_data_reconstructable: bool,
) -> CausalGrade:
    if raw_data_reconstructable and event_time_available:
        return CausalGrade.B_RECONSTRUCTABLE_FROM_RAW_CHAIN
    if not publication_time_available:
        return CausalGrade.D_DERIVED_HISTORICAL_SERIES_WITH_UNKNOWN_REVISION
    return CausalGrade.E_NOT_CAUSALLY_USABLE


def account_for_all_symbols(expected: Iterable[str], observed: Iterable[str]) -> None:
    expected_set = set(expected)
    observed_list = list(observed)
    if len(observed_list) != len(set(observed_list)):
        raise ValueError("duplicate economic-entity mapping")
    if expected_set != set(observed_list):
        missing = sorted(expected_set - set(observed_list))
        extra = sorted(set(observed_list) - expected_set)
        raise ValueError(f"symbol mapping mismatch missing={missing} extra={extra}")
