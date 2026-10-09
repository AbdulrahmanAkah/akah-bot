"""Separately bound scaling overlay; the frozen runner still executes all arms."""
import hashlib
import json
import runpy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'.akah_bot')]
from scripts.research.integration_v15 import runner


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


parity_path=ROOT/'.akah_bot/v15_scaling_parity.json'
parity=json.loads(parity_path.read_text())
source=ROOT/'.akah_bot/v15_scaling_acceleration.py'
if sha(source)!=parity['scaling_source_sha256']:
    raise RuntimeError('SCALING_SOURCE_RECEIPT_DRIFT')
for key in ('exact_long_prefix_graph_diagnostics_permission_parity',
            'eighteen_exact_synthetic_output_parity','full_source_enumeration_and_metadata_parity'):
    if parity.get(key) is not True:
        raise RuntimeError('SCALING_EXACT_PARITY_REQUIRED:'+key)
if parity['measured_long_prefix_source_speedup']<3:
    raise RuntimeError('NO_RESTART_WITHOUT_SUBSTANTIAL_MEASURED_SOURCE_SPEEDUP')
tests={}
for name,minimum in (('v15_scaling_unit_results.xml',9),('v15_scaling_regression.xml',590)):
    path=ROOT/'.akah_bot'/name
    result=ET.parse(path).getroot()
    count=len(result.findall('.//testcase'))
    if count<minimum or any(result.findall('.//'+kind) for kind in ('error','failure','skipped')):
        raise RuntimeError('SCALING_REGRESSION_NOT_CLOSED:'+name)
    tests[name]={'sha256':sha(path),'tests':count}
certificate={'source_path':str(source),'sha256':sha(source),
             'launcher_sha256':sha(Path(__file__)), 'tests':tests,
             'parity_receipt_sha256':sha(parity_path), 'parity_report':parity,
             'base_frozen_source_unchanged':True,'all_eighteen_arms_preserved':True,
             'trading_policy_changed':False,'full_source_checks_not_skipped':True,
             'authorization':'User forbids restarting unless substantially faster; measured long-prefix source speedup >=3x.',
             'full_replay_speedup_not_measured':True,
             'authority':'Explicit separate source/runtime certificate; NOT implied by frozen base SHA.'}
import v15_scaling_acceleration
v15_scaling_acceleration.install()
original=runner.execute_authorized


def execute(repo,authorization,output):
    authorization['supplemental_scaling_acceleration']=certificate
    print('EXACT_SCALING_ACCELERATION=ARMED_ALL_EIGHTEEN_ARMS',flush=True)
    original(repo,authorization,output)
    if sha(source)!=certificate['sha256'] or sha(parity_path)!=certificate['parity_receipt_sha256']:
        raise RuntimeError('SCALING_AUTHORITY_CHANGED_DURING_RUN')
    import shutil
    runner.save(output/'supplemental_scaling_certificate.json',certificate)
    for name,binding in tests.items():
        path=ROOT/'.akah_bot'/name
        if sha(path)!=binding['sha256']:
            raise RuntimeError('SCALING_TEST_RECEIPT_DRIFT:'+name)
        shutil.copyfile(path,output/name)
    shutil.copyfile(source,output/'supplemental_scaling_runtime.py')
    shutil.copyfile(parity_path,output/'supplemental_scaling_parity.json')


runner.execute_authorized=execute
runpy.run_path(str(ROOT/'.akah_bot/run_frozen_v15.py'),run_name='__main__')
