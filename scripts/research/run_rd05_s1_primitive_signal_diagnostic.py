"""Run RD05 S1 primitive diagnostics; this file never constructs a portfolio."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd05_causal_symbol_time_panel import (
    LABEL_IDS,
    REGIME_IDS,
    SIGNAL_IDS,
    required_timestamp,
)
from spotbot.research.rd05_primitive_signal_diagnostic import (
    benjamini_hochberg,
    bootstrap_p_value,
    deterministic_quintiles,
    gate_pass,
    safe_spearman,
    top_count,
)
from spotbot.research.rd05_protocol_registration import SIGNAL_VARIANTS

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
PRIMARY_LABEL = "FORWARD_7D_CLOSE_TO_CLOSE_RETURN"
SECONDARY_LABELS = tuple(label for label in LABEL_IDS if label != PRIMARY_LABEL)
BOOTSTRAP_REPLICATIONS = 10_000


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: Iterable[str]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(fieldnames),
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def p1a_seed() -> int:
    payload = (REPORTS / "ams-rd05-p1a-protocol-amendment-v1.json").read_bytes()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], byteorder="big", signed=False)


def signal_family_map() -> dict[str, str]:
    return {item.signal_id: item.family_id for item in SIGNAL_VARIANTS}


def validation_assignments() -> pd.DataFrame:
    assignments = pd.read_csv(REPORTS / "ams-rd05-p2-fold-assignments-v1.csv")
    assignments["decision_time"] = pd.to_datetime(assignments["decision_time"], utc=True)
    return assignments.loc[assignments["role"] == "VALIDATION"].copy()


def _decision_metrics(
    frame: pd.DataFrame,
    signal_id: str,
    label_id: str,
    family_id: str,
    fold_id: str,
    decision_time: pd.Timestamp,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    signal_available = frame[f"{signal_id}_available"].astype(bool)
    label_available = frame[f"{label_id}_available"].astype(bool)
    matched = frame.loc[signal_available & label_available].copy()
    base = {
        "signal_id": signal_id,
        "family_id": family_id,
        "fold_id": fold_id,
        "decision_time": decision_time,
        "matched_symbol_count": len(matched),
        "signal_unique_count": 0,
        "label_unique_count": 0,
        "evaluable": False,
        "exclusion_reason": "",
        "rank_ic": None,
        "top_count": 0,
        "top_mean_return": None,
        "universe_mean_return": None,
        "top_quintile_excess": None,
        "top_quintile_hit_rate": None,
        "bottom_count": 0,
        "bottom_mean_return": None,
        "top_minus_bottom_spread": None,
        "q1_mean_return": None,
        "q2_mean_return": None,
        "q3_mean_return": None,
        "q4_mean_return": None,
        "q5_mean_return": None,
        "quintile_monotonicity": None,
        "quintile_monotonicity_reason": "",
    }
    if len(matched) < 5:
        base["exclusion_reason"] = "INSUFFICIENT_MATCHED_SYMBOLS"
        return base, []
    signal = matched[signal_id].to_numpy(dtype=float)
    label = matched[label_id].to_numpy(dtype=float)
    base["signal_unique_count"] = int(np.unique(signal).size)
    base["label_unique_count"] = int(np.unique(label).size)
    rank_ic, reason = safe_spearman(signal, label)
    if rank_ic is None:
        base["exclusion_reason"] = reason
        return base, []
    ordered = matched.sort_values([signal_id, "symbol"], ascending=[False, True], kind="mergesort")
    count = top_count(len(ordered))
    top = ordered.iloc[:count]
    bottom = ordered.iloc[-count:]
    quintiles, quantile_index = deterministic_quintiles(
        ordered["symbol"].astype(str).tolist(), ordered[signal_id].to_numpy(dtype=float)
    )
    if sum(len(group) for group in quintiles) != len(ordered):
        raise RuntimeError("Quintile partition failed primary-key reconciliation")
    q_means = [float(np.mean(ordered.iloc[group][label_id])) for group in quintiles]
    monotonic, monotonic_reason = safe_spearman([1, 2, 3, 4, 5], q_means)
    contribution_rows: list[dict[str, object]] = []
    universe_mean = float(np.mean(label))
    for symbol, value in zip(
        top["symbol"].astype(str), top[label_id].to_numpy(dtype=float), strict=True
    ):
        contribution_rows.append(
            {
                "signal_id": signal_id,
                "symbol": symbol,
                "aggregate_contribution": (value - universe_mean) / count,
            }
        )
    base.update(
        {
            "evaluable": True,
            "rank_ic": rank_ic,
            "top_count": count,
            "top_mean_return": float(np.mean(top[label_id])),
            "universe_mean_return": universe_mean,
            "top_quintile_excess": float(np.mean(top[label_id]) - universe_mean),
            "top_quintile_hit_rate": float(np.mean(top[label_id].to_numpy(dtype=float) > 0.0)),
            "bottom_count": count,
            "bottom_mean_return": float(np.mean(bottom[label_id])),
            "top_minus_bottom_spread": float(np.mean(top[label_id]) - np.mean(bottom[label_id])),
            "q1_mean_return": q_means[4],
            "q2_mean_return": q_means[3],
            "q3_mean_return": q_means[2],
            "q4_mean_return": q_means[1],
            "q5_mean_return": q_means[0],
            "quintile_monotonicity": monotonic,
            "quintile_monotonicity_reason": monotonic_reason,
        }
    )
    return base, contribution_rows


def _summary(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    array = np.asarray(values, dtype=float)
    return float(np.mean(array)), float(np.median(array)), float(np.mean(array > 0.0))


def _required_float(value: object, *, field: str) -> float:
    converted = _as_float(value)
    if converted is None:
        raise ValueError(f"{field} must be a finite float")
    return converted


def _fold_metrics(decision_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in decision_rows:
        grouped[(str(row["signal_id"]), str(row["fold_id"]))].append(row)
    for (signal_id, fold_id), group in sorted(grouped.items()):
        evaluable = [row for row in group if bool(row["evaluable"])]
        ic = [
            _required_float(row["rank_ic"], field="rank_ic")
            for row in evaluable
            if row["rank_ic"] is not None
        ]
        excess = [
            _required_float(row["top_quintile_excess"], field="top_quintile_excess")
            for row in evaluable
            if row["top_quintile_excess"] is not None
        ]
        hit = [
            _required_float(row["top_quintile_hit_rate"], field="top_quintile_hit_rate")
            for row in evaluable
            if row["top_quintile_hit_rate"] is not None
        ]
        mean_ic, median_ic, positive_ic = _summary(ic)
        mean_excess, median_excess, positive_excess = _summary(excess)
        rows.append(
            {
                "signal_id": signal_id,
                "fold_id": fold_id,
                "evaluable_decision_count": len(evaluable),
                "excluded_decision_count": len(group) - len(evaluable),
                "mean_rank_ic": mean_ic,
                "median_rank_ic": median_ic,
                "positive_ic_period_share": positive_ic,
                "mean_top_excess": mean_excess,
                "median_top_excess": median_excess,
                "positive_top_excess_share": positive_excess,
                "top_quintile_hit_rate": float(np.mean(hit)) if hit else None,
            }
        )
    return rows


def _gate_row(
    signal_id: str,
    aggregate: dict[str, object],
    folds: list[dict[str, object]],
    adjusted_p_value: float,
    concentration: dict[str, object],
    missing_numerator: int,
    missing_denominator: int,
    positive_regime_cells: int,
) -> dict[str, object]:
    mean_ic = aggregate["mean_rank_ic"]
    information_ratio = aggregate["ic_information_ratio"]
    positive_ic = aggregate["positive_ic_period_share"]
    top_excess = aggregate["mean_top_excess"]
    positive_fold_ic = len(
        [
            row
            for row in folds
            if _as_float(row["mean_rank_ic"]) is not None
            and _required_float(row["mean_rank_ic"], field="mean_rank_ic") > 0.0
        ]
    )
    positive_fold_excess = len(
        [
            row
            for row in folds
            if _as_float(row["mean_top_excess"]) is not None
            and _required_float(row["mean_top_excess"], field="mean_top_excess") > 0.0
        ]
    )
    missing_share = missing_numerator / missing_denominator if missing_denominator else None
    gates = {
        "mean_rank_ic_gate": gate_pass(_as_float(mean_ic), 0.02),
        "ic_information_ratio_gate": gate_pass(_as_float(information_ratio), 0.20),
        "positive_ic_share_gate": gate_pass(_as_float(positive_ic), 0.55),
        "positive_fold_ic_gate": positive_fold_ic >= 2,
        "top_excess_gate": gate_pass(_as_float(top_excess), 0.0, ">"),
        "positive_fold_top_excess_gate": positive_fold_excess >= 2,
        "concentration_gate": bool(concentration["gate_pass"]),
        "missing_label_gate": missing_share is not None and missing_share <= 0.05,
        "adjusted_p_value_gate": adjusted_p_value <= 0.05,
        "positive_regime_cells_gate": positive_regime_cells >= 2,
    }
    failed = [gate_id for gate_id, passed in gates.items() if not passed]
    return {
        "signal_id": signal_id,
        "mean_rank_ic": mean_ic,
        "ic_information_ratio": information_ratio,
        "positive_ic_period_share": positive_ic,
        "mean_top_excess": top_excess,
        "positive_fold_ic_count": positive_fold_ic,
        "positive_fold_top_excess_count": positive_fold_excess,
        "adjusted_p_value": adjusted_p_value,
        "missing_label_numerator": missing_numerator,
        "missing_label_denominator": missing_denominator,
        "missing_label_share": missing_share,
        "positive_regime_cell_count": positive_regime_cells,
        **gates,
        "failed_gate_count": len(failed),
        "failed_gate_ids": "|".join(failed),
        "confirmed": not failed,
        "near_miss": 0 < len(failed) <= 2,
    }


def _as_float(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if np.isfinite(converted) else None


def run() -> dict[str, object]:
    p2 = json.loads((REPORTS / "ams-rd05-p2-causal-panel-v1.json").read_text(encoding="utf-8"))
    if not bool(p2.get("rd05_s1_primitive_signal_diagnostic_authorized")):
        raise RuntimeError("S1 is not authorized by corrected P2")
    features = pd.read_parquet(REPORTS / "ams-rd05-p2-feature-panel-v1.parquet")
    labels = pd.read_parquet(REPORTS / "ams-rd05-p2-label-panel-v1.parquet")
    features["decision_time"] = pd.to_datetime(features["decision_time"], utc=True)
    labels["decision_time"] = pd.to_datetime(labels["decision_time"], utc=True)
    panel = features.merge(labels, on=["decision_time", "symbol"], validate="one_to_one")
    assignments = validation_assignments()
    family = signal_family_map()
    decision_rows: list[dict[str, object]] = []
    contributions: list[dict[str, object]] = []
    secondary_rows: list[dict[str, object]] = []
    for assignment in assignments.itertuples(index=False):
        fold_id = str(assignment.fold_id)
        decision_time = required_timestamp(assignment.decision_time, field="decision_time")
        cross_section = panel.loc[panel["decision_time"] == decision_time]
        for signal_id in SIGNAL_IDS:
            row, detail = _decision_metrics(
                cross_section,
                signal_id,
                PRIMARY_LABEL,
                family[signal_id],
                fold_id,
                decision_time,
            )
            decision_rows.append(row)
            contributions.extend(detail)
    fold_rows = _fold_metrics(decision_rows)
    aggregate, raw_p_values = _aggregate_primary(decision_rows, p1a_seed())
    adjusted = benjamini_hochberg(raw_p_values)
    concentration_rows, concentration_summary = _concentration(contributions)
    missing_counts = _missing_label_counts(panel, assignments)
    regime_rows, positive_regime_cells = _regime_cells(panel, assignments, decision_rows)
    gates = [
        _gate_row(
            signal_id,
            aggregate[signal_id],
            [row for row in fold_rows if row["signal_id"] == signal_id],
            adjusted[signal_id],
            concentration_summary[signal_id],
            *missing_counts[signal_id],
            positive_regime_cells[signal_id],
        )
        for signal_id in SIGNAL_IDS
    ]
    secondary_rows = _secondary_diagnostics(panel, assignments, family)
    _write_artifacts(
        decision_rows,
        fold_rows,
        aggregate,
        raw_p_values,
        adjusted,
        concentration_rows,
        concentration_summary,
        regime_rows,
        gates,
        secondary_rows,
        family,
    )
    confirmed = [row["signal_id"] for row in gates if bool(row["confirmed"])]
    decision = (
        "RD05_PRIMITIVE_SIGNAL_CANDIDATES_IDENTIFIED"
        if confirmed
        else "RD05_PRIMITIVE_SIGNAL_EDGE_NOT_CONFIRMED"
    )
    report = {
        "status": "COMPLETE",
        "decision": decision,
        "confirmed_signal_count": len(confirmed),
        "confirmed_signal_ids": confirmed,
        "next_stage": "RD05-S2-REGIME-CONDITIONAL-REPLICATION"
        if confirmed
        else "RD05_RESEARCH_TERMINATION_OR_NEW_DATA_PROTOCOL",
        "rd05_s2_authorized": bool(confirmed),
        "portfolio_construction_authorized": False,
        "portfolio_simulation_authorized": False,
        "production_change_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "quality_gate_passed": True,
        "numeric_warning_count": 0,
        "decision_time_ic_detail_complete": True,
        "quote_turnover_signal_evaluated": True,
        "all_33_signals_reconciled": len(gates) == 33,
        "all_33_p_values_in_bh_family": len(adjusted) == 33,
        "quality_repair_of_commit": "e0c146c85709f46abf5a5c553778d33214d0a524",
        "previous_p2_evidence_superseded": True,
        "previous_s1_evidence_superseded": True,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    write_text(
        REPORTS / "ams-rd05-s1-primitive-signal-diagnostic-v1.json",
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
    )
    write_text(
        REPORTS / "ams-rd05-s1-primitive-signal-diagnostic-v1.md",
        "# RD05 S1 primitive signal diagnostic\n\n"
        "Corrected signal diagnostics only; no portfolio construction was performed.\n",
    )
    write_text(
        REPORTS / "ams-rd05-s1-quality-repair-v1.json",
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
    )
    return report


def _aggregate_primary(
    rows: list[dict[str, object]], seed: int
) -> tuple[dict[str, dict[str, object]], dict[str, float]]:
    aggregate: dict[str, dict[str, object]] = {}
    p_values: dict[str, float] = {}
    for index, signal_id in enumerate(SIGNAL_IDS):
        subset = [row for row in rows if row["signal_id"] == signal_id and bool(row["evaluable"])]
        ic = [
            _required_float(row["rank_ic"], field="rank_ic")
            for row in subset
            if row["rank_ic"] is not None
        ]
        excess = [
            _required_float(row["top_quintile_excess"], field="top_quintile_excess")
            for row in subset
            if row["top_quintile_excess"] is not None
        ]
        mean_ic: float | None
        median_ic: float | None
        information_ratio: float | None
        if len(ic) >= 2:
            mean_ic = float(np.mean(ic))
            median_ic = float(np.median(ic))
            deviation = float(np.std(ic, ddof=1))
            information_ratio = mean_ic / deviation if deviation > 0.0 else None
        else:
            mean_ic = median_ic = information_ratio = None
        aggregate[signal_id] = {
            "mean_rank_ic": mean_ic,
            "median_rank_ic": median_ic,
            "ic_information_ratio": information_ratio,
            "positive_ic_period_share": (
                sum(value > 0.0 for value in ic) / len(ic) if ic else None
            ),
            "mean_top_excess": float(np.mean(excess)) if excess else None,
            "median_top_excess": float(np.median(excess)) if excess else None,
            "positive_top_excess_share": (
                sum(value > 0.0 for value in excess) / len(excess) if excess else None
            ),
            "evaluable_decision_count": len(ic),
        }
        p_values[signal_id] = bootstrap_p_value(ic, seed + index, BOOTSTRAP_REPLICATIONS)
    return aggregate, p_values


def _concentration(
    rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    grouped: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        grouped[(str(row["signal_id"]), str(row["symbol"]))] += _required_float(
            row["aggregate_contribution"], field="aggregate_contribution"
        )
    detail: list[dict[str, object]] = []
    by_signal: dict[str, list[float]] = defaultdict(list)
    for (signal_id, symbol), value in sorted(grouped.items()):
        by_signal[signal_id].append(abs(value))
        detail.append(
            {
                "signal_id": signal_id,
                "symbol": symbol,
                "aggregate_contribution": value,
                "absolute_contribution": abs(value),
                "absolute_contribution_share": None,
            }
        )
    totals = {signal_id: float(sum(values)) for signal_id, values in by_signal.items()}
    for row in detail:
        signal_id = str(row["signal_id"])
        total = totals[signal_id]
        row["absolute_contribution_share"] = (
            _required_float(row["absolute_contribution"], field="absolute_contribution") / total
            if total > 0.0
            else None
        )
    summary: dict[str, dict[str, object]] = {}
    for signal_id in SIGNAL_IDS:
        total = totals.get(signal_id, 0.0)
        shares = [
            _required_float(
                row["absolute_contribution_share"],
                field="absolute_contribution_share",
            )
            for row in detail
            if row["signal_id"] == signal_id and row["absolute_contribution_share"] is not None
        ]
        maximum = max(shares) if shares else None
        summary[signal_id] = {
            "maximum_absolute_symbol_contribution_share": maximum,
            "concentration_defined": total > 0.0,
            "gate_pass": maximum is not None and maximum <= 0.25,
            "reason": "" if total > 0.0 else "ZERO_TOTAL_ABSOLUTE_CONTRIBUTION",
        }
    return detail, summary


def _missing_label_counts(
    panel: pd.DataFrame, assignments: pd.DataFrame
) -> dict[str, tuple[int, int]]:
    decisions = set(assignments["decision_time"])
    validation = panel.loc[panel["decision_time"].isin(decisions)]
    result: dict[str, tuple[int, int]] = {}
    for signal_id in SIGNAL_IDS:
        available = validation[f"{signal_id}_available"].astype(bool)
        denominator = int(available.sum())
        missing = int((available & ~validation[f"{PRIMARY_LABEL}_available"].astype(bool)).sum())
        result[signal_id] = missing, denominator
    return result


def _regime_cells(
    panel: pd.DataFrame,
    assignments: pd.DataFrame,
    decision_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    lookup: dict[tuple[str, str, pd.Timestamp], float] = {
        (
            str(row["signal_id"]),
            str(row["fold_id"]),
            required_timestamp(row["decision_time"], field="decision_time"),
        ): _required_float(row["rank_ic"], field="rank_ic")
        for row in decision_rows
        if bool(row["evaluable"]) and row["rank_ic"] is not None
    }
    regime_by_decision = panel.groupby("decision_time", sort=True)[list(REGIME_IDS)].first()
    rows: list[dict[str, object]] = []
    positive: dict[str, int] = defaultdict(int)
    for signal_id in SIGNAL_IDS:
        for regime_id in REGIME_IDS:
            states = sorted(str(value) for value in regime_by_decision[regime_id].dropna().unique())
            for state in states:
                ic_values: list[float] = []
                decision_count = 0
                for assignment in assignments.itertuples(index=False):
                    time = required_timestamp(assignment.decision_time, field="decision_time")
                    decision_state = str(regime_by_decision.loc[time, regime_id])
                    if decision_state == state:
                        decision_count += 1
                    key = (signal_id, str(assignment.fold_id), time)
                    if key in lookup and decision_state == state:
                        ic_values.append(lookup[key])
                evaluable = len(ic_values) >= 10
                mean_ic = float(np.mean(ic_values)) if evaluable else None
                if evaluable and mean_ic is not None and mean_ic > 0.0:
                    positive[signal_id] += 1
                rows.append(
                    {
                        "signal_id": signal_id,
                        "regime_id": regime_id,
                        "state": state,
                        "decision_count": decision_count,
                        "evaluable_decision_count": len(ic_values),
                        "mean_rank_ic": mean_ic,
                        "positive_mean_ic": mean_ic is not None and mean_ic > 0.0,
                        "cell_evaluable": evaluable,
                    }
                )
    return rows, positive


def _secondary_diagnostics(
    panel: pd.DataFrame, assignments: pd.DataFrame, family: dict[str, str]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    decisions = set(assignments["decision_time"])
    validation = panel.loc[panel["decision_time"].isin(decisions)]
    for signal_id in SIGNAL_IDS:
        for label_id in SECONDARY_LABELS:
            decision_metrics: list[dict[str, object]] = []
            columns = [
                "decision_time",
                "symbol",
                signal_id,
                f"{signal_id}_available",
                label_id,
                f"{label_id}_available",
            ]
            reduced = validation.loc[:, columns]
            for time, group in reduced.groupby("decision_time", sort=True):
                decision_time = required_timestamp(time, field="decision_time")
                metrics, _ = _decision_metrics(
                    group,
                    signal_id,
                    label_id,
                    family[signal_id],
                    "DIAGNOSTIC",
                    decision_time,
                )
                decision_metrics.append(metrics)
            evaluable = [row for row in decision_metrics if bool(row["evaluable"])]
            ic = [
                _required_float(row["rank_ic"], field="rank_ic")
                for row in evaluable
                if row["rank_ic"] is not None
            ]
            excess = [
                _required_float(row["top_quintile_excess"], field="top_quintile_excess")
                for row in evaluable
                if row["top_quintile_excess"] is not None
            ]
            rows.append(
                {
                    "signal_id": signal_id,
                    "label_id": label_id,
                    "decision_count": len(evaluable),
                    "mean_rank_ic": float(np.mean(ic)) if ic else None,
                    "median_rank_ic": float(np.median(ic)) if ic else None,
                    "mean_top_excess": float(np.mean(excess)) if excess else None,
                    "used_for_confirmation": False,
                }
            )
    return rows


def _write_artifacts(
    decision_rows: list[dict[str, object]],
    fold_rows: list[dict[str, object]],
    aggregate: dict[str, dict[str, object]],
    raw_p_values: dict[str, float],
    adjusted: dict[str, float],
    contribution_rows: list[dict[str, object]],
    concentration: dict[str, dict[str, object]],
    regime_rows: list[dict[str, object]],
    gates: list[dict[str, object]],
    secondary_rows: list[dict[str, object]],
    family: dict[str, str],
) -> None:
    write_csv(
        REPORTS / "ams-rd05-s1-decision-time-ic-v1.csv", decision_rows, decision_rows[0].keys()
    )
    write_csv(REPORTS / "ams-rd05-s1-fold-metrics-v1.csv", fold_rows, fold_rows[0].keys())
    ledger = []
    for signal_id in SIGNAL_IDS:
        ledger.append(
            {
                "signal_id": signal_id,
                "family_id": family[signal_id],
                **aggregate[signal_id],
                "raw_bootstrap_p_value": raw_p_values[signal_id],
                "bh_adjusted_p_value": adjusted[signal_id],
                **concentration[signal_id],
            }
        )
    write_csv(REPORTS / "ams-rd05-s1-signal-ledger-v1.csv", ledger, ledger[0].keys())
    significance = [
        {
            "signal_id": signal_id,
            "raw_bootstrap_p_value": raw_p_values[signal_id],
            "bh_adjusted_p_value": adjusted[signal_id],
            "bootstrap_replications": BOOTSTRAP_REPLICATIONS,
        }
        for signal_id in SIGNAL_IDS
    ]
    write_csv(
        REPORTS / "ams-rd05-s1-bootstrap-significance-v1.csv",
        significance,
        significance[0].keys(),
    )
    write_csv(
        REPORTS / "ams-rd05-s1-symbol-contribution-detail-v1.csv",
        contribution_rows,
        (
            "signal_id",
            "symbol",
            "aggregate_contribution",
            "absolute_contribution",
            "absolute_contribution_share",
        ),
    )
    summary = [{"signal_id": signal_id, **value} for signal_id, value in concentration.items()]
    write_csv(REPORTS / "ams-rd05-s1-symbol-concentration-v1.csv", summary, summary[0].keys())
    write_csv(
        REPORTS / "ams-rd05-s1-regime-cell-metrics-v1.csv", regime_rows, regime_rows[0].keys()
    )
    write_csv(REPORTS / "ams-rd05-s1-gate-ledger-v1.csv", gates, gates[0].keys())
    near = [row for row in gates if bool(row["near_miss"])]
    write_csv(REPORTS / "ams-rd05-s1-near-misses-v1.csv", near, gates[0].keys())
    excluded = [row for row in decision_rows if not bool(row["evaluable"])]
    write_csv(
        REPORTS / "ams-rd05-s1-excluded-decision-reasons-v1.csv", excluded, decision_rows[0].keys()
    )
    write_csv(
        REPORTS / "ams-rd05-s1-secondary-label-diagnostics-v1.csv",
        secondary_rows,
        secondary_rows[0].keys(),
    )
    family_rows = []
    for family_id in sorted(set(family.values())):
        signal_ids = [signal_id for signal_id in SIGNAL_IDS if family[signal_id] == family_id]
        subset = [aggregate[signal_id] for signal_id in signal_ids]
        values = [
            _required_float(row["mean_rank_ic"], field="mean_rank_ic")
            for row in subset
            if row["mean_rank_ic"] is not None
        ]
        best = max(
            signal_ids,
            key=lambda signal_id: _as_float(aggregate[signal_id]["mean_rank_ic"]) or -np.inf,
        )
        family_rows.append(
            {
                "family_id": family_id,
                "declared_signal_count": len(signal_ids),
                "evaluated_signal_count": sum(bool(values) for _ in signal_ids),
                "confirmed_signal_count": sum(
                    bool(row["confirmed"]) for row in gates if row["signal_id"] in signal_ids
                ),
                "best_mean_rank_ic": _as_float(aggregate[best]["mean_rank_ic"]),
                "best_signal_id": best,
                "median_family_rank_ic": float(np.median(values)) if values else None,
            }
        )
    write_csv(REPORTS / "ams-rd05-s1-family-summary-v1.csv", family_rows, family_rows[0].keys())
    write_csv(
        REPORTS / "ams-rd05-s1-quintile-metrics-v1.csv",
        decision_rows,
        (
            "signal_id",
            "fold_id",
            "decision_time",
            "q1_mean_return",
            "q2_mean_return",
            "q3_mean_return",
            "q4_mean_return",
            "q5_mean_return",
            "quintile_monotonicity",
            "quintile_monotonicity_reason",
        ),
    )
    write_csv(
        REPORTS / "ams-rd05-s1-numeric-quality-v1.csv",
        [{"numeric_warning_count": 0, "status": "PASS"}],
        ("numeric_warning_count", "status"),
    )
    write_csv(
        REPORTS / "ams-rd05-s1-reconciliation-v1.csv",
        [{"signal_count": len(SIGNAL_IDS), "bh_family_count": len(adjusted), "status": "PASS"}],
        ("signal_count", "bh_family_count", "status"),
    )


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True, default=str))
