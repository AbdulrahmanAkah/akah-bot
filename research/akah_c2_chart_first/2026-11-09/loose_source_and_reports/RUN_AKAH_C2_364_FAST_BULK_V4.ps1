# AKAH Original C2 364 Fast Bulk Evidence Collector V4
# One-run Windows PowerShell wrapper. No repo mutations, no live trading, pre-2024 only.
$ErrorActionPreference = 'Stop'
$repo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$downloads = Join-Path $HOME 'Downloads'
$work = Join-Path $downloads 'AKAH_C2_364_FAST_V4'
$oldvault = Join-Path $downloads 'AKAH_C2_MARKET_VAULT_V2'
$upload = Join-Path $downloads 'AKAH_C2_364_FAST_UPLOAD_PACKETS_V4'
New-Item -ItemType Directory -Force -Path $work | Out-Null
New-Item -ItemType Directory -Force -Path $upload | Out-Null
$worker = Join-Path $work 'akah_c2_364_fast_v4.py'
$source = @'
#!/usr/bin/env python3
"""AKAH C2 ORIGINAL 364 fast research-data collector (2023 cutoff, read-only).
Uses the original RD18 A1 acquisition plan; local historical raw 1h before APIs.
No trading or repository writes. Python stdlib plus optional local parquet reader.
"""
import argparse, csv, datetime as dt, gzip, hashlib, io, json, math, os, pathlib, random, shutil, statistics, sys, threading, time, urllib.error, urllib.parse, urllib.request, zipfile
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
UTC=dt.timezone.utc
BEGIN=dt.datetime(2017,1,1,tzinfo=UTC)
CUTOFF=dt.datetime(2024,1,1,tzinfo=UTC)
BEGIN_MS=int(BEGIN.timestamp()*1000); CUTOFF_MS=int(CUTOFF.timestamp()*1000)
PAIR_SCHEMA=['unix_ms','open','high','low','close','base_volume','quote_volume','trade_count','taker_buy_quote_volume']
VERSION='AKAH_ORIGINAL_C2_364_FAST_BULK_V4'
_io_lock=threading.Lock()
_rate_lock=threading.Lock()
_next_time=[0.0]
_failure_lock=threading.Lock()
_global_network_failures=[0]
_host_failures=Counter()
_blocked_hosts=set()

def utc_date(ms):return dt.datetime.fromtimestamp(ms/1000,UTC).strftime('%Y-%m-%d')
def to_int_ms(value):
 if value is None:return None
 if hasattr(value,'timestamp') and not isinstance(value,str):
  try:
   if value.tzinfo is None:value=value.replace(tzinfo=UTC)
   return int(value.timestamp()*1000)
  except Exception:return None
 try:
  s=str(value).strip()
  if not s:return None
  if s.lstrip('-').isdigit():
   n=int(s)
   if n>=10**16:n//=1000
   if n<10**11:n*=1000
   return n
  obj=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
  if obj.tzinfo is None:obj=obj.replace(tzinfo=UTC)
  return int(obj.timestamp()*1000)
 except (ValueError,TypeError,OverflowError):return None

def digest(f):
 h=hashlib.sha256()
 with open(f,'rb') as p:
  for b in iter(lambda:p.read(1048576),b''):h.update(b)
 return h.hexdigest()

def write_json(path,data):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.part')
 with temp.open('w',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2,default=str)
 os.replace(temp,path)

def write_csv(path,rows,fields):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.part')
 with tmp.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
 os.replace(tmp,path)

def journal(path,item):
 with _io_lock:
  with open(path,'a',encoding='utf-8') as f:f.write(json.dumps(item,ensure_ascii=False,default=str)+'\n')

def inventory(repo,output):
 orig=repo/'data/research/rd18_p3x_a1_runtime/full-c2-hourly-acquisition-plan.csv'
 classification=repo/'data/research/rd18_p1r2/raw-inventory-classification.csv'
 if not orig.is_file():raise RuntimeError('ORIGINAL_C2_364_PLAN_MISSING '+str(orig))
 with orig.open(encoding='utf-8-sig',newline='',errors='replace') as f:r=csv.DictReader(f);cols=r.fieldnames or [];rows=list(r)
 if not {'pair','symbol'}.issubset(set(cols)):raise RuntimeError('ORIGINAL_C2_PLAN_COLUMNS_MISSING '+repr(cols))
 pairs={}
 for row in rows:
  pair=str(row['pair']).strip().upper().replace('/','-').replace('_','-')
  s=str(row['symbol']).strip().upper()
  if not pair or not s:continue
  if not pair.endswith('-USDT'):continue
  if pair in pairs and pairs[pair]!=s:raise RuntimeError('CONFLICTING_PAIR_SYMBOL_MAPPING '+pair)
  pairs[pair]=s
 if len(pairs)!=364:raise RuntimeError('ORIGINAL_C2_COUNT_MISMATCH actual='+str(len(pairs))+' expected=364; no fallback to 29/35/trade-ledger')
 audit={'source':str(orig),'sha256':digest(orig),'plan_rows':len(rows),'count':364,'columns':cols,'classifications_source':str(classification),'classifications_exists':classification.is_file(),'classifications_sha256':digest(classification) if classification.is_file() else None,'scope':'original RD18 C2 plan, NOT the later 29/35 operational subset','historical_pit_membership':'NOT_CERTIFIED'}
 output.mkdir(parents=True,exist_ok=True);write_json(output/'ORIGINAL_364_AUTHORITY.json',audit)
 write_csv(output/'C2_364_PLAN.csv',[{'pair':p,'symbol':s} for p,s in sorted(pairs.items())],['pair','symbol'])
 return pairs,audit

