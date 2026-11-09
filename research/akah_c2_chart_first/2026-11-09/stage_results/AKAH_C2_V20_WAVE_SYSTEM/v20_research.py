#!/usr/bin/env python3
"""AKAH C2 V20: no-2024, no-network, read-only multi-policy wave opportunity lab.
Historical/retrospective only; NO live/PIT claim. For every entry, inputs end at prior day's close.
"""
import json, math, hashlib, time
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
import sys
sys.path.insert(0,'/mnt/data/AKAH_C2_V19')
import v19_replay as v
OUT=Path('/mnt/data/AKAH_C2_V20_WAVE_SYSTEM');OUT.mkdir(exist_ok=True)
ST0=v.ST0;START=v.START; END=v.END; DAY=v.DAY
EXCLUDED={'LUNA-USDT','LUNC-USDT','UST-USDT','USTC-USDT','BTT-USDT','BTTOLD-USDT','NULS-USDT'} # split identities / re-denomination risk; extend only with audited source lineage
KEYS=['open','high','low','close','atr14','ma20','ma50','ma200','ret5','ret10','ret20','ret60','q20prev','rvol','prev20high','prev55high','atrpct']

def build():
    data,venues,src,errors=v.load(); D=v.features(data)
    pairs=sorted(D)
    arr={k:np.stack([D[p][k].to_numpy(dtype=np.float64) for p in pairs]) for k in KEYS}
    P=len(pairs); T=len(v.DAYS); idx={p:i for i,p in enumerate(pairs)};btc=idx['BTC-USDT']
    # Only from past: 14-day close RSI, rolling range and 20-day dollar volume, 14d buy pressure.
    rsi=[];max90=[];stdev=[];age=[];quote_native=[]
    for p in pairs:
        d=D[p];c=d.close;chg=c.diff();up=chg.clip(lower=0).rolling(14,min_periods=14).mean();dn=(-chg.clip(upper=0)).rolling(14,min_periods=14).mean()
        ratio=up/dn.replace(0,np.nan);r=100-100/(1+ratio)
        rsi.append(r.to_numpy(dtype=np.float64));max90.append(d.high.shift(1).rolling(90,min_periods=90).max().to_numpy(dtype=np.float64))
        stdev.append((c.pct_change(fill_method=None).rolling(20,min_periods=20).std()).to_numpy(dtype=np.float64))
        age.append((c.notna().cumsum()).to_numpy(dtype=np.int32));quote_native.append(d.q_native_available.to_numpy(dtype=bool))
    arr['rsi14']=np.stack(rsi);arr['prev90high']=np.stack(max90);arr['std20']=np.stack(stdev);arr['age']=np.stack(age);arr['quote_native']=np.stack(quote_native)
    arrays_json={'pairs':P,'day_bars':int(np.isfinite(arr['close']).sum()),'original_sources':len(src),'failures':errors,'venue_pairs':venues,'EXCLUDED_SYMBOLS':sorted(EXCLUDED),'pit_certified':False,'completed_asof_rules':True,'no_2024':True,'timestamped':int(time.time())}
    (OUT/'SOURCE_AND_DATA_STATUS.json').write_text(json.dumps(arrays_json,ensure_ascii=False,indent=2))
    return pairs,idx,arr

