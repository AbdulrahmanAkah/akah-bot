"""Research-only integrated authority; not production. See source provenance manifest."""

from __future__ import annotations

import bisect
import json
import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import akah_full_fidelity_runtime_v1 as rt
from . import akah_replay_ready_detectors_v1 as det
from .akah_foundation_core_v1r1 import utc

# Optimizations are enabled explicitly by the fidelity runner, not on import.

START = pd.Timestamp("2022-01-01T00:00:00Z")
END = pd.Timestamp("2024-01-01T00:00:00Z")
INITIAL_EQUITY = 100_000.0
FIXED_RISK_FRACTION = 0.005
MAX_POSITIONS = 5
MAX_GROSS_EXPOSURE_FRACTION = 0.90
EQUAL_SLOT_FRACTION = 0.18
MAX_SINGLE_ASSET_FRACTION = 0.40
CAPACITY_NOTIONAL_FRACTION = 0.005
COST_SCENARIOS = {"1X": 0.0025, "2X": 0.0050}


def parse_json(v):
    if isinstance(v, dict):
        return v
    return json.loads(v)


def targets(v):
    if isinstance(v, list):
        return [float(x) for x in v]
    return [float(x) for x in json.loads(v)]


def next_open_index(ts: pd.DatetimeIndex, t: pd.Timestamp) -> int | None:
    j = int(ts.searchsorted(utc(t), side="right"))
    return j if j < len(ts) else None


def gap_or_intrabar_static(open_, high, low, stop, target):
    """
    Long-side deterministic conservative ordering:
    1) gap through stop at open
    2) gap above target at open -> target fill (conservative target price)
    3) if stop+target both occur intrabar, stop wins (unknown path)
    4) otherwise whichever single level is touched.
    """
    if open_ <= stop:
        return "STOP", float(open_)
    if open_ >= target:
        return "TARGET", float(target)
    sh = low <= stop
    th = high >= target
    if sh and th:
        return "STOP", float(stop)
    if sh:
        return "STOP", float(stop)
    if th:
        return "TARGET", float(target)
    return None, None


def confirmed_primary_down_times(h4: pd.DataFrame) -> list[pd.Timestamp]:
    x = det.add_indicators(h4)
    piv = rt.confirmed_pivots_2l2r(x)
    by = {}
    for p in piv:
        by.setdefault(utc(p.confirm_time), []).append(p)
    available = []
    out = []
    prev = "UNKNOWN"
    for t in sorted(by):
        available.extend(by[t])
        tr = rt.trend_from_pivots(rt.collapse_same_kind(available))
        if tr == "DOWN" and prev != "DOWN":
            out.append(t)
        prev = tr
    return out


def bearish_mss_times(raw: pd.DataFrame) -> list[pd.Timestamp]:
    x = det.add_indicators(raw)
    piv = rt.confirmed_pivots_2l2r(x)
    by = {}
    for p in piv:
        by.setdefault(utc(p.confirm_time), []).append(p)
    latest_low = None
    out = []
    for _, r in x.iterrows():
        t = utc(r["timestamp"])
        for p in by.get(t, []):
            if p.kind == "L":
                latest_low = float(p.price)
        if latest_low is not None and float(r["close"]) < latest_low:
            out.append(t)
            latest_low = None  # require a newly confirmed internal low before another MSS event
    return out


def first_timeline_exit(ts: pd.DatetimeIndex, times: list[pd.Timestamp], entry_time: pd.Timestamp):
    j = bisect.bisect_right(times, utc(entry_time))
    if j >= len(times):
        return None, None
    sig = times[j]
    k = next_open_index(ts, sig)
    if k is None:
        return None, None
    return k, sig


def ny16_exit_index(ts: pd.DatetimeIndex, entry_idx: int):
    for k in range(entry_idx, len(ts)):
        open_time = utc(ts[k]) - pd.Timedelta(hours=1)
        ny = open_time.tz_convert("America/New_York")
        if ny.weekday() < 5 and ny.hour == 16 and ny.minute == 0:
            return k
    return None


def quote_turnover_24h(raw: pd.DataFrame, signal_time: pd.Timestamp) -> float:
    ts = pd.to_datetime(raw["timestamp"], utc=True)
    t = utc(signal_time)
    a = int(ts.searchsorted(t - pd.Timedelta(hours=24), side="right"))
    b = int(ts.searchsorted(t, side="right"))
    if b <= a:
        return 0.0
    q = raw.iloc[a:b]
    return float((q["volume"].astype(float) * q["close"].astype(float)).sum())


def bar_open_time(bar_timestamp: pd.Timestamp) -> pd.Timestamp:
    # Raw timestamp is candle CLOSE time. The candle's open is one hour earlier.
    return utc(bar_timestamp) - pd.Timedelta(hours=1)


def _first_true(mask: np.ndarray) -> int | None:
    if mask.size == 0 or not bool(mask.any()):
        return None
    return int(np.argmax(mask))


