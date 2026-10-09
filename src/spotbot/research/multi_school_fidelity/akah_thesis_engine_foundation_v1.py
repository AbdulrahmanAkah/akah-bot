"""Research-only integrated authority; not production. See source provenance manifest."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

CONTRACT_ID = "AKAH_MULTI_SCHOOL_THESIS_ENGINE_FOUNDATION_V1"
CAPITAL_CONTRACT_ID = "AKAH_CURRENT_MTM_THESIS_RISK_V1"
ROUTER_ID = "AKAH_STRUCTURAL_ROUTER_V1"
SELECTOR_ID = "AKAH_SHARED_FEASIBILITY_FIFO_LIQUIDITY_V1"

INITIAL_EQUITY = 100_000.0
NEW_THESIS_RISK_FRACTION = 0.005
MAX_TOTAL_OPEN_STOP_RISK_FRACTION = 0.025
MAX_GROSS_MTM_FRACTION = 0.90
MAX_ASSET_MTM_FRACTION = 0.18
MAX_DISTINCT_OPEN_ASSETS = 5
CAPACITY_PARTICIPATION_FRACTION = 0.005


class EvidenceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class ParentEdgeType(StrEnum):
    HISTORICAL_PREREQUISITE = "HISTORICAL_PREREQUISITE"
    LIVE_REQUIREMENT = "LIVE_REQUIREMENT"
    MANAGEMENT_DEPENDENCY = "MANAGEMENT_DEPENDENCY"


@dataclass(frozen=True)
class ParentEdge:
    parent_event_id: str
    edge_type: ParentEdgeType


@dataclass
class EvidenceRecord:
    event_id: str
    evidence_kind: str
    structure_id: str
    observed_at: Any
    available_at: Any
    source_rule_hash: str
    valid_until: Any | None = None
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    parent_edges: tuple[ParentEdge, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_live(self, now: Any, parent_status: dict[str, EvidenceStatus] | None = None) -> bool:
        if now < self.available_at:
            return False
        if self.status is not EvidenceStatus.ACTIVE:
            return False
        if self.valid_until is not None and now >= self.valid_until:
            return False
        if self.parent_edges:
            parent_status = parent_status or {}
            for edge in self.parent_edges:
                if (
                    edge.edge_type is ParentEdgeType.LIVE_REQUIREMENT
                    and parent_status.get(edge.parent_event_id) is not EvidenceStatus.ACTIVE
                ):
                    return False
        return True

    def invalidate(self):
        self.status = EvidenceStatus.INVALIDATED

    def expire(self):
        self.status = EvidenceStatus.EXPIRED

    def consume(self):
        self.status = EvidenceStatus.CONSUMED


@dataclass(frozen=True)
class ThesisRecord:
    thesis_id: str
    owner_grammar: str
    owner_structure_id: str
    pair: str
    ready_at: Any
    entry_reason: str
    invalidation_rule: str
    management_rule: str
    risk_budget: float
    supporting_evidence_ids: tuple[str, ...]
    capacity_fraction: float
    action_class: str = "NEW_ENTRY"
    funded_ready: bool = False

    def canonical_identity(self) -> str:
        return "|".join((self.owner_grammar, self.owner_structure_id, self.pair, self.thesis_id))


@dataclass
class CampaignRecord:
    campaign_id: str
    thesis_id: str
    pair: str
    initial_risk_budget: float
    committed_risk: float = 0.0
    add_count: int = 0

    def can_commit(self, entry_risk: float, current_equity: float, stage_allowance: float) -> bool:
        if entry_risk <= 0 or current_equity <= 0:
            return False
        return (
            self.committed_risk + entry_risk <= self.initial_risk_budget + 1e-12
            and self.committed_risk + entry_risk
            <= NEW_THESIS_RISK_FRACTION * current_equity + 1e-12
            and entry_risk <= stage_allowance + 1e-12
        )

    def commit(
        self, entry_risk: float, current_equity: float, stage_allowance: float, *, is_add=False
    ):
        if is_add and self.add_count >= 1:
            raise ValueError("MAXIMUM_ONE_STAGED_ADD")
        if not self.can_commit(entry_risk, current_equity, stage_allowance):
            raise ValueError("CAMPAIGN_B0_EXCEEDED")
        self.committed_risk += entry_risk
        self.add_count += int(is_add)


@dataclass(frozen=True)
class PositionMark:
    pair: str
    quantity: float
    mark: float
    protective_stop: float
    exit_cost_fraction: float

    @property
    def current_market_value(self):
        return self.quantity * self.mark

    @property
    def open_stop_risk(self):
        return max(
            0.0,
            self.quantity * self.mark
            - self.quantity * self.protective_stop * (1.0 - self.exit_cost_fraction),
        )


def equity(cash: float, positions: Sequence[PositionMark]) -> float:
    return float(cash + sum(p.current_market_value for p in positions))


def gross_mtm(positions: Sequence[PositionMark]) -> float:
    return float(sum(p.current_market_value for p in positions))


def asset_mtm(pair: str, positions: Sequence[PositionMark]) -> float:
    return float(sum(p.current_market_value for p in positions if p.pair == pair))


def portfolio_open_stop_risk(positions: Sequence[PositionMark]) -> float:
    return float(sum(p.open_stop_risk for p in positions))


def entry_risk(
    quantity: float,
    entry_price: float,
    stop_price: float,
    entry_cost_fraction: float,
    exit_cost_fraction: float,
) -> float:
    if min(quantity, entry_price) <= 0 or stop_price < 0:
        return 0.0
    return quantity * (
        entry_price * (1.0 + entry_cost_fraction) - stop_price * (1.0 - exit_cost_fraction)
    )


def new_thesis_budget(current_equity: float) -> float:
    return NEW_THESIS_RISK_FRACTION * current_equity


def selector_digest(t: ThesisRecord) -> str:
    return hashlib.sha256(f"{SELECTOR_ID}|{t.canonical_identity()}".encode()).hexdigest()


def selector_key(t: ThesisRecord):
    return (
        0 if t.action_class == "ADD" else 1,
        t.ready_at,
        -float(t.capacity_fraction),
        selector_digest(t),
    )


def order_eligible_theses(theses: Iterable[ThesisRecord]) -> list[ThesisRecord]:
    return sorted(
        [t for t in theses if t.funded_ready and t.capacity_fraction > 0], key=selector_key
    )


class Direction(StrEnum):
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DOWN = "DOWN"
    BALANCED = "BALANCED"


class StructuralPhase(StrEnum):
    UNKNOWN = "UNKNOWN"
    BASE_CANDIDATE = "BASE_CANDIDATE"
    MARKUP = "MARKUP"
    MARKDOWN = "MARKDOWN"
    DISTRIBUTION_RISK = "DISTRIBUTION_RISK"
    REACCUMULATION_CANDIDATE = "REACCUMULATION_CANDIDATE"
    REDISTRIBUTION_RISK = "REDISTRIBUTION_RISK"


class Activity(StrEnum):
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"
    COMPRESSION = "COMPRESSION"
    EXPANSION = "EXPANSION"


@dataclass(frozen=True)
class RouterState:
    market_direction_1d: Direction
    asset_direction_1d: Direction
    structural_phase_4h: StructuralPhase
    activity_4h: Activity
    data_authority_valid: bool = True
    major_protected_structure_valid: bool = True


def long_entry_veto(s: RouterState):
    if not s.data_authority_valid:
        return True, "DATA_OR_AUTHORITY_FAILURE"
    if not s.major_protected_structure_valid:
        return True, "MAJOR_PROTECTED_STRUCTURE_INVALID"
    if s.market_direction_1d in {Direction.DOWN, Direction.UNKNOWN}:
        return True, "HIGHER_TIMEFRAME_ENTRY_VETO"
    if s.structural_phase_4h in {
        StructuralPhase.DISTRIBUTION_RISK,
        StructuralPhase.REDISTRIBUTION_RISK,
    }:
        return True, "STRUCTURAL_PHASE_VETO"
    return False, "ALLOWED"


FUNDING_STATUS = {
    "H1_V2_ACCEPTED_MARKUP": False,
    "H2_V2_RANGE_ROTATION": False,
    "H3_V2_CORRECTION_RESUMPTION": False,
}
UNRESOLVED_BLOCKERS = (
    "HARMONIC_FAMILY_BY_FAMILY_RATIO_STOP_MANAGEMENT_MATRIX",
    "ELLIOTT_PARENT_CHILD_GRAMMAR_AND_OWNER_COUNT_SELECTION",
    "WYCKOFF_PNF_COUNT_LINE_AND_COUNT_SEGMENT_AUTHORITY",
    "WYCKOFF_DOWNSIDE_OBJECTIVE_AND_STRIDE_BINDINGS",
    "HISTORICAL_TICK_LOT_MIN_NOTIONAL_BINDINGS_IF_NOT_CANONICAL",
)
