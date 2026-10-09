from __future__ import annotations


def _b(v):
    if v is None: return False
    if isinstance(v, bool): return v
    if isinstance(v, (int,float)) and v in (0,1): return bool(v)
    s=str(v).strip().lower()
    if s in ('true','1','yes','y'): return True
    if s in ('false','0','no','n','','nan'): return False
    raise ValueError('invalid boolean value: %r' % (v,))


def _sig(stalled, structural, volatility):
    p=[]
    if stalled: p.append('STALLED')
    if structural: p.append('STRUCTURAL_BREAK')
    if volatility: p.append('VOLATILITY_DAMAGE')
    return '+'.join(p) if p else 'NONE'


def _tr(prev,cur):
    if not prev and not cur: return 'STAY_INACTIVE'
    if not prev and cur: return 'ACTIVATE'
    if prev and cur: return 'CONTINUE'
    return 'CLEAR'


class IntegrationAdapter:
    def __init__(self):
        self.lifecycle_key=None
        self.stalled_active=False
        self.prev_snapshot=None

    def reset(self, lifecycle_key):
        self.lifecycle_key=tuple(lifecycle_key)
        self.stalled_active=False
        self.prev_snapshot=None

    def export_checkpoint(self):
        return {
            'lifecycle_key': list(self.lifecycle_key) if self.lifecycle_key is not None else None,
            'stalled_active': bool(self.stalled_active),
            'prev_snapshot': dict(self.prev_snapshot) if self.prev_snapshot is not None else None,
        }

    def restore_checkpoint(self, checkpoint):
        self.lifecycle_key=tuple(checkpoint['lifecycle_key']) if checkpoint['lifecycle_key'] is not None else None
        self.stalled_active=bool(checkpoint['stalled_active'])
        self.prev_snapshot=dict(checkpoint['prev_snapshot']) if checkpoint['prev_snapshot'] is not None else None

    def update(self,row):
        key=(row['year'],row['pair'],row['entry_time'],row['native_exit_time'])
        if self.lifecycle_key != key:
            self.reset(key)
        memory=_b(row['memory_seen']); c=_b(row['C_signal']); base=str(row['base_state'])
        if self.stalled_active and memory: self.stalled_active=False
        if (not self.stalled_active) and c and base=='UNCONFIRMED' and not memory: self.stalled_active=True
        structural=_b(row['a_condition_now']); volatility=_b(row['b_condition_now'])
        snap={
            'year':row['year'],'pair':row['pair'],'entry_time':row['entry_time'],'native_exit_time':row['native_exit_time'],
            'decision_time_4h':row['decision_time_4h'],'base_state':base,
            'stalled_active':bool(self.stalled_active),'structural_break_active':bool(structural),'volatility_damage_active':bool(volatility),
        }
        snap['persistent_overlay_count']=int(self.stalled_active)+int(structural)+int(volatility)
        snap['persistent_overlay_signature']=_sig(self.stalled_active,structural,volatility)
        tr=None
        if self.prev_snapshot is not None:
            a=self.prev_snapshot; b=snap
            tr={
                'year':b['year'],'pair':b['pair'],'entry_time':b['entry_time'],'native_exit_time':b['native_exit_time'],
                'from_decision_time_4h':a['decision_time_4h'],'to_decision_time_4h':b['decision_time_4h'],
                'from_base_state':a['base_state'],'to_base_state':b['base_state'],
                'base_phase_transition':str(a['base_state'])+'->'+str(b['base_state']),
                'from_overlay_signature':a['persistent_overlay_signature'],'to_overlay_signature':b['persistent_overlay_signature'],
            }
            parts=[]
            for label,col in [('STALLED','stalled_active'),('STRUCTURAL_BREAK','structural_break_active'),('VOLATILITY_DAMAGE','volatility_damage_active')]:
                t=_tr(bool(a[col]),bool(b[col])); tr[col+'_transition']=t; parts.append(label+':'+t)
            tr['overlay_transition_signature']='|'.join(parts)
        self.prev_snapshot=dict(snap)
        return snap,tr
