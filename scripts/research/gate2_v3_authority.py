"""Verify locked reviews and expose only past source provenance, never economics."""
from pathlib import Path
import sys,json,csv,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_post_dual_review_adjudication as previous
from spotbot.research.multi_school_fidelity import fidelity_pipeline as pipe

OUT=Path('governance/final_gate2_to_gate3_replay_ready_mega_v3')
V2=Path('governance/post_dual_review_gate2_adjudication_pre_gate3_closure_v2')

def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=str)+'\n',encoding='utf-8')

def main():
    repo=Path.cwd(); downloads=Path('C:/Users/abdul/Downloads')
    a,b,trace,proof,spec,bindings=previous.authorities(repo,downloads)
    save('original_98_authority_reverified.json',{'proof':proof,'bindings':bindings})
    peerpath=downloads/'AKAH_FINAL_GATE2_TO_GATE3_REPLAY_READY_MEGA_V3_HANDOFF/AKAH_GATE2_SUPPLEMENTAL_INDEPENDENT_AI_LOCK_V1.json'
    assert pipe.source_hash(peerpath)=='EB299491759F490662B2AB91D58AAA293B3AC5EBDA8031B31A2140E9A448B3A0'
    mine=json.loads((OUT/'02_SUPPLEMENTAL_CODEX_PROXY_LOCK.json').read_text())
    peer=json.loads(peerpath.read_text())
    ids={f'G2-SV-{i:04}' for i in range(1,35)}
    assert mine['locked'] and peer['locked']
    assert mine['corpus_sha256']==peer['corpus_sha256']=='DB9B3C97518ED4AF1D524397CB4A91CAE562808BCD3F231C0115AB15C050560D'
    assert {r['case_id'] for r in mine['responses']}=={r['case_id'] for r in peer['responses']}==ids
    mapped=json.loads((V2/'supplemental_view_SEALED_map.json').read_text())
    result=[]
    for m in mapped:
        cid=m['view_case_id']; source=m['source_case']
        x=next(r for r in mine['responses'] if r['case_id']==cid)
        y=next(r for r in peer['responses'] if r['case_id']==cid)
        result.append({'case_id':cid,'source_case':source,'proxy':x,'independent':y,'exact_agreement':x['action']==y['human_action']})
    save('03_SUPPLEMENTAL_DUAL_REVIEW_RECONCILIATION.json',{'proxy_sha256':pipe.source_hash(OUT/'02_SUPPLEMENTAL_CODEX_PROXY_LOCK.json'),'independent_sha256':pipe.source_hash(peerpath),'same_34_ids':True,'cases':result,'exact_agreements':sum(r['exact_agreement'] for r in result),'agreement_is_not_gate':True,'map_opened_after_proxy_lock':True})
    save('predrawn_reserve_source_trace.json',[r for r in trace if r['reserve']])
    save('primary_source_trace.json',[r for r in trace if not r['reserve']])
    print('ORIGINAL_RECONCILIATION='+json.dumps(proof)); print('SUPPLEMENTAL_AUTHORITY=PASS')

if __name__=='__main__': main()
