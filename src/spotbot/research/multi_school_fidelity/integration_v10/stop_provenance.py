"""Immutable executable stop derivations, not generic parent ordering."""

from dataclasses import dataclass

from ..harmonic_contract_v8 import HarmonicContract
from ..school_contract_common_v8 import Known, clock, digest
from ..structural_lifecycle_v6 import ContractError


@dataclass(frozen=True)
class StopProof:
    kind: str
    source_ids: tuple[str, ...]

    def evaluate(self, graph, now):
        now = clock(now)
        if not self.source_ids or len(set(self.source_ids)) != len(self.source_ids):
            raise ContractError("EXPLICIT_UNIQUE_STOP_SOURCES_REQUIRED")
        values = []
        for eid in self.source_ids:
            if not graph.live(eid, now):
                raise ContractError("STOP_SOURCE_INVALIDATED_OR_EXPIRED")
            values.append(graph.nodes[eid].evidence.value)
        if self.kind in {"RAID_LOW", "SPRING_LOW", "LPS_LOW", "CLASSICAL_ACCEPTANCE_LOW"}:
            if len(values) != 1 or not isinstance(values[0], tuple) or len(values[0]) != 2:
                raise ContractError("STOP_COMPLETED_BAR_SOURCE_REQUIRED")
            return values[0][0].low
        if self.kind == "PROTECTED_LEVEL":
            if (
                len(values) != 1
                or isinstance(values[0], bool)
                or not isinstance(values[0], (float, int))
            ):
                raise ContractError("STOP_PROTECTED_LEVEL_SOURCE_REQUIRED")
            return float(values[0])
        if self.kind == "CLASSICAL_CONFIRMED_LOW":
            if len(values) != 1 or getattr(values[0], "kind", None) != "L":
                raise ContractError("STOP_CONFIRMED_LOW_SOURCE_REQUIRED")
            return values[0].price
        if self.kind == "ELLIOTT_COMMON_PARENT_FLOOR":
            floors = []
            counts = [v for v in values if hasattr(v, "parent_prefix")]
            points = [v for v in values if hasattr(v, "kind") and hasattr(v, "price")]
            if not counts or len(counts) + len(points) != len(values):
                raise ContractError("COUNT_AND_EXACT_PARENT_FLOOR_SOURCES_REQUIRED")
            for count in counts:
                count.validate(now)
                if count.correction.sign != -1:
                    raise ContractError("LONG_COUNT_STOP_REQUIRED")
                index = 1 if count.leg_name == "W4" else 0
                point = count.parent_prefix.points[index]
                if point not in points:
                    raise ContractError("COUNT_PARENT_FLOOR_NOT_IN_STOP_GRAPH")
                floor = point.price
                if floor != count.invalidation:
                    raise ContractError("COUNT_STOP_PARENT_PARITY")
                floors.append(floor)
            return max(floors)
        if self.kind == "HARMONIC_FROZEN_PROFILE_STOP":
            p = values[0]
            bars = [x[0] for x in values[1:]]
            if not bars or any(b.start < p.available_at for b in bars):
                raise ContractError("HARMONIC_TRAVERSAL_SOURCE_REQUIRED")
            m = HarmonicContract(p)
            m.terminal_extreme = (
                min(b.low for b in bars) if p.sign == 1 else max(b.high for b in bars)
            )
            value = m._stop(bars[-1])
            if value is None:
                raise ContractError("HARMONIC_PROFILE_STOP_INVALID")
            return value
        raise ContractError("UNSUPPORTED_STOP_DERIVATION")

    def bind(self, graph, thesis, now):
        value = self.evaluate(graph, now)
        if value != thesis.initial_invalidation:
            raise ContractError("SEMANTIC_STOP_PRICE_PARITY_REQUIRED")
        # Earliest complete availability; repeated staged adds reuse the exact
        # original stop claim, not a new binding with a fresh risk budget.
        available = max(graph.nodes[e].evidence.available_at for e in self.source_ids)
        eid = digest(("V10_STOP", thesis.owner, thesis.structure_id, self))
        claim = Known(eid, self, available, thesis.source_sha256, thesis.structure_id)
        if eid in graph.nodes:
            graph.require(claim, now)
        else:
            graph.register(claim, self.source_ids, origin="DETECTOR_GEOMETRY")
        return claim

    def validate_owner(self, thesis):
        permitted = {
            "ICT_SESSION": {"RAID_LOW"},
            "H2_4H_STRUCTURE": {"PROTECTED_LEVEL"},
            "WYCKOFF_RANGE_OWNER": {"SPRING_LOW", "LPS_LOW"},
            "HARMONIC_TYPE_I": {"HARMONIC_FROZEN_PROFILE_STOP"},
            "HARMONIC_TYPE_II": {"HARMONIC_FROZEN_PROFILE_STOP"},
            "ELLIOTT_COMMON_COUNT_OWNER": {"ELLIOTT_COMMON_PARENT_FLOOR"},
        }
        if self.kind not in permitted.get(thesis.owner, set()):
            raise ContractError("STOP_DERIVATION_WRONG_OWNER")
