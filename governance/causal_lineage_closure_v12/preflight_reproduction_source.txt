"""Read-only repository authority and synthetic V11 lineage reproduction."""
import ast
import hashlib
import importlib.util
import json
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
START='203ee785c1546937172aaee6f487f6b76821d3ad'
REMOTE='f533d32a8f2f132e7b9c64e472f74fb93f323bb2'
REVIEW=Path('C:/Users/abdul/Downloads/AKAH_REV783_V11_INDEPENDENT_REVIEW_RESULT.zip')
REVIEW_SHA='D9B94E84AC1F5B363E3776B1B5FD7AC7D93E6077A74C513FC1F7DC859A264148'


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def load_fixture():
    path=ROOT/'tests/research/integration_v11/test_integrity.py'
    spec=importlib.util.spec_from_file_location('v12_existing_source_fixture',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tree=ast.parse(path.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
            and n.name=='test_h3_sealed_isolated_composition')
    body=[]
    for n in fn.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='pipe'
                                           for t in n.targets):
            break
        body.append(n)
    fn.name='h3_source';fn.decorator_list=[]
    fn.args=ast.arguments(posonlyargs=[],args=[ast.arg(arg='f')],kwonlyargs=[],
                          kw_defaults=[],defaults=[])
    fn.body=body+[ast.parse('return p,c,r,location,hybrid').body[0]]
    exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),
                 str(path),'exec'),module.__dict__)
    return module


def type2_source(f):
    p,c,sid,r=f.harmonic_source()
    pipe=f.PipelineV9(f.kernel(),f.RouterV9(synthetic_fixture_execution=True))
    env=pipe.bind(r,p,f.state(),f.context(p,f.at(19)))
    assert pipe.on_open(f.at(19),{f.PAIR:213},{f.PAIR:100000},(env,),
                        research_authorized=True)[0]
    cid=pipe.execution.portfolio.k.positions[1]['campaign_id']
    final=r.thesis.objectives[1]
    bar=f.bar(19,213,final+1,212,final)
    p.on_close(bar,1,bar.end)
    c.harmonic_close(sid,bar,pit_eligible=f.pit(p,f.at(20)))
    pipe.on_completed_hour({f.PAIR:bar},capacities={f.PAIR:100000})
    assert not pipe.execution.portfolio.k.positions
    pipe.acknowledge_harmonic_completion(c,sid,'HARMONIC_TYPE_I',f.at(20),cid)
    receipt=next(node.evidence for node in p.graph.nodes.values()
                 if node.evidence.value==('CAMPAIGN_CLOSED','HARMONIC_TYPE_I'))
    pipe.on_open(f.at(20),{f.PAIR:213},{f.PAIR:100000},research_authorized=True)
    bar=f.bar(20,213,214,209.95,211);p.on_close(bar,1,bar.end)
    assert c.harmonic_close(sid,bar,pit_eligible=f.pit(p,f.at(21))) is None
    pipe.on_completed_hour({f.PAIR:bar},capacities={f.PAIR:100000})
    pipe.on_open(f.at(21),{f.PAIR:211},{f.PAIR:100000},research_authorized=True)
    bar=f.bar(21,211,217,210,215);p.on_close(bar,1,bar.end)
    second=c.harmonic_close(sid,bar,pit_eligible=f.pit(p,f.at(22)))
    pipe.on_completed_hour({f.PAIR:bar},capacities={f.PAIR:100000})
    return p,c,sid,second,pipe,receipt,cid


