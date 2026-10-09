"""Revalidate exact producer authority at the real kernel admission boundary."""

from __future__ import annotations

from dataclasses import dataclass

from ..integration_v10.execution import ExecutionV9 as PreviousExecution
from ..structural_lifecycle_v6 import ContractError
from .contracts import Produced, freeze, verify_issue


@dataclass(frozen=True)
class SourceGuard:
    issue: object
    graph: object
    row: object
    binding: object
    add_evidence: object
    required_claims: tuple
    configuration: tuple

    def validate(self, row, binding, now, campaign_id, add_evidence, configuration=None):
        eligible = verify_issue(self.issue, self.graph, now)
        for claim in self.required_claims:
            self.graph.require(claim, now)
        if freeze(row) != self.row or binding != self.binding or add_evidence != self.add_evidence:
            raise ContractError("FILL_SOURCE_PAYLOAD_PARITY")
        if row["pit_eligible"] is not eligible:
            raise ContractError("FILL_PIT_SOURCE_PARITY")
        if configuration is not None and configuration != self.configuration:
            raise ContractError("FILL_NATIVE_CONFIGURATION_PARITY")
        if isinstance(self.issue, Produced) and self.issue.add_proof:
            proof = self.issue.add_proof.value
            expected = proof.evaluate(self.graph, self.issue.thesis, row["pair"], now)
            if (
                add_evidence is None
                or add_evidence.lps_low != expected
                or campaign_id != proof.campaign_id
            ):
                raise ContractError("FILL_ADD_PROVENANCE_PARITY")
        elif campaign_id != row["identity"]:
            raise ContractError("FILL_CAMPAIGN_ID_PARITY")
        return eligible


class ExecutionV11(PreviousExecution):
    def __init__(self, portfolio):
        super().__init__(portfolio)
        self.source_guards = {}

    def admit_owned(self, row, binding, now, entry, capacity, campaign_id, **kwargs):
        guard = self.source_guards.get(row["identity"])
        if guard is None:
            raise ContractError("V11_KERNEL_SOURCE_GUARD_REQUIRED")
        configuration = (
            kwargs.get("mode"),
            tuple(kwargs.get("objectives", ())),
            kwargs.get("partial_plan"),
            kwargs.get("staged", False),
        )
        if not guard.validate(
            row, binding, now, campaign_id, kwargs.get("add_evidence"), configuration
        ):
            return False, "PIT_SOURCE_NOT_ELIGIBLE"
        return super().admit_owned(row, binding, now, entry, capacity, campaign_id, **kwargs)
