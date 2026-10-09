"""Native Classical V3 patterns -> sealed source issues, not replay-row repair.

The pattern repertoire, 180/60 completed-H4 expiry and six-H4 continuation
identity cooldown are inherited verbatim from scan_classical. V6's local
acceptance stop is used instead of quietly reverting to the old wide stop.
H1 additionally needs a supplied LIVE markup owner, never the word 'UP'.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import median

import pandas as pd

from .. import akah_full_fidelity_runtime_v1 as native
from ..akah_replay_ready_detectors_v1 import event_row
from ..integration_v10.stop_provenance import StopProof
from ..owned_runtime_v3 import ClassicalRuntimeV3
from ..school_contract_common_v8 import clock, digest
from ..structural_lifecycle_v6 import Binding, CL, H1, ContractError, Mode, Objective, PendingSetup, instant


@dataclass(frozen=True)
class LegacyEmission:
    issue: object
    binding: Binding
    stop_proof: StopProof
    objectives: tuple[Objective, ...]
    mode: Mode = Mode.TREND


class ClassicalSource:
    def __init__(self, producer):
        self.producer = producer
        self.prefix = producer.prefix
        self.runtime = ClassicalRuntimeV3(self.prefix.pair)
        self.metadata = {}
        self.seen = set()
        self.last_cont = {}
        self.last = None
        self.diagnostics = []

    def _points(self, now):
        prefix = self.prefix
        points = sorted((p for p in prefix.points.values() if p.degree == "4H" and instant(p.available_at) <= now),
                        key=lambda p:(instant(p.observed_at),p.event_id))
        # Original detector indexes are bar indexes, not ordinal pivot indexes.
        index = {b.end: i for i,b in enumerate(prefix.bars["4H"])}
        pivots = [native.Pivot(p.kind,index[p.observed_at],p.price,pd.Timestamp(p.observed_at),
                              pd.Timestamp(p.available_at)) for p in points]
        return points, pivots

    def close(self, bar, fresh, membership, *, markup=None):
        now = clock(bar.end)
        if bar.timeframe != "4H" or self.last is not None and now <= self.last:
            raise ContractError("CLASSICAL_COMPLETED_H4_CHRONOLOGY_REQUIRED")
        self.prefix.require_bar(bar,now)
        self.last = now
        bs = self.prefix.bars["4H"]
        index = len(bs)-1
        if fresh:
            try:
                atr = self.prefix.atr("4H",self.prefix.pair,now)
            except ContractError as exc:
                self.diagnostics.append((now,str(exc)))
            else:
                points, pivots = self._points(now)
                pats = native.classical_patterns_from_pivots(pivots,atr.value,pd.Timestamp(now))
                frame = pd.DataFrame([dict(timestamp=b.end,open=b.open,high=b.high,low=b.low,close=b.close,volume=v)
                    for b,v in zip(bs,self.prefix.volumes["4H"],strict=True)])
                prior = [p for p in pivots if index >=12 and p.confirm_time <= pd.Timestamp(bs[index-12].end)]
                pats += native.continuation_patterns_from_bars(frame,atr.value,prior)
                for pattern in pats:
                    signature = (pattern.kind,round(pattern.boundary,8),round(pattern.support,8),str(pattern.formed_at))
                    if signature in self.seen:
                        continue
                    if pattern.kind in {"FLAG","PENNANT","BASE_BREAKOUT"}:
                        if index-self.last_cont.get(pattern.kind,-999)<6:
                            continue
                        self.last_cont[pattern.kind] = index
                    self.seen.add(signature)
                    sid = digest(("V13_CLASSICAL",self.prefix.pair,signature))
                    parents = tuple(p.event_id for p in points) + (self.prefix.bar_id(bar),atr.event_id)
                    claim = self.producer._claim(sid,pattern,now,sid,parents)
                    self.runtime.mature(pattern)
                    self.metadata[pattern.pattern_id] = dict(mature=index,breakout=None,sid=sid,claim=claim)
        emitted = []
        for pid in tuple(self.runtime.pending):
            q = self.runtime.pending[pid]
            m = self.metadata[pid]
            pattern = q["pattern"]
            if (q["state"] == "MATURE" and index-m["mature"]>180 or
                q["state"] == "BREAKOUT" and index-m["breakout"]>60):
                self.prefix.graph.terminate(m["claim"].event_id)
                del self.runtime.pending[pid]
                continue
            if q["state"] == "MATURE":
                vm = median(self.prefix.volumes["4H"][-20:]) if len(bs)>=10 else float("inf")
                if self.runtime.update_breakout(pd.Timestamp(now),pid,bar.close,self.prefix.volumes["4H"][-1],vm):
                    m["breakout"] = index
                    m["breakout_bar"] = self.prefix.bar_id(bar)
            if q["state"] != "BREAKOUT" or index <= m["breakout"]:
                continue
            lows = sorted((p for p in self.prefix.points.values() if p.degree=="4H" and p.kind=="L" and
                           instant(p.observed_at)>instant(q["breakout_time"]) and instant(p.available_at)<=now),
                          key=lambda p:(p.observed_at,p.event_id))
            low = lows[-1] if lows else None
            intent = self.runtime.entry_intent(pd.Timestamp(now),pid,bar.low,bar.close,low.price if low else None)
            if q["state"] == "INVALIDATED":
                self.prefix.graph.terminate(m["claim"].event_id)
                del self.runtime.pending[pid]
                continue
            if intent is None:
                continue
            retest = intent.branch.endswith(":THROWBACK")
            proof = StopProof("CLASSICAL_ACCEPTANCE_LOW" if retest else "CLASSICAL_CONFIRMED_LOW",
                              (self.prefix.bar_id(bar) if retest else low.event_id,))
            stop = proof.evaluate(self.prefix.graph,now)
            if not stop < bar.close:
                self.diagnostics.append((m["sid"],now,"LOCAL_STOP_NOT_BELOW_ENTRY"))
                continue
            for grammar in (CL,H1):
                parents = [m["claim"].event_id,m["breakout_bar"],*proof.source_ids]
                if grammar == H1:
                    if markup is None:
                        self.diagnostics.append((m["sid"],now,"H1_NATIVE_MARKUP_OWNER_UNAVAILABLE"))
                        continue
                    self.prefix.graph.require(markup,now)
                    if markup.value != "MARKUP" or markup.valid_until is None or now>=instant(markup.valid_until):
                        raise ContractError("H1_CURRENT_OWNED_MARKUP_REQUIRED")
                    parents.append(markup.event_id)
                binding = Binding(grammar,CL,m["sid"],self.prefix.sha,"4H",now,stop,proof.source_ids[0])
                objective = Objective(digest((m["sid"],"MEASURED_PATTERN",intent.target)),m["sid"],intent.target,
                                      "MEASURED_PATTERN",now,self.prefix.sha)
                event = event_row(grammar,self.prefix.pair,now,intent.branch,"THESIS_INTENT",membership.value.eligible,
                                  dict(owner_structure_id=m["sid"],stop=stop,invalidation_source=proof.source_ids[0],
                                       required_evidence_ids=parents,management_owner=CL,management_degree="4H",
                                       management_mode="TREND_CHECKPOINTS",target=intent.target))
                issued = self.producer.seal_legacy(event,binding,proof,membership)
                emitted.append(LegacyEmission(issued,binding,proof,(objective,)))
        return emitted
