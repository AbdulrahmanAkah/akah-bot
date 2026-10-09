"""Source/metadata-only tests. No historical data, PnL, replay or network."""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest

from spotbot.research.multi_school_fidelity.gate3_precommit import config_hash, specification
from spotbot.research.multi_school_fidelity.integration_v10.pipeline import PHASES

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/research/integration_v13/economic_precommit.py"
SPEC = importlib.util.spec_from_file_location("v13_economic_precommit", SCRIPT)
precommit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(precommit)


@pytest.fixture
def frozen():
    return precommit.build_precommit(REPO)


def rehash(payload):
    payload["precommit_sha256"] = config_hash(
        {key: value for key, value in payload.items() if key != "precommit_sha256"}
    )
    return payload


def test_full_current_family_both_costs_and_no_dow_arm():
    contract = precommit.specification()
    assert set(contract["grammars"]) == set(PHASES)
    assert len(contract["arms"]) == 16
    assert set(contract["claims"]) == set(PHASES)
    assert all(contract["claims"][g] == {g + "|2X": 1.0} for g in PHASES)
    assert contract["costs_round_trip"] == {"1X": 0.0025, "2X": 0.005}
    assert contract["dow"]["role"] == "CONTEXT_ONLY"
    assert contract["dow"]["economic_arm"] is False


def test_inherits_entire_literal_qualification_without_tuning():
    contract = precommit.specification()
    assert contract["qualification_literal"] == specification()
    assert contract["risk"] == specification()["risk"]
    assert contract["capital_capacity"] == specification()["capital_capacity"]
    assert contract["qualification_literal"]["uncertainty"]["replications"] == 9999
    assert contract["period_disposition"].startswith("ALREADY_EXPOSED_EXPLORATORY")
    assert contract["quantity"]["historical_exchange_rules"] == "EXCLUDED_BY_USER_NOT_CLOSED"
    assert contract["review"] == "WAIVED_FOR_EXPERIMENT_BY_USER_NOT_INDEPENDENT_PASS"
    assert not contract["model_fit"] and not contract["threshold_search"]
    assert not contract["historical_exchange_executability_certified"]
    assert not contract["independent_review_pass"] and not contract["production_authorized"]


def test_contract_calls_are_independent_not_mutable_global_policy():
    first = precommit.specification()
    first["qualification_literal"]["hard_rules"].clear()
    first["outputs"]["fills"].clear()
    assert precommit.specification()["qualification_literal"] == specification()
    assert precommit.specification()["outputs"]["fills"]


def test_output_schemas_precede_economics_including_empty_cash_calendar():
    outputs = precommit.specification()["outputs"]
    assert {
        "campaigns",
        "decisions",
        "fills",
        "hourly_equity",
        "daily_equity",
        "cost_reconciliation",
        "annual",
        "asset_attribution",
        "concentration",
        "uncertainty",
        "risk_audit",
        "execution_audit",
        "unsupported_forms",
        "qualification",
    } <= outputs.keys()
    assert {"B0", "add_count", "terminal_mtm", "net_including_fees_and_terminal_mtm"} <= set(
        outputs["campaigns"]
    )
    assert {"emission_id", "required_evidence_ids", "applies_from"} <= set(outputs["decisions"])
    assert {"fee", "cash_delta", "execution_phase"} <= set(outputs["fills"])
    assert "never drop claims" in outputs["empty_arms"]
    assert "Every UTC day" in outputs["daily_calendar"]
    assert "no fabricated liquidation" in outputs["cost_reconciliation"]["terminal"]
    terminal = outputs["terminal_coverage"]
    assert terminal["source_row_timestamp"] == "COMPLETED_CLOSE_NOT_OPEN"
    assert terminal["last_permitted_completed_close"] == "2023-12-31T23:00:00Z"
    assert terminal["full_2023_terminal_hour_coverage"] is False
    assert terminal["protected_close_hlc_access"] is False


def test_recursive_freeze_includes_v12_and_only_source_protocol(frozen):
    hashes = frozen["source_hashes"]
    assert all(path in hashes for path in precommit.REQUIRED_SOURCES)
    assert "src/spotbot/research/multi_school_fidelity/integration_v12/producers.py" in hashes
    assert "src/spotbot/research/multi_school_fidelity/integration_v11/execution.py" in hashes
    assert all(path.endswith(".py") or path == precommit.PROTOCOL_PATH for path in hashes)
    assert frozen["source_version_sha256"] == config_hash(hashes)


