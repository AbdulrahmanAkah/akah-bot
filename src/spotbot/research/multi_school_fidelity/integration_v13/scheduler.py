"""Bounded chronological scheduler of supplied hours, with no replay fallback.

Input loading remains the authority resolver's responsibility. This component
cannot certify missing school semantics. Only OPEN prices leave the current
hour before completion; capacity uses exactly 24 prior completed source hours.
"""
from collections import deque
from datetime import datetime, timedelta, timezone
from heapq import heappush, heappop
from math import isfinite

from ..structural_lifecycle_v6 import ContractError, instant
from .guarded_driver import OpenPacket, ClosePacket

START=datetime(2022,1,1,tzinfo=timezone.utc)
LAST_OPEN=datetime(2023,12,31,22,tzinfo=timezone.utc)
CUTOFF=datetime(2024,1,1,tzinfo=timezone.utc)


class BoundedScheduler:
    def __init__(self, streams):
        if not isinstance(streams,dict) or not streams:
            raise ContractError("EXPLICIT_BOUNDED_SOURCE_STREAMS_REQUIRED")
        self.streams={p:iter(s) for p,s in sorted(streams.items())}
        self.prior={p:deque(maxlen=24) for p in streams}
        self.last={}
        self.diagnostics=[]
        self.started=False

    def _next(self,pair):
        item=next(self.streams[pair],None)
        if item is None:
            return None
        bar,volume=item
        bar.validate()
        if bar.timeframe!="1H" or instant(bar.end)>=CUTOFF:
            raise ContractError("PROTECTED_OR_NON_HOURLY_SOURCE_ROW")
        if instant(bar.start)<datetime(2021,9,1,tzinfo=timezone.utc):
            raise ContractError("SOURCE_BEFORE_FROZEN_WARMUP")
        if type(volume) not in {int,float} or not isfinite(volume) or volume<0:
            raise ContractError("FINITE_SOURCE_VOLUME_REQUIRED")
        if pair in self.last and instant(bar.start)!=self.last[pair]:
            raise ContractError("SOURCE_GAP_REQUIRES_NEW_IDENTITY_NOT_FORWARD_FILL:"+pair)
        self.last[pair]=instant(bar.end)
        return bar,volume

    def run(self, driver):
        if self.started:
            raise ContractError("SCHEDULER_ONE_RUN_NO_RESURRECTION")
        self.started=True
        heap=[]
        for pair in self.streams:
            item=self._next(pair)
            if item is not None:
                heappush(heap,(instant(item[0].start),pair,item))
        expected=START
        while heap:
            at=heap[0][0]
            items={}
            while heap and heap[0][0]==at:
                _,pair,item=heappop(heap)
                items[pair]=item
            packet=ClosePacket(tuple((p,x[0]) for p,x in sorted(items.items())),
                               tuple((p,x[1]) for p,x in sorted(items.items())))
            if at<START:
                driver.source.on_completed_hour(packet)
            else:
                if at!=expected or at>LAST_OPEN:
                    raise ContractError("FROZEN_ECONOMIC_CALENDAR_COVERAGE_GAP")
                caps=[]
                for pair in items:
                    prior=self.prior[pair]
                    contiguous=(len(prior)==24 and prior[-1][0]==at and
                                prior[0][0]==at-timedelta(hours=23))
                    caps.append((pair,.005*sum(q for _,q in prior) if contiguous else 0.))
                driver.on_open(OpenPacket(at,tuple((p,x[0].open) for p,x in sorted(items.items())),
                                          tuple(caps)))
                driver.on_completed_hour(packet)
                expected+=timedelta(hours=1)
            for pair,(bar,volume) in items.items():
                self.prior[pair].append((instant(bar.end),volume*bar.close))
                item=self._next(pair)
                if item is not None:
                    heappush(heap,(instant(item[0].start),pair,item))
        if expected!=LAST_OPEN+timedelta(hours=1):
            raise ContractError("FULL_FROZEN_CALENDAR_NOT_COMPLETED")
        return driver.outputs()
