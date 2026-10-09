"""Synthetic-only checks for the bounded Phase A audit executor."""

import importlib.util
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pytest

SPEC = importlib.util.spec_from_file_location(
    "phase_a_recovery", Path(__file__).resolve().parents[2] / "governance/v2_a2_exec.py",
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def schema(open_type=None, close_type=None):
    open_type = pa.timestamp("us", tz="UTC") if open_type is None else open_type
    close_type = pa.timestamp("ms", tz="UTC") if close_type is None else close_type
    return pa.schema([("bar_open_time", open_type), ("bar_close_time", close_type)])


def test_schema_specific_units_and_timezone_are_preserved():
    start, end = pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2023-01-01", tz="UTC")
    bounds = audit.timestamp_bounds(schema(), start, end)
    for name in schema().names:
        assert all(scalar.type == schema().field(name).type for scalar in bounds[name])


def test_mixed_units_filter_runs_and_excludes_protected_boundary():
    start, end = pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2023-01-01", tz="UTC")
    dates = [start.to_pydatetime(), end.to_pydatetime()]
    table = pa.table({field.name: pa.array(dates, type=field.type) for field in schema()})
    bounds = audit.timestamp_bounds(table.schema, start, end)
    expression = None
    for name, (lower, upper) in bounds.items():
        term = (ds.field(name) >= lower) & (ds.field(name) < upper)
        expression = term if expression is None else expression & term
    assert ds.dataset(table).to_table(filter=expression).num_rows == 1


@pytest.mark.parametrize("invalid", [pa.timestamp("us"), pa.timestamp("us", tz="Europe/London"),
                                    pa.int64()])
def test_unknown_timezone_or_non_timestamp_fails_closed(invalid):
    with pytest.raises(RuntimeError):
        audit.timestamp_bounds(schema(open_type=invalid), pd.Timestamp("2022-01-01", tz="UTC"),
                               pd.Timestamp("2023-01-01", tz="UTC"))


def test_entry_spanning_bar_excluded_and_only_complete_bars_expected():
    entry = pd.Timestamp("2022-01-01T01:00Z")
    opens = audit.expected_opens(entry, entry + pd.Timedelta(hours=168))
    assert opens[0] == pd.Timestamp("2022-01-01T04:00Z")
    assert (opens + pd.Timedelta(hours=4) <= entry + pd.Timedelta(hours=168)).all()
    assert len(opens) == 41


def test_exact_entry_boundary_has_42_full_bars():
    entry = pd.Timestamp("2022-01-01T00:00Z")
    assert len(audit.expected_opens(entry, entry + pd.Timedelta(hours=168))) == 42


def test_missing_is_not_zero_or_timestamp():
    assert audit.timestamp_equal(pd.NaT, pd.NaT)
    assert not audit.timestamp_equal(pd.NaT, pd.Timestamp("2022-01-01", tz="UTC"))


def test_safe_projection_does_not_include_terminal_outcomes():
    assert not set(audit.SAFE_CONTROL) & {
        "exit_time", "exit_reason", "exit_price", "net_pnl", "gross_pnl", "holding_hours",
        "mfe", "mae", "return_fraction",
    }
