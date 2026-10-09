"""Collect ONLY complete, SHA-bound saved arms; use frozen qualification.

No market reader, fitting, new gate, or synthetic profitability certificate.
Missing arm receipts block qualification, never shrink the claim family.
"""
import json
from pathlib import Path
import pandas as pd
import replay_output_transactions as transaction


def read_arm(root,output,session,arm,*,task_id,precommit_sha,source_sha,certificate_sha):
    key=arm.replace('|','_')
    receipt=json.loads((session/(key+'_complete.json')).read_text())
    a=receipt['authority']
    if (receipt['status']!='FULL_FROZEN_ARM_COMPLETED' or a['arm']!=arm
        or a['task_id']!=task_id or a['precommit_sha256']!=precommit_sha
        or a['source_version_sha256']!=source_sha or a['supplemental_certificate_sha256']!=certificate_sha):
        raise RuntimeError('COMPLETE_ARM_AUTHORITY_REQUIRED')
    expected={output/(key+'.json'),output/(key+'_metrics.json')}
    actual=set()
    for b in receipt['outputs']:
        p=(root/b['path']).resolve()
        if p not in expected or transaction.sha(p)!=b['sha256']:
            raise RuntimeError('COMPLETE_ARM_SHA_OR_OUTPUT_SCOPE_DRIFT')
        actual.add(p)
    if actual!=expected:raise RuntimeError('BOTH_ARM_OUTPUTS_REQUIRED')
    # Avoid loading the much larger event ledger merely to collect metrics.
    metrics=json.loads((output/(key+'_metrics.json')).read_text())
    day=metrics['daily_equity']
    index=pd.DatetimeIndex([r['date'] for r in day])
    full=pd.date_range('2022-01-01','2023-12-31',freq='D',tz='UTC')
    if not index.equals(full):raise RuntimeError('SAVED_FULL_DAILY_CASH_CALENDAR_REQUIRED')
    metrics['daily_log']=pd.Series([r['daily_net_mtm_log_return'] for r in day],index=index)
    metrics['annual_net']={int(y):v for y,v in metrics['annual_net'].items()}
    return metrics


def collect(root,frozen,authorization,certificate_sha):
    root=Path(root).resolve()
    requested=frozen['contract']['arms']
    if len(requested)!=18 or len(set(requested))!=18:raise RuntimeError('EXACT_EIGHTEEN_FROZEN_ARMS_REQUIRED')
    output=root/'governance/single_frozen_all_nine_gate3_replay_v15'
    session=root/'.akah_bot/v15_recoverable_session'
    arms={arm:read_arm(root,output,session,arm,task_id=authorization['task_id'],
        precommit_sha=frozen['precommit_sha256'],source_sha=frozen['source_version_sha256'],
        certificate_sha=certificate_sha) for arm in requested}
    from spotbot.research.multi_school_fidelity.gate3_market_v3 import qualify
    qualification=qualify(arms,{'funded_grammars':list(dict.fromkeys(a.split('|')[0] for a in requested))},
                          frozen['contract']['claims'])
    manifest={'authorization':authorization,'precommit_sha256':frozen['precommit_sha256'],
        'arms':requested,'completed_arms':sorted(arms),'technical_failures':{},
        'qualification':'qualification.json; nine fixed claims, no role-incremental claims without ablation',
        'supplemental_certificate_sha256':certificate_sha}
    pointer=session/'collection_publication.json'
    if pointer.exists():binding=json.loads(pointer.read_text())
    else:
        binding=transaction.prepare(session,output,{'qualification.json':qualification,'run_manifest.json':manifest},
                                    {'precommit_sha256':frozen['precommit_sha256'],'certificate_sha256':certificate_sha})
        transaction.json_file(pointer,binding)
    return transaction.publish(binding,session,output,
        {'precommit_sha256':frozen['precommit_sha256'],'certificate_sha256':certificate_sha})
