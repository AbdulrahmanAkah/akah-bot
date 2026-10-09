"""Native pre-terminal projection scheduling, with execution-only Type-II reset.

Each newly confirmed alternating quadruple is projected once per frozen family.
Same-side repeated pivot types are not silently collapsed to prettier extremes.
Tick is the explicitly excluded-exchange research precision, never claimed PIT.
"""

from __future__ import annotations

from ..harmonic_contract_v8 import FAMILIES
from ..school_contract_common_v8 import clock
from ..structural_lifecycle_v6 import ContractError, instant


class HarmonicSource:
    def __init__(self, producer, tick=1e-12):
        if tick != 1e-12:
            raise ContractError("FROZEN_APPROXIMATE_PRECISION_REQUIRED")
        self.producer = producer
        self.prefix = producer.prefix
        self.tick = tick
        self.seen = set()
        self.active = set()
        self.diagnostics = []
        self.last = {}

    def close(self, bar, fresh, membership):
        now = clock(bar.end)
        self.prefix.require_bar(bar, now)
        degree = bar.timeframe
        if degree in self.last and now <= self.last[degree]:
            raise ContractError("HARMONIC_SOURCE_CLOSE_REPEATED")
        self.last[degree] = now
        emitted = []
        for sid in sorted(tuple(self.active)):
            contract = self.producer.harmonics[sid]
            if contract.projection.points[0].degree != degree:
                continue
            if contract.state in {"DONE", "INVALIDATED"}:
                self.active.remove(sid)
                continue
            item = self.producer.harmonic_close(sid, bar, pit_eligible=membership)
            if item is not None:
                emitted.append(item)
        if not fresh:
            return emitted
        points = sorted(
            (p for p in self.prefix.points.values() if p.degree == degree and instant(p.available_at) <= now),
            key=lambda p: (instant(p.observed_at), p.event_id),
        )
        if len(points) < 4:
            return emitted
        quartet = tuple(points[-4:])
        for point in quartet:
            self.prefix.require_point(point,now)
        try:
            atr = self.prefix.atr(degree, self.prefix.pair, now)
        except ContractError as exc:
            if str(exc)!="NATIVE_ATR20_COMPLETED_WARMUP_REQUIRED":
                raise
            self.diagnostics.append((now, degree, str(exc)))
            return emitted
        for family in FAMILIES:
            key = (family, tuple(p.event_id for p in quartet))
            if key in self.seen:
                continue
            self.seen.add(key)
            try:
                sid = self.producer.start_harmonic(family, quartet, atr, self.tick, now)
            except ContractError as exc:
                if str(exc) not in {
                    "ORDERED_ALTERNATING_SWINGS_REQUIRED", "FAMILY_DIRECTION_GEOMETRY", "ZERO_LEG",
                    "FAILED_IMPULSE_RATIO", "FIVE_ZERO_FAILED_TREND_GEOMETRY", "FIVE_ZERO_BC_EXTENSION",
                    "SHARK_OXAB_GEOMETRY", "ABCD_C_RETRACEMENT", "REGULAR_PATTERN_INTERIOR_POINTS",
                    "DEFINING_B_RATIO", "DEFINING_B_RANGE", "BAT_B_MUST_BE_BELOW_618",
                    "DEEP_CRAB_B_CANNOT_VIOLATE_X", "REGULAR_C_RETRACEMENT_PROFILE",
                    "NONPOSITIVE_PROJECTED_PRICE", "NO_PRETERMINAL_PRZ_CONVERGENCE",
                }:
                    raise
                self.diagnostics.append((key, now, str(exc)))
                continue
            if self.producer.harmonics[sid].projection.sign < 0:
                self.diagnostics.append((sid, now, "SHORT_NOT_AUTHORIZED"))
                continue
            self.active.add(sid)
        return emitted

    def completed(self, sid, owner, at, receipt):
        self.producer.acknowledge_harmonic_completion(sid, owner, at, execution_receipt=receipt)
