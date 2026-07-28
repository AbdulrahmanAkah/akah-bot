"""Audit RD07 matched Binance coverage against the frozen RD06 PIT panel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from spotbot.research.rd07_coverage_audit import (
    attach_match_flags,
    decision_metrics,
    evaluate_gate,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    index_path = REPORTS / "ams-rd06-p1-panel-index-v1.parquet"
    assignment_path = REPORTS / "ams-rd06-p1-fold-grid-assignments-v1.csv"
    mapping_path = REPORTS / "ams-rd07-binance-symbol-mapping-v1.csv"
    index = pd.read_parquet(index_path)
    mapping = pd.read_csv(mapping_path)
    close_times: dict[str, set[pd.Timestamp]] = {}
    lineage: list[dict[str, object]] = []
    for row in mapping.itertuples(index=False):
        symbol = str(row.kucoin_canonical_symbol)
        raw_path = str(row.parquet_path)
        if not raw_path:
            close_times[symbol] = set()
            continue
        path = ROOT / raw_path
        if not path.exists():
            close_times[symbol] = set()
            continue
        frame = pd.read_parquet(path, columns=["open_time"])
        times = set(pd.to_datetime(frame["open_time"], utc=True) + pd.Timedelta(hours=4))
        close_times[symbol] = times
        lineage.append(
            {
                "symbol": symbol,
                "path": raw_path,
                "sha256": sha256(path),
                "registered_sha256": str(row.parquet_sha256),
                "hash_match": sha256(path) == str(row.parquet_sha256),
                "close_time_count": len(times),
            }
        )
    matched = attach_match_flags(index, close_times)
    decisions = decision_metrics(matched)
    assignments = pd.read_csv(assignment_path)
    assignments["decision_time"] = pd.to_datetime(assignments["decision_time"], utc=True)
    validation = matched.merge(
        assignments[["fold_id", "decision_time", "grid_id"]],
        on=["decision_time", "grid_id"],
        how="inner",
        validate="many_to_one",
    )
    fold_grid = (
        validation.groupby(["fold_id", "grid_id"], observed=True)["matched"]
        .agg(["count", "sum", "mean"])
        .reset_index()
        .rename(
            columns={
                "count": "pit_panel_rows",
                "sum": "matched_panel_rows",
                "mean": "matched_row_share",
            }
        )
    )
    symbol_frame = (
        matched.groupby("symbol", observed=True)["matched"]
        .agg(["count", "sum", "mean"])
        .reset_index()
        .rename(
            columns={
                "count": "pit_panel_rows",
                "sum": "matched_panel_rows",
                "mean": "matched_row_share",
            }
        )
    )
    passed, blockers = evaluate_gate(matched, decisions, fold_grid)
    decision = (
        "RD07_EXTERNAL_SPOT_DATA_COVERAGE_COMPLETE"
        if passed
        else "RD07_EXTERNAL_SPOT_DATA_COVERAGE_INSUFFICIENT"
    )
    report = {
        "stage": "RD07-CROSS-VENUE-COVERAGE-AUDIT",
        "status": "COMPLETE" if passed else "BLOCKED",
        "decision": decision,
        "next_stage": "RD07-MATCHED-PANEL" if passed else "RD07_TERMINATION_OR_NEW_DATA",
        "signal_diagnostic_authorized": passed,
        "overall_matched_panel_row_coverage": float(matched["matched"].mean()),
        "median_decision_matched_symbol_share": float(decisions["matched_symbol_share"].median()),
        "minimum_fold_grid_matched_coverage": float(fold_grid["matched_row_share"].min()),
        "minimum_matched_symbols_per_decision": int(decisions["matched_symbol_count"].min()),
        "pit_panel_rows": len(matched),
        "matched_panel_rows": int(matched["matched"].sum()),
        "decision_count": len(decisions),
        "blockers": blockers,
        "source_hash_failures": sum(not bool(row["hash_match"]) for row in lineage),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "portfolio_construction_authorized": False,
    }
    decisions.to_csv(REPORTS / "ams-rd07-coverage-by-decision-v1.csv", index=False)
    fold_grid.to_csv(REPORTS / "ams-rd07-coverage-by-fold-grid-v1.csv", index=False)
    symbol_frame.to_csv(REPORTS / "ams-rd07-coverage-by-symbol-v1.csv", index=False)
    pd.DataFrame(lineage).to_csv(
        REPORTS / "ams-rd07-coverage-source-reconciliation-v1.csv", index=False
    )
    write_json(REPORTS / "ams-rd07-coverage-audit-v1.json", report)
    (REPORTS / "ams-rd07-coverage-audit-v1.md").write_text(
        "# RD07 Coverage Audit\n\n"
        f"- Status: `{report['status']}`\n"
        f"- Decision: `{decision}`\n"
        f"- Overall coverage: `{report['overall_matched_panel_row_coverage']}`\n"
        f"- Median decision share: `{report['median_decision_matched_symbol_share']}`\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
