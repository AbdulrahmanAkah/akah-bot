"""Source and synthetic runtime evidence; never load canonical outcomes or bars."""

import ast
import inspect
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_rd27_later_trigger_v2_native_hook import native_kwargs

from spotbot.research import rd27_lifecycle_replay as replay
from spotbot.research.rd27_later_trigger_v2_native_hook import NativeV2ShadowHook


class IdentityClockObserver:
    """Test-only observer stores immutable identity, not a mutable native position."""

    def __init__(self):
        self.active = {}
        self.events = []

    def sync_native_position(self, *, pair, position, fallback_observed_through):
        assert pair not in self.active
        self.active[pair] = (position.pair, position.entry_time)
        self.events.append(("ENTRY", self.active[pair], position.entry_time))

    def observe_position(self, *, pair, decision_time):
        assert pair in self.active
        self.events.append(("OBSERVE", self.active[pair], decision_time))

    def close_position(self, *, pair, closed_at):
        identity = self.active.pop(pair)
        self.events.append(("TERMINAL", identity, closed_at))


def test_keyword_only_identity_and_clock_were_omitted_by_prior_adjudicator():
    parameters = inspect.signature(NativeV2ShadowHook.close_position).parameters
    assert parameters["pair"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["closed_at"].kind is inspect.Parameter.KEYWORD_ONLY


def test_native_source_owns_two_removals_and_two_v2_notifications():
    tree = ast.parse(Path(inspect.getfile(replay)).read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "replay_lifecycle_policy")
    removals = sorted(n.lineno for n in ast.walk(function) if isinstance(n, ast.Delete)
                      and any(ast.unparse(t) == "positions[pair]" for t in n.targets))
    notifications = sorted((n for n in ast.walk(function) if isinstance(n, ast.Call)
                            and ast.unparse(n.func) ==
                            "later_trigger_v2_shadow_hook.close_position"),
                           key=lambda n: n.lineno)
    assert len(removals) == len(notifications) == 2
    for notification, removal in zip(notifications, removals, strict=True):
        assert {k.arg: ast.unparse(k.value) for k in notification.keywords} == {
            "pair": "pair", "closed_at": "timestamp",
        }
        assert notification.end_lineno + 1 == removal


@pytest.mark.parametrize("scenario", ["static_time_failure", "max_hold", "entry_touch",
                                     "existing_gap", "existing_touch"])
def test_terminal_identity_clock_and_opaque_native_output_parity(scenario):
    kwargs = native_kwargs()
    entry = kwargs["events"].iloc[0].timestamp + pd.Timedelta(hours=1)
    frame = kwargs["frames"]["AAA-USDT"]
    if scenario == "max_hold":
        frame.loc[:, "close"] = 101.0
        expected = entry + pd.Timedelta(hours=168)
    elif scenario == "static_time_failure":
        expected = entry + pd.Timedelta(hours=72)
    else:
        kwargs["policy_id"] = replay.ADAPTIVE_EXIT_FIXED_CAPITAL
        hour = 1 if scenario == "entry_touch" else 2
        frame.loc[hour, "low"] = 94.0
        if scenario == "existing_gap":
            frame.loc[hour, "open"] = 94.0
        expected = entry + pd.Timedelta(hours=hour - 1)
    baseline = replay.replay_lifecycle_policy(**kwargs)
    observer = IdentityClockObserver()
    observed = replay.replay_lifecycle_policy(**kwargs, later_trigger_v2_shadow_hook=observer)
    for off, on in zip(baseline[:2], observed[:2], strict=True):
        assert_frame_equal(off, on, check_exact=True)
    assert baseline[2:] == observed[2:]
    terminals = [event for event in observer.events if event[0] == "TERMINAL"]
    assert terminals == [("TERMINAL", ("AAA-USDT", entry), expected)]
    assert not observer.active
    assert observer.events[0] == ("ENTRY", ("AAA-USDT", entry), entry)
    if scenario != "entry_touch":
        assert observer.events[-2] == ("OBSERVE", ("AAA-USDT", entry), expected)


def test_control_policy_is_delegated_not_covered_by_v2_close_sites():
    source = inspect.getsource(replay.replay_lifecycle_policy)
    tree = ast.parse(source)
    delegates = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and ast.unparse(n.func) == "rd26_replay_policy"]
    assert len(delegates) == 1
    assert delegates[0].lineno < next(n.lineno for n in ast.walk(tree)
                                    if isinstance(n, ast.For)
                                    and ast.unparse(n.target) == "timestamp")
