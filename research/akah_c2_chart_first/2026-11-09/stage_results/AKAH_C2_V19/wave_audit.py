from pathlib import Path
import sys, pandas as pd, numpy as np
sys.path.insert(0,str(Path(__file__).parent));import v19_replay as v
D,src,_,_=v.load();F=v.features(D)
w=pd.read_csv('/mnt/data/AKAH_C2_V12_DURABLE_CLOSE_RALLIES.csv')
w=w[(w.year==2023)&(w.max_later_close_multiple_7d>=5)].copy()
for field in ('venue_used','max_qprev','max_rvol','valid_bar_days','first_eligible_day_1m','first_eligible_day_3m','first_eligible_day_5m','gain_remaining_first_eligible_1m','gain_remaining_first_eligible_3m'):
 w[field]=np.nan if field!='venue_used' else ''
for idx,r in w.iterrows():
 if r.pair not in F:continue
 d=F[r.pair]; lo=int(pd.Timestamp(r.trough_date,tz='UTC').value//10**6//v.DAY);hi=int(pd.Timestamp(r.peak_date,tz='UTC').value//10**6//v.DAY)
 s=d.loc[lo:hi];w.at[idx,'venue_used']=src[r.pair];w.at[idx,'valid_bar_days']=s.close.notna().sum();w.at[idx,'max_qprev']=s.q20prev.max();w.at[idx,'max_rvol']=s.rvol.max()
 for th in (1e6,3e6,5e6):
  e=s[s.q20prev>=th]
  if len(e):
   first=e.index[0];w.at[idx,f'first_eligible_day_{int(th/1e6)}m']=first
   if th in (1e6,3e6) and np.isfinite(d.loc[first].close) and np.isfinite(d.loc[hi].close):w.at[idx,f'gain_remaining_first_eligible_{int(th/1e6)}m']=d.loc[hi].close/d.loc[first].close-1
w.to_csv('/mnt/data/AKAH_C2_V19/V19_FIVE_X_WAVE_ELIGIBILITY.csv',index=False)
print('five_x',len(w),'in data',w.valid_bar_days.notna().sum(),'volume 1m',int((w.max_qprev>=1e6).sum()),'3m',int((w.max_qprev>=3e6).sum()),'5m',int((w.max_qprev>=5e6).sum()))
print(w[['pair','max_later_close_multiple_7d','venue_used','max_qprev','gain_remaining_first_eligible_3m']].sort_values('max_later_close_multiple_7d',ascending=False).head(25).to_string(index=False))
