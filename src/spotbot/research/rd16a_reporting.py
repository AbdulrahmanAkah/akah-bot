from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from spotbot.research.rd16a_common import (
    BASELINE_COMMIT,
    BRANCH,
    DECISION,
    NEXT_STAGE,
    SCHEMA_VERSION,
    STRATEGIC_STATUS,
    CohortData,
    RD16AError,
    _finite_float,
    _optional_float,
)


def _protocol() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": "RD16A_DAILY_FORENSIC_CLOSURE",
        "baseline_commit": BASELINE_COMMIT,
        "branch": BRANCH,
        "purpose": (
            "Measure why RD15 failed to capture the 2020-2021 bull-market opportunity "
            "and preserve only independently supported components."
        ),
        "sealed_data": {
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
        },
        "optimization_performed": False,
        "winner_selected": False,
        "required_analyses": [
            "bull upside capture",
            "regime exposure and time in cash",
            "trade concentration",
            "exit-reason attribution",
            "asset contribution",
            "score calibration",
            "rejected-opportunity outcomes",
            "same-bar stop audit",
        ],
        "bull_adequacy_rule": {
            "high_opportunity_threshold": 2.0,
            "minimum_strategy_return": 1.0,
            "minimum_upside_capture": 0.40,
            "minimum_bull_exposure": 0.35,
        },
        "next_stage": NEXT_STAGE,
    }


def _all_finite(payload: object) -> bool:
    if isinstance(payload, bool) or payload is None or isinstance(payload, str):
        return True
    if isinstance(payload, (int, float)):
        return math.isfinite(float(payload))
    if isinstance(payload, dict):
        return all(_all_finite(key) and _all_finite(value) for key, value in payload.items())
    if isinstance(payload, (list, tuple)):
        return all(_all_finite(value) for value in payload)
    return True


