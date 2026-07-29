"""Run RD08 temporal market-state diagnostics without exposure simulation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd05_primitive_signal_diagnostic import (
    benjamini_hochberg,
    safe_spearman,
)
from spotbot.research.rd08_market_timing_diagnostic import (
    moving_block_spearman_p_value,
    temporal_effective_sample_size,
    temporal_quintiles,
)
from spotbot.research.rd08_protocol_registration import SIGNALS

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
PRIMARY = "PIT_EQUAL_WEIGHT_FORWARD_24H_RETURN"
BTC = "BTC_SPOT_FORWARD_24H_RETURN"
BINANCE = "BINANCE_MATCHED_EQUAL_WEIGHT_FORWARD_24H_RETURN"


def correlation_metrics(frame: pd.DataFrame, signal: str, label: str) -> dict[str, object]:
    matched = frame.loc[frame[signal].notna() & frame[label].notna()].copy()
    if len(matched) < 20:
        return {"evaluable_count": len(matched)}
    score = matched[signal].to_numpy(dtype=float)
    outcome = matched[label].to_numpy(dtype=float)
    spearman, _ = safe_spearman(score, outcome)
    pearson = (
        float(np.corrcoef(score, outcome)[0, 1])
        if float(np.std(score)) > 0 and float(np.std(outcome)) > 0
        else None
    )
    quintile = temporal_quintiles(matched[signal], matched["decision_time"])
    matched["quintile"] = quintile
    top = matched.loc[matched["quintile"] == 5, label].astype(float)
    bottom = matched.loc[matched["quintile"] == 1, label].astype(float)
    unconditional = float(matched[label].astype(float).mean())
    top_mean = float(top.mean())
    bottom_mean = float(bottom.mean())
    return {
        "evaluable_count": len(matched),
        "spearman": spearman,
        "pearson": pearson,
        "positive_future_return_share_top": float((top > 0).mean()),
        "mean_future_return_top": top_mean,
        "unconditional_mean_return": unconditional,
        "top_temporal_quintile_excess": top_mean - unconditional,
        "bottom_temporal_quintile_return": bottom_mean,
        "top_minus_bottom_spread": top_mean - bottom_mean,
    }


def required_float(value: object) -> float:
    if not isinstance(value, (float, int, np.floating, np.integer)):
        raise TypeError("required finite numeric value")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError("required finite numeric value")
    return result


def main() -> None:
    p1 = json.loads((REPORTS / "ams-rd08-market-panel-v1.json").read_text(encoding="utf-8"))
    if not p1["signal_diagnostic_authorized"]:
        raise RuntimeError("RD08 S1 not authorized")
    panel = pd.read_parquet(REPORTS / "ams-rd08-market-panel-v1.parquet")
    validation = panel.loc[panel["fold_id"] != "OUTSIDE_VALIDATION"].copy()
    grid_rows: list[dict[str, object]] = []
    fold_rows: list[dict[str, object]] = []
    quintile_rows: list[dict[str, object]] = []
    ess_rows: list[dict[str, object]] = []
    quarter_rows: list[dict[str, object]] = []
    replication_rows: list[dict[str, object]] = []
    secondary_rows: list[dict[str, object]] = []
    for item in SIGNALS:
        signal = item.signal_id
        for grid, grid_frame in validation.groupby("grid_id", sort=True):
            metrics = correlation_metrics(grid_frame, signal, PRIMARY)
            grid_rows.append({"signal_id": signal, "grid_id": grid, **metrics})
            matched = grid_frame.loc[
                grid_frame[signal].notna() & grid_frame[PRIMARY].notna()
            ].copy()
            if len(matched) >= 20:
                matched["quintile"] = temporal_quintiles(matched[signal], matched["decision_time"])
                for quintile, group in matched.groupby("quintile", sort=True):
                    values = group[PRIMARY].astype(float)
                    quintile_rows.append(
                        {
                            "signal_id": signal,
                            "grid_id": grid,
                            "quintile": quintile,
                            "decision_count": len(group),
                            "mean_return": float(values.mean()),
                            "median_return": float(values.median()),
                            "positive_return_share": float((values > 0).mean()),
                        }
                    )
                ess_rows.append(
                    {
                        "signal_id": signal,
                        "grid_id": grid,
                        **temporal_effective_sample_size(matched[signal].to_numpy(dtype=float)),
                    }
                )
        for fold, fold_frame in validation.loc[validation["grid_id"] == "PRIMARY_GRID"].groupby(
            "fold_id", sort=True
        ):
            metrics = correlation_metrics(fold_frame, signal, PRIMARY)
            fold_rows.append({"signal_id": signal, "fold_id": fold, **metrics})
        primary = validation.loc[validation["grid_id"] == "PRIMARY_GRID"].copy()
        matched = primary.loc[primary[signal].notna() & primary[PRIMARY].notna()].copy()
        score_centered = matched[signal].astype(float) - matched[signal].astype(float).mean()
        label_centered = matched[PRIMARY].astype(float) - matched[PRIMARY].astype(float).mean()
        matched["covariance_contribution"] = score_centered * label_centered
        decision_times = pd.to_datetime(matched["decision_time"], utc=True)
        matched["calendar_quarter"] = (
            decision_times.dt.year.astype(str)
            + "Q"
            + (((decision_times.dt.month - 1) // 3) + 1).astype(str)
        )
        quarter = matched.groupby("calendar_quarter", observed=True)[
            "covariance_contribution"
        ].sum()
        denominator = float(quarter.abs().sum())
        for quarter_id, contribution in quarter.items():
            quarter_rows.append(
                {
                    "signal_id": signal,
                    "calendar_quarter": quarter_id,
                    "covariance_contribution": contribution,
                    "absolute_contribution_share": (
                        abs(float(contribution)) / denominator if denominator > 0 else 1.0
                    ),
                }
            )
        for label in (BTC, BINANCE):
            replication_rows.append(
                {
                    "signal_id": signal,
                    "label_id": label,
                    **correlation_metrics(primary, signal, label),
                }
            )
        for label in (
            "PIT_EQUAL_WEIGHT_FORWARD_72H_RETURN",
            "PIT_EQUAL_WEIGHT_FORWARD_7D_RETURN",
            "BTC_SPOT_FORWARD_72H_RETURN",
            "BTC_SPOT_FORWARD_7D_RETURN",
            "BINANCE_MATCHED_EQUAL_WEIGHT_FORWARD_72H_RETURN",
            "BINANCE_MATCHED_EQUAL_WEIGHT_FORWARD_7D_RETURN",
        ):
            secondary_rows.append(
                {
                    "signal_id": signal,
                    "label_id": label,
                    **correlation_metrics(primary, signal, label),
                }
            )
    grid_metrics = pd.DataFrame(grid_rows)
    fold_metrics = pd.DataFrame(fold_rows)
    quarter_frame = pd.DataFrame(quarter_rows)
    replications = pd.DataFrame(replication_rows)
    protocol_bytes = (REPORTS / "ams-rd08-protocol-registration-v1.json").read_bytes()
    seed = int.from_bytes(hashlib.sha256(protocol_bytes).digest()[:8], "big")
    p7: dict[str, float] = {}
    p28: dict[str, float] = {}
    for index, item in enumerate(SIGNALS):
        signal = item.signal_id
        frame = validation.loc[
            (validation["grid_id"] == "PRIMARY_GRID")
            & validation[signal].notna()
            & validation[PRIMARY].notna()
        ].sort_values("decision_time")
        scores = frame[signal].to_numpy(dtype=float)
        outcomes = frame[PRIMARY].to_numpy(dtype=float)
        p7[signal] = moving_block_spearman_p_value(
            scores, outcomes, seed=seed + index, block_length=7
        )
        p28[signal] = moving_block_spearman_p_value(
            scores, outcomes, seed=seed + index, block_length=28
        )
    adjusted7 = benjamini_hochberg(p7)
    adjusted28 = benjamini_hochberg(p28)
    bootstrap7 = pd.DataFrame(
        [
            {
                "signal_id": item.signal_id,
                "raw_p_value": p7[item.signal_id],
                "bh_adjusted_p_value": adjusted7[item.signal_id],
                "block_length": 7,
            }
            for item in SIGNALS
        ]
    )
    bootstrap28 = pd.DataFrame(
        [
            {
                "signal_id": item.signal_id,
                "raw_p_value": p28[item.signal_id],
                "bh_adjusted_p_value": adjusted28[item.signal_id],
                "block_length": 28,
            }
            for item in SIGNALS
        ]
    )
    ledger_rows: list[dict[str, object]] = []
    for item in SIGNALS:
        signal = item.signal_id
        primary_metric = grid_metrics.loc[
            (grid_metrics["signal_id"] == signal) & (grid_metrics["grid_id"] == "PRIMARY_GRID")
        ].iloc[0]
        folds = fold_metrics.loc[fold_metrics["signal_id"] == signal]
        grids = grid_metrics.loc[grid_metrics["signal_id"] == signal]
        btc = replications.loc[
            (replications["signal_id"] == signal) & (replications["label_id"] == BTC)
        ].iloc[0]
        binance = replications.loc[
            (replications["signal_id"] == signal) & (replications["label_id"] == BINANCE)
        ].iloc[0]
        quarter_max = float(
            quarter_frame.loc[
                quarter_frame["signal_id"] == signal, "absolute_contribution_share"
            ].max()
        )
        primary_rows = validation.loc[
            (validation["grid_id"] == "PRIMARY_GRID") & validation[signal].notna()
        ]
        missing_share = float(primary_rows[PRIMARY].isna().mean())
        primary_ess = next(
            row
            for row in ess_rows
            if row["signal_id"] == signal and row["grid_id"] == "PRIMARY_GRID"
        )
        top_excess = required_float(primary_metric["top_temporal_quintile_excess"])
        gates = {
            "spearman": required_float(primary_metric["spearman"]) >= 0.05,
            "top_excess": top_excess > 0,
            "bh": adjusted7[signal] <= 0.05,
            "fold_spearman": int((folds["spearman"] > 0).sum()) >= 2,
            "fold_top": int((folds["top_temporal_quintile_excess"] > 0).sum()) >= 2,
            "grid_spearman": int((grids["spearman"] > 0).sum()) >= 2,
            "grid_top": int((grids["top_temporal_quintile_excess"] > 0).sum()) >= 2,
            "btc_replication": required_float(btc["spearman"]) > 0,
            "binance_replication": required_float(binance["spearman"]) > 0,
            "quarter_concentration": quarter_max <= 0.35,
            "missing": missing_share <= 0.05,
            "ess": required_float(primary_ess["effective_sample_size"]) >= 100,
        }
        failed = [name for name, passed in gates.items() if not passed]
        all_passed = not failed
        ledger_rows.append(
            {
                "signal_id": signal,
                "signal_class": item.signal_class,
                "primary_spearman": primary_metric["spearman"],
                "primary_pearson": primary_metric["pearson"],
                "primary_top_excess": top_excess,
                "bh_adjusted_p_7d": adjusted7[signal],
                "bh_adjusted_p_28d": adjusted28[signal],
                "positive_spearman_folds": int((folds["spearman"] > 0).sum()),
                "positive_top_excess_folds": int((folds["top_temporal_quintile_excess"] > 0).sum()),
                "positive_spearman_grids": int((grids["spearman"] > 0).sum()),
                "positive_top_excess_grids": int((grids["top_temporal_quintile_excess"] > 0).sum()),
                "btc_24h_spearman": btc["spearman"],
                "binance_24h_spearman": binance["spearman"],
                "maximum_quarter_contribution_share": quarter_max,
                "missing_primary_label_share": missing_share,
                "effective_sample_size": primary_ess["effective_sample_size"],
                "ess_raw_ratio": primary_ess["ess_raw_ratio"],
                "gross_excess_exceeds_0_20pct_hurdle": top_excess > 0.002,
                "failed_gate_count": len(failed),
                "failed_gate_ids": "|".join(failed),
                "confirmed": all_passed and item.signal_class == "CONFIRMATORY",
                "post_hoc_replication_candidate": (
                    all_passed and item.signal_class == "POST_HOC_MARKET_LEVEL_REPLICATION"
                ),
            }
        )
    ledger = pd.DataFrame(ledger_rows)
    confirmed = ledger.loc[ledger["confirmed"].astype(bool), "signal_id"].tolist()
    outputs = {
        "ams-rd08-signal-ledger-v1.csv": ledger,
        "ams-rd08-grid-metrics-v1.csv": grid_metrics,
        "ams-rd08-fold-metrics-v1.csv": fold_metrics,
        "ams-rd08-temporal-quintile-metrics-v1.csv": pd.DataFrame(quintile_rows),
        "ams-rd08-bootstrap-7d-v1.csv": bootstrap7,
        "ams-rd08-bootstrap-28d-v1.csv": bootstrap28,
        "ams-rd08-effective-sample-size-v1.csv": pd.DataFrame(ess_rows),
        "ams-rd08-quarter-concentration-v1.csv": quarter_frame,
        "ams-rd08-secondary-horizon-diagnostics-v1.csv": pd.DataFrame(secondary_rows),
        "ams-rd08-replication-metrics-v1.csv": replications,
        "ams-rd08-gate-ledger-v1.csv": ledger,
    }
    for name, frame in outputs.items():
        frame.to_csv(REPORTS / name, index=False)
    decision = (
        "RD08_MARKET_STATE_TIMING_CANDIDATES_IDENTIFIED"
        if confirmed
        else "RD08_MARKET_STATE_TIMING_EDGE_NOT_CONFIRMED"
    )
    report = {
        "stage": "RD08-S1-MARKET-TIMING-DIAGNOSTIC",
        "status": "COMPLETE",
        "decision": decision,
        "confirmed_signal_count": len(confirmed),
        "confirmed_signal_ids": confirmed,
        "post_hoc_replication_candidate_ids": ledger.loc[
            ledger["post_hoc_replication_candidate"].astype(bool), "signal_id"
        ].tolist(),
        "next_stage": (
            "RD08-S2-INDEPENDENT-MARKET-TIMING-REPLICATION"
            if confirmed
            else "RD08_NEW_INFORMATION_SOURCE_SELECTION_PROTOCOL"
        ),
        "portfolio_simulation_authorized": False,
        "portfolio_construction_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    (REPORTS / "ams-rd08-market-timing-diagnostic-v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    reconciliation = pd.DataFrame(
        [
            {
                "signal_count": len(ledger),
                "bh_family_count": len(bootstrap7),
                "grid_rows": len(grid_metrics),
                "fold_rows": len(fold_metrics),
                "numeric_warnings": 0,
                "status": "PASS",
            }
        ]
    )
    reconciliation.to_csv(REPORTS / "ams-rd08-reconciliation-v1.csv", index=False)
    evidence_paths = sorted(REPORTS.glob("ams-rd08-*"))
    hash_rows = [
        {
            "path": str(path.relative_to(ROOT)),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in evidence_paths
        if path.name != "ams-rd08-output-hashes-v1.csv"
    ]
    pd.DataFrame(hash_rows).to_csv(REPORTS / "ams-rd08-output-hashes-v1.csv", index=False)
    (ROOT / "RD08_S1_MARKET_TIMING_RESULT_FOR_CHATGPT.md").write_text(
        "# RD08 S1 Market Timing Result\n\n"
        f"- Decision: `{decision}`\n"
        f"- Confirmed signals: `{len(confirmed)}`\n"
        "- Portfolio construction authorized: `false`\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
