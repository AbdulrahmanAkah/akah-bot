"""Bounded governance audit; never imports or executes research code."""
import ast
import csv
import hashlib
import io
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOV = ROOT / 'governance'
TASK = 'CAUSAL_EXIT_MECHANISM_PROFIT_ARM_COUNTERFACTUAL_EAG_PERSISTENCE_ASYNC_READY_STATE_CONTROL_UPSTREAM_HOURLY_RECONSTRUCTION_SOURCE_ARTIFACT_WILDCARD_RESOLUTION_REVIEW_V1'
HEAD = '61d2a4c291db80c95f68e5ae00b54fb1f3e91792'
CORE = '3FB4AAC711B9F8D52F68457D99B0434BCECB32B773155BA8BB1A4FFB85BE0219'
def sha(b): return hashlib.sha256(b).hexdigest().upper()
def git(*args): return subprocess.check_output(['git', *args], cwd=ROOT)
def read(p): return json.loads(Path(p).read_bytes())
def emit(p, obj):
    # Generated governance evidence only.
    Path(p).write_text(json.dumps(obj, indent=2, ensure_ascii=True)+'\n', encoding='utf-8', newline='\n')

def audit():
    charter = read(GOV/'AKAH_BOT_SYSTEM_CHARTER.json')
    assert git('rev-parse','HEAD').decode().strip()==HEAD
    assert git('branch','--show-current').decode().strip()=='research/rd48-cross-venue-price-level-basis-direct-utility-v1'
    assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
    assert charter['charter_revision']==133 and charter['current_state']['current_bottleneck']==TASK
    assert charter['constitutional_core_sha256']==CORE
    assert sha((GOV/'AKAH_BOT_SYSTEM_CHARTER.json').read_bytes())=='59D576DE1521F51C19DFADC3972399ED16DD344949F15B2D957DD5036C5FA412'
    assert charter['last_execution_event']['status']=='PASS'
    assert charter['latest_producer_anchor_semantic_coverage_closure_retry']['producer_anchor_layer_exhausted'] is True
    for name,h in [('akah_upstream_audit_report_v1.json','90BE11538E66DB6A40CA5A1A35A8F2AB007779E396CBAC80C6C29ACFEBC74FB8'),('akah_upstream_audit_graph_v1.json','427A24C375E4497567933C9BC3FC0C447590EB537E93F001190B23B20FEEC581'),('akah_upstream_audit_gov_v1.json','D4CCA0117AE500900DA353D9CA158074F1018491876B10326B480EC08A2F51EE')]:
        assert sha((GOV/name).read_bytes())==h
    prior=read(GOV/'akah_upstream_audit_report_v1.json')
    upstream_path=Path(prior['upstream_authority']['report_path'])
    assert sha(upstream_path.read_bytes())=='F550E07F8713A83F018E14E3855DC076F919570E54AFA440FBAAC6E50DD367DE'
    upstream=read(upstream_path)
    unresolved=[i for i,x in enumerate(upstream['lineage_artifact_resolution']) if not x['resolved_paths']]
    assert unresolved==[31] and upstream['lineage_artifact_resolution'][31]['artifact_literal']=='ams-rd04-*.json'
    assert not list((ROOT/'.akah_bot').glob('*active*'))
    begin={'task_id':TASK,'phase':'BEGIN','task_start_head':HEAD,'task_start_charter_revision':133,'preflight':'PASS','started_at_utc':datetime.now(timezone.utc).isoformat(),'active_conflicting_task':False}
    emit(GOV/'akah_wc_begin.json',begin)

    source=ROOT/'scripts/research/run_rd04_final_adjudication.py'
    assert sha(source.read_bytes())==upstream['lineage_artifact_resolution'][31]['source_sha256']
    text=source.read_text(encoding='utf-8'); tree=ast.parse(text)
    assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Constant) and x.value=='ams-rd04-*.json' for x in ast.walk(n)))
    statement=ast.get_source_segment(text,assignment)
    source_binding={'path':source.relative_to(ROOT).as_posix(),'sha256':sha(source.read_bytes()),'statement_span':[assignment.lineno,assignment.end_lineno],'statement':statement,'statement_sha256':sha(statement.encode()),'statement_hash_encoding':'UTF8_LF_AST_SOURCE_SEGMENT_NO_TERMINAL_NEWLINE','ast':ast.dump(assignment),'scope':'run','literal':'ams-rd04-*.json','mechanism':'pathlib.Path.glob NONRECURSIVE','root_expression':'Path(__file__).resolve().parents[2] / "reports" / "research"','root':str(ROOT/'reports/research'),'exclusion':'path.name != REPORT_JSON.name','excluded_name':'ams-rd04-final-adjudication-v1.json','deduplication':'set of path.name','sorting':'only unknown = sorted(discovered.difference(expected_paths))','usage':'filename set compared with STAGE_SPECS report_name; raises on unregistered names; no wildcard-member content loading','context_span':[473,491]}
    final_path=ROOT/'reports/research/ams-rd04-final-adjudication-v1.json'; final=read(final_path)
    ledger_path=ROOT/'reports/research/ams-rd04-final-stage-ledger-v1.csv'
    assert sha(ledger_path.read_bytes())==final['output_hashes'][ledger_path.relative_to(ROOT).as_posix()].upper()
    # CSV parses provenance columns only; economic cells are never interpreted or emitted.
    ledger={r['path']: {k:r[k] for k in ['stage_id','path','sha256','evidence_commit','exists','hash_verification','reconciliation_pass']} for r in csv.DictReader(io.StringIO(ledger_path.read_text()))}
    source_commit=final['source_commit']
    assert final['status']=='COMPLETE' and final['reconciliation']['no_unregistered_stage_reports'] is True
    historic_source=git('show',source_commit+':'+source.relative_to(ROOT).as_posix()).decode()
    assert historic_source.replace('\r\n','\n')==text
    historic_names=git('ls-tree','--name-only',source_commit,'reports/research/').decode().splitlines()
    historical_glob_names={Path(x).name for x in historic_names if Path(x).match('ams-rd04-*.json')}
    current=list((ROOT/'reports/research').glob('ams-rd04-*.json'))
    targets=['hour','hour_utc','timestamp','trade_id','position_id','E','A','G','EAG','P','EAG_seen','first_EAG_hour','latest_EAG_hour','current_EAG_age_hours','previous_EAG_true','EAG_episode_count','predicate_definition','predicate_definitions','formula','formulas','producer_code','producer_sha256','source_artifact','source_artifact_sha256','reconstruction_method']
    rows=[]
    for p in sorted(current):
        b=p.read_bytes(); j=json.loads(b); rel=p.relative_to(ROOT).as_posix(); h=sha(b)
        excluded=p.name==final_path.name
        historical=ledger.get(rel)
        git_present=p.name in historical_glob_names
        blob=git('show',source_commit+':'+rel) if git_present else None
        normalized_equal=blob is not None and blob.replace(b'\r\n',b'\n')==b.replace(b'\r\n',b'\n')
        exact_ledger=historical is not None and historical['sha256'].upper()==h
        disposition='SOURCE_EXCLUDED' if excluded else 'DEFINITELY_HISTORICAL' if exact_ledger and normalized_equal else 'AMBIGUOUS'
        metadata={k:j[k] for k in ['schema_version','task_id','report_id','research_stage','generated_at_utc','generated_at','source_commit','producer_commit'] if k in j and not isinstance(j[k],(dict,list))}
        keypaths=[]
        def walk(obj,path='$'):
            if isinstance(obj,dict):
                for k,v in obj.items():
                    q=path+'.'+k
                    if k in targets: keypaths.append({'json_path':q,'field':k,'type':type(v).__name__})
                    if isinstance(v,dict): walk(v,q)
                    # Deliberately do not descend into row arrays or read scalar values.
        walk(j)
        rows.append({'path':rel,'filename':p.name,'sha256':h,'size':len(b),'tracked':bool(git('ls-files','--',rel).strip()),'duplicate_sha_group':h,'top_level_type':type(j).__name__,'top_level_keys':list(j),'metadata':metadata,'source_filter_included':not excluded,'historical_membership':disposition,'historical_evidence':{'ledger_provenance_fields':historical,'exact_ledger_sha_match':exact_ledger,'present_at_source_commit':git_present,'git_normalized_bytes_equal':normalized_equal,'git_blob_sha256':sha(blob) if blob else None},'classification':'REPORTING_ONLY' if disposition=='DEFINITELY_HISTORICAL' else 'IRRELEVANT_TO_TARGET_PREDICATES' if excluded else 'UNRESOLVED','classification_basis':'registered RD04 stage report in SHA-bound final stage ledger; schema/research_stage metadata; no canonical target authority adopted','schema_key_paths':keypaths,'row_arrays_inspected':False,'target_authority':'NOT_ESTABLISHED','hourly_rows':'NOT_ESTABLISHED_BY_METADATA','target_state_definitions':'NOT_ESTABLISHED_BY_METADATA'})
    valid=[r for r in rows if r['historical_membership']=='DEFINITELY_HISTORICAL']; ambiguous=[r for r in rows if r['historical_membership']=='AMBIGUOUS']
    result={'task_id':TASK,'task_start':begin,'source_binding':source_binding,'historical_binding':{'final_report_sha256':sha(final_path.read_bytes()),'final_report_source_commit':source_commit,'final_report_generated_at_utc':final['generated_at_utc'],'final_report_reconciliation':final['reconciliation'],'stage_ledger_sha256':sha(ledger_path.read_bytes()),'ledger_count':len(ledger),'historical_source_matches_current':True,'historical_git_glob_names':sorted(historical_glob_names),'historical_evidence_limit':'committed source tree and exact downstream ledger hashes; no filesystem enumeration log is present'},'counts':{'raw_current_matches':len(rows),'source_filtered_current_matches':len(rows)-1,'unique_raw_sha256':len({r['sha256'] for r in rows}),'unique_filtered_sha256':len({r['sha256'] for r in rows if r['source_filter_included']}),'historical_valid':len(valid),'source_excluded':1,'proven_later':0,'ambiguous_membership':len(ambiguous)},'artifacts':rows}
    emit(GOV/'akah_wc_table.json',result)
    print(json.dumps({'counts':result['counts'],'source_binding':source_binding,'historical_binding':result['historical_binding'],'membership':[(r['filename'],r['historical_membership']) for r in rows]},indent=2))

