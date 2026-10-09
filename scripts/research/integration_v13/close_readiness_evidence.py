"""Persist source/synthetic evidence, never read a market row or arm economics.

This is a governed evidence packager. It records an unsuccessful full-scope
readiness result; it does NOT turn missing producer authority into a certificate.
"""
import ast
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.research.integration_v13 import economic_precommit as pc

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"governance/research_readiness_v13"
NEXT="V13_WYCKOFF_H1_SEMANTIC_PRODUCER_AUTHORITY_AND_FULL_SCOPE_RESEARCH_READINESS"

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def write(name,obj):
    target=OUT/name
    with target.open("w",encoding="utf-8",newline="\n") as stream:
        stream.write(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n")
    return {"path":target.relative_to(ROOT).as_posix(),"sha256":sha(target),"bytes":target.stat().st_size}
def junit(name):
    root=ET.parse(OUT/name).getroot()
    suites=list(root.iter("testsuite"))
    return {key:sum(int(s.attrib.get(key,0)) for s in suites)
            for key in ("tests","failures","errors","skipped")}

def main():
    active=json.loads((ROOT/".akah_bot/active_task.json").read_text())
    assert active["task_id"]==pc.TASK and active["starting_charter_revision"]==784
    assert sha(ROOT/"governance/AKAH_BOT_SYSTEM_CHARTER.json")==active["starting_charter_sha256"]
    tests={n:junit(n) for n in ("v13_synthetic_results.xml","inherited_synthetic_results.xml")}
    assert all(x["tests"]>0 and not any(x[k] for k in ("failures","errors","skipped")) for x in tests.values())
    pre=pc.build_precommit(ROOT)
    for path in pre["source_hashes"]:
        if path.endswith(".py"):
            ast.parse((ROOT/path).read_text(encoding="utf-8-sig"),filename=path)
    assert pc.verify_precommit(ROOT,pre)["valid"]
    old_diff=subprocess.check_output(["git","diff","--name-only",active["starting_head"],"--",
                                    "src","tests","scripts","governance"],cwd=ROOT,text=True).strip()
    own=("src/spotbot/research/multi_school_fidelity/integration_v13/",
         "scripts/research/integration_v13/","tests/research/integration_v13/",
         "governance/research_readiness_v13/")
    assert all(path.startswith(own) for path in old_diff.splitlines()),"EXISTING_TRACKED_AUTHORITY_CHANGED"
    manifest_path="governance/final_gate2_to_gate3_replay_ready_mega_v3/bounded_market_input_manifest.json"
    manifest=json.loads((ROOT/manifest_path).read_text())
    searches={}
    for query in ("DOWNSIDE_OBJECTIVE_MET", "downward_objective_context", "H1_NATIVE_MARKUP_OWNER_UNAVAILABLE"):
        r=subprocess.run(["rg","-n","--glob","*.py",query,
                          "src/spotbot/research/multi_school_fidelity"],cwd=ROOT,text=True,capture_output=True)
        assert r.returncode in (0,1)
        searches[query]=r.stdout.splitlines()
    bindings=[]
    authorities=[
        manifest_path,"governance/school_ownership_bundle_v8/IMPLEMENTATION_CONTRACT.md",
        "governance/school_ownership_bundle_v8/profile_binding.json",
        "governance/causal_lineage_closure_v12/canonical_result.json",
        "src/spotbot/research/multi_school_fidelity/akah_replay_ready_detectors_v1.py",
        "src/spotbot/research/multi_school_fidelity/akah_full_fidelity_runtime_v1.py",
        "src/spotbot/data/aggregation.py","src/spotbot/data/provider.py",
    ]
    for rel in authorities:
        p=ROOT/rel
        if not p.is_file():raise ValueError("AUTHORITY_MISSING:"+rel)
        bindings.append({"path":rel,"sha256":sha(p),"bytes":p.stat().st_size})
    write("input_authority_manifest.json",{
        "starting_state":active,"files":bindings,"market_manifest_only":True,
        "market_rows_read_this_mission":0,"existing_bounded_input_manifest":{
            "eligible_pairs":manifest["eligible_pairs"],"bounded_available_pairs":len(manifest["pairs"]),
            "missing_raw_pairs":manifest["missing_raw_pairs"],
            "physical_market_file_shas_or_rows_reverified":False,
        }})
    write("source_authority_search.json",{"scope":"CURRENT_LOCAL_SCHOOL_SOURCE_ONLY_NO_MARKET_DATA",
        "queries":searches,"conclusion":"Frozen V8 requires supplied PS/SC/ST/downside-objective; old detector supplies bool(sc) and base_formed=True, not these typed proofs"})
    gaps=[
        {"id":"WY_ACCUMULATION_SOURCE","status":"UNRESOLVED","affected":["WYCKOFF","H1"],
         "need":"Independent causal definitions/producer for PS, SC, ST and a source-bound downward objective; old bool(sc) cannot certify them",
         "authority":"school_ownership_bundle_v8/IMPLEMENTATION_CONTRACT.md:145-148; akah_replay_ready_detectors_v1.py:631-637"},
        {"id":"WY_CONTEXT_REACCUMULATION","status":"UNRESOLVED","affected":["WYCKOFF","H1"],
         "need":"Actual source-owned market/RS and historical markup with fresh range identity, not generic direction==UP relabelled MARKUP"},
        {"id":"WY_DISTRIBUTION_MANAGEMENT","status":"UNRESOLVED","affected":["WYCKOFF"],
         "need":"Producer-owned distribution / market-distribution plus RS-loss events. Structural stops alone do not complete native management"},
        {"id":"H1_MARKUP_PARENT","status":"UNRESOLVED","affected":["H1"],
         "need":"Live native markup claim with expiry and ownership; current Classical source correctly abstains without it"},
        {"id":"DOW_COMPLETE_PIT_FRAME","status":"INCOMPLETE_SOURCE_FRAME","affected":["DOW_CONTEXT"],
         "need":"Complete contemporaneous PIT source coverage, or an explicitly new precommitted incomplete-data context contract. 16 historically eligible assets lack raw in the saved manifest; no claim all 16 are simultaneous members"},
        {"id":"ELLIOTT_ABC_OBJECTIVE","status":"DIAGNOSTIC_ONLY","affected":["ELLIOTT","H3"],
         "need":"Forward objective binding to recursively certified named motive parent; only W2/W4 literal objectives are automatically source-bound"},
        {"id":"FULL_SCOPE_END_TO_END_RECEIPT","status":"NOT_CERTIFIED","affected":["ALL"],
         "need":"Actual immutable generation -> sealed issues -> execution -> owner updates -> retained economic-output harness for every declared arm. Adapter/consumer fixture tests cannot certify missing semantics; whole-universe combinatorial search scalability also unverified"},
    ]
    write("remaining_authority_gaps.json",gaps)
    rows=[
        (1,"Harmonic family ownership","FINITE_V8_CONTRACT_AND_GENERATOR_SYNTHETIC_PASS","Not full discretionary-school certification; no historical economics"),
        (2,"Elliott parent/child ownership","FINITE_W2_W4_SYNTHETIC_PASS_ABC_DIAGNOSTIC","All compatible/opposing counts retained; no hidden work cap; full-universe runtime unverified"),
        (3,"Wyckoff reaccumulation","PARTIAL_SOURCE_BOUND_GENERATOR_REQUIRED_AUTHORITIES_MISSING","No false new selling climax or old PNF/LPS inheritance"),
        (4,"ICT/H2 entry-owned management","CAUSAL_BINDINGS_IMPLEMENTED_SYNTHETIC_PASS","Session distinct from protected 4H trend owner; no after-profit conversion"),
        (5,"Actual producer integration","PARTIAL_NOT_HISTORICAL_CERTIFICATION","Provider, exact seals, open/close scheduling and receipt feedback implemented; semantic upstream authority prevents full scope"),
        (6,"Live Dow context","IMPLEMENTED_COMPLETE_FRAME_OR_EXPLICIT_GAP","Context-only; no standalone executable entry/stop; missing frame not narrowed"),
        (7,"Historical exchange rules","EXCLUDED_BY_USER_NOT_CLOSED","Continuous numerical research rule only, not historical exchange execution"),
        (8,"Unused independent reserve","WAIVED_BY_USER_NOT_INDEPENDENT_PASS","No reviewer/human identity falsification or reused cases certified"),
        (9,"Opportunity arbiter","INHERITED_DETERMINISTIC_NOT_ECONOMIC_EDGE_PROVEN","Feasibility, staged add priority, FIFO and digest; no refit or outcome tuning"),
        (10,"Convincing profit","STRUCTURAL_NET_GEOMETRY_NOT_PER_TRADE_GUARANTEE","Source targets; trend checkpoints not fixed profit ceilings; expected realization untested"),
        (11,"Economic value","NOT_EXECUTED_FAIL_CLOSED","Full readiness failed; no old replay used as a substitute for new source logic"),
    ]
    write("eleven_gap_dispositions.json",[dict(id=i,point=n,status=s,limitation=l) for i,n,s,l in rows])
    write("unarmed_economic_precommit.json",pre)
    readiness=pc.readiness_gate(ROOT,pre,None)
    assert not readiness["ready"] and not readiness["economic_data_access_allowed"]
    readiness["material_source_blockers"]=gaps
    readiness["generator_components_exist_but_no_full_scope_receipt"]=True
    write("readiness_certificate.json",readiness)
    declarations={key:False for key in (
        "lookahead_or_future_information_used","pair_or_event_identity_used_as_runtime_rule",
        "posthoc_outcome_threshold_search_used","2023_new_raw_or_replay_accessed",
        "2024_used_as_fresh_holdout","2024_used_to_define_new_runtime_rule","2025_accessed","production_changed")}
    write("governance_report.json",dict(task_id=pc.TASK,governance_declarations=declarations,
        begin="ACTIVE_GOVERNED_TASK_FROM_REV784",complete_verify="REQUIRED_AFTER_IMPLEMENTATION_COMMIT",
        governance_sync="REQUIRED_BEFORE_NEXT_TASK",research_branch_push=False,
        outcome="FAIL_CLOSED",scientific_conclusion="NONE",all_requested_points_closed=False))
    count=sum(x["tests"] for x in tests.values())
    write("evidence_snapshot.json",{
        "task_id":pc.TASK,"source_version_sha256":pre["source_version_sha256"],
        "test_results":tests,"total_synthetic_tests":count,"python_parse":"PASS",
        "old_tracked_sources_changed":False,"synthetic_only":True,
        "market_rows_read":0,"pnl_read":False,"economic_replay_executed":False,
        "known_inherited_arch_constant_fixture_warnings":12,
        "estimator_substitution":False,"gates_weakened":False,"new_independent_review":False,
        "note":"Early concurrent-edit runs are superseded by stable final JUnit evidence; green tests do not prove missing producer authority or economic profitability"})
    bound=[]
    for p in sorted(OUT.iterdir()):
        if p.is_file() and p.name!="canonical_result.json":
            bound.append({"path":p.relative_to(ROOT).as_posix(),"sha256":sha(p),"bytes":p.stat().st_size})
    result={"task_id":pc.TASK,"classification":"SYNTHETIC_IMPLEMENTATION_PROGRESS_REAL_SEMANTIC_AUTHORITY_INCOMPLETE",
        "outcome":"FAIL_CLOSED","scientific_conclusion":"NONE","source_version_sha256":pre["source_version_sha256"],
        "artifact_bindings":bound,"total_synthetic_tests":count,"all_eleven_gaps_closed":False,
        "packages_2_3_fully_closed":False,"historical_exchange_rules":"EXCLUDED_BY_USER_NOT_CLOSED",
        "independent_review":"WAIVED_NOT_PASS","ready_for_single_gate3_replay":False,
        "economic_replay_executed":False,"new_trades_created":0,"2024_rows_accessed":False,
        "2025_rows_accessed":False,"production_changed":False,"research_branch_push":False,
        "next_bottleneck":NEXT,"remaining_gap_ids":[x["id"] for x in gaps]}
    result_binding=write("canonical_result.json",result)
    print(json.dumps({"result":result_binding,"tests":count,"ready":False,"next_bottleneck":NEXT}))

if __name__=="__main__":main()
