import sys, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import v19_replay as v, v19_fast as fast
import pandas as pd
p=Path(__file__).parent
print('WAVE_V19_BEGIN',flush=True)
D,src,_,_=v.load();F=v.features(D);pairs,ids,A=fast.to_arrays(F)
policies=[
 {'name':'V19_WAVE_NEW_40','style':'wave','alt_fraction':.40,'bear_alt':True,'atr_trail':6.,'risk':.015,'max_holdings':4},
 {'name':'V19_WAVE_NEW_60','style':'wave','alt_fraction':.60,'bear_alt':True,'atr_trail':8.,'risk':.014,'max_holdings':5},
]
allrows=[]
for pol in policies:
 bank=fast.bank_ids(v.make_bank(F,pol),ids)
 print('POL',pol['name'],'signals',sum(map(len,bank.values())),flush=True)
 for alloc in (1.,.5):
  px=dict(pol);px['name']=pol['name']+('_BTC50' if alloc==.5 else '')
  result,t,n=fast.replay(px,bank,pairs,ids,A,btc_alloc=alloc);allrows.append(result)
  t.to_csv(p/(px['name']+'_TRADES.csv'),index=False);n.to_csv(p/(px['name']+'_NAV.csv'),index=False)
  double,_,_=fast.replay(px,bank,pairs,ids,A,btc_alloc=alloc,fee=.006,slip=.002);allrows.append(double)
  excluded=result['top3_pairs'].split(',') if result['top3_pairs'] else []
  excl,_,_=fast.replay(px,bank,pairs,ids,A,btc_alloc=alloc,fee=.006,slip=.002,exclude=tuple(excluded));allrows.append(excl)
  print('WAVE_RESULT',px['name'], 'BASE',round(result['total_return_pct'],2),'DD',round(result['maxdd_pct'],2),'2022',round(result['ret_2022'],2),'2023',round(result['ret_2023'],2),'2X',round(double['total_return_pct'],2),'EXC3_2X',round(excl['total_return_pct'],2),flush=True)
  pd.DataFrame(allrows).to_csv(p/'V19_WAVE_POLICY_RESULTS.csv',index=False)
print('DONE',len(allrows))
