"""Certified packed worker with exact single-pass recovery / bounded caches."""
import argparse
import gc
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]

if __name__ == '__main__':
    from v15_incremental_recoverable_worker import install, prepare_arm
    import v15_incremental_checkpoints as previous
    import v15_packed_checkpoints as packed
    import v15_io_repair as repair
    worker, cert = install()
    if cert.get('exact_single_pass_recovery_and_source_cache_proven') is not True:
        raise RuntimeError('IO_REPAIR_NOT_CERTIFIED')
    repair.install()
    worker.write_checkpoint = previous.write_checkpoint = packed.write_checkpoint
    worker.read_checkpoint = previous.read_checkpoint = repair.read_checkpoint
    run = worker.ResumableScheduler.run
    def cached_run(self, driver, **kwargs):
        repair.source_cache(driver)
        return run(self, driver, **kwargs)
    worker.ResumableScheduler.run = cached_run
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--arm'); group.add_argument('--collect', action='store_true'); args = parser.parse_args()
    if args.collect: worker.collect_all()
    else: prepare_arm(worker, cert, args.arm); gc.collect(); worker.main(args.arm)