def candidate_bank(pairs,ids,A):
    C=A['close']; ma20=A['ma20'];ma50=A['ma50'];ret5=A['ret5'];ret20=A['ret20'];ret60=A['ret60'];rvol=A['rvol'];q=A['q20prev'];atrp=A['atrpct'];b=ids['BTC-USDT'];H20=A['prev20high']; H55=A['prev55high'];H90=A['prev90high'];age=A['age'];rsi=A['rsi14']
    banks={k:defaultdict(list) for k in ('continuation','reversal','reclaim','all','highconviction')}
    stats=[]
    for a,p in enumerate(pairs):
        if p=='BTC-USDT' or p in EXCLUDED:continue
        # Causal native dollar volume preferred; proxy otherwise labeled as estimate; execution NOT certified.
        valid=(C[a]>0)&(age[a]>=100)&(q[a]>=1e6)&np.isfinite(atrp[a])&(atrp[a]>=.007)&(atrp[a]<=.28)&np.isfinite(ret60[a])&(A['rsi14'][a]>0)
        rel20=ret20[a]-ret20[b];rel60=ret60[a]-ret60[b]
        br20=(C[a]>H20[a]) & (np.roll(C[a],1)<=np.roll(H20[a],1));br55=(C[a]>H55[a]) & (np.roll(C[a],1)<=np.roll(H55[a],1))
        breakout=(br20|br55)
        trend=(C[a]>ma50[a])&(ma20[a]>ma50[a])&(ret20[a]>.08)
        revers=(breakout)&(ret60[a]<-.15)&(ret5[a]>.05)&(C[a]>ma20[a])
        reclaim=(np.isfinite(A['low'][a])&(A['low'][a]<ma20[a])&(C[a]>ma20[a])&(ret20[a]>.08)&(C[a]>ma50[a])&(ret5[a]>.015)&(rvol[a]>1.15))
        cont=breakout & trend & (rel20>-.05)
        strong=(br55|((C[a]>H90[a])&(ret60[a]>.18))) & trend & (rel20>.03) & (rvol[a]>1.25)
        groups={'continuation':cont,'reversal':revers,'reclaim':reclaim,'all':(cont|revers|reclaim),'highconviction':strong}
        # scoring only prior close features; reduce instability of huge listing returns with clipping
        score=(0.8*np.clip(rel20,-.5,2)+.5*np.clip(rel60,-.5,3)+.4*np.clip(ret5[a],-.2,1.5)+.30*np.clip(np.log(np.maximum(rvol[a],.1)), -2,2)+0.10*(C[a]>ma50[a]) + 0.05*br55) 
        for tag,mask in groups.items():
            ix=np.where(valid & mask & np.isfinite(score) & (v.DAYS>=START-1) & (v.DAYS<END-1))[0]
            for i in ix:
                banks[tag][int(v.DAYS[i])+1].append((float(score[i]),a))
        stats.append((p,int(valid.sum()),int((valid & cont).sum()),int((valid & revers).sum()),int((valid & reclaim).sum()),int((valid & strong).sum()),float(np.nanmedian(q[a])) if np.isfinite(q[a]).any() else np.nan))
    for tag in banks:
        for day in banks[tag]:banks[tag][day].sort(key=lambda it:(-it[0],pairs[it[1]]))
    pd.DataFrame(stats,columns=['pair','eligible_days','continuation_signals','reversal_signals','reclaim_signals','highconviction_signals','median_quoted_or_estimated_dollar_volume']).to_csv(OUT/'ASOF_SIGNAL_COUNTS.csv',index=False)
    return banks

