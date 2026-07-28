from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from spotbot.research.rd08_market_state_panel import (
    average_pairwise_correlation,
    valid_market_label,
)


def test_market_label_requires_registered_coverage() -> None:
    values = pd.Series([0.01] * 19 + [np.nan] * 11)
    assert valid_market_label(values, member_count=30) is None
    assert valid_market_label(pd.Series([0.01] * 21), member_count=30) == pytest.approx(0.01)


def test_pairwise_correlation_requires_ten_pairs() -> None:
    few = pd.DataFrame(np.arange(42 * 4).reshape(42, 4))
    assert average_pairwise_correlation(few) is None
    enough = pd.DataFrame({str(index): np.arange(42, dtype=float) + index for index in range(5)})
    assert average_pairwise_correlation(enough) == 1.0
