"""Prospective table adds one explicitly owned Dow long grammar."""
from dataclasses import dataclass
from ..integration_v13.research_bridge import ProducerCertificate, MODE
from ..integration_v10.pipeline import PHASES as EIGHT_PHASES
from ..akah_thesis_engine_foundation_v1 import StructuralPhase, long_entry_veto
from ..school_contract_common_v8 import valid_sha
from ..structural_lifecycle_v6 import DO, ContractError

PHASES = {**EIGHT_PHASES, DO: frozenset({StructuralPhase.MARKUP, StructuralPhase.REACCUMULATION_CANDIDATE})}

@dataclass(frozen=True)
class Certificate(ProducerCertificate):
    def validate(self, scope):
        for x in (self.source_version_sha256, self.protocol_sha256, self.evidence_sha256):
            valid_sha(x)
        if (self.grammar not in PHASES or self.source_version_sha256 != scope.source_version_sha256
                or self.protocol_sha256 != scope.protocol_sha256
                or self.status != "SOURCE_BOUND_RESEARCH_IMPLEMENTATION_PASS"
                or self.evidence_scope != "SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION"):
            raise ContractError("EXACT_NINE_SOURCE_CERTIFICATE_REQUIRED")

def permission_for(router, grammar, state):
    router.scope.validate()
    veto, reason = long_entry_veto(state)
    if veto:
        return False, reason
    if grammar not in PHASES or state.structural_phase_4h not in PHASES[grammar]:
        return False, "PHASE_OUTSIDE_PROSPECTIVE_NINE_TABLE"
    cert = router.certificates.get(grammar)
    if cert is None:
        return False, "EXACT_SOURCE_CERTIFICATE_MISSING"
    cert.validate(router.scope)
    return True, MODE
