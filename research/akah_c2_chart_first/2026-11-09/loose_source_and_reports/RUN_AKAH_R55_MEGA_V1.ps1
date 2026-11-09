# AKAH R55 MEGA, research-only, no 2024, no live orders, read-only repository.
# Fully self-contained executable launcher; one PowerShell command.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repo = 'C:\SIRAJ\Repositories\spot-speculation-bot'
$py = Join-Path $repo '.venv\Scripts\python.exe'
$downloads = Join-Path $HOME 'Downloads'
if (-not (Test-Path -LiteralPath $repo -PathType Container)) { throw ('REPO_MISSING: ' + $repo) }
if (-not (Test-Path -LiteralPath $py -PathType Leaf)) { throw ('PYTHON_MISSING: ' + $py) }
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
$work = Join-Path $downloads ('AKAH_R55_MEGA_WORK_' + $stamp)
$out = Join-Path $work 'RESULTS'
New-Item -ItemType Directory -Path $out -Force | Out-Null
$utf8 = New-Object System.Text.UTF8Encoding($false)
$r55_inlined_0 = @'
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
[System.IO.File]::WriteAllText((Join-Path $work 'r54_p0r5_reclaim_census.py'), $r55_inlined_0, $utf8)
$r55_inlined_1 = @'
#!/usr/bin/env python3
"""AKAH R54 Mega: 20-pair historical research & dry-run simulator, 2022–2023 only.

This is deliberately NOT a live trader; 20-pair cohort not PIT exchange-certified;
fees, slippage and liquidity are model assumptions (not venue-calibrated).
All signals are from closed bars; executions are at subsequent candle opens.
"""
from __future__ import annotations
import argparse,csv,datetime as dt,hashlib,json,math,pathlib,statistics,sys,traceback,zipfile
from dataclasses import dataclass
from collections import Counter,defaultdict
import r54_p0r5_reclaim_census as r5

VERSION='AKAH_R54_MEGA_P0R6_V1'
YEAREND=8760
TOTAL=r5.TOTAL
START=dt.datetime(2022,1,1,tzinfo=dt.timezone.utc)
CLOSE_OUT_BAR=TOTAL-1
EXPECTED_COUNTS={'2022_unique':7948,'2023_unique':5882,'2022_24':7691,'2023_24':5634,
 '2022_168':2657,'2023_168':1264,'2022_720':1131,'2023_720':508}
RESEARCH_ONLY='RETROSPECTIVE_20PAIR_NOT_PIT_CERTIFIED'

@dataclass(frozen=True)
class Policy:
    name:str
    horizon:int
    hold:int
    stop:float
    mode:str='fixed'
    shift:int=0

POLICIES=(
 Policy('D24_TACTICAL',24,48,0.08),
 Policy('W168_SWING',168,168,0.12),
 Policy('M720_REVERSAL',720,336,0.18),
 Policy('CONFLUENCE_24_168',168,240,0.12,'confluence'),
 Policy('RECLAIM_TO_TREND',24,72,0.08,'promote'),
 Policy('D24_DELAY_48H_CONTROL',24,48,0.08,'fixed',48),
)

SCENARIOS=(
 {'name':'MODEL_1X','fee_bps':10,'slip_bps':5,'latency_hours':1},
 {'name':'MODEL_2X','fee_bps':20,'slip_bps':10,'latency_hours':1},
 {'name':'MODEL_2X_DELAY3H','fee_bps':20,'slip_bps':10,'latency_hours':3},
 {'name':'MODEL_2X_EXTRA_SLIP','fee_bps':20,'slip_bps':20,'latency_hours':1},
)
CAP={'initial_cash':100000.0,'per_position_equity':0.20,'portfolio_equity_cap':0.60,
     'max_open_positions':3,'min_order_usdt':100.0,
     'max_fraction_prior_24h_quote_volume':0.001,
     'max_fraction_prior_1h_quote_volume':0.01,
     'cooldown_hours_after_exit':24}

class Gate(Exception): pass

def check(condition, message):
    if not condition: raise Gate(message)

def putjson(p,obj):
    p.write_text(json.dumps(obj,indent=2,sort_keys=True,ensure_ascii=False,default=str)+'\n',encoding='utf-8')

def putcsv(p,rows,columns):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore',lineterminator='\n')
        w.writeheader();w.writerows(rows)

def load_pin(local):
    d=json.loads(local.read_text(encoding='utf-8'))
    check(d.get('event_rows')==13830 and d.get('counts')==EXPECTED_COUNTS,'CENSUS_PIN_REPORT_MISMATCH')
    check(len(d['proofs'])==20 and d['2024_market_rows_read']==0,'PIN_REPORT_SCOPE_MISMATCH')
    return d


def causal_floor_events(low,close):
    out=[0]*len(low)
    for idx,flags in r5.detect_events(zip(low,close)):
        bit=0
        for h in flags:
            bit |= {24:1,168:2,720:4}[h]
        out[idx]=bit
    return out


def read_tapes(repo,downloads,work,pin):
    plan,plan_path=r5.load_plan(downloads)
    mod,vendor=r5.get_vendor(downloads,work)
    check(mod.REC.size==92,'R43_RECORD_SIZE_MISMATCH')
    check(set(r5.REF_WITNESS)==set(x['pair'] for x in pin['proofs']),'PIN_PAIR_LIST_MISMATCH')
    tape={}; proofs=[];counts=Counter()
    refs={x['pair']:x for x in pin['proofs']}
    for pair in sorted(r5.REF_WITNESS):
        offset=plan['eligible'].get(pair)
        check(isinstance(offset,int) and offset>=0,'FROZEN_R27_OFFSET_MISSING:'+pair)
        path=repo/'.akah_bot'/'v2r2_common_causal_tape_v1'/'pairs'/(pair+'.1H.bars.bin')
        check(path.is_file(),'TAPE_MISSING:'+pair)
        check(path.stat().st_size >= (offset+TOTAL)*mod.REC.size,'TAPE_SHORT:'+pair)
        arr={'open':[],'high':[],'low':[],'close':[],'quote_volume':[]}
        h22=hashlib.sha256();h23=hashlib.sha256()
        with path.open('rb') as f:
            f.seek(offset*mod.REC.size)
            for i in range(TOTAL):
                blob=f.read(mod.REC.size)
                check(len(blob)==mod.REC.size,'SHORT_READ:'+pair)
                v=mod.validate_row(blob,i)
                op,hi,lo,cl,vol=[float(v[j]) for j in range(5)]
                check(all(math.isfinite(x) for x in (op,hi,lo,cl,vol)),'NONFINITE_MARKET_ROW:'+pair)
                check(min(op,hi,lo,cl)>0 and lo<=min(op,cl) and hi>=max(op,cl) and hi>=lo and vol>=0,'BAD_BAR:'+pair)
                for k,x in (('open',op),('high',hi),('low',lo),('close',cl)):arr[k].append(x)
                arr['quote_volume'].append(vol*cl) # proxy; NOT certified exchange dollar-volume
                (h22 if i<YEAREND else h23).update(blob)
        w=r5.REF_WITNESS[pair]
        check(h22.hexdigest().upper()==w['2022_sha256'].upper(),'SHA_DRIFT_2022:'+pair)
        check(h23.hexdigest().upper()==w['2023_8759_sha256'].upper(),'SHA_DRIFT_2023:'+pair)
        check(refs[pair]['r27_offset']==offset,'OFFSET_DRIFT:'+pair)
        ev=causal_floor_events(arr['low'],arr['close'])
        for i,bit in enumerate(ev):
            if bit:
                year='2022' if i<YEAREND else '2023'
                counts[year+'_unique']+=1
                for h,b in ((24,1),(168,2),(720,4)):
                    if bit&b: counts[year+'_'+str(h)]+=1
        arr['events']=ev
        # Available using only prior completed bars, excluding current bar.
        prefix=[0.0];nonzero=[0]; close_prefix=[0.0]
        for volume,price in zip(arr['quote_volume'],arr['close']):
            prefix.append(prefix[-1]+volume);nonzero.append(nonzero[-1]+int(volume>0));close_prefix.append(close_prefix[-1]+price)
        arr['vol_prefix']=prefix;arr['positive_vol_prefix']=nonzero;arr['close_prefix']=close_prefix
        tape[pair]=arr
        proofs.append({'pair':pair,'2022_sha':h22.hexdigest().upper(),'2023_sha':h23.hexdigest().upper(),'offset':offset,'events':sum(bool(x) for x in ev)})
        print('PINNED='+pair+' EVENTS='+str(proofs[-1]['events']),flush=True)
    check(dict(counts)==EXPECTED_COUNTS,'RECALCULATED_CENSUS_NOT_EQUAL_FROZEN_P0R5')
    return tape,{'pairs':len(tape),'record_size':mod.REC.size,'r27_path':str(plan_path),'vendor':vendor,
                 'event_counts':dict(counts),'sources':proofs,'read_market_rows':len(tape)*TOTAL,
                 '2024_rows_read':0,'PIT_membership_certified':False}

