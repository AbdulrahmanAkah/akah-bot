"""Frozen V5 research adaptations. Not school fidelity or historical execution certification.

V4 is imported as an immutable accounting/data authority, never edited. No model,
outcome-selected threshold, future path label, pair whitelist or production hook.
"""
from __future__ import annotations

import bisect
import copy
import csv
import gzip
import hashlib
import json
import math
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from decimal import Decimal, ROUND_FLOOR
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from . import full_replay_v4 as v4
from . import akah_full_fidelity_runtime_v1 as rt
from . import akah_replay_ready_detectors_v1 as det
from . import akah_native_replay_engine_v1 as eng
from .akah_foundation_core_v1r1 import (raw_frame, canonical_aggregate, utc,
    load_broad_eligibility, BroadEligibilityIndex)
from .gate3_market_v3 import bounded_sha, trend_series, asof, campaign_attribution

TASK = 'AKAH_SIX_SCHOOL_HYBRID_REPAIR_AND_REPLAY_MEGA_V5'
REL = Path('governance/six_school_hybrid_repair_replay_v5')
OLD = v4.REL
GRAMMARS = v4.GRAMMARS
WY, ICT, HA, CL, EL, DO, H1, H2, H3 = GRAMMARS
CLOCK = v4.CLOCK
DATA_START = v4.DATA_START
sha, save = v4.sha, v4.save


def protocol():
    return {
        'task': TASK, 'scope': 'PROSPECTIVE_RESEARCH_ADAPTATIONS_ALL_NINE_NOT_FULL_SCHOOL_CERTIFICATION',
        'period': [str(CLOCK[0]), str(CLOCK[-1])], 'grammars': list(GRAMMARS),
        'source': 'SHA-bound V4 causal intents/events/bars; bounded warmup readers only to recover original pivot indices and completed D',
        'controls': 'V4 immutable; 2022/2023 already exposed, not fresh validation; no outcome-directed repair after freeze',
        'costs': {'1X': .0025, '2X': .005}, 'initial_equity': 100000,
        'risk': v4.protocol()['risk'],
        'quantity': 'CONTINUOUS_PRICE_EXPERIMENT; identity price, computational quantity floor 1e-12, minimum entry 50 USDT. NOT historical tick/lot authority',
        'capacity': 'V4 .005 prior completed 24h turnover; entry quantity also bounded by half of min(current capacity, minimum observed capacity over prior 24h). Current buy/sell share capacity. No future-liquidity guarantee',
        'geometry': 'At executable open AFTER price normalization: finite final objective must have strictly positive net-per-unit after both fees. Non-economic TGT1 omitted; no RR threshold search',
        'classical': 'Trade stop=acceptance-bar low for THROWBACK, or latest post-breakout confirmed 4H low for HIGHER_LOW; frozen base support remains context invalidation. No stop replacement when that source is missing',
        'campaign_mode': 'CL TREND only if source prior_trend UP and completed 1D/4H trend UP at entry; H1 TREND. EL W3/W5 TREND. H3 TREND with count owner stop, not mixed min objectives/max stops. Others finite except WY/DO native trend',
        'trend_management': 'Objective is checkpoint, not liquidation. Only confirmed post-entry higher H followed by later higher L earns stop ratchet; owner timeframe, nondecreasing, low must exceed prior L and old stop and be below completed close. No MFE profit threshold. Confirmed protected structure failure exits; hard stop first',
        'harmonic': 'Existing classify_harmonic family rules evaluated at observed completed D=min low from terminal through confirmation. Later close above terminal-bar HIGH required as new structural-confirmation research grammar. Unbound FIVE_ZERO/SHARK abstain. Type-II uses its actual later retest low, not old D',
        'harmonic_management': 'Finite 50/50 planned exits only if TGT1 net-positive; otherwise 100% TGT2. After TGT1, campaign BE=(total buy outlay-net realized sales)/(remaining quantity*(1-exit_fee)); ratchet only if BE below observed price, applies next bar',
        'elliott': 'Existing chosen count remains diagnostic. W3/W5 source pivot sequence recovered exactly; W3 trade stop W2, W5 W4. First completed close above W1/W3 while local low unbroken activates, no count resurrection. Count invalidation stored separately. Parent-child doctrine UNRESOLVED',
        'wyckoff': 'Require observed current-cause B range with support<resistance, source readiness, live owned evidence and no subsequent RESET. No inherited reaccumulation cause, no loosening readiness. New cause doctrine remains UNRESOLVED',
        'ict': 'Preserve raid->later MSS/FVG->later retracement and native NY16/bearish MSS. No automatic removal of intraday expiry. ICT-trigger trend owner deferred until a separately bound higher-structure grammar exists',
        'dow': 'Experimental standalone adapter, not orthodox claim: source broad confirmation held asof latest weekly checkpoint, primary/secondary updates at each completed 4H; stop latest confirmed BTC H4 L, primary reversal exit',
        'hybrids': {'H1': 'Live WY markup + source CL trigger, CL local structure owns trend management',
            'H2': 'Live source base + ICT failed-auction trigger, finite ICT owner, never silently promoted',
            'H3': 'Same-checkpoint corrective count + revalidated harmonic location + terminal-high confirmation; count stop owns campaign, conflict with observed D rejects'},
        'selector': v4.protocol()['selection'],
        'clock': v4.protocol()['execution'],
        'outputs': ['campaigns.csv', 'fills.csv', 'position_decisions.csv.gz', 'accepted_intents.csv',
            'candidate_intents.csv.gz', 'rejections.csv.gz', 'hourly_equity.csv.gz', 'metrics.json'],
        'unresolved': {'historical_tick_lot': 'UNRESOLVED', 'WY_reaccumulation_cause': 'UNRESOLVED',
            'HA_full_matrix': 'UNRESOLVED; source-classified regular families only in this adaptation',
            'EL_parent_child': 'DIAGNOSTIC_ONLY', 'DO_school_fidelity': 'DIAGNOSTIC_ONLY',
            'independent_reserve_review': 'NOT_EXECUTED; all economics experimental'},
        '2024_access': False, '2025_access': False, 'production_change': False,
        'threshold_search': False, 'profit_guarantee': False,
    }


