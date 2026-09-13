from __future__ import annotations

import inspect

from spotbot.research import eaa_same_pair_secondary_shadow as shadow


def test_shadow_is_disabled_by_default() -> None:
    assert shadow.DEFAULT_SHADOW_ENABLED is False
    assert shadow.IMPLEMENTATION_PROTOCOL_ID == "SHADOW_DISABLED_BY_DEFAULT_CAUSAL_SAME_PAIR_SECONDARY_IMPLEMENTATION_V1"


def test_same_pair_bypasses_only_when_no_secondary_is_active() -> None:
    assert shadow.secondary_precedence_decision(same_pair_open=True, secondary_open=False, open_position_count=2) == "BYPASS_SAME_PAIR_ONLY_CONTINUE_NATIVE_DOWNSTREAM"


def test_global_single_active_secondary_precedes_downstream() -> None:
    assert shadow.secondary_precedence_decision(same_pair_open=True, secondary_open=True, open_position_count=2) == "BLOCK_GLOBAL_SINGLE_ACTIVE_SECONDARY"


def test_position_limit_remains_five() -> None:
    shadow.validate_shadow_constants()
    assert shadow.MAXIMUM_POSITIONS == 5
    assert shadow.secondary_precedence_decision(same_pair_open=True, secondary_open=False, open_position_count=5) == "BLOCK_POSITION_SLOTS"


def test_non_same_pair_remains_native_flow() -> None:
    assert shadow.secondary_precedence_decision(same_pair_open=False, secondary_open=False, open_position_count=4) == "NATIVE_FLOW"


def test_shadow_source_has_no_oracle_selection_dependency() -> None:
    source = inspect.getsource(shadow)
    for token in ("P4P2_EVENT_LOCAL_ORACLE_WEIGHT", "P4P3R_WIS_SELECTED_EVENT_ID", "P4P3R_WIS_WEIGHT", "CONTROL_EXIT_PRICE", "FUTURE_RETURN"):
        assert token not in source
