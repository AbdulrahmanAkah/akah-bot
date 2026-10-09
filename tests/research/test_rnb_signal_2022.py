import pandas as pd
import pytest

from spotbot.research import rd26_exit_architecture as rd26
from spotbot.research.rnb_signal_2022 import CUTOFF, filter_2022


def events(times):
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(times, utc=True),
            "universe_id": "C2",
            "family_id": "MOMENTUM_BREAKOUT",
            "membership_rank": 1,
            "pair": "BTC-USDT",
        }
    )


def test_native_filter_semantics_and_module_globals_unchanged():
    frame = events(["2022-06-01", "2022-12-24", "2022-12-31"])
    original = rd26.DATA_CUTOFF
    actual = filter_2022(frame)
    native = rd26.filter_robustness_events(frame)
    expected = native.loc[native.timestamp + pd.Timedelta(hours=169) < CUTOFF]
    pd.testing.assert_frame_equal(actual, expected.reset_index(drop=True))
    assert original == rd26.DATA_CUTOFF
    assert len(actual) == 2


def test_already_mixed_input_rejected_not_filtered():
    with pytest.raises(ValueError, match="already be 2022"):
        filter_2022(events(["2022-06-01", "2023-01-01"]))


def test_exact_max_hold_guard_boundary():
    frame = events([CUTOFF - pd.Timedelta(hours=170), CUTOFF - pd.Timedelta(hours=169)])
    assert len(filter_2022(frame)) == 1
