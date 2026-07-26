from __future__ import annotations

import numpy as np


def test_score_bins_are_exhaustive_and_non_overlapping() -> None:
    values = np.array(
        [0, 49.9, 50, 54.9, 55, 59.9, 60, 64.9, 65, 69.9, 70, 74.9, 75, 79.9, 80, 100]
    )
    bins = [-np.inf, 50, 55, 60, 65, 70, 75, 80, np.inf]
    assigned = np.digitize(values, bins, right=False)
    assert len(assigned) == len(values)
    assert (assigned >= 1).all()
