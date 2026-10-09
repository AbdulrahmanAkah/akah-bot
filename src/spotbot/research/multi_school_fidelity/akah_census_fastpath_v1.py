"""Research-only integrated authority; not production. See source provenance manifest."""

from __future__ import annotations

import bisect
import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

_INDICATOR_CACHE = {}
_PIVOT_CACHE = {}
_CONFIRM_CACHE = {}
_ASOF_CACHE = {}


def cached_add_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    key = id(frame)
    hit = _INDICATOR_CACHE.get(key)
    if hit is not None and hit[0] is frame:
        return hit[1]
    x = frame.copy().sort_values("timestamp", kind="stable").reset_index(drop=True)
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="raise")
    pc = x["close"].shift(1)
    x["true_range"] = pd.concat(
        [x["high"] - x["low"], (x["high"] - pc).abs(), (x["low"] - pc).abs()], axis=1
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
    _INDICATOR_CACHE[key] = (frame, x)
    return x


def vectorized_pivots_factory(rt):
    Pivot = rt.Pivot
    utc = rt.utc

    def fn(frame: pd.DataFrame, left: int = 2, right: int = 2):
        key = (id(frame), left, right)
        hit = _PIVOT_CACHE.get(key)
        if hit is not None and hit[0] is frame:
            return hit[1]
        x = frame.reset_index(drop=True)
        n = len(x)
        out = []
        if n >= left + right + 1:
            hi = x["high"].astype(float).to_numpy()
            lo = x["low"].astype(float).to_numpy()
            ts = pd.to_datetime(x["timestamp"], utc=True)
            vol = x["volume"].astype(float).to_numpy() if "volume" in x else np.full(n, np.nan)
            tr = (
                x["true_range"].astype(float).to_numpy()
                if "true_range" in x
                else np.full(n, np.nan)
            )
            for i in range(left, n - right):
                hs = hi[i - left : i + right + 1]
                ls = lo[i - left : i + right + 1]
                h = hi[i]
                l = lo[i]  # noqa: E741 - retained geometric notation
                if h == float(np.max(hs)) and int(np.count_nonzero(hs == h)) == 1:
                    out.append(
                        Pivot(
                            "H",
                            i,
                            float(h),
                            utc(ts.iloc[i]),
                            utc(ts.iloc[i + right]),
                            float(vol[i]),
                            float(tr[i]),
                        )
                    )
                if l == float(np.min(ls)) and int(np.count_nonzero(ls == l)) == 1:  # noqa: E741 - retained geometric notation
                    out.append(
                        Pivot(
                            "L",
                            i,
                            float(l),
                            utc(ts.iloc[i]),
                            utc(ts.iloc[i + right]),
                            float(vol[i]),
                            float(tr[i]),
                        )
                    )
            out = sorted(out, key=lambda p: (p.confirm_time, p.index, p.kind))
        _PIVOT_CACHE[key] = (frame, out)
        return out

    return fn


def fast_available_factory(rt):
    utc = rt.utc

    def fn(pivots: Sequence[Any], t: pd.Timestamp):
        key = id(pivots)
        hit = _CONFIRM_CACHE.get(key)
        if hit is None or hit[0] is not pivots:
            times = [utc(p.confirm_time) for p in pivots]
            _CONFIRM_CACHE[key] = (pivots, times)
        else:
            times = hit[1]
        return pivots[: bisect.bisect_right(times, utc(t))]

    return fn


def fast_continuation_factory(rt):
    CP = rt.ClassicalPattern
    utc = rt.utc

    def fn(frame: pd.DataFrame, atr: float):
        n = len(frame)
        if n < 20 or not math.isfinite(atr) or atr <= 0:
            return []
        out = []
        now = utc(frame.iloc[-1]["timestamp"])
        pole_start = float(frame.iloc[-18]["close"])
        pole_end = float(frame.iloc[-8]["close"])
        pole = pole_end - pole_start
        tail = frame.iloc[-8:]
        hi = tail["high"].astype(float).to_numpy()
        lo = tail["low"].astype(float).to_numpy()
        if pole >= 3 * atr:
            hs = float(np.polyfit(np.arange(len(hi)), hi, 1)[0])
            ls = float(np.polyfit(np.arange(len(lo)), lo, 1)[0])
            if hs < 0 and ls < 0 and abs(hs - ls) <= 0.25 * atr:
                out.append(
                    CP(
                        f"FLAG:{n}",
                        "FLAG",
                        float(hi[-1]),
                        float(lo.min()),
                        pole,
                        "UP",
                        now,
                        {"pole": pole},
                    )
                )
            if hi[-1] < hi[0] and lo[-1] > lo[0]:
                out.append(
                    CP(
                        f"PENNANT:{n}",
                        "PENNANT",
                        float(hi[-1]),
                        float(lo[-1]),
                        pole,
                        "UP",
                        now,
                        {"pole": pole},
                    )
                )
        base = frame.iloc[-12:]
        height = float(base["high"].max() - base["low"].min())
        if height <= 4 * atr:
            top = float(base["high"].max())
            bot = float(base["low"].min())
            out.append(CP(f"BASE:{n}", "BASE_BREAKOUT", top, bot, height, "RANGE", now, {}))
        return out

    return fn


def fast_smt_factory(rt):
    utc = rt.utc

    def fn(btc, eth, t, hours: int = 24):
        t = utc(t)

        def lows(df):
            ts = pd.to_datetime(df["timestamp"], utc=True)
            e = int(ts.searchsorted(t, side="right"))
            m = int(ts.searchsorted(t - pd.Timedelta(hours=hours), side="right"))
            s = int(ts.searchsorted(t - pd.Timedelta(hours=2 * hours), side="right"))
            a = df.iloc[m:e]
            b = df.iloc[s:m]
            return (
                (float(a["low"].min()), float(b["low"].min()))
                if len(a) and len(b)
                else (None, None)
            )

        ba, bb = lows(btc)
        ea, eb = lows(eth)
        if None in (ba, bb, ea, eb):
            return False
        return (ba < bb and ea >= eb) or (ea < eb and ba >= bb)

    return fn


def fast_weekly_factory(det):
    utc = det.utc

    def fn(pair, raw, ranking_pair):
        rows = []
        ts = pd.to_datetime(raw["timestamp"], utc=True)
        cl = raw["close"].astype(float).to_numpy()
        for tv in ranking_pair["decision_time"]:
            t = utc(tv)
            t0 = t - pd.Timedelta(hours=72)
            j1 = int(ts.searchsorted(t, side="right")) - 1
            j0 = int(ts.searchsorted(t0, side="right")) - 1
            if j1 < 0 or j0 < 0:
                continue
            p1 = float(cl[j1])
            p0 = float(cl[j0])
            rows.append(
                {"pair": pair, "decision_time": t, "ret72": p1 / p0 - 1 if p0 > 0 else math.nan}
            )
        return rows

    return fn


def fast_asof(df, t, time_col, value_col, default):
    key = (id(df), time_col, value_col)
    hit = _ASOF_CACHE.get(key)
    if hit is None or hit[0] is not df:
        times = pd.DatetimeIndex(pd.to_datetime(df[time_col], utc=True))
        vals = df[value_col].astype(object).to_numpy()
        _ASOF_CACHE[key] = (df, times, vals)
    else:
        times, vals = hit[1], hit[2]
    tt = pd.Timestamp(t)
    tt = tt.tz_localize("UTC") if tt.tzinfo is None else tt.tz_convert("UTC")
    j = int(times.searchsorted(tt, side="right")) - 1
    return default if j < 0 else str(vals[j])


def install(det, rt):
    det.add_indicators = cached_add_indicators
    rt.confirmed_pivots_2l2r = vectorized_pivots_factory(rt)
    rt.available_pivots = fast_available_factory(rt)
    # Preserve Stage-A causal context; legacy fast continuation overwrites it.
    rt.smt_bullish_context = fast_smt_factory(rt)
    rt.matched_swing_relative_strength = fast_matched_swing_rs_factory(rt)
    rt.external_liquidity_map = fast_external_liquidity_factory(rt)
    det.latest_pivots = fast_latest_pivots
    det.weekly_return_rows = fast_weekly_factory(det)
    rt.utc = fast_utc
    det.utc = fast_utc


_TS_CACHE = {}


def clear_pair_caches():
    _INDICATOR_CACHE.clear()
    _PIVOT_CACHE.clear()
    _CONFIRM_CACHE.clear()
    _TS_CACHE.clear()
    # ASOF cache is tiny and global-market only; safe to retain.


def fast_utc(v):
    if isinstance(v, pd.Timestamp):
        if v.tzinfo is None:
            return v.tz_localize("UTC")
        # pandas Timestamp UTC conversion is unnecessary if already UTC.
        if str(v.tzinfo) == "UTC":
            return v
        return v.tz_convert("UTC")
    t = pd.Timestamp(v)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def _ts_values(df):
    k = id(df)
    h = _TS_CACHE.get(k)
    if h is not None and h[0] is df:
        return h[1]
    # Preserve datetime semantics, not dtype-native integer units. Parquet may
    # materialize datetime64[us, UTC]; Timestamp.value is ns. Integer comparison
    # across those two units caused the V1 Wyckoff RS false-negative collapse.
    ts = pd.DatetimeIndex(pd.to_datetime(df["timestamp"], utc=True))
    _TS_CACHE[k] = (df, ts)
    return ts


def fast_ratio_at(pair_raw, btc_raw, t):
    tt = fast_utc(t)

    def close(df):
        ts = _ts_values(df)
        j = int(ts.searchsorted(tt, side="right")) - 1
        return None if j < 0 else float(df.iloc[j]["close"])

    p = close(pair_raw)
    b = close(btc_raw)
    return None if p is None or b is None or b <= 0 else p / b


def fast_matched_swing_rs_factory(rt):
    def fn(pair_raw, btc_raw, intermediate_pivots, t):
        # Directly select the latest two confirmed pivots without materializing the full prefix.
        key = id(intermediate_pivots)
        hit = _CONFIRM_CACHE.get(key)
        if hit is None or hit[0] is not intermediate_pivots:
            times = [fast_utc(p.confirm_time) for p in intermediate_pivots]
            _CONFIRM_CACHE[key] = (intermediate_pivots, times)
        else:
            times = hit[1]
        j = bisect.bisect_right(times, fast_utc(t))
        if j < 2:
            return {
                "eligible": False,
                "reason": "<2 confirmed intermediate swings",
                "ratio_old": None,
                "ratio_new": None,
            }
        p0, p1 = intermediate_pivots[j - 2], intermediate_pivots[j - 1]
        r0 = fast_ratio_at(pair_raw, btc_raw, p0.pivot_time)
        r1 = fast_ratio_at(pair_raw, btc_raw, p1.pivot_time)
        if r0 is None or r1 is None:
            return {
                "eligible": False,
                "reason": "ratio unavailable",
                "ratio_old": r0,
                "ratio_new": r1,
            }
        return {
            "eligible": bool(r1 > r0),
            "reason": "pair/BTC ratio rising over latest two confirmed intermediate swing timestamps"  # noqa: E501 - frozen source literal
            if r1 > r0
            else "relative strength not rising",
            "ratio_old": r0,
            "ratio_new": r1,
            "old_swing_time": p0.pivot_time,
            "new_swing_time": p1.pivot_time,
        }

    return fn


def fast_external_liquidity_factory(rt):
    def fn(prior, pivots, t):
        key = id(pivots)
        hit = _CONFIRM_CACHE.get(key)
        if hit is None or hit[0] is not pivots:
            times = [fast_utc(p.confirm_time) for p in pivots]
            _CONFIRM_CACHE[key] = (pivots, times)
        else:
            times = hit[1]
        j = bisect.bisect_right(times, fast_utc(t))
        highs = []
        lows = []
        k = j - 1
        while k >= 0 and (len(highs) < 4 or len(lows) < 4):
            p = pivots[k]
            if p.kind == "H" and len(highs) < 4:
                highs.append(float(p.price))
            elif p.kind == "L" and len(lows) < 4:
                lows.append(float(p.price))
            k -= 1
        highs.reverse()
        lows.reverse()
        buy = [x for x in [prior.get("prior_high"), *highs] if x is not None]
        sell = [x for x in [prior.get("prior_low"), *lows] if x is not None]
        return {
            "buy_side": sorted(set(map(float, buy))),
            "sell_side": sorted(set(map(float, sell))),
        }

    return fn


def fast_latest_pivots(pivots, t, n=20):
    key = id(pivots)
    hit = _CONFIRM_CACHE.get(key)
    if hit is None or hit[0] is not pivots:
        times = [fast_utc(p.confirm_time) for p in pivots]
        _CONFIRM_CACHE[key] = (pivots, times)
    else:
        times = hit[1]
    j = bisect.bisect_right(times, fast_utc(t))
    return pivots[max(0, j - n) : j]
