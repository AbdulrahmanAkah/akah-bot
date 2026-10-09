"""Synthetic warmup prefix; no historical market inputs or outcomes."""
from datetime import datetime, timedelta, timezone
from collections import deque
import json
import pytest
import v15_checkpoints as baseline
import v15_incremental_checkpoints as incremental
import v15_shared_warmup as warmup
from test_v15_checkpoints import advance, signature
from scripts.research.integration_v15 import runner as base
from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import MembershipSource, MembershipSnapshot


def make(arm):
    frozen = json.loads((base.Path.cwd() / base.OUT / 'gate3_precommit.json').read_text())
    ready = json.loads((base.Path.cwd() / base.OUT / 'readiness_certificate.json').read_text())
    start = datetime(2021, 9, 1, tzinfo=timezone.utc)
    members = MembershipSource((MembershipSnapshot(start, datetime(2024, 1, 1, tzinfo=timezone.utc),
                               frozenset({'BTC-USDT', 'ETH-USDT'}), 'A' * 64),))
    scope = base.ResearchScope(frozen['source_hashes'][base.PROTOCOL], frozen['source_version_sha256'])
    certs = tuple(base.ProducerCertificate(g, scope.source_version_sha256, scope.protocol_sha256, 'a' * 64,
                  'SOURCE_BOUND_RESEARCH_IMPLEMENTATION_PASS',
                  'SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION') for g in base.FUNDED)
    source = base.ScopedSourceProvider({'BTC-USDT': 'B' * 64, 'ETH-USDT': 'C' * 64}, members, scope.source_version_sha256)
    execution = base.ScopedExecution(base.Portfolio(frozen['contract']['costs_round_trip'][arm.split('|')[1]],
                                   {p: base.ApproximateRule(p, scope) for p in source.feeds}))
    source.attach_execution(execution)
    driver = base.ScopedDriver(base.Path.cwd(), frozen, base.ScopedPipeline(execution, base.ScopedRouter(scope, certs)),
             source, arm=arm, readiness_receipt=ready, certificate_provider=baseline.Certificates(certs))
    advance(source, 0, 24)
    state = {'cursor': source.last_close, 'expected': warmup.START,
             'prior': {p: deque(maxlen=24) for p in source.feeds},
             'last': {p: source.last_close for p in source.feeds}}
    return {'driver': driver, 'scheduler': state}


@pytest.mark.parametrize('index', range(9))
@pytest.mark.parametrize('scenario', ['1X', '2X'])
def test_all_eighteen_untraded_forks_match_independently_built_prefix(tmp_path, index, scenario):
    arm = base.FUNDED[index] + '|' + scenario
    reference = make(arm)
    origin = make(base.FUNDED[0] + '|1X')
    authority = {'purpose': 'SYNTHETIC_SHARED_PREFIX'}
    path = incremental.write_checkpoint(tmp_path, origin, authority)
    restored = incremental.read_checkpoint(path, authority)
    fork = warmup.fork(restored, arm)
    assert signature(fork['driver'].source) == signature(reference['driver'].source)
    assert fork['driver'].arm == arm
    assert fork['driver'].pipeline.execution.portfolio.k.exit_cost_rate == reference['driver'].pipeline.execution.portfolio.k.exit_cost_rate
    assert fork['driver'].source.execution is fork['driver'].pipeline.execution
    assert fork['driver'].pipeline.execution.context_validator.__self__ is fork['driver']
    assert fork['driver'].pipeline.execution.receipt_graph is fork['driver'].trace
    # Later advance/mutation of either restoration must never leak to the other.
    advance(fork['driver'].source, 24, 28); advance(reference['driver'].source, 24, 28)
    assert signature(fork['driver'].source) == signature(reference['driver'].source)
    assert signature(origin['driver'].source) != signature(fork['driver'].source)


@pytest.mark.parametrize('bad', ['fills', 'positions', 'campaigns', 'economic_clock', 'feedback'])
def test_any_traded_prefix_is_rejected(bad):
    saved = make(base.FUNDED[0] + '|1X')
    d = saved['driver']
    if bad == 'economic_clock': saved['scheduler']['cursor'] = warmup.START + timedelta(hours=1)
    elif bad == 'feedback': d.feedback.append('synthetic_actual_receipt')
    elif bad == 'fills': d.pipeline.execution.portfolio.k.fills.append({'synthetic': True})
    else: getattr(d.pipeline.execution.portfolio.k, bad)['synthetic'] = True
    with pytest.raises(Exception, match='EXACT_UNTRADED_WARMUP'):
        warmup.fork(saved, base.FUNDED[0] + '|2X')
