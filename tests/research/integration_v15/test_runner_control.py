"""Mock-only runner control flow: no source callback, market row, or fill."""
import json
from types import SimpleNamespace
from pathlib import Path
from scripts.research.integration_v15 import runner
from scripts.research.integration_v15.precommit import build
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError


def test_mock_arm_failure_retained_all_eighteen_attempted_no_claim_shrink(monkeypatch,tmp_path):
    import spotbot.research.multi_school_fidelity.integration_v15.scheduler as scheduler
    import spotbot.research.multi_school_fidelity.integration_v15.evaluation as evaluation
    import spotbot.research.multi_school_fidelity.gate3_market_v3 as qualification
    frozen=build(Path.cwd())
    (tmp_path/runner.OUT).mkdir(parents=True)
    (tmp_path/runner.INPUT_MANIFEST).parent.mkdir(parents=True)
    (tmp_path/runner.OUT/"gate3_precommit.json").write_text(json.dumps(frozen))
    (tmp_path/runner.OUT/"readiness_certificate.json").write_text(json.dumps({
        "evidence":{"synthetic_results.xml":{"sha256":"a"*64}}}))
    (tmp_path/runner.INPUT_MANIFEST).write_text(json.dumps({
        "pairs":[{"pair":"BTC-USDT","bounded_sha256":"b"*64}]}))
    (tmp_path/".akah_bot").mkdir()
    task="AKAH_SINGLE_FROZEN_ALL_NINE_GATE3_REPLAY_V15"
    (tmp_path/".akah_bot/active_task.json").write_text(json.dumps({"task_id":task}))
    monkeypatch.setattr(runner,"preflight",lambda *_:None)
    monkeypatch.setattr(runner,"membership",lambda *_:None)
    monkeypatch.setattr(runner,"raw_frame",lambda *_:(_ for _ in ()).throw(AssertionError("market read")))
    class Source:
        def __init__(self,*args):pass
        def attach_execution(self,execution):pass
    class Driver:
        def __init__(self,*args,arm,**kwargs):
            self.arm,self.pipeline,self.equity,self.diagnostics=arm,args[2],[],[]
    attempted=[]
    class Scheduler:
        def __init__(self,streams):pass # never consume a source iterator
        def run(self,driver):
            attempted.append(driver.arm)
            if len(attempted)==1:raise ContractError("MOCK_TECHNICAL_FAILURE")
            return {"disposition":"MOCK_CONTROL_FLOW_NOT_ECONOMIC_EVIDENCE"}
    monkeypatch.setattr(runner,"ScopedSourceProvider",Source)
    monkeypatch.setattr(runner,"ScopedDriver",Driver)
    monkeypatch.setattr(scheduler,"ScopedScheduler",Scheduler)
    monkeypatch.setattr(evaluation,"summarize_arm",lambda *_:{"campaigns":[],"daily_log":{},"daily_equity":[]})
    monkeypatch.setattr(qualification,"qualify",lambda *_:(_ for _ in ()).throw(AssertionError("reduced claim family")))
    output=tmp_path/"governance/mock_only_control_test"
    runner.execute_authorized(tmp_path,{"task_id":task,"explicit_user_replay_authorization":True,
        "precommit_sha256":frozen["precommit_sha256"]},output)
    assert attempted==frozen["contract"]["arms"] and len(attempted)==18
    manifest=json.loads((output/"run_manifest.json").read_text())
    assert len(manifest["completed_arms"])==17 and len(manifest["technical_failures"])==1
    result=json.loads((output/"qualification.json").read_text())
    assert result["claim_family_not_reduced"] and result["status"].startswith("TECHNICAL_FAIL_CLOSED")
