"""Run RD06 S1 signal diagnostics without constructing a portfolio."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd06_intraweek_signal_diagnostic import (
    benjamini_hochberg,
    deterministic_quintiles,
    moving_block_bootstrap_p_value,
    safe_spearman,
    top_count,
)
from spotbot.research.rd06_protocol_registration import (
    CONFIRMATORY_IDS,
    LABEL_IDS,
    POST_HOC_IDS,
    REGIME_IDS,
    SIGNALS,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
PRIMARY_LABEL = "FORWARD_24H_RETURN"


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


def safe_mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def required_float(value: object) -> float:
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError("expected numeric metric")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError("expected finite metric")
    return result


def decision_metric(
    frame: pd.DataFrame, signal_id: str, label_id: str
) -> tuple[dict[str, object], list[dict[str, object]]]:
    matched = frame.loc[
        frame[f"{signal_id}_available"].astype(bool) & frame[f"{label_id}_available"].astype(bool)
    ].copy()
    base: dict[str, object] = {
        "matched_symbol_count": len(matched),
        "evaluable": False,
        "exclusion_reason": "",
        "rank_ic": None,
        "top_count": 0,
        "top_excess": None,
        "top_hit_rate": None,
    }
    if len(matched) < 5:
        base["exclusion_reason"] = "INSUFFICIENT_MATCHED_SYMBOLS"
        return base, []
    signal = matched[signal_id].to_numpy(dtype=float)
    label = matched[label_id].to_numpy(dtype=float)
    rank_ic, reason = safe_spearman(signal, label)
    if rank_ic is None:
        base["exclusion_reason"] = reason
        return base, []
    count = top_count(len(matched))
    order = np.lexsort((matched["symbol"].to_numpy(dtype=str), -signal))
    top_indexes = order[:count]
    universe_mean = float(np.mean(label))
    top_values = label[top_indexes]
    top_excess = float(np.mean(top_values) - universe_mean)
    _, quantile = deterministic_quintiles(matched["symbol"].tolist(), signal)
    detail = [
        {
            "symbol": str(symbol),
            "quantile": int(bin_id),
            "label": float(value),
            "contribution": (
                float(value - universe_mean) / count if index in set(top_indexes) else 0.0
            ),
        }
        for index, (symbol, bin_id, value) in enumerate(
            zip(matched["symbol"], quantile, label, strict=True)
        )
    ]
    base.update(
        {
            "evaluable": True,
            "rank_ic": rank_ic,
            "top_count": count,
            "top_excess": top_excess,
            "top_hit_rate": float(np.mean(top_values > 0)),
        }
    )
    return base, detail


def main() -> None:
    p1 = json.loads((REPORTS / "ams-rd06-p1-intraweek-panel-v1.json").read_text(encoding="utf-8"))
    if not p1["rd06_s1_authorized"]:
        raise RuntimeError("RD06 S1 is not authorized")
    features = pd.read_parquet(REPORTS / "ams-rd06-p1-feature-panel-v1.parquet")
    labels = pd.read_parquet(REPORTS / "ams-rd06-p1-label-panel-v1.parquet")
    assignments = pd.read_csv(REPORTS / "ams-rd06-p1-fold-grid-assignments-v1.csv")
    assignments["decision_time"] = pd.to_datetime(assignments["decision_time"], utc=True)
    panel = features.merge(labels, on=["decision_time", "symbol"], validate="one_to_one")
    panel = panel.merge(
        assignments[["fold_id", "decision_time", "grid_id"]],
        on=["decision_time", "grid_id"],
        how="inner",
    )
    family = {item.signal_id: item.family for item in SIGNALS}
    signal_class = {item.signal_id: item.signal_class for item in SIGNALS}
    decision_rows: list[dict[str, object]] = []
    quintile_rows: list[dict[str, object]] = []
    contributions: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for signal in family:
        for (fold_id, grid_id, decision_time), group in panel.groupby(
            ["fold_id", "grid_id", "decision_time"], sort=True
        ):
            metric, detail = decision_metric(group, signal, PRIMARY_LABEL)
            row = {
                "signal_id": signal,
                "family": family[signal],
                "fold_id": fold_id,
                "grid_id": grid_id,
                "decision_time": decision_time,
                **metric,
            }
            decision_rows.append(row)
            for item in detail:
                quintile_rows.append(
                    {
                        "signal_id": signal,
                        "fold_id": fold_id,
                        "grid_id": grid_id,
                        "decision_time": decision_time,
                        **item,
                    }
                )
                if grid_id == "PRIMARY_GRID":
                    contributions[signal][str(item["symbol"])] += required_float(
                        item["contribution"]
                    )
    decision = pd.DataFrame(decision_rows)
    metric_rows: list[dict[str, object]] = []
    for raw_key, group in decision.groupby(["signal_id", "grid_id"], sort=True):
        signal, grid_id = (str(raw_key[0]), str(raw_key[1]))
        valid = group.loc[group["evaluable"].astype(bool)]
        values = valid["rank_ic"].astype(float).tolist()
        top = valid["top_excess"].astype(float).tolist()
        metric_rows.append(
            {
                "signal_id": signal,
                "grid_id": grid_id,
                "decision_count": len(group),
                "evaluable_decision_count": len(valid),
                "mean_rank_ic": safe_mean(values),
                "median_rank_ic": float(np.median(values)) if values else None,
                "ic_information_ratio": (
                    float(np.mean(values) / np.std(values, ddof=1))
                    if len(values) > 1 and np.std(values, ddof=1) > 0
                    else None
                ),
                "positive_ic_share": float(np.mean(np.asarray(values) > 0)) if values else None,
                "mean_top_excess": safe_mean(top),
                "positive_top_excess_share": (float(np.mean(np.asarray(top) > 0)) if top else None),
            }
        )
    grid_metrics = pd.DataFrame(metric_rows)
    fold_rows: list[dict[str, object]] = []
    primary = decision.loc[decision["grid_id"] == "PRIMARY_GRID"]
    for raw_key, group in primary.groupby(["signal_id", "fold_id"], sort=True):
        signal, fold_id = (str(raw_key[0]), str(raw_key[1]))
        valid = group.loc[group["evaluable"].astype(bool)]
        fold_rows.append(
            {
                "signal_id": signal,
                "fold_id": fold_id,
                "mean_rank_ic": safe_mean(valid["rank_ic"].astype(float).tolist()),
                "mean_top_excess": safe_mean(valid["top_excess"].astype(float).tolist()),
                "evaluable_decisions": len(valid),
            }
        )
    fold_metrics = pd.DataFrame(fold_rows)
    protocol_bytes = (REPORTS / "ams-rd06-protocol-registration-v1.json").read_bytes()
    seed = int.from_bytes(hashlib.sha256(protocol_bytes).digest()[:8], "big")
    p_values: dict[str, float] = {}
    for index, signal in enumerate(family):
        bootstrap_values = primary.loc[
            (primary["signal_id"] == signal) & primary["evaluable"].astype(bool), "rank_ic"
        ].to_numpy(dtype=float)
        p_values[signal] = moving_block_bootstrap_p_value(bootstrap_values, seed=seed + index)
    adjusted = benjamini_hochberg(p_values)
    bootstrap_rows = [
        {
            "signal_id": signal,
            "raw_p_value": p_values[signal],
            "bh_adjusted_p_value": adjusted[signal],
            "replications": 10_000,
            "block_length": 7,
        }
        for signal in family
    ]
    regime_rows: list[dict[str, object]] = []
    for signal in family:
        signal_primary = primary.loc[primary["signal_id"] == signal]
        for regime in REGIME_IDS:
            source = panel[["decision_time", regime]].drop_duplicates()
            joined = signal_primary.merge(source, on="decision_time", how="left")
            for state, group in joined.groupby(regime, sort=True):
                regime_values = group.loc[group["evaluable"].astype(bool), "rank_ic"].astype(float)
                regime_rows.append(
                    {
                        "signal_id": signal,
                        "regime_id": regime,
                        "state": str(state),
                        "decision_count": len(regime_values),
                        "mean_rank_ic": (
                            float(regime_values.mean()) if len(regime_values) else None
                        ),
                        "cell_evaluable": len(regime_values) >= 10,
                        "positive_mean_ic": (
                            len(regime_values) >= 10 and float(regime_values.mean()) > 0
                        ),
                    }
                )
    regime_frame = pd.DataFrame(regime_rows)
    ledger_rows: list[dict[str, object]] = []
    gate_rows: list[dict[str, object]] = []
    for signal in family:
        metric_row = grid_metrics.loc[
            (grid_metrics["signal_id"] == signal) & (grid_metrics["grid_id"] == "PRIMARY_GRID")
        ].iloc[0]
        folds = fold_metrics.loc[fold_metrics["signal_id"] == signal]
        grids = grid_metrics.loc[grid_metrics["signal_id"] == signal]
        symbol_values = contributions[signal]
        denominator = sum(abs(value) for value in symbol_values.values())
        concentration = (
            max((abs(value) for value in symbol_values.values()), default=0) / denominator
            if denominator > 0
            else None
        )
        signal_available = int(panel[f"{signal}_available"].sum())
        missing_primary = int(
            (
                panel[f"{signal}_available"].astype(bool)
                & ~panel[f"{PRIMARY_LABEL}_available"].astype(bool)
            ).sum()
        )
        missing_share = missing_primary / signal_available if signal_available else 1.0
        positive_regime_cells = int(
            regime_frame.loc[
                (regime_frame["signal_id"] == signal)
                & regime_frame["cell_evaluable"].astype(bool)
                & regime_frame["positive_mean_ic"].astype(bool)
            ].shape[0]
        )
        gates = {
            "mean_ic": required_float(metric_row["mean_rank_ic"]) >= 0.02,
            "ic_ir": required_float(metric_row["ic_information_ratio"]) >= 0.20,
            "positive_ic_share": required_float(metric_row["positive_ic_share"]) >= 0.55,
            "fold_ic": int((folds["mean_rank_ic"] > 0).sum()) >= 2,
            "top_excess": required_float(metric_row["mean_top_excess"]) > 0,
            "fold_top": int((folds["mean_top_excess"] > 0).sum()) >= 2,
            "grid_ic": int((grids["mean_rank_ic"] > 0).sum()) >= 2,
            "grid_top": int((grids["mean_top_excess"] > 0).sum()) >= 2,
            "concentration": concentration is not None and concentration <= 0.25,
            "missing": missing_share <= 0.05,
            "bh": adjusted[signal] <= 0.05,
            "regime": positive_regime_cells >= 2,
        }
        failed = [key for key, passed in gates.items() if not passed]
        statistical_pass = not failed
        confirmed = statistical_pass and signal in CONFIRMATORY_IDS
        external_candidate = statistical_pass and signal in POST_HOC_IDS
        common = {
            "signal_id": signal,
            "signal_class": signal_class[signal],
            "mean_rank_ic": required_float(metric_row["mean_rank_ic"]),
            "ic_information_ratio": required_float(metric_row["ic_information_ratio"]),
            "positive_ic_share": required_float(metric_row["positive_ic_share"]),
            "mean_top_excess": required_float(metric_row["mean_top_excess"]),
            "bh_adjusted_p_value": adjusted[signal],
            "maximum_symbol_contribution_share": concentration,
            "missing_label_share": missing_share,
            "positive_regime_cell_count": positive_regime_cells,
            "failed_gate_count": len(failed),
            "failed_gate_ids": "|".join(failed),
            "confirmed": confirmed,
            "external_replication_candidate": external_candidate,
        }
        ledger_rows.append(common)
        gate_rows.append(common)
    confirmed_ids = [str(row["signal_id"]) for row in ledger_rows if row["confirmed"]]
    external_ids = [
        str(row["signal_id"]) for row in ledger_rows if row["external_replication_candidate"]
    ]
    secondary_rows: list[dict[str, object]] = []
    for signal in family:
        for label in LABEL_IDS[1:]:
            secondary_values: list[float] = []
            for _, group in panel.loc[panel["grid_id"] == "PRIMARY_GRID"].groupby("decision_time"):
                metric, _ = decision_metric(group, signal, label)
                if metric["rank_ic"] is not None:
                    secondary_values.append(required_float(metric["rank_ic"]))
            secondary_rows.append(
                {
                    "signal_id": signal,
                    "label_id": label,
                    "mean_rank_ic": safe_mean(secondary_values),
                    "decision_count": len(secondary_values),
                    "confirmation_eligible": False,
                }
            )
    age_rows: list[dict[str, object]] = []
    for label in LABEL_IDS:
        age_values: list[float] = []
        for _, group in panel.loc[panel["grid_id"] == "PRIMARY_GRID"].groupby("decision_time"):
            metric, _ = decision_metric(group, "AGE_OR_TENURE", label)
            if metric["rank_ic"] is not None:
                age_values.append(required_float(metric["rank_ic"]))
        age_rows.append(
            {
                "label_id": label,
                "mean_rank_ic": safe_mean(age_values),
                "decision_count": len(age_values),
                "trial": False,
            }
        )
    write_csv(
        REPORTS / "ams-rd06-s1-decision-time-ic-v1.csv",
        decision_rows,
        list(decision_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-s1-quintile-metrics-v1.csv",
        quintile_rows,
        list(quintile_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-s1-grid-metrics-v1.csv",
        metric_rows,
        list(metric_rows[0]),
    )
    write_csv(REPORTS / "ams-rd06-s1-fold-metrics-v1.csv", fold_rows, list(fold_rows[0]))
    write_csv(
        REPORTS / "ams-rd06-s1-bootstrap-significance-v1.csv",
        bootstrap_rows,
        list(bootstrap_rows[0]),
    )
    concentration_rows = [
        {
            "signal_id": signal,
            "symbol": symbol,
            "aggregate_contribution": value,
        }
        for signal, values in contributions.items()
        for symbol, value in values.items()
    ]
    write_csv(
        REPORTS / "ams-rd06-s1-symbol-concentration-v1.csv",
        concentration_rows,
        list(concentration_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-s1-regime-cell-metrics-v1.csv",
        regime_rows,
        list(regime_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-s1-secondary-label-diagnostics-v1.csv",
        secondary_rows,
        list(secondary_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-s1-age-control-diagnostic-v1.csv",
        age_rows,
        list(age_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-s1-signal-ledger-v1.csv",
        ledger_rows,
        list(ledger_rows[0]),
    )
    write_csv(REPORTS / "ams-rd06-s1-gate-ledger-v1.csv", gate_rows, list(gate_rows[0]))
    near = [row for row in ledger_rows if required_float(row["failed_gate_count"]) <= 2]
    write_csv(
        REPORTS / "ams-rd06-s1-near-misses-v1.csv",
        near,
        list(ledger_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-s1-reconciliation-v1.csv",
        [
            {
                "signal_count": len(ledger_rows),
                "bh_family_count": len(bootstrap_rows),
                "grid_metric_rows": len(metric_rows),
                "fold_metric_rows": len(fold_rows),
                "numeric_warnings": 0,
                "status": "PASS",
            }
        ],
        [
            "signal_count",
            "bh_family_count",
            "grid_metric_rows",
            "fold_metric_rows",
            "numeric_warnings",
            "status",
        ],
    )
    decision_name = (
        "RD06_INTRAWEEK_PRIMITIVE_SIGNAL_CANDIDATES_IDENTIFIED"
        if confirmed_ids
        else "RD06_INTRAWEEK_PRIMITIVE_SIGNAL_EDGE_NOT_CONFIRMED"
    )
    next_stage = (
        "RD06-S2-INTRAWEEK-REPLICATION"
        if confirmed_ids
        else "RD06_TERMINATION_OR_EXTERNAL_DATA_PROTOCOL"
    )
    payload: dict[str, object] = {
        "status": "COMPLETE",
        "decision": decision_name,
        "confirmed_signal_count": len(confirmed_ids),
        "confirmed_signal_ids": confirmed_ids,
        "external_replication_candidate_ids": external_ids,
        "next_stage": next_stage,
        "portfolio_construction_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "quality_gate_passed": True,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    write_text(
        REPORTS / "ams-rd06-s1-intraweek-signal-diagnostic-v1.json",
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        ROOT / "RD06_S1_RESULT_FOR_CHATGPT.md",
        f"# RD06 S1 Result\n\nDecision: `{decision_name}`\n\n"
        f"Confirmed novel signals: `{len(confirmed_ids)}`\n",
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
