"""Hash-gated real event runner; NEVER call run_market without the next mission token.

No frozen future exit rows are accepted. Native management is evaluated on each
completed bar. Prepared entry events are causal scanner outputs, not outcome labels.
"""
from __future__ import annotations
import hashlib,json,math,sqlite3,bisect
from pathlib import Path
from decimal import Decimal
import numpy as np
import pandas as pd
from . import akah_full_fidelity_runtime_v1 as rt
from . import akah_replay_ready_detectors_v1 as det
from . import akah_native_replay_engine_v1 as eng
from .akah_foundation_core_v1r1 import raw_frame,canonical_aggregate,load_broad_eligibility,BroadEligibilityIndex,utc,DATA_START,DATA_CUTOFF,ny_session_end_utc
from .akah_thesis_engine_foundation_v1 import EvidenceRecord,ParentEdge,ParentEdgeType,ThesisRecord,RouterState,Direction,StructuralPhase,Activity,EvidenceStatus
from .evidence_selector import EvidenceStore,Feasibility
from .source_router import SourceBoundRouter,GrammarPermission
from .event_execution_bridge import EventExecutionBridge,QuantityRule,CompletedBar
from .portfolio_kernel import PortfolioKernel
from .owned_runtime_v3 import ClassicalRuntimeV3
from .qualification_uncertainty import evaluate_calendar_claims
from .gate3_precommit import concentration

GOV=Path('governance/final_gate2_to_gate3_replay_ready_mega_v3')
TOKEN='AKAH_GATE3_SINGLE_REPLAY_AUTHORIZED'
NEXT_TASK='AKAH_SINGLE_FROZEN_GATE3_ECONOMIC_REPLAY_V3'
ICT='FS_ICT_2022_CORE_CRYPTO_LONG'; CLASSICAL='FS_CLASSICAL_FULL_LONG'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()
def bounded_sha(frame): return hashlib.sha256(pd.util.hash_pandas_object(frame,index=False).values.tobytes()).hexdigest().upper()
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,default=str)+'\n',encoding='utf-8')

def quantity_rules(pairs,source_sha):
    return {p:QuantityRule(p,'2026-10-03T00:00:00Z','2021-09-01T00:00:00Z',DATA_CUTOFF,
        Decimal('0.00000001'),Decimal('0.00000001'),Decimal('50'),source_sha,
        'PROSPECTIVE_DESIGN_CHOICE_NOT_HISTORICAL_EXCHANGE_RULE') for p in pairs}

def preflight(repo:Path,*,verify_data=False):
    root=repo/GOV; manifest=json.loads((root/'15_GATE3_FROZEN_HASH_MANIFEST.json').read_text())
    failures=[]
    for relative,expected in manifest['files'].items():
        path=(repo/relative).resolve()
        if not path.is_relative_to(repo.resolve()) or not path.is_file() or sha(path)!=expected:
            failures.append('SOURCE_OR_CONFIG_HASH_DRIFT:'+relative)
    config=json.loads((root/'13_GATE3_PRECOMMIT_FINAL.json').read_text())
    scope=json.loads((root/'07_FUNDED_SCOPE_FINAL.json').read_text())
    if config['funded_grammars']!=scope['funded_grammars'] or not scope['funded_grammars']:
        failures.append('FUNDED_SCOPE_DRIFT')
    registry=pd.read_csv(root/'14_GATE3_FINAL_CLAIM_REGISTRY.csv')
    if (list(registry.claim_id)!=config['primary_claim_family']
        or set(registry.claim_id)!=set(scope['funded_grammars'])
        or any(r.arm!=r.claim_id+'|2X' for r in registry.itertuples())):
        failures.append('FIXED_PRIMARY_CLAIM_FAMILY_DRIFT')
    dep=json.loads((root/'12_DEPENDENCY_LOCK.json').read_text())
    from importlib import metadata
    for dist in dep['distributions']:
        try:
            installed=metadata.distribution(dist['name'])
            if installed.version!=dist['version']: failures.append('DEPENDENCY_VERSION_DRIFT:'+dist['name'])
            for p,expected in dist['installed_files'].items():
                path=Path(installed.locate_file(p))
                if not path.is_file() or sha(path)!=expected: failures.append('DEPENDENCY_FILE_DRIFT:'+p)
        except metadata.PackageNotFoundError: failures.append('DEPENDENCY_MISSING:'+dist['name'])
    inputs=json.loads((root/'bounded_market_input_manifest.json').read_text())
    if inputs['protected_rows_loaded']!=0: failures.append('PROTECTED_BOUNDARY')
    if verify_data:
        ranking=load_broad_eligibility(repo)
        current=hashlib.sha256(pd.util.hash_pandas_object(ranking[['decision_time','pair','eligible','adjusted_rank']],index=False).values.tobytes()).hexdigest().upper()
        if current!=inputs['membership_bounded_sha256']: failures.append('PIT_MEMBERSHIP_DRIFT')
        for row in inputs['pairs']:
            frame=raw_frame(repo,row['pair'])
            if bounded_sha(frame)!=row['bounded_sha256']: failures.append('BOUNDED_MARKET_HASH_DRIFT:'+row['pair'])
    result={'status':'PASS' if not failures else 'FAIL','failures':failures,
        'source_config_scope_dependency_claims_verified':not failures,'bounded_market_hashes_verified':verify_data,
        'economic_replay_executed':False,'authorization_token_received':False}
    if failures: raise ValueError(json.dumps(result))
    return result

