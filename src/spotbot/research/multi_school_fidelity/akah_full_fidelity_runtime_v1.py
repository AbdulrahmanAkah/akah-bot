"""Research-only integrated authority; not production. See source provenance manifest."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .akah_foundation_core_v1r1 import (
    ict_pending_expired,
    utc,
)
from .akah_foundation_core_v1r1 import wyckoff_a_reset_reason as wyckoff_a_reset_reason

# =============================================================================
# SHARED CAUSAL STRUCTURES
# =============================================================================


@dataclass(frozen=True)
class Pivot:
    kind: str
    index: int
    price: float
    pivot_time: pd.Timestamp
    confirm_time: pd.Timestamp
    volume: float = math.nan
    true_range: float = math.nan


@dataclass(frozen=True)
class StateTransition:
    system_id: str
    pair: str
    timestamp: pd.Timestamp
    from_state: str
    to_state: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ThesisIntent:
    system_id: str
    pair: str
    timestamp: pd.Timestamp
    branch: str
    stop: float
    target: float | None
    metadata: dict[str, Any] = field(default_factory=dict)


def confirmed_pivots_2l2r(frame: pd.DataFrame, left: int = 2, right: int = 2) -> list[Pivot]:
    """
    Causal pivot: the pivot at i becomes available only at timestamp i+right.
    """
    x = frame.reset_index(drop=True)
    out = []
    for i in range(left, len(x) - right):
        hs = x.loc[i - left : i + right, "high"].astype(float)
        ls = x.loc[i - left : i + right, "low"].astype(float)
        hi = float(x.loc[i, "high"])
        lo = float(x.loc[i, "low"])
        if hi == float(hs.max()) and int((hs == hi).sum()) == 1:
            out.append(
                Pivot(
                    "H",
                    i,
                    hi,
                    utc(x.loc[i, "timestamp"]),
                    utc(x.loc[i + right, "timestamp"]),
                    float(x.loc[i].get("volume", math.nan)),
                    float(x.loc[i].get("true_range", math.nan)),
                )
            )
        if lo == float(ls.min()) and int((ls == lo).sum()) == 1:
            out.append(
                Pivot(
                    "L",
                    i,
                    lo,
                    utc(x.loc[i, "timestamp"]),
                    utc(x.loc[i + right, "timestamp"]),
                    float(x.loc[i].get("volume", math.nan)),
                    float(x.loc[i].get("true_range", math.nan)),
                )
            )
    return sorted(out, key=lambda p: (p.confirm_time, p.index, p.kind))


def available_pivots(pivots: Sequence[Pivot], t: pd.Timestamp) -> list[Pivot]:
    t = utc(t)
    return [p for p in pivots if p.confirm_time <= t]


def collapse_same_kind(pivots: Sequence[Pivot]) -> list[Pivot]:
    out = []
    for p in sorted(pivots, key=lambda q: (q.pivot_time, q.confirm_time)):
        if not out or out[-1].kind != p.kind:
            out.append(p)
        else:
            prev = out[-1]
            if (p.kind == "H" and p.price > prev.price) or (p.kind == "L" and p.price < prev.price):
                out[-1] = p
    return out


def trend_from_pivots(pivots: Sequence[Pivot]) -> str:
    p = collapse_same_kind(pivots)
    hs = [q for q in p if q.kind == "H"][-2:]
    ls = [q for q in p if q.kind == "L"][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return "UNKNOWN"
    if hs[-1].price > hs[-2].price and ls[-1].price > ls[-2].price:
        return "UP"
    if hs[-1].price < hs[-2].price and ls[-1].price < ls[-2].price:
        return "DOWN"
    return "RANGE"


def ratio_at(pair_raw: pd.DataFrame, btc_raw: pd.DataFrame, t: pd.Timestamp) -> float | None:
    def close(df, tt):
        s = pd.to_datetime(df["timestamp"], utc=True)
        j = int(s.searchsorted(utc(tt), side="right")) - 1
        return None if j < 0 else float(df.iloc[j]["close"])

    p = close(pair_raw, t)
    b = close(btc_raw, t)
    if p is None or b is None or b <= 0:
        return None
    return p / b


def matched_swing_relative_strength(
    pair_raw: pd.DataFrame,
    btc_raw: pd.DataFrame,
    intermediate_pivots: Sequence[Pivot],
    t: pd.Timestamp,
) -> dict[str, Any]:
    """
    Frozen operationalization of the registry's 'rising over the two most recent
    confirmed intermediate swings'. The two latest confirmed asset swing points
    form the comparison timestamps. Pair/BTC ratio must rise from older to newer.
    """
    av = available_pivots(intermediate_pivots, t)
    if len(av) < 2:
        return {
            "eligible": False,
            "reason": "<2 confirmed intermediate swings",
            "ratio_old": None,
            "ratio_new": None,
        }
    p0, p1 = av[-2], av[-1]
    r0 = ratio_at(pair_raw, btc_raw, p0.pivot_time)
    r1 = ratio_at(pair_raw, btc_raw, p1.pivot_time)
    if r0 is None or r1 is None:
        return {"eligible": False, "reason": "ratio unavailable", "ratio_old": r0, "ratio_new": r1}
    return {
        "eligible": bool(r1 > r0),
        "reason": "pair/BTC ratio rising over latest two confirmed intermediate swing timestamps"
        if r1 > r0
        else "relative strength not rising",
        "ratio_old": r0,
        "ratio_new": r1,
        "old_swing_time": p0.pivot_time,
        "new_swing_time": p1.pivot_time,
    }


# =============================================================================
# WYCKOFF — FULL FROZEN RUNTIME
# =============================================================================

WY_STATES = {
    "UNKNOWN",
    "DOWNTREND",
    "A_STOPPING",
    "B_CAUSE_BUILDING",
    "C_TESTING_SUPPLY",
    "D_DEMAND_DOMINANT",
    "E_MARKUP",
    "REACCUMULATION",
    "DISTRIBUTION_RISK",
    "INVALID",
}


@dataclass
class WyckoffRuntime:
    pair: str
    state: str = "UNKNOWN"
    context: dict[str, Any] = field(default_factory=dict)
    transitions: list[StateTransition] = field(default_factory=list)

    def _change(self, t, new, reason, meta=None):
        if new not in WY_STATES:
            raise ValueError(new)
        if new != self.state:
            self.transitions.append(
                StateTransition(
                    "FS_WYCKOFF_FULL_LONG", self.pair, utc(t), self.state, new, reason, meta or {}
                )
            )
            self.state = new

    def readiness_vector(
        self,
        *,
        downward_objective_context: bool,
        bullish_activity: bool,
        downward_stride_broken: bool,
        higher_lows: bool,
        higher_highs: bool,
        relative_strength: bool,
        base_formed: bool,
        upward_potential_r: float,
    ) -> dict[str, bool]:
        c = self.context
        return {
            "DOWNSIDE_OBJECTIVE_CONTEXT": bool(downward_objective_context),
            "PS_SC_ST": bool(c.get("sc") and c.get("ar") and c.get("st")),
            "BULLISH_ACTIVITY": bool(bullish_activity),
            "DOWNWARD_STRIDE_BROKEN": bool(downward_stride_broken),
            "HIGHER_LOWS": bool(higher_lows),
            "HIGHER_HIGHS": bool(higher_highs),
            "RELATIVE_STRENGTH": bool(relative_strength),
            "BASE_FORMED": bool(base_formed),
            "UPWARD_POTENTIAL_GE_3R": bool(
                math.isfinite(upward_potential_r) and upward_potential_r >= 3.0
            ),
        }

    def step(self, t: pd.Timestamp, event: str, meta: dict[str, Any] | None = None):
        """
        Event-driven phase machine. Bar-to-event detection is separate so every
        phase transition can be fixture-tested without economic replay.
        """
        t = utc(t)
        m = meta or {}
        # universal structural risk
        if event == "DISTRIBUTION_RISK":
            self._change(t, "DISTRIBUTION_RISK", "definite distribution/supply dominance", m)
            return
        if self.state == "UNKNOWN" and event == "PRIOR_DOWNTREND":
            self._change(t, "DOWNTREND", "prior decline confirmed", m)
            return
        if self.state == "DOWNTREND" and event == "SELLING_CLIMAX":
            self.context = {"sc": m.copy(), "sc_time": t}
            self._change(t, "A_STOPPING", "PS/SC stopping action", m)
            return
        if self.state == "A_STOPPING":
            if event == "AUTOMATIC_RALLY":
                self.context["ar"] = m.copy()
                return
            if event == "SECONDARY_TEST_REDUCED_SUPPLY" and self.context.get("ar"):
                self.context["st"] = m.copy()
                self.context["support"] = float(
                    m.get("support", self.context["sc"].get("low", math.nan))
                )
                self.context["resistance"] = float(
                    m.get("resistance", self.context["ar"].get("high", math.nan))
                )
                self._change(t, "B_CAUSE_BUILDING", "SC/AR/ST define range", m)
                return
            if event in {
                "A_STRUCTURAL_FAIL",
                "A_TIMEOUT",
                "NEW_STRONGER_SC",
                "STOPPING_RESOLVED_WITHOUT_ST",
            }:
                nxt = "DOWNTREND" if event == "A_STRUCTURAL_FAIL" else "UNKNOWN"
                self.context = {}
                self._change(t, nxt, f"A_STOPPING liveness reset: {event}", m)
                return
        if self.state == "B_CAUSE_BUILDING":
            if event in {"SPRING_RECLAIM", "HIGHER_RANGE_SUPPLY_TEST"}:
                self.context["phase_c"] = m.copy()
                self._change(t, "C_TESTING_SUPPLY", "Phase C supply test", m)
                return
            if event == "RANGE_SUPPORT_FAIL":
                self.context = {}
                self._change(t, "DOWNTREND", "range support failed", m)
                return
        if self.state == "C_TESTING_SUPPLY" and event == "SOS_DEMAND_DOMINANCE":
            self.context["sos"] = m.copy()
            self._change(t, "D_DEMAND_DOMINANT", "successful test + SOS", m)
            return
        if self.state == "D_DEMAND_DOMINANT" and event == "LPS_HOLDS":
            self.context["lps"] = m.copy()
            self._change(t, "E_MARKUP", "SOS followed by valid LPS / higher low", m)
            return
        if self.state == "E_MARKUP" and event == "HIGHER_LEVEL_RANGE_FORMS":
            self.context = {"prior_markup": True, "range": m.copy()}
            self._change(t, "REACCUMULATION", "new higher-level range within markup", m)
            return
        if self.state == "REACCUMULATION" and event == "REACCUMULATION_SOS_LPS":
            self.context["lps"] = m.copy()
            self._change(t, "E_MARKUP", "reaccumulation resolves upward", m)
            return

    def entry_intent(
        self,
        t: pd.Timestamp,
        *,
        branch: str,
        market_state: str,
        rs: dict[str, Any],
        readiness: dict[str, bool],
        entry: float,
        structural_low: float,
        pnf_objective: float,
    ) -> ThesisIntent | None:
        allowed_market = {"C_TESTING_SUPPLY", "D_DEMAND_DOMINANT", "E_MARKUP", "REACCUMULATION"}
        if market_state not in allowed_market:
            return None
        if not rs.get("eligible", False):
            return None
        if not all(readiness.values()):
            return None
        risk = entry - structural_low
        if risk <= 0 or pnf_objective - entry < 3.0 * risk:
            return None
        if branch == "SPRING_TEST" and self.state not in {"C_TESTING_SUPPLY", "D_DEMAND_DOMINANT"}:
            return None
        if branch in {"NO_SPRING_LPS", "REACCUMULATION_LPS"} and self.state != "E_MARKUP":
            return None
        return ThesisIntent(
            "FS_WYCKOFF_FULL_LONG",
            self.pair,
            utc(t),
            branch,
            structural_low,
            pnf_objective,
            {
                "staged_initial_fraction": 0.5 if branch == "SPRING_TEST" else 1.0,
                "add_remaining_at_phase_d_lps": branch == "SPRING_TEST",
                "management": "trail only after new SOS then confirmed higher LPS; P&F objective is stop-look-listen",  # noqa: E501 - frozen source literal
            },
        )


# =============================================================================
# ICT / SMC — BOUNDED COMPLETE 2022 CORE CRYPTO ADAPTATION
# =============================================================================


def ny_session_state(t: pd.Timestamp) -> str:
    q = utc(t).tz_convert("America/New_York")
    if q.weekday() >= 5:
        return "OUTSIDE_WEEKDAY_MODEL"
    tm = q.hour * 60 + q.minute
    if tm < 8 * 60 + 30:
        return "PRE_NY_0830"
    if tm < 12 * 60:
        return "POST_NY_0830"
    if tm < 16 * 60:
        return "NY_AFTERNOON"
    return "OUTSIDE_WEEKDAY_MODEL"


def dealing_range_state(price: float, low: float, high: float) -> str:
    if high <= low:
        return "AMBIGUOUS"
    eq = (low + high) / 2
    if price < eq:
        return "DISCOUNT"
    if price > eq:
        return "PREMIUM"
    return "EQUILIBRIUM"


def prior_day_anchors(hourly: pd.DataFrame, t: pd.Timestamp) -> dict[str, float | None]:
    x = hourly.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    tt = utc(t)
    ny = x["timestamp"].dt.tz_convert("America/New_York")
    target = tt.tz_convert("America/New_York")
    d = target.date()
    prev = (pd.Timestamp(d) - pd.Timedelta(days=1)).date()
    out = {}
    for name, day in [("prior", prev), ("today", d)]:
        q = x.loc[ny.dt.date == day]
        out[f"{name}_high"] = float(q["high"].max()) if len(q) else None
        out[f"{name}_low"] = float(q["low"].min()) if len(q) else None
    # anchors available only once their timestamp has passed
    for label, hour, minute in [("ny_midnight", 0, 0), ("ny_0830", 8, 30)]:
        at = pd.Timestamp(
            year=target.year,
            month=target.month,
            day=target.day,
            hour=hour,
            minute=minute,
            tz="America/New_York",
        ).tz_convert("UTC")
        q = x.loc[x["timestamp"] <= min(tt, at)]
        q = q.loc[q["timestamp"] >= at - pd.Timedelta(hours=1)]
        out[label] = float(q.iloc[-1]["open"]) if len(q) and tt >= at else None
    return out


def smt_bullish_context(
    btc: pd.DataFrame, eth: pd.DataFrame, t: pd.Timestamp, hours: int = 24
) -> bool:
    """
    Supporting-only SMT proxy: BTC makes a lower rolling low vs prior window
    while ETH does not, or vice versa. Never a mandatory V1 gate.
    """
    t = utc(t)

    def lows(df):
        x = df.copy()
        x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
        a = x[(x["timestamp"] <= t) & (x["timestamp"] > t - pd.Timedelta(hours=hours))]
        b = x[
            (x["timestamp"] <= t - pd.Timedelta(hours=hours))
            & (x["timestamp"] > t - pd.Timedelta(hours=2 * hours))
        ]
        return (float(a["low"].min()), float(b["low"].min())) if len(a) and len(b) else (None, None)

    ba, bb = lows(btc)
    ea, eb = lows(eth)
    if None in (ba, bb, ea, eb):
        return False
    return (ba < bb and ea >= eb) or (ea < eb and ba >= bb)


def bullish_fvg(prev: pd.Series, mid: pd.Series, cur: pd.Series) -> tuple[float, float] | None:
    # bullish three-candle imbalance
    if float(cur["low"]) > float(prev["high"]) and float(mid["close"]) > float(mid["open"]):
        return float(prev["high"]), float(cur["low"])
    return None


def last_bearish_order_block(
    hourly: pd.DataFrame, displacement_index: int, lookback: int = 12
) -> dict[str, Any] | None:
    lo = max(0, displacement_index - lookback)
    for j in range(displacement_index - 1, lo - 1, -1):
        r = hourly.iloc[j]
        if float(r["close"]) < float(r["open"]):
            return {
                "index": j,
                "time": utc(r["timestamp"]),
                "low": float(r["low"]),
                "high": float(r["high"]),
            }
    return None


@dataclass
class ICTPending:
    raid_time: pd.Timestamp
    raid_low: float
    internal_high: float
    target: float
    state: str = "SELLSIDE_RAIDED"
    fvg: tuple[float, float] | None = None
    fvg_created_at: pd.Timestamp | None = None
    mss_time: pd.Timestamp | None = None
    order_block: dict[str, Any] | None = None
    validated_ob: bool = False


@dataclass
class ICT2022CoreRuntime:
    pair: str
    pending: ICTPending | None = None
    transitions: list[StateTransition] = field(default_factory=list)

    def invalidate_pending_raid(self, t, bar_low):
        """Every later completed bar checks protection, even before MSS/FVG."""
        p = self.pending
        t = utc(t)
        if p is None or t <= p.raid_time or float(bar_low) > p.raid_low:
            return False
        self.transitions.append(
            StateTransition(
                "FS_ICT_2022_CORE_CRYPTO_LONG",
                self.pair,
                t,
                p.state,
                "INVALIDATED",
                "raid low violated before entry",
                {"raid_time": str(p.raid_time), "raid_low": p.raid_low},
            )
        )
        self.pending = None
        return True

    def expire_if_needed(self, t: pd.Timestamp):
        if self.pending and ict_pending_expired(self.pending.raid_time, t):
            self.transitions.append(
                StateTransition(
                    "FS_ICT_2022_CORE_CRYPTO_LONG",
                    self.pair,
                    utc(t),
                    self.pending.state,
                    "EXPIRED",
                    "NY 16:00 intraday thesis expiry",
                    {},
                )
            )
            self.pending = None

    def register_raid(
        self,
        t,
        raid_low,
        internal_high,
        target,
        *,
        htf_bias: str,
        dealing_state: str,
        reclaimed: bool,
        session_state: str,
    ):
        self.expire_if_needed(t)
        if self.pending is not None:
            return False
        if session_state not in {"POST_NY_0830", "NY_AFTERNOON"}:
            return False
        if htf_bias not in {"BULLISH_DRAW", "TRANSITION_BULLISH"}:
            return False
        if not (dealing_state == "DISCOUNT" or reclaimed):
            return False
        if not reclaimed:
            return False
        self.pending = ICTPending(utc(t), float(raid_low), float(internal_high), float(target))
        self.transitions.append(
            StateTransition(
                "FS_ICT_2022_CORE_CRYPTO_LONG",
                self.pair,
                utc(t),
                "SELLSIDE_AVAILABLE",
                "SELLSIDE_RAIDED",
                "external sell-side liquidity raid and reclaim",
                {},
            )
        )
        return True

    def register_mss_displacement(self, t, close, prior_close, atr, fvg, order_block):
        if not self.pending:
            return False
        self.expire_if_needed(t)
        if not self.pending:
            return False
        t = utc(t)
        # Gate-1 fidelity: raid -> later MSS/displacement -> later retracement.
        if t <= self.pending.raid_time:
            return False
        if close <= self.pending.internal_high:
            return False
        if not math.isfinite(atr) or close - prior_close < 0.5 * atr:
            return False
        if fvg is None:
            return False
        self.pending.fvg = fvg
        self.pending.fvg_created_at = t
        self.pending.mss_time = t
        self.pending.order_block = order_block
        self.pending.state = "BULLISH_DISPLACEMENT"
        self.transitions.append(
            StateTransition(
                "FS_ICT_2022_CORE_CRYPTO_LONG",
                self.pair,
                t,
                "SELLSIDE_RAIDED",
                "BULLISH_DISPLACEMENT",
                "MSS through internal high + displacement + bullish FVG",
                {"fvg": fvg, "fvg_created_at": str(t)},
            )
        )
        return True

    def validate_order_block(self, t, close):
        if not self.pending or not self.pending.order_block:
            return False
        if close > float(self.pending.order_block["high"]):
            self.pending.validated_ob = True
            self.transitions.append(
                StateTransition(
                    "FS_ICT_2022_CORE_CRYPTO_LONG",
                    self.pair,
                    utc(t),
                    "BULLISH_DISPLACEMENT",
                    "VALIDATED_ORDER_BLOCK",
                    "last opposing candle validated by later structure",
                    {},
                )
            )
            return True
        return False

    def retracement_intent(self, t, bar_low, bar_high, bar_close) -> ThesisIntent | None:
        if self.invalidate_pending_raid(t, bar_low):
            return None
        self.expire_if_needed(t)
        p = self.pending
        if p is None or p.fvg is None or p.fvg_created_at is None:
            return None
        t = utc(t)
        # FVG creation cannot satisfy its own retracement.
        if t <= p.fvg_created_at:
            return None
        f0, f1 = p.fvg
        touch = bar_low <= f1 and bar_high >= f0
        reject = touch and bar_close > f0
        if not reject:
            return None
        # OB remains diagnostic-only until a separately source-bound grammar exists.
        arr = "FVG"
        intent = ThesisIntent(
            "FS_ICT_2022_CORE_CRYPTO_LONG",
            self.pair,
            t,
            arr,
            p.raid_low,
            p.target,
            {
                "execution_array": arr,
                "day_boundary": ny_session_state(t),
                "bearish_mss_exit": True,
                "smt_supporting_only": True,
                "order_block_diagnostic_only": bool(p.validated_ob),
                "raid_time": str(p.raid_time),
                "mss_time": str(p.mss_time) if p.mss_time is not None else None,
                "fvg_created_at": str(p.fvg_created_at),
                "retrace_time": str(t),
            },
        )
        self.transitions.append(
            StateTransition(
                "FS_ICT_2022_CORE_CRYPTO_LONG",
                self.pair,
                t,
                p.state,
                "RETRACE_CONFIRMED",
                "first strictly-later causal rejection/reclaim from frozen FVG",
                {"array": arr, "fvg_created_at": str(p.fvg_created_at)},
            )
        )
        self.pending = None
        return intent


# =============================================================================
# HARMONIC — FULL PUBLICLY BINDABLE FAMILY
# =============================================================================


@dataclass(frozen=True)
class HarmonicCandidate:
    pattern: str
    X: float
    A: float
    B: float
    C: float
    D: float
    prz_low: float
    prz_high: float
    make_or_break: float
    metadata: dict[str, Any] = field(default_factory=dict)


def _r(a, b, c) -> float:
    den = abs(b - a)
    return math.nan if den <= 0 else abs(c - b) / den


def _near(v, target, tol) -> bool:
    return math.isfinite(v) and abs(v - target) <= tol


def _directional_level(origin: float, anchor: float, ratio: float) -> float:
    """Project from anchor back through origin direction. For bullish X<A this is A-ratio*XA."""
    return anchor - math.copysign(ratio * abs(anchor - origin), anchor - origin)


def project_harmonic_prz(X, A, B, C, pattern: str) -> dict[str, Any] | None:
    """Project a tight PRZ from XABC only, before D is observed."""
    xa = abs(A - X)
    ab = abs(B - A)
    bc = abs(C - B)
    if min(xa, ab, bc) <= 0:
        return None
    bullish = A > X
    rev = -1.0 if C > B else 1.0

    def xa_level(q):
        return A - (q * xa if bullish else -q * xa)

    def bc_level(q):
        return C + rev * q * bc

    def ab_level(q):
        return C + rev * q * ab

    specs = {
        "GARTLEY": {"xa": 0.786, "bc": [1.13, 1.27, 1.618], "ab": [1.0, 1.27], "stop": 1.0},
        "BAT": {"xa": 0.886, "bc": [1.618, 2.0, 2.618], "ab": [1.0, 1.27], "stop": 1.13},
        "ALTERNATE_BAT": {
            "xa": 1.13,
            "bc": [2.0, 2.24, 2.618, 3.14, 3.618],
            "ab": [1.618, 2.0, 2.24, 2.618, 3.14, 3.618],
            "stop": 1.30,
        },
        "BUTTERFLY": {
            "xa": 1.27,
            "bc": [1.618, 2.0, 2.24, 2.618],
            "ab": [1.0, 1.27, 1.618],
            "stop": 1.50,
        },
        "CRAB": {
            "xa": 1.618,
            "bc": [2.618, 3.14, 3.618],
            "ab": [1.0, 1.27, 1.618, 2.0, 2.24, 2.618, 3.14, 3.618],
            "stop": 1.80,
        },
        "DEEP_CRAB": {
            "xa": 1.618,
            "bc": [2.24, 2.618, 3.14, 3.618],
            "ab": [1.0, 1.27],
            "stop": 1.80,
        },
        "ABCD": {"xa": None, "bc": [], "ab": [1.0], "stop": None},
    }
    sp = specs.get(pattern)
    if sp is None:
        return None
    if pattern == "ABCD":
        lev = ab_level(1.0)
        return {
            "pattern": pattern,
            "levels": [lev],
            "prz_low": lev,
            "prz_high": lev,
            "make_or_break": min(B, C) if bullish else max(B, C),
        }
    xalev = xa_level(sp["xa"])
    # PRZ convergence: for optional BC and AB=CD variants, select the projection
    # closest to the defining XA level without consulting D.
    bc_levels = [bc_level(q) for q in sp["bc"]]
    ab_levels = [ab_level(q) for q in sp["ab"]]
    chosen_bc = min(bc_levels, key=lambda z: abs(z - xalev))
    chosen_ab = min(ab_levels, key=lambda z: abs(z - xalev))
    levels = [xalev, chosen_bc, chosen_ab]
    return {
        "pattern": pattern,
        "levels": levels,
        "prz_low": min(levels),
        "prz_high": max(levels),
        "make_or_break": xa_level(sp["stop"]),
    }


def classify_harmonic(X, A, B, C, D) -> list[HarmonicCandidate]:
    """Classify only when defining ratios and the preprojected PRZ agree."""
    xa = abs(A - X)
    ab = abs(B - A)
    bc = abs(C - B)
    cd = abs(D - C)
    if min(xa, ab, bc, cd) <= 0:
        return []
    bxa = ab / xa
    adx = abs(A - D) / xa
    bcp = cd / bc
    abcd = cd / ab
    rules = {
        "GARTLEY": (
            _near(bxa, 0.618, 0.03),
            _near(adx, 0.786, 0.04),
            1.10 <= bcp <= 1.70,
            0.90 <= abcd <= 1.35,
        ),
        "BAT": (
            bxa < 0.618 and 0.35 <= bxa <= 0.55,
            _near(adx, 0.886, 0.04),
            1.618 <= bcp <= 2.70,
            0.90 <= abcd <= 1.35,
        ),
        "ALTERNATE_BAT": (bxa <= 0.402, _near(adx, 1.13, 0.05), bcp >= 2.0, abcd >= 1.50),
        "BUTTERFLY": (
            _near(bxa, 0.786, 0.04),
            _near(adx, 1.27, 0.06),
            1.60 <= bcp <= 2.70,
            0.90 <= abcd <= 1.70,
        ),
        "CRAB": (0.35 <= bxa <= 0.65, _near(adx, 1.618, 0.08), 2.50 <= bcp <= 3.75, abcd >= 0.90),
        "DEEP_CRAB": (
            _near(bxa, 0.886, 0.04),
            _near(adx, 1.618, 0.08),
            2.20 <= bcp <= 3.75,
            0.90 <= abcd <= 1.35,
        ),
        "ABCD": (True, True, True, 0.85 <= abcd <= 1.15),
    }
    out = []
    for name, conds in rules.items():
        if not all(conds):
            continue
        pr = project_harmonic_prz(X, A, B, C, name)
        if pr is None:
            continue
        # PRZ must be a genuine convergence zone: <= 20% XA width for M/W families.
        if name != "ABCD":
            max_width = (0.35 if name in {"ALTERNATE_BAT", "CRAB", "DEEP_CRAB"} else 0.20) * xa
            if pr["prz_high"] - pr["prz_low"] > max_width:
                continue
        tol = 0.03 * xa
        if pr["prz_low"] - tol <= D <= pr["prz_high"] + tol:
            out.append(
                HarmonicCandidate(
                    name,
                    X,
                    A,
                    B,
                    C,
                    D,
                    pr["prz_low"],
                    pr["prz_high"],
                    pr["make_or_break"],
                    {
                        "B_XA": bxa,
                        "AD_XA": adx,
                        "BC_proj": bcp,
                        "ABCD": abcd,
                        "projected_levels": pr["levels"],
                    },
                )
            )
    return out


def project_five_zero_prz(X, A, B, C) -> dict[str, Any] | None:
    ab = abs(B - A)
    bc = abs(C - B)
    if min(ab, bc) <= 0:
        return None
    bc_ab = bc / ab
    if not (1.618 <= bc_ab <= 2.24):
        return None
    rev = -1.0 if C > B else 1.0
    level_50 = C + rev * 0.50 * bc
    # Reciprocal AB=CD projects an AB-equivalent move opposite BC from C.
    level_rec = C + rev * ab
    return {
        "levels": [level_50, level_rec],
        "prz_low": min(level_50, level_rec),
        "prz_high": max(level_50, level_rec),
        "make_or_break": min(B, C) if rev > 0 else max(B, C),
        "BC_AB": bc_ab,
    }


def classify_five_zero(X, A, B, C, D) -> HarmonicCandidate | None:
    pr = project_five_zero_prz(X, A, B, C)
    if pr is None:
        return None
    ab = abs(B - A)
    bc = abs(C - B)
    cd = abs(D - C)
    tol = 0.03 * max(ab, bc)
    if (
        pr["prz_low"] - tol <= D <= pr["prz_high"] + tol
        and 0.45 <= cd / bc <= 0.55
        and 0.90 <= cd / ab <= 1.10
    ):
        return HarmonicCandidate(
            "FIVE_ZERO",
            X,
            A,
            B,
            C,
            D,
            pr["prz_low"],
            pr["prz_high"],
            pr["make_or_break"],
            {
                "BC_AB": bc / ab,
                "D_BC": cd / bc,
                "reciprocal_ABCD": cd / ab,
                "projected_levels": pr["levels"],
            },
        )
    return None


def project_shark_prz(O, X, A, B) -> dict[str, Any] | None:  # noqa: E741 - retained geometric notation
    ox = abs(X - O)
    ab = abs(B - A)
    if min(ox, ab) <= 0:
        return None
    # completion retests/extends the O anchor opposite the O->X impulse
    sign = 1.0 if X > O else -1.0
    l886 = O - sign * 0.886 * ox
    l113 = O - sign * 1.13 * ox
    return {
        "levels": [l886, l113],
        "prz_low": min(l886, l113),
        "prz_high": max(l886, l113),
        "make_or_break": l113,
    }


def classify_shark(O, X, A, B, C) -> HarmonicCandidate | None:  # noqa: E741 - retained geometric notation
    pr = project_shark_prz(O, X, A, B)
    if pr is None:
        return None
    ab = abs(B - A)
    impulse = abs(C - B) / ab if ab > 0 else math.nan
    tol = 0.03 * abs(X - O)
    if impulse >= 1.618 and pr["prz_low"] - tol <= C <= pr["prz_high"] + tol:
        return HarmonicCandidate(
            "SHARK",
            O,
            X,
            A,
            B,
            C,
            pr["prz_low"],
            pr["prz_high"],
            pr["make_or_break"],
            {"extreme_impulse": impulse, "projected_levels": pr["levels"]},
        )
    return None


def full_prz_tested(bar_low: float, bar_high: float, prz_low: float, prz_high: float) -> bool:
    return bar_low <= prz_low and bar_high >= prz_high


def bullish_rsi_bamm(prices: Sequence[float], rsis: Sequence[float]) -> bool:
    if len(prices) < 5 or len(rsis) != len(prices):
        return False
    troughs = [
        i
        for i in range(1, len(rsis) - 1)
        if rsis[i] < 30 and rsis[i] <= rsis[i - 1] and rsis[i] <= rsis[i + 1]
    ]
    if len(troughs) < 2:
        return False
    a, b = troughs[-2], troughs[-1]
    divergence = prices[b] < prices[a] and rsis[b] > rsis[a]
    recross = rsis[-1] > 30 and b < len(rsis) - 1
    return bool(divergence and recross)


@dataclass
class HarmonicLifecycle:
    candidate: HarmonicCandidate
    state: str = "PRZ_PROJECTED"
    terminal_time: pd.Timestamp | None = None
    type1_complete: bool = False
    transitions: list[str] = field(default_factory=list)

    def invalidate(self):
        self.state = "INVALIDATED"
        self.type1_complete = False
        self.transitions.append("INVALIDATED")

    def test_prz(self, t, low, high):
        if self.state != "PRZ_PROJECTED":
            return False
        if full_prz_tested(low, high, self.candidate.prz_low, self.candidate.prz_high):
            self.state = "TERMINAL_BAR_COMPLETE"
            self.terminal_time = utc(t)
            self.transitions.append("TERMINAL_BAR_COMPLETE")
            return True
        return False

    def type1_confirm(self, price_action: bool, rsi_bamm: bool) -> bool:
        if self.state != "TERMINAL_BAR_COMPLETE":
            return False
        if price_action or rsi_bamm:
            self.state = "TYPE_I_ACTIVE"
            self.transitions.append("TYPE_I_ACTIVE")
            return True
        return False

    def type1_targets(self) -> tuple[float, float]:
        span = abs(self.candidate.A - self.candidate.D)
        return self.candidate.D + 0.382 * span, self.candidate.D + 0.618 * span

    def complete_type1(self):
        if self.state == "TYPE_I_ACTIVE":
            self.state = "TYPE_I_COMPLETE"
            self.type1_complete = True
            self.transitions.append("TYPE_I_COMPLETE")

    def type2_retest(self, low, high, renewed_confirmation: bool) -> bool:
        if self.state == "INVALIDATED":
            return False
        if low <= self.candidate.make_or_break:
            self.invalidate()
            return False
        if not self.type1_complete:
            return False
        touches = low <= self.candidate.prz_high and high >= self.candidate.prz_low
        intact = low > self.candidate.make_or_break
        if touches and intact:
            self.state = "TYPE_II_RETEST"
            self.transitions.append("TYPE_II_RETEST")
            if renewed_confirmation:
                self.state = "TYPE_II_ACTIVE"
                self.transitions.append("TYPE_II_ACTIVE")
                return True
        return False


# =============================================================================
# CLASSICAL — COHERENT TREND/PATTERN SYSTEM
# =============================================================================


@dataclass(frozen=True)
class ClassicalPattern:
    pattern_id: str
    kind: str
    boundary: float
    support: float
    height: float
    prior_trend: str
    formed_at: pd.Timestamp
    metadata: dict[str, Any] = field(default_factory=dict)


def persistent_gaps(frame: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    x = frame.reset_index(drop=True)
    for i in range(1, len(x)):
        if float(x.loc[i, "low"]) > float(x.loc[i - 1, "high"]):
            out.append(
                {
                    "kind": "GAP_UP",
                    "time": utc(x.loc[i, "timestamp"]),
                    "low": float(x.loc[i - 1, "high"]),
                    "high": float(x.loc[i, "low"]),
                }
            )
        elif float(x.loc[i, "high"]) < float(x.loc[i - 1, "low"]):
            out.append(
                {
                    "kind": "GAP_DOWN",
                    "time": utc(x.loc[i, "timestamp"]),
                    "low": float(x.loc[i, "high"]),
                    "high": float(x.loc[i - 1, "low"]),
                }
            )
    return out


def channel_from_pivots(pivs: Sequence[Pivot]) -> dict[str, Any] | None:
    p = collapse_same_kind(pivs)
    lows = [q for q in p if q.kind == "L"][-2:]
    highs = [q for q in p if q.kind == "H"][-2:]
    if len(lows) < 2 or len(highs) < 2:
        return None
    return {
        "lower": [(lows[0].pivot_time, lows[0].price), (lows[1].pivot_time, lows[1].price)],
        "upper": [(highs[0].pivot_time, highs[0].price), (highs[1].pivot_time, highs[1].price)],
        "trend": trend_from_pivots(p),
    }


def classical_patterns_from_pivots(
    pivs: Sequence[Pivot], atr: float, t: pd.Timestamp
) -> list[ClassicalPattern]:
    p = collapse_same_kind(available_pivots(pivs, t))
    if len(p) < 4:
        return []
    tol = max(0.25 * atr, 1e-12)
    out = []
    # Rectangle from last 4+ alternating pivots
    q = p[-6:]
    hs = [x for x in q if x.kind == "H"]
    ls = [x for x in q if x.kind == "L"]
    if len(hs) >= 2 and len(ls) >= 2:
        if (
            max(x.price for x in hs) - min(x.price for x in hs) <= 2 * tol
            and max(x.price for x in ls) - min(x.price for x in ls) <= 2 * tol
        ):
            top = sum(x.price for x in hs) / len(hs)
            bot = sum(x.price for x in ls) / len(ls)
            out.append(
                ClassicalPattern(
                    f"RECT:{q[0].index}:{q[-1].index}",
                    "RECTANGLE",
                    top,
                    bot,
                    top - bot,
                    trend_from_pivots(p[:-2]),
                    utc(q[-1].confirm_time),
                )
            )
        if hs[-1].price >= hs[-2].price - tol and ls[-1].price > ls[-2].price + tol:
            top = max(hs[-1].price, hs[-2].price)
            bot = ls[-1].price
            out.append(
                ClassicalPattern(
                    f"ASC:{q[0].index}:{q[-1].index}",
                    "ASC_TRIANGLE",
                    top,
                    bot,
                    top - bot,
                    trend_from_pivots(p[:-2]),
                    utc(q[-1].confirm_time),
                )
            )
        if hs[-1].price < hs[-2].price and ls[-1].price > ls[-2].price:
            top = hs[-1].price
            bot = ls[-1].price
            out.append(
                ClassicalPattern(
                    f"SYM:{q[0].index}:{q[-1].index}",
                    "SYMM_TRIANGLE",
                    top,
                    bot,
                    abs(top - bot),
                    trend_from_pivots(p[:-2]),
                    utc(q[-1].confirm_time),
                )
            )
    # Double bottom / inverse H&S
    lows = [x for x in p[-7:] if x.kind == "L"]
    highs = [x for x in p[-7:] if x.kind == "H"]
    if len(lows) >= 2 and abs(lows[-1].price - lows[-2].price) <= 2 * tol and highs:
        neck = (
            max(
                h.price
                for h in highs
                if h.pivot_time > lows[-2].pivot_time and h.pivot_time < lows[-1].pivot_time
            )
            if any(
                h.pivot_time > lows[-2].pivot_time and h.pivot_time < lows[-1].pivot_time
                for h in highs
            )
            else None
        )
        if neck:
            prior = [z for z in p if z.index < lows[-2].index]
            prior_trend = trend_from_pivots(prior) if len(prior) >= 4 else "UNKNOWN"
            out.append(
                ClassicalPattern(
                    f"DB:{lows[-2].index}:{lows[-1].index}",
                    "DOUBLE_BOTTOM",
                    neck,
                    min(lows[-1].price, lows[-2].price),
                    neck - min(lows[-1].price, lows[-2].price),
                    prior_trend,
                    utc(lows[-1].confirm_time),
                )
            )
    if (
        len(lows) >= 3
        and lows[-2].price < lows[-3].price
        and lows[-2].price < lows[-1].price
        and abs(lows[-3].price - lows[-1].price) <= 3 * tol
        and len(highs) >= 2
    ):
        neck = max(highs[-1].price, highs[-2].price)
        support = min(l.price for l in lows[-3:])  # noqa: E741 - retained geometric notation
        prior = [z for z in p if z.index < lows[-3].index]
        prior_trend = trend_from_pivots(prior) if len(prior) >= 4 else "UNKNOWN"
        out.append(
            ClassicalPattern(
                f"IHS:{lows[-3].index}:{lows[-1].index}",
                "INVERSE_HS",
                neck,
                support,
                neck - support,
                prior_trend,
                utc(lows[-1].confirm_time),
            )
        )
    return out


@dataclass
class ClassicalRuntime:
    pair: str
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)
    transitions: list[StateTransition] = field(default_factory=list)

    def mature(self, p: ClassicalPattern):
        self.pending[p.pattern_id] = {
            "pattern": p,
            "state": "MATURE",
            "breakout_time": None,
            "breakout_low": None,
        }

    def update_breakout(self, t, pid, close, volume, vol_median):
        q = self.pending.get(pid)
        if not q or q["state"] != "MATURE":
            return False
        p = q["pattern"]
        if close > p.boundary and volume >= vol_median:
            q["state"] = "BREAKOUT"
            q["breakout_time"] = utc(t)
            self.transitions.append(
                StateTransition(
                    "FS_CLASSICAL_FULL_LONG",
                    self.pair,
                    utc(t),
                    "MATURE",
                    "BREAKOUT",
                    "close beyond frozen boundary with volume confirmation",
                    {"pattern": p.kind},
                )
            )
            return True
        return False

    def entry_intent(
        self, t, pid, bar_low, bar_close, confirmed_higher_low: float | None = None
    ) -> ThesisIntent | None:
        q = self.pending.get(pid)
        if not q or q["state"] != "BREAKOUT":
            return None
        p = q["pattern"]
        if utc(t) <= q["breakout_time"]:
            return None
        retest = bar_low <= p.boundary and bar_close > p.boundary
        no_retest_continuation = (
            confirmed_higher_low is not None and confirmed_higher_low > p.boundary
        )
        if not (retest or no_retest_continuation):
            return None
        stop = min(bar_low if retest else confirmed_higher_low, p.support)
        target = p.boundary + p.height
        branch = "THROWBACK" if retest else "NO_RETEST_CONTINUATION"
        q["state"] = "CONTINUATION"
        self.transitions.append(
            StateTransition(
                "FS_CLASSICAL_FULL_LONG",
                self.pair,
                utc(t),
                "BREAKOUT",
                "CONTINUATION",
                branch,
                {"pattern": p.kind},
            )
        )
        return ThesisIntent(
            "FS_CLASSICAL_FULL_LONG",
            self.pair,
            utc(t),
            f"{p.kind}:{branch}",
            stop,
            target,
            {
                "trail_after_objective_progress": "beneath confirmed higher swing lows / channel",
                "exit_on_primary_trend_reversal": True,
                "gaps_and_channels_persistent_context": True,
            },
        )


# =============================================================================
# ELLIOTT — ONLINE MULTI-DEGREE HYPOTHESIS SET
# =============================================================================


@dataclass(frozen=True)
class ElliottCount:
    count_id: str
    degree: str
    kind: str
    direction: str
    points: tuple[Pivot, ...]
    invalidation: float
    objective: float | None
    created_at: pd.Timestamp
    priority: int = 1


def _alternating(points: Sequence[Pivot]) -> bool:
    return all(points[i].kind != points[i - 1].kind for i in range(1, len(points)))


@dataclass
class ElliottOnlineRuntime:
    seen: set[str] = field(default_factory=set)
    active: dict[str, ElliottCount] = field(default_factory=dict)

    def reconstruct(
        self, t: pd.Timestamp, degree_pivots: dict[str, Sequence[Pivot]]
    ) -> dict[str, list[ElliottCount]]:
        snapshot = {}
        for degree, pivs in degree_pivots.items():
            counts = enumerate_impulse_counts(pivs, degree, t) + enumerate_corrective_counts(
                pivs, degree, t
            )
            uniq = {c.count_id: c for c in counts}
            snapshot[degree] = list(uniq.values())
            for c in uniq.values():
                self.active[c.count_id] = c
        # invalidate using only current t/prices elsewhere; reconstruction itself never
        # sees future pivots.
        return snapshot

    @staticmethod
    def consensus(snapshot: dict[str, list[ElliottCount]]) -> str:
        material = []
        for degree in ("1D", "4H", "1H"):
            material.extend(snapshot.get(degree, []))
        if not material:
            return "AMBIGUOUS"
        dirs = {c.direction for c in material if c.priority >= 2}
        if dirs == {"BULLISH"}:
            return "CONSENSUS_BULLISH"
        if len(dirs) > 1:
            return "CONSENSUS_NEUTRAL"
        return "AMBIGUOUS"

    @staticmethod
    def common_invalidation(snapshot: dict[str, list[ElliottCount]]) -> float | None:
        bullish = [
            c.invalidation
            for xs in snapshot.values()
            for c in xs
            if c.direction == "BULLISH" and c.priority >= 2
        ]
        return max(bullish) if bullish else None


# =============================================================================
# DOW — BROAD CRYPTO ADAPTATION
# =============================================================================


def broad_equal_weight_confirmation(returns: dict[str, float | None]) -> dict[str, float | bool]:
    vals = [v for v in returns.values() if v is not None and math.isfinite(v)]
    if not vals:
        return {"breadth": math.nan, "equal_weight_return": math.nan, "confirmed": False}
    breadth = sum(v > 0 for v in vals) / len(vals)
    ew = float(np.mean(vals))
    return {
        "breadth": breadth,
        "equal_weight_return": ew,
        "confirmed": bool(breadth >= 0.5 and ew > 0),
    }


def friction_safe_stop(
    entry: float, stop: float, round_trip_cost_fraction: float, max_cost_r: float
) -> bool:
    risk = entry - stop
    if entry <= 0 or risk <= 0 or round_trip_cost_fraction < 0 or max_cost_r <= 0:
        return False
    cost_per_unit = entry * round_trip_cost_fraction
    return cost_per_unit / risk <= max_cost_r


@dataclass
class DowRuntime:
    state: str = "UNCONFIRMED"

    def update(
        self,
        btc_primary_trend: str,
        secondary_trend: str,
        confirmation: dict[str, Any],
        volume_confirms: bool,
    ) -> str:
        # Source-bound V1R1 recovery: reversal priority, then nonabsorbing restart.
        if btc_primary_trend == "DOWN" and self.state in {
            "PRIMARY_BULL",
            "RECONFIRMED_BULL",
            "SECONDARY_REACTION",
        }:
            self.state = "DEFINITE_REVERSAL"
            return self.state
        if (
            self.state == "DEFINITE_REVERSAL"
            and btc_primary_trend == "UP"
            and confirmation.get("confirmed")
        ):
            self.state = "PRIMARY_BULL"
            return self.state
        if (
            self.state == "UNCONFIRMED"
            and btc_primary_trend == "UP"
            and confirmation.get("confirmed")
        ):
            self.state = "PRIMARY_BULL"
        elif self.state == "PRIMARY_BULL" and secondary_trend in {"DOWN", "RANGE"}:
            self.state = "SECONDARY_REACTION"
        elif (
            self.state == "SECONDARY_REACTION"
            and btc_primary_trend == "UP"
            and secondary_trend == "UP"
            and confirmation.get("confirmed")
        ):
            self.state = "RECONFIRMED_BULL"
        elif (
            self.state in {"PRIMARY_BULL", "RECONFIRMED_BULL", "SECONDARY_REACTION"}
            and btc_primary_trend == "DOWN"
        ):
            self.state = "DEFINITE_REVERSAL"
        return self.state


# =============================================================================
# COHERENT HYBRIDS — TRUE SHARED STATE MACHINES
# =============================================================================


@dataclass
class HybridFSM:
    system_id: str
    stages: tuple[str, ...]
    state: str = "IDLE"
    idx: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def observe(
        self, t: pd.Timestamp, role: str, ok: bool, payload: dict[str, Any] | None = None
    ) -> str:
        if not ok:
            return self.state
        expected = self.stages[self.idx] if self.idx < len(self.stages) else None
        if role != expected:
            return self.state
        self.evidence[role] = payload or {}
        self.idx += 1
        self.state = (
            "THESIS_ACTIVE" if self.idx == len(self.stages) else f"AWAIT_{self.stages[self.idx]}"
        )
        return self.state

    def reset(self):
        self.state = "IDLE"
        self.idx = 0
        self.evidence = {}


def markup_continuation_fsm() -> HybridFSM:
    return HybridFSM(
        "HYB_MARKUP_CONTINUATION",
        (
            "MARKET_STATE",
            "SELECTION",
            "STRUCTURAL_STATE",
            "ACTIVATION",
            "ACCEPTANCE",
            "MANAGEMENT_BINDING",
        ),
    )


def failed_auction_reversal_fsm() -> HybridFSM:
    return HybridFSM(
        "HYB_FAILED_AUCTION_REVERSAL",
        (
            "MARKET_STATE",
            "SELECTION",
            "LOCATION",
            "FAILED_AUCTION",
            "CONFIRMATION",
            "ENTRY_LOCATION",
            "MANAGEMENT_BINDING",
        ),
    )


def corrective_completion_resumption_fsm() -> HybridFSM:
    return HybridFSM(
        "HYB_CORRECTIVE_COMPLETION_RESUMPTION",
        (
            "MARKET_STATE",
            "SELECTION",
            "CORRECTION_MODEL",
            "GEOMETRIC_LOCATION",
            "TRIGGER",
            "CONFIRMATION",
            "MANAGEMENT_BINDING",
        ),
    )


def alias_collapse_failed_auction(tags: Iterable[str]) -> str:
    aliases = {"SPRING", "LIQUIDITY_RAID", "FALSE_BREAKDOWN", "SELLSIDE_SWEEP"}
    return "FAILED_AUCTION" if any(t in aliases for t in tags) else "OTHER"


# =============================================================================
# FIDELITY COMPLETION EXTENSIONS — REQUIRED BY FROZEN REGISTRY
# =============================================================================


def percentage_pnf_cause(
    closes: Sequence[float], support: float, box_pct: float = 0.01, reversal: int = 3
) -> dict[str, float | int]:
    """Percentage P&F, 3-box reversal. Returns cause columns and conservative objective."""
    xs = [float(x) for x in closes if math.isfinite(float(x)) and float(x) > 0]
    if len(xs) < 2 or support <= 0:
        return {"columns": 0, "objective": math.nan, "box_pct": box_pct, "reversal": reversal}
    direction = 0
    col_anchor = xs[0]
    extreme = xs[0]
    columns = 1
    for px in xs[1:]:
        box = max(col_anchor * box_pct, 1e-12)
        if direction == 0:
            if px >= col_anchor + box:
                direction = 1
                extreme = px
            elif px <= col_anchor - box:
                direction = -1
                extreme = px
            continue
        if direction > 0:
            if px > extreme:
                extreme = px
            elif px <= extreme - reversal * box:
                columns += 1
                direction = -1
                col_anchor = extreme
                extreme = px
        else:
            if px < extreme:
                extreme = px
            elif px >= extreme + reversal * box:
                columns += 1
                direction = 1
                col_anchor = extreme
                extreme = px
    # Conservative horizontal cause translation; fixed source-inspired engineering adaptation.
    objective = support * (1.0 + columns * box_pct * reversal)
    return {"columns": columns, "objective": objective, "box_pct": box_pct, "reversal": reversal}


def pnf_sensitivity_shadow(
    closes: Sequence[float], support: float
) -> dict[str, dict[str, float | int]]:
    return {
        "PRIMARY_1PCT": percentage_pnf_cause(closes, support, 0.01, 3),
        "SHADOW_0P5PCT": percentage_pnf_cause(closes, support, 0.005, 3),
        "SHADOW_2PCT": percentage_pnf_cause(closes, support, 0.02, 3),
    }


def wyckoff_effort_result(
    volume: float, spread: float, progress: float, vol_median: float, spread_median: float
) -> str:
    if min(volume, spread, vol_median, spread_median) <= 0:
        return "UNKNOWN"
    high_effort = volume >= vol_median
    wide = spread >= spread_median
    if high_effort and wide and progress > 0:
        return "DEMAND_PROGRESS"
    if high_effort and progress <= 0:
        return "ABSORPTION_OR_SUPPLY"
    if not high_effort and not wide and progress >= 0:
        return "DIMINISHING_SUPPLY"
    return "NEUTRAL"


@dataclass
class WyckoffPositionPlan:
    branch: str
    structural_stop: float
    pnf_objective: float
    initial_fraction: float
    remaining_fraction: float
    current_stop: float

    def add_at_lps(self, lps_low: float) -> bool:
        if self.remaining_fraction <= 0:
            return False
        self.current_stop = max(self.current_stop, float(lps_low))
        self.remaining_fraction = 0.0
        return True

    def trail_after_sos_lps(self, lps_low: float):
        self.current_stop = max(self.current_stop, float(lps_low))

    def objective_state(self, price: float) -> str:
        return "STOP_LOOK_LISTEN" if price >= self.pnf_objective else "HOLD_THESIS"


def build_wyckoff_position_plan(intent: ThesisIntent) -> WyckoffPositionPlan:
    frac = float(intent.metadata.get("staged_initial_fraction", 1.0))
    return WyckoffPositionPlan(
        intent.branch, intent.stop, float(intent.target), frac, 1.0 - frac, intent.stop
    )


# ICT context + active management


def external_liquidity_map(
    prior: dict[str, float | None], pivots: Sequence[Pivot], t: pd.Timestamp
) -> dict[str, list[float]]:
    av = available_pivots(pivots, t)
    highs = [p.price for p in av if p.kind == "H"][-4:]
    lows = [p.price for p in av if p.kind == "L"][-4:]
    buy = [x for x in [prior.get("prior_high"), *highs] if x is not None]
    sell = [x for x in [prior.get("prior_low"), *lows] if x is not None]
    return {"buy_side": sorted(set(map(float, buy))), "sell_side": sorted(set(map(float, sell)))}


def ict_bias_state(
    d1_trend: str, h4_trend: str, price: float, buy_target: float | None, sell_target: float | None
) -> str:
    if (
        d1_trend == "UP"
        and h4_trend in {"UP", "RANGE"}
        and buy_target is not None
        and buy_target > price
    ):
        return "BULLISH_DRAW"
    if d1_trend == "DOWN" and sell_target is not None and sell_target < price:
        return "BEARISH_DRAW"
    if d1_trend == "UP" and h4_trend == "DOWN":
        return "TRANSITION_BULLISH"
    if d1_trend == "RANGE" or h4_trend == "RANGE":
        return "BALANCED"
    return "AMBIGUOUS"


def ict_manage_active(
    *,
    t: pd.Timestamp,
    raid_time: pd.Timestamp,
    bar_low: float,
    bar_high: float,
    raid_low: float,
    target: float,
    bearish_mss: bool,
) -> str:
    if bar_low <= raid_low:
        return "STRUCTURAL_INVALIDATION"
    if bar_high >= target:
        return "OPPOSING_LIQUIDITY_TARGET"
    if bearish_mss:
        return "BEARISH_MSS_EXIT_NEXT_OPEN"
    if ict_pending_expired(raid_time, t):
        return "NY_1600_DAY_BOUNDARY"
    return "HOLD"


# Classical missing families + active management


def continuation_patterns_from_bars(
    frame: pd.DataFrame, atr: float, prior_pivots=None
) -> list[ClassicalPattern]:
    x = frame.reset_index(drop=True)
    if len(x) < 20 or not math.isfinite(atr) or atr <= 0:
        return []
    out = []
    now = utc(x.iloc[-1]["timestamp"])
    pole_start = float(x.iloc[-18]["close"])
    pole_end = float(x.iloc[-8]["close"])
    pole = pole_end - pole_start
    tail = x.iloc[-8:]
    hi = tail["high"].astype(float).to_numpy()
    lo = tail["low"].astype(float).to_numpy()
    if pole >= 3 * atr:
        # flag: contained, gently downward/sloping corrective channel
        h_slope = float(np.polyfit(np.arange(len(hi)), hi, 1)[0])
        l_slope = float(np.polyfit(np.arange(len(lo)), lo, 1)[0])
        if h_slope < 0 and l_slope < 0 and abs(h_slope - l_slope) <= 0.25 * atr:
            boundary = float(hi[-1])
            support = float(lo.min())
            out.append(
                ClassicalPattern(
                    f"FLAG:{len(x)}", "FLAG", boundary, support, pole, "UP", now, {"pole": pole}
                )
            )
        # pennant: converging highs/lows after pole
        if hi[-1] < hi[0] and lo[-1] > lo[0]:
            boundary = float(hi[-1])
            support = float(lo[-1])
            out.append(
                ClassicalPattern(
                    f"PENNANT:{len(x)}",
                    "PENNANT",
                    boundary,
                    support,
                    pole,
                    "UP",
                    now,
                    {"pole": pole},
                )
            )
    # base breakout candidate: context must be measured before formation.
    base = x.iloc[-12:]
    height = float(base["high"].max() - base["low"].min())
    prior_frame = x.iloc[:-12]
    prior_pivs = (
        (confirmed_pivots_2l2r(prior_frame) if len(prior_frame) >= 8 else [])
        if prior_pivots is None
        else prior_pivots
    )
    prior_trend = trend_from_pivots(prior_pivs) if len(prior_pivs) >= 4 else "UNKNOWN"
    if height <= 4 * atr:
        top = float(base["high"].max())
        bot = float(base["low"].min())
        out.append(
            ClassicalPattern(
                f"BASE:{len(x)}", "BASE_BREAKOUT", top, bot, height, prior_trend, now, {}
            )
        )
    return out


def classical_management_update(
    *,
    price: float,
    target: float,
    current_stop: float,
    confirmed_higher_low: float | None,
    primary_trend: str,
    pattern_failed: bool,
) -> dict[str, Any]:
    if pattern_failed:
        return {"action": "EXIT_PATTERN_FAILURE", "stop": current_stop}
    if primary_trend == "DOWN":
        return {"action": "EXIT_PRIMARY_TREND_REVERSAL", "stop": current_stop}
    stop = current_stop
    if confirmed_higher_low is not None and price >= target * 0.75:
        stop = max(stop, float(confirmed_higher_low))
    if price >= target:
        return {"action": "OBJECTIVE_REACHED", "stop": stop}
    return {"action": "HOLD", "stop": stop}


# Elliott completed impulse + combination + invalidation


def validate_completed_impulse(points: Sequence[Pivot]) -> bool:
    if len(points) != 6 or [p.kind for p in points] != ["L", "H", "L", "H", "L", "H"]:
        return False
    w0, w1, w2, w3, w4, w5 = points
    if w2.price <= w0.price:
        return False
    if w4.price <= w1.price:
        return False  # standard impulse wave4 non-overlap
    l1 = w1.price - w0.price
    l3 = w3.price - w2.price
    l5 = w5.price - w4.price
    if min(l1, l3, l5) <= 0:
        return False
    return not l3 < min(l1, l5)


# Override corrective enumeration to include explicit ZIGZAG + FLAT + TRIANGLE + COMBINATION.
def enumerate_impulse_counts(
    pivs: Sequence[Pivot], degree: str, t: pd.Timestamp
) -> list[ElliottCount]:
    p = collapse_same_kind(available_pivots(pivs, t))
    out = []
    # W1/W2 -> prospective W3: L-H-L
    for i in range(max(0, len(p) - 12), len(p) - 2):
        q = p[i : i + 3]
        if len(q) < 3 or [x.kind for x in q] != ["L", "H", "L"]:
            continue
        w0, w1, w2 = q
        if w2.price <= w0.price:
            continue  # wave2 must not retrace >100%
        l1 = w1.price - w0.price
        if l1 <= 0:
            continue
        cid = f"{degree}:W3:{w0.index}-{w1.index}-{w2.index}"
        out.append(
            ElliottCount(
                cid,
                degree,
                "W3",
                "BULLISH",
                tuple(q),
                w0.price,
                w2.price + 1.618 * l1,
                utc(w2.confirm_time),
                3,
            )
        )
    # W1-W4 -> prospective W5: L-H-L-H-L
    for i in range(max(0, len(p) - 14), len(p) - 4):
        q = p[i : i + 5]
        if [x.kind for x in q] != ["L", "H", "L", "H", "L"]:
            continue
        w0, w1, w2, w3, w4 = q
        l1 = w1.price - w0.price
        l3 = w3.price - w2.price
        if w2.price <= w0.price or w3.price <= w1.price or w4.price <= w1.price:
            continue
        # wave3 cannot be shortest once 1 and 3 measurable relative to projected W5 is
        # only guideline;
        # hard validation here requires wave3 positive and standard wave4 non-overlap.
        if l1 <= 0 or l3 <= 0:
            continue
        cid = f"{degree}:W5:{w0.index}-{w1.index}-{w2.index}-{w3.index}-{w4.index}"
        out.append(
            ElliottCount(
                cid,
                degree,
                "W5",
                "BULLISH",
                tuple(q),
                w4.price,
                w4.price + l1,
                utc(w4.confirm_time),
                2,
            )
        )
    return out


def enumerate_corrective_counts(
    pivs: Sequence[Pivot], degree: str, t: pd.Timestamp
) -> list[ElliottCount]:
    p = collapse_same_kind(available_pivots(pivs, t))
    out = []
    # completed bullish ABC correction: prior H -> L(A) -> H(B) -> L(C), C above larger-
    # degree origin
    for i in range(max(0, len(p) - 12), len(p) - 3):
        q = p[i : i + 4]
        if [x.kind for x in q] != ["H", "L", "H", "L"]:
            continue
        h0, a, b, c = q
        if b.price >= h0.price or c.price >= a.price:
            continue
        cid = f"{degree}:ABC_END:{h0.index}-{a.index}-{b.index}-{c.index}"
        out.append(
            ElliottCount(
                cid,
                degree,
                "ABC_END",
                "BULLISH",
                tuple(q),
                c.price,
                h0.price,
                utc(c.confirm_time),
                2,
            )
        )
    # Flat proxy: H-L-H-L with B near/above origin and C near/below A.
    for i in range(max(0, len(p) - 12), len(p) - 3):
        q = p[i : i + 4]
        if [x.kind for x in q] != ["H", "L", "H", "L"]:
            continue
        h0, a, b, c = q
        amp = max(h0.price - a.price, 1e-12)
        if b.price >= h0.price - 0.15 * amp and c.price <= a.price + 0.15 * amp:
            cid = f"{degree}:FLAT_END:{h0.index}-{a.index}-{b.index}-{c.index}"
            out.append(
                ElliottCount(
                    cid,
                    degree,
                    "FLAT_END",
                    "BULLISH",
                    tuple(q),
                    c.price,
                    h0.price,
                    utc(c.confirm_time),
                    1,
                )
            )
    # Triangle completion: last 5 alternating pivots contract.
    if len(p) >= 5:
        q = p[-5:]
        if _alternating(q):
            highs = [x.price for x in q if x.kind == "H"]
            lows = [x.price for x in q if x.kind == "L"]
            if len(highs) >= 2 and len(lows) >= 2 and highs[-1] < highs[0] and lows[-1] > lows[0]:
                cid = f"{degree}:TRIANGLE:{'-'.join(str(x.index) for x in q)}"
                out.append(
                    ElliottCount(
                        cid,
                        degree,
                        "TRIANGLE",
                        "BULLISH",
                        tuple(q),
                        min(lows),
                        max(highs),
                        utc(q[-1].confirm_time),
                        1,
                    )
                )
    return out


def enumerate_combination_counts(
    pivs: Sequence[Pivot], degree: str, t: pd.Timestamp
) -> list[ElliottCount]:
    p = collapse_same_kind(available_pivots(pivs, t))
    out = []
    if len(p) < 7:
        return out
    for i in range(max(0, len(p) - 12), len(p) - 6):
        q = p[i : i + 7]
        if not _alternating(q):
            continue
        # W-X-Y operationalization: two corrective swings connected by an X retracement,
        # remaining within the initial correction origin and ending at a higher-
        # timeframe support side.
        if q[0].kind == "H" and q[-1].kind == "H":
            lows = [x for x in q if x.kind == "L"]
            if len(lows) >= 3 and max(x.price for x in q[1:]) <= q[0].price * 1.03:
                inv = min(x.price for x in lows)
                cid = f"{degree}:COMBINATION:{'-'.join(str(x.index) for x in q)}"
                out.append(
                    ElliottCount(
                        cid,
                        degree,
                        "COMBINATION",
                        "BULLISH",
                        tuple(q),
                        inv,
                        q[0].price,
                        utc(q[-1].confirm_time),
                        1,
                    )
                )
    return out


_old_enumerate_corrective_counts = enumerate_corrective_counts


def enumerate_corrective_counts(
    pivs: Sequence[Pivot], degree: str, t: pd.Timestamp
) -> list[ElliottCount]:
    base = _old_enumerate_corrective_counts(pivs, degree, t)
    converted = []
    for c in base:
        if c.kind == "ABC_END":
            converted.append(
                ElliottCount(
                    c.count_id.replace("ABC_END", "ZIGZAG_END"),
                    c.degree,
                    "ZIGZAG_END",
                    c.direction,
                    c.points,
                    c.invalidation,
                    c.objective,
                    c.created_at,
                    c.priority,
                )
            )
        else:
            converted.append(c)
    converted.extend(enumerate_combination_counts(pivs, degree, t))
    # idempotent by count id
    return list({c.count_id: c for c in converted}.values())


# Hybrid management is bound from role evidence, not cloned from a source episode.
def hybrid_management_plan(fsm: HybridFSM) -> dict[str, Any] | None:
    if fsm.state != "THESIS_ACTIVE":
        return None
    e = fsm.evidence
    if fsm.system_id == "HYB_MARKUP_CONTINUATION":
        m = e.get("MANAGEMENT_BINDING", {})
        return {
            "stop": m.get("structural_stop"),
            "target": m.get("trend_objective"),
            "exit_on_market_reversal": True,
            "source": "shared_markup_state",
        }
    if fsm.system_id == "HYB_FAILED_AUCTION_REVERSAL":
        loc = e.get("LOCATION", {})
        evt = e.get("FAILED_AUCTION", {})
        m = e.get("MANAGEMENT_BINDING", {})
        stops = [
            x
            for x in [loc.get("make_or_break"), evt.get("raid_low"), m.get("spring_low")]
            if x is not None
        ]
        return {
            "stop": max(stops) if stops else None,
            "target": m.get("opposing_liquidity"),
            "phase_d_trailing": True,
            "source": "shared_failed_auction_state",
        }
    if fsm.system_id == "HYB_CORRECTIVE_COMPLETION_RESUMPTION":
        c = e.get("CORRECTION_MODEL", {})
        m = e.get("MANAGEMENT_BINDING", {})
        stops = [
            x for x in [c.get("count_invalidation"), m.get("structural_stop")] if x is not None
        ]
        targets = [
            x for x in [c.get("wave_objective"), m.get("external_liquidity")] if x is not None
        ]
        return {
            "stop": max(stops) if stops else None,
            "target": min(targets) if targets else None,
            "source": "shared_correction_state",
        }
    return None


# =============================================================================
# CENSUS FIDELITY HARDENING — SYMMETRIC BEARISH ELLIOTT ALTERNATES
# This closes a pre-census gap: consensus must be able to see materially opposing counts.
# =============================================================================

_prev_enumerate_impulse_counts_census = enumerate_impulse_counts


def enumerate_impulse_counts(
    pivs: Sequence[Pivot], degree: str, t: pd.Timestamp
) -> list[ElliottCount]:
    out = list(_prev_enumerate_impulse_counts_census(pivs, degree, t))
    p = collapse_same_kind(available_pivots(pivs, t))
    # Bearish W1/W2 -> prospective W3: H-L-H
    for i in range(max(0, len(p) - 12), len(p) - 2):
        q = p[i : i + 3]
        if len(q) < 3 or [x.kind for x in q] != ["H", "L", "H"]:
            continue
        w0, w1, w2 = q
        if w2.price >= w0.price:
            continue  # W2 cannot exceed origin in bearish impulse
        l1 = w0.price - w1.price
        if l1 <= 0:
            continue
        cid = f"{degree}:BEAR_W3:{w0.index}-{w1.index}-{w2.index}"
        out.append(
            ElliottCount(
                cid,
                degree,
                "W3",
                "BEARISH",
                tuple(q),
                w0.price,
                w2.price - 1.618 * l1,
                utc(w2.confirm_time),
                3,
            )
        )
    # Bearish prospective W5: H-L-H-L-H, standard W4 non-overlap with W1 end.
    for i in range(max(0, len(p) - 14), len(p) - 4):
        q = p[i : i + 5]
        if [x.kind for x in q] != ["H", "L", "H", "L", "H"]:
            continue
        w0, w1, w2, w3, w4 = q
        l1 = w0.price - w1.price
        l3 = w2.price - w3.price
        if w2.price >= w0.price or w3.price >= w1.price or w4.price >= w1.price:
            continue
        if l1 <= 0 or l3 <= 0:
            continue
        cid = f"{degree}:BEAR_W5:{w0.index}-{w1.index}-{w2.index}-{w3.index}-{w4.index}"
        out.append(
            ElliottCount(
                cid,
                degree,
                "W5",
                "BEARISH",
                tuple(q),
                w4.price,
                w4.price - l1,
                utc(w4.confirm_time),
                2,
            )
        )
    return list({c.count_id: c for c in out}.values())


_prev_enumerate_combination_counts_census = enumerate_combination_counts


def enumerate_combination_counts(
    pivs: Sequence[Pivot], degree: str, t: pd.Timestamp
) -> list[ElliottCount]:
    out = list(_prev_enumerate_combination_counts_census(pivs, degree, t))
    p = collapse_same_kind(available_pivots(pivs, t))
    if len(p) >= 7:
        for i in range(max(0, len(p) - 12), len(p) - 6):
            q = p[i : i + 7]
            if not _alternating(q):
                continue
            # Mirror W-X-Y correction in a larger bearish context: L ... L.
            if q[0].kind == "L" and q[-1].kind == "L":
                highs = [x for x in q if x.kind == "H"]
                if len(highs) >= 3 and min(x.price for x in q[1:]) >= q[0].price * 0.97:
                    inv = max(x.price for x in highs)
                    cid = f"{degree}:BEAR_COMBINATION:{'-'.join(str(x.index) for x in q)}"
                    out.append(
                        ElliottCount(
                            cid,
                            degree,
                            "COMBINATION",
                            "BEARISH",
                            tuple(q),
                            inv,
                            q[0].price,
                            utc(q[-1].confirm_time),
                            1,
                        )
                    )
    return list({c.count_id: c for c in out}.values())


_prev_enumerate_corrective_counts_census = enumerate_corrective_counts


def enumerate_corrective_counts(
    pivs: Sequence[Pivot], degree: str, t: pd.Timestamp
) -> list[ElliottCount]:
    base = list(_prev_enumerate_corrective_counts_census(pivs, degree, t))
    p = collapse_same_kind(available_pivots(pivs, t))
    out = []
    # Replace triangle direction with prior-trend context when available.
    prior_trend = trend_from_pivots(p[:-5]) if len(p) > 5 else "UNKNOWN"
    for c in base:
        if c.kind == "TRIANGLE":
            direction = (
                "BULLISH"
                if prior_trend == "UP"
                else ("BEARISH" if prior_trend == "DOWN" else "NEUTRAL")
            )
            out.append(
                ElliottCount(
                    c.count_id,
                    c.degree,
                    c.kind,
                    direction,
                    c.points,
                    c.invalidation,
                    c.objective,
                    c.created_at,
                    c.priority,
                )
            )
        else:
            out.append(c)
    # Mirror completed upward correction within a larger bear trend: L-H-L-H.
    for i in range(max(0, len(p) - 12), len(p) - 3):
        q = p[i : i + 4]
        if [x.kind for x in q] != ["L", "H", "L", "H"]:
            continue
        l0, a, b, c = q
        if b.price <= l0.price or c.price <= a.price:
            continue
        cid = f"{degree}:BEAR_ZIGZAG_END:{l0.index}-{a.index}-{b.index}-{c.index}"
        out.append(
            ElliottCount(
                cid,
                degree,
                "ZIGZAG_END",
                "BEARISH",
                tuple(q),
                c.price,
                l0.price,
                utc(c.confirm_time),
                2,
            )
        )
        amp = max(a.price - l0.price, 1e-12)
        if b.price <= l0.price + 0.15 * amp and c.price >= a.price - 0.15 * amp:
            fid = f"{degree}:BEAR_FLAT_END:{l0.index}-{a.index}-{b.index}-{c.index}"
            out.append(
                ElliottCount(
                    fid,
                    degree,
                    "FLAT_END",
                    "BEARISH",
                    tuple(q),
                    c.price,
                    l0.price,
                    utc(c.confirm_time),
                    1,
                )
            )
    # Current global combination enumerator now includes both directions.
    out.extend(enumerate_combination_counts(pivs, degree, t))
    return list({c.count_id: c for c in out}.values())


def invalidate_elliott_counts(
    snapshot: dict[str, list[ElliottCount]], current_price: float
) -> dict[str, list[ElliottCount]]:
    out = {}
    for deg, xs in snapshot.items():
        keep = []
        for c in xs:
            if c.direction == "BULLISH" and current_price <= c.invalidation:
                continue
            if c.direction == "BEARISH" and current_price >= c.invalidation:
                continue
            keep.append(c)
        out[deg] = keep
    return out


def invalidate_elliott_counts_persistent(
    snapshot: dict[str, list[ElliottCount]],
    current_price: float,
    tombstones: set[str],
) -> tuple[dict[str, list[ElliottCount]], set[str]]:
    """Absorbing Elliott invalidation for a count identity."""
    out = {}
    dead = set(tombstones)
    for deg, xs in snapshot.items():
        keep = []
        for c in xs:
            if c.count_id in dead:
                continue
            breached = (c.direction == "BULLISH" and current_price <= c.invalidation) or (
                c.direction == "BEARISH" and current_price >= c.invalidation
            )
            if breached:
                dead.add(c.count_id)
                continue
            keep.append(c)
        out[deg] = keep
    return out, dead
