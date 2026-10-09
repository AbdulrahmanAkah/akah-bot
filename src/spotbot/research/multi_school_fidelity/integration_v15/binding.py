"""Same guarded binding for all nine, with historical admission-clock verification.

Expiry of an entry-only PIT/context lease is not loss of historical ownership.
Payload mutation and explicit revocation remain hard failures. Live entry/add
claims are still verified at actual current kernel admission.
"""
from ..integration_v13.guarded_driver import SourceIssue, _pairs
from ..integration_v12.producers import ContractProducer
from ..integration_v11.contracts import Produced, LegacyIssue, verify_issue
from ..school_contract_common_v8 import digest
from ..structural_lifecycle_v6 import Mode, PendingSetup, instant, ContractError, CL, H1, DO
from .authority import funded

def bind_request(driver, request, now):
    if not isinstance(request, SourceIssue) or not isinstance(request.producer, ContractProducer):
        raise ContractError("ACTUAL_V12_SOURCE_ISSUE_REQUIRED")
    issue, producer = request.issue, request.producer
    if not isinstance(issue, (Produced, LegacyIssue)):
        raise ContractError("SEALED_TYPED_ISSUE_REQUIRED")
    verify_issue(issue, producer.graph, now)
    if instant(issue.event["timestamp"]) != now:
        raise ContractError("EXACT_CURRENT_SOURCE_CHECKPOINT_REQUIRED")
    grammar = funded(issue.event["system_id"])
    if isinstance(issue, Produced) and producer.emitted.get(digest(issue)) != issue:
        raise ContractError("ACTUAL_SOURCE_EMITTED_ISSUE_REQUIRED")
    if driver.arm is not None and grammar != driver.arm.split("|")[0]:
        driver.diagnostics.append((now, grammar, "NOT_THIS_PRECOMMITTED_ARM"))
        return None
    options = _pairs(request.options)
    if set(options) - {"valid_until", "session_end", "existing_campaign_id", "mode", "objectives"}:
        raise ContractError("UNBOUND_SOURCE_BIND_OPTIONS")
    if isinstance(issue, Produced):
        if "mode" in options or "objectives" in options:
            raise ContractError("NATIVE_MANAGEMENT_CANNOT_BE_OVERRIDDEN")
        envelope = driver.pipeline.bind(issue, producer.prefix, request.state, request.context, **options)
    else:
        if issue.binding.grammar not in {CL, H1, DO}:
            raise ContractError("UNBOUND_LEGACY_OWNER")
        if not {"mode", "objectives", "valid_until"} <= options.keys():
            raise ContractError("EXPLICIT_LEGACY_MANAGEMENT_REQUIRED")
        options["mode"] = Mode(options["mode"])
        envelope = driver.pipeline.bind_legacy(issue, issue.binding, PendingSetup(issue.binding.structure_id),
            request.state, context=request.context, graph=producer.graph, stop_proof=issue.stop_proof, **options)
    driver._entry_sources[envelope.row["identity"]] = (producer, issue, envelope.binding)
    return envelope

def registered_producer(driver, pair, binding):
    producer = driver.source.producer_for(pair, binding.structure_id)
    if not isinstance(producer, ContractProducer) or producer.prefix.pair != pair:
        raise ContractError("ACTUAL_PRODUCER_OWNER_SOURCE_PARITY")
    matches = [(identity, issue) for identity, (registered, issue, saved) in driver._entry_sources.items()
               if registered is producer and saved == binding]
    if not matches:
        raise ContractError("EXACT_ISSUED_OWNER_BINDING_REQUIRED")
    for identity, issue in matches:
        guard = driver.pipeline.execution.source_guards.get(identity)
        if guard is None or guard.issue != issue or guard.binding != binding or guard.graph is not producer.graph:
            raise ContractError("EXACT_STORED_SOURCE_GUARD_REQUIRED")
        if isinstance(issue, Produced) and (producer.emitted.get(digest(issue)) != issue
                or issue.thesis.source_sha256 != binding.source_sha256
                or issue.thesis.structure_id != binding.structure_id or issue.thesis.grammar != binding.grammar):
            raise ContractError("EXACT_PRODUCER_ISSUED_THESIS_REQUIRED")
        if isinstance(issue, LegacyIssue) and issue.binding != binding:
            raise ContractError("EXACT_PRODUCER_LEGACY_BINDING_REQUIRED")
        verify_issue(issue, producer.graph, instant(issue.event["timestamp"]))
    return producer
