# AKAH BOT - C2 SOURCE-FIRST FULL HISTORY MEGA V1
# Read-only against repository; public terminal requests only; NO market data >= 2024.
$ErrorActionPreference = 'Stop'
$repo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$dl = Join-Path $HOME 'Downloads'
if (-not (Test-Path -LiteralPath $repo -PathType Container)) { throw "REPO_NOT_FOUND: $repo" }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$run = Join-Path $dl ('AKAH_C2_FULL_HISTORY_RUN_' + $stamp)
New-Item -ItemType Directory -Path $run -Force | Out-Null
$worker = Join-Path $run 'akah_c2_terminal_vault.py'
$payload = @'
#!/usr/bin/env python3
"""AKAH C2 SOURCE-FIRST TERMINAL VAULT V1. Read-only, cutoff 2023, no trading.
Python standard library only. No invented universe membership; all network calls from USER terminal.
"""
from __future__ import annotations
import argparse, ast, csv, datetime as dt, gzip, hashlib, io, json, os, pathlib, re, shutil, sys, time, traceback, urllib.parse, urllib.error, urllib.request, zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

UTC=dt.timezone.utc
END=dt.datetime(2024,1,1,tzinfo=UTC) # exclusive; NEVER open 2024 data
BEGIN=dt.datetime(2017,1,1,tzinfo=UTC)
END_S=int(END.timestamp())
UA='AKAH-C2-Research-Data-Vault/1.0 (terminal-readonly)'
EXTS={'.json','.csv','.py','.md','.txt','.toml','.yaml','.yml'}
BAD_DIRS={'.git','.venv','node_modules','__pycache__','.pytest_cache','artifacts','tmp','temp','logs'}
PAIR_RE=re.compile(r'^[A-Z0-9]{2,24}[-_/]?(USDT|USDC|BTC|ETH)$')
MARKET_KEYS=('pair','symbol','market','asset','ticker','instrument','base_asset','trading_pair')
UNIV_KEYS=('universe','universe_id','universe_name','cohort','cohort_id','universe_code')

class Audit:
 def __init__(self,out):
  self.out=out; self.errors=[]; self.status={};self.retrieval=[];self.universe_evidence=[];self.listed=[];self.rejections=[];self.gaps=[]
 def write(self,name,obj):
  p=self.out/name;p.parent.mkdir(parents=True,exist_ok=True)
  p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str,sort_keys=True)+'\n',encoding='utf-8')
 def err(self,step,exc):
  self.errors.append({'stage':step,'error':repr(exc),'trace':traceback.format_exc()[-1500:]})
  print('WARN',step,str(exc)[:200],flush=True)

def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def pairnorm(x):
 if not isinstance(x,str):return None
 s=x.strip().upper().replace('_','-').replace('/','-').replace(' ','')
 if s.endswith('USDT') and not s.endswith('-USDT'):s=s[:-4]+'-USDT'
 if s.endswith('USDC') and not s.endswith('-USDC'):s=s[:-4]+'-USDC'
 if s.endswith('BTC') and not s.endswith('-BTC'):s=s[:-3]+'-BTC'
 if s.endswith('ETH') and not s.endswith('-ETH'):s=s[:-3]+'-ETH'
 return s if PAIR_RE.fullmatch(s) else None

def collect_strs(node):
 if isinstance(node,str):
  p=pairnorm(node);return {p} if p else set()
 if isinstance(node,(list,tuple,set)):
  ret=set()
  for v in node:ret |= collect_strs(v)
  return ret
 if isinstance(node,dict):
  ret=set()
  for k,v in node.items():
   p=pairnorm(k)
   if p:ret.add(p)
   ret |= collect_strs(v)
  return ret
 return set()

def walk_paths(roots):
 for root in roots:
  if not root.exists():continue
  for dp,dns,fns in os.walk(root):
   dns[:]=[d for d in dns if d not in BAD_DIRS and not d.startswith('2024')]
   for fn in fns:
    p=pathlib.Path(dp)/fn
    if p.suffix.lower() in EXTS and '2024' not in p.parts:
     yield p

