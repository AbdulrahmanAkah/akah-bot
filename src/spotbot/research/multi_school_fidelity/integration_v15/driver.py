"""Real guard/clock/accounting path with exact V15 nine-system receipt scope."""
from __future__ import annotations

from dataclasses import replace
import json
import math

from scripts.research.integration_v15.precommit import PROTOCOL, INPUT_MANIFEST, ROOTS, config_hash, require_ready, verify
from ..integration_v13.guarded_driver import GuardedDriver
from ..integration_v13.source_provider import SourceProvider
from ..school_contract_common_v8 import digest, clock
from ..structural_lifecycle_v6 import ContractError
from .authority import ReceiptGraph, funded
from .authority import FUNDED
from .bridge import ScopedPipeline
from .binding import bind_request, registered_producer


class ScopedDriver(GuardedDriver):
    def __init__(self, *args, mechanics_only=False, **kwargs):
        self.mechanics_only = mechanics_only
        source = args[3]
        # Actual historical source provider can NEVER run in fixture scope.
        if mechanics_only and isinstance(source, SourceProvider):
            raise ContractError("REAL_MARKET_SOURCE_CANNOT_USE_MECHANICS_SCOPE")
        self.trace = ReceiptGraph(args[1]["source_version_sha256"], args[1]["precommit_sha256"])
        self.terminal_receipt = None
        self.owner_receipts = {}
        self.context_receipts = {}
        self.fill_phases = {}
        if not isinstance(args[2], ScopedPipeline):
            raise ContractError("EXACT_SCOPED_PIPELINE_REQUIRED")
        args[2].execution.receipt_graph = self.trace
        args[2].execution.context_validator = self._verify_context
        args[2].execution.selector_receipt_hook = self._selected_receipt
        multi_fixture = mechanics_only and kwargs.get("arm") is None
        if multi_fixture:
            kwargs["arm"] = FUNDED[0] + "|2X"
        super().__init__(*args, **kwargs)
        if multi_fixture:
            self.arm = None

    def _certificates(self, now):
        if self.mechanics_only and self.arm is None:
            for grammar in FUNDED:
                self.pipeline.router.certificates[grammar].validate(self.pipeline.router.scope)
            return
        return super()._certificates(now)

    def _stat_sources(self):
        paths = {PROTOCOL, INPUT_MANIFEST}
        for root in ROOTS:
            paths.update(p.relative_to(self.repo).as_posix() for p in (self.repo / root).rglob("*.py"))
        return {p: ((self.repo / p).stat().st_size, (self.repo / p).stat().st_mtime_ns,
                    (self.repo / p).stat().st_ctime_ns) for p in sorted(paths)}

    def _assert_current(self, *, full=False):
        if self.failed:
            raise ContractError("DRIVER_FAILED_NO_AUTOMATIC_RETRY")
        checkpoint = max((t for t in (self.last_open, self.last_close) if t is not None), default=None)
        if checkpoint is not None:
            for receipt in self.owner_receipts.values():
                self.trace.verify(receipt, checkpoint)
        payload = {k: v for k, v in self.precommit.items() if k != "precommit_sha256"}
        if config_hash(payload) != self._frozen_payload_hash:
            raise ContractError("FROZEN_PRECOMMIT_PAYLOAD_DRIFT")
        snapshot = self._stat_sources()
        if self._source_snapshot is not None and snapshot != self._source_snapshot:
            raise ContractError("SOURCE_SNAPSHOT_DRIFT_BEFORE_CALLBACK")
        scope = self.pipeline.router.scope
        scope.validate()
        if (scope.source_version_sha256 != self.precommit["source_version_sha256"]
                or scope.protocol_sha256 != self.precommit["source_hashes"][PROTOCOL]):
            raise ContractError("RESEARCH_SCOPE_PRECOMMIT_VERSION_PARITY")
        if self.arm is not None:
            rate = self.precommit["contract"]["costs_round_trip"][self.arm.split("|")[1]] / 2
            if self.pipeline.execution.portfolio.k.exit_cost_rate != rate:
                raise ContractError("FROZEN_ARM_COST_PARITY")
        if full:
            verify(self.repo, self.precommit)
            if not self.mechanics_only:
                require_ready(self.repo, self.precommit, self.readiness_receipt)
            if snapshot != self._stat_sources():
                raise ContractError("SOURCE_DRIFT_DURING_FULL_VERIFICATION")
        self._source_snapshot = snapshot

    def _bind(self, request, now):
        funded(request.issue.event["system_id"])
        permission = getattr(self.source, "permission", None)
        if permission is None or not permission.permits(now):
            raise ContractError("COMPLETE_CURRENT_DOW_PERMISSION_REQUIRED")
        envelope = bind_request(self, request, now)
        if envelope is None:
            return None
        producer, issue = request.producer, request.issue
        chain = self.trace.append("SOURCE_EVIDENCE", {"source_sha": producer.prefix.sha,
                                  "source_issue_sha": digest(issue),
                                  "source_emission": getattr(issue, "emission_id", None),
                                  "required_evidence_ids": issue.event.get("required_evidence_ids", ()),
                                  "dow": str(permission)}, now)
        chain = self.trace.append("SEMANTIC_PRODUCER", {"grammar": envelope.binding.grammar,
                                  "structure": envelope.binding.structure_id}, now, (chain,))
        chain = self.trace.append("EMISSION_SEAL", {"issue_sha": digest(issue)}, now, (chain,))
        chain = self.trace.append("BOUND_ADMISSION_REQUEST", {"identity": envelope.row["identity"],
                                  "binding": digest(envelope.binding)}, now, (chain,))
        self.pipeline.execution.admission_receipts[envelope.row["identity"]] = chain
        self.context_receipts[envelope.row["identity"]] = permission
        # Live source/receipt checks are repeated by ScopedExecution AFTER preview.
        return envelope

    def _producer(self, pair, binding):
        return registered_producer(self, pair, binding)

    def _selected_receipt(self, row, binding, now):
        identity = row["identity"]
        parent = self.pipeline.execution.admission_receipts[identity]
        return self.trace.append("SELECTOR_ADMISSION", {
            "identity": identity, "binding_sha": digest(binding), "selected": True,
            "grammar": binding.grammar, "mode": "ACTUAL_SELECTED_KERNEL_ATTEMPT_NOT_PREVIEW",
            "selector": self.precommit["contract"]["selector"],
        }, now, (parent,))

    def _verify_context(self, identity, now):
        permission = getattr(self.source, "permission", None)
        if (permission is None or not permission.permits(now)
                or permission != self.context_receipts.get(identity)):
            raise ContractError("CURRENT_COMPLETE_DOW_CONTEXT_CHANGED_BEFORE_FILL")

    def _retain_fills(self, first, now, kind):
        execution = self.pipeline.execution
        for index, fill in enumerate(execution.portfolio.k.fills[first:], first):
            self.fill_phases[index] = "OPEN" if kind == "EXECUTION_FILL" else "CLOSE"
            identity = fill["identity"]
            parent = self.owner_receipts.get(identity, execution.admission_receipts.get(identity))
            if parent is None:
                raise ContractError("FILL_WITHOUT_RETAINED_ADMISSION_LINEAGE")
            actual_kind = "LIFECYCLE_EXECUTION" if fill["side"] == "SELL" else kind
            rid = self.trace.append(actual_kind, fill, now, (parent,))
            self.owner_receipts[identity] = rid

    def on_open(self, packet):
        first = len(self.pipeline.execution.portfolio.k.fills)
        result = super().on_open(packet)
        self.terminal_marks = dict(packet.prices)
        self._retain_fills(first, packet.at, "EXECUTION_FILL")
        return result

    def _owner_updates(self, updates, now):
        values = super()._owner_updates(updates, now)
        execution = self.pipeline.execution
        for update in updates:
            identities = [p["episode"]["identity"] for tid, p in execution.portfolio.k.positions.items()
                          if execution.managers[tid].binding.structure_id == update.structure_id]
            for identity in identities:
                parent = self.owner_receipts[identity]
                rid = self.trace.append("OWNER_UPDATE", {
                    "producer_source_sha": update.producer.prefix.sha,
                    "structure_id": update.structure_id, "bar_sha": digest(update.bar),
                    "pivots_sha": digest(update.pivots), "objectives_sha": digest(update.objectives),
                    "failure_sha": digest(update.failure),
                }, now, (parent,))
                self.owner_receipts[identity] = rid
        for tid, position in execution.portfolio.k.positions.items():
            binding = execution.managers[tid].binding
            self._producer(position["episode"]["pair"], binding)
            identity = position["episode"]["identity"]
            self.owner_receipts[identity] = self.trace.append("OWNER_UPDATE", {
                "identity": identity, "binding_sha": digest(binding),
                "owner_checked": True, "completed_owner_update": binding.structure_id in values[0],
                "policy": "NO_INVENTED_OWNER_BAR;HOURLY_PROTECTION_REMAINS_ACTIVE",
            }, now, (self.owner_receipts[identity],))
        return values

    def on_completed_hour(self, packet):
        first = len(self.pipeline.execution.portfolio.k.fills)
        # Verify the prior retained owner lineage BEFORE any close execution.
        for rid in self.owner_receipts.values():
            self.trace.verify(rid, packet.bars[0][1].end)
        super().on_completed_hour(packet)
        self.terminal_marks = {pair: bar.close for pair, bar in packet.bars}
        self._retain_fills(first, self.last_close, "LIFECYCLE_EXECUTION")

    def outputs(self):
        if self.terminal_receipt is not None:
            prior = self.trace.verify(self.terminal_receipt, self.last_close or self.last_open)
            payload = json.loads(prior.payload_json)
            kernel = self.pipeline.execution.portfolio.k
            if (payload["fills_sha"] != digest(kernel.fills)
                    or payload["campaigns_sha"] != digest(kernel.campaigns)
                    or payload["marks_sha"] != digest(self.equity) or payload["cash"] != kernel.cash):
                raise ContractError("ACCOUNTING_OUTPUT_MUTATED_AFTER_RECEIPT")
        outputs = super().outputs()
        kernel = self.pipeline.execution.portfolio.k
        expected_cash = self.precommit["contract"]["risk"]["initial_equity"] + sum(f["cash_delta"] for f in kernel.fills)
        if not math.isclose(kernel.cash, expected_cash, rel_tol=1e-12, abs_tol=1e-7):
            raise ContractError("CASH_LEDGER_RECONCILIATION_FAILED")
        for fill in kernel.fills:
            notional = fill["qty"] * fill["price"]
            fee = notional * kernel.exit_cost_rate
            expected = -notional-fee if fill["side"] == "BUY" else notional-fee
            if (not math.isclose(fill["fee"], fee, rel_tol=1e-12, abs_tol=1e-8)
                    or not math.isclose(fill["cash_delta"], expected, rel_tol=1e-12, abs_tol=1e-8)):
                raise ContractError("FILL_FEE_CASH_RECONCILIATION_FAILED")
        parents = tuple(self.owner_receipts.values())
        self.terminal_receipt = self.trace.append("ACCOUNTING_OUTPUT", {
            "cash": kernel.cash, "fills_sha": digest(kernel.fills),
            "campaigns_sha": digest(kernel.campaigns), "marks_sha": digest(self.equity),
            "disposition": "SYNTHETIC_MECHANICS_ONLY" if self.mechanics_only else "EXPOSED_RESEARCH",
        }, self.last_close or self.last_open, parents)
        self.trace.verify(self.terminal_receipt, self.last_close or self.last_open)
        outputs["receipt_graph"] = self.trace.export()
        outputs["accounting_receipt"] = self.terminal_receipt
        outputs["source_diagnostics"] = dict(getattr(self.source, "diagnostics", {}))
        outputs["terminal_prices"] = dict(getattr(self, "terminal_marks", {}))
        outputs["fill_ledger"] = [dict(fill, arm=self.arm, execution_phase=self.fill_phases[index])
            for index, fill in enumerate(kernel.fills)]
        outputs["hourly_equity_ledger"] = [dict(row, arm=self.arm) for row in self.equity]
        outputs["dow"] = "CONTEXT_AND_EXPLICIT_V15_STANDALONE_OWNER"
        return outputs
