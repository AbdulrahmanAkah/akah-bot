"""Explicit governed research entrypoint, no production access."""
import argparse
from pathlib import Path
from spotbot.research.multi_school_fidelity.full_replay_v5 import freeze, run

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--freeze',action='store_true');p.add_argument('--run',action='store_true')
    p.add_argument('--workers',type=int,default=4);a=p.parse_args();repo=Path(__file__).resolve().parents[2]
    if a.freeze:print(freeze(repo),flush=True)
    if a.run:print(run(repo,a.workers)['status'],flush=True)
