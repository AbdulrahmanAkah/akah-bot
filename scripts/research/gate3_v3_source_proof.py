"""Source-only evidence recertification and bounded input hashing; no portfolio."""
from pathlib import Path
import argparse,json,hashlib
import pandas as pd
from spotbot.research.multi_school_fidelity import akah_replay_ready_detectors_v1 as det
from spotbot.research.multi_school_fidelity.akah_foundation_core_v1r1 import raw_frame,canonical_aggregate,load_broad_eligibility,BroadEligibilityIndex,utc,DATA_CUTOFF
from spotbot.research.multi_school_fidelity.gate3_market_v3 import bounded_sha,ICT,save,sha

OUT=Path('governance/final_gate2_to_gate3_replay_ready_mega_v3')
V2=Path('governance/post_dual_review_gate2_adjudication_pre_gate3_closure_v2')

def source_proof(repo):
    primary=json.loads((OUT/'primary_source_trace.json').read_text())
    reserve=json.loads((OUT/'predrawn_reserve_source_trace.json').read_text())
    supplemental=json.loads((V2/'supplemental_view_SEALED_map.json').read_text())
    cases=[{**r,'audit_id':r['case_id']} for r in primary+reserve if r['system_id']==ICT]
    cases.extend({**r['source_case'],'audit_id':r['view_case_id']} for r in supplemental if r['source_case']['system_id']==ICT)
    index=BroadEligibilityIndex.build(load_broad_eligibility(repo))
    btc,eth=raw_frame(repo,'BTC-USDT'),raw_frame(repo,'ETH-USDT')
    results=[]
    for pair in sorted({r['pair'] for r in cases}):
        selected=[r for r in cases if r['pair']==pair]; max_t=max(utc(r['time']) for r in selected)
        # Parquet timestamps are microsecond-backed. Do not truncate a 1ns bound
        # to the checkpoint itself when converting to Python datetime.
        raw=raw_frame(repo,pair,cutoff=max_t+pd.Timedelta(microseconds=1))
        h4=canonical_aggregate(repo,pair,raw,'4h'); d1=canonical_aggregate(repo,pair,raw,'1d')
        _,events,intents,_=det.scan_ict(pair,raw,h4,d1,btc.loc[btc.timestamp<=max_t],eth.loc[eth.timestamp<=max_t],index)
        for case in selected:
            t=utc(case['time']); observed=[r for r in intents if utc(r['timestamp'])==t]
            proof={'case_id':case['audit_id'],'source_case_id':case.get('case_id',case.get('supplemental_case_id')),
                'pair':pair,'checkpoint':str(t),'kind':case['kind'],'reserve':case.get('reserve',False),
                'reconstructed_intents':observed,'source_match':False,'protected_rows_loaded':0}
            if case['kind']=='POSITIVE':
                expected=json.loads(case['engine_row']['metadata'])
                match=[r for r in observed if json.loads(r['metadata'])==expected]
                proof['source_match']=bool(match)
                raid=utc(expected['raid_time']); mss=utc(expected['mss_time']); created=utc(expected['fvg_created_at'])
                proof['causal_order']=raid<mss==created<t
                proof['session_live']=t<raid.tz_convert('America/New_York').normalize()+pd.Timedelta(hours=16)
                chain=[r for r in events if raid<=utc(r['timestamp'])<=t]
                proof['owning_events']=chain
                proof['frozen_parameters']={'displacement':'.5 ATR20','retrace':'overlap frozen FVG and close > lower gap boundary','raid':'latest frozen external sell level, reclaim, own D1 UP, H4 UP/RANGE/DOWN bullish-transition; reclaim permits premium'}
            else:
                proof['source_match']=not observed
                proof['source_neutral_view_audit']='Neutral anchors enumerate all visible geometry, not the selected external liquidity/HTF-owned chain. Extra local geometry is not a funded source intent.'
            results.append(proof)
        print('ICT_SOURCE_PREFIX_AUDIT='+pair+' CASES='+str(len(selected)),flush=True)
    save(OUT/'ict_checkpoint_source_audit.json',{'cases':results,'signal_semantics_changed':False,'source_matches':sum(r['source_match'] for r in results),'all_source_matches':all(r['source_match'] for r in results),'detector_sha256':sha(Path(det.__file__)),'no_economics':True})
    if not all(r['source_match'] for r in results): raise ValueError('SOURCE_RECONSTRUCTION_MISMATCH_REQUIRES_ADJUDICATION')

def inputs(repo):
    ranking=load_broad_eligibility(repo); records=[]; missing=[]
    pairs=sorted(set(ranking.pair))
    for i,pair in enumerate(pairs):
        path=repo/'data/raw/rd16b/kucoin'/pair/'1h.parquet'
        if not path.is_file(): missing.append(pair); continue
        frame=raw_frame(repo,pair)
        if frame.empty: missing.append(pair); continue
        records.append({'pair':pair,'path':str(path.relative_to(repo)),'bounded_sha256':bounded_sha(frame),
            'rows':len(frame),'min':str(frame.timestamp.min()),'max':str(frame.timestamp.max())})
        if i%25==0: print('BOUNDED_INPUTS_VERIFIED='+str(i+1)+'/'+str(len(pairs)),flush=True)
    eligibility_sha=hashlib.sha256(pd.util.hash_pandas_object(ranking[['decision_time','pair','eligible','adjusted_rank']],index=False).values.tobytes()).hexdigest().upper()
    save(OUT/'bounded_market_input_manifest.json',{'membership_bounded_sha256':eligibility_sha,'membership_source':'data/research/rd18_p2u2/weekly-e10-ranking.csv','eligible_pairs':len(pairs),'pairs':records,'missing_raw_pairs':missing,'protected_rows_loaded':0,'full_mixed_market_files_hashed':False,'reader_predicate':'2021-09-01 <= timestamp < 2024-01-01','selection':'All PIT eligible pairs with bounded raw, no outcome-based exclusion'})
    print('BOUNDED_INPUT_MANIFEST=PASS PAIRS='+str(len(records))+' MISSING='+str(len(missing)),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--inputs',action='store_true'); args=parser.parse_args()
    inputs(Path.cwd()) if args.inputs else source_proof(Path.cwd())
