"""Pure diagnostic join and summaries for RD04-D5C1."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, TypeAlias

from spotbot.research.rd04_external_tail_event_source_freeze import (
    EventRecord,
    frozen_events,
    parse_utc,
    registry_fingerprint,
)

SCHEMA_VERSION = "ams-rd04-d5c1-idiosyncratic-tail-label-join-v1"
RESEARCH_STAGE = "RD04-D5C1"

DECISION_COMPLETE = "IDIOSYNCRATIC_TAIL_LABEL_DIAGNOSTIC_COMPLETE"
DECISION_BLOCKED = "IDIOSYNCRATIC_TAIL_LABEL_DIAGNOSTIC_BLOCKED"

TradeRow: TypeAlias = dict[str, str]
SummaryRow: TypeAlias = dict[str, Any]

ORIGINAL_TRADE_FIELDS = (
    "universe_mode",
    "portfolio_mode",
    "fold_id",
    "trade_id",
    "position_id",
    "candidate_id",
    "symbol",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "quantity",
    "gross_pnl",
    "net_pnl",
    "return_fraction",
    "exit_reason",
    "alignment_tier",
    "holding_hours",
    "mfe",
    "mae",
    "natural_reselection_sequence",
    "previous_position_id",
)

LABEL_FIELDS = (
    "canonical_symbol",
    "event_association",
    "event_count",
    "event_ids",
    "primary_categories",
    "all_categories",
    "timing_labels",
)

EXPECTED_PIT_CONTROL_TRADE_COUNT = 153
EXPECTED_RESEARCH_BOUNDARY_EXIT_COUNT = 3
RESEARCH_END_UTC = "2025-01-01T00:00:00Z"


class TailLabelDiagnosticError(RuntimeError):
    """Raised when the frozen diagnostic join violates its contract."""


@dataclass(frozen=True)
class EventLink:
    trade_id: str
    fold_id: str
    symbol: str
    canonical_symbol: str
    event_id: str
    entity: str
    primary_category: str
    all_categories: tuple[str, ...]
    event_start_utc: str
    association_end_utc: str
    persistence_mode: str
    timing_label: str


def required_text(row: TradeRow, field: str) -> str:
    value = row.get(field)
    if value is None or not value.strip():
        raise TailLabelDiagnosticError(f"trade row has missing field: {field}")
    return value.strip()


def required_float(row: TradeRow, field: str) -> float:
    raw = required_text(row, field)
    try:
        value = float(raw)
    except ValueError as error:
        raise TailLabelDiagnosticError(f"trade field is not numeric: {field}={raw}") from error
    if not math.isfinite(value):
        raise TailLabelDiagnosticError(f"trade field is not finite: {field}={raw}")
    return value


def parse_trade_time(row: TradeRow, field: str) -> datetime:
    return parse_utc(required_text(row, field))


def canonical_maps(
    events: tuple[EventRecord, ...],
) -> tuple[dict[str, str], dict[str, tuple[EventRecord, ...]]]:
    aliases: dict[str, str] = {}
    event_map: dict[str, list[EventRecord]] = {}
    for event in events:
        for symbol in event.direct_symbols:
            aliases[symbol] = symbol
            event_map.setdefault(symbol, []).append(event)
        for alias, canonical in event.symbol_aliases:
            aliases[alias] = canonical
    return (
        aliases,
        {
            symbol: tuple(
                sorted(
                    items,
                    key=lambda item: (
                        item.event_start_utc,
                        item.event_id,
                        item.primary_category,
                    ),
                )
            )
            for symbol, items in event_map.items()
        },
    )


def event_overlaps_trade(
    *,
    entry_time: datetime,
    exit_time: datetime,
    event: EventRecord,
) -> bool:
    event_start = parse_utc(event.event_start_utc)
    event_end = parse_utc(event.association_end_utc)
    return entry_time < event_end and exit_time >= event_start


def timing_label(
    *,
    entry_time: datetime,
    exit_time: datetime,
    event: EventRecord,
) -> str:
    event_start = parse_utc(event.event_start_utc)
    event_end = parse_utc(event.association_end_utc)
    if entry_time < event_start <= exit_time:
        return "PRE_EVENT_EXPOSURE"
    if event_start <= entry_time < event_end:
        return "EVENT_WINDOW_ENTRY"
    raise TailLabelDiagnosticError("overlapping event has no registered timing label")


def research_boundary_audit(
    trades: list[TradeRow],
) -> dict[str, int]:
    boundary = parse_utc(RESEARCH_END_UTC)
    return {
        "entry_at_or_after_boundary_count": sum(
            parse_trade_time(row, "entry_time") >= boundary for row in trades
        ),
        "post_boundary_exit_count": sum(
            parse_trade_time(row, "exit_time") > boundary for row in trades
        ),
        "boundary_exit_count": sum(
            parse_trade_time(row, "exit_time") == boundary for row in trades
        ),
        "boundary_exit_reason_mismatch_count": sum(
            parse_trade_time(row, "exit_time") == boundary
            and required_text(row, "exit_reason") != "END_OF_FOLD_EXIT"
            for row in trades
        ),
    }


def validate_input_trades(
    trades: list[TradeRow],
    *,
    expected_count: int = EXPECTED_PIT_CONTROL_TRADE_COUNT,
) -> None:
    if len(trades) != expected_count:
        raise TailLabelDiagnosticError(
            f"expected {expected_count} PIT control trades, observed {len(trades)}"
        )

    trade_ids: set[str] = set()
    folds: set[str] = set()
    boundary = parse_utc(RESEARCH_END_UTC)
    boundary_exit_count = 0
    for row in trades:
        missing = [field for field in ORIGINAL_TRADE_FIELDS if field not in row]
        if missing:
            raise TailLabelDiagnosticError(f"trade row missing columns: {missing}")
        if row["universe_mode"] != "PIT_UNIVERSE":
            raise TailLabelDiagnosticError("non-PIT row entered D5C1")
        if row["portfolio_mode"] != "CONTROL":
            raise TailLabelDiagnosticError("non-control row entered D5C1")
        trade_id = required_text(row, "trade_id")
        if trade_id in trade_ids:
            raise TailLabelDiagnosticError(f"duplicate trade id: {trade_id}")
        trade_ids.add(trade_id)
        folds.add(required_text(row, "fold_id"))

        entry = parse_trade_time(row, "entry_time")
        exit_time = parse_trade_time(row, "exit_time")
        if exit_time < entry:
            raise TailLabelDiagnosticError(f"trade exits before entry: {trade_id}")
        if entry >= boundary:
            raise TailLabelDiagnosticError(
                f"trade entry reaches prohibited research boundary: {trade_id}"
            )
        if exit_time > boundary:
            raise TailLabelDiagnosticError(f"trade exits after research boundary: {trade_id}")
        if exit_time == boundary:
            if required_text(row, "exit_reason") != "END_OF_FOLD_EXIT":
                raise TailLabelDiagnosticError(
                    f"research-boundary exit is not END_OF_FOLD_EXIT: {trade_id}"
                )
            boundary_exit_count += 1
        for field in (
            "entry_price",
            "exit_price",
            "quantity",
            "gross_pnl",
            "net_pnl",
            "return_fraction",
            "holding_hours",
            "mfe",
            "mae",
        ):
            required_float(row, field)

    if folds != {"WF01", "WF02", "WF03"}:
        raise TailLabelDiagnosticError(f"unexpected fold set: {sorted(folds)}")
    if boundary_exit_count != EXPECTED_RESEARCH_BOUNDARY_EXIT_COUNT:
        raise TailLabelDiagnosticError(
            f"unexpected registered research-boundary exit count: {boundary_exit_count}"
        )


def label_trades(
    trades: list[TradeRow],
    *,
    events: tuple[EventRecord, ...] | None = None,
) -> tuple[list[TradeRow], list[EventLink]]:
    selected_events = frozen_events() if events is None else events
    aliases, event_map = canonical_maps(selected_events)
    labelled_rows: list[TradeRow] = []
    links: list[EventLink] = []

    for original in trades:
        row = dict(original)
        symbol = required_text(original, "symbol").upper()
        canonical = aliases.get(symbol, symbol)
        entry_time = parse_trade_time(original, "entry_time")
        exit_time = parse_trade_time(original, "exit_time")

        trade_links: list[EventLink] = []
        for event in event_map.get(canonical, ()):
            if not event_overlaps_trade(
                entry_time=entry_time,
                exit_time=exit_time,
                event=event,
            ):
                continue
            categories = (
                event.primary_category,
                *event.secondary_categories,
            )
            trade_links.append(
                EventLink(
                    trade_id=required_text(original, "trade_id"),
                    fold_id=required_text(original, "fold_id"),
                    symbol=symbol,
                    canonical_symbol=canonical,
                    event_id=event.event_id,
                    entity=event.entity,
                    primary_category=event.primary_category,
                    all_categories=categories,
                    event_start_utc=event.event_start_utc,
                    association_end_utc=event.association_end_utc,
                    persistence_mode=event.persistence_mode,
                    timing_label=timing_label(
                        entry_time=entry_time,
                        exit_time=exit_time,
                        event=event,
                    ),
                )
            )

        trade_links.sort(
            key=lambda item: (
                item.event_start_utc,
                item.event_id,
                item.primary_category,
            )
        )
        links.extend(trade_links)

        row["canonical_symbol"] = canonical
        row["event_association"] = "LABELLED" if trade_links else "UNLABELLED"
        row["event_count"] = str(len(trade_links))
        row["event_ids"] = "|".join(item.event_id for item in trade_links)
        row["primary_categories"] = "|".join(
            dict.fromkeys(item.primary_category for item in trade_links)
        )
        row["all_categories"] = "|".join(
            dict.fromkeys(category for item in trade_links for category in item.all_categories)
        )
        row["timing_labels"] = "|".join(dict.fromkeys(item.timing_label for item in trade_links))
        labelled_rows.append(row)

    return labelled_rows, links


def projection_fingerprint(
    rows: list[TradeRow],
    fields: tuple[str, ...] = ORIGINAL_TRADE_FIELDS,
) -> str:
    payload = [{field: row.get(field, "") for field in fields} for row in rows]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_projection(
    original: list[TradeRow],
    labelled: list[TradeRow],
) -> None:
    if len(original) != len(labelled):
        raise TailLabelDiagnosticError("label join changed trade-row count")
    for index, (source, output) in enumerate(zip(original, labelled, strict=True)):
        for field in ORIGINAL_TRADE_FIELDS:
            if source.get(field, "") != output.get(field, ""):
                raise TailLabelDiagnosticError(
                    f"label join changed original field {field} at row {index}"
                )
    if projection_fingerprint(original) != projection_fingerprint(labelled):
        raise TailLabelDiagnosticError("label projection fingerprint changed")


def loss_amount(row: TradeRow) -> float:
    return max(-required_float(row, "net_pnl"), 0.0)


def aggregate_rows(
    rows: list[TradeRow],
    *,
    group_name: str,
) -> SummaryRow:
    trade_count = len(rows)
    net_pnl = sum(required_float(row, "net_pnl") for row in rows)
    gross_pnl = sum(required_float(row, "gross_pnl") for row in rows)
    losses = sum(loss_amount(row) for row in rows)
    returns = [required_float(row, "return_fraction") for row in rows]
    maes = [required_float(row, "mae") for row in rows]
    return {
        "group_name": group_name,
        "trade_count": trade_count,
        "winning_trade_count": sum(required_float(row, "net_pnl") > 0.0 for row in rows),
        "losing_trade_count": sum(required_float(row, "net_pnl") < 0.0 for row in rows),
        "net_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "loss_amount": losses,
        "mean_return_fraction": (sum(returns) / trade_count if trade_count else None),
        "maximum_adverse_excursion": (min(maes) if maes else None),
    }


def with_without_label_summary(
    labelled_rows: list[TradeRow],
) -> list[SummaryRow]:
    labelled = [row for row in labelled_rows if row["event_association"] == "LABELLED"]
    unlabelled = [row for row in labelled_rows if row["event_association"] == "UNLABELLED"]
    return [
        aggregate_rows(
            labelled_rows,
            group_name="ALL_PIT_TRADES_UNCHANGED",
        ),
        aggregate_rows(
            labelled,
            group_name="LABELLED_TRADES",
        ),
        aggregate_rows(
            unlabelled,
            group_name="UNLABELLED_TRADES",
        ),
    ]


def fold_distribution(
    labelled_rows: list[TradeRow],
) -> list[SummaryRow]:
    output: list[SummaryRow] = []
    for fold_id in ("WF01", "WF02", "WF03"):
        for status in ("ALL", "LABELLED", "UNLABELLED"):
            rows = [
                row
                for row in labelled_rows
                if row["fold_id"] == fold_id
                and (status == "ALL" or row["event_association"] == status)
            ]
            summary = aggregate_rows(
                rows,
                group_name=f"{fold_id}_{status}",
            )
            summary["fold_id"] = fold_id
            summary["event_association"] = status
            output.append(summary)
    return output


def link_rows(links: list[EventLink]) -> list[SummaryRow]:
    return [
        {
            **asdict(link),
            "all_categories": "|".join(link.all_categories),
        }
        for link in links
    ]


def event_breakdown(
    labelled_rows: list[TradeRow],
    links: list[EventLink],
) -> list[SummaryRow]:
    trade_by_id = {row["trade_id"]: row for row in labelled_rows}
    output: list[SummaryRow] = []
    for event in frozen_events():
        event_links = [link for link in links if link.event_id == event.event_id]
        trade_ids = list(dict.fromkeys(link.trade_id for link in event_links))
        rows = [trade_by_id[trade_id] for trade_id in trade_ids]
        summary = aggregate_rows(
            rows,
            group_name=event.event_id,
        )
        summary.update(
            {
                "event_id": event.event_id,
                "entity": event.entity,
                "primary_category": event.primary_category,
                "direct_symbols": "|".join(event.direct_symbols),
                "event_start_utc": event.event_start_utc,
                "association_end_utc": event.association_end_utc,
                "persistence_mode": event.persistence_mode,
                "pre_event_exposure_count": sum(
                    link.timing_label == "PRE_EVENT_EXPOSURE" for link in event_links
                ),
                "event_window_entry_count": sum(
                    link.timing_label == "EVENT_WINDOW_ENTRY" for link in event_links
                ),
            }
        )
        output.append(summary)
    return output


def category_breakdown(
    labelled_rows: list[TradeRow],
    links: list[EventLink],
) -> list[SummaryRow]:
    trade_by_id = {row["trade_id"]: row for row in labelled_rows}
    categories = sorted({category for link in links for category in link.all_categories})
    output: list[SummaryRow] = []
    for category in categories:
        trade_ids = list(
            dict.fromkeys(link.trade_id for link in links if category in link.all_categories)
        )
        rows = [trade_by_id[trade_id] for trade_id in trade_ids]
        summary = aggregate_rows(
            rows,
            group_name=category,
        )
        summary["category"] = category
        summary["non_additive_attribution"] = True
        output.append(summary)
    return output


def timing_breakdown(
    labelled_rows: list[TradeRow],
    links: list[EventLink],
) -> list[SummaryRow]:
    trade_by_id = {row["trade_id"]: row for row in labelled_rows}
    output: list[SummaryRow] = []
    for label in (
        "PRE_EVENT_EXPOSURE",
        "EVENT_WINDOW_ENTRY",
    ):
        trade_ids = list(
            dict.fromkeys(link.trade_id for link in links if link.timing_label == label)
        )
        rows = [trade_by_id[trade_id] for trade_id in trade_ids]
        summary = aggregate_rows(
            rows,
            group_name=label,
        )
        summary["timing_label"] = label
        output.append(summary)
    return output


def diagnostic_metrics(
    labelled_rows: list[TradeRow],
) -> dict[str, Any]:
    labelled = [row for row in labelled_rows if row["event_association"] == "LABELLED"]
    unlabelled = [row for row in labelled_rows if row["event_association"] == "UNLABELLED"]
    total_loss = sum(loss_amount(row) for row in labelled_rows)
    labelled_loss = sum(loss_amount(row) for row in labelled)
    return {
        "total_trade_count": len(labelled_rows),
        "labelled_trade_count": len(labelled),
        "unlabelled_trade_count": len(unlabelled),
        "labelled_trade_net_pnl": sum(required_float(row, "net_pnl") for row in labelled),
        "unlabelled_trade_net_pnl": sum(required_float(row, "net_pnl") for row in unlabelled),
        "total_loss_amount": total_loss,
        "labelled_loss_amount": labelled_loss,
        "unlabelled_loss_amount": sum(loss_amount(row) for row in unlabelled),
        "labelled_loss_share": (labelled_loss / total_loss if total_loss > 0.0 else 0.0),
        "labelled_maximum_adverse_excursion": (
            min(required_float(row, "mae") for row in labelled) if labelled else None
        ),
        "unlabelled_maximum_adverse_excursion": (
            min(required_float(row, "mae") for row in unlabelled) if unlabelled else None
        ),
    }


def decision_record(*, structural_pass: bool) -> dict[str, Any]:
    return {
        "decision": (DECISION_COMPLETE if structural_pass else DECISION_BLOCKED),
        "reason": (
            "FROZEN_DIRECT_ASSET_EVENTS_JOINED_WITHOUT_TRADE_EXCLUSION"
            if structural_pass
            else "INPUT_OR_JOIN_RECONCILIATION_FAILED"
        ),
        "structural_pass": structural_pass,
        "d5e0_midweek_pullback_diagnostic_authorized": structural_pass,
        "diagnostic_only": True,
        "causality_claim_authorized": False,
        "event_based_symbol_exclusion_authorized": False,
        "point_in_time_universe_research_baseline_authorized": False,
        "production_change_authorized": False,
        "universe_change_authorized": False,
        "ranking_change_authorized": False,
        "entry_change_authorized": False,
        "exit_change_authorized": False,
        "weight_change_authorized": False,
        "live_ready": False,
        "production_ready": False,
        "ati_v1_authorized": False,
        "trade_logic_changed": False,
    }


def validate_report(report: dict[str, Any]) -> None:
    if report.get("status") != "COMPLETE":
        raise TailLabelDiagnosticError("D5C1 report status is not COMPLETE")
    if report.get("research_stage") != RESEARCH_STAGE:
        raise TailLabelDiagnosticError("D5C1 research stage drifted")
    if report.get("registry_fingerprint") != registry_fingerprint():
        raise TailLabelDiagnosticError("D5C1 registry fingerprint drifted")

    validation = report.get("validation")
    if not isinstance(validation, dict):
        raise TailLabelDiagnosticError("D5C1 validation record is missing")
    for field in (
        "source_trade_hash_matches_d5b2",
        "pit_control_trade_count_matches_d5b2",
        "all_original_trade_fields_unchanged",
        "input_output_projection_fingerprint_equal",
        "labelled_plus_unlabelled_equals_total",
        "all_rows_retained",
    ):
        if validation.get(field) is not True:
            raise TailLabelDiagnosticError(f"D5C1 validation failed: {field}")

    boundary_audit = report.get("research_boundary_audit")
    if not isinstance(boundary_audit, dict):
        raise TailLabelDiagnosticError("D5C1 research-boundary audit is missing")
    expected_boundary = {
        "entry_at_or_after_boundary_count": 0,
        "post_boundary_exit_count": 0,
        "boundary_exit_count": EXPECTED_RESEARCH_BOUNDARY_EXIT_COUNT,
        "boundary_exit_reason_mismatch_count": 0,
    }
    if any(boundary_audit.get(field) != expected for field, expected in expected_boundary.items()):
        raise TailLabelDiagnosticError("D5C1 research-boundary audit failed")

    metrics = report.get("metrics")
    if not isinstance(metrics, dict):
        raise TailLabelDiagnosticError("D5C1 metrics are missing")
    if metrics.get("total_trade_count") != (EXPECTED_PIT_CONTROL_TRADE_COUNT):
        raise TailLabelDiagnosticError("D5C1 total trade count drifted")
    if (
        int(metrics.get("labelled_trade_count", -1))
        + int(metrics.get("unlabelled_trade_count", -1))
        != EXPECTED_PIT_CONTROL_TRADE_COUNT
    ):
        raise TailLabelDiagnosticError("D5C1 labelled split does not reconcile")

    decision = report.get("decision")
    if not isinstance(decision, dict):
        raise TailLabelDiagnosticError("D5C1 decision is missing")
    if decision.get("decision") != DECISION_COMPLETE:
        raise TailLabelDiagnosticError("D5C1 diagnostic did not complete")
    if decision.get("d5e0_midweek_pullback_diagnostic_authorized") is not True:
        raise TailLabelDiagnosticError("D5E0 diagnostic was not authorized")
    forbidden = (
        "causality_claim_authorized",
        "event_based_symbol_exclusion_authorized",
        "point_in_time_universe_research_baseline_authorized",
        "production_change_authorized",
        "universe_change_authorized",
        "ranking_change_authorized",
        "entry_change_authorized",
        "exit_change_authorized",
        "weight_change_authorized",
        "live_ready",
        "production_ready",
        "ati_v1_authorized",
        "trade_logic_changed",
    )
    if any(decision.get(field) is not False for field in forbidden):
        raise TailLabelDiagnosticError("D5C1 contains an unsafe authorization")

    safety = report.get("safety")
    if not isinstance(safety, dict):
        raise TailLabelDiagnosticError("D5C1 safety record is missing")
    required_false = (
        "market_data_read",
        "trade_rows_excluded",
        "outcome_based_event_selection_used",
        "symbol_blacklist_used",
        "test_2025_accessed",
        "holdout_2026_accessed",
        "trade_logic_changed",
    )
    if any(safety.get(field) is not False for field in required_false):
        raise TailLabelDiagnosticError("D5C1 safety boundary failed")
    required_true = (
        "trade_ledger_read",
        "trade_outcomes_read",
        "trade_join_executed",
    )
    if any(safety.get(field) is not True for field in required_true):
        raise TailLabelDiagnosticError("D5C1 diagnostic execution was not recorded")


__all__ = [
    "DECISION_BLOCKED",
    "DECISION_COMPLETE",
    "EXPECTED_PIT_CONTROL_TRADE_COUNT",
    "EXPECTED_RESEARCH_BOUNDARY_EXIT_COUNT",
    "EventLink",
    "LABEL_FIELDS",
    "ORIGINAL_TRADE_FIELDS",
    "RESEARCH_END_UTC",
    "RESEARCH_STAGE",
    "SCHEMA_VERSION",
    "SummaryRow",
    "TailLabelDiagnosticError",
    "TradeRow",
    "aggregate_rows",
    "canonical_maps",
    "category_breakdown",
    "decision_record",
    "diagnostic_metrics",
    "event_breakdown",
    "event_overlaps_trade",
    "fold_distribution",
    "label_trades",
    "link_rows",
    "loss_amount",
    "parse_trade_time",
    "projection_fingerprint",
    "research_boundary_audit",
    "required_float",
    "required_text",
    "timing_breakdown",
    "timing_label",
    "validate_input_trades",
    "validate_projection",
    "validate_report",
    "with_without_label_summary",
]