def _static_level_event(
    raw: pd.DataFrame, en: int, stop: float, target: float, end_idx: int | None = None
):
    """
    Fast long-side event search. For an unknown intrabar path, stop has
    precedence over target when both are touched. Gap/open events happen at
    the bar's effective open timestamp; intrabar touches are conservatively
    timestamped at bar close.
    """
    last = len(raw) - 1 if end_idx is None else min(int(end_idx), len(raw) - 1)
    if en > last:
        return None
    q = raw.iloc[en : last + 1]
    o = q["open"].astype(float).to_numpy()
    h = q["high"].astype(float).to_numpy()
    l = q["low"].astype(float).to_numpy()  # noqa: E741 - retained geometric notation
    mask = (o <= stop) | (o >= target) | (l <= stop) | (h >= target)
    j = _first_true(mask)
    if j is None:
        return None
    k = en + j
    oo, hh, ll = float(o[j]), float(h[j]), float(l[j])
    bt = utc(raw.iloc[k]["timestamp"])
    ot = bar_open_time(bt)
    if oo <= stop:
        return {"index": k, "time": ot, "price": oo, "reason": "STOP_GAP"}
    if oo >= target:
        return {"index": k, "time": ot, "price": target, "reason": "TARGET"}
    if ll <= stop:
        return {"index": k, "time": bt, "price": stop, "reason": "STOP"}
    if hh >= target:
        return {"index": k, "time": bt, "price": target, "reason": "TARGET"}
    return None


def evaluate_classical(row, raw, h4, down_times=None):
    ts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
    en = int(ts.get_indexer([utc(row.entry_time)])[0])
    if en < 0:
        return None
    stop = float(row.stop)
    target = targets(row.targets_json)[0]
    downs = confirmed_primary_down_times(h4) if down_times is None else down_times
    rev_idx, rev_sig = first_timeline_exit(ts, downs, utc(row.entry_time))
    ev = _static_level_event(raw, en, stop, target, rev_idx)
    if rev_idx is not None and (ev is None or rev_idx <= ev["index"]):
        r = raw.iloc[rev_idx]
        t = bar_open_time(ts[rev_idx])
        px = float(r["open"])
        return {
            "exit_time": t,
            "exit_price": px,
            "exit_reason": "PRIMARY_TREND_REVERSAL",
            "fills": [(1.0, t, px, "PRIMARY_TREND_REVERSAL")],
        }
    if ev is not None:
        return {
            "exit_time": ev["time"],
            "exit_price": ev["price"],
            "exit_reason": ev["reason"],
            "fills": [(1.0, ev["time"], ev["price"], ev["reason"])],
        }
    r = raw.iloc[-1]
    t = utc(ts[-1])
    px = float(r["close"])
    return {
        "exit_time": t,
        "exit_price": px,
        "exit_reason": "END_OF_DATA",
        "fills": [(1.0, t, px, "END_OF_DATA")],
    }


def evaluate_elliott(row, raw):
    ts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
    en = int(ts.get_indexer([utc(row.entry_time)])[0])
    if en < 0:
        return None
    stop = float(row.stop)
    target = targets(row.targets_json)[0]
    ev = _static_level_event(raw, en, stop, target)
    if ev is not None:
        return {
            "exit_time": ev["time"],
            "exit_price": ev["price"],
            "exit_reason": ev["reason"],
            "fills": [(1.0, ev["time"], ev["price"], ev["reason"])],
        }
    t = utc(ts[-1])
    px = float(raw.iloc[-1]["close"])
    return {
        "exit_time": t,
        "exit_price": px,
        "exit_reason": "END_OF_DATA",
        "fills": [(1.0, t, px, "END_OF_DATA")],
    }


