#!/usr/bin/env python3
"""Fast independent-in-memory execution path for V19; read-only, pre-2024 only.
Does not access live trading, 2024+ bars, user credentials, or any broker endpoints.
"""
from pathlib import Path
import sys,json,time,hashlib
from collections import defaultdict
import numpy as np,pandas as pd
sys.path.insert(0,str(Path(__file__).parent))
import v19_replay as v
OUT=Path(__file__).parent

def to_arrays(data):
    pairs=sorted(data)
    arrs={}
    keys=('open','high','low','close','ma20','ma50','ma200','atr14','q20prev')
    for k in keys:arrs[k]=np.stack([data[p][k].to_numpy(dtype='float64') for p in pairs])
    return pairs,{p:i for i,p in enumerate(pairs)},arrs

def bank_ids(bank, ids):
    return {day: [(score,ids[p]) for score,p in entries if p in ids] for day,entries in bank.items()}

def replay(p,bank,pairs,ids,A,fee=.003,slip=.001,exclude=(),btc_alloc=1., risk_guard=None):
    op=A['open'];hi=A['high'];lo=A['low'];cl=A['close'];ma20=A['ma20'];ma50=A['ma50'];ma200=A['ma200'];atr=A['atr14'];q20prev=A['q20prev']
    ibtc=ids['BTC-USDT']
    # Index day->column, all bar timestamps anchored on 2019-01-01
    base=v.ST0; btc=ibtc;excl={ids[x] for x in exclude if x in ids}
    money=1e5;bu=0.;bstop=0.;bhigh=0.;be=0;bbasis=0.;bcool=0
    holdings={}; cool={}; trades=[]; navs=[]; pnl=defaultdict(float);maxnav=1e5;mdd=0.;n_alt=0;n_btc=0;n_censor=0;n_missing=0
    maxn=p['max_holdings'];risk=p['risk'];altf=p['alt_fraction'];style=p['style'];atr_mult=p['atr_trail']; bear_alt=p['bear_alt']
    for day in range(v.START,v.END):
        i=day-base; j=i-1;bo=op[btc,i];bc=cl[btc,i];market_on=bool(np.isfinite(cl[btc,j]) and np.isfinite(ma200[btc,j]) and cl[btc,j]>ma200[btc,j])
        if not (np.isfinite(bo) and np.isfinite(bc)):raise ValueError('BTC has missing bar')
        for a,h in list(holdings.items()):
            x=op[a,i]
            if not np.isfinite(x):h['missing']+=1;n_censor+=1;continue
            weak=bool(np.isfinite(cl[a,j]) and np.isfinite(ma50[a,j]) and cl[a,j]<ma50[a,j] and ma20[a,j]<ma50[a,j])
            if h['missing'] or x<=h['stop'] or weak:
                xfill=x*(1-slip);amount=h['units']*xfill*(1-fee);money+=amount
                gain=amount-h['basis'];pnl[a]+=gain
                trades.append((a,h['entry'],day,h['entry_px'],xfill,h['basis'],gain,'missing_or_gap' if h['missing'] else 'stop_or_weak',h['highest']))
                del holdings[a];cool[a]=day+3
            else:h['missing']=0
        if bu and (not market_on or bo<=bstop):
            proceeds=bu*bo*(1-slip)*(1-fee);money+=proceeds
            trades.append((btc,be,day,bbasis/max(bu,1e-9),bo*(1-slip),bbasis,proceeds-bbasis,'btc_open_exit',bhigh))
            bu=0.;bcool=day+7;n_btc+=1;bbasis=0.
        def open_nav():
            return money+bu*bo+sum(h['units']*(op[a,i] if np.isfinite(op[a,i]) else h['last']) for a,h in holdings.items())
        alt_mv=sum(h['units']*(op[a,i] if np.isfinite(op[a,i]) else h['last']) for a,h in holdings.items())
        active_alt=market_on or (bear_alt and np.isfinite(ma50[btc,j]) and cl[btc,j]>ma50[btc,j])
        if active_alt and altf>0 and len(holdings)<maxn:
            for score,a in bank.get(day,()):
                if a in holdings or a in excl or day<cool.get(a,0):continue
                if len(holdings)>=maxn:break
                px=op[a,i]; yclose=cl[a,j];at=atr[a,j];qprev=q20prev[a,j]
                if not (np.isfinite(px) and np.isfinite(at) and np.isfinite(qprev)):
                    n_missing+=1;continue
                buy=px*(1+slip)
                if buy/yclose>1.10:continue
                dist=min(max(.06*buy,atr_mult*at),.35*buy)
                en=open_nav()
                q=min(.22*en,risk*en/max(dist/buy,.005),.001*qprev,
                      max(0,altf*en-alt_mv),en/max(maxn,1))
                if q<100:continue
                need=q*(1+fee)-money
                if need>0 and bu>0:
                    sell=min(bu,need/(bo*(1-slip)*(1-fee)))
                    amount=sell*bo*(1-slip)*(1-fee);money+=amount
                    if bu>0:bbasis*=max(0,(bu-sell)/bu)
                    bu-=sell;n_btc+=1
                    if bu<1e-10:bu=0
                q=min(q,max(0,money/(1+fee)))
                if q<100:continue
                units=q/buy; spent=q*(1+fee);money-=spent;alt_mv+=q;n_alt+=1
                holdings[a]={'units':units,'basis':spent,'entry':day,'entry_px':buy,'stop':buy-dist,'highest':buy,'last':buy,'missing':0}
        if market_on and day>=bcool and money>max(300,.01*open_nav()) and btc_alloc>0:
            cap=min(money/(1+fee),max(0,btc_alloc*open_nav()-bu*bo))
            if cap>300:
                buyprice=bo*(1+slip)
                if bu==0:
                    be=day;bhigh=buyprice;bstop=buyprice-max(.04*buyprice,6*atr[btc,j]);bbasis=0.
                bbasis+=cap*(1+fee);bu+=cap/buyprice;money-=cap*(1+fee);n_btc+=1
        # Stops placed before session; no proceeds can finance earlier buys
        for a,h in list(holdings.items()):
            if not all(map(np.isfinite,(op[a,i],hi[a,i],lo[a,i],cl[a,i]))):continue
            if lo[a,i]<=h['stop']:
                x=min(op[a,i],h['stop'])*(1-slip)
                money+=h['units']*x*(1-fee);profit=h['units']*x*(1-fee)-h['basis'];pnl[a]+=profit
                trades.append((a,h['entry'],day,h['entry_px'],x,h['basis'],profit,'intraday_stop',h['highest']))
                del holdings[a];cool[a]=day+3
            else:
                h['highest']=max(h['highest'],hi[a,i]);h['last']=cl[a,i]
                tatr=atr[a,i] if np.isfinite(atr[a,i]) else atr[a,j]
                dist=min(max(.06*cl[a,i],atr_mult*tatr),.35*cl[a,i]);h['stop']=max(h['stop'],h['highest']-dist)
        if bu>0:
            if lo[btc,i]<=bstop:
                fill=min(bo,bstop)*(1-slip);got=bu*fill*(1-fee);money+=got
                trades.append((btc,be,day,bbasis/max(bu,1e-9),fill,bbasis,got-bbasis,'btc_intraday_stop',bhigh))
                bu=0.;bcool=day+7;bbasis=0.;n_btc+=1
            else:
                bhigh=max(bhigh,hi[btc,i]);bstop=max(bstop,bhigh-max(.04*bc,6*atr[btc,i]))
        total=money+bu*bc+sum(h['units']*(cl[a,i] if np.isfinite(cl[a,i]) else h['last']) for a,h in holdings.items())
        maxnav=max(total,maxnav);mdd=min(mdd,total/maxnav-1)
        navs.append((day,total,bu*bc,total-money-bu*bc,money,len(holdings)))
        if money<-.01:raise AssertionError(('negative',day,money))
    # final liquidation
    for a,h in holdings.items():
        px=h['last']*(1-slip);amount=h['units']*px*(1-fee);money+=amount
        profit=amount-h['basis'];pnl[a]+=profit
        trades.append((a,h['entry'],v.END-1,h['entry_px'],px,h['basis'],profit,'end_2023',h['highest']))
    if bu:money+=bu*cl[btc,v.END-1-base]*(1-slip)*(1-fee)
    nv=pd.DataFrame(navs,columns=['day','nav','btc_value','alt_value','cash','alt_positions'])
    yr={};prev=1e5
    for y in range(2020,2024):
        di=int(pd.Timestamp(f'{y}-12-31',tz='UTC').value//10**6//v.DAY)
        val=float(nv.loc[nv.day.eq(di),'nav'].iloc[0]);yr[str(y)]=100*(val/prev-1);prev=val
    top=sorted(pnl.items(),key=lambda x:-x[1]);top3=[pairs[a] for a,x in top[:3]]
    result={'policy':p['name'],'btc_allocation_cap':btc_alloc,'total_return_pct':(money/1e5-1)*100,'maxdd_pct':mdd*100,'alt_trades':n_alt,'btc_orders':n_btc,'trades':len(trades),'top3_pairs':','.join(top3),'top3_net':sum(x for a,x in top[:3]),'missing_bar_days':n_censor,'unexecuted_missing_bar_signals':n_missing,'fee':fee,'slippage':slip,'excluded':','.join(exclude),**{f'ret_{y}':rv for y,rv in yr.items()}}
    log=pd.DataFrame(trades,columns=['pair_i','entry_day','exit_day','entry_price','exit_price','spent','net','reason','high_since_entry'])
    if len(log):log['pair']=log.pair_i.map(lambda a:pairs[a]);log.drop(columns=['pair_i'],inplace=True)
    return result,log,nv

def main():
    data,venues,files,errors=v.load();D=v.features(data);pairs,ids,A=to_arrays(D)
    policies=v.POLICIES
    print('V19_FAST_DATA',len(pairs),flush=True)
    res=[]
    for p in policies:
        bank={} if p['style']=='none' else bank_ids(v.make_bank(D,p),ids)
        for alloc in [1.,.5] if p['alt_fraction']>0 else [1.,.5]:
            pf=dict(p);pf['name']=p['name']+('_BTC50' if alloc==.5 else '')
            r,t,n=replay(pf,bank,pairs,ids,A,btc_alloc=alloc)
            res.append(r)
            t.to_csv(OUT/(pf['name']+'_V19F_TRADES.csv'),index=False)
            n.to_csv(OUT/(pf['name']+'_V19F_NAV.csv'),index=False)
            if p['alt_fraction']:
                s,_,_=replay(pf,bank,pairs,ids,A,fee=.006,slip=.002,btc_alloc=alloc);res.append(s)
                if r['top3_pairs']:
                    x,_,_=replay(pf,bank,pairs,ids,A,fee=.006,slip=.002,btc_alloc=alloc,exclude=tuple(r['top3_pairs'].split(',')));res.append(x)
            print('V19_FAST',pf['name'],round(r['total_return_pct'],2),round(r['maxdd_pct'],2),*[round(r[f'ret_{y}'],2) for y in (2020,2021,2022,2023)],'2x',round(s['total_return_pct'],2) if p['alt_fraction'] else '',flush=True)
            pd.DataFrame(res).to_csv(OUT/'V19F_COMPARISON_PARTIAL.csv',index=False)
    pd.DataFrame(res).to_csv(OUT/'V19F_COMPARISON.csv',index=False)
    (OUT/'V19F_STATUS.json').write_text(json.dumps({'data_pairs':len(pairs),'venue':venues,'policies':len(policies),'scenario_count':len(res),'start':'2020-01-01','end':'2023-12-31','C2_PIT_CERTIFIED':False,'unbiased_holdout':False,'broker_connected':False},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
