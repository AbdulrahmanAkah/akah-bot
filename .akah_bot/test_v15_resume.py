from datetime import datetime,timedelta,timezone
from collections import deque
import pytest
import v15_checkpoints as checkpoints
import v15_resumable_scheduler as scheduler
from spotbot.research.multi_school_fidelity.integration_v14 import scheduler as baseline
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest


class StubSource:
    def __init__(self):self.calls=[]
    def on_completed_hour(self,packet):self.calls.append(('WARMUP',packet))


class StubDriver:
    def __init__(self):self.source=StubSource();self.calls=[]
    def on_open(self,packet):self.calls.append(('OPEN',packet))
    def on_completed_hour(self,packet):self.calls.append(('CLOSE',packet))
    def outputs(self):return digest((self.source.calls,self.calls))


def streams():
    start=datetime(2021,12,30,tzinfo=timezone.utc)
    values={p:[] for p in ('BTC-USDT','ETH-USDT')}
    for i in range(96):
        at=start+timedelta(hours=i)
        for pair in values:
            if pair=='ETH-USDT' and i in (18,19):continue
            price=100.+i
            values[pair].append((CompletedBar(at,at+timedelta(hours=1),'1H',price,price+2.,price-1.,price+.5),float(i+1)))
    return values


@pytest.mark.parametrize('hour',[1,24,47,48,49,60,95,96])
def test_scheduler_continuous_vs_checkpoint_resume_exact(tmp_path,monkeypatch,hour):
    end=datetime(2022,1,2,23,tzinfo=timezone.utc)
    monkeypatch.setattr(scheduler,'LAST_OPEN',end)
    monkeypatch.setattr(baseline,'LAST_OPEN',end)
    old=StubDriver();expected=baseline.ScopedScheduler(streams()).run(old)
    consumer=StubDriver()
    stop=datetime(2021,12,30,tzinfo=timezone.utc)+timedelta(hours=hour)
    state=scheduler.ResumableScheduler(streams()).run(consumer,stop_at=stop)
    authority={'fixture':'SYNTHETIC_ONLY','cursor':str(state['cursor'])}
    receipt=checkpoints.write_checkpoint(tmp_path,{'driver':consumer,'scheduler':state},authority)
    saved=checkpoints.read_checkpoint(receipt,authority)
    result=scheduler.ResumableScheduler(streams()).run(saved['driver'],restored=saved['scheduler'])
    assert result==expected
    assert saved['driver'].calls==old.calls
    assert saved['driver'].source.calls==old.source.calls


def test_real_driver_pipeline_source_graph_roundtrip(tmp_path):
    import v15_bounded_storage as storage
    storage.install()
    from scripts.research.integration_v15 import runner
    import json
    from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import MembershipSnapshot,MembershipSource
    frozen=json.loads((runner.Path.cwd()/runner.OUT/'gate3_precommit.json').read_text())
    ready=json.loads((runner.Path.cwd()/runner.OUT/'readiness_certificate.json').read_text())
    start=datetime(2021,9,1,tzinfo=timezone.utc)
    members=MembershipSource((MembershipSnapshot(start,datetime(2024,1,1,tzinfo=timezone.utc),frozenset({'BTC-USDT','ETH-USDT'}),'A'*64),))
    scope=runner.ResearchScope(frozen['source_hashes'][runner.PROTOCOL],frozen['source_version_sha256'])
    certs=tuple(runner.ProducerCertificate(g,scope.source_version_sha256,scope.protocol_sha256,'a'*64,
        'SOURCE_BOUND_RESEARCH_IMPLEMENTATION_PASS','SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION') for g in runner.FUNDED)
    source=runner.ScopedSourceProvider({'BTC-USDT':'B'*64,'ETH-USDT':'C'*64},members,scope.source_version_sha256)
    execution=runner.ScopedExecution(runner.Portfolio(.0025,{p:runner.ApproximateRule(p,scope) for p in source.feeds}))
    source.attach_execution(execution)
    driver=runner.ScopedDriver(runner.Path.cwd(),frozen,runner.ScopedPipeline(execution,runner.ScopedRouter(scope,certs)),
        source,arm=runner.FUNDED[0]+'|1X',readiness_receipt=ready,certificate_provider=checkpoints.Certificates(certs))
    from test_v15_checkpoints import advance,signature
    advance(source,0,24)
    before=signature(source)
    receipt=checkpoints.write_checkpoint(tmp_path,{'driver':driver},{'purpose':'SYNTHETIC_WARMUP_FULL_CONSUMER'})
    restored=checkpoints.read_checkpoint(receipt,{'purpose':'SYNTHETIC_WARMUP_FULL_CONSUMER'})['driver']
    assert signature(restored.source)==before
    assert restored.source.execution is restored.pipeline.execution
    assert restored.pipeline.execution.context_validator.__self__ is restored
    assert restored.pipeline.execution.selector_receipt_hook.__self__ is restored
    assert restored.pipeline.execution.receipt_graph is restored.trace
    advance(source,24,36);advance(restored.source,24,36)
    assert signature(restored.source)==signature(source)


