"""Finalize blocked RD09B coverage and selection evidence."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from spotbot.research.rd09b_dune_feasibility import (
    SELECTION_WEIGHTS,
    BroadCoverage,
    SectorCoverage,
    validate_weights,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    validate_weights()
    account_path = REPORTS / "ams-rd09b-dune-account-usage-v1.json"
    account = json.loads(account_path.read_text(encoding="utf-8"))
    if account["decision"] != "RD09B_DUNE_CREDENTIAL_REQUIRED":
        raise RuntimeError("this blocked evidence runner requires a missing credential")
    queries = read_csv(REPORTS / "ams-rd09b-query-registry-v1.csv")
    mappings = read_csv(REPORTS / "ams-rd09b-entity-mapping-v1.csv")
    selected_namespaces = sorted(
        {
            row["namespace"]
            for row in read_csv(REPORTS / "ams-rd09b-namespace-selection-v1.csv")
            if row["selected"] == "True"
        }
    )
    broad = BroadCoverage(0, 0.0, 0.0, (0.0, 0.0, 0.0), (0, 0, 0), 0)
    sector = SectorCoverage(0, 0.0, (0.0, 0.0, 0.0), 0)
    write_csv(
        REPORTS / "ams-rd09b-metric-coverage-v1.csv",
        [
            {
                "namespace": namespace,
                "metric_bundle": "NATIVE_CHAIN_ACTIVITY",
                "registered_query_count": sum(row["namespace"] == namespace for row in queries),
                "executed_query_count": 0,
                "acquired_day_count": 0,
                "expected_day_count": 93,
                "daily_availability_proven": False,
                "causally_usable_asset_count": 0,
                "coverage_status": "NOT_ACQUIRED_CREDENTIAL_MISSING",
            }
            for namespace in selected_namespaces
        ],
        [
            "namespace",
            "metric_bundle",
            "registered_query_count",
            "executed_query_count",
            "acquired_day_count",
            "expected_day_count",
            "daily_availability_proven",
            "causally_usable_asset_count",
            "coverage_status",
        ],
    )
    write_csv(
        REPORTS / "ams-rd09b-fold-coverage-v1.csv",
        [
            {
                "fold_id": fold,
                "pit_panel_rows": "NOT_RECOMPUTED_WITHOUT_ACQUISITION",
                "causally_covered_rows": 0,
                "coverage": 0.0,
                "median_usable_symbols": 0,
                "broad_gate_passed": False,
                "sector_gate_passed": False,
            }
            for fold in ("WF01", "WF02", "WF03")
        ],
        [
            "fold_id",
            "pit_panel_rows",
            "causally_covered_rows",
            "coverage",
            "median_usable_symbols",
            "broad_gate_passed",
            "sector_gate_passed",
        ],
    )
    write_csv(
        REPORTS / "ams-rd09b-causal-audit-v1.csv",
        [
            {
                "namespace": namespace,
                "metric_bundle": "NATIVE_CHAIN_ACTIVITY",
                "raw_event_or_block_timestamp": True,
                "immutable_historical_events": True,
                "daily_reconstruction_deterministic": True,
                "current_survivor_list_required": False,
                "event_time_mapping_valid": True,
                "design_causal_grade": "B_RECONSTRUCTABLE_FROM_RAW_CHAIN",
                "pilot_acquisition_verified": False,
                "operational_causal_grade": "E_NOT_CAUSALLY_USABLE",
                "notes": "Query design is causal; acquisition was blocked before evidence.",
            }
            for namespace in selected_namespaces
        ],
        [
            "namespace",
            "metric_bundle",
            "raw_event_or_block_timestamp",
            "immutable_historical_events",
            "daily_reconstruction_deterministic",
            "current_survivor_list_required",
            "event_time_mapping_valid",
            "design_causal_grade",
            "pilot_acquisition_verified",
            "operational_causal_grade",
            "notes",
        ],
    )
    score = {
        "source_id": "DUNE_RAW_ONCHAIN",
        "causal_integrity": 30,
        "pit_coverage": 0,
        "reproducibility": 12,
        "economic_information_independence": 15,
        "cost_licensing_suitability": 4,
        "native_frequency_latency_suitability": 4,
        "total_score": 65,
        "causal_grade": "B_RECONSTRUCTABLE_FROM_RAW_CHAIN",
        "pilot_acquisition_complete": False,
        "broad_coverage_gate_passed": broad.passed,
        "sector_coverage_gate_passed": sector.passed,
        "zero_paid_spending": True,
        "predictive_metric_used": False,
        "selection_gate_passed": False,
    }
    write_csv(
        REPORTS / "ams-rd09b-source-selection-score-v1.csv",
        [score],
        list(score),
    )
    safety = {
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "signal_computation_authorized": False,
        "label_computation_authorized": False,
        "portfolio_simulation_authorized": False,
        "portfolio_construction_authorized": False,
        "production_change_authorized": False,
        "live_ready": False,
        "production_ready": False,
        "trade_logic_changed": False,
        "spot_only": True,
        "long_only": True,
        "no_leverage": True,
        "no_margin": True,
        "no_futures": True,
        "no_shorts": True,
        "no_borrowing": True,
        "no_interest": True,
        "no_dca": True,
        "no_kelly": True,
        "no_averaging_down": True,
        "no_pyramiding": True,
    }
    final = {
        "stage": "RD09B-DUNE-ZERO-SPEND-RAW-CHAIN-FEASIBILITY",
        "status": "BLOCKED",
        "decision": "RD09B_DUNE_CREDENTIAL_REQUIRED",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "upstream_rd09_decision": ("RD09_NEW_INFORMATION_SOURCE_FEASIBILITY_NOT_CONFIRMED"),
        "credential_present": False,
        "zero_spend_attested": bool(account["zero_spend_attested"]),
        "user_attested_spend_limit_usd": account["user_attested_spend_limit_usd"],
        "credits_included": None,
        "credits_used": None,
        "credits_consumed": 0,
        "api_requests_executed": 0,
        "execution_mode": "BLOCKED_BEFORE_API",
        "selected_namespaces": selected_namespaces,
        "registered_query_count": len(queries),
        "executed_query_count": 0,
        "pilot_row_count": 0,
        "broad_coverage_gate_passed": broad.passed,
        "sector_coverage_gate_passed": sector.passed,
        "updated_dune_selection_score": 65,
        "full_source_freeze_protocol_authorized": False,
        "full_source_freeze_authorized": False,
        "alpha_protocol_authorized": False,
        "next_stage": "DUNE_CREDENTIAL_AND_ZERO_SPEND_ATTESTATION_REQUIRED",
        "mapping_rows": len(mappings),
        "silent_entity_exclusions": 0,
        "selection_weights": SELECTION_WEIGHTS,
        "safety": safety,
    }
    final_path = REPORTS / "ams-rd09b-final-decision-v1.json"
    write_text(final_path, json.dumps(final, indent=2, sort_keys=True) + "\n")
    markdown = (
        "# RD09B Dune Zero-Spend Feasibility\n\n"
        "- Status: `BLOCKED`\n"
        "- Decision: `RD09B_DUNE_CREDENTIAL_REQUIRED`\n"
        "- Credential present: `false`\n"
        "- Zero-spend attestation: `false`\n"
        "- API requests: `0`\n"
        "- Credits consumed: `0`\n"
        f"- Selected query-pack namespaces: `{', '.join(selected_namespaces)}`\n"
        f"- Registered manual queries: `{len(queries)}`\n"
        "- Broad coverage: `NOT TESTABLE WITHOUT ACQUISITION`\n"
        "- Sector coverage: `NOT TESTABLE WITHOUT ACQUISITION`\n"
        "- Updated Dune score: `65`; selection gate remains `false`.\n"
        "- No signal, label, predictive metric, portfolio, 2025, or 2026 access.\n"
    )
    write_text(REPORTS / "ams-rd09b-final-decision-v1.md", markdown)
    write_text(ROOT / "RD09B_DUNE_FEASIBILITY_RESULT_FOR_CHATGPT.md", markdown)
    output_paths = [
        REPORTS / "ams-rd09b-dune-account-usage-v1.json",
        REPORTS / "ams-rd09b-dune-catalog-v1.csv",
        REPORTS / "ams-rd09b-namespace-selection-v1.csv",
        REPORTS / "ams-rd09b-entity-mapping-v1.csv",
        REPORTS / "ams-rd09b-query-registry-v1.csv",
        REPORTS / "ams-rd09b-query-execution-manifest-v1.csv",
        REPORTS / "ams-rd09b-pilot-quality-v1.csv",
        REPORTS / "ams-rd09b-metric-coverage-v1.csv",
        REPORTS / "ams-rd09b-fold-coverage-v1.csv",
        REPORTS / "ams-rd09b-causal-audit-v1.csv",
        REPORTS / "ams-rd09b-credit-usage-v1.csv",
        REPORTS / "ams-rd09b-source-selection-score-v1.csv",
        REPORTS / "ams-rd09b-manual-query-registry-v1.csv",
        final_path,
        REPORTS / "ams-rd09b-final-decision-v1.md",
    ]
    output_paths.extend(sorted((REPORTS / "rd09b-queries").glob("*.sql")))
    write_csv(
        REPORTS / "ams-rd09b-output-hashes-v1.csv",
        [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in output_paths
        ],
        ["path", "sha256", "size_bytes"],
    )
    print("RD09B_STATUS=BLOCKED")
    print("RD09B_DECISION=RD09B_DUNE_CREDENTIAL_REQUIRED")
    print("EXECUTED_QUERIES=0")
    print("CREDITS_CONSUMED=0")
    print("UPDATED_DUNE_SCORE=65")


if __name__ == "__main__":
    main()
