"""Explicit research-only entrypoint; all schools/hybrids, no production."""
import argparse
from pathlib import Path
from spotbot.research.multi_school_fidelity.full_replay_v4 import freeze,run

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--freeze',action='store_true');a.add_argument('--run',action='store_true')
    a.add_argument('--workers',type=int,default=6);a.add_argument('--mechanical-repair',action='store_true')
    a.add_argument('--resume',action='store_true');a.add_argument('--stage-only',action='store_true')
    args=a.parse_args();repo=Path(__file__).resolve().parents[2]
    if args.freeze:print(freeze(repo,mechanical_repair=args.mechanical_repair))
    if args.run:run(repo,args.workers,resume=args.resume,stage_only=args.stage_only)
