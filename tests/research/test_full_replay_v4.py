import json
from dataclasses import replace
import numpy as np
import pandas as pd
import pytest
from spotbot.research.multi_school_fidelity import full_replay_v4 as v
from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as rt
from spotbot.research.multi_school_fidelity import akah_replay_ready_detectors_v1 as det

T=pd.Timestamp('2022-01-03T15:00:00Z')

def test_real_producer_timestamp_supported_no_generic_string_fallback():
    row=det.event_row(v.ICT,'X',T,'FVG','INTENT',True,{'stop':90.,'target':120.})
    assert isinstance(row['timestamp'],pd.Timestamp)
    assert json.loads(json.dumps(row,default=v.encode))['timestamp']==str(T)
    with pytest.raises(TypeError):v.encode(object())

def test_cached_ohlc_geometry_and_missing_rows_are_not_fabricated(monkeypatch):
    monkeypatch.setattr(v,'CLOCK',pd.date_range(T,periods=2,freq='h'))
    a=np.full((2,10),np.nan);a[0,:5]=[100,101,99,100,500]
    assert v.validate_cached_bars(a)['missing_rows']==1
    b=a.copy();b[0,1]=98
    with pytest.raises(ValueError,match='INVALID_OHLC'):v.validate_cached_bars(b)
    b=a.copy();b[1,0]=100
    with pytest.raises(ValueError,match='PARTIAL_OHLC'):v.validate_cached_bars(b)

def test_pit_and_protected_boundary_never_silently_pass():
    row=det.event_row(v.CL,'X',T,'THROWBACK','INTENT',False,{'stop':90,'target':120})
    assert v.normalize_intent(row) is None
    row['broad_eligible']=True;row['timestamp']=pd.Timestamp('2024-01-01T00:00:00Z')
    assert v.normalize_intent(row) is None

def test_wyckoff_live_stop_owned_not_old_base_and_consumption():
    w=v.OwnedWyckoffV4('X',state='D_DEMAND_DOMINANT',context={'cause_id':'a'})
    w.step(T,'LPS_HOLDS',{'low':90})
    assert w.entry_stop('NO_SPRING_LPS',80)==90
    kw=dict(branch='NO_SPRING_LPS',market_state='E_MARKUP',rs={'eligible':True},
        readiness={'x':True},entry=100,structural_low=90,pnf_objective=140)
    assert w.entry_intent(T,**kw) is not None
    assert w.entry_intent(T+pd.Timedelta(hours=1),**kw) is None
    w=v.OwnedWyckoffV4('X',state='D_DEMAND_DOMINANT',context={'cause_id':'a'})
    w.step(T,'LPS_HOLDS',{'low':90});w.observe_bar(T+pd.Timedelta(hours=1),89)
    assert w.entry_intent(T+pd.Timedelta(hours=1),**kw) is None

def test_elliott_same_owner_not_target_from_another_count():
    a=rt.ElliottCount('a','4H','ABC','BULLISH',(),90.,130.,T,2)
    b=rt.ElliottCount('b','1H','ABC','BULLISH',(),95.,110.,T,2)
    assert v.material_owner({'4H':[a],'1H':[b]},T,100) is a
    assert v.material_owner({'4H':[a],'1H':[replace(b,direction='BEARISH')]},T,100) is None
    motive=replace(a,kind='W3')
    assert v.material_owner({'4H':[motive]},T,100,corrective=True) is None
    corrective=replace(a,kind='ABC_END')
    assert v.material_owner({'4H':[corrective]},T,100,corrective=True) is corrective
    assert v.material_owner({'4H':[replace(corrective,created_at=T+pd.Timedelta(hours=1))]},T,100) is None

def test_capacity_limited_exit_is_explicit_partial_not_unlimited():
    r=v.quantity_rules(['X'],'sha');p=v.ResearchPortfolio(.0025,r)
    row={'identity':'x','pair':'X','owner_structure_id':'x','owner_grammar':v.CL,'stop':90,'entry_open':100}
    assert p.k.admit(row,lambda *a:100,T,20000,r['X'].normalize,'x',funded_ready=True)[0]
    q=p.k.positions[1]['qty_current'];cap={'X':100.}
    assert not p.sell(1,100,T,cap,'STOP')
    assert p.k.positions[1]['qty_current']<q and cap['X']>=-1e-9
    assert p.pending[1]=='STOP'

