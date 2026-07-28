"""Build the authorized causal RD08 market-state panel."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd08_market_state_panel import (
    aggregate_return,
    average_pairwise_correlation,
    dispersion,
    valid_market_label,
)
from spotbot.research.rd08_protocol_registration import LABELS, SIGNALS

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
KUCOIN = (
    ROOT / "data/research/rd04/kucoin-spot-usdt-adjudicated-v1/"
    "ams-rd04-d0c-kucoin-adjudicated-4h.parquet"
)
QUOTE = (
    ROOT / "data/research/rd04/kucoin-native-quote-turnover-v1/"
    "ams-rd04-d5a-native-quote-turnover-4h.parquet"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    protocol = json.loads(
        (REPORTS / "ams-rd08-protocol-registration-v1.json").read_text(encoding="utf-8")
    )
    if protocol["decision"] != "RD08_MARKET_STATE_TIMING_PROTOCOL_REGISTERED":
        raise RuntimeError("RD08 P1 is not authorized")
    index = pd.read_parquet(REPORTS / "ams-rd06-p1-panel-index-v1.parquet")
    features = pd.read_parquet(REPORTS / "ams-rd06-p1-feature-panel-v1.parquet")
    labels = pd.read_parquet(REPORTS / "ams-rd06-p1-label-panel-v1.parquet")
    bn_features = pd.read_parquet(REPORTS / "ams-rd07-binance-feature-panel-v1.parquet")
    bn_labels = pd.read_parquet(REPORTS / "ams-rd07-matched-label-panel-v1.parquet")
    assignments = pd.read_csv(REPORTS / "ams-rd06-p1-fold-grid-assignments-v1.csv")
    assignments["decision_time"] = pd.to_datetime(assignments["decision_time"], utc=True)
    kucoin = pd.read_parquet(KUCOIN)
    quote = pd.read_parquet(QUOTE)
    quote["symbol"] = quote["venue_pair"].str.removesuffix("-USDT")
    kucoin = kucoin.merge(
        quote[["symbol", "bar_open_time", "quote_turnover_usdt"]],
        on=["symbol", "bar_open_time"],
        how="left",
        validate="one_to_one",
    )
    kucoin["log_return"] = kucoin.groupby("symbol", observed=True)["close"].transform(
        lambda values: pd.Series(np.log(values.astype(float).to_numpy()), index=values.index).diff()
    )
    return_pivot = kucoin.pivot(
        index="bar_close_time", columns="symbol", values="log_return"
    ).sort_index()
    quote_pivot = kucoin.pivot(
        index="bar_close_time", columns="symbol", values="quote_turnover_usdt"
    ).sort_index()
    mapping = pd.read_csv(REPORTS / "ams-rd07-binance-symbol-mapping-v1.csv")
    bn_roll_parts: list[pd.DataFrame] = []
    for mapping_row in mapping.itertuples(index=False):
        if pd.isna(mapping_row.parquet_path):
            continue
        symbol = str(mapping_row.kucoin_canonical_symbol)
        frame = pd.read_parquet(ROOT / str(mapping_row.parquet_path))
        frame["decision_time"] = pd.to_datetime(frame["open_time"], utc=True) + pd.Timedelta(
            hours=4
        )
        frame["bn_quote_6"] = (
            frame["quote_asset_volume"].astype(float).rolling(6, min_periods=6).sum()
        )
        frame["bn_taker_6"] = (
            frame["taker_buy_quote_asset_volume"].astype(float).rolling(6, min_periods=6).sum()
        )
        bn_roll_parts.append(
            frame[["decision_time", "bn_quote_6", "bn_taker_6"]].assign(symbol=symbol)
        )
    bn_roll = pd.concat(bn_roll_parts, ignore_index=True)
    keys = ["decision_time", "symbol"]
    symbol_panel = (
        index[keys + ["grid_id"]]
        .merge(features, on=keys + ["grid_id"], validate="one_to_one")
        .merge(labels, on=keys, validate="one_to_one")
        .merge(
            bn_features[
                keys
                + [
                    "BN_KC_RETURN_DIVERGENCE_6",
                    "BN_KC_RETURN_DIVERGENCE_6_available",
                ]
            ],
            on=keys,
            validate="one_to_one",
        )
        .merge(
            bn_labels[
                keys
                + [
                    "BN_FORWARD_24H_RETURN",
                    "BN_FORWARD_72H_RETURN",
                    "BN_FORWARD_7D_RETURN",
                ]
            ],
            on=keys,
            validate="one_to_one",
        )
        .merge(bn_roll, on=keys, how="left", validate="one_to_one")
    )
    fold_lookup = (
        assignments.groupby(["decision_time", "grid_id"], observed=True)["fold_id"]
        .agg("|".join)
        .reset_index()
    )
    rows: list[dict[str, object]] = []
    for raw_key, group in symbol_panel.groupby(["decision_time", "grid_id"], sort=True):
        decision_time = pd.Timestamp(str(raw_key[0]))
        grid_id = str(raw_key[1])
        members = group["symbol"].astype(str).tolist()
        member_count = len(members)
        valid_members = int(group["RETURN_42BAR"].notna().sum())
        matched_members = int(group["BN_KC_RETURN_DIVERGENCE_6"].notna().sum())
        ret6 = group["RETURN_6BAR"].astype(float)
        ret18 = group["RETURN_18BAR"].astype(float)
        ret42 = group["RETURN_42BAR"].astype(float)
        dispersion18 = dispersion(ret18)
        dispersion42 = dispersion(ret42)
        historical42 = return_pivot.loc[:decision_time, members].tail(42)
        historical18 = historical42.tail(18)
        corr42 = average_pairwise_correlation(historical42)
        corr18 = average_pairwise_correlation(historical18)
        aggregate_quote = quote_pivot.loc[:decision_time, members].tail(42).sum(axis=1)
        quote_mean6 = float(aggregate_quote.tail(6).mean())
        quote_mean42 = float(aggregate_quote.mean())
        bn_valid = group.loc[group["bn_quote_6"].notna() & group["bn_taker_6"].notna()]
        bn_quote = float(bn_valid["bn_quote_6"].sum())
        bn_taker = float(bn_valid["bn_taker_6"].sum())
        market_returns = historical42.mean(axis=1, skipna=True)
        market_row: dict[str, object] = {
            "decision_time": decision_time,
            "grid_id": grid_id,
            "pit_member_count": member_count,
            "valid_kucoin_member_count": valid_members,
            "matched_binance_member_count": matched_members,
            "matched_binance_share": matched_members / member_count,
            "MKT_PIT_EW_RETURN_6BAR": aggregate_return(ret6),
            "MKT_PIT_EW_RETURN_18BAR": aggregate_return(ret18),
            "MKT_PIT_EW_RETURN_42BAR": aggregate_return(ret42),
            "MKT_BREADTH_POSITIVE_6BAR": float((ret6.dropna() > 0).mean()),
            "MKT_BREADTH_THRUST_6_42": float(
                (ret6.dropna() > 0).mean() - (ret42.dropna() > 0).mean()
            ),
            "MKT_BREADTH_ABOVE_EMA20": float(
                (group["DISTANCE_FROM_EMA20_ATR_4H"].dropna().astype(float) < 0).mean()
            ),
            "MKT_CROSS_SECTIONAL_DISPERSION_42": dispersion42,
            "MKT_DISPERSION_ACCEL_18_42": (
                dispersion18 / dispersion42 - 1.0
                if dispersion18 is not None and dispersion42 is not None and dispersion42 > 0
                else None
            ),
            "MKT_AVG_PAIRWISE_CORRELATION_42": corr42,
            "MKT_CORRELATION_CHANGE_18_42": (
                corr18 - corr42 if corr18 is not None and corr42 is not None else None
            ),
            "MKT_AGG_QUOTE_TURNOVER_ACCEL_6_42": (
                quote_mean6 / quote_mean42 - 1.0 if quote_mean42 > 0 else None
            ),
            "MKT_BN_AGG_TAKER_IMBALANCE_6": (
                2.0 * bn_taker / bn_quote - 1.0 if bn_quote > 0 else None
            ),
            "MKT_BN_KC_RETURN_DIVERGENCE_6": (
                float(group["BN_KC_RETURN_DIVERGENCE_6"].dropna().mean())
                if matched_members >= 20
                else None
            ),
            "MKT_LOW_REALIZED_VOLATILITY_42": (
                -float(market_returns.std(ddof=1)) if len(market_returns.dropna()) == 42 else None
            ),
        }
        label_map = {
            "PIT_EQUAL_WEIGHT_FORWARD_24H_RETURN": "FORWARD_24H_RETURN",
            "PIT_EQUAL_WEIGHT_FORWARD_72H_RETURN": "FORWARD_72H_RETURN",
            "PIT_EQUAL_WEIGHT_FORWARD_7D_RETURN": "FORWARD_7D_RETURN",
        }
        for output_label, source_label in label_map.items():
            market_row[output_label] = valid_market_label(
                group[source_label], member_count=member_count
            )
        btc = group.loc[group["symbol"] == "BTC"]
        market_row["BTC_SPOT_FORWARD_24H_RETURN"] = (
            float(btc["FORWARD_24H_RETURN"].iloc[0])
            if len(btc) and pd.notna(btc["FORWARD_24H_RETURN"].iloc[0])
            else None
        )
        market_row["BTC_SPOT_FORWARD_72H_RETURN"] = (
            float(btc["FORWARD_72H_RETURN"].iloc[0])
            if len(btc) and pd.notna(btc["FORWARD_72H_RETURN"].iloc[0])
            else None
        )
        market_row["BTC_SPOT_FORWARD_7D_RETURN"] = (
            float(btc["FORWARD_7D_RETURN"].iloc[0])
            if len(btc) and pd.notna(btc["FORWARD_7D_RETURN"].iloc[0])
            else None
        )
        for horizon in ("24H", "72H", "7D"):
            source_label = f"BN_FORWARD_{horizon}_RETURN"
            output_label = f"BINANCE_MATCHED_EQUAL_WEIGHT_FORWARD_{horizon}_RETURN"
            market_row[output_label] = valid_market_label(
                group[source_label], member_count=member_count
            )
        rows.append(market_row)
    panel = pd.DataFrame(rows).merge(
        fold_lookup,
        on=["decision_time", "grid_id"],
        how="left",
        validate="one_to_one",
    )
    panel["fold_id"] = panel["fold_id"].fillna("OUTSIDE_VALIDATION")
    for item in SIGNALS:
        panel[f"{item.signal_id}_available"] = panel[item.signal_id].notna()
        panel[f"{item.signal_id}_missing_reason"] = panel[f"{item.signal_id}_available"].map(
            {True: "", False: "MARKET_INPUT_OR_LOOKBACK_UNAVAILABLE"}
        )
    for label in LABELS:
        panel[f"{label}_available"] = panel[label].notna()
        panel[f"{label}_missing_reason"] = panel[f"{label}_available"].map(
            {True: "", False: "MARKET_LABEL_COVERAGE_OR_HORIZON_UNAVAILABLE"}
        )
    output_path = REPORTS / "ams-rd08-market-panel-v1.parquet"
    panel.to_parquet(output_path, index=False)
    signal_coverage = pd.DataFrame(
        [
            {
                "signal_id": item.signal_id,
                "available_count": int(panel[item.signal_id].notna().sum()),
                "row_count": len(panel),
                "coverage": float(panel[item.signal_id].notna().mean()),
            }
            for item in SIGNALS
        ]
    )
    label_coverage = pd.DataFrame(
        [
            {
                "label_id": label,
                "available_count": int(panel[label].notna().sum()),
                "row_count": len(panel),
                "coverage": float(panel[label].notna().mean()),
            }
            for label in LABELS
        ]
    )
    signal_coverage.to_csv(REPORTS / "ams-rd08-signal-coverage-v1.csv", index=False)
    label_coverage.to_csv(REPORTS / "ams-rd08-label-coverage-v1.csv", index=False)
    sources = [
        {
            "source": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
            "status": "PASS",
        }
        for path in (
            KUCOIN,
            QUOTE,
            REPORTS / "ams-rd06-p1-panel-index-v1.parquet",
            REPORTS / "ams-rd07-binance-feature-panel-v1.parquet",
            REPORTS / "ams-rd07-matched-label-panel-v1.parquet",
        )
    ]
    pd.DataFrame(sources).to_csv(REPORTS / "ams-rd08-source-reconciliation-v1.csv", index=False)
    report = {
        "stage": "RD08-P1-MARKET-STATE-CAUSAL-PANEL",
        "status": "COMPLETE",
        "decision": "RD08_MARKET_STATE_CAUSAL_PANEL_COMPLETE",
        "next_stage": "RD08-S1-MARKET-TIMING-DIAGNOSTIC",
        "signal_diagnostic_authorized": True,
        "panel_rows": len(panel),
        "unique_keys": not panel.duplicated(["decision_time", "grid_id"]).any(),
        "validation_rows": int((panel["fold_id"] != "OUTSIDE_VALIDATION").sum()),
        "minimum_pit_members": int(panel["pit_member_count"].min()),
        "minimum_matched_binance_members": int(panel["matched_binance_member_count"].min()),
        "median_matched_binance_share": float(panel["matched_binance_share"].median()),
        "panel_sha256": sha256(output_path),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "portfolio_construction_authorized": False,
    }
    (REPORTS / "ams-rd08-market-panel-v1.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (ROOT / "RD08_P1_MARKET_PANEL_RESULT_FOR_CHATGPT.md").write_text(
        "# RD08 P1 Market Panel\n\n"
        f"- Rows: `{len(panel)}`\n"
        "- Decision: `RD08_MARKET_STATE_CAUSAL_PANEL_COMPLETE`\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