def has_signal(bit,pol):
    if pol.mode=='confluence':return (bit&3)==3
    return bool(bit&{24:1,168:2,720:4}[pol.horizon])

def liquidity_max_usd(bars,t):
    if t<25:return 0.0
    # t is entry candle opening; [t-24,t) and t-1 are already completed.
    v24=bars['vol_prefix'][t]-bars['vol_prefix'][t-24]
    v1=bars['quote_volume'][t-1]
    enough=(bars['positive_vol_prefix'][t]-bars['positive_vol_prefix'][t-24])>=23
    return min(CAP['max_fraction_prior_24h_quote_volume']*v24,
               CAP['max_fraction_prior_1h_quote_volume']*v1) if enough and v1>0 else 0.0

def eligible_entry_score(bars,j):
    # Only source event-bar OHLCV; large candle recovery moves first, deterministic tie-break.
    return (bars['close'][j]/bars['low'][j]-1.0)

def sim(tape,policy,scenario,exclude=None,diagnostics=False):
    pairs=[p for p in sorted(tape) if p!=exclude]
    check(pairs,'NO_ASSETS')
    fee=scenario['fee_bps']/10000.0
    slip=scenario['slip_bps']/10000.0
    lag=scenario['latency_hours']+policy.shift
    cash=CAP['initial_cash'];pos={};last_exit={}; trades=[]; daily=[];weekly=[]
    max_equity=cash;max_dd=0;yearend_equity=None
    count=Counter();total_abs_exposure=0.;n_exposure_samples=0
    prev_annual_week=None
    for t in range(TOTAL):
        # Only bar t OPEN is executable; all decisions derive from <= t-1 CLOSE.
        if pos:
            for pair in sorted(list(pos)):
                entry=pos[pair];b=tape[pair];age=t-entry['i']
                prev_close=b['close'][t-1] if t>0 else b['open'][t]
                if t>entry['i']:
                    entry['peak']=max(entry['peak'],prev_close)
                if policy.mode=='promote' and not entry['promoted'] and age>=48 and t>168:
                    avg=(b['close_prefix'][t]-b['close_prefix'][t-168])/168.0
                    if prev_close>=entry['fill']*1.05 and prev_close>avg:
                        entry['promoted']=True
                        entry['hold']=336
                stop=entry['fill']*(1-policy.stop)
                if entry['promoted']:
                    stop=max(stop,entry['peak']*0.88)
                reason=None
                if t==CLOSE_OUT_BAR: reason='CONTRACT_LAST_KNOWN_OPEN'
                elif age>=entry['hold']: reason='MAX_HOLD'
                elif prev_close<=stop:reason='CLOSE_CONFIRMED_STOP_NEXT_OPEN'
                if reason:
                    proceeds=entry['qty']*b['open'][t]*(1-slip)*(1-fee)
                    pnl=proceeds-entry['cash_spent']
                    cash+=proceeds
                    trades.append({'policy':policy.name,'scenario':scenario['name'],'pair':pair,
                        'entry_i':entry['i'],'exit_i':t,
                        'entry_utc':(START+dt.timedelta(hours=entry['i'])).isoformat(),
                        'exit_utc':(START+dt.timedelta(hours=t)).isoformat(),
                        'entry_fill':entry['fill'],'exit_open':b['open'][t],
                        'entry_cash':round(entry['cash_spent'],4),'exit_cash':round(proceeds,4),
                        'net_pnl':round(pnl,4),'net_return_pct':round(100*pnl/entry['cash_spent'],5),
                        'holding_hours':age,'entry_event_bar':entry['signal_i'],
                        'promoted':entry['promoted'],'exit_reason':reason})
                    last_exit[pair]=t;del pos[pair];count['exits']+=1
        # Eligibility is at OPEN, using the prior completed event candle(s) only.
        # Limit new entries to leave at least one next-known-open for exits.
        if t < CLOSE_OUT_BAR and t>=lag and len(pos)<CAP['max_open_positions']:
            equity_open=cash+sum(item['qty']*tape[p]['open'][t] for p,item in pos.items())
            open_exposure=sum(item['qty']*tape[p]['open'][t] for p,item in pos.items())
            headroom=max(0.,CAP['portfolio_equity_cap']*equity_open-open_exposure)
            j=t-lag
            candidates=[]
            for p in pairs:
                if p in pos or t-last_exit.get(p,-10000)<CAP['cooldown_hours_after_exit']:continue
                b=tape[p]
                if not has_signal(b['events'][j],policy):continue
                max_liq=liquidity_max_usd(b,t)
                if max_liq<CAP['min_order_usdt']:
                    count['liquidity_rejected']+=1;continue
                candidates.append((-eligible_entry_score(b,j),p,max_liq,j))
            for _,p,liquid_cap,j in sorted(candidates):
                if len(pos)>=CAP['max_open_positions'] or headroom<CAP['min_order_usdt']:break
                amount=min(cash, CAP['per_position_equity']*equity_open,headroom,liquid_cap)
                if amount<CAP['min_order_usdt']:continue
                op=tape[p]['open'][t]
                fill=op*(1+slip)
                qty=amount/(fill*(1+fee))
                check(qty>0 and math.isfinite(qty),'NONPOSITIVE_QTY')
                cash-=amount;headroom-=amount
                pos[p]={'i':t,'signal_i':j,'fill':fill,'qty':qty,'cash_spent':amount,
                        'hold':policy.hold,'promoted':False,'peak':fill}
                count['entries']+=1
        # NAV includes liquidation friction on outstanding positions.
        nav=cash+sum(entry['qty']*tape[p]['close'][t]*(1-slip)*(1-fee) for p,entry in pos.items())
        check(math.isfinite(nav) and nav>0,'BANKRUPT_OR_NONFINITE_EQUITY')
        max_equity=max(nav,max_equity);max_dd=max(max_dd,1-nav/max_equity)
        if (t+1)%24==0 or t==TOTAL-1 or t==YEAREND-1:
            when=START+dt.timedelta(hours=t+1)
            daily.append({'bar_index':t,'asof_closed_utc':when.isoformat(),
                          'value_usdt':round(nav,6),'open_positions':len(pos)})
            total_abs_exposure+=sum(x['qty']*tape[p]['close'][t] for p,x in pos.items())/nav
            n_exposure_samples+=1
        if t==YEAREND-1:yearend_equity=nav
    check(not pos,'NONFLAT_AT_CONTRACT_END')
    check(yearend_equity is not None,'NO_YEAR_END_NAV')
    capital=CAP['initial_cash'];endval=cash
    # Weeks ending Sunday at 23:59 UTC; calculate from daily NAV. Separate years.
    week_last={}
    for day in daily:
        timestamp=dt.datetime.fromisoformat(day['asof_closed_utc'])
        # bar last belongs to its open date, important at year boundary
        effective=START+dt.timedelta(hours=day['bar_index'])
        year_week=effective.isocalendar()[:2]
        week_last[year_week]=(effective,day['value_usdt'])
    prev=capital
    for (year,week), (at,value) in sorted(week_last.items(),key=lambda k:k[1][0]):
        # ISO calendar can include prior year, use actual close timestamp label
        weekly.append({'week_year':year,'iso_week':week,'ending_open_utc':at.isoformat(),
                       'net_change_usdt':round(value-prev,4),
                       'ending_equity_usdt':round(value,4)})
        prev=value
    win=sum(t['net_pnl']>0 for t in trades)
    losses=-sum(t['net_pnl'] for t in trades if t['net_pnl']<0)
    gains=sum(t['net_pnl'] for t in trades if t['net_pnl']>0)
    by_pair=defaultdict(float)
    for t in trades:by_pair[t['pair']]+=t['net_pnl']
    positive_by_pair=sorted((v,p) for p,v in by_pair.items() if v>0)
    return {
        'policy':policy.name,'scenario':scenario['name'],'excluded_pair':exclude,
        'initial_cash':round(capital,3),'final_equity':round(endval,3),
        'total_pnl':round(endval-capital,3),'return_pct':round(100*(endval/capital-1),5),
        '2022_pnl':round(yearend_equity-capital,3),'2023_pnl':round(endval-yearend_equity,3),
        'max_drawdown_pct':round(max_dd*100,5), 'trades':len(trades),'winning_trades':win,
        'win_rate_pct':round(win/max(1,len(trades))*100,3),
        'profit_factor':round(gains/losses,4) if losses else None,
        'positive_weeks':sum(v['net_change_usdt']>0.001 for v in weekly),
        'negative_weeks':sum(v['net_change_usdt']<-.001 for v in weekly),
        'flat_weeks':sum(abs(v['net_change_usdt'])<=.001 for v in weekly),
        'top_profitable_pair':positive_by_pair[-1][1] if positive_by_pair else '',
        'top_profitable_pair_pnl':round(positive_by_pair[-1][0],3) if positive_by_pair else 0,
        'top_3_profitable_pair_pnl':round(sum(v for v,_ in positive_by_pair[-3:]),3),
        'avg_daily_exposure_pct':round(100*total_abs_exposure/max(1,n_exposure_samples),3),
        'liquidity_rejections':count['liquidity_rejected'],
        'cash_end':round(cash,3),
        '_trades':trades if diagnostics else [],'_daily':daily if diagnostics else [],'_weekly':weekly if diagnostics else [],
        '_pair_pnl':{p:round(v,4) for p,v in sorted(by_pair.items())} if diagnostics else {}
    }

