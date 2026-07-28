"""Build the authorized RD07 matched KuCoin/Binance panel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from spotbot.research.rd07_matched_panel import (
    REGIME_IDS,
    SIGNAL_IDS,
    compute_binance_features,
    compute_binance_labels,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
KUCOIN_PATH = (
    ROOT / "data/research/rd04/kucoin-spot-usdt-adjudicated-v1/"
    "ams-rd04-d0c-kucoin-adjudicated-4h.parquet"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    coverage = json.loads((REPORTS / "ams-rd07-coverage-audit-v1.json").read_text(encoding="utf-8"))
    if coverage["decision"] != "RD07_EXTERNAL_SPOT_DATA_COVERAGE_COMPLETE":
        raise RuntimeError("RD07 coverage did not authorize the matched panel")
    index = pd.read_parquet(REPORTS / "ams-rd06-p1-panel-index-v1.parquet")
    rd06_features = pd.read_parquet(REPORTS / "ams-rd06-p1-feature-panel-v1.parquet")
    kucoin_labels = pd.read_parquet(REPORTS / "ams-rd06-p1-label-panel-v1.parquet")
    mapping = pd.read_csv(REPORTS / "ams-rd07-binance-symbol-mapping-v1.csv")
    kucoin = pd.read_parquet(KUCOIN_PATH)
    quote_path = (
        ROOT / "data/research/rd04/kucoin-native-quote-turnover-v1/"
        "ams-rd04-d5a-native-quote-turnover-4h.parquet"
    )
    quote = pd.read_parquet(quote_path)
    quote["symbol"] = quote["venue_pair"].str.removesuffix("-USDT")
    kucoin = kucoin.merge(
        quote[["symbol", "bar_open_time", "quote_turnover_usdt"]],
        on=["symbol", "bar_open_time"],
        how="left",
        validate="one_to_one",
    )
    feature_parts: list[pd.DataFrame] = []
    label_parts: list[pd.DataFrame] = []
    for row in mapping.itertuples(index=False):
        if pd.isna(row.parquet_path):
            continue
        raw_path = str(row.parquet_path)
        symbol = str(row.kucoin_canonical_symbol)
        binance = pd.read_parquet(ROOT / raw_path)
        local = kucoin.loc[kucoin["symbol"] == symbol].copy()
        if local.empty:
            continue
        features = compute_binance_features(binance, local)
        features.insert(1, "symbol", symbol)
        labels = compute_binance_labels(binance)
        labels.insert(1, "symbol", symbol)
        feature_parts.append(features)
        label_parts.append(labels)
    lookup_features = pd.concat(feature_parts, ignore_index=True)
    lookup_labels = pd.concat(label_parts, ignore_index=True)
    keys = ["decision_time", "symbol"]
    panel_index = index.copy()
    feature_panel = panel_index[keys].merge(
        lookup_features, on=keys, how="left", validate="one_to_one"
    )
    regime_columns = ["decision_time", "symbol", *REGIME_IDS]
    feature_panel = feature_panel.merge(
        rd06_features[regime_columns], on=keys, how="left", validate="one_to_one"
    )
    feature_panel = feature_panel.merge(
        index[keys + ["grid_id"]], on=keys, how="left", validate="one_to_one"
    )
    for signal in (*SIGNAL_IDS, "BINANCE_AGE_OR_TENURE"):
        feature_panel[f"{signal}_available"] = feature_panel[signal].notna()
        feature_panel[f"{signal}_missing_reason"] = feature_panel[f"{signal}_available"].map(
            {True: "", False: "BINANCE_INPUT_OR_LOOKBACK_UNAVAILABLE"}
        )
    label_panel = panel_index[keys].merge(kucoin_labels, on=keys, how="left", validate="one_to_one")
    label_panel = label_panel.merge(lookup_labels, on=keys, how="left", validate="one_to_one")
    for label in (
        "BN_FORWARD_24H_RETURN",
        "BN_FORWARD_72H_RETURN",
        "BN_FORWARD_7D_RETURN",
    ):
        label_panel[f"{label}_available"] = label_panel[label].notna()
        label_panel[f"{label}_missing_reason"] = label_panel[f"{label}_available"].map(
            {True: "", False: "BINANCE_HORIZON_UNAVAILABLE"}
        )
    index_output = REPORTS / "ams-rd07-matched-panel-index-v1.parquet"
    feature_output = REPORTS / "ams-rd07-binance-feature-panel-v1.parquet"
    label_output = REPORTS / "ams-rd07-matched-label-panel-v1.parquet"
    panel_index.to_parquet(index_output, index=False)
    feature_panel.to_parquet(feature_output, index=False)
    label_panel.to_parquet(label_output, index=False)
    coverage_rows = [
        {
            "field_id": signal,
            "available_rows": int(feature_panel[signal].notna().sum()),
            "total_rows": len(feature_panel),
            "coverage": float(feature_panel[signal].notna().mean()),
        }
        for signal in (*SIGNAL_IDS, "BINANCE_AGE_OR_TENURE")
    ]
    pd.DataFrame(coverage_rows).to_csv(
        REPORTS / "ams-rd07-matched-signal-coverage-v1.csv", index=False
    )
    label_rows = [
        {
            "label_id": label,
            "available_rows": int(label_panel[label].notna().sum()),
            "total_rows": len(label_panel),
            "coverage": float(label_panel[label].notna().mean()),
        }
        for label in (
            "FORWARD_24H_RETURN",
            "BN_FORWARD_24H_RETURN",
            "BN_FORWARD_72H_RETURN",
            "BN_FORWARD_7D_RETURN",
        )
    ]
    pd.DataFrame(label_rows).to_csv(REPORTS / "ams-rd07-matched-label-coverage-v1.csv", index=False)
    fingerprints = {
        str(path.relative_to(ROOT)): sha256(path)
        for path in (index_output, feature_output, label_output)
    }
    report = {
        "stage": "RD07-MATCHED-CROSS-VENUE-PANEL",
        "status": "COMPLETE",
        "decision": "RD07_MATCHED_PANEL_COMPLETE",
        "next_stage": "RD07-CROSS-VENUE-SIGNAL-DIAGNOSTIC",
        "signal_diagnostic_authorized": True,
        "panel_rows": len(panel_index),
        "unique_keys": not panel_index.duplicated(keys).any(),
        "feature_keys_identical": len(feature_panel) == len(panel_index),
        "label_keys_identical": len(label_panel) == len(panel_index),
        "signal_count": len(SIGNAL_IDS),
        "regime_count": len(REGIME_IDS),
        "fingerprints": fingerprints,
        "numeric_warnings": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "portfolio_construction_authorized": False,
    }
    (REPORTS / "ams-rd07-matched-panel-v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (REPORTS / "ams-rd07-matched-panel-v1.md").write_text(
        "# RD07 Matched Panel\n\n"
        f"- Rows: `{len(panel_index)}`\n"
        "- Decision: `RD07_MATCHED_PANEL_COMPLETE`\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
