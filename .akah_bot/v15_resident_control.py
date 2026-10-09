"""Use observed PRIVATE resident high-water, not file-mapping-inclusive RSS.

Keep native counter validation and permanent conservative fallback on missing
samples; fixed physical/commit floors, Job lifetime and heartbeat stay exact.
"""
from pathlib import Path
import v15_adaptive_guard as guard
from v15_private_working_set import displaced_resident

DECISION = guard.decision
OBSERVER = None
INSTALLED = False


class ResidentEnvelope:
    def __init__(self): self.peak = 0; self.native_complete = True

    def action(self, sample, budget_mib, paused=False, *, resident_restore_bytes=None):
        if sample.get('private_working_set_supported') is True:
            # The existing observer checks exact positive/internally bounded
            # counters. Never silently use an inconsistent native value.
            displaced_resident(sample, 0)
            self.peak = max(self.peak, sample['process_private_working_set_bytes'])
        else:
            self.native_complete = False
        envelope = (self.peak if self.native_complete and self.peak > 0
                    and resident_restore_bytes is not None else resident_restore_bytes)
        return DECISION(sample, budget_mib, paused, resident_restore_bytes=envelope)


def reset():
    global OBSERVER
    OBSERVER = ResidentEnvelope()


def action(*args, **kwargs):
    if OBSERVER is None: raise RuntimeError('OWNED_RESIDENT_EPOCH_REQUIRED')
    return OBSERVER.action(*args, **kwargs)


def install():
    global INSTALLED
    if INSTALLED: return
    previous = guard.atomic
    def atomic(path, value):
        if Path(path).name == 'guardian_manifest.json':
            value = dict(value); value['runtime_bindings'] = dict(value['runtime_bindings'])
            value['runtime_bindings']['.akah_bot/v15_resident_control.py'] = guard.sha(__file__)
            value['resident_resume_policy'] = 'OBSERVED_PRIVATE_RESIDENT_PEAK_IF_ALL_NATIVE_SAMPLES_VALID_ELSE_TOTAL_RSS'
        return previous(path, value)
    guard.atomic = atomic; guard.decision = action; INSTALLED = True

