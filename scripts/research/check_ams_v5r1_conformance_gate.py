"""Fail closed unless all V5R1 Native conformance evidence is complete."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def load(name: str) -> dict[str, Any]:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def strategic_v4_dependencies() -> list[str]:
    dependencies: list[str] = []
    paths = [ROOT / "src/spotbot/research/ams_v5_native_engine.py"]
    paths.extend(ROOT.glob("scripts/research/*ams_v5r1*.py"))
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            dependencies.extend(
                name for name in names if "ams_v4_active_conviction_swing" in name
            )
    return dependencies


def evaluate() -> dict[str, Any]:
    audit = load("ams-v5r1-conformance-audit-v1.json")
    integration = load("ams-v5r1-native-engine-integration-v1.json")
    shadow = load("ams-v5r1-shadow-validation-v1.json")
    critical = [item for item in audit["requirements"] if item["risk"] == "CRITICAL"]
    not_full = [item for item in critical if item["status"] != "FULL"]
    missing_paths = [
        item["requirement_id"]
        for item in critical
        if not item["implementation_paths"] or not item["test_paths"]
    ]
    dependencies = strategic_v4_dependencies()
    checks = {
        "native_integration": integration["status"] == "PASS",
        "shadow_validation": shadow["status"] == "PASS",
        "critical_requirements_full": not not_full,
        "critical_paths_present": not missing_paths,
        "strategic_v4_dependencies_zero": not dependencies,
        "pnl_reconciliation": shadow["pnl_reconciliation"] == "PASS",
        "open_positions_after_fold": shadow["open_positions_after_fold"] == 0,
        "boundary_flags": not shadow["test_2025_accessed"]
        and not shadow["holdout_2026_accessed"],
        "pretrial_budget": audit["v5r1_trials_executed"] == 0
        and audit["v5r1_trials_remaining"] == 24,
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "critical_count": len(critical),
        "critical_not_full": len(not_full),
        "missing_paths": missing_paths,
        "dependencies": dependencies,
        "integration": integration,
        "shadow": shadow,
        "audit": audit,
    }


def main() -> None:
    result = evaluate()
    values = {
        "CONFORMANCE_GATE": result["status"],
        "NATIVE_INTEGRATION": result["integration"]["status"],
        "SHADOW_VALIDATION": result["shadow"]["status"],
        "CRITICAL_REQUIREMENTS_NOT_FULL": result["critical_not_full"],
        "STRATEGIC_V4_DEPENDENCIES": len(result["dependencies"]),
        "PNL_RECONCILIATION": result["shadow"]["pnl_reconciliation"],
        "OPEN_POSITIONS_AFTER_FOLD": result["shadow"]["open_positions_after_fold"],
        "V5R1_TRIALS_EXECUTED": result["audit"]["v5r1_trials_executed"],
        "V5R1_TRIALS_REMAINING": result["audit"]["v5r1_trials_remaining"],
        "TEST_2025_ACCESSED": str(result["shadow"]["test_2025_accessed"]).lower(),
        "HOLDOUT_2026_ACCESSED": str(result["shadow"]["holdout_2026_accessed"]).lower(),
    }
    print("\n".join(f"{key}={value}" for key, value in values.items()))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
