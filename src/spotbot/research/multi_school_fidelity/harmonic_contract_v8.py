"""Nine explicit family contracts and lifecycle; engineering choices are labeled.

No outcome, market reader, ratio fit, or inference of D at projection time.
Stop/trigger choices are AKAH adaptations, not an official universal doctrine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .school_contract_common_v8 import (
    Known,
    Point,
    SchoolThesis,
    clock,
    completed,
    digest,
    price,
    validate_points,
)
from .structural_lifecycle_v6 import CompletedBar, ContractError, instant

BASE_URL = "https://harmonictrader.com/harmonic-patterns/"


@dataclass(frozen=True)
class Family:
    b_low: float
    b_high: float
    xa_completion: float | None
    bc_projections: tuple[float, ...]
    ab_projections: tuple[float, ...]
    source_slug: str
    span: str = "A_TERMINAL"


# Ranges/equalities follow defining public measurements; alternate projection
# choices are frozen AKAH profiles, not a claim of one exhaustive interpretation.
FAMILIES = {
    "GARTLEY": Family(0.618, 0.618, 0.786, (1.27, 1.618), (1.0,), "gartley-pattern/"),
    "BAT": Family(0.382, 0.618, 0.886, (1.618, 2.0, 2.618), (1.0, 1.27), "bat-pattern/"),
    "ALTERNATE_BAT": Family(
        0.0, 0.382, 1.13, (2.0, 2.24, 2.618, 3.14, 3.618), (1.618,), "alternate-bat-pattern/"
    ),
    "BUTTERFLY": Family(
        0.786, 0.786, 1.27, (1.618, 2.0, 2.24, 2.618), (1.0, 1.27, 1.618), "butterfly-pattern/"
    ),
    "CRAB": Family(0.382, 0.618, 1.618, (2.618, 3.14, 3.618), (1.0, 1.27, 1.618), "crab-pattern/"),
    "DEEP_CRAB": Family(
        0.886, 1.0, 1.618, (2.24, 2.618, 3.14, 3.618), (1.0, 1.27), "deep-crab-pattern/"
    ),
    "ABCD": Family(0.0, 0.0, None, (), (1.0,), "abcd-pattern/"),
    "FIVE_ZERO": Family(1.13, 1.618, None, (), (), "5-0/", "C_TERMINAL"),
    "SHARK": Family(1.13, 1.618, None, (), (), "shark-pattern/", "B_TERMINAL"),
}


@dataclass(frozen=True)
class Projection:
    family: str
    points: tuple[Point, ...]
    available_at: datetime
    sign: int
    levels: tuple[float, ...]
    low: float
    high: float
    tolerance: float
    tick: float
    source_sha256: str
    structure_id: str


def project(family: str, points: tuple[Point, ...], now, atr: Known, tick: float):
    now = clock(now)
    if family not in FAMILIES or len(points) != 4:
        raise ContractError("FAMILY_FOUR_SOURCE_POINTS_REQUIRED")
    validate_points(points, now)
    atr.validate(now)
    price(float(atr.value))
    price(tick)
    if len({p.degree for p in points}) != 1:
        raise ContractError("SAME_PATTERN_DEGREE_REQUIRED")
    x, a, b, c = [p.price for p in points]
    f = FAMILIES[family]
    # 5-0 reverses BC; Shark uses OXAB, not regular XABC.
    sign = (1 if c > b else -1) if family == "FIVE_ZERO" else (1 if a > x else -1)
    expected = ("L", "H", "L", "H") if sign == 1 else ("H", "L", "H", "L")
    if tuple(p.kind for p in points) != expected:
        raise ContractError("FAMILY_DIRECTION_GEOMETRY")
    xa, ab, bc = abs(a - x), abs(b - a), abs(c - b)
    if min(xa, ab, bc) <= 0:
        raise ContractError("ZERO_LEG")
    if family in {"FIVE_ZERO", "SHARK"}:
        ratio = ab / xa if family == "FIVE_ZERO" else bc / ab
        if not f.b_low - 1e-12 <= ratio <= f.b_high + 1e-12:
            raise ContractError("FAILED_IMPULSE_RATIO")
        if family == "FIVE_ZERO":
            if not sign * b < sign * x < sign * a or not sign * c > sign * a:
                raise ContractError("FIVE_ZERO_FAILED_TREND_GEOMETRY")
            if not 1.618 <= bc / ab <= 2.24:
                raise ContractError("FIVE_ZERO_BC_EXTENSION")
            levels = (c - sign * 0.5 * bc, c - sign * ab)
        else:
            if not sign * x < sign * b < sign * a < sign * c:
                raise ContractError("SHARK_OXAB_GEOMETRY")
            # OX retracement measured from X, not incorrectly from O.
            levels = (a - sign * 0.886 * xa, a - sign * 1.13 * xa)
    elif family == "ABCD":
        if not 0.382 <= bc / ab <= 0.886:
            raise ContractError("ABCD_C_RETRACEMENT")
        levels = (c - sign * ab,)
    else:
        if not (sign * x < sign * b < sign * a and sign * b < sign * c < sign * a):
            raise ContractError("REGULAR_PATTERN_INTERIOR_POINTS")
        ratio = ab / xa
        if f.b_low == f.b_high:
            if abs(ab - f.b_low * xa) > tick + 1e-12:
                raise ContractError("DEFINING_B_RATIO")
        elif not f.b_low - 1e-12 <= ratio <= f.b_high + 1e-12:
            raise ContractError("DEFINING_B_RANGE")
        if family == "BAT" and ratio >= 0.618:
            raise ContractError("BAT_B_MUST_BE_BELOW_618")
        if family == "DEEP_CRAB" and ratio >= 1.0:
            raise ContractError("DEEP_CRAB_B_CANNOT_VIOLATE_X")
        if not 0.382 <= bc / ab <= 0.886:
            raise ContractError("REGULAR_C_RETRACEMENT_PROFILE")
        defining = a - sign * f.xa_completion * xa
        bc_levels = [c - sign * q * bc for q in f.bc_projections]
        ab_levels = [c - sign * q * ab for q in f.ab_projections]
        levels = (
            defining,
            min(bc_levels, key=lambda z: (abs(z - defining), z)),
            min(ab_levels, key=lambda z: (abs(z - defining), z)),
        )
    if any(z <= 0 for z in levels):
        raise ContractError("NONPOSITIVE_PROJECTED_PRICE")
    tol = 0.25 * float(atr.value)
    # Shark 0.886–1.13 is a source band, not multiple converging levels.
    if family != "SHARK" and max(levels) - min(levels) > tol:
        raise ContractError("NO_PRETERMINAL_PRZ_CONVERGENCE")
    sid = digest((family, [p.event_id for p in points], list(levels), str(now), atr.source_sha256))
    return Projection(
        family,
        points,
        now,
        sign,
        levels,
        min(levels),
        max(levels),
        tol,
        tick,
        atr.source_sha256,
        sid,
    )


@dataclass
class HarmonicContract:
    projection: Projection
    state: str = "PROJECTED"
    terminal: CompletedBar | None = None
    terminal_extreme: float | None = None
    near_edge_seen: bool = False
    last_close: datetime | None = None
    stop: float | None = None
    type1_complete_at: datetime | None = None
    retest_at: datetime | None = None
    retest_extreme: float | None = None
    used_types: set[str] = field(default_factory=set)
    history: list[dict] = field(default_factory=list)
    _frozen_projection: Projection = field(init=False)

    def __post_init__(self):
        self._frozen_projection = self.projection

    def _check_owner(self):
        if self.projection != self._frozen_projection:
            raise ContractError("PATTERN_OWNER_MUTATED")

    def _stop(self, bar):
        p = self.projection
        outward = self.terminal_extreme
        boundary = p.low if p.sign == 1 else p.high
        if p.family == "GARTLEY":
            boundary = p.points[0].price
            if outward <= boundary if p.sign == 1 else outward >= boundary:
                return None
        elif p.family == "BAT":
            x, a = [z.price for z in p.points[:2]]
            boundary = a - p.sign * 1.13 * abs(a - x)
            if outward <= boundary if p.sign == 1 else outward >= boundary:
                return None
        return min(boundary, outward) - p.tick if p.sign == 1 else max(boundary, outward) + p.tick

    def on_close(self, bar: CompletedBar):
        self._check_owner()
        p = self.projection
        now = clock(bar.end)
        completed(bar, now, p.points[0].degree)
        if instant(bar.start) < instant(p.available_at):
            raise ContractError("TERMINAL_BAR_BEFORE_PROJECTION")
        if self.last_close is not None and instant(bar.start) != self.last_close:
            raise ContractError("REPEAT_OR_MISSING_PATTERN_BAR")
        if self.state in {"INVALIDATED", "DONE"}:
            raise ContractError("PATTERN_NO_RESURRECTION")
        self.last_close = now
        if self.stop is not None and (
            bar.low <= self.stop if p.sign == 1 else bar.high >= self.stop
        ):
            self.state = "INVALIDATED"
            return None
        if self.state == "PROJECTED":
            # Full required-zone traversal can span several completed bars.
            extreme = bar.low if p.sign == 1 else bar.high
            self.terminal_extreme = (
                extreme
                if self.terminal_extreme is None
                else (
                    min(self.terminal_extreme, extreme)
                    if p.sign == 1
                    else max(self.terminal_extreme, extreme)
                )
            )
            self.near_edge_seen |= (
                bar.low <= p.high <= bar.high if p.sign == 1 else (bar.low <= p.low <= bar.high)
            )
            # A gap over the entire PRZ is not evidence of zone traversal.
            tested = self.near_edge_seen and (
                bar.low <= p.low <= bar.high if p.sign == 1 else (bar.low <= p.high <= bar.high)
            )
            # Source range must have actually been entered before reaching far edge.
            if tested:
                if p.family == "SHARK" and abs(p.points[-1].price - self.terminal_extreme) < (
                    1.618 * abs(p.points[-1].price - p.points[-2].price)
                ):
                    self.state = "INVALIDATED"
                    return None
                self.stop = self._stop(bar)
                if self.stop is None or self.stop <= 0:
                    self.state = "INVALIDATED"
                    return None
                self.terminal = bar
                self.state = "TERMINAL_COMPLETE"
            return None
        if self.state == "TERMINAL_COMPLETE":
            confirms = (
                bar.close > self.terminal.high if p.sign == 1 else bar.close < self.terminal.low
            )
            if confirms:
                self.state = "TYPE_I_ACTIVE"
                return self.thesis(now, "TYPE_I")
        elif self.state == "TYPE_I_COMPLETE":
            touches = bar.low <= p.high and bar.high >= p.low
            if touches and now > self.type1_complete_at:
                self.retest_at = now
                self.retest_extreme = bar.high if p.sign == 1 else bar.low
                self.state = "TYPE_II_RETEST"
        elif self.state == "TYPE_II_RETEST":
            if bar.close > self.retest_extreme if p.sign == 1 else bar.close < self.retest_extreme:
                self.state = "TYPE_II_ACTIVE"
                return self.thesis(now, "TYPE_II")
        return None

    def thesis(self, now, kind):
        self._check_owner()
        p = self.projection
        required = {"TYPE_I": "TYPE_I_ACTIVE", "TYPE_II": "TYPE_II_ACTIVE"}
        if self.state != required.get(kind) or kind in self.used_types:
            raise ContractError("TYPE_OWNERSHIP_OR_REUSE")
        now = clock(now)
        if now != self.last_close:
            raise ContractError("THESIS_NOT_THIS_CONFIRMATION")
        d = self.terminal_extreme
        anchor_index = -1 if p.family in {"FIVE_ZERO", "SHARK"} else 1
        anchor = p.points[anchor_index].price
        span = abs(anchor - d)
        goals = (d + p.sign * 0.382 * span, d + p.sign * 0.618 * span)
        self.used_types.add(kind)
        self.history.append({"known_at": now, "kind": kind, "stop": self.stop, "goals": goals})
        return SchoolThesis(
            "FS_HARMONIC_CAUSAL_ADAPTATION_V8",
            "HARMONIC_" + kind,
            p.structure_id,
            now,
            p.points[0].degree,
            "LONG" if p.sign == 1 else "SHORT_DIAGNOSTIC",
            self.stop,
            goals,
            "FINITE_REACTION",
            p.source_sha256,
            tuple(z.event_id for z in p.points)
            + (digest((self.terminal.start, self.terminal.end)), digest((now, kind))),
            "V7_FIXED_INITIAL_HALF_PARTIAL_THEN_FINAL_WITH_COST_BREAKEVEN",
            "EXPLICIT_FAMILY_STRUCTURAL_STOP_AND_LATER_PRICE_ACTION_PROFILE_V8",
        )

    def complete_type1(self, at):
        self._check_owner()
        at = clock(at)
        if self.state != "TYPE_I_ACTIVE" or at != self.last_close:
            raise ContractError("TYPE_I_COMPLETION_ORDER")
        self.state = "TYPE_I_COMPLETE"
        self.type1_complete_at = at

    def complete_type2(self):
        self._check_owner()
        if self.state != "TYPE_II_ACTIVE":
            raise ContractError("TYPE_II_COMPLETION_ORDER")
        self.state = "DONE"
