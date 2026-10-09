"""Quarantine checked at bind, selection and actual owned execution."""
import copy
from ..integration_v11.execution import ExecutionV11
from ..integration_v13.research_bridge import ResearchPipeline, ResearchRouter
from ..structural_lifecycle_v6 import ContractError
from ..portfolio_kernel import PortfolioKernel
from ..full_replay_v4 import DecimalQuantityKernel
from .authority import funded


class ScopedKernel(DecimalQuantityKernel):
    def admit(self, row, *args, **kwargs):
        grammar = row.get("owner_grammar", row.get("system_id"))
        funded(grammar)
        if getattr(self, "_source_admission", None) != (row.get("identity"), grammar):
            raise ContractError("KERNEL_SOURCE_ADMISSION_CAPABILITY_REQUIRED")
        return super().admit(row, *args, **kwargs)


class ScopedExecution(ExecutionV11):
    def __init__(self, portfolio):
        if type(portfolio.k) is DecimalQuantityKernel:
            old = portfolio.k
            portfolio.k = ScopedKernel(**old.__dict__)
        if not isinstance(portfolio.k, ScopedKernel):
            raise ContractError("SCOPED_KERNEL_REQUIRED")
        super().__init__(portfolio)
        self.receipt_graph = None
        self.admission_receipts = {}
        self.context_validator = None
        self.selector_receipt_hook = None
        self._preview = False

    def __deepcopy__(self, memo):
        # Preview may mutate portfolio/managers, NEVER source or receipt graphs.
        # Share read-only validators and immutable SourceGuard objects so a
        # candidate preview cannot copy the full market graph or a live driver.
        result = type(self).__new__(type(self))
        memo[id(self)] = result
        for key, value in self.__dict__.items():
            if key in {"receipt_graph", "context_validator", "selector_receipt_hook"}:
                setattr(result, key, value)
            elif key == "source_guards":
                setattr(result, key, dict(value))
            else:
                setattr(result, key, copy.deepcopy(value, memo))
        result._preview = True
        return result

    def admit_owned(self, row, binding, now, *args, **kwargs):
        funded(row.get("owner_grammar", row.get("system_id")))
        funded(binding.grammar)
        if self.receipt_graph is None or row["identity"] not in self.admission_receipts:
            raise ContractError("ACTUAL_FILL_REQUIRES_ADMISSION_RECEIPT")
        self.receipt_graph.verify(self.admission_receipts[row["identity"]], now)
        if not callable(self.context_validator):
            raise ContractError("LIVE_CONTEXT_VALIDATOR_REQUIRED")
        self.context_validator(row["identity"], now)
        if not self._preview:
            if not callable(self.selector_receipt_hook):
                raise ContractError("ACTUAL_SELECTOR_RECEIPT_HOOK_REQUIRED")
            receipt = self.selector_receipt_hook(row, binding, now)
            self.admission_receipts[row["identity"]] = receipt
            self.receipt_graph.verify(receipt, now)
        self.portfolio.k._source_admission = (row["identity"], binding.grammar)
        try:
            return super().admit_owned(row, binding, now, *args, **kwargs)
        finally:
            self.portfolio.k._source_admission = None


class ScopedRouter(ResearchRouter):
    def permission(self, grammar, state):
        funded(grammar)
        return super().permission(grammar, state)


class ScopedPipeline(ResearchPipeline):
    def __init__(self, execution, router):
        if not isinstance(execution, ScopedExecution) or not isinstance(router, ScopedRouter):
            raise ContractError("EXACT_FUNDED_SCOPE_EXECUTION_ROUTER_REQUIRED")
        super().__init__(execution, router)

    def bind(self, issue, *args, **kwargs):
        funded(issue.event["system_id"])
        return super().bind(issue, *args, **kwargs)

    def bind_legacy(self, issue, *args, **kwargs):
        funded(issue.event["system_id"])
        return super().bind_legacy(issue, *args, **kwargs)

    def _bind(self, candidate, now, *args, **kwargs):
        funded(candidate.row.get("owner_grammar", candidate.row.get("system_id")))
        funded(candidate.binding.grammar)
        return super()._bind(candidate, now, *args, **kwargs)

    def on_open(self, now, prices, capacities, candidates=(), **kwargs):
        for candidate in candidates:
            funded(candidate.row.get("owner_grammar", candidate.row.get("system_id")))
        return super().on_open(now, prices, capacities, candidates, **kwargs)