def evaluate_harmonic(row, raw):
    ts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
    en = int(ts.get_indexer([utc(row.entry_time)])[0])
    if en < 0:
        return None
    stop = float(row.stop)
    tgts = targets(row.targets_json)
    if len(tgts) < 2:
        return None
    t1, t2 = float(tgts[0]), float(tgts[1])
    entry = float(row.entry_open)

    q = raw.iloc[en:]
    o = q["open"].astype(float).to_numpy()
    h = q["high"].astype(float).to_numpy()
    l = q["low"].astype(float).to_numpy()  # noqa: E741 - retained geometric notation
    first_mask = (o <= stop) | (o >= t1) | (l <= stop) | (h >= t1)
    j = _first_true(first_mask)
    fills = []
    if j is None:
        t = utc(ts[-1])
        px = float(raw.iloc[-1]["close"])
        return {
            "exit_time": t,
            "exit_price": px,
            "exit_reason": "END_OF_DATA",
            "fills": [(1.0, t, px, "END_OF_DATA")],
        }

    k = en + j
    oo, hh, ll = float(o[j]), float(h[j]), float(l[j])
    bt = utc(ts[k])
    ot = bar_open_time(bt)

    # Open events are known before the intrabar path.
    if oo <= stop:
        fills = [(1.0, ot, oo, "HARD_STOP")]
    elif oo >= t1:
        fills.append((0.5, ot, t1, "TGT1"))
        if oo >= t2:
            fills.append((0.5, ot, t2, "TGT2"))
        elif ll <= stop:
            fills.append((0.5, bt, stop, "HARD_STOP_AFTER_OPEN_TGT1"))
        elif hh >= t2:
            fills.append((0.5, bt, t2, "TGT2"))
        else:
            # Breakeven trail becomes active only from next bar.
            ev2 = _static_level_event(raw, k + 1, max(stop, entry), t2)
            if ev2 is None:
                t = utc(ts[-1])
                px = float(raw.iloc[-1]["close"])
                fills.append((0.5, t, px, "END_OF_DATA"))
            else:
                reason = "TGT2" if ev2["reason"] == "TARGET" else "BREAKEVEN_OR_TRAIL_STOP"
                fills.append((0.5, ev2["time"], ev2["price"], reason))
    else:
        # Unknown intrabar ordering: stop wins if both stop and TGT1 are touched.
        if ll <= stop:
            fills = [(1.0, bt, stop, "HARD_STOP")]
        elif hh >= t2:
            fills = [(0.5, bt, t1, "TGT1"), (0.5, bt, t2, "TGT2")]
        elif hh >= t1:
            fills = [(0.5, bt, t1, "TGT1")]
            ev2 = _static_level_event(raw, k + 1, max(stop, entry), t2)
            if ev2 is None:
                t = utc(ts[-1])
                px = float(raw.iloc[-1]["close"])
                fills.append((0.5, t, px, "END_OF_DATA"))
            else:
                reason = "TGT2" if ev2["reason"] == "TARGET" else "BREAKEVEN_OR_TRAIL_STOP"
                fills.append((0.5, ev2["time"], ev2["price"], reason))
        else:
            raise RuntimeError("HARMONIC_FIRST_EVENT_INCONSISTENT")

    avg = sum(fr * px for fr, _, px, _ in fills)
    return {
        "exit_time": fills[-1][1],
        "exit_price": avg,
        "exit_reason": fills[-1][3],
        "fills": fills,
    }


def evaluate_ict(row, raw, mss_times=None):
    ts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
    en = int(ts.get_indexer([utc(row.entry_time)])[0])
    if en < 0:
        return None
    stop = float(row.stop)
    target = targets(row.targets_json)[0]
    mss = bearish_mss_times(raw) if mss_times is None else mss_times
    mss_idx, mss_sig = first_timeline_exit(ts, mss, utc(row.entry_time))
    boundary = ny16_exit_index(ts, en)
    time_idx = [x for x in [mss_idx, boundary] if x is not None]
    earliest = min(time_idx) if time_idx else None
    ev = _static_level_event(raw, en, stop, target, earliest)
    if earliest is not None and (ev is None or earliest <= ev["index"]):
        r = raw.iloc[earliest]
        t = bar_open_time(ts[earliest])
        px = float(r["open"])
        reason = (
            "NY16_SESSION_CLOSE" if boundary is not None and earliest == boundary else "BEARISH_MSS"
        )
        return {
            "exit_time": t,
            "exit_price": px,
            "exit_reason": reason,
            "fills": [(1.0, t, px, reason)],
        }
    if ev is not None:
        return {
            "exit_time": ev["time"],
            "exit_price": ev["price"],
            "exit_reason": ev["reason"],
            "fills": [(1.0, ev["time"], ev["price"], ev["reason"])],
        }
    t = utc(ts[-1])
    px = float(raw.iloc[-1]["close"])
    return {
        "exit_time": t,
        "exit_price": px,
        "exit_reason": "END_OF_DATA",
        "fills": [(1.0, t, px, "END_OF_DATA")],
    }


