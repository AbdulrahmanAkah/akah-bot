import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from spotbot.research.multi_school_fidelity import full_replay_v5 as v

T=pd.Timestamp('2022-01-03T15:00:00Z')


def test_no_fake_tick_price_and_no_exchange_authority_claim():
    rule=v.ContinuousRule('X','sha'); px=3.294e-8
    assert rule.price(px,buy=True)==px and rule.price(px,buy=False)==px
    assert 'NOT_EXCHANGE_AUTHORITY' in rule.authority_kind
    assert rule.normalize('X',100,100,T)==100
    assert rule.normalize('X',.1,100,T)==0
    assert rule.normalize_exit('X',.1,100,T)==.1
    assert rule.normalize('X',100,100,pd.Timestamp('2024-01-01T00:00:00Z'))==0


def test_cost_gate_not_arbitrary_rr_gate():
    assert v.target_net_per_unit(100,100.1,.0025)<0
    assert v.target_net_per_unit(100,101,.0025)>0


def test_campaign_be_includes_prior_realized_loss_and_partial_profit():
    fs=[{'campaign_id':'x','cash_delta':-1005}, {'campaign_id':'x','cash_delta':398}]
    assert v.campaign_breakeven(fs,'x',6,.005)==pytest.approx(607/(6*.995))
    fs.append({'campaign_id':'other','cash_delta':100000})
    assert v.campaign_breakeven(fs,'x',6,.005)==pytest.approx(607/(6*.995))


def p(kind,price,h,confirm):
    return {'kind':kind,'price':price,'pivot_time':str(T+pd.Timedelta(hours=h)),
        'confirm_time':str(T+pd.Timedelta(hours=confirm))}


def test_structural_confirmation_future_right_bars_not_available():
    ps=[p('H',105,-6,-4),p('L',90,-5,-3),p('H',110,1,3),p('L',100,2,4)]
    assert v.earned_stop(ps,T,T+pd.Timedelta(hours=3),108,95)==(95,None)
    assert v.earned_stop(ps,T,T+pd.Timedelta(hours=4),108,95)[0]==100
    assert v.earned_stop(ps,T,T+pd.Timedelta(hours=4),99,95)==(95,None)
    assert v.earned_stop(ps,T,T+pd.Timedelta(hours=4),108,101)==(101,None)


def test_no_mfe_threshold_and_nonhigher_structure_cannot_earn_stop():
    ps=[p('H',110,-6,-4),p('L',90,-5,-3),p('H',105,1,3),p('L',100,2,4)]
    assert v.earned_stop(ps,T,T+pd.Timedelta(hours=4),200,95)==(95,None)


def test_trend_mode_does_not_mix_objective_and_stop_from_other_owner():
    e=v.det.event_row(v.H3,'X',T,'test','INTENT',True,{'stop':90,'targets':[110,120],
        'count_id':'4H:ABC_END:1-2-3-4','management_owner':v.HA,'campaign_mode':'TREND_CAMPAIGN'})
    r=v.normalize(e)
    assert r['stop']==90 and r['target']==1e100


@pytest.mark.parametrize('grammar',v.GRAMMARS)
def test_all_nine_synthetic_execution_paths_and_complete_ledgers(grammar,tmp_path,monkeypatch):
    clock=pd.date_range(T,periods=3,freq='h');monkeypatch.setattr(v,'CLOCK',clock);monkeypatch.setattr(v,'DATA_START',T)
    monkeypatch.setattr(v.v4,'CLOCK',clock);monkeypatch.setattr(v.v4,'DATA_START',T)
    a=np.array([[100,125,99,120,100000,0,0,90,1,6],[100,125,99,120,100000,0,0,90,1,6],[101,105,100,102,100000,0,0,90,1,6]],float)
    ps=[p('L',90,-48,-24)]
    m={'stop':90.,'target':120.,'raid_time':str(T-pd.Timedelta(hours=4)),
        'campaign_mode':'NATIVE_TREND' if grammar in (v.WY,v.DO) else 'LIMITED_REBOUND'}
    if grammar==v.HA:m['targets']=[110,120]
    if grammar in (v.H1,v.H2,v.H3):m['management_owner']={v.H1:v.CL,v.H2:v.ICT,v.H3:v.HA}[grammar]
    if grammar==v.H3:m.update({'campaign_mode':'TREND_CAMPAIGN','targets':[110,120]})
    if grammar==v.H1:m['campaign_mode']='TREND_CAMPAIGN'
    e=v.det.event_row(grammar,'X',T,'V5_SYNTHETIC','INTENT',True,m)
    doc={'h4_pivots':ps,'daily_pivots':ps,'events':[],'intents':[e],
        'management_pivots':{d:ps for d in ('1H','4H','1D')}}
    result=v.replay_arm(grammar,.0025,{'X':a,'BTC-USDT':a},{'X':doc,'BTC-USDT':{**doc,'intents':[]}},tmp_path,'sha')
    assert result['filled_entries']==1 and result['net'] is not None
    folder=tmp_path/(grammar+'__1X')
    for name in v.protocol()['outputs']:assert (folder/name).is_file()
    fills=pd.read_csv(folder/'fills.csv'); assert fills.iloc[0].execution_phase=='OPEN'
    if grammar in (v.H1,v.H3,v.WY,v.DO):assert 'OBJECTIVE' not in set(fills.reason)


def test_negative_small_tgt1_disabled_no_unearned_be(tmp_path):
    pfolio=v.Portfolio(.005,{'X':v.ContinuousRule('X','sha')})
    row={'identity':'x','pair':'X','owner_structure_id':'x','owner_grammar':v.HA,'management_owner':v.HA,
        'stop':90,'entry_open':100,'targets':[100.1,120],'tgt1_disabled':True,'campaign_mode':'LIMITED_REBOUND'}
    assert pfolio.k.admit(row,lambda *args:100,T,10000,pfolio.rules['X'].normalize,'x',funded_ready=True)[0]
    q=pfolio.k.positions[1]['qty_current']
    v.harmonic_manage(pfolio,1,101,101,T+pd.Timedelta(hours=1),{'X':100000})
    assert pfolio.k.positions[1]['qty_current']==q and pfolio.k.positions[1]['current_stop']==90


def test_protocol_never_calls_uncertainty_resolved_or_guarantees_profit():
    x=v.protocol()
    assert not x['profit_guarantee'] and not x['2024_access'] and not x['production_change']
    assert x['unresolved']['historical_tick_lot']=='UNRESOLVED'