def c2_discovery(repo,dl,audit):
 roots=[repo/'config',repo/'governance',repo/'src',repo/'scripts',repo/'data'/'research',dl/'AKAH_R13R27_MEGA_WORK']
 candidates=[]; hits=[]; count=0
 for p in walk_paths(roots):
  count+=1
  try:
   sz=p.stat().st_size
   if sz>64*1024*1024:
    audit.rejections.append({'path':str(p),'reason':'TEXT_FILE_OVER_64MB_DISCOVERY_NOT_READ'})
    continue
   suff=p.suffix.lower()
   if suff=='.csv':
    with p.open('r',encoding='utf-8-sig',errors='replace',newline='') as f:
     reader=csv.DictReader(f)
     if not reader.fieldnames:continue
     cols={x.lower().strip():x for x in reader.fieldnames if x}
     us=[cols[k] for k in UNIV_KEYS if k in cols]
     pairs=[cols[k] for k in MARKET_KEYS if k in cols]
     if not us or not pairs:continue
     found=set(); c2_rows=0; inspected=0; dates=[]
     for r in reader:
      inspected+=1
      if any(str(r.get(k,'')).strip().upper()=='C2' for k in us):
       c2_rows+=1
       for pk in pairs:
        q=pairnorm(r.get(pk));
        if q:found.add(q)
       if 'date' in cols and len(dates)<5:dates.append(r.get(cols['date']))
     if c2_rows:
      ev={'path':str(p),'format':'CSV_ROWS','row_count':c2_rows,'symbols':sorted(found),'dates_sample':dates,'has_asof_date':'date' in cols,'sha256':sha(p),'authority':'POTENTIAL_MAPPING_NOT_PIT_CERTIFICATION'}
      candidates.append(ev);hits.append({'path':str(p),'rows_with_C2':c2_rows,'pair_count':len(found)})
   elif suff=='.json':
    raw=p.read_text(encoding='utf-8-sig',errors='replace')
    if 'C2' not in raw:continue
    hits.append({'path':str(p),'C2_count':raw.count('C2'),'size':sz})
    try:x=json.loads(raw)
    except:continue
    def sub(x,path='',depth=0):
     if depth>10:return
     if isinstance(x,dict):
      for k,v in x.items():
       if str(k).upper()=='C2':
        syms=collect_strs(v)
        if syms:candidates.append({'path':str(p),'format':'JSON_C2_KEY','key_path':path+'.'+str(k),'symbols':sorted(syms),'sha256':sha(p),'authority':'POTENTIAL_MAPPING_NOT_PIT_CERTIFICATION'})
       if isinstance(v,dict) and any(str(v.get(k,'')).strip().upper()=='C2' for k in UNIV_KEYS):
        syms=set()
        for key in ('members','symbols','pairs','eligible','instruments','assets'):
         if key in v:syms |= collect_strs(v[key])
        if syms:candidates.append({'path':str(p),'format':'JSON_C2_OBJECT','key_path':path+'.'+str(k),'symbols':sorted(syms),'sha256':sha(p),'authority':'POTENTIAL_MAPPING_NOT_PIT_CERTIFICATION'})
       if isinstance(v,(list,dict)):sub(v,path+'.'+str(k),depth+1)
     elif isinstance(x,list):
      for i,v in enumerate(x):
       if isinstance(v,(list,dict)):sub(v,path+f'[{i}]',depth+1)
    sub(x)
   else:
    # Extract ONLY literal, static source mappings to C2, without importing project code.
    if suff=='.py':
     try:
      syntax=ast.parse(p.read_text(encoding='utf-8-sig',errors='replace'))
      for node in ast.walk(syntax):
       if isinstance(node,(ast.Assign,ast.AnnAssign)):
        targets=node.targets if isinstance(node,ast.Assign) else [node.target]
        ids=[t.id for t in targets if isinstance(t,ast.Name)]
        for ident in ids:
         if 'C2' not in ident.upper():continue
         if not any(x in ident.upper() for x in ('UNIVERSE','MEMBER','ELIGIBLE','PAIRS','SYMBOLS')):continue
         try:syms=collect_strs(ast.literal_eval(node.value))
         except:continue
         if len(syms)>=2:candidates.append({'path':str(p),'format':'PYTHON_LITERAL_C2_MAPPING','variable':ident,'symbols':sorted(syms),'sha256':sha(p)})
     except Exception as e:audit.err('C2_STATIC_SOURCE_'+str(p),e)
    # Source-code/notes hits are EVIDENCE only, never silently converted into membership.
    lines=[]
    with p.open('r',encoding='utf-8-sig',errors='replace') as f:
     for n,line in enumerate(f,1):
      if re.search(r'(?<![A-Za-z0-9])C2(?![A-Za-z0-9])',line) and len(lines)<120:
       lines.append({'line':n,'text':line[:350].rstrip()})
    if lines:hits.append({'path':str(p),'samples':lines})
  except Exception as e:audit.err('DISCOVERY_'+str(p),e)
 audit.write('C2_SOURCE_DISCOVERY.json',{'files_considered':count,'candidates':candidates,'references':hits[:1000], 'hard_rule':'No C2 inferred from 20-pair cohort or from traded-only ledger'})
 # Explicit mapping with 2+ pairs, no trades / pnl / outcomes. Prefer documented universe registry.
 qualified=[]
 for c in candidates:
  path=c['path'].lower().replace('\\','/')
  if any(z in path for z in ('trade-ledger','trades','pnl','portfolio-run','period-metrics','concentration')):continue
  if len(c['symbols'])<2:continue
  structurally_authoritative=any(z in path for z in ('universe','membership','cohort','eligible','registry')) or '/governance/' in path or '/config/' in path or c['format']=='PYTHON_LITERAL_C2_MAPPING'
  if not structurally_authoritative:continue
  confidence=4 if any(z in path for z in ('universe','membership','cohort','eligible','registry')) else 2
  if '/governance/' in path or '/config/' in path:confidence+=2
  if 'rd26' in path or 'rd27' in path or 'rd33' in path:confidence+=1
  qualified.append((confidence,c))
 if not qualified:
  return None,{'status':'BLOCKED_EXACT_C2_MEMBERSHIP_NOT_LOCATED','possible_mappings':len(candidates),'readable_C2_references':len(hits)}
 best=max(x[0] for x in qualified)
 winners=[x[1] for x in qualified if x[0]==best]
 sets={tuple(x['symbols']) for x in winners}
 if len(sets)!=1:
  return None,{'status':'BLOCKED_CONFLICTING_C2_UNIVERSE_AUTHORITIES','candidates':winners}
 chosen=sorted(sets.pop())
 return chosen,{'status':'C2_MEMBERSHIP_CANDIDATE_FOUND_NOT_PIT_CERTIFIED','members':chosen,'authority_evidence':winners,'other_candidate_count':len(qualified)}

