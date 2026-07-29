from spotbot.research.rd09b_dune_acquisition import (
    execution_gate,
    may_execute,
    validate_query_identity,
)


def test_credential_and_attestation_are_required_without_serialization() -> None:
    assert execution_gate({}).decision == "RD09B_DUNE_CREDENTIAL_REQUIRED"
    gated = execution_gate({"DUNE_API_KEY": "secret"})
    assert gated.decision == "RD09B_ZERO_SPEND_ATTESTATION_REQUIRED"
    assert "secret" not in repr(gated)


def test_unknown_or_excess_cost_cannot_execute() -> None:
    assert not may_execute(
        estimated_credits=None,
        credits_included=2500,
        credits_used=0,
    )
    assert not may_execute(
        estimated_credits=501,
        credits_included=2500,
        credits_used=0,
    )


def test_successful_query_is_not_reexecuted() -> None:
    sql = (
        "SELECT block_date FROM bitcoin.transactions "
        "WHERE block_time >= TIMESTAMP '2022-03-01' "
        "AND block_time < TIMESTAMP '2022-04-01' ORDER BY block_date"
    )
    digest = validate_query_identity(
        start="2022-03-01",
        end_exclusive="2022-04-01",
        prior_successful_hashes=set(),
        sql=sql,
    )
    try:
        validate_query_identity(
            start="2022-03-01",
            end_exclusive="2022-04-01",
            prior_successful_hashes={digest},
            sql=sql,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("duplicate successful execution was not blocked")
