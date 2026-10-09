from pathlib import Path
import json
from decimal import Decimal
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as rt
from spotbot.research.multi_school_fidelity.owned_runtime_v3 import OwnedWyckoffRuntimeV3,ClassicalRuntimeV3,classical_manage_v3
from spotbot.research.multi_school_fidelity.gate3_market_v3 import quantity_rules,bind_request,router_state,run_market,ICT,CLASSICAL,campaign_attribution
from spotbot.research.multi_school_fidelity.event_execution_bridge import EventExecutionBridge,CompletedBar
from spotbot.research.multi_school_fidelity.evidence_selector import EvidenceStore
from spotbot.research.multi_school_fidelity.portfolio_kernel import PortfolioKernel
from spotbot.research.multi_school_fidelity.source_router import SourceBoundRouter,GrammarPermission
from spotbot.research.multi_school_fidelity.akah_thesis_engine_foundation_v1 import StructuralPhase,RouterState,Direction,Activity
from spotbot.research.multi_school_fidelity.qualification_uncertainty import evaluate_calendar_claims

T=pd.Timestamp('2023-01-03T15:00:00Z')
STATE=RouterState(Direction.UP,Direction.UP,StructuralPhase.MARKUP,Activity.NORMAL)

def router(): return SourceBoundRouter((GrammarPermission(ICT,frozenset({StructuralPhase.MARKUP}), 'sha',True,True),))
def event():
    return {'timestamp':str(T),'pair':'TEST-USDT','system_id':ICT,'event':'FVG','metadata':json.dumps({
        'raid_time':str(T-pd.Timedelta(hours=3)), 'mss_time':str(T-pd.Timedelta(hours=2)),
        'fvg_created_at':str(T-pd.Timedelta(hours=2)),'retrace_time':str(T),'stop':90,'target':120})}
def real_fixture():
    k=PortfolioKernel(100000,{}, {},.00125); e=EvidenceStore(); rules=quantity_rules(['TEST-USDT'],'design-choice-hash')
    b=EventExecutionBridge(k,e,rules,synthetic_fixture=False,
        market_contract={'source_hash_verified':True,'funded_grammars':[ICT]})
    req,why=bind_request(event(),e,STATE,router(),T,20000,'sha',[ICT])
    assert why=='BOUND_COMPLETE_THESIS'
    assert b.on_open(T,{'TEST-USDT':100},{'TEST-USDT':20000},[req])=={}
    return k,e,b,req

def test_real_bridge_binds_source_graph_fees_risk_and_campaign():
    k,e,b,req=real_fixture()
    assert len(k.positions)==1 and k.fills[0]['side']=='BUY'
    b.on_close(T+pd.Timedelta(hours=1),{'TEST-USDT':CompletedBar('TEST-USDT',T,T+pd.Timedelta(hours=1),100,130,80,110)},
        {req[1]['identity']:{'known_at':T+pd.Timedelta(hours=1)}})
    assert not k.positions and k.fills[-1]['reason']=='STRUCTURAL_STOP'
    assert k.cash==pytest.approx(100000+sum(f['cash_delta'] for f in k.fills))
    campaigns,assets=campaign_attribution(k,{})
    assert sum(assets.values())==pytest.approx(k.cash-100000)
    assert len(campaigns)==1

@pytest.mark.parametrize('bad',['same_bar','wrong_owner','future','quarantined'])
def test_invalid_requests_and_unfunded_graph_cannot_fill(bad):
    e=event(); store=EvidenceStore()
    if bad=='same_bar':
        m=json.loads(e['metadata']); m['fvg_created_at']=str(T); m['mss_time']=str(T); e['metadata']=json.dumps(m)
    if bad=='future': e['timestamp']=str(T+pd.Timedelta(hours=1))
    if bad=='quarantined': e['system_id']='FS_WYCKOFF_FULL_LONG'
    if bad=='wrong_owner':
        m=json.loads(e['metadata']); m['raid_time']=None; e['metadata']=json.dumps(m)
    with pytest.raises((ValueError,TypeError,KeyError)):
        bind_request(e,store,STATE,router(),T,1000,'sha',[ICT])

