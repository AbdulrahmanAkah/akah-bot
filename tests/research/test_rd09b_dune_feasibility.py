from spotbot.research.rd09b_dune_feasibility import (
    BroadCoverage,
    NamespaceCandidate,
    SectorCoverage,
    credit_budget,
    rank_namespaces,
    validate_weights,
)


def test_budget_and_weights_are_frozen() -> None:
    validate_weights()
    assert credit_budget(2500, 100) == 500
    assert credit_budget(1000, 900) == 100


def test_namespace_ranking_is_deterministic_and_capped() -> None:
    candidates = [
        NamespaceCandidate("ethereum", 1, True),
        NamespaceCandidate("bitcoin", 1, True),
        NamespaceCandidate("cardano", 1, True),
        NamespaceCandidate("avalanche_c", 1, True),
        NamespaceCandidate("polygon", 1, True),
        NamespaceCandidate("unsupported", 99, False),
    ]
    assert [item.namespace for item in rank_namespaces(candidates)] == [
        "avalanche_c",
        "bitcoin",
        "cardano",
        "ethereum",
    ]


def test_coverage_gates_fail_closed() -> None:
    broad = BroadCoverage(19, 0.9, 0.9, (0.9, 0.9, 0.9), (20, 20, 20), 0)
    sector = SectorCoverage(14, 0.9, (0.9, 0.9, 0.9), 2)
    assert not broad.passed
    assert not sector.passed