def main():
    assert git('rev-parse','HEAD')==START
    assert git('branch','--show-current')=='research/rd48-cross-venue-price-level-basis-direct-utility-v1'
    assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
    assert not (ROOT/'.akah_bot/active_task.json').exists()
    charter=json.loads((ROOT/'governance/AKAH_BOT_SYSTEM_CHARTER.json').read_bytes())
    assert charter['charter_revision']==783
    charter_sha=sha(ROOT/'governance/AKAH_BOT_SYSTEM_CHARTER.json')
    assert charter_sha=='239E11DE3CD58EEAC763E74C04515B9B3970E1533ABA92C8987EE2D51C33C851'
    assert git('ls-remote','origin','refs/heads/governance/akah-system-charter-live').split()[0]==REMOTE
    manifest=json.loads(git('show',REMOTE+':governance/AKAH_BOT_SYSTEM_CHARTER_GITHUB_SYNC_MANIFEST.json'))
    assert manifest['charter_revision']==783 and manifest['source_head']==START
    assert manifest['canonical_local_charter']['sha256']==charter_sha
    assert sha(REVIEW)==REVIEW_SHA
    with zipfile.ZipFile(REVIEW) as z:
        for name,item in json.loads(z.read('MANIFEST.json')).items():
            assert hashlib.sha256(z.read(name)).hexdigest().upper()==item['sha256']
            assert len(z.read(name))==item['bytes']
        review=json.loads(z.read('AKAH_REV783_V11_INDEPENDENT_LOCKED_REVIEW.json'))
    assert review['locked'] and review['packet_sha256']==sha(
        'C:/Users/abdul/Downloads/AKAH_REV783_V11_INDEPENDENT_REVIEW.zip')
    assert len(review['new_remaining_findings'])==2
    old=json.loads((ROOT/'governance/source_integrity_closure_v11/input_authority_manifest.json').read_text())
    for item in old['inputs']+old['preserved_sources_and_authorities']:
        path=ROOT/item['path'];assert sha(path)==item['sha256']
        if path.suffix=='.py':compile(path.read_text(encoding='utf-8-sig'),str(path),'exec')
    for rel in ('src/spotbot/research/multi_school_fidelity/integration_v12/producers.py',
                'tests/research/integration_v12/test_lineage.py',
                'scripts/research/integration_v12/certify.py'):
        assert not (ROOT/rel).exists()
        assert subprocess.run(['git','check-ignore','--',rel],cwd=ROOT,
                              capture_output=True).returncode==1
    module=load_fixture()
    findings=[]
    for which in ('count','location'):
        f=module.f.__wrapped__();p,c,count,loc,hybrid=module.h3_source(f)
        phase=f.StructuralPhase.MARKUP
        pipe=f.PipelineV9(f.kernel(),f.RouterV9(synthetic_fixture_execution=True))
        env=pipe.bind(hybrid,p,f.state(phase),f.context(p,f.at(57),phase))
        seal=count.emission_id if which=='count' else loc.emission_id
        assert seal not in hybrid.evidence_ids
        p.graph.terminate(seal)
        selected,denied=pipe.on_open(f.at(57),{f.PAIR:190},{f.PAIR:100000},
                                      (env,),research_authorized=True)
        assert selected and not denied and len(pipe.execution.portfolio.k.fills)==1
        findings.append(dict(finding='F4',parent=which,seal_missing=True,
                             revoked_parent_filled=True,synthetic=True))
    f=module.f.__wrapped__()
    p,c,sid,second,pipe,receipt,cid=type2_source(f)
    assert receipt.event_id not in second.evidence_ids
    env=pipe.bind(second,p,f.state(),f.context(p,f.at(22)))
    p.graph.terminate(receipt.event_id)
    selected,denied=pipe.on_open(f.at(22),{f.PAIR:215},{f.PAIR:100000},
                                  (env,),research_authorized=True)
    assert selected and not denied
    findings.append(dict(finding='F5',receipt_missing=True,revoked_receipt_filled=True,synthetic=True))
    result=dict(preflight='PASS',findings_confirmed= ['F4','F5'],reproductions=findings,
        revision=783,head=START,charter_sha256=charter_sha,remote_governance_commit=REMOTE,
        review_sha256=REVIEW_SHA,old_authorities_verified=True,tracked_index_clean=True,
        stageability='PASS',old_compile='PASS',period='SYNTHETIC_2023_ONLY',
        raw_market_rows=False,pnl_read=False,economic_replay=False,
        preflight_script_sha256=sha(__file__))
    (ROOT/'.akah_bot/v12_preflight_result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
