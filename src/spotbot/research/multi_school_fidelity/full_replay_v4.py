"""Bounded nine-arm experimental replay. NOT an orthodox-school/Gate2 certificate.

Policy decisions are prospectively declared before staging. No future outcome rows
enter execution. Unknown doctrine is retained in the certificate, not promoted.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import traceback
import time
import shutil
import sys
from importlib.metadata import version
from decimal import Decimal, ROUND_FLOOR
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from . import akah_full_fidelity_runtime_v1 as rt
from . import akah_replay_ready_detectors_v1 as det
from . import akah_native_replay_engine_v1 as eng
from . import akah_census_fastpath_v1 as fast
from .akah_foundation_core_v1r1 import (raw_frame, canonical_aggregate, load_broad_eligibility,
    BroadEligibilityIndex, DATA_START, DATA_CUTOFF, utc, raw_relative_strength)
from .owned_runtime_v3 import OwnedWyckoffRuntimeV3, ClassicalRuntimeV3, classical_manage_v3
from .portfolio_kernel import PortfolioKernel
from .gate3_market_v3 import bounded_sha, trend_series, asof, campaign_attribution, quantity_rules

TASK = 'AKAH_SIX_SCHOOL_HYBRID_REPAIR_AND_REPLAY_MEGA_V4'
REL = Path('governance/six_school_hybrid_repair_replay_v4')
READY = Path('governance/final_gate2_to_gate3_replay_ready_mega_v3')
WY = 'FS_WYCKOFF_FULL_LONG'
ICT = 'FS_ICT_2022_CORE_CRYPTO_LONG'
HA = 'FS_HARMONIC_FULL_LONG'
CL = 'FS_CLASSICAL_FULL_LONG'
EL = 'FS_ELLIOTT_FULL_LONG'
DO = 'FS_DOW_CRYPTO_ADAPTED_LONG'
H1 = 'HYB_MARKUP_CONTINUATION'
H2 = 'HYB_FAILED_AUCTION_REVERSAL'
H3 = 'HYB_CORRECTIVE_COMPLETION_RESUMPTION'
GRAMMARS = (WY, ICT, HA, CL, EL, DO, H1, H2, H3)
CLOCK = pd.date_range(DATA_START, DATA_CUTOFF-pd.Timedelta(hours=2), freq='h')

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20), b''): h.update(b)
    return h.hexdigest().upper()

def encode(v):
    if isinstance(v, (pd.Timestamp,)): return str(utc(v))
    if isinstance(v, np.generic): return v.item()
    raise TypeError('UNSUPPORTED_EVENT_VALUE:'+type(v).__name__)

def save(p, v):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(v, indent=2, default=encode, allow_nan=False)+'\n', encoding='utf-8')

class OwnedWyckoffV4(OwnedWyckoffRuntimeV3):
    """Evidence ownership fix; no invention of a new reaccumulation cause doctrine."""
    def step(self, t, event, meta=None):
        super().step(t, event, meta)
        if event == 'SELLING_CLIMAX': self.context['cause_doctrine_bound'] = True
        # New ranges cannot inherit the old base's readiness/cause.
    def observe_bar(self, t, low):
        for k in ('lps','phase_c'):
            e = self.context.get(k, {})
            if e.get('live') and utc(t)>utc(e['available_at']) and low<=e.get('low',-math.inf):
                e['live'] = False
    def entry_stop(self, branch, fallback):
        e=self.context.get('phase_c' if branch=='SPRING_TEST' else 'lps', {})
        return float(e.get('low', fallback))

def protocol():
    return {
        'task':TASK, 'scope':'EXPERIMENTAL_BOUNDED_IMPLEMENTATIONS_NOT_FULL_SCHOOL_CERTIFICATION',
        'grammars':list(GRAMMARS), 'period':['2022-01-01T00:00:00Z','2023-12-31T22:00:00Z'],
        'raw_reader':'predicate bounded 2021-09-01 <= close_timestamp < 2024-01-01',
        'initial_equity':100000, 'cost_round_trip':{'1X':.0025,'2X':.005},
        'risk':{'campaign_B0':'.005 current MTM equity at entry; never recycled',
            'total_stop_risk':.025,'gross':.9,'asset_MTM':.18,'distinct_assets':5,
            'cluster':'all spot longs one market-risk cluster; no diversification credit',
            'staged':'spring 50% B0; at most one source-owned LPS add, remaining 50%; no new cause',
            'gap':'actual next open, realized loss may exceed B0; reported not concealed',
            'risk_reduction':'continuous common lambda, retained quantities floor to 1e-8 with two-lot numerical safeguard; no GCD liquidation artefact'},
        'quantity':'prospective 1e-8 tick/lot and 50 USDT entry minimum; NOT historical exchange certification',
        'capacity':'.005 completed trailing 24h quote-turnover; per-hour shared buys/sells; partial exits if capacity constrained; TGT1 fixed quantity ledger, never a full pending exit',
        'selection':'same-asset current owner preserved; multiple different owners at checkpoint all rejected; descending causal capacity then deterministic lineage digest; no score/outcome/year/pair alpha',
        'execution':'decision at completed close, first following 1H open; stop-before-target on intrabar collision; standing gap targets at OPEN; close-generated stops next bar only; OPEN+CLOSE MTM; terminal OPEN no forced liquidation',
        'router':'retain frozen completed 1D BTC/asset protected-structure veto; lower timeframe cannot override DOWN/UNKNOWN',
        'management':{
            WY:'source structural stop + source LPS ratchet + asset distribution OR market distribution AND RS loss; P&F not take-profit',
            ICT:'existing raid stop / opposing-liquidity target / bearish MSS / NY16 next-open',
            CL:'ClassicalRuntimeV3 frozen-support pre-entry invalidation; objective + objective-progress 75% HL ratchet + confirmed H4 DOWN',
            HA:'existing bullish projected family grammar, finite stop below full PRZ required; 50% TGT1 and 50% TGT2; breakeven cost adjusted after TGT1 only from next bar; TypeII remains a distinct lifecycle',
            EL:'DIAGNOSTIC mechanical consensus adaptation: deterministic material bullish owner at highest degree/latest availability, all material opposite counts veto; stop/objective owned by SAME count; no claim of parent-child doctrine',
            DO:'DIAGNOSTIC crypto adaptation: source weekly broad-confirmation reconfirmed-bull; last confirmed H4 BTC low frozen protective stop; no price target; definite primary DOWN exit',
            H1:'NEW_PROSPECTIVE role composition: live Wyckoff E_MARKUP + positive causal RS + Classical accepted breakout; Classical management owner',
            H2:'NEW_PROSPECTIVE role composition: live Wyckoff B/C/D base and source range location + ICT raid/MSS/FVG/later retrace; ICT management owner',
            H3:'NEW_PROSPECTIVE role composition: live material bullish corrective Elliott owner + Harmonic terminal/confirmation; stop max(count invalidation,harmonic stop), target2 min(count objective,harmonic target2); Harmonic management owner'},
        'unresolved':{WY:'reaccumulation cause/readiness doctrine; intentionally no inherited old base',
            HA:'matrix doctrine and Shark/FiveZero/ABCD geometry not independently recertified; invalid projected stop geometry abstains, not silently repaired by ATR',
            EL:'full parent-child/owner doctrine unresolved; mechanical adaptation DIAGNOSTIC_ONLY',
            DO:'protective-stop is prospective research choice; orthodoxy/fidelity unresolved',
            'ALL':'independent changed-version blind reserve fidelity not certified in this economic mission'},
        'qualification':'economic metrics for every arm; NOT Gate3 qualification or production promotion because fidelity remains unclosed',
        'failure_policy':'mechanical repairs with failing regression fixtures allowed; no outcome-conditioned policy repair; isolate per-pair/per-grammar failures and continue all arms; incomplete coverage cannot qualify',
        'protected_years_access':False, 'production_change':False,'threshold_search':False,
    }

def install_fast():
    fast.install(det, rt)

def material_owner(snapshot, t, price, *, corrective=False):
    cs=[(degree,c) for degree,xs in snapshot.items() for c in xs
        if c.priority>=2 and utc(c.created_at)<=utc(t)]
    if not cs or any(c.direction!='BULLISH' for _,c in cs): return None
    good=[(d,c) for d,c in cs if c.objective is not None and 0<c.invalidation<price<c.objective
        and (not corrective or c.kind in {'ABC_END','FLAT_END','TRIANGLE','COMBINATION','ZIGZAG_END'})]
    if not good: return None
    good.sort(key=lambda dc:({'1D':0,'4H':1,'1H':2}[dc[0]],-utc(dc[1].created_at).value,
        dc[1].count_id))
    return good[0][1]

def elliott_intents(pair, raw, h4, d1, eligibility, correction_checkpoints=None):
    frames={'1H':det.add_indicators(raw),'4H':det.add_indicators(h4),'1D':det.add_indicators(d1)}
    piv={d:rt.confirmed_pivots_2l2r(f) for d,f in frames.items()}
    counts={d:[] for d in frames}; nprev={d:-1 for d in frames}; tomb=set(); emitted=set()
    out=[]; correction=[]
    times={d:[p.confirm_time for p in ps] for d,ps in piv.items()}
    for r in raw.itertuples(index=False):
        t=utc(r.timestamp); price=float(r.close)
        for d,ps in piv.items():
            n=bisect.bisect_right(times[d],t)
            if n!=nprev[d]:
                sl=ps[max(0,n-24):n]
                xs=rt.enumerate_impulse_counts(sl,d,t)+rt.enumerate_corrective_counts(sl,d,t)
                counts[d]=list({c.count_id:c for c in xs if c.count_id not in tomb}.values()); nprev[d]=n
        counts,tomb=rt.invalidate_elliott_counts_persistent(counts,price,tomb)
        owner=material_owner(counts,t,price)
        corr=(material_owner(counts,t,price,corrective=True)
            if correction_checkpoints is None or t in correction_checkpoints else None)
        if corr is not None: correction.append((str(t),corr.count_id,float(corr.invalidation),float(corr.objective)))
        if owner is None or owner.count_id in emitted or not eligibility.eligible(pair,t): continue
        emitted.add(owner.count_id)
        out.append(det.event_row(EL,pair,t,'V4_MECHANICAL_OWNED_CONSENSUS','EXPERIMENTAL_DIAGNOSTIC',True,
            {'stop':float(owner.invalidation),'target':float(owner.objective),'count_id':owner.count_id,
             'owner_kind':owner.kind,'doctrine_certified':False}))
    return out,correction

def state_at(trans, t):
    j=bisect.bisect_right(trans[0],t)-1
    return trans[1][j] if j>=0 else 'UNKNOWN'

def rs_lookup(raw,btc):
    series=[]
    for frame in (raw,btc):
        series.append((pd.DatetimeIndex(pd.to_datetime(frame.timestamp,utc=True)),frame.close.to_numpy(dtype=float)))
    def lookup(t):
        values=[]
        for ts,cl in series:
            for at in (t,t-pd.Timedelta(hours=72)):
                j=int(ts.searchsorted(at,side='right'))-1
                if j<0:return None
                values.append(float(cl[j]))
        p1,p0,b1,b0=values
        if min(p0,b0,b1)<=0 or not all(math.isfinite(z) for z in values):return None
        return (p1/p0)/(b1/b0)-1.
    return lookup

def make_hybrids(pair, raw, btc, trans, events, intents, corrections):
    wt=[r for r in trans if r.get('system_id')==WY]
    wt.sort(key=lambda r:utc(r['timestamp']))
    state=([utc(r['timestamp']) for r in wt],[r['to_state'] for r in wt])
    corr_times=[utc(r[0]) for r in corrections]; hybrids=[]
    rawtimes=pd.DatetimeIndex(pd.to_datetime(raw.timestamp,utc=True))
    relative_strength=rs_lookup(raw,btc)
    for e in sorted(intents,key=lambda e:utc(e['timestamp'])):
        t=utc(e['timestamp']); g=e['system_id']; m=json.loads(e['metadata']); phase=state_at(state,t)
        rs=relative_strength(t)
        role=None
        if g==CL and phase=='E_MARKUP' and rs is not None and rs>0:
            lps=[z for z in events if z['system_id']==WY and z['event']=='LPS_HOLDS' and utc(z['timestamp'])<=t]
            resets=[z for z in events if z['system_id']==WY and z['stage']=='RESET' and utc(z['timestamp'])<=t]
            if lps:
                le=lps[-1];lt=utc(le['timestamp']);low=json.loads(le['metadata']).get('low')
                first=int(rawtimes.searchsorted(lt,side='right'));end=int(rawtimes.searchsorted(t,side='right'))
                live=low is not None and not any(utc(z['timestamp'])>=lt for z in resets)
                if live and (first==end or float(raw.iloc[first:end].low.min())>low):role=H1
        elif g==ICT and phase in {'B_CAUSE_BUILDING','C_TESTING_SUPPLY','D_DEMAND_DOMINANT'}:
            # Raid is source-owned and retracement later. No independent sweep votes.
            raid=utc(m['raid_time'])
            bases=[z for z in wt if z['to_state']=='B_CAUSE_BUILDING' and utc(z['timestamp'])<=raid]
            if bases and state_at(state,raid) in {'B_CAUSE_BUILDING','C_TESTING_SUPPLY','D_DEMAND_DOMINANT'}:
                bm=json.loads(bases[-1]['metadata']);support=bm.get('support');resistance=bm.get('resistance')
                j=int(rawtimes.searchsorted(raid,side='right'))-1
                if support is not None and resistance is not None and j>=0:
                    rr=raw.iloc[j]
                    if float(rr.low)<float(support)<float(rr.close)<float(resistance):role=H2
        elif g==HA:
            j=bisect.bisect_right(corr_times,t)-1
            # A correction must be present at THIS completed checkpoint, not a
            # stale count from an arbitrary earlier bar.
            if j>=0 and corr_times[j]==t:
                _,cid,inv,obj=corrections[j]
                targets=m['targets']
                m={**m,'stop':max(float(m['stop']),inv),'targets':[float(targets[0]),min(float(targets[1]),obj)],'count_id':cid}
                if m['targets'][0]<m['targets'][1]: role=H3
        if role:
            h={**e,'system_id':role,'event':'V4_ROLE_BOUND_'+e['event'],'metadata':json.dumps({**m,
               'management_owner':g,'role_context_phase':phase,'role_context_known_at':str(t),
               'role_selection_rs':rs,'doctrine_certified':False},default=encode,allow_nan=False)}
            hybrids.append(h)
    return hybrids

def pair_worker(repo_string, record, market_trans):
    repo=Path(repo_string); root=repo/REL; pair=record['pair']; install_fast()
    raw=raw_frame(repo,pair)
    if bounded_sha(raw)!=record['bounded_sha256']: raise ValueError('BOUNDED_SHA_DRIFT:'+pair)
    h4=canonical_aggregate(repo,pair,raw,'4h'); d1=canonical_aggregate(repo,pair,raw,'1d')
    eligibility=BroadEligibilityIndex.build(load_broad_eligibility(repo))
    btc=raw_frame(repo,'BTC-USDT'); eth=raw_frame(repo,'ETH-USDT')
    trans=[]; events=[]; intents=[]; errors=[]; summaries=[]
    calls=[(WY,det.scan_wyckoff,(pair,h4,raw,btc,eligibility,market_trans,False),{'runtime_factory':OwnedWyckoffV4}),
        (ICT,det.scan_ict,(pair,raw,h4,d1,btc,eth,eligibility),{}),
        (HA,det.scan_harmonic,(pair,h4,eligibility),{}),
        (CL,det.scan_classical,(pair,h4,eligibility),{'runtime_factory':ClassicalRuntimeV3})]
    for g,fn,args,kwargs in calls:
        started=time.monotonic()
        try:
            tr,ev,it,su=fn(*args,**kwargs); trans+=tr; events+=ev; intents+=it; summaries.append(su)
        except Exception:
            errors.append({'pair':pair,'grammar':g,'trace':traceback.format_exc()})
        print('PAIR_ACTIVITY',pair,g,round(time.monotonic()-started,2),flush=True)
    started=time.monotonic()
    try:
        checkpoints={utc(e['timestamp']) for e in intents if e['system_id']==HA}
        ei,corrections=elliott_intents(pair,raw,h4,d1,eligibility,checkpoints); intents+=ei
    except Exception: corrections=[];errors.append({'pair':pair,'grammar':EL,'trace':traceback.format_exc()})
    print('PAIR_ACTIVITY',pair,'ELLIOTT',round(time.monotonic()-started,2),flush=True)
    started=time.monotonic()
    try: intents+=make_hybrids(pair,raw,btc,trans,events,intents,corrections)
    except Exception: errors.append({'pair':pair,'grammar':'HYBRIDS','trace':traceback.format_exc()})
    print('PAIR_ACTIVITY',pair,'HYBRIDS',round(time.monotonic()-started,2),flush=True)
    # Only causal fields: no future exit prices/reasons or path labels in cache.
    data=np.full((len(CLOCK),10),np.nan)
    ts=pd.DatetimeIndex(pd.to_datetime(raw.timestamp,utc=True))
    vol=pd.Series(raw.volume.to_numpy()*raw.close.to_numpy(),index=ts).rolling('24h',min_periods=24).sum()
    market_d=trend_series(d1); asset4=trend_series(h4)
    mss=set(eng.bearish_mss_times(raw)); down=set(eng.confirmed_primary_down_times(h4))
    hp=asset4[2]; lows=[p for p in hp if p.kind=='L']; lt=[p.confirm_time for p in lows]
    wy_trans=([utc(x['timestamp']) for x in trans if x['system_id']==WY],
        [x['to_state'] for x in trans if x['system_id']==WY])
    for i,r in enumerate(raw.itertuples(index=False)):
        opening=utc(r.timestamp)-pd.Timedelta(hours=1); k=int((opening-DATA_START)/pd.Timedelta(hours=1))
        if k<0 or k>=len(CLOCK): continue
        t=utc(r.timestamp); j=bisect.bisect_right(lt,t)-1
        cap=vol.iloc[i-1]*.005 if i>0 and ts[i-1]==opening else np.nan
        # mss/down/HL columns belong to current COMPLETED close, never read at entry open.
        data[k]=[r.open,r.high,r.low,r.close,cap,float(t in mss),float(t in down),
            lows[j].price if j>=0 else np.nan, {'UP':1,'DOWN':-1,'RANGE':0,'UNKNOWN':-2}[asof(market_d,opening)],
            state_code(state_at(wy_trans,t))]
    cache=root/'cache';cache.mkdir(exist_ok=True)
    np.save(cache/(pair+'.npy'),data)
    save(cache/(pair+'.events.json'),{'transitions':trans,'events':events,'intents':intents,
        'daily_pivots':[{'kind':p.kind,'price':p.price,'confirm_time':str(p.confirm_time),'pivot_time':str(p.pivot_time)} for p in market_d[2]],
        'h4_pivots':[{'kind':p.kind,'price':p.price,'confirm_time':str(p.confirm_time),'pivot_time':str(p.pivot_time)} for p in hp],
        'weekly':det.weekly_return_rows(pair,raw,load_broad_eligibility(repo).query('pair == @pair')),
        'errors':errors,'summaries':summaries,'input_sha':record['bounded_sha256'],'producer_schema':2})
    fast.clear_pair_caches()
    return {'pair':pair,'intents':len(intents),'errors':errors,'cache_sha':sha(cache/(pair+'.npy')),
        'events_sha':sha(cache/(pair+'.events.json'))}

def state_code(s):
    return {'UNKNOWN':0,'DOWNTREND':1,'A_STOPPING':2,'B_CAUSE_BUILDING':3,'C_TESTING_SUPPLY':4,
        'D_DEMAND_DOMINANT':5,'E_MARKUP':6,'REACCUMULATION':7,'DISTRIBUTION_RISK':8}.get(s,0)

def validate_cached_bars(array):
    """Structural validation only; missing pre-listing/gap rows are not fabricated."""
    if array.shape != (len(CLOCK),10):raise ValueError('CACHE_SCHEMA')
    bars=array[:,:4];present=np.isfinite(bars).any(axis=1)
    if not np.isfinite(bars[present]).all():raise ValueError('PARTIAL_OHLC_ROW')
    b=bars[present]
    if len(b) and (np.any(b<=0) or np.any(b[:,1]<np.maximum(b[:,0],b[:,3]))
        or np.any(b[:,2]>np.minimum(b[:,0],b[:,3])) or np.any(b[:,2]>b[:,1])):
        raise ValueError('INVALID_OHLC_GEOMETRY')
    cap=array[:,4];valid=np.isfinite(cap)
    if np.any(cap[valid]<0):raise ValueError('NEGATIVE_PARTICIPATION_CAPACITY')
    return {'present_rows':int(present.sum()),'missing_rows':int((~present).sum()),'ohlc_schema':'PASS'}

def normalize_intent(e):
    if not e.get('broad_eligible',False): return None
    t=utc(e['timestamp'])
    if not DATA_START<=t<CLOCK[-1]: return None
    m=json.loads(e['metadata']) if isinstance(e['metadata'],str) else dict(e['metadata'])
    owner=m.get('management_owner',e['system_id'])
    targets=list(m.get('targets',[m.get('target',math.inf)]))
    stop=float(m['stop'])
    if not math.isfinite(stop) or stop<=0 or any(not math.isfinite(float(x)) or x<=0 for x in targets):
        if owner!=DO: return None
    identity=hashlib.sha256(json.dumps(e,sort_keys=True,default=encode).encode()).hexdigest()
    return {**m,'identity':identity,'pair':e['pair'],'owner_grammar':e['system_id'],
        'management_owner':owner,'owner_structure_id':m.get('cause_id') or m.get('pattern_id') or
        m.get('projection_id') or m.get('count_id') or identity,'ready_at':str(t),
        'stop':stop,'target':float(targets[-1]),'targets':targets,'source_event':e['event']}

def router_ok(p, btc_pivots, pivots, k, prices, *, market_direction):
    t=CLOCK[k]
    def protected(ps,mark):
        if isinstance(ps,tuple):
            j=bisect.bisect_right(ps[0],t)-1
            return j>=0 and mark>ps[1][j]
        ls=[z for z in ps if z['kind']=='L' and utc(z['confirm_time'])<=t]
        return bool(ls and mark>ls[-1]['price'])
    return (market_direction not in (-1,-2) and p[k,8] not in (-1,-2)
        and protected(btc_pivots,prices.get('BTC-USDT',0))
        and protected(pivots,prices.get('PAIR',0)))

class DecimalQuantityKernel(PortfolioKernel):
    def partial_exit(self,tid,quantity,price,*,now=None,reason='EXIT'):
        old=self.positions[tid]['qty_current']
        remaining=float(Decimal(str(old))-Decimal(str(quantity)))
        super().partial_exit(tid,quantity,price,now=now,reason=reason)
        if tid in self.positions:self.positions[tid]['qty_current']=remaining

class ResearchPortfolio:
    def __init__(self,cost,rules):
        self.k=DecimalQuantityKernel(100000.,{}, {},cost/2); self.rules=rules; self.pending={}
        self.rejects=[];self.audit=[];self.risk_pass=True;self.seen=set()
        self.capacity_blocked_full_exit_count=0
    def sell(self,tid,price,t,cap,reason,fraction=1.):
        p=self.k.positions[tid];pair=p['episode']['pair'];rule=self.rules[pair]
        px=rule.price(price,buy=False); available=max(0,cap.get(pair,0) or 0)
        if not math.isfinite(available):available=0
        qty=min(p['qty_current']*fraction,available/px)
        qty=rule.normalize_exit(pair,qty,px,t)
        full_request=fraction==1. and reason not in {'TGT1','COMMON_RISK_REDUCTION'}
        if qty<=0:
            if full_request:
                self.pending[tid]=reason;self.risk_pass=False;self.capacity_blocked_full_exit_count+=1
            return False
        requested=p['qty_current']*fraction
        cap[pair]-=qty*px
        self.k.partial_exit(tid,qty,px,now=t,reason=reason)
        if full_request and tid in self.k.positions:
            self.pending[tid]=reason;self.risk_pass=False;self.capacity_blocked_full_exit_count+=1
        elif tid not in self.k.positions:self.pending.pop(tid,None)
        return qty>=requested-1e-10
    def safety(self,t,prices,capacity):
        marks=lambda pair,at:prices.get(pair)
        lam,state=eng.proportional_risk_reduction_lambda(self.k.cash,self.k.positions,marks,t,self.k.exit_cost_rate)
        if lam is None:self.risk_pass=False;return False
        if lam<1:
            # Round retained quantities DOWN, not common lattice by GCD.
            for tid,p in list(self.k.positions.items()):
                rule=self.rules[p['episode']['pair']];qty=p['qty_current']
                units=(Decimal(str(qty))*Decimal(str(lam))/rule.lot).to_integral_value(rounding=ROUND_FLOOR)
                # Two machine lot units cover float->Decimal->float boundary
                # error; this is numerical conservatism, not an alpha threshold.
                retained=float(max(Decimal(0),units-2)*rule.lot)
                self.sell(tid,prices[p['episode']['pair']],t,capacity,'COMMON_RISK_REDUCTION',max(0,(qty-retained)/qty))
        ok=eng.current_mtm_limits_ok(self.k.snapshot(marks,t))
        if not ok:self.risk_pass=False
        return ok

def harmonic_manage(portfolio,tid,high,close_at,capacity):
    p=portfolio.k.positions[tid];r=p['episode'];old_stop=p['current_stop']
    target1,target2=map(float,r['targets'])
    if 'tgt1_quantity' not in r:
        lot=portfolio.rules[r['pair']].lot
        r['tgt1_quantity']=float((Decimal(str(p['qty_current']))/2/lot).to_integral_value(rounding=ROUND_FLOOR)*lot)
        r['tgt1_sold']=0.
    if not r.get('tgt1_done') and high>=target1:
        remaining=max(0,r['tgt1_quantity']-r['tgt1_sold']);before=p['qty_current']
        portfolio.sell(tid,target1,close_at,capacity,'TGT1',min(1,remaining/before))
        after=portfolio.k.positions.get(tid,{}).get('qty_current',0.)
        r['tgt1_sold']+=before-after
        if r['tgt1_sold']>=r['tgt1_quantity']-1e-10:
            r['tgt1_done']=True
            if tid in portfolio.k.positions:
                rate=portfolio.k.exit_cost_rate;be=r['entry_open']*(1+rate)/(1-rate)
                p['current_stop']=max(old_stop,be)
    if tid in portfolio.k.positions and r.get('tgt1_done') and high>=target2:
        portfolio.sell(tid,target2,close_at,capacity,'TGT2')

def replay_arm(grammar,cost,arrays,events,root,input_sha):
    rules=quantity_rules(arrays,input_sha); portfolio=ResearchPortfolio(cost,rules);kernel=portfolio.k
    candidates={};events_by_pair={};pivots={};daily_pivots={};birth={};last={};equity=[]
    low_index={};daily_low_index={}
    for pair,doc in events.items():
        pivots[pair]=doc['h4_pivots'];daily_pivots[pair]=doc['daily_pivots']
        ls=[p for p in pivots[pair] if p['kind']=='L']
        low_index[pair]=([utc(p['confirm_time']) for p in ls],
            [utc(p['pivot_time']) for p in ls],[float(p['price']) for p in ls])
        dl=[p for p in daily_pivots[pair] if p['kind']=='L']
        daily_low_index[pair]=([utc(p['confirm_time']) for p in dl],[float(p['price']) for p in dl])
        events_by_pair[pair]={}
        for e in doc['events']:
            events_by_pair[pair].setdefault(str(utc(e['timestamp'])),[]).append(e)
        for e in doc['intents']:
            if e['system_id']!=grammar:continue
            try:r=normalize_intent(e)
            except Exception as ex:portfolio.rejects.append({'reason':'SCHEMA:'+str(ex),'pair':pair});continue
            if r:candidates.setdefault(int((utc(r['ready_at'])-DATA_START)/pd.Timedelta(hours=1)),[]).append(r)
    missing=[]
    for k,t in enumerate(CLOCK):
        btc=arrays['BTC-USDT'];requests=candidates.get(k,[])
        held={p['episode']['pair'] for p in kernel.positions.values()}
        wanted=held|{r['pair'] for r in requests}|{'BTC-USDT'}
        prices={p:float(arrays[p][k,0]) for p in wanted if p in arrays and np.isfinite(arrays[p][k,0])}
        last.update(prices)
        cap={p:float(arrays[p][k,4]) if np.isfinite(arrays[p][k,4]) else 0. for p in prices}
        absent=held-set(prices)
        if absent:portfolio.risk_pass=False;missing.append({'time':str(t),'pairs':sorted(absent)})
        for tid,p in list(kernel.positions.items()):
            r=p['episode'];pair=r['pair']
            if pair not in prices:continue
            px=prices[pair]
            if px<=p['current_stop']:portfolio.sell(tid,px,t,cap,'STOP_GAP')
            elif r['management_owner']==HA and px>=float(r['targets'][0]):
                harmonic_manage(portfolio,tid,px,t,cap)
                if tid in kernel.positions and tid in portfolio.pending:
                    portfolio.sell(tid,px,t,cap,portfolio.pending[tid])
            elif r['management_owner'] not in (WY,DO) and px>=r['target']:
                portfolio.sell(tid,r['target'],t,cap,'OBJECTIVE_GAP')
            elif tid in portfolio.pending:portfolio.sell(tid,px,t,cap,portfolio.pending[tid])
        safe=not absent and portfolio.safety(t,prices,cap) and not portfolio.pending
        batch={}
        for r in requests:batch.setdefault(r['pair'],[]).append(r)
        ordered=[]
        for pair,rs in batch.items():
            if len({r['owner_structure_id'] for r in rs})>1:
                portfolio.rejects.append({'time':str(t),'pair':pair,'reason':'SAME_ASSET_OWNER_CONFLICT'});continue
            ordered.append(min(rs,key=lambda r:r['identity']))
        ordered.sort(key=lambda r:(-cap.get(r['pair'],0),r['identity']))
        for r in ordered:
            pair=r['pair'];tid=r['identity'];reason=None
            if tid in portfolio.seen:reason='NO_RESURRECTION'
            portfolio.seen.add(tid)
            if reason is None and (not safe or pair not in prices):reason='RISK_OR_PRICE_UNAVAILABLE'
            if reason is None and not router_ok(arrays[pair],daily_low_index['BTC-USDT'],daily_low_index[pair],k,
                {'BTC-USDT':prices.get('BTC-USDT',0),'PAIR':prices[pair]},market_direction=btc[k,8]):reason='ROUTER_VETO'
            if reason is None:
                px=rules[pair].price(prices[pair],buy=True)
                r['stop']=rules[pair].price(r['stop'],buy=False)
                if not 0<r['stop']<px<r['target']:reason='FROZEN_ENTRY_GEOMETRY_INVALID'
                if r['management_owner']==HA and px>=float(r['targets'][0]):reason='FIRST_OBJECTIVE_ALREADY_PASSED'
            if reason is not None:portfolio.rejects.append({'time':str(t),'pair':pair,'reason':reason});continue
            r={**r,'entry_open':px}
            staged=r['management_owner']==WY and r['source_event']=='SPRING_TEST'
            existing=[p for p in kernel.positions.values() if p['episode']['pair']==pair]
            is_add=bool(existing and staged is False and r['management_owner']==WY and
                existing[0]['episode'].get('staged') and existing[0]['episode']['owner_structure_id']==r['owner_structure_id'])
            cid=existing[0]['campaign_id'] if is_add else tid
            r['staged']=staged
            ok,reason=kernel.admit(r,lambda pair,at:prices[pair],t,cap.get(pair),rules[pair].normalize,cid,
                funded_ready=True,is_add=is_add,staged=staged)
            if ok:
                f=kernel.fills[-1];cap[pair]-=f['qty']*f['price'];birth[tid]=t
            else:portfolio.rejects.append({'time':str(t),'pair':pair,'reason':reason})
        expected=100000.+sum(f['cash_delta'] for f in kernel.fills)
        if not math.isclose(expected,kernel.cash,abs_tol=1e-5):raise ValueError('CASH_LEDGER_PARITY')
        s=kernel.snapshot(lambda pair,at:last.get(pair),t)
        if not s['valid']:raise ValueError('MTM_NO_MARK')
        equity.append({'time':str(t),'observation':'OPEN','equity':s['equity'],'cash':kernel.cash,'gross':s['gross'],
            'stop_risk':s['open_stop_risk'],'risk_limits_pass':eng.current_mtm_limits_ok(s),'stale_mark':bool(absent)})
        if k==len(CLOCK)-1:break
        close=t+pd.Timedelta(hours=1)
        for tid,p in list(kernel.positions.items()):
            r=p['episode'];pair=r['pair'];a=arrays[pair][k]
            if not np.isfinite(a[:4]).all():continue
            lo,hi,cl=float(a[2]),float(a[1]),float(a[3]);owner=r['management_owner']
            old_stop=p['current_stop']
            if lo<=old_stop:
                portfolio.sell(tid,old_stop,close,cap,'STRUCTURAL_STOP');continue
            # Harmonic scale-out uses the OLD stop first. New break-even cannot
            # be tested retrospectively against this completed bar's low.
            if owner==HA:
                harmonic_manage(portfolio,tid,hi,close,cap)
                continue
            if owner not in (WY,DO) and hi>=r['target']:
                portfolio.sell(tid,r['target'],close,cap,'OBJECTIVE');continue
            native=events_by_pair[pair].get(str(close),[])
            if owner==ICT:
                action=rt.ict_manage_active(t=close,raid_time=utc(r['raid_time']),bar_low=lo,bar_high=hi,
                    raid_low=old_stop,target=r['target'],bearish_mss=bool(a[5]))
                if action in {'BEARISH_MSS_EXIT_NEXT_OPEN','NY_1600_DAY_BOUNDARY'}:portfolio.pending[tid]=action
            elif owner==CL:
                lc,lp,lv=low_index[pair];j=bisect.bisect_right(lc,close)-1
                hl=lv[j] if j>=0 and lp[j]>utc(r['ready_at']) else None
                dec=classical_manage_v3(entry_price=r['entry_open'],price=cl,target=r['target'],current_stop=old_stop,
                    confirmed_higher_low=hl,primary_trend='DOWN' if a[6] else 'UP',
                    pattern_failed=cl<=r.get('frozen_support',-math.inf))
                p['current_stop']=max(old_stop,dec['stop'])
                if dec['action'].startswith('EXIT'):portfolio.pending[tid]=dec['action']
            elif owner==WY:
                for e in native:
                    if e['system_id']!=WY:continue
                    m=json.loads(e['metadata'])
                    if e['event']=='DISTRIBUTION_RISK':portfolio.pending[tid]='ASSET_DISTRIBUTION'
                    if e['event']=='LPS_HOLDS' and m.get('low') and old_stop<float(m['low'])<cl:
                        p['current_stop']=float(m['low'])
                # State at close is descriptive management information only.
                if btc[k,9]==8:
                    j=max(0,k-72)
                    ap0=arrays[pair][j,3];bp0=btc[j,3]
                    if ap0>0 and bp0>0 and (cl/ap0)/(btc[k,3]/bp0)<=1:portfolio.pending[tid]='MARKET_DISTRIBUTION_RS_LOSS'
            elif owner==DO:
                if btc[k,8]==-1:portfolio.pending[tid]='DEFINITE_PRIMARY_REVERSAL'
            elif owner!=EL:raise ValueError('UNBOUND_MANAGEMENT_OWNER:'+owner)
        close_prices={pair:float(arrays[pair][k,3]) for pair in wanted
            if pair in arrays and np.isfinite(arrays[pair][k,3])}
        closing_state=kernel.snapshot(lambda pair,at:close_prices.get(pair,last.get(pair)),close)
        close_risk=eng.current_mtm_limits_ok(closing_state)
        if not close_risk:portfolio.risk_pass=False
        equity.append({'time':str(close),'observation':'CLOSE','equity':closing_state['equity'],
            'cash':kernel.cash,'gross':closing_state['gross'],'stop_risk':closing_state['open_stop_risk'],
            'risk_limits_pass':close_risk,'stale_mark':bool(absent)})
    folder=root/(grammar+'__'+str(int(cost/.0025))+'X');folder.mkdir(exist_ok=True)
    eq=pd.DataFrame(equity);eq['time']=pd.to_datetime(eq.time,utc=True);eq=eq.set_index('time')
    daily=eq.equity.resample('D').last();campaigns,assets=campaign_attribution(kernel,last)
    open_campaigns={p['campaign_id'] for p in kernel.positions.values()}
    by_campaign={}
    for fill in kernel.fills:by_campaign.setdefault(fill['campaign_id'],[]).append(fill)
    holding=[]
    for row in campaigns:
        cid=row['campaign_id'];campaign=kernel.campaigns[cid];fs=by_campaign[cid]
        row.update({'B0':campaign.initial_risk_budget,'committed_risk':campaign.committed_risk,
            'add_count':campaign.add_count,'closed':cid not in open_campaigns,
            'first_entry_at':fs[0]['time']})
        if cid not in open_campaigns:
            row['final_exit_at']=fs[-1]['time'];row['holding_hours']=float((utc(fs[-1]['time'])-utc(fs[0]['time']))/pd.Timedelta(hours=1))
            holding.append(row['holding_hours'])
    net=float(eq.equity.iloc[-1]-100000)
    if not math.isclose(sum(c['net_including_fees_and_terminal_mtm'] for c in campaigns),net,abs_tol=1e-5):raise ValueError('CAMPAIGN_PARITY')
    pnl=np.array([c['net_including_fees_and_terminal_mtm'] for c in campaigns]);wins=pnl[pnl>0];loss=pnl[pnl<0]
    closed_pnl=np.array([c['net_including_fees_and_terminal_mtm'] for c in campaigns if c['closed']])
    closed_loss=closed_pnl[closed_pnl<0].sum()
    annual={};previous=100000.
    for year,values in daily.groupby(daily.index.year):
        annual[str(year)]=float(values.iloc[-1]-previous);previous=float(values.iloc[-1])
    metrics={'grammar':grammar,'cost':cost,'status':'REPLAY_COMPLETE_EXPERIMENTAL_NOT_FIDELITY_CERTIFIED',
        'initial_equity':100000.,'final_equity':float(eq.equity.iloc[-1]),'net':net,
        'mdd':float((1-eq.equity/eq.equity.cummax().clip(lower=100000)).max()),
        'campaigns':len(kernel.campaigns),'filled_entries':sum(f['side']=='BUY' for f in kernel.fills),
        'closed_campaigns':len(kernel.campaigns)-len({p['campaign_id'] for p in kernel.positions.values()}),
        'win_rate_including_terminal_MTM':float((pnl>0).mean()) if len(pnl) else None,
        'profit_factor_including_terminal_MTM':float(wins.sum()/-loss.sum()) if loss.sum()<0 else None,
        'closed_campaign_profit_factor':float(closed_pnl[closed_pnl>0].sum()/-closed_loss) if closed_loss<0 else None,
        'mean_closed_holding_hours':float(np.mean(holding)) if holding else None,
        'net_2022':annual.get('2022'),'net_2023':annual.get('2023'),
        'annual_net':annual,
        'fees':sum(f['fee'] for f in kernel.fills),'open_positions':len(kernel.positions),
        'risk_pass':portfolio.risk_pass,'missing_mark_hours':len(missing),'mean_gross_utilization':float((eq.gross/eq.equity).mean()),
        'capacity_blocked_full_exit_count':portfolio.capacity_blocked_full_exit_count,
        'pending_exits_at_cutoff':len(portfolio.pending),
        'economic_interpretation':('INCOMPLETE_EXECUTION_PATH_STALE_MTM_NOT_CERTIFIED' if missing
            else 'BOUNDED_EXPERIMENTAL_METRICS_NOT_SCHOOL_QUALIFICATION'),
        'turnover_over_mean_equity':float(sum(f['qty']*f['price'] for f in kernel.fills)/eq.equity.mean()),
        'campaign_loss_exceeds_B0_count':sum(c['net_including_fees_and_terminal_mtm']<-c['B0'] for c in campaigns),
        'leave_largest_asset_net':net-max(assets.values(),default=0.),
        'leave_largest_campaign_net':net-max(pnl,default=0.),'qualification':'NOT_ELIGIBLE_UNCLOSED_FIDELITY',
        '2024_access':False,'2025_access':False,'production_change':False}
    eq.to_csv(folder/'hourly_equity.csv.gz',compression='gzip')
    pd.DataFrame(kernel.fills).to_csv(folder/'fills.csv',index=False)
    pd.DataFrame(campaigns).to_csv(folder/'campaigns.csv',index=False)
    pd.DataFrame(portfolio.rejects).to_csv(folder/'rejections.csv.gz',index=False,compression='gzip')
    save(folder/'missing_marks.json',missing);save(folder/'metrics.json',metrics)
    return metrics

def freeze(repo,*,mechanical_repair=False):
    root=repo/REL;root.mkdir(exist_ok=True)
    if (root/'STARTED.json').exists():
        if not mechanical_repair:raise PermissionError('USE_EXISTING_RUN_CHECKPOINT_NOT_NEW_FREEZE')
        if list(root.glob('*/metrics.json')):raise PermissionError('ECONOMICS_ALREADY_STARTED')
        suffix='initial' if not (root/'frozen_source_manifest_initial.json').exists() else 'pre_economics_'+pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%S%f')
        shutil.copyfile(root/'frozen_source_manifest.json',root/f'frozen_source_manifest_{suffix}.json')
        shutil.copyfile(root/'research_protocol.json',root/f'research_protocol_{suffix}.json')
        save(root/'mechanical_repair_before_economics.json',{
            'original_manifest_sha':sha(root/'frozen_source_manifest_initial.json'),
            'defect':'TGT1 retries sold half of remaining rather than fixed initial half when participation constrained',
            'discovery':'source inspection BEFORE any economic output',
            'repair':'retain original quantity target; ledger cumulative actual fills',
            'outcome_or_parameter_selection':False,'previous_START_preserved':True,
            'correction_kind_repair':'W3/W5 are motive, never corrective; explicit existing runtime correction-kind set',
            'other_pre_economic_mechanical_repairs':['typed Timestamp serialization','ns/us causal asof parity',
                'BTC veto precedence','Decimal quantity residual accounting','capacity blocked TGT1 is not a full exit',
                'OPEN and CLOSE MTM accounting','indexed confirmed-pivot and causal RS lookup parity',
                'structural cached OHLC/capacity validation','dependent hybrid source-coverage propagation'],
            'resume':'reuse complete causal pair caches; regenerate H3 for pre-repair caches; unfinished pairs recomputed; no old replay data reused'})
    source={str(p.relative_to(repo)).replace('\\','/'):sha(p)
        for p in sorted((repo/'src/spotbot/research/multi_school_fidelity').glob('*.py'))}
    source['scripts/research/run_full_replay_v4.py']=sha(repo/'scripts/research/run_full_replay_v4.py')
    for relative in ('scripts/research/report_full_replay_v4.py','tests/research/test_full_replay_v4.py',
        'src/spotbot/data/aggregation.py','src/spotbot/data/timeframes.py','src/spotbot/data/validator.py',
        'src/spotbot/core/models.py'):
        source[relative]=sha(repo/relative)
    for p in source:compile((repo/p).read_text(encoding='utf-8-sig'),p,'exec')
    save(root/'research_protocol.json',protocol())
    save(root/'runtime_dependencies.json',{'python':sys.version,
        'packages':{name:version(name) for name in ('numpy','pandas','pyarrow','arch','pytest')}})
    save(root/'frozen_source_manifest.json',{'files':source,'protocol_sha':sha(root/'research_protocol.json'),
        'input_manifest_sha':sha(repo/READY/'bounded_market_input_manifest.json'),
        'runtime_dependency_sha':sha(root/'runtime_dependencies.json')})
    return root

def run(repo,workers=6,*,resume=False,stage_only=False):
    root=repo/REL
    active=json.loads((repo/'.akah_bot/active_task.json').read_text())
    if active['task_id']!=TASK:raise PermissionError('GOVERNED_TASK_REQUIRED')
    m=json.loads((root/'frozen_source_manifest.json').read_text())
    if any(sha(repo/p)!=s for p,s in m['files'].items()) or sha(root/'research_protocol.json')!=m['protocol_sha']:
        raise ValueError('FROZEN_SOURCE_OR_POLICY_DRIFT')
    if sha(repo/READY/'bounded_market_input_manifest.json')!=m['input_manifest_sha']:
        raise ValueError('FROZEN_INPUT_MANIFEST_DRIFT')
    if 'runtime_dependency_sha' in m:
        if sha(root/'runtime_dependencies.json')!=m['runtime_dependency_sha']:raise ValueError('DEPENDENCY_CONTRACT_DRIFT')
        deps=json.loads((root/'runtime_dependencies.json').read_text())
        if deps['python']!=sys.version or any(version(n)!=v for n,v in deps['packages'].items()):
            raise ValueError('RUNTIME_DEPENDENCY_DRIFT')
    if (root/'STARTED.json').exists():
        if not resume or not (root/'mechanical_repair_before_economics.json').exists():raise PermissionError('ALREADY_STARTED')
        save(root/'RESUMED.json',{'task':TASK,'mechanical_only':True,'source_manifest_sha':sha(root/'frozen_source_manifest.json')})
    else:save(root/'STARTED.json',{'task':TASK,'user_all_arms_authorization':True,'source_manifest_sha':sha(root/'frozen_source_manifest.json')})
    inputs=json.loads((repo/READY/'bounded_market_input_manifest.json').read_text());install_fast()
    ranking=load_broad_eligibility(repo)
    membership=hashlib.sha256(pd.util.hash_pandas_object(ranking[['decision_time','pair','eligible','adjusted_rank']],index=False).values.tobytes()).hexdigest().upper()
    if membership!=inputs['membership_bounded_sha256']:raise ValueError('PIT_MEMBERSHIP_SHA_DRIFT')
    eligibility=BroadEligibilityIndex.build(ranking);btc=raw_frame(repo,'BTC-USDT')
    # Scanner needs actual transition rows (not reset/event proxies).
    market_trans,_,_,_=det.scan_wyckoff('BTC-USDT',canonical_aggregate(repo,'BTC-USDT',btc,'4h'),btc,btc,eligibility,[],True,runtime_factory=OwnedWyckoffV4)
    reports=[];failures=[];remaining=[]
    for record in inputs['pairs']:
        pair=record['pair'];npfile=root/'cache'/(pair+'.npy');jsfile=root/'cache'/(pair+'.events.json')
        try:
            doc=json.loads(jsfile.read_text()) if resume and jsfile.exists() else None
            arr=np.load(npfile,mmap_mode='r') if doc and npfile.exists() else None
            if doc and doc['input_sha']==record['bounded_sha256'] and arr.shape==(len(CLOCK),10):
                if doc.get('producer_schema')!=2:
                    raw=raw_frame(repo,pair)
                    if bounded_sha(raw)!=record['bounded_sha256']:raise ValueError('CACHE_REPAIR_INPUT_DRIFT')
                    h4=canonical_aggregate(repo,pair,raw,'4h');d1=canonical_aggregate(repo,pair,raw,'1d')
                    base=[e for e in doc['intents'] if e['system_id'] not in (H1,H2,H3)]
                    checkpoints={utc(e['timestamp']) for e in base if e['system_id']==HA}
                    _,corr=elliott_intents(pair,raw,h4,d1,eligibility,checkpoints)
                    doc['intents']=base+make_hybrids(pair,raw,btc,doc['transitions'],doc['events'],base,corr)
                    # Preserve the original pre-economic stage authority.
                    original=jsfile.with_suffix('.pre_correction_kind_repair.json')
                    if not original.exists():shutil.copyfile(jsfile,original)
                    doc['producer_schema']=2;save(jsfile,doc);fast.clear_pair_caches()
                report={'pair':pair,'intents':len(doc['intents']),'errors':doc['errors'],
                    'cache_sha':sha(npfile),'events_sha':sha(jsfile),'reused_completed_pre_economic_cache':True}
                reports.append(report);failures+=doc['errors'];continue
        except (ValueError,KeyError,OSError):pass
        remaining.append(record)
    print('RESUME_CACHED_PAIRS',len(reports),'REMAINING',len(remaining),flush=True)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(pair_worker,str(repo),r,market_trans):r['pair'] for r in remaining}
        for f in as_completed(futures):
            try: report=f.result();reports.append(report);failures+=report['errors']
            except Exception:failures.append({'pair':futures[f],'grammar':'ALL','trace':traceback.format_exc()})
            if len(reports)%10==0:print('STAGED',len(reports),'/',len(inputs['pairs']),'errors',len(failures),flush=True)
    save(root/'staging_audit.json',{'pairs':reports,'errors':failures,'protected_rows_loaded':0})
    if stage_only:
        print('STAGING_COMPLETE',len(reports),'ERRORS',len(failures),flush=True)
        return {'status':'STAGING_COMPLETE','pairs':len(reports),'errors':len(failures)}
    arrays={r['pair']:np.load(root/'cache'/(r['pair']+'.npy'),mmap_mode='r') for r in reports}
    bar_audit={}
    for pair in list(arrays):
        try:bar_audit[pair]=validate_cached_bars(arrays[pair])
        except ValueError as ex:
            failures.append({'pair':pair,'grammar':'ALL','trace':str(ex)})
            bar_audit[pair]={'status':'QUARANTINED_INVALID_BAR_AUTHORITY','error':str(ex)}
            del arrays[pair]
    save(root/'cached_bar_schema_audit.json',bar_audit)
    docs={}
    for pair in arrays:
        # Preserve the full, SHA-bound authority on disk. Execution needs only
        # intents, causal pivots, weekly context and the two native WY events.
        # Large scan transcripts are not retained as duplicated live objects.
        d=json.loads((root/'cache'/(pair+'.events.json')).read_text())
        docs[pair]={key:d[key] for key in ('intents','daily_pivots','h4_pivots','weekly')}
        docs[pair]['events']=[e for e in d['events'] if e['system_id']==WY
            and e['event'] in {'DISTRIBUTION_RISK','LPS_HOLDS'}]
    del d
    if 'BTC-USDT' not in arrays:raise ValueError('BTC_CONTEXT_UNAVAILABLE')
    # Source weekly broad-confirmation, no forecast/outcome selection.
    weekly={}
    for p,d in docs.items():
        for row in d['weekly']:weekly.setdefault(row['decision_time'],{})[p]=row['ret72']
    dow=rt.DowRuntime();btc_d=trend_series(canonical_aggregate(repo,'BTC-USDT',btc,'1d'));btc4=trend_series(canonical_aggregate(repo,'BTC-USDT',btc,'4h'))
    for st,returns in sorted(weekly.items()):
        t=utc(st);before=dow.state;new=dow.update(asof(btc_d,t),asof(btc4,t),rt.broad_equal_weight_confirmation(returns),False)
        lows=[p for p in btc4[2] if p.kind=='L' and p.confirm_time<=t]
        if new=='RECONFIRMED_BULL' and before!=new and lows and eligibility.eligible('BTC-USDT',t):
            e=det.event_row(DO,'BTC-USDT',t,'V4_RECONFIRMED_BULL','EXPERIMENTAL_DIAGNOSTIC',True,
                {'stop':lows[-1].price,'target':None,'stop_owner':str(lows[-1].pivot_time)})
            e['metadata']=json.dumps({'stop':lows[-1].price,'target':1e100,'stop_owner':str(lows[-1].pivot_time)})
            docs['BTC-USDT']['intents'].append(e)
    save(root/'dow_causal_intents.json',docs['BTC-USDT']['intents'][-20:])
    results=[]
    for g in GRAMMARS:
        for label,cost in (('1X',.0025),('2X',.005)):
            print('REPLAY',g,label,flush=True)
            try:
                r=replay_arm(g,cost,arrays,docs,root,m['protocol_sha'])
                dependencies={H1:(WY,CL),H2:(WY,ICT),H3:(HA,EL)}.get(g,(g,))
                error_owners=(*dependencies,'ALL',*(['HYBRIDS'] if g in (H1,H2,H3) else []))
                r['source_coverage_complete']=(len(reports)==len(inputs['pairs'])
                    and not any(e['grammar'] in error_owners for e in failures))
            except Exception:
                r={'grammar':g,'cost':cost,'status':'TECHNICAL_FAIL_NO_SCIENTIFIC_CONCLUSION','error':traceback.format_exc(),
                    'net':None,'mdd':None,'qualification':'FAIL_CLOSED'}
            results.append(r);save(root/'results_checkpoint.json',results)
            print('RESULT',g,label,r.get('net'),r['status'],flush=True)
    result={'task':TASK,'status':'ALL_ARMS_REPLAY_COMPLETE' if all(r['net'] is not None for r in results) else 'PARTIAL_REPLAY_COMPLETION',
        'results':results,'doctrine_and_gate2_closed':False,'gate3_qualification_executed':False,
        'unresolved':protocol()['unresolved'],'staging_errors':len(failures),'2024_access':False,'2025_access':False,
        'production_change':False,'threshold_search':False,'prior_V3_preserved':True}
    save(root/'canonical_result.json',result)
    pd.DataFrame([{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in results]).to_csv(root/'scorecard.csv',index=False)
    save(root/'output_manifest.json',{'files':{str(p.relative_to(root)).replace('\\','/'):sha(p) for p in root.rglob('*')
        if p.is_file() and p.name!='output_manifest.json'}})
    print('FINAL',result['status'],flush=True)
    return result
