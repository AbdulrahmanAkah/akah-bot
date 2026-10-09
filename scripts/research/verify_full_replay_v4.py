"""Audit saved V4 outputs only. No market reader, model or policy execution."""
import hashlib
import json
import csv
import math
from decimal import Decimal
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
ROOT=REPO/'governance/six_school_hybrid_repair_replay_v4'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest().upper()

def table(p):
    try:return pd.read_csv(p)
    except pd.errors.EmptyDataError:return pd.DataFrame()

def main():
    result=json.loads((ROOT/'canonical_result.json').read_text())
    manifest=json.loads((ROOT/'frozen_source_manifest.json').read_text())
    assert all(sha(REPO/p)==s for p,s in manifest['files'].items()),'EXECUTABLE_SOURCE_DRIFT'
    assert sha(ROOT/'research_protocol.json')==manifest['protocol_sha']
    assert len(result['results'])==18 and len({r['grammar'] for r in result['results']})==9
    audit=[]
    for r in result['results']:
        assert r['net'] is not None,r.get('error','ARM_NOT_COMPLETE')
        folder=ROOT/(r['grammar']+'__'+str(round(r['cost']/.0025))+'X')
        m=json.loads((folder/'metrics.json').read_text())
        assert m['net']==r['net'] and m['mdd']==r['mdd']
        eq=table(folder/'hourly_equity.csv.gz');fills=table(folder/'fills.csv');campaigns=table(folder/'campaigns.csv')
        ts=pd.to_datetime(eq.time,utc=True)
        assert ts.min()>=pd.Timestamp('2022-01-01T00:00Z')
        assert ts.max()<=pd.Timestamp('2023-12-31T22:00Z')
        assert ts.is_monotonic_increasing and np.isfinite(eq.equity).all()
        error=abs(float(eq.equity.iloc[-1])-100000-r['net'])
        pnl=campaigns.net_including_fees_and_terminal_mtm.sum() if len(campaigns) else 0.
        campaign_error=abs(float(pnl)-r['net'])
        cash_change=float(fills.cash_delta.sum()) if len(fills) else 0.
        cash_error=abs(100000+cash_change-float(eq.cash.iloc[-1]))
        assert max(error,campaign_error,cash_error)<1e-5,'ACCOUNTING_PARITY'
        assert abs(float((1-eq.equity/eq.equity.cummax().clip(lower=100000)).max())-r['mdd'])<1e-12
        if len(fills):
            ft=pd.to_datetime(fills.time,utc=True)
            assert ft.min()>=pd.Timestamp('2022-01-01T00:00Z') and ft.max()<pd.Timestamp('2024-01-01T00:00Z')
            assert (fills.qty>0).all() and (fills.price>0).all() and (fills.fee>=0).all()
            # CSV -> pandas float conversion plus cumsum can create a negative
            # balance even when the original serialized decimals sum to zero.
            # Audit the text values; explicitly bound the native float64
            # serialization/remainder arithmetic rather than use a magic
            # absolute quantity tolerance across differently priced assets.
            balances={};rounding={};quantity_residual=Decimal(0);value_residual=Decimal(0)
            with (folder/'fills.csv').open(newline='') as stream:
                for f in csv.DictReader(stream):
                    key=f['identity'];q=Decimal(f['qty'])
                    balances[key]=balances.get(key,Decimal(0))+q*(1 if f['side']=='BUY' else -1)
                    rounding[key]=rounding.get(key,Decimal(0))+2*Decimal(str(math.ulp(float(q))))
                    assert balances[key]>=-rounding[key],'OVERSELL_BEYOND_BINARY64_ROUNDING'
                    quantity_residual=min(quantity_residual,balances[key])
                    value_residual=min(value_residual,balances[key]*Decimal(f['price']))
        else:quantity_residual=Decimal(0);value_residual=Decimal(0)
        assert r['source_coverage_complete'],'INCOMPLETE_SOURCE_COVERAGE'
        audit.append({'grammar':r['grammar'],'cost':r['cost'],'terminal_error':error,
            'campaign_error':campaign_error,'cash_error':cash_error,'fill_rows':len(fills),
            'campaign_rows':len(campaigns),'risk_pass':r['risk_pass'],'missing_mark_hours':r['missing_mark_hours'],
            'max_negative_serialized_quantity_residual':str(-quantity_residual),
            'max_negative_serialized_value_residual':str(-value_residual),
            'quantity_precision_contract':'serialized Decimal ledger + explicit cumulative binary64 ULP envelope; NOT exchange-lot certification',
            'status':'OUTPUT_ACCOUNTING_PASS_NOT_RISK_OR_FIDELITY_QUALIFICATION'})
    output={'status':'PASS','arms_checked':len(audit),'arms':audit,
        'source_manifest_sha256':sha(ROOT/'frozen_source_manifest.json'),
        'canonical_result_sha256':sha(ROOT/'canonical_result.json'),
        'verification_script_sha256':sha(Path(__file__)),
        'market_rows_read':False,'policy_rerun':False,'2024_access':False,'2025_access':False}
    (ROOT/'output_accounting_audit.json').write_text(json.dumps(output,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    # Preserve the exact pre-economic working bytes, independent of Git's
    # checkout line-ending conversion. This is provenance packaging only.
    with zipfile.ZipFile(ROOT/'frozen_executable_source.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
        paths={p:REPO/p for p in manifest['files']}
        paths['scripts/research/verify_full_replay_v4.py']=Path(__file__)
        for name in ('research_protocol.json','frozen_source_manifest.json','runtime_dependencies.json'):
            paths['contracts/'+name]=ROOT/name
        for name,p in sorted(paths.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,p.read_bytes())
    if (ROOT/'governance_evidence.json').exists():
        evidence=json.loads((ROOT/'governance_evidence.json').read_text())
        extra={'source_manifest':'frozen_source_manifest.json','output_accounting_audit':'output_accounting_audit.json',
            'exact_executable_source_archive':'frozen_executable_source.zip'}
        evidence=[r for r in evidence if r['type'] not in extra]
        evidence.extend({'type':k,'path':str((ROOT/n).relative_to(REPO)).replace('\\','/'),
            'sha256':sha(ROOT/n)} for k,n in extra.items())
        (ROOT/'governance_evidence.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    bindings={'files':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p)
        for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='output_manifest.json'},
        'reporting_script_sha':sha(REPO/'scripts/research/report_full_replay_v4.py'),
        'verification_script_sha':sha(Path(__file__))}
    (ROOT/'output_manifest.json').write_text(json.dumps(bindings,indent=2)+'\n',encoding='utf-8')
    print('SAVED_OUTPUT_AUDIT=PASS ARMS=18')

if __name__=='__main__':main()
