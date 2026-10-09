from __future__ import annotations

import copy
import dataclasses
import math
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

MANDATORY_EXACT = {
    "MAX_HOLD_168H",
    "ADAPTIVE_PROTECTION_GAP",
    "ADAPTIVE_PROTECTION_TOUCH",
}
OPTIONAL_PREFIXES = ("ADAPTIVE_STAGNATION_",)


class TwoSidedSurfaceError(RuntimeError):
    pass


def utc(value: Any) -> pd.Timestamp:
    t = pd.Timestamp(value)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def classify_exit_reason(reason: str | None) -> str:
    if reason is None:
        return "NO_EXIT"
    r = str(reason)
    if r in MANDATORY_EXACT:
        return "MANDATORY"
    if any(r.startswith(prefix) for prefix in OPTIONAL_PREFIXES):
        return "OPTIONAL"
    return "UNKNOWN"


def suppress_optional_decision(decision: Any) -> Any:
    if not bool(getattr(decision, "should_exit", False)):
        return decision
    reason = str(getattr(decision, "exit_reason", ""))
    if classify_exit_reason(reason) != "OPTIONAL":
        raise TwoSidedSurfaceError(f"SUPPRESS_NONOPTIONAL_FORBIDDEN:{reason}")
    if dataclasses.is_dataclass(decision):
        return dataclasses.replace(decision, should_exit=False, exit_price=None, exit_reason=None)
    # Defensive fallback for namedtuple-like immutable objects.
    if hasattr(decision, "_replace"):
        return decision._replace(should_exit=False, exit_price=None, exit_reason=None)
    raise TwoSidedSurfaceError(f"UNSUPPORTED_DECISION_TYPE:{type(decision).__name__}")


@dataclass(frozen=True)
class BranchExit:
    branch: str
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str
    net_sale_proceeds: float
    mandatory_exit: bool
    optional_exit: bool


def _bar(bar_lookup: dict[int, dict[str, float]], ts: pd.Timestamp) -> dict[str, float]:
    key = int(utc(ts).value)
    if key not in bar_lookup:
        raise TwoSidedSurfaceError(f"BAR_MISSING:{utc(ts).isoformat()}")
    return bar_lookup[key]


def _net_sale(quantity: float, price: float, exit_side_cost: float) -> float:
    gross = float(quantity) * float(price)
    return gross - gross * float(exit_side_cost)


def _evaluate(
    rd27: Any,
    lifecycle: Any,
    ts: pd.Timestamp,
    bar_lookup: dict[int, dict[str, float]],
    market_state_at: Callable[[pd.Timestamp], str],
) -> tuple[Any, dict[str, float]]:
    bar = _bar(bar_lookup, ts)
    prior = _bar(bar_lookup, ts - pd.Timedelta(hours=1))
    state = market_state_at(ts)
    decision = rd27.evaluate_adaptive_exit(
        lifecycle,
        current_open_time=ts,
        current_open=float(bar["open"]),
        current_low=float(bar["low"]),
        prior_asset_close=float(prior["close"]),
        market_state=str(state),
    )
    return decision, bar


def _survivor_update(rd27: Any, lifecycle: Any, decision: Any, bar: dict[str, float]) -> Any:
    return rd27.apply_completed_bar_update(
        lifecycle,
        decision=decision,
        completed_high=float(bar["high"]),
    )


