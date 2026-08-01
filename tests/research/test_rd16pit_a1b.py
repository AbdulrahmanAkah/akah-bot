from __future__ import annotations

import subprocess
import sys
import urllib.parse
from pathlib import Path

import pandas as pd
import pytest

from scripts.research.run_rd16pit_a1b import (
    A1BError,
    canonicalize_rows,
    complete_membership_only,
    decision_for_a1b,
    masked_numeric_sum,
    request_url,
    resolve_complete_top30_absence,
    scenario_summary,
    unresolved_year_symbol_summary,
    validate_request_url,
)


def test_request_is_hard_bounded_before_2021() -> None:
    url = request_url()
    validate_request_url(url)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert query["start_time"] == ["2018-12-30"]
    assert query["end_time"] == ["2020-12-31"]
    assert query["assets"] == ["*"]
    assert "2025" not in url
    assert "2026" not in url


def test_request_rejects_endpoint_or_date_drift() -> None:
    with pytest.raises(A1BError):
        validate_request_url(
            "https://api.coinmetrics.io/v4/timeseries/asset-metrics?"
            "assets=%2A&metrics=CapMrktCurUSD%2CCapMrktEstUSD&frequency=1d&"
            "start_time=2018-12-30&end_time=2020-12-31&end_inclusive=true&"
            "page_size=10000&paging_from=start&sort=time&"
            "ignore_unsupported_errors=true&ignore_forbidden_errors=true&"
            "null_as_zero=false"
        )
    with pytest.raises(A1BError):
        validate_request_url(request_url().replace("2020-12-31", "2025-01-01"))


def test_canonical_panel_prefers_current_then_estimated_cap() -> None:
    frame = canonicalize_rows(
        [
            {
                "asset": "btc",
                "time": "2019-01-01T00:00:00Z",
                "CapMrktCurUSD": "100",
                "CapMrktEstUSD": "90",
            },
            {
                "asset": "xrp",
                "time": "2019-01-01T00:00:00Z",
                "CapMrktCurUSD": None,
                "CapMrktEstUSD": "50",
            },
        ]
    )
    assert frame["market_cap_usd"].tolist() == [100.0, 50.0]
    assert frame["market_cap_source"].tolist() == [
        "CapMrktCurUSD",
        "CapMrktEstUSD",
    ]


def test_canonical_panel_rejects_sealed_timestamp() -> None:
    with pytest.raises(A1BError):
        canonicalize_rows(
            [
                {
                    "asset": "btc",
                    "time": "2021-01-01T00:00:00Z",
                    "CapMrktCurUSD": "100",
                }
            ]
        )


def test_only_complete_snapshots_are_rank_resolved() -> None:
    weekly = pd.DataFrame(
        {
            "rebalance_time": pd.to_datetime(
                ["2019-01-07T00:00:00Z", "2019-01-14T00:00:00Z"],
                utc=True,
            ),
            "canonical_symbol": ["BTC", "BTC"],
            "market_cap_rank": [1, 1],
        }
    )
    snapshots = pd.DataFrame(
        {
            "rebalance_time": pd.to_datetime(
                ["2019-01-07T00:00:00Z", "2019-01-14T00:00:00Z"],
                utc=True,
            ),
            "snapshot_complete": [False, True],
        }
    )
    result = complete_membership_only(weekly, snapshots)
    assert result["rebalance_time"].tolist() == [pd.Timestamp("2019-01-14T00:00:00Z")]


def test_a1b_does_not_loop_back_to_itself_when_fragile() -> None:
    frame = pd.DataFrame(
        {
            "fixed6_pit_status": [
                "PIT_ELIGIBLE",
                "UNRESOLVED_MARKET_CAP_RANK",
            ],
            "net_pnl": [10.0, -100.0],
            "rebalance_time": pd.to_datetime(
                ["2019-01-07T00:00:00Z", "2019-01-14T00:00:00Z"],
                utc=True,
            ),
        }
    )
    scenarios = scenario_summary(frame)
    decision, next_stage, _ = decision_for_a1b(frame, scenarios)
    assert decision == "PIT_INCONCLUSIVE_AND_FRAGILE_UNDER_BOUNDS"
    assert next_stage == "RD16_PIT_A1C_ALTERNATE_SOURCE_OR_RESEARCH_STOP"


