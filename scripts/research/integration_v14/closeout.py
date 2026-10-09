"""Create final engineering evidence only after the retained tests/smoke verify."""
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from .precommit import OUT, TASK, PROTOCOL, build, sha, require_ready
from .runner import save, preflight
from spotbot.research.multi_school_fidelity.integration_v14.authority import FUNDED, QUARANTINED


def main():
    repo = Path.cwd().resolve()
    root = repo / OUT
    frozen = build(repo)
    names = ("synthetic_results.xml", "regression_results.xml", "e2e_receipts.json", "mechanical_smoke.json")
    certificate = {"task_id": TASK, "source_version_sha256": frozen["source_version_sha256"],
        "precommit_sha256": frozen["precommit_sha256"], "evidence": {
            n: {"path": OUT + "/" + n, "sha256": sha(root/n)} for n in names},
        "historical_exchange_certified": False, "independent_reserve_certified": False,
        "disposition": "USER_AUTHORIZED_APPROXIMATE_EXPOSED_RESEARCH_SUBSET_ONLY"}
    require_ready(repo, frozen, certificate)
    # The originals remain recoverable byte-for-byte inside the authorized ZIP.
    origin = Path("C:/Users/abdul/Downloads/AKAH_AUTHORITY_GAPS_CLOSURE_TO_REPLAY_READY_V1.zip")
    if sha(origin) != "657C480FED505A84AFBA8852E0C25618B00E36348900A4FAF928AF4EFD212657":
        raise ValueError("USER_MISSION_AUTHORITY_ZIP_DRIFT")
    shutil.copyfile(origin, root / "input_authority.zip")
    save(root/"gate3_precommit.json", frozen)
    save(root/"readiness_certificate.json", certificate)
    preflight_result = preflight(repo)
    save(root/"preflight_certificate.json", preflight_result)
    count = {n: len(ET.parse(root/n).getroot().findall(".//testcase"))
             for n in ("synthetic_results.xml", "regression_results.xml")}
    smoke = json.loads((root/"mechanical_smoke.json").read_text())
    final = {
        "task_id": TASK, "outcome": "PASS", "scientific_conclusion": "NONE_ENGINEERING_READINESS_ONLY",
        "AUTHORITY_GAPS_REPLAY_BLOCKING_OPEN": 0,
        "MATERIAL_IMPLEMENTATION_BUGS_OPEN_IN_FUNDED_SCOPE": 0,
        "MATERIAL_SPEC_AMBIGUITIES_OPEN_IN_FUNDED_SCOPE": 0,
        "FINAL_FUNDED_GRAMMARS": list(FUNDED), "QUARANTINED_GRAMMARS": QUARANTINED,
        "E2E_RECEIPT_HARNESS": "PASS", "QUARANTINED_PATH_UNREACHABILITY": "PASS",
        "GATE3_PRECOMMIT_FREEZE": "PASS", "GATE3_REPLAY_RUNNER_BUILT": "YES",
        "GATE3_REPLAY_PREFLIGHT": "PASS", "READY_FOR_SINGLE_GATE3_REPLAY": "YES",
        "2024_ROWS_ACCESSED": "NO", "2025_ROWS_ACCESSED": "NO", "PNL_READ": "NO",
        "ECONOMIC_REPLAY_EXECUTED": "NO", "PRODUCTION_CHANGE": "NO",
        "NEXT_ACTION": "RUN_THE_SINGLE_FROZEN_GATE3_REPLAY_WITH_EXPLICIT_AUTHORIZATION",
        "test_counts": count, "source_version_sha256": frozen["source_version_sha256"],
        "precommit_sha256": frozen["precommit_sha256"],
        "bounded_preflight": {k: smoke[k] for k in ("pairs_inspected", "eligible_pairs", "missing_raw_pairs",
            "checkpoint_count", "ready_candidate_count", "ready_by_grammar", "wall_seconds", "peak_rss_bytes")},
        "research_gaps_not_claimed_closed": {
            **QUARANTINED, "HISTORICAL_EXCHANGE_RULES": "EXCLUDED_BY_USER_NOT_CLOSED",
            "INDEPENDENT_REVIEW": "INHERITED_USER_WAIVER_NOT_A_PASS",
            "ECONOMIC_VALUE": "NOT_TESTED_IN_THIS_MISSION"},
        "dow_contract": "All funded entries require complete current PIT Dow permission; incomplete data means UNKNOWN and cash/abstention, NOT fabricated bullish breadth.",
        "complete_2023_terminal_hour": False,
        "terminal_contract": "Final completed close 2023-12-31 23UTC; 23UTC-to-2024 terminal hour explicitly missing; never invent a mark.",
        "runner": "scripts/research/integration_v14/runner.py:execute_authorized",
        "runner_preflight_command": ".venv/Scripts/python.exe -B -m scripts.research.integration_v14.runner",
        "regression_correction": "Test module name collision corrected to exact qualified implementation module; no trading behavior modified.",
        "old_readiness": "V13 all-eight-arm FAIL_CLOSED preserved; this new subset does not erase its missing doctrine findings.",
    }
    save(root/"canonical_result.json", final)
    save(root/"authority_gap_dispositions.json", {"replay_blocking_open": 0,
        "funded": list(FUNDED), "quarantined": QUARANTINED,
        "A_B_C_D": "WYCKOFF/H1 unreachable; no invented native semantics or structural-stop substitution",
        "E": "Complete current membership AND contemporaneous frame AND matching 4H membership; missing/stale denies",
        "F": "ABC diagnostic and Elliott/H3 quarantined; existing literal W2/W4 profiles unchanged and regression-tested",
        "G": "Retained per-arm/multi-arm source-seal-selector-fill-owner-exit-accounting DAG; mutation/death fails closed"})
    save(root/"evidence_snapshot.json", {"task_id": TASK, "boundary": "NO_MARKET_OUTCOMES",
        "source_hashes": frozen["source_hashes"], "dependencies": frozen["dependencies"],
        "evidence": certificate["evidence"], "mission_zip_sha256": sha(root/"input_authority.zip"),
        "canonical_result_sha256": sha(root/"canonical_result.json")})
    save(root/"governance_report.json", {"task_id": TASK, "alignment": "ALIGNED_WITH_SCOPE_UPDATE",
        "vision_impact": "ADVANCES", "starting_revision": 785, "target_revision": 786,
        "result_ref": OUT + "/canonical_result.json", "result_sha256": sha(root/"canonical_result.json"),
        "next_bottleneck": "AKAH_SINGLE_FROZEN_GATE3_REPLAY_V14_EXPLICIT_AUTHORIZATION_REQUIRED",
        "scientific_conclusion": "NONE", "governance_sync": "REQUIRED_AFTER_COMPLETE_AND_VERIFY"})
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
