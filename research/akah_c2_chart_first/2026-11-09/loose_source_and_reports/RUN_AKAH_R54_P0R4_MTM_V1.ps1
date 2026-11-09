# AKAH R54-P0R4 — one-command read-only pinned RD33 daily MTM / entry timing
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$repo='C:\SIRAJ\Repositories\spot-speculation-bot'
$python=Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "PYTHON_VENV_MISSING: $python" }
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$work=Join-Path $HOME ("Downloads\AKAH_R54_P0R4_MTM_WORK_"+$stamp)
$out=Join-Path $work 'OUTPUT'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$worker=Join-Path $work 'r54_p0r4_mtm_entry.py'
$source=@'
#!/usr/bin/env python3
"""AKAH R54-P0R4 -- read-only original RD33 daily-MTM and entry-timing reconciliation.

Only consumes 3 SHA-pinned original RD33 2022-2023 outputs, not market tapes,
not 2024, not new strategy execution. Python standard library only.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, json, math, pathlib, sys
from collections import defaultdict

VERSION='AKAH_R54_P0R4_MTM_ENTRY_TIMING_V1'
POLICY='MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H'
PORTFOLIO='UNION_FOCUS'
INITIAL=100000.0
HASHES={
 'output-manifest.json':'fedecff908f01a956e5e6d549b8e19d4905e661e3c96af81c3fb9dc89db7954d',
 'daily-equity.csv':'32d6c55d999c5df8e81c20d7d6ed7ce9b25c4746a38a24ff790f8130b66c1317',
 'trade-ledger.csv':'c26c5017d55ed106bfe04546c67b01be28718b606e6ccd7411f90ede16544dd2',
 'portfolio-run-metrics.csv':'f6fe6d4037571000041e372757870cc55741e828b709a6786376794002ad517e',
 'portfolio-period-metrics.csv':'c2658c46f3f6b44539c51d62956dd83afec88266236ddc77df2587c1bccd0850',
}
REF={
 'C2':{'trades':158,'final':132780.0428236915,'2022':-9865.924713688859,'2023':42645.96753738025},
 'D2':{'trades':160,'final':155718.37625953453,'2022':-9865.924713688859,'2023':65584.30097322336},
 'E2':{'trades':162,'final':136797.47539911213,'2022':-9865.924713688859,'2023':46663.40011280107},
}
class Blocked(Exception):pass

def check(condition,message):
 if not condition:raise Blocked(message)

def sha256(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def timestamp(raw):
 s=str(raw or '').strip()
 check(bool(s),'MISSING_TIMESTAMP')
 try:
  t=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
 except ValueError:raise Blocked('INVALID_TIMESTAMP:'+s[:70])
 check(t.tzinfo is not None,'TIMESTAMP_NO_UTC_OFFSET:'+s[:70])
 t=t.astimezone(dt.timezone.utc)
 check(t.year in (2022,2023),'OUTSIDE_FROZEN_2022_2023_TIME_BOUNDARY:'+s[:70])
 return t

def number(raw):
 try:v=float(raw)
 except Exception:raise Blocked('INVALID_NUMERIC:'+str(raw)[:80])
 check(math.isfinite(v),'NONFINITE_NUMERIC')
 return v

def read_csv(path):
 with path.open('r',encoding='utf-8-sig',newline='') as f:
  dr=csv.DictReader(f)
  check(dr.fieldnames is not None, 'EMPTY_CSV:'+path.name)
  for row in dr:yield row

def sel(r):
 return r.get('policy_id')==POLICY and r.get('portfolio_id')==PORTFOLIO and r.get('universe_id') in REF and r.get('cost_multiplier','') in ('2','2.0')

def daily_summary(rows,universe):
 """Split ISO weeks across calendar year; mark-to-market end-of-day equity, not realized trade PnL."""
 check(bool(rows),'NO_DAILY_EQUITY:'+universe)
 rows.sort(key=lambda r:r['timestamp'])
 check(len(rows)==len({r['timestamp'].date() for r in rows}),'DUPLICATED_DAY:'+universe)
 check(rows[0]['timestamp'].year==2022 and rows[-1]['timestamp'].year==2023,'DAILY_CUTOFF_MISSING:'+universe)
 check(rows[0]['timestamp'].date()==dt.date(2022,1,1),'FIRST_DAY_IS_NOT_2022_JAN_01:'+universe)
 check(rows[-1]['timestamp'].date()==dt.date(2023,12,31),'LAST_DAY_IS_NOT_2023_DEC_31:'+universe)
 groups=[];prior=INITIAL;current_key=None;bag=[]
 year_ends={}
 for r in rows:
  date=r['timestamp'].date()
  monday=date-dt.timedelta(days=date.weekday())
  key=(date.year,monday)
  if current_key is not None and key!=current_key:
   last=bag[-1]
   final=last['equity'];delta=final-prior
   groups.append({'universe':universe,'year':current_key[0],'week_monday_utc':current_key[1].isoformat(),
                  'start_date_utc':bag[0]['timestamp'].date().isoformat(),
                  'end_date_utc':last['timestamp'].date().isoformat(),
                  'days_observed':len(bag),'start_equity':round(prior,6),'end_equity':round(final,6),
                  'weekly_mtm_pnl':round(delta,6), 'weekly_return_pct':round((delta/prior)*100,6),
                  'ending_cash':round(last['cash'],6),'ending_open_positions':last['open_positions'],
                  'ending_gross_exposure_fraction':round(last['gross_exposure_fraction'],6)})
   prior=final;bag=[]
  bag.append(r);current_key=key
  if date.month==12 and date.day==31:year_ends[date.year]=r['equity']
 if bag:
  last=bag[-1];delta=last['equity']-prior
  groups.append({'universe':universe,'year':current_key[0],'week_monday_utc':current_key[1].isoformat(),
                 'start_date_utc':bag[0]['timestamp'].date().isoformat(),
                 'end_date_utc':last['timestamp'].date().isoformat(),
                 'days_observed':len(bag),'start_equity':round(prior,6),'end_equity':round(last['equity'],6),
                 'weekly_mtm_pnl':round(delta,6),'weekly_return_pct':round((delta/prior)*100,6),
                 'ending_cash':round(last['cash'],6),'ending_open_positions':last['open_positions'],
                 'ending_gross_exposure_fraction':round(last['gross_exposure_fraction'],6)})
 check(len(year_ends)==2,'MISSING_DEC31_MARK')
 check(abs(year_ends[2022]-INITIAL-REF[universe]['2022'])<.03,'2022_EQUITY_DOES_NOT_RECONCILE:'+universe)
 check(abs(year_ends[2023]-year_ends[2022]-REF[universe]['2023'])<.03,'2023_EQUITY_DOES_NOT_RECONCILE:'+universe)
 check(abs(year_ends[2023]-REF[universe]['final'])<.03,'FINAL_EQUITY_DOES_NOT_RECONCILE:'+universe)
 years={}
 for year in (2022,2023):
  g=[w for w in groups if w['year']==year]
  positive=sum(w['weekly_mtm_pnl']>0.005 for w in g)
  negative=sum(w['weekly_mtm_pnl']<-0.005 for w in g)
  flat=len(g)-positive-negative
  years[str(year)]={'weeks':len(g),'positive_mtm_weeks':positive,'negative_mtm_weeks':negative,
                    'flat_mtm_weeks':flat,'worst_week_pnl':round(min(w['weekly_mtm_pnl'] for w in g),6),
                    'best_week_pnl':round(max(w['weekly_mtm_pnl'] for w in g),6),
                    'year_end_equity':round(year_ends[year],6),
                    'year_net_mtm_pnl':round((year_ends[year]-(INITIAL if year==2022 else year_ends[2022])),6)}
 return groups,{'daily_rows':len(rows),'first_day':rows[0]['timestamp'].date().isoformat(),
                'last_day':rows[-1]['timestamp'].date().isoformat(), 'years':years}

def entry_lag_bin(hours,family):
 if family=='RELATIVE_STRENGTH_ROTATION':return 'RS_IMMEDIATE'
 if hours<=2:return 'MB_LE_2H'
 if hours<=24:return 'MB_3_TO_24H'
 if hours<=48:return 'MB_25_TO_48H'
 if hours<=74:return 'MB_49_TO_74H'
 return 'MB_ABOVE_74H_INVALID_REVIEW'

def entry_lag_summary(rows,universe):
 check(len(rows)==REF[universe]['trades'],'TRADE_COUNT_MISMATCH:'+universe)
 buckets=defaultdict(list);out=[]
 for r in rows:
  signal=timestamp(r['signal_time']);entry=timestamp(r['entry_time']);ex=timestamp(r['exit_time'])
  check(signal<=entry<=ex,'CAUSAL_ORDER_BROKEN')
  hours=(entry-signal).total_seconds()/3600
  family=r['support_families']
  check(family in ('RELATIVE_STRENGTH_ROTATION','MOMENTUM_BREAKOUT'),'UNEXPECTED_FAMILY:'+family)
  label=entry_lag_bin(hours,family)
  check(label!='MB_ABOVE_74H_INVALID_REVIEW','EXCESSIVE_MB_SIGNAL_ENTRY_LAG')
  pnl=number(r['net_pnl'])
  year=ex.year
  buckets[(year,family,label)].append(pnl)
  out.append({'universe':universe,'year':year,'pair':r['pair'],'family':family,'lag_bin':label,
              'signal_time_utc':signal.isoformat(),'entry_time_utc':entry.isoformat(),
              'exit_time_utc':ex.isoformat(),'signal_to_entry_hours':round(hours,6),'net_pnl':round(pnl,6)})
 labels=[]
 for (year,family,lag),pnl in sorted(buckets.items()):
  labels.append({'universe':universe,'year':year,'family':family,'lag_bin':lag,'count':len(pnl),
                 'wins':sum(x>0 for x in pnl),'net_pnl':round(sum(pnl),6),
                 'mean_net_pnl':round(sum(pnl)/len(pnl),6)})
 return out,labels

def write_csv(path,rows):
 check(bool(rows),'EMPTY_OUTPUT:'+path.name)
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction='ignore',lineterminator='\n')
  w.writeheader();w.writerows(rows)

def run(repo,out):
 directory=repo/'data'/'research'/'rd33_p1_runtime'
 check(directory.is_dir(),'ORIGINAL_RD33_DIRECTORY_MISSING:'+str(directory))
 for name,sha in HASHES.items():
  path=directory/name;check(path.is_file(),'SOURCE_MISSING:'+name)
  check(sha256(path)==sha,'PINNED_SHA_MISMATCH:'+name)
 manifest=json.loads((directory/'output-manifest.json').read_text(encoding='utf-8-sig'))
 for name,sha in HASHES.items():
  if name=='output-manifest.json':continue
  declared=manifest.get('files',{}).get(name,{})
  check(declared.get('sha256','').lower()==sha,'MANIFEST_PIN_MISMATCH:'+name)
  check(int(declared.get('bytes',-1))==(directory/name).stat().st_size,'FILE_SIZE_DRIFT:'+name)
 metrics={}
 for r in read_csv(directory/'portfolio-run-metrics.csv'):
  if sel(r):
   u=r['universe_id'];check(u not in metrics,'DUPLICATED_METRIC_ROW:'+u)
   check(int(float(r['trade_count']))==REF[u]['trades'],'METRIC_TRADE_COUNT:'+u)
   check(abs(number(r['final_equity'])-REF[u]['final'])<.02,'METRIC_EQUITY:'+u)
   metrics[u]=r
 check(set(metrics)==set(REF),'NOT_ALL_THREE_UNIVERSES_IN_METRICS')
 dailies=defaultdict(list);read_daily=0
 for r in read_csv(directory/'daily-equity.csv'):
  read_daily+=1
  # all rows are pinned RD33 2022-2023 source, validate before filtering.
  time=timestamp(r.get('timestamp',''))
  if not sel(r):continue
  dailies[r['universe_id']].append({'timestamp':time,'equity':number(r['equity']),
      'cash':number(r['cash']),'gross_exposure_fraction':number(r['gross_exposure_fraction']),
      'open_positions':int(float(r['open_positions']))})
 all_weekly=[];daily_summaries={}
 for u in REF:
  weekly,info=daily_summary(dailies[u],u);all_weekly.extend(weekly);daily_summaries[u]=info
 all_trades=defaultdict(list);total_trade_rows=0
 for r in read_csv(directory/'trade-ledger.csv'):
  total_trade_rows+=1
  if not sel(r):continue
  all_trades[r['universe_id']].append(r)
 all_lags=[];all_lag_groups=[]
 for u in REF:
  trades,group=entry_lag_summary(all_trades[u],u)
  all_lags.extend(trades);all_lag_groups.extend(group)
 out.mkdir(parents=True,exist_ok=True)
 write_csv(out/'R54_P0R4_WEEKLY_MARK_TO_MARKET_2X.csv',all_weekly)
 write_csv(out/'R54_P0R4_PREENTRY_LAG_BINS_2X.csv',all_lag_groups)
 write_csv(out/'R54_P0R4_CAUSAL_ENTRY_TIMING_ROWS_2X.csv',all_lags)
 result={'version':VERSION,'status':'PASS_ORIGINAL_RD33_DAILY_MTM_RECONCILED','policy':POLICY,'portfolio':PORTFOLIO,
  'scope':'2022_2023_FROZEN_SOURCE_ONLY','2024_market_rows_read':False,'new_strategy_tested':False,
  'independent_fresh_market_replay':False,'PIT_listing_certified':False,'production_mutations':0,'live_orders':0,
  'verified_source_sha256':HASHES,'all_original_daily_rows_read':read_daily,'all_original_trade_rows_read':total_trade_rows,
  'daily_mtm':daily_summaries,
  'warnings':['Calendar-week PnL is changes in RD33 historical daily marked equity, NOT realized-trade aggregation.',
    'Weekly figure derives from original replay, not independent recalculation from raw market bars.',
    'Entry-to-signal lag is determined at entry; subgroup PnL is retrospective and NOT evidence of a profitable entry filter.',
    'The original pending-lifecycle ledger lacks a cost-multiplier identifier; no unverified join to 2X trades is attempted.',
    'No PIT historical listing certification. A new economic strategy remains blocked.']}
 (out/'R54_P0R4_REPORT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True),encoding='utf-8')
 text='\n'.join(['# R54-P0R4 RD33 Mark-to-Market & Entry Timing',
       'Status: PASS_ORIGINAL_RD33_DAILY_MTM_RECONCILED','Original SHA-pinned outputs. No market tape read. No 2024. No live trade.',
       'Weekly PnL is daily marked equity end-of-week difference, including open positions. This is not independently replayed equity.',
       'Entry lag is known at entry but retrospective bin PnL is NOT a validated predictive rule.',
       'Pending lifecycle is not cost tagged: no spurious confirmation-to-2X mapping.','Historical listing PIT not certified.',
       'Next gate: independent historical membership/venue authority and causal pre-entry features BEFORE any economic policy comparison.'])+'\n'
 (out/'README_RESULTS.md').write_text(text,encoding='utf-8')
 return result

def selftest():
 def mk(day,equity):return {'timestamp':dt.datetime.fromisoformat(day+'T23:00:00+00:00'),
   'equity':equity,'cash':equity,'gross_exposure_fraction':0.0,'open_positions':0}
 # test internal calculation separately without reference-year reconciliation
 check(entry_lag_bin(1,'RELATIVE_STRENGTH_ROTATION')=='RS_IMMEDIATE','SELFTEST_RS')
 check(entry_lag_bin(2,'MOMENTUM_BREAKOUT')=='MB_LE_2H','SELFTEST_MB_2')
 check(entry_lag_bin(24,'MOMENTUM_BREAKOUT')=='MB_3_TO_24H','SELFTEST_MB_24')
 check(entry_lag_bin(48,'MOMENTUM_BREAKOUT')=='MB_25_TO_48H','SELFTEST_MB_48')
 check(entry_lag_bin(74,'MOMENTUM_BREAKOUT')=='MB_49_TO_74H','SELFTEST_MB_74')
 check(entry_lag_bin(75,'MOMENTUM_BREAKOUT').startswith('MB_ABOVE'),'SELFTEST_MB_INVALID')
 t=timestamp('2023-12-31 23:00:00+00:00');check(t.year==2023,'SELFTEST_TIMESTAMP')
 try:timestamp('2024-01-01 00:00:00+00:00')
 except Blocked:pass
 else:raise Blocked('SELFTEST_2024_BOUNDARY_FAILED')
 try:timestamp('2022-01-01 00:00:00')
 except Blocked:pass
 else:raise Blocked('SELFTEST_TIMEZONE_REQUIRED_FAILED')
 check(mk('2022-01-01',100000)['equity']==INITIAL,'SELFTEST_EQUITY_INPUT')
 # Two complete synthetic years, with exact pinned C2 annual profit accounting.
 rows=[]
 first=dt.date(2022,1,1)
 end22=INITIAL+REF['C2']['2022']
 end23=end22+REF['C2']['2023']
 for i in range(730):
  date=first+dt.timedelta(days=i)
  if i<365:equity=INITIAL+(end22-INITIAL)*(i+1)/365
  else:equity=end22+(end23-end22)*(i-364)/365
  rows.append(mk(date.isoformat(),equity))
 weeks,info=daily_summary(rows,'C2')
 check(len(weeks)>=104,'SELFTEST_WEEK_COUNT')
 check(sum(x['weekly_mtm_pnl'] for x in weeks)>32779.99,'SELFTEST_MTM_TELESCOPING')
 check(abs(info['years']['2022']['year_net_mtm_pnl']-REF['C2']['2022'])<.02,'SELFTEST_YEAR22')
 check(abs(info['years']['2023']['year_net_mtm_pnl']-REF['C2']['2023'])<.02,'SELFTEST_YEAR23')
 print('R54_P0R4_SELFTEST=PASS_13');return True

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--repo');ap.add_argument('--out');ap.add_argument('--selftest',action='store_true')
 a=ap.parse_args()
 try:
  if a.selftest:selftest();return
  check(bool(a.repo and a.out),'MISSING_REPO_OR_OUTPUT')
  out=pathlib.Path(a.out)
  result=run(pathlib.Path(a.repo),out)
  for u,info in result['daily_mtm'].items():
   for y,stats in info['years'].items():
    print(f"R54_P0R4_WEEKLY_MTM_{u}_{y}=POS_{stats['positive_mtm_weeks']}_NEG_{stats['negative_mtm_weeks']}_FLAT_{stats['flat_mtm_weeks']}")
  print('R54_P0R4_STATUS=PASS_ORIGINAL_RD33_DAILY_MTM_RECONCILED')
 except Exception as ex:
  print('R54_P0R4_STATUS=BLOCKED:'+str(ex))
  if a.out:
   out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
   (out/'R54_P0R4_BLOCKER.json').write_text(json.dumps({'status':'BLOCKED_NO_ASSUMED_RESULTS',
     'reason':str(ex),'2024_market_rows_read':False,'production_mutations':0,'live_orders':0},indent=2),encoding='utf-8')
  sys.exit(3)

if __name__=='__main__':main()

'@
[System.IO.File]::WriteAllText($worker,$source,[System.Text.Encoding]::UTF8)
$log=Join-Path $work 'R54_P0R4_TERMINAL.log'
"R54_P0R4_MODE=READ_ONLY_RD33_PINNED_DAILY_MTM_NO_MARKET_NO_2024_NO_PRODUCTION" | Tee-Object -FilePath $log
& $python $worker --selftest 2>&1 | Tee-Object -Append $log
if ($LASTEXITCODE -ne 0) { throw 'R54_P0R4_SELFTEST_FAILED' }
& $python $worker --repo $repo --out $out 2>&1 | Tee-Object -Append $log
$code=$LASTEXITCODE
Copy-Item -LiteralPath $log -Destination (Join-Path $out 'R54_P0R4_TERMINAL.log') -Force
$archive=Join-Path $HOME ("Downloads\UPLOAD_THIS_AKAH_R54_P0R4_MTM_AND_ENTRY_"+$stamp+".zip")
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $archive -Force
"R54_P0R4_OUTPUT_ZIP=$archive"
if ($code -ne 0) { "R54_P0R4_WORKER_EXIT_CODE=$code"; exit $code }
"R54_P0R4_COMPLETE=PASS"
