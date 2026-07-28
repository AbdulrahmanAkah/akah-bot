"""Run the frozen RD04-D5E0 midweek pullback diagnostic on D5B2 control trades."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from spotbot.research.rd04_midweek_pullback_diagnostic import (
    EXPECTED_TRADE_COUNT,
    ORIGINAL_TRADE_FIELDS,
    RESEARCH_STAGE,
    SCHEMA_VERSION,
    MidweekPullbackError,
    OutputRow,
    TradeRow,
    entry_diagnostics,
    fold_metrics,
    paths_for_trades,
    pattern_gate,
    projection_fingerprint,
    validate_four_hour,
    validate_input_trades,
    validate_projection,
    weekday_metrics,
    weekly_low_distribution,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D4_REPORT = REPORTS / "ams-rd04-d4-hypothesis-registry-v1.json"
D5B1_REPORT = REPORTS / "ams-rd04-d5b1-stop-protocol-adjudication-v1.json"
D5B2_REPORT = REPORTS / "ams-rd04-d5b2-structural-stop-evaluation-v1.json"
D0C_REPORT = REPORTS / "ams-rd04-d0c-adjudicated-dataset-registration-v1.json"
TRADE_SOURCE = REPORTS / "ams-rd04-d5b2-base-cost-trades-v1.csv"

REPORT_JSON = REPORTS / "ams-rd04-d5e0-midweek-pullback-diagnostic-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5e0-midweek-pullback-diagnostic-v1.md"
ENTRY_DIAGNOSTICS_CSV = REPORTS / "ams-rd04-d5e0-entry-diagnostics-v1.csv"
ENTRY_WEEKDAY_CSV = REPORTS / "ams-rd04-d5e0-entry-weekday-metrics-v1.csv"
PATHS_CSV = REPORTS / "ams-rd04-d5e0-weekly-path-samples-v1.csv"
LOW_DISTRIBUTION_CSV = REPORTS / "ams-rd04-d5e0-weekly-low-distribution-v1.csv"
TUESDAY_FRIDAY_CSV = REPORTS / "ams-rd04-d5e0-tuesday-signal-to-friday-v1.csv"
FOLD_METRICS_CSV = REPORTS / "ams-rd04-d5e0-fold-metrics-v1.csv"
PATTERN_GATE_CSV = REPORTS / "ams-rd04-d5e0-pattern-gate-v1.csv"
FINAL_COPY = ROOT / "RD04_D5E0_RESULT_FOR_CHATGPT.md"


class MidweekDiagnosticRunError(RuntimeError):
    """Raised when the frozen D5E0 runner contract is violated."""


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MidweekDiagnosticRunError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    temporary.replace(path)


def read_trades(path: Path) -> tuple[list[str], list[TradeRow]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise MidweekDiagnosticRunError("D5B2 trade source has no header")
        fields = [str(field) for field in reader.fieldnames]
        rows: list[TradeRow] = []
        for record in reader:
            row: TradeRow = {}
            for key, value in record.items():
                if key is None or value is None:
                    raise MidweekDiagnosticRunError("D5B2 trade source contains a null cell")
                row[str(key)] = str(value)
            rows.append(row)
    return fields, rows


def output_fields(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    return fields


def required_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MidweekDiagnosticRunError(f"missing mapping: {label}")
    return cast(Mapping[str, Any], value)


def registered_dataset_path(d0c: Mapping[str, Any]) -> Path:
    datasets = required_mapping(d0c.get("datasets"), "D0C datasets")
    four_hour = required_mapping(datasets.get("four_hour"), "D0C four_hour")
    relative = four_hour.get("path")
    if not isinstance(relative, str):
        raise MidweekDiagnosticRunError("D0C 4H path is missing")
    return ROOT / relative


def verify_upstream() -> dict[str, Any]:
    d4 = load_json(D4_REPORT)
    d5b1 = load_json(D5B1_REPORT)
    d5b2 = load_json(D5B2_REPORT)
    d0c = load_json(D0C_REPORT)
    if d4.get("status") != "COMPLETE":
        raise MidweekDiagnosticRunError("RD04-D4 is not COMPLETE")
    hypotheses = d4.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise MidweekDiagnosticRunError("RD04-D4 hypotheses are missing")
    hypothesis = next(
        (
            item
            for item in hypotheses
            if isinstance(item, Mapping)
            and item.get("hypothesis_id") == "RD04-D5E-MIDWEEK-PULLBACK-DIAGNOSTIC"
        ),
        None,
    )
    if not isinstance(hypothesis, Mapping):
        raise MidweekDiagnosticRunError("RD04-D5E hypothesis is not registered")
    frozen = required_mapping(hypothesis.get("frozen_parameters"), "D5E frozen parameters")
    if frozen.get("week_start") != "MONDAY_00_00":
        raise MidweekDiagnosticRunError("D5E week boundary changed")
    if frozen.get("primary_weekday") != "TUESDAY":
        raise MidweekDiagnosticRunError("D5E primary weekday changed")
    if frozen.get("all_weekdays_reported") is not True:
        raise MidweekDiagnosticRunError("D5E all-weekday reporting was disabled")
    if frozen.get("reentry_attempts_if_later_tested") != 1:
        raise MidweekDiagnosticRunError("D5E reentry contract changed")
    if frozen.get("averaging_down_allowed") is not False:
        raise MidweekDiagnosticRunError("D5E averaging-down constraint changed")
    if frozen.get("pyramiding_allowed") is not False:
        raise MidweekDiagnosticRunError("D5E risk constraints changed")
    if d5b1.get("status") != "COMPLETE":
        raise MidweekDiagnosticRunError("RD04-D5B1 is not COMPLETE")
    d5b1_decision = required_mapping(d5b1.get("decision"), "D5B1 decision")
    if d5b1_decision.get("structural_pass") is not True:
        raise MidweekDiagnosticRunError("registered structural protocol does not pass")
    if d5b2.get("status") != "COMPLETE":
        raise MidweekDiagnosticRunError("RD04-D5B2 is not COMPLETE")
    output_hashes = required_mapping(d5b2.get("output_hashes"), "D5B2 output hashes")
    trade_key = TRADE_SOURCE.relative_to(ROOT).as_posix()
    expected_trade_hash = output_hashes.get(trade_key)
    if not isinstance(expected_trade_hash, str):
        raise MidweekDiagnosticRunError("D5B2 control-trade hash is missing")
    if file_sha256(TRADE_SOURCE) != expected_trade_hash:
        raise MidweekDiagnosticRunError("D5B2 control-trade hash mismatch")
    pit = required_mapping(d5b2.get("pit_comparison"), "D5B2 PIT comparison")
    base = required_mapping(pit.get("BASE_COST"), "D5B2 BASE_COST")
    if base.get("control_trade_count") != EXPECTED_TRADE_COUNT:
        raise MidweekDiagnosticRunError("D5B2 does not register 153 PIT control trades")
    if d0c.get("status") != "PASS":
        raise MidweekDiagnosticRunError("D0C adjudicated dataset is not PASS")
    four_hour_path = registered_dataset_path(d0c)
    four_hour = required_mapping(
        required_mapping(d0c.get("datasets"), "D0C datasets").get("four_hour"), "D0C 4H"
    )
    expected_dataset_hash = four_hour.get("file_sha256")
    if not isinstance(expected_dataset_hash, str):
        raise MidweekDiagnosticRunError("D0C 4H SHA256 is missing")
    if file_sha256(four_hour_path) != expected_dataset_hash:
        raise MidweekDiagnosticRunError("D0C 4H SHA256 mismatch")
    return {
        "d4_hypothesis_status": hypothesis.get("status"),
        "d5b1_structural_pass": True,
        "d5b2_trade_source_sha256": expected_trade_hash,
        "d0c_four_hour_path": four_hour_path.relative_to(ROOT).as_posix(),
        "d0c_four_hour_sha256": expected_dataset_hash,
    }


def weekly_path_rows(paths: Sequence[Any]) -> list[OutputRow]:
    return [
        {
            "fold_id": path.fold_id,
            "symbol": path.symbol,
            "week_start": path.week_start.isoformat().replace("+00:00", "Z"),
            "weekly_path_complete": path.complete,
            "observed_bar_count": path.observed_bar_count,
            "missing_bar_count": path.missing_bar_count,
            "weekly_low_time": (
                path.weekly_low_time.isoformat().replace("+00:00", "Z")
                if path.weekly_low_time is not None
                else ""
            ),
            "weekly_low_weekday": path.weekly_low_weekday or "",
            "weekly_low_price": path.weekly_low_price if path.weekly_low_price is not None else "",
            "friday_close": path.friday_close if path.friday_close is not None else "",
        }
        for path in paths
    ]


def markdown_report(report: Mapping[str, Any]) -> str:
    gate = required_mapping(report["pattern_gate"], "pattern gate")
    counts = required_mapping(report["weekly_paths"], "weekly paths")
    decision = required_mapping(report["decision"], "decision")
    return "\n".join(
        [
            "# RD04-D5E0 Midweek Pullback Diagnostic",
            "",
            "## Frozen diagnostic result",
            "",
            f"- Status: `{report['status']}`",
            f"- Decision: `{decision['decision']}`",
            f"- Next stage: `{decision['next_stage']}`",
            f"- Tuesday weekly-low share: `{gate['tuesday_weekly_low_share']:.6f}`",
            f"- Largest other weekday share: `{gate['largest_other_weekday_share']:.6f}`",
            f"- Tuesday signals: `{gate['tuesday_signal_count']}`",
            (f"- Tuesday-to-Friday mean return: `{gate['tuesday_to_friday_mean_return']}`"),
            (f"- Tuesday-to-Friday median return: `{gate['tuesday_to_friday_median_return']}`"),
            f"- Positive Tuesday folds: `{gate['positive_tuesday_fold_count']}`",
            f"- Folds with Tuesday observations: `{gate['folds_with_tuesday_observations']}`",
            f"- Weekly paths: `{counts['total']}`",
            f"- Complete weekly paths: `{counts['complete']}`",
            f"- Incomplete weekly paths: `{counts['incomplete']}`",
            "",
            "## Safety boundary",
            "",
            "- This is a descriptive diagnostic over immutable D5B2 PIT control trades.",
            "- No portfolio simulation, re-entry simulation, new entry, or parameter search",
            "  occurred.",
            "- `test_2025_accessed=false`; `holdout_2026_accessed=false`.",
            "",
        ]
    )


def run() -> dict[str, Any]:
    upstream = verify_upstream()
    fields, trades = read_trades(TRADE_SOURCE)
    if tuple(fields) != ORIGINAL_TRADE_FIELDS:
        raise MidweekDiagnosticRunError("D5B2 trade columns changed")
    validate_input_trades(trades)
    source_fingerprint = projection_fingerprint(trades)
    bars_path = ROOT / str(upstream["d0c_four_hour_path"])
    bars = validate_four_hour(pd.read_parquet(bars_path))
    paths, path_index = paths_for_trades(trades, bars)
    entries = entry_diagnostics(trades, path_index)
    validate_projection(trades, entries)
    if projection_fingerprint(entries) != source_fingerprint:
        raise MidweekDiagnosticRunError("immutable D5B2 trade projection hash changed")
    weekday_rows = weekday_metrics(entries)
    low_rows = weekly_low_distribution(paths)
    fold_rows = fold_metrics(entries)
    gate = pattern_gate(low_rows, fold_rows, entries)
    complete_count = sum(path.complete for path in paths)
    decision = (
        "MIDWEEK_PULLBACK_PATTERN_SUPPORTED"
        if bool(gate["pattern_supported"])
        else "MIDWEEK_PULLBACK_PATTERN_NOT_SUPPORTED"
    )
    next_stage = (
        "RD04-D5E1-SINGLE-REENTRY-ABLATION"
        if bool(gate["pattern_supported"])
        else "RD04-D5F-MEMBERSHIP-EXIT-PATH-DIAGNOSTIC"
    )
    reentry_authorized = bool(gate["pattern_supported"])
    path_rows = weekly_path_rows(paths)
    tuesday_rows = [row for row in entries if row["entry_weekday"] == "TUESDAY"]
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": RESEARCH_STAGE,
        "status": "COMPLETE",
        "generated_at_utc": utc_now(),
        "source_commit": source_commit(),
        "diagnostic_only": True,
        "trade_source": {
            "path": TRADE_SOURCE.relative_to(ROOT).as_posix(),
            "sha256": upstream["d5b2_trade_source_sha256"],
            "trade_count": len(trades),
            "projection_fingerprint": source_fingerprint,
            "original_trades_unchanged": True,
        },
        "dataset": {
            "four_hour_path": upstream["d0c_four_hour_path"],
            "four_hour_sha256": upstream["d0c_four_hour_sha256"],
            "four_hour_row_count": len(bars),
            "bar_open_time_before_2025": True,
            "bar_close_time_at_or_before_2025": True,
        },
        "weekly_path_population": "UNIQUE_TRADE_ASSOCIATED_FOLD_SYMBOL_MONDAY_00_UTC",
        "weekly_paths": {
            "total": len(paths),
            "complete": complete_count,
            "incomplete": len(paths) - complete_count,
            "bars_per_complete_path": 42,
            "tie_break": "EARLIEST_FOUR_HOUR_BAR",
        },
        "pattern_gate": gate,
        "decision": {
            "decision": decision,
            "next_stage": next_stage,
            "d5e1_single_reentry_ablation_authorized": reentry_authorized,
            "tuesday_only_entry_rule_authorized": False,
            "averaging_down_authorized": False,
            "pyramiding_authorized": False,
            "more_than_one_reentry_authorized": False,
            "point_in_time_universe_research_baseline_authorized": False,
            "production_change_authorized": False,
            "trade_logic_changed": False,
            "ati_v1_authorized": False,
            "tactical_reentries_executed": 0,
        },
        "safety": {
            "spot_only": True,
            "long_only": True,
            "no_leverage": True,
            "no_margin": True,
            "no_futures": True,
            "no_shorts": True,
            "no_borrowing": True,
            "no_interest": True,
            "no_dca": True,
            "no_kelly_sizing": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
        "output_hashes": {},
    }
    write_csv(ENTRY_DIAGNOSTICS_CSV, entries, output_fields(entries))
    write_csv(ENTRY_WEEKDAY_CSV, weekday_rows, output_fields(weekday_rows))
    write_csv(PATHS_CSV, path_rows, output_fields(path_rows))
    write_csv(LOW_DISTRIBUTION_CSV, low_rows, output_fields(low_rows))
    write_csv(TUESDAY_FRIDAY_CSV, tuesday_rows, output_fields(entries))
    write_csv(FOLD_METRICS_CSV, fold_rows, output_fields(fold_rows))
    write_csv(PATTERN_GATE_CSV, [gate], output_fields([gate]))
    outputs = (
        ENTRY_DIAGNOSTICS_CSV,
        ENTRY_WEEKDAY_CSV,
        PATHS_CSV,
        LOW_DISTRIBUTION_CSV,
        TUESDAY_FRIDAY_CSV,
        FOLD_METRICS_CSV,
        PATTERN_GATE_CSV,
    )
    report["output_hashes"] = {
        path.relative_to(ROOT).as_posix(): file_sha256(path) for path in outputs
    }
    atomic_json(REPORT_JSON, report)
    rendered = markdown_report(report)
    atomic_text(REPORT_MD, rendered)
    atomic_text(FINAL_COPY, rendered)
    return report


def main() -> None:
    try:
        report = run()
    except (MidweekDiagnosticRunError, MidweekPullbackError) as error:
        raise SystemExit(f"RD04-D5E0 FAILED: {error}") from error
    gate = required_mapping(report["pattern_gate"], "pattern gate")
    decision = required_mapping(report["decision"], "decision")
    print("RD04_D5E0_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"NEXT_STAGE={decision['next_stage']}")
    print(f"TUESDAY_WEEKLY_LOW_SHARE={gate['tuesday_weekly_low_share']}")
    print(f"TUESDAY_SIGNAL_COUNT={gate['tuesday_signal_count']}")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