def test_open_unknown_missing_capacity_and_gap_are_not_fake_fills():
    k,e,b,req=real_fixture()
    b.on_close(T+pd.Timedelta(hours=1),{'TEST-USDT':CompletedBar('TEST-USDT',T,T+pd.Timedelta(hours=1),100,105,95,101)},
        {req[1]['identity']:{'known_at':T+pd.Timedelta(hours=1)}})
    with pytest.raises(ValueError,match='MISSING_POSITION_OPEN'): b.on_open(T+pd.Timedelta(hours=1),{}, {})
    assert len(k.positions)==1
    k,e,b,req=real_fixture()
    b.on_close(T+pd.Timedelta(hours=1),{'TEST-USDT':CompletedBar('TEST-USDT',T,T+pd.Timedelta(hours=1),100,105,95,101)},
        {req[1]['identity']:{'known_at':T+pd.Timedelta(hours=1)}})
    with pytest.raises(ValueError,match='RISK_BREACH_UNRESOLVED'):
        b.on_open(T+pd.Timedelta(hours=1),{'TEST-USDT':80},{'TEST-USDT':None})
    assert len(k.positions)==1
    k,e,b,req=real_fixture()
    b.on_close(T+pd.Timedelta(hours=1),{'TEST-USDT':CompletedBar('TEST-USDT',T,T+pd.Timedelta(hours=1),100,105,95,101)},
        {req[1]['identity']:{'known_at':T+pd.Timedelta(hours=1)}})
    b.on_open(T+pd.Timedelta(hours=1),{'TEST-USDT':80},{'TEST-USDT':20000})
    assert k.fills[-1]['price']==80 and not k.positions

def test_close_actions_execute_next_open_not_earlier():
    k,e,b,req=real_fixture(); close=T+pd.Timedelta(hours=1)
    b.on_close(close,{'TEST-USDT':CompletedBar('TEST-USDT',T,close,100,105,95,101)},
        {req[1]['identity']:{'known_at':close,'bearish_mss':True}})
    assert len(k.positions)==1
    b.on_open(close,{'TEST-USDT':102},{'TEST-USDT':20000})
    assert not k.positions and k.fills[-1]['price']==102

def test_shared_capacity_is_not_reset_between_open_and_close():
    k,e,b,req=real_fixture(); remaining=b.capacity_remaining['TEST-USDT']
    assert remaining<20000
    b.capacity_remaining['TEST-USDT']=1
    b.on_close(T+pd.Timedelta(hours=1),{'TEST-USDT':CompletedBar('TEST-USDT',T,T+pd.Timedelta(hours=1),100,105,80,85)},
        {req[1]['identity']:{'known_at':T+pd.Timedelta(hours=1),'exit_capacity':999999}})
    assert k.positions and k.risk_breach_unresolved

def test_lattice_rounds_down_and_design_choice_does_not_claim_history():
    r=quantity_rules(['X'],'sha')['X']
    assert r.authority_kind=='PROSPECTIVE_DESIGN_CHOICE_NOT_HISTORICAL_EXCHANGE_RULE'
    assert r.normalize('X',1.123456789,100,T)<=1.123456789
    assert r.normalize('X',.01,100,T)==0
    assert r.normalize_exit('X',.01,100,T)==pytest.approx(.01)
    assert r.price(100.123456789,buy=True)>=100.123456789
    assert r.price(100.123456789,buy=False)<=100.123456789
    assert r.normalize('X',1,100,pd.Timestamp('2024-01-01T00:00:00Z'))==0

def test_common_lattice_lambda_and_safety_accounting():
    positions={i:{'episode':{'pair':pair,'identity':pair},'qty_current':q,'current_stop':90,'campaign_id':pair}
        for i,(pair,q) in enumerate([('X',800.),('Y',900.)],1)}
    k=PortfolioKernel(10000,positions,{},.00125); rules=quantity_rules(['X','Y'],'sha')
    def norm(p,q,price,t): return rules[p].normalize_exit(p,q,price,t)
    norm.quantity_rules=rules
    assert k.reduce_common(lambda *a:100,T,{'X':1e5,'Y':1e5},norm)
    assert k.positions[1]['qty_current']/800==pytest.approx(k.positions[2]['qty_current']/900)
    assert len(k.fills)==2 and k.cash==pytest.approx(10000+sum(f['cash_delta'] for f in k.fills))

