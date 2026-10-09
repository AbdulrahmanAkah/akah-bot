"""Honor research exclusions without turning real market data into synthetic fixtures.

Old V12 actual mode remains fail-closed. This separate scope changes ONLY the
review/quantity admission policy. Source proof, preview and actual kernel guards
are unchanged. Certificates are trusted artifacts, not user-selectable alpha.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace

from ..akah_thesis_engine_foundation_v1 import long_entry_veto
from ..full_replay_v5 import ContinuousRule
from ..integration_v10.execution import ContractBinding
from ..integration_v10.pipeline import PHASES, envelope_signature
from ..integration_v12.pipeline import PipelineV12
from ..owned_event_pipeline_v7 import OwnedEventPipelineV7
from ..school_contract_common_v8 import clock, valid_sha
from ..structural_lifecycle_v6 import ContractError, instant

MODE = "USER_AUTHORIZED_APPROXIMATE_RESEARCH_V13"


@dataclass(frozen=True)
class ResearchScope:
    protocol_sha256: str
    source_version_sha256: str
    review_policy: str = "USER_WAIVED_NOT_INDEPENDENT_PASS"
    quantity_policy: str = "APPROXIMATE_NOT_HISTORICAL_EXCHANGE_AUTHORITY"
    mode: str = MODE

    def validate(self):
        valid_sha(self.protocol_sha256)
        valid_sha(self.source_version_sha256)
        if (
            self.mode != MODE
            or self.review_policy != "USER_WAIVED_NOT_INDEPENDENT_PASS"
            or self.quantity_policy != "APPROXIMATE_NOT_HISTORICAL_EXCHANGE_AUTHORITY"
        ):
            raise ContractError("EXPLICIT_USER_RESEARCH_EXCLUSIONS_REQUIRED")


@dataclass(frozen=True)
class ProducerCertificate:
    """Issued only by a source-bound implementation harness, not this router.

    The evidence artifact contains source-generator and guarded-driver tests.
    This is permission for a bounded research test, NOT historical certification.
    Actual prefix, seal and live-parent proofs remain mandatory at every fill.
    """

    grammar: str
    source_version_sha256: str
    protocol_sha256: str
    evidence_sha256: str
    status: str
    evidence_scope: str

    def validate(self, scope):
        for value in (self.source_version_sha256, self.protocol_sha256, self.evidence_sha256):
            valid_sha(value)
        if (
            self.status != "SOURCE_BOUND_RESEARCH_IMPLEMENTATION_PASS"
            or self.evidence_scope != "SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION"
            or self.grammar not in PHASES
            or self.source_version_sha256 != scope.source_version_sha256
            or self.protocol_sha256 != scope.protocol_sha256
        ):
            raise ContractError("EXACT_VERSION_IMPLEMENTATION_CERTIFICATE_REQUIRED")


class ApproximateRule(ContinuousRule):
    """Inherited numerical precision/minimum, explicitly not exchange metadata."""

    def __init__(self, pair, scope):
        scope.validate()
        super().__init__(pair, scope.source_version_sha256)
        self.scope = scope


class ResearchRouter:
    synthetic_fixture_execution = False

    def __init__(self, scope, certificates=()):
        scope.validate()
        self.scope = scope
        self.certificates = {}
        for certificate in certificates:
            certificate.validate(scope)
            if certificate.grammar in self.certificates:
                raise ContractError("DUPLICATE_RESEARCH_GRAMMAR_CERTIFICATE")
            self.certificates[certificate.grammar] = certificate

    def permission(self, grammar, state):
        self.scope.validate()
        veto, reason = long_entry_veto(state)
        if veto:
            return False, reason
        if grammar not in PHASES:
            return False, "UNBOUND_OR_CONTEXT_ONLY_GRAMMAR"
        if state.structural_phase_4h not in PHASES[grammar]:
            return False, "PHASE_NOT_IN_V9_PROSPECTIVE_TABLE"
        certificate = self.certificates.get(grammar)
        if certificate is None:
            return False, "V13_TYPED_PRODUCER_AND_DRIVER_IMPLEMENTATION_CERTIFICATION_REQUIRED"
        certificate.validate(self.scope)
        return True, MODE


class ResearchPipeline(PipelineV12):
    def __init__(self, execution, router):
        if not isinstance(router, ResearchRouter) or router.synthetic_fixture_execution:
            raise ContractError("SEPARATE_NON_SYNTHETIC_RESEARCH_ROUTER_REQUIRED")
        super().__init__(execution, router)

    def _bind(self, c, now, prices, capacities):
        """Same V10 preview and V11 seal guard, with an explicit quantity scope.

        Direct base call below is deliberate: reproduce EVERY intervening source
        check here, replace ONLY the historical-rule clause. No fixture flag.
        """
        now = clock(now)
        guard = self.execution.source_guards.get(c.row["identity"])
        if guard is None:
            return None, "V11_KERNEL_SOURCE_GUARD_REQUIRED"
        try:
            guard.validate(
                c.row, c.binding, now, c.existing_campaign_id or c.row["identity"], c.add_evidence
            )
        except ContractError as exc:
            return None, "V11_SOURCE_AUTHORITY:" + str(exc)
        saved = self.provenance.get(c.row["identity"])
        if saved is None:
            raise ContractError("UNBOUND_V9_PRODUCER_ENVELOPE")
        graph, ids, row_sha, binding = saved
        if envelope_signature(c) != row_sha or c.binding != binding:
            raise ContractError("IMMUTABLE_PRODUCER_OWNER_ROW_REQUIRED")
        if not all(graph.live(e, now) for e in ids):
            return None, "SOURCE_PARENT_INVALIDATED_BEFORE_EXECUTION"
        if isinstance(binding, ContractBinding):
            if c.add_evidence is None:
                entry = prices.get(c.row["pair"])
                if entry is None:
                    return None, "EXECUTABLE_OPEN_MISSING"
                binding.thesis.executable_at(now, binding.available_at, entry)
            elif instant(c.add_evidence.available_at) != now:
                raise ContractError("CURRENT_SOURCE_ADD_CHECKPOINT_REQUIRED")
        rule = self.execution.portfolio.rules.get(c.row["pair"])
        if (
            type(rule) is not ApproximateRule
            or rule.scope != self.router.scope
            or rule.pair != c.row["pair"]
            or rule.source_sha256 != self.router.scope.source_version_sha256
        ):
            return None, "V13_EXACT_APPROXIMATE_QUANTITY_SCOPE_REQUIRED"
        result, reason = OwnedEventPipelineV7._bind(self, c, now, prices, capacities)
        if result is None:
            return result, reason
        feasible, store = result
        preview = copy.deepcopy(self.execution)
        ok, why = preview.admit_owned(
            c.row,
            c.binding,
            now,
            prices[c.row["pair"]],
            capacities[c.row["pair"]],
            c.existing_campaign_id or c.row["identity"],
            mode=c.mode,
            objectives=c.objectives,
            partial_plan=c.partial_plan,
            staged=c.staged,
            add_evidence=c.add_evidence,
            prices=prices,
            research_authorized=True,
        )
        if not ok:
            return None, "PREBATCH_ADMISSION_INFEASIBLE:" + why
        return (replace(feasible, portfolio_risk_feasible=ok), store), reason