def evaluate_wyckoff(row, raw, h4, asset_events, market_sensor, btc_raw):
    ts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
    en = int(ts.get_indexer([utc(row.entry_time)])[0])
    if en < 0:
        return None
    stop = float(row.stop)
    ae = asset_events.loc[
        (asset_events["system_id"] == "FS_WYCKOFF_FULL_LONG")
        & (asset_events["event"] == "DISTRIBUTION_RISK")
        & (asset_events["timestamp"] > utc(row.signal_time))
    ]
    asset_times = sorted(pd.to_datetime(ae["timestamp"], utc=True).tolist())
    asset_idx, asset_sig = first_timeline_exit(ts, asset_times, utc(row.entry_time))
    x4 = det.add_indicators(h4)
    piv = rt.confirmed_pivots_2l2r(x4)
    market_idx = None
    for mt in pd.to_datetime(
        market_sensor.loc[
            (market_sensor["to_state"] == "DISTRIBUTION_RISK")
            & (pd.to_datetime(market_sensor["timestamp"], utc=True) > utc(row.signal_time)),
            "timestamp",
        ],
        utc=True,
    ):
        rs = rt.matched_swing_relative_strength(raw, btc_raw, piv, mt)
        if not rs.get("eligible", False):
            market_idx = next_open_index(ts, mt)
            if market_idx is not None:
                break
    exits = [x for x in [asset_idx, market_idx] if x is not None]
    native_idx = min(exits) if exits else None
    # Structural stop is the only price level; vectorized scan.
    q = raw.iloc[en : (native_idx + 1 if native_idx is not None else len(raw))]
    o = q["open"].astype(float).to_numpy()
    l = q["low"].astype(float).to_numpy()  # noqa: E741 - retained geometric notation
    j = _first_true((o <= stop) | (l <= stop))
    stop_idx = None if j is None else en + j
    if native_idx is not None and (stop_idx is None or native_idx <= stop_idx):
        r = raw.iloc[native_idx]
        t = bar_open_time(ts[native_idx])
        px = float(r["open"])
        reason = (
            "ASSET_DISTRIBUTION"
            if asset_idx is not None and native_idx == asset_idx
            else "MARKET_DISTRIBUTION_RS_LOSS"
        )
        return {
            "exit_time": t,
            "exit_price": px,
            "exit_reason": reason,
            "fills": [(1.0, t, px, reason)],
        }
    if stop_idx is not None:
        r = raw.iloc[stop_idx]
        bt = utc(ts[stop_idx])
        oo = float(r["open"])
        if oo <= stop:
            t = bar_open_time(bt)
            px = oo
            reason = "STRUCTURAL_STOP_GAP"
        else:
            t = bt
            px = stop
            reason = "STRUCTURAL_STOP"
        return {
            "exit_time": t,
            "exit_price": px,
            "exit_reason": reason,
            "fills": [(1.0, t, px, reason)],
        }
    t = utc(ts[-1])
    px = float(raw.iloc[-1]["close"])
    return {
        "exit_time": t,
        "exit_price": px,
        "exit_reason": "END_OF_DATA",
        "fills": [(1.0, t, px, "END_OF_DATA")],
    }


def evaluate_dow(edge, dow_trans, btc_raw):
    ts = pd.DatetimeIndex(pd.to_datetime(btc_raw["timestamp"], utc=True))
    q = dow_trans.loc[
        (dow_trans["to_state"] == "DEFINITE_REVERSAL")
        & (pd.to_datetime(dow_trans["timestamp"], utc=True) > utc(edge.signal_time))
    ]
    if len(q):
        sig = utc(pd.to_datetime(q.iloc[0]["timestamp"], utc=True))
        k = next_open_index(ts, sig)
        if k is not None:
            t = bar_open_time(ts[k])
            px = float(btc_raw.iloc[k]["open"])
            return {
                "exit_time": t,
                "exit_price": px,
                "exit_reason": "DEFINITE_REVERSAL",
                "fills": [(1.0, t, px, "DEFINITE_REVERSAL")],
            }
    t = utc(ts[-1])
    px = float(btc_raw.iloc[-1]["close"])
    return {
        "exit_time": t,
        "exit_price": px,
        "exit_reason": "END_OF_DATA",
        "fills": [(1.0, t, px, "END_OF_DATA")],
    }


@dataclass
class RankIndex:
    times: list[pd.Timestamp]
    maps: list[dict[str, float]]

    @classmethod
    def build(cls, ranking):
        times = []
        maps = []
        for t, g in ranking.groupby("decision_time", sort=True):
            times.append(utc(t))
            maps.append({str(r["pair"]): float(r["adjusted_rank"]) for _, r in g.iterrows()})
        return cls(times, maps)

    def rank(self, pair, t):
        j = bisect.bisect_right(self.times, utc(t)) - 1
        if j < 0:
            return 1e9
        return float(self.maps[j].get(str(pair), 1e9))


def episode_record(row, outcome, capacity):
    # itertuples() rows are namedtuples; Series rows have to_dict().
    rec = row._asdict() if hasattr(row, "_asdict") else row.to_dict()
    # Candidate entry_time is the timestamp label of the candle whose OPEN is
    # executed. Raw labels are candle close times, so effective execution time
    # is one hour earlier.
    rec["entry_bar_timestamp"] = rec["entry_time"]
    rec["entry_time"] = bar_open_time(rec["entry_time"])
    rec["exit_time"] = outcome["exit_time"]
    rec["exit_price"] = outcome["exit_price"]
    rec["exit_reason"] = outcome["exit_reason"]
    rec["fills_json"] = json.dumps(
        [[float(fr), str(t), float(px), str(reason)] for fr, t, px, reason in outcome["fills"]],
        separators=(",", ":"),
    )
    rec["capacity_notional"] = float(capacity)
    rec["management_trace_json"] = json.dumps(
        outcome.get("management_trace", []), separators=(",", ":")
    )
    return rec


