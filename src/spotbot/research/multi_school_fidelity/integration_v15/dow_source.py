"""Prospectively frozen AKAH Dow crypto standalone owner, not context relabeling."""
from dataclasses import dataclass
from datetime import timedelta
from ..integration_v10.stop_provenance import StopProof
from ..integration_v13.classical_source import LegacyEmission
from ..integration_v13.market_source import points_at, direction
from ..akah_replay_ready_detectors_v1 import event_row
from ..school_contract_common_v8 import Point, clock, digest, validate_points
from ..structural_lifecycle_v6 import Binding, DO, Mode, ContractError

@dataclass(frozen=True)
class DowStopProof(StopProof):
    def evaluate(self, graph, now):
        if self.kind != "DOW_CONFIRMED_SECONDARY_LOW" or len(self.source_ids) != 1:
            raise ContractError("DOW_SECONDARY_STOP_PROOF_REQUIRED")
        point = graph.require(graph.nodes[self.source_ids[0]].evidence, now).value
        if not isinstance(point, Point) or point.degree != "4H" or point.kind != "L":
            raise ContractError("DOW_ACTUAL_CONFIRMED_SECONDARY_LOW_REQUIRED")
        return point.price

class DowSource:
    def __init__(self, producer):
        self.producer, self.prefix, self.consumed = producer, producer.prefix, set()

    def close(self, bar, membership, permission):
        now = clock(bar.end)
        self.prefix.require_bar(bar, now)
        if bar.timeframe != "4H":
            raise ContractError("DOW_COMPLETED_SECONDARY_DEGREE_REQUIRED")
        if permission is None or not permission.permits(now) or permission.direction != "UP":
            return ()
        if direction(self.prefix, "1D", now) != "UP":
            return ()
        points = points_at(self.prefix, "4H", bar.start)
        if len(points) < 3:
            return ()
        a, h, b = points[-3:]
        if tuple(p.kind for p in (a, h, b)) != ("L", "H", "L") or b.price <= a.price:
            return ()
        try:
            validate_points((a, h, b), bar.start)
        except ContractError as exc:
            if str(exc) != "ORDERED_ALTERNATING_SWINGS_REQUIRED":
                raise
            return ()
        if bar.close <= h.price or bar.start < b.available_at:
            return ()
        sid = digest(("AKAH_V15_DOW_SECONDARY_RECONFIRMATION", self.prefix.pair, a, h, b))
        if sid in self.consumed:
            return ()
        parents = (a.event_id, h.event_id, b.event_id, self.prefix.bar_id(bar), membership.event_id)
        daily = points_at(self.prefix, "1D", now)
        parents += tuple(p.event_id for p in daily)
        claim = self.prefix.source_claim(digest((sid, "ENTRY", now)), "DOW_SECONDARY_RECONFIRMED",
            now, sid, parents, self.prefix.sha)
        proof = DowStopProof("DOW_CONFIRMED_SECONDARY_LOW", (b.event_id,))
        binding = Binding(DO, DO, sid, self.prefix.sha, "4H", now, b.price, b.event_id)
        meta = {"structure_id": sid, "owner_structure_id": sid, "owner_grammar": DO,
                "required_evidence_ids": (*parents, claim.event_id), "invalidation_source": b.event_id,
                "invalidation_derivation": proof.kind, "stop": b.price,
                "known_at": now.isoformat(), "applies_from": now.isoformat(),
                "profile": "AKAH_V15_DOW_STANDALONE_ADAPTATION"}
        event = event_row(DO, self.prefix.pair, now, "SECONDARY_RECONFIRMATION", "THESIS_INTENT",
                          membership.value.eligible, meta)
        issue = self.producer.seal_legacy(event, binding, proof, membership)
        self.consumed.add(sid)
        return (LegacyEmission(issue, binding, proof, (), Mode.TREND),)