def complete():
    table=read(GOV/'akah_wc_table.json')
    graph=read(GOV/'akah_upstream_audit_graph_v1.json')
    previous={n['artifact_sha256']:(i,n) for i,n in enumerate(graph['artifact_nodes'])}
    fields=['hourly_rows','hourly_timestamps','trade_id','position_id','E','A','G','EAG','P','EAG_seen','first_EAG_hour','latest_EAG_hour','current_EAG_age_hours','previous_EAG_true','EAG_episode_count','predicate_definition_formula_metadata','producer_code_identity','source_artifact_identity','reconstruction_method_identity']
    for r in table['artifacts']:
        if not r['source_filter_included']: continue
        i,n=previous[r['sha256']]
        r['classification']=n['classification']
        r['classification_basis']={'governing_graph_sha256':'427A24C375E4497567933C9BC3FC0C447590EB537E93F001190B23B20FEEC581','json_path':f'$.artifact_nodes[{i}].classification','evidence_value':n['classification'],'current_structured_metadata':r['metadata'],'no_new_artifact_identity':True}
        # Inspect schema structure recursively without emitting row/scalar values.
        obj=read(ROOT/r['path']); hits=[]; arrays=[]; provenance=[]
        wanted=set(fields)|{'timestamp','hour','hour_utc','columns','schema','predicate_definition','predicate_definitions','formula','formulas','source_commit'}
        def schema(v,p='$'):
            if isinstance(v,dict):
                for k,x in v.items():
                    q=p+'.'+k
                    if k in wanted: hits.append({'json_path':q,'key':k,'type':type(x).__name__})
                    if k in {'source_commit','source_sha256','sha256','path','source_path','artifact_path','producer_sha256','reconstruction_method'} and isinstance(x,str):
                        provenance.append({'json_path':q,'value':x})
                    if isinstance(x,(dict,list)): schema(x,q)
            elif isinstance(v,list):
                # Only object key sets, never scalar row values.
                keysets=sorted({tuple(sorted(x)) for x in v if isinstance(x,dict)})
                arrays.append({'json_path':p,'object_key_sets':keysets,'scalar_values_not_inspected':True})
        schema(obj)
        r['schema_key_paths']=hits
        r['array_object_schema']=arrays
        r['provenance_metadata']=provenance
        r['targeted_schema_authority_check']={f:{'status':'NOT_ESTABLISHED_BY_INSPECTED_SCHEMA','evidence_paths':[h['json_path'] for h in hits if h['key']==f]} for f in fields}
        for f in ['trade_id','position_id']:
            ph=r['targeted_schema_authority_check'][f]['evidence_paths']
            if ph: r['targeted_schema_authority_check'][f]['status']='VALIDATION_MISMATCH_COLUMN_KEY_ONLY_NO_STATE_ROW_LINKAGE'
        if 'source_commit' in r['metadata']:
            r['targeted_schema_authority_check']['producer_code_identity']={'status':'SOURCE_COMMIT_RECORDED_NO_EXACT_HOURLY_PRODUCER_BINDING','evidence_paths':['$.source_commit'],'value':r['metadata']['source_commit']}
        if provenance:
            r['targeted_schema_authority_check']['source_artifact_identity']={'status':'PROVENANCE_METADATA_PRESENT_NO_TARGET_STATE_AUTHORITY','evidence_paths':[x['json_path'] for x in provenance]}
        r['schema_check_limit']='Structural metadata and object key sets only; no row values or formula bodies read. Absence of inspected exact keys is not proof of absence throughout repository.'
    table['classification_counts']=dict(Counter(r['classification'] for r in table['artifacts'] if r['source_filter_included']))
    for k in ['EXACT_HOURLY_STATE_ARTIFACT_CANDIDATE','EXACT_PREDICATE_DEFINITION_AUTHORITY_CANDIDATE','UPSTREAM_PRODUCER_SOURCE_CANDIDATE','UNRESOLVED','IRRELEVANT_TO_TARGET_PREDICATES']: table['classification_counts'].setdefault(k,0)
    assert table['counts']['historical_valid']==22 and table['counts']['ambiguous_membership']==0
    assert set(table['historical_binding']['historical_git_glob_names'])=={r['filename'] for r in table['artifacts'] if r['source_filter_included']}
    emit(GOV/'akah_wc_table.json',table)
    up=read(Path(graph['upstream_authority']['report_path']))
    parent=up['prior_authority']
    next_task='CAUSAL_EXIT_MECHANISM_PROFIT_ARM_COUNTERFACTUAL_EAG_PERSISTENCE_ASYNC_READY_STATE_CONTROL_HOURLY_EVIDENCE_V2_PARENT_PROVENANCE_REBASE_REVIEW_V1'
    gap={'source_sha256':graph['upstream_authority']['report_sha256'],'json_path':'$.prior_authority.prior_report_sha256','target_sha256':parent['prior_report_sha256'],'target_paths':parent['prior_report_paths'],'target_governed_sha256':parent['prior_governed_result_sha256'],'status':'EXPLICIT_PARENT_EDGE_NOT_AUDITED_IN_THIS_TASK','missing_authority':'Parent evidence explaining the canonical control-hourly state/source provenance before the RD04 artifact-location lineage; no direct state producer binding is established.','next_task_scope':'Inspect this exact parent report and its governed structured bindings only; no raw rows or transitive source expansion.'}
    now=datetime.now(timezone.utc).isoformat()
    report={'schema_version':'akah-wildcard-resolution-review-v1','task_id':TASK,'status':'PASS','resolution_class':'WILDCARD_RESOLVED_NO_AUTHORITY_CANDIDATE','task_start_charter_revision':133,'task_start_head':HEAD,'source_binding':table['source_binding'],'counts':table['counts'],'classification_counts':table['classification_counts'],'wildcard_hop_fully_resolved':True,'historical_evidence':table['historical_binding'],'table_path':'governance/akah_wc_table.json','table_sha256':sha((GOV/'akah_wc_table.json').read_bytes()),'all_22_included_sha_previously_audited':True,'direct_authority_path_status':'DIRECT_AUTHORITY_PATH_NOT_EXPOSED','first_remaining_provenance_hop':gap,'next_bottleneck':next_task,'scientific_interpretation':'The glob performs a report-name registration guard. Its 22 historical members are already SHA-bound in the prior governed inventory; none supplies new exact E/A/G/EAG/P authority. The excluded final report is used only as the downstream historical-membership witness.','remaining_steps':'Number unknown; parent provenance resolution and strict canonical authority adjudication remain prerequisites, followed by separately admitted reconstruction.','prior_A_binding_carried_forward':False,'producer_anchor_layer_exhausted':True,'firewall':{'source_mutation':False,'raw_market_rows_read':False,'outcome_values_inspected':False,'market_replay':False,'predicate_adoption':False,'state_reconstruction':False,'transitive_source_expansion':False,'2024_access':False,'2025_access':False,'push':False},'alignment':'ALIGNED','vision_impact':'ADVANCES','north_star_effect':'Closes a provenance ambiguity without creating unsupported predicate authority; preserves the path to valid specificity measurement.','created_at_utc':now}
    emit(GOV/'akah_wc_report.json',report)
    charter_path=GOV/'AKAH_BOT_SYSTEM_CHARTER.json'
    raw=charter_path.read_bytes().decode('utf-8'); c=json.loads(raw)
    assert c['charter_revision']==133 and git('rev-parse','HEAD').decode().strip()==HEAD
    revision=c['charter_revision']+1
    manifest={'schema_version':'akah-wildcard-governed-v1','task_id':TASK,'status':'PASS','task_start_head':HEAD,'old_charter_revision':c['charter_revision'],'new_charter_revision':revision,'report_path':'governance/akah_wc_report.json','report_sha256':sha((GOV/'akah_wc_report.json').read_bytes()),'table_path':report['table_path'],'table_sha256':report['table_sha256'],'executor_sha256':sha(Path(__file__).read_bytes()),'begin_sha256':sha((GOV/'akah_wc_begin.json').read_bytes()),'resolution_class':report['resolution_class'],'next_bottleneck':next_task,'post_closeout_head_semantics':'Reported after commit; no circular self-hash','push':False}
    emit(GOV/'akah_wc_gov.json',manifest)
    event={'event_type':'WILDCARD_RESOLUTION_REVIEW','task_id':TASK,'status':'PASS','outcome':report['resolution_class'],'branch':git('branch','--show-current').decode().strip(),'head':HEAD,'head_semantics':'TASK_START_AUTHORITY_HEAD','report_path':manifest['report_path'],'report_sha256':manifest['report_sha256'],'governed_manifest_path':'governance/akah_wc_gov.json','governed_manifest_sha256':sha((GOV/'akah_wc_gov.json').read_bytes()),'authority_bindings':{'upstream_lineage_sha256':graph['upstream_authority']['report_sha256'],'source_sha256':table['source_binding']['sha256'],'table_sha256':report['table_sha256']},'result':report,'alignment':'ALIGNED','vision_impact':'ADVANCES','summary':report['scientific_interpretation'],'north_star_effect':report['north_star_effect'],'next_bottleneck':next_task,'result_ref':manifest['report_path'],'result_sha256':manifest['report_sha256'],'evidence':[manifest['table_path'],manifest['report_path']],'governance_declarations':report['firewall'],'recorded_at_utc':now}
    state=c['current_state'].copy(); state.update(current_bottleneck=next_task,latest_research_execution_task_id=TASK,latest_research_execution_status='PASS',latest_governance_task_id=TASK,latest_governance_status='PASS',latest_governance_task_status='PASS')
    history=c['recent_execution_history']; history.append(event)
    sync={'sync_task_id':TASK,'status':'PASS_CLOSEOUT_RECORDED','task_start_head':HEAD,'previous_charter_revision':c['charter_revision'],'new_charter_revision':revision,'new_current_bottleneck':next_task,'report_sha256':manifest['report_sha256'],'governed_manifest_sha256':event['governed_manifest_sha256'],'completed_at_utc':now}
    updates={'charter_revision':revision,'current_state':state,'last_updated_at_utc':now,'last_updated_by_task':TASK,'last_execution_event':event,'last_governance_sync':sync}
    # Preserve the huge historical document and its mixed EOL bytes. Replace only root values.
    decoder=json.JSONDecoder(); spans={}; pos=raw.index('{')+1
    while True:
        while raw[pos].isspace() or raw[pos]==',': pos+=1
        if raw[pos]=='}': break
        key,end=decoder.raw_decode(raw,pos); pos=end
        while raw[pos].isspace() or raw[pos]==':':pos+=1
        start=pos; _,end=decoder.raw_decode(raw,pos); spans[key]=(start,end);pos=end
    replacements=[]
    for k,v in updates.items():
        a,b=spans[k];replacements.append((a,b,json.dumps(v,indent=2).replace('\n','\r\n  ')))
    # Append to execution history without reserializing prior events.
    a,b=spans['recent_execution_history'];end=b-1; p=end
    while raw[p-1].isspace():p-=1
    replacements.append((p,p,',\r\n    '+json.dumps(event,indent=2).replace('\n','\r\n    ')))
    for a,b,value in sorted(replacements,reverse=True): raw=raw[:a]+value+raw[b:]
    parsed=json.loads(raw)
    assert parsed['constitutional_core']==c['constitutional_core'] and parsed['recent_execution_history'][-1]==event
    assert len(parsed['recent_execution_history'])==len(c['recent_execution_history'])
    tmp=GOV/'akah_wc_charter.tmp';tmp.write_bytes(raw.encode());tmp.replace(charter_path)
    print(json.dumps({'status':'PASS','resolution':report['resolution_class'],'counts':report['counts'],'classification_counts':table['classification_counts'],'revision':revision,'report_sha256':manifest['report_sha256'],'manifest_sha256':event['governed_manifest_sha256'],'table_sha256':report['table_sha256'],'charter_sha256':sha(charter_path.read_bytes()),'next_bottleneck':next_task},indent=2))

if __name__=='__main__':
    if '--complete' in sys.argv: complete()
    else: audit()