# Broker is deliberately rebuilt rather than reusing V19 replay, to test different portfolio state and exit timing.
def simulate(policy,pairs,ids,A,banks,fee=.003,slip=.001,exclude=(),start=START,end=END,save=False):
    O=A['open'];H=A['high'];L=A['low'];C=A['close'];ATR=A['atr14'];MA20=A['ma20'];MA50=A['ma50'];MA200=A['ma200'];Q=A['q20prev'];btc=ids['BTC-USDT'];exclude_ids={ids[p] for p in exclude if p in ids}
    cash=100000.;bu=0.;bbasis=0.;bstop=0.;bhigh=0.;bcool=0;positions={};cool={};closed=[];daily=[];pnl=defaultdict(float);maxnav=100000.;dd=0;reentry=0;prvexited=set();last_holding={};miss=0;events_eligible=0;gaploss=0
    btc_fraction=policy['btc'];alt_fraction=policy['alt'];maxhold=policy['positions']; stopmult=policy['atr'];risk=policy['risk'];participation=policy['participation'];active_bear=policy.get('bear',False)
    sidx=start-ST0;eidx=end-ST0
    def asset_open(a,i):
        x=O[a,i];return x if np.isfinite(x) else positions[a]['last']
    def nav_open(i):return cash+bu*O[btc,i]+sum(x['units']*asset_open(a,i) for a,x in positions.items())
    for i in range(sidx,eidx):
        day=ST0+i;j=i-1
        if not (np.isfinite(O[btc,i]) and np.isfinite(C[btc,i])):raise AssertionError(('BTC missing',day))
        market_on=bool(np.isfinite(C[btc,j]) and np.isfinite(MA200[btc,j]) and C[btc,j]>MA200[btc,j]);
        # Prior-close trend and gap exits at today's open (before funding today's entries)
        for a,h in list(positions.items()):
            px=O[a,i]
            if not np.isfinite(px):h['missing']+=1;miss+=1;continue
            trend_exit=bool(policy.get('trend_exit',False) and np.isfinite(C[a,j]) and np.isfinite(MA50[a,j]) and C[a,j]<MA50[a,j] and MA20[a,j]<MA50[a,j])
            if h['missing'] or px<=h['stop'] or trend_exit:
                fill=px*(1-slip);pr=fill*h['units']*(1-fee);cash+=pr;gain=pr-h['basis'];pnl[a]+=gain
                closed.append((pairs[a],h['entry'],day,h['basis'],pr,gain,'open_gap_or_trend',h['entry_score'],h['high'],h['adds']))
                del positions[a];cool[a]=day+policy['cooldown'];prvexited.add(a)
            else:h['missing']=0
        # BTC exits at open
        if bu and (not market_on or O[btc,i]<=bstop):
            pr=bu*O[btc,i]*(1-slip)*(1-fee);cash+=pr;closed.append(('BTC-USDT',-1,day,bbasis,pr,pr-bbasis,'btc_open',0,bhigh,0));bu=0;bbasis=0;bcool=day+7
        # enter ALTs at open only on complete previous day's event
        active=market_on or active_bear
        if active and alt_fraction>0 and len(positions)<maxhold:
            for score,a in banks[policy['bank']].get(day,()):
                if a in exclude_ids or a in positions or day<cool.get(a,0) or len(positions)>=maxhold:continue
                px=O[a,i];at=ATR[a,j];q=Q[a,j]
                if not (np.isfinite(px) and np.isfinite(at) and np.isfinite(q) and px>0 and C[a,j]>0):continue
                if px/C[a,j]>1.12:continue
                entry=px*(1+slip);dist=max(policy['minstop']*entry,stopmult*at);dist=min(.38*entry,dist)
                en=nav_open(i);current=sum(h['units']*asset_open(b,i) for b,h in positions.items())
                qsize=min(policy['poscap']*en,risk*en/(dist/entry),participation*q,max(0,alt_fraction*en-current))
                if qsize<min(250.,.002*en):continue
                need=qsize*(1+fee)-cash
                if need>0 and bu>0:
                    qty=min(bu,need/(O[btc,i]*(1-slip)*(1-fee)))
                    cash+=qty*O[btc,i]*(1-slip)*(1-fee)
                    bbasis*=max(0,(bu-qty)/bu);bu-=qty
                    if bu<1e-12:bu=0.;bbasis=0.
                qsize=min(qsize,max(0,cash/(1+fee)))
                if qsize<min(250.,.002*en):continue
                units=qsize/entry;spent=qsize*(1+fee);cash-=spent
                positions[a]={'units':units,'basis':spent,'entry':day,'entry_score':score,'stop':entry-dist,'high':entry,'last':entry,'adds':0,'entry_price':entry,'missing':0,'entry_risk':dist/entry}
                if a in prvexited:reentry+=1;prvexited.discard(a)
        # BTC core uses remaining cash up to prescribed fraction; no forward knowledge
        if market_on and day>=bcool and btc_fraction>0 and cash>200:
            budget=min(cash/(1+fee),max(0,btc_fraction*nav_open(i)-bu*O[btc,i]))
            if budget>250:
                px=O[btc,i]*(1+slip)
                if bu==0:bhigh=px;bstop=px-max(.04*px,6*ATR[btc,j])
                bbasis+=budget*(1+fee);bu+=budget/px;cash-=budget*(1+fee)
        # intraday pre-set stop (no redeploy intraday proceeds); update after current bar closed
        for a,h in list(positions.items()):
            if not np.isfinite(L[a,i]) or not np.isfinite(O[a,i]) or not np.isfinite(C[a,i]):continue
            if L[a,i]<=h['stop']:
                fill=min(O[a,i],h['stop'])*(1-slip);pr=h['units']*fill*(1-fee);cash+=pr;gain=pr-h['basis'];pnl[a]+=gain
                closed.append((pairs[a],h['entry'],day,h['basis'],pr,gain,'intraday_stop',h['entry_score'],h['high'],h['adds']))
                if fill < h['stop']*(1-slip)*.975:gaploss+=1
                del positions[a];cool[a]=day+policy['cooldown'];prvexited.add(a)
            else:
                h['high']=max(h['high'],H[a,i]);h['last']=C[a,i]
                dist=max(policy['minstop']*C[a,i],stopmult*ATR[a,i]);dist=min(.38*C[a,i],dist)
                h['stop']=max(h['stop'],h['high']-dist)
                # pyramiding at next day's open only: pending from close, implemented via bank? no forward; no pyramiding here
        if bu:
            if L[btc,i]<=bstop:
                x=min(O[btc,i],bstop)*(1-slip);pr=bu*x*(1-fee);cash+=pr
                closed.append(('BTC-USDT',-1,day,bbasis,pr,pr-bbasis,'btc_intraday',0,bhigh,0));bu=0;bbasis=0;bcool=day+7
            else:
                bhigh=max(bhigh,H[btc,i]);bstop=max(bstop,bhigh-max(.04*C[btc,i],6*ATR[btc,i]))
        nav=cash+bu*C[btc,i]+sum(h['units']*(C[a,i] if np.isfinite(C[a,i]) else h['last']) for a,h in positions.items())
        maxnav=max(maxnav,nav);dd=min(dd,nav/maxnav-1)
        daily.append((day,nav,cash,bu*C[btc,i],nav-cash-bu*C[btc,i],len(positions)))
        if cash<-0.01 or len(positions)>maxhold:raise AssertionError(('account_invariant',day,cash,len(positions)))
    # End audit: liquidation prices use last close of 2023; double-run evaluations each scoped period need mark-to-market consistency
    for a,h in positions.items():
        x=(C[a,eidx-1] if np.isfinite(C[a,eidx-1]) else h['last'])*(1-slip);pr=h['units']*x*(1-fee);cash+=pr;gain=pr-h['basis'];pnl[a]+=gain
        closed.append((pairs[a],h['entry'],ST0+eidx-1,h['basis'],pr,gain,'censored_end_liquidation',h['entry_score'],h['high'],h['adds']))
    if bu:
        x=C[btc,eidx-1]*(1-slip);pr=bu*x*(1-fee);cash+=pr;closed.append(('BTC-USDT',-1,ST0+eidx-1,bbasis,pr,pr-bbasis,'censored_end_liquidation',0,bhigh,0))
    navdf=pd.DataFrame(daily,columns=['day','nav','cash','btc_value','alt_value','n_alt']);trdf=pd.DataFrame(closed,columns=['pair','entry_day','exit_day','spent','proceeds','pnl','reason','entry_score','high_in_trade','add_count'])
    ret=(cash/100000.-1)*100;dates=pd.to_datetime(navdf.day*DAY,unit='ms',utc=True);yrs={}
    prev=100000.
    for year in sorted(dates.dt.year.unique()):
        equity=float(navdf.loc[dates.dt.year.eq(year),'nav'].iloc[-1]);yrs[f'{year}_pct']=(equity/prev-1)*100;prev=equity
    # Yearly NAV uses close MTM; terminal return final liquidation is additionally costed
    top=[(pairs[a],float(g)) for a,g in sorted(pnl.items(),key=lambda kv:-kv[1])[:6]]
    out={'name':policy['name'],'style':policy['bank'],'fee_each_side':fee,'slippage_each_side':slip,'total_return_pct':ret,'max_drawdown_pct':dd*100,'trades':len(trdf),'alt_trades':int(trdf.pair.ne('BTC-USDT').sum()),'win_rate_alt':float((trdf.loc[trdf.pair.ne('BTC-USDT'),'pnl']>0).mean()) if (trdf.pair!='BTC-USDT').sum() else None,'top3_alt_profit_pairs':','.join(a for a,_ in top[:3]),'top3_alt_profit_sum':sum(g for _,g in top[:3]),'reentries':reentry,'missing_bar_days':miss,'gapped_stops':gaploss,'start':start,'end_exclusive':end,**yrs}
    if save:
        navdf.to_csv(OUT/(policy['name']+'_NAV.csv'),index=False)
        trdf.to_csv(OUT/(policy['name']+'_TRADES.csv'),index=False)
    return out,navdf,trdf

