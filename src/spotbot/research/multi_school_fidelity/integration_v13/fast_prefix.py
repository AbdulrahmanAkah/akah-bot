"""Exact five-bar native pivot semantics without a DataFrame per hourly tick.

No window change: the original CompletedPrefix also feeds exactly the final
five bars to native.confirmed_pivots_2l2r. Equal extrema are rejected, both
independent extrema may be emitted, and both right closes remain mandatory.
"""

from __future__ import annotations

import math

from ..integration_v9.sources import CompletedPrefix
from ..school_contract_common_v8 import Known, Point, clock, completed, digest
from ..structural_lifecycle_v6 import ContractError, instant


class FastCompletedPrefix(CompletedPrefix):
    def on_close(self, bar, volume, now):
        now = clock(now)
        completed(bar,now,bar.timeframe)
        if type(volume) not in {int,float} or not math.isfinite(volume) or volume<0:
            raise ContractError("COMPLETED_VOLUME_REQUIRED")
        bs = self.bars[bar.timeframe]
        if bs and instant(bar.start)!=instant(bs[-1].end):
            raise ContractError("PREFIX_REPEAT_OR_COVERAGE_GAP")
        self.graph.register(Known(self.bar_id(bar),(bar,volume),now,self.sha,self.pair),origin="COMPLETED_BAR")
        bs.append(bar)
        self.volumes[bar.timeframe].append(volume)
        if len(bs)<5:
            return ()
        last = bs[-5:]
        center = last[2]
        fresh = []
        for kind, values, value in (("H",[b.high for b in last],center.high),("L",[b.low for b in last],center.low)):
            extreme = max(values) if kind=="H" else min(values)
            if value!=extreme or values.count(value)!=1:
                continue
            pid = digest((self.pair,bar.timeframe,instant(center.end),kind,"PIVOT"))
            point = Point(pid,kind,value,instant(center.end),instant(last[-1].end),bar.timeframe)
            point.validate(now)
            self.graph.register(Known(pid,point,point.available_at,self.sha,self.pair),
                                tuple(self.bar_id(b) for b in last),origin="CONFIRMED_PIVOT")
            self.points[pid]=point
            fresh.append(point)
        return tuple(fresh)

    def atr(self, degree, structure_id, now, n=20):
        now = clock(now)
        bs = self.bars[degree]
        if n!=20 or len(bs)<10 or instant(bs[-1].end)!=now:
            raise ContractError("NATIVE_ATR20_COMPLETED_WARMUP_REQUIRED")
        first = max(0,len(bs)-20)
        tr=[]
        for i in range(first,len(bs)):
            b=bs[i]
            prev=bs[i-1].close if i else b.open
            tr.append(max(b.high-b.low,abs(b.high-prev),abs(b.low-prev)) if i else b.high-b.low)
        value=sum(tr)/len(tr)
        eid=digest((self.pair,degree,now,"ATR20"))
        e=Known(eid,value,now,self.sha,self.pair)
        if eid in self.graph.nodes:
            return self.graph.require(e,now)
        return self.graph.register(e,tuple(self.bar_id(b) for b in bs[-21:]),origin="DETECTOR_GEOMETRY")
