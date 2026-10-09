"""Operational launcher only; the frozen runner owns all economic decisions."""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo))
os.chdir(repo)
from scripts.research.integration_v15.runner import execute_authorized

authorization = json.loads((repo / ".akah_bot/v15_replay_authorization.json").read_text(encoding="utf-8"))
authorization["launcher_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper()
authorization["closeout_sha256"] = hashlib.sha256((repo / ".akah_bot/finish_frozen_v15.py").read_bytes()).hexdigest().upper()
supplement = repo / '.akah_bot/v15_acceleration_parity.json'
if supplement.is_file():
    accelerator_path = repo / '.akah_bot/v15_exact_acceleration.py'
    parity = json.loads(supplement.read_text(encoding='utf-8'))
    actual = hashlib.sha256(accelerator_path.read_bytes()).hexdigest().upper()
    if actual != parity.get('accelerator_sha256'):
        raise RuntimeError('SUPPLEMENTAL_ACCELERATOR_SOURCE_DRIFT')
    if not (parity.get('synthetic_eighteen_exact_output_parity') is True
            and parity.get('source_graph_diagnostics_permission_exact_parity') is True):
        raise RuntimeError('EXACT_DIFFERENTIAL_PARITY_REQUIRED')
    bindings = {}
    for name, minimum in (('v15_acceleration_unit_results.xml', 11), ('v15_acceleration_regression.xml', 600)):
        path = repo / '.akah_bot' / name
        tree = ET.parse(path).getroot()
        cases = tree.findall('.//testcase')
        if len(cases) < minimum or tree.findall('.//failure') or tree.findall('.//error') or tree.findall('.//skipped'):
            raise RuntimeError('SUPPLEMENTAL_ACCELERATION_TESTS_NOT_CLOSED:' + name)
        bindings[name] = {'sha256':hashlib.sha256(path.read_bytes()).hexdigest().upper(), 'tests':len(cases)}
    sys.path.insert(0, str(repo / '.akah_bot'))
    import v15_exact_acceleration
    v15_exact_acceleration.install()
    authorization['supplemental_runtime_acceleration'] = {
        'source_path':'.akah_bot/v15_exact_acceleration.py', 'sha256':actual,
        'base_frozen_source_unchanged':True, 'trading_decisions_not_cached':True,
        'parity_receipt_sha256':hashlib.sha256(supplement.read_bytes()).hexdigest().upper(),
        'tests':bindings, 'measured_bounded_source_speedup':parity['source_speedup'],
        'full_replay_speedup_not_yet_measured':True,
        'user_authorization':'Direct user request to accelerate without loss of accuracy.',
        'authority':'Explicit supplemental runtime implementation, NOT covered by the base source SHA alone.'}
    print('EXACT_RUNTIME_ACCELERATION=ARMED_WITH_SUPPLEMENTAL_AUTHORITY',flush=True)
print("REPLAY_STARTED_AT=" + datetime.now(timezone.utc).isoformat(), flush=True)
print("FROZEN_PRECOMMIT_SHA256=" + authorization["precommit_sha256"], flush=True)
print("REQUESTED_ARMS=18", flush=True)
execute_authorized(repo, authorization, repo / "governance/single_frozen_all_nine_gate3_replay_v15")
if 'supplemental_runtime_acceleration' in authorization:
    expected = authorization['supplemental_runtime_acceleration']['sha256']
    if hashlib.sha256(accelerator_path.read_bytes()).hexdigest().upper() != expected:
        raise RuntimeError('ACCELERATOR_DRIFT_DURING_REPLAY_NO_QUALIFICATION_CLOSEOUT')
    from scripts.research.integration_v15.runner import save
    saved = repo / 'governance/single_frozen_all_nine_gate3_replay_v15'
    save(saved/'supplemental_acceleration_certificate.json',
         dict(authorization['supplemental_runtime_acceleration'], parity_report=parity))
    import shutil
    shutil.copyfile(accelerator_path, saved/'supplemental_runtime_accelerator.py')
    for name, binding in bindings.items():
        original = repo / '.akah_bot' / name
        if hashlib.sha256(original.read_bytes()).hexdigest().upper() != binding['sha256']:
            raise RuntimeError('SUPPLEMENTAL_TEST_EVIDENCE_DRIFT:' + name)
        shutil.copyfile(original, saved/name)
    if hashlib.sha256(supplement.read_bytes()).hexdigest().upper() != authorization['supplemental_runtime_acceleration']['parity_receipt_sha256']:
        raise RuntimeError('SUPPLEMENTAL_PARITY_RECEIPT_DRIFT')
    shutil.copyfile(supplement, saved/'supplemental_exact_parity_report.json')
print("REPLAY_FINISHED_AT=" + datetime.now(timezone.utc).isoformat(), flush=True)
from finish_frozen_v15 import finish
finish(repo, authorization)