def trend_series(frame):
    piv=rt.confirmed_pivots_2l2r(det.add_indicators(frame)); by={}
    for p in piv: by.setdefault(utc(p.confirm_time),[]).append(p)
    av=[]; values=[]; times=[]
    for t,ps in sorted(by.items()):
        av.extend(ps); times.append(t); values.append(rt.trend_from_pivots(av))
    return times,values,piv

def asof(series,t):
    j=bisect.bisect_right(series[0],utc(t))-1
    return series[1][j] if j>=0 else 'UNKNOWN'

def router_state(market,asset,h4,t,*,asset_mark=None,market_mark=None):
    dm,da,dh=asof(market,t),asof(asset,t),asof(h4,t)
    direction=lambda x:Direction.BALANCED if x=='RANGE' else Direction(x)
    phase=(StructuralPhase.MARKUP if dh=='UP' else StructuralPhase.BASE_CANDIDATE if dh=='RANGE'
        else StructuralPhase.REACCUMULATION_CANDIDATE if dh=='DOWN' and da=='UP'
        else StructuralPhase.MARKDOWN if dh=='DOWN' else StructuralPhase.UNKNOWN)
    def protected(series,mark):
        lows=[p for p in series[2] if p.kind=='L' and p.confirm_time<=utc(t)]
        return bool(lows and mark is not None and math.isfinite(mark) and mark>lows[-1].price)
    authority=asset_mark is not None and market_mark is not None
    major_valid=protected(asset,asset_mark) and protected(market,market_mark)
    return RouterState(direction(dm),direction(da),phase,Activity.NORMAL,
        data_authority_valid=authority,major_protected_structure_valid=major_valid)

