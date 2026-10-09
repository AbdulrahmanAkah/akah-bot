"""Final bounded parent provenance audit and governance closeout."""
import hashlib
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GOV=ROOT/'governance'
TASK='CAUSAL_EXIT_MECHANISM_PROFIT_ARM_COUNTERFACTUAL_EAG_PERSISTENCE_ASYNC_READY_STATE_CONTROL_HOURLY_EVIDENCE_V2_PARENT_PROVENANCE_REBASE_REVIEW_V1'
NEXT='CAUSAL_EXIT_MECHANISM_PROFIT_ARM_COUNTERFACTUAL_EAG_PERSISTENCE_ASYNC_READY_STATE_CONTROL_CANONICAL_STATE_RECOVERY_ALTERNATIVE_PATH_DECISION_V1'
RES='CANONICAL_PREDICATE_PROVENANCE_RECOVERY_TERMINATED_WITHOUT_REPRODUCIBLE_AUTHORITY'
def sha(b):return hashlib.sha256(b).hexdigest().upper()
def read(p):return json.loads(Path(p).read_bytes())
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT).decode().strip()
def emit(name,obj):
    (GOV/name).write_text(json.dumps(obj,indent=2,ensure_ascii=True)+'\n',encoding='utf-8',newline='\n')

def main():
    cp=GOV/'AKAH_BOT_SYSTEM_CHARTER.json'; raw=cp.read_bytes().decode();c=json.loads(raw)
    begin=read(GOV/'akah_parent_begin.json'); start=begin['task_start_head']
    assert git('rev-parse','HEAD')==start
    assert git('branch','--show-current')=='research/rd48-cross-venue-price-level-basis-direct-utility-v1'
    assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
    assert c['charter_revision']==begin['task_start_charter_revision']==134
    assert sha(cp.read_bytes())==begin['task_start_charter_sha256']
    assert c['constitutional_core_sha256']=='3FB4AAC711B9F8D52F68457D99B0434BCECB32B773155BA8BB1A4FFB85BE0219'
    assert c['current_state']['current_bottleneck']==TASK
    assert not list((ROOT/'.akah_bot').glob('*active*'))
    assert c['last_execution_event']['status']=='PASS'
    assert c['latest_producer_anchor_semantic_coverage_closure_retry']['producer_anchor_layer_exhausted'] is True
    wc=read(GOV/'akah_wc_report.json'); assert wc['wildcard_hop_fully_resolved'] is True
    assert sha((GOV/'akah_wc_report.json').read_bytes())==c['last_execution_event']['report_sha256']
    edge=wc['first_remaining_provenance_hop']; assert edge['target_sha256']==begin['sole_target_sha256']
    graph=read(GOV/'akah_upstream_audit_graph_v1.json')
    lineage_path=Path(graph['upstream_authority']['report_path']);assert sha(lineage_path.read_bytes())==edge['source_sha256']
    lineage=read(lineage_path);assert lineage['prior_authority']['prior_report_sha256']==edge['target_sha256']
    paths=[Path(p) for p in edge['target_paths']]; matched=[p for p in paths if p.exists() and sha(p.read_bytes())==edge['target_sha256']]
    assert matched
    parent=read(matched[0]); a=parent['assessment']; refs=a['formula_authority_references']
    assert len(refs)==a['formula_authority_reference_count']==188
    # Fail rather than silently discard a changed/unknown authority surface.
    assert set(parent)=={'schema_version','task_id','status','authority','assessment','scientific_firewall','next_bottleneck','created_at_utc'}
    assert all(set(r)=={'path','sha256','state_symbol_hits','primitive_token_hits','snippets'} for r in refs)
    assert all(set(s)=={'line','text'} for r in refs for s in r['snippets'])
    assert a['full_coverage_direct_candidates']==[] and a['full_coverage_primitive_candidates']==[]
    assert a['candidate_byte_distinct_count']==0
    ref_table=[]
    for i,r in enumerate(refs):
        ref_table.append({'json_path':f'$.assessment.formula_authority_references[{i}]','path':r['path'],'sha256':r['sha256'],'recorded_state_symbol_hits':r['state_symbol_hits'],'recorded_primitive_token_hits':r['primitive_token_hits'],'snippet_count':len(r['snippets']),'snippet_evidence':[{'json_path':f'$.assessment.formula_authority_references[{i}].snippets[{n}]','line':s['line'],'text_sha256':sha(s['text'].encode())} for n,s in enumerate(r['snippets'])],'authority_class':'SOURCE_REFERENCE_ONLY_NO_TARGET_SEMANTIC_BINDING','referenced_file_opened':False,'producer_scope_binding':None,'input_output_contract_binding':None})
    symbols=Counter(s for r in refs for s in r['state_symbol_hits'])
    targets=['E','A','G','EAG','P','EAG_seen','first_EAG_hour','latest_EAG_hour','current_EAG_age_hours','previous_EAG_true','EAG_episode_count']
    states=[]
    for target in targets:
        exact=[{'json_path':f'$.assessment.formula_authority_references[{i}].state_symbol_hits[{k}]','value':s} for i,r in enumerate(refs) for k,s in enumerate(r['state_symbol_hits']) if s==target]
        suffix=[{'json_path':f'$.assessment.formula_authority_references[{i}].state_symbol_hits[{k}]','value':s} for i,r in enumerate(refs) for k,s in enumerate(r['state_symbol_hits']) if s==target+'_t']
        states.append({'state':target,'referenced_exact_structured_symbol':bool(exact),'exact_reference_paths':exact,'recorded_suffixed_symbol_hits_without_correspondence_authority':suffix,'definition_present':False,'authoritative_formula_expression_present':False,'target_producer_identity_present':False,'target_authority_artifact_identity_present':False,'target_schema_field_present':False,'definition_executable_reproducible':False,'candidate_family_count':0,'source_artifact':None,'source_path':None,'source_sha256':None,'expression_formula':None,'definition_json_path':None,'authority_tier':'NONE','authority_class':'NO_TARGET_DEFINITION_OR_PRODUCTION_BINDING','ambiguity_status':'NO_QUALIFYING_AUTHORITY_FAMILY','basis_json_paths':['$.assessment.full_coverage_direct_candidates','$.assessment.full_coverage_primitive_candidates','$.assessment.formula_authority_references'],'snippet_text_not_promoted_to_authority':True})
    evidence={'schema_version':'akah-final-parent-authority-surfaces-v1','parent_sha256':edge['target_sha256'],'top_level_keys':list(parent),'authority_section':parent['authority'],'assessment_without_snippet_payload':{k:v for k,v in a.items() if k!='formula_authority_references'},'scientific_firewall_section':parent['scientific_firewall'],'reference_table':ref_table,'state_surface_table':states,'recorded_symbol_hit_counts':dict(symbols),'other_parent_edge_recorded_not_followed':{'json_path':'$.authority.identity_audit_sha256','value':parent['authority']['identity_audit_sha256'],'follow_authorized':False},'parent_next_bottleneck_historical_only':parent['next_bottleneck'],'source_commit':parent.get('source_commit'),'research_stage':parent.get('research_stage'),'no_child_artifacts_opened':True}
    emit('akah_parent_evidence.json',evidence)
    now=datetime.now(timezone.utc).isoformat()
    report={'schema_version':'akah-final-parent-provenance-review-v1','task_id':TASK,'status':'PASS','task_start_charter_revision':c['charter_revision'],'task_start_head':start,'preflight':'PASS','parent':{'physical_paths':[str(p) for p in matched],'sha256':edge['target_sha256'],'file_type':'JSON_OBJECT','bytes':matched[0].stat().st_size,'schema_version':parent['schema_version'],'task_id':parent['task_id'],'research_stage':parent.get('research_stage'),'source_commit':parent.get('source_commit'),'top_level_keys':list(parent),'classification':'PROVENANCE_ONLY'},'classification_evidence':[{'json_path':'$.assessment.resolution_class','value':a['resolution_class']},{'json_path':'$.assessment.reason','value':a['reason']},{'json_path':'$.assessment.full_coverage_direct_candidates','value':[]},{'json_path':'$.assessment.full_coverage_primitive_candidates','value':[]},{'json_path':'$.assessment.formula_authority_references[*]','record_keys':sorted(refs[0]),'value_interpretation':'Path/SHA/token-hit/snippet references; no canonical semantic-role or executable state contract'}],'counts':{'referenced_exact_E_A_G_EAG_P_symbols':sum(s['referenced_exact_structured_symbol'] for s in states[:5]),'recorded_suffixed_symbols_without_correspondence_authority':len(symbols),'formula_reference_records':len(refs),'exact_predicate_definition_candidates':0,'exact_hourly_state_candidates':0,'exact_producer_candidates':0,'direct_authority_child_candidates':0},'candidate_identities':[],'hourly_artifact_check':{'trade_identity':'$.authority.canonical_join_identity = trade_id','control_count':153,'time_index_binding':None,'target_state_fields_binding':None,'producing_source_binding':None,'complete_authority_chain':False},'direct_authority_path_status':'DIRECT_AUTHORITY_PATH_NOT_EXPOSED','canonical_provenance_recovery_terminated':True,'further_parent_provenance_chase_authorized':False,'resolution_class':RES,'next_bottleneck':NEXT,'evidence_path':'governance/akah_parent_evidence.json','evidence_sha256':sha((GOV/'akah_parent_evidence.json').read_bytes()),'strict_rules':{'prior_A_binding_carried_forward':False,'formula_adoption':False,'symbol_alias_correspondence_inferred':False,'reference_count_used_as_authority':False},'scientific_limit':'Termination applies to this provenance-recovery branch; not a proof that no reproducible authority exists anywhere.','alternative_decision_options':['Known-trace-identity authoritative pre-materialized hourly dataset','Control test based on directly observable frozen variables','Abandon non-reproducible historical mechanism and admit a new formulation'],'alternative_selected':None,'alignment':'ALIGNED','vision_impact':'ADVANCES','summary':'Final ordinary parent review exposes only provenance references and an explicit hourly authority gap; terminate provenance recovery and route the scientific alternative decision.','north_star_effect':'Prevents unsupported control testing and stops recursive provenance work without reproducible authority.','firewall':{'source_mutation':False,'market_data_reads':False,'control_rows_read':False,'outcome_analysis':False,'replay':False,'pnl':False,'utility':False,'optimization':False,'2023_economics':False,'2024_access':False,'2025_access':False,'hourly_reconstruction':False,'specificity_or_FPR':False,'production_claim':False,'recursive_parent_chase':False,'push':False},'created_at_utc':now}
    emit('akah_parent_report.json',report)
    revision=c['charter_revision']+1
    manifest={'schema_version':'akah-final-parent-governed-v1','task_id':TASK,'status':'PASS','task_start_head':start,'old_charter_revision':c['charter_revision'],'new_charter_revision':revision,'report_path':'governance/akah_parent_report.json','report_sha256':sha((GOV/'akah_parent_report.json').read_bytes()),'evidence_path':report['evidence_path'],'evidence_sha256':report['evidence_sha256'],'begin_sha256':sha((GOV/'akah_parent_begin.json').read_bytes()),'executor_sha256':sha(Path(__file__).read_bytes()),'resolution_class':RES,'canonical_provenance_recovery_terminated':True,'further_parent_provenance_chase_authorized':False,'next_bottleneck':NEXT,'post_closeout_head_semantics':'External post-commit identity; avoids circular self-hash','push':False}
    emit('akah_parent_gov.json',manifest)
    event={'event_type':'FINAL_PARENT_PROVENANCE_REVIEW','task_id':TASK,'status':'PASS','outcome':RES,'branch':git('branch','--show-current'),'head':start,'head_semantics':'TASK_START_AUTHORITY_HEAD','authority_bindings':{'parent_sha256':edge['target_sha256'],'source_lineage_sha256':edge['source_sha256']},'report_path':manifest['report_path'],'report_sha256':manifest['report_sha256'],'governed_manifest_path':'governance/akah_parent_gov.json','governed_manifest_sha256':sha((GOV/'akah_parent_gov.json').read_bytes()),'result':report,'alignment':report['alignment'],'vision_impact':report['vision_impact'],'summary':report['summary'],'north_star_effect':report['north_star_effect'],'next_bottleneck':NEXT,'result_ref':manifest['report_path'],'result_sha256':manifest['report_sha256'],'evidence':[report['evidence_path']],'governance_declarations':report['firewall'],'recorded_at_utc':now}
    state=c['current_state'].copy();state.update(current_bottleneck=NEXT,latest_research_execution_task_id=TASK,latest_research_execution_status='PASS',latest_governance_task_id=TASK,latest_governance_status='PASS',latest_governance_task_status='PASS',canonical_predicate_provenance_recovery_terminated=True,further_parent_provenance_chase_authorized=False,prior_A_binding_carried_forward=False)
    sync={'sync_task_id':TASK,'status':'PASS_CLOSEOUT_RECORDED','task_start_head':start,'previous_charter_revision':c['charter_revision'],'new_charter_revision':revision,'new_current_bottleneck':NEXT,'report_sha256':manifest['report_sha256'],'governed_manifest_sha256':event['governed_manifest_sha256'],'completed_at_utc':now}
    updates={'charter_revision':revision,'current_state':state,'last_updated_at_utc':now,'last_updated_by_task':TASK,'last_execution_event':event,'last_governance_sync':sync}
    decoder=json.JSONDecoder();spans={};pos=raw.index('{')+1
    while True:
        while raw[pos].isspace() or raw[pos]==',':pos+=1
        if raw[pos]=='}':break
        key,end=decoder.raw_decode(raw,pos);pos=end
        while raw[pos].isspace() or raw[pos]==':':pos+=1
        startpos=pos;_,end=decoder.raw_decode(raw,pos);spans[key]=(startpos,end);pos=end
    changes=[]
    for k,v in updates.items():
        a0,b0=spans[k];changes.append((a0,b0,json.dumps(v,indent=2).replace('\n','\r\n  ')))
    _,end=spans['recent_execution_history'];p=end-1
    while raw[p-1].isspace():p-=1
    changes.append((p,p,',\r\n    '+json.dumps(event,indent=2).replace('\n','\r\n    ')))
    for a0,b0,v in sorted(changes,reverse=True):raw=raw[:a0]+v+raw[b0:]
    parsed=json.loads(raw)
    assert parsed['constitutional_core']==c['constitutional_core']
    assert len(parsed['recent_execution_history'])==len(c['recent_execution_history'])+1
    assert parsed['recent_execution_history'][-1]==event
    assert git('rev-parse','HEAD')==begin['task_start_head']
    tmp=GOV/'akah_parent_charter.tmp';tmp.write_bytes(raw.encode());tmp.replace(cp)
    print(json.dumps({'status':'RECORDED_PENDING_COMMIT','resolution_class':RES,'revision':revision,'report_sha256':manifest['report_sha256'],'manifest_sha256':event['governed_manifest_sha256'],'evidence_sha256':report['evidence_sha256'],'charter_sha256':sha(cp.read_bytes()),'counts':report['counts'],'next_bottleneck':NEXT},indent=2))

if __name__=='__main__':main()
