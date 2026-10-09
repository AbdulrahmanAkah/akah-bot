"""No candidate source installation before bound differential certification."""
import runpy
from pathlib import Path
from v15_recoverable_worker import certified

if __name__ == '__main__':
    cert = certified()
    if cert.get('exact_point_query_and_continuation_index_proven') is not True:
        raise RuntimeError('POINT_INDEX_NOT_CERTIFIED')
    import cache_budget_v15
    import v15_native_epoch_candidate
    cache_budget_v15.install(); v15_native_epoch_candidate.install()
    import v15_point_query_index
    v15_point_query_index.install()
    runpy.run_path(str(Path(__file__).with_name('v15_paged_recoverable_worker.py')), run_name='__main__')
