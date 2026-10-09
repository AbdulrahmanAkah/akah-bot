"""Bounded OHLCV -> exact completed-prefix graph, never old event-row repair.

This feed establishes numerical lineage only. It cannot certify a range phase,
wave subdivision or school's discretionary claims merely by hashing bars.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from ..akah_foundation_core_v1r1 import DATA_CUTOFF, raw_frame, utc
from ..integration_v11.contracts import PitMembership
from ..integration_v9.sources import CompletedPrefix, aggregate_completed
from ..school_contract_common_v8 import clock, digest
from ..structural_lifecycle_v6 import CompletedBar, ContractError, instant
from .fast_prefix import FastCompletedPrefix


@dataclass(frozen=True)
class MembershipSnapshot:
    available_at: object
    effective_until: object
    members: frozenset[str]
    source_sha256: str


class MembershipSource:
    def __init__(self, snapshots):
        self.snapshots = tuple(snapshots)
        self.times = tuple(clock(s.available_at) for s in self.snapshots)
        if not self.snapshots or any(b <= a for a, b in zip(self.times, self.times[1:])):
            raise ContractError("ORDERED_NONEMPTY_PIT_SNAPSHOTS_REQUIRED")
        for s in self.snapshots:
            if instant(s.effective_until) <= clock(s.available_at):
                raise ContractError("POSITIVE_PIT_SNAPSHOT_INTERVAL_REQUIRED")
            if not isinstance(s.members, frozenset) or not s.members:
                raise ContractError("EXPLICIT_PIT_MEMBER_SET_REQUIRED")

    def snapshot(self, now):
        now = clock(now)
        j = bisect_right(self.times, now) - 1
        if j < 0 or now >= instant(self.snapshots[j].effective_until):
            raise ContractError("PIT_SNAPSHOT_MISSING_OR_STALE")
        return self.snapshots[j]

    def bind(self, prefix, now):
        now = clock(now)
        s = self.snapshot(now)
        available = clock(s.available_at)
        hours = prefix.bars["1H"]
        if not hours or clock(hours[-1].end) != now:
            raise ContractError("CURRENT_COMPLETED_PIT_CHECKPOINT_REQUIRED")
        value = PitMembership(prefix.pair, now, prefix.pair in s.members, available, s.effective_until)
        eid = digest(("V13_PIT", prefix.pair, now, s.source_sha256, sorted(s.members)))
        if eid in prefix.graph.nodes:
            return prefix.graph.require(prefix.graph.nodes[eid].evidence, now)
        return prefix.source_claim(
            eid, value, now, prefix.pair, (prefix.bar_id(hours[-1]),), s.source_sha256
        )


class HistoricalFeed:
    """Contiguous completed hours; incomplete HTF buckets never become evidence."""

    def __init__(self, pair, bounded_input_sha256, graph=None):
        self.prefix = FastCompletedPrefix(pair, bounded_input_sha256, graph)
        self.buckets = {"4H": [], "1D": []}
        self.last_close = None

    def close_hour(self, bar, volume):
        if bar.timeframe != "1H":
            raise ContractError("HISTORICAL_FEED_HOURLY_INPUT_REQUIRED")
        now = clock(bar.end)
        if self.last_close is not None and instant(bar.start) != self.last_close:
            raise ContractError("HISTORICAL_PREFIX_GAP_REQUIRES_NEW_IDENTITY_NOT_FORWARD_FILL")
        fresh = {"1H": self.prefix.on_close(bar, volume, now)}
        self.last_close = now
        for degree, count in (("4H", 4), ("1D", 24)):
            bucket = self.buckets[degree]
            bucket.append((bar, volume))
            if now.timestamp() % (count * 3600):
                continue
            if len(bucket) == count:
                combined = aggregate_completed([b for b, _ in bucket], degree, now)
                fresh[degree] = self.prefix.on_close(combined, sum(v for _, v in bucket), now)
            bucket.clear()
        return fresh


def historical_hours(repo, pair, *, start, cutoff):
    """Use the canonical predicate reader, exposing rows strictly before cutoff.

    Never hash/read the entire physical mixed-year parquet. A bar whose close is
    at the protected boundary is not passed to the pre-2024 decision API.
    """
    frame = raw_frame(repo, pair, start=utc(start), cutoff=utc(cutoff))
    if len(frame) and frame.timestamp.max() >= min(utc(cutoff), DATA_CUTOFF):
        raise ContractError("BOUNDED_SOURCE_READ_FAILED")
    for row in frame.itertuples(index=False):
        # Repository candle authority stores CLOSE timestamps (aggregation.py
        # _target_close_ns / provider.py normalization), not exchange opens.
        end = utc(row.timestamp).to_pydatetime()
        begin = end - timedelta(hours=1)
        if pd.Timestamp(end) >= utc(cutoff) or pd.Timestamp(begin)<utc(start):
            continue
        yield CompletedBar(
            begin, end, "1H", float(row.open), float(row.high), float(row.low), float(row.close)
        ), float(row.volume)


def all_source_gaps(availability):
    """Full-scope readiness, not a filter that drops failing schools quietly."""
    required = {
        "CLASSICAL": ("native_patterns", "sealed_local_stop", "owner_updates"),
        "HARMONIC": ("prefix_projection", "native_confirmation", "execution_receipt_feedback"),
        "ELLIOTT": ("recursive_count_generator", "source_owned_objective", "all_count_invalidation"),
        "WYCKOFF": ("fresh_range_generator", "typed_readiness_generator", "whole_pnf_segments"),
        "ICT": ("native_auction_chain", "exact_fvg", "session_owner_updates"),
        "DOW": ("complete_pit_market_context", "context_router_binding"),
        "H1": ("native_markup_context", "classical_owner_issue", "sealed_live_parent_graph"),
        "H2": ("native_auction_chain", "prior_daily_state", "protected_4h_acceptance"),
        "H3": ("recursive_count_generator", "harmonic_location_issue", "same_checkpoint_parent_seals"),
        "DRIVER": ("chronological_v12_guarded_bridge", "actual_fill_feedback", "actual_closure_feedback"),
    }
    return {
        school: [field for field in fields if availability.get(school, {}).get(field) != "ACTUAL_SOURCE_VERIFIED"]
        for school, fields in required.items()
        if any(availability.get(school, {}).get(field) != "ACTUAL_SOURCE_VERIFIED" for field in fields)
    }
