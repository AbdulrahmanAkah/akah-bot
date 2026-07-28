"""Run the preregistered RD07 cross-venue spot-flow signal diagnostic."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd07_matched_panel import REGIME_IDS, SIGNAL_IDS
from spotbot.research.rd07_signal_diagnostic import (
    benjamini_hochberg,
    effective_sample_size,
    moving_block_p_value,
    safe_spearman,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
PRIMARY = "FORWARD_24H_RETURN"
EXTERNAL = "BN_FORWARD_24H_RETURN"
POST_HOC = "BN_LOW_REALIZED_VOLATILITY_42"


def decision_metric(group: pd.DataFrame, signal: str, label: str) -> dict[str, object]:
    matched = group.loc[group[signal].notna() & group[label].notna()].copy()
    if len(matched) < 5:
        return {"evaluable": False, "matched": len(matched)}
    scores = matched[signal].to_numpy(dtype=float)
    labels = matched[label].to_numpy(dtype=float)
    rank_ic, reason = safe_spearman(scores, labels)
    if rank_ic is None:
        return {"evaluable": False, "matched": len(matched), "reason": reason}
    count = max(1, int(np.ceil(len(matched) / 5)))
    order = np.lexsort((matched["symbol"].to_numpy(dtype=str), -scores))
    top = matched.iloc[order[:count]]
    universe_mean = float(labels.mean())
    return {
        "evaluable": True,
        "matched": len(matched),
        "rank_ic": rank_ic,
        "top_excess": float(top[label].mean() - universe_mean),
        "top_symbols": "|".join(top["symbol"].astype(str)),
        "universe_mean": universe_mean,
        "top_count": count,
    }


def mean_or_none(series: pd.Series) -> float | None:
    values = series.dropna().astype(float)
    return float(values.mean()) if len(values) else None


def required_float(value: object) -> float:
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError("expected numeric value")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError("expected finite value")
    return result


def main() -> None:
    panel_report = json.loads(
        (REPORTS / "ams-rd07-matched-panel-v1.json").read_text(encoding="utf-8")
    )
    if not panel_report["signal_diagnostic_authorized"]:
        raise RuntimeError("RD07 matched panel did not authorize diagnostics")
    features = pd.read_parquet(REPORTS / "ams-rd07-binance-feature-panel-v1.parquet")
    labels = pd.read_parquet(REPORTS / "ams-rd07-matched-label-panel-v1.parquet")
    assignments = pd.read_csv(REPORTS / "ams-rd06-p1-fold-grid-assignments-v1.csv")
    assignments["decision_time"] = pd.to_datetime(assignments["decision_time"], utc=True)
    panel = features.merge(labels, on=["decision_time", "symbol"], validate="one_to_one")
    panel = panel.merge(
        assignments[["fold_id", "decision_time", "grid_id"]],
        on=["decision_time", "grid_id"],
        how="inner",
        validate="many_to_one",
    )
    decision_rows: list[dict[str, object]] = []
    external_rows: list[dict[str, object]] = []
    contribution: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for signal in SIGNAL_IDS:
        for (fold, grid, decision), group in panel.groupby(
            ["fold_id", "grid_id", "decision_time"], sort=True
        ):
            metric = decision_metric(group, signal, PRIMARY)
            decision_rows.append(
                {
                    "signal_id": signal,
                    "fold_id": fold,
                    "grid_id": grid,
                    "decision_time": decision,
                    **metric,
                }
            )
            external_metric = decision_metric(group, signal, EXTERNAL)
            external_rows.append(
                {
                    "signal_id": signal,
                    "fold_id": fold,
                    "grid_id": grid,
                    "decision_time": decision,
                    **external_metric,
                }
            )
            if grid == "PRIMARY_GRID" and bool(metric["evaluable"]):
                universe_mean = required_float(metric["universe_mean"])
                top_symbols = str(metric["top_symbols"]).split("|")
                top_frame = group.loc[group["symbol"].astype(str).isin(top_symbols)]
                for row in top_frame.itertuples(index=False):
                    contribution[signal][str(row.symbol)] += (
                        float(getattr(row, PRIMARY)) - universe_mean
                    ) / len(top_symbols)
    decisions = pd.DataFrame(decision_rows)
    external_decisions = pd.DataFrame(external_rows)
    grid_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    external_fold_rows: list[dict[str, object]] = []
    for raw_key, metric_group in decisions.groupby(["signal_id", "grid_id"], sort=True):
        signal_key, grid_key = str(raw_key[0]), str(raw_key[1])
        valid = metric_group.loc[metric_group["evaluable"].astype(bool)]
        ic = valid["rank_ic"].astype(float)
        top_excess_values = valid["top_excess"].astype(float)
        grid_rows.append(
            {
                "signal_id": signal_key,
                "grid_id": grid_key,
                "decision_count": len(metric_group),
                "evaluable_decision_count": len(valid),
                "mean_rank_ic": mean_or_none(ic),
                "median_rank_ic": float(ic.median()) if len(ic) else None,
                "ic_information_ratio": (
                    float(ic.mean() / ic.std(ddof=1))
                    if len(ic) > 1 and float(ic.std(ddof=1)) > 0
                    else None
                ),
                "positive_ic_share": float((ic > 0).mean()) if len(ic) else None,
                "mean_top_excess": mean_or_none(top_excess_values),
            }
        )
    for raw_key, fold_group in decisions.loc[decisions["grid_id"] == "PRIMARY_GRID"].groupby(
        ["signal_id", "fold_id"], sort=True
    ):
        signal_key, fold_key = str(raw_key[0]), str(raw_key[1])
        valid = fold_group.loc[fold_group["evaluable"].astype(bool)]
        fold_rows.append(
            {
                "signal_id": signal_key,
                "fold_id": fold_key,
                "mean_rank_ic": mean_or_none(valid["rank_ic"]),
                "mean_top_excess": mean_or_none(valid["top_excess"]),
            }
        )
    for raw_key, external_group in external_decisions.loc[
        external_decisions["grid_id"] == "PRIMARY_GRID"
    ].groupby(["signal_id", "fold_id"], sort=True):
        signal_key, fold_key = str(raw_key[0]), str(raw_key[1])
        valid = external_group.loc[external_group["evaluable"].astype(bool)]
        external_fold_rows.append(
            {
                "signal_id": signal_key,
                "fold_id": fold_key,
                "mean_rank_ic": mean_or_none(valid["rank_ic"]),
                "mean_top_excess": mean_or_none(valid["top_excess"]),
            }
        )
    grid_metrics = pd.DataFrame(grid_rows)
    fold_metrics = pd.DataFrame(fold_rows)
    external_folds = pd.DataFrame(external_fold_rows)
    primary = decisions.loc[decisions["grid_id"] == "PRIMARY_GRID"]
    external_primary = external_decisions.loc[external_decisions["grid_id"] == "PRIMARY_GRID"]
    protocol = (REPORTS / "ams-rd07-protocol-registration-v1.json").read_bytes()
    seed = int.from_bytes(hashlib.sha256(protocol).digest()[:8], "big")
    p7: dict[str, float] = {}
    p28: dict[str, float] = {}
    ess_rows: list[dict[str, object]] = []
    for index, signal in enumerate(SIGNAL_IDS):
        bootstrap_values = primary.loc[
            (primary["signal_id"] == signal) & primary["evaluable"].astype(bool),
            "rank_ic",
        ].to_numpy(dtype=float)
        p7[signal] = moving_block_p_value(bootstrap_values, seed=seed + index, block_length=7)
        p28[signal] = moving_block_p_value(bootstrap_values, seed=seed + index, block_length=28)
        ess_rows.append({"signal_id": signal, **effective_sample_size(bootstrap_values)})
    adjusted7 = benjamini_hochberg(p7)
    adjusted28 = benjamini_hochberg(p28)
    bootstrap_rows = [
        {
            "signal_id": signal,
            "raw_p_7d": p7[signal],
            "bh_adjusted_p_7d": adjusted7[signal],
            "raw_p_28d": p28[signal],
            "bh_adjusted_p_28d": adjusted28[signal],
        }
        for signal in SIGNAL_IDS
    ]
    regime_rows: list[dict[str, object]] = []
    regime_source = panel[["decision_time", *REGIME_IDS]].drop_duplicates()
    for signal in SIGNAL_IDS:
        signal_primary = primary.loc[primary["signal_id"] == signal]
        for regime in REGIME_IDS:
            joined = signal_primary.merge(
                regime_source[["decision_time", regime]], on="decision_time", how="left"
            )
            for state, regime_group in joined.groupby(regime, sort=True):
                regime_values = regime_group.loc[
                    regime_group["evaluable"].astype(bool), "rank_ic"
                ].astype(float)
                regime_rows.append(
                    {
                        "signal_id": signal,
                        "regime_id": regime,
                        "state": state,
                        "decision_count": len(regime_values),
                        "mean_rank_ic": mean_or_none(regime_values),
                        "evaluable": len(regime_values) >= 10,
                        "positive": (len(regime_values) >= 10 and float(regime_values.mean()) > 0),
                    }
                )
    regime_frame = pd.DataFrame(regime_rows)
    turnover_rows: list[dict[str, object]] = []
    ledger_rows: list[dict[str, object]] = []
    concentration_rows: list[dict[str, object]] = []
    for signal in SIGNAL_IDS:
        metric_row = grid_metrics.loc[
            (grid_metrics["signal_id"] == signal) & (grid_metrics["grid_id"] == "PRIMARY_GRID")
        ].iloc[0]
        folds = fold_metrics.loc[fold_metrics["signal_id"] == signal]
        grids = grid_metrics.loc[grid_metrics["signal_id"] == signal]
        ext = external_primary.loc[
            (external_primary["signal_id"] == signal) & external_primary["evaluable"].astype(bool)
        ]
        ext_folds = external_folds.loc[external_folds["signal_id"] == signal]
        contribution_values = contribution[signal]
        denominator = sum(abs(value) for value in contribution_values.values())
        concentration = (
            max((abs(value) for value in contribution_values.values()), default=0.0) / denominator
            if denominator > 0
            else 1.0
        )
        for symbol, value in contribution_values.items():
            concentration_rows.append(
                {
                    "signal_id": signal,
                    "symbol": symbol,
                    "aggregate_contribution": value,
                }
            )
        signal_available = panel[signal].notna()
        missing_share = float((signal_available & panel[PRIMARY].isna()).sum()) / max(
            1, int(signal_available.sum())
        )
        positive_regimes = int(
            regime_frame.loc[
                (regime_frame["signal_id"] == signal)
                & regime_frame["evaluable"].astype(bool)
                & regime_frame["positive"].astype(bool)
            ].shape[0]
        )
        signal_primary = primary.loc[
            (primary["signal_id"] == signal) & primary["evaluable"].astype(bool)
        ].sort_values("decision_time")
        previous: dict[str, float] = {}
        turnovers: list[float] = []
        costs: list[float] = []
        gross: list[float] = []
        retention: list[float] = []
        for row in signal_primary.itertuples(index=False):
            symbols = str(row.top_symbols).split("|")
            current = {symbol: 1.0 / len(symbols) for symbol in symbols}
            union = set(previous) | set(current)
            turnover = 0.5 * sum(
                abs(current.get(symbol, 0.0) - previous.get(symbol, 0.0)) for symbol in union
            )
            turnovers.append(turnover)
            costs.append(turnover * 0.002)
            gross.append(required_float(row.top_excess))
            retention.append(len(set(previous) & set(current)) / len(current) if previous else 0)
            previous = current
        net = float(np.mean(np.asarray(gross) - np.asarray(costs)))
        turnover_rows.append(
            {
                "signal_id": signal,
                "mean_one_way_turnover": float(np.mean(turnovers)),
                "median_turnover": float(np.median(turnovers)),
                "mean_gross_top_excess": float(np.mean(gross)),
                "mean_cost_proxy": float(np.mean(costs)),
                "mean_net_top_excess_proxy": net,
                "retention_share": float(np.mean(retention)),
            }
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
            "concentration": concentration <= 0.25,
            "missing": missing_share <= 0.05,
            "bh": adjusted7[signal] <= 0.05,
            "regime": positive_regimes >= 2,
            "external_ic": float(ext["rank_ic"].mean()) > 0,
            "external_top": float(ext["top_excess"].mean()) > 0,
            "external_fold_ic": int((ext_folds["mean_rank_ic"] > 0).sum()) >= 2,
            "economic_proxy": net > 0,
        }
        failed = [name for name, passed in gates.items() if not passed]
        all_passed = not failed
        ledger_rows.append(
            {
                "signal_id": signal,
                "signal_class": (
                    "POST_HOC_EXTERNAL_REPLICATION" if signal == POST_HOC else "CONFIRMATORY"
                ),
                "mean_rank_ic": metric_row["mean_rank_ic"],
                "ic_information_ratio": metric_row["ic_information_ratio"],
                "positive_ic_share": metric_row["positive_ic_share"],
                "mean_top_excess": metric_row["mean_top_excess"],
                "bh_adjusted_p_value": adjusted7[signal],
                "maximum_symbol_contribution_share": concentration,
                "missing_primary_label_share": missing_share,
                "positive_regime_cells": positive_regimes,
                "external_mean_rank_ic": mean_or_none(ext["rank_ic"]),
                "external_mean_top_excess": mean_or_none(ext["top_excess"]),
                "mean_net_top_excess_proxy": net,
                "failed_gate_count": len(failed),
                "failed_gate_ids": "|".join(failed),
                "confirmed": all_passed and signal != POST_HOC,
                "external_replication_candidate": all_passed and signal == POST_HOC,
            }
        )
    age_rows: list[dict[str, object]] = []
    for label in (PRIMARY, EXTERNAL, "FORWARD_72H_RETURN", "FORWARD_7D_RETURN"):
        age_values: list[float] = []
        for _, group in panel.loc[panel["grid_id"] == "PRIMARY_GRID"].groupby("decision_time"):
            age_metric = decision_metric(group, "BINANCE_AGE_OR_TENURE", label)
            if bool(age_metric["evaluable"]):
                age_values.append(required_float(age_metric["rank_ic"]))
        age_rows.append(
            {
                "label_id": label,
                "mean_rank_ic": float(np.mean(age_values)) if age_values else None,
                "decision_count": len(age_values),
                "trial": False,
            }
        )
    confirmed = [str(row["signal_id"]) for row in ledger_rows if bool(row["confirmed"])]
    candidates = [
        str(row["signal_id"]) for row in ledger_rows if bool(row["external_replication_candidate"])
    ]
    outputs = {
        "ams-rd07-signal-ledger-v1.csv": pd.DataFrame(ledger_rows),
        "ams-rd07-decision-time-metrics-v1.csv": decisions,
        "ams-rd07-grid-metrics-v1.csv": grid_metrics,
        "ams-rd07-fold-metrics-v1.csv": fold_metrics,
        "ams-rd07-bootstrap-7d-28d-v1.csv": pd.DataFrame(bootstrap_rows),
        "ams-rd07-effective-sample-size-v1.csv": pd.DataFrame(ess_rows),
        "ams-rd07-regime-cell-metrics-v1.csv": regime_frame,
        "ams-rd07-symbol-concentration-v1.csv": pd.DataFrame(concentration_rows),
        "ams-rd07-turnover-cost-proxy-v1.csv": pd.DataFrame(turnover_rows),
        "ams-rd07-external-replication-v1.csv": external_decisions,
        "ams-rd07-binance-age-diagnostic-v1.csv": pd.DataFrame(age_rows),
        "ams-rd07-gate-ledger-v1.csv": pd.DataFrame(ledger_rows),
    }
    for name, frame in outputs.items():
        frame.to_csv(REPORTS / name, index=False)
    decision_name = (
        "RD07_CROSS_VENUE_SPOT_FLOW_CANDIDATES_IDENTIFIED"
        if confirmed
        else "RD07_CROSS_VENUE_SPOT_FLOW_EDGE_NOT_CONFIRMED"
    )
    report = {
        "stage": "RD07-CROSS-VENUE-SPOT-FLOW-SIGNAL-DIAGNOSTIC",
        "status": "COMPLETE",
        "decision": decision_name,
        "confirmed_signal_count": len(confirmed),
        "confirmed_signal_ids": confirmed,
        "external_replication_candidate_ids": candidates,
        "next_stage": (
            "RD07-S2-INDEPENDENT-REPLICATION"
            if confirmed
            else "RD07_TERMINATION_OR_NEW_INFORMATION_SOURCE"
        ),
        "portfolio_construction_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    (REPORTS / "ams-rd07-signal-diagnostic-v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (REPORTS / "ams-rd07-signal-diagnostic-v1.md").write_text(
        "# RD07 Signal Diagnostic\n\n"
        f"- Decision: `{decision_name}`\n"
        f"- Confirmed signals: `{len(confirmed)}`\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