def simulate_portfolio(episodes, rank_index, cost_rt_fraction):
    if episodes.empty:
        return pd.DataFrame(), pd.DataFrame(), {"accepted": 0, "ending_cash": INITIAL_EQUITY}
    ep = episodes.copy()
    ep["entry_time"] = pd.to_datetime(ep["entry_time"], utc=True)
    ep["exit_time"] = pd.to_datetime(ep["exit_time"], utc=True)
    ep["priority_rank"] = [
        rank_index.rank(p, t) for p, t in zip(ep["pair"], ep["signal_time"], strict=False)
    ]
    ep = ep.sort_values(
        ["entry_time", "priority_rank", "pair", "identity"], kind="stable"
    ).reset_index(drop=True)

    cash = INITIAL_EQUITY
    openpos = {}
    accepted = []
    suppress = []
    trade_id = 0
    exit_events = []

    def cycle_root(identity):
        x = str(identity)
        for suffix in ("|SPRING_TEST", "|SPRING_LPS_ADD"):
            if x.endswith(suffix):
                return x[: -len(suffix)]
        return x

    def process_exits(until):
        nonlocal cash, exit_events
        exit_events.sort(key=lambda x: (x[0], x[1]))
        keep = []
        for ev in exit_events:
            t, tid, fr, px, reason = ev
            if t > until:
                keep.append(ev)
                continue
            pos = openpos.get(tid)
            if pos is None:
                continue
            qty = pos["qty"] * fr
            gross = qty * px
            exit_cost = gross * (cost_rt_fraction / 2.0)
            cash += gross - exit_cost
            pos["remaining_fraction"] -= fr
            pos["exit_cost"] += exit_cost
            pos["gross_exit_proceeds"] += gross
            pos["last_exit_time"] = t
            pos["last_exit_reason"] = reason
            if pos["remaining_fraction"] <= 1e-12:
                entry_notional = pos["entry_notional"]
                gross_pnl = pos["gross_exit_proceeds"] - entry_notional
                total_cost = pos["entry_cost"] + pos["exit_cost"]
                accepted.append(
                    {
                        **pos["episode"],
                        "trade_id": tid,
                        "notional": entry_notional,
                        "quantity": pos["qty"],
                        "entry_cost": pos["entry_cost"],
                        "exit_cost": pos["exit_cost"],
                        "gross_pnl": gross_pnl,
                        "costs": total_cost,
                        "net_pnl": gross_pnl - total_cost,
                        "portfolio_exit_time": pos["last_exit_time"],
                        "portfolio_exit_reason": pos["last_exit_reason"],
                    }
                )
                del openpos[tid]
        exit_events = keep

    for r in ep.itertuples(index=False):
        process_exits(utc(r.entry_time))
        active_same = [p for p in openpos.values() if p["episode"]["pair"] == r.pair]
        is_add = str(r.action) == "ADD_50"
        if is_add:
            root = cycle_root(r.identity)
            parent = [
                p
                for p in active_same
                if str(p["episode"].get("action")) == "ENTER_50"
                and cycle_root(p["episode"].get("identity")) == root
            ]
            duplicate_add = [
                p
                for p in active_same
                if str(p["episode"].get("action")) == "ADD_50"
                and cycle_root(p["episode"].get("identity")) == root
            ]
            if not parent:
                suppress.append(
                    {
                        "system_id": r.system_id,
                        "pair": r.pair,
                        "entry_time": r.entry_time,
                        "identity": r.identity,
                        "reason": "ADD_PARENT_NOT_ACTIVE",
                    }
                )
                continue
            if duplicate_add:
                suppress.append(
                    {
                        "system_id": r.system_id,
                        "pair": r.pair,
                        "entry_time": r.entry_time,
                        "identity": r.identity,
                        "reason": "DUPLICATE_ADD",
                    }
                )
                continue
        elif active_same:
            suppress.append(
                {
                    "system_id": r.system_id,
                    "pair": r.pair,
                    "entry_time": r.entry_time,
                    "identity": r.identity,
                    "reason": "OVERLAP_SUPPRESSED",
                }
            )
            continue

        active_pairs = {p["episode"]["pair"] for p in openpos.values()}
        if (r.pair not in active_pairs) and len(active_pairs) >= MAX_POSITIONS:
            suppress.append(
                {
                    "system_id": r.system_id,
                    "pair": r.pair,
                    "entry_time": r.entry_time,
                    "identity": r.identity,
                    "reason": "MAX_POSITIONS",
                }
            )
            continue

        gross_open = sum(p["entry_notional"] * p["remaining_fraction"] for p in openpos.values())
        pair_open = sum(p["entry_notional"] * p["remaining_fraction"] for p in active_same)
        target = size_notional(r, INITIAL_EQUITY, r.capacity_notional)
        gross_room = INITIAL_EQUITY * MAX_GROSS_EXPOSURE_FRACTION - gross_open
        pair_room = INITIAL_EQUITY * EQUAL_SLOT_FRACTION - pair_open
        target = min(target, max(0.0, gross_room), max(0.0, pair_room))
        entry_cost_rate = cost_rt_fraction / 2.0
        target = min(target, cash / (1.0 + entry_cost_rate))
        if target <= 0:
            suppress.append(
                {
                    "system_id": r.system_id,
                    "pair": r.pair,
                    "entry_time": r.entry_time,
                    "identity": r.identity,
                    "reason": "NO_CAPACITY_OR_CASH",
                }
            )
            continue

        qty = target / float(r.entry_open)
        entry_cost = target * entry_cost_rate
        cash -= target + entry_cost
        trade_id += 1
        fills = json.loads(r.fills_json)
        for fr, t, px, reason in fills:
            exit_events.append((utc(pd.Timestamp(t)), trade_id, float(fr), float(px), str(reason)))
        openpos[trade_id] = {
            "episode": r._asdict(),
            "qty": qty,
            "entry_notional": target,
            "entry_cost": entry_cost,
            "exit_cost": 0.0,
            "gross_exit_proceeds": 0.0,
            "remaining_fraction": 1.0,
            "last_exit_time": None,
            "last_exit_reason": None,
        }

    process_exits(pd.Timestamp("2100-01-01", tz="UTC"))
    if openpos:
        raise RuntimeError("PORTFOLIO_OPEN_POSITIONS_AFTER_FINAL_FLUSH")
    return (
        pd.DataFrame(accepted),
        pd.DataFrame(suppress),
        {"accepted": len(accepted), "ending_cash": cash},
    )


