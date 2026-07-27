from __future__ import annotations

import json
from typing import Any

import pandas as pd
import pytest

from spotbot.research.rd01_dominance import (
    DECISION_LAG,
    DominanceDataError,
    align_dominance_sources,
    canonical_json_bytes,
    coverage_record,
    future_mutation_invariance,
    parse_coinmetrics_dominance_history,
    parse_defillama_stablecoin_history,
    sha256_bytes,
    tag_events_causally,
    validate_dominance_frame,
)


def coinmetrics_payload(
    start: str,
    periods: int,
    *,
    skip: set[int] | None = None,
) -> dict[str, Any]:
    skip = skip or set()
    days = pd.date_range(start, periods=periods, freq="1D", tz="UTC")
    rows: list[dict[str, Any]] = []

    for index, day in enumerate(days):
        if index in skip:
            continue

        total = 1_000_000_000_000.0 + index * 1_000_000.0
        btc_dominance = 40.0 + index * 0.01
        eth_dominance = 20.0
        rows.extend(
            [
                {
                    "asset": "btc",
                    "time": (day + pd.Timedelta(minutes=2)).isoformat(),
                    "CapMrktEstDomPct": str(btc_dominance),
                    "CapMrktEstUSD": str(total * btc_dominance / 100.0),
                },
                {
                    "asset": "eth",
                    "time": (day + pd.Timedelta(minutes=3)).isoformat(),
                    "CapMrktEstDomPct": str(eth_dominance),
                    "CapMrktEstUSD": str(total * eth_dominance / 100.0),
                },
            ]
        )

    return {"data": rows}


def stablecoin_payload(
    start: str,
    periods: int,
    *,
    skip: set[int] | None = None,
) -> list[dict[str, Any]]:
    skip = skip or set()
    days = pd.date_range(start, periods=periods, freq="1D", tz="UTC")
    rows: list[dict[str, Any]] = []

    for index, day in enumerate(days):
        if index in skip:
            continue

        rows.append(
            {
                "date": int(day.timestamp()),
                "totalCirculatingUSD": {"peggedUSD": 100_000_000_000.0 + index * 100_000.0},
            }
        )

    return rows


