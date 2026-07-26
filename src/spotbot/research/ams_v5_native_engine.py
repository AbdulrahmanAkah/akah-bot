"""Native, self-contained AMS V5R1 research engine (no V4 strategy imports)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import math
import pandas as pd
import numpy as np

LOCK=pd.Timestamp("2025-01-01T00:00:00Z")
class V5NativeError(RuntimeError): pass
@dataclass(frozen=True)
class V5Fill:
    fill_id:str;candidate_id:str;position_id:str;symbol:str;timestamp:pd.Timestamp;fill_type:str;price:float;quantity:float;notional:float;fee:float;cash_before:float;cash_after:float;position_quantity_before:float;position_quantity_after:float;reason:str
@dataclass(frozen=True)
class V5ScheduledEntry:
    candidate:V5SetupCandidate;entry_time:pd.Timestamp
@dataclass
class V5RejectionCounters:
    values:dict[str,int]=field(default_factory=dict)
    def add(self,key:str)->None:self.values[key]=self.values.get(key,0)+1
@dataclass(frozen=True)
class V5PortfolioProfile:
    profile_id:str;base_risk:float;max_initial_risk:float;max_position_risk:float;max_heat:float;max_positions:int;max_cluster:int=2
@dataclass(frozen=True)
class V5Parameters:
    configuration_id:str;family:str;stop_model:str;fibonacci_mode:str;threshold:int;cost:float
@dataclass(frozen=True)
class V5SetupCandidate:
    candidate_id:str;symbol:str;signal_open:pd.Timestamp;signal_close:pd.Timestamp;scheduled_open:pd.Timestamp;family:str;score:float;threshold:int;d1_score:float;eight_hour_score:float;four_hour_score:float;fibonacci:float;entry_reference:float;structural_stop_reference:float;atr:float;stop_atr:float;requested_risk:float=0.
@dataclass
class V5OpenPosition:
    symbol:str;quantity:float;entry:float;stop:float;initial_stop:float;risk_fraction:float;entry_time:pd.Timestamp;notional:float;entry_fee:float;mfe:float=0.;mae:float=0.;bars:int=0;addon:bool=False
@dataclass(frozen=True)
class V5ClosedTrade:
    symbol:str;entry_time:pd.Timestamp;exit_time:pd.Timestamp;entry:float;exit:float;quantity:float;pnl:float;reason:str;mae_r:float;mfe_r:float
def assert_boundary(frame:pd.DataFrame)->None:
    for col,strict in (("bar_open_time",True),("bar_close_time",False)):
        if col in frame:
            x=pd.to_datetime(frame[col],utc=True)
            if (x.ge(LOCK) if strict else x.gt(LOCK)).any():raise V5NativeError(f"locked {col}")
def profiles()->tuple[V5PortfolioProfile,...]:
    return (V5PortfolioProfile("AMS-V5R1-P01",.007,.0095,.012,.045,5),V5PortfolioProfile("AMS-V5R1-P02",.0095,.013,.016,.065,6))
def build_features(four_hour:pd.DataFrame,availability:pd.DataFrame)->pd.DataFrame:
    assert_boundary(four_hour);x=four_hour.copy();x["bar_open_time"]=pd.to_datetime(x["bar_open_time"],utc=True);x["bar_close_time"]=pd.to_datetime(x["bar_close_time"],utc=True);x=x.sort_values(["symbol","bar_close_time"])
    out=[]
    for symbol,g in x.groupby("symbol",sort=True):
        g=g.copy();prev=g.close.shift();g["atr"]=pd.concat([g.high-g.low,(g.high-prev).abs(),(g.low-prev).abs()],axis=1).max(axis=1).rolling(14).mean();g["ema21"]=g.close.ewm(span=21,adjust=False).mean();g["ema55"]=g.close.ewm(span=55,adjust=False).mean();g["slope"]=g.ema21.pct_change(8);g["trend"]=(g.close>g.ema21)&(g.ema21>g.ema55);g["depth"]=((g.ema21-g.low)/g.atr).clip(lower=0);g["shallow"]=g.trend&g.depth.between(.5,1.5)&(g.close>g.ema21)&(g.close>g.open);g["deep"]=g.trend&g.depth.between(1.5,3)&(g.close>g.ema21)&(g.low>=g.low.rolling(12).min().shift());g["prior_high"]=g.high.rolling(8).max().shift();g["reaccel"]=g.trend&(g.close>g.prior_high)&(((g.high-g.low)/g.atr)>1);g["d1_score"]=np.where(g.trend,12.,7.);g["eight_hour_score"]=np.where(g.trend,18.,5.)+np.clip(g.slope*1000,0,10);g["four_hour_score"]=np.where(g.shallow|g.deep|g.reaccel,25.,0.);g["fib"]=np.where(g.depth.between(.5,1.5),5.,np.where(g.depth>3,-5.,0.));g["score_no_fib"]=(g.d1_score+g.eight_hour_score+g.four_hour_score+8).clip(0,100);g["score_soft_fib"]=(g.score_no_fib+g.fib).clip(0,100);g["family"]=np.select([g.shallow,g.deep,g.reaccel],["SHALLOW_PULLBACK_RECLAIM","DEEP_PULLBACK_RECOVERY","MOMENTUM_REACCELERATION"],default="NONE");out.append(g)
    y=pd.concat(out).merge(availability[["symbol","tradable_from","tradable_until"]],on="symbol",how="left");y["tradable_from"]=pd.to_datetime(y.tradable_from,utc=True);y["tradable_until"]=pd.to_datetime(y.tradable_until,utc=True);assert_boundary(y);return y.sort_values(["bar_close_time","symbol"])
def threshold_train_only(frame:pd.DataFrame,validation_start:pd.Timestamp)->int:
    train=frame.loc[frame.bar_open_time<validation_start];return 50 if (train.family!="NONE").sum()<8000 else 55
def risk_multiplier(score:float)->float:return .7 if score<60 else .9 if score<70 else 1 if score<80 else 1.2
def drawdown_multiplier(dd:float)->float:return 1 if dd<.08 else .85 if dd<.12 else .65 if dd<.16 else .4 if dd<.20 else .2 if dd<=.24 else 0
def trailing_stop(current:float,entry:float,atr:float,mfe_r:float,higher_low:float|None)->tuple[float,str|None]:
    if mfe_r<2.25 and higher_low is None:return current,None
    candidate=max(entry-3.5*atr,(higher_low-.25*atr) if higher_low is not None else -math.inf)
    return max(current,candidate),"HIGHER_LOW" if higher_low is not None else "MFE_2_25R"
def may_add_on(pos:V5OpenPosition,price:float,score:float,overextended:bool,profile:V5PortfolioProfile,heat:float,cash:float)->tuple[bool,str]:
    r=max(pos.entry-pos.initial_stop,1e-12)
    if pos.addon:return False,"ADD_ON_ALREADY_USED"
    if price-pos.entry<1.25*r:return False,"ADD_ON_NOT_PROFITABLE"
    if overextended:return False,"OVEREXTENSION"
    qty=.25*pos.quantity/(1.25 if pos.addon else 1.0)
    added_risk=pos.risk_fraction*.25
    if pos.risk_fraction+added_risk>profile.max_position_risk:return False,"POSITION_RISK_LIMIT"
    if heat+added_risk>profile.max_heat:return False,"PORTFOLIO_HEAT"
    if qty*price>cash:return False,"INSUFFICIENT_CASH"
    return True,"ADD_ON"
def may_reenter(last_stop_bar:int,current_bar:int,used:bool,trend:bool,crisis:bool,invalidated:bool)->tuple[bool,str]:
    if used:return False,"REENTRY_ALREADY_USED"
    if current_bar-last_stop_bar<2:return False,"REENTRY_COOLDOWN"
    if crisis:return False,"CRISIS_STATE"
    if invalidated:return False,"STRUCTURAL_INVALIDATION"
    return (True,"REENTRY") if trend else (False,"INVALID_8H_STRUCTURE")
def correlation_clusters(frame:pd.DataFrame,as_of:pd.Timestamp,window_days:int=60)->dict[str,str]:
    x=frame.loc[(frame.bar_close_time<as_of)&(frame.bar_close_time>=as_of-pd.Timedelta(days=window_days))].copy()
    if x.empty:return {}
    daily=x.set_index("bar_close_time").groupby("symbol").close.resample("1D").last().unstack(0).pct_change().dropna();symbols=sorted(daily.columns);out={}
    for symbol in symbols:
        peers=[other for other in symbols if other!=symbol and daily[symbol].corr(daily[other])>=.75]
        out[symbol]=min([symbol,*peers])
    return out
def choose_threshold(metrics_by_threshold:dict[int,dict[str,float]])->dict[str,Any]:
    allowed={50,55}
    if set(metrics_by_threshold)!=allowed:raise V5NativeError("thresholds must be 50 and 55")
    eligible={k:v for k,v in metrics_by_threshold.items() if v["profit_factor"]>=1.1 and v["maximum_drawdown"]<=.3 and not v.get("safety_failure",False)}
    if not eligible:return {"selected":55,"excluded":{k:"UNSAFE" for k in allowed},"quality_scores":{}}
    keys=("expectancy","profit_factor","calmar","activity_alignment","stress_resilience")
    normalized={k:{key:(v[key]-min(x[key] for x in eligible.values()))/max(max(x[key] for x in eligible.values())-min(x[key] for x in eligible.values()),1e-12) for key in keys} for k,v in eligible.items()}
    weights={"expectancy":.35,"profit_factor":.25,"calmar":.2,"activity_alignment":.1,"stress_resilience":.1};scores={k:sum(weights[key]*normalized[k][key] for key in keys) for k in eligible}
    return {"selected":max(scores,key=lambda k:(scores[k],k)),"excluded":{k:"UNSAFE" for k in allowed-eligible.keys()},"quality_scores":scores,"normalized":normalized}
def reconcile_fills(initial_cash:float,fills:list[V5Fill])->dict[str,float]:
    cash=initial_cash;fees=turnover=0.
    for f in fills:
        signed=-f.notional-f.fee if f.fill_type in {"ENTRY","ADD_ON"} else f.notional-f.fee
        cash+=signed;fees+=f.fee;turnover+=f.notional
    return {"cash":cash,"fees":fees,"turnover":turnover}
def stop_distance(entry:float,atr:float,structural:float,model:str)->float|None:
    lo,hi=(2.2,3.4) if model=="STRUCTURE_BALANCED" else (2.6,4.0)
    distance=entry-structural
    if not math.isfinite(distance) or distance/atr>hi:return None
    return max(distance,atr*lo)
def make_candidate(row:pd.Series,params:V5Parameters,fold_id:str)->V5SetupCandidate|None:
    actual=str(row.family)
    if actual=="NONE" or (params.family!="HYBRID_ALL_THREE" and actual!=params.family):return None
    score=float(row.score_soft_fib if params.fibonacci_mode=="SOFT_FIBONACCI_SCORE" else row.score_no_fib)
    dist=stop_distance(float(row.close),float(row.atr),float(row.low)-.25*float(row.atr),params.stop_model)
    if dist is None:return None
    return V5SetupCandidate(f"{params.configuration_id}:{fold_id}:{row.symbol}:{row.bar_close_time.isoformat()}",str(row.symbol),pd.Timestamp(row.bar_open_time),pd.Timestamp(row.bar_close_time),pd.Timestamp(row.bar_close_time)+pd.Timedelta(hours=4),actual,score,params.threshold,float(row.d1_score),float(row.eight_hour_score),float(row.four_hour_score),float(row.fib if params.fibonacci_mode=="SOFT_FIBONACCI_SCORE" else 0),float(row.close),float(row.close-dist),float(row.atr),dist/float(row.atr),0.)
def simulate_fold(frame:pd.DataFrame,params:V5Parameters,profile:V5PortfolioProfile,capital:float=100000.)->tuple[float,list[V5ClosedTrade],list[V5Fill],V5RejectionCounters]:
    """Native conservative long-only simulation; candidate close, fill next open."""
    assert_boundary(frame);cash=capital;positions:dict[str,V5OpenPosition]={};scheduled:dict[str,V5ScheduledEntry]={};trades=[];fills=[];reject=V5RejectionCounters();peak=capital
    for ts,g in frame.sort_values(["bar_close_time","symbol"]).groupby("bar_close_time",sort=True):
        rows={str(x.symbol):x for x in g.itertuples(index=False)}
        for sym,pos in list(positions.items()):
            row=rows.get(sym)
            if row is None:continue
            pos.bars+=1;r=max(pos.entry-pos.initial_stop,1e-12);pos.mfe=max(pos.mfe,(float(row.high)-pos.entry)/r);pos.mae=min(pos.mae,(float(row.low)-pos.entry)/r)
            price=None;reason=""
            if pd.Timestamp(row.bar_open_time)>=pd.Timestamp(row.tradable_until):price=float(row.open);reason="VENUE_EXIT"
            elif float(row.open)<=pos.stop:price=float(row.open);reason="STOP_EXIT"
            elif float(row.low)<=pos.stop:price=pos.stop;reason="STOP_EXIT"
            elif pos.bars>=24 and pos.mfe<.75 and float(row.slope)<0:price=float(row.close);reason="STAGNATION_EXIT"
            elif pos.mfe>=2.25:pos.stop=max(pos.stop,float(row.close)-3.5*float(row.atr))
            if price is not None:
                fee=price*pos.quantity*params.cost;before=cash;cash+=price*pos.quantity-fee;fills.append(V5Fill(f"F{len(fills)}","",sym,sym,pd.Timestamp(ts),reason,price,pos.quantity,price*pos.quantity,fee,before,cash,pos.quantity,0.,reason));trades.append(V5ClosedTrade(sym,pos.entry_time,pd.Timestamp(ts),pos.entry,price,pos.quantity,price*pos.quantity-fee-pos.notional-pos.entry_fee,reason,pos.mae,pos.mfe));del positions[sym]
        equity=cash+sum(p.quantity*p.entry for p in positions.values());peak=max(peak,equity);dd=1-equity/peak
        for sym,entry in sorted(scheduled.items(),key=lambda x:(-x[1].candidate.score,x[0])):
            row=rows.get(sym)
            if row is None or sym in positions:continue
            c=entry.candidate;open_=float(row.open);distance=open_-c.structural_stop_reference
            if distance<=0 or distance/float(row.atr)>4:reject.add("GAP_INVALIDATED_RISK");continue
            heat=sum(p.risk_fraction for p in positions.values());risk=min(profile.max_initial_risk,profile.base_risk*risk_multiplier(c.score)*drawdown_multiplier(dd),profile.max_heat-heat)
            if risk<=0 or len(positions)>=profile.max_positions:reject.add("PORTFOLIO_LIMIT");continue
            qty=min(equity*risk/distance,cash/(open_*(1+params.cost)));notional=qty*open_;fee=notional*params.cost
            if qty<=0 or notional+fee>cash:reject.add("INSUFFICIENT_CASH");continue
            before=cash;cash-=notional+fee;positions[sym]=V5OpenPosition(sym,qty,open_,c.structural_stop_reference,c.structural_stop_reference,risk,pd.Timestamp(row.bar_open_time),notional,fee);fills.append(V5Fill(f"F{len(fills)}",c.candidate_id,sym,sym,pd.Timestamp(row.bar_open_time),"ENTRY",open_,qty,notional,fee,before,cash,0.,qty,"NEXT_BAR_OPEN"))
        scheduled={}
        for sym,row in rows.items():
            c=make_candidate(pd.Series(row._asdict()),params,"FOLD")
            if c is None:continue
            if c.score<params.threshold:reject.add("CONVICTION_THRESHOLD");continue
            scheduled[sym]=V5ScheduledEntry(c,c.scheduled_open)
    for sym,p in list(positions.items()):
        price=p.entry;fee=price*p.quantity*params.cost;cash+=price*p.quantity-fee;trades.append(V5ClosedTrade(sym,p.entry_time,pd.Timestamp(frame.bar_close_time.max()),p.entry,price,p.quantity,price*p.quantity-fee-p.notional-p.entry_fee,"END_OF_FOLD_EXIT",p.mae,p.mfe))
    return cash,trades,fills,reject
