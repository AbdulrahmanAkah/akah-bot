"""Same causal open/close schedule; data gaps cannot be disguised by forward fill."""
from datetime import timedelta

from ..integration_v13.scheduler import BoundedScheduler, START, LAST_OPEN
from ..integration_v13.guarded_driver import ClosePacket, OpenPacket
from ..structural_lifecycle_v6 import ContractError, instant
from scripts.research.integration_v14.runner import merged


class ScopedScheduler(BoundedScheduler):
    def run(self, driver):
        if self.started:
            raise ContractError("SCHEDULER_ONE_RUN_NO_RESURRECTION")
        self.started = True
        expected = START
        for at, items in merged(self.streams):
            for pair, (bar, volume) in items.items():
                bar.validate()
                if (bar.timeframe != "1H" or instant(bar.end).year >= 2024
                        or instant(bar.start).year < 2021 or volume < 0):
                    raise ContractError("PROTECTED_OR_INVALID_BOUNDED_HOUR")
                if pair in self.last and instant(bar.start) < self.last[pair]:
                    raise ContractError("SOURCE_CLOCK_REVERSED_OR_DUPLICATE")
                if pair in self.last and instant(bar.start) != self.last[pair]:
                    self.prior[pair].clear()
                self.last[pair] = instant(bar.end)
            close = ClosePacket(tuple((p, x[0]) for p, x in sorted(items.items())),
                                tuple((p, x[1]) for p, x in sorted(items.items())))
            if at < START:
                driver.source.on_completed_hour(close)
            else:
                if at != expected or at > LAST_OPEN:
                    raise ContractError("FROZEN_ECONOMIC_CALENDAR_COVERAGE_GAP")
                caps = []
                for pair in items:
                    prior = self.prior[pair]
                    complete = (len(prior) == 24 and prior[-1][0] == at
                                and prior[0][0] == at-timedelta(hours=23))
                    caps.append((pair, .005*sum(q for _, q in prior) if complete else 0.))
                driver.on_open(OpenPacket(at, tuple((p, x[0].open) for p, x in sorted(items.items())), tuple(caps)))
                driver.on_completed_hour(close)
                expected += timedelta(hours=1)
            for pair, (bar, volume) in items.items():
                self.prior[pair].append((instant(bar.end), volume*bar.close))
        if expected != LAST_OPEN + timedelta(hours=1):
            raise ContractError("FULL_FROZEN_CALENDAR_NOT_COMPLETED")
        return driver.outputs()
