# ruff: noqa
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from spotbot.research.ams_v4_active_conviction_swing import file_sha256
ROOT=Path.cwd();REPORTS=ROOT/"reports/research";LEDGER=REPORTS/"ams-v5-experiment-ledger-v1.json"
def write(path:Path,value:Any)->None:
 text=value if isinstance(value,str) else json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n";h,t=tempfile.mkstemp(dir=path.parent,prefix=f".{path.name}.",suffix=".tmp")
 try:
  with os.fdopen(h,"w",encoding="utf-8")as f:f.write(text)
  os.replace(t,path)
 except BaseException:
  if os.path.exists(t):os.unlink(t)
  raise
def activity(x:float)->str:
 return "VERY_SPARSE" if x<90 else "SPARSE" if x<120 else "MODERATE_ACTIVITY" if x<160 else "TARGET_ACTIVITY" if x<=220 else "HIGH_ACTIVITY" if x<=320 else "POTENTIAL_OVERTRADING"
def main()->None:
 ledger=json.loads(LEDGER.read_text());account=ledger["trial_accounting"]
 if account["executed_trials"]!=24 or account["remaining_trials"]!=0:raise RuntimeError("Need all trials")
 rows=[]
 for trial in ledger["trial_plan"]:
  path=ROOT/trial["report_path"]
  if file_sha256(path)!=trial["report_sha256"]:raise RuntimeError("Hash mismatch")
  report=json.loads(path.read_text());base=report["aggregate"]["base"];stress=report["aggregate"]["stress"];metrics=[f["base"]["metrics"] for f in report["fold_results"]];trades=[t for f in report["fold_results"] for t in f["base"]["trades"]];returns=np.array([t["return_fraction"] for t in trades])
  ci="INSUFFICIENT_SAMPLE" if len(returns)<30 else [float(np.quantile(np.array([np.random.default_rng(20260726).choice(returns,len(returns),replace=True).mean() for _ in range(1000)]),q)) for q in (.025,.975)]
  rows.append({"trial_id":trial["trial_id"],"configuration_id":trial["configuration_id"],"portfolio_profile_id":trial["portfolio_profile_id"],"base_compounded_return":base["aggregate_compounded_return"],"stress_compounded_return":stress["aggregate_compounded_return"],"maximum_drawdown":base["mean_maximum_drawdown"],"calmar":base["mean_calmar"],"profit_factor_base":base["mean_profit_factor"],"profit_factor_stress":stress["mean_profit_factor"],"trades_per_year":base["mean_trades_per_year"],"trade_count":base["total_trade_count"],"activity":activity(base["mean_trades_per_year"]),"positive_fold_ratio":base["positive_fold_ratio"],"worst_fold_return":base["worst_fold_return"],"win_rate":float(pd.Series([x["win_rate"] for x in metrics]).mean()),"payoff_ratio":float(pd.Series([x["payoff_ratio"] for x in metrics if x["payoff_ratio"] is not None]).mean()),"expectancy":float(returns.mean()) if len(returns) else 0,"bootstrap_expectancy_ci":ci,"mfe_capture":float(pd.Series([x["mfe_capture_ratio"] for x in metrics if x["mfe_capture_ratio"] is not None]).mean())})
 ranked=sorted(rows,key=lambda x:(-(x["base_compounded_return"]/max(x["maximum_drawdown"],.01)),x["trial_id"]));best=ranked[0]
 strong=best["positive_fold_ratio"]>=2/3 and best["worst_fold_return"]>=-.1 and best["calmar"]>=1.2 and best["profit_factor_base"]>=1.3 and best["profit_factor_stress"]>=1.12 and best["stress_compounded_return"]>0 and best["trades_per_year"]>=120 and isinstance(best["bootstrap_expectancy_ci"],list) and best["bootstrap_expectancy_ci"][0]>=0
 verdict="REQUEST_2025_TEST_CANDIDATE" if strong else "REVISE_WITHOUT_2025" if best["base_compounded_return"]>0 else "FAIL"
 v4={"base":.4149133908207694,"stress":.2609502915847426,"dd":.09449072602801711,"pf":1.4073315283457166,"trades_per_year":78}
 payload={"schema_version":"ams-v5-final-assessment-v1","status":"PASS","assessment":verdict,"authorized_trials":24,"executed_trials":24,"remaining_trials":0,"best_model":best,"top_five":ranked[:5],"all_trials":sorted(rows,key=lambda x:x["trial_id"]),"comparison_v4_t12":{"v4":v4,"difference":{"base_return":best["base_compounded_return"]-v4["base"],"stress_return":best["stress_compounded_return"]-v4["stress"],"drawdown":best["maximum_drawdown"]-v4["dd"],"trades_per_year":best["trades_per_year"]-78}},"overfitting":{"models_tested":24,"deflated_sharpe_ratio":"INSUFFICIENT_INDEPENDENT_FOLDS","pbo":"INSUFFICIENT_FOLDS_FOR_VALID_CSCV"},"test_2025_accessed":False,"holdout_2026_accessed":False,"next_action":"DO_NOT_OPEN_2025" if verdict!="REQUEST_2025_TEST_CANDIDATE" else "REQUEST_GOVERNED_2025_OPENING"}
 out=REPORTS/"ams-v5-final-assessment-v1.json";write(out,payload);table="\n".join(f"| {x['trial_id']} | {x['configuration_id']} | {x['portfolio_profile_id']} | {x['base_compounded_return']:.2%} | {x['stress_compounded_return']:.2%} | {x['trades_per_year']:.1f} |"for x in rows);write(REPORTS/"ams-v5-final-assessment-v1.md",f"# AMS V5 Final Assessment\n\nAssessment: **{verdict}**\n\n| Trial | Alpha | Profile | Base | Stress | Trades/year |\n|---|---|---|---:|---:|---:|\n{table}\n")
 ledger["final_assessment"]={"report_path":"reports/research/ams-v5-final-assessment-v1.json","report_sha256":file_sha256(out),"assessment":verdict};write(LEDGER,ledger);ready=json.loads((REPORTS/"ams-v5-data-readiness-v1.json").read_text());ready.update({"status":"AMS_V5_COMPLETE","executed_trials":24,"remaining_trials":0,"assessment":verdict,"test_2025_accessed":False,"holdout_2026_accessed":False});write(REPORTS/"ams-v5-data-readiness-v1.json",ready)
if __name__=="__main__":main()