def strip_private(x):return {k:v for k,v in x.items() if not k.startswith('_')}

def bench_buy_hold(tape,pair,scenario):
    b=tape[pair];fee=scenario['fee_bps']/10000.;slip=scenario['slip_bps']/10000.
    qty=CAP['initial_cash']/(b['open'][0]*(1+slip)*(1+fee))
    navend=qty*b['open'][CLOSE_OUT_BAR]*(1-slip)*(1-fee)
    nav22=qty*b['close'][YEAREND-1]*(1-slip)*(1-fee)
    return {'name':'B&H_'+pair,'final_equity':round(navend,3),'2022_pnl':round(nav22-100000,3),
            '2023_pnl':round(navend-nav22,3),'research_benchmark_only':True}

def verdict(m):
    return {'positive_both_years':m['2022_pnl']>0 and m['2023_pnl']>0,
            'positive_2x_total':m['total_pnl']>0,
            'max_drawdown_25pct_bound':m['max_drawdown_pct']<=25,
            'minimum_52_trades_2yrs':m['trades']>=52,
            'max_pair_dominance_less_80pct': (m['top_profitable_pair_pnl']<0.8*m['total_pnl']) if m['total_pnl']>0 else False}

def simulate_all(tape,out):
    allrows=[]; base={}
    for pol in POLICIES:
        for sc in SCENARIOS:
            result=sim(tape,pol,sc,diagnostics=sc['name']=='MODEL_2X')
            print('ECON_POLICY='+pol.name+' SCENARIO='+sc['name']+' FINAL='+str(result['final_equity'])+' 2022='+str(result['2022_pnl'])+' 2023='+str(result['2023_pnl']),flush=True)
            allrows.append(strip_private(result))
            if sc['name']=='MODEL_2X':
                base[pol.name]=result
                tag=pol.name
                putcsv(out/(tag+'_TRADES_2X.csv'),result['_trades'],
                      ['policy','scenario','pair','entry_i','exit_i','entry_utc','exit_utc','entry_fill','exit_open','entry_cash','exit_cash','net_pnl','net_return_pct','holding_hours','entry_event_bar','promoted','exit_reason'])
                putcsv(out/(tag+'_WEEKLY_2X.csv'),result['_weekly'],
                       ['week_year','iso_week','ending_open_utc','net_change_usdt','ending_equity_usdt'])
                putcsv(out/(tag+'_DAILY_2X.csv'),result['_daily'],
                       ['bar_index','asof_closed_utc','value_usdt','open_positions'])
    stress=[]
    for pol in POLICIES:
        x=base[pol.name];target=x['top_profitable_pair']
        if not target:continue
        z=sim(tape,pol,SCENARIOS[1],exclude=target)
        stress.append({'policy':pol.name,'excluded_pair':target,'final_equity':z['final_equity'],
                       '2022_pnl':z['2022_pnl'],'2023_pnl':z['2023_pnl'],'total_pnl':z['total_pnl'],
                       'max_drawdown_pct':z['max_drawdown_pct'],'trades':z['trades']})
    putcsv(out/'R54_MEGA_ALL_POLICY_SCENARIOS.csv',allrows,list(allrows[0]))
    putcsv(out/'R54_MEGA_TOP_PAIR_EXCLUSION_2X.csv',stress,
          ['policy','excluded_pair','final_equity','2022_pnl','2023_pnl','total_pnl','max_drawdown_pct','trades'])
    bench=[bench_buy_hold(tape,p,SCENARIOS[1]) for p in ('BTC-USDT','ETH-USDT')]
    ratings=[]
    for pol in POLICIES:
        row=base[pol.name];g=verdict(row)
        stressrow=next((z for z in stress if z['policy']==pol.name),None)
        oneok=bool(stressrow and stressrow['2022_pnl']>0 and stressrow['2023_pnl']>0)
        ratings.append({'policy':pol.name,'predefined_gates':g,'leave_top_pair_out_both_years_positive':oneok,
                        'research_gate_all':all(g.values()) and oneok,
                        'deployment_permitted':False,
                        'reason':'20-pair retrospective cohort not venue PIT certified; costs model-dependent; 2022–2023 repeatedly exposed'})
    # No automatic best strategy chosen from repeatedly used 2022-2023.
    return {'policies':len(POLICIES),'scenarios':len(SCENARIOS),'total_backtests':len(allrows)+len(stress),
            'results_model_2x':[strip_private(base[p.name]) for p in POLICIES],
            'benchmarks_2x':bench,'top_pair_exclusions':stress,'research_gates':ratings,
            'selected_for_live':None,'selected_for_paper_deployment':None,
            'model_cost_warning':'Assumed 1X fee 10bps + slip 5bps each side; 2X fee20bps + slip10bps; NOT canonical RD33/R50 execution model.'}

