# AKAH R54-P0R5 — read-only 20-pair, 2022-2023, SHA-pinned causal reclaim event census.
# Single command; no repo mutation, no 2024, no live orders, no portfolio replay.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$python = Join-Path $repo '.venv\Scripts\python.exe'
$dl = Join-Path $HOME 'Downloads'
if (-not (Test-Path -LiteralPath $repo -PathType Container)) { throw "REPO_MISSING: $repo" }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "PYTHON_MISSING: $python" }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$work = Join-Path $dl ("AKAH_R54_P0R5_20PAIR_CENSUS_WORK_" + $stamp)
$out = Join-Path $work 'RESULTS'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$worker = Join-Path $work 'r54_p0r5_reclaim_census.py'
$source = @'
#!/usr/bin/env python3
"""AKAH R54-P0R5: SHA-pinned closed-hour sweep/reclaim event census on frozen 20-pair cohort.
No economic replay; no 2024; no execution; no PIT certification.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, hashlib, importlib.util, json, math, pathlib, re, sys, traceback, zipfile
from collections import Counter, defaultdict, deque

HORIZONS = (24, 168, 720)
HOURS_22, HOURS_23 = 8760, 8759
TOTAL = HOURS_22 + HOURS_23
VERSION = 'AKAH_R54_P0R5_20PAIR_CAUSAL_RECLAIM_CENSUS_V1'
R43_SOURCE_SHA = '2778E5EA5F34E77912A1B705A34296E4AD7A1D292E4B85FE593A163AF4C5F929'
REF_WITNESS = json.loads(r'''{"1INCH-USDT":{"2022_sha256":"A2B2D1B212824F7A8CC2D37E01F112AAE3EC848CDA129FDE3B22EAB7CEE634C9","2023_8759_sha256":"0E9EAC9EF1536C455E8A8D276F9DDD2E8704DC92BABE644BB23E2A5E043E71FC","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"AAVE-USDT":{"2022_sha256":"3B8A2B040CFE0589605BA8DB87CF90D148415F5BAB677466AFF516230F2D12C2","2023_8759_sha256":"0554E4011A62AF11B28613F1205FFD7A78561599889A3F93EFB7DEBD56FBE4FC","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ADA-USDT":{"2022_sha256":"3A925BDCC23035328FC8EC6227AE2011BEA98E3F4B475D4E7437F7514BBDB08A","2023_8759_sha256":"0628CD4CFEC38775355354133D017DF040D05880DAB79DE859322EE0DD382344","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ADX-USDT":{"2022_sha256":"52057587AF1C3D7EF3400E65B753E505A24E2E7389C57AFC180CE3480F7E9387","2023_8759_sha256":"8E10D0E803F0E9A3F1942CEA422990A180125A43F2A010ED67FDBD5494367B36","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"AGLD-USDT":{"2022_sha256":"B494E50690A9A53BC94FC11513C4E02418CBD096C85E40AD616355D50DDD4672","2023_8759_sha256":"1398D53186267B006591A5EAF2D05FB0C4E4D3860D574E3CF276CDBA3C998217","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"AIOZ-USDT":{"2022_sha256":"90F63E581674AA0E0FF83B444E6380C4EEF79E063EA91A66863FD85BFD3FC46D","2023_8759_sha256":"E150B4523899AE4B38B623F234F467367BE95B8ED6991CB174A9FA1BDE6A658D","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ALEPH-USDT":{"2022_sha256":"CFB0CC0DD3D09E57801BE33A45DFF52F5FB13533EFCE745F52827A9E67BD4D5A","2023_8759_sha256":"93B367C36AB8DC4A5E12849D6081D2FA00809F5AE71BF5E3E2025B36C38019F7","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ALGO-USDT":{"2022_sha256":"4DD285FB2BE78C1DBCE89D2ECFD1B4BAD06A3AFE595AB8ABFBF0B1DCFE985144","2023_8759_sha256":"1378FB8BADCA8859CCE710027D1B9B555CBD110E7EFF268714CED656EF47DB79","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ALICE-USDT":{"2022_sha256":"9694133FE370F2B70EEB3A00B4E268A88932F39512930878D717708397C53CF1","2023_8759_sha256":"7E396A0BCB13D8C59AA79D5D8555E677658E571FB6A0E945D5852F471625A6B2","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ANKR-USDT":{"2022_sha256":"475B7C77AFFEE31E78F8024C2BBE356016A52495B9D42A90ABEFFB68DA816675","2023_8759_sha256":"61ADBEB17ADFF5FDC8B730C8A9302469EFEDF9E42B8B4997C6216BDCAA85554E","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"API3-USDT":{"2022_sha256":"3D1B476C9A46454A39BBBCD5182AD39CF6858F20360A43B5FC5F890DED9F7A51","2023_8759_sha256":"6948B49E12FB01C7733B3B2C3B3E856F715DEBB89CFD8A7F28CF0F2408D01FDA","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"AR-USDT":{"2022_sha256":"47CF3202BE11A54CCC82709431498BDFB8A02DF6EAEADFCF4E7DF8D024CEB870","2023_8759_sha256":"F190D0C237FB0FFC726B47113E24E439D6003725002F04796914810A2F128970","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ARPA-USDT":{"2022_sha256":"48C759C25C5262C9A7537A059930D017ED7B0ACF665837F21DF2E129ED3F62F6","2023_8759_sha256":"4482DDB59203702D3E3E1FC9B09E2DB2A3CC05CD6D8732FD1FFB1573663C2D4F","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ATA-USDT":{"2022_sha256":"834B07ECB89BA234C45F84D88DB9A36F4A93E8C4A6A03F74D62CBC8971646272","2023_8759_sha256":"AA419935BAE8048031158BB91759E510865B78BA41F64901109AEA855CE6A9A6","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ATOM-USDT":{"2022_sha256":"2426D32C40A9D7D6D6A24521594FF471F5B6AD7A1C59AE59D8413AF5FFE3C8BC","2023_8759_sha256":"22DBDBE127B7A469EA75DD8BAB5E9005177D13E7AEEDFD4A6FA63D4183FEA9C1","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"AUDIO-USDT":{"2022_sha256":"019744BFFC74A56DFFF4812F9BD0FB036AD2B0DDEE46C56BF3FE8B8EC90D6A1A","2023_8759_sha256":"EB4016BD6998EAEB3616D78453BDBB69B7BD5743C6486CB4182BA2E4F733E81B","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"AVA-USDT":{"2022_sha256":"0C0AB9E49660A4E2094182C6082E41D6D6D2208131BFA7400E933E1CE7906E3C","2023_8759_sha256":"68E41435CF09416FC65C2AC13C2BA4225236129D848ADCE068EF0BCECEDF676E","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"BTC-USDT":{"2022_sha256":"783D22974685C454DE44D033C9C8E205B75348B3588E957FF25719DE79619260","2023_8759_sha256":"1594DC431F2E7F7E26FECA061CAF337FB2B54AD0E134806158DFDE2A4F59D519","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"ETH-USDT":{"2022_sha256":"2D95E40F8957642E9BF11DA86A1137327E222D56F72AF1418CA9B992AB81F073","2023_8759_sha256":"3C52C93F5376134219ED68A261CC687C094CDB640748B33BDBD18518E97780BA","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true},"SOL-USDT":{"2022_sha256":"061A21B1D916B3F681936EC7C3633134EB5C10D47829D8E251902BEBEA40012C","2023_8759_sha256":"998CEE1328D65907C740CD9554D8B22E7B05F3F6D501393B042FA3D0AB45968C","2023_allowed_complete_hours":8759,"2023_first_open_utc":"2023-01-01T00:00:00Z","2023_last_close_utc":"2023-12-31T23:00:00Z","2023_last_open_utc":"2023-12-31T22:00:00Z","2023_terminal_hour_unobserved_by_contract":true}}''')

class ResearchBlocked(Exception): pass

def require(ok, msg):
    if not ok:raise ResearchBlocked(msg)

def sha256(buf):return hashlib.sha256(buf).hexdigest().upper()

def write_json(p, x):
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False,sort_keys=True,default=str)+'\n',encoding='utf-8')

def write_csv(p, rows, fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)

def finder(downloads):
    # Bounded: only archived trusted R50 bundles used previously in this research lineage.
    wanted=[]
    for root in [downloads/'AKAH_R50_CONTINUOUS_SURVIVAL_WORK',downloads/'AKAH_R50R1_SHA_CHAIN_RECOVERY_WORK',downloads]:
        if not root.is_dir():continue
        for f in sorted(root.glob('AKAH_R50*.zip')):
            if f not in wanted:wanted.append(f)
    return wanted

def get_vendor(downloads, work):
    for f in finder(downloads):
        with zipfile.ZipFile(f) as z:
            choices=[n for n in z.namelist() if n.replace('\\','/').endswith('/r43_data.py')]
            for name in choices:
                # Check source bytes BEFORE importing.
                raw=z.read(name)
                if sha256(raw)!=R43_SOURCE_SHA:continue
                local=work/'r54_checked_r43_data.py';local.write_bytes(raw)
                spec=importlib.util.spec_from_file_location('r54_checked_r43_data',local)
                require(spec is not None and spec.loader is not None,'INVALID_PINNED_R43_MODULE')
                mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
                for field in ('REC','START','H','validate_row'):require(hasattr(mod,field),'R43_MISSING_ATTRIBUTE_'+field)
                require(hasattr(mod.REC,'size') and mod.REC.size>0,'INVALID_RECORD_STRUCT')
                return mod,{'archive':str(f),'member':name,'r43_source_sha256':sha256(raw),'record_size':mod.REC.size}
    raise ResearchBlocked('PINNED_R43_DATA_MODULE_NOT_FOUND_IN_R50_ARCHIVES')

def load_plan(downloads):
    choices=[downloads/'AKAH_R13R27_MEGA_WORK'/'R13R27_FROZEN_PLAN.json', downloads/'R13R27_FROZEN_PLAN.json']
    for p in choices:
        if p.is_file():
            x=json.loads(p.read_text(encoding='utf-8-sig'))
            require(isinstance(x.get('eligible'),dict),'R27_ELIGIBLE_MAP_MISSING')
            return x,p
    raise ResearchBlocked('R27_FROZEN_PLAN_MISSING')

def detect_events(rows):
    queues={h:deque() for h in HORIZONS}
    found=[]
    for idx,(lo,cl) in enumerate(rows):
        flags=[]
        for h in HORIZONS:
            q=queues[h]
            while q and q[0][0]<idx-h:q.popleft()
            if idx>=h:
                require(bool(q),'EMPTY_CAUSAL_HISTORY')
                floor=q[0][1]
                if lo<floor and cl>floor:flags.append(h)
            while q and q[-1][1]>=lo:q.pop()
            q.append((idx,lo))
        if flags:found.append((idx,tuple(flags)))
    return found

def verify_detector():
    for h in HORIZONS:
        series=[(100.0,101.0)]*h + [(99.0,101.0)]
        found=detect_events(series)
        require(len(found)==1 and found[0][0]==h and h in found[0][1],'DETECTOR_TEST_'+str(h))
        no_reclaim=[(100.,101.)]*h+[(99.,99.)]
        require(not detect_events(no_reclaim),'FAILURE_TO_REJECT_NOT_RECLAIMED')
        require(not detect_events(series[:-1]),'FAILURE_TO_REJECT_INCOMPLETE_HISTORY')
        ext=series+[(50.,50.),(60.,60.)]
        require(found[0] in detect_events(ext),'PREFIX_INVARIANCE_FAIL')
    # Boundary: 24-hour floor must not include current bar when deciding sweep.
    require(not detect_events([(100.,100.)]*24+[(101.,101.)]),'NON_SWEEP_ACCEPTED')
    return 13

def scan_pair(repo, pair, offset, mod, out_rows):
    path=repo/'.akah_bot'/'v2r2_common_causal_tape_v1'/'pairs'/(pair+'.1H.bars.bin')
    require(path.is_file(),'TAPE_MISSING:'+pair)
    require(isinstance(offset,int) and offset>=0,'INVALID_R27_OFFSET:'+pair)
    require(path.stat().st_size >= (offset+TOTAL)*mod.REC.size,'INSUFFICIENT_RECORD_BYTES:'+pair)
    dig22=hashlib.sha256();dig23=hashlib.sha256(); lows=[]; closes=[]; nonpos_volume=0
    with path.open('rb') as f:
        f.seek(offset*mod.REC.size)
        for i in range(TOTAL):
            raw=f.read(mod.REC.size)
            require(len(raw)==mod.REC.size,'SHORT_READ_'+pair+'_'+str(i))
            vals=mod.validate_row(raw,i)
            require(len(vals)>=5,'UNEXPECTED_R43_ROW_SCHEMA:'+pair)
            op,hi,lo,cl,base_vol=[float(vals[j]) for j in range(5)]
            require(all(math.isfinite(v) for v in (op,hi,lo,cl,base_vol)),'NONFINITE_BAR:'+pair)
            require(min(op,hi,lo,cl)>0 and lo<=min(op,cl) and hi>=max(op,cl) and hi>=lo,'BAD_OHLC:'+pair)
            nonpos_volume+=(base_vol<=0)
            lows.append(lo);closes.append(cl)
            if i<HOURS_22:dig22.update(raw)
            else:dig23.update(raw)
    expected=REF_WITNESS[pair]
    sha22,sha23=dig22.hexdigest().upper(),dig23.hexdigest().upper()
    require(sha22==expected['2022_sha256'].upper(),'2022_SHA_DRIFT:'+pair)
    require(sha23==expected['2023_8759_sha256'].upper(),'2023_SHA_DRIFT:'+pair)
    events=detect_events(zip(lows,closes))
    counts=Counter()
    for idx, flags in events:
        at=mod.START+(idx+1)*mod.H
        require(at.year in (2022,2023),'OUT_OF_SCOPE_EVENT')
        y=at.year
        masks=set(flags)
        counts[str(y)+'_unique']+=1
        for h in flags:counts[str(y)+'_'+str(h)]+=1
        out_rows.append({'pair':pair,'event_closed_at_utc':at.astimezone(dt.timezone.utc).isoformat(),
                        'year':y,'bar_index':idx,'sweep_reclaim_24h':int(24 in masks),
                        'sweep_reclaim_168h':int(168 in masks),'sweep_reclaim_720h':int(720 in masks),
                        'low':round(lows[idx],12),'close':round(closes[idx],12),
                        'economic_outcome_known':False,'historical_PIT_membership_certified':False})
    return {'pair':pair,'sha256_2022':sha22,'sha256_2023_8759':sha23,
            'rows_2022':HOURS_22,'rows_2023':HOURS_23,'nonpositive_base_volume_bars':nonpos_volume,
            'events':dict(sorted(counts.items())),'r27_offset':offset}

def main(repo,downloads,out,work):
    out.mkdir(parents=True,exist_ok=True)
    report={'version':VERSION,'stage':'R54-P0R5','status':'RUNNING','PIT_membership_certified':False,
            'full_196_asset_universe_certified':False,'fresh_economic_replay':False,
            'production_mutations':0,'live_orders':0,'2024_market_rows_read':0,
            'year_boundary':'2023-12-31T22:00:00Z_LAST_ALLOWED_OPEN','scope':'FROZEN_R42_20PAIR_RESEARCH_ONLY',
            'no_PIT_venue_authority':True}
    try:
        report['selftests']=verify_detector()
        plan,planpath=load_plan(downloads)
        eligible=plan['eligible']
        require(set(REF_WITNESS)<=set(eligible),'R42_FROZEN_PAIRS_NOT_SUBSET_R27')
        mod,vendor=get_vendor(downloads,work)
        report['vendor']=vendor;report['r27_plan_path']=str(planpath)
        report['R42_witness_pair_count']=len(REF_WITNESS)
        rows=[];proof=[]
        for n,pair in enumerate(sorted(REF_WITNESS),1):
            offset=eligible[pair]
            proof.append(scan_pair(repo,pair,offset,mod,rows))
            print('R54_P0R5_TAPE_PIN='+pair+' EVENT_ROWS='+str(len(rows)),flush=True)
        rows.sort(key=lambda r:(r['event_closed_at_utc'],r['pair']))
        write_csv(out/'R54_P0R5_CAUSAL_RECLAIM_EVENTS_20PAIR.csv',rows,
                  ['pair','event_closed_at_utc','year','bar_index','sweep_reclaim_24h',
                   'sweep_reclaim_168h','sweep_reclaim_720h','low','close',
                   'economic_outcome_known','historical_PIT_membership_certified'])
        counts=Counter()
        for r in rows:
            counts[str(r['year'])+'_unique']+=1
            for h in HORIZONS:
                if r['sweep_reclaim_'+str(h)+'h']:counts[str(r['year'])+'_'+str(h)]+=1
        report['status']='PASS_20PAIR_SHA_PINNED_CAUSAL_EVENT_CENSUS_NOT_ECONOMIC'
        report['rows_read_2022']=len(proof)*HOURS_22
        report['rows_read_2023']=len(proof)*HOURS_23
        report['counts']=dict(sorted(counts.items()))
        report['event_rows']=len(rows)
        report['proofs']=proof
        report['warnings']=['20-pair retrospective diagnostic cohort; not historical point-in-time listing membership.',
            'No exchange rules, spread/depth or execution impact certified.',
            'Reclaim event timing is at candle close; no same-candle executable entry assumed.',
            'No PnL calculated; any subsequent outcome analysis needs a pre-declared comparison and costs.',
            '720-hour events cannot be enumerated in first 720 hours of 2022 without 2021 history.']
    except Exception as e:
        report['status']='BLOCKED_SOURCE_OR_AUTHORITY'
        report['blocker']=type(e).__name__+': '+str(e)
        report['traceback_tail']=traceback.format_exc()[-2500:]
    write_json(out/'R54_P0R5_EVENT_CENSUS_REPORT.json',report)
    print('R54_P0R5_STATUS='+report['status'],flush=True)
    if 'blocker' in report:print('R54_P0R5_BLOCKER='+report['blocker'],flush=True)
    return report['status']=='PASS_20PAIR_SHA_PINNED_CAUSAL_EVENT_CENSUS_NOT_ECONOMIC'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=pathlib.Path,required=True)
    p.add_argument('--downloads',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--work',type=pathlib.Path,required=True)
    a=p.parse_args()
    ok=main(a.repo,a.downloads,a.out,a.work)
    sys.exit(0 if ok else 2)
'@
[System.IO.File]::WriteAllText($worker, $source, (New-Object System.Text.UTF8Encoding($false)))
$log = Join-Path $work 'RUN.log'
Write-Host 'R54_P0R5=BEGIN 20PAIR_SHA_PINNED_RECLAIM_CENSUS_2022_2023_READONLY'
& $python $worker --repo $repo --downloads $dl --out $out --work $work 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
Copy-Item -LiteralPath $log -Destination (Join-Path $out 'R54_P0R5_TERMINAL.log') -Force
$zipout = Join-Path $dl ("UPLOAD_THIS_AKAH_R54_P0R5_20PAIR_RECLAIM_CENSUS_" + $stamp + '.zip')
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $zipout -CompressionLevel Optimal -Force
Write-Host ('R54_P0R5_UPLOAD_THIS=' + $zipout)
Write-Host ('R54_P0R5_EXIT_CODE=' + $code)
if ($code -ne 0) { Write-Host 'R54_P0R5_SOURCE_GATE_BLOCKED=SEE_REPORT_IN_ZIP' }
exit $code
