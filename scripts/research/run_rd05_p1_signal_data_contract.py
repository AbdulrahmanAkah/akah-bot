"""Audit registered RD05 sources and write contracts without evaluating market signals."""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spotbot.research.rd05_protocol_registration import SAFETY, SIGNAL_VARIANTS, TRIAL_BUDGET
from spotbot.research.rd05_signal_data_contract import (
    CRITICAL_SOURCES,
    LABEL_CONTRACTS,
    MAX_FORWARD_HORIZON_DAYS,
    MAX_LOOKBACK_DAYS,
    OPTIONAL_SOURCES,
    P1_STAGE,
    RESEARCH_START,
    SUPPORTING_SOURCES,
    file_sha256,
    formula_rows,
    regime_rows,
    validate_contracts,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
P0 = REPORTS / "ams-rd05-protocol-registration-v1.json"
SOURCE_REGISTRY = REPORTS / "ams-rd05-source-registry-v1.csv"
LOCK = pd.Timestamp("2025-01-01T00:00:00Z")
OUT_NAMES = (
    "source-audit",
    "schema-registry",
    "timeframe-reconciliation",
    "symbol-coverage",
    "membership-coverage",
    "decision-time-contract",
    "label-contract",
    "signal-formula-contract",
    "signal-source-readiness",
    "regime-contract",
    "fold-feasibility",
    "quote-turnover-contract",
    "panel-schema-contract",
    "blockers",
    "upstream-reconciliation",
)
OUT = {name: REPORTS / f"ams-rd05-p1-{name}-v1.csv" for name in OUT_NAMES}
JSON_OUT = REPORTS / "ams-rd05-p1-signal-data-contract-v1.json"
MD_OUT = REPORTS / "ams-rd05-p1-signal-data-contract-v1.md"


class P1RunError(RuntimeError):
    """Raised when P1 cannot safely produce its source-freeze evidence."""


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(
    path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str] | None = None
) -> None:
    headings = list(fields or (list(rows[0]) if rows else []))
    if not headings:
        raise P1RunError(f"no CSV headings for {path}")
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headings, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(path, buffer.getvalue())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P1RunError(f"JSON object required: {path}")
    return value


def timestamp(value: object) -> pd.Timestamp:
    result = pd.Timestamp(str(value))
    if result.tzinfo is None:
        return result.tz_localize("UTC")
    return result.tz_convert("UTC")


def scalar_time(value: pd.Timestamp | None) -> str:
    return "NOT_RECORDED" if value is None or pd.isna(value) else value.isoformat()


def source_rows() -> list[dict[str, str]]:
    source_frame = pd.read_csv(SOURCE_REGISTRY, dtype=str).fillna("NOT_RECORDED")
    raw_rows = source_frame.to_dict("records")
    return [{str(key): str(value) for key, value in row.items()} for row in raw_rows]


def source_path(row: Mapping[str, str]) -> Path:
    return ROOT / row["path"]


def valid_bar_frame(frame: pd.DataFrame) -> pd.DataFrame:
    opened = pd.to_datetime(frame["bar_open_time"], utc=True)
    closed = pd.to_datetime(frame["bar_close_time"], utc=True)
    selected = frame.loc[(opened < LOCK) & (closed <= LOCK)].copy()
    selected["bar_open_time"] = pd.to_datetime(selected["bar_open_time"], utc=True)
    selected["bar_close_time"] = pd.to_datetime(selected["bar_close_time"], utc=True)
    return selected


def numeric_nonfinite(frame: pd.DataFrame, columns: Sequence[str]) -> int:
    return int(
        sum(
            (~np.isfinite(pd.to_numeric(frame[column], errors="coerce"))).sum()
            for column in columns
        )
    )