def simulate_exit_now(
    *,
    rd27: Any,
    lifecycle_snapshot: Any,
    decision_time: pd.Timestamp,
    bar_lookup: dict[int, dict[str, float]],
    market_state_at: Callable[[pd.Timestamp], str],
    quantity: float,
    exit_side_cost: float,
    candidate_execution_lag_hours: int = 1,
) -> BranchExit:
    """EXIT_NOW with native pi0 precedence until the first legal candidate execution open."""
    lifecycle = copy.deepcopy(lifecycle_snapshot)
    dt = utc(decision_time)
    execute_at = dt + pd.Timedelta(hours=int(candidate_execution_lag_hours))
    ts = dt
    while ts <= execute_at:
        decision, bar = _evaluate(rd27, lifecycle, ts, bar_lookup, market_state_at)
        if bool(decision.should_exit):
            if decision.exit_price is None or decision.exit_reason is None:
                raise TwoSidedSurfaceError("PI0_EXIT_MISSING_FILL")
            reason = str(decision.exit_reason)
            cls = classify_exit_reason(reason)
            if cls == "UNKNOWN":
                raise TwoSidedSurfaceError(f"UNKNOWN_PI0_EXIT_REASON:{reason}")
            px = float(decision.exit_price)
            return BranchExit(
                branch="EXIT_NOW",
                exit_time=ts,
                exit_price=px,
                exit_reason=reason,
                net_sale_proceeds=_net_sale(quantity, px, exit_side_cost),
                mandatory_exit=(cls == "MANDATORY"),
                optional_exit=(cls == "OPTIONAL"),
            )
        if ts == execute_at:
            px = float(bar["open"])
            return BranchExit(
                branch="EXIT_NOW",
                exit_time=ts,
                exit_price=px,
                exit_reason="RESEARCH_EXIT_NOW_FIRST_LEGAL_OPEN",
                net_sale_proceeds=_net_sale(quantity, px, exit_side_cost),
                mandatory_exit=False,
                optional_exit=False,
            )
        lifecycle = _survivor_update(rd27, lifecycle, decision, bar)
        ts += pd.Timedelta(hours=1)
    raise TwoSidedSurfaceError("EXIT_NOW_UNREACHABLE")


def simulate_hold_one_step_then_pi0(
    *,
    rd27: Any,
    lifecycle_snapshot: Any,
    decision_time: pd.Timestamp,
    step_hours: int,
    max_exit_time: pd.Timestamp,
    bar_lookup: dict[int, dict[str, float]],
    market_state_at: Callable[[pd.Timestamp], str],
    quantity: float,
    exit_side_cost: float,
) -> tuple[BranchExit, dict[str, int]]:
    """Suppress only optional pi0 exits for exactly one canonical decision step."""
    if int(step_hours) <= 0:
        raise TwoSidedSurfaceError("INVALID_STEP_HOURS")
    lifecycle = copy.deepcopy(lifecycle_snapshot)
    dt = utc(decision_time)
    hold_until = dt + pd.Timedelta(hours=int(step_hours))
    hard_end = utc(max_exit_time)
    ts = dt
    suppressed = 0
    mandatory_seen = 0
    while ts <= hard_end:
        decision, bar = _evaluate(rd27, lifecycle, ts, bar_lookup, market_state_at)
        if bool(decision.should_exit):
            if decision.exit_price is None or decision.exit_reason is None:
                raise TwoSidedSurfaceError("PI0_EXIT_MISSING_FILL")
            reason = str(decision.exit_reason)
            cls = classify_exit_reason(reason)
            if cls == "UNKNOWN":
                raise TwoSidedSurfaceError(f"UNKNOWN_PI0_EXIT_REASON:{reason}")
            if cls == "MANDATORY":
                mandatory_seen += 1
                px = float(decision.exit_price)
                return (
                    BranchExit(
                        branch="HOLD_ONE_STEP_THEN_PI0",
                        exit_time=ts,
                        exit_price=px,
                        exit_reason=reason,
                        net_sale_proceeds=_net_sale(quantity, px, exit_side_cost),
                        mandatory_exit=True,
                        optional_exit=False,
                    ),
                    {"optional_exits_suppressed": suppressed, "mandatory_exits_seen": mandatory_seen},
                )
            if ts < hold_until:
                suppressed += 1
                survivor_decision = suppress_optional_decision(decision)
                lifecycle = _survivor_update(rd27, lifecycle, survivor_decision, bar)
                ts += pd.Timedelta(hours=1)
                continue
            px = float(decision.exit_price)
            return (
                BranchExit(
                    branch="HOLD_ONE_STEP_THEN_PI0",
                    exit_time=ts,
                    exit_price=px,
                    exit_reason=reason,
                    net_sale_proceeds=_net_sale(quantity, px, exit_side_cost),
                    mandatory_exit=False,
                    optional_exit=True,
                ),
                {"optional_exits_suppressed": suppressed, "mandatory_exits_seen": mandatory_seen},
            )
        lifecycle = _survivor_update(rd27, lifecycle, decision, bar)
        ts += pd.Timedelta(hours=1)
    raise TwoSidedSurfaceError("HOLD_BRANCH_REACHED_END_WITHOUT_EXIT")


