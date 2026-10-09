"""Research-only integrated authority; not production. See source provenance manifest."""

from __future__ import annotations

import json
import math

import pandas as pd

from . import akah_full_fidelity_runtime_v1 as rt
from . import akah_native_replay_engine_v1 as eng


class ManagementBindingError(RuntimeError):
    pass


def _get(row, name, default=None):
    return getattr(row, name, default) if hasattr(row, name) else row.get(name, default)


def _meta(row):
    raw = _get(row, "metadata", "{}")
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)


def evaluate_ict_native(row, raw, mss_times=None):
    meta = _meta(row)
    raid_time = meta.get("raid_time")
    if raid_time is None:
        raise ManagementBindingError("ICT_RAID_TIME_PROVENANCE_REQUIRED")
    raid_time = eng.utc(pd.Timestamp(raid_time))
    ts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
    en = int(ts.get_indexer([eng.utc(_get(row, "entry_time"))])[0])
    if en < 0:
        return None
    stop = float(_get(row, "stop"))
    target = eng.targets(_get(row, "targets_json"))[0]
    mss = set(eng.utc(x) for x in (eng.bearish_mss_times(raw) if mss_times is None else mss_times))
    trace = []
    for k in range(en, len(raw)):
        rr = raw.iloc[k]
        bt = eng.utc(ts[k])
        ot = eng.bar_open_time(bt)
        oo = float(rr["open"])
        lo = float(rr["low"])
        hi = float(rr["high"])
        if oo <= stop:
            trace.append(
                {
                    "time": str(ot),
                    "source": "rt.ict_manage_active",
                    "action": "STRUCTURAL_INVALIDATION_GAP",
                }
            )
            return {
                "exit_time": ot,
                "exit_price": oo,
                "exit_reason": "STRUCTURAL_INVALIDATION_GAP",
                "fills": [(1.0, ot, oo, "STRUCTURAL_INVALIDATION_GAP")],
                "management_trace": trace,
            }
        action = rt.ict_manage_active(
            t=bt,
            raid_time=raid_time,
            bar_low=lo,
            bar_high=hi,
            raid_low=stop,
            target=target,
            bearish_mss=bt in mss,
        )
        trace.append({"time": str(bt), "source": "rt.ict_manage_active", "action": action})
        if action == "STRUCTURAL_INVALIDATION":
            return {
                "exit_time": bt,
                "exit_price": stop,
                "exit_reason": action,
                "fills": [(1.0, bt, stop, action)],
                "management_trace": trace,
            }
        if action == "OPPOSING_LIQUIDITY_TARGET":
            return {
                "exit_time": bt,
                "exit_price": target,
                "exit_reason": action,
                "fills": [(1.0, bt, target, action)],
                "management_trace": trace,
            }
        if action == "BEARISH_MSS_EXIT_NEXT_OPEN":
            j = eng.next_open_index(ts, bt)
            if j is not None:
                t = eng.bar_open_time(ts[j])
                px = float(raw.iloc[j]["open"])
                return {
                    "exit_time": t,
                    "exit_price": px,
                    "exit_reason": action,
                    "fills": [(1.0, t, px, action)],
                    "management_trace": trace,
                }
        if action == "NY_1600_DAY_BOUNDARY":
            # A completed 16:00 bar cannot authorize a 15:00 open fill.
            j = eng.next_open_index(ts, bt)
            if j is not None:
                t = eng.bar_open_time(ts[j])
                px = float(raw.iloc[j]["open"])
                return {
                    "exit_time": t,
                    "exit_price": px,
                    "exit_reason": action,
                    "fills": [(1.0, t, px, action)],
                    "management_trace": trace,
                }
    t = eng.utc(ts[-1])
    px = float(raw.iloc[-1]["close"])
    return {
        "exit_time": t,
        "exit_price": px,
        "exit_reason": "END_OF_DATA",
        "fills": [(1.0, t, px, "END_OF_DATA")],
        "management_trace": trace,
    }


