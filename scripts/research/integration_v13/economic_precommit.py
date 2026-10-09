"""Source-only V13 economic precommit and fail-closed implementation readiness.

All functions return in-memory metadata. Nothing writes a freeze, reads market
rows/results, imports a proposed driver, or executes economics. A readiness
receipt belongs to a trusted synthetic harness; names, hashes and receipt shape
alone do not certify school doctrine or historical coverage.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from spotbot.research.multi_school_fidelity.gate3_precommit import config_hash
from spotbot.research.multi_school_fidelity.gate3_precommit import specification as qualification

TASK = "AKAH_PACKAGE2_PACKAGE3_GUARDED_HISTORICAL_RESEARCH_CLOSURE_V13"
PROTOCOL_PATH = "governance/research_readiness_v13/research_protocol.json"
GRAMMARS = (
    "FS_WYCKOFF_FRESH_CAUSE_V8",
    "FS_ICT_SESSION_OWNER_V8",
    "FS_HARMONIC_CAUSAL_ADAPTATION_V8",
    "FS_CLASSICAL_FULL_LONG",
    "FS_ELLIOTT_PROOF_RESUMPTION_V8",
    "HYB_MARKUP_CONTINUATION",
    "HYB_FAILED_AUCTION_HTF_OWNER_V8",
    "HYB_CORRECTIVE_PROOF_LOCATION_V9",
)
COSTS = {"1X": 0.0025, "2X": 0.005}
PERIOD = ["2022-01-01T00:00:00Z", "2024-01-01T00:00:00Z"]
SOURCE_ROOTS = (
    "src/spotbot",
    "scripts/research/integration_v13",
    "tests/research/integration_v13",
)
REQUIRED_SOURCES = (
    "src/spotbot/research/multi_school_fidelity/gate3_precommit.py",
    "src/spotbot/research/multi_school_fidelity/qualification_uncertainty.py",
    "src/spotbot/research/multi_school_fidelity/gate3_market_v3.py",
    "src/spotbot/research/multi_school_fidelity/full_replay_v5.py",
    "src/spotbot/research/multi_school_fidelity/integration_v11/contracts.py",
    "src/spotbot/research/multi_school_fidelity/integration_v11/execution.py",
    "src/spotbot/research/multi_school_fidelity/integration_v12/pipeline.py",
    "src/spotbot/research/multi_school_fidelity/integration_v12/producers.py",
    "scripts/research/integration_v13/economic_precommit.py",
    "tests/research/integration_v13/test_economic_precommit.py",
    PROTOCOL_PATH,
)
CHECKS = (
    "typed_semantic_source_generation",
    "immutable_semantic_generation_not_fixture_injection",
    "actual_source_provider_and_bounded_historical_scheduling",
    "pit_pair_checkpoint_effective_interval",
    "exact_v12_emission_and_h3_parent_seals",
    "actual_kernel_source_guard_after_preview",
    "chronological_open_close_and_owner_degree",
    "no_future_or_protected_rows",
    "shared_capacity_and_current_all_asset_marks",
    "wyckoff_actual_first_fill_and_original_b0",
    "harmonic_actual_type_i_closure_for_type_ii",
    "source_revocation_and_no_resurrection",
    "separate_research_scope_no_synthetic_market_switch",
    "unsupported_forms_explicit_abstention",
    "dow_context_only",
    "cash_fees_terminal_mtm_and_cost_reconciliation",
    "complete_calendar_and_fixed_claim_family",
    "no_v5_replay_fallback",
)

# A callable adapter accepting externally supplied Known objects is not a
# producer definition for those objects. These literal authority gaps may not
# be concealed by a green packet-consumer or fixture-injection test.
SEMANTIC_AUTHORITIES = (
    "WYCKOFF_PS_SC_ST_DOWNWARD_OBJECTIVE",
    "WYCKOFF_MARKET_RS_AND_PRIOR_MARKUP",
    "WYCKOFF_DISTRIBUTION_OWNER_EVENTS",
    "H1_ACTUAL_MARKUP_PARENT",
    "DOW_COMPLETE_PIT_CONTEXT_AND_ROUTER",
)


class ReadinessError(ValueError):
    """No economic access is authorized by a missing or stale precommit."""


def output_contract():
    """Schemas and accounting meanings frozen before any economic observations."""
    return {
        "campaigns": [
            "campaign_id",
            "grammar",
            "pair",
            "owner",
            "structure_id",
            "source_sha256",
            "first_entry_at",
            "final_exit_at",
            "closed",
            "B0",
            "committed_risk",
            "add_count",
            "buy_outlay_including_fees",
            "net_sale_proceeds",
            "terminal_quantity",
            "terminal_mark",
            "terminal_mtm",
            "net_including_fees_and_terminal_mtm",
        ],
        "decisions": [
            "arm",
            "time",
            "known_at",
            "applies_from",
            "identity",
            "campaign_id",
            "owner",
            "structure_id",
            "source_sha256",
            "emission_id",
            "required_evidence_ids",
            "action",
            "admitted",
            "reason",
            "mode",
            "hard_stop_before",
            "hard_stop_after",
        ],
        "fills": [
            "arm",
            "time",
            "execution_phase",
            "side",
            "campaign_id",
            "pair",
            "identity",
            "qty",
            "price",
            "fee",
            "cash_delta",
            "reason",
        ],
        "hourly_equity": [
            "arm",
            "time",
            "observation",
            "equity",
            "cash",
            "gross",
            "stop_risk",
            "risk_limits_pass",
            "mark_coverage_complete",
        ],
        "daily_equity": ["arm", "date", "equity", "daily_net_mtm_log_return"],
        "cost_reconciliation": {
            "fields": [
                "arm",
                "cash_ledger_pass",
                "campaign_attribution_pass",
                "fees_pass",
                "terminal_mtm_pass",
                "risk_execution_pass",
                "coverage_complete",
            ],
            "cash": "initial_equity + sum(fill.cash_delta) == terminal_cash",
            "equity": "cash + current holdings marked at the same checkpoint",
            "campaign_net": "net sales + terminal MTM - buy outlay, including all legs/fees",
            "numerical_policy": "Inherited V5 CASH_LEDGER_PARITY/CAMPAIGN_PARITY abs_tol=1e-5",
            "terminal": (
                "Last permitted completed CLOSE MTM at 23UTC, missing terminal 1H disclosed; "
                "no fabricated liquidation or liquidation fee"
            ),
            "fees": "Each fill uses half the frozen scenario round-trip rate",
        },
        "annual": ["grammar", "scenario", "year", "net", "mdd", "risk_execution_pass"],
        "asset_attribution": ["arm", "pair", "net_including_fees_and_terminal_mtm"],
        "concentration": (
            "Literal inherited qualification.concentration; 2X campaign/asset deletion"
        ),
        "uncertainty": "Literal inherited qualification.uncertainty; full paired calendar family",
        "risk_audit": ["arm", "time", "limit", "observed", "passed", "reason"],
        "execution_audit": ["arm", "time", "check", "passed", "source_ids", "reason"],
        "unsupported_forms": ["grammar", "form", "count", "reason", "source_ids"],
        "qualification": ["grammar", "hard_rules_pass", "uncertainty_status", "status"],
        "empty_arms": "Retain schema, zero activity and all calendar cash days; never drop claims",
        "daily_calendar": (
            "Every UTC day of 2022/2023; previous year terminal equity carries forward"
        ),
        "capacity": "One completed trailing-24h budget shared by buys/sells and OPEN/CLOSE",
        "failure": "Incomplete accounting/coverage => TECHNICAL_FAIL, no scientific conclusion",
        "terminal_coverage": {
            "source_row_timestamp": "COMPLETED_CLOSE_NOT_OPEN",
            "last_permitted_completed_close": "2023-12-31T23:00:00Z",
            "last_permitted_execution_open": "2023-12-31T22:00:00Z",
            "missing_terminal_hour": ["2023-12-31T23:00:00Z", "2024-01-01T00:00:00Z"],
            "disclosure": "Missing terminal 1H explicitly; no invented terminal mark",
            "protected_close_hlc_access": False,
            "full_2023_terminal_hour_coverage": False,
        },
    }


def specification():
    inherited = qualification()
    return {
        "task_id": TASK,
        "version": 13,
        "period": list(PERIOD),
        "warmup_start": "2021-09-01T00:00:00Z",
        "grammars": list(GRAMMARS),
        "arms": [f"{grammar}|{scenario}" for grammar in GRAMMARS for scenario in COSTS],
        "costs_round_trip": dict(COSTS),
        "primary_claim_family": list(GRAMMARS),
        "claims": {grammar: {f"{grammar}|2X": 1.0} for grammar in GRAMMARS},
        "claim_family_must_not_shrink": True,
        "qualification_literal": inherited,
        "qualification_binding": {
            "scope": "V13 grammar/claim registry supersedes legacy scope IDs only",
            "hard_rules_concentration_uncertainty_roles": "INHERIT_LITERAL_UNCHANGED",
            "qualification_function": "gate3_market_v3.qualify",
            "uncertainty_function": "qualification_uncertainty.evaluate_calendar_claims",
            "unexecuted_role_interventions": "NO_ALPHA_OR_RISK_ROLE_CLAIM",
        },
        "quantity": {
            "implementation": "full_replay_v5.ContinuousRule",
            "quantity_floor": "1e-12",
            "minimum_entry_usdt": 50,
            "price": "IDENTITY_CONTINUOUS_PRICE_EXPERIMENT",
            "historical_exchange_rules": "EXCLUDED_BY_USER_NOT_CLOSED",
        },
        "review": "WAIVED_FOR_EXPERIMENT_BY_USER_NOT_INDEPENDENT_PASS",
        "dow": {
            "role": "CONTEXT_ONLY",
            "economic_arm": False,
            "reason": "No source-owned executable entry/stop route",
        },
        "period_disposition": "ALREADY_EXPOSED_EXPLORATORY_RESEARCH_NOT_FRESH_VALIDATION",
        "risk": inherited["risk"],
        "capital_capacity": inherited["capital_capacity"],
        "selector": "Inherited feasibility/ADD priority/FIFO/capacity/digest",
        "finite_geometry": "Source-owned final objective net-positive after both fees",
        "trend_objectives": "SOURCE_OWNED_CHECKPOINTS_NOT_LIQUIDATION",
        "model_fit": False,
        "threshold_search": False,
        "production_authorized": False,
        "historical_exchange_executability_certified": False,
        "independent_review_pass": False,
        "economic_access": "ONLY_AFTER_REQUIRE_READY; THIS_MODULE_NEVER_EXECUTES_ECONOMICS",
        "v5_replay_fallback": False,
        "outputs": output_contract(),
        "readiness_checks": list(CHECKS),
    }


def _safe_source(repo, relative):
    if not isinstance(relative, str) or "\\" in relative:
        raise ReadinessError("CANONICAL_RELATIVE_SOURCE_PATH_REQUIRED")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        raise ReadinessError("SOURCE_PATH_OUTSIDE_CONTRACT")
    allowed = relative == PROTOCOL_PATH or (
        path.suffix == ".py" and any(path.is_relative_to(Path(root)) for root in SOURCE_ROOTS)
    )
    target = (repo / path).resolve()
    if not allowed or not target.is_relative_to(repo.resolve()):
        raise ReadinessError("SOURCE_PATH_OUTSIDE_CONTRACT")
    return target


def source_hashes(repo):
    """Recursive Python sources plus the protocol; never data/cache/result files."""
    repo = Path(repo).resolve()
    paths = {PROTOCOL_PATH}
    for relative in SOURCE_ROOTS:
        root = _safe_source(repo, relative + "/__init__.py").parent
        if root.is_dir():
            paths.update(path.relative_to(repo).as_posix() for path in root.rglob("*.py"))
    return {
        relative: hashlib.sha256(_safe_source(repo, relative).read_bytes()).hexdigest().upper()
        for relative in sorted(paths)
        if _safe_source(repo, relative).is_file()
    }


def _protocol_errors(protocol):
    expected = {
        "task_id": TASK,
        "period": PERIOD,
        "warmup_start": "2021-09-01T00:00:00Z",
        "costs_roundtrip": COSTS,
        "review_disposition": "WAIVED_FOR_EXPERIMENT_BY_USER_NOT_INDEPENDENT_PASS",
        "historical_exchange_rules": "EXCLUDED_BY_USER_NOT_CLOSED",
        "models_or_threshold_search": False,
        "old_versions_mutated": False,
        "2024_rows_access": False,
        "2025_rows_access": False,
        "production": False,
        "research_branch_push": False,
    }
    return [
        f"PROTOCOL_PARITY:{key}"
        for key, value in expected.items()
        if type(protocol.get(key)) is not type(value) or protocol.get(key) != value
    ]


def build_precommit(repo):
    """Prepare a reviewable freeze payload, in memory, even when readiness is blocked."""
    repo = Path(repo).resolve()
    protocol = json.loads(_safe_source(repo, PROTOCOL_PATH).read_text(encoding="utf-8-sig"))
    errors = _protocol_errors(protocol)
    if errors:
        raise ReadinessError(";".join(errors))
    payload = {"contract": specification(), "source_hashes": source_hashes(repo)}
    payload["source_version_sha256"] = config_hash(payload["source_hashes"])
    payload["precommit_sha256"] = config_hash(payload)
    return payload


def _source_callable(repo, binding, frozen, *, tests=False):
    """Resolve an exact source callable; presence never certifies its behavior."""
    if not isinstance(binding, Mapping):
        return None
    relative, symbol = binding.get("path"), binding.get("symbol")
    if not isinstance(relative, str) or not isinstance(symbol, str):
        return None
    root = ("tests/research/integration_v13/" if tests
            else "src/spotbot/research/multi_school_fidelity/integration_v13/")
    if not relative.startswith(root):
        return None
    if binding.get("sha256") != frozen.get(relative):
        return None
    try:
        tree = ast.parse(_safe_source(repo, relative).read_text(encoding="utf-8-sig"))
    except (OSError, SyntaxError, ReadinessError):
        return None
    node = tree
    for part in symbol.split("."):
        node = next(
            (
                item
                for item in getattr(node, "body", ())
                if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == part
            ),
            None,
        )
        if node is None:
            return None
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    return node


def _implemented_symbol(repo, binding, frozen):
    """Concrete implementation existence only; requires a trusted harness too."""
    node = _source_callable(repo, binding, frozen)
    if node is None:
        return False
    meaningful = [
        item
        for item in node.body
        if not (
            isinstance(item, ast.Pass)
            or isinstance(item, ast.Expr)
            and isinstance(item.value, ast.Constant)
        )
    ]
    # A method that only raises/returns a sentinel is not a implemented producer/driver.
    return (
        bool(meaningful)
        and not all(isinstance(item, ast.Raise) for item in meaningful)
        and any(isinstance(item, ast.Call) for item in ast.walk(node))
    )


def _synthetic_test_symbol(repo, binding, frozen):
    node = _source_callable(repo, binding, frozen, tests=True)
    if node is None or not node.name.startswith("test_"):
        return False
    # Resolving a test name and its assertions is not evidence that it ran.
    # Execution status remains the trusted harness's responsibility.
    return any(isinstance(item, ast.Assert) for item in ast.walk(node))


def verify_precommit(repo, precommit):
    """Source/protocol/contract integrity only; never economic readiness by itself."""
    repo = Path(repo).resolve()
    blockers = []
    if not isinstance(precommit, Mapping):
        return {
            "valid": False,
            "current_source_hashes": {},
            "blockers": ["PRECOMMIT_REQUIRED"],
        }
    payload = {key: value for key, value in precommit.items() if key != "precommit_sha256"}
    try:
        if config_hash(payload) != precommit.get("precommit_sha256"):
            blockers.append("PRECOMMIT_HASH_DRIFT")
        if config_hash(precommit.get("contract")) != config_hash(specification()):
            blockers.append("FIXED_ECONOMIC_CONTRACT_DRIFT")
        current = source_hashes(repo)
        if current != precommit.get("source_hashes"):
            blockers.append("RECURSIVE_SOURCE_HASH_DRIFT")
        if config_hash(current) != precommit.get("source_version_sha256"):
            blockers.append("SOURCE_VERSION_HASH_DRIFT")
        blockers.extend(
            f"REQUIRED_SOURCE_MISSING:{path}" for path in REQUIRED_SOURCES if path not in current
        )
        protocol = json.loads(_safe_source(repo, PROTOCOL_PATH).read_text(encoding="utf-8-sig"))
        blockers.extend(_protocol_errors(protocol))
    except (OSError, ValueError, TypeError) as exc:
        blockers.append(f"SOURCE_OR_PROTOCOL_INVALID:{type(exc).__name__}")
        current = {}
    return {"valid": not blockers, "blockers": blockers, "current_source_hashes": current}


def readiness_gate(repo, precommit, receipt=None):
    """Verify a trusted implementation-test receipt, never a market/fidelity certificate.

    Receipt binds each generator and driver entrypoint to exact source bytes and
    named synthetic test nodes. It must be produced by the package test harness,
    not by setting ready=True. Receipt authenticity is the enclosing governed
    harness's responsibility, just as V12 trusts its source graph infrastructure.
    """
    repo = Path(repo).resolve()
    integrity = verify_precommit(repo, precommit)
    blockers = list(integrity["blockers"])
    current = integrity.get("current_source_hashes", {})
    if not isinstance(precommit, Mapping):
        precommit = {}
    if not isinstance(receipt, Mapping):
        blockers.extend(
            (
                "ACTUAL_TYPED_SEMANTIC_PRODUCER_BINDINGS_MISSING",
                "CURRENT_CHRONOLOGICAL_GUARDED_DRIVER_MISSING",
                "SOURCE_BOUND_SYNTHETIC_READINESS_RECEIPT_MISSING",
            )
        )
    else:
        expected = {
            "task_id": TASK,
            "source_version_sha256": precommit.get("source_version_sha256"),
            "protocol_sha256": current.get(PROTOCOL_PATH),
            "contract_sha256": config_hash(specification()),
            "scope": "SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION",
            "market_rows_read": False,
            "pnl_read": False,
            "economic_replay_executed": False,
            "network_access": False,
            "fixture_injection_is_generator_evidence": False,
            "historical_certification": False,
        }
        for key, value in expected.items():
            if type(receipt.get(key)) is not type(value) or receipt.get(key) != value:
                blockers.append(f"READINESS_RECEIPT_PARITY:{key}")
        producers = receipt.get("producers")
        if not isinstance(producers, Mapping) or set(producers) != set(GRAMMARS):
            blockers.append("COMPLETE_TYPED_SEMANTIC_PRODUCER_BINDINGS_REQUIRED")
            producers = {}
        for grammar in GRAMMARS:
            binding = producers.get(grammar)
            if not _implemented_symbol(repo, binding, current):
                blockers.append(f"ACTUAL_TYPED_PRODUCER_MISSING:{grammar}")
        driver = receipt.get("driver")
        if not _implemented_symbol(repo, driver, current):
            blockers.append("CURRENT_CHRONOLOGICAL_GUARDED_DRIVER_MISSING")
        provider, scheduler = receipt.get("source_provider"), receipt.get("scheduler")
        if not _implemented_symbol(repo, provider, current):
            blockers.append("ACTUAL_SEMANTIC_SOURCE_PROVIDER_MISSING")
        if not _implemented_symbol(repo, scheduler, current):
            blockers.append("BOUNDED_HISTORICAL_SCHEDULER_MISSING")
        bindings = dict(producers, driver=driver, source_provider=provider, scheduler=scheduler)
        authorities = receipt.get("semantic_authorities", {})
        if not isinstance(authorities, Mapping):
            authorities = {}
        for authority in SEMANTIC_AUTHORITIES:
            bound = authorities.get(authority)
            if (not isinstance(bound, Mapping)
                    or bound.get("status") != "SOURCE_DEFINED_END_TO_END_TESTED"
                    or not _implemented_symbol(repo, bound.get("producer"), current)
                    or not _synthetic_test_symbol(repo, bound.get("test"), current)):
                blockers.append(f"SEMANTIC_SOURCE_AUTHORITY_UNRESOLVED:{authority}")
        proofs = receipt.get("checks", {})
        if not isinstance(proofs, Mapping) or set(proofs) != set(CHECKS):
            blockers.append("COMPLETE_SYNTHETIC_READINESS_CHECKS_REQUIRED")
            proofs = {}
        for check in CHECKS:
            proof = proofs.get(check)
            # All generators, provider, scheduler AND driver need harness coverage;
            # a boolean or old-version passing test is never enough.
            if not isinstance(proof, Mapping) or proof.get("status") != "PASS":
                blockers.append(f"SYNTHETIC_READINESS_NOT_PROVEN:{check}")
                continue
            if proof.get("evidence_kind") != "TRUSTED_SOURCE_IMPLEMENTATION_SYNTHETIC_RUN":
                blockers.append(f"TRUSTED_IMPLEMENTATION_RUN_REQUIRED:{check}")
            if check in {
                "typed_semantic_source_generation",
                "immutable_semantic_generation_not_fixture_injection",
            } and proof.get("coverage") != "ACTUAL_IMMUTABLE_SEMANTIC_GENERATION":
                blockers.append(f"ACTUAL_SEMANTIC_GENERATION_EVIDENCE_REQUIRED:{check}")
            tests = proof.get("tests")
            covered = proof.get("bindings")
            if not isinstance(tests, list) or not tests or covered != bindings:
                blockers.append(f"SYNTHETIC_COMPONENT_BINDING_MISSING:{check}")
                continue
            for test in tests:
                if not isinstance(test, Mapping):
                    blockers.append(f"SYNTHETIC_TEST_SOURCE_INVALID:{check}")
                    continue
                path, symbol = test.get("path"), test.get("symbol")
                if (
                    not isinstance(path, str)
                    or not path.startswith("tests/research/integration_v13/")
                    or current.get(path) != test.get("sha256")
                    or not isinstance(symbol, str)
                    or not symbol.startswith("test_")
                    or not _synthetic_test_symbol(repo, test, current)
                ):
                    blockers.append(f"SYNTHETIC_TEST_SOURCE_INVALID:{check}")
    return {
        "ready": not blockers,
        "economic_data_access_allowed": not blockers,
        "blockers": sorted(set(blockers)),
        "period_disposition": "ALREADY_EXPOSED_EXPLORATORY_RESEARCH_NOT_FRESH_VALIDATION",
        "independent_review_pass": False,
        "historical_exchange_rules_closed": False,
        "production_authorized": False,
        "replay_executed": False,
    }


def require_ready(repo, precommit, receipt=None):
    result = readiness_gate(repo, precommit, receipt)
    if not result["ready"]:
        raise ReadinessError("ECONOMICS_DENIED:" + ";".join(result["blockers"]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    precommit = build_precommit(args.repo)
    # Deliberately no --run, market reader, receipt auto-certification or output writer.
    print(
        json.dumps(
            {"precommit": precommit, "readiness": readiness_gate(args.repo, precommit)},
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
