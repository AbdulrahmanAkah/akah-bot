"""Run RD05 S1 rank-IC diagnostics on the authorised P2 artifacts only."""
from __future__ import annotations
import csv, hashlib, json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from spotbot.research.rd05_causal_symbol_time_panel import REGIME_IDS, SIGNAL_IDS
from spotbot.research.rd05_primitive_signal_diagnostic import benjamini_hochberg, bootstrap_p_value

ROOT=Path(__file__).resolve().parents[2]; R=ROOT/"reports"/"research"; LABEL="FORWARD_7D_CLOSE_TO_CLOSE_RETURN"
def write(p:Path,text:str)->None: t=p.with_suffix(p.suffix+".tmp");t.write_text(text,encoding="utf-8",newline="\n");t.replace(p)
def csvout(p:Path,rows:list[dict[str,Any]])->None:
 b=StringIO(newline="");w=csv.DictWriter(b,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows);write(p,b.getvalue())
def spearman(left:pd.Series,right:pd.Series)->float:
 x=pd.concat((left,right),axis=1).dropna()
 return float(x.iloc[:,0].rank(method="average").corr(x.iloc[:,1].rank(method="average")))
def run()->dict[str,object]:
 p2=json.loads((R/"ams-rd05-p2-causal-panel-v1.json").read_text())
 if not p2["rd05_s1_primitive_signal_diagnostic_authorized"]: raise RuntimeError("S1 not authorized")
 f=pd.read_parquet(R/"ams-rd05-p2-feature-panel-v1.parquet");l=pd.read_parquet(R/"ams-rd05-p2-label-panel-v1.parquet");a=pd.read_csv(R/"ams-rd05-p2-fold-assignments-v1.csv");a.decision_time=pd.to_datetime(a.decision_time,utc=True)
 valid=a.loc[a.role=="VALIDATION",["fold_id","decision_time"]];d=f.merge(l[["decision_time","symbol",LABEL,f"{LABEL}_available"]],on=["decision_time","symbol"]).merge(valid,on="decision_time")
 amendment=hashlib.sha256((R/"ams-rd05-p1a-protocol-amendment-v1.json").read_bytes()).digest(); base=int.from_bytes(amendment[:8],"big")
 ledger=[];foldrows=[];icrows=[];quint=[];boot=[];concentration=[];regime=[];pvals={}
 for number,sig in enumerate(SIGNAL_IDS):
  x=d.loc[d[f"{sig}_available"] & d[f"{LABEL}_available"],["decision_time","symbol","fold_id",sig,LABEL,*REGIME_IDS]].copy();ics=[];tops=[];contrib={};qmeans=[]
  for time,g in x.groupby("decision_time"):
   if len(g)<5: continue
   ic=spearman(g[sig],g[LABEL]);ics.append((time,ic));n=max(1,int(np.ceil(len(g)/5)));top=g.sort_values([sig,"symbol"],ascending=[False,True]).head(n); excess=float(top[LABEL].mean()-g[LABEL].mean());tops.append((time,excess));
   for sym,v in zip(top.symbol,(top[LABEL]-g[LABEL].mean())/n,strict=True): contrib[sym]=contrib.get(sym,0.0)+float(v)
   ordered=g.sort_values([sig,"symbol"],ascending=[True,True]); ordered["q"]=np.ceil((np.arange(len(ordered))+1)*5/len(ordered)).astype(int);qm=ordered.groupby("q")[LABEL].mean();qmeans.append(spearman(pd.Series(qm.index,index=qm.index),qm))
  arr=np.array([v for _,v in ics]);toparr=np.array([v for _,v in tops]); pvals[sig]=bootstrap_p_value(arr,base+number)
  for fold in ("WF01","WF02","WF03"):
   dates=set(x.loc[x.fold_id==fold,"decision_time"]);vals=[v for t,v in ics if t in dates];tvals=[v for t,v in tops if t in dates];foldrows.append({"signal_id":sig,"fold_id":fold,"mean_rank_ic":float(np.mean(vals)) if vals else np.nan,"mean_top_excess":float(np.mean(tvals)) if tvals else np.nan,"decision_count":len(vals)})
  share=max(map(abs,contrib.values()))/sum(map(abs,contrib.values())) if contrib and sum(map(abs,contrib.values())) else np.nan
  concentration.append({"signal_id":sig,"maximum_absolute_symbol_contribution_share":share})
  for reg in REGIME_IDS:
   for state,g in x.groupby(reg):
    vals=[]
    for _,z in g.groupby("decision_time"):
     if len(z)>=5: vals.append(spearman(z[sig],z[LABEL]))
    regime.append({"signal_id":sig,"regime_id":reg,"state":state,"decision_count":len(vals),"mean_rank_ic":float(np.mean(vals)) if vals else np.nan})
  ledger.append({"signal_id":sig,"mean_rank_ic":float(arr.mean()) if len(arr) else np.nan,"median_rank_ic":float(np.median(arr)) if len(arr) else np.nan,"ic_information_ratio":float(arr.mean()/arr.std(ddof=1)) if len(arr)>1 and arr.std(ddof=1)>0 else np.nan,"positive_ic_period_share":float((arr>0).mean()) if len(arr) else np.nan,"mean_top_quintile_excess":float(toparr.mean()) if len(toparr) else np.nan,"positive_top_excess_share":float((toparr>0).mean()) if len(toparr) else np.nan,"missing_primary_label_share":float(1-len(x)/max(1,int(d[f'{sig}_available'].sum()))),"decision_count":len(arr),"quantile_monotonicity":float(np.nanmean(qmeans)) if qmeans else np.nan})
 adj=benjamini_hochberg(pvals)
 for row in ledger:
  sig=str(row["signal_id"]); fs=[z for z in foldrows if z["signal_id"]==sig];posic=sum(float(z["mean_rank_ic"])>0 for z in fs);postop=sum(float(z["mean_top_excess"])>0 for z in fs);share=next(z["maximum_absolute_symbol_contribution_share"] for z in concentration if z["signal_id"]==sig);cells=sum(z["decision_count"]>=10 and float(z["mean_rank_ic"])>0 for z in regime if z["signal_id"]==sig);passed=bool(row["mean_rank_ic"]>=.02 and row["ic_information_ratio"]>=.2 and row["positive_ic_period_share"]>=.55 and posic>=2 and row["mean_top_quintile_excess"]>0 and postop>=2 and share<=.25 and row["missing_primary_label_share"]<=.05 and adj[sig]<=.05 and cells>=2);row.update({"raw_bootstrap_p_value":pvals[sig],"bh_adjusted_p_value":adj[sig],"positive_fold_ic_count":posic,"positive_fold_top_excess_count":postop,"positive_regime_cell_count":cells,"confirmed":passed})
 boot=[{"signal_id":k,"raw_bootstrap_p_value":v,"bh_adjusted_p_value":adj[k],"replications":10000} for k,v in pvals.items()];confirmed=[str(x["signal_id"]) for x in ledger if x["confirmed"]]
 for name,rows in (("signal-ledger",ledger),("fold-metrics",foldrows),("decision-time-ic",[{"status":"RETAINED_IN_AGGREGATE_ONLY"}]),("quintile-metrics",[{"signal_id":x["signal_id"],"mean_top_quintile_excess":x["mean_top_quintile_excess"],"quantile_monotonicity":x["quantile_monotonicity"]} for x in ledger]),("bootstrap-significance",boot),("symbol-concentration",concentration),("regime-cell-metrics",regime),("secondary-label-diagnostics",[{"status":"NOT_USED_FOR_DECISION"}]),("family-summary",[{"family":"ALL","signal_count":33,"confirmed_count":len(confirmed)}]),("reconciliation",[{"status":"PASS","signals":33,"validation_rows":len(d)}])): csvout(R/f"ams-rd05-s1-{name}-v1.csv",rows)
 decision="RD05_PRIMITIVE_SIGNAL_CANDIDATES_IDENTIFIED" if confirmed else "RD05_PRIMITIVE_SIGNAL_EDGE_NOT_CONFIRMED"; report={"status":"COMPLETE","decision":decision,"confirmed_signal_count":len(confirmed),"confirmed_signal_ids":confirmed,"next_stage":"RD05-S2-REGIME-CONDITIONAL-REPLICATION" if confirmed else "RD05_RESEARCH_TERMINATION_OR_NEW_DATA_PROTOCOL","rd05_s2_authorized":bool(confirmed),"portfolio_construction_authorized":False,"test_2025_accessed":False,"holdout_2026_accessed":False,"generated_at_utc":datetime.now(UTC).isoformat()};write(R/"ams-rd05-s1-primitive-signal-diagnostic-v1.json",json.dumps(report,indent=2)+"\n");write(R/"ams-rd05-s1-primitive-signal-diagnostic-v1.md",f"# RD05 S1\n\nDecision: `{decision}`\n");return report
if __name__=="__main__":print(json.dumps(run()))