def evaluate_classical_native(row, raw, h4, down_times=None):
    ts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
    en = int(ts.get_indexer([eng.utc(_get(row, "entry_time"))])[0])
    if en < 0:
        return None
    stop = float(_get(row, "stop"))
    target = eng.targets(_get(row, "targets_json"))[0]
    meta = _meta(row)
    kind = str(meta.get("pattern_kind", ""))
    if not kind:
        raise ManagementBindingError("CLASSICAL_PATTERN_KIND_PROVENANCE_REQUIRED")
    downs = set(
        eng.utc(x)
        for x in (eng.confirmed_primary_down_times(h4) if down_times is None else down_times)
    )
    hp = rt.confirmed_pivots_2l2r(eng.det.add_indicators(h4))
    continuation = kind in {"FLAG", "PENNANT", "BASE_BREAKOUT", "ASC_TRIANGLE", "SYMM_TRIANGLE"}
    trace = []
    current_stop = stop
    for k in range(en, len(raw)):
        rr = raw.iloc[k]
        bt = eng.utc(ts[k])
        ot = eng.bar_open_time(bt)
        oo = float(rr["open"])
        lo = float(rr["low"])
        hi = float(rr["high"])
        close = float(rr["close"])
        if oo <= current_stop:
            return {
                "exit_time": ot,
                "exit_price": oo,
                "exit_reason": "STRUCTURAL_STOP_GAP",
                "fills": [(1.0, ot, oo, "STRUCTURAL_STOP_GAP")],
                "management_trace": trace,
            }
        if lo <= current_stop:
            return {
                "exit_time": bt,
                "exit_price": current_stop,
                "exit_reason": "STRUCTURAL_STOP",
                "fills": [(1.0, bt, current_stop, "STRUCTURAL_STOP")],
                "management_trace": trace,
            }
        if hi >= target:
            return {
                "exit_time": bt,
                "exit_price": target,
                "exit_reason": "OBJECTIVE_REACHED",
                "fills": [(1.0, bt, target, "OBJECTIVE_REACHED")],
                "management_trace": trace,
            }
        hl = None
        if continuation:
            lows = [
                p
                for p in hp
                if p.kind == "L" and eng.utc(p.confirm_time) <= bt and p.price > current_stop
            ]
            hl = float(lows[-1].price) if lows else None
        decision = rt.classical_management_update(
            price=close,
            target=target,
            current_stop=current_stop,
            confirmed_higher_low=hl,
            primary_trend="DOWN" if bt in downs else "UP",
            pattern_failed=False,
        )
        trace.append(
            {
                "time": str(bt),
                "source": "rt.classical_management_update",
                "action": decision["action"],
                "stop": decision["stop"],
            }
        )
        current_stop = max(current_stop, float(decision["stop"]))
        if decision["action"] == "EXIT_PRIMARY_TREND_REVERSAL":
            j = eng.next_open_index(ts, bt)
            if j is not None:
                t = eng.bar_open_time(ts[j])
                px = float(raw.iloc[j]["open"])
                return {
                    "exit_time": t,
                    "exit_price": px,
                    "exit_reason": decision["action"],
                    "fills": [(1.0, t, px, decision["action"])],
                    "management_trace": trace,
                }
    t = eng.utc(ts[-1])
    px = float(raw.iloc[-1]["close"])
    return {
        "exit_time": t,
        "exit_price": px,
        "exit_reason": "END_OF_DATA",
        "fills": [(1.0, t, px, "END_OF_DATA")],
        "management_trace": trace,
    }


def evaluate_wyckoff_native(row, raw, h4, asset_events, market_sensor, btc_raw):
    stop = float(_get(row, "stop"))
    tgts = eng.targets(_get(row, "targets_json"))
    target = float(tgts[0]) if tgts else float(_get(row, "target", math.nan))
    if not math.isfinite(target):
        raise ManagementBindingError("WYCKOFF_TARGET_REVIEW_POINT_REQUIRED_FOR_POSITION_PLAN")
    intent = rt.ThesisIntent(
        "FS_WYCKOFF_FULL_LONG",
        str(_get(row, "pair")),
        eng.utc(_get(row, "signal_time")),
        str(_get(row, "event", "WYCKOFF")),
        stop,
        target,
        {"staged_initial_fraction": 0.5 if str(_get(row, "action", "")) == "ENTER_50" else 1.0},
    )
    plan = rt.build_wyckoff_position_plan(intent)
    ts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
    en = int(ts.get_indexer([eng.utc(_get(row, "entry_time"))])[0])
    if en < 0:
        return None
    q = asset_events.loc[
        (asset_events["system_id"] == "FS_WYCKOFF_FULL_LONG")
        & (pd.to_datetime(asset_events["timestamp"], utc=True) > eng.utc(_get(row, "signal_time")))
    ].copy()
    q["timestamp"] = pd.to_datetime(q["timestamp"], utc=True)
    by_time = {}
    for _, er in q.iterrows():
        by_time.setdefault(eng.utc(er["timestamp"]), []).append(er)
    trace = []
    for k in range(en, len(raw)):
        rr = raw.iloc[k]
        bt = eng.utc(ts[k])
        ot = eng.bar_open_time(bt)
        oo = float(rr["open"])
        lo = float(rr["low"])
        if oo <= plan.current_stop:
            return {
                "exit_time": ot,
                "exit_price": oo,
                "exit_reason": "STRUCTURAL_STOP_GAP",
                "fills": [(1.0, ot, oo, "STRUCTURAL_STOP_GAP")],
                "management_trace": trace,
            }
        if lo <= plan.current_stop:
            return {
                "exit_time": bt,
                "exit_price": plan.current_stop,
                "exit_reason": "STRUCTURAL_STOP",
                "fills": [(1.0, bt, plan.current_stop, "STRUCTURAL_STOP")],
                "management_trace": trace,
            }
        for er in by_time.get(bt, []):
            ev = str(er.get("event", ""))
            meta = eng.parse_json(er.get("metadata", "{}"))
            if ev == "LPS_HOLDS" and meta.get("low") is not None:
                plan.trail_after_sos_lps(float(meta["low"]))
                trace.append(
                    {
                        "time": str(bt),
                        "source": "WyckoffPositionPlan.trail_after_sos_lps",
                        "stop": plan.current_stop,
                    }
                )
            if ev == "DISTRIBUTION_RISK":
                j = eng.next_open_index(ts, bt)
                if j is not None:
                    t = eng.bar_open_time(ts[j])
                    px = float(raw.iloc[j]["open"])
                    return {
                        "exit_time": t,
                        "exit_price": px,
                        "exit_reason": "ASSET_DISTRIBUTION",
                        "fills": [(1.0, t, px, "ASSET_DISTRIBUTION")],
                        "management_trace": trace,
                    }
    t = eng.utc(ts[-1])
    px = float(raw.iloc[-1]["close"])
    return {
        "exit_time": t,
        "exit_price": px,
        "exit_reason": "END_OF_DATA",
        "fills": [(1.0, t, px, "END_OF_DATA")],
        "management_trace": trace,
    }