def wave_audit(pairs,ids,A,banks):
    # Fully ex-post price opportunities, never used as a signal source.
    C=A['close'];Q=A['q20prev'];results=[]
    for a,p in enumerate(pairs):
        if p=='BTC-USDT' or p in EXCLUDED:continue
        idx=np.arange(START-ST0,END-ST0)
        cc=C[a,idx];d=np.isfinite(cc)
        if int(d.sum())<90:continue
        x=cc.copy();x[~d]=np.nan
        # strictly time-ordered min-close to maximum subsequent close within a year
        for year in (2020,2021,2022,2023):
            ys=int(pd.Timestamp(f'{year}-01-01',tz='UTC').value//10**6//DAY)-ST0
            ye=int(pd.Timestamp(f'{year+1}-01-01',tz='UTC').value//10**6//DAY)-ST0
            lows=np.inf;lowi=-1;best=1;st=-1;peak=-1
            for i in range(ys,ye):
                pr=C[a,i]
                if not np.isfinite(pr) or pr<=0:continue
                if lowi>=0 and pr/lows>best:
                    best=pr/lows;st=lowi;peak=i
                if pr<lows:lows=pr;lowi=i
            if best<3 or st<0 or peak<st:continue
            start_day=ST0+st;top_day=ST0+peak
            row={'pair':p,'year':year,'multiple':best,'start_day':start_day,'peak_day':top_day,'duration_days':peak-st,'max_pre_peak_estimated_quote':float(np.nanmax(Q[a,st:peak+1])) if np.isfinite(Q[a,st:peak+1]).any() else np.nan}
            for tag,b in banks.items():
                signal_days=[day for day,items in b.items() if start_day<=day<=top_day and any(aa==a for sc,aa in items)]
                row[f'{tag}_first_signal_day']=min(signal_days) if signal_days else None
                row[f'{tag}_theoretical_remaining_multiple']=float(C[a,peak]/A['open'][a,min(signal_days)-ST0]) if signal_days and np.isfinite(A['open'][a,min(signal_days)-ST0]) else np.nan
            results.append(row)
    df=pd.DataFrame(results)
    df.to_csv(OUT/'RETROSPECTIVE_BIG_WAVES_AND_SIGNAL_COVERAGE.csv',index=False)
    return df

def policies():
    specs=[]
    for tag,bear in [('continuation',False),('reversal',True),('all',True),('highconviction',False),('reclaim',False)]:
        for cap in [.60,1.0]:
            specs.append({'name':f'V20_{tag}_{int(cap*100)}','bank':tag,'btc':0. if cap==1 else .50,'alt':cap,'positions':4,'atr':5. if tag!='highconviction' else 6.,'risk':.018,'participation':.003,'poscap':.30,'minstop':.08,'cooldown':3,'bear':bear,'trend_exit':True})
    specs.append({'name':'V20_ALL_WIDE','bank':'all','btc':.5,'alt':.75,'positions':4,'atr':8.,'risk':.018,'participation':.003,'poscap':.30,'minstop':.08,'cooldown':3,'bear':True,'trend_exit':False})
    specs.append({'name':'V20_ALL_TIGHT','bank':'all','btc':.5,'alt':.75,'positions':4,'atr':3.,'risk':.018,'participation':.003,'poscap':.30,'minstop':.055,'cooldown':3,'bear':True,'trend_exit':True})
    specs.append({'name':'V20_BTC_CORE','bank':'continuation','btc':1.,'alt':0.,'positions':0,'atr':6.,'risk':0.,'participation':.003,'poscap':.30,'minstop':.08,'cooldown':3,'bear':False,'trend_exit':True})
    return specs

def main():
    print('V20_BUILD_SOURCE',flush=True);pairs,ids,A=build();print('V20_SOURCE_PAIRS',len(pairs),'BAR_ROWS',np.isfinite(A['close']).sum(),flush=True)
    banks=candidate_bank(pairs,ids,A);print('V20_SIGNAL_COUNTS',[(x,sum(len(l) for l in b.values())) for x,b in banks.items()],flush=True)
    w=wave_audit(pairs,ids,A,banks)
    print('V20_WAVES',len(w),'GE_10X',sum(w.multiple>=10),flush=True)
    specs=policies();train_end=int(pd.Timestamp('2022-01-01',tz='UTC').value//10**6//DAY)
    # PRE-REGISTER FIRST STAGE: 2020-21 research, 2022-23 stress; acknowledge prior work already used both.
    rows=[]
    for p in specs:
        o,nav,tr=simulate(p,pairs,ids,A,banks)
        rows.append(o);print('V20_RUN',p['name'],'ret',round(o['total_return_pct'],2),'dd',round(o['max_drawdown_pct'],2),'22',round(o['2022_pct'],2),'23',round(o['2023_pct'],2),'alts',o['alt_trades'],flush=True)
    pd.DataFrame(rows).to_csv(OUT/'V20_POLICY_COMPARISON.csv',index=False)
    # Select one based ONLY 2020-21 results for illustrative time-split; nevertheless 2022-23 was repeatedly seen in earlier project's research.
    choices=[r for r in rows if r['name']!='V20_BTC_CORE'];selected=max(choices,key=lambda r:(1+r['2020_pct']/100)*(1+r['2021_pct']/100)-1 + min(0,r['max_drawdown_pct']+40)*.01)
    s=next(p for p in specs if p['name']==selected['name'])
    scenario=[]
    for label,f,sli,exclude in [('BASE',.003,.001,()),('COST_2X',.006,.002,()),('EXCLUDE_TOP3_AND_2X',.006,.002,selected['top3_alt_profit_pairs'].split(',') if selected['top3_alt_profit_pairs'] else ())]:
        out,nav,tr=simulate({**s,'name':s['name']+'_'+label},pairs,ids,A,banks,fee=f,slip=sli,exclude=exclude,save=True)
        out['stress']=label;scenario.append(out)
    pd.DataFrame(scenario).to_csv(OUT/'V20_SELECTED_POLICY_STRESS.csv',index=False)
    # BTC independently in same execution engine for fair comparison.
    btc=next(p for p in specs if p['name']=='V20_BTC_CORE');o,nav,tr=simulate(btc,pairs,ids,A,banks,save=True)
    # Coverage for 2023 by signal, not necessarily actual entry
    w23=w[(w.year==2023)&(w.multiple>=5)]
    print('V20_2023_5X_WAVES',len(w23),'LIQ_GE3M',int((w23.max_pre_peak_estimated_quote>=3e6).sum()),flush=True)
    result={'selected_train_exploratory':selected['name'],'source_pairs':len(pairs),'waves_ge_10x':int((w.multiple>=10).sum()),'source_data_end':'2023-12-31','not_pit_certified':True,'training_period_reused_in_prior_research':True,'research_not_live_approved':True}
    (OUT/'V20_SUMMARY.json').write_text(json.dumps(result,indent=2))
    print('V20_COMPLETE',json.dumps(result),flush=True)

if __name__=='__main__':main()
