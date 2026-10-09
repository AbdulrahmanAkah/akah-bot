"""Existing native contracts, sealed emission and externally supplied PIT facts."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

from ..integration_v10.producers import ContractProducer as PreviousProducer
from ..school_contract_common_v8 import clock, digest
from ..structural_lifecycle_v6 import ContractError
from ..wyckoff_contract_v8 import Readiness
from .contracts import (
    LegacyIssue,
    LpsAddProof,
    Produced,
    fingerprint,
    freeze,
    membership_value,
    seal_issue,
    verify_issue,
)


class ContractProducer(PreviousProducer):
    def _emit(
        self,
        thesis,
        *,
        pit_eligible,
        stop_proof,
        staged=False,
        extra=(),
        add_instruction=None,
        add_proof=None,
    ):
        now = clock(add_instruction["known_at"] if add_instruction else thesis.available_at)
        eligible = membership_value(pit_eligible, self.graph, self.prefix.pair, now, now)
        if add_instruction is not None and add_proof is None:
            raise ContractError("SOURCE_BOUND_ADD_PROOF_REQUIRED")
        parents = (*extra, pit_eligible.event_id)
        if add_proof:
            self.graph.require(add_proof, now)
            parents += (add_proof.event_id,)
        raw = super()._emit(
            thesis,
            pit_eligible=eligible,
            stop_proof=stop_proof,
            staged=staged,
            extra=parents,
            add_instruction=add_instruction,
        )
        # The temporary V10 payload is not accepted by the V11 binding path.
        self.emitted.pop(digest(raw), None)
        event = dict(raw.event)
        meta = json.loads(event["metadata"])
        meta.update(
            producer_version="V11",
            membership_source_id=pit_eligible.event_id,
            add_proof_id=add_proof.event_id if add_proof else None,
        )
        event["metadata"] = json.dumps(meta, sort_keys=True)
        result = Produced(
            raw.thesis,
            freeze(event),
            raw.evidence_ids,
            staged,
            freeze(add_instruction) if add_instruction is not None else None,
            stop_proof,
            raw.stop_claim_id,
            pit_eligible,
            add_proof,
            "",
        )
        eid = seal_issue(result, self.graph, thesis.source_sha256, thesis.structure_id, now)
        result = replace(result, emission_id=eid)
        verify_issue(result, self.graph, now)
        self.emitted[digest(result)] = result
        return result

    def wyckoff_add(self, sid, now, entry, readiness, bars, segments, count_line, *, pit_eligible):
        now = clock(now)
        membership_value(pit_eligible, self.graph, self.prefix.pair, now, now)
        if sid not in self.stage_campaign_receipts:
            raise ContractError("WYCKOFF_ACTUAL_STAGE_FILL_RECEIPT_REQUIRED")
        receipt = self.stage_campaign_receipts[sid]
        self.graph.require(receipt, now)
        contract = self.wyckoff[sid]
        if not isinstance(readiness, Readiness):
            raise ContractError("TYPED_PRODUCER_READINESS_REQUIRED")
        self.graph.require(contract.cause.authority, now)
        self.graph.require(count_line, now)
        ids = self._readiness_ids(readiness, bars, now)
        for e in (readiness.market, readiness.rs, *readiness.branch_events):
            self.graph.require(e, now)
        for segment in segments:
            node = self.graph.nodes.get(segment.event_id)
            if (
                not node
                or node.evidence.value != segment
                or not self.graph.live(segment.event_id, now)
            ):
                raise ContractError("SOURCE_OWNED_PNF_SEGMENT_REQUIRED")
        projected = copy.deepcopy(contract)
        instruction = projected.lps_add(now, entry, readiness, bars, segments, count_line)
        if instruction is None:
            return None
        stop = self.stage_stop_proofs[sid].bind(self.graph, projected.stage1, now)
        lps = self.graph.nodes[self.prefix.bar_id(readiness.lps.bar)].evidence
        proof = LpsAddProof(lps, stop, receipt, now, sid, receipt.value[1])
        floor = proof.evaluate(self.graph, projected.stage1, self.prefix.pair, now)
        if floor != instruction["stop_floor"]:
            raise ContractError("NATIVE_ADD_STOP_SOURCE_PARITY")
        claim = self._claim(
            fingerprint(("V11_ADD", sid, now, proof)),
            proof,
            now,
            sid,
            (lps.event_id, stop.event_id, receipt.event_id),
        )
        instruction = dict(instruction, source_campaign_id=sid, campaign_id=proof.campaign_id)
        result = self._emit(
            projected.stage1,
            pit_eligible=pit_eligible,
            extra=(
                receipt.event_id,
                *ids,
                count_line.event_id,
                readiness.market.event_id,
                readiness.rs.event_id,
                *(e.event_id for e in readiness.branch_events),
                *(s.event_id for s in segments),
            ),
            add_instruction=instruction,
            add_proof=claim,
            stop_proof=self.stage_stop_proofs[sid],
        )
        self.wyckoff[sid] = projected
        return result

    def h3(self, count_intent, location_intent, *, pit_eligible):
        for item in (count_intent, location_intent):
            verify_issue(item, self.graph, item.thesis.available_at)
            if item.membership != pit_eligible:
                raise ContractError("HYBRID_SAME_PIT_SOURCE_REQUIRED")
        return super().h3(count_intent, location_intent, pit_eligible=pit_eligible)

    def seal_legacy(self, event, binding, stop_proof, membership):
        now = clock(event["timestamp"])
        eligible = membership_value(membership, self.graph, self.prefix.pair, now, now)
        if event["pair"] != self.prefix.pair or event["broad_eligible"] is not eligible:
            raise ContractError("LEGACY_PIT_EVENT_PARITY")
        meta = json.loads(event["metadata"])
        ids = tuple(
            dict.fromkeys(
                (
                    *meta.get("required_evidence_ids", ()),
                    *stop_proof.source_ids,
                    membership.event_id,
                )
            )
        )
        meta.update(
            required_evidence_ids=ids,
            membership_source_id=membership.event_id,
            producer_version="V11",
        )
        row = dict(event, metadata=json.dumps(meta, sort_keys=True))
        issue = LegacyIssue(freeze(row), binding, stop_proof, membership, ids, "")
        eid = seal_issue(issue, self.graph, binding.source_sha256, binding.structure_id, now)
        issue = replace(issue, emission_id=eid)
        verify_issue(issue, self.graph, now)
        return issue