def bind_request(event,store,state,router,now,capacity,source_sha,scope,*,decision_equity=100000.0):
    row=dict(event); grammar=row['system_id']; pair=row['pair']; m=json.loads(row['metadata'])
    if grammar not in scope: raise ValueError('QUARANTINED_GRAMMAR_REACHED_EXECUTION')
    if not math.isfinite(decision_equity) or decision_equity<=0: raise ValueError('CURRENT_EQUITY_UNBOUND')
    permission,reason=router.permission(grammar,state)
    if not permission: return None,reason
    t=utc(row['timestamp'])
    if t!=utc(now) or t>=DATA_CUTOFF: raise ValueError('ENTRY_NEXT_OPEN_CLOCK_DRIFT')
    owner=(f"{pair}|ICT|{m['raid_time']}" if grammar==ICT else f"{pair}|CLASSICAL|{m['pattern_id']}")
    identity=hashlib.sha256(f'{grammar}|{owner}|{t}'.encode()).hexdigest()
    if identity in store.records: raise ValueError('THESIS_RESURRECTION')
    if grammar==ICT:
        raid,mss,fvg,retrace=map(utc,(m['raid_time'],m['mss_time'],m['fvg_created_at'],m['retrace_time']))
        if not raid<mss==fvg<retrace==t: raise ValueError('ICT_CAUSAL_ORDER_OR_OWNER_UNBOUND')
        expiry=ny_session_end_utc(raid)
        if t>=expiry: return None,'SESSION_EXPIRED'
        nodes=[('RAID',raid),('MSS',mss),('FVG',fvg),('RETRACEMENT',t)]
    else:
        formed,broken=utc(m['formed_at']),utc(m['breakout_time'])
        if not formed<=broken<t: raise ValueError('CLASSICAL_CAUSAL_ORDER_UNBOUND')
        expiry=t+pd.Timedelta(hours=1)
        nodes=[('STRUCTURE',formed),('BREAKOUT',broken),('ACCEPTANCE',t)]
    previous=None; ids=[]
    for kind,known in nodes:
        eid=identity+'|'+kind
        edges=() if previous is None else (ParentEdge(previous,ParentEdgeType.LIVE_REQUIREMENT),)
        store.register(EvidenceRecord(eid,kind,owner,known,known,source_sha,expiry,parent_edges=edges,
            metadata={'stop':m['stop'],'target':m['target']}))
        ids.append(eid); previous=eid
    store.register(EvidenceRecord(identity,'COMPLETE_THESIS',owner,t,t,source_sha,expiry,
        parent_edges=(ParentEdge(previous,ParentEdgeType.LIVE_REQUIREMENT),)))
    thesis=ThesisRecord(identity,grammar,owner,pair,t,row['event'],'OWNER_STRUCTURAL_STOP',
        'ICT_NATIVE_SESSION' if grammar==ICT else 'CLASSICAL_NATIVE_V3',0.005*decision_equity,tuple(ids),
        float(capacity or 0)/decision_equity,funded_ready=True)
    requestrow={'identity':identity,'pair':pair,'owner_grammar':grammar,'owner_structure_id':owner,
        'stop':float(m['stop']),'target':float(m['target']),**m,'ready_at':str(t)}
    f=Feasibility(thesis,state,True,True,True,True,True)
    return (f,requestrow,identity),'BOUND_COMPLETE_THESIS'

