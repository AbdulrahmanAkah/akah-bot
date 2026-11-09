from pathlib import Path
import sys
from collections import defaultdict
import pandas as pd
sys.path.insert(0,'/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')
import v20_research as v
import v20_early_trends as early
OUT=Path('/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')
pairs,ids,A=v.build();bb=early.make(pairs,ids,A);orig=v.candidate_bank(pairs,ids,A)
combo=defaultdict(list)
for day in set(bb['early_new'])|set(orig['continuation']):
 p={}
 for sc,a in bb['early_new'].get(day,[]):p[a]=.5+sc
 for sc,a in orig['continuation'].get(day,[]):p[a]=max(.5+sc,p.get(a,-1e9))
 combo[day]=sorted([(score,a) for a,score in p.items()],key=lambda x:(-x[0],pairs[x[1]]))
bb['combined']=combo
pol={'name':'V20_REG_combined_bear0','bank':'combined','btc':.5,'alt':.7,'positions':4,'atr':5.5,'risk':.015,'participation':.003,'poscap':.30,'minstop':.08,'cooldown':4,'bear':False,'trend_exit':True}
results=[]
base,_,_=v.simulate(pol,pairs,ids,A,bb);ex=base['top3_alt_profit_pairs'].split(',')
for label,fee,slip,omit in [('BASE',.003,.001,()),('DOUBLE_COST',.006,.002,()),('NO_TOP3',.003,.001,ex),('DOUBLE_COST_NO_TOP3',.006,.002,ex)]:
 out,_,_=v.simulate({**pol,'name':pol['name']+'_'+label},pairs,ids,A,bb,fee=fee,slip=slip,exclude=omit,save=True)
 out['scenario']=label;results.append(out)
 print('V20_REG_STRESS',label,round(out['total_return_pct'],2),round(out['max_drawdown_pct'],2),round(out['2022_pct'],2),round(out['2023_pct'],2),flush=True)
pd.DataFrame(results).to_csv(OUT/'V20_COMBINED_REGIME_STRESS.csv',index=False)
