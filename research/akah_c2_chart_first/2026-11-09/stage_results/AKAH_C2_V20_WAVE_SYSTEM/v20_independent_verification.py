from pathlib import Path
import pandas as pd, numpy as np, json, hashlib, zipfile
from sklearn.metrics import roc_auc_score
R=Path('/mnt/data/AKAH_C2_V20_WAVE_SYSTEM')
s=pd.read_csv(R/'ALL_CAUSAL_ENTRY_SIGNALS_WITH_HOURLY_FUNDING_AND_FORWARD_LABELS.csv.gz')
s=s[s.year.between(2020,2023)].copy()
# All signals, not only positive cases. Deduplicate within coin and spaced 90 days; censor 90d events near 2023 end.
s=s.sort_values(['pair','entry_day','score'],ascending=[True,True,False]); s=s.drop_duplicates(['pair','entry_day'])
s['eligible_90d']=s.entry_day<=int(pd.Timestamp('2023-10-02',tz='UTC').value//10**6//86400000)
records=[]
for year in (2020,2021,2022,2023):
 y=s[(s.year==year)&s.eligible_90d& s.success_plus50_before_minus20_90d.notna()]
 r={'year':year,'all_unique_daily_signals':len(y),'distinct_pairs':y.pair.nunique(),'success50_before_stop20_pct':100*y.success_plus50_before_minus20_90d.astype(float).mean(),'median_90d_close_pct':y.forward_90d_close_pct.median(),'median_mfe_90d_pct':y.mfe_90d_pct.median(),'median_mae_90d_pct':y.mae_90d_pct.median()}
 # Greedy leave at least 90d between sampled signals by pair
 ix=[]
 for pair,df in y.groupby('pair',sort=False):
  last=-10000
  for row in df.itertuples():
   if row.entry_day-last>=90:ix.append(row.Index);last=row.entry_day
 z=y.loc[ix]
 r.update(nonoverlap_90d_n=len(z),nonoverlap_pairs=z.pair.nunique(),nonoverlap_success_pct=100*z.success_plus50_before_minus20_90d.astype(float).mean(),nonoverlap_median_90d_pct=z.forward_90d_close_pct.median(),nonoverlap_mean_90d_pct=z.forward_90d_close_pct.mean())
 records.append(r)
rec=pd.DataFrame(records);rec.to_csv(R/'INDEPENDENT_NONOVERLAP_SIGNAL_DIAGNOSTICS.csv',index=False)
# OOS ranker evidence
model=pd.read_csv(R/'FROZEN_2021_HOURLY_FUNDING_MODEL_VALIDATION.csv')
# 2023 captured vs actual positive wave entries, use v20 saved portfolios (do not conflate signals and actual fills)
w=pd.read_csv(R/'RETROSPECTIVE_BIG_WAVES_AND_SIGNAL_COVERAGE.csv'); w=w[(w.year==2023)&(w.multiple>=5)]
base=['V20_SPEC_early_new_75','V20_SPEC_early_consolidation_75','V20_continuation_60','V20_highconviction_60']
covers=[]
for pol in base:
 f=R/(pol+'_TRADES.csv')
 if not f.exists():continue
 t=pd.read_csv(f); t=t[t.pair.ne('BTC-USDT')]
 if 'pnl' not in t.columns:continue
 tt=[]
 for rr in w.itertuples():
  rows=t[(t.pair==rr.pair)&(t.entry_day>=rr.start_day)&(t.entry_day<=rr.peak_day)]
  tt.append((len(rows)>0,float(rows.pnl.sum()),rr.max_pre_peak_estimated_quote>=3e6))
 covers.append({'policy':pol,'2023_5x_waves':len(w),'entered':sum(q[0] for q in tt),'entered_and_positive_net':sum(q[0] and q[1]>0 for q in tt),'waves_liquid_3m_sometime':sum(q[2] for q in tt),'entered_liquid_3m':sum(q[0] and q[2] for q in tt),'entered_liquid_and_positive':sum(q[0] and q[2] and q[1]>0 for q in tt)})
pd.DataFrame(covers).to_csv(R/'INDEPENDENT_2023_WAVE_CAPTURE_AND_PROFIT.csv',index=False)
# independent ledger cash reconciliation: terminal return vs sum realized trades for BASE policies, with no forced cash injections
checks=[]
for pol in ['V20_continuation_60','V20_highconviction_60','V20_reclaim_60','V20_BTC_CORE','V20_SPEC_early_new_75','V20_SPEC_early_consolidation_75']:
 tr=pd.read_csv(R/(pol+'_TRADES.csv')); nav=pd.read_csv(R/(pol+'_NAV.csv')); initial=100000
 last=nav.iloc[-1]; realized=tr.pnl.sum(); delta=realized-(last.nav-initial)
 # after final liquidation, last daily nav before final liquidation fees; discrepancy should be small and negative
 checks.append({'policy':pol,'trades':len(tr),'sum_closed_pnl':realized,'last_marked_nav':last.nav,'diff_realized_minus_marked_nav':delta,'last_marked_alt_value':last.alt_value,'last_marked_btc_value':last.btc_value})
pd.DataFrame(checks).to_csv(R/'INDEPENDENT_LEDGER_MARK_TO_LIQUIDATION.csv',index=False)
# Dataset diagnostics sources
status=json.loads((R/'SOURCE_AND_DATA_STATUS.json').read_text());
summary={'hourly_funding_signals_total_unique_day_asset':int(len(s)),'signal_2020_2023_per_year':rec.to_dict(orient='records'),'wave_counts_2023_5x':len(w),'ranker_validation':model.to_dict(orient='records'),'wave_capture':covers,'source_count':status.get('pairs'),'PIT_certified':False,'future_holdout_independent':False,'no_2024':True}
(R/'V20_INDEPENDENT_FALSIFICATION_SUMMARY.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False,default=float))
print(rec.to_string(index=False));print(pd.DataFrame(covers).to_string(index=False));print(pd.DataFrame(checks).to_string(index=False))
