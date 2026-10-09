"""Research-only window binding; delegates native signal formulas unchanged."""

from types import FunctionType

import pandas as pd

from spotbot.research import rd26_exit_architecture as rd26

START = pd.Timestamp("2022-01-01T00:00:00Z")
CUTOFF = pd.Timestamp("2023-01-01T00:00:00Z")


def filter_2022(events: pd.DataFrame) -> pd.DataFrame:
    """Bind only the window in a private globals mapping, never patch RD26 state.

    The exact native filter code computes its native MAX_HOLD+1h coverage guard.
    Only DATA_CUTOFF differs from native mixed-window orchestration. No policy,
    feature, predicate, threshold, or economic constant is changed.
    """
    timestamps = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
    if not timestamps.between(START, CUTOFF, inclusive="left").all():
        raise ValueError("construction input must already be 2022-only")
    namespace = dict(rd26.filter_robustness_events.__globals__)
    namespace["DATA_CUTOFF"] = CUTOFF
    function = FunctionType(rd26.filter_robustness_events.__code__, namespace)
    return function(events)


def construct(membership, frames):
    events, funnel = rd26.scan_focus_signals(
        membership=membership,
        features=frames,
        periods={"ROBUSTNESS_2022": (START, CUTOFF)},
        data_start=START,
        data_cutoff=CUTOFF,
        guard_each_period_hours=None,
    )
    return filter_2022(events), funnel
