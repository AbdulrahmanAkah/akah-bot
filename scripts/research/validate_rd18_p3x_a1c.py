from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

EXPECTED_PAIRS = {"ETN-USDT", "STRAX-USDT"}
EXPECTED_SEGMENT_TYPES = {
    "PRE_EVENT_IDENTITY",
    "SUSPENSION_OR_MIGRATION_GAP",
    "POST_EVENT_IDENTITY",
}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Validate RD18-P3X-A1C corporate-action outputs offline."
    )
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--offline", action="store_true")
    return result


def _read_json(path: Path) -> dict[str, Any]:
    raw: object = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return dict(raw)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise SystemExit("A1C validator requires --offline")

    output = args.output_dir.resolve()
    event_path = output / "corporate-action-event-ledger.csv"
    segment_path = output / "corporate-action-segment-ledger.csv"
    terminal_path = output / "corporate-action-terminal-classification.csv"
    report_path = output / "rd18-p3x-a1c-runtime-report-v1.json"
    manifest_path = output / "output-manifest.json"

    required = (
        event_path,
        segment_path,
        terminal_path,
        report_path,
        manifest_path,
    )
    checks: dict[str, bool] = {f"file:{path.name}": path.is_file() for path in required}
    if not all(checks.values()):
        result = {
            "schema_version": "rd18-p3x-a1c-runtime-validation-v1",
            "passed": False,
            "checks": checks,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    events = _read_csv(event_path)
    segments = _read_csv(segment_path)
    terminals = _read_csv(terminal_path)
    report = _read_json(report_path)
    manifest = _read_json(manifest_path)

    checks.update(
        {
            "report_schema": (report.get("schema_version") == "rd18-p3x-a1c-runtime-report-v1"),
            "report_passed": report.get("passed") is True,
            "events_count": len(events) == 2,
            "segments_count": len(segments) == 6,
            "terminals_count": len(terminals) == 2,
            "event_pairs": {row.get("pair", "") for row in events} == EXPECTED_PAIRS,
            "terminal_pairs": {row.get("pair", "") for row in terminals} == EXPECTED_PAIRS,
            "segment_pairs": {row.get("pair", "") for row in segments} == EXPECTED_PAIRS,
            "segment_types": {row.get("segment_type", "") for row in segments}
            == EXPECTED_SEGMENT_TYPES,
            "three_segments_per_pair": all(
                sum(row.get("pair") == pair for row in segments) == 3 for pair in EXPECTED_PAIRS
            ),
            "strategy_use_blocked": all(
                row.get("strategy_use_authorized") == "False" for row in terminals
            ),
            "candidate_generation_blocked": all(
                row.get("candidate_generation_authorized") == "False" for row in terminals
            ),
            "normalization_blocked": all(
                row.get("normalization_authorized") == "False" for row in terminals
            ),
            "raw_gap_fill_blocked": all(
                row.get("raw_gap_filling_authorized") == "False" for row in terminals
            ),
            "gap_has_no_raw_or_synthetic_rows": all(
                row.get("raw_rows_authorized") == "False"
                and row.get("synthetic_rows_authorized") == "False"
                for row in segments
                if row.get("segment_type") == "SUSPENSION_OR_MIGRATION_GAP"
            ),
            "identity_not_continuous": all(
                row.get("identity_continuity_with_previous") == "False" for row in segments
            ),
            "sealed_cutoff": (report.get("sealed_cutoff") == "2025-01-01T00:00:00+00:00"),
            "next_stage": (
                report.get("next_stage")
                == ("RD18_P3X_A2_C2_GENERATOR_BUILD_WITH_A1B_GATE_AND_A1C_EXCLUSIONS")
            ),
            "manifest_schema": (
                manifest.get("schema_version") == "rd18-p3x-a1c-output-manifest-v1"
            ),
            "manifest_network_zero": manifest.get("network_requests") == 0,
            "manifest_raw_zero": (manifest.get("raw_market_data_written") is False),
            "manifest_synthetic_zero": (manifest.get("synthetic_candles_written") is False),
            "manifest_normalization_zero": (manifest.get("normalization_executed") is False),
            "manifest_generation_zero": (
                manifest.get("strategy_candidate_generation_executed") is False
            ),
            "manifest_replay_zero": (manifest.get("strategy_replay_executed") is False),
            "manifest_returns_zero": (manifest.get("return_calculation_executed") is False),
        }
    )

    raw_files = manifest.get("files")
    manifest_files_ok = isinstance(raw_files, list)
    if manifest_files_ok:
        rows = [dict(item) for item in raw_files if isinstance(item, dict)]
        manifest_files_ok = len(rows) == len(raw_files)
        expected_names = {
            event_path.name,
            segment_path.name,
            terminal_path.name,
            report_path.name,
        }
        manifest_files_ok = (
            manifest_files_ok and {str(row.get("path", "")) for row in rows} == expected_names
        )
        for row in rows:
            path = output / str(row.get("path", ""))
            checks[f"bytes:{path.name}"] = path.stat().st_size == int(row.get("bytes", -1))
            checks[f"hash:{path.name}"] = _sha256(path) == str(row.get("sha256", ""))
    checks["manifest_files"] = manifest_files_ok

    passed = all(checks.values())
    result = {
        "schema_version": "rd18-p3x-a1c-runtime-validation-v1",
        "passed": passed,
        "checks": checks,
        "events": len(events),
        "segments": len(segments),
        "terminal_classifications": len(terminals),
        "output_dir": str(output),
        "network_requests": 0,
    }
    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