def parse_pair(
    *,
    periods: int = 20,
    market_skip: set[int] | None = None,
    stable_skip: set[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    start = pd.Timestamp("2021-01-01T00:00:00Z")
    end = start + pd.Timedelta(days=periods)
    market = parse_coinmetrics_dominance_history(
        coinmetrics_payload("2021-01-01", periods, skip=market_skip),
        start=start,
        end_exclusive=end,
    )
    stable = parse_defillama_stablecoin_history(
        stablecoin_payload("2021-01-01", periods, skip=stable_skip),
        start=start,
        end_exclusive=end,
    )
    aligned = align_dominance_sources(market, stable)
    return market, stable, aligned


def test_coinmetrics_parser_enforces_next_day_availability() -> None:
    market, _, _ = parse_pair(periods=5)

    assert len(market) == 5
    assert (market["available_at"] - market["day"]).eq(DECISION_LAG).all()
    assert market["btc_dominance_pct"].iloc[0] == pytest.approx(40.0)
    assert market["total_market_cap_usd"].iloc[0] == pytest.approx(1_000_000_000_000.0)


def test_defillama_parser_handles_pegged_usd_mapping() -> None:
    _, stable, _ = parse_pair(periods=5)

    assert len(stable) == 5
    assert stable["stablecoin_market_cap_usd"].iloc[0] == pytest.approx(100_000_000_000.0)
    assert (stable["available_at"] - stable["day"]).eq(DECISION_LAG).all()


def test_alignment_is_inner_without_forward_fill() -> None:
    _, _, aligned = parse_pair(
        periods=10,
        market_skip={3},
        stable_skip={6},
    )

    assert len(aligned) == 8
    assert pd.Timestamp("2021-01-04T00:00:00Z") not in set(aligned["day"])
    assert pd.Timestamp("2021-01-07T00:00:00Z") not in set(aligned["day"])
    assert aligned["stablecoin_market_cap_usd"].notna().all()


def test_causal_tagging_uses_only_available_observations() -> None:
    _, _, aligned = parse_pair(periods=10)
    events = pd.DataFrame(
        {
            "event_time": [
                pd.Timestamp("2021-01-03T12:00:00Z"),
                pd.Timestamp("2021-01-05T00:00:00Z"),
            ]
        }
    )
    tagged = tag_events_causally(events, aligned)

    assert tagged["available_at"].iloc[0] <= tagged["event_time"].iloc[0]
    assert tagged["available_at"].iloc[1] <= tagged["event_time"].iloc[1]
    assert tagged["day"].iloc[0] == pd.Timestamp("2021-01-02T00:00:00Z")
    assert tagged["day"].iloc[1] == pd.Timestamp("2021-01-04T00:00:00Z")


def test_future_mutation_cannot_change_past_tags() -> None:
    _, _, aligned = parse_pair(periods=20)
    events = pd.DataFrame(
        {
            "event_time": pd.date_range(
                "2021-01-04T00:00:00Z",
                periods=12,
                freq="1D",
            )
        }
    )

    assert future_mutation_invariance(
        events,
        aligned,
        cutoff=pd.Timestamp("2021-01-10T23:59:59Z"),
        feature_columns=(
            "btc_dominance_pct",
            "stablecoin_dominance_pct",
        ),
    )


def test_validation_passes_complete_short_window() -> None:
    market, stable, aligned = parse_pair(periods=20)
    start = pd.Timestamp("2021-01-01T00:00:00Z")
    end = pd.Timestamp("2021-01-21T00:00:00Z")
    summary = validate_dominance_frame(
        aligned,
        source_frames=(("COINMETRICS", market), ("DEFILLAMA", stable)),
        start=start,
        end_exclusive=end,
    )

    assert summary.status == "PASS"
    assert summary.no_forward_fill
    assert summary.causal_availability_enforced
    assert summary.timestamps_unique
    assert summary.values_bounded


def test_validation_marks_large_gaps_as_fail() -> None:
    market, stable, aligned = parse_pair(
        periods=20,
        market_skip={3, 4, 5, 6, 7, 8, 9, 10},
    )
    start = pd.Timestamp("2021-01-01T00:00:00Z")
    end = pd.Timestamp("2021-01-21T00:00:00Z")
    summary = validate_dominance_frame(
        aligned,
        source_frames=(("COINMETRICS", market), ("DEFILLAMA", stable)),
        start=start,
        end_exclusive=end,
    )

    assert summary.status == "FAIL"
    assert summary.reason == "INSUFFICIENT_DAILY_COVERAGE"


def test_validation_rejects_same_day_availability() -> None:
    market, stable, aligned = parse_pair(periods=5)
    aligned.loc[:, "available_at"] = aligned["day"]

    summary = validate_dominance_frame(
        aligned,
        source_frames=(("COINMETRICS", market), ("DEFILLAMA", stable)),
        start=pd.Timestamp("2021-01-01T00:00:00Z"),
        end_exclusive=pd.Timestamp("2021-01-06T00:00:00Z"),
    )

    assert summary.status == "FAIL"
    assert not summary.causal_availability_enforced


def test_parser_rejects_non_numeric_dominance() -> None:
    payload = coinmetrics_payload("2021-01-01", 2)
    payload["data"][0]["CapMrktEstDomPct"] = "invalid"

    with pytest.raises(DominanceDataError):
        parse_coinmetrics_dominance_history(
            payload,
            start=pd.Timestamp("2021-01-01T00:00:00Z"),
            end_exclusive=pd.Timestamp("2021-01-03T00:00:00Z"),
        )


def test_coverage_record_reports_missing_days() -> None:
    market, _, _ = parse_pair(periods=5, market_skip={2})
    coverage = coverage_record(
        market,
        source_id="COINMETRICS",
        start=pd.Timestamp("2021-01-01T00:00:00Z"),
        end_exclusive=pd.Timestamp("2021-01-06T00:00:00Z"),
    )

    assert coverage.observations == 4
    assert coverage.missing_days == 1
    assert coverage.maximum_gap_days == 1


def test_canonical_hash_is_order_independent() -> None:
    left = canonical_json_bytes({"b": 2, "a": 1})
    right = canonical_json_bytes({"a": 1, "b": 2})

    assert left == right
    assert sha256_bytes(left) == sha256_bytes(right)
    assert json.loads(left) == {"a": 1, "b": 2}


def test_parser_derives_dominance_from_free_market_cap_panel() -> None:
    payload = {
        "data": [
            {
                "asset": "btc",
                "time": "2021-01-01T00:02:00+00:00",
                "CapMrktCurUSD": "500",
            },
            {
                "asset": "eth",
                "time": "2021-01-01T00:03:00+00:00",
                "CapMrktCurUSD": "300",
            },
            {
                "asset": "xrp",
                "time": "2021-01-01T00:04:00+00:00",
                "CapMrktCurUSD": "200",
            },
        ]
    }
    market = parse_coinmetrics_dominance_history(
        payload,
        start=pd.Timestamp("2021-01-01T00:00:00Z"),
        end_exclusive=pd.Timestamp("2021-01-02T00:00:00Z"),
    )

    assert len(market) == 1
    assert market["total_market_cap_usd"].iloc[0] == pytest.approx(1_000.0)
    assert market["btc_dominance_pct"].iloc[0] == pytest.approx(50.0)
    assert market["eth_dominance_pct"].iloc[0] == pytest.approx(30.0)
    assert market["altcoin_market_cap_usd"].iloc[0] == pytest.approx(500.0)