def request_json(url,retries=3):
 for n in range(retries):
  try:
   req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json'})
   with urllib.request.urlopen(req,timeout=22) as r:return json.load(r)
  except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,OSError,ValueError) as e:
   if n==retries-1:raise
   time.sleep(1.3*(n+1))

def kucoin_history(pair,typ,dir_,audit):
 sec={'1hour':3600,'1day':86400}[typ];step=sec*1200
 rows={};attempts=0;failures=[];started=int(BEGIN.timestamp())
 for start in range(started,END_S,step):
  end=min(END_S-1,start+step-1)
  params=urllib.parse.urlencode({'type':typ,'symbol':pair,'startAt':start,'endAt':end})
  u='https://api.kucoin.com/api/v1/market/candles?'+params
  try:
   j=request_json(u);attempts+=1
   if j.get('code')!='200000' or not isinstance(j.get('data'),list):
    failures.append({'start':start,'end':end,'code':j.get('code'),'message':str(j.get('msg'))[:120]});continue
   for bar in j['data']:
    if len(bar)<7:continue
    t=int(bar[0]);
    if t>=END_S or t<started:continue
    # KuCoin: time, open, close, high, low, base_volume, quote_volume
    rows[t]=[t,bar[1],bar[3],bar[4],bar[2],bar[5],bar[6]]
  except Exception as e:
   attempts+=1;failures.append({'start':start,'end':end,'error':str(e)[:150]})
  if attempts%50==0:print('KUCOIN',pair,typ,'requests',attempts,'rows',len(rows),flush=True)
  time.sleep(.09)
 dir_.mkdir(parents=True,exist_ok=True)
 path=dir_/(pair.replace('-','')+'_'+typ+'.csv.gz')
 if rows:
  with gzip.open(path,'wt',encoding='utf8',newline='') as f:
   w=csv.writer(f);w.writerow(['unix_s','open','high','low','close','base_volume','quote_volume'])
   for t in sorted(rows):w.writerow(rows[t])
  h=sha(path)
 else:h=None
 return {'source':'kucoin_public_api','pair':pair,'interval':typ,'attempted_windows':attempts,'rows':len(rows),'first':min(rows) if rows else None,'last':max(rows) if rows else None,'failures':failures,'data_file':str(path) if rows else None,'sha256':h,'claim':'venue-specific candles only; not full lifetime of token'}

