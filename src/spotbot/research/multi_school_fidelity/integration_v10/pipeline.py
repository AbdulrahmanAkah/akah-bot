"""Source graph -> immutable owner envelope -> prebatch selector -> kernel.

No Gate-2/Gate-3 self-attestation. Synthetic execution is explicitly separate.
"""

from __future__ import annotations

import copy
import json
from dataclasses import replace
from datetime import timedelta

from ..akah_thesis_engine_foundation_v1 import StructuralPhase, long_entry_veto
from ..campaign_execution_v7 import AddEvidence, authority_is_historical
from ..ict_h2_contract_v8 import SESSION, TREND
from ..owned_event_pipeline_v7 import OwnedEventPipelineV7, bind_producer_event
from ..school_contract_common_v8 import Known, clock, digest
from ..structural_lifecycle_v6 import (
    CL,
    H1,
    ContractError,
    LiveEvidence,
    Mode,
    Objective,
    PendingSetup,
    instant,
)
from .execution import ContractBinding, NativeFailureV9, PartialPlanV9
from .producers import ELLIOTT, H3, HARMONIC, WYCKOFF
from .stop_provenance import StopProof

PHASES = {
    HARMONIC: frozenset({StructuralPhase.BASE_CANDIDATE, StructuralPhase.REACCUMULATION_CANDIDATE}),
    ELLIOTT: frozenset({StructuralPhase.MARKUP, StructuralPhase.REACCUMULATION_CANDIDATE}),
    WYCKOFF: frozenset({StructuralPhase.BASE_CANDIDATE, StructuralPhase.REACCUMULATION_CANDIDATE}),
    SESSION: frozenset({StructuralPhase.BASE_CANDIDATE, StructuralPhase.REACCUMULATION_CANDIDATE}),
    TREND: frozenset({StructuralPhase.MARKUP, StructuralPhase.REACCUMULATION_CANDIDATE}),
    H3: frozenset({StructuralPhase.MARKUP, StructuralPhase.REACCUMULATION_CANDIDATE}),
    CL: frozenset(
        {
            StructuralPhase.BASE_CANDIDATE,
            StructuralPhase.MARKUP,
            StructuralPhase.REACCUMULATION_CANDIDATE,
        }
    ),
    H1: frozenset({StructuralPhase.MARKUP, StructuralPhase.REACCUMULATION_CANDIDATE}),
}


class RouterV9:
    """Prospective phase table; NOT a Gate-2 certificate or optimized regime rule."""

    def __init__(self, *, synthetic_fixture_execution=False):
        self.synthetic_fixture_execution = synthetic_fixture_execution

    def permission(self, grammar, state):
        veto, reason = long_entry_veto(state)
        if veto:
            return False, reason
        if grammar not in PHASES:
            return False, "UNBOUND_OR_CONTEXT_ONLY_GRAMMAR"
        if state.structural_phase_4h not in PHASES[grammar]:
            return False, "PHASE_NOT_IN_V9_PROSPECTIVE_TABLE"
        if not self.synthetic_fixture_execution:
            return False, "V10_INDEPENDENT_RESERVE_AND_PRODUCER_CERTIFICATION_REQUIRED"
        return True, "SYNTHETIC_MECHANICS_ONLY_NOT_FUNDED_CERTIFICATION"


def _no_outcomes(value):
    forbidden = {
        "pnl",
        "net_pnl",
        "profit",
        "future_exit",
        "future_exit_time",
        "exit_price",
        "outcome",
        "exit_market_state",
        "label_end",
        "realized_return",
    }
    if isinstance(value, dict):
        if forbidden & value.keys():
            raise ContractError("OUTCOME_NOT_CAUSAL_PRODUCER_INPUT")
        for v in value.values():
            _no_outcomes(v)
    elif isinstance(value, (tuple, list)):
        for v in value:
            _no_outcomes(v)


def envelope_signature(c):
    """Freeze decision inputs, not mutable consumed/invalidated graph status."""
    return digest(
        (
            c.row,
            c.binding,
            c.mode,
            c.objectives,
            c.required_events,
            c.state,
            c.ready_at,
            c.valid_until,
            c.context_known_at,
            c.context_source_sha256,
            c.partial_plan,
            c.staged,
            c.add_evidence,
            c.existing_campaign_id,
            sorted(c.setup.evidence.items()),
        )
    )


