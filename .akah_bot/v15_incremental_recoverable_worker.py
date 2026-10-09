"""Certified candidate harness: unchanged frozen worker + exact storage/warmup hooks."""
import argparse
import gc
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / '.akah_bot')]


def authority(arm):
    from v15_checkpoints import sha
    from scripts.research.integration_v15 import runner as base
    manifest = json.loads((ROOT / base.INPUT_MANIFEST).read_text())
    frozen = json.loads((ROOT / base.OUT / 'gate3_precommit.json').read_text())
    active = json.loads((ROOT / '.akah_bot/active_task.json').read_text())
    return {'task_id': active['task_id'], 'precommit_sha256': frozen['precommit_sha256'],
            'source_version_sha256': frozen['source_version_sha256'], 'arm': arm,
            'input_shas': {r['pair']: r['bounded_sha256'] for r in manifest['pairs']},
            'membership_sha256': manifest['membership_bounded_sha256'],
            'supplemental_certificate_sha256': sha(ROOT / '.akah_bot/v15_bounded_runtime_certificate.json')}


def install():
    import v15_recoverable_worker as original
    import v15_incremental_checkpoints as snapshots
    import v15_shared_warmup as warmup
    from v15_resumable_scheduler import ResumableScheduler
    from v15_checkpoint_repair_lineage import checkpoint_authority
    import v15_checkpoint_lineage as lineage
    cert = original.certified()
    if (cert.get('incremental_checkpoint_parity_proven') is not True
            or cert.get('shared_untraded_warmup_all_eighteen_proven') is not True):
        raise RuntimeError('INCREMENTAL_WARMUP_RUNTIME_NOT_CERTIFIED')
    original.write_checkpoint = snapshots.write_checkpoint
    original.read_checkpoint = snapshots.read_checkpoint
    lineage.checkpoint_authority = checkpoint_authority
    session = ROOT / '.akah_bot/v15_recoverable_session'
    shared = session / 'shared_untraded_warmup.json'

    class Scheduler(ResumableScheduler):
        def run(self, driver, *, checkpoint=None, **kwargs):
            def retained(d, state):
                if state['cursor'] == warmup.START and not shared.exists():
                    saved = {'driver': d, 'scheduler': state}
                    warmup.assert_untraded(saved)
                    receipt = snapshots.write_checkpoint(session / 'shared_untraded_prefix', saved, authority(d.arm))
                    original.atomic(shared, {'receipt': str(receipt), 'sha256': original.sha(receipt),
                                            'cursor': str(state['cursor']), 'status': 'EXACT_UNTRADED_PREFIX'})
                    print('SHARED_UNTRADED_WARMUP_RETAINED=' + str(state['cursor']), flush=True)
                if checkpoint is not None:
                    checkpoint(d, state)
            return super().run(driver, checkpoint=retained, **kwargs)

    original.ResumableScheduler = Scheduler
    return original, cert


def prepare_arm(original, cert, arm):
    session = ROOT / '.akah_bot/v15_recoverable_session'
    latest = session / (arm.replace('|', '_') + '_checkpoint.json')
    shared = session / 'shared_untraded_warmup.json'
    if latest.exists() or not shared.exists():
        return
    from v15_checkpoints import sha
    from v15_incremental_checkpoints import read_checkpoint, write_checkpoint
    from v15_shared_warmup import fork
    from v15_checkpoint_repair_lineage import checkpoint_authority
    link = json.loads(shared.read_text())
    path = Path(link['receipt']).resolve()
    if not path.is_relative_to(session) or sha(path) != link['sha256']:
        raise RuntimeError('SHARED_WARMUP_POINTER_DRIFT')
    actual = json.loads(path.read_text())['authority']
    expected = authority(arm)
    if actual.get('arm') not in json.loads((ROOT / original.base.OUT / 'gate3_precommit.json').read_text())['contract']['arms']:
        raise RuntimeError('SHARED_WARMUP_ORIGIN_ARM_NOT_FROZEN')
    origin_expected = dict(expected, arm=actual['arm'])
    verified = checkpoint_authority(path, origin_expected, cert, ROOT)
    # Install the same certified operational representations BEFORE unpickling.
    import v15_disk_history; v15_disk_history.install()
    import v15_input_memorymap; v15_input_memorymap.install()
    import cache_budget_v15; cache_budget_v15.install()
    import source_scan_acceleration; source_scan_acceleration.install()
    import v15_scalar_hour_stream; v15_scalar_hour_stream.install()
    import v15_native_epoch_candidate; v15_native_epoch_candidate.install()
    saved = fork(read_checkpoint(path, verified), arm)
    receipt = write_checkpoint(session / arm.replace('|', '_'), saved, expected)
    original.atomic(latest, {'receipt': str(receipt), 'sha256': sha(receipt),
                            'cursor': str(saved['scheduler']['cursor'])})
    print('EXACT_SHARED_UNTRADED_PREFIX_REUSED=' + arm + '@' + str(saved['scheduler']['cursor']), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--arm'); group.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    worker, cert = install()
    if args.collect:
        worker.collect_all()
    else:
        prepare_arm(worker, cert, args.arm)
        # prepare_arm may have deserialized a large source prefix to publish
        # this arm's exact snapshot. Release its cyclic graph BEFORE the original
        # main independently restores it; never keep two copies of the prefix.
        gc.collect()
        worker.main(args.arm)
