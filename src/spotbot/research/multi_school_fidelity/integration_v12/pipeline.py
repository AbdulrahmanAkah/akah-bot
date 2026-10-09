"""Reuse V11 exact kernel guards with V12 complete live dependency edges."""

from ..integration_v11.pipeline import PipelineV11, RouterV11


class RouterV12(RouterV11):
    def permission(self, grammar, state):
        ok, reason = super().permission(grammar, state)
        if reason == "V11_INDEPENDENT_RESERVE_AND_PRODUCER_CERTIFICATION_REQUIRED":
            reason = "V12_INDEPENDENT_RESERVE_AND_PRODUCER_CERTIFICATION_REQUIRED"
        return ok, reason


class PipelineV12(PipelineV11):
    """No new execution, price, cost, risk or grammar semantics."""