class ContinuousRule:
    """Numerical simulation precision; must never claim historical exchange rules."""
    lot = Decimal('0.000000000001')
    authority_kind = 'CONTINUOUS_PRICE_EXPERIMENT_NOT_EXCHANGE_AUTHORITY'
    def __init__(self, pair, source_sha):
        self.pair, self.source_sha256 = pair, source_sha
    def price(self, price, *, buy):
        return float(price)
    def normalize(self, pair, quantity, price, now, *, exit=False):
        if pair != self.pair or not self.source_sha256 or not DATA_START <= utc(now) < v4.DATA_CUTOFF:
            return 0.
        if not all(math.isfinite(z) and z > 0 for z in (quantity, price)): return 0.
        q = float((Decimal(str(quantity))/self.lot).to_integral_value(rounding=ROUND_FLOOR)*self.lot)
        return q if exit or q*price >= 50 else 0.
    def normalize_exit(self, pair, quantity, price, now):
        return self.normalize(pair, quantity, price, now, exit=True)


def target_net_per_unit(entry, target, rate):
    return target*(1-rate)-entry*(1+rate)


def campaign_breakeven(fills, campaign_id, remaining_quantity, rate):
    if remaining_quantity <= 0: return None
    cash = sum(f['cash_delta'] for f in fills if f['campaign_id'] == campaign_id)
    return max(0., -cash/(remaining_quantity*(1-rate)))


def earned_stop(pivots, entry_at, close_at, current_price, old_stop):
    """Higher H then a higher L, both observed post-entry and confirmed by close."""
    if isinstance(pivots,tuple):
        ht,hs,lt,ls=pivots; now=utc(close_at)
        hn=bisect.bisect_right(ht,now);ln=bisect.bisect_right(lt,now)
        highs=hs[max(0,hn-2):hn];lows=ls[max(0,ln-2):ln]
    else:
        ps = [p for p in pivots if utc(p['confirm_time']) <= utc(close_at)]
        highs = [p for p in ps if p['kind'] == 'H']
        lows = [p for p in ps if p['kind'] == 'L']
    if len(highs) < 2 or len(lows) < 2: return old_stop, None
    h0, h1 = highs[-2:]; l0, l1 = lows[-2:]
    valid = (utc(h1['pivot_time']) > utc(entry_at) and utc(l1['pivot_time']) > utc(h1['pivot_time'])
        and h1['price'] > h0['price'] and l1['price'] > l0['price']
        and old_stop < l1['price'] < current_price)
    return (float(l1['price']), str(l1['confirm_time'])) if valid else (old_stop, None)


def pivot_dict(p):
    return {'kind': p.kind, 'price': float(p.price), 'pivot_time': str(p.pivot_time),
        'confirm_time': str(p.confirm_time), 'index': int(p.index)}


