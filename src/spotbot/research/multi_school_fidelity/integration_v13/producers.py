"""V12 seals with complete same-checkpoint Elliott claim enumeration.

Every claim sees the identical pre-decision book including all opposing counts.
No latest/best claim is picked by the generator; downstream frozen selector owns
competition. Each native book decision remains single-clock, then its tombstones
and consumed claims are merged only after the whole checkpoint has been checked.
"""

from __future__ import annotations

import copy

from ..integration_v12.producers import ContractProducer as V12Producer
from ..school_contract_common_v8 import clock
from ..structural_lifecycle_v6 import ContractError


class HistoricalProducer(V12Producer):
    def elliott_candidates(self, bar, *, pit_eligible):
        now=clock(bar.end)
        self.prefix.require_bar(bar,now)
        original=copy.deepcopy(self.elliott)
        if original.last_clock is not None and now<=original.last_clock:
            raise ContractError("COUNT_CLOCK_REVERSED")
        claims=sorted({c.claim for cid,c in original.counts.items() if cid not in original.tombstones},key=str)
        results=[]
        tombstones=set(original.tombstones)
        consumed=set(original.used_claims)
        try:
            for claim in claims:
                self.elliott=copy.deepcopy(original)
                item=super().elliott_close(bar,claim,pit_eligible=pit_eligible)
                tombstones.update(self.elliott.tombstones)
                consumed.update(self.elliott.used_claims)
                if item is not None:
                    results.append(item)
        finally:
            self.elliott=original
        self.elliott.tombstones=tombstones
        self.elliott.used_claims=consumed
        self.elliott.last_clock=now
        return tuple(results)
