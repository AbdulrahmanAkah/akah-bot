# AKAH R54-P0R3 read-only RD33 attribution. One-command runner. No package install.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Python venv is absent: $python" }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$work = Join-Path $HOME ("Downloads\AKAH_R54_P0R3_RD33_FORENSIC_WORK_" + $stamp)
$out = Join-Path $work 'OUTPUT'
New-Item -Path $out -ItemType Directory -Force | Out-Null
$worker = Join-Path $work 'r54_p0r3_rd33_forensic.py'
$source = @'
#!/usr/bin/env python3
"""AKAH R54-P0R3: read-only RD33 2X trade-ledger forensic; no market or 2024 data."""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, json, math, os, pathlib, statistics, sys, zipfile
from collections import defaultdict, Counter

VERSION='AKAH_R54_P0R3_RD33_2022_FAILURE_ATTRIBUTION_V1'
POLICY='MB_FIRST_RETEST_RECLAIM_WITHIN_FROZEN_72H'
PORTFOLIO='UNION_FOCUS'
EXPECTED={
 'C2':{'trades':158,'equity':132780.0428236915,'year_pnl':{'2022':-9865.924713688859,'2023':42645.96753738025}},
 'D2':{'trades':160,'equity':155718.37625953453,'year_pnl':{'2022':-9865.924713688859,'2023':65584.30097322336}},
 'E2':{'trades':162,'equity':136797.47539911213,'year_pnl':{'2022':-9865.924713688859,'2023':46663.40011280107}}
}
REQUIRED={'trade-ledger.csv','output-manifest.json','portfolio-run-metrics.csv','portfolio-period-metrics.csv','hard-gate-evaluation.csv'}
KEY_FIELDS={'policy_id','portfolio_id','universe_id','cost_multiplier','pair','entry_time','exit_time','net_pnl'}

class Fail(Exception):pass

def require(ok,message):
 if not ok:raise Fail(message)

