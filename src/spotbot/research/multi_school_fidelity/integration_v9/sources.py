"""Close-clock adapters for actual V1 detector primitives and owned source graphs.

Input is an already supplied completed prefix, not a path/cache/data loader.
External semantic claims remain identified as supplied producer evidence, not
certified school doctrine. A SHA authenticates lineage, not a claim's truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

from .. import akah_full_fidelity_runtime_v1 as native
from ..school_contract_common_v8 import DEGREES, Known, Point, clock, completed, digest, valid_sha
from ..structural_lifecycle_v6 import ContractError, instant


@dataclass(frozen=True)
class SourceNode:
    evidence: Known
    parents: tuple[str, ...]
    origin: str


class SourceGraph:
    def __init__(self):
        self.nodes: dict[str, SourceNode] = {}
        self.terminated: set[str] = set()

    def register(self, evidence, parents=(), *, origin):
        evidence.validate(evidence.available_at)
        if origin not in {
            "COMPLETED_BAR",
            "CONFIRMED_PIVOT",
            "DETECTOR_GEOMETRY",
            "SUPPLIED_SEMANTIC_PRODUCER",
        }:
            raise ContractError("SOURCE_ORIGIN_REQUIRED")
        if evidence.event_id in self.nodes:
            raise ContractError("SOURCE_ID_IMMUTABLE_NO_RESURRECTION")
        for p in parents:
            if not self.live(p, evidence.available_at):
                raise ContractError("LIVE_SOURCE_PARENT_REQUIRED")
        self.nodes[evidence.event_id] = SourceNode(evidence, tuple(parents), origin)
        return evidence

    def live(self, eid, now):
        now = clock(now)
        if eid not in self.nodes or eid in self.terminated:
            return False
        node = self.nodes[eid]
        try:
            node.evidence.validate(now)
        except ContractError:
            return False
        return all(self.live(p, now) for p in node.parents)

    def require(self, evidence, now):
        if (
            evidence.event_id not in self.nodes
            or self.nodes[evidence.event_id].evidence != evidence
            or not self.live(evidence.event_id, now)
        ):
            raise ContractError("UNBOUND_MUTATED_OR_INVALIDATED_SOURCE")
        return evidence

    def terminate(self, eid):
        if eid not in self.nodes or eid in self.terminated:
            raise ContractError("UNKNOWN_OR_ALREADY_TERMINAL_SOURCE")
        self.terminated.add(eid)


class CompletedPrefix:
    """One asset, independent contiguous streams, no current-bar HLCV inputs."""

    def __init__(self, pair, producer_sha256, graph=None):
        if not pair:
            raise ContractError("ASSET_REQUIRED")
        valid_sha(producer_sha256)
        self.pair, self.sha = pair, producer_sha256
        self.graph = graph if graph is not None else SourceGraph()
        self.bars = {d: [] for d in DEGREES}
        self.volumes = {d: [] for d in DEGREES}
        self.points: dict[str, Point] = {}

    def bar_id(self, bar):
        return digest((self.pair, bar.timeframe, bar.start, bar.end, "BAR"))

    def on_close(self, bar, volume, now):
        import math

        now = clock(now)
        completed(bar, now, bar.timeframe)
        if (
            not isinstance(volume, (int, float))
            or isinstance(volume, bool)
            or not math.isfinite(volume)
            or volume < 0
        ):
            raise ContractError("COMPLETED_VOLUME_REQUIRED")
        bs = self.bars[bar.timeframe]
        if bs and instant(bar.start) != instant(bs[-1].end):
            raise ContractError("PREFIX_REPEAT_OR_COVERAGE_GAP")
        eid = self.bar_id(bar)
        self.graph.register(
            Known(eid, (bar, volume), now, self.sha, self.pair), origin="COMPLETED_BAR"
        )
        bs.append(bar)
        self.volumes[bar.timeframe].append(volume)
        # Native detector over just the five complete bars. Never expose a full
        # future frame to the source's open-stamped pivot algorithm.
        fresh = []
        if len(bs) >= 5:
            frame = pd.DataFrame(
                [
                    {"timestamp": b.start, "high": b.high, "low": b.low, "volume": v}
                    for b, v in zip(bs[-5:], self.volumes[bar.timeframe][-5:], strict=True)
                ]
            )
            for p in native.confirmed_pivots_2l2r(frame):
                observed = instant(p.pivot_time.to_pydatetime()) + DEGREES[bar.timeframe]
                available = instant(p.confirm_time.to_pydatetime()) + DEGREES[bar.timeframe]
                pid = digest((self.pair, bar.timeframe, observed, p.kind, "PIVOT"))
                point = Point(pid, p.kind, p.price, observed, available, bar.timeframe)
                point.validate(now)
                self.graph.register(
                    Known(pid, point, available, self.sha, self.pair),
                    tuple(self.bar_id(b) for b in bs[-5:]),
                    origin="CONFIRMED_PIVOT",
                )
                self.points[pid] = point
                fresh.append(point)
        return tuple(fresh)

    def require_bar(self, bar, now, volume=None):
        eid = self.bar_id(bar)
        if not self.graph.live(eid, now):
            raise ContractError("BAR_NOT_IN_COMPLETED_SOURCE_PREFIX")
        saved, vol = self.graph.nodes[eid].evidence.value
        if saved != bar or volume is not None and vol != volume:
            raise ContractError("SOURCE_BAR_OR_VOLUME_MUTATED")
        return eid

    def require_point(self, point, now):
        point.validate(now)
        if self.points.get(point.event_id) != point or not self.graph.live(point.event_id, now):
            raise ContractError("PIVOT_NOT_FROM_BOUND_COMPLETED_PREFIX")
        return point.event_id

    def fvg(self, structure_id, now):
        now = clock(now)
        bs = self.bars["1H"]
        if len(bs) < 3 or instant(bs[-1].end) != now:
            raise ContractError("CURRENT_THREE_COMPLETED_BARS_REQUIRED")
        rows = [
            pd.Series({"high": b.high, "low": b.low, "open": b.open, "close": b.close})
            for b in bs[-3:]
        ]
        zone = native.bullish_fvg(*rows)
        if zone is None:
            return None
        eid = digest((self.pair, structure_id, now, "FVG"))
        evidence = Known(eid, zone, now, self.sha, structure_id)
        if eid in self.graph.nodes:
            return self.graph.require(evidence, now)
        return self.graph.register(
            evidence, tuple(self.bar_id(b) for b in bs[-3:]), origin="DETECTOR_GEOMETRY"
        )

    def atr(self, degree, structure_id, now, n=20):
        """Inherited native rolling TR mean, minimum ten completed observations."""
        now = clock(now)
        bs = self.bars[degree]
        if n != 20 or len(bs) < 10 or instant(bs[-1].end) != now:
            raise ContractError("NATIVE_ATR20_COMPLETED_WARMUP_REQUIRED")
        tr = []
        for i, b in enumerate(bs):
            prev = bs[i - 1].close if i else b.open
            tr.append(
                max(b.high - b.low, abs(b.high - prev), abs(b.low - prev)) if i else b.high - b.low
            )
        value = sum(tr[-20:]) / len(tr[-20:])
        eid = digest((self.pair, degree, now, "ATR20"))
        evidence = Known(eid, value, now, self.sha, self.pair)
        if eid in self.graph.nodes:
            return self.graph.require(evidence, now)
        return self.graph.register(
            evidence,
            tuple(self.bar_id(b) for b in bs[-21:]),
            origin="DETECTOR_GEOMETRY",
        )

    def source_claim(
        self, event_id, value, at, structure_id, parents, source_sha256, valid_until=None
    ):
        """Bound external producer statement, explicitly NOT inferred doctrine.

        Used for owned range/market/branch/objective facts that OHLC geometry
        alone cannot prove. Missing source-specific certification still blocks
        funded routing. Cannot introduce an unbound or future parent.
        """
        if not parents:
            raise ContractError("SEMANTIC_CLAIM_REQUIRES_SOURCE_PARENTS")
        return self.graph.register(
            Known(event_id, value, clock(at), source_sha256, structure_id, valid_until),
            parents,
            origin="SUPPLIED_SEMANTIC_PRODUCER",
        )


def aggregate_completed(hours, degree, now):
    """Exact UTC buckets; absent sub-bars cannot be silently filled."""
    from ..structural_lifecycle_v6 import CompletedBar

    now = clock(now)
    if degree not in {"4H", "1D"}:
        raise ContractError("HIGHER_DEGREE_REQUIRED")
    count = int(DEGREES[degree] / timedelta(hours=1))
    if len(hours) != count:
        raise ContractError("INCOMPLETE_AGGREGATION_BUCKET")
    for i, b in enumerate(hours):
        completed(b, b.end, "1H")
        if instant(b.end) > now or i and b.start != hours[i - 1].end:
            raise ContractError("AGGREGATION_GAP_OR_FUTURE")
    result = CompletedBar(
        hours[0].start,
        hours[-1].end,
        degree,
        hours[0].open,
        max(b.high for b in hours),
        min(b.low for b in hours),
        hours[-1].close,
    )
    completed(result, now, degree)
    return result


def live_market_observations(prefixes, leader_pair, membership, now):
    """Bound PIT complete-frame breadth and pivot trend for the Dow wrapper.

    This declared 4H snapshot adapter is not retrospective certification of an
    old weekly Dow series. Missing members make the source incomplete, never a
    narrower conveniently positive market. Volume is availability, not a veto.
    """
    from ..live_dow_context_v7 import KnownObservation

    now = clock(now)
    pairs = membership.value
    if not isinstance(pairs, tuple) or not pairs or len(set(pairs)) != len(pairs):
        raise ContractError("EXPLICIT_PIT_MARKET_MEMBERSHIP_REQUIRED")
    if leader_pair not in pairs or set(pairs) != set(prefixes):
        raise ContractError("COMPLETE_PIT_MARKET_FRAME_REQUIRED")
    graph = prefixes[leader_pair].graph
    graph.require(membership, now)
    returns, parents, source_shas = {}, [membership.event_id], []
    for pair in pairs:
        p = prefixes[pair]
        if p.pair != pair or p.graph is not graph:
            raise ContractError("SHARED_MARKET_SOURCE_GRAPH_REQUIRED")
        bs = p.bars["4H"]
        if len(bs) < 2 or instant(bs[-1].end) != now:
            raise ContractError("COMPLETE_CONTEMPORANEOUS_MARKET_BARS_REQUIRED")
        parents.extend((p.require_bar(bs[-2], now), p.require_bar(bs[-1], now)))
        returns[pair] = bs[-1].close / bs[-2].close - 1
        source_shas.append(p.sha)
    leader = prefixes[leader_pair]
    directions = {}
    for degree, key in (("1D", "primary"), ("4H", "secondary")):
        bs = leader.bars[degree]
        if not bs or instant(bs[-1].end) > now:
            raise ContractError("CAUSAL_LEADER_DEGREE_REQUIRED")
        # 1D state must be the most recent completed daily bucket, not a stale
        # historical UP carried through missing daily data.
        if degree == "1D" and instant(bs[-1].end).timestamp() != (now.timestamp() // 86400) * 86400:
            raise ContractError("CURRENT_COMPLETED_LEADER_DAILY_STATE_REQUIRED")
        points = [
            p
            for p in leader.points.values()
            if p.degree == degree and instant(p.available_at) <= now
        ]
        ps = [
            native.Pivot(
                p.kind, i, p.price, pd.Timestamp(p.observed_at), pd.Timestamp(p.available_at)
            )
            for i, p in enumerate(sorted(points, key=lambda q: q.observed_at))
        ]
        directions[key] = native.trend_from_pivots(ps)
        parents.extend(p.event_id for p in points)
        parents.append(leader.bar_id(bs[-1]))
    broad = native.broad_equal_weight_confirmation(returns)
    values = dict(directions, broad_confirmation=broad["confirmed"], volume=True)
    source_sha = digest(("V9_COMPLETE_PIT_4H_BREADTH", sorted(source_shas)))
    result = {}
    for key, value in values.items():
        eid = digest(("MARKET", key, now, membership.event_id))
        e = Known(eid, value, now, source_sha, "market")
        if eid not in graph.nodes:
            graph.register(e, tuple(dict.fromkeys(parents)), origin="DETECTOR_GEOMETRY")
        else:
            graph.require(e, now)
        result[key] = KnownObservation(value, now, now, source_sha)
    return result, broad
