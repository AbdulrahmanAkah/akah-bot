import hashlib
import json
import pathlib
import subprocess

R = pathlib.Path(__file__).resolve().parents[1]
TASK = 'AKAH_FOUR_SOURCE_REPAIRS_AND_UNUSED_RESERVE_PREPARATION_V10'
def git(*a):
    return subprocess.check_output(['git', *a], cwd=R, text=True).strip()
assert git('rev-parse','HEAD') == '720c45c38d3edfd2042430d253cdbafb94ae8277'
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
assert not (R/'.akah_bot/active_task.json').exists()
c = json.loads((R/'governance/AKAH_BOT_SYSTEM_CHARTER.json').read_bytes())
assert c['charter_revision'] == 781
receipt = json.loads((R/'.akah_bot/transition_sync_781_0np2fo57/verified_receipt.json').read_bytes())
assert receipt['manifest']['charter_revision'] == 781
assert receipt['manifest']['source_head'] == git('rev-parse','HEAD')
assert receipt['manifest']['canonical_local_charter']['sha256'] == hashlib.sha256((R/'governance/AKAH_BOT_SYSTEM_CHARTER.json').read_bytes()).hexdigest().upper()
old = json.loads((R/'governance/producer_integration_bundle_v9/input_authority_manifest.json').read_bytes())
for x in old['inputs'] + old['preserved_source_blobs'] + old['authorities']:
    p=R/x['path']; assert hashlib.sha256(p.read_bytes()).hexdigest().upper() == x['sha256'], p
    if p.suffix == '.py': compile(p.read_text(encoding='utf-8-sig'),str(p),'exec')
for p in ['src/spotbot/research/multi_school_fidelity/integration_v10/producer.py', 'tests/research/integration_v10/test_repairs.py', 'governance/four_source_repairs_v10/research_protocol.json']:
    assert not (R/p).exists()
    assert subprocess.run(['git','check-ignore','--',p],cwd=R,capture_output=True).returncode == 1
print(json.dumps({'task':TASK,'revision':781,'authority_hashes':'PASS','compile':'PASS','tracked_clean':True,'sync_authority':'EXISTING_SHA_BOUND_REV781_RECEIPT_NOT_NEW_NETWORK_CHECK','no_raw_or_economic_access':True}))