def stage_pair(repo_string, record):
    """No economic labels. Reconstruct missing source coordinates from bounded frames."""
    repo = Path(repo_string); pair = record['pair']; v4.install_fast()
    original = repo/OLD/'cache'/(pair+'.events.json')
    doc = json.loads(original.read_text()); raw = raw_frame(repo, pair)
    if bounded_sha(raw) != record['bounded_sha256'] or doc['input_sha'] != record['bounded_sha256']:
        raise ValueError('BOUNDED_SOURCE_HASH_DRIFT:'+pair)
    h4 = canonical_aggregate(repo, pair, raw, '4h')
    d1 = canonical_aggregate(repo, pair, raw, '1d')
    frames = {'1H': raw, '4H': h4, '1D': d1}
    pivot_objects = {d: rt.confirmed_pivots_2l2r(det.add_indicators(f)) for d,f in frames.items()}
    pivs = {d:[pivot_dict(p) for p in ps] for d,ps in pivot_objects.items()}
    confirmation_times={d:[utc(p.confirm_time) for p in ps] for d,ps in pivot_objects.items()}
    dirs = {'4H': trend_series(h4), '1D': trend_series(d1)}
    by_index = {d: {p['index']: p for p in ps} for d, ps in pivs.items()}
    ts = {d: pd.DatetimeIndex(pd.to_datetime(f.timestamp, utc=True)) for d, f in frames.items()}
    eligibility = BroadEligibilityIndex.build(load_broad_eligibility(repo))
    terminals = {json.loads(e['metadata']).get('projection_id'): e for e in doc['events']
        if e['system_id'] == HA and e['stage'] == 'TERMINAL'}
    transformed = []; rejects = []
    for e in doc['intents']:
        t = utc(e['timestamp']); g = e['system_id']
        if not DATA_START <= t < CLOCK[-1]: continue
        m = json.loads(e['metadata']); source_owner = m.get('management_owner', g)
        m.update({'v4_source_identity': hashlib.sha256(json.dumps(e, sort_keys=True, default=v4.encode).encode()).hexdigest(),
            'source_management_owner': source_owner, 'campaign_mode': 'LIMITED_REBOUND',
            'management_degree': '4H', 'count_invalidation': m.get('stop') if g in (EL, H3) else None})
        reason = None
        if g in (CL, H1):
            j = int(ts['4H'].searchsorted(t, side='right'))-1
            if j < 0 or ts['4H'][j] != t: reason = 'ACCEPTANCE_BAR_AUTHORITY_MISSING'
            elif 'THROWBACK' in e['event']: m['stop'] = float(h4.iloc[j].low)
            elif 'NO_RETEST_CONTINUATION' in e['event']:
                ls = [p for p in pivs['4H'] if p['kind'] == 'L' and utc(p['confirm_time']) <= t
                    and utc(p['pivot_time']) > utc(m['breakout_time'])]
                if not ls: reason = 'OWNED_ACCEPTANCE_HL_MISSING'
                else: m['stop'] = ls[-1]['price']
            else: reason = 'ACCEPTANCE_TRIGGER_UNBOUND'
            trend = g == H1 or (m.get('prior_trend') == 'UP' and asof(dirs['4H'], t) == 'UP'
                and asof(dirs['1D'], t) == 'UP')
            if trend: m['campaign_mode'] = 'TREND_CAMPAIGN'
        elif g in (HA, H3):
            pid = m['projection_id']; family, indices = pid.split(':', 1)
            indices = [int(z) for z in indices.split('-')]
            ps = [by_index['4H'].get(z) for z in indices]
            te = terminals.get(pid)
            if family not in {'GARTLEY','BAT','ALTERNATE_BAT','BUTTERFLY','CRAB','DEEP_CRAB','ABCD'}:
                reason = 'UNBOUND_HARMONIC_FAMILY'
            elif any(p is None or utc(p['confirm_time']) > t for p in ps) or te is None:
                reason = 'HARMONIC_SOURCE_COORDINATES_MISSING'
            else:
                terminal = utc(te['timestamp']); j = int(ts['4H'].searchsorted(t, side='right'))-1
                a = int(ts['4H'].searchsorted(terminal, side='left'))
                if not terminal < t or j < a: reason = 'TERMINAL_CONFIRMATION_ORDER'
                else:
                    # Type II has a new retest; Type I retains all observed terminal->confirmation lows.
                    D = float(h4.iloc[j].low) if 'TYPE_II' in e['event'] else float(h4.iloc[a:j+1].low.min())
                    X,A,B,C = [p['price'] for p in ps]
                    matches = rt.classify_harmonic(X,A,B,C,D)
                    match = next((z for z in matches if z.pattern == family), None)
                    if match is None: reason = 'OBSERVED_D_FAMILY_GEOMETRY_NOT_VALID'
                    elif float(h4.iloc[j].close) <= float(h4.iloc[a].high):
                        reason = 'TERMINAL_HIGH_NOT_RECLAIMED'
                    elif D <= match.make_or_break: reason = 'HARMONIC_INVALIDATION_ALREADY_OBSERVED'
                    else:
                        m.update({'observed_D': D, 'terminal_available_at': str(terminal),
                            'geometry_known_at': str(t), 'ratios': match.metadata,
                            'stop': match.make_or_break, 'targets': [D+.382*abs(A-D), D+.618*abs(A-D)]})
                        if g == H3:
                            degree, kind, count_indices = m['count_id'].split(':', 2)
                            cp = [by_index[degree].get(int(z)) for z in count_indices.split('-')]
                            if any(p is None or utc(p['confirm_time']) > t for p in cp):
                                reason = 'CORRECTIVE_COUNT_COORDINATES_MISSING'
                            else:
                                inv = cp[-1]['price']
                                if inv >= D: reason = 'COUNT_LOCATION_OWNER_CONFLICT'
                                else:
                                    m.update({'stop': inv, 'count_invalidation': inv,
                                        'management_degree': degree, 'campaign_mode': 'TREND_CAMPAIGN'})
        elif g == EL:
            degree, kind, indices = m['count_id'].split(':', 2)
            ps = [by_index[degree].get(int(z)) for z in indices.split('-')]
            if any(p is None or utc(p['confirm_time']) > t for p in ps): reason = 'COUNT_COORDINATES_MISSING'
            elif kind in {'W3','W5'}:
                local_stop = ps[-1]['price']; activation = ps[-2]['price']
                start = int(ts['1H'].searchsorted(t, side='left')); trigger = None
                for j in range(start, len(raw)):
                    rr = raw.iloc[j]; at = utc(rr.timestamp)
                    if at >= CLOCK[-1] or float(rr.low) <= local_stop: break
                    if float(rr.close) > activation:
                        trigger = at; break
                if trigger is None: reason = 'OWNED_MOTIVE_TRIGGER_NOT_COMPLETED_BEFORE_INVALIDATION'
                else:
                    t = trigger
                    # Delayed activation cannot inherit a formerly valid consensus blindly.
                    snapshot={}
                    for d,ps0 in pivot_objects.items():
                        n=bisect.bisect_right(confirmation_times[d],t);sl=ps0[max(0,n-24):n]
                        cs=rt.enumerate_impulse_counts(sl,d,t)+rt.enumerate_corrective_counts(sl,d,t)
                        snapshot[d]=[c for c in cs if (c.direction=='BULLISH' and float(raw.iloc[j].close)>c.invalidation)
                            or (c.direction=='BEARISH' and float(raw.iloc[j].close)<c.invalidation)]
                    owner=v4.material_owner(snapshot,t,float(raw.iloc[j].close))
                    if owner is None or owner.count_id!=m['count_id']:
                        reason='COUNT_CONSENSUS_NOT_LIVE_AT_ACTIVATION'
                    else:
                        m.update({'count_available_at': e['timestamp'], 'stop': local_stop,
                            'activation_boundary': activation, 'campaign_mode': 'TREND_CAMPAIGN',
                            'management_degree': degree})
            else: m['management_degree'] = degree
        elif g == WY:
            # BASE_FORMED is proved from a range observation, not the old unconditional True flag.
            cause = m.get('cause_id')
            bs = [z for z in doc['transitions'] if z['system_id'] == WY
                and z['to_state'] == 'B_CAUSE_BUILDING' and utc(z['timestamp']) <= t]
            scs = [z for z in doc['events'] if z['system_id'] == WY and z['event'] == 'SELLING_CLIMAX'
                and utc(z['timestamp']) <= t]
            if not bs or not scs: reason = 'OBSERVED_BASE_OR_CAUSE_MISSING'
            else:
                b = bs[-1]; bm = json.loads(b['metadata']); sc = scs[-1]
                cid = hashlib.sha256(f'{pair}|ACCUM|{utc(sc["timestamp"])}'.encode()).hexdigest()
                if cause != cid or not (0 < bm.get('support',0) < bm.get('resistance',0)):
                    reason = 'CURRENT_CAUSE_BASE_NOT_BOUND'
                else:
                    m.update({'base_support': bm['support'], 'base_resistance': bm['resistance'],
                        'base_available_at': b['timestamp'], 'campaign_mode': 'NATIVE_TREND'})
        if reason:
            rejects.append({'pair': pair, 'grammar': g, 'available_at': str(t),
                'source_identity': m['v4_source_identity'], 'reason': reason})
            continue
        m['objective_checkpoint'] = m.get('target', m.get('targets', [None])[-1])
        transformed.append({**e, 'timestamp': str(t), 'broad_eligible': eligibility.eligible(pair,t),
            'event': 'V5_'+e['event'], 'metadata': json.dumps(m, default=v4.encode, allow_nan=False)})
    out = {k:doc[k] for k in ('daily_pivots','h4_pivots','weekly')}
    out.update({'intents': transformed, 'management_pivots': pivs,
        'events': [z for z in doc['events'] if z['system_id'] == WY
            and z['event'] in {'LPS_HOLDS','DISTRIBUTION_RISK'}],
        'source_event_sha': sha(original), 'bounded_raw_sha': record['bounded_sha256'], 'rejects': rejects})
    path = repo/REL/'cache'/(pair+'.events.json'); save(path,out)
    v4.fast.clear_pair_caches()
    return {'pair':pair,'source_event_sha':out['source_event_sha'],'events_sha':sha(path),
        'input_sha':record['bounded_sha256'],'intents':len(transformed),'staging_rejects':len(rejects)}