def hourly_equity(trades, raw_cache, cost_rt_fraction):
    if trades.empty:
        return pd.DataFrame(columns=["timestamp", "equity"])
    hours = pd.date_range(START, END, freq="h", inclusive="left", tz="UTC")
    n = len(hours)
    cash_delta = np.zeros(n, dtype=float)
    qty_delta = defaultdict(lambda: np.zeros(n, dtype=float))

    def idx(t):
        t = utc(t)
        j = int((t - START) / pd.Timedelta(hours=1))
        return j if 0 <= j < n else None

    for r in trades.itertuples(index=False):
        j = idx(r.entry_time)
        if j is None:
            raise RuntimeError(f"ENTRY_TIME_OUTSIDE_HOURLY_GRID:{r.entry_time}")
        cash_delta[j] -= float(r.notional) + float(r.entry_cost)
        qty_delta[str(r.pair)][j] += float(r.quantity)
        for fr, t, px, _reason in json.loads(r.fills_json):
            k = idx(pd.Timestamp(t))
            if k is None:
                raise RuntimeError(f"EXIT_TIME_OUTSIDE_HOURLY_GRID:{t}")
            q = float(r.quantity) * float(fr)
            gross = q * float(px)
            cost = gross * (cost_rt_fraction / 2.0)
            cash_delta[k] += gross - cost
            qty_delta[str(r.pair)][k] -= q

    cash = INITIAL_EQUITY + np.cumsum(cash_delta)
    equity = cash.copy()

    for pair, deltas in qty_delta.items():
        qty = np.cumsum(deltas)
        if not np.any(np.abs(qty) > 1e-12):
            continue
        raw = raw_cache[pair]
        rts = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], utc=True))
        # Exact hourly boundary mark: candle open belongs to timestamp-1h.
        open_index = rts - pd.Timedelta(hours=1)
        opens = pd.Series(raw["open"].astype(float).to_numpy(), index=open_index)
        closes = pd.Series(raw["close"].astype(float).to_numpy(), index=rts)
        mark = opens.reindex(hours)
        fallback = closes.reindex(hours)
        mark = mark.combine_first(fallback).ffill().fillna(0.0).to_numpy(dtype=float)
        equity += qty * mark

    curve = pd.DataFrame({"timestamp": hours, "equity": equity})
    # All episodes are force-closed no later than the last protected 2023 row.
    expected = INITIAL_EQUITY + float(trades["net_pnl"].sum())
    if abs(float(curve.iloc[-1]["equity"]) - expected) > max(0.01, abs(expected) * 1e-8):
        raise RuntimeError(
            f"HOURLY_EQUITY_RECONCILIATION_FAIL:curve={curve.iloc[-1]['equity']}:expected={expected}"  # noqa: E501 - frozen source literal
        )
    return curve