def test_classical_absorbing_support_failure_and_progress_not_price_level():
    p=rt.ClassicalPattern('p','RECTANGLE',100,90,20,'UP',T)
    c=ClassicalRuntimeV3('X'); c.mature(p); assert c.update_breakout(T,'p',101,10,10)
    assert c.entry_intent(T+pd.Timedelta(hours=4),'p',89,101) is None
    assert c.entry_intent(T+pd.Timedelta(hours=8),'p',99,101) is None
    c=ClassicalRuntimeV3('X'); c.mature(p); c.update_breakout(T,'p',101,10,10)
    assert c.entry_intent(T+pd.Timedelta(hours=4),'p',99,101) is not None
    base=dict(entry_price=100,target=120,current_stop=90,confirmed_higher_low=98,primary_trend='UP',pattern_failed=False)
    assert classical_manage_v3(price=101,**base)['stop']==90
    assert classical_manage_v3(price=115,**base)['stop']==98

def test_wyckoff_ownership_reaccumulation_is_new_cause_no_resurrection():
    w=OwnedWyckoffRuntimeV3('X',state='D_DEMAND_DOMINANT',context={'cause_id':'accum','sc':{'low':80},'sc_time':T,'ar':{'high':100},'st':{'low':90}})
    w.step(T,'LPS_HOLDS',{'low':90})
    kw=dict(branch='NO_SPRING_LPS',market_state='E_MARKUP',rs={'eligible':True},readiness={'x':True},entry=100,structural_low=90,pnf_objective=140)
    assert w.entry_intent(T,**kw) is not None
    assert w.entry_intent(T+pd.Timedelta(hours=4),**kw) is None
    w.step(T+pd.Timedelta(hours=4),'HIGHER_LEVEL_RANGE_FORMS',{'low':95,'high':110})
    assert 'sc' not in w.context and 'sc' in w.context['historical_parent']
    assert w.context['cause_id']!='accum' and not w.context['cause_doctrine_bound']
    w.step(T+pd.Timedelta(hours=8),'REACCUMULATION_SOS_LPS',{'low':95})
    assert w.entry_intent(T+pd.Timedelta(hours=8),**{**kw,'structural_low':95}) is None

def test_router_uses_completed_asof_not_future_and_quarantine_has_no_permission():
    series=([T,T+pd.Timedelta(days=1)],['UP','DOWN'],[])
    s=router_state(series,series,series,T)
    assert s.market_direction_1d==Direction.UP and s.structural_phase_4h==StructuralPhase.MARKUP
    assert not router().permission(CLASSICAL,s)[0]
    assert not router().permission(ICT,replace(s,market_direction_1d=Direction.UNKNOWN))[0]
    assert not s.data_authority_valid
    low=rt.Pivot('L',0,90,T-pd.Timedelta(hours=2),T,1,1)
    protected_series=([T],['UP'],[low])
    live=router_state(protected_series,protected_series,protected_series,T,asset_mark=100,market_mark=100)
    assert router().permission(ICT,live)[0]
    failed=router_state(protected_series,protected_series,protected_series,T,asset_mark=89,market_mark=100)
    assert not router().permission(ICT,failed)[0]

@pytest.mark.parametrize('grammar',[CLASSICAL,'FS_WYCKOFF_FULL_LONG','FS_HARMONIC_FULL_LONG',
    'FS_ELLIOTT_FULL_LONG','FS_DOW_CRYPTO_ADAPTED_LONG','HYB_MARKUP_CONTINUATION',
    'HYB_FAILED_AUCTION_REVERSAL','HYB_CORRECTIVE_COMPLETION_RESUMPTION',
    'H1_V2_ACCEPTED_MARKUP','H2_V2_RANGE_ROTATION','H3_V2_CORRECTION_RESUMPTION'])
