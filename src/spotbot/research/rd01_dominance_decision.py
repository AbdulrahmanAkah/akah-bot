"""RD01-D3 conservative decision gate for a minimal dominance overlay."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any, cast

D3_SCHEMA_VERSION = "ams-rd01-d3-dominance-overlay-decision-v1"


@dataclass(frozen=True)
class OverlayCandidate:
    """One pre-registered minimal overlay candidate."""

    dominance_quadrant: str
    action: str
    target: str
    multiplier: float
    aggregate_excess_return: float
    aggregate_mean_trade_pnl: float
    daily_excess_negative_folds: int
    trade_expectancy_negative_folds: int
    rationale: str


def _metric(
    aggregate_daily: Mapping[str, Any],
    return_column: str,
    metric: str,
) -> float | None:
    metrics = aggregate_daily.get("metrics")

    if not isinstance(metrics, Mapping):
        return None

    series_metrics = metrics.get(return_column)

    if not isinstance(series_metrics, Mapping):
        return None

    value = series_metrics.get(metric)

    if value is None:
        return None

    return float(value)


def evaluate_overlay_decision(
    d2_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply the pre-registered D3 stability gate.

    The gate can authorize only one minimal entry-weight overlay.  It cannot
    authorize exit changes, leverage, Kelly sizing, production, or live use.
    """

    if d2_report.get("status") != "COMPLETE":
        return {
            "schema_version": D3_SCHEMA_VERSION,
            "status": "BLOCKED_BY_UPSTREAM",
            "decision": "INCONCLUSIVE_MORE_EVIDENCE_REQUIRED",
            "reason": "RD01_D2_NOT_COMPLETE",
            "candidate": None,
            "ati_v1_authorized": False,
        }

    stability = d2_report.get("stability")
    aggregate_daily_by_quadrant = d2_report.get("aggregate_daily_by_quadrant")
    aggregate_trades_by_quadrant = d2_report.get("aggregate_trades_by_quadrant")

    if (
        not isinstance(stability, list)
        or not isinstance(aggregate_daily_by_quadrant, Mapping)
        or not isinstance(aggregate_trades_by_quadrant, Mapping)
    ):
        return {
            "schema_version": D3_SCHEMA_VERSION,
            "status": "FAIL",
            "decision": "INCONCLUSIVE_MORE_EVIDENCE_REQUIRED",
            "reason": "MALFORMED_D2_REPORT",
            "candidate": None,
            "ati_v1_authorized": False,
        }

    candidates: list[OverlayCandidate] = []
    sufficiently_observed_quadrants = 0

    for raw_row in stability:
        if not isinstance(raw_row, Mapping):
            continue

        row = cast(Mapping[str, Any], raw_row)
        quadrant = str(row.get("dominance_quadrant"))
        valid_daily_folds = int(row.get("valid_daily_folds") or 0)
        valid_trade_folds = int(row.get("valid_trade_folds") or 0)

        if valid_daily_folds >= 2 and valid_trade_folds >= 2:
            sufficiently_observed_quadrants += 1

        aggregate_daily_raw = aggregate_daily_by_quadrant.get(quadrant)
        aggregate_trade_raw = aggregate_trades_by_quadrant.get(quadrant)

        if not isinstance(aggregate_daily_raw, Mapping) or not isinstance(
            aggregate_trade_raw, Mapping
        ):
            continue

        aggregate_daily = cast(
            Mapping[str, Any],
            aggregate_daily_raw,
        )
        aggregate_trade = cast(
            Mapping[str, Any],
            aggregate_trade_raw,
        )
        aggregate_observations = int(aggregate_daily.get("observations") or 0)
        aggregate_trade_count = int(aggregate_trade.get("trade_count") or 0)
        aggregate_excess = float(aggregate_daily.get("m05_minus_exposure_matched_return") or 0.0)
        mean_trade_pnl_raw = aggregate_trade.get("mean_net_pnl")
        mean_trade_pnl = float(mean_trade_pnl_raw) if mean_trade_pnl_raw is not None else 0.0

        m05_sharpe = _metric(
            aggregate_daily,
            "m05_daily_return",
            "sharpe",
        )
        benchmark_sharpe = _metric(
            aggregate_daily,
            "exposure_matched_equal_weight_return",
            "sharpe",
        )
        m05_drawdown = _metric(
            aggregate_daily,
            "m05_daily_return",
            "maximum_drawdown",
        )
        benchmark_drawdown = _metric(
            aggregate_daily,
            "exposure_matched_equal_weight_return",
            "maximum_drawdown",
        )
        sharpe_disadvantage = (
            m05_sharpe is not None
            and benchmark_sharpe is not None
            and m05_sharpe <= benchmark_sharpe
        )
        drawdown_disadvantage = (
            m05_drawdown is not None
            and benchmark_drawdown is not None
            and m05_drawdown >= benchmark_drawdown
        )
        stable_harm = (
            valid_daily_folds == 3
            and valid_trade_folds >= 2
            and bool(row.get("daily_excess_sign_consistent"))
            and bool(row.get("trade_expectancy_sign_consistent"))
            and int(row.get("daily_excess_negative_folds") or 0) == 3
            and int(row.get("trade_expectancy_negative_folds") or 0) >= 2
            and aggregate_daily.get("status") == "VALID"
            and aggregate_trade.get("status") == "VALID"
            and aggregate_observations >= 180
            and aggregate_trade_count >= 12
            and aggregate_excess < 0.0
            and mean_trade_pnl < 0.0
            and (sharpe_disadvantage or drawdown_disadvantage)
        )

        if stable_harm:
            candidates.append(
                OverlayCandidate(
                    dominance_quadrant=quadrant,
                    action="REDUCE_NEW_ENTRY_TARGET_WEIGHT",
                    target="M05_NEW_ENTRIES_ONLY",
                    multiplier=0.50,
                    aggregate_excess_return=aggregate_excess,
                    aggregate_mean_trade_pnl=mean_trade_pnl,
                    daily_excess_negative_folds=int(row["daily_excess_negative_folds"]),
                    trade_expectancy_negative_folds=int(row["trade_expectancy_negative_folds"]),
                    rationale=(
                        "The quadrant underperformed the exposure-matched "
                        "benchmark in all three folds, produced negative "
                        "trade expectancy in at least two folds, and showed "
                        "a risk-adjusted disadvantage."
                    ),
                )
            )

    if candidates:
        selected = min(
            candidates,
            key=lambda item: (
                item.aggregate_excess_return,
                item.dominance_quadrant,
            ),
        )
        decision = "MINIMAL_OVERLAY_JUSTIFIED"
        reason = "ONE_STABLE_HARMFUL_QUADRANT_IDENTIFIED"
        status = "COMPLETE"
        candidate_payload: dict[str, Any] | None = asdict(selected)
        ati_authorized = True
    elif sufficiently_observed_quadrants >= 2:
        decision = "NO_OVERLAY_JUSTIFIED"
        reason = "NO_STABLE_HARMFUL_QUADRANT"
        status = "COMPLETE"
        candidate_payload = None
        ati_authorized = False
    else:
        decision = "INCONCLUSIVE_MORE_EVIDENCE_REQUIRED"
        reason = "INSUFFICIENT_CROSS_FOLD_QUADRANT_COVERAGE"
        status = "COMPLETE"
        candidate_payload = None
        ati_authorized = False

    return {
        "schema_version": D3_SCHEMA_VERSION,
        "research_stage": "RD01-D3",
        "status": status,
        "decision": decision,
        "reason": reason,
        "candidate": candidate_payload,
        "evaluated_candidates": [asdict(candidate) for candidate in candidates],
        "sufficiently_observed_quadrants": (sufficiently_observed_quadrants),
        "ati_v1_authorized": ati_authorized,
        "safety": {
            "entry_weight_overlay_only": ati_authorized,
            "exit_logic_change_authorized": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
            "production_ready": False,
            "live_ready": False,
            "md02_authorized": False,
            "kelly_used": False,
            "leverage_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
    }
