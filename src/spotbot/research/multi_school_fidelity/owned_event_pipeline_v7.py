"""Deterministic event-to-campaign integration, not a replacement alpha learner.

Consumes typed causal producer envelopes, never outcome/trade-row filtering.
Missing source/routing permissions deny entry. Does not certify old producers.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime

from .akah_thesis_engine_foundation_v1 import (
    EvidenceRecord,
    ParentEdge,
    ParentEdgeType,
    RouterState,
    ThesisRecord,
)
from .campaign_execution_v7 import AddEvidence, CampaignExecutionV7, PartialPlan
from .evidence_selector import EvidenceStore, Feasibility, select_prebatch
from .source_router import SourceBoundRouter
from .structural_lifecycle_v6 import (
    Binding,
    CompletedBar,
    ContractError,
    LiveEvidence,
    Mode,
    Objective,
    PendingSetup,
    StructuralManager,
    instant,
)


@dataclass(frozen=True)
class CandidateEnvelope:
    row: dict
    binding: Binding
    mode: Mode
    objectives: tuple[Objective, ...]
    setup: PendingSetup
    required_events: tuple[str, ...]
    state: RouterState
    ready_at: datetime
    valid_until: datetime
    context_known_at: datetime
    context_source_sha256: str
    partial_plan: PartialPlan | None = None
    staged: bool = False
    add_evidence: AddEvidence | None = None
    existing_campaign_id: str | None = None


def bind_producer_event(
    event,
    binding,
    setup,
    state,
    *,
    mode,
    objectives,
    valid_until,
    context_known_at,
    context_source_sha256,
    partial_plan=None,
    staged=False,
    add_evidence=None,
    existing_campaign_id=None,
):
    """Adapter for actual detector event_row schema; do not manufacture ownership.

    Signal at a completed close is executable at that boundary's following OPEN,
    not at the OPEN of the completed bar. No outcome fields enter the envelope.
    Caller supplies the source-owned live evidence/management contract, not names.
    """
    forbidden = {
        "pnl",
        "net_pnl",
        "profit",
        "future_exit",
        "exit_price",
        "outcome",
        "exit_market_state",
        "future_exit_time",
        "label_end",
        "realized_return",
    }
    if forbidden & event.keys():
        raise ContractError("OUTCOME_ROW_NOT_PRODUCER_EVENT")
    if event.get("system_id") != binding.grammar:
        raise ContractError("PRODUCER_GRAMMAR_OWNER_MISMATCH")
    metadata = event.get("metadata", {})
    metadata = json.loads(metadata) if isinstance(metadata, str) else dict(metadata)
    if forbidden & metadata.keys():
        raise ContractError("OUTCOME_METADATA_NOT_CAUSAL_STATE")
    ready = instant(event["timestamp"])
    if ready.year not in {2022, 2023} or instant(binding.available_at) > ready:
        raise ContractError("PRODUCER_CLOCK_OR_PROTECTED_BOUNDARY")
    if (
        not metadata.get("invalidation_source")
        or metadata.get("stop") != binding.initial_invalidation
    ):
        raise ContractError("SOURCE_INITIAL_INVALIDATION_NOT_BOUND")
    owner_key = (
        metadata.get("count_id")
        if binding.grammar == "HYB_CORRECTIVE_COMPLETION_RESUMPTION"
        else metadata.get("owner_structure_id")
    )
    if owner_key != binding.structure_id:
        raise ContractError("PRODUCER_STRUCTURE_OWNER_NOT_BOUND")
    if any(instant(e.available_at) > ready for e in setup.evidence.values()):
        raise ContractError("PRODUCER_FUTURE_EVIDENCE")
    # Digest is lineage/tie-break only, never an alpha feature or pair whitelist.
    digest = hashlib.sha256(json.dumps(event, sort_keys=True, default=str).encode()).hexdigest()
    row = {
        "identity": digest,
        "pair": event["pair"],
        "owner_grammar": binding.grammar,
        "owner_structure_id": binding.structure_id,
        "count_id": metadata.get("count_id"),
        "pit_eligible": event.get("broad_eligible") is True,
    }
    return CandidateEnvelope(
        row,
        binding,
        Mode(mode),
        tuple(objectives),
        setup,
        tuple(metadata.get("required_evidence_ids", ())),
        state,
        ready,
        instant(valid_until),
        instant(context_known_at),
        context_source_sha256,
        partial_plan,
        staged,
        add_evidence,
        existing_campaign_id,
    )


class OwnedEventPipelineV7:
    def __init__(self, execution: CampaignExecutionV7, router: SourceBoundRouter):
        self.execution = execution
        self.router = router
        self.evidence = EvidenceStore()
        self.ledger: list[dict] = []
        self.last_open = None
        self.last_close = None

    def _bind(self, c: CandidateEnvelope, now, prices, capacities):
        if (
            instant(c.context_known_at) > now
            or len(c.context_source_sha256) != 64
            or any(ch not in "0123456789abcdefABCDEF" for ch in c.context_source_sha256)
        ):
            raise ContractError("CAUSAL_SOURCE_CONTEXT_REQUIRED")
        if not instant(c.ready_at) <= now < instant(c.valid_until):
            return None, "EVENT_EXPIRED_OR_NOT_READY"
        if c.setup.structure_id != c.binding.structure_id:
            raise ContractError("ENVELOPE_SETUP_OWNER_MISMATCH")
        if not c.required_events or not all(c.setup.live(e, now) for e in c.required_events):
            return None, "LIVE_PRODUCER_EVIDENCE_REQUIRED"
        allowed, reason = self.router.permission(c.binding.grammar, c.state)
        if not allowed:
            return None, reason
        pair = c.row["pair"]
        entry = prices.get(pair)
        if entry is None or not math.isfinite(entry) or entry <= 0:
            return None, "EXECUTABLE_OPEN_MISSING"
        cap = capacities.get(pair)
        if cap is None or not math.isfinite(cap) or cap <= 0:
            return None, "UNKNOWN_OR_ZERO_CAPACITY"
        c.binding.validate(now, entry)
        if (c.add_evidence is None) != (c.existing_campaign_id is None):
            raise ContractError("ADD_REQUIRES_SOURCE_AND_EXISTING_CAMPAIGN")
        if c.add_evidence is not None:
            if c.staged or c.partial_plan is not None:
                raise ContractError("ADD_CANNOT_RESET_STAGING_OR_PARTIAL_PLAN")
            execution = self.execution
            cid = c.existing_campaign_id
            if cid not in execution.staged_campaigns or execution.campaign_owner[cid] != c.binding:
                raise ContractError("ADD_CAMPAIGN_OWNER_MISMATCH")
            parent = [
                p for p in execution.portfolio.k.positions.values() if p["campaign_id"] == cid
            ]
            if not parent or any(p["episode"]["pair"] != pair for p in parent):
                raise ContractError("ADD_LIVE_ASSET_OWNER_REQUIRED")
            c.add_evidence.validate(c.binding, execution.campaign_entry[cid], now, entry)
        if c.row.get("owner_grammar") != c.binding.grammar:
            raise ContractError("ENTRY_GRAMMAR_MISMATCH")
        owner_key = (
            c.row.get("count_id")
            if c.binding.grammar == "HYB_CORRECTIVE_COMPLETION_RESUMPTION"
            else c.row.get("owner_structure_id")
        )
        if owner_key != c.binding.structure_id:
            raise ContractError("ENTRY_STRUCTURE_MISMATCH")
        objective_inputs = c.objectives
        if c.partial_plan is not None:
            c.partial_plan.validate(c.binding, now, entry, c.mode)
            objective_inputs = (c.partial_plan.final,)
        StructuralManager(
            c.binding,
            now,
            entry,
            c.mode,
            self.execution.portfolio.k.exit_cost_rate,
            self.execution.portfolio.k.exit_cost_rate,
            objective_inputs,
        )
        ident = c.row["identity"]
        if ident in self.evidence.records:
            return None, "THESIS_NO_RESURRECTION"
        # Translate the producer's entire live dependency graph transactionally.
        store = copy.deepcopy(self.evidence)
        ids = {}

        def register(eid):
            if eid in ids:
                return ids[eid]
            event: LiveEvidence = c.setup.evidence[eid]
            if not c.setup.live(eid, now):
                raise ContractError("INVALID_LIVE_PARENT")
            parents = tuple(
                ParentEdge(register(p), ParentEdgeType.LIVE_REQUIREMENT) for p in event.live_parents
            )
            sid = ident + "|" + eid
            store.register(
                EvidenceRecord(
                    sid,
                    "SOURCE_CAUSAL_EVIDENCE",
                    c.binding.structure_id,
                    instant(event.available_at),
                    instant(event.available_at),
                    c.binding.source_sha256,
                    instant(event.valid_until) if event.valid_until else None,
                    parent_edges=parents,
                )
            )
            ids[eid] = sid
            return sid

        required = tuple(register(e) for e in c.required_events)
        store.register(
            EvidenceRecord(
                ident,
                "COMPLETE_SOURCE_THESIS",
                c.binding.structure_id,
                now,
                now,
                c.binding.source_sha256,
                instant(c.valid_until),
                parent_edges=tuple(
                    ParentEdge(e, ParentEdgeType.LIVE_REQUIREMENT) for e in required
                ),
            )
        )
        equity = self.execution.portfolio.k.snapshot(lambda p, at: prices.get(p), now)["equity"]
        thesis = ThesisRecord(
            ident,
            c.binding.grammar,
            c.binding.structure_id,
            pair,
            instant(c.ready_at),
            "SOURCE_OWNED_TRIGGER",
            "OWNER_INVALIDATION",
            "AKAH_CAMPAIGN_EXECUTION_V7",
            0.005 * equity,
            required,
            float(cap) / equity,
            action_class="ADD" if c.add_evidence is not None else "NEW_ENTRY",
            funded_ready=True,
        )
        feasibility = Feasibility(
            thesis, c.state, bool(c.row.get("pit_eligible")), True, True, True, True
        )
        return (feasibility, store), "BOUND"

    def on_open(self, now, prices, capacities, candidates=(), *, research_authorized=False):
        if not research_authorized:
            raise ContractError("RESEARCH_AUTHORITY_REQUIRED")
        now = instant(now)
        if now.year not in {2022, 2023}:
            raise ContractError("PROTECTED_OR_UNAUTHORIZED_PERIOD")
        if self.last_open is not None and (now <= self.last_open or now != self.last_close):
            raise ContractError("EVENT_CLOCK_OR_MISSING_COMPLETED_HOUR")
        # Reject incomplete global marks before any fill or cash mutation.
        held = {p["episode"]["pair"] for p in self.execution.portfolio.k.positions.values()}
        if not held <= prices.keys() or any(
            not isinstance(prices[pair], (int, float))
            or not math.isfinite(prices[pair])
            or prices[pair] <= 0
            for pair in held
        ):
            raise ContractError("CURRENT_ALL_ASSET_MARKS_REQUIRED")
        caps = dict(capacities)
        self.execution.on_open(now, prices, caps)
        self.execution.restore_risk_at_open(now, prices, caps)
        bound, envelopes, rejected = [], {}, {}
        store = copy.deepcopy(self.evidence)
        for c in candidates:
            ident = c.row["identity"]
            if ident in envelopes:
                raise ContractError("DUPLICATE_THESIS_ID")
            envelopes[ident] = c
            # All envelopes validated before selecting, no best-looking first shortcut.
            old = self.evidence
            self.evidence = store
            try:
                pair, reason = self._bind(c, now, prices, caps)
            finally:
                self.evidence = old
            if pair is None:
                rejected[ident] = reason
                continue
            feasible, store = pair
            bound.append(feasible)
        owners = {
            p["episode"]["pair"]: p["episode"]["owner_structure_id"]
            for p in self.execution.portfolio.k.positions.values()
        }
        selected, denied = select_prebatch(bound, store, now, owners)
        rejected.update(denied)
        self.evidence = store
        for thesis in selected:
            c = envelopes[thesis.thesis_id]
            ok, reason = self.execution.admit_owned(
                c.row,
                c.binding,
                now,
                prices[c.row["pair"]],
                caps.get(c.row["pair"]),
                c.existing_campaign_id or thesis.thesis_id,
                mode=c.mode,
                objectives=c.objectives,
                partial_plan=c.partial_plan,
                staged=c.staged,
                add_evidence=c.add_evidence,
                prices=prices,
                research_authorized=True,
            )
            if ok:
                fill = self.execution.portfolio.k.fills[-1]
                caps[c.row["pair"]] -= fill["qty"] * fill["price"]
                if not c.setup.activate(c.required_events, now):
                    raise ContractError("ENTRY_EVIDENCE_CONSUMPTION_PARITY")
                for eid in thesis.supporting_evidence_ids:
                    store.records[eid].consume()
            else:
                rejected[thesis.thesis_id] = reason
            self.ledger.append(
                {
                    "time": now,
                    "identity": thesis.thesis_id,
                    "admitted": ok,
                    "reason": reason,
                    "owner": c.binding.owner,
                }
            )
        self.last_open = now
        return selected, rejected

    def on_completed_hour(
        self,
        bars: dict[str, CompletedBar],
        *,
        owner_bars=None,
        pivots=None,
        objectives=None,
        native_failures=None,
        capacities=None,
    ):
        if self.last_open is None:
            raise ContractError("COMPLETED_HOUR_WITHOUT_LEGAL_OPEN")
        from datetime import timedelta

        now = self.last_open + timedelta(hours=1)
        if now.year not in {2022, 2023}:
            raise ContractError("PROTECTED_COMPLETED_BAR")
        if self.last_close == now:
            raise ContractError("REPEATED_COMPLETED_HOUR")
        owner_bars, pivots = owner_bars or {}, pivots or {}
        objectives, native_failures = objectives or {}, native_failures or {}
        capacities = dict(capacities or {})
        held = {p["episode"]["pair"] for p in self.execution.portfolio.k.positions.values()}
        if not held <= bars.keys():
            raise ContractError("MISSING_HELD_COMPLETED_HOUR")
        for bar in bars.values():
            bar.validate()
            if instant(bar.start) != self.last_open or instant(bar.end) != now:
                raise ContractError("COMPLETED_HOUR_CLOCK")

        # Validate all held-owner updates before changing any real campaign cash.
        def arguments(execution, tid):
            p = execution.portfolio.k.positions[tid]
            pair = p["episode"]["pair"]
            owner = execution.managers[tid].binding.structure_id
            return pair, {
                "owner_bar": owner_bars.get(owner),
                "pivots": tuple(pivots.get(owner, ())),
                "objectives": tuple(objectives.get(owner, ())),
                "native_failure": native_failures.get(owner),
            }

        tids = list(self.execution.portfolio.k.positions)
        for tid in tids:
            pair, kw = arguments(self.execution, tid)
            self.execution.preview_close(tid, bars[pair], **kw)
        for tid in tids:
            pair, kw = arguments(self.execution, tid)
            self.execution.on_completed_hour(tid, bars[pair], capacities, **kw)
        self.last_close = now