class SyntheticOwnedSource:
    """Pickleable explicit fixture; never permitted as market authority."""
    def __init__(self,original,requests,grammar):
        from spotbot.research.multi_school_fidelity.integration_v12.producers import ContractProducer
        # FixtureProducer's only extra behavior manufactures bool membership
        # before emission. Already-sealed requests use the real base producer.
        producer=ContractProducer.__new__(ContractProducer)
        producer.__dict__.update(original.producer.__dict__)
        from dataclasses import replace
        self.producer=producer
        self.pending=tuple(replace(r,producer=producer) for r in requests)
        self.permission=original.permission
        self.grammar=grammar;self.feedback=[];self.calls=[]
    def issues_at_open(self,at):
        value=self.pending;self.pending=();self.calls.append(('OPEN',at));return value
    def on_completed_hour(self,packet):
        self.calls.append(('CLOSE',packet.bars[0][1].end))
        p=self.producer.prefix
        for (_,bar),(_,volume) in zip(packet.bars,packet.volumes,strict=True):
            if p.bar_id(bar) not in p.graph.nodes:p.on_close(bar,volume,bar.end)
        from spotbot.research.multi_school_fidelity.integration_v15.authority import FUNDED
        if self.grammar==FUNDED[2]:
            from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Known
            bar=packet.bars[0][1]
            psha=p.sha
            parents=(p.bar_id(bar),)
            membership=p.source_claim('resume-fixture-membership',True,bar.end,'member',parents,psha)
            for sid in tuple(self.producer.harmonics):
                self.producer.harmonic_close(sid,bar,pit_eligible=membership)
        return ()
    def producer_for(self,pair,structure_id):return self.producer
    def on_execution_receipt(self,receipt):
        self.feedback.append(receipt);self.calls.append(('RECEIPT',receipt.at))


@pytest.mark.parametrize('index',range(9))
@pytest.mark.parametrize('scenario',['1X','2X'])
def test_open_campaign_state_resume_exact_all_eighteen(tmp_path,index,scenario):
    from benchmark_v15_acceleration import module,ROOT
    fmod=module(ROOT/'tests/research/integration_v15/test_closure.py','resume_fixture_closure')
    helper=module(ROOT/'tests/research/integration_v13/test_guarded_driver.py','resume_fixture_helper')
    fmod._HELPERS=helper
    lineage=helper.lineage.__wrapped__();fixture=helper.f.__wrapped__(lineage)
    grammar=fmod.FUNDED[index]
    original,issue,h,price=fmod.source_arm(fixture,lineage,grammar)
    fmod.permit(original,fixture,h)
    source=SyntheticOwnedSource(original,original.issues_at_open(fixture.at(h)),grammar)
    driver=fmod.make(helper,fixture,source,arm=grammar+'|'+scenario)
    driver.certificate_provider=checkpoints.Certificates(tuple(driver.pipeline.router.certificates.values()))
    assert driver.on_open(helper.open_packet(fixture,h,price))[0]
    receipt=checkpoints.write_checkpoint(tmp_path,{'driver':driver},{'purpose':'SYNTHETIC_OPEN_CAMPAIGN','arm':driver.arm})
    restored=checkpoints.read_checkpoint(receipt,{'purpose':'SYNTHETIC_OPEN_CAMPAIGN','arm':driver.arm})['driver']
    assert restored.pipeline.execution.context_validator.__self__ is restored
    assert restored.pipeline.execution.receipt_graph is restored.trace
    stop=driver.pipeline.execution.managers[1].hard_stop
    bar=(fixture.bar(h,price,issue.thesis.objectives[-1]+1,price-.5,issue.thesis.objectives[-1])
        if index==2 else fixture.bar(h,price,price+1,stop-1,stop))
    driver.on_completed_hour(helper.close_packet(fixture,bar))
    restored.on_completed_hour(helper.close_packet(fixture,bar))
    assert digest(driver.outputs())==digest(restored.outputs())
    assert restored.source.feedback==driver.source.feedback
