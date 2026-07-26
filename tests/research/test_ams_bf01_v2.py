from __future__ import annotations

import pytest

from spotbot.research.ams_bf01_v2 import (
    DATE_COLUMNS,
    build_audit,
    extract_benchmark_comparison,
    extract_beta_folds,
    extract_rd01_benchmarks,
    extract_variant_diagnostics,
    parse_fraction,
    render_percent,
    resolve_entity_exact,
    validate_drawdown,
    validate_exposure,
    validate_spot_return,
)


def test_entity_matching_is_exact_and_keeps_benchmarks_distinct() -> None:
    assert resolve_entity_exact("MD01-M05") == "M05_DUAL_28"
    assert resolve_entity_exact("B00") == "MD01_B00_CASH"
    assert resolve_entity_exact("B01") == "MD01_B01_BTC_BUY_HOLD"
    assert resolve_entity_exact("B02") == "MD01_B02_EQUAL_WEIGHT"
    assert resolve_entity_exact("prefix-MD01-M05-suffix") is None
    assert resolve_entity_exact("M05") is None


def test_aggregate_and_fold_zero_are_never_conflated() -> None:
    payload = {
        "benchmarks": {
            "B00": {
                "name": "CASH",
                "BASE_COST": {
                    "compounded_return": 0.0,
                    "folds": [{"net_return": 0.0, "maximum_drawdown": 0.0, "exposure": 0.0}],
                },
            },
            "B01": {
                "name": "BTC_BUY_AND_HOLD",
                "BASE_COST": {
                    "compounded_return": 1.25,
                    "folds": [
                        {"net_return": -0.5, "maximum_drawdown": 0.6, "exposure": 1.0}
                    ],
                },
            },
            "B02": {
                "name": "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE",
                "BASE_COST": {
                    "compounded_return": 2.0,
                    "folds": [{"net_return": -0.7, "maximum_drawdown": 0.8, "exposure": 1.0}],
                },
            },
        }
    }
    records = extract_benchmark_comparison(payload)
    btc_aggregate = [
        record
        for record in records
        if record.entity == "MD01_B01_BTC_BUY_HOLD"
        and record.metric == "total_return"
        and record.scope == "aggregate"
    ]
    btc_fold = [
        record
        for record in records
        if record.entity == "MD01_B01_BTC_BUY_HOLD"
        and record.metric == "net_return"
        and record.scope == "fold"
    ]
    assert btc_aggregate[0].value == 1.25
    assert btc_fold[0].value == -0.5
    assert btc_fold[0].fold_id == "WF01"


def test_percent_values_are_scaled_only_once() -> None:
    assert parse_fraction("12.5%") == pytest.approx(0.125)
    assert parse_fraction(0.125) == pytest.approx(0.125)
    assert render_percent("12.5%") == "12.50%"
    assert render_percent(0.125) == "12.50%"


def test_window_days_is_metadata_not_beta() -> None:
    payload = {
        "benchmarks": {
            "BTC_BUY_AND_HOLD": 2.19,
            "EQUAL_WEIGHT_SURVIVOR_30": 7.83,
            "HIGH_BETA_28": {
                "net_compounded_return": 2.35,
                "average_exposure": 0.99,
                "maximum_exposure": 1.0,
                "selection_count": 208,
                "turnover": 133.0,
                "window_days": 28,
            },
            "HIGH_BETA_84": {
                "net_compounded_return": 1.38,
                "average_exposure": 0.99,
                "maximum_exposure": 1.0,
                "selection_count": 208,
                "turnover": 67.0,
                "window_days": 84,
            },
        }
    }
    records = extract_rd01_benchmarks(payload)
    window = [record for record in records if record.metric == "window_days"]
    beta = [record for record in records if record.metric == "beta"]
    assert {record.value for record in window} == {28, 84}
    assert all(record.scope == "metadata" for record in window)
    assert beta == []


def test_snapshot_time_is_a_date_alias() -> None:
    assert "snapshot_time" in DATE_COLUMNS


