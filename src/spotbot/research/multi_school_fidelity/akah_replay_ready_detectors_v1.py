"""Research-only integrated authority; not production. See source provenance manifest."""

from __future__ import annotations

import bisect
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from . import akah_full_fidelity_runtime_v1 as rt
from .akah_foundation_core_v1r1 import (
    DATA_CUTOFF,
    DATA_START,
    BroadEligibilityIndex,
    utc,
)

# =============================================================================
# DETECTOR CONTRACT — BAR/PIVOT -> RUNTIME EVENT
# No PnL, no cost, no portfolio selection.
# =============================================================================


def add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    x = frame.copy().sort_values("timestamp", kind="stable").reset_index(drop=True)
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="raise")
    pc = x["close"].shift(1)
    x["true_range"] = pd.concat(
        [
            x["high"] - x["low"],
            (x["high"] - pc).abs(),
            (x["low"] - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)
    x["atr20"] = x["true_range"].rolling(20, min_periods=10).mean()
    x["spread_median20"] = x["true_range"].rolling(20, min_periods=10).median()
    x["volume_median20"] = x["volume"].rolling(20, min_periods=10).median()
    delta = x["close"].diff()
    up = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    dn = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rs = up / dn.replace(0, np.nan)
    x["rsi14"] = 100 - (100 / (1 + rs))
    x["close_pos"] = (x["close"] - x["low"]) / (x["high"] - x["low"]).replace(0, np.nan)
    return x


def asof_state(transitions: Sequence[Any], t: pd.Timestamp, default: str = "UNKNOWN") -> str:
    if not transitions:
        return default

    def qt(q):
        return utc(q["timestamp"]) if isinstance(q, dict) else utc(q.timestamp)

    def qs(q):
        return str(q["to_state"]) if isinstance(q, dict) else str(q.to_state)

    tv = [int(qt(q).value) for q in transitions]
    j = bisect.bisect_right(tv, int(utc(t).value)) - 1
    return qs(transitions[j]) if j >= 0 else default


def pivot_events(pivots: Sequence[rt.Pivot]) -> dict[pd.Timestamp, list[rt.Pivot]]:
    d = {}
    for p in pivots:
        d.setdefault(utc(p.confirm_time), []).append(p)
    return d


def latest_pivots(pivots: Sequence[rt.Pivot], t: pd.Timestamp, n: int = 20) -> list[rt.Pivot]:
    av = rt.available_pivots(pivots, t)
    return av[-n:]


def last_by_kind(pivots: Sequence[rt.Pivot], kind: str, n: int = 1) -> list[rt.Pivot]:
    return [p for p in pivots if p.kind == kind][-n:]


def event_row(system, pair, t, event, stage, eligible, meta=None):
    return {
        "system_id": system,
        "pair": pair,
        "timestamp": utc(t),
        "event": event,
        "stage": stage,
        "broad_eligible": bool(eligible),
        "metadata": json.dumps(meta or {}, default=str, sort_keys=True),
    }


def transition_rows(transitions: Sequence[rt.StateTransition], eligibility: BroadEligibilityIndex):
    rows = []
    for q in transitions:
        rows.append(
            {
                "system_id": q.system_id,
                "pair": q.pair,
                "timestamp": utc(q.timestamp),
                "from_state": q.from_state,
                "to_state": q.to_state,
                "reason": q.reason,
                "broad_eligible": eligibility.eligible(q.pair, q.timestamp)
                if q.pair != "__MARKET__"
                else True,
                "metadata": json.dumps(q.metadata, default=str, sort_keys=True),
            }
        )
    return rows


# =============================================================================
# WYCKOFF
# =============================================================================


@dataclass
class WyckoffScan:
    runtime: rt.WyckoffRuntime
    event_rows: list[dict[str, Any]] = field(default_factory=list)
    intent_rows: list[dict[str, Any]] = field(default_factory=list)
    state_entered: pd.Timestamp | None = None
    max_dwell_hours: float = 0.0
    reset_count: int = 0


def scan_wyckoff(
    pair: str,
    h4: pd.DataFrame,
    raw: pd.DataFrame,
    btc_raw: pd.DataFrame,
    eligibility: BroadEligibilityIndex,
    market_transitions: Sequence[rt.StateTransition] | None = None,
    market_mode: bool = False,
    *, runtime_factory=None,
) -> tuple[list[dict], list[dict], list[dict], dict]:
    x = add_indicators(h4)
    piv = rt.confirmed_pivots_2l2r(x)
    pe = pivot_events(piv)
    w = (runtime_factory or rt.WyckoffRuntime)("__MARKET__" if market_mode else pair)
    events = []
    intents = []
    state_entered = x.iloc[0]["timestamp"] if len(x) else DATA_START
    phase_c_branch = None
    last_lps_time = None

    for i, row in x.iterrows():
        t = utc(row["timestamp"])
        if t >= DATA_CUTOFF:
            break
        av = latest_pivots(piv, t, 30)
        collapsed = rt.collapse_same_kind(av)
        trend = rt.trend_from_pivots(collapsed)
        atr = float(row["atr20"]) if pd.notna(row["atr20"]) else math.nan
        spread = float(row["true_range"]) if pd.notna(row["true_range"]) else math.nan
        smed = float(row["spread_median20"]) if pd.notna(row["spread_median20"]) else math.nan
        vol = float(row["volume"]) if pd.notna(row["volume"]) else math.nan
        vmed = float(row["volume_median20"]) if pd.notna(row["volume_median20"]) else math.nan
        close = float(row["close"])
        low = float(row["low"])
        high = float(row["high"])
        eligible = True if market_mode else eligibility.eligible(pair, t)
        prev_state = w.state
        # V4 owned runtimes invalidate live child evidence on the completed bar,
        # before considering a new intent. The reference V1 path is unchanged.
        if hasattr(w, "observe_bar"):
            w.observe_bar(t, low)

        if w.state == "UNKNOWN" and trend == "DOWN":
            w.step(t, "PRIOR_DOWNTREND")
            events.append(
                event_row(
                    w.transitions[-1].system_id,
                    pair,
                    t,
                    "PRIOR_DOWNTREND",
                    "CONTEXT",
                    eligible,
                    {"trend": trend},
                )
            )

        if (
            w.state == "DOWNTREND"
            and i >= 20
            and math.isfinite(atr)
            and math.isfinite(vmed)
            and math.isfinite(smed)
        ):
            prev_low = float(x.loc[max(0, i - 20) : i - 1, "low"].min())
            sc = (
                low <= prev_low
                and spread >= smed
                and vol >= vmed
                and float(row["close_pos"] if pd.notna(row["close_pos"]) else 0) >= 0.45
            )
            if sc:
                w.step(
                    t, "SELLING_CLIMAX", {"low": low, "high": high, "volume": vol, "spread": spread}
                )
                events.append(
                    event_row(
                        w.transitions[-1].system_id,
                        pair,
                        t,
                        "SELLING_CLIMAX",
                        "STRUCTURAL",
                        eligible,
                        {"low": low, "volume": vol, "spread": spread},
                    )
                )

        if w.state == "A_STOPPING" and w.context.get("sc"):
            sc = w.context["sc"]
            sc_time = utc(w.context["sc_time"])
            newps = pe.get(t, [])
            if not w.context.get("ar"):
                highs = [p for p in newps if p.kind == "H" and p.pivot_time > sc_time]
                if highs and math.isfinite(atr) and highs[-1].price >= float(sc["low"]) + atr:
                    p = highs[-1]
                    w.step(t, "AUTOMATIC_RALLY", {"high": p.price, "pivot_time": p.pivot_time})
                    events.append(
                        event_row(
                            w.transitions[-1].system_id,
                            pair,
                            t,
                            "AUTOMATIC_RALLY",
                            "STRUCTURAL",
                            eligible,
                            {"high": p.price},
                        )
                    )
            elif not w.context.get("st"):
                ar = w.context["ar"]
                lows = [
                    p
                    for p in newps
                    if p.kind == "L"
                    and p.pivot_time > utc(ar.get("pivot_time", t - pd.Timedelta(days=1)))
                ]
                if lows and math.isfinite(atr):
                    p = lows[-1]
                    prow = x.iloc[p.index]
                    reduced = (
                        abs(p.price - float(sc["low"])) <= 1.5 * atr
                        and float(prow["volume"]) <= float(sc.get("volume", math.inf))
                        and float(prow["true_range"]) <= float(sc.get("spread", math.inf))
                    )
                    if reduced:
                        w.step(
                            t,
                            "SECONDARY_TEST_REDUCED_SUPPLY",
                            {
                                "support": p.price,
                                "resistance": float(ar["high"]),
                                "volume": float(prow["volume"]),
                                "spread": float(prow["true_range"]),
                            },
                        )
                        events.append(
                            event_row(
                                w.transitions[-1].system_id,
                                pair,
                                t,
                                "SECONDARY_TEST_REDUCED_SUPPLY",
                                "STRUCTURAL",
                                eligible,
                                {"support": p.price, "resistance": float(ar["high"])},
                            )
                        )
            # liveness/reset
            ar = w.context.get("ar")
            stronger = (
                (
                    low < float(sc["low"]) - (0.5 * atr if math.isfinite(atr) else 0)
                    and spread >= smed
                    and vol >= vmed
                )
                if math.isfinite(smed) and math.isfinite(vmed)
                else False
            )
            upbreak = bool(ar and math.isfinite(atr) and close > float(ar["high"]) + atr)
            reason = rt.wyckoff_a_reset_reason(
                now=t,
                sc_time=sc_time,
                sc_low=float(sc["low"]),
                close=close,
                atr=atr,
                stronger_new_sc=stronger,
                confirmed_up_break=upbreak,
            )
            if reason:
                ev = {
                    "SC_STRUCTURALLY_FAILED": "A_STRUCTURAL_FAIL",
                    "RESEED_NEW_SC": "NEW_STRONGER_SC",
                    "STOPPING_RESOLVED_WITHOUT_CANONICAL_ST": "STOPPING_RESOLVED_WITHOUT_ST",
                    "PHASE_A_SAFETY_EXPIRY_90D": "A_TIMEOUT",
                }[reason]
                w.step(t, ev, {"foundation_reason": reason})
                events.append(
                    event_row(
                        w.transitions[-1].system_id,
                        pair,
                        t,
                        ev,
                        "RESET",
                        eligible,
                        {"reason": reason},
                    )
                )

        if w.state == "B_CAUSE_BUILDING":
            support = float(w.context.get("support", math.nan))
            res = float(w.context.get("resistance", math.nan))
            if math.isfinite(support) and math.isfinite(atr):
                if close < support - atr:
                    w.step(t, "RANGE_SUPPORT_FAIL", {"close": close, "support": support})
                    events.append(
                        event_row(
                            w.transitions[-1].system_id,
                            pair,
                            t,
                            "RANGE_SUPPORT_FAIL",
                            "RESET",
                            eligible,
                            {},
                        )
                    )
                elif low < support and close > support and low >= support - 2 * atr:
                    phase_c_branch = "SPRING_TEST"
                    w.step(t, "SPRING_RECLAIM", {"low": low, "support": support})
                    events.append(
                        event_row(
                            w.transitions[-1].system_id,
                            pair,
                            t,
                            "SPRING_RECLAIM",
                            "ACTIVATION",
                            eligible,
                            {"support": support},
                        )
                    )
                else:
                    for p in pe.get(t, []):
                        if p.kind != "L":
                            continue
                        prow = x.iloc[p.index]
                        if (
                            p.price > support
                            and p.price <= support + 2 * atr
                            and float(prow["volume"]) <= vmed
                            and float(prow["true_range"]) <= smed
                        ):
                            phase_c_branch = "NO_SPRING_LPS"
                            w.step(
                                t, "HIGHER_RANGE_SUPPLY_TEST", {"low": p.price, "support": support}
                            )
                            events.append(
                                event_row(
                                    w.transitions[-1].system_id,
                                    pair,
                                    t,
                                    "HIGHER_RANGE_SUPPLY_TEST",
                                    "ACTIVATION",
                                    eligible,
                                    {"support": support},
                                )
                            )
                            break

        if w.state == "C_TESTING_SUPPLY":
            res = float(w.context.get("resistance", math.nan))
            support = float(w.context.get("support", math.nan))
            if math.isfinite(support) and math.isfinite(atr) and close < support - atr:
                w.step(t, "DISTRIBUTION_RISK", {"support": support, "close": close})
                events.append(
                    event_row(
                        w.transitions[-1].system_id,
                        pair,
                        t,
                        "DISTRIBUTION_RISK",
                        "RESET",
                        eligible,
                        {},
                    )
                )
            elif (
                math.isfinite(res)
                and math.isfinite(atr)
                and close > res + 0.25 * atr
                and spread >= smed
                and vol >= vmed
            ):
                w.step(t, "SOS_DEMAND_DOMINANCE", {"high": high, "close": close, "resistance": res})
                events.append(
                    event_row(
                        w.transitions[-1].system_id,
                        pair,
                        t,
                        "SOS_DEMAND_DOMINANCE",
                        "CONFIRMATION",
                        eligible,
                        {"resistance": res},
                    )
                )

        if w.state == "D_DEMAND_DOMINANT":
            support = float(w.context.get("support", math.nan))
            res = float(w.context.get("resistance", math.nan))
            sos_t = utc(w.transitions[-1].timestamp) if w.transitions else t
            for p in pe.get(t, []):
                if p.kind != "L" or p.pivot_time <= sos_t:
                    continue
                prow = x.iloc[p.index]
                if (
                    math.isfinite(support)
                    and p.price > support
                    and (
                        not math.isfinite(res)
                        or p.price <= res + 2 * (atr if math.isfinite(atr) else 0)
                    )
                    and float(prow["volume"]) <= vmed
                ):
                    w.step(t, "LPS_HOLDS", {"low": p.price, "pivot_time": p.pivot_time})
                    last_lps_time = t
                    events.append(
                        event_row(
                            w.transitions[-1].system_id,
                            pair,
                            t,
                            "LPS_HOLDS",
                            "ACCEPTANCE",
                            eligible,
                            {"low": p.price},
                        )
                    )
                    break

        if w.state == "E_MARKUP":
            if trend == "DOWN":
                w.step(t, "DISTRIBUTION_RISK", {"trend": "DOWN"})
                events.append(
                    event_row(
                        w.transitions[-1].system_id,
                        pair,
                        t,
                        "DISTRIBUTION_RISK",
                        "RESET",
                        eligible,
                        {"trend": "DOWN"},
                    )
                )
            elif i >= 30 and math.isfinite(atr):
                q = x.iloc[i - 19 : i + 1]
                height = float(q["high"].max() - q["low"].min())
                if (
                    trend == "RANGE"
                    and height <= 6 * atr
                    and (last_lps_time is None or t - last_lps_time >= pd.Timedelta(days=3))
                ):
                    w.step(
                        t,
                        "HIGHER_LEVEL_RANGE_FORMS",
                        {"low": float(q["low"].min()), "high": float(q["high"].max())},
                    )
                    events.append(
                        event_row(
                            w.transitions[-1].system_id,
                            pair,
                            t,
                            "HIGHER_LEVEL_RANGE_FORMS",
                            "STRUCTURAL",
                            eligible,
                            {},
                        )
                    )

        if w.state == "REACCUMULATION":
            rg = w.context.get("range", {})
            rh = float(rg.get("high", math.nan))
            rl = float(rg.get("low", math.nan))
            if math.isfinite(rl) and math.isfinite(atr) and close < rl - atr:
                w.step(t, "DISTRIBUTION_RISK", {"range_low": rl})
                events.append(
                    event_row(
                        w.transitions[-1].system_id,
                        pair,
                        t,
                        "DISTRIBUTION_RISK",
                        "RESET",
                        eligible,
                        {},
                    )
                )
            elif math.isfinite(rh) and math.isfinite(atr) and close > rh + 0.25 * atr:
                # require a confirmed higher low at/above range high within
                # later pivot confirmations
                lows = [p for p in pe.get(t, []) if p.kind == "L" and p.price >= rl]
                if lows:
                    w.step(t, "REACCUMULATION_SOS_LPS", {"low": lows[-1].price, "range_high": rh})
                    events.append(
                        event_row(
                            w.transitions[-1].system_id,
                            pair,
                            t,
                            "REACCUMULATION_SOS_LPS",
                            "ACCEPTANCE",
                            eligible,
                            {},
                        )
                    )

        # downstream liveness safety. These resets create no trade and exist only to
        # prevent zombie states.
        age = t - state_entered
        if w.state == "B_CAUSE_BUILDING" and age > pd.Timedelta(days=180):
            w.context = {}
            w._change(t, "UNKNOWN", "B_CAUSE_BUILDING safety expiry 180d", {})
            events.append(
                event_row(w.transitions[-1].system_id, pair, t, "B_TIMEOUT", "RESET", eligible, {})
            )
            state_entered = t
        elif w.state == "C_TESTING_SUPPLY" and age > pd.Timedelta(days=60):
            w.context = {}
            w._change(t, "UNKNOWN", "C_TESTING_SUPPLY safety expiry 60d", {})
            events.append(
                event_row(w.transitions[-1].system_id, pair, t, "C_TIMEOUT", "RESET", eligible, {})
            )
            state_entered = t
        elif w.state == "D_DEMAND_DOMINANT" and age > pd.Timedelta(days=90):
            w.context = {}
            w._change(t, "UNKNOWN", "D_DEMAND_DOMINANT safety expiry 90d", {})
            events.append(
                event_row(w.transitions[-1].system_id, pair, t, "D_TIMEOUT", "RESET", eligible, {})
            )
            state_entered = t
        elif w.state == "DISTRIBUTION_RISK":
            # Distribution is a regime warning, not an absorbing state. Resolve
            # causally into a fresh downtrend/unknown cycle.
            if trend == "DOWN" and age >= pd.Timedelta(days=1):
                w.context = {}
                w._change(t, "DOWNTREND", "distribution resolved into downtrend", {})
                events.append(
                    event_row(
                        w.transitions[-1].system_id,
                        pair,
                        t,
                        "DISTRIBUTION_TO_DOWNTREND",
                        "RESET",
                        eligible,
                        {},
                    )
                )
                state_entered = t
            elif trend == "UP" and age >= pd.Timedelta(days=3):
                w.context = {}
                w._change(t, "UNKNOWN", "distribution warning invalidated by renewed uptrend", {})
                events.append(
                    event_row(
                        w.transitions[-1].system_id,
                        pair,
                        t,
                        "DISTRIBUTION_RESET",
                        "RESET",
                        eligible,
                        {},
                    )
                )
                state_entered = t
        elif w.state == "REACCUMULATION" and age > pd.Timedelta(days=120):
            w.context = {}
            w._change(t, "UNKNOWN", "REACCUMULATION safety expiry 120d", {})
            events.append(
                event_row(
                    w.transitions[-1].system_id,
                    pair,
                    t,
                    "REACCUMULATION_TIMEOUT",
                    "RESET",
                    eligible,
                    {},
                )
            )
            state_entered = t

        # full readiness/intents only on meaningful states and only for pair, never market sensor
        if (
            not market_mode
            and eligible
            and w.state in {"C_TESTING_SUPPLY", "D_DEMAND_DOMINANT", "E_MARKUP", "REACCUMULATION"}
            and math.isfinite(atr)
        ):
            market_state = asof_state(market_transitions or [], t)
            rs = rt.matched_swing_relative_strength(raw, btc_raw, piv, t)
            cp = rt.collapse_same_kind(latest_pivots(piv, t, 20))
            hs = [p for p in cp if p.kind == "H"][-2:]
            ls = [p for p in cp if p.kind == "L"][-2:]
            higher_h = len(hs) >= 2 and hs[-1].price > hs[-2].price
            higher_l = len(ls) >= 2 and ls[-1].price > ls[-2].price
            res = float(w.context.get("resistance", math.nan))
            stride = math.isfinite(res) and close > res
            er = (
                rt.wyckoff_effort_result(
                    vol, spread, max(close - float(x.iloc[max(0, i - 1)]["close"]), 0), vmed, smed
                )
                if math.isfinite(vmed) and math.isfinite(smed)
                else "UNKNOWN"
            )
            bullish = er in {"DEMAND_PROGRESS", "DIMINISHING_SUPPLY"}
            sc_time = w.context.get("sc_time")
            support = float(w.context.get("support", w.context.get("sc", {}).get("low", math.nan)))
            pnf = {"objective": math.nan}
            if sc_time is not None and math.isfinite(support):
                closes = (
                    x.loc[(x["timestamp"] >= utc(sc_time)) & (x["timestamp"] <= t), "close"]
                    .astype(float)
                    .tolist()
                )
                pnf = rt.percentage_pnf_cause(closes, support, 0.01, 3)
            risk = close - support if math.isfinite(support) else math.nan
            upr = (
                (float(pnf["objective"]) - close) / risk
                if math.isfinite(risk) and risk > 0 and math.isfinite(float(pnf["objective"]))
                else math.nan
            )
            readiness = w.readiness_vector(
                downward_objective_context=bool(w.context.get("sc")),
                bullish_activity=bullish,
                downward_stride_broken=stride,
                higher_lows=higher_l,
                higher_highs=higher_h,
                relative_strength=rs.get("eligible", False),
                base_formed=True,
                upward_potential_r=upr,
            )
            if all(readiness.values()):
                branch = (
                    "SPRING_TEST"
                    if phase_c_branch == "SPRING_TEST"
                    and w.state in {"C_TESTING_SUPPLY", "D_DEMAND_DOMINANT"}
                    else (
                        "REACCUMULATION_LPS"
                        if w.state == "E_MARKUP" and w.context.get("prior_markup")
                        else "NO_SPRING_LPS"
                    )
                )
                intent = w.entry_intent(
                    t,
                    branch=branch,
                    market_state=market_state,
                    rs=rs,
                    readiness=readiness,
                    entry=close,
                    structural_low=(w.entry_stop(branch, support) if hasattr(w, "entry_stop") else support),
                    pnf_objective=float(pnf["objective"]),
                )
                if intent is not None:
                    intents.append(
                        event_row(
                            "FS_WYCKOFF_FULL_LONG",
                            pair,
                            t,
                            intent.branch,
                            "THESIS_INTENT",
                            True,
                            {
                                "stop": intent.stop,
                                "target": intent.target,
                                "readiness": readiness,
                                "market_state": market_state,
                                "owner_metadata": intent.metadata,
                                "cause_id": w.context.get("cause_id"),
                            },
                        )
                    )

        if w.state != prev_state:
            state_entered = t

    trans = transition_rows(w.transitions, eligibility)
    summary = {
        "system_id": "FS_WYCKOFF_FULL_LONG" if not market_mode else "MARKET_WYCKOFF_SENSOR",
        "pair": pair,
        "transition_count": len(trans),
        "event_count": len(events),
        "intent_count": len(intents),
        "final_state": w.state,
        "a_timeout_count": sum(e["event"] == "A_TIMEOUT" for e in events),
        "reset_count": sum(e["stage"] == "RESET" for e in events),
    }
    return trans, events, intents, summary


# =============================================================================
# ICT
# =============================================================================


def _trend_asof(pivs, t):
    return rt.trend_from_pivots(rt.collapse_same_kind(latest_pivots(pivs, t, 20)))


def _ny_daily_maps(hourly: pd.DataFrame):
    x = hourly.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    local = x["timestamp"].dt.tz_convert("America/New_York")
    x["ny_date"] = local.dt.date
    daily = x.groupby("ny_date").agg(high=("high", "max"), low=("low", "min")).to_dict("index")
    anchors = {}
    for d, g in x.groupby("ny_date"):
        g = g.sort_values("timestamp")
        localg = g["timestamp"].dt.tz_convert("America/New_York")
        mid = g.loc[(localg.dt.hour == 0)].head(1)
        # 1H raw has no exact 08:30; source anchor is represented by the containing
        # 08:00-09:00 bar open,
        # explicitly an hourly-data adaptation for census state, not an economic fill.
        eight = g.loc[(localg.dt.hour == 8)].head(1)
        anchors[d] = {
            "ny_midnight": float(mid.iloc[0]["open"]) if len(mid) else None,
            "ny_0830_hourly_proxy": float(eight.iloc[0]["open"]) if len(eight) else None,
        }
    return daily, anchors


def scan_ict(pair, raw, h4, d1, btc_raw, eth_raw, eligibility):
    x = add_indicators(raw)
    h4i = add_indicators(h4)
    d1i = add_indicators(d1)
    p1 = rt.confirmed_pivots_2l2r(x)
    p4 = rt.confirmed_pivots_2l2r(h4i)
    pd1 = rt.confirmed_pivots_2l2r(d1i)
    ict = rt.ICT2022CoreRuntime(pair)
    events = []
    intents = []
    daily, anchors = _ny_daily_maps(x)
    max_pending_h = 0.0
    pending_started = None
    expired = 0
    ts = pd.to_datetime(x["timestamp"], utc=True)
    local_ts = ts.dt.tz_convert("America/New_York")
    dates = local_ts.dt.date.to_numpy()
    weekdays = local_ts.dt.weekday.to_numpy()
    hours = local_ts.dt.hour.to_numpy()
    minutes = local_ts.dt.minute.to_numpy()
    opens = x["open"].astype(float).to_numpy()
    highs = x["high"].astype(float).to_numpy()
    lows = x["low"].astype(float).to_numpy()
    closes = x["close"].astype(float).to_numpy()
    atrs = x["atr20"].astype(float).to_numpy()
    n = len(x)
    for i in range(n):
        t = utc(ts.iloc[i])
        if t >= DATA_CUTOFF:
            break
        eligible = eligibility.eligible(pair, t)
        before = ict.pending
        if ict.invalidate_pending_raid(t, lows[i]):
            events.append(
                event_row(
                    "FS_ICT_2022_CORE_CRYPTO_LONG",
                    pair,
                    t,
                    "RAID_INVALIDATED",
                    "INVALIDATION",
                    eligible,
                    {"raid_time": str(before.raid_time), "raid_low": before.raid_low},
                )
            )
            if pending_started is not None:
                max_pending_h = max(max_pending_h, (t - pending_started).total_seconds() / 3600)
                pending_started = None
            before = None
        ict.expire_if_needed(t)
        if before is not None and ict.pending is None:
            expired += 1
            events.append(
                event_row(
                    "FS_ICT_2022_CORE_CRYPTO_LONG", pair, t, "SESSION_EXPIRY", "RESET", eligible, {}
                )
            )
            if pending_started is not None:
                max_pending_h = max(max_pending_h, (t - pending_started).total_seconds() / 3600)
                pending_started = None
        if weekdays[i] >= 5:
            session = "OUTSIDE_WEEKDAY_MODEL"
        else:
            tm = int(hours[i]) * 60 + int(minutes[i])
            session = (
                "PRE_NY_0830"
                if tm < 510
                else (
                    "POST_NY_0830"
                    if tm < 720
                    else ("NY_AFTERNOON" if tm < 960 else "OUTSIDE_WEEKDAY_MODEL")
                )
            )
        local_date = dates[i]
        prevd = (pd.Timestamp(local_date) - pd.Timedelta(days=1)).date()
        prior = daily.get(prevd, {})
        prior_map = {"prior_high": prior.get("high"), "prior_low": prior.get("low")}
        h4av = latest_pivots(p4, t, 20)
        liq = rt.external_liquidity_map(prior_map, h4av, t)
        price = float(closes[i])
        prev_close = float(closes[i - 1] if i >= 1 else closes[0])
        buys = [z for z in liq["buy_side"] if z > price]
        sells = [z for z in liq["sell_side"] if z < prev_close]
        target = min(buys) if buys else None
        sell = max(sells) if sells else None
        collapsed = rt.collapse_same_kind(h4av)
        h4_lows = last_by_kind(collapsed, "L", 1)
        h4_highs = last_by_kind(collapsed, "H", 1)
        if h4_lows and h4_highs:
            dr_low = min(h4_lows[-1].price, h4_highs[-1].price)
            dr_high = max(h4_lows[-1].price, h4_highs[-1].price)
            dealing = rt.dealing_range_state(price, dr_low, dr_high)
        else:
            dealing = "AMBIGUOUS"
        dtrend = _trend_asof(pd1, t)
        htrend = _trend_asof(p4, t)
        bias = rt.ict_bias_state(dtrend, htrend, price, target, sell)
        if ict.pending is None and eligible and sell is not None and target is not None and i >= 1:
            raid = float(lows[i]) < sell and float(closes[i]) > sell
            if raid:
                ints = last_by_kind(rt.collapse_same_kind(latest_pivots(p1, t, 30)), "H", 1)
                internal = ints[-1].price if ints else None
                if internal is not None:
                    ok = ict.register_raid(
                        t,
                        float(lows[i]),
                        internal,
                        target,
                        htf_bias=bias,
                        dealing_state=dealing,
                        reclaimed=True,
                        session_state=session,
                    )
                    if ok:
                        pending_started = t
                        events.append(
                            event_row(
                                "FS_ICT_2022_CORE_CRYPTO_LONG",
                                pair,
                                t,
                                "SELLSIDE_RAIDED",
                                "FAILED_AUCTION",
                                eligible,
                                {
                                    "sell_level": sell,
                                    "internal_high": internal,
                                    "target": target,
                                    "bias": bias,
                                    "dealing": dealing,
                                    "smt": rt.smt_bullish_context(btc_raw, eth_raw, t, 24),
                                    "anchors": anchors.get(local_date, {}),
                                },
                            )
                        )
        if ict.pending is not None and ict.pending.state == "SELLSIDE_RAIDED" and i >= 2:
            fvg = (
                (float(highs[i - 2]), float(lows[i]))
                if float(lows[i]) > float(highs[i - 2])
                and float(closes[i - 1]) > float(opens[i - 1])
                else None
            )
            atr = float(atrs[i]) if math.isfinite(float(atrs[i])) else math.nan
            ob = None
            for j in range(i - 1, max(-1, i - 13), -1):
                if float(closes[j]) < float(opens[j]):
                    ob = {
                        "index": j,
                        "time": utc(ts.iloc[j]),
                        "low": float(lows[j]),
                        "high": float(highs[j]),
                    }
                    break
            ok = ict.register_mss_displacement(
                t, float(closes[i]), float(closes[i - 1]), atr, fvg, ob
            )
            if ok:
                events.append(
                    event_row(
                        "FS_ICT_2022_CORE_CRYPTO_LONG",
                        pair,
                        t,
                        "MSS_DISPLACEMENT_FVG",
                        "CONFIRMATION",
                        eligible,
                        {"fvg": fvg, "order_block": ob},
                    )
                )
        if (
            ict.pending is not None
            and ict.pending.order_block is not None
            and not ict.pending.validated_ob
        ) and ict.validate_order_block(t, float(closes[i])):
            events.append(
                event_row(
                    "FS_ICT_2022_CORE_CRYPTO_LONG",
                    pair,
                    t,
                    "ORDER_BLOCK_VALIDATED",
                    "EXECUTION_ARRAY",
                    eligible,
                    {},
                )
            )
        if ict.pending is not None and ict.pending.fvg is not None:
            had_pending = ict.pending is not None
            intent = ict.retracement_intent(t, float(lows[i]), float(highs[i]), float(closes[i]))
            if had_pending and ict.pending is None and pending_started is not None:
                max_pending_h = max(max_pending_h, (t - pending_started).total_seconds() / 3600)
                pending_started = None
            if intent is not None and eligible:
                intents.append(
                    event_row(
                        "FS_ICT_2022_CORE_CRYPTO_LONG",
                        pair,
                        t,
                        intent.branch,
                        "THESIS_INTENT",
                        True,
                        {"stop": intent.stop, "target": intent.target, **intent.metadata},
                    )
                )
    if ict.pending is not None and pending_started is not None:
        max_pending_h = max(
            max_pending_h, (min(DATA_CUTOFF, ts.iloc[-1]) - pending_started).total_seconds() / 3600
        )
    trans = transition_rows(ict.transitions, eligibility)
    summary = {
        "system_id": "FS_ICT_2022_CORE_CRYPTO_LONG",
        "pair": pair,
        "transition_count": len(trans),
        "event_count": len(events),
        "intent_count": len(intents),
        "final_state": ict.pending.state if ict.pending else "IDLE",
        "max_pending_hours": max_pending_h,
        "expiry_count": expired,
    }
    return trans, events, intents, summary


# =============================================================================
# HARMONIC
# =============================================================================

REGULAR_HARMONICS = ("GARTLEY", "BAT", "ALTERNATE_BAT", "BUTTERFLY", "CRAB", "DEEP_CRAB", "ABCD")


def _regular_projection_allowed(X, A, B, C, name):
    xa = abs(A - X)
    ab = abs(B - A)
    if xa <= 0:
        return False
    bxa = ab / xa
    if name == "GARTLEY":
        return abs(bxa - 0.618) <= 0.03
    if name == "BAT":
        return 0.35 <= bxa <= 0.55
    if name == "ALTERNATE_BAT":
        return bxa <= 0.402
    if name == "BUTTERFLY":
        return abs(bxa - 0.786) <= 0.04
    if name == "CRAB":
        return 0.35 <= bxa <= 0.65
    if name == "DEEP_CRAB":
        return abs(bxa - 0.886) <= 0.04
    return name == "ABCD"


def scan_harmonic(pair, h4, eligibility):
    """
    Real-time harmonic census:
    confirmed XABC -> PRZ projected BEFORE D -> first later bar traversing the
    complete PRZ is Terminal Bar. D is not required to become a future-confirmed pivot.
    """
    x = add_indicators(h4)
    # Immutable raw confirmed-pivot ledger; collapse only after time filtering.
    piv = rt.confirmed_pivots_2l2r(x)
    pe = pivot_events(piv)
    events = []
    intents = []
    seen_projection = set()
    seen_terminal = set()
    active = {}  # projection_id -> projection record
    lifecycles = []
    projected = completed = type1 = type2 = invalidated = 0

    def add_projection(name, a4, pr):
        nonlocal projected
        pid = f"{name}:{a4[0].index}-{a4[1].index}-{a4[2].index}-{a4[3].index}"
        if pid in seen_projection:
            return
        seen_projection.add(pid)
        projected += 1
        rec = {
            "pid": pid,
            "name": name,
            "pivots": tuple(a4),
            "pr": pr,
            "created": utc(a4[-1].confirm_time),
            "created_index": a4[-1].index + 2,
        }
        active[pid] = rec
        events.append(
            event_row(
                "FS_HARMONIC_FULL_LONG",
                pair,
                rec["created"],
                f"{name}_PRZ_PROJECTED",
                "LOCATION",
                eligibility.eligible(pair, rec["created"]),
                pr,
            )
        )

    # Iterate every completed 4H bar. New projections enter only when C is causally confirmed.
    for i, row in x.iterrows():
        t = utc(row["timestamp"])
        # New confirmed pivot(s) can define XABC.
        if pe.get(t):
            av = rt.collapse_same_kind(rt.available_pivots(piv, t))
            if len(av) >= 4:
                a4 = av[-4:]
                if [p.kind for p in a4] == ["L", "H", "L", "H"]:
                    X, A, B, C = [p.price for p in a4]
                    for name in REGULAR_HARMONICS:
                        if not _regular_projection_allowed(X, A, B, C, name):
                            continue
                        pr = rt.project_harmonic_prz(X, A, B, C, name)
                        if pr:
                            add_projection(name, a4, pr)
                    pr5 = rt.project_five_zero_prz(X, A, B, C)
                    if pr5:
                        add_projection("FIVE_ZERO", a4, pr5)
                    prs = rt.project_shark_prz(X, A, B, C)
                    if prs:
                        add_projection("SHARK", a4, prs)

        # Test all active projected zones using only the current completed bar.
        for pid, rec in list(active.items()):
            if i <= rec["created_index"]:
                continue
            pr = rec["pr"]
            name = rec["name"]
            low = float(row["low"])
            high = float(row["high"])
            mb = float(pr["make_or_break"])
            # Hard invalidation has precedence over activation on the same bar.
            if math.isfinite(mb) and low <= mb:
                invalidated += 1
                events.append(
                    event_row(
                        "FS_HARMONIC_FULL_LONG",
                        pair,
                        t,
                        f"{name}_PROJECTION_INVALIDATED",
                        "RESET",
                        eligibility.eligible(pair, t),
                        {"make_or_break": mb},
                    )
                )
                active.pop(pid, None)
                continue
            if not rt.full_prz_tested(low, high, float(pr["prz_low"]), float(pr["prz_high"])):
                continue
            if pid in seen_terminal:
                active.pop(pid, None)
                continue
            seen_terminal.add(pid)
            completed += 1
            a4 = rec["pivots"]
            X, A, B, C = [p.price for p in a4]
            D = float(
                pr["prz_low"]
            )  # canonical bullish completion price at deepest required PRZ level
            c = rt.HarmonicCandidate(
                name,
                X,
                A,
                B,
                C,
                D,
                float(pr["prz_low"]),
                float(pr["prz_high"]),
                mb,
                {"projected_levels": pr.get("levels", [])},
            )
            lc = rt.HarmonicLifecycle(c)
            if not lc.test_prz(t, low, high):
                active.pop(pid, None)
                continue
            events.append(
                event_row(
                    "FS_HARMONIC_FULL_LONG",
                    pair,
                    t,
                    f"{name}_TERMINAL_BAR",
                    "TERMINAL",
                    eligibility.eligible(pair, t),
                    {
                        "prz_low": c.prz_low,
                        "prz_high": c.prz_high,
                        "make_or_break": c.make_or_break,
                        "projection_id": pid,
                    },
                )
            )
            lifecycles.append(
                {
                    "lc": lc,
                    "terminal_i": i,
                    "confirm_i": None,
                    "type1_hit_i": None,
                    "done": False,
                    "pid": pid,
                }
            )
            active.pop(pid, None)

        # Advance completed lifecycles causally.
        for L in lifecycles:
            if L["done"]:
                continue
            lc = L["lc"]
            if float(row["low"]) <= lc.candidate.make_or_break:
                lc.invalidate()
                L["done"] = True
                events.append(
                    event_row(
                        "FS_HARMONIC_FULL_LONG",
                        pair,
                        t,
                        f"{lc.candidate.pattern}_LIFECYCLE_INVALIDATED",
                        "RESET",
                        eligibility.eligible(pair, t),
                        {"projection_id": L["pid"]},
                    )
                )
                continue
            if (
                lc.state == "TERMINAL_BAR_COMPLETE"
                and i > L["terminal_i"]
                and i <= L["terminal_i"] + 3
            ):
                pa = float(row["close"]) > float(x.iloc[i - 1]["close"]) and float(
                    row["close"]
                ) > float(x.iloc[L["terminal_i"]]["close"])
                lo = max(0, i - 20)
                prices = x.iloc[lo : i + 1]["close"].astype(float).tolist()
                rsis = x.iloc[lo : i + 1]["rsi14"].fillna(50).astype(float).tolist()
                rb = rt.bullish_rsi_bamm(prices, rsis)
                if lc.type1_confirm(pa, rb):
                    L["confirm_i"] = i
                    type1 += 1
                    intents.append(
                        event_row(
                            "FS_HARMONIC_FULL_LONG",
                            pair,
                            t,
                            f"{lc.candidate.pattern}_TYPE_I",
                            "THESIS_INTENT",
                            eligibility.eligible(pair, t),
                            {
                                "stop": lc.candidate.make_or_break,
                                "targets": lc.type1_targets(),
                                "price_action": pa,
                                "rsi_bamm": rb,
                                "projection_id": L["pid"],
                            },
                        )
                    )
            if lc.state == "TERMINAL_BAR_COMPLETE" and i > L["terminal_i"] + 3:
                L["done"] = True
            elif lc.state == "TYPE_I_ACTIVE" and L["confirm_i"] is not None and i > L["confirm_i"]:
                tgt1, _ = lc.type1_targets()
                if float(row["low"]) <= lc.candidate.make_or_break:
                    L["done"] = True
                elif float(row["high"]) >= tgt1:
                    lc.complete_type1()
                    L["type1_hit_i"] = i
            elif (
                lc.state == "TYPE_I_COMPLETE"
                and L["type1_hit_i"] is not None
                and i > L["type1_hit_i"]
                and i <= L["type1_hit_i"] + 40
            ):
                if float(row["low"]) <= lc.candidate.make_or_break:
                    L["done"] = True
                    events.append(
                        event_row(
                            "FS_HARMONIC_FULL_LONG",
                            pair,
                            t,
                            f"{lc.candidate.pattern}_TYPE_II_INVALIDATED",
                            "RESET",
                            eligibility.eligible(pair, t),
                            {
                                "projection_id": L["pid"],
                                "make_or_break": lc.candidate.make_or_break,
                            },
                        )
                    )
                    continue
                renewed = float(row["close"]) > float(x.iloc[i - 1]["close"])
                if lc.type2_retest(float(row["low"]), float(row["high"]), renewed):
                    type2 += 1
                    type2_meta = {
                        "projection_id": L["pid"],
                        "stop": lc.candidate.make_or_break,
                        "targets": lc.type1_targets(),
                    }
                    events.append(
                        event_row(
                            "FS_HARMONIC_FULL_LONG",
                            pair,
                            t,
                            f"{lc.candidate.pattern}_TYPE_II",
                            "THESIS_INTENT",
                            eligibility.eligible(pair, t),
                            type2_meta,
                        )
                    )
                    intents.append(
                        event_row(
                            "FS_HARMONIC_FULL_LONG",
                            pair,
                            t,
                            f"{lc.candidate.pattern}_TYPE_II",
                            "THESIS_INTENT",
                            eligibility.eligible(pair, t),
                            type2_meta,
                        )
                    )
                    L["done"] = True
            elif (
                lc.state == "TYPE_I_COMPLETE"
                and L["type1_hit_i"] is not None
                and i > L["type1_hit_i"] + 40
            ):
                L["done"] = True
        # `done` records are skipped forever by the reference code; deleting them is output-neutral.
        if lifecycles:
            lifecycles = [L for L in lifecycles if not L["done"]]

    summary = {
        "system_id": "FS_HARMONIC_FULL_LONG",
        "pair": pair,
        "transition_count": 0,
        "event_count": len(events),
        "intent_count": len(intents),
        "final_state": "N/A",
        "projected_count": projected,
        "terminal_count": completed,
        "type1_count": type1,
        "type2_count": type2,
        "projection_invalidated_count": invalidated,
        "open_projection_count": len(active),
    }
    return [], events, intents, summary


# =============================================================================
# CLASSICAL
# =============================================================================


def scan_classical(pair, h4, eligibility, *, runtime_factory=None):
    x = add_indicators(h4)
    piv = rt.confirmed_pivots_2l2r(x)
    pe = pivot_events(piv)
    cr = (runtime_factory or rt.ClassicalRuntime)(pair)
    events = []
    intents = []
    seen = set()
    meta = {}
    expiry_mature = 180  # 30 days of 4H bars; safety only, no alpha
    expiry_breakout = 60  # 10 days after breakout
    last_cont_admit = {}
    for i, row in x.iterrows():
        t = utc(row["timestamp"])
        eligible = eligibility.eligible(pair, t)
        atr = float(row["atr20"]) if pd.notna(row["atr20"]) else math.nan
        # Pivot-based patterns only when a pivot becomes newly available.
        if pe.get(t):
            pats = rt.classical_patterns_from_pivots(piv, atr, t) if math.isfinite(atr) else []
            # Bar-based continuation families sampled at structural update times to
            # avoid same pattern every bar.
            prior_pivots = (
                rt.available_pivots(piv, utc(x.iloc[i - 12]["timestamp"])) if i >= 12 else []
            )
            pats += (
                rt.continuation_patterns_from_bars(x.iloc[: i + 1], atr, prior_pivots)
                if math.isfinite(atr)
                else []
            )
            for p in pats:
                sig = f"{p.kind}:{round(p.boundary, 8)}:{round(p.support, 8)}:{str(p.formed_at)}"
                if p.kind in {"FLAG", "PENNANT", "BASE_BREAKOUT"}:
                    lasti = last_cont_admit.get(p.kind, -999)
                    if i - lasti < 6:
                        continue
                    last_cont_admit[p.kind] = i
                if sig in seen:
                    continue
                seen.add(sig)
                cr.mature(p)
                meta[p.pattern_id] = {"mature_i": i, "breakout_i": None}
                events.append(
                    event_row(
                        "FS_CLASSICAL_FULL_LONG",
                        pair,
                        t,
                        f"{p.kind}_MATURE",
                        "STRUCTURAL",
                        eligible,
                        {"boundary": p.boundary, "support": p.support},
                    )
                )
        # update all pending, with explicit expiry
        for pid in list(cr.pending.keys()):
            q = cr.pending.get(pid)
            if q is None:
                continue
            m = meta.setdefault(pid, {"mature_i": i, "breakout_i": None})
            if q["state"] == "MATURE" and i - m["mature_i"] > expiry_mature:
                cr.pending.pop(pid, None)
                events.append(
                    event_row(
                        "FS_CLASSICAL_FULL_LONG",
                        pair,
                        t,
                        "PATTERN_EXPIRED",
                        "RESET",
                        eligible,
                        {"pattern": q["pattern"].kind},
                    )
                )
                continue
            if (
                q["state"] == "BREAKOUT"
                and m["breakout_i"] is not None
                and i - m["breakout_i"] > expiry_breakout
            ):
                cr.pending.pop(pid, None)
                events.append(
                    event_row(
                        "FS_CLASSICAL_FULL_LONG",
                        pair,
                        t,
                        "BREAKOUT_EXPIRED",
                        "RESET",
                        eligible,
                        {"pattern": q["pattern"].kind},
                    )
                )
                continue
            if q["state"] == "MATURE":
                vm = float(row["volume_median20"]) if pd.notna(row["volume_median20"]) else math.inf
                if cr.update_breakout(t, pid, float(row["close"]), float(row["volume"]), vm):
                    m["breakout_i"] = i
                    events.append(
                        event_row(
                            "FS_CLASSICAL_FULL_LONG",
                            pair,
                            t,
                            f"{q['pattern'].kind}_BREAKOUT",
                            "ACTIVATION",
                            eligible,
                            {},
                        )
                    )
            if q["state"] == "BREAKOUT" and m["breakout_i"] is not None and i > m["breakout_i"]:
                # confirmed higher low after breakout
                lows = [
                    p
                    for p in rt.available_pivots(piv, t)
                    if p.kind == "L" and m["breakout_i"] is not None and p.index > m["breakout_i"]
                ]
                hl = lows[-1].price if lows else None
                intent = cr.entry_intent(t, pid, float(row["low"]), float(row["close"]), hl)
                if q["state"] == "INVALIDATED":
                    cr.pending.pop(pid, None)
                    events.append(event_row("FS_CLASSICAL_FULL_LONG", pair, t,
                        "PATTERN_PREENTRY_INVALIDATED", "INVALIDATION", eligible,
                        {"pattern_id": pid, "support": q["pattern"].support}))
                    continue
                if intent is not None:
                    if eligible:
                        intents.append(
                            event_row(
                                "FS_CLASSICAL_FULL_LONG",
                                pair,
                                t,
                                intent.branch,
                                "THESIS_INTENT",
                                True,
                                {
                                    "stop": intent.stop,
                                    "target": intent.target,
                                    "pattern_id": pid,
                                    "pattern_kind": q["pattern"].kind,
                                    "formed_at": str(q["pattern"].formed_at),
                                    "prior_trend": q["pattern"].prior_trend,
                                    "frozen_boundary": q["pattern"].boundary,
                                    "frozen_support": q["pattern"].support,
                                    "breakout_time": str(q["breakout_time"]),
                                },
                            )
                        )
                    events.append(
                        event_row(
                            "FS_CLASSICAL_FULL_LONG",
                            pair,
                            t,
                            "ACCEPTANCE",
                            "ACCEPTANCE",
                            eligible,
                            {"branch": intent.branch},
                        )
                    )
                    cr.pending.pop(pid, None)
    trans = transition_rows(cr.transitions, eligibility)
    summary = {
        "system_id": "FS_CLASSICAL_FULL_LONG",
        "pair": pair,
        "transition_count": len(trans),
        "event_count": len(events),
        "intent_count": len(intents),
        "final_state": "N/A",
        "mature_count": sum(e["stage"] == "STRUCTURAL" for e in events),
        "breakout_count": sum(e["stage"] == "ACTIVATION" for e in events),
        "expired_count": sum(e["stage"] == "RESET" for e in events),
    }
    return trans, events, intents, summary


# =============================================================================
# ELLIOTT
# =============================================================================


def scan_elliott(pair, h1, h4, d1, eligibility):
    """Hourly causal Elliott census with absorbing count invalidation.

    Owner-count selection and the full parent/child multi-degree grammar remain
    UNRESOLVED; therefore emitted consensus remains DIAGNOSTIC_ONLY.
    """
    f1 = add_indicators(h1)
    f4 = add_indicators(h4)
    fd = add_indicators(d1)
    p1 = rt.confirmed_pivots_2l2r(f1)
    p4 = rt.confirmed_pivots_2l2r(f4)
    pd1 = rt.confirmed_pivots_2l2r(fd)
    i1 = i4 = id1 = 0
    prev1 = prev4 = prevd = -1
    seen = set()
    events = []
    intents = []
    consensus_count = 0
    tombstones = set()
    f1_ts = pd.to_datetime(f1["timestamp"], utc=True)
    f1_close = f1["close"].astype(float).to_numpy()
    cached = {"1H": [], "4H": [], "1D": []}

    for pj, t0 in enumerate(f1_ts):
        t = utc(t0)
        if t >= DATA_CUTOFF:
            break
        while i1 < len(p1) and utc(p1[i1].confirm_time) <= t:
            i1 += 1
        while i4 < len(p4) and utc(p4[i4].confirm_time) <= t:
            i4 += 1
        while id1 < len(pd1) and utc(pd1[id1].confirm_time) <= t:
            id1 += 1

        for deg, pv, n, prevname in [
            ("1H", p1, i1, "prev1"),
            ("4H", p4, i4, "prev4"),
            ("1D", pd1, id1, "prevd"),
        ]:
            prev = {"prev1": prev1, "prev4": prev4, "prevd": prevd}[prevname]
            if n != prev:
                sl = pv[max(0, n - 24) : n]
                xs = rt.enumerate_impulse_counts(sl, deg, t) + rt.enumerate_corrective_counts(
                    sl, deg, t
                )
                cached[deg] = [
                    c for c in {c.count_id: c for c in xs}.values() if c.count_id not in tombstones
                ]
                if prevname == "prev1":
                    prev1 = n
                elif prevname == "prev4":
                    prev4 = n
                else:
                    prevd = n

        price = float(f1_close[pj])
        cached, new_tombstones = rt.invalidate_elliott_counts_persistent(cached, price, tombstones)
        newly_dead = new_tombstones - tombstones
        tombstones = new_tombstones
        eligible = eligibility.eligible(pair, t)

        for cid in sorted(newly_dead):
            events.append(
                event_row(
                    "FS_ELLIOTT_FULL_LONG",
                    pair,
                    t,
                    "COUNT_INVALIDATED",
                    "RESET",
                    eligible,
                    {"count_id": cid, "price": price},
                )
            )

        new = []
        for deg, xs in cached.items():
            for c in xs:
                if c.count_id not in seen:
                    seen.add(c.count_id)
                    new.append(c)
                    events.append(
                        event_row(
                            "FS_ELLIOTT_FULL_LONG",
                            pair,
                            t,
                            f"{c.direction}_{c.kind}",
                            "STRUCTURAL",
                            eligible,
                            {
                                "degree": deg,
                                "direction": c.direction,
                                "count_id": c.count_id,
                                "invalidation": c.invalidation,
                                "objective": c.objective,
                            },
                        )
                    )

        cons = rt.ElliottOnlineRuntime.consensus(cached)
        if cons == "CONSENSUS_BULLISH" and eligible and any(c.priority >= 2 for c in new):
            inv = rt.ElliottOnlineRuntime.common_invalidation(cached)
            objs = [
                float(c.objective)
                for xs in cached.values()
                for c in xs
                if c.direction == "BULLISH"
                and c.priority >= 2
                and c.objective is not None
                and float(c.objective) > price
            ]
            if inv is not None and float(inv) < price and objs:
                consensus_count += 1
                intents.append(
                    event_row(
                        "FS_ELLIOTT_FULL_LONG",
                        pair,
                        t,
                        "COUNT_CONSENSUS_DIAGNOSTIC",
                        "DIAGNOSTIC_ONLY",
                        True,
                        {
                            "stop": float(inv),
                            "target": min(objs),
                            "signal_price": price,
                            "new_count_ids": [c.count_id for c in new],
                            "funded_ready": False,
                            "reason": "OWNER_COUNT_AND_PARENT_CHILD_GRAMMAR_UNRESOLVED",
                        },
                    )
                )

    summary = {
        "system_id": "FS_ELLIOTT_FULL_LONG",
        "pair": pair,
        "transition_count": 0,
        "event_count": len(events),
        "intent_count": len(intents),
        "final_state": "N/A",
        "unique_count_ids": len(seen),
        "consensus_event_count": consensus_count,
        "tombstoned_count_ids": len(tombstones),
        "funded_ready": False,
    }
    return [], events, intents, summary


# =============================================================================
# WEEKLY RETURN FOR DOW + HYBRID HELPERS
# =============================================================================


def weekly_return_rows(pair, raw, ranking_pair: pd.DataFrame):
    rows = []
    for t in ranking_pair["decision_time"]:
        t = utc(t)
        a = raw.loc[raw["timestamp"] <= t]
        b = raw.loc[raw["timestamp"] <= t - pd.Timedelta(hours=72)]
        if a.empty or b.empty:
            continue
        p1 = float(a.iloc[-1]["close"])
        p0 = float(b.iloc[-1]["close"])
        rows.append(
            {"pair": pair, "decision_time": t, "ret72": p1 / p0 - 1 if p0 > 0 else math.nan}
        )
    return rows


# =============================================================================
# PAIR CENSUS
# =============================================================================


def scan_pair(pair, raw, h4, d1, btc_raw, eth_raw, eligibility, market_transitions, ranking_pair):
    trs = []
    ev = []
    it = []
    summ = []
    for fn, args in [
        (scan_wyckoff, (pair, h4, raw, btc_raw, eligibility, market_transitions, False)),
        (scan_ict, (pair, raw, h4, d1, btc_raw, eth_raw, eligibility)),
        (scan_harmonic, (pair, h4, eligibility)),
        (scan_classical, (pair, h4, eligibility)),
        (scan_elliott, (pair, raw, h4, d1, eligibility)),
    ]:
        t, e, i, s = fn(*args)
        trs += t
        ev += e
        it += i
        summ.append(s)
    wr = weekly_return_rows(pair, raw, ranking_pair)
    return trs, ev, it, summ, wr
