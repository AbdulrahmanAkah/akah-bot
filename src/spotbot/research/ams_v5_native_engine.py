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
class V5PortfolioProfile:
    profile_id:str;base_risk:float;max_initial_risk:float;max_position_risk:float;max_heat:float;max_positions:int;max_cluster:int=2
@dataclass(frozen=True)
class V5Parameters:
    configuration_id:str;family:str;stop_model:str;fibonacci_mode:str;threshold:int;cost:float
@dataclass(frozen=True)
class V5SetupCandidate:
    symbol:str;signal_close:pd.Timestamp;scheduled_open:pd.Timestamp;family:str;score:float;threshold:int;d1_score:float;eight_hour_score:float;four_hour_score:float;fibonacci:float;stop:float;stop_atr:float
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