def funding_hist(pair,dir_):
 # A second market dimension, independent from spot. Futures may not exist for an asset.
 symbol=pair.replace('-',''); start=int(dt.datetime(2019,9,1,tzinfo=UTC).timestamp()*1000); end=END_S*1000-1
 rows=[];seen=set();failure=None;loops=0
 while start<=end and loops<200:
  loops+=1
  u='https://fapi.binance.com/fapi/v1/fundingRate?'+urllib.parse.urlencode({'symbol':symbol,'startTime':start,'endTime':end,'limit':1000})
  try:j=request_json(u,retries=2)
  except Exception as e:failure=str(e)[:200];break
  if not isinstance(j,list):failure='API_RETURN_NOT_ARRAY';break
  for v in j:
   t=int(v['fundingTime'])
   if t not in seen and t<END_S*1000:
    seen.add(t);rows.append({'time_ms':t,'rate':v.get('fundingRate'),'mark_price':v.get('markPrice')})
  if len(j)<1000:break
  nxt=max(int(v['fundingTime']) for v in j)+1
  if nxt<=start:failure='NON_ADVANCING_FUNDING_PAGE';break
  start=nxt
  time.sleep(.1)
 path=None
 if rows:
  path=dir_/(symbol+'_funding.csv.gz');path.parent.mkdir(parents=True,exist_ok=True)
  with gzip.open(path,'wt',encoding='utf8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['time_ms','rate','mark_price']);w.writeheader();w.writerows(sorted(rows,key=lambda x:x['time_ms']))
 return {'source':'binance_usdm_futures_funding','pair':pair,'rows':len(rows),'first':min(seen) if seen else None,'last':max(seen) if seen else None,'fail':failure,'pages':loops,'file':str(path) if path else None,'not_spot':True}

def archive_index(repo,pairs,audit):
 sym={x.replace('-','').upper() for x in pairs}
 roots=[repo/'data'/'raw',repo/'.akah_bot']
 found=[]; total=0
 for root in roots:
  if not root.exists():continue
  for dp,dns,fns in os.walk(root):
   dns[:]=[d for d in dns if d not in {'.git','.venv','__pycache__'} and not d.startswith('2024')]
   for f in fns:
    total+=1
    p=pathlib.Path(dp)/f
    if '2024' in p.parts:continue
    normalized=f.upper().replace('-','').replace('_','')
    if any(s in normalized for s in sym) or any(x in normalized for x in ('DOMINANCE','BTCD','USDTD','TOTAL2','TOTAL3','MARKETCAP','FUNDING','OPENINTEREST')):
     try:found.append({'path':str(p),'bytes':p.stat().st_size,'unsafe_to_copy_unknown_time_span':True})
     except:pass
 audit.write('LOCAL_RAW_FILE_INDEX.json',{'files_indexed':total,'matching_files':found,'warning':'Binary files indexed, not copied unless explicit 2023 cutoff can be proven. This prevents reading sealed 2024 rows.'})
 return found

def copy_known_c2_reports(repo, audit):
 # Index matching C2 research reports; do not treat strategy outputs as market data.
 found=[]
 for root in (repo/'data'/'research',):
  if not root.exists():continue
  for dp,dns,fns in os.walk(root):
   dns[:]=[d for d in dns if d not in BAD_DIRS]
   for f in fns:
    p=pathlib.Path(dp)/f
    if f.endswith(('.json','.csv','.md')) and (re.search(r'rd(2[4-9]|3[0-5])',str(p),re.I) or 'c2' in f.lower()):
     try:found.append({'path':str(p),'size':p.stat().st_size})
     except:pass
 audit.write('C2_RESEARCH_REPORT_INDEX.json',{'files':found})

def c2_local_causal_tapes(repo,downloads,pairs,out,audit):
 # Reuse frozen binary schema and R27 offsets; read 2022+2023 only, not unknown 2024 bytes.
 import importlib.util
 PIN='2778E5EA5F34E77912A1B705A34296E4AD7A1D292E4B85FE593A163AF4C5F929'
 planpaths=[downloads/'AKAH_R13R27_MEGA_WORK'/'R13R27_FROZEN_PLAN.json',downloads/'R13R27_FROZEN_PLAN.json']
 planpath=next((p for p in planpaths if p.is_file()),None)
 if not planpath:return {'status':'SOURCE_MISSING','reason':'FROZEN_R27_PLAN_NOT_FOUND'}
 try:
  plan=json.loads(planpath.read_text(encoding='utf-8-sig'));offsets=plan['eligible']
 except Exception as e:return {'status':'SOURCE_UNREADABLE','reason':str(e)}
 arches=list(downloads.glob('AKAH_R50*.zip'))
 for work in ('AKAH_R50_CONTINUOUS_SURVIVAL_WORK','AKAH_R50R1_SHA_CHAIN_RECOVERY_WORK'):
  arches.extend((downloads/work).glob('AKAH_R50*.zip'))
 mod=None;orig=None;witness={}
 for ar in arches:
  try:
   with zipfile.ZipFile(ar) as z:
    for member in z.namelist():
     if member.replace('\\','/').endswith('/r43_data.py'):
      data=z.read(member)
      if hashlib.sha256(data).hexdigest().upper()!=PIN:continue
      import tempfile
      with tempfile.TemporaryDirectory() as t:
       pp=pathlib.Path(t)/'verified_r43_data.py';pp.write_bytes(data)
       spec=importlib.util.spec_from_file_location('verified_r43_data',pp)
       m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
       if all(hasattr(m,x) for x in ('REC','START','H','validate_row')):
        mod=m;orig={'archive':str(ar),'member':member,'module_sha256':PIN}
     if member.endswith('R42_2023_8759_CANONICAL_TAPE_WITNESS.json'):
      try:witness=json.loads(z.read(member));origw=str(ar)
      except:pass
    if mod:break
  except Exception as e:audit.err('ARCHIVE_R43_'+str(ar),e)
 if not mod:return {'status':'PINNED_DECODER_MISSING','archives_seen':[str(x) for x in arches]}
 if not isinstance(mod.START,dt.datetime):return {'status':'UNSUPPORTED_R43_START'}
 st=mod.START if mod.START.tzinfo else mod.START.replace(tzinfo=UTC)
 if st.year>2023:return {'status':'R43_START_OUTSIDE_ALLOWED_PERIOD'}
 H=mod.H.total_seconds()
 if H!=3600:return {'status':'R43_UNSUPPORTED_INTERVAL','hour_seconds':H}
 rows_target=8760+8759
 results=[]
 for pair in pairs:
  if pair not in offsets:
   results.append({'pair':pair,'status':'NO_R27_OFFSET','not_a_C2_membership_change':True});continue
  path=repo/'.akah_bot'/'v2r2_common_causal_tape_v1'/'pairs'/(pair+'.1H.bars.bin')
  if not path.is_file():results.append({'pair':pair,'status':'LOCAL_TAPE_MISSING'});continue
  offset=offsets[pair]
  try:
   if isinstance(offset,bool) or not isinstance(offset,int) or offset<0:raise ValueError('INVALID_OFFSET')
   size=mod.REC.size
   if (offset+rows_target)*size>path.stat().st_size:raise ValueError('INCOMPLETE_2022_2023_TAPE')
   dest=out/'market'/pair.replace('-','')/'LOCAL_PINNED_2022_2023_HOURLY.csv.gz';dest.parent.mkdir(parents=True,exist_ok=True)
   sha22=hashlib.sha256();sha23=hashlib.sha256()
   with path.open('rb') as f, gzip.open(dest,'wt',newline='',encoding='utf8') as g:
    f.seek(offset*size);w=csv.writer(g);w.writerow(['open_time_utc','open','high','low','close','base_volume','source'])
    for i in range(rows_target):
     blob=f.read(size)
     if len(blob)!=size:raise RuntimeError('SHORT_READ')
     vals=mod.validate_row(blob,i)
     if len(vals)<5:raise ValueError('UNKNOWN_R43_ROW_SCHEMA')
     t=st+dt.timedelta(seconds=i*H)
     if t.year>=2024:raise RuntimeError('PROHIBITED_2024_ROW_TIME')
     (sha22 if i<8760 else sha23).update(blob)
     w.writerow([t.isoformat(),*vals[:5],'R43_PINNED_CAUSAL_TAPE'])
   proof=witness.get(pair,{})
   verified=(bool(proof) and sha22.hexdigest().upper()==proof.get('2022_sha256','').upper() and sha23.hexdigest().upper()==proof.get('2023_8759_sha256','').upper())
   results.append({'pair':pair,'status':'EXTRACTED_WITH_R42_SHA_PARITY' if verified else 'EXTRACTED_WITHOUT_R42_SHA_PARITY','rows':rows_target,'first_time':st.isoformat(),'last_time':(st+dt.timedelta(seconds=(rows_target-1)*H)).isoformat(),'sha22':sha22.hexdigest().upper(),'sha23':sha23.hexdigest().upper(),'r42_proof_present':bool(proof),'output_sha256':sha(dest),'output_file':str(dest)})
  except Exception as e:
   audit.err('LOCAL_TAPE_'+pair,e);results.append({'pair':pair,'status':'BLOCKED','reason':str(e)})
 return {'status':'DONE','decoder':orig,'plan_path':str(planpath),'results':results,'warning':'R27 eligibility or frozen R42 coverage is NOT itself C2 PIT membership or price formation since token launch.'}

def indicators_from_daily(path,output):
 # Descriptive diagnostics derived from observed daily bars; no signal thresholds or fitting.
 import statistics
 with gzip.open(path,'rt',encoding='utf8') as f:raw=list(csv.DictReader(f))
 if not raw:return None
 x=[]
 for r in raw:
  try:x.append({'t':int(r['unix_s']),'o':float(r['open']),'h':float(r['high']),'l':float(r['low']),'c':float(r['close']),'v':float(r['base_volume']),'q':float(r['quote_volume'])})
  except (KeyError,TypeError,ValueError):continue
 n=len(x); closes=[v['c'] for v in x];vols=[v['v'] for v in x]
 def avg(a,i,k):return sum(a[i-k+1:i+1])/k if i>=k-1 else None
 def sd(a,i,k):return __import__('statistics').pstdev(a[i-k+1:i+1]) if i>=k-1 else None
 def ema_seq(a,k):
  ret=[];cur=None;al=2/(k+1)
  for i,v in enumerate(a):cur=v if cur is None else al*v+(1-al)*cur;ret.append(cur if i>=k-1 else None)
  return ret
 em={p:ema_seq(closes,p) for p in (8,12,21,26,55,200)}
 tr=[];obv=0;prev=None;deltas=[];gains=[];losses=[];moneypos=[];moneyneg=[]
 for i,v in enumerate(x):
  tr.append(max(v['h']-v['l'],abs(v['h']-closes[i-1]) if i else 0,abs(v['l']-closes[i-1]) if i else 0))
  if i:
   obv+=(1 if v['c']>closes[i-1] else -1 if v['c']<closes[i-1] else 0)*v['v']
   d=v['c']-closes[i-1];gains.append(max(d,0));losses.append(max(-d,0))
  else:gains.append(0);losses.append(0)
  typ=(v['h']+v['l']+v['c'])/3
  flow=typ*v['v'];up=prev is not None and typ>prev;down=prev is not None and typ<prev
  moneypos.append(flow if up else 0);moneyneg.append(flow if down else 0);prev=typ
  deltas.append(obv)
 diffs=[(em[12][i]-em[26][i]) if em[12][i] is not None and em[26][i] is not None else None for i in range(n)]
 macd_signal=[];s=None
 for i,val in enumerate(diffs):
  if val is None:macd_signal.append(None);continue
  s=val if s is None else 0.2*val+0.8*s
  macd_signal.append(s)
 output.parent.mkdir(parents=True,exist_ok=True)
 fields=['unix_s','close','quote_volume','ret_1d_pct','ret_7d_pct','ret_30d_pct','ret_90d_pct','sma_5','sma_10','sma_20','sma_50','sma_100','sma_200','ema_8','ema_12','ema_21','ema_26','ema_55','ema_200','rsi_14','atr_14','bollinger_upper_20_2sd','bollinger_lower_20_2sd','macd_12_26','macd_signal_9','macd_histogram','obv','mfi_14','realized_volatility_20d_annualized_pct','volume_zscore_20','rolling_max_drawdown_90d_pct']
 with gzip.open(output,'wt',encoding='utf8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for i,v in enumerate(x):
   def ret(k):return 100*(v['c']/closes[i-k]-1) if i>=k and closes[i-k]>0 else None
   b=avg(closes,i,20);d=sd(closes,i,20)
   pos=sum(moneypos[i-13:i+1]) if i>=13 else None; neg=sum(moneyneg[i-13:i+1]) if i>=13 else None
   rg=sum(gains[i-13:i+1]) if i>=13 else None; rl=sum(losses[i-13:i+1]) if i>=13 else None
   rsi=(100 if rl==0 and rg>0 else 50 if rl==0 and rg==0 else 100-100/(1+rg/rl)) if rg is not None else None
   mfi=(100 if neg==0 and pos>0 else 50 if neg==0 and pos==0 else 100-100/(1+pos/neg)) if pos is not None else None
   lv=[__import__('math').log(closes[j]/closes[j-1]) for j in range(max(1,i-19),i+1)] if i>=20 else []
   vmean=avg(vols,i,20);vstd=sd(vols,i,20)
   m=macd_signal[i];mn=diffs[i]
   row={'unix_s':v['t'],'close':v['c'],'quote_volume':v['q'],'ret_1d_pct':ret(1),'ret_7d_pct':ret(7),'ret_30d_pct':ret(30),'ret_90d_pct':ret(90),'rsi_14':rsi,'atr_14':avg(tr,i,14),'bollinger_upper_20_2sd':b+2*d if b is not None else None,'bollinger_lower_20_2sd':b-2*d if b is not None else None,'macd_12_26':mn,'macd_signal_9':m,'macd_histogram':mn-m if mn is not None and m is not None else None,'obv':deltas[i],'mfi_14':mfi,'realized_volatility_20d_annualized_pct':__import__('statistics').pstdev(lv)*(365**0.5)*100 if len(lv)>=20 else None,'volume_zscore_20':(v['v']-vmean)/vstd if vstd else None,'rolling_max_drawdown_90d_pct':100*(v['c']/max(closes[max(0,i-89):i+1])-1) if i>=89 else None}
   for k in (5,10,20,50,100,200):row[f'sma_{k}']=avg(closes,i,k)
   for k in (8,12,21,26,55,200):row[f'ema_{k}']=em[k][i]
   w.writerow({k:('' if z is None else z) for k,z in row.items()})
 return {'indicator_file':str(output),'source_file':str(path),'rows':n,'sha256':sha(output),'definition':'Descriptive indicators based on historical close/high/low/volume; no forward fill, no risk adjusted alpha claim'}

def binance_1m_archive(pair,dest):
 # Full original monthly 1-minute Spot candle archives (where Binance offers them).
 # Do not pretend that an unavailable Binance month is an unavailable coin.
 base=pair.replace('-','');dest.mkdir(parents=True,exist_ok=True)
 rows=[];downloaded=0;bytes_=0;notfound=0;failure=[]
 for year in range(2017,2024):
  for month in range(1,13):
   if year==2017 and month<8:continue
   ym=f'{year}-{month:02d}';name=f'{base}-1m-{ym}.zip'
   p=dest/name
   if p.is_file() and zipfile.is_zipfile(p):
    downloaded+=1;bytes_+=p.stat().st_size;continue
   url=f'https://data.binance.vision/data/spot/monthly/klines/{base}/1m/{name}'
   try:
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=18) as resp:
     with p.open('wb') as f:shutil.copyfileobj(resp,f,length=1024*1024)
    if not zipfile.is_zipfile(p):
     p.unlink(missing_ok=True);failure.append({'month':ym,'cause':'NOT_VALID_ZIP'});continue
    downloaded+=1;bytes_+=p.stat().st_size
   except urllib.error.HTTPError as e:
    if e.code in (400,404):notfound+=1
    else:failure.append({'month':ym,'http_status':e.code})
   except Exception as e:failure.append({'month':ym,'exception':str(e)[:120]})
   if (downloaded+notfound+len(failure))%15==0:print('MINUTE_ARCHIVE',pair,'downloaded',downloaded,'missing',notfound,flush=True)
 return {'source':'data.binance.vision','pair':pair,'interval':'1m','months_downloaded':downloaded,'months_not_available':notfound,'compressed_bytes':bytes_,'failures':failure,'venue_lifetime_only':True,'2024_plus_excluded':True}

def bundle(out,audit,root):
 files=[p for p in out.rglob('*') if p.is_file() and p.name!='VAULT_FILE_SHA256.json']
 manifest=[]
 for p in files:
  manifest.append({'relative_path':p.relative_to(out).as_posix(),'size':p.stat().st_size,'sha256':sha(p)})
 audit.write('VAULT_FILE_SHA256.json',{'version':'C2_VAULT_V1','files':manifest})
 # Uploadable full-resolution chunks; no downsampling. A source monthly ZIP remains byte-identical.
 packets=[];MAX_PACKET=48*1024*1024
 market=out/'market'
 if market.exists():
  for assetdir in sorted(market.iterdir()):
   if not assetdir.is_dir():continue
   group=[];weight=0;part=0
   for p in sorted(assetdir.rglob('*')):
    if not p.is_file():continue
    if group and weight+p.stat().st_size>MAX_PACKET:
     part+=1;name=f'UPLOAD_THIS_C2_MARKET_{assetdir.name}_PART{part:03d}.zip';z=root/name
     with zipfile.ZipFile(z,'w',zipfile.ZIP_STORED,allowZip64=True) as w:
      for p0 in group:w.write(p0,p0.relative_to(out))
     packets.append({'name':name,'bytes':z.stat().st_size,'sha256':sha(z)});group=[];weight=0
    group.append(p);weight+=p.stat().st_size
   if group:
    part+=1;name=f'UPLOAD_THIS_C2_MARKET_{assetdir.name}_PART{part:03d}.zip';z=root/name
    with zipfile.ZipFile(z,'w',zipfile.ZIP_STORED,allowZip64=True) as w:
     for p0 in group:w.write(p0,p0.relative_to(out))
    packets.append({'name':name,'bytes':z.stat().st_size,'sha256':sha(z)})
 index=root/'UPLOAD_THIS_AKAH_C2_AUTHORITY_AND_COVERAGE.zip'
 audit.write('UPLOAD_PACKET_INDEX.json',packets)
 with zipfile.ZipFile(index,'w',zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True) as w:
  for p in sorted(out.rglob('*')):
   if p.is_file() and 'market' not in p.relative_to(out).parts:
    w.write(p,p.relative_to(out))
 return index,packets

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',type=pathlib.Path,required=True);ap.add_argument('--downloads',type=pathlib.Path,required=True);ap.add_argument('--output',type=pathlib.Path,required=True);ap.add_argument('--offline',action='store_true');ap.add_argument('--no-minute-archives',action='store_true')
 args=ap.parse_args();repo=args.repo;dl=args.downloads;out=args.output;out.mkdir(parents=True,exist_ok=True)
 a=Audit(out);a.status={'schema':'AKAH_C2_SOURCE_FIRST_TERMINAL_V1','research_universe':'C2_EXACT_ONLY','period_end_exclusive':END.isoformat(),'production_mutations':0,'live_orders':0,'2024_market_rows_read':0,'network_operations_run_from':'USER_TERMINAL_ONLY','engine_uses_2022_2023_outcomes_for_selection':False}
 try:
  if not repo.is_dir():raise RuntimeError('REPOSITORY_NOT_FOUND:'+str(repo))
  pairs,authority=c2_discovery(repo,dl,a);a.status['universe']=authority;a.write('C2_MEMBERSHIP_AUTHORITY.json',authority)
  copy_known_c2_reports(repo,a)
  if not pairs:
   a.status['status']=authority['status'];print('BLOCKED_C2_MEMBERSHIP',flush=True)
  else:
   print('C2_IDENTIFIED',len(pairs),'members',','.join(pairs),flush=True)
   loc=archive_index(repo,pairs,a)
   local_data=c2_local_causal_tapes(repo,dl,pairs,out,a)
   a.write('LOCAL_PINNED_CAUSAL_TAPES.json',local_data)
   if args.offline:a.status['status']='OFFLINE_INDEX_ONLY_NOT_FULL_HISTORY'
   else:
    a.status['status']='FETCHING'
    tasks=[]
    with ThreadPoolExecutor(max_workers=4) as ex:
     for p in pairs:
      dest=out/'market'/p.replace('-','')
      for interval in ('1day','1hour'):
       tasks.append(ex.submit(kucoin_history,p,interval,dest,a))
      tasks.append(ex.submit(funding_hist,p,dest))
      if not args.no_minute_archives:tasks.append(ex.submit(binance_1m_archive,p,dest/'binance_spot_1m_monthly_original'))
     for f in as_completed(tasks):
      try:
       r=f.result();a.retrieval.append(r)
       if r.get('source')=='kucoin_public_api' and r.get('interval')=='1day' and r.get('data_file'):
        try:a.retrieval.append(indicators_from_daily(pathlib.Path(r['data_file']),pathlib.Path(r['data_file']).with_name('DESCRIPTIVE_INDICATORS_1day.csv.gz')))
        except Exception as e:a.err('INDICATORS_'+r.get('pair',''),e)
       print('C2_DATA',r.get('pair'),r.get('interval','funding'),'rows',r.get('rows',0),'failures',len(r.get('failures',[])),flush=True)
      except Exception as e:a.err('DOWNLOAD_TASK',e)
    a.status['status']='ACQUIRED_WITH_COVERAGE_GAPS_REVIEW_REQUIRED'
   a.status['C2_member_count']=len(pairs)
  a.status['missing_source_categories']=[
   'True BTC.D / TOTAL / TOTAL2 / TOTAL3 historical capitalization series not implied by OHLCV; require source and historical access',
   'Historical full-depth order books / intrabar spread / partial fills not recoverable from OHLCV',
   'Historical open interest often retention-limited; funding data only where contract listed',
   'Historical on-chain metrics / supply / unlocks / tokenomics / news require independent data licenses and temporal provenance',
   'No guarantee KuCoin listing equals creation of coin; other venue early history separate',
   'Binance 1-minute monthly archives are preserved where available, venue-specific and potentially multi-gigabyte; Binance archive gaps remain explicit',
   '2024+ deliberately SEALED from earlier explicit user instruction']
 except Exception as e:a.err('MAIN',e);a.status['status']='BLOCKED_EXECUTION_ERROR'
 finally:
  a.write('TERMINAL_RETRIEVAL_LOG.json',a.retrieval)
  a.write('UNAVAILABLE_AND_ERRORS.json',a.errors)
  a.write('C2_DATA_VAULT_STATUS.json',a.status)
  index,packets=bundle(out,a,out.parent)
  total=sum(p.stat().st_size for p in out.rglob('*') if p.is_file())
  if total<=250*1024*1024:
   full=out.parent/'UPLOAD_THIS_AKAH_C2_COMPLETE_DATA_VAULT.zip'
   with zipfile.ZipFile(full,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
    for p in sorted(out.rglob('*')):
     if p.is_file():z.write(p,p.relative_to(out))
   print('UPLOAD_PREFERRED_SINGLE='+str(full),flush=True)
  else:
   print('FULL_ARCHIVE_TOO_LARGE_TO_PACK_AS_ONE_FILE; use INDEX plus all MARKET parts',flush=True)
  (out.parent/'AKAH_C2_UPLOAD_INSTRUCTIONS.txt').write_text('Upload first '+index.name+'; then upload every UPLOAD_THIS_C2_MARKET_*.zip generated by this run. Raw full files stay in local output directory. No 2024 data.\n',encoding='utf8')
  print('UPLOAD_FIRST='+str(index),flush=True)
  for packet in packets:print('UPLOAD_MARKET='+packet['name']+' BYTES='+str(packet['bytes']),flush=True)
  print('FINAL_STATUS='+a.status['status'],flush=True)
  return 0 if a.status['status'].startswith(('ACQUIRED','OFFLINE')) else 2
if __name__=='__main__':sys.exit(main())

'@
[System.IO.File]::WriteAllText($worker, $payload, (New-Object System.Text.UTF8Encoding($false)))
$venv = Join-Path $repo '.venv\Scripts\python.exe'
$prefix = @()
if (Test-Path -LiteralPath $venv) { $py = $venv }
elseif (Get-Command 'py' -ErrorAction SilentlyContinue) { $py = 'py'; $prefix = @('-3') }
elseif (Get-Command 'python' -ErrorAction SilentlyContinue) { $py = 'python' }
else { throw 'PYTHON_NOT_FOUND_USE_REPO_VENV_OR_PYTHON3' }
$log = Join-Path $run 'C2_TERMINAL_FULL_LOG.txt'
Write-Host 'AKAH_C2_TERMINAL_COLLECTION=START'
Write-Host 'SCOPE=EXACT_C2_ONLY 2024_AND_LATER=SEALED ORDERS=0 REPO_CHANGES=0'
& $py @prefix $worker '--repo' $repo '--downloads' $dl '--output' (Join-Path $run 'VAULT') 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
Write-Host ('AKAH_C2_RUN_DIRECTORY=' + $run)
Write-Host ('AKAH_C2_EXIT_CODE=' + $code)
Write-Host 'UPLOAD: UPLOAD_THIS_AKAH_C2_COMPLETE_DATA_VAULT.zip if produced, otherwise UPLOAD_THIS_AKAH_C2_AUTHORITY_AND_COVERAGE.zip and every UPLOAD_THIS_C2_MARKET_*.zip'
if ($code -ne 0) { Write-Warning 'C2 source authority or collection gate blocked. Upload the authority packet for diagnosis; no arbitrary asset fallback.' }
exit $code
