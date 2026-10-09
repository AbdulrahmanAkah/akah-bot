"""Causal evidence identity and prebatch feasibility arbitration; no score ranking."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .akah_thesis_engine_foundation_v1 import (
    EvidenceRecord,
    EvidenceStatus,
    ParentEdgeType,
    RouterState,
    ThesisRecord,
    long_entry_veto,
    selector_key,
)


class EvidenceStore:
    def __init__(self):
        self.records: dict[str, EvidenceRecord] = {}

    def register(self, record: EvidenceRecord):
        if record.event_id in self.records:
            raise ValueError("EVENT_ID_RESURRECTION_OR_DUPLICATE")
        if record.observed_at > record.available_at:
            raise ValueError("OBSERVATION_AFTER_AVAILABILITY")
        if not record.source_rule_hash or record.status != EvidenceStatus.ACTIVE:
            raise ValueError("NEW_EVENT_AUTHORITY_INVALID")
        if record.valid_until is not None and record.valid_until <= record.available_at:
            raise ValueError("EVENT_EXPIRES_BEFORE_AVAILABLE")
        for edge in record.parent_edges:
            if edge.parent_event_id not in self.records:
                raise ValueError("UNBOUND_PARENT_EVENT")
            if self.records[edge.parent_event_id].available_at > record.available_at:
                raise ValueError("CHILD_AVAILABLE_BEFORE_PARENT")
        self.records[record.event_id] = record

    def terminate(self, event_id: str, status: EvidenceStatus):
        if status not in {
            EvidenceStatus.CONSUMED,
            EvidenceStatus.EXPIRED,
            EvidenceStatus.INVALIDATED,
        }:
            raise ValueError("RESURRECTION_FORBIDDEN")
        record = self.records[event_id]
        if record.status != EvidenceStatus.ACTIVE:
            raise ValueError("TERMINAL_EVENT_CANNOT_TRANSITION")
        record.status = status

    def live(self, event_id, now, *, management=False):
        record = self.records[event_id]
        if not record.is_live(now, {k: r.status for k, r in self.records.items()}):
            return False
        for edge in record.parent_edges:
            if edge.edge_type == ParentEdgeType.LIVE_REQUIREMENT and not self.live(
                edge.parent_event_id, now
            ):
                return False
            if (
                management
                and edge.edge_type == ParentEdgeType.MANAGEMENT_DEPENDENCY
                and not self.live(edge.parent_event_id, now, management=True)
            ):
                return False
        return True


@dataclass(frozen=True)
class Feasibility:
    thesis: ThesisRecord
    router: RouterState
    pit_membership: bool
    geometry_valid: bool
    portfolio_risk_feasible: bool
    quantity_authority_bound: bool
    next_open_valid: bool


def select_prebatch(
    candidates: list[Feasibility], evidence: EvidenceStore, now, existing_owner: dict[str, str]
):
    accepted, rejected, same_asset = [], {}, defaultdict(list)
    seen = set()
    for candidate in candidates:
        t = candidate.thesis
        if t.thesis_id in seen:
            raise ValueError("DUPLICATE_THESIS_ID")
        seen.add(t.thesis_id)
        reason = None
        if not t.funded_ready or not candidate.quantity_authority_bound:
            reason = "INCOMPLETE_FROZEN_FUNDED_THESIS"
        elif not candidate.pit_membership or not candidate.geometry_valid:
            reason = "MEMBERSHIP_OR_GEOMETRY"
        elif t.capacity_fraction <= 0 or not candidate.portfolio_risk_feasible:
            reason = "CAPACITY_OR_RISK_INFEASIBLE"
        elif not candidate.next_open_valid or t.ready_at > now:
            reason = "NEXT_OPEN_EXPIRED_OR_NOT_READY"
        elif long_entry_veto(candidate.router)[0]:
            reason = "ROUTER_VETO"
        elif not t.supporting_evidence_ids or not all(
            eid in evidence.records and evidence.live(eid, now) for eid in t.supporting_evidence_ids
        ):
            reason = "LIVE_EVIDENCE_INVALID"
        elif t.action_class == "ADD" and existing_owner.get(t.pair) != t.owner_structure_id:
            reason = "ADD_OWNER_MISMATCH"
        elif t.action_class != "ADD" and t.pair in existing_owner:
            reason = "EXISTING_OWNER_NO_WINNER_REPLACEMENT"
        if reason is not None:
            rejected[t.thesis_id] = reason
        else:
            same_asset[t.pair].append(t)
    for theses in same_asset.values():
        owners = {(t.owner_grammar, t.owner_structure_id) for t in theses}
        if len(owners) > 1:
            for t in theses:
                rejected[t.thesis_id] = "SAME_ASSET_OWNERSHIP_CONFLICT"
            continue
        # Multiple aliases of one owned structure are one thesis, not independent votes.
        accepted.append(min(theses, key=selector_key))
    return sorted(accepted, key=selector_key), rejected
