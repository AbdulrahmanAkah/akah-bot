"""Run the post-hoc RD07A age/quality mechanism diagnostic."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd05_primitive_signal_diagnostic import safe_spearman
from spotbot.research.rd07a_age_quality_diagnostic import (
    fit_residual_model,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
FACTORS = (
    "AGE_OR_TENURE",
    "LOW_REALIZED_VOLATILITY_42",
    "DRAWDOWN_RESILIENCE_42",
    "LOG_MEDIAN_QUOTE_TURNOVER_42",
    "QUOTE_TURNOVER_STABILITY_42",
)
LABELS = (
    "FORWARD_24H_RETURN",
    "FORWARD_72H_RETURN",
    "FORWARD_7D_RETURN",
    "FORWARD_24H_MFE",
    "FORWARD_24H_MAE",
)


def write_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    write_text(path, buffer.getvalue())


def rank_center(frame: pd.DataFrame, column: str) -> pd.Series:
    ranks = frame.groupby("decision_time")[column].rank(pct=True, method="average")
    return ranks - ranks.groupby(frame["decision_time"]).transform("mean")


def mean_decision_ic(frame: pd.DataFrame, factor: str, label: str) -> float:
    values: list[float] = []
    for _, group in frame.groupby("decision_time", sort=True):
        matched = group[[factor, label]].dropna()
        correlation, _ = safe_spearman(
            matched[factor].to_numpy(dtype=float),
            matched[label].to_numpy(dtype=float),
        )
        if correlation is not None:
            values.append(correlation)
    return float(np.mean(values)) if values else float("nan")


def main() -> None:
    final = json.loads(
        (REPORTS / "ams-rd06-final-adjudication-v1.json").read_text(encoding="utf-8")
    )
    if final["next_stage"] != "RD07_CROSS_VENUE_SPOT_DATA_PROTOCOL":
        raise RuntimeError("RD07A is not authorized")
    features = pd.read_parquet(REPORTS / "ams-rd06-p1-feature-panel-v1.parquet")
    labels = pd.read_parquet(REPORTS / "ams-rd06-p1-label-panel-v1.parquet")
    panel = features.merge(labels, on=["decision_time", "symbol"], validate="one_to_one")
    panel = panel.loc[panel["grid_id"] == "PRIMARY_GRID"].copy()
    quote = pd.read_parquet(
        ROOT / "data/research/rd04/kucoin-native-quote-turnover-v1/"
        "ams-rd04-d5a-native-quote-turnover-4h.parquet"
    )
    quote["symbol"] = quote["venue_pair"].str.removesuffix("-USDT")
    quote = quote.sort_values(["symbol", "bar_close_time"])
    grouped = quote.groupby("symbol", sort=False)["quote_turnover_usdt"]
    quote["LOG_MEDIAN_QUOTE_TURNOVER_42"] = np.log1p(
        grouped.transform(lambda value: value.rolling(42, min_periods=42).median())
    )
    quote["QUOTE_TURNOVER_STABILITY_42"] = -grouped.transform(
        lambda value: np.log1p(value).rolling(42, min_periods=42).std(ddof=1)
    )
    panel = panel.merge(
        quote[
            [
                "symbol",
                "bar_close_time",
                "LOG_MEDIAN_QUOTE_TURNOVER_42",
                "QUOTE_TURNOVER_STABILITY_42",
            ]
        ],
        left_on=["symbol", "decision_time"],
        right_on=["symbol", "bar_close_time"],
        how="left",
        validate="one_to_one",
    )
    correlation_rows: list[dict[str, object]] = []
    for left_index, left in enumerate(FACTORS):
        for right in FACTORS[left_index + 1 :]:
            correlations: list[float] = []
            for _, group in panel.groupby("decision_time", sort=True):
                matched = group[[left, right]].dropna()
                value, _ = safe_spearman(
                    matched[left].to_numpy(dtype=float),
                    matched[right].to_numpy(dtype=float),
                )
                if value is not None:
                    correlations.append(value)
            correlation_rows.append(
                {
                    "left_factor": left,
                    "right_factor": right,
                    "decision_count": len(correlations),
                    "mean_correlation": float(np.mean(correlations)),
                    "median_correlation": float(np.median(correlations)),
                }
            )
    outcome_rows: list[dict[str, object]] = []
    for factor in FACTORS:
        for label in LABELS:
            outcome_rows.append(
                {
                    "factor": factor,
                    "label": label,
                    "mean_rank_ic": mean_decision_ic(panel, factor, label),
                }
            )
    folds = (
        ("WF01", "2022-01-03", "2022-12-25", "2023-01-02", "2023-06-30"),
        ("WF02", "2022-01-03", "2023-06-25", "2023-07-03", "2023-12-31"),
        ("WF03", "2022-01-03", "2023-12-24", "2024-01-01", "2024-12-31"),
    )
    residual_rows: list[dict[str, object]] = []
    residual_validation: list[pd.DataFrame] = []
    residual_ics: list[float] = []
    for fold_id, train_start, train_end, valid_start, valid_end in folds:
        train = panel.loc[
            panel["decision_time"].between(
                pd.Timestamp(train_start, tz="UTC"), pd.Timestamp(train_end, tz="UTC")
            )
        ].copy()
        validation = panel.loc[
            panel["decision_time"].between(
                pd.Timestamp(valid_start, tz="UTC"), pd.Timestamp(valid_end, tz="UTC")
            )
        ].copy()
        for frame in (train, validation):
            frame["AGE_RANK"] = rank_center(frame, "AGE_OR_TENURE")
            for name in (
                "LOW_REALIZED_VOLATILITY_42",
                "DRAWDOWN_RESILIENCE_42",
                "LOG_MEDIAN_QUOTE_TURNOVER_42",
            ):
                frame[f"{name}_RANK"] = rank_center(frame, name)
        controls = [
            "LOW_REALIZED_VOLATILITY_42_RANK",
            "DRAWDOWN_RESILIENCE_42_RANK",
            "LOG_MEDIAN_QUOTE_TURNOVER_42_RANK",
        ]
        clean_train = train.dropna(subset=["AGE_RANK", *controls])
        model = fit_residual_model(
            clean_train["AGE_RANK"].to_numpy(dtype=float),
            clean_train[controls].to_numpy(dtype=float),
        )
        clean_validation = validation.dropna(
            subset=["AGE_RANK", *controls, "FORWARD_24H_RETURN"]
        ).copy()
        clean_validation["RESIDUAL_AGE"] = model.apply(
            clean_validation["AGE_RANK"].to_numpy(dtype=float),
            clean_validation[controls].to_numpy(dtype=float),
        )
        residual_ic = mean_decision_ic(clean_validation, "RESIDUAL_AGE", "FORWARD_24H_RETURN")
        residual_rows.append(
            {
                "fold_id": fold_id,
                "residual_age_mean_ic": residual_ic,
                "validation_rows": len(clean_validation),
                "coefficient_low_vol": model.coefficients[0],
                "coefficient_drawdown": model.coefficients[1],
                "coefficient_log_turnover": model.coefficients[2],
            }
        )
        residual_ics.append(residual_ic)
        clean_validation["fold_id"] = fold_id
        residual_validation.append(clean_validation)
    combined = pd.concat(residual_validation, ignore_index=True)
    loo_rows: list[dict[str, object]] = []
    for symbol in sorted(combined["symbol"].astype(str).unique()):
        selected = combined.loc[combined["symbol"] != symbol]
        loo_rows.append(
            {
                "excluded_symbol": symbol,
                "residual_age_mean_ic": mean_decision_ic(
                    selected, "RESIDUAL_AGE", "FORWARD_24H_RETURN"
                ),
            }
        )
    worst_case = combined.loc[~combined["symbol"].isin(["AAVE", "BCH"])]
    worst_rows = [
        {
            "excluded_symbols": "AAVE|BCH",
            "classification": "POST_HOC_WORST_CASE_INFLUENCE_DIAGNOSTIC",
            "residual_age_mean_ic": mean_decision_ic(
                worst_case, "RESIDUAL_AGE", "FORWARD_24H_RETURN"
            ),
            "remaining_rows": len(worst_case),
        }
    ]
    mean_residual = float(np.mean(residual_ics))
    positive_folds = sum(value > 0 for value in residual_ics)
    contributions = combined.groupby("symbol")["RESIDUAL_AGE"].sum().abs()
    concentration = float(contributions.max() / contributions.sum())
    if concentration > 0.25:
        decision = "AGE_EFFECT_SYMBOL_CONCENTRATED"
    elif mean_residual >= 0.02 and positive_folds >= 2:
        decision = "AGE_RETAINS_INCREMENTAL_CONTENT_AFTER_CONTROLS"
    else:
        decision = "AGE_EFFECT_ABSORBED_BY_QUALITY_CONTROLS"
    write_csv(REPORTS / "ams-rd07a-age-quality-correlations-v1.csv", correlation_rows)
    write_csv(REPORTS / "ams-rd07a-age-quality-outcomes-v1.csv", outcome_rows)
    write_csv(REPORTS / "ams-rd07a-age-residualized-folds-v1.csv", residual_rows)
    write_csv(REPORTS / "ams-rd07a-age-leave-one-out-v1.csv", loo_rows)
    write_csv(REPORTS / "ams-rd07a-age-aave-bch-sensitivity-v1.csv", worst_rows)
    payload: dict[str, object] = {
        "stage": "RD07A-AGE-LOWVOL-QUALITY-MECHANISM-DIAGNOSTIC",
        "status": "COMPLETE",
        "decision": decision,
        "mean_residual_age_ic": mean_residual,
        "positive_fold_count": positive_folds,
        "symbol_concentration": concentration,
        "confirmed_alpha": False,
        "portfolio_construction_authorized": False,
        "next_stage": "RD07_CROSS_VENUE_SPOT_DATA_PROTOCOL",
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    report_path = REPORTS / "ams-rd07a-age-quality-mechanism-v1.json"
    write_text(report_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_text(
        REPORTS / "ams-rd07a-age-quality-mechanism-v1.md",
        f"# RD07A Age Quality Mechanism\n\nDecision: `{decision}`\n",
    )
    manifest_rows = [
        {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }
        for path in (
            report_path,
            REPORTS / "ams-rd07a-age-quality-correlations-v1.csv",
            REPORTS / "ams-rd07a-age-residualized-folds-v1.csv",
        )
    ]
    write_csv(REPORTS / "ams-rd07a-evidence-manifest-v1.csv", manifest_rows)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