def selftest():
    check(r5.verify_detector()==13,'R5_CAUSAL_SELFTEST_FAILURE')
    p=next(q for q in POLICIES if q.name=='D24_TACTICAL')
    check(has_signal(1,p) and not has_signal(2,p),'MASK_CLASSIFICATION')
    check(has_signal(3,POLICIES[3]) and not has_signal(2,POLICIES[3]),'CONFLUENCE_MASK')
    b={'vol_prefix':[0.,100.,300.,600.,1000.], 'positive_vol_prefix':[0,1,2,3,4],
       'quote_volume':[100,200,300,400]}
    check(liquidity_max_usd(b,3)==0,'PAST_24H_REQUIREMENT')
    # No close-bar signal may fill on itself.
    check(SCENARIOS[0]['latency_hours']>=1,'SAME_CANDLE_FILL')
    check(TOTAL==17519 and CLOSE_OUT_BAR==17518,'2023_HARD_BOUNDARY')
    check(START+dt.timedelta(hours=CLOSE_OUT_BAR)==dt.datetime(2023,12,31,22,tzinfo=dt.timezone.utc),'LAST_OPEN_BOUNDARY')
    check(all(sc['fee_bps']>=0 and sc['slip_bps']>=0 for sc in SCENARIOS),'NONNEGATIVE_COSTS')
    check(all(0<pol.stop<1 and pol.hold<=720 for pol in POLICIES),'POLICY_PROTOCOL_BOUNDS')
    check(all(pol.shift>=0 for pol in POLICIES),'INVALID_SHIFT')
    return 13+9