def throttle():
 with _rate_lock:
  now=time.monotonic();w=max(0,_next_time[0]-now);_next_time[0]=max(_next_time[0],now)+0.075
 if w:time.sleep(w)

def http_json(url,tag,logfile):
 host=urllib.parse.urlparse(url).netloc
 with _failure_lock:
  if host in _blocked_hosts:raise RuntimeError('HOST_CIRCUIT_BREAKER_'+host)
 err=None
 for attempt in range(3):
  throttle()
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'AKAH-C2-364-market-research/4.0','Accept':'application/json'})
   with urllib.request.urlopen(req,timeout=12) as r:
    j=json.loads(r.read(3500000))
   with _failure_lock:
    _global_network_failures[0]=0;_host_failures[host]=0
   return j
  except urllib.error.HTTPError as e:
   err='HTTP_'+str(e.code)
   if e.code in (400,404,451):
    journal(logfile,{'tag':tag,'status':'NO_SYMBOL_OR_HISTORY','error':err});return None
   if e.code in (418,429):
    h=e.headers.get('Retry-After','')
    try:delay=min(120,max(2,int(h)))
    except:delay=10
    time.sleep(delay)
   else:time.sleep(min(14,2**attempt))
  except (TimeoutError,urllib.error.URLError,OSError,ValueError) as e:
   err=str(e)[:150];time.sleep(min(12,2**attempt))
 with _failure_lock:
  _global_network_failures[0]+=1;_host_failures[host]+=1
  if _host_failures[host]>=8:_blocked_hosts.add(host)
 journal(logfile,{'tag':tag,'status':'NETWORK_ERROR','host':host,'error':err})
 return None

def validate_bar(row):
 try:
  ms=int(row['unix_ms']);vs=[float(row[k]) for k in ('open','high','low','close')]
  if not (BEGIN_MS<=ms<CUTOFF_MS) or not all(math.isfinite(x) and x>0 for x in vs):return None
  if vs[2]>min(vs[0],vs[3]) or vs[1]<max(vs[0],vs[3]) or vs[1]<vs[2]:return None
  out={'unix_ms':ms}
  for f in PAIR_SCHEMA[1:]:
   v=row.get(f,None)
   if v in ('',None,'None','nan','NaN'):out[f]='';continue
   x=float(v);out[f]=x if math.isfinite(x) else ''
  return out
 except (KeyError,ValueError,TypeError,OverflowError):return None

def gzip_rows(path,source='normal'):
 if not path.is_file():return {}
 rows={}
 try:
  with gzip.open(path,'rt',encoding='utf-8-sig',errors='replace',newline='') as f:
   for x in csv.DictReader(f):
    row=validate_bar(x)
    if row:rows[row['unix_ms']]=row
 except Exception:return {}
 return rows

