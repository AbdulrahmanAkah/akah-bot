# ruff: noqa
from __future__ import annotations
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_ams_v5_trial import LEDGER,load_panel,run_trial
def main()->None:
 ledger=json.loads(LEDGER.read_text());panel=load_panel()
 for trial in ledger["trial_plan"]:
  if trial["trial_status"]=="REGISTERED_NOT_EXECUTED":run_trial(trial["configuration_id"],trial["portfolio_profile_id"],panel=panel)
if __name__=="__main__":main()
