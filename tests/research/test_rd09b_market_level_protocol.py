from spotbot.research.rd09b_market_level_protocol import (
    NAMESPACE_ORDER,
    ORIGINAL_RD09_BROAD_GATE,
    ORIGINAL_RD09_DUNE_SCORE,
    PILOT_RANGES,
    SCORE_WEIGHTS,
    market_level_score,
    registered_queries,
    validate_protocol,
)


def test_protocol_has_fixed_namespaces_months_and_execution_order() -> None:
    validate_protocol()
    queries = registered_queries()
    assert len(NAMESPACE_ORDER) == 5
    assert len(PILOT_RANGES) == 3
    assert len(queries) == 15
    assert [query.namespace for query in queries[:5]] == [
        "bitcoin",
        "ethereum",
        "cardano",
        "avalanche_c",
        "polkadot",
    ]
    assert queries[4].asset == "DOT"
    assert all(query.end_exclusive.startswith(("2022-", "2023-", "2024-")) for query in queries)


def test_market_score_is_non_predictive_and_original_rd09_is_unchanged() -> None:
    assert sum(SCORE_WEIGHTS.values()) == 100
    assert ORIGINAL_RD09_DUNE_SCORE == 65
    assert not ORIGINAL_RD09_BROAD_GATE
    assert (
        market_level_score(
            passing_namespace_count=4,
            causal_integrity_passed=True,
            reproducibility_passed=True,
            independent_information=True,
            zero_paid_spend=True,
            daily_frequency_suitable=True,
        )
        == 95
    )
