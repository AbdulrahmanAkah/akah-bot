# ruff: noqa
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
import pandas as pd
from spotbot.research.ams_v5_native_engine import build_features,assert_boundary
ROOT=Path.cwd();REPORTS=ROOT/"reports/research"
def write(p,v):
 t=json.dumps(v,indent=2,sort_keys=True)+"\n";h,x=tempfile.mkstemp(dir=p.parent,prefix=".tmp",suffix=".json")
 try:
  with os.fdopen(h,"w",encoding="utf-8")as f:f.write(t)
  os.replace(x,p)
 except: 
  if os.path.exists(x):os.unlink(x)
  raise
def main():
 reg=json.loads((REPORTS/"ams-v3-4h-dataset-registration-v1.json").read_text())["datasets"];bars=pd.read_parquet(ROOT/reg["four_hour"]["path"]);avail=pd.read_parquet(ROOT/reg["availability"]["path"]);panel=build_features(bars.loc[bars.symbol.isin(["BTC","ETH","SOL"])],avail.loc[avail.symbol.isin(["BTC","ETH","SOL"])]);assert_boundary(panel);write(REPORTS/"ams-v5r1-native-engine-integration-v1.json",{"status":"PASS","symbols":["BTC","ETH","SOL"],"rows":len(panel),"families":panel.family.value_counts().to_dict(),"score_bounds":[float(panel.score_no_fib.min()),float(panel.score_soft_fib.max())],"fibonacci_bounds":[float(panel.fib.min()),float(panel.fib.max())],"test_2025_accessed":False,"holdout_2026_accessed":False})
if __name__=="__main__":main()
