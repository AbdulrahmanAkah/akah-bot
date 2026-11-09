from pathlib import Path
import sys,json,pandas as pd,numpy as np
sys.path.insert(0,str(Path(__file__).parent))
import v19_replay as v,v19_fast as f
D,_,_,_=v.load();p=dict(v.POLICIES[4]);F=v.features(D);pairs,ids,A=f.to_arrays(F);basebank=f.bank_ids(v.make_bank(F,p),ids)
r1,t1,n1=f.replay(p,basebank,pairs,ids,A,btc_alloc=.5)
cut=int(pd.Timestamp('2023-07-01',tz='UTC').value//10**6//v.DAY)
D2={x:y.copy() for x,y in D.items()}
for x,fac in [('BTC-USDT',1.9),('SOL-USDT',.25),('INJ-USDT',3.2),('AVAX-USDT',.6)]:
 if x not in D2:continue
 d=D2[x];sel=d.index>=cut
 for col in ['open','high','low','close']:d.loc[sel,col]=d.loc[sel,col]*fac
F2=v.features(D2);pairs2,ids2,A2=f.to_arrays(F2);bank2=f.bank_ids(v.make_bank(F2,p),ids2)
r2,t2,n2=f.replay(p,bank2,pairs2,ids2,A2,btc_alloc=.5)
assert pairs==pairs2
v1=n1[n1.day<cut].nav.to_numpy();v2=n2[n2.day<cut].nav.to_numpy()
maxdiff=float(np.max(np.abs(v1-v2)));assert maxdiff<1e-6,(maxdiff,len(v1))
# Compare only fills (entry+exit) strictly earlier than cut; opposite bar after cut may close prior entry, correctly ignored.
trade_a=t1[t1.exit_day<cut].sort_values(['pair','entry_day','exit_day'])
trade_b=t2[t2.exit_day<cut].sort_values(['pair','entry_day','exit_day'])
assert len(trade_a)==len(trade_b)
assert np.allclose(trade_a.net.to_numpy(),trade_b.net.to_numpy(),atol=1e-7)
report={'status':'PASS_PREFIX_INVARIANCE','cut_day':'2023-07-01','policies_checked':[p['name']],'modified_future_assets':['BTC','SOL','INJ','AVAX'],'daily_equity_values_checked':len(v1),'trades_closed_before_cut_checked':len(trade_a),'max_pre_cut_usdt_difference':maxdiff,'scope':'only future mutated, not independent PIT test'}
(Path(__file__).parent/'V19_PREFIX_INVARIANCE.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report))