class Portfolio(v4.ResearchPortfolio):
    def __init__(self, cost, rules):
        super().__init__(cost,rules); self.decisions=[]; self.phase='OPEN'; self.accepted=[]
    def sell(self, tid, price, t, cap, reason, fraction=1.):
        n=len(self.k.fills); result=super().sell(tid,price,t,cap,reason,fraction)
        for f in self.k.fills[n:]: f['execution_phase']=self.phase
        return result
    def record(self, tid, at, action, old, new, extra=None):
        p=self.k.positions.get(tid)
        if p:
            self.decisions.append({'time':str(at),'campaign_id':p['campaign_id'],'identity':p['episode']['identity'],
                'pair':p['episode']['pair'],'action':action,'old_stop':old,'new_stop':new,
                'applies_from':str(at),'known_at':str(at),'execution_phase':self.phase,
                'state':p['episode'].get('lifecycle_state','ENTERED_UNCONFIRMED'), **(extra or {})})


def harmonic_manage(portfolio, tid, high, mark, close_at, capacity):
    p=portfolio.k.positions[tid]; r=p['episode']; old=p['current_stop']; q=p['qty_current']
    t1,t2=map(float,r['targets'])
    if 'tgt1_quantity' not in r:
        r['tgt1_quantity']=float((Decimal(str(q))/2/portfolio.rules[r['pair']].lot).to_integral_value(rounding=ROUND_FLOOR)*portfolio.rules[r['pair']].lot)
        r['tgt1_sold']=0.
    if r.get('tgt1_disabled'): r['tgt1_done']=True
    if not r.get('tgt1_done') and high>=t1:
        before=p['qty_current']; need=max(0.,r['tgt1_quantity']-r['tgt1_sold'])
        portfolio.sell(tid,t1,close_at,capacity,'TGT1',min(1.,need/before))
        r['tgt1_sold']+=before-portfolio.k.positions.get(tid,{}).get('qty_current',0.)
        r['tgt1_done']=r['tgt1_sold']>=r['tgt1_quantity']-1e-10
    if tid not in portfolio.k.positions:return
    if r.get('tgt1_done') and not r.get('tgt1_disabled'):
        cid=p['campaign_id']; remain=sum(z['qty_current'] for z in portfolio.k.positions.values() if z['campaign_id']==cid)
        be=campaign_breakeven(portfolio.k.fills,cid,remain,portfolio.k.exit_cost_rate)
        if be is not None and old<be<mark:
            p['current_stop']=be; portfolio.record(tid,close_at,'CAMPAIGN_BREAKEVEN',old,be)
    if tid in portfolio.k.positions and r.get('tgt1_done') and high>=t2:
        portfolio.sell(tid,t2,close_at,capacity,'TGT2')


def normalize(e):
    r=v4.normalize_intent(e)
    if r and r.get('campaign_mode') in {'TREND_CAMPAIGN','NATIVE_TREND'}:
        r['target']=1e100
    return r


