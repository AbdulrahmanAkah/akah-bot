"""Explicit Dow legacy bridge retaining exact V11 issue/source kernel guard."""
import copy
import json
from ..integration_v11.contracts import LegacyIssue, verify_issue
from ..integration_v10.pipeline import _no_outcomes, envelope_signature
from ..owned_event_pipeline_v7 import bind_producer_event
from ..structural_lifecycle_v6 import DO, LiveEvidence, ContractError, instant
from .dow_source import DowStopProof

def bind_dow(pipeline, issue, binding, setup, state, *, context, graph, stop_proof, **kwargs):
    if not isinstance(issue, LegacyIssue) or binding != issue.binding or stop_proof != issue.stop_proof:
        raise ContractError("DOW_SEALED_ISSUED_BINDING_PARITY")
    now = instant(issue.event["timestamp"])
    verify_issue(issue, graph, now)
    if (binding.grammar != DO or binding.owner != DO or not isinstance(stop_proof, DowStopProof)
            or stop_proof.evaluate(graph, now) != binding.initial_invalidation
            or binding.invalidation_source not in stop_proof.source_ids):
        raise ContractError("DOW_SECONDARY_STOP_SOURCE_PARITY")
    event = copy.deepcopy(dict(issue.event))
    meta = json.loads(event["metadata"]) if isinstance(event.get("metadata"), str) else dict(event.get("metadata", {}))
    if meta.get("invalidation_source") != binding.invalidation_source:
        raise ContractError("DOW_STOP_METADATA_PARITY")
    ids = tuple(dict.fromkeys((*meta.get("required_evidence_ids", ()), *stop_proof.source_ids, context.event_id)))
    meta.update(required_evidence_ids=ids, invalidation_source_ids=stop_proof.source_ids,
                invalidation_derivation=stop_proof.kind, producer_version="V15_DOW")
    event["metadata"] = json.dumps(meta, sort_keys=True)
    setup = copy.deepcopy(setup)
    def observe(eid):
        if eid in setup.evidence:
            return
        if not graph.live(eid, now):
            raise ContractError("LIVE_DOW_SOURCE_REQUIRED")
        node = graph.nodes[eid]
        for parent in node.parents:
            observe(parent)
        setup.observe(LiveEvidence(eid, binding.structure_id, node.evidence.available_at,
                                  node.parents, node.evidence.valid_until), now)
    for eid in ids:
        observe(eid)
    _no_outcomes(event)
    _no_outcomes(meta)
    graph.require(context, now)
    if context.value != state:
        raise ContractError("DOW_ROUTER_NOT_SOURCE_BOUND")
    envelope = bind_producer_event(event, binding, setup, state, context_known_at=context.available_at,
                                  context_source_sha256=context.source_sha256, **kwargs)
    ids = tuple(dict.fromkeys((*envelope.required_events, context.event_id)))
    if not all(graph.live(e, now) for e in ids):
        raise ContractError("DOW_SOURCE_GRAPH_INVALID_BEFORE_BIND")
    pipeline.provenance[envelope.row["identity"]] = (graph, ids, envelope_signature(envelope), binding)
    return pipeline._authorize(envelope, issue, graph)
