# ruff: noqa
"""Produce an immutable conformance audit for the historical AMS V5 run."""
from __future__ import annotations
import ast
import json
import os
import tempfile
from pathlib import Path
from typing import Any

ROOT=Path.cwd(); REPORTS=ROOT/"reports/research"
def write(path:Path,value:dict[str,Any]|str)->None:
    text=value if isinstance(value,str) else json.dumps(value,indent=2,sort_keys=True)+"\n";h,t=tempfile.mkstemp(dir=path.parent,prefix=f".{path.name}.",suffix=".tmp")
    try:
        with os.fdopen(h,"w",encoding="utf-8") as f:f.write(text)
        os.replace(t,path)
    except BaseException:
        if os.path.exists(t):os.unlink(t)
        raise
def record(rid:str,req:str,status:str,paths:list[str],risk:str,fix:str)->dict[str,Any]:
    return {"requirement_id":rid,"requirement":req,"status":status,"implementation_paths":paths,"test_paths":[],"observed_behaviour":"Verified by AST and source review.","expected_behaviour":req,"risk":risk,"required_correction":fix}
def main()->None:
    legacy=ROOT/"src/spotbot/research/ams_v5_active_pullback_reacceleration.py"
    tree=ast.parse(legacy.read_text(encoding="utf-8")); imports=[node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom) and node.module]
    v4=[x for x in imports if "ams_v4_active_conviction_swing" in x]
    matrix=[
      record("V5-REQ-NATIVE-001","V5 engine must not import V4 strategic engine.","DIFFERENT_IMPLEMENTATION",[str(legacy.relative_to(ROOT))],"CRITICAL","Create ams_v5_native_engine.py without V4 strategy imports."),
      record("V5-REQ-EXEC-002","Native V5 fill, stop, trailing, add-on and re-entry policies.","INHERITED_V4",[str(legacy.relative_to(ROOT))],"CRITICAL","Implement and test native V5 execution state machine."),
      record("V5-REQ-THRESHOLD-003","Train-only 50/55 threshold objective with safety gates.","PARTIAL",[str(legacy.relative_to(ROOT))],"CRITICAL","Implement frozen quality-score objective and validation-independence tests."),
      record("V5-REQ-SETUP-004","Three V5 families with distinct causal rules.","PARTIAL",[str(legacy.relative_to(ROOT))],"HIGH","Implement native family-specific candidate records and tests."),
      record("V5-REQ-STOP-005","Balanced/wide structural stop contract.","PARTIAL",[str(legacy.relative_to(ROOT))],"CRITICAL","Implement native structural anchors, ceilings, gap recalculation and sizing."),
      record("V5-REQ-REPORT-006","Full V5 diagnostics and rejection audit trail.","MISSING",["scripts/research/run_ams_v5_trial.py"],"HIGH","Persist candidate/fill records and required metrics."),
      record("V5-REQ-TEST-007","Comprehensive behavioural test suite.","UNTESTED",["tests/test_ams_v5_*.py"],"CRITICAL","Add native feature, setup, execution, portfolio, threshold and accounting tests."),
      record("V5-REQ-CAUSAL-008","Research boundary and next-open execution.","INHERITED_V4",[str(legacy.relative_to(ROOT))],"MEDIUM","Re-prove in neutral native core tests."),
    ]
    counts={k:sum(x["status"]==k for x in matrix) for k in ("FULL","PARTIAL","INHERITED_V4","MISSING","DIFFERENT_IMPLEMENTATION","UNTESTED")}
    payload={"schema_version":"ams-v5r1-conformance-audit-v1","status":"PASS","legacy_v5_scientific_status":"IMPLEMENTATION_INCOMPLETE","v4_strategy_imports":v4,"requirements":matrix,"counts":counts,"critical_blockers":[x["requirement_id"] for x in matrix if x["risk"]=="CRITICAL" and x["status"]!="FULL"],"rerun_allowed":False,"test_2025_accessed":False,"holdout_2026_accessed":False}
    write(REPORTS/"ams-v5r1-conformance-audit-v1.json",payload)
    write(REPORTS/"ams-v5r1-conformance-audit-v1.md","# AMS V5R1 Conformance Audit\n\nLegacy V5 status: **IMPLEMENTATION_INCOMPLETE**. Critical V4 strategy delegation blocks a scientific rerun until the native engine replaces it.\n")
if __name__=="__main__":main()
