"""Proof-carrying finite Elliott profile. Unsupported counts are diagnostic.

Degrees are AKAH timeframe proxies. Lowest-degree geometric leaves are an
explicit finite resolution, not a certificate of unseen sub-degree waves.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .school_contract_common_v8 import (
    Known,
    Point,
    SchoolThesis,
    clock,
    digest,
    price,
    valid_sha,
    validate_points,
)
from .structural_lifecycle_v6 import ContractError, instant

LEGS = {"IMPULSE": 5, "ZIGZAG": 3, "FLAT": 3, "TRIANGLE": 5, "DOUBLE_THREE": 3, "TRIPLE_THREE": 5}
CORRECTIVE = frozenset(LEGS) - {"IMPULSE"}
CHILD_DEGREE = {"1D": "4H", "4H": "1H"}


@dataclass(frozen=True)
class Wave:
    wave_id: str
    kind: str
    degree: str
    points: tuple[Point, ...]
    children: tuple[Wave, ...]
    source_sha256: str

    @property
    def sign(self):
        return 1 if self.points[-1].price > self.points[0].price else -1

    def validate(self, now, visiting=frozenset()):
        now = clock(now)
        valid_sha(self.source_sha256)
        if not self.wave_id or self.wave_id in visiting:
            raise ContractError("WAVE_ID_OR_CYCLE")
        if self.kind not in LEGS:
            raise ContractError("UNSUPPORTED_WAVE_DIAGNOSTIC")
        if len(self.points) != LEGS[self.kind] + 1:
            raise ContractError("COMPLETE_WAVE_GRAMMAR_REQUIRED")
        validate_points(self.points, now)
        if any(p.degree != self.degree for p in self.points):
            raise ContractError("WAVE_POINT_DEGREE")
        s = self.sign
        z = [s * p.price for p in self.points]
        if self.kind == "IMPULSE":
            if not (z[0] < z[2] < z[1] < z[4] < z[3] < z[5]):
                raise ContractError("IMPULSE_ORIGIN_OVERLAP_OR_EXTENSION")
            lengths = (z[1] - z[0], z[3] - z[2], z[5] - z[4])
            if lengths[1] < min(lengths[0], lengths[2]):
                raise ContractError("WAVE_THREE_SHORTEST")
        elif self.kind == "ZIGZAG":
            if not (z[0] < z[2] < z[1] and z[3] > z[1]):
                raise ContractError("ZIGZAG_B_OR_C_GEOMETRY")
        elif self.kind == "FLAT":
            # Frozen bounded regular/expanded profile, not every running flat.
            if not (0.9 <= abs(z[2] - z[1]) / abs(z[1] - z[0]) <= 1.382 and z[3] > z[1]):
                raise ContractError("FLAT_PROFILE_GEOMETRY")
        elif self.kind == "TRIANGLE":
            highs = [p.price for p in self.points if p.kind == "H"]
            lows = [p.price for p in self.points if p.kind == "L"]
            if not (
                all(b < a for a, b in zip(highs[:-1], highs[1:], strict=True))
                and all(b > a for a, b in zip(lows[:-1], lows[1:], strict=True))
            ):
                raise ContractError("CONTRACTING_TRIANGLE_PROFILE")
        if self.degree == "1H":
            if self.children or self.kind in {"DOUBLE_THREE", "TRIPLE_THREE"}:
                raise ContractError("SUBDEGREE_PROOF_UNAVAILABLE_DIAGNOSTIC")
            return
        if self.degree not in CHILD_DEGREE or len(self.children) != LEGS[self.kind]:
            raise ContractError("SUBDIVISION_PROOF_REQUIRED")
        expected = {
            "IMPULSE": ("M", "C", "M", "C", "M"),
            "ZIGZAG": ("M", "C", "M"),
            "FLAT": ("C", "C", "M"),
        }.get(self.kind, tuple("C" for _ in self.children))
        for i, (child, role) in enumerate(zip(self.children, expected, strict=True)):
            child.validate(now, visiting | {self.wave_id})
            a, b = self.points[i : i + 2]
            ca, cb = child.points[0], child.points[-1]
            if (
                child.degree != CHILD_DEGREE[self.degree]
                or (ca.observed_at, ca.price) != (a.observed_at, a.price)
                or (cb.observed_at, cb.price) != (b.observed_at, b.price)
            ):
                raise ContractError("NAMED_PARENT_LEG_ENDPOINT_OR_DEGREE")
            if (role == "M" and child.kind != "IMPULSE") or (
                role == "C" and child.kind not in CORRECTIVE
            ):
                raise ContractError("WRONG_CHILD_SUBDIVISION_GRAMMAR")


@dataclass(frozen=True)
class ParentPrefix:
    parent_id: str
    degree: str
    points: tuple[Point, ...]
    children: tuple[Wave, ...]

    def validate(self, now, leg):
        n = {"W2": 1, "W4": 3, "ABC": 5}.get(leg)
        if n is None or self.degree not in CHILD_DEGREE or len(self.points) != n + 1:
            raise ContractError("MOTIVE_PARENT_PREFIX_REQUIRED")
        validate_points(self.points, now)
        if any(p.degree != self.degree for p in self.points) or len(self.children) != n:
            raise ContractError("PARENT_PREFIX_DEGREE_OR_SUBDIVISION")
        for i, w in enumerate(self.children):
            w.validate(now)
            a, b = self.points[i : i + 2]
            if (
                w.degree != CHILD_DEGREE[self.degree]
                or (w.points[0].observed_at, w.points[0].price) != (a.observed_at, a.price)
                or (w.points[-1].observed_at, w.points[-1].price) != (b.observed_at, b.price)
                or (w.kind != "IMPULSE" if i % 2 == 0 else w.kind not in CORRECTIVE)
            ):
                raise ContractError("PARENT_PREFIX_CHILD_GRAMMAR_OR_ENDPOINT")
        s = 1 if self.points[1].price > self.points[0].price else -1
        z = [s * p.price for p in self.points]
        if n >= 3 and not z[0] < z[2] < z[1] < z[3]:
            raise ContractError("PARENT_W2_OR_W3_INVALID")
        if n == 5:
            Wave(
                self.parent_id,
                "IMPULSE",
                self.degree,
                self.points,
                self.children,
                self.children[0].source_sha256,
            ).validate(now)


@dataclass(frozen=True)
class ResumeCount:
    count_id: str
    parent_id: str
    parent_degree: str
    leg_name: str
    parent_start: Point
    parent_end: Point
    correction: Wave
    invalidation: float
    objective: Known
    parent_prefix: ParentPrefix

    def validate(self, now):
        self.correction.validate(now)
        self.parent_prefix.validate(now, self.leg_name)
        validate_points((self.parent_start, self.parent_end), now)
        if (
            self.leg_name not in {"W2", "W4", "ABC"}
            or not self.parent_id
            or not self.count_id
            or self.correction.kind not in CORRECTIVE
            or CHILD_DEGREE.get(self.parent_degree) != self.correction.degree
            or any(p.degree != self.parent_degree for p in (self.parent_start, self.parent_end))
        ):
            raise ContractError("OWNER_COUNT_PARENT_GRAMMAR")
        prefix = self.parent_prefix
        if (
            prefix.parent_id != self.parent_id
            or prefix.degree != self.parent_degree
            or prefix.points[-1] != self.parent_start
        ):
            raise ContractError("PARENT_PREFIX_NOT_THIS_CORRECTION")
        a, b = self.correction.points[0], self.correction.points[-1]
        if (a.observed_at, a.price) != (self.parent_start.observed_at, self.parent_start.price) or (
            b.observed_at,
            b.price,
        ) != (self.parent_end.observed_at, self.parent_end.price):
            raise ContractError("CORRECTION_NOT_NAMED_PARENT_LEG")
        parent_sign = 1 if prefix.points[1].price > prefix.points[0].price else -1
        floor = prefix.points[1].price if self.leg_name == "W4" else prefix.points[0].price

        def all_prices(w):
            return [p.price for p in w.points] + [
                v for child in w.children for v in all_prices(child)
            ]

        extreme = (
            min(all_prices(self.correction))
            if parent_sign == 1
            else max(all_prices(self.correction))
        )
        if self.correction.sign != -parent_sign or (
            extreme <= floor if parent_sign == 1 else extreme >= floor
        ):
            raise ContractError("CORRECTION_INVALIDATES_PARENT_TREND")
        if self.invalidation != floor:
            raise ContractError("COUNT_STOP_NOT_PARENT_INVALIDATION")
        self.objective.validate(now, self.parent_id)
        price(float(self.objective.value))
        if not (
            self.invalidation > 0
            and (
                self.invalidation < b.price
                if self.correction.sign == -1
                else self.invalidation > b.price
            )
        ):
            raise ContractError("COUNT_INVALIDATION_GEOMETRY")

    @property
    def claim(self):
        return (
            self.parent_id,
            self.parent_degree,
            self.leg_name,
            self.parent_start.observed_at,
            self.parent_end.observed_at,
        )


@dataclass
class ElliottBook:
    counts: dict[str, ResumeCount] = field(default_factory=dict)
    tombstones: set[str] = field(default_factory=set)
    used_claims: set[tuple] = field(default_factory=set)
    last_clock: object = None

    def add(self, count, now):
        now = clock(now)
        count.validate(now)
        if count.count_id in self.tombstones:
            raise ContractError("COUNT_NO_RESURRECTION")
        if count.count_id in self.counts and self.counts[count.count_id] != count:
            raise ContractError("COUNT_ID_MUTATED")
        self.counts[count.count_id] = count

    def invalidate_wave(self, wave_id):
        def contains(w):
            return w.wave_id == wave_id or any(contains(c) for c in w.children)

        ids = [
            k for k, v in self.counts.items() if contains(v.correction) or v.parent_id == wave_id
        ]
        self.tombstones.update(ids)

    def decide(self, now, close, claim):
        now = clock(now)
        price(close)
        if self.last_clock is not None and now <= self.last_clock:
            raise ContractError("COUNT_CLOCK_REVERSED")
        for c in self.counts.values():
            if c.count_id not in self.tombstones:
                c.validate(now)
        self.last_clock = now
        live = [c for c in self.counts.values() if c.count_id not in self.tombstones]
        for c in live:
            if close <= c.invalidation if c.correction.sign == -1 else close >= c.invalidation:
                self.tombstones.add(c.count_id)
        live = [c for c in live if c.count_id not in self.tombstones]
        own = [c for c in live if c.claim == claim]
        if not own or claim in self.used_claims:
            return None
        # All retained opposing interpretations veto; no latest/best count selection.
        if any(c.correction.sign != -1 for c in live):
            return None
        if any(
            now
            <= max(
                *(instant(p.available_at) for p in c.correction.points),
                instant(c.parent_end.available_at),
                instant(c.objective.available_at),
            )
            for c in own
        ):
            return None
        # Last internal corrective high, not the correction's original start high.
        internal = [[p for p in c.correction.points[1:-1] if p.kind == "H"] for c in own]
        if any(not ps for ps in internal):
            return None
        trigger = max(ps[-1].price for ps in internal)
        if close <= trigger:
            return None
        stop = max(c.invalidation for c in own)
        goals = tuple(sorted(set(float(c.objective.value) for c in own)))
        if stop >= close:
            return None
        self.used_claims.add(claim)
        ids = tuple(sorted(c.count_id for c in own))
        source = digest([self.counts[k].correction.source_sha256 for k in ids])
        return SchoolThesis(
            "FS_ELLIOTT_PROOF_RESUMPTION_V8",
            "ELLIOTT_COMMON_COUNT_OWNER",
            digest((claim, ids)),
            now,
            own[0].parent_degree,
            "LONG",
            stop,
            goals,
            "TREND_CHECKPOINTS",
            source,
            ids,
            "OWNER_STRUCTURE_OR_COUNT_INVALIDATION_NO_FORCED_OBJECTIVE",
            "FINITE_1H_LEAF_AND_NAMED_1D_4H_PARENT_PROFILE_NOT_ALL_ELLIOTT_COUNTS",
        )