def self_test() -> None:
    assert classify_exit_reason("MAX_HOLD_168H") == "MANDATORY"
    assert classify_exit_reason("ADAPTIVE_PROTECTION_GAP") == "MANDATORY"
    assert classify_exit_reason("ADAPTIVE_PROTECTION_TOUCH") == "MANDATORY"
    assert classify_exit_reason("ADAPTIVE_STAGNATION_24H") == "OPTIONAL"
    assert classify_exit_reason("SOMETHING_NEW") == "UNKNOWN"
    assert math.isclose(_net_sale(2.0, 100.0, 0.001), 199.8)

    @dataclass(frozen=True)
    class _D:
        should_exit: bool
        exit_price: float | None
        exit_reason: str | None
        market_state: str = "RISK_ON"
        age_hours: int = 1
        effective_floor: float = 0.0
        floor_source: str = "TEST"
        stagnation_threshold_hours: int = 24

    class _R:
        def __init__(self, reasons: dict[int, str]):
            self.reasons = reasons
        def evaluate_adaptive_exit(self, lifecycle, *, current_open_time, current_open, current_low, prior_asset_close, market_state):
            h = int(utc(current_open_time).hour)
            reason = self.reasons.get(h)
            if reason is None:
                return _D(False, None, None)
            return _D(True, float(current_open), reason)
        def apply_completed_bar_update(self, lifecycle, *, decision, completed_high):
            return dict(lifecycle)

    start = pd.Timestamp("2022-01-01T04:00:00Z")
    bars = {}
    for h in range(0, 13):
        ts = pd.Timestamp("2022-01-01T00:00:00Z") + pd.Timedelta(hours=h)
        bars[int(ts.value)] = {"open": 100.0 + h, "high": 101.0 + h, "low": 99.0 + h, "close": 100.5 + h}
    state = lambda _ts: "RISK_ON"
    rd = _R({4: "ADAPTIVE_STAGNATION_24H", 6: "ADAPTIVE_PROTECTION_TOUCH"})
    hold, audit = simulate_hold_one_step_then_pi0(
        rd27=rd, lifecycle_snapshot={"x": 1}, decision_time=start, step_hours=4,
        max_exit_time=start + pd.Timedelta(hours=8), bar_lookup=bars,
        market_state_at=state, quantity=1.0, exit_side_cost=0.0,
    )
    assert audit["optional_exits_suppressed"] == 1
    assert hold.exit_reason == "ADAPTIVE_PROTECTION_TOUCH" and hold.mandatory_exit
    rd2 = _R({8: "ADAPTIVE_STAGNATION_24H"})
    hold2, audit2 = simulate_hold_one_step_then_pi0(
        rd27=rd2, lifecycle_snapshot={"x": 1}, decision_time=start, step_hours=4,
        max_exit_time=start + pd.Timedelta(hours=8), bar_lookup=bars,
        market_state_at=state, quantity=1.0, exit_side_cost=0.0,
    )
    assert hold2.exit_time == start + pd.Timedelta(hours=4)
    assert hold2.exit_reason == "ADAPTIVE_STAGNATION_24H"
    assert audit2["optional_exits_suppressed"] == 0


if __name__ == "__main__":
    self_test()
    print("TWO_SIDED_RESEARCH_SIDECAR_SELF_TEST=PASS")
