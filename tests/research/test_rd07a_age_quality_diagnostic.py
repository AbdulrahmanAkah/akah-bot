import numpy as np

from spotbot.research.rd07a_age_quality_diagnostic import (
    fit_residual_model,
    mechanism_decision,
)


def test_residual_model_removes_linear_quality_component() -> None:
    control = np.arange(20, dtype=float).reshape(-1, 1)
    age = control[:, 0] * 2
    model = fit_residual_model(age, control)
    assert np.allclose(model.apply(age, control), 0)


def test_mechanism_decision_is_diagnostic_only() -> None:
    assert mechanism_decision(0.03, 2, 0.1) == "AGE_RETAINS_INCREMENTAL_CONTENT_AFTER_CONTROLS"