def audit_ohlcv(row: Mapping[str, str]) -> tuple[dict[str, object], pd.DataFrame]:
    path = source_path(row)
    frame = pd.read_parquet(path)
    filtered = valid_bar_frame(frame)
    required = [
        "symbol",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    missing = [column for column in required if column not in frame]
    duration = {"OHLCV_4H": 4, "OHLCV_8H": 8, "OHLCV_1D": 24}[row["source_id"]]
    opens = filtered["bar_open_time"]
    closes = filtered["bar_close_time"]
    durations = closes - opens
    prices = ["open", "high", "low", "close"]
    invalid_ohlc = int(
        (
            (filtered["high"] < filtered[prices].max(axis=1))
            | (filtered["low"] > filtered[prices].min(axis=1))
        ).sum()
    )
    duplicate_count = int(filtered.duplicated(["symbol", "bar_open_time"]).sum())
    ordered = filtered.sort_values(["symbol", "bar_open_time"])
    out_of_order = int((ordered["bar_open_time"] != filtered["bar_open_time"]).sum())
    audit: dict[str, object] = {
        "source_id": row["source_id"],
        "path": row["path"],
        "registered_sha256": row["registered_sha256"],
        "observed_sha256": file_sha256(path),
        "hash_match": file_sha256(path) == row["registered_sha256"],
        "file_format": "PARQUET",
        "schema": "|".join(f"{name}:{dtype}" for name, dtype in frame.dtypes.items()),
        "column_names": "|".join(frame.columns),
        "dtypes": "|".join(f"{name}:{dtype}" for name, dtype in frame.dtypes.items()),
        "row_count": len(frame),
        "symbol_count": int(frame["symbol"].nunique()),
        "first_open_time": scalar_time(opens.min()),
        "last_open_time": scalar_time(opens.max()),
        "first_close_time": scalar_time(closes.min()),
        "last_close_time": scalar_time(closes.max()),
        "timezone": "UTC",
        "duplicate_key_count": duplicate_count,
        "null_counts_by_required_field": json.dumps(
            {c: int(frame[c].isna().sum()) for c in required if c in frame}
        ),
        "nonfinite_numeric_count": numeric_nonfinite(
            filtered, [c for c in prices + ["volume"] if c in filtered]
        ),
        "negative_volume_count": int((filtered["volume"] < 0).sum()),
        "invalid_ohlc_count": invalid_ohlc,
        "out_of_order_count": out_of_order,
        "pre_2021_count": int(
            (pd.to_datetime(frame["bar_open_time"], utc=True) < RESEARCH_START).sum()
        ),
        "2025_open_count": int((pd.to_datetime(frame["bar_open_time"], utc=True) >= LOCK).sum()),
        "post_2025_boundary_close_count": int(
            (pd.to_datetime(frame["bar_close_time"], utc=True) > LOCK).sum()
        ),
        "verification_status": "SOURCE_READY"
        if not missing and file_sha256(path) == row["registered_sha256"]
        else "FAIL",
        "blocking_status": "NONE"
        if not missing and file_sha256(path) == row["registered_sha256"]
        else "CRITICAL_SOURCE_FAILURE",
        "notes": (
            f"duration_hours={duration}; "
            f"duration_mismatch={int((durations != pd.Timedelta(hours=duration)).sum())}; "
            f"missing={missing}"
        ),
    }
    return audit, filtered


def audit_availability(row: Mapping[str, str]) -> tuple[dict[str, object], pd.DataFrame]:
    path = source_path(row)
    frame = pd.read_parquet(path)
    required = ["symbol", "tradable_from", "tradable_until", "availability_basis"]
    missing = [column for column in required if column not in frame]
    audit: dict[str, object] = {
        "source_id": row["source_id"],
        "path": row["path"],
        "registered_sha256": row["registered_sha256"],
        "observed_sha256": file_sha256(path),
        "hash_match": file_sha256(path) == row["registered_sha256"],
        "file_format": "PARQUET",
        "schema": "|".join(f"{n}:{d}" for n, d in frame.dtypes.items()),
        "column_names": "|".join(frame.columns),
        "dtypes": "|".join(f"{n}:{d}" for n, d in frame.dtypes.items()),
        "row_count": len(frame),
        "symbol_count": int(frame["symbol"].nunique()),
        "first_open_time": "NOT_APPLICABLE",
        "last_open_time": "NOT_APPLICABLE",
        "first_close_time": "NOT_APPLICABLE",
        "last_close_time": "NOT_APPLICABLE",
        "timezone": "UTC",
        "duplicate_key_count": int(frame.duplicated(["symbol"]).sum()),
        "null_counts_by_required_field": json.dumps(
            {c: int(frame[c].isna().sum()) for c in required if c in frame}
        ),
        "nonfinite_numeric_count": 0,
        "negative_volume_count": 0,
        "invalid_ohlc_count": 0,
        "out_of_order_count": 0,
        "pre_2021_count": 0,
        "2025_open_count": 0,
        "post_2025_boundary_close_count": 0,
        "verification_status": "SOURCE_READY"
        if not missing and file_sha256(path) == row["registered_sha256"]
        else "FAIL",
        "blocking_status": "NONE"
        if not missing and file_sha256(path) == row["registered_sha256"]
        else "CRITICAL_SOURCE_FAILURE",
        "notes": (
            "[tradable_from, tradable_until) is the frozen interval convention; no price synthesis"
        ),
    }
    return audit, frame


def audit_membership(
    row: Mapping[str, str],
) -> tuple[dict[str, object], pd.DataFrame, list[dict[str, object]]]:
    path = source_path(row)
    frame = pd.read_csv(path)
    decision = pd.to_datetime(frame["rebalance_time"], utc=True)
    frame = frame.assign(rebalance_time=decision)
    before_2022 = int((decision < pd.Timestamp("2022-01-01T00:00:00Z")).sum())
    audit: dict[str, object] = {
        "source_id": row["source_id"],
        "path": row["path"],
        "registered_sha256": row["registered_sha256"],
        "observed_sha256": file_sha256(path),
        "hash_match": file_sha256(path) == row["registered_sha256"],
        "file_format": "CSV",
        "schema": "|".join(f"{n}:{d}" for n, d in frame.dtypes.items()),
        "column_names": "|".join(frame.columns),
        "dtypes": "|".join(f"{n}:{d}" for n, d in frame.dtypes.items()),
        "row_count": len(frame),
        "symbol_count": int(frame["canonical_symbol"].nunique()),
        "first_open_time": scalar_time(decision.min()),
        "last_open_time": scalar_time(decision.max()),
        "first_close_time": "NOT_APPLICABLE",
        "last_close_time": "NOT_APPLICABLE",
        "timezone": "UTC",
        "duplicate_key_count": int(frame.duplicated(["rebalance_time", "canonical_symbol"]).sum()),
        "null_counts_by_required_field": json.dumps(
            {
                c: int(frame[c].isna().sum())
                for c in ("rebalance_time", "canonical_symbol", "venue_data_eligible")
            }
        ),
        "nonfinite_numeric_count": 0,
        "negative_volume_count": 0,
        "invalid_ohlc_count": 0,
        "out_of_order_count": 0,
        "pre_2021_count": before_2022,
        "2025_open_count": int((decision >= LOCK).sum()),
        "post_2025_boundary_close_count": 0,
        "verification_status": "BLOCKED_PIT_MEMBERSHIP_2021_COVERAGE",
        "blocking_status": "CRITICAL_SOURCE_FAILURE",
        "notes": "No registered causal 2021 snapshot found; P1 must not reconstruct membership.",
    }
    coverage = [
        {
            "coverage_type": "PIT_MEMBERSHIP",
            "first_decision_time": scalar_time(decision.min()),
            "last_decision_time": scalar_time(decision.max()),
            "monday_utc_violations": int((decision.dt.weekday != 0).sum()),
            "snapshot_count": int(decision.nunique()),
            "has_causal_2021_membership": False,
            "decision": "BLOCKED_PIT_MEMBERSHIP_2021_COVERAGE",
        }
    ]
    return audit, frame, coverage


def audit_quote(
    row: Mapping[str, str], ohlcv4: pd.DataFrame, availability: pd.DataFrame
) -> tuple[dict[str, object], pd.DataFrame, list[dict[str, object]]]:
    path = source_path(row)
    frame = valid_bar_frame(pd.read_parquet(path)).rename(columns={"venue_pair": "venue_pair"})
    key_ohlcv = set(zip(ohlcv4["symbol"], ohlcv4["bar_open_time"], strict=True))
    venue_to_symbol = {
        str(source).replace("/", "-"): str(symbol)
        for source, symbol in zip(
            availability["source_symbols"], availability["symbol"], strict=True
        )
    }
    quote_symbol = frame["venue_pair"].map(venue_to_symbol)
    if quote_symbol.isna().any():
        raise P1RunError("unmapped native quote-turnover venue pair")
    key_quote = set(zip(quote_symbol, frame["bar_open_time"], strict=True))
    match = file_sha256(path) == row["registered_sha256"]
    key_match = len(key_ohlcv - key_quote) == 0 and len(key_quote - key_ohlcv) == 0
    status = "SOURCE_READY" if match and key_match else "BLOCKED_SOURCE_RECONCILIATION_FAILURE"
    audit: dict[str, object] = {
        "source_id": row["source_id"],
        "path": row["path"],
        "registered_sha256": row["registered_sha256"],
        "observed_sha256": file_sha256(path),
        "hash_match": match,
        "file_format": "PARQUET",
        "schema": "|".join(f"{n}:{d}" for n, d in frame.dtypes.items()),
        "column_names": "|".join(frame.columns),
        "dtypes": "|".join(f"{n}:{d}" for n, d in frame.dtypes.items()),
        "row_count": len(frame),
        "symbol_count": int(quote_symbol.nunique()),
        "first_open_time": scalar_time(frame["bar_open_time"].min()),
        "last_open_time": scalar_time(frame["bar_open_time"].max()),
        "first_close_time": scalar_time(frame["bar_close_time"].min()),
        "last_close_time": scalar_time(frame["bar_close_time"].max()),
        "timezone": "UTC",
        "duplicate_key_count": int(
            frame.assign(symbol=quote_symbol).duplicated(["symbol", "bar_open_time"]).sum()
        ),
        "null_counts_by_required_field": json.dumps(
            {
                c: int(frame[c].isna().sum())
                for c in ("venue_pair", "bar_open_time", "quote_turnover_usdt")
            }
        ),
        "nonfinite_numeric_count": numeric_nonfinite(frame, ["quote_turnover_usdt"]),
        "negative_volume_count": int((frame["quote_turnover_usdt"] < 0).sum()),
        "invalid_ohlc_count": 0,
        "out_of_order_count": 0,
        "pre_2021_count": 0,
        "2025_open_count": int(
            (pd.to_datetime(pd.read_parquet(path)["bar_open_time"], utc=True) >= LOCK).sum()
        ),
        "post_2025_boundary_close_count": 0,
        "verification_status": status,
        "blocking_status": "NONE" if status == "SOURCE_READY" else status,
        "notes": (
            "KuCoin native seventh kline field; interval total denominated in USDT, "
            "never close*base_volume."
        ),
    }
    contract = [
        {
            "source_id": row["source_id"],
            "native_field_name": "quote_turnover_usdt",
            "native_exchange_meaning": "NATIVE_SEVENTH_KLINE_FIELD",
            "currency_unit": "USDT",
            "interval_or_cumulative": "INTERVAL_TOTAL",
            "timestamp_semantics": "bar_open_time to bar_close_time",
            "row_key": "venue_pair|bar_open_time",
            "matched_keys": len(key_quote & key_ohlcv),
            "quote_only_keys": len(key_quote - key_ohlcv),
            "ohlcv_only_keys": len(key_ohlcv - key_quote),
            "duplicate_keys": audit["duplicate_key_count"],
            "null_values": int(frame["quote_turnover_usdt"].isna().sum()),
            "nonfinite_values": audit["nonfinite_numeric_count"],
            "negative_values": audit["negative_volume_count"],
            "signal_decision": status,
        }
    ]
    return audit, frame, contract


def reconcile(
    four: pd.DataFrame, target: pd.DataFrame, hours: int, source_id: str
) -> dict[str, object]:
    frame = four.copy()
    frame["bucket"] = frame["bar_open_time"].dt.floor(f"{hours}h")
    grouped = frame.groupby(["symbol", "bucket"], sort=True)
    aggregate = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        component_count=("open", "size"),
    ).reset_index()
    aggregate = aggregate.loc[aggregate["component_count"] == hours // 4].copy()
    expected = target.rename(columns={"bar_open_time": "bucket"})
    merged = aggregate.merge(
        expected[["symbol", "bucket", "open", "high", "low", "close", "volume"]],
        on=["symbol", "bucket"],
        how="outer",
        suffixes=("_4h", "_target"),
        indicator=True,
    )
    numeric = ["open", "high", "low", "close", "volume"]
    mismatch = merged["_merge"] != "both"
    for column in numeric:
        mismatch |= (merged[f"{column}_4h"] - merged[f"{column}_target"]).abs().fillna(
            np.inf
        ) > 1e-10
    mismatch |= merged["component_count"].fillna(0) != hours // 4
    return {
        "reconciliation_id": f"4H_TO_{source_id}",
        "component_source": "OHLCV_4H",
        "target_source": source_id,
        "expected_component_bars": hours // 4,
        "aggregate_rows": len(aggregate),
        "target_rows": len(target),
        "mismatch_count": int(mismatch.sum()),
        "status": "PASS" if not mismatch.any() else "FAIL",
        "tolerance": "1e-10 absolute; source IEEE float storage",
        "details": "open=first; high=max; low=min; close=last; volume=sum; UTC buckets",
    }


def coverage_rows(four: pd.DataFrame, availability: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in availability.itertuples(index=False):
        symbol = str(item.symbol)
        begin = timestamp(item.tradable_from)
        end = timestamp(item.tradable_until)
        interval = four.loc[
            (four["symbol"] == symbol)
            & (four["bar_open_time"] >= begin)
            & (four["bar_open_time"] < end)
        ]
        expected = max(
            0,
            int(
                (min(end, LOCK) - max(begin, pd.Timestamp(RESEARCH_START))) / pd.Timedelta(hours=4)
            ),
        )
        observed = len(interval)
        times = interval["bar_open_time"].sort_values().tolist()
        largest = max(
            (
                int((later - earlier) / pd.Timedelta(hours=4)) - 1
                for earlier, later in zip(times, times[1:], strict=False)
            ),
            default=0,
        )
        rows.append(
            {
                "source_id": "OHLCV_4H",
                "symbol": symbol,
                "expected_bar_count": expected,
                "observed_bar_count": observed,
                "missing_bar_count": max(0, expected - observed),
                "largest_gap_bars": largest,
                "first_valid_bar": scalar_time(interval["bar_open_time"].min()),
                "last_valid_bar": scalar_time(interval["bar_open_time"].max()),
                "complete_lookback_feasibility": observed >= MAX_LOOKBACK_DAYS * 6,
                "gap_classification": "UNEXPECTED_GAP" if observed < expected else "NONE",
            }
        )
    return rows


def fold_rows(membership: pd.DataFrame, availability: pd.DataFrame) -> list[dict[str, object]]:
    definitions = (
        ("WF01", "2021-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
        ("WF02", "2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
        ("WF03", "2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    )
    first_member = membership["rebalance_time"].min()
    rows: list[dict[str, object]] = []
    for fold, train_start, train_end, validation_start, validation_end in definitions:
        start = pd.Timestamp(validation_start, tz="UTC")
        end = pd.Timestamp(validation_end, tz="UTC")
        snapshots = membership.loc[
            (membership["rebalance_time"] >= start) & (membership["rebalance_time"] <= end)
        ]
        wf01_gap = fold == "WF01" and first_member > pd.Timestamp("2021-01-01T00:00:00Z")
        rows.append(
            {
                "fold_id": fold,
                "train_start": train_start,
                "train_end": train_end,
                "validation_start": validation_start,
                "validation_end": validation_end,
                "purge_embargo_days": MAX_FORWARD_HORIZON_DAYS,
                "membership_coverage": "MISSING_CAUSAL_2021"
                if wf01_gap
                else "COVERED_VALIDATION_ONLY",
                "feature_warmup_coverage": "AVAILABLE_FROM_2021_OHLCV",
                "label_horizon_coverage": "CONTRACT_ONLY_NOT_COMPUTED",
                "eligible_decision_count_estimate": int(snapshots["rebalance_time"].nunique()),
                "symbols_available": int(availability["symbol"].nunique()),
                "critical_source_coverage": "FAIL" if wf01_gap else "PARTIAL",
                "feasible": False,
                "blocking_reason": "PIT_MEMBERSHIP_2021_NOT_REGISTERED"
                if wf01_gap
                else "GLOBAL_P1_BLOCKED_BY_WF01",
            }
        )
    return rows


def markdown(summary: Mapping[str, object]) -> str:
    return "\n".join(
        (
            "# RD05 P1 Signal Data Contract",
            "",
            f"- Status: `{summary['status']}`",
            f"- Decision: `{summary['decision']}`",
            f"- PIT membership coverage: `{summary['pit_membership_coverage']}`",
            f"- P2 authorised: `{summary['rd05_p2_panel_build_authorized']}`",
            "",
            "P1 performed source/schema/integrity audits only. It computed no signal, label, "
            "rank, return, regime value, model, backtest, or portfolio result.",
            "",
        )
    )


def run() -> dict[str, object]:
    validate_contracts()
    p0 = load_json(P0)
    if p0.get("status") != "COMPLETE" or p0.get("decision", {}).get("next_stage") != P1_STAGE:
        raise P1RunError("P0 does not authorize P1")
    sources = source_rows()
    source_index = {row["source_id"]: row for row in sources}
    missing = set(CRITICAL_SOURCES + SUPPORTING_SOURCES + OPTIONAL_SOURCES) - set(source_index)
    if missing:
        raise P1RunError(f"missing source registry entries: {sorted(missing)}")
    audits: list[dict[str, object]] = []
    bars: dict[str, pd.DataFrame] = {}
    for sid in ("OHLCV_4H", "OHLCV_8H", "OHLCV_1D"):
        audit, bars[sid] = audit_ohlcv(source_index[sid])
        audits.append(audit)
    availability_audit, availability = audit_availability(source_index["AVAILABILITY"])
    audits.append(availability_audit)
    membership_audit, membership, membership_rows = audit_membership(source_index["PIT_MEMBERSHIP"])
    audits.append(membership_audit)
    quote_audit, _quote, quote_rows = audit_quote(
        source_index["QUOTE_TURNOVER_4H"], bars["OHLCV_4H"], availability
    )
    audits.append(quote_audit)
    source_status = {str(audit["source_id"]): str(audit["verification_status"]) for audit in audits}
    formulas = formula_rows(source_status)
    blocked_signals = [
        str(row["signal_id"]) for row in formulas if not bool(row["p2_build_eligibility"])
    ]
    recon = [
        reconcile(bars["OHLCV_4H"], bars["OHLCV_8H"], 8, "OHLCV_8H"),
        reconcile(bars["OHLCV_4H"], bars["OHLCV_1D"], 24, "OHLCV_1D"),
    ]
    coverage = coverage_rows(bars["OHLCV_4H"], availability)
    folds = fold_rows(membership, availability)
    labels = [
        {
            "label_id": item.label_id,
            "source_timeframe": item.source_timeframe,
            "decision_price_convention": "decision_time close",
            "horizon_definition": f"{item.horizon_days} calendar days",
            "horizon_end_timestamp": item.last_permissible_decision_time.isoformat(),
            "end_price_convention": item.end_price_convention,
            "interval_inclusion_exclusion": "future closed bars only; decision bar excluded",
            "mfe_mae_bar_interval": "future 1D bars only",
            "minimum_required_future_observations": item.horizon_days,
            "last_permissible_decision_date": (
                item.last_permissible_decision_time.date().isoformat()
            ),
            "missing_horizon_handling": "EXCLUDE_AND_REPORT",
            "data_end_handling": "EXCLUDE_AND_REPORT",
            "delisting_handling": "EXCLUDE_AND_REPORT",
            "no_zero_imputation_rule": True,
            "computed": False,
        }
        for item in LABEL_CONTRACTS
    ]
    decision_rows = [
        {
            "contract_id": "WEEKLY_PIT_DECISION",
            "week_timezone": "UTC",
            "decision_clock": "Monday 00:00 UTC",
            "closed_bar_inclusion": "bar_close_time <= decision_time",
            "bar_opening_at_decision_excluded": True,
            "same_timestamp_close_included": True,
            "availability_interval_closure": "[tradable_from, tradable_until)",
            "membership_snapshot_join_rule": (
                "rebalance_time == decision_time and venue_data_eligible == true"
            ),
            "partial_bars_prohibited": True,
        }
    ]
    panel = [
        {
            "panel_schema_version": "ams-rd05-p2-panel-contract-v1",
            "grain": "decision_time x PIT-eligible symbol",
            "primary_key": "decision_time|symbol",
            "sorting_order": "decision_time ascending, symbol ascending",
            "duplicate_policy": "BLOCK",
            "null_policy": "exclude with missing_reason",
            "row_exclusion_reasons": "PIT_MISSING|AVAILABILITY|WARMUP|MISSING_SOURCE",
            "partitioning": "fold_id/year",
            "parquet_schema": "UTC timestamp; string symbol; float64 raw references",
            "float_precision": "float64",
            "timestamp_type": "timestamp[us,UTC]",
            "fingerprint_construction": "source SHA256 + contract SHA256",
            "deterministic_output_ordering": True,
            "signal_values_present": False,
            "label_values_present": False,
        }
    ]
    blockers = [
        {
            "blocker_id": "PIT_MEMBERSHIP_2021_COVERAGE",
            "severity": "CRITICAL",
            "status": "OPEN",
            "scope": "WF01 and P2",
            "evidence": "registered PIT membership begins 2022-01-03T00:00:00Z",
            "permitted_resolution": (
                "recover causal 2021 PIT snapshots from existing provenance OR "
                "preregister revised folds using only covered years"
            ),
            "automatic_resolution": "PROHIBITED",
            "protocol_amendment_required": True,
        }
    ]
    upstream = [
        {
            "artifact": "RD05_P0_PROTOCOL",
            "path": str(P0.relative_to(ROOT)),
            "sha256": file_sha256(P0),
            "expected_status": "COMPLETE",
            "observed_status": p0.get("status"),
            "expected_next_stage": P1_STAGE,
            "observed_next_stage": p0.get("decision", {}).get("next_stage"),
            "reconciliation_pass": True,
        }
    ]
    for name, rows in (
        ("source-audit", audits),
        (
            "schema-registry",
            [
                {
                    "source_id": a["source_id"],
                    "schema": a["schema"],
                    "primary_key": "symbol|bar_open_time"
                    if str(a["source_id"]).startswith("OHLCV")
                    else "REGISTERED_NATIVE_KEY",
                }
                for a in audits
            ],
        ),
        ("timeframe-reconciliation", recon),
        ("symbol-coverage", coverage),
        ("membership-coverage", membership_rows),
        ("decision-time-contract", decision_rows),
        ("label-contract", labels),
        ("signal-formula-contract", formulas),
        (
            "signal-source-readiness",
            [
                {
                    "signal_id": row["signal_id"],
                    "source_readiness": row["source_readiness"],
                    "p2_build_eligibility": row["p2_build_eligibility"],
                }
                for row in formulas
            ],
        ),
        ("regime-contract", regime_rows()),
        ("fold-feasibility", folds),
        ("quote-turnover-contract", quote_rows),
        ("panel-schema-contract", panel),
        ("blockers", blockers),
        ("upstream-reconciliation", upstream),
    ):
        write_csv(OUT[name], rows)
    output_hashes: dict[str, str] = {
        str(path.relative_to(ROOT)): file_sha256(path) for path in OUT.values()
    }
    summary: dict[str, object] = {
        "schema_version": "ams-rd05-p1-signal-data-contract-v1",
        "research_stage": P1_STAGE,
        "status": "BLOCKED",
        "decision": "RD05_P1_BLOCKED_PIT_MEMBERSHIP_COVERAGE",
        "next_stage": "PROTOCOL_AMENDMENT_REQUIRED",
        "rd05_p2_panel_build_authorized": False,
        "signal_computation_authorized": False,
        "label_evaluation_authorized": False,
        "primitive_signal_diagnostic_authorized": False,
        "portfolio_simulation_authorized": False,
        "pit_membership_coverage": "NO_REGISTERED_CAUSAL_2021_SOURCE",
        "source_ready_signal_count": len(SIGNAL_VARIANTS) - len(blocked_signals),
        "blocked_signal_count": len(blocked_signals),
        "blocked_signal_ids": blocked_signals,
        "formula_ambiguity_count": sum(
            str(r["source_readiness"]) == "BLOCKED_FORMULA_AMBIGUITY" for r in formulas
        ),
        "reconciliation": {str(row["reconciliation_id"]): row["status"] for row in recon},
        "trial_budget": TRIAL_BUDGET,
        "declared_trial_budget_unchanged": True,
        "safety": SAFETY,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "execution_status": "P1_SOURCE_AUDIT_ONLY_NO_SIGNALS_OR_LABELS",
        "output_hashes": output_hashes,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    atomic_text(MD_OUT, markdown(summary))
    output_hashes[str(MD_OUT.relative_to(ROOT))] = file_sha256(MD_OUT)
    atomic_text(JSON_OUT, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


if __name__ == "__main__":
    result = run()
    print(f"P1_STATUS={result['status']}")
    print(f"P1_DECISION={result['decision']}")
    print(f"RD05_P2_PANEL_BUILD_AUTHORIZED={result['rd05_p2_panel_build_authorized']}")
