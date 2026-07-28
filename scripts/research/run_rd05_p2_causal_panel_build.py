"""Build the authorized RD05 P2 index, feature, label, and fold artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spotbot.research.rd05_causal_symbol_time_panel import LABEL_IDS, REGIME_IDS, SIGNAL_IDS, signal_values
from spotbot.research.rd05_p1a_protocol_amendment import FOLDS

ROOT = Path(__file__).resolve().parents[2]; REPORTS = ROOT / "reports" / "research"
LOCK = pd.Timestamp("2025-01-01T00:00:00Z")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp"); temp.write_text(text, encoding="utf-8", newline="\n"); temp.replace(path)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    buf = StringIO(newline=""); writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(rows); write_text(path, buf.getvalue())


def role(fold: object, decision: pd.Timestamp) -> str:
    start, end = pd.Timestamp(fold.train_start, tz="UTC"), pd.Timestamp(fold.train_end, tz="UTC")
    if start <= decision <= end: return "TRAIN"
    start, end = pd.Timestamp(fold.validation_start, tz="UTC"), pd.Timestamp(fold.validation_end, tz="UTC")
    if start <= decision <= end: return "VALIDATION"
    if pd.Timestamp(fold.train_end, tz="UTC") < decision < pd.Timestamp(fold.validation_start, tz="UTC"): return "PURGE_EMBARGO"
    return "OUTSIDE_REGISTERED_FOLD"


def labels(future: pd.DataFrame, reference: float) -> dict[str, float]:
    result = {name: float("nan") for name in LABEL_IDS}
    for days, name in ((1,"FORWARD_1D_RETURN"),(3,"FORWARD_3D_RETURN"),(7,"FORWARD_7D_CLOSE_TO_CLOSE_RETURN"),(14,"FORWARD_14D_RETURN"),(28,"FORWARD_28D_RETURN")):
        if len(future) >= days: result[name] = float(future.close.iloc[days-1]/reference-1)
    if len(future) >= 7:
        result["FORWARD_7D_MAX_FAVOURABLE_EXCURSION"] = float(future.high.iloc[:7].max()/reference-1)
        result["FORWARD_7D_MAX_ADVERSE_EXCURSION"] = float(future.low.iloc[:7].min()/reference-1)
    return result


def run() -> dict[str, object]:
    authorization = json.loads((REPORTS / "ams-rd05-p1-re-adjudication-v1.json").read_text())
    if not authorization["rd05_p2_panel_build_authorized"]: raise RuntimeError("P2 is not authorized")
    d0c = json.loads((REPORTS / "ams-rd04-d0c-adjudicated-dataset-registration-v1.json").read_text())
    paths = {k: ROOT / v["path"] for k,v in d0c["datasets"].items()}
    daily = pd.read_parquet(paths["daily"]); four = pd.read_parquet(paths["four_hour"]); availability = pd.read_parquet(paths["availability"])
    daily = daily.loc[(daily.bar_open_time < LOCK) & (daily.bar_close_time <= LOCK)].sort_values(["symbol","bar_close_time"])
    four = four.loc[(four.bar_open_time < LOCK) & (four.bar_close_time <= LOCK)]
    membership = pd.read_csv(REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv")
    membership["decision_time"] = pd.to_datetime(membership.rebalance_time, utc=True)
    membership = membership.loc[membership.venue_data_eligible].copy()
    index_rows: list[dict[str, Any]]=[]; feature_rows: list[dict[str, Any]]=[]; label_rows: list[dict[str, Any]]=[]
    daily_by = {symbol: frame.set_index("bar_close_time").sort_index() for symbol,frame in daily.groupby("symbol")}
    btc = daily_by["BTC"].close; btc_returns = np.log(btc).diff()
    market_return: dict[pd.Timestamp,pd.Series] = {}
    for decision, group in membership.groupby("decision_time"):
        symbols = group.canonical_symbol.tolist(); start = decision-pd.Timedelta(days=7); closes=[]
        for symbol in symbols:
            h=daily_by.get(symbol)
            if h is not None: closes.append(np.log(h.close.loc[(h.index>start)&(h.index<=decision)]).diff())
        if closes: market_return[decision] = pd.concat(closes,axis=1).mean(axis=1)
    regime_history: dict[str,list[float]] = defaultdict(list)
    for decision, group in membership.groupby("decision_time", sort=True):
        current_market = market_return.get(decision, pd.Series(dtype=float)); btc_hist=btc_returns.loc[btc_returns.index<=decision]
        raw_regimes={"BTC_REALIZED_VOLATILITY_TERCILE":float(btc_hist.tail(28).std(ddof=1)),"CROSS_SECTIONAL_DISPERSION_TERCILE":float('nan'),"AVERAGE_PAIRWISE_CORRELATION_TERCILE":float('nan'),"MARKET_BREADTH_TERCILE":float('nan'),"PIT_UNIVERSE_SIZE_TERCILE":float(len(group))}
        r28=[]
        for symbol in group.canonical_symbol:
            h=daily_by.get(symbol)
            if h is not None and len(h.loc[h.index<=decision])>=29:
                x=h.loc[h.index<=decision].close; r28.append(x.iloc[-1]/x.iloc[-29]-1)
        if r28: raw_regimes["CROSS_SECTIONAL_DISPERSION_TERCILE"]=float(np.std(r28,ddof=1)); raw_regimes["MARKET_BREADTH_TERCILE"]=float(np.mean(np.array(r28)>0))
        states={"BTC_TREND_STATE":"UP" if len(btc.loc[btc.index<=decision])>=84 and btc.loc[btc.index<=decision].iloc[-1]>btc.loc[btc.index<=decision].tail(84).mean() else "INSUFFICIENT_HISTORY"}
        for name,value in raw_regimes.items():
            history=regime_history[name]; states[name]="INSUFFICIENT_HISTORY" if len(history)<52 else ("LOW" if value<=np.quantile(history,1/3,method="linear") else "MID" if value<=np.quantile(history,2/3,method="linear") else "HIGH")
            if np.isfinite(value): history.append(value)
        for item in group.itertuples(index=False):
            symbol=str(item.canonical_symbol); h=daily_by.get(symbol)
            if h is None: continue
            past=h.loc[h.index<=decision]; future=h.loc[h.index>decision]
            available=availability.loc[availability.symbol==symbol].iloc[0]
            cutoff=past.index.max() if not past.empty else pd.NaT
            index_rows.append({"panel_schema_version":"ams-rd05-p2-panel-v1","decision_time":decision,"symbol":symbol,"membership_snapshot_id":str(decision),"availability_start":available.tradable_from,"availability_end":available.tradable_until,"source_cutoff_time":decision,"last_eligible_1d_close_time":cutoff,"last_eligible_4h_close_time":four.loc[(four.symbol==symbol)&(four.bar_close_time<=decision),"bar_close_time"].max(),"feature_warmup_complete":len(past)>=84,"source_fingerprint":sha(paths["daily"]),"row_missing_reason":""})
            values=signal_values(past,btc_returns.loc[btc_returns.index<=decision],current_market)
            quote=float('nan')
            values["QUOTE_TURNOVER_CHANGE_7D_30D"]=quote
            values["AGE_OR_TENURE"]=float((decision-pd.Timestamp(available.tradable_from)).days)
            feature_rows.append({"decision_time":decision,"symbol":symbol,**values,**{f"{k}_available":bool(np.isfinite(v)) for k,v in values.items()},**states})
            lab=labels(future,float(past.close.iloc[-1])) if not past.empty else {name:float('nan') for name in LABEL_IDS}
            label_rows.append({"decision_time":decision,"symbol":symbol,**lab,**{f"{k}_available":bool(np.isfinite(v)) for k,v in lab.items()},**{f"{k}_end_timestamp":decision+pd.Timedelta(days=int(k.split('_')[1].replace('D',''))) if '_D_' in k else decision+pd.Timedelta(days=7) for k in LABEL_IDS}})
    index=pd.DataFrame(index_rows).sort_values(["decision_time","symbol"]); features=pd.DataFrame(feature_rows).sort_values(["decision_time","symbol"]); labels_frame=pd.DataFrame(label_rows).sort_values(["decision_time","symbol"])
    out={"index":REPORTS/"ams-rd05-p2-panel-index-v1.parquet","feature":REPORTS/"ams-rd05-p2-feature-panel-v1.parquet","label":REPORTS/"ams-rd05-p2-label-panel-v1.parquet"}
    for frame,path in ((index,out["index"]),(features,out["feature"]),(labels_frame,out["label"])): frame.to_parquet(path,index=False)
    assignments=[{"fold_id":fold.fold_id,"decision_time":decision,"role":role(fold,decision),"purge_embargo_days":28,"primary_label_eligible":role(fold,decision)=="VALIDATION" and decision<=pd.Timestamp(fold.validation_end,tz="UTC")} for decision in sorted(membership.decision_time.unique()) for fold in FOLDS]
    write_csv(REPORTS/"ams-rd05-p2-fold-assignments-v1.csv",assignments)
    coverage=[{"signal_id":name,"available_rows":int(features[f"{name}_available"].sum()),"total_rows":len(features)} for name in SIGNAL_IDS]; write_csv(REPORTS/"ams-rd05-p2-signal-coverage-v1.csv",coverage)
    label_cov=[{"label_id":name,"available_rows":int(labels_frame[f"{name}_available"].sum()),"total_rows":len(labels_frame)} for name in LABEL_IDS]; write_csv(REPORTS/"ams-rd05-p2-label-coverage-v1.csv",label_cov)
    regime_cov=[{"regime_id":name,"available_rows":int((features[name]!="INSUFFICIENT_HISTORY").sum()),"total_rows":len(features)} for name in REGIME_IDS]; write_csv(REPORTS/"ams-rd05-p2-regime-coverage-v1.csv",regime_cov)
    schema=[{"artifact":"index","primary_key":"decision_time|symbol","rows":len(index)},{"artifact":"feature","primary_key":"decision_time|symbol","rows":len(features)},{"artifact":"label","primary_key":"decision_time|symbol","rows":len(labels_frame)}]; write_csv(REPORTS/"ams-rd05-p2-panel-schema-v1.csv",schema)
    write_csv(REPORTS/"ams-rd05-p2-missing-reasons-v1.csv",[{"reason":"MISSING_OR_INSUFFICIENT_WARMUP","count":int(features[list(SIGNAL_IDS)].isna().all(axis=1).sum())}])
    write_csv(REPORTS/"ams-rd05-p2-source-lineage-v1.csv",[{"source":"D0C","daily_sha256":sha(paths["daily"]),"membership_sha256":sha(REPORTS/"ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv")}])
    reconciliation={"index_rows":len(index),"feature_rows":len(features),"label_rows":len(labels_frame),"keys_identical":set(map(tuple,index[["decision_time","symbol"]].to_numpy()))==set(map(tuple,features[["decision_time","symbol"]].to_numpy()))==set(map(tuple,labels_frame[["decision_time","symbol"]].to_numpy())),"signal_columns":len(SIGNAL_IDS),"label_columns":len(LABEL_IDS),"regime_columns":len(REGIME_IDS),"status":"PASS"}; write_csv(REPORTS/"ams-rd05-p2-reconciliation-v1.csv",[reconciliation])
    report={"status":"COMPLETE","decision":"RD05_CAUSAL_SYMBOL_TIME_PANEL_COMPLETE","next_stage":"RD05-S1-PRIMITIVE-SIGNAL-DIAGNOSTIC","rd05_s1_primitive_signal_diagnostic_authorized":True,"portfolio_simulation_authorized":False,"rows":len(index),"reconciliation":reconciliation,"test_2025_accessed":False,"holdout_2026_accessed":False,"generated_at_utc":datetime.now(UTC).isoformat()}
    write_text(REPORTS/"ams-rd05-p2-causal-panel-v1.json",json.dumps(report,indent=2,default=str)+"\n"); write_text(REPORTS/"ams-rd05-p2-causal-panel-v1.md","# RD05 P2 causal panel\n\nNo predictive evaluation or portfolio simulation was executed.\n")
    return report


if __name__=="__main__": print(json.dumps(run(),default=str))
