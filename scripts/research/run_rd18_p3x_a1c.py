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

from spotbot.research.rd18_p3x_a1c_corporate_actions import (  # noqa: E402
    EVENT_FIELDS,
    SEGMENT_FIELDS,
    TERMINAL_FIELDS,
    build_a1c,
    deterministic_manifest,
    load_json,
    write_csv,
    write_json,
)

EXPECTED_PLAN_ROWS = 364


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Build RD18-P3X-A1C fail-closed corporate-action ledgers "
            "without market-data writes, normalization, candidate generation, "
            "strategy replay, or returns."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--a1-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1c_runtime",
    )
    result.add_argument(
        "--write-ledgers",
        action="store_true",
        help="Required acknowledgement for deterministic local ledger writes.",
    )
    return result


def _read_plan(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"A1 plan is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if len(rows) != EXPECTED_PLAN_ROWS:
        raise SystemExit(f"expected {EXPECTED_PLAN_ROWS} A1 plan rows, found {len(rows)}")
    pairs = [row.get("pair", "") for row in rows]
    if len(set(pairs)) != len(pairs):
        raise SystemExit("A1 plan contains duplicate pairs")
    return rows


def main() -> int:
    args = parser().parse_args()
    if not args.write_ledgers:
        raise SystemExit("A1C requires --write-ledgers")

    repo = args.repo_root.resolve()
    a1_runtime = args.a1_runtime.resolve()
    output = args.output_dir.resolve()

    registry_path = repo / "data/research/rd18_p3x_a1/corporate-action-registry-v1.json"
    protocol_path = (
        repo / "data/research/rd18_p3x_a1/rd18-p3x-a1c-causal-corporate-action-policy-v1.json"
    )
    plan_path = a1_runtime / "full-c2-hourly-acquisition-plan.csv"
    checkpoint_path = a1_runtime / "acquisition-checkpoint.json"

    for path in (registry_path, protocol_path, checkpoint_path):
        if not path.is_file():
            raise SystemExit(f"required A1C input is missing: {path}")

    result = build_a1c(
        registry=load_json(registry_path),
        protocol=load_json(protocol_path),
        plan_rows=_read_plan(plan_path),
        checkpoint=load_json(checkpoint_path),
    )

    output.mkdir(parents=True, exist_ok=True)
    event_name = "corporate-action-event-ledger.csv"
    segment_name = "corporate-action-segment-ledger.csv"
    terminal_name = "corporate-action-terminal-classification.csv"
    report_name = "rd18-p3x-a1c-runtime-report-v1.json"

    write_csv(output / event_name, result.events, EVENT_FIELDS)
    write_csv(output / segment_name, result.segments, SEGMENT_FIELDS)
    write_csv(output / terminal_name, result.terminals, TERMINAL_FIELDS)
    write_json(output / report_name, result.report)

    names = (event_name, segment_name, terminal_name, report_name)
    manifest = deterministic_manifest(output, names)
    write_json(output / "output-manifest.json", manifest)

    response = {
        **result.report,
        "output_dir": str(output),
        "output_manifest": str(output / "output-manifest.json"),
        "network_requests": 0,
        "raw_market_data_written": False,
    }
    print(json.dumps(response, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
