"""Chronological consumer of injected source-issued packets, never a market reader.

The enclosing scheduler owns bounded inputs and semantic generation. This driver
owns OPEN/CLOSE order, exact V12 admission, shared capacity and actual execution
receipt feedback. Synthetic mode is explicitly separate and cannot arm economics.
No legacy replay/admission fallback or output writer exists.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from scripts.research.integration_v13.economic_precommit import (
    GRAMMARS,
    PROTOCOL_PATH,
    SOURCE_ROOTS,
    _safe_source,
    config_hash,
    require_ready,
    verify_precommit,
)

from ..akah_native_replay_engine_v1 import current_mtm_limits_ok
from ..integration_v11.contracts import LegacyIssue, Produced, verify_issue
from ..integration_v12.pipeline import PipelineV12
from ..integration_v12.producers import ContractProducer
from ..school_contract_common_v8 import Known, Point, digest
from ..structural_lifecycle_v6 import (
    CompletedBar,
    ContractError,
    Mode,
    PendingSetup,
    instant,
)
from .research_bridge import ProducerCertificate, ResearchPipeline, ResearchRouter


@dataclass(frozen=True)
class OpenPacket:
    at: object
    prices: tuple[tuple[str, float], ...]
    capacity: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class ClosePacket:
    bars: tuple[tuple[str, CompletedBar], ...]
    volumes: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class SourceIssue:
    producer: ContractProducer
    issue: Produced | LegacyIssue
    state: object
    context: Known
    # Session endpoint, validity and legacy management are supplied source facts.
    options: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True)
class OwnerUpdate:
    producer: ContractProducer
    structure_id: str
    bar: CompletedBar | None = None
    pivots: tuple = ()
    objectives: tuple = ()
    failure: Known | None = None


@dataclass(frozen=True)
class ExecutionFeedback:
    campaign_id: str
    grammar: str
    structure_id: str
    owner: str
    at: object
    receipt: Known


def _pairs(values, *, numbers=False, positive=False):
    if not isinstance(values, tuple) or any(not isinstance(item, tuple) for item in values):
        raise ContractError("FROZEN_PACKET_TUPLES_REQUIRED")
    result = {}
    for item in values:
        if len(item) != 2:
            raise ContractError("PACKET_PAIR_REQUIRED")
        key, value = item
        if not isinstance(key, str) or not key or key in result:
            raise ContractError("UNIQUE_PACKET_IDENTITIES_REQUIRED")
        if numbers and (
            type(value) not in {int, float}
            or not math.isfinite(value)
            or value < 0
            or positive and value == 0
        ):
            raise ContractError("FINITE_PACKET_NUMBER_REQUIRED")
        result[key] = value
    return result


class GuardedDriver:
    """One frozen arm, or an explicit synthetic multi-scope mechanics fixture.

    Source provider interface:
      issues_at_open(at) -> tuple[SourceIssue, ...]
      on_completed_hour(ClosePacket) -> tuple[OwnerUpdate, ...]
      producer_for(pair, structure_id) -> actual V12 ContractProducer
      on_execution_receipt(ExecutionFeedback) -> None

    In research mode the certificate provider returns exact existing
    ProducerCertificates for this arm. Neither provider is auto-certified here.
    Readiness receipts are trusted harness artifacts as documented by precommit.
    """

    def __init__(
        self, repo, precommit, pipeline, source_provider, *, arm=None,
        certificate_provider=None, readiness_receipt=None, synthetic_certification=False,
    ):
        if type(synthetic_certification) is not bool:
            raise ContractError("EXPLICIT_SYNTHETIC_DISPOSITION_REQUIRED")
        if not isinstance(pipeline, PipelineV12):
            raise ContractError("EXACT_V12_GUARDED_PIPELINE_REQUIRED")
        for method in (
            "issues_at_open", "on_completed_hour", "producer_for", "on_execution_receipt"
        ):
            if not callable(getattr(source_provider, method, None)):
                raise ContractError("INJECTED_TYPED_SOURCE_PROVIDER_REQUIRED:" + method)
        if arm is not None and arm not in precommit.get("contract", {}).get("arms", ()):
            raise ContractError("ARM_NOT_IN_FIXED_PRECOMMIT")
        if synthetic_certification:
            if (isinstance(pipeline, ResearchPipeline)
                    or not pipeline.router.synthetic_fixture_execution):
                raise ContractError("SYNTHETIC_CERTIFICATION_REQUIRES_VISIBLE_FIXTURE_ROUTER")
        elif (
            arm is None or not isinstance(pipeline, ResearchPipeline)
            or not isinstance(pipeline.router, ResearchRouter)
            or pipeline.router.synthetic_fixture_execution
            or not callable(certificate_provider)
        ):
            raise ContractError("SEPARATE_RESEARCH_PIPELINE_ARM_AND_CERTIFICATE_PROVIDER_REQUIRED")
        self.repo, self.precommit = Path(repo).resolve(), copy.deepcopy(precommit)
        self.pipeline, self.source = pipeline, source_provider
        self.arm, self.synthetic = arm, synthetic_certification
        self.certificate_provider = certificate_provider
        self.readiness_receipt = copy.deepcopy(readiness_receipt)
        self.failed = False
        self.last_open = self.last_close = None
        self.open_prices = {}
        self.remaining_capacity = {}
        self.feedback = []
        self.equity = []
        self.diagnostics = []
        self._receipt_keys = set()
        self._entry_sources = {}
        self._source_snapshot = None
        self._frozen_payload_hash = precommit.get("precommit_sha256")
        kernel = pipeline.execution.portfolio.k
        if kernel.fills or kernel.positions or kernel.campaigns or pipeline.last_open is not None:
            raise ContractError("FRESH_GUARDED_EXECUTION_REQUIRED")
        if arm is not None:
            rate = precommit["contract"]["costs_round_trip"][arm.split("|")[1]] / 2
            if kernel.exit_cost_rate != rate:
                raise ContractError("FROZEN_ARM_COST_PARITY")
        self._assert_current(full=True)

    def _stat_sources(self):
        # Enumerate the exact recursive source set too: new/deleted files are drift.
        # No content reads on this event path; ctime/inode also detect replacement
        # with preserved size/mtime. Deliberate source rewrites are not authorized.
        paths = {PROTOCOL_PATH}
        for root in SOURCE_ROOTS:
            paths.update(p.relative_to(self.repo).as_posix()
                         for p in (self.repo / root).rglob("*.py"))
        snapshot = {}
        for relative in sorted(paths):
            path = _safe_source(self.repo, relative)
            info = path.stat()
            snapshot[relative] = (
                info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino, info.st_dev,
            )
        return snapshot

    def _assert_current(self, *, full=False):
        if self.failed:
            raise ContractError("DRIVER_FAILED_NO_AUTOMATIC_RETRY")
        payload = {k: v for k, v in self.precommit.items() if k != "precommit_sha256"}
        if (self.precommit.get("precommit_sha256") != self._frozen_payload_hash
                or config_hash(payload) != self._frozen_payload_hash):
            self.failed = True
            raise ContractError("FROZEN_PRECOMMIT_PAYLOAD_DRIFT")
        try:
            before = self._stat_sources()
        except (OSError, ValueError) as exc:
            self.failed = True
            verify_precommit(self.repo, self.precommit)
            raise ContractError("SOURCE_SNAPSHOT_UNAVAILABLE") from exc
        if self._source_snapshot is not None and before != self._source_snapshot:
            self.failed = True
            verify_precommit(self.repo, self.precommit)
            raise ContractError("SOURCE_SNAPSHOT_DRIFT_BEFORE_CALLBACK")
        if not self.synthetic:
            if (not isinstance(self.pipeline, ResearchPipeline)
                    or not isinstance(self.pipeline.router, ResearchRouter)
                    or self.pipeline.router.synthetic_fixture_execution):
                self.failed = True
                raise ContractError("NON_SYNTHETIC_RESEARCH_SCOPE_REQUIRED")
            scope = self.pipeline.router.scope
            scope.validate()
            if (
                scope.source_version_sha256 != self.precommit["source_version_sha256"]
                or scope.protocol_sha256 != self.precommit["source_hashes"][PROTOCOL_PATH]
            ):
                self.failed = True
                raise ContractError("RESEARCH_SCOPE_PRECOMMIT_VERSION_PARITY")
        if self.arm is not None:
            rate = self.precommit["contract"]["costs_round_trip"][self.arm.split("|")[1]] / 2
            if self.pipeline.execution.portfolio.k.exit_cost_rate != rate:
                self.failed = True
                raise ContractError("FROZEN_ARM_COST_PARITY")
        if not full:
            return
        integrity = verify_precommit(self.repo, self.precommit)
        if not integrity["valid"]:
            self.failed = True
            raise ContractError(
                "FROZEN_PRECOMMIT_VERSION_INVALID:" + ";".join(integrity["blockers"])
            )
        if not self.synthetic:
            # This is checked BEFORE source callbacks, fills, or economic outputs.
            require_ready(self.repo, self.precommit, self.readiness_receipt)
        if self._stat_sources() != before:
            self.failed = True
            raise ContractError("SOURCE_DRIFT_DURING_FULL_VERIFICATION")
        self._source_snapshot = before

    def _certificates(self, now):
        if self.synthetic:
            return
        grammar = self.arm.split("|")[0]
        certificates = self.certificate_provider(now, self.precommit, grammar)
        if not isinstance(certificates, tuple) or len(certificates) != 1:
            raise ContractError("EXACT_ARM_SOURCE_CERTIFICATE_REQUIRED")
        certificate = certificates[0]
        if not isinstance(certificate, ProducerCertificate):
            raise ContractError("TYPED_SOURCE_CERTIFICATE_REQUIRED")
        certificate.validate(self.pipeline.router.scope)
        if (certificate.grammar != grammar
                or self.pipeline.router.certificates.get(grammar) != certificate):
            raise ContractError("CERTIFICATE_PROVIDER_ROUTER_PARITY")

    def _bind(self, request, now):
        if (not isinstance(request, SourceIssue)
                or not isinstance(request.producer, ContractProducer)):
            raise ContractError("ACTUAL_V12_SOURCE_ISSUE_REQUIRED")
        issue, producer = request.issue, request.producer
        if not isinstance(issue, (Produced, LegacyIssue)):
            raise ContractError("SEALED_TYPED_ISSUE_REQUIRED_NOT_DICTIONARY")
        verify_issue(issue, producer.graph, now)
        if instant(issue.event["timestamp"]) != now:
            raise ContractError("EXACT_CURRENT_SOURCE_CHECKPOINT_REQUIRED")
        grammar = issue.event["system_id"]
        if grammar not in GRAMMARS:
            raise ContractError("UNBOUND_OR_CONTEXT_ONLY_GRAMMAR")
        if isinstance(issue, Produced) and producer.emitted.get(digest(issue)) != issue:
            raise ContractError("ACTUAL_SOURCE_EMITTED_ISSUE_REQUIRED")
        if self.arm is not None and grammar != self.arm.split("|")[0]:
            self.diagnostics.append((now, grammar, "NOT_THIS_PRECOMMITTED_ARM"))
            return None
        options = _pairs(request.options)
        allowed = {"valid_until", "session_end", "existing_campaign_id", "mode", "objectives"}
        if set(options) - allowed:
            raise ContractError("UNBOUND_SOURCE_BIND_OPTIONS")
        if isinstance(issue, Produced):
            if "mode" in options or "objectives" in options:
                raise ContractError("NATIVE_THESIS_MANAGEMENT_CANNOT_BE_OVERRIDDEN")
            envelope = self.pipeline.bind(
                issue, producer.prefix, request.state, request.context, **options
            )
        else:
            if issue.binding.grammar not in {GRAMMARS[3], GRAMMARS[5]}:
                raise ContractError("LEGACY_ROUTE_ONLY_CLASSICAL_OR_H1")
            if "mode" not in options or "objectives" not in options or "valid_until" not in options:
                raise ContractError("EXPLICIT_LEGACY_SOURCE_MANAGEMENT_REQUIRED")
            options["mode"] = Mode(options["mode"])
            envelope = self.pipeline.bind_legacy(
                issue, issue.binding, PendingSetup(issue.binding.structure_id), request.state,
                context=request.context, graph=producer.graph,
                stop_proof=issue.stop_proof, **options,
            )
        self._entry_sources[envelope.row["identity"]] = (producer, issue, envelope.binding)
        return envelope

    def _consume_capacity(self, initial, first_fill):
        remaining = {pair: Decimal(str(value)) for pair, value in initial.items()}
        for fill in self.pipeline.execution.portfolio.k.fills[first_fill:]:
            pair = fill["pair"]
            if pair not in remaining:
                raise ContractError("FILL_WITHOUT_SHARED_CAPACITY")
            remaining[pair] -= Decimal(str(fill["qty"])) * Decimal(str(fill["price"]))
            if remaining[pair] < 0:
                raise ContractError("SHARED_OPEN_CLOSE_CAPACITY_EXCEEDED")
        return {pair: float(value) for pair, value in remaining.items()}

    def _producer(self, pair, binding):
        producer = self.source.producer_for(pair, binding.structure_id)
        if not isinstance(producer, ContractProducer) or producer.prefix.pair != pair:
            raise ContractError("RECEIPT_ACTUAL_PRODUCER_OWNER_SOURCE_PARITY")
        # A thesis proof digest may deliberately differ from the raw prefix SHA.
        # Ownership is the exact registered sealed issue/guard, never a guessed SHA.
        matches = [(identity, issue) for identity, (registered, issue, issued_binding)
                   in self._entry_sources.items()
                   if registered is producer and issued_binding == binding]
        if not matches:
            raise ContractError("EXACT_ISSUED_OWNER_BINDING_REQUIRED")
        for identity, issue in matches:
            guard = self.pipeline.execution.source_guards.get(identity)
            if (guard is None or guard.issue != issue or guard.binding != binding
                    or guard.graph is not producer.graph):
                raise ContractError("EXACT_STORED_SOURCE_GUARD_REQUIRED")
            if isinstance(issue, Produced):
                if (producer.emitted.get(digest(issue)) != issue
                        or issue.thesis.structure_id != binding.structure_id
                        or issue.thesis.source_sha256 != binding.source_sha256
                        or issue.thesis.grammar != binding.grammar):
                    raise ContractError("EXACT_PRODUCER_ISSUED_THESIS_REQUIRED")
            elif issue.binding != binding:
                raise ContractError("EXACT_PRODUCER_ISSUED_LEGACY_BINDING_REQUIRED")
            verify_issue(issue, producer.graph, self.last_open)
        return producer

    def _feedback(self, now):
        execution = self.pipeline.execution
        kernel = execution.portfolio.k
        for cid, binding in tuple(execution.campaign_owner.items()):
            campaign = kernel.campaigns[cid]
            alive = any(p["campaign_id"] == cid for p in kernel.positions.values())
            if cid in execution.staged_campaigns and (cid, "STAGE1") not in self._receipt_keys:
                producer = self._producer(campaign.pair, binding)
                self.pipeline.acknowledge_wyckoff_stage(producer, binding.structure_id, now, cid)
                receipt = producer.stage_campaign_receipts[binding.structure_id]
                self._publish_feedback(cid, binding, now, receipt, "STAGE1")
            if (binding.grammar == GRAMMARS[2] and not alive
                    and (cid, "CLOSED") not in self._receipt_keys):
                producer = self._producer(campaign.pair, binding)
                self.pipeline.acknowledge_harmonic_completion(
                    producer, binding.structure_id, binding.owner, now, cid
                )
                receipt = producer.graph.nodes[digest((cid, binding.owner, now, "CLOSED"))].evidence
                self._publish_feedback(cid, binding, now, receipt, "CLOSED")

    def _publish_feedback(self, cid, binding, now, receipt, kind):
        if instant(receipt.available_at) != now:
            raise ContractError("ACTUAL_EXECUTION_RECEIPT_CLOCK_REQUIRED")
        feedback = ExecutionFeedback(
            cid, binding.grammar, binding.structure_id, binding.owner, now, receipt
        )
        self._receipt_keys.add((cid, kind))
        self.feedback.append(feedback)
        self.source.on_execution_receipt(feedback)

    def _snapshot(self, now, marks, observation):
        kernel = self.pipeline.execution.portfolio.k
        snapshot = kernel.snapshot(lambda pair, _at: marks.get(pair), now)
        if not snapshot["valid"]:
            raise ContractError("CURRENT_ALL_ASSET_EQUITY_MARKS_REQUIRED")
        self.equity.append({
            "arm": self.arm, "time": now, "observation": observation,
            "equity": snapshot["equity"], "cash": kernel.cash, "gross": snapshot["gross"],
            "stop_risk": snapshot["open_stop_risk"],
            "risk_limits_pass": current_mtm_limits_ok(snapshot), "mark_coverage_complete": True,
        })

    def on_open(self, packet):
        try:
            self._assert_current()
            if not isinstance(packet, OpenPacket):
                raise ContractError("OPEN_ONLY_PACKET_REQUIRED_NO_CURRENT_HLCV")
            now = instant(packet.at)
            if now.year not in {2022, 2023}:
                raise ContractError("PROTECTED_OR_UNAUTHORIZED_PERIOD")
            last_open = instant(self.precommit["contract"]["outputs"]["terminal_coverage"][
                "last_permitted_execution_open"
            ])
            if now > last_open:
                raise ContractError("MISSING_TERMINAL_HOUR_NOT_EXECUTABLE")
            if self.last_open is not None and (now <= self.last_open or now != self.last_close):
                raise ContractError("CHRONOLOGICAL_OPEN_REQUIRES_PREVIOUS_COMPLETED_HOUR")
            prices = _pairs(packet.prices, numbers=True, positive=True)
            capacity = _pairs(packet.capacity, numbers=True)
            if not set(prices) <= capacity.keys():
                raise ContractError("EXPLICIT_SHARED_CAPACITY_REQUIRED")
            self._certificates(now)
            requests = self.source.issues_at_open(now)
            if not isinstance(requests, tuple):
                raise ContractError("FROZEN_SOURCE_ISSUE_BATCH_REQUIRED")
            envelopes = tuple(
                env for request in requests if (env := self._bind(request, now)) is not None
            )
            cursor = len(self.pipeline.execution.portfolio.k.fills)
            selected, denied = self.pipeline.on_open(
                now, prices, capacity, envelopes, research_authorized=True
            )
            self.remaining_capacity = self._consume_capacity(capacity, cursor)
            self.last_open = now
            self.open_prices = prices
            self._feedback(now)
            self._snapshot(now, prices, "OPEN")
            return selected, denied
        except Exception:
            self.failed = True
            raise

    def _owner_updates(self, updates, now):
        if not isinstance(updates, tuple):
            raise ContractError("FROZEN_SOURCE_OWNER_UPDATES_REQUIRED")
        bars, pivots, objectives, failures = {}, {}, {}, {}
        execution = self.pipeline.execution
        for update in updates:
            if (not isinstance(update, OwnerUpdate)
                    or not isinstance(update.producer, ContractProducer)
                    or not isinstance(update.pivots, tuple)
                    or not isinstance(update.objectives, tuple)
                    or update.structure_id in bars):
                raise ContractError("UNIQUE_TYPED_OWNER_UPDATE_REQUIRED")
            ids = [tid for tid, p in execution.portfolio.k.positions.items()
                   if execution.managers[tid].binding.structure_id == update.structure_id
                   and p["episode"]["pair"] == update.producer.prefix.pair]
            if not ids:
                raise ContractError("OWNER_UPDATE_WITHOUT_CURRENT_CAMPAIGN")
            binding = execution.managers[ids[0]].binding
            producer = self._producer(update.producer.prefix.pair, binding)
            if producer is not update.producer:
                raise ContractError("OWNER_UPDATE_ACTUAL_PRODUCER_PARITY")
            if update.bar is not None:
                producer.prefix.require_bar(update.bar, now)
                if instant(update.bar.end) != now or update.bar.timeframe != binding.timeframe:
                    raise ContractError("EXACT_COMPLETED_OWNER_DEGREE_REQUIRED")
            elif update.pivots or update.objectives:
                raise ContractError("SOURCE_OWNER_BAR_REQUIRED")
            for pivot in update.pivots:
                evidence = producer.graph.nodes.get(pivot.event_id)
                if evidence is None or not isinstance(evidence.evidence.value, Point):
                    raise ContractError("ACTUAL_CONFIRMED_SOURCE_PIVOT_REQUIRED")
                point = evidence.evidence.value
                producer.prefix.require_point(point, now)
                if (pivot.structure_id != binding.structure_id or point.degree != binding.timeframe
                        or (pivot.kind, pivot.price, pivot.observed_at, pivot.available_at)
                        != (point.kind, point.price, point.observed_at, point.available_at)):
                    raise ContractError("OWNER_PIVOT_SOURCE_PARITY")
            for objective in update.objectives:
                node = producer.graph.nodes.get(objective.event_id)
                if node is None:
                    raise ContractError("SOURCE_OWNED_OBJECTIVE_REQUIRED")
                producer.graph.require(node.evidence, now)
                if (objective.structure_id != binding.structure_id
                        or objective.source_sha256 != node.evidence.source_sha256
                        or objective.available_at != node.evidence.available_at
                        or node.evidence.value not in (objective, objective.price)):
                    raise ContractError("OWNER_OBJECTIVE_SOURCE_PARITY")
            bars[update.structure_id] = update.bar
            pivots[update.structure_id] = update.pivots
            objectives[update.structure_id] = update.objectives
            if update.failure is not None:
                failures[update.structure_id] = self.pipeline.source_failure(
                    ids[0], update.failure, producer.graph, now
                )
        return bars, pivots, objectives, failures

    def on_completed_hour(self, packet):
        try:
            self._assert_current()
            if not isinstance(packet, ClosePacket) or self.last_open is None:
                raise ContractError("COMPLETED_PACKET_REQUIRES_OPEN")
            now = self.last_open + timedelta(hours=1)
            if now.year not in {2022, 2023} or self.last_close == now:
                raise ContractError("PROTECTED_OR_REPEATED_COMPLETED_HOUR")
            bars = _pairs(packet.bars)
            volumes = _pairs(packet.volumes, numbers=True)
            if set(bars) != set(volumes):
                raise ContractError("EXACT_COMPLETED_VOLUME_COVERAGE_REQUIRED")
            for pair, bar in bars.items():
                if not isinstance(bar, CompletedBar):
                    raise ContractError("ACTUAL_TYPED_COMPLETED_BAR_REQUIRED")
                bar.validate()
                if (bar.timeframe != "1H" or instant(bar.start) != self.last_open
                        or instant(bar.end) != now):
                    raise ContractError("EXACT_COMPLETED_EXECUTION_HOUR_REQUIRED")
                if pair not in self.open_prices or bar.open != self.open_prices[pair]:
                    raise ContractError("ACTUAL_OPEN_COMPLETED_BAR_PARITY")
            held = {p["episode"]["pair"]
                    for p in self.pipeline.execution.portfolio.k.positions.values()}
            if not held <= bars.keys():
                raise ContractError("MISSING_HELD_COMPLETED_HOUR")
            updates = self.source.on_completed_hour(packet)
            owner_bars, pivots, objectives, failures = self._owner_updates(updates, now)
            cursor = len(self.pipeline.execution.portfolio.k.fills)
            self.pipeline.on_completed_hour(
                bars, owner_bars=owner_bars, pivots=pivots, objectives=objectives,
                native_failures=failures, capacities=self.remaining_capacity,
            )
            self.remaining_capacity = self._consume_capacity(self.remaining_capacity, cursor)
            self.last_close = now
            self._feedback(now)
            self._snapshot(now, {pair: bar.close for pair, bar in bars.items()}, "CLOSE")
        except Exception:
            self.failed = True
            raise

    def outputs(self):
        """Return copies of this consumer's ledgers only after another version check."""
        self._assert_current(full=True)
        execution = self.pipeline.execution
        return copy.deepcopy({
            "arm": self.arm, "source_version_sha256": self.precommit["source_version_sha256"],
            "precommit_sha256": self.precommit["precommit_sha256"],
            "disposition": "SYNTHETIC_ONLY_NOT_ECONOMIC_EVIDENCE" if self.synthetic
                           else "ALREADY_EXPOSED_EXPLORATORY_RESEARCH",
            "fills": execution.portfolio.k.fills,
            "decisions": [*self.pipeline.ledger, *execution.decision_ledger],
            "campaigns": execution.portfolio.k.campaigns,
            "equity": self.equity, "feedback": self.feedback, "diagnostics": self.diagnostics,
            "remaining_capacity": self.remaining_capacity,
            "terminal_coverage": {
                **self.precommit["contract"]["outputs"]["terminal_coverage"],
                "last_observed_completed_close": self.last_close,
                "bounded_terminal_close_observed": self.last_close == instant(
                    self.precommit["contract"]["outputs"]["terminal_coverage"][
                        "last_permitted_completed_close"
                    ]
                ),
            },
            "dow": "CONTEXT_ONLY", "production_authorized": False,
            "historical_exchange_rules_closed": False, "independent_review_pass": False,
        })