def replay_arm(grammar,cost,arrays,events,root,input_sha):
    rules={p:ContinuousRule(p,input_sha) for p in arrays}; portfolio=Portfolio(cost,rules); kernel=portfolio.k
    candidates={}; native={}; daily={}; management={}; last={}; equity=[]; missing=[]; staged_rejects=[]
    for pair,doc in events.items():
        lows=[z for z in doc['daily_pivots'] if z['kind']=='L']
        daily[pair]=([utc(z['confirm_time']) for z in lows],[z['price'] for z in lows])
        management[pair]={}
        for degree,ps in doc['management_pivots'].items():
            hs=[z for z in ps if z['kind']=='H'];ls=[z for z in ps if z['kind']=='L']
            management[pair][degree]=([utc(z['confirm_time']) for z in hs],hs,
                [utc(z['confirm_time']) for z in ls],ls)
        native[pair]={}
        for e in doc['events']:native[pair].setdefault(str(utc(e['timestamp'])),[]).append(e)
        staged_rejects += [z for z in doc.get('rejects',[]) if z['grammar']==grammar]
        for e in doc['intents']:
            if e['system_id']!=grammar:continue
            r=normalize(e)
            if r:candidates.setdefault(int((utc(r['ready_at'])-DATA_START)/pd.Timedelta(hours=1)),[]).append(r)
    all_requests=[r for batch in candidates.values() for r in batch]
    # Purely causal admission inventory constraint. No future exit capacity is read.
    capacity_min={p:pd.Series(a[:,4]).rolling(24,min_periods=1).min().to_numpy() for p,a in arrays.items()}
    for k,t in enumerate(CLOCK):
        portfolio.phase='OPEN'; requests=candidates.get(k,[]); btc=arrays['BTC-USDT']
        held={p['episode']['pair'] for p in kernel.positions.values()}
        wanted=held|{r['pair'] for r in requests}|{'BTC-USDT'}
        prices={p:float(arrays[p][k,0]) for p in wanted if np.isfinite(arrays[p][k,0])}
        last.update(prices); cap={p:max(0.,float(arrays[p][k,4])) if np.isfinite(arrays[p][k,4]) else 0. for p in prices}
        absent=held-set(prices)
        if absent:portfolio.risk_pass=False;missing.append({'time':str(t),'pairs':sorted(absent)})
        for tid,p in list(kernel.positions.items()):
            r=p['episode']; pair=r['pair']
            if pair not in prices:continue
            px=prices[pair]
            if px<=p['current_stop']:portfolio.sell(tid,px,t,cap,'STOP_GAP')
            elif tid in portfolio.pending:portfolio.sell(tid,px,t,cap,portfolio.pending[tid])
            elif r['management_owner']==HA and r['campaign_mode']=='LIMITED_REBOUND' and px>=r['targets'][0]:
                harmonic_manage(portfolio,tid,px,px,t,cap)
            elif r['campaign_mode']=='LIMITED_REBOUND' and r['management_owner']!=HA and px>=r['target']:
                portfolio.sell(tid,r['target'],t,cap,'OBJECTIVE_GAP')
        safe=not absent and portfolio.safety(t,prices,cap) and not portfolio.pending
        batch={}
        for r in requests:batch.setdefault(r['pair'],[]).append(r)
        ordered=[]
        for pair,rs in batch.items():
            if len({r['owner_structure_id'] for r in rs})>1:
                portfolio.rejects.append({'time':str(t),'pair':pair,'reason':'SAME_ASSET_OWNER_CONFLICT'});continue
            ordered.append(min(rs,key=lambda r:r['identity']))
        ordered.sort(key=lambda r:(-cap.get(r['pair'],0),r['identity']))
        for original in ordered:
            r=copy.deepcopy(original); pair=r['pair']; identity=r['identity']; reason=None
            if identity in portfolio.seen:reason='NO_RESURRECTION'
            portfolio.seen.add(identity)
            if reason is None and (not safe or pair not in prices):reason='RISK_OR_PRICE_UNAVAILABLE'
            if reason is None and not v4.router_ok(arrays[pair],daily['BTC-USDT'],daily[pair],k,
                {'BTC-USDT':prices.get('BTC-USDT',0),'PAIR':prices[pair]},market_direction=btc[k,8]):reason='ROUTER_VETO'
            if reason is None:
                px=rules[pair].price(prices[pair],buy=True); r['stop']=rules[pair].price(r['stop'],buy=False)
                if not 0<r['stop']<px<r['target']:reason='EXECUTABLE_GEOMETRY_INVALID'
                elif r['campaign_mode']=='LIMITED_REBOUND' and target_net_per_unit(px,r['target'],cost/2)<=0:
                    reason='FINAL_OBJECTIVE_CANNOT_COVER_COSTS'
                elif r['management_owner']==HA and r['campaign_mode']=='LIMITED_REBOUND':
                    r['tgt1_disabled']=target_net_per_unit(px,float(r['targets'][0]),cost/2)<=0
                    if not r['tgt1_disabled'] and px>=r['targets'][0]:reason='FIRST_OBJECTIVE_PASSED'
            if reason:
                portfolio.rejects.append({'time':str(t),'pair':pair,'identity':identity,'reason':reason});continue
            r.update({'entry_open':px,'lifecycle_state':'ENTERED_UNCONFIRMED'})
            staged=r['management_owner']==WY and r['source_event']=='V5_SPRING_TEST'
            existing=[p for p in kernel.positions.values() if p['episode']['pair']==pair]
            is_add=bool(existing and not staged and r['management_owner']==WY and existing[0]['episode'].get('staged')
                and existing[0]['episode']['owner_structure_id']==r['owner_structure_id'])
            cid=existing[0]['campaign_id'] if is_add else identity; r['staged']=staged
            observed=capacity_min[pair][k]
            admission_capacity=min(cap.get(pair,0),observed)/2 if np.isfinite(observed) else 0.
            ok,reason=kernel.admit(r,lambda p,at:prices[p],t,admission_capacity,rules[pair].normalize,cid,
                funded_ready=True,is_add=is_add,staged=staged)
            if ok:
                f=kernel.fills[-1]; f['execution_phase']='OPEN'; cap[pair]-=f['qty']*f['price']
                portfolio.accepted.append({**r,'campaign_id':cid,'entry_qty':f['qty'],'entry_fee':f['fee']})
            else:portfolio.rejects.append({'time':str(t),'pair':pair,'identity':identity,'reason':reason})
        if not math.isclose(100000.+sum(f['cash_delta'] for f in kernel.fills),kernel.cash,abs_tol=1e-5):
            raise ValueError('CASH_LEDGER_PARITY')
        s=kernel.snapshot(lambda p,at:last.get(p),t)
        if not s['valid']:raise ValueError('MTM_NO_MARK')
        equity.append({'time':str(t),'observation':'OPEN','equity':s['equity'],'cash':kernel.cash,
            'gross':s['gross'],'stop_risk':s['open_stop_risk'],'risk_limits_pass':eng.current_mtm_limits_ok(s)})
        if k==len(CLOCK)-1:break
        close=t+pd.Timedelta(hours=1); portfolio.phase='INTRABAR_OR_COMPLETED_CLOSE'
        for tid,p in list(kernel.positions.items()):
            r=p['episode']; pair=r['pair']; a=arrays[pair][k]
            if not np.isfinite(a[:4]).all():continue
            lo,hi,cl=float(a[2]),float(a[1]),float(a[3]); old=p['current_stop']; owner=r['management_owner']
            if lo<=old:portfolio.sell(tid,old,close,cap,'STRUCTURAL_STOP');continue
            if owner==HA and r['campaign_mode']=='LIMITED_REBOUND':
                harmonic_manage(portfolio,tid,hi,cl,close,cap);continue
            if r['campaign_mode']=='LIMITED_REBOUND' and hi>=r['target']:
                portfolio.sell(tid,r['target'],close,cap,'OBJECTIVE');continue
            pending=None
            if owner==ICT:
                action=rt.ict_manage_active(t=close,raid_time=utc(r['raid_time']),bar_low=lo,bar_high=hi,
                    raid_low=old,target=r['target'],bearish_mss=bool(a[5]))
                if action in {'BEARISH_MSS_EXIT_NEXT_OPEN','NY_1600_DAY_BOUNDARY'}:pending=action
            elif owner==WY:
                for e in native[pair].get(str(close),[]):
                    if e['event']=='DISTRIBUTION_RISK':pending='ASSET_DISTRIBUTION'
                    elif e['event']=='LPS_HOLDS':
                        low=json.loads(e['metadata']).get('low')
                        if low and old<low<cl:p['current_stop']=float(low)
                if btc[k,9]==8:
                    j=max(0,k-72); ap,bp=arrays[pair][j,3],btc[j,3]
                    if min(ap,bp)>0 and (cl/ap)/(btc[k,3]/bp)<=1:pending='MARKET_DISTRIBUTION_RS_LOSS'
            elif owner==DO:
                if btc[k,8]==-1:pending='DEFINITE_PRIMARY_REVERSAL'
            elif owner in (CL,EL,HA):
                if owner==CL and cl<=r.get('frozen_support',-math.inf):pending='PATTERN_CONTEXT_FAILURE'
                degree=r.get('management_degree','4H')
                new,known=earned_stop(management[pair][degree],utc(r['ready_at']),close,cl,old)
                if new>old:
                    p['current_stop']=new; r['lifecycle_state']='STRUCTURALLY_CONFIRMED'
                    if r['campaign_mode']=='TREND_CAMPAIGN':r['lifecycle_state']='TREND_ACTIVE'
                if owner==CL and a[6]:pending=pending or 'CONFIRMED_H4_REVERSAL'
                if owner==EL and cl<=r.get('count_invalidation',-math.inf):pending='COUNT_INVALIDATED'
            else:raise ValueError('UNBOUND_OWNER:'+owner)
            if owner in (WY,DO):
                new,_=earned_stop(management[pair]['4H'],utc(r['ready_at']),close,cl,p['current_stop'])
                if new>p['current_stop']:
                    p['current_stop']=new;r['lifecycle_state']='TREND_ACTIVE'
            if p['current_stop']<old:raise ValueError('STOP_LOOSENED')
            portfolio.record(tid,close,'EXIT_SIGNAL' if pending else 'HOLD',old,p['current_stop'],
                {'pending_reason':pending,'close_mark':cl,'mode':r['campaign_mode'],
                 'owner':owner,'objective_checkpoint':r.get('objective_checkpoint')})
            if pending:portfolio.pending[tid]=pending
        closes={p:float(arrays[p][k,3]) for p in wanted if np.isfinite(arrays[p][k,3])}
        s=kernel.snapshot(lambda p,at:closes.get(p,last.get(p)),close)
        ok=eng.current_mtm_limits_ok(s)
        if not ok:portfolio.risk_pass=False
        equity.append({'time':str(close),'observation':'CLOSE','equity':s['equity'],'cash':kernel.cash,
            'gross':s['gross'],'stop_risk':s['open_stop_risk'],'risk_limits_pass':ok})
    folder=root/(grammar+'__'+str(round(cost/.0025))+'X'); folder.mkdir(parents=True,exist_ok=True)
    eq=pd.DataFrame(equity); eq['time']=pd.to_datetime(eq.time,utc=True); eq=eq.set_index('time')
    campaigns,assets=campaign_attribution(kernel,last); opened={p['campaign_id'] for p in kernel.positions.values()}
    fills_by={}
    for f in kernel.fills:fills_by.setdefault(f['campaign_id'],[]).append(f)
    holdings=[]
    for c in campaigns:
        cid=c['campaign_id']; fs=fills_by[cid]; campaign=kernel.campaigns[cid]
        c.update({'closed':cid not in opened,'B0':campaign.initial_risk_budget,
            'committed_risk':campaign.committed_risk,'add_count':campaign.add_count,'first_entry_at':fs[0]['time']})
        if cid not in opened:
            c.update({'final_exit_at':fs[-1]['time'],'holding_hours':float((utc(fs[-1]['time'])-utc(fs[0]['time']))/pd.Timedelta(hours=1))})
            holdings.append(c['holding_hours'])
    net=float(eq.equity.iloc[-1]-100000)
    if not math.isclose(sum(c['net_including_fees_and_terminal_mtm'] for c in campaigns),net,abs_tol=1e-5):raise ValueError('CAMPAIGN_PARITY')
    pnl=np.array([c['net_including_fees_and_terminal_mtm'] for c in campaigns]); losses=pnl[pnl<0]; wins=pnl[pnl>0]
    annual={}; previous=100000.
    for y,es in eq.equity.resample('D').last().groupby(lambda x:x.year):
        annual[str(y)]=float(es.iloc[-1]-previous);previous=float(es.iloc[-1])
    result={'grammar':grammar,'cost':cost,'status':'REPLAY_COMPLETE_EXPERIMENTAL_NOT_FIDELITY_CERTIFIED',
        'net':net,'final_equity':float(eq.equity.iloc[-1]),'mdd':float((1-eq.equity/eq.equity.cummax().clip(lower=100000)).max()),
        'campaigns':len(campaigns),'filled_entries':sum(f['side']=='BUY' for f in kernel.fills),
        'closed_campaigns':sum(c['closed'] for c in campaigns),'open_positions':len(kernel.positions),
        'fees':sum(f['fee'] for f in kernel.fills),'annual_net':annual,
        'win_rate_including_terminal_MTM':float((pnl>0).mean()) if len(pnl) else None,
        'profit_factor_including_terminal_MTM':float(wins.sum()/-losses.sum()) if losses.sum()<0 else None,
        'mean_closed_holding_hours':float(np.mean(holdings)) if holdings else None,
        'risk_pass':portfolio.risk_pass,'capacity_blocked_full_exit_count':portfolio.capacity_blocked_full_exit_count,
        'missing_mark_hours':len(missing),'pending_exits_at_cutoff':len(portfolio.pending),
        'mean_gross_utilization':float((eq.gross/eq.equity).mean()),
        'turnover_over_mean_equity':sum(f['qty']*f['price'] for f in kernel.fills)/float(eq.equity.mean()),
        'leave_largest_campaign_net':net-max(pnl,default=0.),'leave_largest_asset_net':net-max(assets.values(),default=0.),
        'campaign_loss_exceeds_B0_count':sum(c['net_including_fees_and_terminal_mtm']<-c['B0'] for c in campaigns),
        'exit_reason_distribution':dict(pd.Series([f['reason'] for f in kernel.fills if f['side']=='SELL'],dtype=str).value_counts()),
        'qualification':'NOT_ELIGIBLE_UNCLOSED_FIDELITY_AND_HISTORICAL_EXCHANGE_RULES',
        '2024_access':False,'2025_access':False,'production_change':False}
    # Empty tables retain a declared schema; zero-funded arms still have auditable outputs.
    def table(rows,path,columns):
        frame=pd.DataFrame(rows) if rows else pd.DataFrame(columns=columns)
        for col in frame.columns:
            if len(frame) and frame[col].map(lambda x:isinstance(x,(dict,list))).any():
                frame[col]=frame[col].map(lambda x:json.dumps(x,default=v4.encode) if isinstance(x,(dict,list)) else x)
        frame.to_csv(path,index=False,compression='gzip' if str(path).endswith('.gz') else None)
    table(kernel.fills,folder/'fills.csv',['time','side','campaign_id','pair','identity','qty','price','fee','cash_delta','reason','execution_phase'])
    table(campaigns,folder/'campaigns.csv',['campaign_id','pair','net_including_fees_and_terminal_mtm','B0','closed'])
    table(portfolio.accepted,folder/'accepted_intents.csv',['identity','campaign_id','pair','ready_at','entry_open','stop','campaign_mode'])
    table(all_requests,folder/'candidate_intents.csv.gz',['identity','pair','ready_at','stop','campaign_mode'])
    table(portfolio.decisions,folder/'position_decisions.csv.gz',['time','campaign_id','identity','pair','action','old_stop','new_stop','known_at','applies_from'])
    table(staged_rejects+portfolio.rejects,folder/'rejections.csv.gz',['time','pair','identity','reason'])
    eq.to_csv(folder/'hourly_equity.csv.gz',compression='gzip');save(folder/'missing_marks.json',missing);save(folder/'metrics.json',result)
    return result