@pytest.mark.parametrize("receipt", [None, {}, True, {"ready": True}, {"all_checks_pass": True}])
def test_missing_actual_producers_and_driver_deny_despite_flags(frozen, receipt):
    result = precommit.readiness_gate(REPO, frozen, receipt)
    assert not result["ready"] and not result["economic_data_access_allowed"]
    assert result["blockers"]
    assert not result["replay_executed"]
    with pytest.raises(precommit.ReadinessError, match="ECONOMICS_DENIED"):
        precommit.require_ready(REPO, frozen, receipt)


@pytest.mark.parametrize("change", ["grammar", "cost", "output", "uncertainty", "review"])
def test_policy_drift_denied_even_when_caller_rehashes(frozen, change):
    bad = copy.deepcopy(frozen)
    contract = bad["contract"]
    if change == "grammar":
        contract["grammars"].pop()
    elif change == "cost":
        contract["costs_round_trip"]["2X"] = 0
    elif change == "output":
        contract["outputs"]["fills"].remove("fee")
    elif change == "uncertainty":
        contract["qualification_literal"]["uncertainty"]["replications"] = 1
    else:
        contract["review"] = "INDEPENDENT_PASS"
    result = precommit.readiness_gate(REPO, rehash(bad))
    assert "FIXED_ECONOMIC_CONTRACT_DRIFT" in result["blockers"]


def test_unrehashed_mutation_and_recursive_source_drift_denied(frozen, monkeypatch):
    bad = copy.deepcopy(frozen)
    bad["contract"]["dow"]["economic_arm"] = True
    assert "PRECOMMIT_HASH_DRIFT" in precommit.readiness_gate(REPO, bad)["blockers"]
    changed = dict(frozen["source_hashes"])
    changed["src/spotbot/research/multi_school_fidelity/integration_v12/producers.py"] = "A" * 64
    monkeypatch.setattr(precommit, "source_hashes", lambda _repo: changed)
    blockers = precommit.readiness_gate(REPO, frozen)["blockers"]
    assert "RECURSIVE_SOURCE_HASH_DRIFT" in blockers
    assert "SOURCE_VERSION_HASH_DRIFT" in blockers


@pytest.mark.parametrize(
    "relative",
    [
        "../outside.py",
        "C:/outside.py",
        "data/raw/a.parquet",
        "governance/results.json",
        "governance/six_school_hybrid_repair_replay_v5/cache/A.events.json",
        "src\\spotbot\\unsafe.py",
    ],
)
def test_read_boundary_rejects_non_source_paths(relative):
    with pytest.raises(precommit.ReadinessError):
        precommit._safe_source(REPO, relative)


def test_old_runner_and_contract_only_methods_cannot_bind_historical_components(frozen):
    for path, symbol in (
        ("src/spotbot/research/multi_school_fidelity/full_replay_v5.py", "replay_arm"),
        (
            "src/spotbot/research/multi_school_fidelity/integration_v12/producers.py",
            "ContractProducer.h3",
        ),
    ):
        binding = {"path": path, "symbol": symbol, "sha256": frozen["source_hashes"][path]}
        assert not precommit._implemented_symbol(REPO, binding, frozen["source_hashes"])


def test_metadata_flags_with_no_concrete_generators_cannot_certify(frozen):
    receipt = {
        "task_id": precommit.TASK,
        "source_version_sha256": frozen["source_version_sha256"],
        "protocol_sha256": frozen["source_hashes"][precommit.PROTOCOL_PATH],
        "contract_sha256": config_hash(precommit.specification()),
        "scope": "SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION",
        "market_rows_read": False,
        "pnl_read": False,
        "economic_replay_executed": False,
        "network_access": False,
        "producers": {
            grammar: {"path": "missing.py", "symbol": "produce", "sha256": "A" * 64}
            for grammar in precommit.GRAMMARS
        },
        "driver": {"path": "missing.py", "symbol": "run", "sha256": "A" * 64},
        "checks": {check: True for check in precommit.CHECKS},
    }
    result = precommit.readiness_gate(REPO, frozen, receipt)
    assert "CURRENT_CHRONOLOGICAL_GUARDED_DRIVER_MISSING" in result["blockers"]
    assert all(
        f"ACTUAL_TYPED_PRODUCER_MISSING:{grammar}" in result["blockers"]
        for grammar in precommit.GRAMMARS
    )
    assert all(
        f"SYNTHETIC_READINESS_NOT_PROVEN:{check}" in result["blockers"]
        for check in precommit.CHECKS
    )
    assert all(f"SEMANTIC_SOURCE_AUTHORITY_UNRESOLVED:{a}" in result["blockers"]
               for a in precommit.SEMANTIC_AUTHORITIES)