def test_missing_m02_contributor_ledger_is_not_evaluated() -> None:
    payload = {
        "variants": {
            "MD01-M02": {
                "concentration": {"hhi": 0.2, "top_1": 0.39, "top_3": 0.62, "top_5": 0.75},
                "fold_returns": [-0.62, 0.44, 1.28],
                "net_pnl": 110073.0,
                "trade_count": 128,
            }
        }
    }
    _, robustness = extract_variant_diagnostics(payload, "MD01-M02")
    assert robustness.status == "NOT_EVALUATED"
    assert robustness.judgement == "NOT_EVALUATED"


@pytest.mark.parametrize(
    ("function", "value"),
    [
        (validate_spot_return, -1.0),
        (validate_spot_return, -1.01),
        (validate_drawdown, 1.01),
        (validate_exposure, 1.01),
    ],
)
def test_domain_gates_reject_impossible_values(function: object, value: float) -> None:
    with pytest.raises(ValueError):
        function(value, "test/path")  # type: ignore[operator]


def test_beta_extraction_uses_exact_variant_and_whitelist() -> None:
    payload = {
        "fold_estimates": [
            {
                "variant_id": "MD01-M05",
                "fold_id": "WF01",
                "beta": 0.2,
                "downside_beta": 0.19,
                "r_squared": 0.15,
                "residual_return": 0.0,
                "maximum_btc_exposure": 1.0,
                "observations": 100,
                "window_days": 28,
            },
            {
                "variant_id": "MD01-M02",
                "fold_id": "WF01",
                "beta": 0.4,
                "r_squared": 0.2,
                "residual_return": 0.0,
                "maximum_btc_exposure": 1.0,
                "observations": 100,
            },
        ]
    }
    records = extract_beta_folds(payload, "MD01-M05")
    assert all(record.entity == "M05_DUAL_28" for record in records)
    metadata_names = {"window_days", "fold_id", "variant_id"}
    assert {record.metric for record in records}.isdisjoint(metadata_names)


def test_audit_does_not_authorize_risk_adjusted_alpha_without_aligned_series() -> None:
    benchmark_payload = {
        "benchmarks": {
            "BTC_BUY_AND_HOLD": 2.19,
            "EQUAL_WEIGHT_SURVIVOR_30": 7.83,
            "HIGH_BETA_28": {
                "net_compounded_return": 2.35,
                "average_exposure": 0.99,
                "maximum_exposure": 1.0,
                "selection_count": 208,
                "turnover": 133.0,
                "window_days": 28,
            },
            "HIGH_BETA_84": {
                "net_compounded_return": 1.38,
                "average_exposure": 0.99,
                "maximum_exposure": 1.0,
                "selection_count": 208,
                "turnover": 67.0,
                "window_days": 84,
            },
        }
    }
    concentration = {
        "variants": {
            "MD01-M05": {
                "concentration": {"hhi": 0.11, "top_1": 0.18, "top_3": 0.48, "top_5": 0.66},
                "fold_returns": [-0.448, 1.089, 2.199],
                "net_pnl": 283975.0,
                "trade_count": 147,
            },
            "MD01-M02": {
                "concentration": {"hhi": 0.2, "top_1": 0.39, "top_3": 0.62, "top_5": 0.75},
                "fold_returns": [-0.62, 0.44, 1.28],
                "net_pnl": 110073.0,
                "trade_count": 128,
            },
        }
    }
    m05_records, _ = extract_variant_diagnostics(concentration, "MD01-M05")
    m02_records, robustness = extract_variant_diagnostics(concentration, "MD01-M02")
    result = build_audit(
        benchmark_records=extract_rd01_benchmarks(benchmark_payload),
        diagnostic_records=[*m05_records, *m02_records],
        beta_records=[],
        m02_robustness=robustness,
    )
    assert result["benchmark_audit"]["alpha_value_judgement"] == "INCONCLUSIVE"
    assert result["benchmark_audit"]["risk_adjusted_comparison_authorized"] is False
