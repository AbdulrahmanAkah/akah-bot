"""Immutable source-authority payloads; no market readers or inferred PIT."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime

from ..integration_v10.stop_provenance import StopProof
from ..school_contract_common_v8 import Known, clock, completed
from ..structural_lifecycle_v6 import CompletedBar, ContractError, instant


def freeze(value):
    if isinstance(value, FrozenMap):
        return value
    if isinstance(value, Mapping):
        return FrozenMap(tuple(sorted((k, freeze(v)) for k, v in value.items())))
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("NONFINITE_AUTHORITY_PAYLOAD")
    if value is None or isinstance(value, (str, bool, int, float, datetime)):
        return value
    if is_dataclass(value) and value.__dataclass_params__.frozen:
        for f in fields(value):
            v = getattr(value, f.name)
            if freeze(v) != v:
                raise ContractError("NESTED_MUTABLE_AUTHORITY_PAYLOAD")
        return value
    raise ContractError("IMMUTABLE_AUTHORITY_VALUE_REQUIRED")


@dataclass(frozen=True, slots=True)
class FrozenMap(Mapping):
    items_tuple: tuple

    def __post_init__(self):
        if not isinstance(self.items_tuple, tuple):
            raise ContractError("IMMUTABLE_MAPPING_TUPLE_REQUIRED")
        keys = [k for k, _ in self.items_tuple]
        if len(set(keys)) != len(keys) or any(not isinstance(k, str) for k in keys):
            raise ContractError("UNIQUE_STRING_MAPPING_KEYS_REQUIRED")
        for _, v in self.items_tuple:
            if isinstance(v, (dict, list)) or freeze(v) != v:
                raise ContractError("NESTED_MUTABLE_AUTHORITY_PAYLOAD")

    def __getitem__(self, key):
        for k, v in self.items_tuple:
            if k == key:
                return v
        raise KeyError(key)

    def __iter__(self):
        return (k for k, _ in self.items_tuple)

    def __len__(self):
        return len(self.items_tuple)

    def __deepcopy__(self, memo):
        return self


def canonical(value):
    if isinstance(value, Mapping):
        return {k: canonical(v) for k, v in value.items()}
    if is_dataclass(value):
        return {
            "type": type(value).__qualname__,
            "fields": {f.name: canonical(getattr(value, f.name)) for f in fields(value)},
        }
    if isinstance(value, (tuple, list)):
        return [canonical(v) for v in value]
    if isinstance(value, datetime):
        return instant(value).isoformat()
    return value


def fingerprint(value):
    raw = json.dumps(canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest().upper()


@dataclass(frozen=True)
class PitMembership:
    pair: str
    checkpoint: datetime
    eligible: bool
    effective_from: datetime
    effective_until: datetime


def membership_value(claim, graph, pair, checkpoint, now):
    if not isinstance(claim, Known) or not isinstance(claim.value, PitMembership):
        raise ContractError("TYPED_SOURCE_BOUND_PIT_MEMBERSHIP_REQUIRED")
    graph.require(claim, now)
    value = claim.value
    if (
        type(value.eligible) is not bool
        or value.pair != pair
        or clock(value.checkpoint) != clock(checkpoint)
        or claim.structure_id != pair
        or not instant(value.effective_from)
        <= instant(value.checkpoint)
        < instant(value.effective_until)
        or instant(claim.available_at) > instant(value.checkpoint)
        or graph.nodes[claim.event_id].origin != "SUPPLIED_SEMANTIC_PRODUCER"
    ):
        raise ContractError("PIT_PAIR_CHECKPOINT_PERIOD_OR_SOURCE_PARITY")
    return value.eligible


@dataclass(frozen=True)
class LpsAddProof:
    lps: Known
    stage_stop: Known
    fill_receipt: Known
    checkpoint: datetime
    source_campaign_id: str
    campaign_id: str

    def evaluate(self, graph, thesis, pair, now):
        for claim in (self.lps, self.stage_stop, self.fill_receipt):
            graph.require(claim, now)
            if claim.source_sha256 != thesis.source_sha256:
                raise ContractError("ADD_SOURCE_SHA_PARITY")
        if (
            not isinstance(self.lps.value, tuple)
            or len(self.lps.value) != 2
            or not isinstance(self.lps.value[0], CompletedBar)
        ):
            raise ContractError("TYPED_COMPLETED_LPS_BAR_REQUIRED")
        bar, _ = self.lps.value
        completed(bar, bar.end, thesis.management_degree)
        if (
            self.lps.structure_id != pair
            or clock(bar.end) != clock(self.checkpoint)
            or self.source_campaign_id != thesis.structure_id
            or self.stage_stop.structure_id != thesis.structure_id
            or self.fill_receipt.structure_id != thesis.structure_id
            or self.fill_receipt.value != ("WYCKOFF_STAGE1_FILLED", self.campaign_id)
            or not isinstance(self.stage_stop.value, StopProof)
            or self.stage_stop.value.kind != "SPRING_LOW"
            or self.stage_stop.value.evaluate(graph, now) != thesis.initial_invalidation
        ):
            raise ContractError("ADD_LPS_STAGE_AND_KERNEL_RECEIPT_PARITY")
        return max(thesis.initial_invalidation, bar.low)


@dataclass(frozen=True)
class EmissionSeal:
    payload_sha256: str
    kind: str


@dataclass(frozen=True)
class Produced:
    thesis: object
    event: FrozenMap
    evidence_ids: tuple[str, ...]
    staged: bool
    add_instruction: FrozenMap | None
    stop_proof: StopProof
    stop_claim_id: str
    membership: Known
    add_proof: Known | None
    emission_id: str


@dataclass(frozen=True)
class LegacyIssue:
    event: FrozenMap
    binding: object
    stop_proof: StopProof
    membership: Known
    evidence_ids: tuple[str, ...]
    emission_id: str


def issue_payload(issue):
    # Receipt ID is excluded to avoid a circular digest, but its canonical
    # derivation and exact parent set are verified separately.
    return tuple(
        (f.name, getattr(issue, f.name))
        for f in fields(issue)
        if f.name not in {"emission_id", "evidence_ids"}
    ) + (("evidence_ids", tuple(e for e in issue.evidence_ids if e != issue.emission_id)),)


def seal_issue(issue, graph, source_sha, structure, now):
    payload = fingerprint(issue_payload(issue))
    kind = type(issue).__name__
    eid = fingerprint(("V11_EMISSION", kind, structure, clock(now), payload))
    claim = Known(eid, EmissionSeal(payload, kind), clock(now), source_sha, structure)
    parents = tuple(e for e in issue.evidence_ids if e != issue.emission_id)
    if eid in graph.nodes:
        graph.require(claim, now)
        if graph.nodes[eid].parents != parents:
            raise ContractError("EMISSION_PARENT_PARITY")
    else:
        graph.register(claim, parents, origin="DETECTOR_GEOMETRY")
    return eid


def verify_issue(issue, graph, now):
    if not isinstance(issue, (Produced, LegacyIssue)) or not isinstance(issue.event, FrozenMap):
        raise ContractError("SEALED_V11_ISSUE_REQUIRED")
    checkpoint = clock(issue.event["timestamp"])
    pair = issue.event["pair"]
    eligible = membership_value(issue.membership, graph, pair, checkpoint, now)
    if issue.event["broad_eligible"] is not eligible:
        raise ContractError("PIT_EVENT_PARITY")
    if issue.membership.event_id not in issue.evidence_ids:
        raise ContractError("PIT_NOT_IN_LIVE_DEPENDENCIES")
    payload = fingerprint(issue_payload(issue))
    structure = (
        issue.thesis.structure_id if isinstance(issue, Produced) else issue.binding.structure_id
    )
    source_sha = (
        issue.thesis.source_sha256 if isinstance(issue, Produced) else issue.binding.source_sha256
    )
    eid = fingerprint(("V11_EMISSION", type(issue).__name__, structure, checkpoint, payload))
    expected = Known(
        eid, EmissionSeal(payload, type(issue).__name__), checkpoint, source_sha, structure
    )
    if issue.emission_id != eid or eid in issue.evidence_ids:
        raise ContractError("EMISSION_PAYLOAD_INTEGRITY_PARITY")
    graph.require(expected, now)
    if graph.nodes[eid].parents != tuple(e for e in issue.evidence_ids if e != eid):
        raise ContractError("EMISSION_PARENT_PARITY")
    if isinstance(issue, Produced):
        if issue.add_instruction is not None:
            if not isinstance(issue.add_instruction, FrozenMap) or issue.add_proof is None:
                raise ContractError("IMMUTABLE_SOURCE_ADD_PROOF_REQUIRED")
            graph.require(issue.add_proof, now)
            proof = issue.add_proof.value
            if not isinstance(proof, LpsAddProof):
                raise ContractError("TYPED_ADD_LPS_PROOF_REQUIRED")
            if (
                issue.add_proof.structure_id != issue.thesis.structure_id
                or issue.add_proof.source_sha256 != issue.thesis.source_sha256
                or clock(issue.add_proof.available_at) != checkpoint
            ):
                raise ContractError("ADD_PROOF_OWNER_SOURCE_CLOCK_PARITY")
            price = proof.evaluate(graph, issue.thesis, pair, now)
            add = issue.add_instruction
            if (
                proof.stage_stop.event_id != issue.stop_claim_id
                or clock(proof.checkpoint) != checkpoint
                or add["stop_floor"] != price
                or add["known_at"] != proof.checkpoint
                or add["source_campaign_id"] != proof.source_campaign_id
                or add["campaign_id"] != proof.campaign_id
                or add["owner"] != issue.thesis.owner
                or issue.add_proof.event_id not in issue.evidence_ids
            ):
                raise ContractError("ADD_PROVENANCE_PARITY")
            parents = (proof.lps.event_id, proof.stage_stop.event_id, proof.fill_receipt.event_id)
            if graph.nodes[issue.add_proof.event_id].parents != parents:
                raise ContractError("ADD_PROOF_PARENT_PARITY")
        elif issue.add_proof is not None:
            raise ContractError("UNEXPECTED_ADD_PROOF")
    return eligible
