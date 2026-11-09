import zipfile, io, gzip, pandas as pd, numpy as np
from collections import defaultdict
from pathlib import Path
root=Path('/mnt/data'); sources=[]
for i in [2,3]:
 z=zipfile.ZipFile(root/f'UPLOAD_THIS_AKAH_C2_364_RAW_PART_{i:04}.zip')
 for n in z.namelist():
  if not n.startswith('daily/') or not n.endswith('.csv.gz'):continue
  x=n[len('daily/'):-len('.csv.gz')]; ven,pair=x.split('_',1)
  try:
   d=pd.read_csv(io.BytesIO(gzip.decompress(z.read(n))), usecols=['unix_ms','open','high','low','close','quote_volume'])
   d=d[(d.unix_ms>=1577836800000)&(d.unix_ms<1704067200000)].sort_values('unix_ms').drop_duplicates('unix_ms')
   d=d[(d.close>0)&(d.low>0)&(d.high>0)].copy()
   sources.append((ven,pair,d))
  except Exception as e:print('FAILED',n,str(e)[:100])
venues=defaultdict(dict)
for v,p,d in sources:venues[p][v]=d
selected=[]
for p,vv in venues.items():
 if 'BINANCE' in vv: v='BINANCE'
 else:v=max(vv, key=lambda k: len(vv[k]))
 selected.append((p,v,vv[v]))
rows=[]
for p,v,d in selected:
 if len(d)<120:continue
 for skip in [0,7,30]:
  x=d.iloc[skip:].reset_index(drop=True)
  if len(x)<120:continue
  # retrospective low-to-later-high 2020--23, best possible timepoint upper bound
  closes=x.close.to_numpy(float); lows=x.low.to_numpy(float); highs=x.high.to_numpy(float)
  minlow=lows[0]; mini=0; peakmult=1.0; lo=hi=None
  minclose=closes[0];mini2=0; multclose=1; lo2=hi2=None
  for j in range(1,len(x)):
   a=highs[j]/minlow
   b=closes[j]/minclose
   if a>peakmult:peakmult=a;lo=mini;hi=j
   if b>multclose:multclose=b;lo2=mini2;hi2=j
   if lows[j]<minlow:minlow=lows[j];mini=j
   if closes[j]<minclose:minclose=closes[j];mini2=j
  q=x.quote_volume.dropna();
  rows.append({'pair':p,'venue':v,'skip_days':skip,'bars':len(x),'start':pd.to_datetime(x.unix_ms.iloc[0],unit='ms').date().isoformat(),'end':pd.to_datetime(x.unix_ms.iloc[-1],unit='ms').date().isoformat(),
  'best_low_to_future_high_x':round(peakmult,3),'best_close_to_future_close_x':round(multclose,3),
  'close_low_date':pd.to_datetime(x.unix_ms.iloc[lo2],unit='ms').date().isoformat() if lo2 is not None else '', 'close_high_date':pd.to_datetime(x.unix_ms.iloc[hi2],unit='ms').date().isoformat() if hi2 is not None else '',
  'median_daily_quote_volume':round(float(q.median()),2) if len(q) else None})
res=pd.DataFrame(rows);res.to_csv(root/'AKAH_C2_2020_2023_RETROSPECTIVE_MULTIPLES_INDEPENDENT.csv',index=False)
print('raw source series',len(sources),'assets unique',len(venues),'filtered assets',res[res.skip_days==0].shape[0])
for skip in [0,7,30]:
 t=res[res.skip_days==skip]
 print('\nSKIP',skip,'count',len(t),'close multipliers ≥5,10,100,1000',[(t.best_close_to_future_close_x>=k).sum() for k in [5,10,100,1000]], 'wick multipliers >=5,10,100,1000',[(t.best_low_to_future_high_x>=k).sum() for k in [5,10,100,1000]])
 print(t.sort_values('best_close_to_future_close_x',ascending=False).head(12)[['pair','start','best_close_to_future_close_x','best_low_to_future_high_x','median_daily_quote_volume']].to_string(index=False))
print('\nBTC',res[res.pair=='BTC-USDT'][['skip_days','best_low_to_future_high_x','best_close_to_future_close_x','start','end']].to_string(index=False))