def test_continuous_risk_reduction_does_not_gcd_liquidate_all():
    r=v.quantity_rules(['X','Y'],'sha');p=v.ResearchPortfolio(.0025,r)
    p.k.cash=50000
    p.k.positions={1:{'episode':{'pair':'X','identity':'x'},'qty_current':500.00000001,'current_stop':90,'campaign_id':'x'},
        2:{'episode':{'pair':'Y','identity':'y'},'qty_current':500.00000002,'current_stop':90,'campaign_id':'y'}}
    assert p.safety(T,{'X':100,'Y':100},{'X':100000,'Y':100000})
    assert len(p.k.positions)==2

@pytest.mark.parametrize('grammar',v.GRAMMARS)
def test_all_nine_event_paths_with_synthetic_prices(grammar,tmp_path,monkeypatch):
    clock=pd.date_range(T,periods=3,freq='h');monkeypatch.setattr(v,'CLOCK',clock)
    a=np.array([[100,125,99,120,100000,0,0,90,1,6],[100,125,99,120,100000,0,0,90,1,6],[101,105,100,102,100000,0,0,90,1,6]],float)
    piv=[{'kind':'L','price':90,'confirm_time':str(T-pd.Timedelta(days=1)),'pivot_time':str(T-pd.Timedelta(days=2))}]
    m={'stop':90,'target':120,'targets':[110,120], 'raid_time':str(T-pd.Timedelta(hours=4))}
    if grammar in (v.H1,v.H2,v.H3):m['management_owner']={v.H1:v.CL,v.H2:v.ICT,v.H3:v.HA}[grammar]
    if grammar in (v.DO,v.WY):m['target']=1e100;m.pop('targets')
    e=det.event_row(grammar,'X',T,'SYNTHETIC_OWNED','INTENT',True,m)
    doc={'h4_pivots':piv,'daily_pivots':piv,'events':[],'intents':[e]}
    empty={**doc,'intents':[]}
    # Operational slot indices are relative to DATA_START; retain synthetic prefix.
    monkeypatch.setattr(v,'DATA_START',T)
    result=v.replay_arm(grammar,.0025,{'X':a,'BTC-USDT':a},{'X':doc,'BTC-USDT':empty},tmp_path,'sha')
    assert result['filled_entries']==1
    assert result['net'] is not None
    assert result['qualification']=='NOT_ELIGIBLE_UNCLOSED_FIDELITY'

def test_new_run_never_claims_gate2_or_fresh_holdout():
    p=v.protocol()
    assert p['protected_years_access'] is False
    assert len(p['grammars'])==9
    assert 'NOT Gate3' in p['qualification']

def test_ns_us_lookup_equivalence_and_future_not_available():
    from spotbot.research.multi_school_fidelity import akah_census_fastpath_v1 as f
    ts=pd.date_range(T,periods=3,freq='h')
    for unit in ('ns','us'):
        df=pd.DataFrame({'t':ts.as_unit(unit),'v':['UP','DOWN','RANGE']})
        assert f.fast_asof(df,T,'t','v','UNKNOWN')=='UP'
        assert f.fast_asof(df,T-pd.Timedelta(seconds=1),'t','v','UNKNOWN')=='UNKNOWN'

def test_fast_pivots_and_indicator_parity():
    from spotbot.research.multi_school_fidelity import akah_census_fastpath_v1 as f
    rng=np.random.default_rng(337);cl=100+np.cumsum(rng.normal(size=100))
    df=pd.DataFrame({'timestamp':pd.date_range(T,periods=100,freq='h'),'open':cl,'close':cl,
        'high':cl+1,'low':cl-1,'volume':rng.uniform(100,200,100)})
    pd.testing.assert_frame_equal(det.add_indicators(df),f.cached_add_indicators(df))
    x=det.add_indicators(df)
    assert rt.confirmed_pivots_2l2r(x)==f.vectorized_pivots_factory(rt)(x)

def test_tgt1_partial_retries_sell_original_half_not_repeated_halves():
    rules=v.quantity_rules(['X'],'sha');p=v.ResearchPortfolio(.0025,rules)
    row={'identity':'x','pair':'X','owner_structure_id':'x','owner_grammar':v.HA,'management_owner':v.HA,
        'stop':90,'entry_open':100,'targets':[110,130]}
    assert p.k.admit(row,lambda *a:100,T,20000,rules['X'].normalize,'x',funded_ready=True)[0]
    initial=p.k.positions[1]['qty_current']
    v.harmonic_manage(p,1,111,T+pd.Timedelta(hours=1),{'X':110.})
    v.harmonic_manage(p,1,111,T+pd.Timedelta(hours=2),{'X':100000.})
    assert p.k.positions[1]['qty_current']==pytest.approx(initial/2,abs=1e-8)
    assert row['tgt1_done']

