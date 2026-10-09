"""Opt-in live-evidence hybrid binding. Legacy hybrid output stays quarantined."""

from __future__ import annotations

from dataclasses import dataclass, field

from .evidence_selector import EvidenceStore


@dataclass
class BoundHybrid:
    owner_grammar: str
    owner_structure_id: str
    stages: tuple[str, ...]
    evidence: EvidenceStore
    source_rule_hash: str
    role_ids: dict[str, str] = field(default_factory=dict)
    terminated: bool = False
    funded_ready: bool = False

    def __post_init__(self):
        if (
            not self.stages
            or len(set(self.stages)) != len(self.stages)
            or not self.source_rule_hash
        ):
            raise ValueError("FROZEN_GRAMMAR_BINDING_REQUIRED")

    def live(self, now):
        return not self.terminated and all(
            self.evidence.live(event_id, now) for event_id in self.role_ids.values()
        )

    def observe(self, role, event_id, now):
        if self.terminated:
            raise ValueError("THESIS_ID_RESURRECTION_FORBIDDEN")
        if not self.live(now):
            self.terminated = True
            return "INVALIDATED"
        index = len(self.role_ids)
        if index == len(self.stages) or role != self.stages[index]:
            return "NO_TRANSITION"
        if event_id not in self.evidence.records or not self.evidence.live(event_id, now):
            return "EVIDENCE_NOT_LIVE"
        self.role_ids[role] = event_id
        return (
            "THESIS_COMPLETE_UNFUNDED"
            if len(self.role_ids) == len(self.stages)
            else "AWAIT_NEXT_ROLE"
        )

    def ready(self, now):
        return self.funded_ready and self.live(now) and len(self.role_ids) == len(self.stages)

    def invalidate_owner(self):
        self.terminated = True
