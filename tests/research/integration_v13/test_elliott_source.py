"""Synthetic completed prefixes only; no files, market readers or economics."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import combinations

import pytest

from spotbot.research.multi_school_fidelity.elliott_contract_v8 import LEGS, Wave
from spotbot.research.multi_school_fidelity.integration_v9.sources import CompletedPrefix
from spotbot.research.multi_school_fidelity.integration_v10.elliott_scope import check_wave
from spotbot.research.multi_school_fidelity.integration_v12.producers import ContractProducer
from spotbot.research.multi_school_fidelity.integration_v13.elliott_source import (
    OBJECTIVE_RULES,
    CompleteProofSearch,
    ElliottSource,
)
from spotbot.research.multi_school_fidelity.school_contract_common_v8 import DEGREES, digest
from spotbot.research.multi_school_fidelity.structural_lifecycle_v6 import (
    CompletedBar,
    ContractError,
)

BASE = datetime(2022, 1, 10, tzinfo=UTC)
SHA = "a" * 64
ANCHORS = (
    (0, 100),
    (4, 130),
    (8, 120),
    (12, 175),
    (16, 160),
    (24, 200),
    (32, 170),
    (40, 185),
    (48, 160),
)


def at(hour):
    return BASE + timedelta(hours=hour)


def native_prefix(streams, *, pair="SYNTH-USDT", prefix=None):
    """Run real CompletedPrefix.on_close; never insert fake Point records.

    Each supplied timeframe is an independent synthetic completed stream, as
    allowed by CompletedPrefix. Shared extrema are exact across degrees.
    """
    prefix = CompletedPrefix(pair, SHA) if prefix is None else prefix
    for degree, anchors in streams.items():
        step = int(DEGREES[degree].total_seconds() / 3600)
        anchors = sorted(anchors)
        first, last = anchors[0][0], anchors[-1][0]

        def value(end, anchors=anchors, first=first, last=last):
            if end < first:
                # Opposite-direction lead-in makes the first actual anchor a pivot.
                direction = 1 if anchors[1][1] > anchors[0][1] else -1
                return anchors[0][1] + direction * (first - end)
            if end > last:
                direction = 1 if anchors[-1][1] > anchors[-2][1] else -1
                return anchors[-1][1] - direction * (end - last)
            for (a, va), (b, vb) in zip(anchors[:-1], anchors[1:], strict=True):
                if a <= end <= b:
                    return va + (vb - va) * (end - a) / (b - a)
            raise AssertionError(end)

        for end in range(first - 2 * step, last + 3 * step + 1, step):
            val = value(end)
            high, low = val + 0.001, val - 0.001
            for j, (hour, anchor) in enumerate(anchors):
                if hour == end:
                    if (j == 0 and anchors[1][1] < anchor) or (
                        j > 0 and anchor > anchors[j - 1][1]
                    ):
                        high = anchor
                    else:
                        low = anchor
            bar = CompletedBar(at(end - step), at(end), degree, val, high, low, val)
            prefix.on_close(bar, 1.0, bar.end)
    return prefix


def point(prefix, degree, hour):
    return next(
        p for p in prefix.points.values() if p.degree == degree and p.observed_at == at(hour)
    )


def w2_prefix(mirror=False):
    anchors = tuple((h, 400 - v if mirror else v) for h, v in ANCHORS)
    return native_prefix(
        {"1H": anchors, "4H": ((0, anchors[0][1]), (24, anchors[5][1]), (48, anchors[-1][1]))}
    )


def test_w2_native_proof_objective_and_v12_registration():
    prefix = w2_prefix()
    result = ElliottSource(prefix).search(at(60), legs=("W2",))
    assert result.counts
    for count in result.counts:
        count.validate(at(60))
        assert count.objective.value == pytest.approx(321.8)
        assert count.invalidation == 100
        assert count.parent_prefix.children[0].kind == "IMPULSE"
        assert count.correction.kind in {"ZIGZAG", "FLAT", "TRIANGLE"}
        assert prefix.graph.live(count.objective.event_id, at(60))
        producer = ContractProducer(prefix)
        producer.add_elliott_count(count, at(60))
        assert prefix.graph.live(count.count_id, at(60))
    objective = result.counts[0].objective
    rule_node = prefix.graph.nodes[prefix.graph.nodes[objective.event_id].parents[0]]
    assert rule_node.evidence.value == OBJECTIVE_RULES["W2"]
    assert rule_node.origin == "DETECTOR_GEOMETRY"


def test_mirrored_opposing_interpretations_are_generated_not_filtered():
    prefix = w2_prefix(mirror=True)
    result = ElliottSource(prefix).search(at(60), legs=("W2",))
    assert result.counts
    assert all(c.correction.sign == 1 for c in result.counts)
    assert all(c.objective.value == pytest.approx(78.2) for c in result.counts)
    assert all(c.invalidation == 300 for c in result.counts)


@pytest.mark.parametrize("kind", ("IMPULSE", "ZIGZAG", "FLAT", "TRIANGLE"))
def test_all_1h_interpretations_match_independent_native_validation(kind):
    prefix = w2_prefix()
    search = CompleteProofSearch(prefix, at(60))
    expected = set()
    for seq in combinations(search.points["1H"], LEGS[kind] + 1):
        wave = Wave("oracle", kind, "1H", seq, (), SHA)
        try:
            wave.validate(at(60))
            check_wave(wave)
        except ContractError:
            continue
        expected.add(tuple(p.event_id for p in seq))
    actual = search.waves("1H", kind)
    assert {tuple(p.event_id for p in w.points) for w in actual} == expected
    assert all(not w.children for w in actual)


def test_snapshot_no_future_endpoints_or_children_and_repeat_stable_ids():
    prefix = w2_prefix()
    early = ElliottSource(prefix).search(at(55), legs=("W2",))
    assert not early.counts  # Higher-degree endpoint at 48 needs two right 4H bars.
    late = ElliottSource(prefix).search(at(56), legs=("W2",))
    assert late.counts
    size = len(prefix.graph.nodes)
    assert ElliottSource(prefix).search(at(56), legs=("W2",)) == late
    later = ElliottSource(prefix).search(at(60), legs=("W2",))
    assert later.counts == late.counts
    assert len(prefix.graph.nodes) == size
    assert all(c.objective.available_at == at(56) for c in late.counts)
    with pytest.raises(ContractError, match="ENDPOINT_NOT_IN_CAUSAL_PREFIX"):
        CompleteProofSearch(prefix, at(55)).waves("1H", "ZIGZAG", point(prefix, "4H", 48))


def test_missing_exact_child_endpoint_abstains_instead_of_padding():
    prefix = w2_prefix()
    prefix.graph.terminate(point(prefix, "1H", 0).event_id)
    result = ElliottSource(prefix).search(at(60), legs=("W2",))
    assert not result.counts
    assert dict(result.diagnostics)["EXACT_CHILD_ENDPOINT_OR_SUBDIVISION_UNAVAILABLE"] > 0


def test_mutated_point_or_claimed_geometry_origin_rejected():
    prefix = w2_prefix()
    p = point(prefix, "1H", 4)
    prefix.points[p.event_id] = replace(p, price=p.price + 1)
    with pytest.raises(ContractError, match="ACTUAL_NATIVE_POINT_SOURCE_REQUIRED"):
        CompleteProofSearch(prefix, at(60))
    prefix.points[p.event_id] = p
    prefix.graph.nodes[p.event_id] = replace(
        prefix.graph.nodes[p.event_id], origin="SUPPLIED_SEMANTIC_PRODUCER"
    )
    with pytest.raises(ContractError, match="ACTUAL_NATIVE_POINT_SOURCE_REQUIRED"):
        CompleteProofSearch(prefix, at(60))


def test_all_exact_child_variants_retained_and_no_latest_window():
    # Two internal motive completions share exact endpoints; both must survive.
    anchors = (
        (0, 100),
        (4, 130),
        (8, 120),
        (12, 160),
        (16, 140),
        (20, 175),
        (24, 155),
        (28, 200),
        (36, 170),
        (44, 185),
        (52, 160),
    )
    prefix = native_prefix({"1H": anchors, "4H": ((0, 100), (28, 200), (52, 160))})
    result = ElliottSource(prefix).search(at(64), legs=("W2",))
    motives = {c.parent_prefix.children[0].wave_id for c in result.counts}
    assert len(motives) > 1
    assert len({c.count_id for c in result.counts}) == len(result.counts)
    assert all(c.parent_prefix.parent_id == result.counts[0].parent_id for c in result.counts)
    # Neither identity nor the latest completion is used to select an owner.
    assert any(point(prefix, "1H", 12) in c.parent_prefix.children[0].points for c in result.counts)
    assert ElliottSource(prefix).search(at(64), legs=("W2",)) == result


def expand(kind, degree, start, end, a, b, streams):
    """A declared synthetic recursive tree; detected pivots supply its evidence."""
    fractions = {
        "IMPULSE": (0, 0.3, 0.15, 0.65, 0.5, 1),
        "ZIGZAG": (0, 0.7, 0.3, 1),
        "DOUBLE_THREE": (0, 0.7, 0.3, 1),
        "TRIPLE_THREE": (0, 0.5, 0.2, 0.8, 0.4, 1),
    }[kind]
    n = len(fractions) - 1
    step = int(DEGREES[degree].total_seconds() / 3600)
    positions = [start + ((end - start) * i // n // step) * step for i in range(n)] + [end]
    anchors = [(h, a + (b - a) * f) for h, f in zip(positions, fractions, strict=True)]
    streams.setdefault(degree, {}).update(anchors)
    if degree != "1H":
        child_degree = {"1D": "4H", "4H": "1H"}[degree]
        for i, ((t0, v0), (t1, v1)) in enumerate(zip(anchors[:-1], anchors[1:], strict=True)):
            child = (
                ("IMPULSE" if i % 2 == 0 else "ZIGZAG")
                if kind in {"IMPULSE", "ZIGZAG"}
                else "ZIGZAG"
            )
            expand(child, child_degree, t0, t1, v0, v1, streams)
    return anchors


def full_parent_prefix():
    anchors = ((0, 100), (24, 130), (48, 115), (72, 160), (96, 140), (120, 180), (144, 150))
    streams = {"4H": dict(anchors)}
    for i, ((t0, a), (t1, b)) in enumerate(zip(anchors[:-1], anchors[1:], strict=True)):
        expand("IMPULSE" if i % 2 == 0 else "ZIGZAG", "1H", t0, t1, a, b, streams)
    return native_prefix({d: tuple(points.items()) for d, points in streams.items()})


def test_w4_uses_w1_floor_and_original_w5_forward_rule():
    prefix = full_parent_prefix()
    result = ElliottSource(prefix).search(at(160), legs=("W4",))
    intended = [
        c
        for c in result.counts
        if c.parent_start.observed_at == at(72) and c.parent_end.observed_at == at(96)
    ]
    assert intended
    assert all(c.invalidation == 130 and c.objective.value == 170 for c in intended)
    assert all(len(c.parent_prefix.children) == 3 for c in intended)
    for count in intended:
        count.validate(at(160))


def test_abc_complete_geometry_has_no_invented_objective_or_graph_writes():
    prefix = full_parent_prefix()
    size = len(prefix.graph.nodes)
    result = ElliottSource(prefix).search(at(160), legs=("ABC",))
    assert any(
        g.parent_prefix.points[-1].observed_at == at(120) and g.parent_end.observed_at == at(144)
        for g in result.geometry
    )
    assert not result.counts
    assert dict(result.diagnostics)["ABC_NAMED_PARENT_FORWARD_OBJECTIVE_AUTHORITY_UNDEFINED"] > 0
    assert len(prefix.graph.nodes) == size
    assert CompleteProofSearch(prefix, at(160)).resumptions(legs=("ABC",)) == result.geometry


@pytest.mark.parametrize("kind", ("DOUBLE_THREE", "TRIPLE_THREE"))
def test_nonleaf_combinations_have_every_corrective_subdivision(kind):
    streams = {}
    anchors = expand(kind, "4H", 0, 120, 100, 180, streams)
    prefix = native_prefix({d: tuple(points.items()) for d, points in streams.items()})
    search = CompleteProofSearch(prefix, at(140))
    waves = search.proofs("4H", kind, tuple(point(prefix, "4H", h) for h, _ in anchors))
    assert waves
    for wave in waves:
        wave.validate(at(140))
        assert len(wave.children) == LEGS[kind]
        assert all(c.kind != "IMPULSE" and c.degree == "1H" for c in wave.children)


def test_objective_revocation_cascades_and_cannot_be_rebound():
    prefix = w2_prefix()
    result = ElliottSource(prefix).search(at(60), legs=("W2",))
    count = result.counts[0]
    producer = ContractProducer(prefix)
    producer.add_elliott_count(count, at(60))
    prefix.graph.terminate(count.objective.event_id)
    assert not prefix.graph.live(count.count_id, at(60))
    with pytest.raises(ContractError, match="UNBOUND_MUTATED_OR_INVALIDATED_SOURCE"):
        ElliottSource(prefix).search(at(60), legs=("W2",))


def test_relabelled_asset_changes_provenance_but_not_geometry_or_objective():
    first = w2_prefix()
    second = native_prefix(
        {"1H": ANCHORS, "4H": ((0, 100), (24, 200), (48, 160))}, pair="OTHER-SYNTH"
    )
    a = ElliottSource(first).search(at(60), legs=("W2",)).counts
    b = ElliottSource(second).search(at(60), legs=("W2",)).counts

    def geometry(count):
        return (
            count.leg_name,
            tuple(p.price for p in count.correction.points),
            tuple(tuple(p.price for p in c.points) for c in count.parent_prefix.children),
            count.invalidation,
            count.objective.value,
        )

    assert {geometry(c) for c in a} == {geometry(c) for c in b}
    assert {c.count_id for c in a}.isdisjoint(c.count_id for c in b)


@pytest.mark.parametrize(
    "anchors,reason",
    (
        (
            ((0, 100), (4, 130), (8, 120), (12, 175), (16, 125), (24, 200)),
            "IMPULSE_ORIGIN_OVERLAP_OR_EXTENSION",
        ),
        (((0, 100), (4, 140), (8, 120), (12, 155), (16, 150), (24, 210)), "WAVE_THREE_SHORTEST"),
        (
            ((0, 100), (4, 130), (8, 120), (12, 175), (16, 160), (24, 170)),
            "UNSUPPORTED_TRUNCATED_PROFILE_DIAGNOSTIC_ONLY",
        ),
    ),
)
def test_native_impulse_rejections_remain_exact(anchors, reason):
    prefix = native_prefix({"1H": anchors})
    search = CompleteProofSearch(prefix, at(40))
    assert not search.proofs("1H", "IMPULSE", tuple(point(prefix, "1H", h) for h, _ in anchors))
    assert dict(search.diagnostics)[reason] > 0


def test_recursive_1d_subdivisions_match_every_parent_leg_exactly():
    streams = {}
    anchors = expand("ZIGZAG", "1D", 0, 720, 300, 200, streams)
    prefix = native_prefix({d: tuple(points.items()) for d, points in streams.items()})
    search = CompleteProofSearch(prefix, at(800))
    points = tuple(point(prefix, "1D", h) for h, _ in anchors)
    waves = search.proofs("1D", "ZIGZAG", points)
    assert waves

    def verify(wave):
        wave.validate(at(800))
        if wave.degree == "1H":
            assert not wave.children
        else:
            assert len(wave.children) == LEGS[wave.kind]
            for a, b, child in zip(wave.points[:-1], wave.points[1:], wave.children, strict=True):
                assert (a.observed_at, a.price) == (
                    child.points[0].observed_at,
                    child.points[0].price,
                )
                assert (b.observed_at, b.price) == (
                    child.points[-1].observed_at,
                    child.points[-1].price,
                )
                verify(child)

    for wave in waves:
        verify(wave)


@pytest.mark.parametrize("kind", ("DOUBLE_THREE", "TRIPLE_THREE"))
def test_combinations_at_1h_remain_explicit_diagnostic(kind):
    prefix = w2_prefix()
    search = CompleteProofSearch(prefix, at(60))
    assert not search.waves("1H", kind)
    assert dict(search.diagnostics)["SUBDEGREE_PROOF_UNAVAILABLE_DIAGNOSTIC"] > 0


def test_protected_period_and_foreign_endpoint_rejected():
    prefix = w2_prefix()
    with pytest.raises(ContractError, match="PROTECTED_PERIOD"):
        CompleteProofSearch(prefix, datetime(2024, 1, 1, tzinfo=UTC))
    other = w2_prefix()
    foreign = replace(point(other, "1H", 0), event_id=digest("foreign"))
    with pytest.raises(ContractError, match="ENDPOINT_NOT_IN_CAUSAL_PREFIX"):
        CompleteProofSearch(prefix, at(60)).waves("1H", "IMPULSE", foreign)


def test_old_complete_proof_survives_more_than_24_new_pivots():
    extended = ANCHORS + tuple((60 + i * 4, 180 if i % 2 == 0 else 150) for i in range(30))
    prefix = native_prefix({"1H": extended, "4H": ((0, 100), (24, 200), (48, 160))})
    result = ElliottSource(prefix).search(at(200), legs=("W2",))
    assert (
        len([p for p in prefix.points.values() if p.degree == "1H" and p.observed_at > at(48)])
        >= 24
    )
    assert result.counts
    assert any(c.parent_end.observed_at == at(48) for c in result.counts)


def test_incremental_new_endpoints_equal_fresh_complete_census(monkeypatch):
    prefix = w2_prefix()
    source = ElliottSource(prefix)
    assert not source.search(at(55), legs=("W2",)).counts
    late = source.search(at(56), legs=("W2",))
    fresh = ElliottSource(prefix).search(at(56), legs=("W2",))
    assert {c.count_id for c in late.counts} == {c.count_id for c in fresh.counts}
    assert {g.structure_id for g in late.geometry} == {g.structure_id for g in fresh.geometry}
    scans = source.endpoint_scans
    queries = source._search.sequence_queries

    def no_repeat(*args, **kwargs):
        raise AssertionError("Unchanged endpoint must not enumerate again")

    monkeypatch.setattr(source._search, "_sequences", no_repeat)
    assert source.search(at(56), legs=("W2",)) == late
    assert source.search(at(60), legs=("W2",)).counts == late.counts
    assert source.endpoint_scans == scans
    assert source._search.sequence_queries == queries
    with pytest.raises(ContractError, match="PROOF_SEARCH_CLOCK_REVERSED"):
        source.search(at(55))


def test_delayed_native_child_ingestion_revisits_affected_endpoints():
    prefix = native_prefix({"4H": ((0, 100), (24, 200), (48, 160))})
    source = ElliottSource(prefix)
    assert not source.search(at(60), legs=("W2",)).counts
    scans = source.endpoint_scans
    native_prefix({"1H": ANCHORS}, prefix=prefix)
    result = source.search(at(60), legs=("W2",))
    assert result.counts and source.endpoint_scans > scans
    fresh = ElliottSource(prefix).search(at(60), legs=("W2",))
    assert {c.count_id for c in result.counts} == {c.count_id for c in fresh.counts}


def test_incremental_source_termination_removes_retained_proof():
    prefix = w2_prefix()
    source = ElliottSource(prefix)
    assert source.search(at(60), legs=("W2",)).counts
    prefix.graph.terminate(point(prefix, "1H", 0).event_id)
    assert not source.search(at(61), legs=("W2",)).counts


def test_persistent_producer_rejects_changed_point_identity():
    prefix = w2_prefix()
    source = ElliottSource(prefix)
    source.search(at(60), legs=("W2",))
    p = point(prefix, "1H", 4)
    prefix.points[p.event_id] = replace(p, price=p.price + 1)
    with pytest.raises(ContractError, match="PREFIX_POINT_ID_MUTATED"):
        source.search(at(61), legs=("W2",))