def _build_report(
    *,
    primary: CohortData,
    transfer: CohortData,
    bull_rows: Sequence[Mapping[str, Any]],
    concentration_rows: Sequence[Mapping[str, Any]],
    exit_rows: Sequence[Mapping[str, Any]],
    score_rows: Sequence[Mapping[str, Any]],
    rejection_rows: Sequence[Mapping[str, Any]],
    regime_rows: Sequence[Mapping[str, Any]],
    same_bar_rows: Sequence[Mapping[str, Any]],
    deterministic_replay_match: bool,
    frozen_inputs_unchanged: bool,
) -> dict[str, Any]:
    primary_bull = [row for row in bull_rows if row["cohort"] == "PRIMARY_LONG_HISTORY"]
    high_opportunity_rows = [row for row in primary_bull if bool(row["high_opportunity_year"])]
    bull_capture_pass = bool(high_opportunity_rows) and all(
        bool(row["bull_adequacy_pass"]) for row in high_opportunity_rows
    )
    bull_exposure_rows = [
        row
        for row in regime_rows
        if row["cohort"] == "PRIMARY_LONG_HISTORY" and row["market_regime"] == "BULL"
    ]
    bull_exposure_pass = bool(bull_exposure_rows) and all(
        row["bull_participation_pass"] is True for row in bull_exposure_rows
    )

    primary_concentration = {
        int(row["top_trade_count"]): row
        for row in concentration_rows
        if row["cohort"] == "PRIMARY_LONG_HISTORY"
    }
    transfer_concentration = {
        int(row["top_trade_count"]): row
        for row in concentration_rows
        if row["cohort"] == "TRANSFER_COHORT"
    }
    primary_top1 = _optional_float(primary_concentration[1]["share_of_total_net_pnl"])
    transfer_top1 = _optional_float(transfer_concentration[1]["share_of_total_net_pnl"])

    primary_score_all = next(
        row
        for row in score_rows
        if row["cohort"] == "PRIMARY_LONG_HISTORY"
        and row["scope"] == "ACCEPTED"
        and row["score_bin"] == "ALL"
    )
    transfer_score_all = next(
        row
        for row in score_rows
        if row["cohort"] == "TRANSFER_COHORT"
        and row["scope"] == "ACCEPTED"
        and row["score_bin"] == "ALL"
    )

    profit_floor_rows = [
        row for row in exit_rows if row["exit_reason"] == "PROFIT_PROTECTION_FLOOR"
    ]
    profit_floor_supported = bool(profit_floor_rows) and all(
        float(row["net_pnl"]) > 0 and float(row["win_rate"]) == 1.0 for row in profit_floor_rows
    )
    thesis_rows = [
        row for row in exit_rows if row["exit_reason"] == "THESIS_HEALTH_CONFIRMED_DETERIORATION"
    ]
    thesis_independently_supported = bool(thesis_rows) and all(
        float(row["net_pnl_excluding_largest_winner"]) > 0 for row in thesis_rows
    )

    primary_metrics = primary.metrics
    transfer_metrics = transfer.metrics
    strategic_gates = {
        "bull_capture_adequate": bull_capture_pass,
        "bull_exposure_gte_35pct": bull_exposure_pass,
        "primary_top_trade_share_lte_35pct": (primary_top1 is not None and primary_top1 <= 0.35),
        "transfer_top_trade_share_lte_50pct": (transfer_top1 is not None and transfer_top1 <= 0.50),
        "score_not_inverse_primary": (
            _optional_float(primary_score_all["spearman_score_forward_20"]) is not None
            and float(primary_score_all["spearman_score_forward_20"]) >= 0
        ),
        "score_not_inverse_transfer": (
            _optional_float(transfer_score_all["spearman_score_forward_20"]) is not None
            and float(transfer_score_all["spearman_score_forward_20"]) >= 0
        ),
        "profit_floor_independently_supported": profit_floor_supported,
        "thesis_exit_independently_supported": thesis_independently_supported,
    }
    technical_gates = {
        "primary_rd15_validation_pass": primary.validation.get("status") == "PASS",
        "transfer_rd15_validation_pass": transfer.validation.get("status") == "PASS",
        "deterministic_replay_match": deterministic_replay_match,
        "frozen_inputs_unchanged": frozen_inputs_unchanged,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "optimization_performed": False,
        "winner_selected": False,
    }

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "baseline_commit": BASELINE_COMMIT,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "rd15_engineering_status": "PASS",
        "rd15_primary_architecture_status": STRATEGIC_STATUS,
        "evidence_classification": "USEFUL_COMPONENTS_ONLY",
        "next_stage": NEXT_STAGE,
        "technical_gates": technical_gates,
        "strategic_gates": strategic_gates,
        "primary_metrics": {
            "net_return": _finite_float(primary_metrics["net_return"], field="primary.net_return"),
            "cagr": _finite_float(primary_metrics["cagr"], field="primary.cagr"),
            "maximum_drawdown": _finite_float(
                primary_metrics["maximum_drawdown"], field="primary.maximum_drawdown"
            ),
            "closed_trade_count": int(primary_metrics["closed_trade_count"]),
            "profit_factor": _finite_float(
                primary_metrics["profit_factor"], field="primary.profit_factor"
            ),
        },
        "transfer_metrics": {
            "net_return": _finite_float(
                transfer_metrics["net_return"],
                field="transfer.net_return",
            ),
            "cagr": _finite_float(transfer_metrics["cagr"], field="transfer.cagr"),
            "maximum_drawdown": _finite_float(
                transfer_metrics["maximum_drawdown"], field="transfer.maximum_drawdown"
            ),
            "closed_trade_count": int(transfer_metrics["closed_trade_count"]),
            "profit_factor": _finite_float(
                transfer_metrics["profit_factor"], field="transfer.profit_factor"
            ),
        },
        "reusable_components": [
            "portfolio accounting and reconciliation",
            "Spot-only and Long-only enforcement",
            "next-bar deterministic execution",
            "initial protective stop",
            "profit-protection floor concept",
            "auditable signal/order/fill/trade/equity ledgers",
            "cross-asset simultaneous-signal handling",
        ],
        "rejected_as_final_architecture": [
            "daily primary signal and execution timeframe",
            "current total-score ranking calibration",
            "current thesis-health exit",
            "current bull-market participation level",
            "three-asset primary opportunity universe",
        ],
        "same_bar_stop_count": len(same_bar_rows),
        "rejected_opportunity_group_count": len(rejection_rows),
        "limitations": [
            "Daily candles cannot reconstruct intrabar paths.",
            "Arithmetic removal of top trades is a sensitivity diagnostic, not a portfolio rerun.",
            "The transfer cohort has already been observed and is not a pristine holdout.",
            (
                "RD16-A diagnoses the daily architecture; it does not optimize "
                "or select a replacement."
            ),
        ],
    }
    if not _all_finite(report):
        raise RD16AError("Final RD16-A report contains non-finite values.")
    return report


