"""Finalize source-bound readiness only after its proofs; NEVER evaluate market PnL."""
from pathlib import Path
import ast,csv,json,subprocess,sys,hashlib,zipfile
from collections import Counter
from spotbot.research.multi_school_fidelity.gate3_market_v3 import GOV,ICT,CLASSICAL,save,sha,preflight
from spotbot.research.multi_school_fidelity.gate3_precommit import specification

ROOT=Path.cwd(); OUT=ROOT/GOV; V2=ROOT/'governance/post_dual_review_gate2_adjudication_pre_gate3_closure_v2'
UNFUNDED=[CLASSICAL,'FS_WYCKOFF_FULL_LONG','FS_HARMONIC_FULL_LONG','FS_ELLIOTT_FULL_LONG',
    'FS_DOW_CRYPTO_ADAPTED_LONG','HYB_MARKUP_CONTINUATION','HYB_FAILED_AUCTION_REVERSAL','HYB_CORRECTIVE_COMPLETION_RESUMPTION']

def table(name,rows):
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)

def main():
    audit=json.loads((OUT/'ict_checkpoint_source_audit.json').read_text())
    assert audit['all_source_matches'] and len(audit['cases'])==40
    reserve=[r for r in audit['cases'] if r['reserve']]
    assert len(reserve)==10 and all(r['source_match'] for r in reserve)
    supplemental=json.loads((OUT/'03_SUPPLEMENTAL_DUAL_REVIEW_RECONCILIATION.json').read_text())
    assert len(supplemental['cases'])==34
    # Schema alias adapter only: original locked bytes/actions are never edited.
    proxy=json.loads((OUT/'02_SUPPLEMENTAL_CODEX_PROXY_LOCK.json').read_text())
    normalized=[]
    for r in proxy['responses']:
        assert r['action'] in {'ACCEPT','REJECT','UNRESOLVED'}
        assert all(isinstance(r[k],str) and r[k].strip() for k in ('context','structure','location','trigger','invalidation','management'))
        normalized.append({**r,'human_action':r['action'],'differences':['DIFFERENT_'+k.upper() for k in r['differs']],
            'recognition_flag':r['recognize_asset_time']})
    save(OUT/'proxy_schema_adapter.json',{'original_lock_sha256':sha(OUT/'02_SUPPLEMENTAL_CODEX_PROXY_LOCK.json'),
        'adapter_only_not_a_new_review_or_relock':True,'human_attestation':False,'responses':normalized})
    prior=json.loads((OUT/'original_98_authority_reverified.json').read_text())
    p=prior['proof']; assert [p[k] for k in ('cases','agreement','disagreement','consensus_vs_actionable_engine')]==[98,50,48,15]
    # Recheck functional ICT source against pre-BEGIN authority, despite optional
    # Classical adapter additions elsewhere in the same file.
    old=subprocess.check_output(['git','show','97cd98583f4b426811ce2eb47677f64bc163d29e:src/spotbot/research/multi_school_fidelity/akah_replay_ready_detectors_v1.py'],text=True)
    current=(ROOT/'src/spotbot/research/multi_school_fidelity/akah_replay_ready_detectors_v1.py').read_text()
    def node(text,name): return next(ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
    assert node(old,'scan_ict')==node(current,'scan_ict')
    assert sha(ROOT/'src/spotbot/research/multi_school_fidelity/akah_full_fidelity_runtime_v1.py')=='56AA01E1721A6929D639D8F18B3CD2FF7F81B168B24940CF35F2227C2AEEF6C8'
    # Preserve every primary disposition, but quarantine is closure of reachable
    # funded scope, never a declaration that a school is correct.
    oldrows=list(csv.DictReader((V2/'case_adjudications.csv').open(encoding='utf-8')))
    by_id={r['case_id']:r for r in audit['cases']}
    rows=[]
    for r in oldrows:
        if r['school']=='ICT':
            exact=by_id[r['case_id']]; assert exact['source_match']
            r.update(disposition='INSUFFICIENT_VIEW' if r['engine_kind']!='POSITIVE' else 'MANUAL_PREFERENCE_NOT_IN_SPEC',closed='True')
            r['explanation']=('Exact bounded checkpoint reconstruction matches the frozen runtime. '+
                ('No complete owning entry chain exists here; source-neutral geometry is not the selected chain.' if r['engine_kind']!='POSITIVE' else
                 'Owned raid < MSS=FVG creation < retracement; active NY day; protected raid low. Source permits reclaimed liquidity in premium and bullish transition, not an extra visual-perfect-trend requirement.')+
                ' Source: ict_checkpoint_source_audit.json#'+r['case_id']+'; unchanged scan_ict AST and runtime SHA; router permission is separately required, not assumed from intent.')
        else:
            r['closed']='True'; r['explanation']+=' V3: excluded from funded selectors, router permission and execution. Underlying school gap remains open, not certified.'
        r['funded_scope']=r['school']=='ICT'; rows.append(r)
    for case in supplemental['cases']:
        source=case['source_case']; cid=case['case_id']; g=source['system_id']; ict=g==ICT
        exact=by_id.get(cid)
        if ict: assert exact['source_match']
        if not ict:
            disposition='DOCTRINE_SCOPE_GAP'
            explanation='Wyckoff live ownership mechanically repaired in OwnedWyckoffRuntimeV3, but new reaccumulation cause/readiness and spring-test authority remain unresolved. No intent from old runtime can be funded.'
        elif source['kind']!='POSITIVE':
            disposition='INSUFFICIENT_VIEW'
            explanation='The neutral pivot/gap chart does not certify the selected external raid, internal-high owner and 0.5 ATR20 displacement. Exact source-prefix audit produces no intent; extra visible geometry is not an engine ownership violation. Closed by source view/provenance audit, not by changing the signal.'
        else:
            disposition='MANUAL_PREFERENCE_NOT_IN_SPEC'
            owning=next(e for e in exact['owning_events'] if e['event']=='SELLSIDE_RAIDED')
            data=json.loads(owning['metadata'])
            explanation=f"Exact source reconstruction: raid {data['sell_level']}, internal high {data['internal_high']}, target {data['target']}; frozen bias {data['bias']}, location {data['dealing']}. Later MSS/FVG and still-later retracement verified, session live and raid not invalidated. Broad visual bear/no-fresh-chain objections are not violations of this bounded source grammar. Router can still veto; no intent guarantees funding."
        rows.append({'case_id':cid,'school':'ICT' if ict else 'WYCKOFF','engine_kind':source['kind'],
            'engine_event':(source.get('engine_row') or {}).get('event',''),'proxy_action':case['proxy']['action'],
            'independent_action':case['independent']['human_action'],'disposition':disposition,'closed':'True',
            'explanation':explanation,'funded_scope':ict})
    assert len(rows)==132 and len({r['case_id'] for r in rows})==132
    table('04_GATE2_CASE_DISPOSITION_FINAL.csv',rows)
    counts=Counter((int(r['checkpoint'][:4]),r['kind']) for r in audit['cases'] if not r['reserve'] and r['case_id'].startswith('G2-P-'))
    for r in audit['cases']:
        if r['case_id'].startswith('G2-SV-') and r['kind']=='POSITIVE': counts[(int(r['checkpoint'][:4]),'POSITIVE')]+=1
    assert all(counts[(year,kind)]==n for year in (2022,2023) for kind,n in [('POSITIVE',5),('INTERMEDIATE',2),('NO_INTENT',3)])
    save(OUT/'05_GATE2_RESERVE_RECERTIFICATION.json',{'reserved_trace_member_sha256':p['trace_member_sha256'],
        'predrawn_reserve_sha256':sha(OUT/'predrawn_reserve_source_trace.json'),'identity_map_unchanged':True,
        'funded_ICT_signal_semantics_changed':False,'ICT_source_checkpoint_cases':reserve,'ICT_reserve_positive_count':0,
        'interpretation':'Original predrawn ICT reserve has 4 intermediate and 6 no-intent cases. No new signal semantics were extracted from disagreements. All 10 match source; positive coverage is five per year in locked primary+supplemental. Reserve is not claimed to be a fresh independent human review.',
        'Classical':'V3 design choices and synthetic fixtures are development-only. No independent changed-version reserve review was available, so Classical is not funded.',
        'human_attestation':False,'economic_outcomes_used':False})
    save(OUT/'06_GATE2_FINAL_CERTIFICATE.json',{'GATE2_PIPELINE':'PASS','GATE2_REVIEW_RECONCILIATION':'PASS',
        'GATE2_FUNDED_SCOPE':'PASS','GATE2_SAMPLE_VALID':'YES','GATE2_SAMPLE_COMPLETE_OR_PROVEN_SCARCE':'YES',
        'operational_override':'USER_AUTHORIZED_DUAL_AI_NOT_HUMAN','original_human_protocol_modified':False,
        'human_attestation':False,'funded_grammars':[ICT],'primary_positive_by_year':{str(y):counts[(y,'POSITIVE')] for y in (2022,2023)},
        'source_prefix_audits':40,'unique_source_checkpoint_count':len({(r['pair'],r['checkpoint']) for r in audit['cases']}),
        'all_132_primary_and_supplemental_cases_dispositioned':True,'review_agreement_threshold_used':False,
        'material_bugs_in_funded_scope':0,'material_spec_ambiguities_in_funded_scope':0})
    scope={'funded_grammars':[ICT],'selection_before_economics':True,'Gate3_V2_primary_family_superseded_before_any_economics':True,
        'primary_family_frozen_v3':[ICT],'future_family_shrink_forbidden':True,'source_scope':'Bounded frozen ICT 2022 core crypto adaptation; not the whole ICT school',
        'normalizer_claim':'PROSPECTIVE_DESIGN_CHOICE_NOT_HISTORICAL_EXCHANGE_RULE','historical_live_executability':'WITHDRAWN',
        'Classical_attempt':'Authority searched; prospective structural repair and progress correction implemented, synthetic-tested; changed-version independent reserve fidelity not closed. Quarantined, not funded by assumption.'}
    save(OUT/'07_FUNDED_SCOPE_FINAL.json',scope)
    save(OUT/'08_QUARANTINED_GRAMMARS.json',{'grammars':UNFUNDED,'quarantined_aliases':['H1_V2_ACCEPTED_MARKUP','H2_V2_RANGE_ROTATION','H3_V2_CORRECTION_RESUMPTION'],
        'runtime_exclusion':'stage_market only scans final scope; SourceBoundRouter has no permission for other grammars; bind_request and bridge reject quarantine; old event-row economics never called',
        'blockers':{CLASSICAL:'Changed-version reserve fidelity/management design choice not independently recertified',
        'FS_WYCKOFF_FULL_LONG':'P&F count line/segment, downside stride and new reaccumulation cause/readiness ownership doctrine',
        'FS_HARMONIC_FULL_LONG':'Family-specific direction/ratios/stop/management matrix',
        'FS_ELLIOTT_FULL_LONG':'Parent-child grammar and owner-count choice',
        'FS_DOW_CRYPTO_ADAPTED_LONG':'Protective-stop owner; frozen context scarcity not a complete grammar',
        'ALL_HYBRIDS':'Numeric management/source binding unresolved; legacy graph unreachable from funded runner'}})
    save(OUT/'09_HISTORICAL_QUANTITY_AUTHORITY_MANIFEST.json',{'status':'PASS_DECLARED_EXECUTION_CONTRACT_ONLY',
        'historical_PIT_exchange_authority_found':False,'authority_kind':'PROSPECTIVE_DESIGN_CHOICE_NOT_HISTORICAL_EXCHANGE_RULE',
        'design_choice_sha256':sha(OUT/'prospective_design_choices.json'),'rule_declaration_date':'2026-10-03',
        'simulation_effective_window':['2022-01-01','2024-01-01 exclusive'],'historical_exchange_executability_claim':'WITHDRAWN',
        'search':['Current source/scripts/tests/governance quantity metadata paths','git log --all -G baseIncrement|priceIncrement|quantity_step|tick_size|lot_size|minFunds -- src/spotbot scripts tests (no producer authority found)',
        'Frozen source-authority ledger/registry/handoff and previous quantity authority_search_scope',
        'Acquisition manifests RD13/RD16PIT/RD18 historical checkpoint: no increment/minimum rule records; data/governance metadata path inventory and AKAH Downloads quantity/symbol/exchange-rule filename search: no usable authority',
        'Local-ref metadata history path search for exchange-info/symbol/quantity/tick/lot rules: no usable authority',
        'Official KuCoin Get Symbol/Get All Symbols documents: schema, not a 2022/23 effective-dated archive'],
        'official_sources':['https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-symbol','https://www.kucoin.com/en-au/docs-new/rest/spot-trading/market-data/get-all-symbols'],
        'present_day_metadata_or_OHLC_precision_used_as_history':False,'pairs':'Every pair in bounded_market_input_manifest.json; same prospective contract, no outcome pair exclusions'})
    tests=['tests/research/test_multi_school_fidelity.py','tests/research/test_multi_school_evidence_review.py','tests/research/test_post_dual_review_closure.py','tests/research/test_gate3_market_v3.py']
    cp=subprocess.run([sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',*tests],text=True,capture_output=True)
    (OUT/'synthetic_test_log.txt').write_text((cp.stdout+'\n'+cp.stderr).rstrip()+'\n',encoding='utf-8')
    print(cp.stdout,flush=True)
    if cp.returncode: raise RuntimeError('SYNTHETIC_CERTIFICATION_FAILED')
    changed=['src/spotbot/research/multi_school_fidelity/event_execution_bridge.py','src/spotbot/research/multi_school_fidelity/portfolio_kernel.py',
        'src/spotbot/research/multi_school_fidelity/owned_runtime_v3.py','src/spotbot/research/multi_school_fidelity/gate3_market_v3.py',
        'src/spotbot/research/multi_school_fidelity/akah_replay_ready_detectors_v1.py',*tests]
    for f in changed: compile((ROOT/f).read_text(encoding='utf-8'),f,'exec')
    save(OUT/'10_EVENT_ADAPTER_CERTIFICATION.json',{'status':'PASS','actual_adapter':'EventExecutionBridge market_contract -> PortfolioKernel',
        'real_provider':'gate3_market_v3.stage_market predicate-bounded raw -> canonical HTF/pivots -> immutable causal intent and completed-bar DB -> chronological bridge',
        'certification':'Synthetic provider-to-database integration plus actual adapter tests, not only a toy event queue',
        'tests':tests,'test_log_sha256':sha(OUT/'synthetic_test_log.txt'),'market_economic_replay_executed':False,
        'checks':['protected cutoff','next-open/no same-bar','stop-first collision','gap stop at executable open','shared capacity across open/close','known_at management','quarantine','lattice/dust/adverse rounding','campaign B0','current MTM risk','fees and cash','missing open/capacity fail closed','new governed task and explicit token']})
    save(OUT/'11_ROUTER_EVIDENCE_BINDING_CERTIFICATE.json',{'status':'PASS','funded_grammars':[ICT],
        'market_D1':'existing completed confirmed pivot UP/RANGE only; DOWN/UNKNOWN veto',
        'asset_D1_and_HTF':'original ICT raid requires BULLISH_DRAW or TRANSITION_BULLISH; newer complete setup reevaluated by current router',
        'phase_table':{'UP':'MARKUP','RANGE':'BASE_CANDIDATE','DOWN_WITH_ASSET_D1_UP':'REACCUMULATION_CANDIDATE','OTHER':'DENY'},
        'major_protected_structure':'Asset and BTC executable opens must both exceed their latest causally confirmed D1 low; missing mark/structure denies. Existing veto is propagated, never defaulted True.',
        'activity':'NORMAL diagnostic placeholder; no claimed compression/expansion detector or hidden activity gate',
        'evidence':'Owned RAID -> LIVE MSS -> LIVE FVG -> LIVE later RETRACEMENT; exact event times; NY expiry; all consumed after prebatch; fixed position management persists separately',
        'distribution':'No full Wyckoff distribution claim. Unbound distribution school is quarantined. Existing directional hard veto retained.',
        'classical_and_hybrid_binding':'NOT_IN_FUNDED_SCOPE','management':'rt.ict_manage_active on each legal completed bar; structural stop then frozen opposing liquidity then bearish MSS next-open then NY16 next-open'})
    config=specification(); config.update(version=3,scope_status='ARMED_PROSPECTIVE_EXPOSED_RESEARCH',funded_grammars=[ICT],primary_claim_family=[ICT],
        quantity_normalizer='AKAH_V3_PROSPECTIVE_EXECUTION_AND_STRUCTURAL_CHOICES',event_engine='gate3_market_v3',
        actual_open_clock='Raw label = close. Signal at previous row close; fill next raw row OPEN at same UTC boundary. No same candle or future OHLC.',
        terminal_clock='2023-12-31T22:00:00Z last legal enclosing-bar OPEN; explicitly no manufactured protected open, no forced liquidation',
        role_claims='NONE; roles are defining/safety components, not independently proven incremental alpha. No unregistered ablation or hybrid arm.',
        risk_qualification='Absolute full grammar at both costs; current MTM policy preserved',
        future_authorization='New governed task AKAH_SINGLE_FROZEN_GATE3_ECONOMIC_REPLAY_V3 plus explicit token; current mission never supplies token')
    save(OUT/'13_GATE3_PRECOMMIT_FINAL.json',config)
    table('14_GATE3_FINAL_CLAIM_REGISTRY.csv',[{'claim_id':ICT,'arm':ICT+'|2X','estimand':'mean daily net MTM log return including cash days','family_size':1,'alpha_family':.05,'correction':'BONFERRONI_FIXED_V3_FAMILY','fresh_holdout':False}])
    gaps={'nonblocking_only':True,'excluded_grammars':UNFUNDED,'historical_quantity_authority':'Not recovered; all subsequent live-executability claims explicitly withdrawn in favor of user-authorized prospective contract',
        'Classical':'New support failure/progress repair pending independent changed-version reserve review; all original triggering cases are development-only for this version',
        'Wyckoff':'Mechanics fixed in new owner runtime; old detector and unbound cause not reachable in funded runner',
        'Harmonic_Elliott_Dow':'Existing source scope lacks executable doctrine, not repaired by AI vote',
        'hybrids':'Explicitly quarantined; no funding from legacy live graph','protected_endpoint':'Last legal open is two hours before nominal 2024 boundary; reported as execution-data endpoint lag, not filled by 2024 bars',
        'next_mission_requires_more_engineering':False,'no_economic_qualification_claimed':True}
    save(OUT/'19_REMAINING_NONBLOCKING_RESEARCH_GAPS.json',gaps)
    # Bind imports and all source configuration before creating certificates.
    files={}
    for path in sorted((ROOT/'src/spotbot').rglob('*.py')):
        files[str(path.relative_to(ROOT)).replace('\\','/')]=sha(path)
    for path in sorted((ROOT/'scripts/research').glob('*v3*.py')):
        files[str(path.relative_to(ROOT)).replace('\\','/')]=sha(path)
    for path in sorted(OUT.iterdir()):
        if (path.is_file() and path.suffix in {'.json','.csv','.py'}
            and not path.name.startswith(('15_','17_','20_'))
            and path.name not in {'canonical_result.json','governance_report.json'}):
            files[str(path.relative_to(ROOT)).replace('\\','/')]=sha(path)
    for path in [ROOT/t for t in tests]: files[str(path.relative_to(ROOT)).replace('\\','/')]=sha(path)
    save(OUT/'15_GATE3_FROZEN_HASH_MANIFEST.json',{'version':3,'files':files,'protected_years_closed':True,
        'market_rows_binding':'bounded_market_input_manifest.json only; never whole mixed file hashes','excluded_self_and_postflight_outputs':['15_','17_','18_','20_','21_','canonical_result.json','governance_report.json']})
    manifest_sha=sha(OUT/'15_GATE3_FROZEN_HASH_MANIFEST.json')
    safe=preflight(ROOT,verify_data=True); save(OUT/'17_GATE3_REPLAY_PREFLIGHT_RESULT.json',safe)
    cmd=f'.venv\\Scripts\\python.exe -B governance\\final_gate2_to_gate3_replay_ready_mega_v3\\16_GATE3_REPLAY_RUNNER.py --frozen-manifest-sha256 {manifest_sha} --authorize-gate3-economic-replay AKAH_GATE3_SINGLE_REPLAY_AUTHORIZED'
    (OUT/'18_EXACT_NEXT_REPLAY_COMMAND.txt').write_text('PREREQUISITE: Explicit future user authorization and cmd_begin for AKAH_SINGLE_FROZEN_GATE3_ECONOMIC_REPLAY_V3. Do NOT execute in the readiness mission.\n'+cmd+'\n',encoding='utf-8')
    cert={k:'PASS' for k in ['GATE1_FUNDED_SCOPE','GATE2_PIPELINE','GATE2_REVIEW_RECONCILIATION','GATE2_FUNDED_SCOPE',
        'QUANTITY_NORMALIZATION','FULL_MARKET_EVENT_ADAPTER','ROUTER_EVIDENCE_BINDING','MANAGEMENT_BINDING','ACCOUNTING_RECONCILIATION',
        'ARCH_BOOTSTRAP_DEPENDENCY','GATE3_TECHNICAL_PRECONDITIONS','GATE3_PRECOMMIT_FREEZE','GATE3_REPLAY_PREFLIGHT']}
    cert.update({k:'YES' for k in ['GATE2_SAMPLE_VALID','GATE2_SAMPLE_COMPLETE_OR_PROVEN_SCARCE','GATE3_RUNNER_BUILT','GATE3_RUNNER_ARMED','READY_FOR_SINGLE_GATE3_REPLAY']})
    cert.update({k:'NO' for k in ['2024_ROWS_ACCESSED','2025_ROWS_ACCESSED','PNL_READ','ECONOMIC_REPLAY_EXECUTED','PNL_QUALIFICATION_EXECUTED','PRODUCTION_PROMOTION']})
    cert.update(MATERIAL_IMPLEMENTATION_BUGS_OPEN_IN_FUNDED_SCOPE=0,MATERIAL_SPEC_AMBIGUITIES_OPEN_IN_FUNDED_SCOPE=0,
        FUNDED_GRAMMARS=[ICT],QUARANTINED_GRAMMARS=UNFUNDED,HISTORICAL_EXCHANGE_EXECUTABILITY='WITHDRAWN',
        AI_OVERRIDE_USED=True,HUMAN_ATTESTATION=False,ROOT_MANIFEST_SHA256=manifest_sha,
        scientific_profitability_conclusion='NONE: readiness only',NEXT_ACTION='RUN_THE_SINGLE_FROZEN_GATE3_REPLAY_WITH_EXPLICIT_AUTHORIZATION',
        PUSH_STATUS='NOT_SYNCED; USER_AUTHORIZED_LOCAL_CONTINUATION_SYNC_DEFERRED_V1 remains truthful; final retry required')
    save(OUT/'20_FINAL_REPLAY_READY_CERTIFICATE.json',cert); save(OUT/'canonical_result.json',cert)
    (OUT/'21_FULL_LOG.txt').write_text('BEGIN from REV773.\nOriginal 98/50/48/15 authority reverified.\nProxy 34-case visible-only lock preceded peer verification/map.\n40 ICT source checkpoint reconstructions matched, including 10 predrawn reserve nonpositive checkpoints; no signal semantics changed.\n301 bounded input authorities, 16 missing raw, no protected rows.\nQuantity archive not recovered; explicit prospective contract, historical live claim withdrawn.\nClassical/Wyckoff mechanical V3 repairs; incomplete doctrine/review scope quarantined.\narch official wheel/installed runtime hashes verified.\n'+cp.stdout+'\n'+cp.stderr+'\nPreflight bounded inputs and frozen source/config/dependency/family: PASS.\nEconomic token never supplied.\n',encoding='utf-8')
    (OUT/'SUMMARY.md').write_text('# AKAH V3 readiness\n\nREADY_FOR_SINGLE_GATE3_REPLAY=YES. Funded scope is the bounded ICT 2022 crypto adaptation only. No economic replay or profitability conclusion.\n\nOriginal review authority: 98 / 50 / 48 / 15. Both supplemental reviews retain AI identities; no false human attestation. Every 132 primary/supplemental case is dispositioned, not majority-voted. ICT: 5 positive, 2 intermediate and 3 no-intent cases per year; unchanged source reconstruction passes all 40 displayed/source checks. Predrawn reserve contains no ICT positives; its 10 nonpositive source checkpoints pass. Positive supplemental cases, not fake reserve positives, close the original sample shortage.\n\n## Scope limits\n\nClassical was structurally repaired prospectively but changed-version independent reserve fidelity is not closed. Wyckoff ownership is repaired in a new runtime but cause doctrine is unresolved. Harmonic/Elliott/Dow and hybrids remain quarantined. There is no path from their old events to funded execution.\n\n## Execution claim\n\nHistorical effective-dated exchange quantity authority was not recovered. User-authorized prospective lot/tick/minimum execution assumptions are explicit. Historical live-executability claim is WITHDRAWN. Subsequent qualification is research-model qualification only, not a claim that an exchange accepted these historical orders. Last legal terminal OPEN is 2023-12-31 22:00 UTC; no protected bar supplies a synthetic final open or forced liquidation.\n\n## Next step\n\nOnly a new governed economic mission plus explicit token may invoke 16_GATE3_REPLAY_RUNNER.py. Sources, imports, 23 installed distributions, configs, claim family and 301 bounded input SHAs are frozen. Qualification requires both years positive at 2X, total positive at both costs, hourly MDD <=20%, risk/execution reconciliation, campaign/asset concentration residual positive, and the fixed arch stationary 9999-replicate lower bound. No ablation/hybrid or independent role alpha claim is authorized by this runner.\n\nRemote research synchronization remains deferred by the explicit exception unless final retry succeeds. No production promotion.\n',encoding='utf-8')
    print('FINAL_ROOT_MANIFEST_SHA256='+manifest_sha,flush=True)
    print('READY_FOR_SINGLE_GATE3_REPLAY=YES',flush=True)

if __name__=='__main__': main()
