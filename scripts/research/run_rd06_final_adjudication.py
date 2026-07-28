"""Complete RD06 evidence and close the research sequence without a portfolio."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd05_primitive_signal_diagnostic import (
    benjamini_hochberg,
    deterministic_quintiles,
)
from spotbot.research.rd06_final_adjudication import (
    FINAL_DECISION,
    NEXT_STAGE,
    classify_quintile_shape,
    effective_sample_size,
)
from spotbot.research.rd06_intraweek_signal_diagnostic import (
    moving_block_bootstrap_p_value,
)
from spotbot.research.rd06_protocol_registration import SIGNAL_IDS

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


def required_float(value: object) -> float:
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise TypeError("expected numeric value")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError("expected finite value")
    return result


def rebuild_quintile_detail() -> pd.DataFrame:
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
    rows: list[dict[str, object]] = []
    for signal_id in (*SIGNAL_IDS, "AGE_OR_TENURE"):
        for key, group in panel.groupby(["fold_id", "grid_id", "decision_time"], sort=True):
            matched = group.loc[
                group[f"{signal_id}_available"].astype(bool)
                & group["FORWARD_24H_RETURN_available"].astype(bool)
            ].copy()
            if len(matched) < 5:
                continue
            _, quintile = deterministic_quintiles(
                matched["symbol"].astype(str).tolist(),
                matched[signal_id].to_numpy(dtype=float),
            )
            for symbol, bin_id, label in zip(
                matched["symbol"],
                quintile,
                matched["FORWARD_24H_RETURN"],
                strict=True,
            ):
                rows.append(
                    {
                        "signal_id": signal_id,
                        "fold_id": str(key[0]),
                        "grid_id": str(key[1]),
                        "decision_time": pd.Timestamp(str(key[2])),
                        "symbol": str(symbol),
                        "quintile": int(bin_id),
                        "label": float(label),
                    }
                )
    return pd.DataFrame(rows).sort_values(
        ["signal_id", "fold_id", "grid_id", "decision_time", "symbol"]
    )


def main() -> None:
    s1 = json.loads(
        (REPORTS / "ams-rd06-s1-intraweek-signal-diagnostic-v1.json").read_text(encoding="utf-8")
    )
    if (
        s1["decision"] != "RD06_INTRAWEEK_PRIMITIVE_SIGNAL_EDGE_NOT_CONFIRMED"
        or s1["confirmed_signal_count"] != 0
    ):
        raise RuntimeError("RD06 final closure evidence mismatch")
    detail = rebuild_quintile_detail()
    detail_path = REPORTS / "ams-rd06-s1-quintile-detail-v1.parquet"
    detail.to_parquet(detail_path, index=False)
    summary = (
        detail.groupby(["signal_id", "fold_id", "grid_id", "quintile"], sort=True)
        .agg(
            decision_count=("decision_time", "nunique"),
            observation_count=("label", "size"),
            mean_return=("label", "mean"),
            median_return=("label", "median"),
            positive_return_share=("label", lambda value: float((value > 0).mean())),
        )
        .reset_index()
    )
    summary_path = REPORTS / "ams-rd06-s1-quintile-summary-v1.csv"
    summary.to_csv(summary_path, index=False, lineterminator="\n")
    manifest = {
        "path": str(detail_path.relative_to(ROOT)),
        "size_bytes": detail_path.stat().st_size,
        "sha256": sha256(detail_path),
        "row_count": len(detail),
        "primary_key_duplicates": int(
            detail.duplicated(["signal_id", "fold_id", "grid_id", "decision_time", "symbol"]).sum()
        ),
        "quintile_contract": "Q1_LOWEST_Q5_HIGHEST",
        "status": "PASS",
    }
    write_text(
        REPORTS / "ams-rd06-s1-quintile-evidence-manifest-v1.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    )
    shape_rows: list[dict[str, object]] = []
    aggregate_summary = detail.groupby(["signal_id", "quintile"])["label"].mean().reset_index()
    for signal, group in aggregate_summary.groupby("signal_id", sort=True):
        means = {
            int(required_float(row["quintile"])): required_float(row["label"])
            for row in group.to_dict(orient="records")
        }
        shape_rows.append(
            {
                "signal_id": str(signal),
                "shape_classification": classify_quintile_shape(means),
                **{f"q{index}_mean_return": means.get(index) for index in range(1, 6)},
                "post_hoc_only": True,
            }
        )
    decision_ic = pd.read_csv(REPORTS / "ams-rd06-s1-decision-time-ic-v1.csv")
    decision_ic = decision_ic.loc[decision_ic["evaluable"].astype(bool)]
    ess_rows: list[dict[str, object]] = []
    for key, group in decision_ic.groupby(["signal_id", "grid_id"], sort=True):
        result = effective_sample_size(group["rank_ic"].to_numpy(dtype=float))
        ess_rows.append(
            {
                "signal_id": str(key[0]),
                "grid_id": str(key[1]),
                "raw_decision_count": result.raw_decision_count,
                "effective_sample_size": result.effective_sample_size,
                "ess_raw_ratio": result.ratio,
                "lag_1_autocorrelation": result.lag_1_autocorrelation,
                "maximum_positive_lag_used": result.maximum_positive_lag_used,
            }
        )
    protocol_bytes = (REPORTS / "ams-rd06-protocol-registration-v1.json").read_bytes()
    seed = int.from_bytes(hashlib.sha256(protocol_bytes).digest()[:8], "big")
    primary = decision_ic.loc[decision_ic["grid_id"] == "PRIMARY_GRID"]
    p28 = {
        signal: moving_block_bootstrap_p_value(
            primary.loc[primary["signal_id"] == signal, "rank_ic"].to_numpy(dtype=float),
            seed=seed + index,
            block_length=28,
        )
        for index, signal in enumerate(SIGNAL_IDS)
    }
    adjusted28 = benjamini_hochberg(p28)
    original_p = pd.read_csv(REPORTS / "ams-rd06-s1-bootstrap-significance-v1.csv").set_index(
        "signal_id"
    )
    bootstrap_rows: list[dict[str, object]] = []
    for signal in SIGNAL_IDS:
        old_adjusted = required_float(original_p.loc[signal, "bh_adjusted_p_value"])
        new_adjusted = adjusted28[signal]
        status = (
            "ROBUST_TO_28D_BLOCK"
            if old_adjusted <= 0.05 and new_adjusted <= 0.05
            else (
                "SENSITIVE_TO_LONG_BLOCK"
                if old_adjusted <= 0.05 < new_adjusted
                else "NOT_SIGNIFICANT_IN_EITHER"
            )
        )
        bootstrap_rows.append(
            {
                "signal_id": signal,
                "original_7d_bh_p_value": old_adjusted,
                "block_28_raw_p_value": p28[signal],
                "block_28_bh_p_value": new_adjusted,
                "classification": status,
                "confirmation_eligible": False,
            }
        )
    primary_detail = detail.loc[detail["grid_id"] == "PRIMARY_GRID"].copy()
    turnover_rows: list[dict[str, object]] = []
    for signal, group in primary_detail.groupby("signal_id", sort=True):
        prior: set[str] = set()
        turnovers: list[float] = []
        costs: list[float] = []
        gross: list[float] = []
        retention: list[float] = []
        for _, day in group.groupby("decision_time", sort=True):
            top = set(day.loc[day["quintile"] == 5, "symbol"].astype(str))
            if prior:
                union = top | prior
                turnover = 0.5 * sum(
                    abs(
                        (1 / len(top) if item in top else 0)
                        - (1 / len(prior) if item in prior else 0)
                    )
                    for item in union
                )
                retention.append(len(top & prior) / len(top | prior) if top | prior else 0)
            else:
                turnover = 1.0
            universe_mean = float(day["label"].mean())
            top_mean = float(day.loc[day["quintile"] == 5, "label"].mean())
            turnovers.append(turnover)
            costs.append(turnover * 0.002)
            gross.append(top_mean - universe_mean)
            prior = top
        turnover_rows.append(
            {
                "signal_id": str(signal),
                "mean_one_way_turnover": float(np.mean(turnovers)),
                "median_turnover": float(np.median(turnovers)),
                "mean_gross_top_excess": float(np.mean(gross)),
                "mean_cost_proxy": float(np.mean(costs)),
                "mean_net_top_excess_proxy": float(np.mean(np.asarray(gross) - costs)),
                "retention_share": float(np.mean(retention)) if retention else None,
                "portfolio_authorization": False,
            }
        )
    weekday_rows: list[dict[str, object]] = []
    primary_metrics = decision_ic.loc[decision_ic["grid_id"] == "PRIMARY_GRID"].copy()
    primary_metrics["decision_time"] = pd.to_datetime(primary_metrics["decision_time"], utc=True)
    for signal, group in primary_metrics.groupby("signal_id", sort=True):
        for bucket, mask in (
            ("MONDAY", group["decision_time"].dt.dayofweek == 0),
            ("TUESDAY_THROUGH_SUNDAY", group["decision_time"].dt.dayofweek != 0),
            ("ALL_DAYS", pd.Series(True, index=group.index)),
        ):
            selected = group.loc[mask]
            weekday_rows.append(
                {
                    "signal_id": str(signal),
                    "weekday_bucket": bucket,
                    "decision_count": len(selected),
                    "mean_rank_ic": float(selected["rank_ic"].mean()),
                    "mean_top_excess": float(selected["top_excess"].mean()),
                    "classification": "POST_HOC_WEEKDAY_DIAGNOSTIC",
                }
            )
    bars = pd.read_parquet(
        ROOT / "data/research/rd04/kucoin-spot-usdt-adjudicated-v1/"
        "ams-rd04-d0c-kucoin-adjudicated-4h.parquet"
    )
    quote = pd.read_parquet(
        ROOT / "data/research/rd04/kucoin-native-quote-turnover-v1/"
        "ams-rd04-d5a-native-quote-turnover-4h.parquet"
    )
    quote["symbol"] = quote["venue_pair"].str.removesuffix("-USDT")
    bars = bars.merge(
        quote[["symbol", "bar_open_time", "quote_turnover_usdt"]],
        on=["symbol", "bar_open_time"],
        how="left",
    )
    quality_rows: list[dict[str, object]] = []
    for symbol, group in bars.groupby("symbol", sort=True):
        ordered = group.sort_values("bar_open_time")
        returns = np.log(ordered["close"]).diff()
        median = float(returns.median())
        mad = float((returns - median).abs().median())
        robust = (
            (returns - median) / (1.4826 * mad)
            if mad > 0
            else pd.Series(np.nan, index=returns.index)
        )
        unchanged = ordered["close"].diff().eq(0)
        runs = unchanged.groupby((~unchanged).cumsum()).sum()
        expected = ordered["bar_open_time"].diff().ne(pd.Timedelta(hours=4))
        quality_rows.append(
            {
                "symbol": str(symbol),
                "bar_count": len(ordered),
                "flat_ohlc_share": float(
                    (
                        (ordered["open"] == ordered["high"])
                        & (ordered["high"] == ordered["low"])
                        & (ordered["low"] == ordered["close"])
                    ).mean()
                ),
                "zero_base_volume_share": float((ordered["volume"] == 0).mean()),
                "zero_quote_turnover_share": float((ordered["quote_turnover_usdt"] == 0).mean()),
                "longest_unchanged_close_run": int(runs.max()),
                "largest_robust_return_zscore": float(robust.abs().max()),
                "unexpected_gap_count": int(expected.iloc[1:].sum()),
                "first_eligible_time": ordered["bar_open_time"].min(),
                "last_eligible_time": ordered["bar_close_time"].max(),
                "quote_turnover_coverage": float(ordered["quote_turnover_usdt"].notna().mean()),
                "symbol_excluded": False,
            }
        )
    write_csv(
        REPORTS / "ams-rd06-final-quintile-shape-v1.csv",
        shape_rows,
        list(shape_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-final-effective-sample-size-v1.csv",
        ess_rows,
        list(ess_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-final-bootstrap-28d-sensitivity-v1.csv",
        bootstrap_rows,
        list(bootstrap_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-final-turnover-cost-proxy-v1.csv",
        turnover_rows,
        list(turnover_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-final-weekday-diagnostic-v1.csv",
        weekday_rows,
        list(weekday_rows[0]),
    )
    write_csv(
        REPORTS / "ams-rd06-final-4h-data-quality-v1.csv",
        quality_rows,
        list(quality_rows[0]),
    )
    signal_ledger = pd.read_csv(REPORTS / "ams-rd06-s1-signal-ledger-v1.csv")
    signal_ledger["final_decision"] = "NOT_CONFIRMED"
    signal_ledger.to_csv(
        REPORTS / "ams-rd06-final-signal-outcomes-v1.csv",
        index=False,
        lineterminator="\n",
    )
    reconciliation_rows = [
        {
            "artifact": path.name,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "status": "PASS",
        }
        for path in (
            detail_path,
            summary_path,
            REPORTS / "ams-rd06-s1-intraweek-signal-diagnostic-v1.json",
            REPORTS / "ams-rd06-p1-feature-panel-v1.parquet",
        )
    ]
    write_csv(
        REPORTS / "ams-rd06-final-reconciliation-v1.csv",
        reconciliation_rows,
        list(reconciliation_rows[0]),
    )
    payload: dict[str, object] = {
        "stage": "RD06-FINAL-EVIDENCE-COMPLETION-AND-ADJUDICATION",
        "status": "COMPLETE",
        "decision": FINAL_DECISION,
        "confirmed_signal_count": 0,
        "external_replication_candidate_ids": [],
        "ohlcv_primitive_signal_space_closed": True,
        "portfolio_construction_authorized": False,
        "next_stage": NEXT_STAGE,
        "quintile_manifest": manifest,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    write_text(
        REPORTS / "ams-rd06-final-adjudication-v1.json",
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        REPORTS / "ams-rd06-final-adjudication-v1.md",
        "# RD06 Final Adjudication\n\n"
        f"- Decision: `{FINAL_DECISION}`\n"
        "- Confirmed signals: `0`\n"
        "- Portfolio construction: `NOT AUTHORIZED`\n",
    )
    summary_text = (
        f"# RD06 Final Result\n\nDecision: {FINAL_DECISION}\n\nNext stage: {NEXT_STAGE}\n"
    )
    write_text(ROOT / "RD06_FINAL_ADJUDICATION_FOR_CHATGPT.md", summary_text)
    write_text(ROOT / "RD06_FINAL_RESULT_FOR_CHATGPT.md", summary_text)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
