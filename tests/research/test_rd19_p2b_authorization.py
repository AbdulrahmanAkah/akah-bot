"""Tests for RD19-P2B discovery execution authorization."""

from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd19_p2b_authorization import (
    EXPECTED_RUNS,
    P2BAuthorizationError,
    authorization_checks,
    execution_contract,
    verify_execution_order,
)


def valid_execution_order() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    order = 0
    for variant_index in range(1, 13):
        for partition in (
            "DISCOVERY_CORE",
            "VALIDATION_2022",
            "STRESS_2023",
        ):
            for universe in ("C2", "D2", "E2"):
                for cost in (1.0, 2.0):
                    order += 1
                    rows.append(
                        {
                            "execution_order": order,
                            "variant_id": (f"RD19_P2_V{variant_index:02d}"),
                            "partition_id": partition,
                            "universe_id": universe,
                            "cost_multiplier": cost,
                        }
                    )
    return pd.DataFrame.from_records(rows)


def test_valid_execution_order_has_216_runs() -> None:
    frame = valid_execution_order()
    assert len(frame) == EXPECTED_RUNS
    verify_execution_order(frame)


def test_duplicate_execution_identity_is_rejected() -> None:
    frame = valid_execution_order()
    frame.loc[1, ["variant_id", "partition_id", "universe_id"]] = frame.loc[
        0, ["variant_id", "partition_id", "universe_id"]
    ]
    frame.loc[1, "cost_multiplier"] = frame.loc[
        0,
        "cost_multiplier",
    ]
    with pytest.raises(
        P2BAuthorizationError,
        match="duplicate run identities",
    ):
        verify_execution_order(frame)


def test_execution_contract_excludes_2024() -> None:
    contract = execution_contract(
        p2_matrix_hash="a" * 64,
        execution_order_hash="b" * 64,
        engine_hash="c" * 64,
        membership_hash="d" * 64,
    )
    assert contract["status"] == "AUTHORIZED_NOT_EXECUTED"
    assert contract["authorized_scope"]["expected_run_count"] == 216
    assert contract["2024_internal_confirmation_authorized"] is False
    assert contract["post_2024_holdout_authorized"] is False
    assert contract["production_authorized"] is False


def test_authorization_check_set_is_complete() -> None:
    checks = authorization_checks()
    assert len(checks) == 21
    assert all(row["passed"] is True for row in checks)
    assert all(row["blocking"] is True for row in checks)
