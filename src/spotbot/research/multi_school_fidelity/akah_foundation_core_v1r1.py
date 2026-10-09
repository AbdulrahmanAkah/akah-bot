"""Research-only integrated authority; not production. See source provenance manifest."""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

DATA_START = pd.Timestamp("2022-01-01T00:00:00Z")
DATA_CUTOFF = pd.Timestamp("2024-01-01T00:00:00Z")
WARMUP_START = pd.Timestamp("2021-09-01T00:00:00Z")


class FoundationError(RuntimeError):
    pass


def utc(v: Any) -> pd.Timestamp:
    t = pd.Timestamp(v)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def load_broad_eligibility(repo: Path) -> pd.DataFrame:
    path = repo / "data/research/rd18_p2u2/weekly-e10-ranking.csv"
    if not path.is_file():
        raise FoundationError(f"broad E10 ranking missing: {path}")
    # Membership metadata only: do not load liquidity/outcome columns.
    x = pd.read_csv(path, usecols=["decision_time", "pair", "eligible", "adjusted_rank"])
    x["decision_time"] = pd.to_datetime(x["decision_time"], utc=True, errors="raise")
    if "eligible" not in x.columns or "pair" not in x.columns:
        raise FoundationError("ranking missing eligible/pair")
    x = x.loc[(x["decision_time"] < DATA_CUTOFF) & x["eligible"].astype(bool)].copy()
    if x.empty:
        raise FoundationError("broad eligibility is empty")
    return x.sort_values(["decision_time", "adjusted_rank", "pair"], kind="stable").reset_index(
        drop=True
    )


@dataclass
class BroadEligibilityIndex:
    times: list[pd.Timestamp]
    sets: list[frozenset[str]]

    @classmethod
    def build(cls, ranking: pd.DataFrame) -> BroadEligibilityIndex:
        times = []
        sets = []
        for t, g in ranking.groupby("decision_time", sort=True):
            times.append(utc(t))
            sets.append(frozenset(g["pair"].astype(str)))
        return cls(times, sets)

    def members_at(self, t: pd.Timestamp) -> frozenset[str]:
        t = utc(t)
        j = bisect.bisect_right(self.times, t) - 1
        return self.sets[j] if j >= 0 else frozenset()

    def eligible(self, pair: str, t: pd.Timestamp) -> bool:
        return str(pair) in self.members_at(t)


def raw_frame(
    repo: Path, pair: str, start: pd.Timestamp = WARMUP_START, cutoff: pd.Timestamp = DATA_CUTOFF
) -> pd.DataFrame:
    start, cutoff = utc(start), utc(cutoff)
    if not WARMUP_START <= start < cutoff <= DATA_CUTOFF:
        raise FoundationError("READER_WINDOW_NOT_AUTHORIZED")
    path = repo / "data/raw/rd16b/kucoin" / pair / "1h.parquet"
    if not path.is_file():
        raise FoundationError(f"raw source missing: {path}")
    x = pd.read_parquet(
        path,
        engine="pyarrow",
        columns=["timestamp", "open", "high", "low", "close", "volume"],
        filters=[
            ("timestamp", ">=", utc(start).to_pydatetime()),
            ("timestamp", "<", utc(cutoff).to_pydatetime()),
        ],
    )
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="raise")
    x = x.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if x["timestamp"].duplicated().any():
        raise FoundationError("DUPLICATE_RAW_TIMESTAMP")
    if len(x) and (x["timestamp"].max() >= cutoff or x["timestamp"].min() < start):
        raise FoundationError("protected 2024 row entered raw memory")
    return x


def canonical_aggregate(
    repo: Path, pair: str, hourly: pd.DataFrame, timeframe: str
) -> pd.DataFrame:
    from spotbot.data.aggregation import aggregate_completed_ohlcv

    result = aggregate_completed_ohlcv(
        hourly,
        symbol=pair,
        source_timeframe="1h",
        target_timeframe=timeframe,
        cutoff=DATA_CUTOFF,
    )
    x = result.frame.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True, errors="raise")
    if len(x) and x["timestamp"].max() >= DATA_CUTOFF:
        raise FoundationError("canonical aggregation crossed protected cutoff")
    return x


def close_at_or_before(frame: pd.DataFrame, t: pd.Timestamp) -> float | None:
    """
    Unit-safe timestamp lookup.

    Do NOT convert datetime to bare int64 and compare with Timestamp.value:
    parquet/pandas may preserve datetime64[us] while Timestamp.value is ns.
    Series.searchsorted compares timestamp values with unit conversion handled
    by pandas and is therefore safe across ns/us datetime backing units.
    """
    if frame.empty:
        return None
    s = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    t = utc(t)
    j = int(s.searchsorted(t, side="right")) - 1
    if j < 0:
        return None
    v = frame.iloc[j]["close"]
    return None if pd.isna(v) else float(v)


def raw_relative_strength(
    pair_raw: pd.DataFrame, btc_raw: pd.DataFrame, t: pd.Timestamp, hours: int = 72
) -> float | None:
    t = utc(t)
    t0 = t - pd.Timedelta(hours=hours)
    p1 = close_at_or_before(pair_raw, t)
    p0 = close_at_or_before(pair_raw, t0)
    b1 = close_at_or_before(btc_raw, t)
    b0 = close_at_or_before(btc_raw, t0)
    if None in (p1, p0, b1, b0) or p0 <= 0 or b0 <= 0 or b1 <= 0:
        return None
    return (p1 / p0) / (b1 / b0) - 1.0


WYCKOFF_PHASE_A_MAX_AGE = pd.Timedelta(days=90)


def wyckoff_a_reset_reason(
    *,
    now: pd.Timestamp,
    sc_time: pd.Timestamp,
    sc_low: float,
    close: float,
    atr: float,
    stronger_new_sc: bool,
    confirmed_up_break: bool,
) -> str | None:
    now = utc(now)
    sc_time = utc(sc_time)
    if math.isfinite(atr) and atr > 0 and close < sc_low - atr:
        return "SC_STRUCTURALLY_FAILED"
    if stronger_new_sc:
        return "RESEED_NEW_SC"
    if confirmed_up_break:
        return "STOPPING_RESOLVED_WITHOUT_CANONICAL_ST"
    if now - sc_time > WYCKOFF_PHASE_A_MAX_AGE:
        return "PHASE_A_SAFETY_EXPIRY_90D"
    return None


def ny_session_end_utc(t: pd.Timestamp) -> pd.Timestamp:
    local = utc(t).tz_convert("America/New_York")
    end = pd.Timestamp(
        year=local.year, month=local.month, day=local.day, hour=16, tz="America/New_York"
    )
    return end.tz_convert("UTC")


def ict_pending_expired(raid_time: pd.Timestamp, now: pd.Timestamp) -> bool:
    return utc(now) >= ny_session_end_utc(raid_time)


@dataclass
class CountIdentityRegistry:
    seen: set[str]

    @classmethod
    def empty(cls) -> CountIdentityRegistry:
        return cls(set())

    def admit_once(self, pair: str, count_id: str) -> bool:
        key = f"{pair}|{count_id}"
        if key in self.seen:
            return False
        self.seen.add(key)
        return True
