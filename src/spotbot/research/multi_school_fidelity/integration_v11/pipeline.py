"""V11 source seal -> guarded old native mechanics, no funding self-attestation."""

from __future__ import annotations

from ..integration_v10.pipeline import PipelineV9 as PreviousPipeline
from ..integration_v10.pipeline import RouterV9 as PreviousRouter
from ..integration_v10.pipeline import _no_outcomes
from ..structural_lifecycle_v6 import ContractError
from .contracts import LegacyIssue, Produced, canonical, freeze, verify_issue
from .execution import ExecutionV11, SourceGuard


class RouterV11(PreviousRouter):
    def permission(self, grammar, state):
        ok, reason = super().permission(grammar, state)
        if reason == "V10_INDEPENDENT_RESERVE_AND_PRODUCER_CERTIFICATION_REQUIRED":
            reason = "V11_INDEPENDENT_RESERVE_AND_PRODUCER_CERTIFICATION_REQUIRED"
        return ok, reason


class PipelineV11(PreviousPipeline):
    def __init__(self, execution, router):
        if not isinstance(execution, ExecutionV11):
            raise ContractError("V11_GUARDED_EXECUTION_REQUIRED")
        super().__init__(execution, router)

    def _authorize(self, envelope, issue, graph):
        claims = tuple(graph.nodes[e].evidence for e in envelope.required_events)
        configuration = (envelope.mode, envelope.objectives, envelope.partial_plan, envelope.staged)
        guard = SourceGuard(
            issue,
            graph,
            freeze(envelope.row),
            envelope.binding,
            envelope.add_evidence,
            claims,
            configuration,
        )
        old = self.execution.source_guards.get(envelope.row["identity"])
        if old is not None and old != guard:
            raise ContractError("KERNEL_SOURCE_GUARD_IMMUTABLE")
        self.execution.source_guards[envelope.row["identity"]] = guard
        return envelope

    def bind(self, produced, prefix, state, context, **kwargs):
        if not isinstance(produced, Produced):
            raise ContractError("SEALED_V11_PRODUCED_REQUIRED")
        verify_issue(produced, prefix.graph, produced.event["timestamp"])
        _no_outcomes(canonical(produced.event))
        envelope = super().bind(produced, prefix, state, context, **kwargs)
        if envelope.row["pit_eligible"] is not produced.membership.value.eligible:
            raise ContractError("BOUND_PIT_SOURCE_PARITY")
        if produced.add_proof:
            expected = produced.add_proof.value.evaluate(
                prefix.graph, produced.thesis, prefix.pair, produced.event["timestamp"]
            )
            if envelope.add_evidence.lps_low != expected:
                raise ContractError("BOUND_ADD_PROVENANCE_PARITY")
        return self._authorize(envelope, produced, prefix.graph)

    def bind_legacy(self, issue, binding, setup, state, *, context, graph, stop_proof, **kwargs):
        if not isinstance(issue, LegacyIssue):
            raise ContractError("SEALED_LEGACY_ISSUE_REQUIRED")
        verify_issue(issue, graph, issue.event["timestamp"])
        if binding != issue.binding or stop_proof != issue.stop_proof:
            raise ContractError("LEGACY_ISSUED_BINDING_PARITY")
        envelope = super().bind_legacy(
            dict(issue.event),
            binding,
            setup,
            state,
            context=context,
            graph=graph,
            stop_proof=stop_proof,
            **kwargs,
        )
        return self._authorize(envelope, issue, graph)

    def _bind(self, candidate, now, prices, capacities):
        guard = self.execution.source_guards.get(candidate.row["identity"])
        if guard is None:
            return None, "V11_KERNEL_SOURCE_GUARD_REQUIRED"
        try:
            guard.validate(
                candidate.row,
                candidate.binding,
                now,
                candidate.existing_campaign_id or candidate.row["identity"],
                candidate.add_evidence,
            )
        except ContractError as exc:
            return None, "V11_SOURCE_AUTHORITY:" + str(exc)
        return super()._bind(candidate, now, prices, capacities)
