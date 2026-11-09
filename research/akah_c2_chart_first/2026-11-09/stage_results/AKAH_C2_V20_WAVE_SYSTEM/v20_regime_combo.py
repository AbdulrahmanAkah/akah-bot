#!/usr/bin/env python3
"""One predeclared bullish-regime vs all-regime comparison, same source and cash accounting."""
from pathlib import Path
import sys
from collections import defaultdict
import pandas as pd
sys.path.insert(0,'/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')
import v20_research as v
import v20_early_trends as early
OUT=Path('/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')

def main():
 pairs,ids,A=v.build(); banks=early.make(pairs,ids,A);full=v.candidate_bank(pairs,ids,A)
 combo=defaultdict(list)
 for day in set(banks['early_new'])|set(full['continuation']):
  seen={}
  for score,a in banks['early_new'].get(day,()):seen[a]=.5+score
  for score,a in full['continuation'].get(day,()):seen[a]=max(seen.get(a,-1e9),.5+score)
  combo[day]=sorted([(score,a) for a,score in seen.items()],key=lambda r:(-r[0],pairs[r[1]]))
 banks['combined']=combo
 specs=[]
 for tag in ('early_new','early_leaders','combined'):
  for bear in (False,True):
   specs.append({'name':f'V20_REG_{tag}_bear{int(bear)}','bank':tag,'btc':.5,'alt':.7,'positions':4,'atr':5.5,'risk':.015,'participation':.003,'poscap':.30,'minstop':.08,'cooldown':4,'bear':bear,'trend_exit':True})
 res=[]
 for pol in specs:
  o,_,tr=v.simulate(pol,pairs,ids,A,banks,save=True)
  res.append(o);print('V20_REG',pol['name'],round(o['total_return_pct'],2),round(o['max_drawdown_pct'],2),round(o['2022_pct'],2),round(o['2023_pct'],2),flush=True)
 pd.DataFrame(res).to_csv(OUT/'V20_REGIME_PROSPECTIVE_POLICY_RESEARCH.csv',index=False)
 print('V20_REG_COMPLETE',flush=True)
if __name__=='__main__':main()
