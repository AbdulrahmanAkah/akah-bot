"""Synthetic mechanics only, never a historical certificate or independent review."""

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

from spotbot.research.multi_school_fidelity.integration_v13.historical_inputs import (
    HistoricalFeed,
    MembershipSnapshot,
    MembershipSource,
    all_source_gaps,
)
from spotbot.research.multi_school_fidelity.integration_v13.research_bridge import (
    ApproximateRule,
    ProducerCertificate,
    ResearchPipeline,
    ResearchRouter,
    ResearchScope,
)
from spotbot.research.multi_school_fidelity.integration_v9.producers import HARMONIC
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import ContractError


@pytest.fixture
def f():
    path = Path(__file__).parents[1] / "integration_v12/test_lineage.py"
    spec = importlib.util.spec_from_file_location("v13_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.f.__wrapped__()


def scope(f):
    return ResearchScope(f.SHA, "B" * 64)


def cert(f, grammar=HARMONIC):
    # Test-only artifact. No production/history job is certified by this fixture.
    return ProducerCertificate(
        grammar, "B" * 64, f.SHA, "C" * 64,
        "SOURCE_BOUND_RESEARCH_IMPLEMENTATION_PASS", "SYNTHETIC_IMPLEMENTATION_READINESS_NOT_HISTORICAL_CERTIFICATION"
    )


def make_pipe(f, certificates):
    s = scope(f)
    kernel = f.kernel()
    kernel.portfolio.rules[f.PAIR] = ApproximateRule(f.PAIR, s)
    return ResearchPipeline(kernel, ResearchRouter(s, certificates))


def test_absent_historical_certificate_still_denies(f):
    p, _, _, issued = f.harmonic_source()
    pipe = make_pipe(f, ())
    c = pipe.bind(issued, p, f.state(), f.context(p, f.at(19)))
    accepted, rejected = pipe.on_open(
        f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (c,), research_authorized=True
    )
    assert not accepted and any("CERTIFICATION_REQUIRED" in r for r in rejected.values())
    assert not pipe.execution.portfolio.k.fills


def test_research_mode_keeps_real_guards_and_normalizer(f):
    p, _, _, issued = f.harmonic_source()
    pipe = make_pipe(f, (cert(f),))
    assert pipe.router.synthetic_fixture_execution is False
    c = pipe.bind(issued, p, f.state(), f.context(p, f.at(19)))
    assert pipe.on_open(f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (c,), research_authorized=True)[0]
    assert pipe.execution.source_guards[c.row["identity"]].issue == issued
    assert len(pipe.execution.portfolio.k.fills) == 1


def test_revocation_still_prevents_real_research_admission(f):
    p, _, _, issued = f.harmonic_source()
    pipe = make_pipe(f, (cert(f),))
    c = pipe.bind(issued, p, f.state(), f.context(p, f.at(19)))
    p.graph.terminate(issued.emission_id)
    assert not pipe.on_open(f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (c,), research_authorized=True)[0]
    assert not pipe.execution.portfolio.k.fills


@pytest.mark.parametrize("field,value", [
    ("status", "SYNTHETIC_PASS"), ("evidence_scope", "SYNTHETIC"),
    ("source_version_sha256", "D" * 64), ("protocol_sha256", "D" * 64),
    ("evidence_sha256", "invalid"), ("grammar", "FS_DOW_CRYPTO_ADAPTED_LONG")
])
def test_wrong_certificate_cannot_arm(f, field, value):
    with pytest.raises(ContractError):
        make_pipe(f, (replace(cert(f), **{field: value}),))


def test_duplicate_certificate_denied(f):
    with pytest.raises(ContractError):
        make_pipe(f, (cert(f), cert(f)))


@pytest.mark.parametrize("field,value", [
    ("review_policy", "INDEPENDENT_PASS"), ("quantity_policy", "HISTORICAL_PASS"),
    ("mode", "PRODUCTION"), ("protocol_sha256", "invalid")
])
def test_exclusions_are_not_falsified(f, field, value):
    with pytest.raises(ContractError):
        replace(scope(f), **{field: value}).validate()


def test_original_normalizer_cannot_sneak_in(f):
    p, _, _, issued = f.harmonic_source()
    pipe = ResearchPipeline(f.kernel(), ResearchRouter(scope(f), (cert(f),)))
    c = pipe.bind(issued, p, f.state(), f.context(p, f.at(19)))
    assert not pipe.on_open(f.at(19), {f.PAIR: 213}, {f.PAIR: 100000}, (c,), research_authorized=True)[0]


def test_complete_hour_aggregation_and_pit(f):
    feed = HistoricalFeed(f.PAIR, f.SHA)
    for h in range(24):
        fresh = feed.close_hour(f.bar(h, 100, 101, 99, 100), h + 1)
    assert len(feed.prefix.bars["4H"]) == 6 and len(feed.prefix.bars["1D"]) == 1
    assert set(fresh) == {"1H", "4H", "1D"}
    assert feed.prefix.volumes["1D"] == [sum(range(1, 25))]
    source = MembershipSource((MembershipSnapshot(f.at(0), f.at(48), frozenset({f.PAIR}), f.SHA),))
    claim = source.bind(feed.prefix, f.at(24))
    assert claim.value.eligible and claim.value.checkpoint == f.at(24)
    assert source.bind(feed.prefix, f.at(24)) == claim


def test_incomplete_bucket_not_aggregated(f):
    feed = HistoricalFeed(f.PAIR, f.SHA)
    for h in range(2, 4):
        feed.close_hour(f.bar(h, 100, 101, 99, 100), 1)
    assert not feed.prefix.bars["4H"] and not feed.prefix.bars["1D"]


def test_gap_does_not_forward_fill_or_relabel(f):
    feed = HistoricalFeed(f.PAIR, f.SHA)
    feed.close_hour(f.bar(0, 100, 101, 99, 100), 1)
    with pytest.raises(ContractError, match="GAP"):
        feed.close_hour(f.bar(2, 100, 101, 99, 100), 1)


def test_membership_never_uses_next_snapshot(f):
    feed = HistoricalFeed(f.PAIR, f.SHA)
    feed.close_hour(f.bar(0, 100, 101, 99, 100), 1)
    src = MembershipSource((
        MembershipSnapshot(f.at(0), f.at(2), frozenset({"OTHER-USDT"}), f.SHA),
        MembershipSnapshot(f.at(2), f.at(5), frozenset({f.PAIR}), f.SHA),
    ))
    assert src.bind(feed.prefix, f.at(1)).value.eligible is False


def test_failing_sources_cannot_be_silently_dropped():
    gaps = all_source_gaps({})
    assert set(gaps) == {"CLASSICAL", "HARMONIC", "ELLIOTT", "WYCKOFF", "ICT", "DOW", "H1", "H2", "H3", "DRIVER"}
    assert all_source_gaps({"WYCKOFF": {"typed_readiness_generator": True}})["WYCKOFF"]
