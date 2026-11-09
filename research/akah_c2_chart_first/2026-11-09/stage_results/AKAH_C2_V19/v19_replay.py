#!/usr/bin/env python3
"""AKAH C2 V19: deterministic, read-only, historical research.
Scope through 2023-12-31; dynamic daily as-of signals; no broker/API orders.
OHLCV venue static for each pair (Binance preferred when available, KuCoin fallback), NOT PIT-certified.
All candidate features derive from completed prior closes. Stops fixed before day session.
"""
import zipfile,io,glob,os,json,hashlib,math
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
DAY=86400000
OUT=Path('/mnt/data/AKAH_C2_V19'); OUT.mkdir(parents=True,exist_ok=True)
ST0=int(pd.Timestamp('2019-01-01',tz='UTC').value//10**6//DAY)
START=int(pd.Timestamp('2020-01-01',tz='UTC').value//10**6//DAY)
END=int(pd.Timestamp('2024-01-01',tz='UTC').value//10**6//DAY)
DAYS=np.arange(ST0,END)
FILES=sorted(glob.glob('/mnt/data/UPLOAD_THIS_AKAH_C2_364_RAW_PART_*.zip'))
FEES=.003; SLIP=.001

def load():
    input_files=[]; rs={}; audit=[]
    for file in FILES:
        with zipfile.ZipFile(file) as z:
            for member in z.namelist():
                if not (member.startswith('daily/') and member.endswith('.csv.gz')):continue
                fname=member[6:-7]
                if '_' not in fname:continue
                venue,pair=fname.split('_',1)
                try:
                    d=pd.read_csv(io.BytesIO(z.read(member)),compression='gzip')
                    d=d[(d.unix_ms>=ST0*DAY)&(d.unix_ms<END*DAY)].copy()
                    for k in ('unix_ms','open','high','low','close','base_volume','quote_volume'):
                        d[k]=pd.to_numeric(d[k],errors='coerce')
                    d=d[(d.open>0)&(d.low>0)&(d.high>=d.low)&(d.high>=d.open)&(d.high>=d.close)&(d.low<=d.open)&(d.low<=d.close)&(d.close>0)&(d.base_volume>=0)]
                    d['day']=(d.unix_ms//DAY).astype(int)
                    d=d.sort_values('day').drop_duplicates('day',keep='last').set_index('day').reindex(DAYS)
                    if int(d.close.notna().sum())<90:continue
                    rs[(venue,pair)]=d
                    input_files.append({'source_zip':Path(file).name,'member':member,'num_nonempty_bars':int(d.close.notna().sum()),'sha256_uncompressed':hashlib.sha256(z.read(member)).hexdigest()})
                except Exception as e:audit.append({'file':member,'error':str(e)[:160]})
    # Venue is frozen per pair for this trial; prefer Binance when both are available.
    # This is a known ex-post membership / venue-choice limitation.
    pp={p for v,p in rs}; data={}; venue={}
    for p in sorted(pp):
        v='BINANCE' if ('BINANCE',p) in rs else 'KUCOIN'
        data[p]=rs[(v,p)];venue[p]=v
    return data,venue,input_files,audit

def features(D):
    o={}
    for pair,raw in D.items():
        d=raw.copy();close=d.close
        tr=pd.concat([d.high-d.low,(d.high-close.shift(1)).abs(),(d.low-close.shift(1)).abs()],axis=1).max(axis=1,skipna=False)
        d['atr14']=tr.rolling(14,min_periods=14).mean()
        d['atrpct']=d.atr14/close
        for n in (5,10,20,30,50,90,100,200):
            d[f'ma{n}']=close.rolling(n,min_periods=n).mean()
        for n in (5,10,20,30,60,90):d[f'ret{n}']=close/close.shift(n)-1
        d['prev20high']=d.high.shift(1).rolling(20,min_periods=20).max()
        d['prev55high']=d.high.shift(1).rolling(55,min_periods=55).max()
        d['prev10high']=d.high.shift(1).rolling(10,min_periods=10).max()
        # QUOTE VOLUME primary if available; base_volume*close only as labeled estimate.
        native=d.quote_volume.where(d.quote_volume>0)
        d['q_est']=d.base_volume*d.close
        d['q_asof']=native.fillna(d.q_est)
        d['q_native_available']=native.notna()
        d['q20prev']=d.q_asof.shift(1).rolling(20,min_periods=20).median()
        d['rvol']=d.base_volume/d.base_volume.shift(1).rolling(20,min_periods=20).median()
        d['weekly_trend']=close>close.rolling(84,min_periods=84).mean()
        d['break20']=(close>d.prev20high)&(close.shift(1)<=d.prev20high.shift(1))
        d['break55']=(close>d.prev55high)&(close.shift(1)<=d.prev55high.shift(1))
        d['reclaim20']=(d.low<d.ma20)&(close>d.ma20)&(close>close.shift(1))
        d['recovery50']=(d.ma20>d.ma50)&(d.ma20.shift(1)<=d.ma50.shift(1))
        o[pair]=d
    return o

def make_bank(D,pol):
    btc=D['BTC-USDT']
    bank=defaultdict(list)
    for pair,d in D.items():
        if pair=='BTC-USDT':continue
        # all indicators known at closed day t; act at next OPEN t+1.
        tradable=(d.q20prev>=3_000_000)&d.close.gt(0)&d.atrpct.between(.008,.22)&d.base_volume.gt(0)
        # Last days have limited info; not a future-availability filter.
        trend=(d.close>d.ma50)&(d.ma20>d.ma50)&d.weekly_trend
        rel20=d.ret20-btc.ret20
        rel60=d.ret60-btc.ret60
        leader=(rel20>.05)&(rel60>.08)&(d.ret20>.07)
        if pol['style']=='breakout':event=d.break20 & trend & leader
        elif pol['style']=='dual':event=((d.break20 & trend & leader)|(d.reclaim20 & trend & leader & (d.rvol>=1.1)))
        elif pol['style']=='recovery':event=(d.break20 & (d.ret20>.03)&(d.ma20>d.ma50)&(rel20>.0)) | (d.recovery50 & (d.ret20>.03)&(rel20>.0))
        elif pol['style']=='broad':event=((d.break20|d.reclaim20)&(d.close>d.ma50)&(d.ret20>.025)&(rel20>-.025))
        elif pol['style']=='wave':
            # Catch new accelerations AND continuation after a completed-bar pullback, not a fixed 72h forecast.
            first_push=d.break20 | (d.close>d.prev10high)&(d.ret5>.06)&(d.ret20>.10)
            resume=d.reclaim20 & (d.ret20>.12) & (d.ma20>d.ma50) & (d.close>d.ma20)
            event=(first_push|resume)&(d.close>d.ma20)&(d.ret20>.08)&(rel20>-.03)&(d.rvol>=1.)
        else:raise ValueError(pol['style'])
        mask=tradable & event & d.ret60.notna() & btc.ret20.notna() & (d.index>=START-1) & (d.index<END-1)
        for day in d.index[mask]:
            row=d.loc[day]; b=btc.loc[day]
            score=1.0*(float(row.ret20)-float(b.ret20))+.7*(float(row.ret60)-float(b.ret60))+.20*float(row.ret10)
            if np.isfinite(row.rvol):score+=.015*min(5.0,float(row.rvol))
            if np.isfinite(score):bank[day+1].append((score,pair))
    for day in bank:bank[day].sort(key=lambda x:(-x[0],x[1]))
    return bank

POLICIES=[
 {'name':'BTC_REFERENCE_100','style':'none','alt_fraction':0.,'bear_alt':False,'atr_trail':6.,'risk':0.,'max_holdings':0,'btc_ma':200},
 {'name':'V19_BREAKOUT_40','style':'breakout','alt_fraction':.40,'bear_alt':False,'atr_trail':6.,'risk':.02,'max_holdings':3,'btc_ma':200},
 {'name':'V19_DUAL_40','style':'dual','alt_fraction':.40,'bear_alt':False,'atr_trail':6.,'risk':.02,'max_holdings':3,'btc_ma':200},
 {'name':'V19_DUAL_60','style':'dual','alt_fraction':.60,'bear_alt':False,'atr_trail':6.,'risk':.02,'max_holdings':4,'btc_ma':200},
 {'name':'V19_BEAR_RECOVERY_35','style':'recovery','alt_fraction':.35,'bear_alt':True,'atr_trail':6.,'risk':.014,'max_holdings':3,'btc_ma':200},
 {'name':'V19_BROAD_30','style':'broad','alt_fraction':.30,'bear_alt':False,'atr_trail':8.,'risk':.012,'max_holdings':4,'btc_ma':200},
]

def execute(D,bank,pol,cost_mult=1.,exclude=()):
    fee=FEES*cost_mult;slip=SLIP*cost_mult
    btc=D['BTC-USDT']; cash=100000.;btc_u=0.; btc_stop=0.;btc_high=0.;btc_entry=0;btc_basis=0.;btc_cool=0
    positions={}; cooldown={}; fills=[]; navlog=[]; pair_pnl=defaultdict(float); missed=0; censors=0; nofund=0; highest_nav=1e5;lowdd=0.;alt_openings=0;btc_orders=0
    for day in range(START,END):
        yesterday=day-1
        bt=btc.loc[day]; bp=btc.loc[yesterday];
        if not (np.isfinite(bt.open) and np.isfinite(bt.close)):
            raise RuntimeError('BTC missing day '+str(day))
        open_btc=float(bt.open);close_btc=float(bt.close)
        market_on=bool(np.isfinite(bp.ma200) and bp.close>bp.ma200)
        # first settle *open* exits based only on pre-existing stops and previous closes
        for pair,p in list(positions.items()):
            r=D[pair].loc[day];yp=D[pair].loc[yesterday]
            if not np.isfinite(r.open):
                p['missing']+=1;censors+=1;continue
            px=float(r.open)
            hardexit=bool(np.isfinite(yp.close) and np.isfinite(yp.ma50) and yp.close < yp.ma50 and yp.ma20<yp.ma50)
            if p['missing']>0 or px <= p['stop'] or hardexit:
                reason='gap_after_missing' if p['missing'] else ('overnight_stop' if px<=p['stop'] else 'prior_day_trend_exit')
                xpx=px*(1-slip);amt=p['units']*xpx*(1-fee);cash+=amt
                pnl=amt-p['basis'];pair_pnl[pair]+=pnl
                fills.append({'pair':pair,'entry_day':p['entry'],'exit_day':day,'entry_price':p['entryprice'],'exit_price':xpx,'spent':p['basis'],'net':pnl,'reason':reason,'highest':p['highest'],'entry_score':p['score'],'entry_qprev':p['qprev']})
                del positions[pair];cooldown[pair]=day+3
            else:p['missing']=0
        # BTC open exits based on known prior data / opening gap
        if btc_u and (not market_on or open_btc<=btc_stop):
            proceeds=btc_u*open_btc*(1-slip)*(1-fee);cash+=proceeds
            fills.append({'pair':'BTC-USDT','entry_day':btc_entry,'exit_day':day,'entry_price':btc_basis/max(btc_u,1e-9),'exit_price':open_btc*(1-slip),'spent':btc_basis,'net':proceeds-btc_basis,'reason':'btc_open_exit','highest':btc_high,'entry_score':None,'entry_qprev':None})
            btc_u=0;btc_cool=day+7;btc_orders+=1
        def equity_open():
            val=cash+btc_u*open_btc
            for pr,p in positions.items():
                price=D[pr].loc[day].open
                val+=p['units']*(float(price) if np.isfinite(price) else p['last'])
            return val
        # trade ALT at open when yesterday's closed-bar signal already known; sell BTC to finance first.
        alt_held=sum(p['units']*(float(D[pr].loc[day].open) if np.isfinite(D[pr].loc[day].open) else p['last']) for pr,p in positions.items())
        active_alt=(market_on or (pol['bear_alt'] and np.isfinite(bp.ma50) and bp.close>bp.ma50))
        if active_alt and pol['alt_fraction']>0 and len(positions)<pol['max_holdings']:
            for score,pair in bank.get(day,[]):
                if pair in positions or pair in exclude or day<cooldown.get(pair,0):continue
                if len(positions)>=pol['max_holdings']:break
                r=D[pair].loc[day];yp=D[pair].loc[yesterday]
                if not (np.isfinite(r.open) and np.isfinite(yp.atr14) and np.isfinite(yp.q20prev) and np.isfinite(r.low)):
                    missed+=1;continue
                px=float(r.open)*(1+slip);close_prev=float(yp.close)
                if not np.isfinite(close_prev):continue
                # Causal overnight gap safety for late entry, avoid paying >10% above signal close.
                if px/close_prev>1.10:continue
                stop_dist=max(.06*px,pol['atr_trail']*float(yp.atr14));stop_dist=min(stop_dist,.35*px)
                stop_px=px-stop_dist
                account=equity_open()
                target_size=min(.22*account,pol['risk']*account/max(stop_dist/px,.005), .001*float(yp.q20prev),
                                max(0,pol['alt_fraction']*account-alt_held), account/max(pol['max_holdings'],1))
                if target_size<100:continue
                needed=target_size*(1+fee)-cash
                # USD proceeds from selling BTC at open are available before ALT entry;
                # not from intra-day stops which occur later.
                if needed>0 and btc_u>0:
                    sellunits=min(btc_u,needed/(open_btc*(1-slip)*(1-fee)))
                    proceeds=sellunits*open_btc*(1-slip)*(1-fee);cash+=proceeds;btc_u-=sellunits;btc_orders+=1
                    if btc_u<1e-10:btc_u=0
                target_size=min(target_size,max(0,cash/(1+fee)))
                if target_size<100:nofund+=1;continue
                units=target_size/px;spent=target_size*(1+fee);cash-=spent;alt_held+=target_size;alt_openings+=1
                positions[pair]={'units':units,'basis':spent,'entry':day,'entryprice':px,'score':score,'qprev':float(yp.q20prev),'stop':stop_px,'highest':px,'last':px,'missing':0}
        # put idle funds in BTC core when in regime and available to buy; no rebalancing out of BTC otherwise.
        if market_on and day>=btc_cool and cash>max(300,0.01*equity_open()):
            # If there is a planned alt sleeve, invest BTC with whatever not in ALT, so cash isn't stranded.
            invest=cash/(1+fee)
            if invest>300:
                buyprice=open_btc*(1+slip)
                if btc_u==0:
                    btc_entry=day;btc_basis=invest*(1+fee);btc_high=buyprice
                    btc_stop=buyprice-max(.04*buyprice,6*float(bp.atr14))
                # subsequent top-ups are cash contributions not distinct tracked tax lots.
                btc_u+=invest/buyprice;cash-=invest*(1+fee);btc_orders+=1
        # stops already active before today's movement. Trailing stops updated AFTER close.
        for pair,p in list(positions.items()):
            r=D[pair].loc[day]
            if not all(np.isfinite(r[k]) for k in ('open','high','low','close')):continue
            if float(r.low)<=p['stop']:
                # pre-committed stop; if entry day open was above stop, fill stop pessimistically.
                xpx=min(float(r.open),p['stop'])*(1-slip)
                proceeds=p['units']*xpx*(1-fee);cash+=proceeds
                pnl=proceeds-p['basis'];pair_pnl[pair]+=pnl
                fills.append({'pair':pair,'entry_day':p['entry'],'exit_day':day,'entry_price':p['entryprice'],'exit_price':xpx,'spent':p['basis'],'net':pnl,'reason':'intraday_precommitted_stop','highest':p['highest'],'entry_score':p['score'],'entry_qprev':p['qprev']})
                cooldown[pair]=day+3;del positions[pair]
            else:
                p['highest']=max(p['highest'],float(r.high));p['last']=float(r.close)
                atr=float(r.atr14) if np.isfinite(r.atr14) else float(D[pair].loc[yesterday].atr14)
                trailing=max(.06*float(r.close),pol['atr_trail']*atr)
                trailing=min(trailing,.35*float(r.close))
                p['stop']=max(p['stop'],p['highest']-trailing)
        # BTC intraday protection placed pre-open; if stopping, cannot fund ALT purchases earlier today.
        if btc_u:
            if np.isfinite(bt.low) and float(bt.low)<=btc_stop:
                xpx=min(open_btc,btc_stop)*(1-slip);proceeds=btc_u*xpx*(1-fee);cash+=proceeds
                fills.append({'pair':'BTC-USDT','entry_day':btc_entry,'exit_day':day,'entry_price':btc_basis/max(btc_u,1e-9),'exit_price':xpx,'spent':btc_basis,'net':proceeds-btc_basis,'reason':'btc_intraday_stop','highest':btc_high,'entry_score':None,'entry_qprev':None})
                btc_u=0;btc_cool=day+7;btc_orders+=1
            else:
                btc_high=max(btc_high,float(bt.high))
                if np.isfinite(bt.atr14):btc_stop=max(btc_stop,btc_high-max(.04*float(bt.close),6*float(bt.atr14)))
        eq=cash+btc_u*close_btc
        for pr,p in positions.items():
            r=D[pr].loc[day];eq+=p['units']*(float(r.close) if np.isfinite(r.close) else p['last'])
        highest_nav=max(highest_nav,eq);lowdd=min(lowdd,eq/highest_nav-1)
        navlog.append({'day':day,'nav':eq,'btc_value':btc_u*close_btc,'alt_value':eq-cash-btc_u*close_btc,'cash':cash,'alt_positions':len(positions),'market_on':int(market_on)})
        if cash<-0.10:raise AssertionError(('negative_cash',day,cash))
        if len(positions)>pol['max_holdings']:raise AssertionError('max holdings exceeded')
    # liquidation at last closing price for final realised NAV with one final fee/slippage charge.
    for pr,p in positions.items():
        xpx=p['last']*(1-slip);proceeds=p['units']*xpx*(1-fee);cash+=proceeds
        pnl=proceeds-p['basis'];pair_pnl[pr]+=pnl
        fills.append({'pair':pr,'entry_day':p['entry'],'exit_day':END-1,'entry_price':p['entryprice'],'exit_price':xpx,'spent':p['basis'],'net':pnl,'reason':'end_2023','highest':p['highest'],'entry_score':p['score'],'entry_qprev':p['qprev']})
    if btc_u:cash+=btc_u*close_btc*(1-slip)*(1-fee)
    nv=pd.DataFrame(navlog)
    def at(t):
        day=int(pd.Timestamp(t,tz='UTC').value//10**6//DAY)
        return float(nv.loc[nv.day.eq(day),'nav'].iloc[0])
    yrend={yr:at(f'{yr}-12-31') for yr in (2020,2021,2022,2023)}
    yearly={};last=100000.
    for yr,val in yrend.items():yearly[str(yr)]=100*(val/last-1);last=val
    top=sorted([(p,v) for p,v in pair_pnl.items() if p!='BTC-USDT'],key=lambda z:-z[1])
    result={'policy':pol['name'],'total_return_pct':100*(cash/100000-1),'maxdd_pct':100*lowdd,'trades':len(fills),'alt_trades':alt_openings,'btc_orders':btc_orders,'distinct_alts':len(set(x['pair'] for x in fills if x['pair']!='BTC-USDT')),'top3_pairs':','.join(x[0] for x in top[:3]),'top3_pnl_usdt':sum(x[1] for x in top[:3]),'censored_pair_days':censors,'missed_no_data_entries':missed,'insufficient_funds_skips':nofund,'cost_mult':cost_mult,'excluded':','.join(exclude),**{f'ret_{k}':v for k,v in yearly.items()},'final_nav':cash}
    return result,pd.DataFrame(fills),nv

def main():
    print('V19_DATA_IMPORT_BEGIN',flush=True)
    data,venue,src,audit=load()
    print('V19_DAILY_PAIRS',len(data),'SOURCE_BARS',sum(int(v.close.notna().sum()) for v in data.values()),flush=True)
    assert 'BTC-USDT' in data and len(data)>200
    with (OUT/'SOURCE_LINEAGE.json').open('w') as f:json.dump({'venue_by_pair':venue,'input_files':src,'errors':audit,'period':'pre2024','pit_certified':False},f,indent=2)
    df=features(data);stats=[];trades={}
    for p in POLICIES:
        print('V19_RUN',p['name'],flush=True)
        bank=defaultdict(list) if p['style']=='none' else make_bank(df,p)
        base,t,n=execute(df,bank,p)
        print('V19_RESULT',p['name'],round(base['total_return_pct'],2),round(base['maxdd_pct'],2),'2022',round(base['ret_2022'],2),'2023',round(base['ret_2023'],2),'ALT_TRADES',base['alt_trades'],flush=True)
        stats.append(base);pd.DataFrame(stats).to_csv(OUT/'V19_POLICY_STRESS_PARTIAL.csv',index=False);trades[p['name']]=t
        t.to_csv(OUT/(p['name']+'_TRADES.csv'),index=False)
        n.to_csv(OUT/(p['name']+'_NAV.csv'),index=False)
        stress,_,_=execute(df,bank,p,cost_mult=2.);stats.append(stress);pd.DataFrame(stats).to_csv(OUT/'V19_POLICY_STRESS_PARTIAL.csv',index=False)
        if p['alt_fraction'] and base['top3_pairs']:
            exc=base['top3_pairs'].split(',')
            res,_,_=execute(df,bank,p,cost_mult=2.,exclude=tuple(exc));stats.append(res);pd.DataFrame(stats).to_csv(OUT/'V19_POLICY_STRESS_PARTIAL.csv',index=False)
            print('V19_STRESS',p['name'],'2X',round(stress['total_return_pct'],2),'EXC3+2X',round(res['total_return_pct'],2),flush=True)
    pd.DataFrame(stats).to_csv(OUT/'V19_POLICY_STRESS.csv',index=False)
    # Frozen offline gates: no 2024, no live, no unbiased holdout, no PIT C2.
    best=sorted((x for x in stats if x['cost_mult']==1),key=lambda x:x['total_return_pct'],reverse=True)
    with (OUT/'STATUS.json').open('w') as f:
        json.dump({'scope':'2020-2023 historical pre-2024 research','pairs_loaded':len(data),'policy_count':len(POLICIES),'scenarios':len(stats),'best_base':best[0]['policy'],'btc_baseline':next(x for x in stats if x['policy']=='BTC_REFERENCE_100' and x['cost_mult']==1),'pit_certified':False,'live_approved':False,'unbiased_holdout':False,'notes':['C2 universe itself derived from later collection plan; membership is ex-post','Venue chosen per pair by fixed Binance-priority (not PIT)','Daily stop intrabar order unknown; conservative precommitted stop fill']},f,indent=2)
    print('V19_DONE',len(stats),flush=True)
if __name__=='__main__':main()
