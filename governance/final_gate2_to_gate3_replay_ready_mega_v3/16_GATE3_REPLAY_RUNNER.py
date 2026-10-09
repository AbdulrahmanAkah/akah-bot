"""Frozen entrypoint. Preflight is safe; economic replay needs new governed task + token."""
from pathlib import Path
import argparse,json,hashlib

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--preflight-only',action='store_true')
    parser.add_argument('--verify-bounded-inputs',action='store_true')
    parser.add_argument('--authorize-gate3-economic-replay',default='')
    parser.add_argument('--frozen-manifest-sha256',required=True)
    args=parser.parse_args(); repo=args.repo.resolve()
    path=repo/'governance/final_gate2_to_gate3_replay_ready_mega_v3/15_GATE3_FROZEN_HASH_MANIFEST.json'
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest().upper()
    if digest(path)!=args.frozen_manifest_sha256.upper(): raise ValueError('ROOT_MANIFEST_HASH_DRIFT')
    manifest=json.loads(path.read_text())
    for relative,expected in manifest['files'].items():
        target=(repo/relative).resolve()
        if not target.is_relative_to(repo) or not target.is_file() or digest(target)!=expected:
            raise ValueError('BOOTSTRAP_SOURCE_OR_CONFIG_HASH_DRIFT:'+relative)
    # No research module is imported until stdlib-only source verification passes.
    from spotbot.research.multi_school_fidelity.gate3_market_v3 import preflight,run_market,save
    if args.preflight_only:
        if args.authorize_gate3_economic_replay: parser.error('NO_AUTHORIZATION_IN_PREFLIGHT')
        result=preflight(repo,verify_data=args.verify_bounded_inputs)
        print(json.dumps(result,indent=2)); return
    if not args.authorize_gate3_economic_replay:
        parser.error('EXPLICIT_NEXT_MISSION_AUTHORIZATION_TOKEN_REQUIRED')
    try: print(json.dumps(run_market(repo,args.authorize_gate3_economic_replay),indent=2))
    except Exception as e:
        failure=repo/'governance/gate3_single_frozen_economic_replay_v3'
        if failure.exists(): save(failure/'TECHNICAL_FAIL.json',{'status':'TECHNICAL_FAIL','error':str(e),'scientific_conclusion':'NONE','automatic_rerun':False})
        raise

if __name__=='__main__': main()
