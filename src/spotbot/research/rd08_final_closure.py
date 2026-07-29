"""Frozen adjudication helpers for the final RD08 market-data closure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

FINAL_DECISION: Final = "RD08_MARKET_DATA_RESEARCH_SEQUENCE_COMPLETE_NO_EDGE_CONFIRMED"
NEXT_STAGE: Final = "RD09_NEW_INFORMATION_SOURCE_SELECTION_AND_FEASIBILITY"
REGISTERED_THRESHOLD: Final = 0.05


@dataclass(frozen=True)
class TrialSequence:
    rd05: int = 33
    rd06: int = 15
    rd07: int = 14
    rd08: int = 14

    @property
    def total(self) -> int:
        return self.rd05 + self.rd06 + self.rd07 + self.rd08


def classify_near_miss(block_7_bh: float, block_28_bh: float) -> str:
    """Preserve the registered family and threshold without selective inference."""

    if block_7_bh <= REGISTERED_THRESHOLD and block_28_bh <= REGISTERED_THRESHOLD:
        return "REGISTERED_GATE_PASSED"
    if min(block_7_bh, block_28_bh) <= 0.06:
        return "UNCONFIRMED_NEAR_MISS"
    return "NOT_CONFIRMED"
