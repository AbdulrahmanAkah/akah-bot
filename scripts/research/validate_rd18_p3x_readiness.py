from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd18_p3x_readiness import (  # noqa: E402
    DECISION_BOTH_REQUIRED,
    DECISION_DATA_REQUIRED,
    DECISION_GENERATOR_REQUIRED,
    DECISION_READY,
    EXPECTED_C2_PAIRS,
    sha256_path,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Validate RD18-P3X readiness outputs offline.")
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "research" / "rd18_p3x_runtime",
    )
    result.add_argument("--offline", action="store_true", required=True)
    return result


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def validate(output_dir: Path) -> dict[str, object]:
    output_dir = output_dir.resolve()
    report = load_json(output_dir / "rd18-p3x-runtime-report-v1.json")
    request = load_json(output_dir / "request-manifest.json")
    inputs = load_json(output_dir / "input-reconciliation.json")
    manifest = load_json(output_dir / "output-manifest.json")
    with (output_dir / "full-c2-hourly-acquisition-plan.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        plan = list(csv.DictReader(handle))
    checks = {
        "network_requests_zero": request.get("network_requests") == 0,
        "input_hashes_reconciled": inputs.get("all_inputs_match") is True,
        "c2_plan_count": len(plan) == EXPECTED_C2_PAIRS,
        "c2_pairs_unique": len({row["pair"] for row in plan}) == len(plan),
        "no_post_2024_required_end": all(
            row["required_last_close"] == "2025-01-01T00:00:00+00:00" for row in plan
        ),
        "known_decision": report.get("decision")
        in {
            DECISION_READY,
            DECISION_DATA_REQUIRED,
            DECISION_GENERATOR_REQUIRED,
            DECISION_BOTH_REQUIRED,
        },
        "replay_not_authorized": not bool(
            dict(report.get("authorizations", {})).get("strategy_replay_authorized", True)
        ),
        "returns_not_authorized": not bool(
            dict(report.get("authorizations", {})).get("return_calculation_authorized", True)
        ),
    }
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list):
        checks["manifest_shape"] = False
    else:
        checks["manifest_shape"] = True
        for item in manifest_files:
            if not isinstance(item, dict):
                checks["manifest_shape"] = False
                continue
            path = output_dir / str(item.get("path", ""))
            checks[f"hash:{item.get('path')}"] = path.is_file() and sha256_path(path) == item.get(
                "sha256"
            )
    passed = all(checks.values())
    return {"passed": passed, "checks": checks, "decision": report.get("decision")}


def main() -> int:
    args = parser().parse_args()
    result = validate(args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
