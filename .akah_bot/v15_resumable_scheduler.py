"""Exact V14/V15 scheduler with snapshots ONLY after fully completed hours.

No temporal/capacity policy changes. Input generators are recreated and hash
verified separately; no open generator or pending current-hour bar is pickled.
"""
from datetime import timedelta
from spotbot.research.multi_school_fidelity.integration_v14.scheduler import ScopedScheduler as Original
from spotbot.research.multi_school_fidelity.integration_v13.scheduler import START, LAST_OPEN
from spotbot.research.multi_school_fidelity.integration_v13.guarded_driver import ClosePacket, OpenPacket
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError, instant
from scripts.research.integration_v14.runner import merged


class ResumableScheduler(Original):
    def run(self, driver, *, restored=None, checkpoint=None, stop_at=None):
        if self.started:
            raise ContractError('SCHEDULER_ONE_RUN_NO_RESURRECTION')
        self.started=True
        expected=START
        cursor=None
        if restored is not None:
            if set(restored['prior']) != set(self.streams):
                raise ContractError('CHECKPOINT_SOURCE_PAIR_SET_DRIFT')
            self.prior=restored['prior'];self.last=restored['last']
            expected=restored['expected'];cursor=restored['cursor']
        # Filter before merge, but stream construction still verifies ALL bounded
        # input SHAs. All skipped rows are prior completed checkpoint history.
        def remaining(stream):
            for item in stream:
                if cursor is None or instant(item[0].end)>cursor:
                    yield item
        streams={p:remaining(s) for p,s in self.streams.items()}
        for at,items in merged(streams):
            for pair,(bar,volume) in items.items():
                bar.validate()
                if (bar.timeframe!='1H' or instant(bar.end).year>=2024
                        or instant(bar.start).year<2021 or volume<0):
                    raise ContractError('PROTECTED_OR_INVALID_BOUNDED_HOUR')
                if pair in self.last and instant(bar.start)<self.last[pair]:
                    raise ContractError('SOURCE_CLOCK_REVERSED_OR_DUPLICATE')
                if pair in self.last and instant(bar.start)!=self.last[pair]:
                    self.prior[pair].clear()
                self.last[pair]=instant(bar.end)
            close=ClosePacket(tuple((p,x[0]) for p,x in sorted(items.items())),
                              tuple((p,x[1]) for p,x in sorted(items.items())))
            if at<START:
                driver.source.on_completed_hour(close)
            else:
                if at!=expected or at>LAST_OPEN:
                    raise ContractError('FROZEN_ECONOMIC_CALENDAR_COVERAGE_GAP')
                caps=[]
                for pair in items:
                    prior=self.prior[pair]
                    complete=(len(prior)==24 and prior[-1][0]==at
                              and prior[0][0]==at-timedelta(hours=23))
                    caps.append((pair,.005*sum(q for _,q in prior) if complete else 0.))
                driver.on_open(OpenPacket(at,tuple((p,x[0].open) for p,x in sorted(items.items())),tuple(caps)))
                driver.on_completed_hour(close)
                expected+=timedelta(hours=1)
            for pair,(bar,volume) in items.items():
                self.prior[pair].append((instant(bar.end),volume*bar.close))
            cursor=at+timedelta(hours=1)
            state={'prior':self.prior,'last':self.last,'expected':expected,'cursor':cursor}
            if checkpoint is not None:
                checkpoint(driver,state)
            if stop_at is not None and cursor>=stop_at:
                return state # Test-only interrupted prefix, NEVER outputs().
        if expected!=LAST_OPEN+timedelta(hours=1):
            raise ContractError('FULL_FROZEN_CALENDAR_NOT_COMPLETED')
        return driver.outputs()
