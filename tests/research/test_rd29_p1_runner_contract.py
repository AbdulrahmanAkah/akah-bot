from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd

from spotbot.research.rd20_p2_minimal_pullback import MembershipSnapshot
from spotbot.research.rd29_thesis_context import POLICIES

RUNNER_PATH = Path("scripts/research/run_rd29_thesis_confidence_lifecycle.py")


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "rd29_p1_runner_contract",
        RUNNER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load RD29 economic runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(
    *,
    start: str,
    end: str,
    members: tuple[tuple[str, int], ...],
) -> MembershipSnapshot:
    return MembershipSnapshot(
        universe_id="C2",
        decision_time=pd.Timestamp(start),
        effective_end=pd.Timestamp(end),
        members=members,
    )


def test_policy_registry_and_hard_gate_count_are_frozen():
    module = load_runner()
    assert tuple(module.POLICIES) == tuple(POLICIES)
    assert len(module.POLICIES) == 4
    assert len(module.HARD_GATES) == 14
    assert module.CONTROL_PARITY_EXPECTED_ROWS == 18


def test_output_contract_contains_selection_report_and_manifest_excludes_itself():
    module = load_runner()
    assert "selected-thesis-policy-freeze.json" in module.OUTPUT_NAMES
    assert "rd29-p1-thesis-confidence-lifecycle-report-v1.json" in module.OUTPUT_NAMES
    assert "output-manifest.json" not in module.OUTPUT_NAMES
    assert len(module.OUTPUT_NAMES) == 14


def test_selection_membership_keeps_only_2022_2023_overlap():
    module = load_runner()
    snapshots = [
        snapshot(
            start="2021-01-01T00:00:00Z",
            end="2022-01-01T00:00:00Z",
            members=(("OLD-USDT", 1),),
        ),
        snapshot(
            start="2021-12-01T00:00:00Z",
            end="2022-02-01T00:00:00Z",
            members=(("A-USDT", 1),),
        ),
        snapshot(
            start="2023-12-01T00:00:00Z",
            end="2024-02-01T00:00:00Z",
            members=(("B-USDT", 1),),
        ),
        snapshot(
            start="2024-01-01T00:00:00Z",
            end="2024-02-01T00:00:00Z",
            members=(("NEW-USDT", 1),),
        ),
    ]
    selected = module.selection_membership(snapshots)
    assert [item.members[0][0] for item in selected] == [
        "A-USDT",
        "B-USDT",
    ]


def test_required_feature_pairs_include_membership_only_assets():
    module = load_runner()
    events = pd.DataFrame([{"pair": "SIGNAL-USDT"}])
    snapshots = [
        snapshot(
            start="2022-01-01T00:00:00Z",
            end="2023-01-01T00:00:00Z",
            members=(
                ("SIGNAL-USDT", 1),
                ("BREADTH-ONLY-USDT", 2),
            ),
        )
    ]
    assert module.required_feature_pairs(events, snapshots) == [
        "BREADTH-ONLY-USDT",
        "SIGNAL-USDT",
    ]


def test_signal_membership_coverage_checks_pair_and_rank():
    module = load_runner()
    snapshots = [
        snapshot(
            start="2022-01-01T00:00:00Z",
            end="2023-01-01T00:00:00Z",
            members=(("AAA-USDT", 1), ("BBB-USDT", 2)),
        )
    ]
    events = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2022-06-01T00:00:00Z"),
                "universe_id": "C2",
                "pair": "AAA-USDT",
                "membership_rank": 1,
            }
        ]
    )
    result = module.validate_signal_membership_coverage(
        events,
        snapshots,
    )
    assert result == {
        "signal_rows_checked": 1,
        "mismatch_count": 0,
    }


def test_control_parity_source_is_rd28_and_requires_18_rows():
    module = load_runner()
    assert module.RD28_RESULTS_COMMIT == ("2ec43cfdab0a72ec10b9197c5a8dfb579595fe4b")
    assert module.RD28_RUN_METRICS.as_posix() == (
        "data/research/rd28_p1_runtime/portfolio-run-metrics.csv"
    )
    assert module.CONTROL_PARITY_EXPECTED_ROWS == 18


def test_runner_import_has_no_economic_side_effects():
    module = load_runner()
    assert module.OUTPUT.as_posix() == "data/research/rd29_p1_runtime"
    assert callable(module.main)
