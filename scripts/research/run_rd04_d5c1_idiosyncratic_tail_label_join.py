"""Run RD04-D5C1 frozen idiosyncratic-tail label diagnostic."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from spotbot.research.rd04_external_tail_event_source_freeze import (
    registry_fingerprint,
    validate_registry,
)
from spotbot.research.rd04_idiosyncratic_tail_label_join import (
    DECISION_COMPLETE,
    EXPECTED_PIT_CONTROL_TRADE_COUNT,
    LABEL_FIELDS,
    ORIGINAL_TRADE_FIELDS,
    RESEARCH_STAGE,
    SCHEMA_VERSION,
    SummaryRow,
    TradeRow,
    category_breakdown,
    decision_record,
    diagnostic_metrics,
    event_breakdown,
    fold_distribution,
    label_trades,
    link_rows,
    projection_fingerprint,
    timing_breakdown,
    validate_input_trades,
    validate_projection,
    validate_report,
    with_without_label_summary,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

D4_REPORT = REPORTS / "ams-rd04-d4-hypothesis-registry-v1.json"
D5B2_REPORT = REPORTS / "ams-rd04-d5b2-structural-stop-evaluation-v1.json"
D5C0_REPORT = REPORTS / "ams-rd04-d5c0-external-event-source-freeze-v1.json"
TRADE_SOURCE = REPORTS / "ams-rd04-d5b2-base-cost-trades-v1.csv"

REPORT_JSON = REPORTS / "ams-rd04-d5c1-idiosyncratic-tail-label-join-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d5c1-idiosyncratic-tail-label-join-v1.md"
LABELLED_TRADES_CSV = REPORTS / "ams-rd04-d5c1-labelled-pit-control-trades-v1.csv"
LINKS_CSV = REPORTS / "ams-rd04-d5c1-trade-event-links-v1.csv"
WITH_WITHOUT_CSV = REPORTS / "ams-rd04-d5c1-with-without-labels-v1.csv"
FOLD_CSV = REPORTS / "ams-rd04-d5c1-fold-distribution-v1.csv"
EVENT_CSV = REPORTS / "ams-rd04-d5c1-event-breakdown-v1.csv"
CATEGORY_CSV = REPORTS / "ams-rd04-d5c1-category-breakdown-v1.csv"
TIMING_CSV = REPORTS / "ams-rd04-d5c1-timing-breakdown-v1.csv"
FINAL_COPY = ROOT / "RD04_D5C1_RESULT_FOR_CHATGPT.md"


class TailLabelDiagnosticRunError(RuntimeError):
    """Raised when live D5C1 evidence is inconsistent or unsafe."""


def utc_now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


def source_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TailLabelDiagnosticRunError(f"Expected JSON object: {path}")
    return cast(dict[str, Any], payload)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    atomic_text(
        path,
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n",
    )


def read_csv_rows(path: Path) -> tuple[list[str], list[TradeRow]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise TailLabelDiagnosticRunError(f"CSV has no header: {path}")
        fieldnames = [str(field) for field in reader.fieldnames]
        rows: list[TradeRow] = []
        for raw in reader:
            converted: TradeRow = {}
            for key, value in raw.items():
                if key is None or value is None:
                    raise TailLabelDiagnosticRunError(f"CSV contains null key or value: {path}")
                converted[str(key)] = str(value)
            rows.append(converted)
    return fieldnames, rows


def write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(fieldnames),
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    temporary.replace(path)


def summary_fields(rows: list[SummaryRow]) -> list[str]:
    ordered: list[str] = []
    for row in rows:
        for key in row:
            if key not in ordered:
                ordered.append(key)
    return ordered


def verify_upstream() -> dict[str, Any]:
    d4 = load_json(D4_REPORT)
    d5b2 = load_json(D5B2_REPORT)
    d5c0 = load_json(D5C0_REPORT)

    if d4.get("status") != "COMPLETE":
        raise TailLabelDiagnosticRunError("RD04-D4 is not COMPLETE.")
    hypotheses = d4.get("hypotheses")
    if not isinstance(hypotheses, list):
        raise TailLabelDiagnosticRunError("D4 hypotheses are missing.")
    hypothesis = next(
        (
            item
            for item in hypotheses
            if isinstance(item, Mapping)
            and item.get("hypothesis_id") == "RD04-D5C-IDIOSYNCRATIC-TAIL-LABELS"
        ),
        None,
    )
    if not isinstance(hypothesis, Mapping):
        raise TailLabelDiagnosticRunError("D5C hypothesis is missing.")
    if hypothesis.get("control") != ("ALL_PIT_TRADES_REPORTED_UNCHANGED"):
        raise TailLabelDiagnosticRunError("D5C unchanged-control contract drifted.")
    if hypothesis.get("treatment") != ("DIAGNOSTIC_LABELS_ONLY_NO_EXCLUSIONS"):
        raise TailLabelDiagnosticRunError("D5C treatment contract drifted.")
    if hypothesis.get("authorization_if_passed") != ("NONE_DIAGNOSTIC_ONLY"):
        raise TailLabelDiagnosticRunError("D5C authorization boundary drifted.")
    frozen = hypothesis.get("frozen_parameters")
    if not isinstance(frozen, Mapping):
        raise TailLabelDiagnosticRunError("D5C frozen parameters are missing.")
    if frozen.get("outcome_based_exclusion_allowed") is not False:
        raise TailLabelDiagnosticRunError("D5C outcome exclusion was enabled.")
    if frozen.get("reported_with_and_without_labels") is not True:
        raise TailLabelDiagnosticRunError("D5C dual reporting requirement drifted.")

    if d5b2.get("status") != "COMPLETE":
        raise TailLabelDiagnosticRunError("RD04-D5B2 is not COMPLETE.")
    output_hashes = d5b2.get("output_hashes")
    if not isinstance(output_hashes, Mapping):
        raise TailLabelDiagnosticRunError("D5B2 output hashes are missing.")
    trade_path = TRADE_SOURCE.relative_to(ROOT).as_posix()
    expected_trade_hash = output_hashes.get(trade_path)
    if not isinstance(expected_trade_hash, str):
        raise TailLabelDiagnosticRunError("D5B2 trade-source hash is missing.")
    observed_trade_hash = file_sha256(TRADE_SOURCE)
    if observed_trade_hash != expected_trade_hash:
        raise TailLabelDiagnosticRunError("D5B2 trade-source hash mismatch.")
    pit = d5b2.get("pit_comparison")
    if not isinstance(pit, Mapping):
        raise TailLabelDiagnosticRunError("D5B2 PIT comparison is missing.")
    base = pit.get("BASE_COST")
    if not isinstance(base, Mapping):
        raise TailLabelDiagnosticRunError("D5B2 PIT base comparison is missing.")
    if base.get("control_trade_count") != (EXPECTED_PIT_CONTROL_TRADE_COUNT):
        raise TailLabelDiagnosticRunError("D5B2 PIT control trade count drifted.")

    if d5c0.get("status") != "COMPLETE":
        raise TailLabelDiagnosticRunError("RD04-D5C0 is not COMPLETE.")
    if d5c0.get("registry_fingerprint") != registry_fingerprint():
        raise TailLabelDiagnosticRunError("D5C0 registry fingerprint drifted.")
    decision = d5c0.get("decision")
    if not isinstance(decision, Mapping):
        raise TailLabelDiagnosticRunError("D5C0 decision is missing.")
    if decision.get("d5c1_tail_label_join_diagnostic_authorized") is not True:
        raise TailLabelDiagnosticRunError("D5C1 diagnostic is not authorized.")
    if d5c0.get("next_stage") != ("RD04-D5C1-IDIOSYNCRATIC-TAIL-LABEL-JOIN"):
        raise TailLabelDiagnosticRunError("D5C0 next-stage pointer drifted.")

    return {
        "d4_hypothesis_status": hypothesis.get("status"),
        "d5b2_decision": cast(
            Mapping[str, Any],
            d5b2["decision"],
        ).get("decision"),
        "d5b2_trade_source_sha256": expected_trade_hash,
        "d5b2_evidence_commit": ("bda1eb0dd06065afc2794c28bfef7bad6e0d30f1"),
        "d5c0_decision": decision.get("decision"),
        "d5c0_registry_fingerprint": registry_fingerprint(),
        "d5c0_evidence_commit": ("751eaa595e9bcf39380603008db1d2d773a93b7b"),
    }


def markdown_report(report: Mapping[str, Any]) -> str:
    decision = cast(Mapping[str, Any], report["decision"])
    metrics = cast(Mapping[str, Any], report["metrics"])
    lines = [
        "# AMS RD04-D5C1 — Idiosyncratic Tail-Label Diagnostic",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        (f"- Total PIT control trades retained: `{metrics['total_trade_count']}`"),
        (f"- Labelled trade count: `{metrics['labelled_trade_count']}`"),
        (f"- Unlabelled trade count: `{metrics['unlabelled_trade_count']}`"),
        (f"- Labelled trade net PnL: `{metrics['labelled_trade_net_pnl']}`"),
        (f"- Unlabelled trade net PnL: `{metrics['unlabelled_trade_net_pnl']}`"),
        (f"- Labelled loss share: `{metrics['labelled_loss_share']}`"),
        (
            "- Labelled maximum adverse excursion: "
            f"`{metrics['labelled_maximum_adverse_excursion']}`"
        ),
        "",
        "## Interpretation",
        "",
        "- Events were frozen independently before this join.",
        "- Every PIT control trade remains present and unchanged.",
        "- Loss share uses `max(-net_pnl, 0)` and is not netted by wins.",
        "- Association is not a causal attribution.",
        "- Event and category tables are diagnostic only.",
        "",
        "## Safety boundary",
        "",
        "- No market data or portfolio simulation was used.",
        "- No symbol, trade or loss was excluded.",
        "- No production, universe, ranking, entry, exit or weight change is authorized.",
        "- No 2025 test or 2026 holdout access.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    upstream = verify_upstream()
    validate_registry()

    source_fields, all_rows = read_csv_rows(TRADE_SOURCE)
    if tuple(source_fields) != ORIGINAL_TRADE_FIELDS:
        raise TailLabelDiagnosticRunError("D5B2 trade CSV schema drifted.")
    trades = [
        row
        for row in all_rows
        if row.get("universe_mode") == "PIT_UNIVERSE" and row.get("portfolio_mode") == "CONTROL"
    ]
    validate_input_trades(trades)

    labelled_rows, links = label_trades(trades)
    validate_projection(trades, labelled_rows)

    input_projection = projection_fingerprint(trades)
    output_projection = projection_fingerprint(labelled_rows)
    metrics = diagnostic_metrics(labelled_rows)
    if (
        metrics["labelled_trade_count"] + metrics["unlabelled_trade_count"]
        != metrics["total_trade_count"]
    ):
        raise TailLabelDiagnosticRunError("labelled and unlabelled counts do not reconcile.")

    with_without = with_without_label_summary(labelled_rows)
    folds = fold_distribution(labelled_rows)
    events = event_breakdown(labelled_rows, links)
    categories = category_breakdown(labelled_rows, links)
    timings = timing_breakdown(labelled_rows, links)
    link_output = link_rows(links)

    write_csv(
        LABELLED_TRADES_CSV,
        labelled_rows,
        (*ORIGINAL_TRADE_FIELDS, *LABEL_FIELDS),
    )
    write_csv(
        LINKS_CSV,
        link_output,
        (
            "trade_id",
            "fold_id",
            "symbol",
            "canonical_symbol",
            "event_id",
            "entity",
            "primary_category",
            "all_categories",
            "event_start_utc",
            "association_end_utc",
            "persistence_mode",
            "timing_label",
        ),
    )
    for path, rows in (
        (WITH_WITHOUT_CSV, with_without),
        (FOLD_CSV, folds),
        (EVENT_CSV, events),
        (CATEGORY_CSV, categories),
        (TIMING_CSV, timings),
    ):
        write_csv(path, rows, summary_fields(rows))

    decision = decision_record(structural_pass=True)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": RESEARCH_STAGE,
        "status": "COMPLETE",
        "generated_at": utc_now(),
        "source_commit": source_commit(),
        "upstream": upstream,
        "registry_fingerprint": registry_fingerprint(),
        "input": {
            "trade_source": TRADE_SOURCE.relative_to(ROOT).as_posix(),
            "trade_source_sha256": file_sha256(TRADE_SOURCE),
            "input_portfolio": ("RD04_D5B2_PIT_UNIVERSE_CONTROL_BASE_COST"),
            "source_row_count": len(all_rows),
            "selected_trade_count": len(trades),
        },
        "validation": {
            "source_trade_hash_matches_d5b2": True,
            "pit_control_trade_count_matches_d5b2": (
                len(trades) == EXPECTED_PIT_CONTROL_TRADE_COUNT
            ),
            "all_original_trade_fields_unchanged": True,
            "input_output_projection_fingerprint_equal": (input_projection == output_projection),
            "all_rows_retained": (len(labelled_rows) == len(trades)),
            "labelled_plus_unlabelled_equals_total": (
                metrics["labelled_trade_count"] + metrics["unlabelled_trade_count"]
                == metrics["total_trade_count"]
            ),
            "input_projection_fingerprint": input_projection,
            "output_projection_fingerprint": output_projection,
        },
        "metrics": metrics,
        "with_without_labels": with_without,
        "fold_distribution": folds,
        "event_breakdown": events,
        "category_breakdown": categories,
        "timing_breakdown": timings,
        "event_link_count": len(links),
        "decision": decision,
        "next_stage": "RD04-D5E0-MIDWEEK-PULLBACK-DIAGNOSTIC",
        "safety": {
            "spot_only": True,
            "long_only": True,
            "market_data_read": False,
            "trade_ledger_read": True,
            "trade_outcomes_read": True,
            "trade_join_executed": True,
            "trade_rows_excluded": False,
            "outcome_based_event_selection_used": False,
            "symbol_blacklist_used": False,
            "portfolio_simulation_executed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "trade_logic_changed": False,
        },
        "outputs": {
            "labelled_trades": LABELLED_TRADES_CSV.relative_to(ROOT).as_posix(),
            "trade_event_links": LINKS_CSV.relative_to(ROOT).as_posix(),
            "with_without_labels": WITH_WITHOUT_CSV.relative_to(ROOT).as_posix(),
            "fold_distribution": FOLD_CSV.relative_to(ROOT).as_posix(),
            "event_breakdown": EVENT_CSV.relative_to(ROOT).as_posix(),
            "category_breakdown": CATEGORY_CSV.relative_to(ROOT).as_posix(),
            "timing_breakdown": TIMING_CSV.relative_to(ROOT).as_posix(),
        },
    }

    report_text = markdown_report(report)
    atomic_text(REPORT_MD, report_text)
    atomic_text(FINAL_COPY, report_text)
    output_paths = (
        REPORT_MD,
        FINAL_COPY,
        LABELLED_TRADES_CSV,
        LINKS_CSV,
        WITH_WITHOUT_CSV,
        FOLD_CSV,
        EVENT_CSV,
        CATEGORY_CSV,
        TIMING_CSV,
    )
    report["output_hashes"] = {
        path.relative_to(ROOT).as_posix(): file_sha256(path) for path in output_paths
    }
    atomic_json(REPORT_JSON, report)
    validate_report(report)

    print("RD04_D5C1_STATUS=COMPLETE")
    print(f"DECISION={DECISION_COMPLETE}")
    print(f"TOTAL_PIT_CONTROL_TRADES={metrics['total_trade_count']}")
    print(f"LABELLED_TRADE_COUNT={metrics['labelled_trade_count']}")
    print(f"UNLABELLED_TRADE_COUNT={metrics['unlabelled_trade_count']}")
    print(f"LABELLED_TRADE_NET_PNL={metrics['labelled_trade_net_pnl']}")
    print(f"UNLABELLED_TRADE_NET_PNL={metrics['unlabelled_trade_net_pnl']}")
    print(f"LABELLED_LOSS_SHARE={metrics['labelled_loss_share']}")
    print(f"LABELLED_MAXIMUM_ADVERSE_EXCURSION={metrics['labelled_maximum_adverse_excursion']}")
    print(f"EVENT_LINK_COUNT={len(links)}")
    print("ALL_ORIGINAL_TRADE_FIELDS_UNCHANGED=True")
    print("ALL_TRADE_ROWS_RETAINED=True")
    print("NEXT_STAGE=RD04-D5E0-MIDWEEK-PULLBACK-DIAGNOSTIC")
    print("EVENT_BASED_SYMBOL_EXCLUSION_AUTHORIZED=False")
    print("POINT_IN_TIME_UNIVERSE_RESEARCH_BASELINE_AUTHORIZED=False")
    print("PRODUCTION_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
