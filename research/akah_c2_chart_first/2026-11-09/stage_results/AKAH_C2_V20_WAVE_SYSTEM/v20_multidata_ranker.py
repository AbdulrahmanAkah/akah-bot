#!/usr/bin/env python3
"""Train historical features through Sep 2021, freeze score, analyze 2022/23; no live orders.
Warnings: holdout 2022/23 previously researched in AKAH V1-V19, not virgin out of sample.
"""
import sys,json
from pathlib import Path
import pandas as pd,numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score,average_precision_score,brier_score_loss
sys.path.insert(0,'/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')
import v20_research as v
OUT=Path('/mnt/data/AKAH_C2_V20_WAVE_SYSTEM');DAY=v.DAY
FIELDS=['ret5_pct','ret20_pct','ret60_pct','btc20_pct','relative20_pct','rsi14','atrpct','rvol','prior_90d_high_ratio','listed_bars_so_far','qprev_estimated_or_original','quote_native_last_signal_day','h_1pct_count','h_upbar_ratio','h_last4h_return','h_24h_close_location','h_last4h_volume_ratio','h_range24h','funding_7d_sum']

def main():
    raw=pd.read_csv(OUT/'ALL_CAUSAL_ENTRY_SIGNALS_WITH_HOURLY_FUNDING_AND_FORWARD_LABELS.csv.gz')
    raw['qprev_estimated_or_original']=np.log1p(raw['qprev_estimated_or_original'].clip(lower=0))
    raw['listed_bars_so_far']=np.log1p(raw['listed_bars_so_far'].clip(lower=0))
    for x in FIELDS:raw[x]=pd.to_numeric(raw[x],errors='coerce')
    for x in ('ret5_pct','ret20_pct','ret60_pct','btc20_pct','relative20_pct'):
        raw[x]=raw[x].clip(-90,500)
    # Train on complete labels known by end 2021. 2021 entries after Sep30 have 90d labels leaking into 2022 and are excluded.
    train=raw[(raw.entry_day < int(pd.Timestamp('2021-10-01',tz='UTC').value//10**6//DAY)) & raw.success_plus50_before_minus20_90d.notna()].copy()
    y=train.success_plus50_before_minus20_90d.astype(int)
    X=train[FIELDS].replace([np.inf,-np.inf],np.nan)
    model=HistGradientBoostingClassifier(max_iter=140,max_leaf_nodes=11,min_samples_leaf=75,learning_rate=.035,l2_regularization=5.0,random_state=1919,early_stopping=False)
    model.fit(X,y)
    raw['learned_probability']=model.predict_proba(raw[FIELDS].replace([np.inf,-np.inf],np.nan))[:,1]
    thresh=float(np.percentile(raw.loc[train.index,'learned_probability'],60))
    rows=[]
    for year in (2020,2021,2022,2023):
        df=raw[(raw.year==year)&raw.success_plus50_before_minus20_90d.notna()].copy()
        if not len(df):continue
        t=df.success_plus50_before_minus20_90d.astype(int).to_numpy();p=df.learned_probability.to_numpy()
        q=np.quantile(p,.8);sel=t[p>=q]
        rows.append({'year':year,'split':'training' if year<=2021 else 'historical_eval_reused','samples':len(t),'base_event_success50_before_loss20':float(t.mean()),'score_auc':roc_auc_score(t,p) if len(set(t))==2 else None,'average_precision':average_precision_score(t,p) if len(set(t))==2 else None,'top20pct_win':float(sel.mean()),'top20pct_events':len(sel),'fixed_train_threshold':thresh,'fraction_above_fixed_threshold':float((p>=thresh).mean()),'fixed_threshold_win':float(t[p>=thresh].mean()) if (p>=thresh).any() else None})
    pd.DataFrame(rows).to_csv(OUT/'FROZEN_2021_HOURLY_FUNDING_MODEL_VALIDATION.csv',index=False)
    print('V20_RANKER_VALIDATION',pd.DataFrame(rows).to_string(index=False),flush=True)
    pairs,ids,A=v.build();banks=v.candidate_bank(pairs,ids,A)
    pmap={(ids[r.pair],int(r.entry_day)):float(r.learned_probability) for r in raw.itertuples(index=False) if r.pair in ids}
    def refined(tag,filter_mode):
        b={}
        for day,items in banks[tag].items():
            selected=[]
            for score,a in items:
                pp=pmap.get((a,day))
                if pp is None:continue
                if filter_mode=='cut' and pp<thresh:continue
                selected.append((pp,a))
            if selected:b[day]=sorted(selected,key=lambda x:(-x[0],pairs[x[1]]))
        return b
    banks['learned_rank']=refined('all','rank')
    banks['learned_cut']=refined('all','cut')
    banks['learned_rank_high']=refined('highconviction','rank')
    bank_stats={name:sum(len(x) for x in bank.values()) for name,bank in banks.items()}
    specs=[]
    for name,bank in [('V20_EVAL_ALL_ORIGINAL','all'),('V20_EVAL_LEARNED_RANK','learned_rank'),('V20_EVAL_LEARNED_CUT','learned_cut'),('V20_EVAL_HIGHCONV_ORIGINAL','highconviction'),('V20_EVAL_HIGHCONV_RANK','learned_rank_high')]:
        specs.append({'name':name,'bank':bank,'btc':.5,'alt':.60,'positions':4,'atr':5.,'risk':.018,'participation':.003,'poscap':.30,'minstop':.08,'cooldown':3,'bear':True,'trend_exit':True})
    baseline={'name':'V20_EVAL_BTC_CORE','bank':'all','btc':1.,'alt':0.,'positions':0,'atr':6.,'risk':0.,'participation':.003,'poscap':.30,'minstop':.08,'cooldown':3,'bear':False,'trend_exit':True}
    specs.append(baseline)
    START2022=int(pd.Timestamp('2022-01-01',tz='UTC').value//10**6//DAY)
    results=[]
    for policy in specs:
        result,nav,tr=v.simulate(policy,pairs,ids,A,banks,start=START2022,end=v.END,save=True)
        results.append(result)
        print('V20_RANKER_POLICY',policy['name'],round(result['total_return_pct'],2),round(result['max_drawdown_pct'],2),round(result['2022_pct'],2),round(result['2023_pct'],2),flush=True)
    pd.DataFrame(results).to_csv(OUT/'FROZEN_RANKER_PORTFOLIO_EVALUATION_2022_2023.csv',index=False)
    (OUT/'RANKER_PRECOMMIT.json').write_text(json.dumps({'features':FIELDS,'train_end_exclusive':'2021-10-01','target':'90d plus50% high before minus20% low: equal-day ambiguous counted failure','model':'HistGradientBoostingClassifier','max_iter':140,'max_leaf_nodes':11,'min_samples_leaf':75,'learning_rate':.035,'l2_regularization':5.,'threshold_training_60pct':thresh,'source_coverage':'observed prior day 1h & Binance funding 7d with missing values explicit','evaluation_previously_researched_not_independent':True,'ticker_pit_certified':False,'signal_counts':bank_stats,'features_lookahead':'none_known; raw market sources provenance unverified'},indent=2))
    print('V20_RANKER_COMPLETE',flush=True)
if __name__=='__main__':main()
