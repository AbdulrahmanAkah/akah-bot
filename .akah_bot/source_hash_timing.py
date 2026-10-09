"""Small source-only environment comparison; no replay or market imports."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    if len(sys.argv)!=2 or sys.argv[1] not in {'sandbox','host'}:raise RuntimeError('EXACT_ENVIRONMENT_LABEL_REQUIRED')
    frozen=json.loads((ROOT/'governance/all_nine_eighteen_arm_readiness_v15/gate3_precommit.json').read_text())
    expected=frozen['source_hashes']
    allowed=('src/spotbot/','scripts/research/integration_v13/','scripts/research/integration_v14/',
             'scripts/research/integration_v15/','tests/research/')
    fixed={'governance/all_nine_eighteen_arm_readiness_v15/research_protocol.json',
           'governance/final_gate2_to_gate3_replay_ready_mega_v3/bounded_market_input_manifest.json'}
    if any(not (p.startswith(allowed) and p.endswith('.py') or p in fixed) for p in expected):
        raise RuntimeError('NON_SOURCE_PATH_NO_READ')
    times=[];total=0
    for repeat in range(3):
        started=time.perf_counter();actual={};size=0
        for relative in sorted(expected):
            path=(ROOT/relative).resolve()
            if not path.is_relative_to(ROOT):raise RuntimeError('SOURCE_PATH_ESCAPE')
            data=path.read_bytes();size+=len(data)
            actual[relative]=hashlib.sha256(data).hexdigest().upper()
        if actual!=expected:raise RuntimeError('FROZEN_SOURCE_SHA_DRIFT')
        times.append(time.perf_counter()-started);total=size
    payload={'environment':sys.argv[1],'files':len(expected),'source_bytes_per_repeat':total,
             'seconds':times,'median_seconds':statistics.median(times),'source_sha_parity':True,
             'source_version_sha256':frozen['source_version_sha256'],'market_rows_read':0,
             'economic_replay_executed':False,'other_apps_controlled':False}
    (ROOT/'.akah_bot'/('source_hash_timing_'+sys.argv[1]+'.json')).write_text(json.dumps(payload,indent=2)+'\n')
    print(json.dumps(payload))


if __name__=='__main__':main()
