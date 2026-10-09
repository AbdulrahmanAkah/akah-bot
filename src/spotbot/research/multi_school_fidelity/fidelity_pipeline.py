"""Fail-fast, non-economic school census and blind-sampling primitives."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from . import akah_full_fidelity_runtime_v1 as rt
from . import akah_replay_ready_detectors_v1 as det
from .akah_foundation_core_v1r1 import (
    DATA_CUTOFF,
    DATA_START,
    BroadEligibilityIndex,
    canonical_aggregate,
    load_broad_eligibility,
    raw_frame,
    utc,
)

SYSTEMS = (
    "FS_WYCKOFF_FULL_LONG",
    "FS_ICT_2022_CORE_CRYPTO_LONG",
    "FS_HARMONIC_FULL_LONG",
    "FS_CLASSICAL_FULL_LONG",
    "FS_ELLIOTT_FULL_LONG",
    "FS_DOW_CRYPTO_ADAPTED_LONG",
)
SEED = "AKAH_GATE2_V1"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def cache_key(source_sha: str, config_sha: str, bounded_input_sha: str) -> str:
    return digest([source_sha, config_sha, bounded_input_sha])


def eligibility_adapter(repo: Path) -> tuple[BroadEligibilityIndex, dict]:
    ranking = load_broad_eligibility(repo)
    index = BroadEligibilityIndex.build(ranking)
    proof = {
        "loader_type": type(ranking).__name__,
        "loader_eligible_type": type(ranking.eligible).__name__,
        "loader_eligible_callable": callable(ranking.eligible),
        "adapter_type": type(index).__name__,
        "adapter_eligible_type": type(index.eligible).__name__,
        "adapter_eligible_callable": callable(index.eligible),
        "api": "BroadEligibilityIndex.build(load_broad_eligibility(repo))",
    }
    if not callable(index.eligible):
        raise TypeError("ELIGIBILITY_API_NOT_CALLABLE")
    return index, proof


class FrameCache:
    """Only predicate-bounded frames enter this cache; no full-file market hashing."""

    def __init__(self, repo: Path):
        self.repo = repo
        self.frames: dict[str, tuple] = {}
        self.audit: dict[str, dict] = {}

    def get(self, pair: str):
        if pair not in self.frames:
            raw = raw_frame(self.repo, pair)
            if raw.empty:
                raise ValueError(f"EMPTY_AUTHORIZED_RAW:{pair}")
            h4 = canonical_aggregate(self.repo, pair, raw, "4h")
            d1 = canonical_aggregate(self.repo, pair, raw, "1d")
            for frame in (raw, h4, d1):
                if frame.empty or frame.timestamp.max() >= DATA_CUTOFF:
                    raise ValueError(f"FRAME_BOUNDARY_OR_EMPTY:{pair}")
            # Hash only the already-bounded rows, never the mixed physical file.
            sha = hashlib.sha256(
                pd.util.hash_pandas_object(raw, index=False).values.tobytes()
            ).hexdigest()
            key = cache_key(source_hash(Path(__file__)), digest(["canonical", "4h", "1d"]), sha)
            self.audit[pair] = {
                "rows": len(raw),
                "min": str(raw.timestamp.min()),
                "max": str(raw.timestamp.max()),
                "bounded_input_sha256": sha,
                "cache_key": key,
                "protected_rows_loaded": 0,
            }
            self.frames[pair] = raw, h4, d1
        return self.frames[pair]


def scan_dow_context(census: pd.DataFrame, eligibility: BroadEligibilityIndex):
    """Replay the frozen *non-economic* Dow context input, not old signal seeds."""
    runtime = rt.DowRuntime()
    transitions, events, intents = [], [], []
    for row in census.itertuples(index=False):
        t = utc(row.decision_time)
        if t >= DATA_CUTOFF:
            raise ValueError("DOW_CONTEXT_PROTECTED_BOUNDARY")
        before = runtime.state
        after = runtime.update(
            str(row.btc_primary_trend),
            str(row.secondary_trend),
            {"confirmed": bool(row.confirmed)},
            bool(row.volume_confirms),
        )
        if before == after:
            continue
        eligible = eligibility.eligible("BTC-USDT", t)
        r = det.event_row(
            SYSTEMS[-1],
            "BTC-USDT",
            t,
            after,
            "CONTEXT",
            eligible,
            {
                "primary": row.btc_primary_trend,
                "secondary": row.secondary_trend,
                "breadth": row.breadth,
                "funded_ready": False,
                "reason": "DOW_PROTECTIVE_STOP_UNRESOLVED",
            },
        )
        transitions.append({**r, "from_state": before, "to_state": after})
        events.append(r)
        if after == "RECONFIRMED_BULL":
            intents.append(r)
    return {
        "transitions": transitions,
        "events": events,
        "intents": intents,
        "summary": {"funded_ready": False, "scope": "BTC_MARKET_CONTEXT_ONLY"},
    }


def scan_pair(pair, frames, btc, eth, eligibility, market_transitions, dow):
    if not isinstance(eligibility, BroadEligibilityIndex):
        raise TypeError("EXPECTED_BROAD_ELIGIBILITY_INDEX")
    raw, h4, d1 = frames
    calls = (
        (
            SYSTEMS[0],
            det.scan_wyckoff,
            (pair, h4, raw, btc, eligibility, market_transitions, False),
        ),
        (SYSTEMS[1], det.scan_ict, (pair, raw, h4, d1, btc, eth, eligibility)),
        (SYSTEMS[2], det.scan_harmonic, (pair, h4, eligibility)),
        (SYSTEMS[3], det.scan_classical, (pair, h4, eligibility)),
        (SYSTEMS[4], det.scan_elliott, (pair, raw, h4, d1, eligibility)),
    )
    result = {}
    for sid, function, args in calls:
        print(f"DETECTOR_START={pair}:{sid}", flush=True)
        # Deliberately no exception handler. The outer CLI preserves the traceback.
        tr, ev, it, summary = function(*args)
        result[sid] = {"transitions": tr, "events": ev, "intents": it, "summary": summary}
        print(f"DETECTOR_DONE={pair}:{sid}:{len(tr)}:{len(ev)}:{len(it)}:errors=0", flush=True)
    result[SYSTEMS[-1]] = (
        dow
        if pair == "BTC-USDT"
        else {
            "transitions": [],
            "events": [],
            "intents": [],
            "summary": {"scope": "NOT_APPLICABLE_ASSET_DOW_IS_BTC_CONTEXT"},
        }
    )
    return result


def week_key(row: dict):
    t = utc(row["time"])
    week = t.isocalendar()
    return row["system_id"], row["pair"], int(week.year), int(week.week)


def sampling_key(row: dict):
    return digest(
        [
            SEED,
            row["system_id"],
            row["pair"],
            str(row["time"]),
            row["kind"],
            digest(row.get("engine_row")),
        ]
    )


def select_cases(pools: dict, *, reserve: bool = False):
    """Global school/pair/week exclusion across all categories, including reserve."""
    chosen, audit, used = [], [], set()
    for sid in SYSTEMS:
        for year in (2022, 2023):
            counts = {}
            for kind, quota in (("POSITIVE", 5), ("INTERMEDIATE", 2), ("NO_INTENT", 3)):
                candidates = sorted(pools.get((sid, year, kind), []), key=sampling_key)
                picked = []
                for r in candidates:
                    if week_key(r) in used:
                        continue
                    used.add(week_key(r))
                    picked.append(r)
                    if len(picked) == quota * (2 if reserve else 1):
                        break
                primary, spare = picked[:quota], picked[quota:]
                chosen.extend({**r, "reserve": False} for r in primary)
                chosen.extend({**r, "reserve": True} for r in spare)
                counts[kind] = {
                    "available": len(candidates),
                    "selected": len(primary),
                    "reserve": len(spare),
                    "shortage": quota - len(primary),
                }
            audit.append({"system_id": sid, "year": year, "categories": counts})
    chosen.sort(key=sampling_key)
    return chosen, audit


def append_pools(pools, pair, frames, result, eligibility):
    raw = frames[0]
    for sid, data in result.items():
        if sid == SYSTEMS[-1] and pair != "BTC-USDT":
            continue
        intent_times = {utc(r["timestamp"]) for r in data["intents"]}
        for kind, rows in (("POSITIVE", data["intents"]), ("INTERMEDIATE", data["events"])):
            for r in rows:
                t = utc(r["timestamp"])
                if kind == "INTERMEDIATE" and t in intent_times:
                    continue
                if DATA_START <= t < DATA_CUTOFF and bool(r["broad_eligible"]):
                    pools.setdefault((sid, t.year, kind), []).append(
                        {"system_id": sid, "pair": pair, "time": t, "kind": kind, "engine_row": r}
                    )
        # Every legal checkpoint participates, not fixed attractive calendar fractions.
        for t in raw.timestamp:
            t = utc(t)
            if (
                DATA_START <= t < DATA_CUTOFF
                and t not in intent_times
                and eligibility.eligible(pair, t)
            ):
                pools.setdefault((sid, t.year, "NO_INTENT"), []).append(
                    {
                        "system_id": sid,
                        "pair": pair,
                        "time": t,
                        "kind": "NO_INTENT",
                        "engine_row": None,
                    }
                )


def next_open_intent_valid(ready_at, effective_open):
    # Close-labelled next candle opens at the just-completed close. Missing next bar expires.
    return utc(ready_at) == utc(effective_open) and utc(effective_open) < DATA_CUTOFF