def test_zero_capacity_tgt1_does_not_schedule_a_full_exit():
    rules=v.quantity_rules(['X'],'sha');p=v.ResearchPortfolio(.0025,rules)
    row={'identity':'x','pair':'X','owner_structure_id':'x','owner_grammar':v.HA,'management_owner':v.HA,
        'stop':90,'entry_open':100,'targets':[110,130]}
    assert p.k.admit(row,lambda *a:100,T,20000,rules['X'].normalize,'x',funded_ready=True)[0]
    q=p.k.positions[1]['qty_current'];v.harmonic_manage(p,1,111,T,{'X':0})
    assert 1 not in p.pending and p.k.positions[1]['qty_current']==q

def test_market_down_cannot_be_overridden_by_asset_up():
    a=np.zeros((len(v.CLOCK),10));a[:,8]=1
    piv=[{'kind':'L','price':90,'confirm_time':str(v.CLOCK[0]-pd.Timedelta(days=1))}]
    prices={'BTC-USDT':100,'PAIR':100}
    assert not v.router_ok(a,piv,piv,0,prices,market_direction=-1)
    assert not v.router_ok(a,piv,piv,0,prices,market_direction=-2)
    assert v.router_ok(a,piv,piv,0,prices,market_direction=1)
    index=([v.CLOCK[0]-pd.Timedelta(days=1)],[90.])
    assert v.router_ok(a,index,index,0,prices,market_direction=1)

def test_precomputed_rs_exact_causal_parity_across_datetime_units():
    ts=pd.date_range(T-pd.Timedelta(hours=100),periods=110,freq='h')
    a=pd.DataFrame({'timestamp':ts.as_unit('us'),'close':np.linspace(90,110,110)})
    b=pd.DataFrame({'timestamp':ts.as_unit('ns'),'close':np.linspace(190,210,110)})
    fast=v.rs_lookup(a,b)
    for t in ts[::7]:assert fast(t)==v.raw_relative_strength(a,b,t)

def test_classical_future_extension_does_not_relabel_past_intents():
    rng=np.random.default_rng(420);price=100+np.cumsum(rng.normal(0,.4,180))
    raw=pd.DataFrame({'timestamp':pd.date_range(T,periods=180,freq='4h'),'open':price,'close':price,
        'high':price+.5,'low':price-.5,'volume':1000.})
    rank=pd.DataFrame({'decision_time':[T-pd.Timedelta(days=1)],'pair':['X'],'eligible':[True],'adjusted_rank':[1]})
    el=v.BroadEligibilityIndex.build(rank)
    prefix=det.scan_classical('X',raw.iloc[:140].copy(),el,runtime_factory=v.ClassicalRuntimeV3)[2]
    full=det.scan_classical('X',raw,el,runtime_factory=v.ClassicalRuntimeV3)[2]
    cutoff=raw.iloc[139].timestamp
    assert prefix==[e for e in full if e['timestamp']<=cutoff]

def test_h1_cannot_use_an_invalidated_old_lps():
    ts=pd.date_range(T-pd.Timedelta(hours=110),periods=111,freq='h')
    raw=pd.DataFrame({'timestamp':ts,'close':np.linspace(90,110,111),'low':100.})
    btc=pd.DataFrame({'timestamp':ts,'close':100.,'low':90.})
    t0=ts[-10];trans=[{'system_id':v.WY,'timestamp':t0,'to_state':'E_MARKUP'}]
    lps=det.event_row(v.WY,'X',t0,'LPS_HOLDS','ACCEPTANCE',True,{'low':99.})
    setup=det.event_row(v.CL,'X',T,'THROWBACK','INTENT',True,{'stop':95,'target':120})
    assert v.make_hybrids('X',raw,btc,trans,[lps],[setup],[])
    changed=raw.copy();changed.loc[len(raw)-2,'low']=98.
    assert not v.make_hybrids('X',changed,btc,trans,[lps],[setup],[])
