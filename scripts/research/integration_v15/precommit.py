"""Exact nine-system source/dependency freeze; evidence, not a READY switch."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.research.integration_v13.economic_precommit import specification as inherited
from spotbot.research.multi_school_fidelity.gate3_precommit import config_hash
from spotbot.research.multi_school_fidelity.integration_v15.authority import FUNDED, QUARANTINED, ReceiptGraph
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError

TASK = "AKAH_ALL_NINE_SYSTEMS_EIGHTEEN_ARM_REPLAY_READINESS_V15"
OUT = "governance/all_nine_eighteen_arm_readiness_v15"
PROTOCOL = OUT + "/research_protocol.json"
INPUT_MANIFEST = "governance/final_gate2_to_gate3_replay_ready_mega_v3/bounded_market_input_manifest.json"
ROOTS = ("src/spotbot", "scripts/research/integration_v13", "scripts/research/integration_v14", "scripts/research/integration_v15", "tests/research")
DEPS = ("numpy", "pandas", "pyarrow", "arch", "pytest")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def source_hashes(repo):
    repo = Path(repo).resolve()
    paths = {PROTOCOL, INPUT_MANIFEST}
    for root in ROOTS:
        paths.update(p.relative_to(repo).as_posix() for p in (repo / root).rglob("*.py"))
    return {p: sha(repo / p) for p in sorted(paths)}


def build(repo):
    repo = Path(repo).resolve()
    protocol = json.loads((repo / PROTOCOL).read_text(encoding="utf-8"))
    if (protocol["task_id"] != TASK or tuple(protocol["final_funded_grammars"]) != FUNDED
            or set(protocol["quarantine"]) != set(QUARANTINED)
            or protocol["economics_in_this_mission"] is not False):
        raise ContractError("FROZEN_PROTOCOL_SCOPE_PARITY")
    contract = inherited()
    contract.update(task_id=TASK, version=15, grammars=list(FUNDED),
                    arms=[g + "|" + c for g in FUNDED for c in ("1X", "2X")],
                    primary_claim_family=list(FUNDED), claims={g: {g + "|2X": 1.} for g in FUNDED},
                    quarantine=QUARANTINED, economic_access="EXPLICIT_SUBSEQUENT_AUTHORIZATION_ONLY",
                    readiness_checks=["EXACT_E2E_EVIDENCE", "UNKNOWN_SCOPE_UNREACHABLE", "DOW_COMPLETE_FRAME",
                                      "BOUNDED_FULL_UNIVERSE_SMOKE", "FULL_REGRESSION_PASS"])
    contract["dow"].update(permission="COMPLETE_CURRENT_PIT_FRAME_REQUIRED_FOR_ALL_FUNDED_GRAMMARS")
    contract["dow"].update(role="CONTEXT_AND_EXPLICIT_STANDALONE_V15_OWNER", economic_arm=True,
                           reason="Prospective source-bound secondary-low/reconfirmation adaptation")
    contract["qualification_binding"]["scope"] = "Explicit pre-economic user-authorized V15 nine-grammar claim family"
    sources = source_hashes(repo)
    value = {"contract": contract, "source_hashes": sources,
             "source_version_sha256": config_hash(sources),
             "dependencies": {d: importlib.metadata.version(d) for d in DEPS}}
    value["precommit_sha256"] = config_hash(value)
    return value


def verify(repo, frozen):
    current = build(repo)
    if current != frozen:
        raise ContractError("EXACT_PRECOMMIT_SOURCE_CONFIG_DEPENDENCY_DRIFT")
    return True


def safe_artifact(repo, relative):
    p = (Path(repo) / relative).resolve()
    root = (Path(repo) / OUT).resolve()
    if not p.is_relative_to(root) or not p.is_file():
        raise ContractError("READINESS_ARTIFACT_OUTSIDE_FROZEN_DIRECTORY")
    return p


def require_ready(repo, frozen, certificate):
    verify(repo, frozen)
    if not isinstance(certificate, dict) or certificate.get("source_version_sha256") != frozen["source_version_sha256"]:
        raise ContractError("EXACT_VERSION_READINESS_CERTIFICATE_REQUIRED")
    if certificate.get("precommit_sha256") != frozen["precommit_sha256"]:
        raise ContractError("READINESS_CONFIG_PARITY")
    evidence = certificate.get("evidence", {})
    required = {"synthetic_results.xml", "regression_results.xml", "e2e_receipts.json", "mechanical_smoke.json"}
    if set(evidence) != required:
        raise ContractError("COMPLETE_RETAINED_READINESS_EVIDENCE_REQUIRED")
    paths = {}
    for name, binding in evidence.items():
        path = safe_artifact(repo, binding["path"])
        if sha(path) != binding["sha256"]:
            raise ContractError("READINESS_EVIDENCE_HASH_DRIFT")
        paths[name] = path
    for name in ("synthetic_results.xml", "regression_results.xml"):
        root = ET.parse(paths[name]).getroot()
        cases = root.findall(".//testcase")
        if not cases or root.findall(".//failure") or root.findall(".//error") or root.findall(".//skipped"):
            raise ContractError("FULL_EXECUTED_REGRESSION_REQUIRED")
    names = {c.attrib["name"].split("[")[0] for c in ET.parse(paths["synthetic_results.xml"]).getroot().findall(".//testcase")}
    mandatory = {"test_funded_e2e", "test_multi_arm_e2e", "test_unknown_scope_all_boundaries",
                 "test_receipt_attack_after_bind", "test_owner_accounting_tamper",
                 "test_incomplete_dow_never_permissive", "test_admission_lease_expiry_not_owner_loss",
                 "test_eighteen_cost_arms", "test_consecutive_elliott_actual_subdivision_source",
                 "test_wyckoff_semantics_actual_raw_parents_to_native_intent",
                 "test_dow_actual_delayed_secondary_source_not_generic_buy",
                 "test_harmonic_invalidated_campaign_cannot_earn_type_ii",
                 "test_harmonic_inside_owner_bar_completion_requires_later_retest",
                 "test_full_nine_source_installation_and_no_fixture_market_mode",
                 "test_wyckoff_same_bar_double_extrema_abstain_not_crash",
                 "test_shared_market_context_has_exact_per_source_claim_namespace",
                 "test_full_cash_day_calendar_and_campaign_accounting_adapter",
                 "test_mock_arm_failure_retained_all_eighteen_attempted_no_claim_shrink"}
    if not mandatory <= names:
        raise ContractError("ADVERSARIAL_AND_E2E_COVERAGE_REQUIRED")
    arm_cases = [c.attrib["name"] for c in ET.parse(paths["synthetic_results.xml"]).getroot().findall(".//testcase")
                 if c.attrib["name"].startswith("test_eighteen_cost_arms[")]
    if len(arm_cases) != 18 or any(not any(g in name and scenario in name for name in arm_cases)
                                 for g in FUNDED for scenario in ("1X", "2X")):
        raise ContractError("EXACT_EIGHTEEN_EXECUTED_COST_ARM_CASES_REQUIRED")
    receipts = json.loads(paths["e2e_receipts.json"].read_text())
    if set(receipts) != {*FUNDED, "MULTI_ARM"}:
        raise ContractError("EVERY_FUNDED_ARM_AND_MULTI_ARM_RECEIPTS_REQUIRED")
    stages = {"SOURCE_EVIDENCE", "SEMANTIC_PRODUCER", "EMISSION_SEAL", "SELECTOR_ADMISSION",
              "EXECUTION_FILL", "OWNER_UPDATE", "LIFECYCLE_EXECUTION", "ACCOUNTING_OUTPUT"}
    for arm, item in receipts.items():
        graph = ReceiptGraph.restore(item["graph"])
        if graph.source_sha256 != frozen["source_version_sha256"] or graph.config_sha256 != frozen["precommit_sha256"]:
            raise ContractError("E2E_RECEIPT_VERSION_PARITY")
        if not stages <= {r.kind for r in graph.nodes.values()}:
            raise ContractError("INCOMPLETE_RETAINED_RECEIPT_CHAIN:" + arm)
        if graph.nodes[item["terminal_receipt"]].kind != "ACCOUNTING_OUTPUT":
            raise ContractError("TERMINAL_ACCOUNTING_RECEIPT_REQUIRED")
        graph.verify(item["terminal_receipt"], graph.nodes[item["terminal_receipt"]].checkpoint)
    smoke = json.loads(paths["mechanical_smoke.json"].read_text())
    if (smoke.get("source_version_sha256") != frozen["source_version_sha256"]
            or smoke.get("complete") is not True or smoke.get("economic_replay_executed") is not False
            or smoke.get("2024_rows_accessed") is not False or smoke.get("2025_rows_accessed") is not False
            or smoke.get("pairs_inspected", 0) < smoke.get("available_pairs", 1)
            or smoke.get("checkpoint_count", 0) <= 0):
        raise ContractError("BOUNDED_FULL_UNIVERSE_SMOKE_REQUIRED")
    return True