def test_source_only_build_and_gate_do_not_call_replay_or_read_market(frozen, monkeypatch):
    original = Path.open
    touched = []

    def source_only(path, *args, **kwargs):
        resolved = path.resolve()
        assert resolved.is_relative_to(REPO)
        relative = resolved.relative_to(REPO).as_posix()
        assert relative.endswith(".py") or relative == precommit.PROTOCOL_PATH
        assert not args or "w" not in args[0] and "a" not in args[0]
        touched.append(relative)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", source_only)
    for name, module in tuple(sys.modules.items()):
        if name == "spotbot.research.multi_school_fidelity.full_replay_v5":
            monkeypatch.setattr(module, "replay_arm", lambda *_a, **_k: pytest.fail("V5 fallback"))
            monkeypatch.setattr(module, "run", lambda *_a, **_k: pytest.fail("V5 run"))
    assert precommit.build_precommit(REPO)["contract"] == frozen["contract"]
    assert not precommit.readiness_gate(REPO, frozen)["economic_data_access_allowed"]
    assert touched


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "another_task"),
        ("period", ["2024-01-01", "2025-01-01"]),
        ("models_or_threshold_search", True),
        ("historical_exchange_rules", "CLOSED"),
        ("review_disposition", "INDEPENDENT_PASS"),
        ("production", 0),
    ],
)
def test_governed_protocol_exact_parity(field, value):
    import json

    protocol = json.loads((REPO / precommit.PROTOCOL_PATH).read_text(encoding="utf-8-sig"))
    protocol[field] = value
    assert f"PROTOCOL_PARITY:{field}" in precommit._protocol_errors(protocol)


@pytest.mark.parametrize("symbol", ["test_invented_generator_pass", "frozen"])
def test_test_presence_requires_real_test_node_and_assertions(frozen, symbol):
    path = "tests/research/integration_v13/test_economic_precommit.py"
    binding = {"path": path, "symbol": symbol, "sha256": frozen["source_hashes"][path]}
    assert not precommit._synthetic_test_symbol(REPO, binding, frozen["source_hashes"])


def test_existing_callable_ast_and_injected_packet_tests_do_not_make_ready(frozen):
    # Deliberately dishonest metadata: callable existence is NOT generation proof.
    path = "src/spotbot/research/multi_school_fidelity/integration_v13/guarded_driver.py"
    binding = {"path": path, "symbol": "GuardedDriver.on_open",
               "sha256": frozen["source_hashes"][path]}
    assert precommit._implemented_symbol(REPO, binding, frozen["source_hashes"])
    test_path = "tests/research/integration_v13/test_guarded_driver.py"
    packet_test = {"path": test_path,
                   "symbol": "test_all_eight_exact_source_issues_reach_actual_v12_guard",
                   "sha256": frozen["source_hashes"][test_path]}
    producers = {g: binding for g in precommit.GRAMMARS}
    receipt = {
        "task_id": precommit.TASK,
        "source_version_sha256": frozen["source_version_sha256"],
        "protocol_sha256": frozen["source_hashes"][precommit.PROTOCOL_PATH],
        "contract_sha256": config_hash(precommit.specification()),
        "scope": "SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION",
        "market_rows_read": False, "pnl_read": False,
        "economic_replay_executed": False, "network_access": False,
        "fixture_injection_is_generator_evidence": False, "historical_certification": False,
        "producers": producers, "driver": binding,
        "checks": {check: {
            "status": "PASS", "tests": [packet_test],
            "bindings": dict(producers, driver=binding, source_provider=None, scheduler=None),
        } for check in precommit.CHECKS},
    }
    result = precommit.readiness_gate(REPO, frozen, receipt)
    assert not result["ready"] and not result["economic_data_access_allowed"]
    assert "ACTUAL_SEMANTIC_SOURCE_PROVIDER_MISSING" in result["blockers"]
    assert "BOUNDED_HISTORICAL_SCHEDULER_MISSING" in result["blockers"]
    assert any(reason.startswith("ACTUAL_SEMANTIC_GENERATION_EVIDENCE_REQUIRED")
               for reason in result["blockers"])
    assert any(reason.startswith("TRUSTED_IMPLEMENTATION_RUN_REQUIRED")
               for reason in result["blockers"])