def test_masked_pnl_partition_uses_explicit_net_pnl_column() -> None:
    frame = pd.DataFrame(
        {
            "fixed6_pit_status": [
                "PIT_ELIGIBLE",
                "FIXED_SELECTION_NOT_TOP6",
                "UNRESOLVED_MARKET_CAP_RANK",
            ],
            "net_pnl": [10.0, 20.0, -5.0],
        }
    )
    status = frame["fixed6_pit_status"].astype(str)
    eligible = status.eq("PIT_ELIGIBLE")
    unresolved = status.str.startswith("UNRESOLVED")
    non_pit = ~eligible & ~unresolved

    partition_total = (
        masked_numeric_sum(frame, eligible, "net_pnl")
        + masked_numeric_sum(frame, non_pit, "net_pnl")
        + masked_numeric_sum(frame, unresolved, "net_pnl")
    )

    assert partition_total == frame["net_pnl"].sum()


def test_runner_supports_direct_script_execution() -> None:
    repo = Path(__file__).resolve().parents[2]
    runner = repo / "scripts" / "research" / "run_rd16pit_a1b.py"
    completed = subprocess.run(
        [sys.executable, str(runner), "--help"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_complete_top30_absence_is_non_pit_membership() -> None:
    attribution = pd.DataFrame(
        {
            "rebalance_time": pd.to_datetime(
                ["2020-01-06T00:00:00Z"],
                utc=True,
            ),
            "market_cap_rank": [pd.NA],
            "fixed6_pit_status": ["UNRESOLVED_MARKET_CAP_RANK"],
            "fixed10_pit_status": ["UNRESOLVED_MARKET_CAP_RANK"],
        }
    )
    snapshots = pd.DataFrame(
        {
            "rebalance_time": pd.to_datetime(
                ["2020-01-06T00:00:00Z"],
                utc=True,
            ),
            "snapshot_complete": [True],
        }
    )

    result = resolve_complete_top30_absence(attribution, snapshots)

    assert result.iloc[0]["fixed6_pit_status"] == "FIXED_SELECTION_NOT_TOP6"
    assert result.iloc[0]["fixed10_pit_status"] == "FIXED_SELECTION_NOT_TOP10"
    assert result.iloc[0]["market_cap_rank_lower_bound"] == 31.0
    assert result.iloc[0]["rank_resolution_method"] == "COMPLETE_TOP30_ABSENCE"


def test_incomplete_snapshot_absence_remains_unresolved() -> None:
    attribution = pd.DataFrame(
        {
            "rebalance_time": pd.to_datetime(
                ["2020-01-06T00:00:00Z"],
                utc=True,
            ),
            "market_cap_rank": [pd.NA],
            "fixed6_pit_status": ["UNRESOLVED_MARKET_CAP_RANK"],
            "fixed10_pit_status": ["UNRESOLVED_MARKET_CAP_RANK"],
        }
    )
    snapshots = pd.DataFrame(
        {
            "rebalance_time": pd.to_datetime(
                ["2020-01-06T00:00:00Z"],
                utc=True,
            ),
            "snapshot_complete": [False],
        }
    )

    result = resolve_complete_top30_absence(attribution, snapshots)

    assert result.iloc[0]["fixed6_pit_status"] == "UNRESOLVED_MARKET_CAP_RANK"
    assert result.iloc[0]["rank_resolution_method"] == ("UNRESOLVED_MARKET_CAP_RANK")


def test_unresolved_summary_excludes_resolved_trades() -> None:
    frame = pd.DataFrame(
        {
            "year": [2020, 2020],
            "symbol": ["BTC", "ETH"],
            "fixed6_pit_status": [
                "PIT_ELIGIBLE",
                "UNRESOLVED_MARKET_CAP_RANK",
            ],
            "net_pnl": [10.0, -5.0],
        }
    )

    summary = unresolved_year_symbol_summary(frame)

    assert len(summary) == 1
    assert summary.iloc[0]["symbol"] == "ETH"
    assert summary.iloc[0]["net_pnl"] == -5.0
