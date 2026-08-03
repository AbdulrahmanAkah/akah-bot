from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from spotbot.research.rd18_p3x_a1c_corporate_actions import (
    A1CError,
    build_a1c,
    deterministic_manifest,
)


def _registry() -> dict[str, object]:
    return {
        "schema_version": ("rd18-p3x-a1-corporate-action-registry-v1"),
        "default_policy": {
            "normalization_authorized": False,
            "raw_gap_filling_authorized": False,
            "strategy_use_authorized": False,
            "unregistered_gap_classification": "FAILED_RETRYABLE",
        },
        "events": {
            "ETN-USDT": {
                "diagnostic_evidence": {
                    "file_name": "remaining-gap-diagnostic-summary.json",
                    "network_scope": ("BOUNDED_PUBLIC_KUCOIN_SPOT_KLINES_DIAGNOSTIC"),
                    "raw_market_data_written": False,
                    "sha256": "5" * 64,
                },
                "event_id": ("KUCOIN_ETN_DELIST_RELIST_SMART_CHAIN_SWAP_2023_09_22"),
                "event_type": "CHAIN_MIGRATION",
                "expected_integrity_report": {
                    "duplicates": 0,
                    "invalid": 0,
                    "missing": 8570,
                },
                "normalization_authorized": False,
                "observed_first_open_after_gap": ("2024-09-13T10:00:00+00:00"),
                "observed_last_close_before_gap": ("2023-09-22T08:00:00+00:00"),
                "official_sources": [
                    "https://example.com/etn-delisting",
                    "https://example.com/etn-swap",
                ],
                "official_trading_closed_at": ("2023-09-22T07:00:00+00:00"),
                "official_trading_reopened_at": ("2024-09-13T10:00:00+00:00"),
                "raw_series_policy": ("PRESERVE_GAP_AND_BLOCK_CONCATENATION"),
                "strategy_use_authorized": False,
                "symbol": "ETN/USDT",
                "venue": "kucoin",
            },
            "STRAX-USDT": {
                "diagnostic_evidence": {
                    "file_name": "strax-diagnostic.json",
                    "network_scope": ("TWO_BOUNDED_PUBLIC_KUCOIN_SPOT_REQUESTS"),
                    "raw_market_data_written": False,
                    "sha256": "8" * 64,
                },
                "event_id": "KUCOIN_STRAX_TOKEN_SWAP_2024_03_19",
                "event_type": "TOKEN_SWAP",
                "expected_integrity_report": {
                    "duplicates": 0,
                    "invalid": 0,
                    "missing": 817,
                },
                "normalization_authorized": False,
                "observed_first_close_after_gap": ("2024-04-22T10:00:00+00:00"),
                "observed_last_close_before_gap": ("2024-03-19T08:00:00+00:00"),
                "official_sources": [
                    "https://example.com/strax-suspension",
                    "https://example.com/strax-complete",
                ],
                "official_trading_closed_at": ("2024-03-19T07:00:00+00:00"),
                "official_trading_reopened_at": ("2024-04-22T09:00:00+00:00"),
                "raw_series_policy": ("PRESERVE_GAP_AND_BLOCK_CONCATENATION"),
                "strategy_use_authorized": False,
                "swap_ratio": {
                    "new_units": 10,
                    "old_units": 1,
                },
                "symbol": "STRAX/USDT",
                "venue": "kucoin",
            },
        },
    }


def _protocol() -> dict[str, object]:
    return {
        "schema_version": ("rd18-p3x-a1c-causal-corporate-action-policy-v1"),
        "authorizations": {
            "broad_candidate_generation": False,
            "normalization_execution": False,
            "production": False,
            "return_calculation": False,
            "strategy_replay": False,
        },
        "decision_rules": {
            "raw_data_policy": {
                "fill_suspended_hours": False,
                "preserve_exchange_timestamps": True,
                "preserve_observed_gap": True,
                "stitch_pre_and_post_segments": False,
                "write_synthetic_candles": False,
            }
        },
    }


def _plan() -> list[dict[str, str]]:
    return [
        {
            "pair": "ETN-USDT",
            "symbol": "ETN/USDT",
            "action": "CORPORATE_ACTION_POLICY_REQUIRED",
            "required_since_open": "2019-01-01T00:00:00+00:00",
        },
        {
            "pair": "STRAX-USDT",
            "symbol": "STRAX/USDT",
            "action": "CORPORATE_ACTION_POLICY_REQUIRED",
            "required_since_open": "2019-01-01T00:00:00+00:00",
        },
    ]


def _checkpoint() -> dict[str, object]:
    return {
        "pairs": {
            "ETN-USDT": {"state": "CORPORATE_ACTION_POLICY_REQUIRED"},
            "STRAX-USDT": {"state": "CORPORATE_ACTION_POLICY_REQUIRED"},
        }
    }


def _build():
    return build_a1c(
        registry=_registry(),
        protocol=_protocol(),
        plan_rows=_plan(),
        checkpoint=_checkpoint(),
    )


def test_valid_registry_builds_two_events_and_six_segments() -> None:
    result = _build()

    assert len(result.events) == 2
    assert len(result.segments) == 6
    assert len(result.terminals) == 2
    assert result.report["passed"] is True
    assert result.report["strategy_ready_events"] == 0