class PipelineV9(OwnedEventPipelineV7):
    def __init__(self, execution, router):
        super().__init__(execution, router)
        self.provenance = {}

    def bind(
        self,
        produced,
        prefix,
        state,
        context,
        *,
        valid_until=None,
        session_end=None,
        existing_campaign_id=None,
    ):
        t = produced.thesis
        add = produced.add_instruction
        now = clock(add["known_at"] if add else t.available_at)
        _no_outcomes(produced.event)
        prefix.graph.require(context, now)
        if context.value != state:
            raise ContractError("ROUTER_STATE_NOT_SOURCE_BOUND")
        if produced.event["pair"] != prefix.pair:
            raise ContractError("CROSS_ASSET_PRODUCER_MISMATCH")
        meta = json.loads(produced.event["metadata"])
        _no_outcomes(meta)
        proof = produced.stop_proof
        if not isinstance(proof, StopProof):
            raise ContractError("EXPLICIT_TYPED_STOP_PROVENANCE_REQUIRED")
        proof.validate_owner(t)
        stop_claim = proof.bind(prefix.graph, t, now)
        if (
            produced.stop_claim_id != stop_claim.event_id
            or meta.get("invalidation_source") != stop_claim.event_id
            or tuple(meta.get("invalidation_source_ids", ())) != proof.source_ids
            or meta.get("invalidation_derivation") != proof.kind
        ):
            raise ContractError("SEMANTIC_STOP_METADATA_PARITY_REQUIRED")
        if (
            produced.event["system_id"] != t.grammar
            or instant(produced.event["timestamp"]) != now
            or meta.get("stop") != t.initial_invalidation
            or meta.get("owner_structure_id") != t.structure_id
            or tuple(meta.get("required_evidence_ids", ())) != produced.evidence_ids
            or meta.get("management_owner") != t.owner
            or meta.get("management_degree") != t.management_degree
            or meta.get("management_mode") != t.mode
        ):
            raise ContractError("PRODUCED_EVENT_THESIS_PARITY_REQUIRED")
        b = ContractBinding(
            t.grammar,
            t.owner,
            t.structure_id,
            t.source_sha256,
            t.management_degree,
            t.available_at,
            t.initial_invalidation,
            stop_claim.event_id,
            t,
            proof,
            stop_claim.event_id,
        )
        setup = PendingSetup(t.structure_id)
        graph = prefix.graph

        def observe(eid):
            if eid in setup.evidence:
                return
            if not graph.live(eid, now):
                raise ContractError("PRODUCER_PARENT_INVALIDATED_OR_EXPIRED")
            node = graph.nodes[eid]
            for parent in node.parents:
                observe(parent)
            e = node.evidence
            setup.observe(
                LiveEvidence(eid, t.structure_id, e.available_at, node.parents, e.valid_until), now
            )

        ids = tuple(dict.fromkeys((*produced.evidence_ids, context.event_id)))
        for eid in ids:
            observe(eid)
        event = dict(produced.event)
        metadata = dict(meta, required_evidence_ids=ids)
        event["metadata"] = json.dumps(metadata, sort_keys=True)
        kinds = {
            HARMONIC: "FAMILY_REACTION",
            ELLIOTT: "COUNT_OBJECTIVE",
            H3: "COUNT_OBJECTIVE",
            WYCKOFF: "PNF_CAUSE",
            SESSION: "CONFIRMED_RESISTANCE",
            TREND: "CONFIRMED_RESISTANCE",
        }
        objectives = tuple(
            Objective(
                digest((t.structure_id, i, goal)),
                t.structure_id,
                goal,
                kinds[t.grammar],
                t.available_at,
                t.source_sha256,
            )
            for i, goal in enumerate(t.objectives)
        )
        partial = None
        if t.grammar == HARMONIC:
            if len(objectives) != 2:
                raise ContractError("EXACT_NATIVE_PARTIAL_PAIR_REQUIRED")
            partial = PartialPlanV9(*objectives, t.owner.removeprefix("HARMONIC_"))
        add_evidence = None
        if add:
            if (
                t.grammar != WYCKOFF
                or existing_campaign_id != add["campaign_id"]
                or add["owner"] != t.owner
            ):
                raise ContractError("SOURCE_ADD_CAMPAIGN_OWNER_REQUIRED")
            add_evidence = AddEvidence(
                digest((t.structure_id, now, "LPS_ADD")),
                t.structure_id,
                now,
                add["stop_floor"],
                t.source_sha256,
            )
        elif existing_campaign_id is not None:
            raise ContractError("NO_ADD_PROOF_FOR_EXISTING_CAMPAIGN")
        envelope = bind_producer_event(
            event,
            b,
            setup,
            state,
            mode=Mode.FINITE if t.mode == "FINITE_REACTION" else Mode.TREND,
            objectives=objectives,
            valid_until=valid_until or now + timedelta(hours=1),
            context_known_at=context.available_at,
            context_source_sha256=context.source_sha256,
            partial_plan=partial,
            staged=produced.staged,
            add_evidence=add_evidence,
            existing_campaign_id=existing_campaign_id,
        )
        if t.grammar == SESSION:
            if session_end is None:
                raise ContractError("SOURCE_SESSION_END_REQUIRED")
            graph.require(session_end, now)
            if session_end.structure_id != t.structure_id or now >= instant(session_end.value):
                raise ContractError("SOURCE_SESSION_OWNER_OR_EXPIRY")
            envelope.row["session_end"] = session_end.value
        self.provenance[envelope.row["identity"]] = (
            graph,
            ids,
            envelope_signature(envelope),
            envelope.binding,
        )
        return envelope

    def bind_legacy(self, event, binding, setup, state, *, context, graph, stop_proof, **kwargs):
        """Classical/H1 stay on their existing source contract; not new fidelity."""
        if binding.grammar not in {CL, H1}:
            raise ContractError("LEGACY_DIAGNOSTIC_NOT_NEW_OWNER_PROOF")
        now = instant(event["timestamp"])
        if (
            not isinstance(stop_proof, StopProof)
            or stop_proof.kind not in {"CLASSICAL_ACCEPTANCE_LOW", "CLASSICAL_CONFIRMED_LOW"}
            or stop_proof.evaluate(graph, now) != binding.initial_invalidation
            or binding.invalidation_source not in stop_proof.source_ids
        ):
            raise ContractError("CLASSICAL_OWNER_STOP_PROVENANCE_REQUIRED")
        event = copy.deepcopy(event)
        meta = (
            json.loads(event["metadata"])
            if isinstance(event.get("metadata"), str)
            else dict(event.get("metadata", {}))
        )
        if meta.get("invalidation_source") != binding.invalidation_source:
            raise ContractError("CLASSICAL_STOP_METADATA_PARITY_REQUIRED")
        ids = tuple(
            dict.fromkeys(
                (*meta.get("required_evidence_ids", ()), *stop_proof.source_ids, context.event_id)
            )
        )
        meta.update(
            required_evidence_ids=ids,
            invalidation_source_ids=stop_proof.source_ids,
            invalidation_derivation=stop_proof.kind,
            producer_version="V10",
        )
        event["metadata"] = json.dumps(meta, sort_keys=True)
        setup = copy.deepcopy(setup)

        def observe(eid):
            if eid in setup.evidence:
                return
            if not graph.live(eid, now):
                raise ContractError("LIVE_LEGACY_SOURCE_REQUIRED")
            node = graph.nodes[eid]
            for p in node.parents:
                observe(p)
            setup.observe(
                LiveEvidence(
                    eid,
                    binding.structure_id,
                    node.evidence.available_at,
                    node.parents,
                    node.evidence.valid_until,
                ),
                now,
            )

        for eid in ids:
            observe(eid)
        _no_outcomes(event)
        _no_outcomes(
            json.loads(event["metadata"])
            if isinstance(event.get("metadata"), str)
            else event.get("metadata", {})
        )
        graph.require(context, event["timestamp"])
        if context.value != state:
            raise ContractError("ROUTER_STATE_NOT_SOURCE_BOUND")
        envelope = bind_producer_event(
            event,
            binding,
            setup,
            state,
            context_known_at=context.available_at,
            context_source_sha256=context.source_sha256,
            **kwargs,
        )
        ids = tuple(envelope.required_events)
        if not graph.live(context.event_id, event["timestamp"]) or not all(
            graph.live(e, event["timestamp"]) for e in ids
        ):
            raise ContractError("LEGACY_ACTUAL_SOURCE_GRAPH_REQUIRED")
        self.provenance[envelope.row["identity"]] = (
            graph,
            (*ids, context.event_id),
            envelope_signature(envelope),
            binding,
        )
        return envelope

    def _bind(self, c, now, prices, capacities):
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
            else:
                if instant(c.add_evidence.available_at) != now:
                    raise ContractError("CURRENT_SOURCE_ADD_CHECKPOINT_REQUIRED")
        rule = self.execution.portfolio.rules.get(c.row["pair"])
        if rule is None:
            return None, "QUANTITY_AUTHORITY_UNBOUND"
        if not self.router.synthetic_fixture_execution and not authority_is_historical(rule, now):
            return None, "HISTORICAL_QUANTITY_AUTHORITY_REQUIRED"
        result, reason = super()._bind(c, now, prices, capacities)
        if result is None:
            return result, reason
        feasible, store = result
        # Call the very same admission method on an isolated state. Do not
        # approximate B0, fees, normalizer, pending exits, asset/cash/risk limits.
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

    def source_failure(self, tid, evidence, graph, now):
        """Exact owner failure only; H2 internal MSS/session expiry is diagnostic."""
        graph.require(evidence, now)
        b = self.execution.managers[tid].binding
        if evidence.structure_id != b.structure_id:
            raise ContractError("FAILURE_WRONG_STRUCTURE")
        if b.grammar == TREND and evidence.value in {"NY16", "BEARISH_MSS"}:
            return None
        f = NativeFailureV9(
            evidence.event_id,
            b.owner,
            b.structure_id,
            evidence.value,
            evidence.available_at,
            evidence.source_sha256,
        )
        f.validate(b, now)
        return f

    def acknowledge_harmonic_completion(self, producer, sid, owner, at, campaign_id):
        """Actual kernel closure, not a detector's guess that a target was hit."""
        at = clock(at)
        e = self.execution
        b = e.campaign_owner.get(campaign_id)
        if b is None or b.grammar != HARMONIC or b.structure_id != sid or b.owner != owner:
            raise ContractError("EXACT_KERNEL_COMPLETION_OWNER_REQUIRED")
        if any(p["campaign_id"] == campaign_id for p in e.portfolio.k.positions.values()):
            raise ContractError("CAMPAIGN_STILL_OPEN_NO_TYPE_COMPLETION")
        sales = [
            f
            for f in e.portfolio.k.fills
            if f["campaign_id"] == campaign_id and f["side"] == "SELL"
        ]
        if not sales or instant(sales[-1]["time"]) != at:
            raise ContractError("KERNEL_CLOSURE_TIMESTAMP_REQUIRED")
        graph = producer.graph
        parents = tuple(producer.harmonics[sid].projection.points[i].event_id for i in range(4))
        receipt = graph.register(
            Known(
                digest((campaign_id, owner, at, "CLOSED")),
                ("CAMPAIGN_CLOSED", owner),
                at,
                b.source_sha256,
                sid,
            ),
            parents,
            origin="DETECTOR_GEOMETRY",
        )
        producer.acknowledge_harmonic_completion(sid, owner, at, execution_receipt=receipt)

    def acknowledge_wyckoff_stage(self, producer, sid, at, campaign_id):
        at = clock(at)
        e = self.execution
        b = e.campaign_owner.get(campaign_id)
        fills = [x for x in e.portfolio.k.fills if x["campaign_id"] == campaign_id]
        if (
            b is None
            or b.grammar != WYCKOFF
            or b.structure_id != sid
            or campaign_id not in e.staged_campaigns
            or not fills
            or fills[0]["side"] != "BUY"
            or instant(fills[0]["time"]) != at
            or at != b.available_at
            or not any(p["campaign_id"] == campaign_id for p in e.portfolio.k.positions.values())
        ):
            raise ContractError("ACTUAL_KERNEL_WYCKOFF_STAGE_FILL_REQUIRED")
        receipt = producer.graph.register(
            Known(
                digest((campaign_id, sid, at, "WY_STAGE_FILL_V10")),
                ("WYCKOFF_STAGE1_FILLED", campaign_id),
                at,
                b.source_sha256,
                sid,
            ),
            b.thesis.parents,
            origin="DETECTOR_GEOMETRY",
        )
        producer.acknowledge_wyckoff_stage(sid, receipt, at)
