"""Tests for RD19-P1 architecture specification."""

from __future__ import annotations

from spotbot.research.rd19_p1_architecture import (
    CANDIDATE_ID,
    architecture_specification,
    discovery_dimension_rows,
    prohibition_rows,
    signal_pipeline_rows,
    state_machine_rows,
    traceability_rows,
)


def test_architecture_identity_and_constraints() -> None:
    spec = architecture_specification()
    assert spec["candidate_id"] == CANDIDATE_ID
    constraints = spec["research_constraints"]
    assert constraints["spot_only"] is True
    assert constraints["long_only"] is True
    assert constraints["cash_only"] is True
    assert constraints["leverage"] is False
    assert constraints["margin"] is False
    assert constraints["derivatives"] is False
    assert constraints["post_2024_access"] is False


def test_single_sleeve_and_no_compression_rescue() -> None:
    spec = architecture_specification()
    sleeve = spec["single_sleeve_rule"]
    assert sleeve["secondary_sleeves_allowed_in_p2"] is False
    assert sleeve["compression_engine_carried_forward"] is False


def test_signal_pipeline_is_complete_and_ordered() -> None:
    rows = signal_pipeline_rows(architecture_specification())
    assert [row["order"] for row in rows] == list(range(1, 10))
    assert rows[0]["component"] == "UNIVERSE_ELIGIBILITY"
    assert rows[-1]["component"] == "PROTECTIVE_AND_CONVEX_EXIT"


def test_state_machine_has_no_direct_off_to_open_transition() -> None:
    rows = state_machine_rows()
    off = next(row for row in rows if row["state"] == "OFF")
    assert off["allowed_transition"] == "OBSERVE"
    assert off["orders_allowed"] is False


def test_discovery_is_bounded_but_unselected() -> None:
    spec = architecture_specification()
    discovery = spec["discovery_contract"]
    assert discovery["maximum_candidate_variants"] == 12
    assert discovery["variant_matrix_frozen_before_first_p2_run"] is True
    assert discovery["post_2024_access"] is False
    rows = discovery_dimension_rows(spec)
    assert len(rows) == 6
    assert all(row["status"] == "UNSELECTED" for row in rows)


def test_traceability_and_prohibitions_are_nonempty() -> None:
    spec = architecture_specification()
    assert len(traceability_rows()) == 5
    prohibitions = prohibition_rows(spec)
    names = {str(row["prohibition"]) for row in prohibitions}
    assert "LEVERAGE" in names
    assert "ANY_PER_UNIVERSE_PARAMETERIZATION" in names