def metrics(trades, equity_curve):
    if trades.empty:
        return {
            "trades": 0,
            "net_pnl": 0.0,
            "net_return": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "costs": 0.0,
            "gross_pnl": 0.0,
        }
    net = trades["net_pnl"].astype(float)
    pos = float(net[net > 0].sum())
    neg = float(-net[net < 0].sum())
    pf = pos / neg if neg > 0 else math.inf
    eq = equity_curve["equity"].astype(float)
    peak = eq.cummax()
    dd = eq / peak - 1.0
    return {
        "trades": int(len(trades)),
        "gross_pnl": float(trades["gross_pnl"].sum()),
        "costs": float(trades["costs"].sum()),
        "net_pnl": float(net.sum()),
        "net_return": float(net.sum() / INITIAL_EQUITY),
        "profit_factor": float(pf),
        "max_drawdown": float(-dd.min()) if len(dd) else 0.0,
        "ending_equity": float(equity_curve.iloc[-1]["equity"])
        if len(equity_curve)
        else INITIAL_EQUITY,
        "positive_share": float((net > 0).mean()),
        "turnover_notional": float(trades["notional"].sum()),
    }


def robustness(trades):
    if trades.empty:
        return {}
    q = trades.copy()
    q["entry_time"] = pd.to_datetime(q["entry_time"], utc=True)
    q["year"] = q["entry_time"].dt.year
    q["month"] = q["entry_time"].dt.to_period("M").astype(str)
    base = float(q["net_pnl"].sum())
    largest = float(q["net_pnl"].max())
    assets = {a: float(base - g["net_pnl"].sum()) for a, g in q.groupby("pair")}
    years = {int(y): float(base - g["net_pnl"].sum()) for y, g in q.groupby("year")}
    months = {m: float(g["net_pnl"].sum()) for m, g in q.groupby("month")}
    positive = q.loc[q["net_pnl"] > 0, "net_pnl"]
    pos_total = float(positive.sum())
    top_asset = q.groupby("pair")["net_pnl"].sum().sort_values(ascending=False)
    return {
        "largest_winner_removed_net_pnl": float(base - largest),
        "loao_min_remaining_net_pnl": float(min(assets.values())) if assets else base,
        "loyo_min_remaining_net_pnl": float(min(years.values())) if years else base,
        "year_net_pnl": {str(y): float(g["net_pnl"].sum()) for y, g in q.groupby("year")},
        "top_asset_net_pnl": float(top_asset.iloc[0]) if len(top_asset) else 0.0,
        "top_asset": str(top_asset.index[0]) if len(top_asset) else None,
        "top_asset_positive_contribution_share": float(max(0.0, top_asset.iloc[0]) / pos_total)
        if pos_total > 0 and len(top_asset)
        else 0.0,
        "month_net_pnl": months,
    }


# =============================================================================
# GATE-1 STAGE-B ENGINE CONTRACT OVERRIDES
# =============================================================================

MAX_TOTAL_OPEN_STOP_RISK_FRACTION = 0.025
MAX_ASSET_MTM_FRACTION = 0.18


class Gate1ContractError(RuntimeError):
    pass


def _row_get(row, name, default=None):
    if hasattr(row, name):
        return getattr(row, name)
    if isinstance(row, dict):
        return row.get(name, default)
    try:
        return row[name]
    except (KeyError, IndexError):
        return default


def _campaign_root(row):
    x = str(_row_get(row, "identity", ""))
    for suffix in ("|SPRING_TEST", "|SPRING_LPS_ADD"):
        if x.endswith(suffix):
            return x[: -len(suffix)]
    return x


class CausalOpenMarkIndex:
    """Exact-hour OPEN marks only. Missing bars fail closed; no forward fill."""

    def __init__(self, loader):
        self.loader = loader
        self._maps = {}

    def _load(self, pair):
        raw = self.loader(str(pair))
        ts = pd.to_datetime(raw["timestamp"], utc=True)
        self._maps[str(pair)] = {
            bar_open_time(t): float(px)
            for t, px in zip(ts, raw["open"].astype(float), strict=False)
        }

    def mark(self, pair, t):
        pair = str(pair)
        if pair not in self._maps:
            self._load(pair)
        return self._maps[pair].get(utc(t))


def entry_risk_per_unit(entry, stop, entry_cost_rate, exit_cost_rate):
    entry = float(entry)
    stop = float(stop)
    if not (math.isfinite(entry) and math.isfinite(stop)) or not 0 < stop < entry:
        return math.inf
    return entry * (1.0 + entry_cost_rate) - stop * (1.0 - exit_cost_rate)


def size_notional(
    row, equity_for_limits, capacity, cost_rt_fraction=0.0, risk_budget_override=None
):
    equity_for_limits = float(equity_for_limits)
    capacity = float(capacity)
    if (
        not math.isfinite(equity_for_limits)
        or not math.isfinite(capacity)
        or equity_for_limits <= 0
        or capacity <= 0
    ):
        return 0.0
    entry = float(_row_get(row, "entry_open", math.nan))
    stop = float(_row_get(row, "stop", math.nan))
    if not (math.isfinite(entry) and math.isfinite(stop)) or not 0 < stop < entry:
        return 0.0
    fraction = 0.5 if str(_row_get(row, "action", "")) in {"ENTER_50", "ADD_50"} else 1.0
    budget = (
        equity_for_limits * FIXED_RISK_FRACTION * fraction
        if risk_budget_override is None
        else float(risk_budget_override)
    )
    per_unit = entry_risk_per_unit(entry, stop, cost_rt_fraction / 2.0, cost_rt_fraction / 2.0)
    if not math.isfinite(per_unit) or per_unit <= 0:
        return 0.0
    qty = budget / per_unit
    return max(0.0, min(qty * entry, equity_for_limits * MAX_ASSET_MTM_FRACTION, capacity))


