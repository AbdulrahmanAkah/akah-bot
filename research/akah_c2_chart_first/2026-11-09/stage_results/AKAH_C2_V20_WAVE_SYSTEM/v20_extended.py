#!/usr/bin/env python3
"""AKAH V20 extended forensic checks. Historical, read only, no 2024 or live."""
import sys,json,io,zipfile,gzip,glob,hashlib
from pathlib import Path
import numpy as np,pandas as pd
sys.path.insert(0,'/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')
import v20_research as v
OUT=Path('/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')
DAY=v.DAY

def context_asof(pairs,ids,A,banks):
    # Load only actual available hourly and funding, label unmatched venue explicitly.
    # We use these to EXPLAIN market context in V20, not silently optimize its policy.
    import sys
    sys.path.insert(0,'/mnt/data/AKAH_C2_V19')
    import v19_replay as r
    lineage=json.loads((Path('/mnt/data/AKAH_C2_V19')/'SOURCE_LINEAGE.json').read_text())
    # Only days with a decision signal are needed; skip unrelated expensive hourly rows.
    relevant=set(a for b in banks.values() for entries in b.values() for sc,a in entries)
    days_by_pair={a:set() for a in relevant}
    for b in banks.values():
        for day,items in b.items():
            for score,a in items:days_by_pair[a].add(day-1)
    # At most ~ 4,900 unique signal (asset,day) source 
    hourly={}
    sources=0
    for file in sorted(glob.glob('/mnt/data/UPLOAD_THIS_AKAH_C2_364_RAW_PART_*.zip')):
        with zipfile.ZipFile(file) as z:
            for member in z.namelist():
                if not member.startswith('hourly/') or not member.endswith('.csv.gz'):continue
                raw=member.split('/')[-1][:-7]
                if '_' not in raw:continue
                venue,pair=raw.split('_',1)
                if pair not in ids:continue
                a=ids[pair]
                if a not in relevant:continue
                selected=days_by_pair[a]
                if not selected:continue
                d=pd.read_csv(io.BytesIO(z.read(member)),compression='gzip',usecols=['unix_ms','open','high','low','close','base_volume'])
                d=d[(d.unix_ms>=v.START*DAY)&(d.unix_ms<v.END*DAY)]
                if not len(d):continue
                d['day']=(d.unix_ms//DAY).astype(int)
                d=d[d.day.isin(selected)].copy()
                if not len(d):continue
                d=d.sort_values('unix_ms');d['up_pct']=d.close/d.open-1
                for day,g in d.groupby('day'):
                    if len(g)<22:continue
                    g=g.dropna(subset=['open','close','high','low']);
                    if len(g)<22:continue
                    pr=float(g.close.iloc[-1]);mx=float(g.high.max());mn=float(g.low.min());
                    after4=g.iloc[-4:];prev20=g.iloc[:-4]
                    hourly[(a,int(day),venue)]={'h_candles':len(g),'h_1pct_count':int((g.up_pct>=.01).sum()),'h_upbar_ratio':float((g.close>g.open).mean()),'h_last4h_return':float(after4.close.iloc[-1]/after4.open.iloc[0]-1),'h_24h_close_location':float((pr-mn)/(mx-mn)) if mx>mn else None,'h_last4h_volume_ratio':float(after4.base_volume.sum()/(prev20.base_volume.sum()/5)) if prev20.base_volume.sum()>0 else None,'h_range24h':float(mx/mn-1) if mn>0 else None,'h_venue':venue}
                sources+=1
    # Funding Binance USDM historical: settlement timestamp; no forward access
    funding={};nfund=0
    for file in sorted(glob.glob('/mnt/data/UPLOAD_THIS_AKAH_C2_364_RAW_PART_*.zip')):
        with zipfile.ZipFile(file) as z:
            for member in z.namelist():
                if not member.startswith('derivatives_funding/') or not member.endswith('.csv.gz'):continue
                name=member.split('/')[-1][:-7]
                pair=name.split('BINANCE_USDM_',1)[-1]
                if pair not in ids or ids[pair] not in relevant:continue
                a=ids[pair];selected=days_by_pair[a]
                if not selected:continue
                d=pd.read_csv(io.BytesIO(z.read(member)),compression='gzip',usecols=['unix_ms','funding_rate'])
                d['day']=(d.unix_ms//DAY).astype(int)
                d=d[(d.day>=v.START-4)&(d.day<v.END)].copy()
                if len(d)<5:continue
                d=d.groupby('day').funding_rate.agg(['sum','count']).reset_index()
                # look back trailing 7 days ending *on signal day* at close; no forward values.
                d=d.set_index('day').reindex(range(v.START-4,v.END));d['fund_sum_7d']=d['sum'].fillna(0).rolling(7,min_periods=3).sum();d['fund_count_7d']=d['count'].fillna(0).rolling(7,min_periods=3).sum()
                for day in selected:
                    if day in d.index and d.loc[day,'fund_count_7d']>=12:
                        funding[(a,day)]=float(d.loc[day,'fund_sum_7d'])
                nfund+=1
    print('V20_CONTEXT_INPUTS','hourly_files',sources,'hourly_event_day_pairs',len(hourly),'funding_pairs',nfund,'funding_event_days',len(funding),flush=True)
    return hourly,funding,lineage

def events_study(pairs,ids,A,banks,hr,fu,lineage):
    # All candidate observations, including losers. Eligibility does NOT use outcomes.
    C=A['close'];O=A['open'];H=A['high'];L=A['low'];Q=A['q20prev'];btc=ids['BTC-USDT'];
    combined={}
    for tag,bank in banks.items():
        for day,items in bank.items():
            for score,a in items:
                ob=combined.setdefault((a,day),{'tags':set(),'score':score});ob['tags'].add(tag)
    rows=[]
    for (a,day),inf in sorted(combined.items()):
        i=day-v.ST0;j=i-1
        if i<1 or i>=C.shape[1]:continue
        o=O[a,i]
        if not np.isfinite(o) or o<=0 or C[a,j]<=0:continue
        row={'pair':pairs[a],'entry_day':day,'year':pd.Timestamp(day*DAY,unit='ms',tz='UTC').year,'score':inf['score'],'sources':','.join(sorted(inf['tags'])),'would_open_next':True,'entry_gap_pct':100*(o/C[a,j]-1),'qprev_estimated_or_original':Q[a,j],'quote_native_last_signal_day':bool(A['quote_native'][a,j]),'ret5_pct':100*A['ret5'][a,j],'ret20_pct':100*A['ret20'][a,j],'ret60_pct':100*A['ret60'][a,j],'btc20_pct':100*A['ret20'][btc,j],'relative20_pct':100*(A['ret20'][a,j]-A['ret20'][btc,j]),'rsi14':A['rsi14'][a,j],'atrpct':100*A['atrpct'][a,j],'rvol':A['rvol'][a,j],'prior_90d_high_ratio':C[a,j]/A['prev90high'][a,j] if A['prev90high'][a,j]>0 else None,'listed_bars_so_far':int(A['age'][a,j])}
        venue=lineage.get('venue_by_pair',{}).get(pairs[a]);source=(hr.get((a,day-1,venue)) or hr.get((a,day-1,'KUCOIN')) or hr.get((a,day-1,'BINANCE')))
        if source:row.update(source);row['hourly_matches_venue']=source['h_venue']==venue
        row['funding_7d_sum']=fu.get((a,day-1))
        # outcome missing handled as censoring, not exclusion from candidate decision.
        for n in (7,30,90):
            if i+n<C.shape[1] and np.isfinite(C[a,i+n]) and all(np.isfinite(C[a,i:i+n+1])):
                row[f'forward_{n}d_close_pct']=100*(C[a,i+n]/o-1)
                row[f'mfe_{n}d_pct']=100*(np.max(H[a,i:i+n+1])/o-1) if np.isfinite(H[a,i:i+n+1]).all() else np.nan
                row[f'mae_{n}d_pct']=100*(np.min(L[a,i:i+n+1])/o-1) if np.isfinite(L[a,i:i+n+1]).all() else np.nan
                # +50% observed before -20% in daily OHLC ordering unknown intraday; if both hit same day, count as failure conservatively.
                if n==90 and np.isfinite(H[a,i:i+n+1]).all() and np.isfinite(L[a,i:i+n+1]).all():
                    h=H[a,i:i+n+1];l=L[a,i:i+n+1];win=np.where(h>=o*1.5)[0];loss=np.where(l<=o*.8)[0]
                    row['success_plus50_before_minus20_90d']=bool(len(win)>0 and (not len(loss) or win[0]<loss[0]))
            else:row[f'forward_{n}d_close_pct']=None;row[f'mfe_{n}d_pct']=None;row[f'mae_{n}d_pct']=None
        rows.append(row)
    df=pd.DataFrame(rows)
    df.to_csv(OUT/'ALL_CAUSAL_ENTRY_SIGNALS_WITH_HOURLY_FUNDING_AND_FORWARD_LABELS.csv.gz',compression='gzip',index=False)
    summary=[]
    for year in (2020,2021,2022,2023):
        for tag in ['continuation','reversal','reclaim','highconviction','all']:
            sub=df[(df.year==year)&(df.sources.str.contains(tag))].copy()
            if not len(sub):continue
            scored=sub.dropna(subset=['forward_90d_close_pct'])
            summary.append({'year':year,'signal':tag,'n_total':len(sub),'n_90d_labeled':len(scored),'mean_30d':sub.forward_30d_close_pct.mean(),'median_30d':sub.forward_30d_close_pct.median(),'median_90d':sub.forward_90d_close_pct.median(),'mean_90d':sub.forward_90d_close_pct.mean(),'p_win_90d':(scored.forward_90d_close_pct>0).mean(),'p_plus50_before_minus20':sub.success_plus50_before_minus20_90d.mean() if 'success_plus50_before_minus20_90d' in sub else np.nan,'p_h_24h_recovery':sub.h_24h_close_location.mean() if 'h_24h_close_location' in sub else np.nan,'funding_coverage':sub.funding_7d_sum.notna().mean(),'hourly_coverage':sub.h_venue.notna().mean() if 'h_venue' in sub else np.nan})
    pd.DataFrame(summary).to_csv(OUT/'ALL_SIGNALS_YEARLY_FORWARD_OUTCOMES.csv',index=False)
    return df

def stress(pairs,ids,A,banks):
    spec=v.policies();names=['V20_continuation_60','V20_highconviction_60','V20_reclaim_60','V20_BTC_CORE']
    rows=[]
    for name in names:
        p=next(x for x in spec if x['name']==name)
        r,_,tr=v.simulate(p,pairs,ids,A,banks,save=True)
        rows.append({**r,'test':'BASE'})
        if name!='V20_BTC_CORE':
            rem=[x.strip() for x in r['top3_alt_profit_pairs'].split(',') if x.strip()]
            for label,fee,slip,ex in [('DOUBLE_COST',.006,.002,()),('NO_TOP3',.003,.001,rem),('DOUBLE_COST_NO_TOP3',.006,.002,rem)]:
                o,_,_=v.simulate(p,pairs,ids,A,banks,fee=fee,slip=slip,exclude=ex)
                rows.append({**o,'test':label})
        print('V20_EXT_STRESS',name,r['total_return_pct'],r['max_drawdown_pct'],flush=True)
    pd.DataFrame(rows).to_csv(OUT/'V20_EXTENDED_STRESS_AND_BENCHMARK.csv',index=False)
    return rows

def audit_execution_and_capture(rows,w,OUT):
    trade_by_policy={}
    ww=w[(w.year==2023)&(w.multiple>=5)].copy()
    for name in ('V20_continuation_60','V20_highconviction_60','V20_reclaim_60'):
        t=pd.read_csv(OUT/(name+'_TRADES.csv'))
        tt=t[t.pair!='BTC-USDT']
        records=[]
        for _,r in ww.iterrows():
            match=tt[(tt.pair==r.pair)&(tt.entry_day>=r.start_day)&(tt.entry_day<=r.peak_day)]
            records.append({'policy':name,'pair':r.pair,'wave_multiple':r.multiple,'start':int(r.start_day),'peak':int(r.peak_day),'max_quote_proxy_before_peak':r.max_pre_peak_estimated_quote,'trades_in_wave':len(match),'net_pnl_in_wave':match.pnl.sum(),'net_positive_trades':int((match.pnl>0).sum()),'any_trade':len(match)>0,'any_profit':(match.pnl>0).any()})
        trade_by_policy[name]=pd.DataFrame(records)
    out=pd.concat(trade_by_policy.values(),ignore_index=True)
    out.to_csv(OUT/'V20_REALIZED_WAVE_CAPTURE_2023.csv',index=False)
    print('V20_CAPTURE',out.groupby('policy')[['any_trade','any_profit']].sum().to_string(),flush=True)
    return out

def main():
    pairs,ids,A=v.build();banks=v.candidate_bank(pairs,ids,A);w=pd.read_csv(OUT/'RETROSPECTIVE_BIG_WAVES_AND_SIGNAL_COVERAGE.csv')
    hr,fu,lineage=context_asof(pairs,ids,A,banks)
    events_study(pairs,ids,A,banks,hr,fu,lineage)
    rows=stress(pairs,ids,A,banks)
    audit_execution_and_capture(rows,w,OUT)
    print('V20_EXTENDED_COMPLETE',flush=True)
if __name__=='__main__':main()
