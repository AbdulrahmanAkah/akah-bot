"""Existing certified worker, changing checkpoint byte storage only."""
import argparse
import gc
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]

if __name__ == '__main__':
    from v15_incremental_recoverable_worker import install, prepare_arm
    import v15_packed_checkpoints as packed
    import v15_incremental_checkpoints as previous
    worker, cert = install()
    if (cert.get('packed_checkpoint_all_eighteen_exact_resume') is not True or
            cert.get('packed_checkpoint_sync_barriers_constant_proven') is not True):
        raise RuntimeError('PACKED_STORAGE_NOT_CERTIFIED')
    # Preserve previous reducers/global restore map and the V1/V2 reader captured
    # by packed.READ_OLD. Only storage dispatch changes; no source code does.
    worker.write_checkpoint = previous.write_checkpoint = packed.write_checkpoint
    worker.read_checkpoint = previous.read_checkpoint = packed.read_checkpoint
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--arm'); group.add_argument('--collect', action='store_true'); args = parser.parse_args()
    if args.collect: worker.collect_all()
    else:
        prepare_arm(worker, cert, args.arm); gc.collect(); worker.main(args.arm)
