"""Exact subset/source/dependency freeze. Evidence is verified, not a READY switch."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.research.integration_v13.economic_precommit import specification as inherited
from spotbot.research.multi_school_fidelity.gate3_precommit import config_hash
from spotbot.research.multi_school_fidelity.integration_v14.authority import FUNDED, QUARANTINED, ReceiptGraph
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError

TASK = "AKAH_FINAL_AUTHORITY_GAPS_TO_REPLAY_READY_MISSION_V1"
OUT = "governance/final_authority_gaps_to_replay_ready_v1"
PROTOCOL = OUT + "/research_protocol.json"
INPUT_MANIFEST = "governance/final_gate2_to_gate3_replay_ready_mega_v3/bounded_market_input_manifest.json"
ROOTS = ("src/spotbot", "scripts/research/integration_v13", "scripts/research/integration_v14", "tests/research")
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
    contract.update(task_id=TASK, version=14, grammars=list(FUNDED),
                    arms=[g + "|" + c for g in FUNDED for c in ("1X", "2X")],
                    primary_claim_family=list(FUNDED), claims={g: {g + "|2X": 1.} for g in FUNDED},
                    quarantine=QUARANTINED, economic_access="EXPLICIT_SUBSEQUENT_AUTHORIZATION_ONLY",
                    readiness_checks=["EXACT_E2E_EVIDENCE", "QUARANTINE_UNREACHABLE", "DOW_COMPLETE_FRAME",
                                      "BOUNDED_FULL_UNIVERSE_SMOKE", "FULL_REGRESSION_PASS"])
    contract["dow"].update(permission="COMPLETE_CURRENT_PIT_FRAME_REQUIRED_FOR_ALL_FUNDED_GRAMMARS")
    contract["qualification_binding"]["scope"] = "Explicit pre-economic user-authorized V14 three-grammar claim family"
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
    mandatory = {"test_funded_e2e", "test_multi_arm_e2e", "test_quarantine_all_boundaries",
                 "test_receipt_attack_after_bind", "test_owner_accounting_tamper",
                 "test_incomplete_dow_never_permissive", "test_abc_parent_death"}
    if not mandatory <= names:
        raise ContractError("ADVERSARIAL_AND_E2E_COVERAGE_REQUIRED")
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