def stage_market(repo,root,inputs,config):
    """Called only by the explicitly authorized future replay; bounded one-pair memory."""
    db=sqlite3.connect(root/'event_market.sqlite')
    db.executescript('CREATE TABLE bars(pair TEXT, t TEXT, o REAL,h REAL,l REAL,c REAL,cap REAL, mss INTEGER,down INTEGER,hl REAL,PRIMARY KEY(pair,t)); CREATE INDEX hour_idx ON bars(t); CREATE TABLE intents(t TEXT, pair TEXT, grammar TEXT, payload TEXT); CREATE INDEX intent_time ON intents(t);')
    ranking=load_broad_eligibility(repo)
    membership_sha=hashlib.sha256(pd.util.hash_pandas_object(ranking[['decision_time','pair','eligible','adjusted_rank']],index=False).values.tobytes()).hexdigest().upper()
    if membership_sha!=inputs['membership_bounded_sha256']: raise ValueError('PIT_MEMBERSHIP_INPUT_DRIFT')
    eligibility=BroadEligibilityIndex.build(ranking)
    btc=raw_frame(repo,'BTC-USDT'); eth=raw_frame(repo,'ETH-USDT')
    market=trend_series(canonical_aggregate(repo,'BTC-USDT',btc,'1d'))
    states={}; source_sha=sha(Path(det.__file__))
    for record in inputs['pairs']:
        pair=record['pair']; raw=raw_frame(repo,pair)
        if bounded_sha(raw)!=record['bounded_sha256']: raise ValueError('BOUNDED_MARKET_INPUT_DRIFT:'+pair)
        h4=canonical_aggregate(repo,pair,raw,'4h'); d1=canonical_aggregate(repo,pair,raw,'1d')
        states[pair]=(trend_series(d1),trend_series(h4))
        # Only fully bounded prior bars enter trailing 24h capacity at the next open.
        timestamps=pd.DatetimeIndex(pd.to_datetime(raw.timestamp,utc=True))
        volume=pd.Series(raw.volume.to_numpy()*raw.close.to_numpy(),index=timestamps)
        rolling=volume.rolling('24h',closed='right',min_periods=24).sum()
        mss=set(eng.bearish_mss_times(raw)); downs=set(eng.confirmed_primary_down_times(h4))
        lows=[p for p in states[pair][1][2] if p.kind=='L']
        lt=[p.confirm_time for p in lows]
        values=[]
        for i,r in enumerate(raw.itertuples(index=False)):
            t=utc(r.timestamp); opening=t-pd.Timedelta(hours=1)
            if opening<DATA_START: continue
            prior=i-1
            cap=float(rolling.iloc[prior])*.005 if prior>=0 and timestamps[prior]==opening and np.isfinite(rolling.iloc[prior]) else None
            j=bisect.bisect_right(lt,t)-1
            hl=float(lows[j].price) if j>=0 else None
            values.append((pair,str(t),r.open,r.high,r.low,r.close,cap,int(t in mss),int(t in downs),hl))
        db.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)',values)
        calls=[]
        if ICT in config['funded_grammars']: calls.append(det.scan_ict(pair,raw,h4,d1,btc,eth,eligibility))
        if CLASSICAL in config['funded_grammars']: calls.append(det.scan_classical(pair,h4,eligibility,runtime_factory=ClassicalRuntimeV3))
        for _,_,intents,_ in calls:
            db.executemany('INSERT INTO intents VALUES (?,?,?,?)',[(str(utc(e['timestamp'])),pair,e['system_id'],json.dumps(e))
                for e in intents if DATA_START<=utc(e['timestamp'])<DATA_CUTOFF])
        db.commit()
    return db,market,states,source_sha

def campaign_attribution(kernel,last_prices):
    totals={}; asset={}
    for f in kernel.fills:
        cid=f['campaign_id']; totals[cid]=totals.get(cid,0)+f['cash_delta']
    for p in kernel.positions.values():
        cid=p['campaign_id']; totals[cid]=totals.get(cid,0)+p['qty_current']*last_prices[p['episode']['pair']]
    rows=[]
    for cid,pnl in totals.items():
        pair=kernel.campaigns[cid].pair; asset[pair]=asset.get(pair,0)+pnl
        rows.append({'campaign_id':cid,'pair':pair,'net_including_fees_and_terminal_mtm':pnl})
    return rows,asset

def qualify(arms,config,claims):
    yearly={y:pd.DataFrame({name:x['daily_log'].loc[str(y)].to_numpy() for name,x in arms.items()},
        index=pd.date_range(f'{y}-01-01',f'{y}-12-31',freq='D',tz='UTC')) for y in (2022,2023)}
    try: uncertainty=evaluate_calendar_claims(yearly,claims)
    except ValueError as e: uncertainty={'status':'EVIDENCE_INCONCLUSIVE','error':str(e),'claims':{}}
    decisions={}
    for grammar in config['funded_grammars']:
        one,two=arms[grammar+'|1X'],arms[grammar+'|2X']
        hard=(all(two['annual_net'][y]>0 for y in (2022,2023)) and one['net']>0 and two['net']>0
            and max(one['mdd'],two['mdd'])<=.20 and one['risk_pass'] and two['risk_pass']
            and concentration(np.array([r['net_including_fees_and_terminal_mtm'] for r in two['campaigns']]),np.array(list(two['assets'].values()))))
        u=uncertainty.get('claims',{}).get(grammar,{})
        decisions[grammar]=('QUALIFIED_EXPOSED_RESEARCH' if hard and u.get('lcb',-np.inf)>0 else
            'EVIDENCE_INCONCLUSIVE' if hard else 'ECONOMIC_NOT_QUALIFIED')
    return {'decisions':decisions,'uncertainty':uncertainty,'production_authorized':False,
        'historical_exchange_executability_claim':'WITHDRAWN','years_already_research_exposed':True}

