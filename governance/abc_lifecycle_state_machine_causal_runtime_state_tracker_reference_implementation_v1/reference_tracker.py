from __future__ import annotations

def _b(v):
    if v is None:return False
    if isinstance(v,bool):return v
    if isinstance(v,(int,float)) and v in (0,1):return bool(v)
    s=str(v).strip().lower()
    if s in ('true','1','yes','y'):return True
    if s in ('false','0','no','n','','nan'):return False
    raise ValueError('invalid boolean value: %r'%(v,))

def _sig(s,a,b):
    p=[]
    if s:p.append('STALLED')
    if a:p.append('STRUCTURAL_BREAK')
    if b:p.append('VOLATILITY_DAMAGE')
    return '+'.join(p) if p else 'NONE'

def track_lifecycle(rows):
    stalled=False; out=[]
    for r in rows:
        memory=_b(r['memory_seen']); c=_b(r['C_signal']); base=str(r['base_state'])
        if stalled and memory:stalled=False
        if (not stalled) and c and base=='UNCONFIRMED' and not memory:stalled=True
        a=_b(r['a_condition_now']); b=_b(r['b_condition_now'])
        z={'year':r['year'],'pair':r['pair'],'entry_time':r['entry_time'],'native_exit_time':r['native_exit_time'],'decision_time_4h':r['decision_time_4h'],'base_state':base,'stalled_active':bool(stalled),'structural_break_active':bool(a),'volatility_damage_active':bool(b)}
        z['persistent_overlay_count']=int(stalled)+int(a)+int(b); z['persistent_overlay_signature']=_sig(stalled,a,b); out.append(z)
    return out

def transition(p,c):
    if not p and not c:return 'STAY_INACTIVE'
    if not p and c:return 'ACTIVATE'
    if p and c:return 'CONTINUE'
    return 'CLEAR'

def transitions_for_lifecycle(states):
    out=[]
    for i in range(1,len(states)):
        a,b=states[i-1],states[i]
        z={'year':b['year'],'pair':b['pair'],'entry_time':b['entry_time'],'native_exit_time':b['native_exit_time'],'from_decision_time_4h':a['decision_time_4h'],'to_decision_time_4h':b['decision_time_4h'],'from_base_state':a['base_state'],'to_base_state':b['base_state'],'base_phase_transition':str(a['base_state'])+'->'+str(b['base_state']),'from_overlay_signature':a['persistent_overlay_signature'],'to_overlay_signature':b['persistent_overlay_signature']}
        parts=[]
        for name,col in [('STALLED','stalled_active'),('STRUCTURAL_BREAK','structural_break_active'),('VOLATILITY_DAMAGE','volatility_damage_active')]:
            t=transition(bool(a[col]),bool(b[col])); z[col+'_transition']=t; parts.append(name+':'+t)
        z['overlay_transition_signature']='|'.join(parts); out.append(z)
    return out
