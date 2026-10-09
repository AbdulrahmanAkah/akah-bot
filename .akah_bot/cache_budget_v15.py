"""Bound only pure derived-value caches, never proof/history/decision state."""
from functools import lru_cache

INSTALLED=False
BAR_CLASS=None
ORIGINAL_BAR=None
NATIVE_IDS=None
TEST_GUARD=None


def release_validation_caches(provider):
    """Call only between completed-hour callbacks, never during DAG recursion.

    These dictionaries store successful validation intervals, not evidence or
    proof-search results. Cache misses re-run the exact original validations.
    Do not clear _proofs/_waves: those also affect diagnostic accounting.
    """
    graphs={id(feed.prefix.graph):feed.prefix.graph for feed in provider.feeds.values()}
    for graph in graphs.values():
        graph._exact_live.clear()
        graph._exact_native.clear()


def bar_id(prefix,bar):
    # Module-level method and original attribute name preserve pickle rebinding.
    if type(bar) is BAR_CLASS:return NATIVE_IDS(prefix.pair,bar)
    return ORIGINAL_BAR(prefix,bar)


def install():
    global INSTALLED,BAR_CLASS,ORIGINAL_BAR,NATIVE_IDS
    if INSTALLED:return
    import v15_diagnostic_journal
    v15_diagnostic_journal.install()
    import v15_disk_seen
    v15_disk_seen.install()
    import v15_scaling_acceleration as scaling
    from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar
    base=scaling.base
    ORIGINAL_BAR=base.bar_id;BAR_CLASS=CompletedBar
    pure_bar=base.immutable_bar_id.__wrapped__
    NATIVE_IDS=lru_cache(maxsize=4096)(pure_bar)
    base.sources.CompletedPrefix.bar_id=bar_id
    scaling.validate_static_point=lru_cache(maxsize=4096)(scaling.validate_static_point.__wrapped__)
    scaling.immutable=lru_cache(maxsize=512)(scaling.immutable.__wrapped__)
    # No source point, wave/count proof, market history or owner state is cleared.
    base.immutable_bar_id.cache_clear()
    INSTALLED=True


def pytest_configure(config):
    global TEST_GUARD
    from v15_resource_guard import ResourceGuard
    TEST_GUARD=ResourceGuard('v15_cache_validation').start()
    import v15_disk_history
    v15_disk_history.install()
    install()


def pytest_unconfigure(config):
    if TEST_GUARD is not None:TEST_GUARD.close()
