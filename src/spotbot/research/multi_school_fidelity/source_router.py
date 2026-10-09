"""Explicit source-bound phase permissions; an absent grammar table denies funding."""

from __future__ import annotations

from dataclasses import dataclass

from .akah_thesis_engine_foundation_v1 import RouterState, StructuralPhase, long_entry_veto


@dataclass(frozen=True)
class GrammarPermission:
    owner_grammar: str
    phases: frozenset[StructuralPhase]
    source_sha256: str
    gate1_closed: bool
    gate2_closed: bool


class SourceBoundRouter:
    def __init__(self, permissions: tuple[GrammarPermission, ...]):
        self.permissions = {p.owner_grammar: p for p in permissions}
        if len(self.permissions) != len(permissions):
            raise ValueError("DUPLICATE_GRAMMAR_PERMISSION")
        for p in permissions:
            if (
                not p.source_sha256
                or not p.phases
                or any(not isinstance(phase, StructuralPhase) for phase in p.phases)
            ):
                raise ValueError("PHASE_TABLE_SOURCE_BINDING_REQUIRED")

    def permission(self, grammar: str, state: RouterState):
        veto, reason = long_entry_veto(state)
        if veto:
            return False, reason
        p = self.permissions.get(grammar)
        if p is None:
            return False, "UNBOUND_PHASE_TO_FUNDED_GRAMMAR"
        if not p.gate1_closed or not p.gate2_closed:
            return False, "GRAMMAR_GATE1_GATE2_NOT_CLOSED"
        if state.structural_phase_4h not in p.phases:
            return False, "PHASE_NOT_IN_SOURCE_BOUND_GRAMMAR"
        return True, "SOURCE_BOUND_PERMISSION"
