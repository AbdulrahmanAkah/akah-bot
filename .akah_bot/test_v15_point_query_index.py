"""Synthetic-only differential and scaling tests; no market/economic inputs."""
import gc
import pickle
import random
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import v15_point_query_index as candidate
from v15_scaling_acceleration import PointJournal
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import Point

START = datetime(2021, 9, 1, tzinfo=timezone.utc)


def point(i, degree='1H', delay=2):
    return Point(str(i), 'L' if i % 2 else 'H', 100.0 + i, START + timedelta(hours=i),
                 START + timedelta(hours=i + delay), degree)


def original(prefix, degree, now):
    from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import instant
    return sorted((p for p in prefix.points.values() if p.degree == degree and instant(p.available_at) <= now),
                  key=lambda p: (instant(p.observed_at), p.event_id))


@pytest.mark.parametrize('mutation', ['append', 'replace', 'delete', 'clear', 'update', 'pop', 'popitem',
                                     'whole_store', 'delayed', 'out_of_order', 'tie', 'restore'])
def test_exact_query_mutations_and_causal_cutoffs(mutation, tmp_path):
    store = PointJournal(); prefix = SimpleNamespace(points=store)
    for i in range(120):
        store[str(i)] = point(i, ('1H', '4H', '1D')[i % 3])
    candidate.select(prefix, '1H', START + timedelta(hours=125))
    if mutation == 'append': store['new'] = replace(point(121), event_id='new')
    elif mutation == 'replace': store['3'] = replace(store['3'], price=999.)
    elif mutation == 'delete': del store['3']
    elif mutation == 'clear': store.clear(); store['fresh'] = point(130)
    elif mutation == 'update': store.update({'3': point(70)})
    elif mutation == 'pop': store.pop('3')
    elif mutation == 'popitem': store.popitem()
    elif mutation == 'whole_store': prefix.points = dict(store)
    elif mutation == 'delayed': store['future'] = point(10, delay=500)
    elif mutation == 'out_of_order': store['early'] = replace(point(1), event_id='early')
    elif mutation == 'tie': store['other'] = replace(point(3), event_id='other')
    elif mutation == 'restore':
        import v15_checkpoints as checkpoints
        path = checkpoints.write_checkpoint(tmp_path, {'points': store}, {'source': 'SYNTHETIC_ONLY'})
        prefix.points = checkpoints.read_checkpoint(path, {'source': 'SYNTHETIC_ONLY'})['points']
    for hour in (0, 3, 30, 125, 600, 20):
        for degree in ('1H', '4H', '1D', 'missing'):
            now = START + timedelta(hours=hour)
            assert list(candidate.select(prefix, degree, now)) == original(prefix, degree, now)
            for cut in (START, START + timedelta(hours=30), START + timedelta(hours=150)):
                expected = [p for p in original(prefix, '4H', now) if p.kind == 'L' and p.observed_at > cut]
                assert list(candidate.lows_after(prefix, cut, now)) == expected


def test_external_derived_index_not_pickled_and_weak_lifetime():
    store = PointJournal(); store['a'] = point(1); prefix = SimpleNamespace(points=store)
    before = pickle.dumps(store); key = id(store)
    candidate.select(prefix, '1H', START + timedelta(hours=20))
    assert before == pickle.dumps(store)
    assert key in candidate.INDEXES
    del prefix, store; gc.collect()
    assert key not in candidate.INDEXES


def test_non_native_value_falls_back_without_changing_sort():
    store = PointJournal(); store['a'] = point(2)
    store['b'] = SimpleNamespace(degree='1H', available_at='2021-09-01T05:00:00Z',
                                 observed_at='2021-09-01T03:00:00Z', event_id='b')
    prefix = SimpleNamespace(points=store); now = START + timedelta(hours=8)
    assert candidate.select(prefix, '1H', now) == original(prefix, '1H', now)


def test_full_synthetic_source_state_exact_after_original_candidate_hours():
    import test_v15_checkpoints as fixture
    candidate.install()
    candidate.ENABLED = False
    baseline = fixture.provider(); fixture.advance(baseline, 0, 96)
    expected = fixture.signature(baseline)
    candidate.ENABLED = True
    accelerated = fixture.provider(); fixture.advance(accelerated, 0, 96)
    assert fixture.signature(accelerated) == expected


def test_long_history_query_benchmark_and_exactness(record_property):
    store = PointJournal(); prefix = SimpleNamespace(points=store)
    for i in range(12000): store[str(i)] = point(i, ('1H', '4H', '1D')[i % 3])
    now = START + timedelta(hours=14000)
    expected = original(prefix, '1H', now)
    assert list(candidate.select(prefix, '1H', now)) == expected
    began = time.perf_counter()
    for _ in range(120): original(prefix, '1H', now)
    old = time.perf_counter() - began
    began = time.perf_counter()
    for _ in range(120):
        found = candidate.select(prefix, '1H', now)
        assert len(found) == len(expected) and found[-1] is expected[-1]
    new = time.perf_counter() - began
    record_property('original_seconds', old); record_property('indexed_seconds', new)
    record_property('query_only_speedup', old / new)
    # Timing is a measurement, never a flaky correctness PASS threshold.


@pytest.mark.parametrize('count', [8, 19, 20, 21, 180, 600, 4000])
def test_continuation_tail_preserves_full_id_count_prices_and_prior_context(count):
    import pandas as pd
    from v15_bounded_storage import PackedBars
    from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import CompletedBar
    from spotbot.research.multi_school_fidelity import akah_full_fidelity_runtime_v1 as native
    from spotbot.research.multi_school_fidelity.school_contract_common_v8 import digest
    candidate.install(); candidate.ENABLED = True
    bars = PackedBars('4H'); volumes = []
    for i in range(count):
        at = START + timedelta(hours=4*i)
        value = 100. + i*.02 + (i%7)*.03
        bars.append(CompletedBar(at, at + timedelta(hours=4), '4H', value, value + .5, value - .4, value + .1))
        volumes.append(100.)
    full = pd.DataFrame([dict(timestamp=b.end, open=b.open, high=b.high, low=b.low, close=b.close, volume=v)
                         for b,v in zip(bars, volumes, strict=True)])
    prior = []
    original_result = native.continuation_patterns_from_bars(full, 1., prior)
    assert digest(candidate.continuation(bars, volumes, 1., prior)) == digest(original_result)
