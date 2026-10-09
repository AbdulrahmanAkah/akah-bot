"""Certify saved synthetic tests and source bindings only. No replay/data reader."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import (
    CONTRACT,
    GRAMMARS,
    unresolved_authorities,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "governance/structural_lifecycle_repair_v6"
TASK = "AKAH_OWNER_LINKED_DYNAMIC_STRUCTURAL_LIFECYCLE_REPAIR_V6"
START = "8c787f5cd7ab711f81f9435a284fab8fc4991b38"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write(name: str, value) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    protocol = json.loads((OUT / "research_protocol.json").read_text())
    assert protocol["task_id"] == TASK and not protocol["market_replay_executed"]
    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
    assert active["task_id"] == TASK and active["starting_head"] == START
    source_files = [
        "src/spotbot/research/multi_school_fidelity/structural_lifecycle_v6.py",
        "src/spotbot/research/multi_school_fidelity/lifecycle_execution_v6.py",
        "tests/research/test_structural_lifecycle_v6.py",
        "scripts/research/certify_structural_lifecycle_v6.py",
    ]
    for path in source_files:
        ast.parse((ROOT / path).read_text())
    immutable_files = [
        "src/spotbot/research/multi_school_fidelity/full_replay_v4.py",
        "src/spotbot/research/multi_school_fidelity/full_replay_v5.py",
        "src/spotbot/research/multi_school_fidelity/portfolio_kernel.py",
        "src/spotbot/research/multi_school_fidelity/akah_native_replay_engine_v1.py",
        "governance/six_school_hybrid_repair_replay_v4/canonical_result.json",
        "governance/six_school_hybrid_repair_replay_v5/canonical_result.json",
    ]
    frozen = {}
    for path in immutable_files:
        old = subprocess.check_output(["git", "show", START + ":" + path], cwd=ROOT)
        # Git autocrlf is checkout encoding, not a research mutation. Actual
        # working bytes and known canonical-result hashes are bound separately.
        current = (ROOT / path).read_bytes()
        assert old.replace(b"\r\n", b"\n") == current.replace(b"\r\n", b"\n"), path
        frozen[path] = digest(ROOT / path)
    assert frozen[immutable_files[1]] == protocol["authority_base"]["v5_immutable_source_sha256"]
    assert frozen[immutable_files[4]] == (
        "4945AC148ACAF08B203872A56CABEF1C17F74D938218F33A58A07901E894F79A"
    )
    assert frozen[immutable_files[5]] == (
        "2EB481E9C3AAB80E7EF538EAABBE257740BB83F575BB09B2A77FE8093945EB1F"
    )
    suites = {}
    for filename in ("test_results.xml", "targeted_test_results.xml"):
        tree = ET.parse(OUT / filename)
        cases = tree.findall(".//testcase")
        assert cases and not tree.findall(".//failure") and not tree.findall(".//error")
        assert not tree.findall(".//skipped")
        suites[filename] = {
            "tests": len(cases),
            "failures": 0,
            "errors": 0,
            "source": filename,
            "sha256": digest(OUT / filename),
        }
        names = {c.attrib["name"] for c in cases}
        for grammar in GRAMMARS:
            assert any("all_nine_real_kernel_dispatches" in n and grammar in n for n in names)
    sources = {p: digest(ROOT / p) for p in source_files}
    sources["governance/structural_lifecycle_repair_v6/research_protocol.json"] = digest(
        OUT / "research_protocol.json"
    )
    write(
        "source_manifest.json",
        {"sources": sources, "immutable_v4_v5_bindings": frozen, "source_compilation": "PASS"},
    )
    gap_rows = [
        {"id": k, "status": "UNRESOLVED", "reason": v} for k, v in unresolved_authorities().items()
    ]
    gap_rows.extend(
        [
            {
                "id": "ict_h2_trend_owner",
                "status": "UNRESOLVED",
                "reason": (
                    "Distinct higher-structure thesis required; "
                    "do not disable native ICT NY16 globally"
                ),
            },
            {
                "id": "native_staged_and_harmonic_partial_management",
                "status": "UNRESOLVED",
                "reason": (
                    "V6 kernel bridge certifies single owned entries, "
                    "not full source-specific staged/Type-I/II management"
                ),
            },
            {
                "id": "dow_live_broad_context",
                "status": "UNRESOLVED",
                "reason": (
                    "V5 producer remains immutable; "
                    "new broad-context producer not certified by this management layer"
                ),
            },
        ]
    )
    write("remaining_gaps.json", {"all_repairs_complete": False, "gaps": gap_rows})
    result = {
        "task_id": TASK,
        "contract_id": CONTRACT,
        "classification": "STRUCTURAL_MANAGEMENT_TECHNICAL_PASS_FULL_REPAIR_NOT_COMPLETE",
        "technical_verification": "PASS",
        "all_repairs_corrected": False,
        "economic_conclusion": "NONE",
        "gate3_ready": False,
        "synthetic_suites": suites,
        "grammars_synthetic_dispatch_certified": list(GRAMMARS),
        "repairs_verified": [
            "H3_COUNT_OWNER_DISPATCH",
            "NO_ARBITRARY_ACCEPTANCE_LOW_FALLBACK",
            "OWNER_ALTERNATING_STRUCTURE_CHAIN",
            "MONOTONIC_HARD_AND_PROTECTED_LEVELS",
            "WICK_VS_PULLBACK_VS_CONFIRMED_FAILED_RECLAIM",
            "RECLAIM_CANCELS_SUSPICION_NOT_PROTECTION",
            "NATIVE_OWNER_FAILURE_SOURCE_CLOCK",
            "TREND_OBJECTIVE_CHECKPOINT_NOT_TAKE_PROFIT",
            "EXECUTABLE_FINITE_TARGET_NET",
            "NO_FABRICATED_DOLLAR_PROFIT_GOAL",
            "LIVE_PARENT_EXPIRY_INVALIDATION_NO_RESURRECTION",
            "HARD_STOP_PRECEDENCE_AND_ACTUAL_GAP_PRICE",
            "NEXT_OPEN_CONFIRMATION_EXECUTION",
            "NEW_LEVEL_NOT_APPLIED_TO_OLD_LOW",
            "CAPACITY_PENDING_EXIT_NOT_FAKE_FILL",
            "CURRENT_ALL_ASSET_MARKS",
            "TARGETED_MTM_RISK_RESTORATION_SAME_CAPS",
            "REPEATED_MISSING_FUTURE_EVENT_REJECTION",
            "CASH_FEE_PARITY",
        ],
        "remaining_gap_count": len(gap_rows),
        "source_manifest_sha256": digest(OUT / "source_manifest.json"),
        "protocol_sha256": digest(OUT / "research_protocol.json"),
        "2024_rows_accessed": False,
        "2025_rows_accessed": False,
        "market_data_accessed": False,
        "economic_replay_executed": False,
        "model_fit": False,
        "parameter_search": False,
        "production_change": False,
        "push": False,
        "v4_v5_unchanged": True,
    }
    write("canonical_result.json", result)
    flags = {
        k: False
        for k in (
            "lookahead_or_future_information_used",
            "pair_or_event_identity_used_as_runtime_rule",
            "posthoc_outcome_threshold_search_used",
            "2023_new_raw_or_replay_accessed",
            "2024_used_as_fresh_holdout",
            "2024_used_to_define_new_runtime_rule",
            "2025_accessed",
            "production_changed",
        )
    }
    write("governance_values.json", flags)
    evidence = [
        {
            "path": str((OUT / f).relative_to(ROOT)).replace("\\", "/"),
            "sha256": digest(OUT / f),
            "type": kind,
        }
        for f, kind in (
            ("canonical_result.json", "technical_result_not_economic"),
            ("research_protocol.json", "prospective_contract"),
            ("source_manifest.json", "immutable_source_bindings"),
            ("test_results.xml", "synthetic_regression"),
            ("targeted_test_results.xml", "final_targeted_synthetic"),
            ("remaining_gaps.json", "unclosed_authority_quarantine"),
        )
    ]
    write("governance_evidence.json", evidence)
    write(
        "output_manifest.json",
        {
            str(p.relative_to(OUT)): digest(p)
            for p in OUT.rglob("*")
            if p.is_file() and p.name != "output_manifest.json"
        },
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
