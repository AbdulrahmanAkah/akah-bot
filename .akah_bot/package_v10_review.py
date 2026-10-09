"""External review handoff; explicitly not a historical chart reserve."""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGET=Path('C:/Users/abdul/Downloads/AKAH_V10_FOUR_REPAIRS_AND_RESERVE_PREPARATION_REV782_20261004.zip')
assert not TARGET.exists(), 'DO_NOT_OVERWRITE_EXISTING_HANDOFF'
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
assert head=='23020400d26d24dfa02decfbca2f74d0086812f7'
assert not (ROOT/'.akah_bot/active_task.json').exists()
assert not subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).strip()
assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT,text=True).strip()
paths=list((ROOT/'src/spotbot/research/multi_school_fidelity').rglob('*.py'))
paths += [ROOT/p for p in ('src/spotbot/__init__.py','src/spotbot/research/__init__.py','pyproject.toml') if (ROOT/p).is_file()]
paths += list((ROOT/'governance/four_source_repairs_v10').glob('*'))
paths += list((ROOT/'scripts/research/integration_v10').glob('*.py'))
paths += list((ROOT/'tests/research/integration_v10').glob('*.py'))
paths += list((ROOT/'tests/research/integration_v9').glob('*.py'))
paths += [ROOT/'tests/research'/p for p in ('test_school_ownership_bundle_v8.py',
    'test_campaign_execution_v7.py','test_structural_lifecycle_v6.py',
    'test_full_replay_v4.py','test_full_replay_v5.py','test_gate3_market_v3.py',
    'test_multi_school_fidelity.py')]
paths=sorted(set(p for p in paths if p.is_file()))
manifest=[]
for p in paths:
    rel=p.relative_to(ROOT).as_posix()
    assert p.suffix in ('.py','.md','.json','.xml','.toml') or p.name=='.gitattributes'
    manifest.append(dict(path=rel,bytes=p.stat().st_size,
        sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper()))
readme='''# V10 source-repair review / reserve PREPARATION handoff

This is NOT an unused historical market-fidelity chart packet.
FRESH_MARKET_RESERVE_READY=NO. No chart/case payloads are included.
Technical repair status=PASS; exact-version historical source/reserve authority
remains blocked. Neither synthetic tests nor old exposed reserve certify Gate 2.

Start with governance/four_source_repairs_v10/canonical_result.json,
IMPLEMENTATION_CONTRACT.md and repair_closure_matrix.json. Independently audit:
1. Owner-specific stop derivation, exact price/source/metadata parity, H3 ownership.
2. Full Wyckoff dependency graph through executable open; no stale resurrection.
3. Actual staged-fill receipt linking source cause and kernel campaign; unchanged B0.
4. Exact isolated prebatch admission before same-asset conflict, final sequential checks.
5. Explicit nontruncated Elliott scope; no invented funded truncation profile.
6. Negative tests, real-mode funding denial and preserved V4-V9 code.
7. Whether stated source-to-kernel synthetic scope matches evidence, especially H3.
8. Fresh reserve blockers and exclusion contract; never approve nonexistent chart data.

Provide findings with source path/function, severity, proof and required correction.
Preserve your real AI/human reviewer identity. This is technical code/spec review,
not market-reserve fidelity or profitability certification. Never read outcomes,
run market replay, fit a model, change a threshold, access 2024/2025 or push.

The included tests are synthetic. In the existing authorized repository environment
the new subset can be verified with:
python -B -m pytest tests/research/integration_v10 -q -p no:cacheprovider
Do NOT run closeout.py or certify.py from this handoff: governance is already closed.
No credentials, raw data, economic results, sealed maps or full Charter are included.
The reconciliation gap remains explicit; do not relabel old G2-P/G2-R charts as new.
'''
certificate=dict(head=head,charter_revision=782,
    charter_sha256='A4994CE25F04A088670526D7FB23DA11ECCD12B8078DFFEB8F59FEB97A9B8A88',
    tests_passed=397,new_tests_passed=58,technical_repairs='PASS',
    fresh_market_reserve='NOT_READY', ready_for_gate3_replay=False,
    governance_complete_verify='PASS', governance_outcome='BLOCKED_FOR_FULL_RESERVE_SCOPE',
    push=False, governance_resync_required_before_next_task=True,
    raw_market_access=False,pnl_read=False,economic_replay=False,
    protected_2024_access=False,protected_2025_access=False,production_change=False)
with zipfile.ZipFile(TARGET,'x',compression=zipfile.ZIP_DEFLATED) as z:
    for p in paths:z.write(p,p.relative_to(ROOT).as_posix())
    z.writestr('README_REVIEW.md',readme)
    z.writestr('FINAL_HANDOFF_CERTIFICATE.json',json.dumps(certificate,sort_keys=True,indent=2)+'\n')
    z.writestr('ARTIFACT_SHA256_MANIFEST.json',json.dumps(manifest,sort_keys=True,indent=2)+'\n')
with zipfile.ZipFile(TARGET) as z:
    assert z.testzip() is None
    for ref in manifest:
        assert hashlib.sha256(z.read(ref['path'])).hexdigest().upper()==ref['sha256']
print(json.dumps(dict(path=str(TARGET),sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest().upper(),
    bytes=TARGET.stat().st_size,entries=len(manifest)+3,certificate=certificate)))
