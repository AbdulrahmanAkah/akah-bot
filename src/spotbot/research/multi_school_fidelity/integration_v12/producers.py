"""Retain exact issue and execution prerequisites through final admission."""

from __future__ import annotations

from dataclasses import replace

from ..integration_v10.producers import ELLIOTT, H3, HARMONIC
from ..integration_v11.contracts import verify_issue
from ..integration_v11.producers import ContractProducer as PreviousProducer
from ..school_contract_common_v8 import clock, digest
from ..structural_lifecycle_v6 import ContractError


class ContractProducer(PreviousProducer):
    def __init__(self, prefix):
        super().__init__(prefix)
        self.type_i_completion_receipts = {}

    def acknowledge_harmonic_completion(self, sid, owner, at, *, execution_receipt):
        at = clock(at)
        self.graph.require(execution_receipt, at)
        if clock(execution_receipt.available_at) != at:
            raise ContractError("COMPLETION_RECEIPT_EXACT_CLOCK_REQUIRED")
        if execution_receipt.source_sha256 != self.prefix.sha:
            raise ContractError("COMPLETION_RECEIPT_SOURCE_PARITY")
        if owner == "HARMONIC_TYPE_I" and sid in self.type_i_completion_receipts:
            raise ContractError("TYPE_I_COMPLETION_NO_REBINDING")
        # Existing pipeline proves actual campaign closure and exact owner/time.
        # Do not infer completion from price touching a target or mutable state.
        super().acknowledge_harmonic_completion(sid, owner, at, execution_receipt=execution_receipt)
        if owner == "HARMONIC_TYPE_I":
            self.type_i_completion_receipts[sid] = execution_receipt

    def _emit(self, thesis, **kwargs):
        if thesis.grammar == HARMONIC and thesis.owner == "HARMONIC_TYPE_II":
            receipt = self.type_i_completion_receipts.get(thesis.structure_id)
            if receipt is None:
                raise ContractError("TYPE_II_EXACT_COMPLETION_RECEIPT_REQUIRED")
            self.graph.require(receipt, thesis.available_at)
            contract = self.harmonics.get(thesis.structure_id)
            if (
                contract is None
                or receipt.value != ("CAMPAIGN_CLOSED", "HARMONIC_TYPE_I")
                or receipt.structure_id != thesis.structure_id
                or receipt.source_sha256 != thesis.source_sha256
                or receipt.available_at != contract.type1_complete_at
                or clock(receipt.available_at) >= clock(thesis.available_at)
            ):
                raise ContractError("TYPE_II_COMPLETION_OWNER_SOURCE_CLOCK_PARITY")
            thesis = replace(
                thesis, parents=tuple(dict.fromkeys((*thesis.parents, receipt.event_id)))
            )
        return super()._emit(thesis, **kwargs)

    def h3(self, count_intent, location_intent, *, pit_eligible):
        c, h = count_intent.thesis, location_intent.thesis
        if c.grammar != ELLIOTT or h.grammar != HARMONIC or c.available_at != h.available_at:
            raise ContractError("SAME_CHECKPOINT_COUNT_AND_LOCATION_REQUIRED")
        for item in (count_intent, location_intent):
            verify_issue(item, self.graph, c.available_at)
            if self.emitted.get(digest(item)) != item:
                raise ContractError("PRODUCER_EMITTED_COUNT_AND_LOCATION_REQUIRED")
            if item.membership != pit_eligible:
                raise ContractError("HYBRID_SAME_PIT_SOURCE_REQUIRED")
        if c.side != "LONG" or h.side != "LONG" or c.initial_invalidation > h.initial_invalidation:
            raise ContractError("COUNT_INVALIDATION_CONFLICTS_WITH_LOCATION")
        seals = (count_intent.emission_id, location_intent.emission_id)
        thesis = replace(
            c,
            grammar=H3,
            parents=tuple(dict.fromkeys((*c.parents, *h.parents, *seals))),
            adaptation="COUNT_OWNS_THESIS_HARMONIC_LOCATION_ONLY_V9",
        )
        # Exact sealed issues are live authority prerequisites, not votes/features.
        return self._emit(
            thesis,
            pit_eligible=pit_eligible,
            extra=tuple(
                dict.fromkeys((*count_intent.evidence_ids, *location_intent.evidence_ids, *seals))
            ),
            stop_proof=count_intent.stop_proof,
        )
