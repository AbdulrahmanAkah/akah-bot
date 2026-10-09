"""Explicit prospective structural choices; no economic outcomes or fitted constants."""
from copy import deepcopy
import hashlib
from . import akah_full_fidelity_runtime_v1 as rt
from .akah_foundation_core_v1r1 import utc


class OwnedWyckoffRuntimeV3(rt.WyckoffRuntime):
    """Mechanical ownership repaired; cause doctrine is still not funded authority."""
    def step(self,t,event,meta=None):
        m=deepcopy(meta or {}); t=utc(t)
        if event=='HIGHER_LEVEL_RANGE_FORMS' and self.state=='E_MARKUP':
            parent=deepcopy(self.context)
            self.context={'prior_markup':True,'historical_parent':parent,'range':m,
                          'cause_id':hashlib.sha256(f'{self.pair}|REACCUM|{t}|{m}'.encode()).hexdigest(),
                          'cause_start':t,'cause_doctrine_bound':False}
            self._change(t,'REACCUMULATION','owned new range/cause; old accumulation is historical only',m)
            return
        if event in {'LPS_HOLDS','REACCUMULATION_SOS_LPS','SPRING_RECLAIM','HIGHER_RANGE_SUPPLY_TEST'}:
            m['evidence_id']=hashlib.sha256(f'{self.pair}|{event}|{t}|{m}'.encode()).hexdigest()
            m['available_at']=t; m['live']=True; m['consumed']=False
            m['parent_cause_id']=self.context.get('cause_id')
        if event in {'RANGE_SUPPORT_FAIL','DISTRIBUTION_RISK','LPS_INVALIDATED','TEST_INVALIDATED'}:
            for key in ('lps','phase_c'):
                if key in self.context: self.context[key]['live']=False
        super().step(t,event,m)
        if event=='SELLING_CLIMAX':
            self.context['cause_id']=hashlib.sha256(f'{self.pair}|ACCUM|{t}'.encode()).hexdigest()
            self.context['cause_start']=t

    def entry_intent(self,t,**kwargs):
        branch=kwargs['branch']; key='phase_c' if branch=='SPRING_TEST' else 'lps'
        e=self.context.get(key,{})
        if (not e.get('evidence_id') or not e.get('live') or e.get('consumed')
            or utc(e['available_at'])>utc(t) or not e.get('parent_cause_id')
            or e['parent_cause_id']!=self.context.get('cause_id')):
            return None
        low=e.get('low',e.get('support'))
        if low is None or kwargs['entry']<=float(low) or kwargs['structural_low']!=float(low):
            return None
        if self.context.get('prior_markup') and not self.context.get('cause_doctrine_bound'):
            return None
        intent=super().entry_intent(t,**kwargs)
        if intent is not None:
            e['consumed']=True
            intent.metadata.update({'owned_evidence_id':e['evidence_id'],'cause_id':self.context['cause_id']})
        return intent


class ClassicalRuntimeV3(rt.ClassicalRuntime):
    """DESIGN_CHOICE: frozen pattern support is an absorbing pre-entry boundary."""
    def entry_intent(self,t,pid,bar_low,bar_close,confirmed_higher_low=None):
        q=self.pending.get(pid)
        if q and q['state']=='BREAKOUT' and utc(t)>q['breakout_time']:
            if bar_low<=q['pattern'].support:
                q['state']='INVALIDATED'
                self.transitions.append(rt.StateTransition('FS_CLASSICAL_FULL_LONG',self.pair,utc(t),
                    'BREAKOUT','INVALIDATED','V3 frozen support violated before acceptance',{'pattern_id':pid}))
                return None
        return super().entry_intent(t,pid,bar_low,bar_close,confirmed_higher_low)


def classical_manage_v3(*,entry_price,price,target,current_stop,confirmed_higher_low,
                         primary_trend,pattern_failed):
    """DESIGN_CHOICE: inherited 75% is objective progress, never 75% of price level."""
    if pattern_failed: return {'action':'EXIT_PATTERN_FAILURE','stop':current_stop}
    if primary_trend=='DOWN': return {'action':'EXIT_PRIMARY_TREND_REVERSAL','stop':current_stop}
    stop=current_stop
    if (confirmed_higher_low is not None and current_stop<float(confirmed_higher_low)<price
        and price>=entry_price+.75*(target-entry_price)):
        stop=float(confirmed_higher_low)
    return {'action':'OBJECTIVE_REACHED' if price>=target else 'HOLD','stop':stop}
