"""V15 engineering certificate, never a market-return or school-doctrine claim."""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from .precommit import OUT, TASK, build, sha, require_ready
from .runner import save, preflight
from spotbot.research.multi_school_fidelity.integration_v15.authority import FUNDED


def main():
    repo = Path.cwd().resolve()
    root = repo / OUT
    frozen = build(repo)
    names = ("synthetic_results.xml", "regression_results.xml", "e2e_receipts.json", "mechanical_smoke.json")
    certificate = {"task_id": TASK, "source_version_sha256": frozen["source_version_sha256"],
        "precommit_sha256": frozen["precommit_sha256"],
        "evidence": {n: {"path": OUT+"/"+n, "sha256": sha(root/n)} for n in names},
        "historical_exchange_certified": False, "independent_reserve_certified": False,
        "disposition": "USER_AUTHORIZED_APPROXIMATE_EXPOSED_RESEARCH_ALL_NINE",
        "school_doctrine_claim": "DECLARED_AKAH_MECHANICAL_PROFILES_NOT_FULL_HUMAN_SCHOOL_EQUIVALENCE"}
    require_ready(repo, frozen, certificate)
    save(root/"gate3_precommit.json", frozen)
    save(root/"readiness_certificate.json", certificate)
    save(root/"preflight_certificate.json", preflight(repo))
    counts = {n: len(ET.parse(root/n).getroot().findall(".//testcase"))
              for n in ("synthetic_results.xml", "regression_results.xml")}
    smoke = json.loads((root/"mechanical_smoke.json").read_text())
    final = {"task_id": TASK, "outcome": "PASS", "scientific_conclusion": "NONE_ENGINEERING_READINESS_ONLY",
        "AUTHORITY_GAPS_REPLAY_BLOCKING_OPEN": 0,
        "REQUESTED_SYSTEMS": 9, "REQUESTED_COST_ARMS": 18,
        "FINAL_FUNDED_GRAMMARS": list(FUNDED), "QUARANTINED_GRAMMARS": {},
        "GATE3_PRECOMMIT_FREEZE": "PASS", "GATE3_REPLAY_RUNNER_BUILT": "YES",
        "GATE3_REPLAY_PREFLIGHT": "PASS", "READY_FOR_SINGLE_GATE3_REPLAY": "YES",
        "2024_ROWS_ACCESSED": "NO", "2025_ROWS_ACCESSED": "NO", "PNL_READ": "NO",
        "ECONOMIC_REPLAY_EXECUTED": "NO", "PRODUCTION_CHANGE": "NO", "RESEARCH_PUSH": "NO",
        "NEXT_ACTION": "SEPARATELY_AUTHORIZE_SINGLE_FROZEN_ALL_NINE_REPLAY",
        "test_counts": counts, "source_version_sha256": frozen["source_version_sha256"],
        "precommit_sha256": frozen["precommit_sha256"],
        "bounded_preflight": {k: smoke[k] for k in ("pairs_inspected", "eligible_pairs", "missing_raw_pairs",
            "checkpoint_count", "ready_candidate_count", "ready_by_grammar", "wall_seconds", "peak_rss_bytes")},
        "research_gaps_not_claimed_closed": {
            "HISTORICAL_EXCHANGE_RULES": "EXCLUDED_BY_USER_NOT_CLOSED",
            "INDEPENDENT_REVIEW": "USER_WAIVED_NOT_INDEPENDENT_PASS",
            "ECONOMIC_VALUE": "NOT_TESTED_IN_THIS_MISSION",
            "UNBOUND_POST_ABC_ELLIOTT_OBJECTIVE": "DIAGNOSTIC_INTERNAL_FORM_NOT_WHOLE_SCHOOL_QUARANTINE"},
        "complete_2023_terminal_hour": False,
        "terminal_contract": "Final completed close 2023-12-31 23UTC; last hour would require a protected 2024 row. No invented terminal mark.",
        "runner": "scripts/research/integration_v15/runner.py:execute_authorized",
        "runner_preflight_command": ".venv/Scripts/python.exe -B -m scripts.research.integration_v15.runner",
        "old_readiness": "V13/V14 artifacts preserved; new explicit prospective contracts do not retroactively erase old missing-doctrine findings."}
    save(root/"canonical_result.json", final)
    save(root/"evidence_snapshot.json", {"task_id": TASK, "boundary": "NO_MARKET_OUTCOMES",
        "source_hashes": frozen["source_hashes"], "dependencies": frozen["dependencies"],
        "evidence": certificate["evidence"], "canonical_result_sha256": sha(root/"canonical_result.json")})
    save(root/"governance_report.json", {"task_id": TASK, "alignment": "ALIGNED_WITH_SCOPE_UPDATE",
        "vision_impact": "ADVANCES", "starting_revision": 786, "target_revision": 787,
        "result_ref": OUT+"/canonical_result.json", "result_sha256": sha(root/"canonical_result.json"),
        "next_bottleneck": "AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15_EXPLICIT_AUTHORIZATION_REQUIRED",
        "scientific_conclusion": "NONE", "governance_sync": "REQUIRED_AFTER_COMPLETE_AND_VERIFY"})
    print(json.dumps({k:v for k,v in final.items() if k in {
        "REQUESTED_SYSTEMS", "REQUESTED_COST_ARMS", "READY_FOR_SINGLE_GATE3_REPLAY", "test_counts"}}, indent=2))


if __name__ == "__main__":
    main()