def current_mtm_state(cash, positions, mark_provider, t, exit_cost_rate):
    marks = {}
    missing = []
    for tid, p in positions.items():
        if (
            not math.isfinite(p["qty_current"])
            or p["qty_current"] < 0
            or not math.isfinite(p["current_stop"])
            or p["current_stop"] <= 0
        ):
            return {"valid": False, "missing": ["INVALID_QUANTITY_OR_STOP"]}
        if p["qty_current"] <= 1e-12:
            continue
        m = mark_provider(p["episode"]["pair"], t)
        if m is None or not math.isfinite(float(m)) or float(m) <= 0:
            missing.append(str(p["episode"]["pair"]))
        else:
            marks[tid] = float(m)
    if missing:
        return {"valid": False, "missing": sorted(set(missing))}
    gross = sum(p["qty_current"] * marks[tid] for tid, p in positions.items() if tid in marks)
    eq = float(cash + gross)
    asset = defaultdict(float)
    open_stop = 0.0
    for tid, p in positions.items():
        if tid not in marks:
            continue
        mv = p["qty_current"] * marks[tid]
        asset[str(p["episode"]["pair"])] += mv
        open_stop += max(
            0.0, mv - p["qty_current"] * float(p["current_stop"]) * (1.0 - exit_cost_rate)
        )
    return {
        "valid": True,
        "equity": eq,
        "gross": gross,
        "asset": dict(asset),
        "open_stop_risk": open_stop,
        "marks": marks,
    }


def current_mtm_limits_ok(state):
    if not state.get("valid") or state["equity"] <= 0:
        return False
    e = state["equity"]
    return (
        len([v for v in state["asset"].values() if v > 0]) <= MAX_POSITIONS
        and state["gross"] <= e * MAX_GROSS_EXPOSURE_FRACTION + 1e-9
        and state["open_stop_risk"] <= e * MAX_TOTAL_OPEN_STOP_RISK_FRACTION + 1e-9
        and all(v <= e * MAX_ASSET_MTM_FRACTION + 1e-9 for v in state["asset"].values())
    )


def proportional_risk_reduction_lambda(cash, positions, mark_provider, t, exit_cost_rate):
    state = current_mtm_state(cash, positions, mark_provider, t, exit_cost_rate)
    if not state["valid"]:
        return None, state
    if current_mtm_limits_ok(state):
        return 1.0, state
    marks = state["marks"]

    def projected(lam):
        gross_sale = sum(
            (1.0 - lam) * p["qty_current"] * marks[tid] for tid, p in positions.items()
        )
        c = cash + gross_sale * (1.0 - exit_cost_rate)
        gross = sum(lam * p["qty_current"] * marks[tid] for tid, p in positions.items())
        eq = c + gross
        asset = defaultdict(float)
        risk = 0.0
        for tid, p in positions.items():
            q = lam * p["qty_current"]
            mv = q * marks[tid]
            asset[str(p["episode"]["pair"])] += mv
            risk += max(0.0, mv - q * float(p["current_stop"]) * (1.0 - exit_cost_rate))
        return {
            "valid": True,
            "equity": eq,
            "gross": gross,
            "asset": dict(asset),
            "open_stop_risk": risk,
        }

    if not current_mtm_limits_ok(projected(0.0)):
        return None, state
    if len([v for v in state["asset"].values() if v > 0]) > MAX_POSITIONS:
        return 0.0, state
    lo, hi = 0.0, 1.0
    for _ in range(64):
        mid = (lo + hi) / 2.0
        if current_mtm_limits_ok(projected(mid)):
            lo = mid
        else:
            hi = mid
    return lo, state


# The old fixed-initial-equity simulator is quarantined.
del simulate_portfolio  # No public legacy simulator escape hatch.


def simulate_portfolio(*args, mark_provider=None, quantity_normalizer=None, **kwargs):
    if mark_provider is None:
        raise Gate1ContractError("CURRENT_MTM_MARK_PROVIDER_REQUIRED")
    if quantity_normalizer is None:
        raise Gate1ContractError("CANONICAL_QUANTITY_NORMALIZER_REQUIRED")
    raise Gate1ContractError(
        "GATE1_STAGE_B_CONTRACT_BOUND_BUT_FULL_EVENT_DRIVEN_PORTFOLIO_EXECUTION_NOT_YET_AUTHORIZED;"
        "USE_GATE3_RUNNER_ONLY_AFTER_GATE2_AND_EXECUTION_ADAPTER_FREEZE"
    )
