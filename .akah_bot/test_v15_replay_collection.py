"""Synthetic saved-artifact fixtures, never market/economic outcomes."""
import json
from pathlib import Path
import pytest
import v15_replay_collection as c
import replay_output_transactions as t


def fixture(tmp_path):
    out=(tmp_path/'governance/single_frozen_all_nine_gate3_replay_v15').resolve();out.mkdir(parents=True)
    session=tmp_path/'.akah_bot/v15_recoverable_session';session.mkdir(parents=True)
    arms=[f'SYNTHETIC_{i}|{cost}' for i in range(9) for cost in ('1X','2X')]
    frozen={'precommit_sha256':'P','source_version_sha256':'S','contract':{'arms':arms,'claims':['FROZEN_FIXTURE']}}
    days=[{'date':str(at),'equity':100000.,'daily_net_mtm_log_return':0.}
          for at in c.pd.date_range('2022-01-01','2023-12-31',freq='D',tz='UTC')]
    for arm in arms:
        key=arm.replace('|','_')
        metrics={'daily_equity':days,'annual_net':{2022:0.,2023:0.},'fixture_only':True}
        t.json_file(out/(key+'.json'),{'fixture_only':True})
        t.json_file(out/(key+'_metrics.json'),metrics)
        a={'arm':arm,'task_id':'T','precommit_sha256':'P','source_version_sha256':'S','supplemental_certificate_sha256':'C'}
        t.json_file(session/(key+'_complete.json'),{'authority':a,'status':'FULL_FROZEN_ARM_COMPLETED',
            'outputs':[{'path':p.relative_to(tmp_path).as_posix(),'sha256':t.sha(p)}
                for p in (out/(key+'.json'),out/(key+'_metrics.json'))]})
    return out,session,arms,frozen


def test_exact_saved_daily_log_and_year_key_restoration(tmp_path):
    out,session,arms,frozen=fixture(tmp_path)
    result=c.read_arm(tmp_path,out,session,arms[0],task_id='T',precommit_sha='P',source_sha='S',certificate_sha='C')
    assert result['annual_net']=={2022:0.,2023:0.}
    assert len(result['daily_log'])==730
    assert result['daily_log'].index.tz is not None
    assert result['daily_log'].to_numpy().tolist()==[0.]*730


def test_no_reduced_claim_family_or_real_qualification(tmp_path,monkeypatch):
    out,session,arms,frozen=fixture(tmp_path)
    from spotbot.research.multi_school_fidelity import gate3_market_v3 as frozen_evaluation
    calls=[]
    def synthetic_only(summaries,config,claims):
        calls.append((list(summaries),config,claims));return {'SYNTHETIC_ONLY':True}
    monkeypatch.setattr(frozen_evaluation,'qualify',synthetic_only)
    c.collect(tmp_path,frozen,{'task_id':'T'},'C')
    assert calls==[(arms,{'funded_grammars':[f'SYNTHETIC_{i}' for i in range(9)]},['FROZEN_FIXTURE'])]
    assert json.loads((out/'run_manifest.json').read_text())['completed_arms']==sorted(arms)


def test_missing_or_corrupt_arm_never_qualified(tmp_path,monkeypatch):
    out,session,arms,frozen=fixture(tmp_path)
    (out/(arms[-1].replace('|','_')+'_metrics.json')).write_text('{}')
    from spotbot.research.multi_school_fidelity import gate3_market_v3 as frozen_evaluation
    monkeypatch.setattr(frozen_evaluation,'qualify',lambda *a:pytest.fail('MISSING_SCOPE_MUST_BLOCK'))
    with pytest.raises(RuntimeError,match='SHA_OR_OUTPUT_SCOPE_DRIFT'):
        c.collect(tmp_path,frozen,{'task_id':'T'},'C')
    assert not (out/'qualification.json').exists()