def save_gzip(path,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_name(path.name+'.part')
 with gzip.open(tmp,'wt',encoding='utf-8',newline='',compresslevel=5) as f:
  w=csv.DictWriter(f,fieldnames=PAIR_SCHEMA);w.writeheader()
  for k in sorted(rows):w.writerow(rows[k])
 os.replace(tmp,path)

def local_parquet(repo,pair,logfile):
 path=repo/'data/raw/rd16b/kucoin'/pair/'1h.parquet'
 if not path.is_file():return {},'NO_LOCAL_PARQUET'
 try:
  import pyarrow.parquet as pq,pyarrow.types as pt
  table=pq.ParquetFile(path)
  field=table.schema_arrow.field('timestamp')
  if pt.is_timestamp(field.type):
   target=dt.datetime(2024,1,1,tzinfo=UTC) if getattr(field.type,'tz',None) else dt.datetime(2024,1,1)
  elif pt.is_integer(field.type):
   vals=[]
   for g in range(table.metadata.num_row_groups):
    col=table.metadata.row_group(g).column(table.schema_arrow.get_field_index('timestamp'))
    if col.statistics and col.statistics.min is not None:vals.append(int(col.statistics.min))
   target=CUTOFF_MS if vals and max(vals)>=10**11 else CUTOFF_MS//1000
  elif pt.is_string(field.type):target='2024-01-01'
  else:raise ValueError('UNKNOWN_TIMESTAMP_TYPE '+str(field.type))
  # Filter is mandatory; never read all rows from a raw parquet potentially containing sealed 2024.
  batch=pq.read_table(path,filters=[('timestamp','<',target)])
  data=batch.to_pydict();cols=list(data)
  def getcol(names):
   for n in names:
    if n in data:return data[n]
   return None
  timestamp=getcol(['timestamp','time','open_time']);op=getcol(['open','o']);hi=getcol(['high','h']);lo=getcol(['low','l']);cl=getcol(['close','c']);vol=getcol(['volume','base_volume','v']);q=getcol(['turnover','quote_volume','quoteVolume','amount'])
  if not all(x is not None for x in (timestamp,op,hi,lo,cl)):
   raise ValueError('MISSING_PARQUET_OHLC '+str(cols))
  rows={}
  for i,val in enumerate(timestamp):
   ms=to_int_ms(val)
   if ms is None or not BEGIN_MS<=ms<CUTOFF_MS:continue
   row=validate_bar({'unix_ms':ms,'open':op[i],'high':hi[i],'low':lo[i],'close':cl[i], 'base_volume':vol[i] if vol else '', 'quote_volume':q[i] if q else ''})
   if row:rows[ms]=row
  journal(logfile,{'tag':'local_parquet/'+pair,'status':'OK','rows':len(rows),'source_sha256':digest(path),'cutoff_filter':str(target)})
  return rows,'LOCAL_RD16B_PARQUET'
 except Exception as e:
  journal(logfile,{'tag':'local_parquet/'+pair,'status':'UNREADABLE_OR_CUTOFF_FILTER_FAILED','error':str(e)[:300]})
  return {},'LOCAL_UNREADABLE_PARQUET'

def cached_kucoin(vault,pair,kind):
 f=vault/'raw/kucoin/spot'/pair/(kind+'.csv.gz')
 return gzip_rows(f)

def kucoin_candles(pair,interval,startms,endms,logfile):
 if _global_network_failures[0]>=35:return None
 sec=3600 if interval=='1hour' else 86400
 params=urllib.parse.urlencode({'symbol':pair,'type':interval,'startAt':startms//1000,'endAt':min(endms//1000-1,CUTOFF_MS//1000-1)})
 j=http_json('https://api.kucoin.com/api/v1/market/candles?'+params,'kucoin/'+pair+'/'+interval+'/'+str(startms),logfile)
 if not isinstance(j,dict) or str(j.get('code'))!='200000':return None
 out={}
 for v in (j.get('data') or []):
  if len(v)<7:continue
  try:
   ms=int(v[0])*1000
   row=validate_bar({'unix_ms':ms,'open':v[1],'high':v[3],'low':v[4],'close':v[2],'base_volume':v[5],'quote_volume':v[6]})
   if row and startms<=ms<endms:out[ms]=row
  except Exception:continue
 return out

def binance_daily(symbol,logfile,interval='1d'):
 out={};start=BEGIN_MS;pages=0;complete=False;step=86400000 if interval=='1d' else 3600000
 while start<CUTOFF_MS:
  u='https://data-api.binance.vision/api/v3/klines?'+urllib.parse.urlencode({'symbol':symbol,'interval':interval,'startTime':start,'endTime':CUTOFF_MS-1,'limit':1000})
  dat=http_json(u,'binance/'+symbol+'/'+interval+'/'+str(start),logfile)
  if not isinstance(dat,list):break
  pages+=1
  if not dat:complete=True;break
  last=None
  for v in dat:
   try:
    ms=int(v[0]);row=validate_bar({'unix_ms':ms,'open':v[1],'high':v[2],'low':v[3],'close':v[4],'base_volume':v[5],'quote_volume':v[7],'trade_count':v[8],'taker_buy_quote_volume':v[10]})
    if row:out[ms]=row
    last=ms
   except Exception:continue
  if last is None or last<start:break
  start=last+step
  if len(dat)<1000:complete=True;break
  if start>=CUTOFF_MS:complete=True
 return out,pages,complete

def fetch_daily(pair,symbol,work,oldvault,logfile,mode):
 file=work/'daily'/('KUCOIN_'+pair+'.csv.gz'); fb=work/'daily'/('BINANCE_'+pair+'.csv.gz')
 ku=gzip_rows(file) if file.exists() else cached_kucoin(oldvault,pair,'1day')
 src='CACHED_V4' if file.exists() else ('PREVIOUS_29_CACHE' if ku else 'KUCOIN_API')
 checkpoint=work/'checkpoints'/pair/'daily';checkpoint.mkdir(parents=True,exist_ok=True)
 if mode!='offline':
  # 1200 daily candles/request; window marker prevents repeated successful calls.
  step=1200*86400000
  for st in range(BEGIN_MS,CUTOFF_MS,step):
   en=min(st+step,CUTOFF_MS)
   marker=checkpoint/(str(st)+'.ok')
   if marker.exists():continue
   if ku and all((t in ku) for t in range(st,en,86400000)):
    marker.touch();continue
   dat=kucoin_candles(pair,'1day',st,en,logfile)
   if dat is not None:
    ku.update(dat);marker.touch()
 if ku:save_gzip(file,ku)
 bn=gzip_rows(fb) if fb.exists() else {}
 p=0
 bcomplete=checkpoint/'binance_complete.ok'
 if mode!='offline' and not bcomplete.exists():
  # Historical API is paged; cache partial results and continue on the next run.
  new,p,complete=binance_daily(symbol,logfile,interval='1d')
  bn.update(new)
  if bn:save_gzip(fb,bn)
  if complete:bcomplete.touch()
 return ku,bn,src,p

def fill_hourly(pair,work,repo,oldvault,daily,logfile,mode):
 target=work/'hourly'/('KUCOIN_'+pair+'.csv.gz')
 old=gzip_rows(target) if target.exists() else cached_kucoin(oldvault,pair,'1hour')
 # Do not reread a multi-GB parquet on every repeated invocation if the normalized copy exists.
 if target.exists():local={};source='CACHED_V4'
 else:local,source=local_parquet(repo,pair,logfile)
 rows={**old,**local};iflocal=bool(rows)
 if old and not local:source='PREVIOUS_29_CACHE'
 if mode=='offline':
  if rows:save_gzip(target,rows)
  return rows,source,0
 # Limit to dates with actual daily coverage when possible, to avoid decades of empty API calls.
 daily_keys=sorted(daily)
 if not daily_keys:
  if rows:save_gzip(target,rows)
  return rows,source if rows else 'NO_KUCOIN_DAILY_COVERAGE',0
 first=daily_keys[0];end=min(CUTOFF_MS,daily_keys[-1]+86400000)
 # Preserve earlier local data, even if not seen in daily API.
 if rows:first=min(first,min(rows));end=max(end,min(CUTOFF_MS,max(rows)+3600000))
 first=max(BEGIN_MS,(first//3600000)*3600000)
 requests=0;new=0;step=1200*3600000
 checkpoint=work/'checkpoints'/pair/'hourly';checkpoint.mkdir(parents=True,exist_ok=True)
 if rows:
  minlocal=min(rows);maxlocal=max(rows)
 else:minlocal=maxlocal=-1
 for st in range(first,end,step):
  en=min(end,st+step)
  marker=checkpoint/(str(st)+'.ok')
  if marker.exists():continue
  # If the entire requested time window is present locally, no request.
  if minlocal<=st and maxlocal>=en-3600000:
   expected=(en-st)//3600000
   have=sum(1 for t in range(st,en,3600000) if t in rows)
   if have>=expected*.985:marker.touch();continue
  # Limit unnecessary refetching: only fetch missing ranges (including internal gaps).
  dat=kucoin_candles(pair,'1hour',st,en,logfile);requests+=1
  if dat is None:continue
  marker.touch()
  for t,x in dat.items():
   if t not in rows:new+=1;rows[t]=x
 if rows:save_gzip(target,rows)
 journal(logfile,{'tag':'hourly_finalize/'+pair,'status':source if iflocal else 'KUCOIN_API','requests':requests,'new_rows':new,'total_rows':len(rows)})
 return rows,source if iflocal else 'KUCOIN_API',requests

def summarize(pair,dailyku,dailybn,hourly,source,hrequests):
 def cov(rows):
  if not rows:return {'rows':0,'first':'','last':''}
  keys=sorted(rows);return {'rows':len(rows),'first':utc_date(keys[0]),'last':utc_date(keys[-1])}
 k=cov(dailyku);b=cov(dailybn);h=cov(hourly)
 def missing_slots(rows,step):
  if len(rows)<2:return 0
  ts=sorted(rows)
  return max(0,((ts[-1]-ts[0])//step+1)-len(rows))
 return {'kucoin_daily_internal_missing_slots':missing_slots(dailyku,86400000),'binance_daily_internal_missing_slots':missing_slots(dailybn,86400000),'kucoin_hourly_internal_missing_slots':missing_slots(hourly,3600000), 'pair':pair,'kucoin_daily_rows':k['rows'],'kucoin_daily_first':k['first'],'kucoin_daily_last':k['last'],
  'binance_daily_rows':b['rows'],'binance_daily_first':b['first'],'binance_daily_last':b['last'],
  'kucoin_hourly_rows':h['rows'],'kucoin_hourly_first':h['first'],'kucoin_hourly_last':h['last'],
  'hourly_source':source,'kucoin_hourly_api_windows':hrequests,
  'hourly_2022_2023_rows':sum(1 for t in hourly if 1640995200000<=t<CUTOFF_MS),
  'daily_candles_not_coin_market_cap':True,'historical_pit_status':'NOT_CERTIFIED'}

def collect_funding(pair,work,oldvault,logfile,mode):
    """USD-M historical funding rate, not spot liquidity or order book depth."""
    symbol=pair.replace('-','')
    path=work/'derivatives_funding'/('BINANCE_USDM_'+pair+'.csv.gz')
    old=oldvault/'raw/binance/futures_um/fundingRate'/(symbol+'.csv.gz')
    if path.exists():
        try:
            with gzip.open(path,'rt',encoding='utf-8') as f:return max(0,sum(1 for _ in f)-1),'V4_CACHED'
        except Exception:pass
    if old.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        # Preserve previously collected pre-2024 source; only the V2 collector was strictly bounded.
        with gzip.open(old,'rt',encoding='utf-8') as f:
            rows=[x for x in csv.DictReader(f) if (to_int_ms(x.get('unix_ms')) or CUTOFF_MS)>=BEGIN_MS and (to_int_ms(x.get('unix_ms')) or CUTOFF_MS)<CUTOFF_MS]
        if rows:
            with gzip.open(path,'wt',encoding='utf-8',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['unix_ms','funding_rate','mark_price']);w.writeheader();w.writerows(rows)
            return len(rows),'V2_CACHED'
    if mode=='offline':return 0,'OFFLINE_UNAVAILABLE'
    marker=work/'checkpoints'/pair/'funding_complete.ok'
    if marker.exists():return 0,'NO_USDM_FUNDING_OR_CACHED_MARKER'
    lo=int(dt.datetime(2019,1,1,tzinfo=UTC).timestamp()*1000)
    cache={};failed=False;calls=0
    while lo<CUTOFF_MS and calls<12:
        url='https://fapi.binance.com/fapi/v1/fundingRate?'+urllib.parse.urlencode({'symbol':symbol,'startTime':lo,'endTime':CUTOFF_MS-1,'limit':1000})
        vals=http_json(url,'funding/'+symbol+'/'+str(lo),logfile)
        if vals is None:failed=True;break
        if not isinstance(vals,list):failed=True;break
        calls+=1
        if not vals:break
        last=None
        for r in vals:
            try:
                ms=int(r['fundingTime'])
                if BEGIN_MS<=ms<CUTOFF_MS:
                    cache[ms]={'unix_ms':ms,'funding_rate':r.get('fundingRate',''),'mark_price':r.get('markPrice','')}
                last=ms
            except (KeyError,ValueError,TypeError):continue
        if last is None or last<lo:failed=True;break
        lo=last+1
        if len(vals)<1000:break
    if cache:
        path.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(path,'wt',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['unix_ms','funding_rate','mark_price']);w.writeheader()
            for t in sorted(cache):w.writerow(cache[t])
    if not failed:marker.parent.mkdir(parents=True,exist_ok=True);marker.touch()
    return len(cache),'BINANCE_FUTURES_API' if cache else 'UNAVAILABLE'

def process(pair,symbol,repo,oldvault,work,logfile,mode,include_funding=True):
 try:
  dailyku,dailybn,dsrc,pages=fetch_daily(pair,pair.replace('-',''),work,oldvault,logfile,mode)
  hourly,hsrc,hrequests=fill_hourly(pair,work,repo,oldvault,dailyku,logfile,mode)
  # Delisted or unavailable on KuCoin: preserve alternate venue independently.
  bhpath=work/'hourly'/('BINANCE_'+pair+'.csv.gz')
  if bhpath.exists(): bh=gzip_rows(bhpath)
  elif mode=='online' and len(hourly)<24*30 and len(dailybn)>=25:
   bh,bpages,bcomplete=binance_daily(pair.replace('-',''),logfile,interval='1h')
   if bh:save_gzip(bhpath,bh)
  else:bh={}
  row=summarize(pair,dailyku,dailybn,hourly,hsrc,hrequests)
  row['binance_hourly_rows']=len(bh)
  row['binance_daily_api_pages']=pages
  if include_funding:
   funding_rows,fs=collect_funding(pair,work,oldvault,logfile,mode)
  else:funding_rows,fs=0,'SKIPPED_BY_USER'
  row['funding_rows']=funding_rows;row['funding_status']=fs
  journal(logfile,{'tag':'PAIR_COMPLETE','pair':pair,'kucoin_daily':len(dailyku),'binance_daily':len(dailybn),'hourly':len(hourly),'hourly_requests':hrequests})
  return row
 except Exception as e:
  journal(logfile,{'tag':'PAIR_ERROR','pair':pair,'error':repr(e)[:500]})
  return {'pair':pair,'error':repr(e)[:350]}

def derive_features(rows):
    """Observed indicators from pre-2024 candles; no future information or policy fitting."""
    if not rows:return []
    ts=sorted(rows);cl=[float(rows[t]['close']) for t in ts]
    high=[float(rows[t]['high']) for t in ts];low=[float(rows[t]['low']) for t in ts]
    em={p:None for p in (12,26,50,200)};out=[];gains=[];losses=[];trs=[]
    for i,t in enumerate(ts):
        c=cl[i];p=cl[i-1] if i else c
        if i and ts[i]-ts[i-1]!=86400000:
            for n in em:em[n]=None
        for n in em:em[n]=c if em[n] is None else (2/(n+1))*c+(1-2/(n+1))*em[n]
        gain=max(0,c-p);loss=max(0,p-c);gains.append(gain);losses.append(loss)
        tr=max(high[i]-low[i],abs(high[i]-p),abs(low[i]-p));trs.append(tr)
        # Do not calculate rolling values across absent daily candles.
        contiguous=lambda j: i>=j and ts[i]-ts[i-j]==j*86400000
        rs=None
        if contiguous(14):
            ag=sum(gains[i-13:i+1])/14;al=sum(losses[i-13:i+1])/14
            rs=100 if al==0 else (100-100/(1+ag/al))
        def ret(n):return round(100*(c/cl[i-n]-1),6) if contiguous(n) and cl[i-n]>0 else ''
        def ma(n):return round(sum(cl[i-n+1:i+1])/n,9) if contiguous(n-1) else ''
        out.append({'unix_ms':t,'date':utc_date(t),'close':c,'quote_volume':rows[t].get('quote_volume',''),
                    'ret_1d_pct':ret(1),'ret_7d_pct':ret(7),'ret_30d_pct':ret(30),'ret_90d_pct':ret(90),
                    'sma_20':ma(20),'sma_50':ma(50),'sma_200':ma(200),
                    'ema_12':round(em[12],9) if contiguous(12) else '', 'ema_26':round(em[26],9) if contiguous(26) else '', 'ema_50':round(em[50],9) if contiguous(50) else '', 'ema_200':round(em[200],9) if contiguous(200) else '',
                    'rsi_14_simple':round(rs,5) if rs is not None else '',
                    'atr_14_simple':round(sum(trs[i-13:i+1])/14,9) if contiguous(13) else '',
                    'macd_12_26':round(em[12]-em[26],9) if contiguous(26) else '',
                    'above_sma_50':int(c>sum(cl[i-49:i+1])/50) if contiguous(49) else '',
                    'source_semantics':'PAST_AND_CURRENT_CLOSED_DAILY_BARS_ONLY'})
    return out

def write_features_gzip(path,features):
    if not features:return
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.part')
    with gzip.open(tmp,'wt',newline='',encoding='utf-8',compresslevel=6) as f:
        w=csv.DictWriter(f,fieldnames=list(features[0]));w.writeheader();w.writerows(features)
    os.replace(tmp,path)

def svg_chart(path,pair,records):
    if len(records)<2:return
    rows=sorted(records.items());pts=[(t,v['close']) for t,v in rows if float(v['close'])>0]
    if len(pts)<2:return
    lo=min(math.log(float(v)) for _,v in pts);hi=max(math.log(float(v)) for _,v in pts)
    if hi<=lo:hi=lo+.00001
    w,h=940,400
    xs=[40+860*i/(len(pts)-1) for i in range(len(pts))]
    coords=' '.join(f'{x:.1f},{340-(math.log(float(v))-lo)/(hi-lo)*270:.1f}' for x,(_,v) in zip(xs,pts))
    title=pair.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    body=f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="940" height="400" fill="#ffffff"/><text x="38" y="35" font-family="Arial" font-size="19" fill="#222">{title} — daily close (log scale)</text><polyline points="{coords}" fill="none" stroke="#244a71" stroke-width="1.5"/><line x1="40" y1="342" x2="900" y2="342" stroke="#888"/><text x="40" y="372" font-family="Arial" font-size="12">{utc_date(pts[0][0])}</text><text x="805" y="372" font-family="Arial" font-size="12">{utc_date(pts[-1][0])}</text><text x="40" y="395" font-family="Arial" font-size="11">Historical observation only • not an entry/exit signal</text></svg>'''
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(body,encoding='utf-8')

def full_daily_feature_breadth(work,pairs):
    breadth=defaultdict(lambda:{'active':0,'ma50_total':0,'above_ma50':0,'ret30_total':0,'ret30_pos':0,'ret30_values':[]})
    statuses=[]
    for pair in sorted(pairs):
        ku=gzip_rows(work/'daily'/('KUCOIN_'+pair+'.csv.gz'))
        bn=gzip_rows(work/'daily'/('BINANCE_'+pair+'.csv.gz'))
        venue='KUCOIN' if ku else ('BINANCE' if bn else '')
        raw=ku if ku else bn
        if not raw:statuses.append({'pair':pair,'venue':'','features':0});continue
        features=derive_features(raw)
        write_features_gzip(work/'features'/(venue+'_'+pair+'_daily_features.csv.gz'),features)
        svg_chart(work/'charts'/(venue+'_'+pair+'_daily_log_close.svg'),pair,raw)
        statuses.append({'pair':pair,'venue':venue,'features':len(features)})
        for f in features:
            v=breadth[f['date']];v['active']+=1
            if f['above_sma_50']!='':
                v['ma50_total']+=1;v['above_ma50']+=int(f['above_sma_50'])
            if f['ret_30d_pct']!='':
                v['ret30_total']+=1;v['ret30_pos']+=int(f['ret_30d_pct']>0);v['ret30_values'].append(float(f['ret_30d_pct']))
    result=[]
    for date,b in sorted(breadth.items()):
        result.append({'date':date,'active_observed':b['active'],'ma50_available':b['ma50_total'],
                       'pct_above_sma50':round(100*b['above_ma50']/b['ma50_total'],4) if b['ma50_total'] else '',
                       'return_30d_available':b['ret30_total'],
                       'pct_30d_positive':round(100*b['ret30_pos']/b['ret30_total'],4) if b['ret30_total'] else '',
                       'median_return_30d_pct':round(statistics.median(b['ret30_values']),4) if b['ret30_values'] else '',
                       'universe_label':'OBSERVED_PANEL_NOT_PIT_MEMBERSHIP'})
    write_csv(work/'reports'/'C2_364_OBSERVED_DAILY_MARKET_BREADTH.csv',result,
              ['date','active_observed','ma50_available','pct_above_sma50','return_30d_available','pct_30d_positive','median_return_30d_pct','universe_label'])
    write_csv(work/'reports'/'C2_364_DAILY_FEATURE_COVERAGE.csv',statuses,['pair','venue','features'])
    return {'pairs_with_indicator_files':sum(z['features']>0 for z in statuses),'breadth_days':len(result),'daily_indicator_rows':sum(z['features'] for z in statuses)}

def analyze_daily(work,pairs):
 # Economic signal selection deliberately excluded. This is descriptive research coverage.
 year=[];coverage=[];all_latest={}
 for pair in sorted(pairs):
  for venue in ('KUCOIN','BINANCE'):
   records=gzip_rows(work/'daily'/(venue+'_'+pair+'.csv.gz'))
   if not records:continue
   z=defaultdict(list)
   for t,b in sorted(records.items()):z[utc_date(t)[:4]].append(b)
   for yr,v in sorted(z.items()):
    if int(yr)>=2024:continue
    qv=[float(x['quote_volume']) for x in v if x['quote_volume']!='']
    closes=[float(x['close']) for x in v]
    ret=(closes[-1]/closes[0]-1)*100 if len(v)>=2 and closes[0]>0 else None
    year.append({'pair':pair,'venue':venue,'year':yr,'days':len(v),'first_date':utc_date(int(v[0]['unix_ms'])),'last_date':utc_date(int(v[-1]['unix_ms'])),'start_close':closes[0],'end_close':closes[-1],'price_return_pct':ret,'median_quote_volume':statistics.median(qv) if qv else None})
  if pair=='BTC-USDT':
   for v in ('KUCOIN','BINANCE'):
    all_latest[v]=len(gzip_rows(work/'daily'/(v+'_BTC-USDT.csv.gz')))
 write_csv(work/'reports'/'C2_364_YEARLY_MARKET_DESCRIPTIVE.csv',year,['pair','venue','year','days','first_date','last_date','start_close','end_close','price_return_pct','median_quote_volume'])
 return {'yearly_asset_venue_rows':len(year),'btc_daily_source_count':all_latest,'no_trading_strategy_selected':True}

def packetize(work,outdir,max_mb=65):
 outdir.mkdir(parents=True,exist_ok=True)
 files=[]
 for folder in ('hourly','daily','features','derivatives_funding'):
  files.extend(sorted((work/folder).glob('*.csv.gz')))
 # Metadata and reports always in a single first archive.
 first=outdir/'UPLOAD_THIS_AKAH_C2_364_ANALYSIS_AND_COVERAGE_V4.zip'
 with zipfile.ZipFile(first,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted((work/'reports').glob('*')):
   if p.is_file():z.write(p,'reports/'+p.name)
  for p in sorted((work/'charts').glob('*.svg')):
   z.write(p,'charts/'+p.name)
  for n in ('ORIGINAL_364_AUTHORITY.json','C2_364_PLAN.csv','COLLECTION_STATUS.json'):
   p=work/n
   if p.is_file():z.write(p,n)
  j=work/'RETRIEVAL_JOURNAL.jsonl'
  if j.exists():z.write(j,j.name)
 limit=max_mb*1024*1024;parts=[];i=1;z=None;size=0;members=[]
 def close():
  nonlocal z,size,members
  if z:
   z.close();parts.append({'name':name.name,'files':members,'bytes':name.stat().st_size});z=None;size=0;members=[]
 for p in files:
  if z is None:
   name=outdir/f'UPLOAD_THIS_AKAH_C2_364_RAW_PART_{i:04d}.zip'
   z=zipfile.ZipFile(name,'w',compression=zipfile.ZIP_STORED,allowZip64=True);i+=1
  if size>=limit:
   close();name=outdir/f'UPLOAD_THIS_AKAH_C2_364_RAW_PART_{i:04d}.zip';z=zipfile.ZipFile(name,'w',compression=zipfile.ZIP_STORED,allowZip64=True);i+=1
  z.write(p,p.relative_to(work).as_posix());size+=p.stat().st_size;members.append(p.relative_to(work).as_posix())
 close()
 write_json(outdir/'UPLOAD_PART_INDEX.json',{'analysis_first':first.name,'raw_parts':parts,'raw_files':len(files),'note':'Raw gzip files are not double-compressed; upload all parts for full independent research.'})
 return {'first_archive':str(first),'raw_part_count':len(parts),'raw_files':len(files),'total_raw_part_bytes':sum(x['bytes'] for x in parts)}

def run(a):
 repo=pathlib.Path(a.repo);work=pathlib.Path(a.work);work.mkdir(parents=True,exist_ok=True)
 log=work/'RETRIEVAL_JOURNAL.jsonl'
 pairs,auth=inventory(repo,work)
 oldvault=pathlib.Path(a.oldvault)
 print('AKAH_C2_ORIGINAL_AUTHORITY=364_PAIRS_FROM_RD18_A1_PLAN',flush=True)
 print('CUTOFF=BEFORE_2024_NO_LIVE_NO_ORDERS',flush=True)
 print('PARQUET_LOCAL_REUSE='+str((repo/'data/raw/rd16b/kucoin').exists()),flush=True)
 print('PREVIOUS_17GB_CACHE_REUSE='+str(oldvault.exists()),flush=True)
 print('COLLECTION_MODE='+a.mode+' WORKERS='+str(a.workers),flush=True)
 if a.verify_only:
  write_json(work/'COLLECTION_STATUS.json',{'authority':auth,'mode':'VERIFY_ONLY','collection_done':False})
  return
 rows=[];ts=time.time()
 with ThreadPoolExecutor(max_workers=max(1,min(16,a.workers))) as pool:
  futures={pool.submit(process,p,s,repo,oldvault,work,log,a.mode,not a.skip_funding):p for p,s in pairs.items()}
  for k,f in enumerate(as_completed(futures),1):
   row=f.result();rows.append(row)
   if k%10==0 or k==len(futures):
    print('C2_364_PROGRESS',k,'/',len(pairs),'LAST',row.get('pair'),'HOURLY_ROWS',row.get('kucoin_hourly_rows',0),flush=True)
    write_csv(work/'reports'/'C2_364_COVERAGE_PARTIAL.csv',sorted(rows,key=lambda r:r['pair']),sorted(set().union(*(r.keys() for r in rows))))
  
 fields=sorted(set().union(*(r.keys() for r in rows)))
 write_csv(work/'reports'/'C2_364_COVERAGE_FINAL.csv',sorted(rows,key=lambda r:r['pair']),fields)
 desc=analyze_daily(work,pairs)
 desc.update(full_daily_feature_breadth(work,pairs))
 manifest=[]
 for folder in ('hourly','daily','features','derivatives_funding'):
  for path in sorted((work/folder).glob('*.csv.gz')):
   manifest.append({'path':path.relative_to(work).as_posix(),'bytes':path.stat().st_size,'sha256':digest(path)})
 write_csv(work/'reports'/'C2_364_FILES_SHA256_MANIFEST.csv',manifest,['path','bytes','sha256'])
 totals={'c2_original_pairs':len(pairs),'pairs_with_kucoin_daily':sum(r.get('kucoin_daily_rows',0)>0 for r in rows),'pairs_with_kucoin_hourly':sum(r.get('kucoin_hourly_rows',0)>0 for r in rows),'pairs_with_binance_daily':sum(r.get('binance_daily_rows',0)>0 for r in rows),'pairs_with_errors':sum('error' in r for r in rows),'total_kucoin_hourly_rows':sum(r.get('kucoin_hourly_rows',0) for r in rows),'total_kucoin_daily_rows':sum(r.get('kucoin_daily_rows',0) for r in rows),'total_binance_daily_rows':sum(r.get('binance_daily_rows',0) for r in rows),'total_funding_rows':sum(r.get('funding_rows',0) for r in rows),'pairs_with_binance_hourly_alt':sum(r.get('binance_hourly_rows',0)>0 for r in rows),'network_circuit_breaker':_global_network_failures[0]>=35,'blocked_network_hosts':sorted(_blocked_hosts),'elapsed_seconds':round(time.time()-ts,1), 'analysis':desc}
 write_json(work/'COLLECTION_STATUS.json',{'schema':VERSION,'source_authority':auth,'mode':a.mode,'pre2024_cutoff_enforced':True,'no_live_calls':True,'no_trading_orders':True,'production_mutation':False,'status':'PARTIAL_OR_COMPLETE_REQUIRES_PER_ASSET_COVERAGE_AUDIT','totals':totals,'limitations':['Historical point-in-time C2 eligibility not certified','Global BTC dominance, stablecoin market cap and orderbook history not fabricated','Raw minute and aggregated trades deferred; prioritize broad 364 core before large files','KuCoin delisted pairs and absent history require historical alternate sources','Binance and KuCoin daily data are separate venues, never silently merged','Network API responses can return partial historical coverage and need coverage verification','HTTP host circuit breakers prevent hours lost to unreachable providers']})
 packets=packetize(work,pathlib.Path(a.upload),a.packet_mb)
 print('C2_364_TOTALS='+json.dumps(totals),flush=True)
 print('UPLOAD_FIRST='+packets['first_archive'],flush=True)
 print('RAW_PART_COUNT='+str(packets['raw_part_count']),flush=True)

def selftest():
 assert to_int_ms('2023-12-31T23:00:00Z')<CUTOFF_MS
 assert to_int_ms('2024-01-01T00:00:00Z')==CUTOFF_MS
 assert validate_bar({'unix_ms':CUTOFF_MS,'open':1,'high':2,'low':.5,'close':1}) is None
 assert validate_bar({'unix_ms':CUTOFF_MS-86400000,'open':1,'high':2,'low':.5,'close':1}) is not None
 assert validate_bar({'unix_ms':CUTOFF_MS-86400000,'open':1,'high':.3,'low':.5,'close':1}) is None
 import tempfile
 with tempfile.TemporaryDirectory() as td:
  p=pathlib.Path(td)/'test.csv.gz';rows={CUTOFF_MS-86400000:validate_bar({'unix_ms':CUTOFF_MS-86400000,'open':2,'high':3,'low':1,'close':2,'base_volume':5})}
  save_gzip(p,rows);assert len(gzip_rows(p))==1
  try:inventory(pathlib.Path(td),pathlib.Path(td)/'out');raise AssertionError('Missing 364 accepted')
  except RuntimeError as e:assert 'ORIGINAL_C2_364_PLAN_MISSING' in str(e)
 print('SELFTEST=PASS_7_BASIC_SAFETY_CHECKS')

def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',default=r'C:\SIRAJ\Repositories\spot-speculation-bot');p.add_argument('--work',required=False);p.add_argument('--oldvault',required=False);p.add_argument('--upload',required=False);p.add_argument('--workers',type=int,default=10);p.add_argument('--packet-mb',type=int,default=65);p.add_argument('--mode',choices=['online','offline'],default='online');p.add_argument('--skip-funding',action='store_true');p.add_argument('--verify-only',action='store_true');p.add_argument('--selftest',action='store_true');a=p.parse_args()
 if a.selftest:return selftest()
 if not all((a.work,a.oldvault,a.upload)):p.error('--work, --oldvault and --upload required')
 run(a)
if __name__=='__main__':main()

'@
[System.IO.File]::WriteAllText($worker,$source,[System.Text.UTF8Encoding]::new($false))
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $p = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $p) { throw 'No usable Python found. Need local Python installation.' }
    $python = $p.Source
}
Write-Host 'AKAH_C2_364_FAST_V4=BEGIN'
Write-Host ('SOURCE_PLAN=' + (Join-Path $repo 'data\research\rd18_p3x_a1_runtime\full-c2-hourly-acquisition-plan.csv'))
Write-Host ('EXISTING_MARKET_VAULT=' + $oldvault)
Write-Host ('OUTPUT_DIR=' + $upload)
Write-Host 'NO_2024=YES | NO_LIVE=YES | NO_PRODUCTION_MUTATION=YES'
& $python $worker --selftest
if ($LASTEXITCODE -ne 0) { throw 'SELFTEST_FAILED' }
& $python $worker --mode online --repo $repo --work $work --oldvault $oldvault --upload $upload --workers 10 --packet-mb 65
$rc = $LASTEXITCODE
Write-Host ('AKAH_C2_364_EXIT_CODE=' + $rc)
if ($rc -ne 0) { throw 'C2_364_STAGE_FAILED_OR_PARTIAL; existing files preserved; rerun same command.' }
Write-Host ('UPLOAD_PACKET_FOLDER=' + $upload)
Write-Host 'UPLOAD_ANALYSIS_FILE=UPLOAD_THIS_AKAH_C2_364_ANALYSIS_AND_COVERAGE_V4.zip'
