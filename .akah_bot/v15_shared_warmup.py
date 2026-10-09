"""Candidate reuse of an UNTRADED source prefix; never on-policy reuse.

Each arm must independently deserialize the snapshot before calling fork().
No live source instance, mutable proof store or economic state is shared.
"""
from spotbot.research.multi_school_fidelity.integration_v13.scheduler import START
from spotbot.research.multi_school_fidelity.integration_v15.source_provider import ScopedSourceProvider
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError, instant


def assert_untraded(saved):
    driver, state = saved['driver'], saved['scheduler']
    source, execution = driver.source, driver.pipeline.execution
    k = execution.portfolio.k
    if (not isinstance(source, ScopedSourceProvider) or driver.failed
            or driver.last_open is not None or driver.last_close is not None
            or instant(state['cursor']) > START or state['expected'] != START
            or source.last_close != state['cursor'] or source.execution is not execution
            or k.fills or k.positions or k.campaigns or driver.feedback or driver.equity
            or driver.owner_receipts or driver.context_receipts or driver.fill_phases
            or execution.managers or execution.admission_receipts
            or k.cash != driver.precommit['contract']['risk']['initial_equity']
            or driver.pipeline.last_open is not None):
        raise ContractError('SHARED_PREFIX_MUST_BE_EXACT_UNTRADED_WARMUP')
    for producer in source.producers.values():
        if producer.stage_campaign_receipts:
            raise ContractError('EXECUTION_DEPENDENT_SOURCE_PREFIX_CANNOT_BE_SHARED')
    return driver, state


def fork(saved, arm):
    """Consume a separately restored warmup; replace ONLY fresh execution scope.

    All native evidence, pivots, pending issues, identities and scheduler prior
    capacity history remain as restored. Source feedback gets a fresh empty
    execution, with the exact target arm's frozen cost contract.
    """
    old, state = assert_untraded(saved)
    if arm not in old.precommit['contract']['arms']:
        raise ContractError('SHARED_WARMUP_TARGET_ARM_NOT_FROZEN')
    from scripts.research.integration_v15 import runner as base
    from v15_checkpoints import Certificates
    scope = old.pipeline.router.scope
    certs = tuple(old.pipeline.router.certificates.values())
    rate = old.precommit['contract']['costs_round_trip'][arm.split('|')[1]]
    execution = base.ScopedExecution(base.Portfolio(rate, {
        p: base.ApproximateRule(p, scope) for p in old.source.feeds}))
    pipeline = base.ScopedPipeline(execution, base.ScopedRouter(scope, certs))
    # Intentional, narrowly proved rebind of an EMPTY execution. Never call this
    # on a source instance shared with another driver or after an actual fill.
    old.source.execution = execution
    driver = base.ScopedDriver(old.repo, old.precommit, pipeline, old.source, arm=arm,
                              readiness_receipt=old.readiness_receipt,
                              certificate_provider=Certificates(certs))
    return {'driver': driver, 'scheduler': state}