def freeze(repo):
    root=repo/REL
    if (root/'frozen_manifest.json').exists():raise PermissionError('ALREADY_FROZEN')
    if json.loads((repo/'.akah_bot/active_task.json').read_text())['task_id']!=TASK:raise PermissionError('GOVERNED_TASK_REQUIRED')
    root.mkdir(parents=True,exist_ok=True); save(root/'research_protocol.json',protocol())
    files={str(p.relative_to(repo)).replace('\\','/'):sha(p) for p in (repo/'src/spotbot/research/multi_school_fidelity').glob('*.py')}
    for relative in ('scripts/research/run_full_replay_v5.py','scripts/research/report_full_replay_v5.py','tests/research/test_full_replay_v5.py',
        'src/spotbot/data/aggregation.py','src/spotbot/data/timeframes.py','src/spotbot/data/validator.py','src/spotbot/core/models.py'):
        p=repo/relative; compile(p.read_text(encoding='utf-8-sig'),relative,'exec'); files[relative]=sha(p)
    for relative in files:compile((repo/relative).read_text(encoding='utf-8-sig'),relative,'exec')
    old=json.loads((repo/OLD/'staging_audit.json').read_text())
    for r in old['pairs']:
        for suffix,key in (('.npy','cache_sha'),('.events.json','events_sha')):
            if sha(repo/OLD/'cache'/(r['pair']+suffix))!=r[key]:raise ValueError('V4_CACHE_SHA_DRIFT')
    authority={str(p.relative_to(repo)).replace('\\','/'):sha(p) for p in
        (repo/OLD/'canonical_result.json',repo/OLD/'staging_audit.json',repo/OLD/'frozen_source_manifest.json',
         repo/v4.READY/'bounded_market_input_manifest.json',
         repo/v4.READY/'09_HISTORICAL_QUANTITY_AUTHORITY_MANIFEST.json')}
    save(root/'frozen_manifest.json',{'sources':files,'inputs':authority,'protocol_sha':sha(root/'research_protocol.json'),
        'python':sys.version,'packages':{p:version(p) for p in ('numpy','pandas','pyarrow','pytest')}})
    return root