def main(args):
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    meta={'version':VERSION,'status':'RUNNING','start_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
      'years':[2022,2023],'2024_market_rows_read':0,'live_orders':0,'production_mutations':0,
      'historical_PIT_membership_certified':False,'execution_costs_calibrated':False,
      'selection_is_exploratory':True,'cohort':RESEARCH_ONLY}
    try:
        meta['selftest_count']=selftest()
        pin=load_pin(args.pin)
        tape,authority=read_tapes(args.repo,args.downloads,args.work,pin)
        meta['authority']=authority
        meta['economic']=simulate_all(tape,out)
        meta['status']='PASS_MEGA_EXPLORATORY_ECONOMIC_REPLAY_NOT_CERTIFIED'
        # No leakage by reading 2024: each tape read exactly 17,519 complete bars.
        write_readme(out,meta)
    except Exception as e:
        meta['status']='BLOCKED_MEGA_SOURCE_OR_ECONOMIC'
        meta['blocker']=type(e).__name__+': '+str(e)
        meta['traceback_tail']=traceback.format_exc()[-3500:]
    meta['end_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    putjson(out/'R54_MEGA_REPORT.json',meta)
    print('R54_MEGA_STATUS='+meta['status'],flush=True)
    if 'blocker'in meta: print('R54_MEGA_BLOCKER='+meta['blocker'],flush=True)
    return meta['status'].startswith('PASS')

def write_readme(out,report):
    rec=report['economic'];rows=rec['results_model_2x']
    lines=['# AKAH R54 — One-pass exploratory report','',
       'NO STRATEGY APPROVED FOR LIVE OR PAPER DEPLOYMENT. Retrospective 20-asset cohort is not PIT certified.',
       'Costs and liquidity are models; no historical exchange spread/depth or order rules certified.','',
       '## 2X modeled economics, $100k initial, continuous 2022–2023','',
       '|Policy|Final equity|2022 PnL|2023 PnL|Max DD|Trades|Weeks +/-/0|','|---|---:|---:|---:|---:|---:|---|']
    for x in rows:
       lines.append(f"|{x['policy']}|${x['final_equity']:,.0f}|${x['2022_pnl']:,.0f}|${x['2023_pnl']:,.0f}|{x['max_drawdown_pct']:.2f}%|{x['trades']}|{x['positive_weeks']}/{x['negative_weeks']}/{x['flat_weeks']}|")
    lines+=['','Reference RD33/R50 values are NOT directly comparable: original cohort and costs differ.',
      'All signals are computed from completed 1H bars and earliest fills occur at future 1H opens.',
      '2024 is SEALED; never route test signal to real orders.',
      'The shifted-control is a DELAY control, not a truly random placebo.',
      'No automatic policy promotion: comparisons after many historical trials require fresh independent evidence.',
      'See R54_MEGA_ALL_POLICY_SCENARIOS.csv and *_TRADES_2X.csv and *_DAILY_2X.csv.','']
    (out/'READ_FIRST.md').write_text('\n'.join(lines),encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('repo','downloads','work','out','pin'):
        parser.add_argument('--'+name,type=pathlib.Path,required=True)
    args=parser.parse_args()
    sys.exit(0 if main(args) else 2)
'@
[System.IO.File]::WriteAllText((Join-Path $work 'r54_p0r6_mega_portfolio.py'), $r55_inlined_1, $utf8)
$r55_inlined_2 = @'
{
  "2024_market_rows_read": 0,
  "PIT_membership_certified": false,
  "R42_witness_pair_count": 20,
  "counts": {
    "2022_168": 2657,
    "2022_24": 7691,
    "2022_720": 1131,
    "2022_unique": 7948,
    "2023_168": 1264,
    "2023_24": 5634,
    "2023_720": 508,
    "2023_unique": 5882
  },
  "event_rows": 13830,
  "fresh_economic_replay": false,
  "full_196_asset_universe_certified": false,
  "live_orders": 0,
  "no_PIT_venue_authority": true,
  "production_mutations": 0,
  "proofs": [
    {
      "events": {
        "2022_168": 133,
        "2022_24": 358,
        "2022_720": 44,
        "2022_unique": 372,
        "2023_168": 57,
        "2023_24": 298,
        "2023_720": 28,
        "2023_unique": 319
      },
      "nonpositive_base_volume_bars": 17,
      "pair": "1INCH-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "A2B2D1B212824F7A8CC2D37E01F112AAE3EC848CDA129FDE3B22EAB7CEE634C9",
      "sha256_2023_8759": "0E9EAC9EF1536C455E8A8D276F9DDD2E8704DC92BABE644BB23E2A5E043E71FC"
    },
    {
      "events": {
        "2022_168": 169,
        "2022_24": 444,
        "2022_720": 55,
        "2022_unique": 458,
        "2023_168": 79,
        "2023_24": 362,
        "2023_720": 24,
        "2023_unique": 372
      },
      "nonpositive_base_volume_bars": 5,
      "pair": "AAVE-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "3B8A2B040CFE0589605BA8DB87CF90D148415F5BAB677466AFF516230F2D12C2",
      "sha256_2023_8759": "0554E4011A62AF11B28613F1205FFD7A78561599889A3F93EFB7DEBD56FBE4FC"
    },
    {
      "events": {
        "2022_168": 117,
        "2022_24": 399,
        "2022_720": 50,
        "2022_unique": 410,
        "2023_168": 61,
        "2023_24": 324,
        "2023_720": 21,
        "2023_unique": 342
      },
      "nonpositive_base_volume_bars": 5,
      "pair": "ADA-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "3A925BDCC23035328FC8EC6227AE2011BEA98E3F4B475D4E7437F7514BBDB08A",
      "sha256_2023_8759": "0628CD4CFEC38775355354133D017DF040D05880DAB79DE859322EE0DD382344"
    },
    {
      "events": {
        "2022_168": 101,
        "2022_24": 298,
        "2022_720": 38,
        "2022_unique": 310,
        "2023_168": 55,
        "2023_24": 224,
        "2023_720": 19,
        "2023_unique": 227
      },
      "nonpositive_base_volume_bars": 265,
      "pair": "ADX-USDT",
      "r27_offset": 1070,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "52057587AF1C3D7EF3400E65B753E505A24E2E7389C57AFC180CE3480F7E9387",
      "sha256_2023_8759": "8E10D0E803F0E9A3F1942CEA422990A180125A43F2A010ED67FDBD5494367B36"
    },
    {
      "events": {
        "2022_168": 109,
        "2022_24": 309,
        "2022_720": 32,
        "2022_unique": 319,
        "2023_168": 55,
        "2023_24": 256,
        "2023_720": 7,
        "2023_unique": 260
      },
      "nonpositive_base_volume_bars": 605,
      "pair": "AGLD-USDT",
      "r27_offset": 1887,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "B494E50690A9A53BC94FC11513C4E02418CBD096C85E40AD616355D50DDD4672",
      "sha256_2023_8759": "1398D53186267B006591A5EAF2D05FB0C4E4D3860D574E3CF276CDBA3C998217"
    },
    {
      "events": {
        "2022_168": 176,
        "2022_24": 492,
        "2022_720": 90,
        "2022_unique": 510,
        "2023_168": 70,
        "2023_24": 323,
        "2023_720": 35,
        "2023_unique": 333
      },
      "nonpositive_base_volume_bars": 41,
      "pair": "AIOZ-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "90F63E581674AA0E0FF83B444E6380C4EEF79E063EA91A66863FD85BFD3FC46D",
      "sha256_2023_8759": "E150B4523899AE4B38B623F234F467367BE95B8ED6991CB174A9FA1BDE6A658D"
    },
    {
      "events": {
        "2022_168": 252,
        "2022_24": 621,
        "2022_720": 169,
        "2022_unique": 629,
        "2023_168": 79,
        "2023_24": 287,
        "2023_720": 34,
        "2023_unique": 296
      },
      "nonpositive_base_volume_bars": 1268,
      "pair": "ALEPH-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "CFB0CC0DD3D09E57801BE33A45DFF52F5FB13533EFCE745F52827A9E67BD4D5A",
      "sha256_2023_8759": "93B367C36AB8DC4A5E12849D6081D2FA00809F5AE71BF5E3E2025B36C38019F7"
    },
    {
      "events": {
        "2022_168": 152,
        "2022_24": 383,
        "2022_720": 55,
        "2022_unique": 396,
        "2023_168": 74,
        "2023_24": 275,
        "2023_720": 37,
        "2023_unique": 290
      },
      "nonpositive_base_volume_bars": 5,
      "pair": "ALGO-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "4DD285FB2BE78C1DBCE89D2ECFD1B4BAD06A3AFE595AB8ABFBF0B1DCFE985144",
      "sha256_2023_8759": "1378FB8BADCA8859CCE710027D1B9B555CBD110E7EFF268714CED656EF47DB79"
    },
    {
      "events": {
        "2022_168": 99,
        "2022_24": 318,
        "2022_720": 39,
        "2022_unique": 338,
        "2023_168": 59,
        "2023_24": 238,
        "2023_720": 24,
        "2023_unique": 248
      },
      "nonpositive_base_volume_bars": 56,
      "pair": "ALICE-USDT",
      "r27_offset": 2390,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "9694133FE370F2B70EEB3A00B4E268A88932F39512930878D717708397C53CF1",
      "sha256_2023_8759": "7E396A0BCB13D8C59AA79D5D8555E677658E571FB6A0E945D5852F471625A6B2"
    },
    {
      "events": {
        "2022_168": 95,
        "2022_24": 339,
        "2022_720": 31,
        "2022_unique": 350,
        "2023_168": 62,
        "2023_24": 237,
        "2023_720": 18,
        "2023_unique": 252
      },
      "nonpositive_base_volume_bars": 17,
      "pair": "ANKR-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "475B7C77AFFEE31E78F8024C2BBE356016A52495B9D42A90ABEFFB68DA816675",
      "sha256_2023_8759": "61ADBEB17ADFF5FDC8B730C8A9302469EFEDF9E42B8B4997C6216BDCAA85554E"
    },
    {
      "events": {
        "2022_168": 105,
        "2022_24": 326,
        "2022_720": 53,
        "2022_unique": 339,
        "2023_168": 50,
        "2023_24": 303,
        "2023_720": 23,
        "2023_unique": 322
      },
      "nonpositive_base_volume_bars": 42,
      "pair": "API3-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "3D1B476C9A46454A39BBBCD5182AD39CF6858F20360A43B5FC5F890DED9F7A51",
      "sha256_2023_8759": "6948B49E12FB01C7733B3B2C3B3E856F715DEBB89CFD8A7F28CF0F2408D01FDA"
    },
    {
      "events": {
        "2022_168": 147,
        "2022_24": 439,
        "2022_720": 83,
        "2022_unique": 453,
        "2023_168": 65,
        "2023_24": 308,
        "2023_720": 39,
        "2023_unique": 328
      },
      "nonpositive_base_volume_bars": 5,
      "pair": "AR-USDT",
      "r27_offset": 1599,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "47CF3202BE11A54CCC82709431498BDFB8A02DF6EAEADFCF4E7DF8D024CEB870",
      "sha256_2023_8759": "F190D0C237FB0FFC726B47113E24E439D6003725002F04796914810A2F128970"
    },
    {
      "events": {
        "2022_168": 121,
        "2022_24": 341,
        "2022_720": 37,
        "2022_unique": 353,
        "2023_168": 61,
        "2023_24": 279,
        "2023_720": 17,
        "2023_unique": 291
      },
      "nonpositive_base_volume_bars": 123,
      "pair": "ARPA-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "48C759C25C5262C9A7537A059930D017ED7B0ACF665837F21DF2E129ED3F62F6",
      "sha256_2023_8759": "4482DDB59203702D3E3E1FC9B09E2DB2A3CC05CD6D8732FD1FFB1573663C2D4F"
    },
    {
      "events": {
        "2022_168": 107,
        "2022_24": 265,
        "2022_720": 50,
        "2022_unique": 281,
        "2023_168": 42,
        "2023_24": 190,
        "2023_720": 19,
        "2023_unique": 200
      },
      "nonpositive_base_volume_bars": 461,
      "pair": "ATA-USDT",
      "r27_offset": 1214,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "834B07ECB89BA234C45F84D88DB9A36F4A93E8C4A6A03F74D62CBC8971646272",
      "sha256_2023_8759": "AA419935BAE8048031158BB91759E510865B78BA41F64901109AEA855CE6A9A6"
    },
    {
      "events": {
        "2022_168": 129,
        "2022_24": 408,
        "2022_720": 63,
        "2022_unique": 423,
        "2023_168": 98,
        "2023_24": 327,
        "2023_720": 47,
        "2023_unique": 350
      },
      "nonpositive_base_volume_bars": 5,
      "pair": "ATOM-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "2426D32C40A9D7D6D6A24521594FF471F5B6AD7A1C59AE59D8413AF5FFE3C8BC",
      "sha256_2023_8759": "22DBDBE127B7A469EA75DD8BAB5E9005177D13E7AEEDFD4A6FA63D4183FEA9C1"
    },
    {
      "events": {
        "2022_168": 137,
        "2022_24": 376,
        "2022_720": 57,
        "2022_unique": 388,
        "2023_168": 59,
        "2023_24": 261,
        "2023_720": 26,
        "2023_unique": 272
      },
      "nonpositive_base_volume_bars": 49,
      "pair": "AUDIO-USDT",
      "r27_offset": 1238,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "019744BFFC74A56DFFF4812F9BD0FB036AD2B0DDEE46C56BF3FE8B8EC90D6A1A",
      "sha256_2023_8759": "EB4016BD6998EAEB3616D78453BDBB69B7BD5743C6486CB4182BA2E4F733E81B"
    },
    {
      "events": {
        "2022_168": 129,
        "2022_24": 392,
        "2022_720": 37,
        "2022_unique": 400,
        "2023_168": 76,
        "2023_24": 254,
        "2023_720": 39,
        "2023_unique": 265
      },
      "nonpositive_base_volume_bars": 232,
      "pair": "AVA-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "0C0AB9E49660A4E2094182C6082E41D6D6D2208131BFA7400E933E1CE7906E3C",
      "sha256_2023_8759": "68E41435CF09416FC65C2AC13C2BA4225236129D848ADCE068EF0BCECEDF676E"
    },
    {
      "events": {
        "2022_168": 112,
        "2022_24": 375,
        "2022_720": 44,
        "2022_unique": 384,
        "2023_168": 69,
        "2023_24": 292,
        "2023_720": 18,
        "2023_unique": 303
      },
      "nonpositive_base_volume_bars": 3,
      "pair": "BTC-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "783D22974685C454DE44D033C9C8E205B75348B3588E957FF25719DE79619260",
      "sha256_2023_8759": "1594DC431F2E7F7E26FECA061CAF337FB2B54AD0E134806158DFDE2A4F59D519"
    },
    {
      "events": {
        "2022_168": 127,
        "2022_24": 395,
        "2022_720": 50,
        "2022_unique": 406,
        "2023_168": 38,
        "2023_24": 285,
        "2023_720": 15,
        "2023_unique": 292
      },
      "nonpositive_base_volume_bars": 5,
      "pair": "ETH-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "2D95E40F8957642E9BF11DA86A1137327E222D56F72AF1418CA9B992AB81F073",
      "sha256_2023_8759": "3C52C93F5376134219ED68A261CC687C094CDB640748B33BDBD18518E97780BA"
    },
    {
      "events": {
        "2022_168": 140,
        "2022_24": 413,
        "2022_720": 54,
        "2022_unique": 429,
        "2023_168": 55,
        "2023_24": 311,
        "2023_720": 18,
        "2023_unique": 320
      },
      "nonpositive_base_volume_bars": 5,
      "pair": "SOL-USDT",
      "r27_offset": 2928,
      "rows_2022": 8760,
      "rows_2023": 8759,
      "sha256_2022": "061A21B1D916B3F681936EC7C3633134EB5C10D47829D8E251902BEBEA40012C",
      "sha256_2023_8759": "998CEE1328D65907C740CD9554D8B22E7B05F3F6D501393B042FA3D0AB45968C"
    }
  ],
  "r27_plan_path": "C:\\Users\\abdul\\Downloads\\AKAH_R13R27_MEGA_WORK\\R13R27_FROZEN_PLAN.json",
  "rows_read_2022": 175200,
  "rows_read_2023": 175180,
  "scope": "FROZEN_R42_20PAIR_RESEARCH_ONLY",
  "selftests": 13,
  "stage": "R54-P0R5",
  "status": "PASS_20PAIR_SHA_PINNED_CAUSAL_EVENT_CENSUS_NOT_ECONOMIC",
  "vendor": {
    "archive": "C:\\Users\\abdul\\Downloads\\AKAH_R50_CONTINUOUS_SURVIVAL_ONEPASS.zip",
    "member": "vendor/r43_data.py",
    "r43_source_sha256": "2778E5EA5F34E77912A1B705A34296E4AD7A1D292E4B85FE593A163AF4C5F929",
    "record_size": 92
  },
  "version": "AKAH_R54_P0R5_20PAIR_CAUSAL_RECLAIM_CENSUS_V1",
  "warnings": [
    "20-pair retrospective diagnostic cohort; not historical point-in-time listing membership.",
    "No exchange rules, spread/depth or execution impact certified.",
    "Reclaim event timing is at candle close; no same-candle executable entry assumed.",
    "No PnL calculated; any subsequent outcome analysis needs a pre-declared comparison and costs.",
    "720-hour events cannot be enumerated in first 720 hours of 2022 without 2021 history."
  ],
  "year_boundary": "2023-12-31T22:00:00Z_LAST_ALLOWED_OPEN"
}
'@
[System.IO.File]::WriteAllText((Join-Path $work 'R54_P0R5_EVENT_CENSUS_REPORT_PIN.json'), $r55_inlined_2, $utf8)
$r55_inlined_3 = @'
#!/usr/bin/env python3
"""AKAH R55 exploratory one-pass: verify R54, predeclared gated reclaim, breakout and momentum.
Only frozen 2022/2023 local 20 tapes; no orders, no vendor API, no production edits.
"""
from __future__ import annotations
import argparse,csv,datetime as dt,hashlib,json,math,pathlib,sys,traceback
from collections import Counter,defaultdict,deque
import r54_p0r6_mega_portfolio as base

VERSION='AKAH_R55_MEGA_REGIME_CAUSAL_COMPARATIVE_V1'
EXPECTED_R54={
'D24_TACTICAL':{'MODEL_2X':70982.561},
'W168_SWING':{'MODEL_1X':103642.509,'MODEL_2X':99103.399,'MODEL_2X_DELAY3H':89627.313,'MODEL_2X_EXTRA_SLIP':91853.268},
}
N=base.TOTAL; YEAR_END=base.YEAREND
SC=base.SCENARIOS
# Hypotheses declared before running this V1 against market rows. Exploratory only.
SPECS=[
 ('BASE_W168',168,168,0.12,'base_w168'),
 ('BASE_D24',24,48,0.08,'base_d24'),
 ('W168_BTC30_RISE',168,168,0.12,'w_btc30'),
 ('W168_BTC90_RISE',168,168,0.12,'w_btc90'),
 ('W168_ASSET30_RISE',168,168,0.12,'w_asset30'),
 ('W168_BTC30_ASSET30',168,168,0.12,'w_both30'),
 ('W168_HOLD336',168,336,0.12,'base_w168'),
 ('D24_BTC30_ASSET30',24,48,0.08,'d_both30'),
 ('B20_CLOSED_BREAKOUT',168,336,0.15,'breakout20'),
 ('B20_BTC30_BREAKOUT',168,336,0.15,'breakout_btc30'),
 ('XS_28D_WEEKLY_TOP3',168,168,0.12,'weekly_top3'),
 ('XS_28D_BTC30_TOP3',168,168,0.12,'weekly_top3_btc30'),
]

def verify(cond,msg):
    if not cond:raise base.Gate(msg)

def closed_sma(b,j,n):
    if j+1<n:return None
    return (b['close_prefix'][j+1]-b['close_prefix'][j+1-n])/n

def btc_rule(btc,j,days):
    n=days*24
    if j<n-1 or j<168:return False
    ma=closed_sma(btc,j,n)
    return btc['close'][j]>ma and btc['close'][j]>btc['close'][j-168]

def asset_rule(b,j):
    if j<719 or j<168:return False
    return b['close'][j]>closed_sma(b,j,720) and b['close'][j]>b['close'][j-168]

def prior_highest(high,lookback=480):
    """out[j] max of high in [j-lookback,j); current j excluded. O(N)."""
    answer=[None]*len(high);q=deque()
    for j,h in enumerate(high):
        while q and q[0]<=j-lookback:q.popleft()
        if j>=lookback:answer[j]=high[q[0]]
        while q and high[q[-1]]<=h:q.pop()
        q.append(j)
    return answer

def create_masks(tape):
    btc=tape['BTC-USDT']
    btc30=[btc_rule(btc,j,30) for j in range(N)]
    btc90=[btc_rule(btc,j,90) for j in range(N)]
    assets={p:[asset_rule(b,j) for j in range(N)] for p,b in tape.items()}
    weekly={p:set() for p in tape}
    # Week decision at Sunday 23:00 UTC CLOSED 1H bar, next-open earliest fill.
    for j in range(47,N,168):
        if j<672:continue
        ranked=sorted(((b['close'][j]/b['close'][j-672]-1,p) for p,b in tape.items()),reverse=True)
        for momentum,p in ranked[:3]:
            if momentum>0:weekly[p].add(j)
    answer={}
    for name,h,hold,stop,mode in SPECS:
        modified={}
        for p,b in tape.items():
            mask=[0]*N
            if mode=='base_w168': mask=[int(bool(x&2))*2 for x in b['events']]
            elif mode=='base_d24': mask=[int(bool(x&1)) for x in b['events']]
            elif mode=='w_btc30': mask=[2 if (x&2) and btc30[j] else 0 for j,x in enumerate(b['events'])]
            elif mode=='w_btc90': mask=[2 if (x&2) and btc90[j] else 0 for j,x in enumerate(b['events'])]
            elif mode=='w_asset30': mask=[2 if (x&2) and assets[p][j] else 0 for j,x in enumerate(b['events'])]
            elif mode=='w_both30':mask=[2 if (x&2) and btc30[j] and assets[p][j] else 0 for j,x in enumerate(b['events'])]
            elif mode=='d_both30':mask=[1 if (x&1) and btc30[j] and assets[p][j] else 0 for j,x in enumerate(b['events'])]
            elif mode.startswith('breakout'):
                prior=prior_highest(b['high'])
                mask=[2 if (prior[j] is not None and b['close'][j]>prior[j] and
                             (mode=='breakout20' or btc30[j])) else 0 for j in range(N)]
            elif mode.startswith('weekly_top3'):
                mask=[0]*N
                for j in weekly[p]:
                    if mode=='weekly_top3' or btc30[j]:mask[j]=2
            else:raise base.Gate('UNKNOWN_MODE:'+mode)
            bb=dict(b);bb['events']=mask;modified[p]=bb
        answer[name]=(base.Policy(name,h,hold,stop),modified)
    return answer,{'btc30_hours':sum(btc30),'btc90_hours':sum(btc90),
                   'top3_weekly_positive_markers':sum(len(s) for s in weekly.values()),
                   'market_lookback_limitation':'2022 starts at 2022-01-01 (30d and 90d gates require in-range warmup; earlier 2021 hours unused)'}

def audit_result(result):
    trades=result['_trades'];daily=result['_daily'];weekly=result['_weekly']
    pnl=sum(t['net_pnl'] for t in trades)
    verify(abs(pnl-result['total_pnl'])<0.1,'PNL_LEDGER_RECONCILIATION:'+result['policy'])
    verify(abs(daily[-1]['value_usdt']-result['final_equity'])<.01,'DAILY_END_RECONCILIATION')
    verify(abs(sum(w['net_change_usdt'] for w in weekly)-result['total_pnl'])<.1,'WEEKLY_RECONCILIATION')
    verify(result['trades']==len(trades),'TRADE_COUNT_MISMATCH')
    verify(abs(result['2022_pnl']+result['2023_pnl']-result['total_pnl'])<0.01,'ANNUAL_RECONCILIATION')
    for t in trades:
        verify(2022<=dt.datetime.fromisoformat(t['entry_utc']).year<=2023 and
               2022<=dt.datetime.fromisoformat(t['exit_utc']).year<=2023,'OUT_OF_BOUNDS_TRADE')
        verify(t['entry_i']>t['entry_event_bar'],'SAME_BAR_FILL')
    return {'trades':len(trades),'net_pnl':round(pnl,3),'daily_rows':len(daily),'weekly_rows':len(weekly)}

def metrics_full(result):
    r=base.strip_private(result)
    r['annual_2022_positive']=r['2022_pnl']>0;r['annual_2023_positive']=r['2023_pnl']>0
    r['weekly_positive_share_pct']=round(100*r['positive_weeks']/max(1,r['positive_weeks']+r['negative_weeks']),3)
    r['stop_exit_pnl']=round(sum(t['net_pnl'] for t in result['_trades'] if t['exit_reason']=='CLOSE_CONFIRMED_STOP_NEXT_OPEN'),3)
    r['stop_exit_count']=sum(t['exit_reason']=='CLOSE_CONFIRMED_STOP_NEXT_OPEN' for t in result['_trades'])
    return r

def write_csv(out,rows,cols=None):
    if not rows:return
    base.putcsv(out,rows,cols or list(rows[0]))

def safe_do(tape,work,out):
    masks,gate_meta=create_masks(tape)
    all_rows=[];base_rows={};audits=[];stress=[];audit_detail=[]
    for name,_,_,_,mode in SPECS:
        pol,masked=masks[name]
        for scenario in SC:
            result=base.sim(masked,pol,scenario,diagnostics=scenario['name']=='MODEL_2X')
            row=metrics_full(result)
            all_rows.append(row)
            if name=='BASE_W168' and scenario['name'] in EXPECTED_R54['W168_SWING']:
                expected=EXPECTED_R54['W168_SWING'][scenario['name']]
                verify(abs(row['final_equity']-expected)<0.01,'R54_W168_BASELINE_PARITY_'+scenario['name'])
            if name=='BASE_D24' and scenario['name']=='MODEL_2X':
                verify(abs(row['final_equity']-EXPECTED_R54['D24_TACTICAL']['MODEL_2X'])<0.01,'R54_D24_BASELINE_PARITY')
            if scenario['name']=='MODEL_2X':
                audits.append({'policy':name,**audit_result(result)})
                base_rows[name]=result
                write_csv(out/(name+'_TRADES_2X.csv'),result['_trades'],['policy','scenario','pair','entry_i','exit_i','entry_utc','exit_utc','entry_fill','exit_open','entry_cash','exit_cash','net_pnl','net_return_pct','holding_hours','entry_event_bar','promoted','exit_reason'])
                write_csv(out/(name+'_DAILY_2X.csv'),result['_daily'],['bar_index','asof_closed_utc','value_usdt','open_positions'])
                write_csv(out/(name+'_WEEKLY_2X.csv'),result['_weekly'],['week_year','iso_week','ending_open_utc','net_change_usdt','ending_equity_usdt'])
            print(f'POLICY={name} SCENARIO={scenario["name"]} FINAL={row["final_equity"]} 2022={row["2022_pnl"]} 2023={row["2023_pnl"]} DD={row["max_drawdown_pct"]}',flush=True)
    for name,_,_,_,mode in SPECS:
        pol,masked=masks[name];ref=base_rows[name]
        target=ref['top_profitable_pair']
        if not target:continue
        rerun=base.sim(masked,pol,SC[1],exclude=target)
        stress.append({'policy':name,'removed_pair':target,'final_equity':rerun['final_equity'],'2022_pnl':rerun['2022_pnl'],
                       '2023_pnl':rerun['2023_pnl'],'max_drawdown_pct':rerun['max_drawdown_pct'],
                       'trades':rerun['trades']})
    write_csv(out/'R55_ALL_48_SCENARIOS.csv',all_rows)
    write_csv(out/'R55_LEAVE_TOP_PAIR_OUT.csv',stress)
    write_csv(out/'R55_ACCOUNTING_AUDIT.csv',audits)
    gates=[]
    for name,_,_,_,mode in SPECS:
        two=next(r for r in all_rows if r['policy']==name and r['scenario']=='MODEL_2X')
        delay=next(r for r in all_rows if r['policy']==name and r['scenario']=='MODEL_2X_DELAY3H')
        slip=next(r for r in all_rows if r['policy']==name and r['scenario']=='MODEL_2X_EXTRA_SLIP')
        ex=next((r for r in stress if r['policy']==name),None)
        g={'positive_both_years':two['2022_pnl']>0 and two['2023_pnl']>0,
           'positive_2x':two['total_pnl']>0,
           '2x_latency3h_positive':delay['total_pnl']>0,
           '2x_extra_slip_positive':slip['total_pnl']>0,
           'drawdown_le_25pct':two['max_drawdown_pct']<=25,
           'leave_top_pair_out_positive_both_years':bool(ex and ex['2022_pnl']>0 and ex['2023_pnl']>0),
           'at_least_52_trades_2yrs':two['trades']>=52}
        gates.append({'policy':name,'gates':g,'mechanical_exploratory_pass':all(g.values()),'PIT_certified':False,'cost_certified':False,'live_approved':False,'paper_approved':False})
    base.putjson(out/'R55_RESEARCH_GATES.json',gates)
    return {'n_policy':len(SPECS),'n_scenarios':len(SC),'n_economic_replays':len(all_rows)+len(stress),
            'gate_meta':gate_meta,'audit_rows':audits,'research_gates':gates,
            'results_2x':[r for r in all_rows if r['scenario']=='MODEL_2X'],
            'top_pair_exclusion':stress, 'controls':['BASE_W168','BASE_D24'],
            'R54_baseline_parity':'PASS_5_CELLS',
            'selection':'NONE_REPEATED_2022_2023_NOT_FRESH_HOLDOUT'}

def selftest():
    verify(base.selftest()==22,'R54_BASE_SELFTEST_FAILED')
    hi=[1,2,3,4,5,2,9];q=prior_highest(hi,3)
    verify(q==[None,None,None,3,4,5,5],f'HIGH_ROLLING_INCLUDES_CURRENT_OR_BAD:{q}')
    b={'close':[100.0]*720,'close_prefix':[0.0]}
    for v in b['close']:b['close_prefix'].append(b['close_prefix'][-1]+v)
    verify(closed_sma(b,719,720)==100 and closed_sma(b,718,720) is None,'SMA_CAUSAL_BAD')
    verify(base.CLOSE_OUT_BAR==17518 and N==17519,'HARD_2023_END')
    verify(len(set(z[0] for z in SPECS))==len(SPECS),'DUPLICATE_POLICY_NAME')
    return 27

def main(args):
    args.out.mkdir(parents=True,exist_ok=True)
    report={'version':VERSION,'status':'RUNNING','start_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'scope':'FROZEN_R42_20PAIR_2022_2023_ONLY','2024_market_rows_read':0,
            'production_modified':False,'live_orders':0,'PIT_historical_universe_certified':False,
            'execution_costs_certified':False,'not_independent_confirmation':True}
    try:
        report['selftests']=selftest()
        pin=base.load_pin(args.pin)
        tape,authority=base.read_tapes(args.repo,args.downloads,args.work,pin)
        report['authority']=authority
        report['economic']=safe_do(tape,args.work,args.out)
        report['status']='PASS_R55_RESEARCH_ONLY_NO_DEPLOYMENT'
    except Exception as e:
        report['status']='BLOCKED_R55';report['error']=type(e).__name__+': '+str(e)
        report['traceback_tail']=traceback.format_exc()[-4500:]
    report['end_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    base.putjson(args.out/'R55_MEGA_REPORT.json',report)
    if report['status'].startswith('PASS'):
        rows=report['economic']['results_2x']
        lines=['# R55 Research Outcomes (2022–2023 only)','',
               'No new independent holdout. All strategies exploratory, 20-asset retrospective universe; no live or paper approval.','',
               '|Policy|Equity|2022|2023|Max DD|Trades|','|---|---:|---:|---:|---:|---:|']
        for r in rows:lines.append(f"|{r['policy']}|${r['final_equity']:,.0f}|${r['2022_pnl']:,.0f}|${r['2023_pnl']:,.0f}|{r['max_drawdown_pct']:.2f}%|{r['trades']}|")
        lines+=['','R54 original W168 and D24 parity checked. 2024 market rows=0.',
                'Do not pick a winning arm from repeatedly inspected 2022/2023 and call it validated.','',
                'Mechanics: R54 verified SHA tapes, close-bar signals, next-open fills, unchanged risk cap and costs.',
                'Market and asset trend gates: data known at event close only; 2022 warmup restriction applies.',
                'Replays are model dependent and the 20-asset universe was selected retrospectively.','']
        (args.out/'READ_FIRST.md').write_text('\n'.join(lines),encoding='utf-8')
    print('R55_STATUS='+report['status'],flush=True)
    if 'error' in report:print('R55_ERROR='+report['error'],flush=True)
    return report['status'].startswith('PASS')

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for a in ('repo','downloads','work','out','pin'):ap.add_argument('--'+a,type=pathlib.Path,required=True)
    sys.exit(0 if main(ap.parse_args()) else 2)
'@
[System.IO.File]::WriteAllText((Join-Path $work 'r55_mega_engine.py'), $r55_inlined_3, $utf8)

$log = Join-Path $work 'R55_MEGA_TERMINAL.log'
Write-Host 'R55_MEGA_BEGIN=R54_BASELINE_PARITY_12_POLICIES_4_COST_SCENARIOS_TOP_PAIR_EXCLUSIONS_ONLY_2022_2023'
& $py (Join-Path $work 'r55_mega_engine.py') --repo $repo --downloads $downloads --work $work --out $out --pin (Join-Path $work 'R54_P0R5_EVENT_CENSUS_REPORT_PIN.json') 2>&1 | Tee-Object -FilePath $log
$code = $LASTEXITCODE
if (Test-Path -LiteralPath $log -PathType Leaf) { Copy-Item -LiteralPath $log -Destination (Join-Path $out 'R55_MEGA_TERMINAL.log') -Force }
$package = Join-Path $downloads ('UPLOAD_THIS_AKAH_R55_MEGA_' + $stamp + '.zip')
Compress-Archive -Path (Join-Path $out '*') -DestinationPath $package -CompressionLevel Optimal -Force
Write-Host ('R55_MEGA_UPLOAD_THIS=' + $package)
Write-Host ('R55_MEGA_EXIT_CODE=' + $code)
exit $code