def test_pre_gap_post_segments_are_distinct_and_fail_closed() -> None:
    result = _build()

    for pair in ("ETN-USDT", "STRAX-USDT"):
        rows = [row for row in result.segments if row["pair"] == pair]
        assert [row["segment_type"] for row in rows] == [
            "PRE_EVENT_IDENTITY",
            "SUSPENSION_OR_MIGRATION_GAP",
            "POST_EVENT_IDENTITY",
        ]
        assert all(row["strategy_use_authorized"] is False for row in rows)
        gap = rows[1]
        assert gap["raw_rows_authorized"] is False
        assert gap["synthetic_rows_authorized"] is False


def test_terminal_classifications_are_pair_specific() -> None:
    result = _build()
    by_pair = {str(row["pair"]): str(row["terminal_classification"]) for row in result.terminals}

    assert by_pair["ETN-USDT"] == ("DOCUMENTED_CHAIN_MIGRATION_SEGMENTS_NOT_STRATEGY_READY")
    assert by_pair["STRAX-USDT"] == ("DOCUMENTED_TOKEN_SWAP_SEGMENTS_NOT_STRATEGY_READY")


def test_normalization_authorization_fails_closed() -> None:
    registry = _registry()
    events = registry["events"]
    assert isinstance(events, dict)
    event = events["STRAX-USDT"]
    assert isinstance(event, dict)
    event["normalization_authorized"] = True

    with pytest.raises(A1CError, match="must be false"):
        build_a1c(
            registry=registry,
            protocol=_protocol(),
            plan_rows=_plan(),
            checkpoint=_checkpoint(),
        )


def test_checkpoint_state_must_be_terminal() -> None:
    checkpoint = _checkpoint()
    pairs = checkpoint["pairs"]
    assert isinstance(pairs, dict)
    row = pairs["ETN-USDT"]
    assert isinstance(row, dict)
    row["state"] = "FAILED_RETRYABLE"

    with pytest.raises(A1CError, match="checkpoint state"):
        build_a1c(
            registry=_registry(),
            protocol=_protocol(),
            plan_rows=_plan(),
            checkpoint=checkpoint,
        )


def test_plan_action_must_be_terminal() -> None:
    plan = _plan()
    plan[0]["action"] = "NETWORK_MARKET_PROBE_REQUIRED"

    with pytest.raises(A1CError, match="A1 plan action"):
        build_a1c(
            registry=_registry(),
            protocol=_protocol(),
            plan_rows=plan,
            checkpoint=_checkpoint(),
        )


def test_event_reopening_after_cutoff_fails_closed() -> None:
    registry = _registry()
    events = registry["events"]
    assert isinstance(events, dict)
    event = events["ETN-USDT"]
    assert isinstance(event, dict)
    event["official_trading_reopened_at"] = "2025-01-02T00:00:00+00:00"

    with pytest.raises(A1CError, match="sealed historical window"):
        build_a1c(
            registry=registry,
            protocol=_protocol(),
            plan_rows=_plan(),
            checkpoint=_checkpoint(),
        )


def test_registry_pair_set_is_exact() -> None:
    registry = _registry()
    events = registry["events"]
    assert isinstance(events, dict)
    events["OTHER-USDT"] = deepcopy(events["ETN-USDT"])

    with pytest.raises(A1CError, match="registered pair set mismatch"):
        build_a1c(
            registry=registry,
            protocol=_protocol(),
            plan_rows=_plan(),
            checkpoint=_checkpoint(),
        )


def test_official_sources_must_be_distinct_https() -> None:
    registry = _registry()
    events = registry["events"]
    assert isinstance(events, dict)
    event = events["ETN-USDT"]
    assert isinstance(event, dict)
    event["official_sources"] = [
        "http://example.com/one",
        "https://example.com/two",
    ]

    with pytest.raises(A1CError, match="must use HTTPS"):
        build_a1c(
            registry=registry,
            protocol=_protocol(),
            plan_rows=_plan(),
            checkpoint=_checkpoint(),
        )


def test_deterministic_manifest_tracks_exact_files(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("x\n1\n", encoding="utf-8")

    first = deterministic_manifest(tmp_path, ("b.csv", "a.json"))
    second = deterministic_manifest(tmp_path, ("a.json", "b.csv"))

    assert first == second
    assert len(first["files"]) == 2
    assert first["network_requests"] == 0
    assert first["synthetic_candles_written"] is False


def test_report_prohibits_generation_replay_and_returns() -> None:
    report = _build().report
    authorizations = report["authorizations"]
    assert isinstance(authorizations, dict)

    assert authorizations["broad_candidate_generation"] is False
    assert authorizations["normalization_execution"] is False
    assert authorizations["return_calculation"] is False
    assert authorizations["strategy_replay"] is False
    assert authorizations["synthetic_candle_writes"] is False


def test_input_objects_are_not_mutated() -> None:
    registry = _registry()
    protocol = _protocol()
    plan = _plan()
    checkpoint = _checkpoint()
    before = deepcopy((registry, protocol, plan, checkpoint))

    build_a1c(
        registry=registry,
        protocol=protocol,
        plan_rows=plan,
        checkpoint=checkpoint,
    )

    assert (registry, protocol, plan, checkpoint) == before
