# ruff: noqa
from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.ams_v5_active_pullback_reacceleration import (
    build_execution_panel, choose_threshold_train_only, metrics, portfolio_profiles, simulate,
)
from spotbot.research.ams_v4_active_conviction_swing import assert_research_boundary, file_sha256

ROOT=Path.cwd(); REPORTS=ROOT/"reports/research"; LEDGER=REPORTS/"ams-v5-experiment-ledger-v1.json"
FOLDS=(("AMS-V5-WF01","2021-01-01T00:00:00Z","2022-01-01T00:00:00Z","2023-01-01T00:00:00Z"),("AMS-V5-WF02","2021-01-01T00:00:00Z","2023-01-01T00:00:00Z","2024-01-01T00:00:00Z"),("AMS-V5-WF03","2021-01-01T00:00:00Z","2024-01-01T00:00:00Z","2025-01-01T00:00:00Z"))

def write(path:Path,value:dict[str,Any])->None:
 text=json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n"; handle,tmp=tempfile.mkstemp(dir=path.parent,prefix=f".{path.name}.",suffix=".tmp")
 try:
  with os.fdopen(handle,"w",encoding="utf-8") as f:f.write(text)
  os.replace(tmp,path)
 except BaseException:
  if os.path.exists(tmp):os.unlink(tmp)
  raise

def load_panel()->pd.DataFrame:
 reg=json.loads((REPORTS/"ams-v3-4h-dataset-registration-v1.json").read_text())["datasets"]
 frames={}
 for name in ("four_hour","availability"):
  path=ROOT/reg[name]["path"]
  if file_sha256(path)!=reg[name]["file_sha256"]:raise RuntimeError("Dataset hash mismatch")
  frames[name]=pd.read_parquet(path)
 return build_execution_panel(frames["four_hour"],frames["availability"])

def run_trial(configuration_id:str,profile_id:str,*,panel:pd.DataFrame|None=None)->Path:
 ledger=json.loads(LEDGER.read_text()); account=ledger["trial_accounting"]
 trial=next(x for x in ledger["trial_plan"] if x["configuration_id"]==configuration_id and x["portfolio_profile_id"]==profile_id)
 if trial["trial_status"]!="REGISTERED_NOT_EXECUTED" or account["remaining_trials"]<=0:raise RuntimeError("Trial not eligible")
 config=next(x for x in ledger["alpha_configurations"] if x["configuration_id"]==configuration_id); profile=next(x for x in portfolio_profiles() if x.profile_id==profile_id); all_panel=panel if panel is not None else load_panel(); timestamps=pd.to_datetime(all_panel["bar_open_time"],utc=True)
 folds=[]
 for fold_id,train_start,val_start,val_end in FOLDS:
  threshold,selection=choose_threshold_train_only(all_panel,config,profile,pd.Timestamp(val_start)); val=all_panel.loc[timestamps.ge(pd.Timestamp(val_start))&timestamps.lt(pd.Timestamp(val_end))].copy(); assert_research_boundary(val); regimes={}
  for mode in ("BASE","STRESS"):
   result=simulate(val,config,profile,cost_mode=mode,threshold=threshold); regimes[mode.lower()]={"metrics":metrics(result),"trades":[{**asdict(t),"entry_time":t.entry_time.isoformat(),"exit_time":t.exit_time.isoformat()} for t in result.trades]}
  folds.append({"fold":{"fold_id":fold_id,"train_start":train_start,"validation_start":val_start,"validation_end_exclusive":val_end,"threshold_selection":selection},"base":regimes["base"],"stress":regimes["stress"]})
 def aggregate(mode:str)->dict[str,Any]:
  values=[x[mode]["metrics"] for x in folds]; returns=[x["net_return"] for x in values]
  return {"aggregate_compounded_return":float(pd.Series([1+x for x in returns]).prod()-1),"mean_fold_return":float(pd.Series(returns).mean()),"worst_fold_return":min(returns),"positive_fold_ratio":sum(x>0 for x in returns)/3,"total_trade_count":sum(x["trade_count"] for x in values),"mean_trades_per_year":float(pd.Series([x["trades_per_year"] for x in values]).mean()),"mean_maximum_drawdown":float(pd.Series([x["maximum_drawdown"] for x in values]).mean()),"mean_calmar":float(pd.Series([x["calmar"] for x in values if x["calmar"] is not None]).mean()),"mean_profit_factor":float(pd.Series([x["profit_factor"] for x in values if x["profit_factor"] is not None]).mean())}
 report={"schema_version":"ams-v5-trial-v1","trial_id":trial["trial_id"],"configuration_id":configuration_id,"portfolio_profile_id":profile_id,"status":"EXECUTED","fold_results":folds,"aggregate":{"base":aggregate("base"),"stress":aggregate("stress")},"test_2025_accessed":False,"holdout_2026_accessed":False}
 path=REPORTS/f"ams-v5-{trial['trial_id'].lower()}-trial-v1.json"; write(path,report); trial.update({"trial_status":"EXECUTED","report_path":str(path.relative_to(ROOT)).replace("\\","/"),"report_sha256":file_sha256(path)}); account["executed_trials"]+=1;account["remaining_trials"]-=1
 if account["executed_trials"]+account["remaining_trials"]!=24:raise RuntimeError("Accounting invariant")
 write(LEDGER,ledger);return path

def main()->None:
 p=argparse.ArgumentParser();p.add_argument("--configuration-id",required=True);p.add_argument("--portfolio-profile-id",required=True);p.add_argument("--cost-mode",default="BOTH",choices=("BOTH","BASE","STRESS"));a=p.parse_args()
 if a.cost_mode!="BOTH":raise RuntimeError("Registered trial requires both cost modes")
 print(run_trial(a.configuration_id,a.portfolio_profile_id))
if __name__=="__main__":main()