def checksum(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while True:
   b=f.read(1024*1024)
   if not b:break
   h.update(b)
 return h.hexdigest().lower()

def parse_time(s):
 s=str(s or '').strip()
 if not s:raise Fail('TIMESTAMP_EMPTY')
 if s.endswith('Z'):s=s[:-1]+'+00:00'
 try:
  d=dt.datetime.fromisoformat(s)
 except Exception:raise Fail('TIMESTAMP_UNPARSEABLE:'+s[:80])
 if d.tzinfo is not None:
  d=d.astimezone(dt.timezone.utc).replace(tzinfo=None)
 require(d.year in (2022,2023),'NON_2022_2023_TRADE_TIMESTAMP:'+s[:80])
 return d

def fl(s):
 v=float(s); require(math.isfinite(v),'NONFINITE_NUMERIC');return v

def csv_dicts(path):
 with path.open('r',encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f)
  require(reader.fieldnames is not None,'EMPTY_CSV:'+path.name)
  for row in reader:yield row

def write_csv(path,rows,fields):
 with path.open('w',encoding='utf-8',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)

def summaries(rows,universe):
 # Use the time basis consistent with the original preregistered period result;
 # do not assume exit-year equals the original performance-year assignment.
 attribution=None
 for key in ['period_id','exit_time','entry_time','signal_time']:
  if key not in rows[0]:continue
  yearly={y:[] for y in ('2022','2023')}
  ok=True
  for t in rows:
   try:
    y=(str(t['period_id'])[-4:] if key=='period_id' else str(parse_time(t[key]).year))
    if y not in yearly:ok=False;break
    yearly[y].append(t)
   except Exception:ok=False;break
  if ok and all(abs(sum(fl(t['net_pnl']) for t in yearly[y])-EXPECTED[universe]['year_pnl'][y])<0.02 for y in yearly):
   attribution=(key,yearly);break
 require(attribution is not None, 'CANNOT_RECONCILE_RD33_YEAR_ATTRIBUTION:'+universe)
 time_basis,per_year=attribution
 per_week=defaultdict(list);per_pair=defaultdict(list);per_exit=defaultdict(list);per_month=defaultdict(list)
 for t in rows:
  t['_at']=parse_time(t['exit_time'])
  wk=(t['_at'].date()-dt.timedelta(days=t['_at'].weekday())).isoformat()
  per_week[wk].append(t);per_pair[t['pair']].append(t)
  per_exit[t.get('exit_reason','UNKNOWN')].append(t)
  per_month[t['_at'].strftime('%Y-%m')].append(t)
 def stats(group):
  pnl=[fl(t['net_pnl']) for t in group]
  pos=sorted((x for x in pnl if x>0),reverse=True)
  neg=sorted((x for x in pnl if x<0))
  return {'trades':len(group),'net_pnl':round(sum(pnl),8),'winners':len(pos),'losers':len(neg),
          'win_rate':round(len(pos)/len(group),8) if group else None,
          'positive_sum':round(sum(pos),8),'negative_sum':round(sum(neg),8),
          'profit_factor':round(sum(pos)/abs(sum(neg)),8) if neg else None,
          'top_1_winner':round(pos[0],8) if pos else None,
          'top_3_winners_sum':round(sum(pos[:3]),8),
          'top_3_share_of_gross_wins':round(sum(pos[:3])/sum(pos),8) if pos else None,
          'top_3_losers_sum':round(sum(neg[:3]),8)}
 yr={y:stats(v) for y,v in per_year.items()}
 require(len(rows)==EXPECTED[universe]['trades'],f'ROW_COUNT_DISAGREE:{universe}:{len(rows)}')
 weekly=[{'week_start_utc':k,**stats(v)} for k,v in sorted(per_week.items())]
 monthly=[{'month':k,**stats(v)} for k,v in sorted(per_month.items())]
 pair=[{'pair':k,**stats(v)} for k,v in per_pair.items()]
 pair.sort(key=lambda x:x['net_pnl'])
 reasons=[{'exit_reason':k,**stats(v)} for k,v in per_exit.items()]
 reasons.sort(key=lambda x:x['net_pnl'])
 return {'overall':stats(rows),'years':yr,'original_year_attribution_basis':time_basis,'weeks':weekly,'months':monthly,'pairs':pair,'exit_reasons':reasons,
         'weeks_with_realized_trade_exits':len(weekly),
         'weeks_with_positive_closed_trade_pnl':sum(r['net_pnl']>0 for r in weekly),
         'weeks_with_negative_closed_trade_pnl':sum(r['net_pnl']<0 for r in weekly)}

def run(repo,out):
 directory=repo/'data'/'research'/'rd33_p1_runtime'
 require(directory.is_dir(),'RD33_RUNTIME_FOLDER_MISSING:'+str(directory))
 missing=sorted(n for n in REQUIRED if not (directory/n).is_file())
 require(not missing,'RD33_REQUIRED_FILES_MISSING:'+','.join(missing))
 man=json.loads((directory/'output-manifest.json').read_text(encoding='utf-8-sig'))
 declared=man.get('files',{})
 for n in REQUIRED-{'output-manifest.json'}:
  require(n in declared,'MANIFEST_MISSING:'+n)
  path=directory/n;meta=declared[n]
  require(path.stat().st_size==int(meta['bytes']),'SIZE_MISMATCH:'+n)
  require(checksum(path)==meta['sha256'].lower(),'SHA_MISMATCH:'+n)
 input_hashes={n:checksum(directory/n) for n in sorted(REQUIRED)}
 metrics=list(csv_dicts(directory/'portfolio-run-metrics.csv'))
 period=list(csv_dicts(directory/'portfolio-period-metrics.csv'))
 gates=list(csv_dicts(directory/'hard-gate-evaluation.csv'))
 selected_metrics=[r for r in metrics if r.get('policy_id')==POLICY and r.get('portfolio_id')==PORTFOLIO and r.get('cost_multiplier','') in ('2.0','2')]
 require(len(selected_metrics)==3,'EXPECTED_THREE_METRIC_ROWS')
 metric_by_u={r['universe_id']:r for r in selected_metrics}
 require(set(metric_by_u)==set(EXPECTED),'UNIVERSE_SET_MISMATCH')
 for u,r in metric_by_u.items():
  require(int(float(r['trade_count']))==EXPECTED[u]['trades'],'TRADES_METRIC_MISMATCH:'+u)
  require(abs(fl(r['final_equity'])-EXPECTED[u]['equity'])<0.01,'FINAL_EQUITY_MISMATCH:'+u)
 periods=[r for r in period if r.get('policy_id')==POLICY and r.get('portfolio_id')==PORTFOLIO and r.get('cost_multiplier','') in ('2.0','2')]
 require(len(periods)==6,'EXPECTED_6_PERIOD_ROWS')
 target={u:[] for u in EXPECTED};header=None;total_read=0
 with (directory/'trade-ledger.csv').open('r',encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f);header=reader.fieldnames
  require(header and KEY_FIELDS.issubset(set(header)),f'TRADE_LEDGER_FIELDS_MISSING:{sorted(KEY_FIELDS-set(header or []))}')
  for r in reader:
   total_read+=1
   if r.get('policy_id')==POLICY and r.get('portfolio_id')==PORTFOLIO and r.get('cost_multiplier','') in ('2.0','2'):
    require(r.get('universe_id') in EXPECTED,'UNKNOWN_UNIVERSE')
    require(bool(r.get('pair','')),'TRADE_PAIR_EMPTY')
    parse_time(r['entry_time']);parse_time(r['exit_time'])
    fl(r['net_pnl']);target[r['universe_id']].append(r)
 summary={u:summaries(rows,u) for u,rows in target.items()}
 for r in periods:
  y=str(r['period_id']).rsplit('_',1)[-1];u=r['universe_id']
  require(y in ('2022','2023') and u in EXPECTED,'UNEXPECTED_PERIOD')
  ref=summary[u]['years'][y]
  require(abs(fl(r['net_pnl'])-ref['net_pnl'])<0.02,'YEAR_PERIOD_VALIDATION_FAILED:'+u+':'+y)
 failures=[]
 for u in EXPECTED:
  gg=[r['gate_id'] for r in gates if r.get('policy_id')==POLICY and r.get('universe_id')==u and r.get('passed','').lower()=='false']
  require(len(gg)==3,'RD33_GATE_BASELINE_DRIFT:'+u)
  failures.append({'universe':u,'failed_gates':gg})
 out.mkdir(parents=True,exist_ok=True)
 summary_file=out/'R54_P0R3_FORENSIC_SUMMARY.json'
 summary_file.write_text(json.dumps({'version':VERSION,'authority':'RD33_REPLAY_REPORT_ONLY_NO_NEW_STRATEGY','rd33_output_sha256':input_hashes,'policy':POLICY,'portfolio':PORTFOLIO,
                                    'total_trade_ledger_rows_read':total_read,'selected_rows':{u:len(t) for u,t in target.items()},
                                    'cohorts':summary,'failed_original_gates':failures,
                                    'economic_validation':'ORIGINAL_RD33_REPORT_RECONCILED_NOT_INDEPENDENT_FRESH_REPLAY',
                                    'historical_PIT_listing_certified':False,'2024_market_data_read':False,'market_rows_read':0,'live_orders':0,'production_modifications':0,
                                    'weekly_metric_warning':'WEEKLY_CLOSED_TRADE_PNL_NOT_MTM_PORTFOLIO_EQUITY;DO_NOT_INFER_POSITIVE_EQUITY_WEEKS'}
                                   ,indent=2,ensure_ascii=False,sort_keys=True),encoding='utf-8')
 cols=['policy_id','portfolio_id','universe_id','cost_multiplier','pair','signal_time','entry_time','exit_time','exit_reason','support_families',
       'entry_price','exit_price','quantity','entry_cost','exit_cost','net_pnl']
 for u,rows in target.items():
  write_csv(out/f'RD33_{u}_2X_TRADE_ROWS.csv',rows,[c for c in cols if c in header])
  s=summary[u]
  for name,field in [('WEEKLY_CLOSED_PNL','weeks'),('MONTHLY_CLOSED_PNL','months'),('PAIR_ATTRIBUTION','pairs'),('EXIT_REASON_ATTRIBUTION','exit_reasons')]:
   rr=s[field]
   if rr:write_csv(out/f'RD33_{u}_2X_{name}.csv',rr,list(rr[0]))
 (out/'README_RESULTS.md').write_text('# R54-P0R3\nRD33 2X trade-ledger forensic: output-manifest hashes verified; 2022 and 2023 trade PnL reconciled to canonical portfolio period metrics.\nNo market rows or 2024 access. This does not certify historical listing PIT. Weekly aggregation is CLOSED TRADE PNL, **not** mark-to-market portfolio equity.\n',encoding='utf-8')
 return summary_file

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--out',required=True);args=p.parse_args()
 out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
 try:
  path=run(pathlib.Path(args.repo),out)
  print('R54_P0R3_STATUS=PASS_RD33_TRADE_PNL_RECONCILED')
  print('R54_P0R3_SUMMARY='+str(path))
 except Exception as ex:
  (out/'R54_P0R3_BLOCKER.json').write_text(json.dumps({'status':'BLOCKED_NO_FABRICATED_RESULTS','blocker':str(ex),'market_rows_read':0,'production_mutations':0,'2024_market_data_read':False},indent=2),encoding='utf-8')
  print('R54_P0R3_STATUS=BLOCKED:'+str(ex))
  sys.exit(3)

if __name__=='__main__':main()
'@
[System.IO.File]::WriteAllText($worker, $source, (New-Object System.Text.UTF8Encoding($false)))
$pythonOutput = & $python $worker --repo $repo --out $out 2>&1
$exitCode = $LASTEXITCODE
$pythonOutput | ForEach-Object { Write-Host $_ }
$zip = Join-Path $HOME ("Downloads\UPLOAD_THIS_AKAH_R54_P0R3_RD33_FORENSIC_" + $stamp + '.zip')
if (Test-Path -LiteralPath $zip) { throw 'OUTPUT_ZIP_ALREADY_EXISTS' }
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zip -CompressionLevel Optimal
Write-Host ('R54_P0R3_OUTPUT_ZIP=' + $zip)
Write-Host ('R54_P0R3_WORKER_EXIT_CODE=' + $exitCode)
if ($exitCode -ne 0) { Write-Host 'R54_P0R3_STATUS=BLOCKED_OR_INCOMPLETE_OPEN_ZIP_FOR_DIAGNOSIS'; exit 3 }
Write-Host 'R54_P0R3_STATUS=PASS_READ_ONLY_RECONCILED'
