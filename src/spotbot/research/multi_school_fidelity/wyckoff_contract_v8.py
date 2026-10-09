"""Fresh range-owned cause/readiness. Percentage PNF is an AKAH adaptation.

No parent range's columns or readiness can pass to a reaccumulation campaign.
Source event segments are supplied by a causal producer, never PnL-selected.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .school_contract_common_v8 import (
    Known,
    Point,
    SchoolThesis,
    clock,
    completed,
    price,
    validate_points,
)
from .structural_lifecycle_v6 import CompletedBar, ContractError, instant


@dataclass(frozen=True)
class RangeCause:
    cause_id: str
    start_at: object
    support: float
    resistance: float
    degree: str
    authority: Known
    branch: str
    prior_markup: Known | None = None

    def validate(self, now):
        self.authority.validate(now, self.cause_id)
        if self.authority.value != "RANGE" or instant(self.authority.available_at) < instant(
            self.start_at
        ):
            raise ContractError("FRESH_RANGE_AUTHORITY_REQUIRED")
        price(self.support)
        if (
            self.resistance <= self.support
            or self.branch not in {"ACCUMULATION", "REACCUMULATION"}
            or self.degree not in {"1H", "4H"}
            or instant(self.start_at) > now
        ):
            raise ContractError("RANGE_CAUSE_CONTRACT")
        price(self.resistance)
        if self.branch == "REACCUMULATION":
            if self.prior_markup is None:
                raise ContractError("PRIOR_MARKUP_REQUIRED")
            self.prior_markup.validate(now)
            if self.prior_markup.value != "MARKUP" or instant(
                self.prior_markup.available_at
            ) > instant(self.start_at):
                raise ContractError("REACCUMULATION_PARENT_NOT_HISTORICAL_MARKUP")
            if self.prior_markup.structure_id == self.cause_id:
                raise ContractError("REACCUMULATION_REQUIRES_NEW_CAUSE")


@dataclass(frozen=True)
class Segment:
    event_id: str
    start_at: object
    end_at: object
    available_at: object
    cause_id: str


def pnf_cause(cause, bars, segments, count_line, now):
    """Logarithmic 1% boxes, 3-box reversal; complete source segments only."""
    now = clock(now)
    cause.validate(now)
    count_line.validate(now, cause.cause_id)
    if not cause.support <= float(count_line.value) <= cause.resistance or not segments or not bars:
        raise ContractError("LPS_COUNT_LINE_OR_COMPLETE_SEGMENTS_REQUIRED")
    if len({s.event_id for s in segments}) != len(segments):
        raise ContractError("DUPLICATE_PNF_SEGMENT")
    for i, s in enumerate(segments):
        if (
            s.cause_id != cause.cause_id
            or not s.event_id
            or not instant(cause.start_at)
            <= instant(s.start_at)
            < instant(s.end_at)
            <= instant(s.available_at)
            <= now
            or instant(s.end_at) > instant(count_line.available_at)
            or (i and instant(segments[i - 1].end_at) != instant(s.start_at))
        ):
            raise ContractError("WHOLE_SEGMENT_CAUSAL_OWNERSHIP")
    if instant(segments[0].start_at) != instant(cause.start_at):
        raise ContractError("COUNT_START_NOT_FRESH_RANGE")
    selected = []
    last = None
    for bar in bars:
        completed(bar, bar.end, cause.degree)
        if instant(bar.end) > now:
            raise ContractError("FUTURE_PNF_BAR")
        if last is not None and instant(bar.start) != last:
            raise ContractError("PNF_CLOSE_COVERAGE_GAP")
        last = instant(bar.end)
        if instant(segments[0].start_at) <= instant(bar.start) and instant(bar.end) <= instant(
            segments[-1].end_at
        ):
            selected.append(bar)
    if not selected or (
        instant(selected[0].start) != instant(segments[0].start_at)
        or instant(selected[-1].end) != instant(segments[-1].end_at)
    ):
        raise ContractError("WHOLE_PNF_RANGE_COVERAGE_REQUIRED")
    # Quantization always uses the same immutable range-low log anchor.
    step = math.log(1.01)

    def index(v):
        return math.floor(math.log(price(v) / cause.support) / step + 1e-10)

    levels = [index(b.close) for b in selected]
    if any(b.close < cause.support or b.close > cause.resistance for b in selected):
        raise ContractError("CAUSE_BAR_OUTSIDE_RANGE")
    lo = hi = levels[0]
    direction = 0
    columns = []
    for q in levels[1:]:
        if direction == 0:
            if q != lo:
                direction = 1 if q > lo else -1
                lo, hi = min(lo, q), max(hi, q)
        elif direction == 1:
            if q >= hi:
                hi = q
            elif hi - q >= 3:
                columns.append((lo, hi))
                lo, hi, direction = q, hi - 1, -1
        else:
            if q <= lo:
                lo = q
            elif q - lo >= 3:
                columns.append((lo, hi))
                lo, hi, direction = lo + 1, q, 1
    if direction:
        columns.append((lo, hi))
    line = index(float(count_line.value))
    count = sum(lo <= line <= hi for lo, hi in columns)
    if not count:
        raise ContractError("NO_HORIZONTAL_COUNT_LINE_COLUMNS")
    target = cause.support * 1.01 ** (3 * count)
    return {
        "count": count,
        "columns": tuple(columns),
        "count_line_box": line,
        "minimum_objective": target,
        "method": "AKAH_LOG_PERCENTAGE_1PCT_3BOX",
        "cause_id": cause.cause_id,
        "source_segments": tuple(s.event_id for s in segments),
    }


@dataclass(frozen=True)
class ActivityBar:
    bar: CompletedBar
    volume: float

    def validate(self, now, degree):
        completed(self.bar, self.bar.end, degree)
        if instant(self.bar.end) > now or not math.isfinite(self.volume) or self.volume <= 0:
            raise ContractError("CAUSAL_POSITIVE_ACTIVITY_REQUIRED")


@dataclass(frozen=True)
class SpringStage:
    cause_id: str
    spring: ActivityBar
    test: ActivityBar
    confirmation: ActivityBar
    market: Known
    rs: Known
    branch_events: tuple[Known, ...]

    def validate(self, cause, now):
        cause.validate(now)
        if self.cause_id != cause.cause_id or cause.branch != "ACCUMULATION":
            raise ContractError("SPRING_WRONG_CAUSE_BRANCH")
        for a in (self.spring, self.test, self.confirmation):
            a.validate(now, cause.degree)
            if instant(a.bar.start) < instant(cause.start_at):
                raise ContractError("OLD_SPRING_STAGE")
        self.market.validate(now)
        self.rs.validate(now, cause.cause_id)
        if tuple(e.value for e in self.branch_events) != (
            "PS",
            "SC",
            "ST",
            "DOWNSIDE_OBJECTIVE_MET",
        ):
            raise ContractError("SPRING_PRIOR_ACCUMULATION_EVENTS")
        for e in self.branch_events:
            e.validate(now, cause.cause_id)
            if instant(e.available_at) < instant(cause.start_at):
                raise ContractError("INHERITED_SPRING_READINESS")
        s, t, c = self.spring, self.test, self.confirmation
        if not (
            instant(s.bar.end) <= instant(t.bar.start)
            and instant(t.bar.end) <= instant(c.bar.start)
            and instant(c.bar.end) == now
        ):
            raise ContractError("SPRING_LATER_TEST_LATER_CONFIRMATION")
        return (
            s.bar.low < cause.support < s.bar.close
            and t.bar.low > s.bar.low
            and t.bar.low >= cause.support
            and t.volume < s.volume
            and t.bar.high - t.bar.low < s.bar.high - s.bar.low
            and c.bar.close > t.bar.high
            and self.market.value in {"UP", "BALANCED"}
            and float(self.rs.value) > 1.0
        )


@dataclass(frozen=True)
class Readiness:
    cause_id: str
    falling_highs: tuple[Point, Point]
    range_swings: tuple[Point, Point, Point, Point]
    supply_reference: ActivityBar
    supply_test: ActivityBar
    sos: ActivityBar
    lps: ActivityBar
    market: Known
    rs: Known
    branch_events: tuple[Known, ...]

    def evaluate(self, cause, now):
        cause.validate(now)
        if self.cause_id != cause.cause_id:
            raise ContractError("READINESS_OTHER_CAUSE")
        if instant(self.lps.bar.end) != now:
            raise ContractError("STALE_LPS_NOT_THIS_CHECKPOINT")
        validate_points(self.falling_highs[:1], now)
        for p in self.falling_highs:
            p.validate(now)
        validate_points(self.range_swings, now)
        h0, h1 = self.falling_highs
        if (
            h0.kind != "H"
            or h1.kind != "H"
            or h1.price >= h0.price
            or not instant(h0.observed_at) < instant(h1.observed_at) < instant(cause.start_at)
            or any(p.degree != cause.degree for p in (*self.falling_highs, *self.range_swings))
        ):
            raise ContractError("PRE_RANGE_FALLING_STRIDE_ANCHORS")
        for p in self.range_swings:
            if (
                instant(p.observed_at) < instant(cause.start_at)
                or instant(p.available_at) > instant(self.sos.bar.start)
                or not cause.support <= p.price <= cause.resistance
            ):
                raise ContractError("OLD_RANGE_READINESS")
        for a in (self.supply_reference, self.supply_test, self.sos, self.lps):
            a.validate(now, cause.degree)
            if instant(a.bar.start) < instant(cause.start_at):
                raise ContractError("OLD_CAUSE_ACTIVITY")
        if not (
            instant(self.supply_reference.bar.end)
            < instant(self.supply_test.bar.end)
            < instant(self.sos.bar.end)
            < instant(self.lps.bar.end)
        ):
            raise ContractError("TEST_SOS_LPS_LATER_ORDER")
        self.market.validate(now)
        self.rs.validate(now, cause.cause_id)
        expected = (
            ("PS", "SC", "ST", "DOWNSIDE_OBJECTIVE_MET")
            if cause.branch == "ACCUMULATION"
            else ("NEW_RANGE_SUPPLY_TEST",)
        )
        if tuple(e.value for e in self.branch_events) != expected:
            raise ContractError("BRANCH_APPLICABLE_READINESS_EVENTS")
        for e in self.branch_events:
            e.validate(now, cause.cause_id)
            if instant(e.available_at) < instant(cause.start_at):
                raise ContractError("OLD_BRANCH_EVENT")
        l0, a0, l1, a1 = self.range_swings
        if tuple(p.kind for p in self.range_swings) != ("L", "H", "L", "H"):
            raise ContractError("HL_HH_RANGE_STRUCTURE")
        seconds = (instant(h1.observed_at) - instant(h0.observed_at)).total_seconds()
        slope = (h1.price - h0.price) / seconds
        line = (
            h1.price + slope * (instant(self.sos.bar.end) - instant(h1.observed_at)).total_seconds()
        )
        ref, test, sos, lps = self.supply_reference, self.supply_test, self.sos, self.lps
        return {
            "market": self.market.value in {"UP", "BALANCED"},
            "rs": float(self.rs.value) > 1.0,
            "higher_lows_highs": l1.price > l0.price and a1.price > a0.price,
            "stride_broken": line > 0 and sos.bar.close > line,
            "supply_diminishes": test.volume < ref.volume
            and test.bar.high - test.bar.low < ref.bar.high - ref.bar.low
            and test.bar.low >= cause.support,
            "demand_effort_result": sos.volume > test.volume
            and sos.bar.close > cause.resistance
            and sos.bar.close > sos.bar.open,
            "lps_holds": lps.bar.low > cause.support
            and lps.bar.close > cause.resistance
            and lps.volume < sos.volume,
        }


@dataclass
class WyckoffContract:
    cause: RangeCause
    consumed_branches: set[str] = field(default_factory=set)
    invalidated: bool = False
    frozen_cause: RangeCause = field(init=False)
    stage1: SchoolThesis | None = field(init=False, default=None)

    def __post_init__(self):
        self.frozen_cause = self.cause

    def invalidate(self):
        self.invalidated = True

    def spring_intent(self, now, entry, stage, bars, segments, count_line):
        now = clock(now)
        price(entry)
        if not isinstance(stage, SpringStage):
            raise ContractError("TYPED_SPRING_STAGE_REQUIRED")
        if self.invalidated or self.cause != self.frozen_cause or self.consumed_branches:
            raise ContractError("SPRING_CAUSE_ALREADY_USED_OR_INVALID")
        if not stage.validate(self.cause, now):
            return None
        if float(count_line.value) != stage.test.bar.low:
            raise ContractError("COUNT_LINE_NOT_THIS_SPRING_TEST")
        target = pnf_cause(self.cause, bars, segments, count_line, now)["minimum_objective"]
        stop = stage.spring.bar.low
        if not stop < entry or target - entry < 3 * (entry - stop):
            return None
        self.stage1 = SchoolThesis(
            "FS_WYCKOFF_FRESH_CAUSE_V8",
            "WYCKOFF_RANGE_OWNER",
            self.cause.cause_id,
            now,
            self.cause.degree,
            "LONG",
            stop,
            (target,),
            "TREND_CHECKPOINTS",
            self.cause.authority.source_sha256,
            (self.cause.authority.event_id, count_line.event_id),
            "STAGE_50_PERCENT_SPRING_THEN_LPS_ADD_WITHIN_SAME_RISK_BUDGET",
            "CAUSAL_SPRING_LATER_TEST_LATER_CONFIRMATION_LOG_PNF_PROFILE",
        )
        self.stage1.validate_entry(now, entry)
        self.consumed_branches.add("SPRING_TEST")
        return self.stage1

    def intent(self, now, entry, readiness, bars, segments, count_line, branch="NO_SPRING_LPS"):
        now = clock(now)
        price(entry)
        if not isinstance(readiness, Readiness):
            raise ContractError("TYPED_READINESS_REQUIRED")
        if self.cause != self.frozen_cause:
            raise ContractError("CAUSE_OWNER_MUTATED")
        if branch == "NO_SPRING_LPS" and self.stage1 is not None:
            raise ContractError("STAGED_CAMPAIGN_USE_LPS_ADD")
        if self.invalidated or branch in self.consumed_branches:
            raise ContractError("CAUSE_NO_RESURRECTION_OR_REUSE")
        if branch not in {"SPRING_TEST", "NO_SPRING_LPS", "REACCUMULATION_LPS"}:
            raise ContractError("UNKNOWN_WYCKOFF_BRANCH")
        if (self.cause.branch == "REACCUMULATION") != (branch == "REACCUMULATION_LPS"):
            raise ContractError("CAUSE_BRANCH_MISMATCH")
        gates = readiness.evaluate(self.cause, now)
        if not all(gates.values()):
            return None
        if branch == "SPRING_TEST":
            raise ContractError("SPRING_STAGE_USES_SPRING_INTENT_NOT_POST_SOS_READINESS")
        pnf = pnf_cause(self.cause, bars, segments, count_line, now)
        stop = readiness.lps.bar.low
        if float(count_line.value) != stop or instant(count_line.available_at) != now:
            raise ContractError("COUNT_LINE_NOT_THIS_LPS")
        target = pnf["minimum_objective"]
        if stop >= entry or target - entry < 3 * (entry - stop):
            return None
        self.consumed_branches.add(branch)
        return SchoolThesis(
            "FS_WYCKOFF_FRESH_CAUSE_V8",
            "WYCKOFF_RANGE_OWNER",
            self.cause.cause_id,
            now,
            self.cause.degree,
            "LONG",
            stop,
            (target,),
            "TREND_CHECKPOINTS",
            self.cause.authority.source_sha256,
            (self.cause.authority.event_id, count_line.event_id, *pnf["source_segments"]),
            "NATIVE_DISTRIBUTION_OR_OWNER_STRUCTURE_PNF_CHECKPOINT_NOT_TAKE_PROFIT",
            "FRESH_LOG_PNF_BRANCH_APPLICABLE_READINESS_LPS_PROFILE",
        )

    def lps_add(self, now, entry, readiness, bars, segments, count_line):
        price(entry)
        if not isinstance(readiness, Readiness):
            raise ContractError("TYPED_READINESS_REQUIRED")
        if self.stage1 is None or self.invalidated or "LPS_ADD" in self.consumed_branches:
            raise ContractError("NO_LIVE_SPRING_CAMPAIGN_OR_DUPLICATE_ADD")
        if self.cause != self.frozen_cause:
            raise ContractError("CAUSE_OWNER_MUTATED")
        now = clock(now)
        if now <= instant(self.stage1.available_at) or not all(
            readiness.evaluate(self.cause, now).values()
        ):
            return None
        target = pnf_cause(self.cause, bars, segments, count_line, now)["minimum_objective"]
        stop = max(self.stage1.initial_invalidation, readiness.lps.bar.low)
        if (
            float(count_line.value) != readiness.lps.bar.low
            or instant(count_line.available_at) != now
        ):
            raise ContractError("COUNT_LINE_NOT_THIS_LPS")
        if stop >= entry or target - entry < 3 * (entry - stop):
            return None
        self.consumed_branches.add("LPS_ADD")
        return {
            "campaign_id": self.cause.cause_id,
            "owner": self.stage1.owner,
            "known_at": now,
            "remaining_initial_fraction": 0.5,
            "stop_floor": stop,
            "campaign_initial_risk_budget_must_not_increase": True,
            "native_staging_executor": "campaign_execution_v7",
        }