def run_market(repo:Path,token:str):
    if token!=TOKEN: raise PermissionError('NEXT_MISSION_EXPLICIT_AUTHORIZATION_REQUIRED')
    active=json.loads((repo/'.akah_bot/active_task.json').read_text())
    if active['task_id']!=NEXT_TASK: raise PermissionError('NEW_GOVERNED_ECONOMIC_TASK_REQUIRED')
    preflight(repo)
    root=repo/'governance/gate3_single_frozen_economic_replay_v3'
    if root.exists(): raise PermissionError('SINGLE_REPLAY_ALREADY_STARTED_NO_AUTOMATIC_RERUN')
    root.mkdir(); save(root/'STARTED.json',{'token':token,'task':active,'one_run':True})
    config=json.loads((repo/GOV/'13_GATE3_PRECOMMIT_FINAL.json').read_text())
    inputs=json.loads((repo/GOV/'bounded_market_input_manifest.json').read_text())
    claims={r['claim_id']:{r['arm']:1.0} for r in pd.read_csv(repo/GOV/'14_GATE3_FINAL_CLAIM_REGISTRY.csv').to_dict('records')}
    db,market,states,source_sha=stage_market(repo,root,inputs,config)
    permissions=tuple(GrammarPermission(g,frozenset({StructuralPhase.MARKUP,StructuralPhase.BASE_CANDIDATE,
        StructuralPhase.REACCUMULATION_CANDIDATE}),source_sha,True,True) for g in config['funded_grammars'])
    router=SourceBoundRouter(permissions); rules=quantity_rules(states,sha(repo/GOV/'prospective_design_choices.json'))
    arms={}; clock=pd.date_range(DATA_START,DATA_CUTOFF-pd.Timedelta(hours=2),freq='h')
    for grammar in config['funded_grammars']:
        for label,cost in config['costs_round_trip'].items():
            kernel=PortfolioKernel(100000.0,{}, {},cost/2); store=EvidenceStore()
            bridge=EventExecutionBridge(kernel,store,rules,synthetic_fixture=False,
                market_contract={'source_hash_verified':True,'funded_grammars':config['funded_grammars']})
            equity=[]; audits=[]; rejections=[]; last_prices={}
            for opening in clock:
                closing=opening+pd.Timedelta(hours=1)
                records=db.execute('SELECT * FROM bars WHERE t=?',(str(closing),)).fetchall()
                prices={r[0]:r[2] for r in records}; capacity={r[0]:r[6] for r in records}
                decision_equity=kernel.snapshot(lambda p,t:prices[p],opening)['equity']
                requests=[]
                for _,pair,g,payload in db.execute('SELECT * FROM intents WHERE t=? AND grammar=?',(str(opening),grammar)):
                    if pair not in prices: raise ValueError('MISSING_CANDIDATE_NEXT_OPEN:'+pair)
                    event=json.loads(payload); state=router_state(market,states[pair][0],states[pair][1],opening,
                        asset_mark=prices[pair],market_mark=prices.get('BTC-USDT'))
                    req,reason=bind_request(event,store,state,router,opening,capacity.get(pair),source_sha,config['funded_grammars'],decision_equity=decision_equity)
                    if req is not None: requests.append(req)
                    else: rejections.append({'time':str(opening),'pair':pair,'reason':reason})
                rejected=bridge.on_open(opening,prices,capacity,requests)
                rejections.extend({'time':str(opening),'identity':k,'reason':v} for k,v in rejected.items())
                # Consumed activations cannot be reused; position management has its own frozen owner.
                for req in requests:
                    t=req[0].thesis
                    for eid in (*t.supporting_evidence_ids,t.thesis_id):
                        if store.records[eid].status==EvidenceStatus.ACTIVE: store.terminate(eid,EvidenceStatus.CONSUMED)
                snapshot=kernel.snapshot(lambda p,t:prices[p],opening)
                if not eng.current_mtm_limits_ok(snapshot): raise ValueError('POST_OPEN_RISK_BREACH')
                expected=100000+sum(f['cash_delta'] for f in kernel.fills)
                if not math.isclose(expected,kernel.cash,rel_tol=1e-10,abs_tol=1e-6): raise ValueError('CASH_FILL_RECONCILIATION')
                equity.append({'time':opening,'equity':snapshot['equity'],'cash':kernel.cash,'gross':snapshot['gross']})
                audits.append({'time':str(opening),'risk_pass':True,'cash_error':expected-kernel.cash})
                last_prices=prices
                bars={r[0]:CompletedBar(r[0],opening,closing,r[2],r[3],r[4],r[5]) for r in records}
                native={}
                by_pair={r[0]:r for r in records}
                for p in kernel.positions.values():
                    row=p['episode']; r=by_pair[row['pair']]
                    # Confirmed HL is legal only if its underlying pivot is post-entry.
                    lowp=[z for z in states[row['pair']][1][2] if z.kind=='L' and z.confirm_time<=closing and z.pivot_time>utc(row['ready_at'])]
                    native[row['identity']]={'known_at':closing,'bearish_mss':bool(r[7]),'confirmed_primary_down':bool(r[8]),
                        'confirmed_higher_low':lowp[-1].price if lowp else None,
                        'pattern_failed':closing in states[row['pair']][1][0] and r[5]<=row.get('frozen_support',-math.inf)}
                # The final legal OPEN is the terminal MTM. Do not process its future close
                # and then report it as OPEN equity; no final forced liquidation.
                if opening!=clock[-1]: bridge.on_close(closing,bars,native)
            hourly=pd.DataFrame(equity).set_index('time'); all_days=pd.date_range('2022-01-01','2023-12-31',freq='D',tz='UTC')
            daily=hourly.equity.resample('D').last().reindex(all_days).ffill().fillna(100000.)
            returns=np.log(daily/daily.shift(1).fillna(100000.))
            campaigns,assets=campaign_attribution(kernel,last_prices)
            terminal=float(hourly.equity.iloc[-1]); net=terminal-100000
            if not math.isclose(sum(r['net_including_fees_and_terminal_mtm'] for r in campaigns),net,abs_tol=1e-5): raise ValueError('CAMPAIGN_ASSET_TERMINAL_RECONCILIATION')
            annual={2022:float(daily.loc['2022'].iloc[-1]-100000),2023:float(daily.loc['2023'].iloc[-1]-daily.loc['2022'].iloc[-1])}
            name=grammar+'|'+label; folder=root/name.replace('|','__'); folder.mkdir()
            hourly.to_csv(folder/'hourly_equity.csv'); daily.to_csv(folder/'daily_equity.csv')
            pd.DataFrame(kernel.fills).to_csv(folder/'fills.csv',index=False); pd.DataFrame(campaigns).to_csv(folder/'campaign_ledger.csv',index=False)
            pd.DataFrame(audits).to_csv(folder/'risk_accounting_audit.csv',index=False); pd.DataFrame(bridge.trace).to_csv(folder/'execution_audit.csv',index=False)
            pd.DataFrame(rejections).to_csv(folder/'selection_rejections.csv',index=False)
            arms[name]={'net':net,'mdd':float((1-hourly.equity/hourly.equity.cummax().clip(lower=100000)).max()),
                'annual_net':annual,'risk_pass':not kernel.risk_breach_unresolved,'campaigns':campaigns,'assets':assets,'daily_log':returns}
            save(folder/'metrics.json',{k:v for k,v in arms[name].items() if k!='daily_log'})
    result=qualify(arms,config,claims); save(root/'canonical_result.json',result); db.close()
    return result
