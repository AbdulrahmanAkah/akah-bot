#!/usr/bin/env python3
"""Independent policy-family expansion: lower-liquidity early-stage wave detection.
All thresholds predeclared in source, results exploratory and no future-based entry filtering.
"""
import sys, json
from pathlib import Path
from collections import defaultdict
import numpy as np,pandas as pd
sys.path.insert(0,'/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')
import v20_research as v
OUT=Path('/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')

def make(pairs,ids,A):
 C=A['close'];H=A['high'];LO=A['low'];BTC=ids['BTC-USDT'];ma20=A['ma20'];ma50=A['ma50'];r5=A['ret5'];r10=A['ret10'];r20=A['ret20'];r60=A['ret60'];q=A['q20prev'];rel=r20-r20[BTC];age=A['age'];rv=A['rvol'];atrp=A['atrpct'];h20=A['prev20high']
 banks={k:defaultdict(list) for k in ('early_new','early_rebound','early_leaders','early_consolidation','broad_momentum')}
 for a,p in enumerate(pairs):
  if p=='BTC-USDT' or p in v.EXCLUDED:continue
  core=(age[a]>=35)&(q[a]>=250000)&(C[a]>0)&np.isfinite(atrp[a])&(atrp[a]>.008)&(atrp[a]<.32)
  # age>=35 and no future history required; enforce signal at closed prior day.
  # Breakout above previous 10-day highest high, not previous period close (valid for every day).
  h10=np.full(C.shape[1],np.nan)
  for i in range(10,len(h10)):
   sub=H[a,i-10:i]
   if np.isfinite(sub).all():h10[i]=max(sub)
  br10=(C[a]>h10)&(np.roll(C[a],1)<=np.roll(h10,1));br20=(C[a]>h20[a])&(np.roll(C[a],1)<=np.roll(h20[a],1))
  core0=core&(C[a]>ma20[a])&np.isfinite(rv[a])&(rv[a]>.95)
  new=(br10|br20)&core0&(r5[a]>.05)&(r10[a]>.04)
  # Strong reaction after deep 30-60d slump: no requirement that BTC is bull.
  reb=br10&core0&(r20[a]<.1)&(r5[a]>.07)&(rv[a]>1.2)
  leaders=(br10|br20)&core0&(r20[a]>.12)&(rel[a]>.04)&(rv[a]>1.05)
  consol=(br20)&core0&(r20[a]>.04)&(rv[a]>1.6)&(A['std20'][a]<.055)
  broad=(new|reb|leaders)&(q[a]>400000)
  scores={
   'early_new':.4*np.clip(r5[a],-.2,1)+.2*np.clip(r20[a],-.5,4)+.14*np.log1p(np.maximum(rv[a],0)),
   'early_rebound':.6*np.clip(r5[a],-.2,1)-.5*np.clip(r20[a],-.5,1)+.25*np.log1p(np.maximum(rv[a],0)),
   'early_leaders':.8*np.clip(rel[a],-1,4)+.5*np.clip(r20[a],-1,4)+.2*np.log1p(np.maximum(rv[a],0)),
   'early_consolidation':.4*np.clip(r5[a],-.2,1)+.25*np.log1p(np.maximum(rv[a],0)),
   'broad_momentum':.6*np.clip(r5[a],-.2,1)+.4*np.clip(r20[a],-.5,4)+.12*np.log1p(np.maximum(rv[a],0))}
  for k,mask in [('early_new',new),('early_rebound',reb),('early_leaders',leaders),('early_consolidation',consol),('broad_momentum',broad)]:
   indices=np.where(mask & np.isfinite(scores[k]) & (v.np.arange(v.ST0,v.END)>=v.START-1)&(v.np.arange(v.ST0,v.END)<v.END-1))[0]
   for i in indices:banks[k][int((v.ST0+i))+1].append((float(scores[k][i]),a))
 for bank in banks.values():
  for day,ls in bank.items():ls.sort(key=lambda x:(-x[0],pairs[x[1]]))
 return banks

def main():
 pairs,ids,A=v.build();banks=make(pairs,ids,A)
 w=pd.read_csv(OUT/'RETROSPECTIVE_BIG_WAVES_AND_SIGNAL_COVERAGE.csv')
 statuses=[]
 for tag,b in banks.items():
  wave=w[(w.year==2023)&(w.multiple>=5)]
  # Signal coverage measured over ex-post wave to identify discovery mechanism; not trade success.
  covered=0;liq=0
  for r in wave.itertuples(index=False):
   if r.pair not in ids:continue
   a=ids[r.pair]
   observed=any(any(aa==a for score,aa in b.get(day,[])) for day in range(int(r.start_day),int(r.peak_day)+1))
   if observed:covered+=1
   if r.max_pre_peak_estimated_quote>=3e6 and observed:liq+=1
  statuses.append({'bank':tag,'signal_count':sum(len(x) for x in b.values()),'2023_5x_waves_with_signal':covered,'2023_5x_liquid_ge3m_waves_with_signal':liq})
 pd.DataFrame(statuses).to_csv(OUT/'EARLY_WAVE_2023_SIGNAL_COVERAGE.csv',index=False)
 print('V20_EARLY_SIGNALS',statuses,flush=True)
 specs=[]
 for tag,cap,atr,bear in [('early_new',.75,5.,True),('early_rebound',.75,4.,True),('early_leaders',.75,5.,True),('early_consolidation',.75,5.,True),('broad_momentum',.75,6.,True),('early_new',1.,6.,True)]:
  specs.append({'name':f'V20_SPEC_{tag}_{round(cap*100)}','bank':tag,'btc':.40 if cap<1 else 0.,'alt':cap,'positions':5,'atr':atr,'risk':.015,'participation':.01,'poscap':.30,'minstop':.08,'cooldown':3,'bear':bear,'trend_exit':True})
 result=[];trade_capture=[]
 for pol in specs:
  s,_,tr=v.simulate(pol,pairs,ids,A,banks,save=True);result.append(s)
  print('V20_EARLY_PORTFOLIO',pol['name'],round(s['total_return_pct'],1),'dd',round(s['max_drawdown_pct'],1),'2022',round(s['2022_pct'],1),'2023',round(s['2023_pct'],1),flush=True)
  for r in w[(w.year==2023)&(w.multiple>=5)].itertuples(index=False):
   t=tr[(tr.pair==r.pair)&(tr.entry_day>=r.start_day)&(tr.entry_day<=r.peak_day)]
   trade_capture.append({'policy':pol['name'],'pair':r.pair,'multiple':r.multiple,'liquid_ge_3m_at_some_point':r.max_pre_peak_estimated_quote>=3e6,'entered_wave':len(t)>0,'profitable_wave_trade':(t.pnl>0).any(),'net_pnl':t.pnl.sum()})
 pd.DataFrame(result).to_csv(OUT/'EARLY_STAGE_PORTFOLIO_COMPARISON.csv',index=False)
 pd.DataFrame(trade_capture).to_csv(OUT/'EARLY_STAGE_REALIZED_2023_WAVE_CAPTURE.csv',index=False)
 print('V20_EARLY_COMPLETE',flush=True)
if __name__=='__main__':main()
