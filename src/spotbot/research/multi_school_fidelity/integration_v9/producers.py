"""Actual source adapters -> V8 finite proof contracts -> causal event_row.

Legacy intents are not proofs. This opt-in producer leaves unsupported evidence
unfunded rather than padding a count, PNF cause or family table with defaults.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace

from ..akah_replay_ready_detectors_v1 import event_row
from ..elliott_contract_v8 import ElliottBook
from ..harmonic_contract_v8 import HarmonicContract, project
from ..ict_h2_contract_v8 import bind_entry
from ..live_dow_context_v7 import LiveDowContextV7
from ..school_contract_common_v8 import Known, SchoolThesis, clock, digest
from ..structural_lifecycle_v6 import ContractError, instant
from ..wyckoff_contract_v8 import Readiness, SpringStage, WyckoffContract
from .sources import CompletedPrefix

HARMONIC = "FS_HARMONIC_CAUSAL_ADAPTATION_V8"
ELLIOTT = "FS_ELLIOTT_PROOF_RESUMPTION_V8"
WYCKOFF = "FS_WYCKOFF_FRESH_CAUSE_V8"
H3 = "HYB_CORRECTIVE_PROOF_LOCATION_V9"


@dataclass(frozen=True)
class Produced:
    thesis: SchoolThesis
    event: dict
    evidence_ids: tuple[str, ...]
    staged: bool = False
    add_instruction: dict | None = None


class ContractProducer:
    def __init__(self, prefix: CompletedPrefix):
        self.prefix = prefix
        self.graph = prefix.graph
        self.harmonics: dict[str, HarmonicContract] = {}
        self.elliott = ElliottBook()
        self.wyckoff: dict[str, WyckoffContract] = {}
        self.dow = LiveDowContextV7()
        self.emitted: dict[str, Produced] = {}

    def _claim(self, eid, value, now, structure, parents):
        e = Known(eid, value, now, self.prefix.sha, structure)
        if eid in self.graph.nodes:
            return self.graph.require(e, now)
        return self.graph.register(e, parents, origin="DETECTOR_GEOMETRY")

    def _emit(self, thesis, *, pit_eligible, staged=False, extra=(), add_instruction=None):
        if not isinstance(pit_eligible, bool):
            raise ContractError("EXPLICIT_PIT_MEMBERSHIP_REQUIRED")
        now = clock(add_instruction["known_at"] if add_instruction else thesis.available_at)
        ids = tuple(dict.fromkeys((*thesis.parents, *extra)))
        if not ids or not all(self.graph.live(e, now) for e in ids):
            raise ContractError("COMPLETE_LIVE_PRODUCER_PROOF_REQUIRED")
        meta = {
            "owner_structure_id": thesis.structure_id,
            "stop": thesis.initial_invalidation,
            "invalidation_source": thesis.parents[0],
            "required_evidence_ids": ids,
            "management_owner": thesis.owner,
            "management_degree": thesis.management_degree,
            "management_mode": thesis.mode,
            "producer_version": "V9",
            "funded_ready": False,
            "economic_qualified": False,
        }
        row = event_row(
            thesis.grammar, self.prefix.pair, now, thesis.owner, "INTENT", pit_eligible, meta
        )
        result = Produced(thesis, row, ids, staged, add_instruction)
        self.emitted[digest(result)] = copy.deepcopy(result)
        return result

    def start_harmonic(self, family, points, atr, tick, now):
        for p in points:
            self.prefix.require_point(p, now)
        self.graph.require(atr, now)
        # Never convert old classify_harmonic output into a new projection.
        projection = project(family, tuple(points), now, atr, tick)
        if projection.structure_id in self.harmonics:
            raise ContractError("PROJECTION_NO_RESURRECTION")
        self.harmonics[projection.structure_id] = HarmonicContract(projection)
        return projection.structure_id

    def harmonic_close(self, sid, bar, *, pit_eligible):
        pid = self.prefix.require_bar(bar, bar.end)
        original = self.harmonics[sid]
        projected = copy.deepcopy(original)
        thesis = projected.on_close(bar)
        # Register native V8 terminal/confirmation IDs, with exact source bars.
        if projected.terminal is not None:
            terminal = projected.terminal
            terminal_id = digest((sid, terminal.start, terminal.end))
            if terminal_id not in self.graph.nodes:
                self._claim(
                    terminal_id, terminal, terminal.end, sid, (self.prefix.bar_id(terminal),)
                )
        if thesis is not None:
            # V8 contract-local hashes intentionally omit asset/family. Namespace
            # these two detector events in the shared graph, not the price pivots.
            terminal_id = digest((sid, projected.terminal.start, projected.terminal.end))
            confirmation = digest((sid, thesis.parents[-1]))
            thesis = replace(thesis, parents=(*thesis.parents[:-2], terminal_id, confirmation))
            self._claim(confirmation, bar, bar.end, sid, (pid, *thesis.parents[:-1]))
            result = self._emit(thesis, pit_eligible=pit_eligible)
        else:
            result = None
        self.harmonics[sid] = projected
        return result

    def acknowledge_harmonic_completion(self, sid, owner, at, *, execution_receipt):
        receipt = self.graph.require(execution_receipt, at)
        if receipt.structure_id != sid or receipt.value != ("CAMPAIGN_CLOSED", owner):
            raise ContractError("SOURCE_EXECUTION_COMPLETION_RECEIPT_REQUIRED")
        m = self.harmonics[sid]
        if owner == "HARMONIC_TYPE_I":
            m.complete_type1(at)
        elif owner == "HARMONIC_TYPE_II":
            m.complete_type2()
        else:
            raise ContractError("HARMONIC_EXECUTION_OWNER_REQUIRED")

    def _wave(self, wave, now):
        wave.validate(now)
        ids = [self.prefix.require_point(p, now) for p in wave.points]
        for child in wave.children:
            ids.append(self._wave(child, now))
        available = max(
            [instant(p.available_at) for p in wave.points]
            + [instant(self.graph.nodes[e].evidence.available_at) for e in ids]
        )
        self._claim(wave.wave_id, wave, available, wave.wave_id, tuple(ids))
        return wave.wave_id

    def add_elliott_count(self, count, now):
        count.validate(now)
        for p in (*count.parent_prefix.points, count.parent_start, count.parent_end):
            self.prefix.require_point(p, now)
        ids = [self._wave(count.correction, now)]
        ids.extend(self._wave(w, now) for w in count.parent_prefix.children)
        self.graph.require(count.objective, now)
        ids.append(count.objective.event_id)
        self._claim(count.count_id, count, now, count.parent_id, tuple(ids))
        self.elliott.add(count, now)

    def elliott_close(self, bar, claim, *, pit_eligible):
        self.prefix.require_bar(bar, bar.end)
        if not self.elliott.counts:
            raise ContractError("PROOF_COUNTS_NOT_LEGACY_DIAGNOSTIC_REQUIRED")
        for cid in self.elliott.counts:
            if not self.graph.live(cid, bar.end) and cid not in self.elliott.tombstones:
                self.elliott.tombstones.add(cid)
        projected = copy.deepcopy(self.elliott)
        thesis = projected.decide(bar.end, bar.close, claim)
        result = self._emit(thesis, pit_eligible=pit_eligible) if thesis else None
        self.elliott = projected
        return result

    def _activity(self, activity, now):
        self.prefix.require_bar(activity.bar, now, activity.volume)

    def start_wyckoff(self, cause, now):
        cause.validate(now)
        self.graph.require(cause.authority, now)
        if cause.prior_markup:
            self.graph.require(cause.prior_markup, now)
        if cause.cause_id in self.wyckoff:
            raise ContractError("CAUSE_NO_RESURRECTION")
        self.wyckoff[cause.cause_id] = WyckoffContract(cause)

    def wyckoff_intent(
        self, sid, now, entry, readiness, bars, segments, count_line, *, branch, pit_eligible
    ):
        now = clock(now)
        contract = self.wyckoff[sid]
        if not isinstance(readiness, SpringStage if branch == "SPRING_TEST" else Readiness):
            raise ContractError("TYPED_PRODUCER_READINESS_REQUIRED")
        self.graph.require(contract.cause.authority, now)
        self.graph.require(count_line, now)
        for b in bars:
            self.prefix.require_bar(b, now)
        for s in segments:
            if (
                not self.graph.live(s.event_id, now)
                or self.graph.nodes[s.event_id].evidence.value != s
            ):
                raise ContractError("SOURCE_OWNED_PNF_SEGMENT_REQUIRED")
        for e in (readiness.market, readiness.rs, *readiness.branch_events):
            self.graph.require(e, now)
        if branch == "SPRING_TEST":
            for a in (readiness.spring, readiness.test, readiness.confirmation):
                self._activity(a, now)
        else:
            for p in (*readiness.falling_highs, *readiness.range_swings):
                self.prefix.require_point(p, now)
            for a in (
                readiness.supply_reference,
                readiness.supply_test,
                readiness.sos,
                readiness.lps,
            ):
                self._activity(a, now)
        projected = copy.deepcopy(contract)
        if branch == "SPRING_TEST":
            thesis = projected.spring_intent(now, entry, readiness, bars, segments, count_line)
        else:
            thesis = projected.intent(now, entry, readiness, bars, segments, count_line, branch)
        proof_ids = (
            readiness.market.event_id,
            readiness.rs.event_id,
            *(e.event_id for e in readiness.branch_events),
            *(s.event_id for s in segments),
        )
        result = (
            self._emit(
                thesis, pit_eligible=pit_eligible, staged=branch == "SPRING_TEST", extra=proof_ids
            )
            if thesis
            else None
        )
        self.wyckoff[sid] = projected
        return result

    def ict_intent(
        self, chain, now, entry, mode, *, pit_eligible, daily=None, acceptance=None, protected=None
    ):
        ids = []
        for b in (chain.raid, chain.mss, chain.retracement):
            ids.append(self.prefix.require_bar(b, now))
        for e in (
            chain.liquidity,
            chain.internal_high,
            chain.fvg,
            chain.opposing_liquidity,
            chain.session_end,
        ):
            self.graph.require(e, now)
            ids.append(e.event_id)
        if self.graph.nodes[chain.fvg.event_id].origin != "DETECTOR_GEOMETRY":
            raise ContractError("ACTUAL_THREE_BAR_FVG_PROVENANCE_REQUIRED")
        if acceptance is not None:
            ids.append(self.prefix.require_bar(acceptance, now))
        for e in (daily, protected):
            if e is not None:
                self.graph.require(e, now)
                ids.append(e.event_id)
        thesis = bind_entry(
            chain, now, entry, mode, daily=daily, acceptance=acceptance, protected=protected
        )
        return self._emit(thesis, pit_eligible=pit_eligible, extra=tuple(ids))

    def wyckoff_add(self, sid, now, entry, readiness, bars, segments, count_line, *, pit_eligible):
        now = clock(now)
        contract = self.wyckoff[sid]
        if not isinstance(readiness, Readiness):
            raise ContractError("TYPED_PRODUCER_READINESS_REQUIRED")
        self.graph.require(contract.cause.authority, now)
        self.graph.require(count_line, now)
        for b in bars:
            self.prefix.require_bar(b, now)
        for p in (*readiness.falling_highs, *readiness.range_swings):
            self.prefix.require_point(p, now)
        for a in (readiness.supply_reference, readiness.supply_test, readiness.sos, readiness.lps):
            self._activity(a, now)
        proof = (readiness.market, readiness.rs, *readiness.branch_events)
        for e in proof:
            self.graph.require(e, now)
        for s in segments:
            if (
                not self.graph.live(s.event_id, now)
                or self.graph.nodes[s.event_id].evidence.value != s
            ):
                raise ContractError("SOURCE_OWNED_PNF_SEGMENT_REQUIRED")
        projected = copy.deepcopy(contract)
        instruction = projected.lps_add(now, entry, readiness, bars, segments, count_line)
        if instruction is None:
            return None
        result = self._emit(
            projected.stage1,
            pit_eligible=pit_eligible,
            extra=(
                count_line.event_id,
                *(e.event_id for e in proof),
                *(s.event_id for s in segments),
            ),
            add_instruction=instruction,
        )
        self.wyckoff[sid] = projected
        return result

    def h3(self, count_intent, location_intent, *, pit_eligible):
        if any(self.emitted.get(digest(x)) != x for x in (count_intent, location_intent)):
            raise ContractError("PRODUCER_EMITTED_COUNT_AND_LOCATION_REQUIRED")
        c, h = count_intent.thesis, location_intent.thesis
        if c.grammar != ELLIOTT or h.grammar != HARMONIC or c.available_at != h.available_at:
            raise ContractError("SAME_CHECKPOINT_COUNT_AND_LOCATION_REQUIRED")
        if c.side != "LONG" or h.side != "LONG" or c.initial_invalidation > h.initial_invalidation:
            raise ContractError("COUNT_INVALIDATION_CONFLICTS_WITH_LOCATION")
        thesis = replace(
            c,
            grammar=H3,
            parents=tuple(dict.fromkeys((*c.parents, *h.parents))),
            adaptation="COUNT_OWNS_THESIS_HARMONIC_LOCATION_ONLY_V9",
        )
        return self._emit(
            thesis,
            pit_eligible=pit_eligible,
            extra=tuple(dict.fromkeys((*count_intent.evidence_ids, *location_intent.evidence_ids))),
        )

    def dow_close(self, now, *, primary, secondary, broad_confirmation, volume):
        for e in (primary, secondary, broad_confirmation, volume):
            # Existing wrapper consumes KnownObservation; match a bound graph node.
            if not any(
                n.evidence.available_at == e.available_at
                and n.evidence.source_sha256 == e.source_sha256
                and n.evidence.value == e.value
                and self.graph.live(k, now)
                for k, n in self.graph.nodes.items()
            ):
                raise ContractError("DOW_SOURCE_OBSERVATION_NOT_BOUND")
        return self.dow.on_completed_4h(
            now,
            primary=primary,
            secondary=secondary,
            broad_confirmation=broad_confirmation,
            volume=volume,
        )
