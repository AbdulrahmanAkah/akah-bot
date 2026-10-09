from __future__ import annotations

import inspect

from spotbot.research.abc_exit_primitives_v1 import replay_overlay


def test_external_signal_adapter_is_optional_and_default_disabled() -> None:
    sig = inspect.signature(replay_overlay)
    assert "external_signal_schedule" in sig.parameters
    assert sig.parameters["external_signal_schedule"].default is None


def test_external_signal_adapter_preserves_legacy_and_external_branches() -> None:
    src = inspect.getsource(replay_overlay)
    assert "if external_signal_schedule is None:" in src
    assert "evaluate_completed_4h(" in src
    assert "EXTERNAL_STATE_CONDITIONED_HYPOTHESIS_SIGNAL" in src
    assert '"execution_time": decision_time + pd.Timedelta(hours=1)' in src
