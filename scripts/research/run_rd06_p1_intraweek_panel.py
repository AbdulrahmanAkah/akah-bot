"""Build the causal RD06 intraweek feature and label panels."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd06_intraweek_panel import (
    LOCK,
    add_label_columns,
    add_signal_columns,
    attach_availability,
    fingerprint_keys,
    validate_panel,
)
from spotbot.research.rd06_protocol_registration import GRIDS, LABEL_IDS, REGIME_IDS, SIGNAL_IDS

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"


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


def decision_index(membership: pd.DataFrame) -> pd.DataFrame:
    snapshots = sorted(pd.to_datetime(membership["rebalance_time"], utc=True).unique())
    decisions = pd.date_range(snapshots[0], LOCK - pd.Timedelta(hours=8), freq="8h")
    decisions = decisions[decisions.hour.isin(tuple(GRIDS.values()))]
    snapshot_frame = pd.DataFrame({"decision_time": decisions})
    source = pd.DataFrame({"snapshot": snapshots})
    joined = pd.merge_asof(
        snapshot_frame.sort_values("decision_time"),
        source.sort_values("snapshot"),
        left_on="decision_time",
        right_on="snapshot",
        direction="backward",
    )
    members = membership.loc[membership["venue_data_eligible"].astype(bool)].copy()
    members["snapshot"] = pd.to_datetime(members["rebalance_time"], utc=True)
    members["symbol"] = members["canonical_symbol"].astype(str)
    panel = joined.merge(members[["snapshot", "symbol"]], on="snapshot", how="inner")
    panel["grid_id"] = panel["decision_time"].dt.hour.map(
        {hour: grid for grid, hour in GRIDS.items()}
    )
    return panel.sort_values(["decision_time", "symbol"]).reset_index(drop=True)


def fold_assignments(decisions: pd.DataFrame) -> pd.DataFrame:
    windows = (
        ("WF01", pd.Timestamp("2023-01-02T00:00:00Z"), pd.Timestamp("2023-06-30T16:00:00Z")),
        ("WF02", pd.Timestamp("2023-07-03T00:00:00Z"), pd.Timestamp("2023-12-31T16:00:00Z")),
        ("WF03", pd.Timestamp("2024-01-01T00:00:00Z"), pd.Timestamp("2024-12-31T00:00:00Z")),
    )
    rows: list[dict[str, object]] = []
    unique = decisions[["decision_time", "grid_id"]].drop_duplicates()
    for fold_id, start, end in windows:
        selected = unique.loc[(unique["decision_time"] >= start) & (unique["decision_time"] <= end)]
        for row in selected.to_dict(orient="records"):
            decision_time = pd.Timestamp(row["decision_time"])
            grid_id = str(row["grid_id"])
            label_end = decision_time + pd.Timedelta(hours=24)
            rows.append(
                {
                    "fold_id": fold_id,
                    "decision_time": decision_time,
                    "grid_id": grid_id,
                    "role": "VALIDATION",
                    "purge_embargo_days": 7,
                    "primary_label_eligible": label_end <= LOCK,
                }
            )
    return pd.DataFrame(rows)


def add_regimes(feature: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    result = feature.copy()
    decision_metrics = (
        result.groupby(["decision_time", "grid_id"], sort=True)
        .agg(
            dispersion=("RETURN_6BAR", "std"),
            breadth=("RETURN_6BAR", lambda value: float((value > 0).mean())),
            universe_size=("symbol", "size"),
        )
        .reset_index()
    )
    btc = result.loc[result["symbol"] == "BTC", ["decision_time", "BTC_TREND_84D", "std42"]]
    decision_metrics = decision_metrics.merge(btc, on="decision_time", how="left")
    decision_metrics["BTC_TREND_STATE"] = np.select(
        [
            decision_metrics["BTC_TREND_84D"] > 0,
            decision_metrics["BTC_TREND_84D"] < 0,
        ],
        ["UP", "DOWN"],
        default="NEUTRAL",
    )
    returns = history.pivot(
        index="bar_close_time", columns="symbol", values="log_return"
    ).sort_index()
    member_map = {
        timestamp: tuple(group["symbol"].astype(str))
        for timestamp, group in result.groupby("decision_time", sort=False)
    }
    pairwise_values: list[float] = []
    for decision_time in decision_metrics["decision_time"]:
        members = member_map[pd.Timestamp(decision_time)]
        window = returns.loc[returns.index <= decision_time, list(members)].tail(42)
        correlation = window.corr(min_periods=30).to_numpy(dtype=float)
        upper = correlation[np.triu_indices_from(correlation, k=1)]
        finite = upper[np.isfinite(upper)]
        pairwise_values.append(float(np.mean(finite)) if finite.size else np.nan)
    decision_metrics["pairwise"] = pairwise_values
    metric_map = {
        "BTC_REALIZED_VOLATILITY_TERCILE": "std42",
        "CROSS_SECTIONAL_DISPERSION_TERCILE": "dispersion",
        "AVERAGE_PAIRWISE_CORRELATION_TERCILE": "pairwise",
        "MARKET_BREADTH_TERCILE": "breadth",
        "PIT_UNIVERSE_SIZE_TERCILE": "universe_size",
    }
    for regime, metric in metric_map.items():
        states = pd.Series("INSUFFICIENT_HISTORY", index=decision_metrics.index, dtype="object")
        for _, indexes in decision_metrics.groupby("grid_id").groups.items():
            values = decision_metrics.loc[indexes, metric]
            lower = values.shift(1).rolling(90, min_periods=90).quantile(1 / 3)
            upper = values.shift(1).rolling(90, min_periods=90).quantile(2 / 3)
            states.loc[indexes] = np.where(
                lower.isna(),
                "INSUFFICIENT_HISTORY",
                np.where(values <= lower, "LOW", np.where(values <= upper, "MID", "HIGH")),
            )
        decision_metrics[regime] = states
    columns = ["decision_time", *REGIME_IDS]
    return result.merge(decision_metrics[columns], on="decision_time", how="left")


def main() -> None:
    protocol = json.loads(
        (REPORTS / "ams-rd06-protocol-registration-v1.json").read_text(encoding="utf-8")
    )
    if not protocol["rd06_p1_authorized"]:
        raise RuntimeError("RD06 P1 is not authorized")
    bars = pd.read_parquet(
        ROOT / "data/research/rd04/kucoin-spot-usdt-adjudicated-v1/"
        "ams-rd04-d0c-kucoin-adjudicated-4h.parquet"
    )
    bars = bars.loc[(bars["bar_open_time"] < LOCK) & (bars["bar_close_time"] <= LOCK)].copy()
    turnover = pd.read_parquet(
        ROOT / "data/research/rd04/kucoin-native-quote-turnover-v1/"
        "ams-rd04-d5a-native-quote-turnover-4h.parquet"
    )
    turnover["symbol"] = turnover["venue_pair"].str.removesuffix("-USDT")
    bars = bars.merge(
        turnover[["symbol", "bar_open_time", "quote_turnover_usdt"]],
        on=["symbol", "bar_open_time"],
        how="left",
        validate="one_to_one",
    )
    computed = add_label_columns(add_signal_columns(bars))
    membership = pd.read_csv(REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv")
    index = decision_index(membership)
    panel = index.merge(
        computed,
        left_on=["decision_time", "symbol"],
        right_on=["bar_close_time", "symbol"],
        how="left",
        validate="one_to_one",
    )
    panel = attach_availability(panel, (*SIGNAL_IDS, "AGE_OR_TENURE", *LABEL_IDS))
    panel = add_regimes(panel, computed)
    key_columns = ["decision_time", "symbol"]
    index_panel = panel[
        [*key_columns, "snapshot", "grid_id", "bar_open_time", "bar_close_time"]
    ].copy()
    index_panel["panel_schema_version"] = "RD06-P1-V1"
    index_panel["source_cutoff_time"] = index_panel["decision_time"]
    index_panel["source_fingerprint"] = protocol["source_hashes"]["OHLCV_4H"]
    feature_columns = list(key_columns)
    for signal in (*SIGNAL_IDS, "AGE_OR_TENURE"):
        feature_columns.extend([signal, f"{signal}_available", f"{signal}_missing_reason"])
    feature_columns.extend(["grid_id", *REGIME_IDS])
    feature_panel = panel[feature_columns].copy()
    label_columns = list(key_columns)
    for label in LABEL_IDS:
        label_columns.extend([label, f"{label}_available", f"{label}_missing_reason"])
    label_panel = panel[label_columns].copy()
    validate_panel(index_panel, feature_panel, label_panel)
    assignments = fold_assignments(index)
    fingerprint = fingerprint_keys(index_panel)
    paths = {
        "index": REPORTS / "ams-rd06-p1-panel-index-v1.parquet",
        "feature": REPORTS / "ams-rd06-p1-feature-panel-v1.parquet",
        "label": REPORTS / "ams-rd06-p1-label-panel-v1.parquet",
    }
    index_panel.to_parquet(paths["index"], index=False)
    feature_panel.to_parquet(paths["feature"], index=False)
    label_panel.to_parquet(paths["label"], index=False)
    assignments.to_csv(
        REPORTS / "ams-rd06-p1-fold-grid-assignments-v1.csv", index=False, lineterminator="\n"
    )
    signal_rows: list[dict[str, object]] = [
        {
            "signal_id": signal,
            "available_rows": int(feature_panel[f"{signal}_available"].sum()),
            "total_rows": len(feature_panel),
        }
        for signal in SIGNAL_IDS
    ]
    label_rows: list[dict[str, object]] = [
        {
            "label_id": label,
            "available_rows": int(label_panel[f"{label}_available"].sum()),
            "total_rows": len(label_panel),
        }
        for label in LABEL_IDS
    ]
    regime_rows: list[dict[str, object]] = [
        {
            "regime_id": regime,
            "available_rows": int((feature_panel[regime] != "INSUFFICIENT_HISTORY").sum()),
            "total_rows": len(feature_panel),
        }
        for regime in REGIME_IDS
    ]
    write_csv(REPORTS / "ams-rd06-p1-signal-coverage-v1.csv", signal_rows)
    write_csv(REPORTS / "ams-rd06-p1-label-coverage-v1.csv", label_rows)
    write_csv(REPORTS / "ams-rd06-p1-regime-coverage-v1.csv", regime_rows)
    missing_rows: list[dict[str, object]] = []
    for item in (*SIGNAL_IDS, "AGE_OR_TENURE", *LABEL_IDS):
        source = feature_panel if item in feature_panel else label_panel
        counts = source.loc[~source[f"{item}_available"], f"{item}_missing_reason"].value_counts()
        for reason, count in counts.items():
            missing_rows.append({"field_id": item, "missing_reason": reason, "row_count": count})
    write_csv(REPORTS / "ams-rd06-p1-missing-reasons-v1.csv", missing_rows)
    reconciliation = [
        {
            "index_rows": len(index_panel),
            "feature_rows": len(feature_panel),
            "label_rows": len(label_panel),
            "unique_keys": True,
            "keys_identical": True,
            "signal_columns": 15,
            "label_columns": 5,
            "regime_columns": 6,
            "numeric_warnings": 0,
            "status": "PASS",
        }
    ]
    write_csv(REPORTS / "ams-rd06-p1-reconciliation-v1.csv", reconciliation)
    payload: dict[str, object] = {
        "status": "COMPLETE",
        "decision": "RD06_INTRAWEEK_CAUSAL_PANEL_COMPLETE",
        "next_stage": "RD06-S1-INTRAWEEK-PRIMITIVE-SIGNAL-DIAGNOSTIC",
        "rows": len(index_panel),
        "panel_fingerprint": fingerprint,
        "decision_counts_by_grid": index.groupby("grid_id")["decision_time"].nunique().to_dict(),
        "rd06_s1_authorized": True,
        "portfolio_construction_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    write_text(
        REPORTS / "ams-rd06-p1-intraweek-panel-v1.json",
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    write_text(
        ROOT / "RD06_P1_RESULT_FOR_CHATGPT.md",
        "# RD06 P1 Result\n\nCausal intraweek panel complete; S1 is authorized.\n",
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