def test_every_quarantined_grammar_and_alias_unreachable(grammar):
    assert not router().permission(grammar,STATE)[0]
    wrong=event(); wrong['system_id']=grammar
    with pytest.raises(ValueError,match='QUARANTINED'):
        bind_request(wrong,EvidenceStore(),STATE,router(),T,20000,'sha',[ICT])
    store=EvidenceStore(); req,_=bind_request(event(),store,STATE,router(),T,20000,'sha',[ICT])
    bad=replace(req[0],thesis=replace(req[0].thesis,owner_grammar=grammar))
    row={**req[1],'owner_grammar':grammar}
    k=PortfolioKernel(100000,{}, {},.00125)
    b=EventExecutionBridge(k,store,quantity_rules(['TEST-USDT'],'sha'),synthetic_fixture=False,
        market_contract={'source_hash_verified':True,'funded_grammars':[ICT]})
    rejects=b.on_open(T,{'TEST-USDT':100},{'TEST-USDT':20000},[(bad,row,req[2])])
    assert rejects and not k.positions and k.cash==100000 and not k.fills

def test_runner_refuses_authorization_in_this_mission(tmp_path):
    with pytest.raises(PermissionError,match='EXPLICIT_AUTHORIZATION'): run_market(tmp_path,'')
    (tmp_path/'.akah_bot').mkdir(); (tmp_path/'.akah_bot/active_task.json').write_text(json.dumps({'task_id':'AKAH_FINAL_GATE2_TO_GATE3_REPLAY_READY_MEGA_V3'}))
    with pytest.raises(PermissionError,match='NEW_GOVERNED'): run_market(tmp_path,'AKAH_GATE3_SINGLE_REPLAY_AUTHORIZED')

def test_actual_event_market_staging_pipeline_with_synthetic_provider(tmp_path,monkeypatch):
    from spotbot.research.multi_school_fidelity import gate3_market_v3 as market
    stamps=pd.date_range(T-pd.Timedelta(hours=30),periods=32,freq='h')
    f=pd.DataFrame({'timestamp':stamps,'open':100.,'high':101.,'low':99.,'close':100.,'volume':1000.})
    ranking=pd.DataFrame({'decision_time':[stamps[0]],'pair':['TEST-USDT'],'eligible':[True],'adjusted_rank':[1]})
    monkeypatch.setattr(market,'raw_frame',lambda *a,**k:f.copy())
    monkeypatch.setattr(market,'canonical_aggregate',lambda repo,pair,raw,tf:f.copy())
    monkeypatch.setattr(market,'load_broad_eligibility',lambda *a:ranking.copy())
    monkeypatch.setattr(market.det,'scan_ict',lambda *a:([],[],[event()],{}))
    membership=market.hashlib.sha256(pd.util.hash_pandas_object(ranking,index=False).values.tobytes()).hexdigest().upper()
    inputs={'pairs':[{'pair':'TEST-USDT','bounded_sha256':market.bounded_sha(f)}],'membership_bounded_sha256':membership}
    db,_,_,_=market.stage_market(tmp_path,tmp_path,inputs,{'funded_grammars':[ICT]})
    row=db.execute('SELECT * FROM bars WHERE t=?',(str(T+pd.Timedelta(hours=1)),)).fetchone()
    assert row[2]==100 and row[6]==pytest.approx(24*100*1000*.005)
    assert db.execute('SELECT count(*) FROM intents').fetchone()[0]==1
    assert row[1]==str(T+pd.Timedelta(hours=1))
    db.close()

def test_arch_api_stationary_9999_paired_cash_days_and_determinism():
    from arch.bootstrap import optimal_block_length
    x=np.sin(np.arange(365)*.51)*.0001+.001
    assert np.isfinite(optimal_block_length(pd.DataFrame({'x':x}))['stationary'].iloc[0])
    frames={y:pd.DataFrame({'A':x,'B':x,'CASH':np.zeros(365)},index=pd.date_range(f'{y}-01-01',f'{y}-12-31',freq='D',tz='UTC')) for y in (2022,2023)}
    claims={'absolute':{'A':1},'paired_identical':{'A':1,'B':-1}}
    a=evaluate_calendar_claims(frames,claims); b=evaluate_calendar_claims(frames,claims)
    assert a==b and a['replications']==9999 and a['primary_family_size']==2
    assert a['claims']['paired_identical']['lcb']==0
    assert a['year_day_weights']=={2022:365,2023:365}