def run(repo,workers=4):
    root=repo/REL; m=json.loads((root/'frozen_manifest.json').read_text())
    if json.loads((repo/'.akah_bot/active_task.json').read_text())['task_id']!=TASK:raise PermissionError('GOVERNED_TASK_REQUIRED')
    if any(sha(repo/p)!=s for section in ('sources','inputs') for p,s in m[section].items()):raise ValueError('FROZEN_AUTHORITY_DRIFT')
    if sha(root/'research_protocol.json')!=m['protocol_sha'] or m['python']!=sys.version or any(version(p)!=x for p,x in m['packages'].items()):raise ValueError('FROZEN_PROTOCOL_DEPENDENCY_DRIFT')
    if (root/'STARTED.json').exists():raise PermissionError('ALREADY_STARTED_NO_POSTHOC_RERUN')
    save(root/'STARTED.json',{'task':TASK,'frozen_manifest_sha':sha(root/'frozen_manifest.json')})
    inputs=json.loads((repo/v4.READY/'bounded_market_input_manifest.json').read_text()); reports=[];errors=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(stage_pair,str(repo),r):r['pair'] for r in inputs['pairs']}
        for f in as_completed(futures):
            try:reports.append(f.result())
            except Exception:errors.append({'pair':futures[f],'error':traceback.format_exc()})
            if (len(reports)+len(errors))%20==0:print('STAGED_V5',len(reports),'ERRORS',len(errors),flush=True)
    save(root/'staging_audit.json',{'pairs':reports,'errors':errors,'protected_rows_loaded':0})
    arrays={r['pair']:np.load(repo/OLD/'cache'/(r['pair']+'.npy'),mmap_mode='r') for r in reports}
    docs={r['pair']:json.loads((root/'cache'/(r['pair']+'.events.json')).read_text()) for r in reports}
    for a in arrays.values():v4.validate_cached_bars(a)
    if 'BTC-USDT' not in arrays:raise ValueError('BTC_SOURCE_UNAVAILABLE')
    # Dow broad frame unchanged; primary/secondary clock advanced causally, not outcome-selected.
    weekly={}
    for pair,d in docs.items():
        for row in d['weekly']:weekly.setdefault(utc(row['decision_time']),{})[pair]=row['ret72']
    btc=raw_frame(repo,'BTC-USDT'); d1=trend_series(canonical_aggregate(repo,'BTC-USDT',btc,'1d'))
    h4=trend_series(canonical_aggregate(repo,'BTC-USDT',btc,'4h')); dow=rt.DowRuntime()
    wt=sorted(weekly); last_broad=None; wi=0; eligibility=BroadEligibilityIndex.build(load_broad_eligibility(repo))
    for t in CLOCK:
        if t.hour%4:continue
        while wi<len(wt) and wt[wi]<=t:last_broad=weekly[wt[wi]];wi+=1
        if last_broad is None:continue
        before=dow.state;new=dow.update(asof(d1,t),asof(h4,t),rt.broad_equal_weight_confirmation(last_broad),False)
        lows=[p for p in h4[2] if p.kind=='L' and p.confirm_time<=t]
        if new=='RECONFIRMED_BULL' and before!=new and lows and eligibility.eligible('BTC-USDT',t):
            docs['BTC-USDT']['intents'].append(det.event_row(DO,'BTC-USDT',t,'V5_RECONFIRMED_BULL','DIAGNOSTIC',True,
                {'stop':lows[-1].price,'target':1e100,'campaign_mode':'NATIVE_TREND','management_degree':'4H',
                 'broad_known_at':str(wt[wi-1]),'stop_owner':str(lows[-1].pivot_time)}))
    save(root/'dow_intents.json',[e for e in docs['BTC-USDT']['intents'] if e['system_id']==DO])
    results=[]
    for g in GRAMMARS:
        for label,cost in (('1X',.0025),('2X',.005)):
            print('REPLAY_V5',g,label,flush=True)
            try:r=replay_arm(g,cost,arrays,docs,root,m['protocol_sha']);r['source_coverage_complete']=not errors and len(reports)==len(inputs['pairs'])
            except Exception:r={'grammar':g,'cost':cost,'net':None,'status':'TECHNICAL_FAIL_CLOSED','error':traceback.format_exc()}
            results.append(r);save(root/'results_checkpoint.json',results)
            print('RESULT_V5',g,label,r['net'],r['status'],flush=True)
    result={'task':TASK,'status':'ALL_18_ARMS_COMPLETE' if all(r['net'] is not None for r in results) else 'PARTIAL_FAIL_CLOSED',
        'results':results,'staging_errors':errors,'unresolved':protocol()['unresolved'],
        '2024_access':False,'2025_access':False,'production_change':False,'threshold_search':False,
        'V4_preserved':True,'fresh_validation_claim':False,'economic_qualification':False}
    save(root/'canonical_result.json',result)
    pd.DataFrame([{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in results]).to_csv(root/'scorecard.csv',index=False)
    save(root/'output_manifest.json',{'files':{str(p.relative_to(root)).replace('\\','/'):sha(p)
        for p in root.rglob('*') if p.is_file() and p.name!='output_manifest.json'}})
    return result
