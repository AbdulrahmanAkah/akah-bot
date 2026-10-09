"""Actual source adapters -> V8 finite proof contracts -> causal event_row.

Legacy intents are not proofs. This opt-in producer leaves unsupported evidence
unfunded rather than padding a count, PNF cause or family table with defaults.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace

from ..akah_replay_ready_detectors_v1 import event_row
from ..harmonic_contract_v8 import HarmonicContract, project
from ..ict_h2_contract_v8 import bind_entry
from ..integration_v9.sources import CompletedPrefix
from ..live_dow_context_v7 import LiveDowContextV7
from ..school_contract_common_v8 import Known, SchoolThesis, clock, digest
from ..structural_lifecycle_v6 import ContractError, instant
from ..wyckoff_contract_v8 import Readiness, SpringStage, WyckoffContract
from .elliott_scope import PROFILE, ElliottBook, check_count
from .stop_provenance import StopProof

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
    stop_proof: StopProof | None = None
    stop_claim_id: str | None = None


class ContractProducer:
    def __init__(self, prefix: CompletedPrefix):
        self.prefix = prefix
        self.graph = prefix.graph
        self.harmonics: dict[str, HarmonicContract] = {}
        self.elliott = ElliottBook()
        self.wyckoff: dict[str, WyckoffContract] = {}
        self.dow = LiveDowContextV7()
        self.emitted: dict[str, Produced] = {}
        self.stage_stop_proofs = {}
        self.harmonic_projection_sources = {}
        self.stage_campaign_receipts = {}

    def _claim(self, eid, value, now, structure, parents):
        e = Known(eid, value, now, self.prefix.sha, structure)
        if eid in self.graph.nodes:
            return self.graph.require(e, now)
        return self.graph.register(e, parents, origin="DETECTOR_GEOMETRY")

    def _emit(
        self, thesis, *, pit_eligible, stop_proof, staged=False, extra=(), add_instruction=None
    ):
        if not isinstance(pit_eligible, bool):
            raise ContractError("EXPLICIT_PIT_MEMBERSHIP_REQUIRED")
        now = clock(add_instruction["known_at"] if add_instruction else thesis.available_at)
        stop_proof.validate_owner(thesis)
        stop_claim = stop_proof.bind(self.graph, thesis, now)
        thesis = replace(
            thesis,
            parents=tuple(
                dict.fromkeys((*thesis.parents, stop_claim.event_id, *stop_proof.source_ids))
            ),
        )
        ids = tuple(dict.fromkeys((*thesis.parents, *extra)))
        if not ids or not all(self.graph.live(e, now) for e in ids):
            raise ContractError("COMPLETE_LIVE_PRODUCER_PROOF_REQUIRED")
        meta = {
            "owner_structure_id": thesis.structure_id,
            "stop": thesis.initial_invalidation,
            "invalidation_source": stop_claim.event_id,
            "invalidation_source_ids": stop_proof.source_ids,
            "invalidation_derivation": stop_proof.kind,
            "required_evidence_ids": ids,
            "management_owner": thesis.owner,
            "management_degree": thesis.management_degree,
            "management_mode": thesis.mode,
            "producer_version": "V10",
            "elliott_profile": PROFILE if thesis.grammar in {ELLIOTT, H3} else None,
            "funded_ready": False,
            "economic_qualified": False,
        }
        row = event_row(
            thesis.grammar, self.prefix.pair, now, thesis.owner, "INTENT", pit_eligible, meta
        )
        result = Produced(
            thesis, row, ids, staged, add_instruction, stop_proof, stop_claim.event_id
        )
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
        claim = self._claim(
            digest((projection.structure_id, "PROJECTION_V10")),
            projection,
            projection.available_at,
            projection.structure_id,
            tuple(p.event_id for p in points) + (atr.event_id,),
        )
        self.harmonic_projection_sources[projection.structure_id] = claim.event_id
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
            traversal = tuple(
                self.prefix.bar_id(b)
                for b in self.prefix.bars[bar.timeframe]
                if projected.projection.available_at <= b.start and b.end <= projected.terminal.end
            )
            proof = StopProof(
                "HARMONIC_FROZEN_PROFILE_STOP", (self.harmonic_projection_sources[sid], *traversal)
            )
            result = self._emit(thesis, pit_eligible=pit_eligible, stop_proof=proof)
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
        check_count(count)
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
        if thesis:
            floor_ids = tuple(
                self.elliott.counts[cid]
                .parent_prefix.points[1 if self.elliott.counts[cid].leg_name == "W4" else 0]
                .event_id
                for cid in thesis.parents
            )
            proof = StopProof(
                "ELLIOTT_COMMON_PARENT_FLOOR", tuple(dict.fromkeys((*thesis.parents, *floor_ids)))
            )
            result = self._emit(thesis, pit_eligible=pit_eligible, stop_proof=proof)
        else:
            result = None
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
        readiness_ids = self._readiness_ids(readiness, bars, now)
        stop_proof = StopProof(
            "SPRING_LOW" if branch == "SPRING_TEST" else "LPS_LOW",
            (
                self.prefix.bar_id(
                    readiness.spring.bar if branch == "SPRING_TEST" else readiness.lps.bar
                ),
            ),
        )
        proof_ids = (
            *readiness_ids,
            count_line.event_id,
            readiness.market.event_id,
            readiness.rs.event_id,
            *(e.event_id for e in readiness.branch_events),
            *(s.event_id for s in segments),
        )
        result = (
            self._emit(
                thesis,
                pit_eligible=pit_eligible,
                staged=branch == "SPRING_TEST",
                extra=proof_ids,
                stop_proof=stop_proof,
            )
            if thesis
            else None
        )
        self.wyckoff[sid] = projected
        if result and branch == "SPRING_TEST":
            self.stage_stop_proofs[sid] = stop_proof
        return result

    def _readiness_ids(self, readiness, bars, now):
        ids = [self.prefix.require_bar(b, now) for b in bars]
        if isinstance(readiness, SpringStage):
            acts = (readiness.spring, readiness.test, readiness.confirmation)
        else:
            ids.extend(
                self.prefix.require_point(p, now)
                for p in (*readiness.falling_highs, *readiness.range_swings)
            )
            acts = (readiness.supply_reference, readiness.supply_test, readiness.sos, readiness.lps)
        ids.extend(self.prefix.require_bar(a.bar, now, a.volume) for a in acts)
        return tuple(dict.fromkeys(ids))

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
        proof = (
            StopProof("RAID_LOW", (self.prefix.bar_id(chain.raid),))
            if mode == "FS_ICT_SESSION_OWNER_V8"
            else StopProof("PROTECTED_LEVEL", (protected.event_id,))
        )
        return self._emit(thesis, pit_eligible=pit_eligible, extra=tuple(ids), stop_proof=proof)

    def wyckoff_add(self, sid, now, entry, readiness, bars, segments, count_line, *, pit_eligible):
        now = clock(now)
        if sid not in self.stage_campaign_receipts:
            raise ContractError("WYCKOFF_ACTUAL_STAGE_FILL_RECEIPT_REQUIRED")
        receipt = self.stage_campaign_receipts[sid]
        self.graph.require(receipt, now)
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
        instruction = dict(instruction, source_campaign_id=sid, campaign_id=receipt.value[1])
        result = self._emit(
            projected.stage1,
            pit_eligible=pit_eligible,
            extra=(
                receipt.event_id,
                *self._readiness_ids(readiness, bars, now),
                count_line.event_id,
                *(e.event_id for e in proof),
                *(s.event_id for s in segments),
            ),
            add_instruction=instruction,
            stop_proof=self.stage_stop_proofs[sid],
        )
        self.wyckoff[sid] = projected
        return result

    def acknowledge_wyckoff_stage(self, sid, receipt, now):
        self.graph.require(receipt, now)
        if (
            sid not in self.wyckoff
            or self.wyckoff[sid].stage1 is None
            or receipt.structure_id != sid
            or receipt.value[0] != "WYCKOFF_STAGE1_FILLED"
            or receipt.available_at != self.wyckoff[sid].stage1.available_at
            or sid in self.stage_campaign_receipts
        ):
            raise ContractError("EXACT_WYCKOFF_STAGE_FILL_AUTHORITY_REQUIRED")
        self.stage_campaign_receipts[sid] = receipt

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
            stop_proof=count_intent.stop_proof,
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
