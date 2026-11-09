import zipfile,gzip,io,pandas as pd,numpy as np
from pathlib import Path
root=Path('/mnt/data'); data={}
for j in [2,3]:
 z=zipfile.ZipFile(root/f'UPLOAD_THIS_AKAH_C2_364_RAW_PART_{j:04}.zip')
 for n in z.namelist():
  if not n.startswith('daily/') or not n.endswith('.csv.gz'):continue
  ven,pair=n[6:-7].split('_',1)
  try:
   d=pd.read_csv(io.BytesIO(gzip.decompress(z.read(n))),usecols=['unix_ms','open','high','low','close','quote_volume']).sort_values('unix_ms')
   d=d[(d.unix_ms>=1577836800000)&(d.unix_ms<1704067200000)].drop_duplicates('unix_ms')
   if len(d)>=120 and (d.close>0).all():data[(ven,pair)]=d.reset_index(drop=True)
  except Exception as e:print('error',n,str(e)[:150])
venue_by={p:('BINANCE' if ('BINANCE',p) in data else 'KUCOIN') for v,p in data}
records=[];bad=0
for pair,ven in venue_by.items():
 d=data[(ven,pair)];s=d.close.to_numpy();h=d.high.to_numpy();q=d.quote_volume.to_numpy();op=d.open.to_numpy()
 min_close=s[0];mi=0;best=1.0;lo=hi=0
 for j in range(1,len(s)):
  r=s[j]/min_close
  if r>best:best=r;lo=mi;hi=j
  if s[j]<min_close:min_close=s[j];mi=j
 if hi<=lo or lo+1>=len(s):continue
 # first confirmed close at > 20d historic high AFTER trough, with minimum 20 days historical prior
 jbreak=None
 for j in range(max(20,lo+1),hi):
  if s[j]>np.nanmax(h[j-20:j]):jbreak=j;break
 # earliest time after low, price up 20% and from prior historic information
 j20=None
 for j in range(lo+1,hi):
  if s[j]>=s[lo]*1.20:j20=j;break
 def event(i):
  if i is None or i+1>=len(d):return (None,None,None)
  md=np.nanmedian(q[max(0,i-19):i+1]);return (round(float(s[hi]/op[i+1]),3) if op[i+1]>0 else None,round(float(md)) if np.isfinite(md) else None,str(pd.to_datetime(d.unix_ms.iloc[i],unit='ms').date()))
 closemult,liquidity,bd=event(jbreak);m20,liq20,d20=event(j20)
 records.append({'pair':pair,'venue':ven,'ideal_close_multiple':round(float(best),3),'trough_date':str(pd.to_datetime(d.unix_ms.iloc[lo],unit='ms').date()),'peak_date':str(pd.to_datetime(d.unix_ms.iloc[hi],unit='ms').date()),'breakout_20d_date':bd,'max_if_buy_after_first_20d_breakout':closemult,'past_20d_median_daily_quote_usd':liquidity,'first_20pct_up_date':d20,'max_if_buy_after_20pct_rebound':m20,'20pct_trigger_past_20d_liquidity':liq20})
res=pd.DataFrame(records)
res.to_csv(root/'AKAH_C2_WAVE_ENTRY_CEILING_2020_2023.csv',index=False)
for threshold in [10,100]:
 t=res[(res.ideal_close_multiple>=threshold)&(res.pair!='LUNA-USDT')]
 print('>=',threshold, 'count',len(t),'20d breakout',t.max_if_buy_after_first_20d_breakout.notna().sum(), 'upper median',t.max_if_buy_after_first_20d_breakout.median(),'>=5x left',sum(t.max_if_buy_after_first_20d_breakout>=5),'past_liquid $1m',sum(t.past_20d_median_daily_quote_usd>=1000000))
 print(t.sort_values('ideal_close_multiple',ascending=False).head(15)[['pair','ideal_close_multiple','max_if_buy_after_first_20d_breakout','past_20d_median_daily_quote_usd']].to_string(index=False))
print('ALL breakouts',res.max_if_buy_after_first_20d_breakout.notna().sum())