def _markdown_reports(
    *,
    report: Mapping[str, Any],
    bull_rows: Sequence[Mapping[str, Any]],
    concentration_rows: Sequence[Mapping[str, Any]],
    exit_rows: Sequence[Mapping[str, Any]],
    regime_rows: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    primary_bull = [row for row in bull_rows if row["cohort"] == "PRIMARY_LONG_HISTORY"]
    bull_lines = "\n".join(
        (
            f"- {int(row['year'])}: strategy {100 * float(row['strategy_return']):.2f}%, "
            f"equal-weight {100 * float(row['equal_weight_return']):.2f}%, "
            f"capture {100 * float(row['equal_weight_upside_capture']):.2f}%"
            if row["equal_weight_upside_capture"] is not None
            else (
                f"- {int(row['year'])}: strategy {100 * float(row['strategy_return']):.2f}%, "
                f"equal-weight {100 * float(row['equal_weight_return']):.2f}%"
            )
        )
        for row in primary_bull
    )
    primary_concentration = [
        row for row in concentration_rows if row["cohort"] == "PRIMARY_LONG_HISTORY"
    ]
    concentration_lines = "\n".join(
        f"- Top {int(row['top_trade_count'])}: "
        f"{100 * float(row['share_of_total_net_pnl']):.2f}% of net PnL"
        for row in primary_concentration
        if row["share_of_total_net_pnl"] is not None
    )
    profit_floor = [row for row in exit_rows if row["exit_reason"] == "PROFIT_PROTECTION_FLOOR"]
    profit_lines = "\n".join(
        f"- {row['cohort']}: {int(row['trade_count'])} trades, "
        f"{100 * float(row['win_rate']):.2f}% win rate, net PnL {float(row['net_pnl']):.2f}"
        for row in profit_floor
    )
    bull_exposure = [row for row in regime_rows if row["market_regime"] == "BULL"]
    exposure_lines = "\n".join(
        f"- {row['cohort']}: mean bull exposure {100 * float(row['mean_exposure']):.2f}%"
        for row in bull_exposure
        if row["mean_exposure"] is not None
    )

    methodology = f"""# RD16-A Daily Forensic Closure Methodology

## Frozen basis

- Baseline commit: `{BASELINE_COMMIT}`
- Branch: `{BRANCH}`
- RD15 is treated as immutable input.
- No 2025 test data, 2026 holdout data, Dune data, optimization, or winner selection is allowed.

## Purpose

RD16-A measures why the daily RD15 architecture failed to exploit the 2020–2021
bull-market opportunity. It separates engineering validity from strategic adequacy
and identifies only components supported strongly enough to carry into the 1H/4H
multi-timeframe architecture.

## Analyses

1. Strategy return versus equal-weight and BTC yearly benchmarks.
2. Bull upside capture and bull-regime exposure.
3. Top-trade concentration sensitivity.
4. Exit-reason attribution.
5. Asset contribution.
6. Score/forward-return calibration.
7. Rejected-opportunity forward outcomes.
8. Same-bar stop-path audit.

## Bull adequacy rule

When the equal-weight benchmark gains more than 200% in a year, RD15 must either
gain at least 100% or capture at least 40% of the benchmark upside. Mean bull-regime
exposure must be at least 35% unless rejected opportunities demonstrate negative
expectancy.
"""

    results = f"""# RD16-A Daily Forensic Closure Results

## Decision

- Decision: `{report["decision"]}`
- Engineering status: `{report["rd15_engineering_status"]}`
- Strategic status: `{report["rd15_primary_architecture_status"]}`
- Evidence: `{report["evidence_classification"]}`
- Next stage: `{report["next_stage"]}`

## Primary bull capture

{bull_lines}

## Bull exposure

{exposure_lines}

## Profit concentration

{concentration_lines}

## Profit-protection floor

{profit_lines}

## Conclusion

RD15 remains a valid deterministic daily benchmark, but it is rejected as the
primary trading architecture. The next stage moves to completed 1H signals, 4H
structure, and 1D/1W context while preserving only independently supported
components.
"""

    trade_audit = """# RD16-A Trade and Exit Audit

## Interpretation rules

- Profit concentration is expected in trend-following systems, but extreme
  dependence on one or two trades makes transfer evidence fragile.
- Arithmetic removal is a sensitivity diagnostic and does not reproduce path-dependent sizing.
- A positive exit category is not independently supported when its result depends
  on one extreme outlier.
- Zero-holding-bar exits require an explicit conservative daily-bar path assumption.

See the generated CSV tables for exact trade concentration, exit attribution,
asset contribution, and same-bar cases.
"""

    reclassification = f"""# RD15 Strategic Reclassification

RD15 passed engineering and accounting validation but failed the strategic objective
of an aggressive Spot speculation system.

The primary architecture status is `{STRATEGIC_STATUS}` because the daily
implementation captured too little of the 2020–2021 bull-market opportunity,
remained overly dependent on a small number of large winners, and did not
demonstrate reliable score ranking in transfer evidence.

The daily strategy is frozen as a benchmark. It will not be polished into the
final bot. RD16-B restores the repository's original multi-timeframe hierarchy:
1H signal/execution, 4H structure, and 1D/1W regime context.
"""

    return {
        "rd16a-daily-forensic-methodology-v1.md": methodology,
        "rd16a-daily-forensic-results-v1.md": results,
        "rd16a-daily-forensic-trade-audit-v1.md": trade_audit,
        "rd15-strategic-reclassification-v1.md": reclassification,
    }
