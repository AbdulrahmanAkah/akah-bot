"""Actual campaign closure clock is independent of Harmonic owner bar degree.

Invalidated family cannot earn Type-II. Actual completion inside a4H bar
cannot make the partly pre-completion bar a post-completion retest.
"""
from ..integration_v13.producers import HistoricalProducer as Previous
from ..school_contract_common_v8 import clock
from ..structural_lifecycle_v6 import ContractError, instant

class HistoricalProducer(Previous):
    def acknowledge_harmonic_completion(self, sid, owner, at, *, execution_receipt):
        at = clock(at)
        receipt = self.graph.require(execution_receipt, at)
        if receipt.structure_id != sid or receipt.value != ("CAMPAIGN_CLOSED", owner):
            raise ContractError("EXACT_ACTUAL_HARMONIC_CLOSURE_RECEIPT_REQUIRED")
        pattern = self.harmonics[sid]
        if pattern.last_close is None or at < pattern.last_close:
            raise ContractError("HARMONIC_CLOSURE_BEFORE_SOURCE_CLOCK")
        if pattern.state == "INVALIDATED":
            return
        if owner == "HARMONIC_TYPE_I":
            if pattern.state != "TYPE_I_ACTIVE":
                raise ContractError("TYPE_I_ACTUAL_COMPLETION_ORDER")
            pattern._check_owner()
            pattern.state = "TYPE_I_COMPLETE"
            pattern.type1_complete_at = at
            self.type_i_completion_receipts[sid] = receipt
        elif owner == "HARMONIC_TYPE_II":
            pattern.complete_type2()
        else:
            raise ContractError("HARMONIC_EXACT_COMPLETION_OWNER_REQUIRED")

    def harmonic_close(self, sid, bar, *, pit_eligible):
        pattern = self.harmonics[sid]
        if (pattern.state == "TYPE_I_COMPLETE" and pattern.type1_complete_at is not None
                and instant(bar.start) < pattern.type1_complete_at):
            self.prefix.require_bar(bar, bar.end)
            if instant(bar.start) != pattern.last_close:
                raise ContractError("PARTIAL_OWNER_BAR_CLOCK_PARITY")
            stopped = (bar.low <= pattern.stop if pattern.projection.sign == 1 else bar.high >= pattern.stop)
            if stopped:
                pattern.state = "INVALIDATED"
            pattern.last_close = clock(bar.end)
            return None
        return super().harmonic_close(sid, bar, pit_eligible=pit_eligible)
