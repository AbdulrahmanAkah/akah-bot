import hashlib
import importlib.metadata
import json
import subprocess
import zipfile
from pathlib import Path

R=Path(__file__).resolve().parents[1]
def git(*a):return subprocess.check_output(['git',*a],cwd=R,text=True).strip()
assert git('rev-parse','HEAD')=='23020400d26d24dfa02decfbca2f74d0086812f7'
assert git('branch','--show-current')=='research/rd48-cross-venue-price-level-basis-direct-utility-v1'
assert not git('diff','--name-only') and not git('diff','--cached','--name-only')
assert not (R/'.akah_bot/active_task.json').exists()
raw=(R/'governance/AKAH_BOT_SYSTEM_CHARTER.json').read_bytes()
c=json.loads(raw);assert c['charter_revision']==782
receipt=json.loads((R/'.akah_bot/transition_sync_782_uw6b3npo/verified_receipt.json').read_bytes())
assert receipt['verification']=='PASS' and receipt['manifest']['charter_revision']==782
assert receipt['manifest']['source_head']==git('rev-parse','HEAD')
assert receipt['manifest']['canonical_local_charter']['sha256']==hashlib.sha256(raw).hexdigest().upper()
assert git('ls-remote','origin','refs/heads/governance/akah-system-charter-live').split()[0]==receipt['remote_commit']
review=Path('C:/Users/abdul/Downloads/AKAH_REV782_V10_INDEPENDENT_REVIEW.zip')
assert hashlib.sha256(review.read_bytes()).hexdigest().upper()=='FA6D3758A0811D6CA70EEE3271EC7D35D9A023708D6327EEABE66285F86A3D45'
with zipfile.ZipFile(review) as z:
    for name,meta in json.loads(z.read('MANIFEST.json')).items():
        assert hashlib.sha256(z.read(name)).hexdigest().upper()==meta['sha256']
old=json.loads((R/'governance/four_source_repairs_v10/input_authority_manifest.json').read_bytes())
for a in old['inputs']+old['preserved_sources_and_authorities']:
    p=R/a['path'];assert hashlib.sha256(p.read_bytes()).hexdigest().upper()==a['sha256']
    if p.suffix=='.py':compile(p.read_text(encoding='utf-8-sig'),str(p),'exec')
for rel in ('src/spotbot/research/multi_school_fidelity/integration_v11/contracts.py',
            'tests/research/integration_v11/test_integrity.py',
            'scripts/research/integration_v11/certify.py'):
    assert not (R/rel).exists()
    assert subprocess.run(['git','check-ignore','--',rel],cwd=R,capture_output=True).returncode==1
print(json.dumps(dict(preflight='PASS',revision=782,remote_commit=receipt['remote_commit'],
    authority_hashes='PASS',tracked_index_clean=True,old_compile='PASS',stageability='PASS',
    arch=importlib.metadata.version('arch'),pytest=importlib.metadata.version('pytest'),
    output='governance/source_integrity_closure_v11',no_market_access=True)))
