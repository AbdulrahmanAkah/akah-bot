from __future__ import annotations

import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.research import rd16n_evaluation as rd16n
from spotbot.research.rd16c_common import (
    BRANCH,
    LOCAL_INPUT_ROOT,
    ROOT,
    SEALED_CUTOFF,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
    verify_local_dataset_hashes,
)
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16d_common import (
    COST_MULTIPLIERS,
    INITIAL_EQUITY,
    STRATEGIC_MONTHLY_TARGET,
    write_csv,
    write_json,
)
from spotbot.research.rd16d_metrics import (
    build_benchmark_daily,
    enrich_trades,
)
from spotbot.research.rd16q_domains import (
    DOMAIN_REGISTRY,
    INTERNAL_COLUMNS,
    SignalDomain,
    build_domain_candidates,
    build_market_internal_feature_frames,
    domain_registry_rows,
)

SCHEMA_VERSION: Final = "rd16q-signal-domain-expansion-alternative-data-v1"
DECISION: Final = "RD16Q_SIGNAL_DOMAIN_EXPANSION_AND_ALTERNATIVE_DATA_RESEARCH_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "SPOT_MARKET_INTERNAL_SIGNAL_DOMAIN_EVIDENCE_EXTRACTED"
NEXT_ASSEMBLY: Final = "RD16R_COMPOSITE_ALPHA_V4_CANDIDATE_ASSEMBLY_AND_INTERACTION_TEST"
NEXT_REFINEMENT: Final = "RD16R_SIGNAL_DOMAIN_REFINEMENT_AND_CAUSAL_STABILITY_RESEARCH"
NEXT_EXPANSION: Final = "RD16R_UNIVERSE_EXPANSION_AND_LIQUIDITY_TIER_RESEARCH"
ALL_DOMAIN_OVERLAY_ID: Final = "ALL_RD16Q_MARKET_INTERNAL_DOMAINS_OVERLAY"

RD16L_ROOT: Final = ROOT / "data" / "research" / "rd16l"
RD16M_ROOT: Final = ROOT / "data" / "research" / "rd16m"
RD16P_ROOT: Final = ROOT / "data" / "research" / "rd16p"
RD16Q_ROOT: Final = ROOT / "data" / "research" / "rd16q"
RD16Q_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16q"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

REGISTRY_FIELDS: Final = (
    "domain_id",
    "hypothesis_id",
    "engine_id",
    "role",
    "information_domain",
    "domain_description",
    "description",
    "stop_atr_multiple",
    "cooldown_hours",
    "engine_priority",
    "normal_holding_bars",
    "strong_bull_holding_bars",
    "fixed_conditions",
    "allowed_regimes",
)

SUMMARY_FIELDS: Final = (
    "domain_id",
    "information_domain",
    "decision",
    "carry_forward",
    "candidate_count",
    "candidate_assets",
    "standalone_trade_count",
    "standalone_net_return",
    "standalone_monthly_geometric_return",
    "standalone_profit_factor",
    "standalone_maximum_drawdown",
    "standalone_two_x_net_return",
    "standalone_two_x_profit_factor",
    "standalone_two_x_capital_feasible",
    "standalone_positive_active_year_fraction",
    "standalone_top_3_trade_profit_share",
    "overlay_new_trade_count",
    "overlay_net_return",
    "overlay_monthly_geometric_return",
    "overlay_profit_factor",
    "overlay_maximum_drawdown",
    "overlay_capital_feasible",
    "overlay_two_x_net_return",
    "overlay_two_x_profit_factor",
    "overlay_two_x_minimum_cash",
    "overlay_two_x_capital_feasible",
    "overlay_mean_high_opportunity_capture",
    "overlay_delta_net_return_vs_v3",
    "overlay_delta_monthly_return_vs_v3",
    "overlay_delta_profit_factor_vs_v3",
    "overlay_delta_maximum_drawdown_vs_v3",
    "overlay_delta_two_x_return_vs_v3",
    "overlay_delta_capture_vs_v3",
    "strategic_objective_met",
    "rationale",
)

DECISION_FIELDS: Final = (
    "domain_id",
    "information_domain",
    "decision",
    "carry_forward",
    "rationale",
    "standalone_net_return",
    "standalone_profit_factor",
    "overlay_delta_net_return_vs_v3",
    "overlay_profit_factor",
    "overlay_two_x_capital_feasible",
    "overlay_delta_capture_vs_v3",
)

COST_FIELDS: Final = (
    "scope",
    "variant_id",
    "cost_multiplier",
    "trade_count",
    "net_return",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
)

COVERAGE_FIELDS: Final = (
    "domain_id",
    "symbol",
    "candidate_count",
    "evaluated_count",
    "standalone_trade_count",
    "overlay_new_trade_count",
    "first_signal_close",
    "last_signal_close",
)

CAUSAL_FIELDS: Final = (
    "domain_id",
    "symbol",
    "candidate_count",
    "next_bar_violations",
    "future_4h_context_violations",
    "future_1d_context_violations",
    "future_1w_context_violations",
    "sealed_cutoff_violations",
)

ROUTING_FIELDS: Final = (
    "scope",
    "variant_id",
    "router_decision",
    "candidate_count",
    "hypothetical_net_pnl",
    "hypothetical_return_on_initial_equity",
    "hypothetical_profit_factor",
)

ANNUAL_FIELDS: Final = (
    "scope",
    "variant_id",
    "period",
    "start_equity",
    "end_equity",
    "return",
    "trade_count",
)

BULL_FIELDS: Final = (
    "scope",
    "variant_id",
    "window_id",
    "start",
    "end",
    "days",
    "portfolio_return",
    "equal_weight_return",
    "capture_ratio",
    "high_opportunity_window",
    "strategic_bull_adequacy",
)

INTERNAL_SUMMARY_FIELDS: Final = (
    "metric",
    "observation_count",
    "minimum",
    "p25",
    "median",
    "mean",
    "p75",
    "maximum",
)

ALL_OVERLAY_FIELDS: Final = (
    "variant_id",
    "new_trade_count",
    "trade_count",
    "net_return",
    "monthly_geometric_return",
    "profit_factor",
    "maximum_drawdown",
    "minimum_cash",
    "capital_feasible",
    "two_x_net_return",
    "two_x_profit_factor",
    "two_x_minimum_cash",
    "two_x_capital_feasible",
    "mean_high_opportunity_capture",
    "delta_net_return_vs_v3",
    "delta_capture_vs_v3",
)

LOCAL_DATASET_KEYS: Final = (
    "candidates",
    "evaluated",
    "standalone_evaluated",
    "standalone_trades",
    "overlay_evaluated",
    "overlay_new_trades",
    "overlay_combined_trades",
)


class RD16QEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DomainDecision:
    decision: str
    carry_forward: bool
    rationale: str
    strategic_objective_met: bool
    gates: dict[str, bool]


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16QEvaluationError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16QEvaluationError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16QEvaluationError(f"{name} must be finite.")
    return numeric


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _metric_profit_factor(metrics: Mapping[str, object]) -> float:
    raw = _optional_float(metrics.get("profit_factor"))
    if raw is not None:
        return raw
    gross_profit = _optional_float(metrics.get("gross_profit")) or 0.0
    gross_loss = _optional_float(metrics.get("gross_loss")) or 0.0
    if gross_profit > 0.0 and gross_loss == 0.0:
        return math.inf
    return 0.0


def _profit_factor_series(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = float(numeric[numeric > 0.0].sum())
    gross_loss = abs(float(numeric[numeric < 0.0].sum()))
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def _optional_delta(value: object, baseline: float) -> float | None:
    numeric = _optional_float(value)
    return numeric - baseline if numeric is not None else None


def _verify_rd16p_ready() -> dict[str, Any]:
    report = read_json_object(RD16P_ROOT / "rd16p-final-report-v1.json")
    expected = {
        "decision": (
            "RD16P_MULTITIMEFRAME_STRUCTURE_AND_CROSS_SECTIONAL_PORTFOLIO_RESEARCH_COMPLETED"
        ),
        "technical_status": "COMPLETED",
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "variants_evaluated": 5,
        "retained_variant_count": 0,
        "promising_variant_count": 0,
        "strategic_objective_met_count": 0,
        "next_stage": ("RD16Q_SIGNAL_DOMAIN_EXPANSION_AND_ALTERNATIVE_DATA_RESEARCH"),
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16QEvaluationError(f"RD16-P readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16QEvaluationError("RD16-P technical gates are missing.")
    for key in (
        "all_input_hashes_verified",
        "cross_sectional_selection_causal",
        "frozen_v3_trades_preserved",
        "maximum_open_risk_preserved",
        "maximum_positions_preserved",
        "notional_only_scaled_down",
        "risk_only_scaled_down",
        "same_symbol_overlap_prohibited",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16QEvaluationError(f"RD16-P technical gate failed: {key}")
    for key in (
        "architecture_changed",
        "dune_api_called",
        "holdout_2026_accessed",
        "optimization_performed",
        "production_authorized",
        "test_2025_accessed",
        "winner_selected",
    ):
        if technical.get(key) is True:
            raise RD16QEvaluationError(f"RD16-P forbidden flag is true: {key}")
    return report


def _verify_rd16p_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16P_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16QEvaluationError("RD16-P output hash manifest is invalid.")
        data_path = RD16P_ROOT / raw_name
        report_path = REPORTS_ROOT / raw_name
        path = data_path if data_path.is_file() else report_path
        if not path.is_file():
            raise RD16QEvaluationError(f"Missing RD16-P output: {raw_name}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16QEvaluationError(f"RD16-P output hash mismatch for {raw_name}.")
        verified[f"rd16p:{raw_name}"] = actual
    return verified


def _baseline_values() -> dict[str, float]:
    report = read_json_object(RD16M_ROOT / "rd16m-final-report-v1.json")
    return {
        "net_return": _finite(
            report["net_return"],
            name="baseline_net_return",
        ),
        "monthly_geometric_return": _finite(
            report["monthly_geometric_return"],
            name="baseline_monthly_return",
        ),
        "profit_factor": _finite(
            report["profit_factor"],
            name="baseline_profit_factor",
        ),
        "maximum_drawdown": _finite(
            report["maximum_drawdown"],
            name="baseline_drawdown",
        ),
        "two_x_net_return": _finite(
            report["two_x_net_return"],
            name="baseline_two_x_return",
        ),
        "two_x_profit_factor": _finite(
            report["two_x_profit_factor"],
            name="baseline_two_x_profit_factor",
        ),
        "mean_high_opportunity_capture": _finite(
            report["mean_high_opportunity_capture"],
            name="baseline_capture",
        ),
    }


def _frozen_input_hashes(
    local_v3_hashes: Mapping[str, str],
) -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16p/rd16p-final-report-v1.json": (RD16P_ROOT / "rd16p-final-report-v1.json"),
        "rd16p/validation-report.json": (RD16P_ROOT / "validation-report.json"),
        "rd16p/output-hashes.json": RD16P_ROOT / "output-hashes.json",
        "rd16p/variant-summary.csv": RD16P_ROOT / "variant-summary.csv",
        "rd16m/rd16m-final-report-v1.json": (RD16M_ROOT / "rd16m-final-report-v1.json"),
        "rd16l/local-ledger-manifest-v1.json": (RD16L_ROOT / "local-ledger-manifest-v1.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16QEvaluationError(f"Frozen RD16-Q input is missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16p_outputs())
    hashes.update(local_v3_hashes)
    hashes.update(verify_local_dataset_hashes(LOCAL_INPUT_ROOT))
    return dict(sorted(hashes.items()))


def classify_domain(
    *,
    domain: SignalDomain,
    candidate_count: int,
    standalone: rd16n.PortfolioEvidence,
    overlay: rd16n.PortfolioEvidence,
    baseline: Mapping[str, float],
) -> DomainDecision:
    standalone_1x = standalone.metrics[1.0]
    standalone_2x = standalone.metrics[2.0]
    overlay_1x = overlay.metrics[1.0]
    overlay_2x = overlay.metrics[2.0]

    standalone_return = _finite(
        standalone_1x["net_return"],
        name="standalone_return",
    )
    standalone_pf = _metric_profit_factor(standalone_1x)
    standalone_drawdown = _finite(
        standalone_1x["maximum_drawdown"],
        name="standalone_drawdown",
    )
    standalone_2x_return = _finite(
        standalone_2x["net_return"],
        name="standalone_two_x_return",
    )
    overlay_return = _finite(
        overlay_1x["net_return"],
        name="overlay_return",
    )
    overlay_monthly = _optional_float(overlay_1x["monthly_geometric_return"])
    overlay_pf = _metric_profit_factor(overlay_1x)
    overlay_drawdown = _finite(
        overlay_1x["maximum_drawdown"],
        name="overlay_drawdown",
    )
    overlay_2x_return = _finite(
        overlay_2x["net_return"],
        name="overlay_two_x_return",
    )
    delta_return = overlay_return - baseline["net_return"]
    delta_capture = (
        overlay.mean_high_opportunity_capture - baseline["mean_high_opportunity_capture"]
    )
    top_three = _optional_float(standalone.concentration.get("top_3_trade_profit_share"))

    gates = {
        "candidate_count_between_24_and_600": (24 <= candidate_count <= 600),
        "standalone_trade_count_gte_24": (int(cast(int, standalone_1x["trade_count"])) >= 24),
        "standalone_net_return_positive": standalone_return > 0.0,
        "standalone_profit_factor_gte_1_15": standalone_pf >= 1.15,
        "standalone_drawdown_lte_30pct": standalone_drawdown <= 0.30,
        "standalone_two_x_positive": standalone_2x_return > 0.0,
        "standalone_two_x_profit_factor_gte_1": (_metric_profit_factor(standalone_2x) >= 1.0),
        "standalone_two_x_capital_feasible": bool(standalone_2x["capital_feasible"]),
        "standalone_positive_active_year_fraction_gte_50pct": (
            standalone.positive_active_year_fraction >= 0.50
        ),
        "standalone_top_3_profit_share_lte_35pct": (top_three is not None and top_three <= 0.35),
        "overlay_delta_net_return_gte_2pp": delta_return >= 0.02,
        "overlay_profit_factor_preserved": (overlay_pf >= baseline["profit_factor"] - 0.05),
        "overlay_drawdown_not_worse_by_more_than_3pp": (
            overlay_drawdown <= baseline["maximum_drawdown"] + 0.03
        ),
        "overlay_capital_feasible": bool(overlay_1x["capital_feasible"]),
        "overlay_two_x_capital_feasible": bool(overlay_2x["capital_feasible"]),
        "overlay_two_x_return_not_below_v3": (overlay_2x_return >= baseline["two_x_net_return"]),
        "overlay_capture_not_worse_by_more_than_0_5pp": (delta_capture >= -0.005),
    }
    robust = all(gates.values())
    promising = (
        candidate_count >= 12
        and standalone_return > 0.0
        and standalone_pf >= 1.0
        and delta_return > 0.0
        and bool(overlay_1x["capital_feasible"])
        and bool(overlay_2x["capital_feasible"])
    )
    strategic = (
        robust and overlay_monthly is not None and overlay_monthly >= STRATEGIC_MONTHLY_TARGET
    )

    if robust:
        decision = "RETAIN_FOR_COMPOSITE_ALPHA_V4_ASSEMBLY"
        carry_forward = True
        rationale = (
            "Passes fixed market-internal domain, standalone, overlay, "
            "cost, capital, concentration, and capture gates."
        )
    elif promising:
        decision = "PROMISING_MARKET_INTERNAL_SIGNAL_DOMAIN"
        carry_forward = False
        failed = [key for key, passed in gates.items() if not passed]
        rationale = (
            "Positive standalone and additive overlay evidence, but fixed "
            f"retention gates failed: {', '.join(failed)}."
        )
    else:
        decision = "REJECT_MARKET_INTERNAL_SIGNAL_DOMAIN"
        carry_forward = False
        failed = [key for key, passed in gates.items() if not passed]
        rationale = (
            f"Insufficient market-internal signal evidence; failed gates: {', '.join(failed)}."
        )
    return DomainDecision(
        decision=decision,
        carry_forward=carry_forward,
        rationale=rationale,
        strategic_objective_met=strategic,
        gates=gates,
    )


def _cost_rows(
    evidence: rd16n.PortfolioEvidence,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for multiplier in COST_MULTIPLIERS:
        metrics = evidence.metrics[multiplier]
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "cost_multiplier": multiplier,
                "trade_count": metrics["trade_count"],
                "net_return": metrics["net_return"],
                "monthly_geometric_return": (metrics["monthly_geometric_return"]),
                "maximum_drawdown": metrics["maximum_drawdown"],
                "profit_factor": metrics["profit_factor"],
                "minimum_cash": metrics["minimum_cash"],
                "minimum_equity": metrics["minimum_equity"],
                "capital_feasible": metrics["capital_feasible"],
            }
        )
    return rows


def _routing_rows(
    frame: pd.DataFrame,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if frame.empty or "router_decision" not in frame.columns:
        return rows
    for decision, group in frame.groupby("router_decision", sort=True):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "router_decision": str(decision),
                "candidate_count": len(group),
                "hypothetical_net_pnl": float(pnl.sum()),
                "hypothetical_return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "hypothetical_profit_factor": _profit_factor_series(pnl),
            }
        )
    return rows


def _symbol_values(frame: pd.DataFrame) -> list[str]:
    if "symbol" not in frame.columns:
        return []
    return frame["symbol"].astype(str).tolist()


def _symbol_count(frame: pd.DataFrame, symbol: str) -> int:
    if "symbol" not in frame.columns:
        return 0
    return int((frame["symbol"].astype(str) == symbol).sum())


def _coverage_rows(
    *,
    domain_id: str,
    candidates: pd.DataFrame,
    evaluated: pd.DataFrame,
    standalone: pd.DataFrame,
    overlay_new: pd.DataFrame,
) -> list[dict[str, object]]:
    symbols = sorted(
        {
            *_symbol_values(candidates),
            *_symbol_values(evaluated),
        }
    )
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        candidate_group = candidates[candidates["symbol"].astype(str) == symbol]
        signals = pd.to_datetime(
            candidate_group["signal_close"],
            utc=True,
            errors="coerce",
        )
        rows.append(
            {
                "domain_id": domain_id,
                "symbol": symbol,
                "candidate_count": len(candidate_group),
                "evaluated_count": _symbol_count(evaluated, symbol),
                "standalone_trade_count": _symbol_count(
                    standalone,
                    symbol,
                ),
                "overlay_new_trade_count": _symbol_count(
                    overlay_new,
                    symbol,
                ),
                "first_signal_close": (
                    signals.min().isoformat() if bool(signals.notna().any()) else ""
                ),
                "last_signal_close": (
                    signals.max().isoformat() if bool(signals.notna().any()) else ""
                ),
            }
        )
    return rows


def _causality_rows(
    candidates: pd.DataFrame,
    *,
    domain_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if candidates.empty:
        return rows
    for symbol, group in candidates.groupby("symbol", sort=True):
        signal = pd.to_datetime(
            group["signal_close"],
            utc=True,
            errors="raise",
        )
        entry_close = pd.to_datetime(
            group["entry_bar_close"],
            utc=True,
            errors="raise",
        )
        four_hour = pd.to_datetime(
            group["4h_context_close"],
            utc=True,
            errors="raise",
        )
        daily = pd.to_datetime(
            group["1d_context_close"],
            utc=True,
            errors="raise",
        )
        weekly = pd.to_datetime(
            group["1w_context_close"],
            utc=True,
            errors="raise",
        )
        rows.append(
            {
                "domain_id": domain_id,
                "symbol": str(symbol),
                "candidate_count": len(group),
                "next_bar_violations": int((entry_close - signal != pd.Timedelta(hours=1)).sum()),
                "future_4h_context_violations": int((four_hour > signal).sum()),
                "future_1d_context_violations": int((daily > signal).sum()),
                "future_1w_context_violations": int((weekly > signal).sum()),
                "sealed_cutoff_violations": int((signal >= SEALED_CUTOFF).sum()),
            }
        )
    return rows


def _annual_rows(
    evidence: rd16n.PortfolioEvidence,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in evidence.annual_rows:
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "period": raw["period"],
                "start_equity": raw["start_equity"],
                "end_equity": raw["end_equity"],
                "return": raw["return"],
                "trade_count": raw["trade_count"],
            }
        )
    return rows


def _bull_rows(
    evidence: rd16n.PortfolioEvidence,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw in evidence.bull_rows:
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "window_id": raw["window_id"],
                "start": raw["start"],
                "end": raw["end"],
                "days": raw["days"],
                "portfolio_return": raw["family_return"],
                "equal_weight_return": raw["equal_weight_return"],
                "capture_ratio": raw["capture_ratio"],
                "high_opportunity_window": (raw["high_opportunity_window"]),
                "strategic_bull_adequacy": (raw["strategic_bull_adequacy"]),
            }
        )
    return rows


def _internal_summary_rows(
    frames: Mapping[str, pd.DataFrame],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if not frames:
        return rows
    combined = pd.concat(
        [frame.loc[:, list(INTERNAL_COLUMNS)].copy() for frame in frames.values()],
        ignore_index=True,
        sort=False,
    )
    for metric in INTERNAL_COLUMNS:
        values = (
            pd.to_numeric(
                combined[metric],
                errors="coerce",
            )
            .replace([math.inf, -math.inf], float("nan"))
            .dropna()
        )
        rows.append(
            {
                "metric": metric,
                "observation_count": len(values),
                "minimum": float(values.min()) if len(values) else None,
                "p25": (float(values.quantile(0.25)) if len(values) else None),
                "median": (float(values.median()) if len(values) else None),
                "mean": float(values.mean()) if len(values) else None,
                "p75": (float(values.quantile(0.75)) if len(values) else None),
                "maximum": float(values.max()) if len(values) else None,
            }
        )
    return rows


def _write_local_frame(
    path: Path,
    frame: pd.DataFrame,
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return {
        "logical_path": path.relative_to(RD16Q_LOCAL_ROOT).as_posix(),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _output_hashes(paths: Sequence[Path]) -> dict[str, str]:
    return {path.name: sha256_path(path) for path in paths}


def _validation_payload(
    *,
    summary_row_count: int,
    deterministic_replay_match: bool,
    causal_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    causal_pass = all(
        int(cast(int, row[field])) == 0
        for row in causal_rows
        for field in (
            "next_bar_violations",
            "future_4h_context_violations",
            "future_1d_context_violations",
            "future_1w_context_violations",
            "sealed_cutoff_violations",
        )
    )
    return {
        "technical_status": "PASS",
        "domain_count": len(DOMAIN_REGISTRY),
        "summary_row_count": summary_row_count,
        "all_domains_classified": (summary_row_count == len(DOMAIN_REGISTRY)),
        "deterministic_replay_match": deterministic_replay_match,
        "causality_audit_pass": causal_pass,
        "sealed_cutoff": SEALED_CUTOFF.isoformat(),
        "spot_only": True,
        "long_only": True,
        "external_alternative_data_used": False,
        "derivatives_data_used": False,
        "dune_api_called": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
    }


def _write_reports(
    *,
    final_report: Mapping[str, object],
    summary_rows: Sequence[Mapping[str, object]],
    all_overlay: Mapping[str, object],
) -> list[Path]:
    results_path = REPORTS_ROOT / "rd16q-signal-domain-expansion-results-v1.md"
    decisions_path = REPORTS_ROOT / "rd16q-signal-domain-carry-forward-decisions-v1.md"
    audit_path = REPORTS_ROOT / "rd16q-market-internals-causality-audit-v1.md"

    results_lines = [
        "# RD16-Q Signal-Domain Expansion Results",
        "",
        f"- Decision: `{final_report['decision']}`",
        f"- Domains evaluated: {final_report['domains_evaluated']}",
        f"- Retained domains: {final_report['retained_domains']}",
        f"- Promising domains: {final_report['promising_domains']}",
        (
            "- All-domain overlay return / PF: "
            f"{_finite(all_overlay['net_return'], name='return'):.2%}"
            " / "
            f"{(_optional_float(all_overlay['profit_factor']) or 0.0):.3f}"
        ),
        "",
        f"Next: `{final_report['next_stage']}`",
        "",
    ]
    results_path.write_text(
        "\n".join(results_lines),
        encoding="utf-8",
        newline="\n",
    )

    decision_lines = [
        "# RD16-Q Signal-Domain Carry-Forward Decisions",
        "",
    ]
    for row in summary_rows:
        decision_lines.extend(
            [
                f"## {row['domain_id']}",
                "",
                f"- Information domain: `{row['information_domain']}`",
                f"- Decision: `{row['decision']}`",
                f"- Carry forward: `{row['carry_forward']}`",
                f"- Rationale: {row['rationale']}",
                (
                    "- Standalone return / PF: "
                    f"{_finite(row['standalone_net_return'], name='ret'):.2%}"
                    " / "
                    f"{(_optional_float(row['standalone_profit_factor']) or 0.0):.3f}"
                ),
                (
                    "- Overlay delta return / capture: "
                    f"{_finite(row['overlay_delta_net_return_vs_v3'], name='delta'):.2%}"
                    " / "
                    f"{_finite(row['overlay_delta_capture_vs_v3'], name='capture'):.2%}"
                ),
                "",
            ]
        )
    decisions_path.write_text(
        "\n".join(decision_lines),
        encoding="utf-8",
        newline="\n",
    )

    audit_lines = [
        "# RD16-Q Market-Internals and Causality Audit",
        "",
        "- Inputs are frozen KuCoin Spot OHLCV for the six pilot pairs.",
        "- Market internals are derived only from completed Spot bars.",
        "- No derivatives, borrowing, leverage, margin, or short selling.",
        "- No external alternative-data provider or Dune API was used.",
        "- Cross-sectional ranks use same-close completed observations.",
        "- Rolling thresholds use causal historical windows.",
        "- Entries occur at the next hourly bar open.",
        "- Frozen V3 trades are never displaced.",
        "- Same-symbol overlap and fixed capacity limits remain enforced.",
        "- 2025 and 2026 remain sealed.",
        "",
    ]
    audit_path.write_text(
        "\n".join(audit_lines),
        encoding="utf-8",
        newline="\n",
    )
    return [results_path, decisions_path, audit_path]


def run_rd16q_research() -> dict[str, object]:
    source_report = _verify_rd16p_ready()
    v3_ledgers, local_v3_hashes = rd16n._load_v3_ledgers()
    baseline_trades = v3_ledgers["trades"].copy()
    baseline = _baseline_values()
    frozen_hashes = _frozen_input_hashes(local_v3_hashes)

    all_market, hourly_frames, daily_frames = rd16n._load_market_frames()
    base_features = {
        symbol: build_feature_frame(frames, symbol=symbol) for symbol, frames in all_market.items()
    }
    internal_frames = build_market_internal_feature_frames(base_features)
    timeline = rd16n._timeline(hourly_frames)
    bar_positions = rd16n._bar_position_maps(hourly_frames)
    benchmark = build_benchmark_daily(daily_frames)

    if RD16Q_LOCAL_ROOT.exists():
        shutil.rmtree(RD16Q_LOCAL_ROOT)
    RD16Q_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    RD16Q_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    causal_rows: list[dict[str, object]] = []
    routing_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    bull_rows: list[dict[str, object]] = []
    retained: list[str] = []
    promising: list[str] = []
    rejected: list[str] = []
    strategic_count = 0
    deterministic_replay_match = True

    local_manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "domains": {},
        "combined": {},
    }
    domain_manifest = cast(
        dict[str, object],
        local_manifest["domains"],
    )

    all_evaluated_frames: list[pd.DataFrame] = []

    for domain in DOMAIN_REGISTRY:
        candidates = build_domain_candidates(
            internal_frames,
            domain=domain,
        )
        replay = build_domain_candidates(
            internal_frames,
            domain=domain,
        )
        if dataframe_content_hash(candidates) != dataframe_content_hash(replay):
            deterministic_replay_match = False

        evaluated = rd16n.evaluate_candidates(
            candidates,
            hourly_frames=hourly_frames,
            bar_positions=bar_positions,
        )
        standalone_evaluated, standalone_trades = rd16n.route_standalone_candidates(
            evaluated,
            hypothesis=domain.hypothesis,
        )
        overlay_evaluated, overlay_new = rd16n.route_overlay_candidates(
            baseline_trades,
            evaluated,
            variant_id=domain.domain_id,
        )

        standalone_enriched = (
            enrich_trades(
                standalone_trades,
                hourly_frames=hourly_frames,
                feature_frames=base_features,
            )
            if not standalone_trades.empty
            else rd16n._empty_enriched_frame(standalone_trades)
        )
        overlay_new_enriched = (
            enrich_trades(
                overlay_new,
                hourly_frames=hourly_frames,
                feature_frames=base_features,
            )
            if not overlay_new.empty
            else rd16n._empty_enriched_frame(overlay_new)
        )
        overlay_combined = (
            pd.concat(
                [baseline_trades, overlay_new_enriched],
                ignore_index=True,
                sort=False,
            )
            .sort_values(
                by=[
                    "entry_open_time",
                    "symbol",
                    "signal_close",
                    "trade_id",
                ],
                kind="stable",
            )
            .reset_index(drop=True)
        )

        standalone_evidence = rd16n._evaluate_portfolio(
            standalone_enriched,
            variant_id=(f"RD16Q-STANDALONE::{domain.domain_id}"),
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        overlay_evidence = rd16n._evaluate_portfolio(
            overlay_combined,
            variant_id=f"RD16Q-OVERLAY::{domain.domain_id}",
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        decision = classify_domain(
            domain=domain,
            candidate_count=len(candidates),
            standalone=standalone_evidence,
            overlay=overlay_evidence,
            baseline=baseline,
        )

        if decision.carry_forward:
            retained.append(domain.domain_id)
        elif decision.decision == "PROMISING_MARKET_INTERNAL_SIGNAL_DOMAIN":
            promising.append(domain.domain_id)
        else:
            rejected.append(domain.domain_id)
        if decision.strategic_objective_met:
            strategic_count += 1

        standalone_1x = standalone_evidence.metrics[1.0]
        standalone_2x = standalone_evidence.metrics[2.0]
        overlay_1x = overlay_evidence.metrics[1.0]
        overlay_2x = overlay_evidence.metrics[2.0]
        top_three = _optional_float(
            standalone_evidence.concentration.get("top_3_trade_profit_share")
        )
        summary_row = {
            "domain_id": domain.domain_id,
            "information_domain": domain.information_domain,
            "decision": decision.decision,
            "carry_forward": decision.carry_forward,
            "candidate_count": len(candidates),
            "candidate_assets": (
                int(candidates["symbol"].nunique()) if not candidates.empty else 0
            ),
            "standalone_trade_count": standalone_1x["trade_count"],
            "standalone_net_return": standalone_1x["net_return"],
            "standalone_monthly_geometric_return": (standalone_1x["monthly_geometric_return"]),
            "standalone_profit_factor": (standalone_1x["profit_factor"]),
            "standalone_maximum_drawdown": (standalone_1x["maximum_drawdown"]),
            "standalone_two_x_net_return": (standalone_2x["net_return"]),
            "standalone_two_x_profit_factor": (standalone_2x["profit_factor"]),
            "standalone_two_x_capital_feasible": (standalone_2x["capital_feasible"]),
            "standalone_positive_active_year_fraction": (
                standalone_evidence.positive_active_year_fraction
            ),
            "standalone_top_3_trade_profit_share": top_three,
            "overlay_new_trade_count": len(overlay_new_enriched),
            "overlay_net_return": overlay_1x["net_return"],
            "overlay_monthly_geometric_return": (overlay_1x["monthly_geometric_return"]),
            "overlay_profit_factor": overlay_1x["profit_factor"],
            "overlay_maximum_drawdown": (overlay_1x["maximum_drawdown"]),
            "overlay_capital_feasible": (overlay_1x["capital_feasible"]),
            "overlay_two_x_net_return": overlay_2x["net_return"],
            "overlay_two_x_profit_factor": (overlay_2x["profit_factor"]),
            "overlay_two_x_minimum_cash": (overlay_2x["minimum_cash"]),
            "overlay_two_x_capital_feasible": (overlay_2x["capital_feasible"]),
            "overlay_mean_high_opportunity_capture": (
                overlay_evidence.mean_high_opportunity_capture
            ),
            "overlay_delta_net_return_vs_v3": (
                _finite(
                    overlay_1x["net_return"],
                    name="overlay_return",
                )
                - baseline["net_return"]
            ),
            "overlay_delta_monthly_return_vs_v3": _optional_delta(
                overlay_1x["monthly_geometric_return"],
                baseline["monthly_geometric_return"],
            ),
            "overlay_delta_profit_factor_vs_v3": (
                _metric_profit_factor(overlay_1x) - baseline["profit_factor"]
            ),
            "overlay_delta_maximum_drawdown_vs_v3": (
                _finite(
                    overlay_1x["maximum_drawdown"],
                    name="overlay_drawdown",
                )
                - baseline["maximum_drawdown"]
            ),
            "overlay_delta_two_x_return_vs_v3": (
                _finite(
                    overlay_2x["net_return"],
                    name="overlay_two_x_return",
                )
                - baseline["two_x_net_return"]
            ),
            "overlay_delta_capture_vs_v3": (
                overlay_evidence.mean_high_opportunity_capture
                - baseline["mean_high_opportunity_capture"]
            ),
            "strategic_objective_met": (decision.strategic_objective_met),
            "rationale": decision.rationale,
        }
        summary_rows.append(summary_row)
        decision_rows.append(
            {
                "domain_id": domain.domain_id,
                "information_domain": domain.information_domain,
                "decision": decision.decision,
                "carry_forward": decision.carry_forward,
                "rationale": decision.rationale,
                "standalone_net_return": (standalone_1x["net_return"]),
                "standalone_profit_factor": (standalone_1x["profit_factor"]),
                "overlay_delta_net_return_vs_v3": (summary_row["overlay_delta_net_return_vs_v3"]),
                "overlay_profit_factor": overlay_1x["profit_factor"],
                "overlay_two_x_capital_feasible": (overlay_2x["capital_feasible"]),
                "overlay_delta_capture_vs_v3": (summary_row["overlay_delta_capture_vs_v3"]),
            }
        )
        cost_rows.extend(
            _cost_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=domain.domain_id,
            )
        )
        cost_rows.extend(
            _cost_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=domain.domain_id,
            )
        )
        coverage_rows.extend(
            _coverage_rows(
                domain_id=domain.domain_id,
                candidates=candidates,
                evaluated=evaluated,
                standalone=standalone_enriched,
                overlay_new=overlay_new_enriched,
            )
        )
        causal_rows.extend(
            _causality_rows(
                candidates,
                domain_id=domain.domain_id,
            )
        )
        routing_rows.extend(
            _routing_rows(
                standalone_evaluated,
                scope="STANDALONE",
                variant_id=domain.domain_id,
            )
        )
        routing_rows.extend(
            _routing_rows(
                overlay_evaluated,
                scope="OVERLAY",
                variant_id=domain.domain_id,
            )
        )
        annual_rows.extend(
            _annual_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=domain.domain_id,
            )
        )
        annual_rows.extend(
            _annual_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=domain.domain_id,
            )
        )
        bull_rows.extend(
            _bull_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=domain.domain_id,
            )
        )
        bull_rows.extend(
            _bull_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=domain.domain_id,
            )
        )

        domain_root = RD16Q_LOCAL_ROOT / domain.domain_id
        local_entries = {
            "candidates": _write_local_frame(
                domain_root / "candidates.parquet",
                candidates,
            ),
            "evaluated": _write_local_frame(
                domain_root / "evaluated.parquet",
                evaluated,
            ),
            "standalone_evaluated": _write_local_frame(
                domain_root / "standalone-evaluated.parquet",
                standalone_evaluated,
            ),
            "standalone_trades": _write_local_frame(
                domain_root / "standalone-trades.parquet",
                standalone_enriched,
            ),
            "overlay_evaluated": _write_local_frame(
                domain_root / "overlay-evaluated.parquet",
                overlay_evaluated,
            ),
            "overlay_new_trades": _write_local_frame(
                domain_root / "overlay-new-trades.parquet",
                overlay_new_enriched,
            ),
            "overlay_combined_trades": _write_local_frame(
                domain_root / "overlay-combined-trades.parquet",
                overlay_combined,
            ),
        }
        if set(local_entries) != set(LOCAL_DATASET_KEYS):
            raise RD16QEvaluationError(f"Local ledger keys mismatch for {domain.domain_id}.")
        domain_manifest[domain.domain_id] = local_entries
        all_evaluated_frames.append(evaluated)

    combined_evaluated = (
        pd.concat(
            all_evaluated_frames,
            ignore_index=True,
            sort=False,
        )
        .sort_values(
            by=[
                "entry_open_time",
                "engine_priority",
                "symbol",
                "signal_close",
                "candidate_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
        if all_evaluated_frames
        else pd.DataFrame()
    )
    combined_routing, combined_new = rd16n.route_overlay_candidates(
        baseline_trades,
        combined_evaluated,
        variant_id=ALL_DOMAIN_OVERLAY_ID,
    )
    combined_new_enriched = (
        enrich_trades(
            combined_new,
            hourly_frames=hourly_frames,
            feature_frames=base_features,
        )
        if not combined_new.empty
        else rd16n._empty_enriched_frame(combined_new)
    )
    combined_trades = (
        pd.concat(
            [baseline_trades, combined_new_enriched],
            ignore_index=True,
            sort=False,
        )
        .sort_values(
            by=[
                "entry_open_time",
                "symbol",
                "signal_close",
                "trade_id",
            ],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    combined_evidence = rd16n._evaluate_portfolio(
        combined_trades,
        variant_id=ALL_DOMAIN_OVERLAY_ID,
        hourly_frames=hourly_frames,
        timeline=timeline,
        benchmark=benchmark,
    )
    combined_1x = combined_evidence.metrics[1.0]
    combined_2x = combined_evidence.metrics[2.0]
    all_overlay = {
        "variant_id": ALL_DOMAIN_OVERLAY_ID,
        "new_trade_count": len(combined_new_enriched),
        "trade_count": combined_1x["trade_count"],
        "net_return": combined_1x["net_return"],
        "monthly_geometric_return": (combined_1x["monthly_geometric_return"]),
        "profit_factor": combined_1x["profit_factor"],
        "maximum_drawdown": combined_1x["maximum_drawdown"],
        "minimum_cash": combined_1x["minimum_cash"],
        "capital_feasible": combined_1x["capital_feasible"],
        "two_x_net_return": combined_2x["net_return"],
        "two_x_profit_factor": combined_2x["profit_factor"],
        "two_x_minimum_cash": combined_2x["minimum_cash"],
        "two_x_capital_feasible": (combined_2x["capital_feasible"]),
        "mean_high_opportunity_capture": (combined_evidence.mean_high_opportunity_capture),
        "delta_net_return_vs_v3": (
            _finite(
                combined_1x["net_return"],
                name="combined_return",
            )
            - baseline["net_return"]
        ),
        "delta_capture_vs_v3": (
            combined_evidence.mean_high_opportunity_capture
            - baseline["mean_high_opportunity_capture"]
        ),
    }
    cost_rows.extend(
        _cost_rows(
            combined_evidence,
            scope="OVERLAY",
            variant_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    routing_rows.extend(
        _routing_rows(
            combined_routing,
            scope="OVERLAY",
            variant_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    annual_rows.extend(
        _annual_rows(
            combined_evidence,
            scope="OVERLAY",
            variant_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    bull_rows.extend(
        _bull_rows(
            combined_evidence,
            scope="OVERLAY",
            variant_id=ALL_DOMAIN_OVERLAY_ID,
        )
    )
    combined_manifest = cast(
        dict[str, object],
        local_manifest["combined"],
    )
    combined_manifest.update(
        {
            "evaluated": _write_local_frame(
                RD16Q_LOCAL_ROOT / "combined" / "evaluated.parquet",
                combined_evaluated,
            ),
            "overlay_evaluated": _write_local_frame(
                RD16Q_LOCAL_ROOT / "combined" / "overlay-evaluated.parquet",
                combined_routing,
            ),
            "overlay_new_trades": _write_local_frame(
                RD16Q_LOCAL_ROOT / "combined" / "overlay-new-trades.parquet",
                combined_new_enriched,
            ),
            "overlay_combined_trades": _write_local_frame(
                RD16Q_LOCAL_ROOT / "combined" / "overlay-combined-trades.parquet",
                combined_trades,
            ),
        }
    )

    if retained:
        next_stage = NEXT_ASSEMBLY
    elif promising:
        next_stage = NEXT_REFINEMENT
    else:
        next_stage = NEXT_EXPANSION

    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "branch": BRANCH,
        "architecture_id": "COMPOSITE_ALPHA_V3",
        "source_stage_decision": source_report["decision"],
        "domains_evaluated": len(DOMAIN_REGISTRY),
        "retained_domain_count": len(retained),
        "retained_domains": retained,
        "promising_domain_count": len(promising),
        "promising_domains": promising,
        "rejected_domain_count": len(rejected),
        "rejected_domains": rejected,
        "strategic_objective_met_count": strategic_count,
        "strategic_objective_met": strategic_count > 0,
        "pre_registered_all_domain_overlay": all_overlay,
        "next_stage": next_stage,
        "technical_gates": {
            "all_input_hashes_verified": True,
            "raw_market_data_verified": True,
            "rd16l_local_ledgers_verified": True,
            "rd16p_outputs_verified": True,
            "deterministic_replay_match": (deterministic_replay_match),
            "all_causality_checks_pass": all(
                int(cast(int, row[field])) == 0
                for row in causal_rows
                for field in (
                    "next_bar_violations",
                    "future_4h_context_violations",
                    "future_1d_context_violations",
                    "future_1w_context_violations",
                    "sealed_cutoff_violations",
                )
            ),
            "frozen_v3_trades_preserved": True,
            "same_symbol_overlap_prohibited": True,
            "maximum_positions_preserved": True,
            "maximum_open_risk_preserved": True,
            "spot_only": True,
            "long_only": True,
            "external_alternative_data_used": False,
            "derivatives_data_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
            "architecture_changed": False,
        },
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "architecture_changed": False,
    }

    registry_path = RD16Q_ROOT / "domain-registry.csv"
    summary_path = RD16Q_ROOT / "domain-summary.csv"
    decisions_path = RD16Q_ROOT / "component-decisions.csv"
    cost_path = RD16Q_ROOT / "cost-stress.csv"
    coverage_path = RD16Q_ROOT / "domain-coverage.csv"
    causal_path = RD16Q_ROOT / "causality-audit.csv"
    routing_path = RD16Q_ROOT / "routing-summary.csv"
    annual_path = RD16Q_ROOT / "annual-performance.csv"
    bull_path = RD16Q_ROOT / "bull-window-capture.csv"
    internal_path = RD16Q_ROOT / "market-internals-summary.csv"
    all_overlay_path = RD16Q_ROOT / "all-domain-overlay-summary.csv"
    frozen_path = RD16Q_ROOT / "frozen-input-hashes.json"
    local_manifest_path = RD16Q_ROOT / "local-output-manifest-v1.json"
    validation_path = RD16Q_ROOT / "validation-report.json"
    final_path = RD16Q_ROOT / "rd16q-final-report-v1.json"
    output_hash_path = RD16Q_ROOT / "output-hashes.json"

    write_csv(
        registry_path,
        domain_registry_rows(),
        fieldnames=REGISTRY_FIELDS,
    )
    write_csv(
        summary_path,
        summary_rows,
        fieldnames=SUMMARY_FIELDS,
    )
    write_csv(
        decisions_path,
        decision_rows,
        fieldnames=DECISION_FIELDS,
    )
    write_csv(cost_path, cost_rows, fieldnames=COST_FIELDS)
    write_csv(
        coverage_path,
        coverage_rows,
        fieldnames=COVERAGE_FIELDS,
    )
    write_csv(
        causal_path,
        causal_rows,
        fieldnames=CAUSAL_FIELDS,
    )
    write_csv(
        routing_path,
        routing_rows,
        fieldnames=ROUTING_FIELDS,
    )
    write_csv(
        annual_path,
        annual_rows,
        fieldnames=ANNUAL_FIELDS,
    )
    write_csv(bull_path, bull_rows, fieldnames=BULL_FIELDS)
    write_csv(
        internal_path,
        _internal_summary_rows(internal_frames),
        fieldnames=INTERNAL_SUMMARY_FIELDS,
    )
    write_csv(
        all_overlay_path,
        [all_overlay],
        fieldnames=ALL_OVERLAY_FIELDS,
    )
    write_json(frozen_path, frozen_hashes)
    write_json(local_manifest_path, local_manifest)
    validation = _validation_payload(
        summary_row_count=len(summary_rows),
        deterministic_replay_match=deterministic_replay_match,
        causal_rows=causal_rows,
    )
    write_json(validation_path, validation)
    write_json(final_path, final_report)

    report_paths = _write_reports(
        final_report=final_report,
        summary_rows=summary_rows,
        all_overlay=all_overlay,
    )
    output_paths = [
        registry_path,
        summary_path,
        decisions_path,
        cost_path,
        coverage_path,
        causal_path,
        routing_path,
        annual_path,
        bull_path,
        internal_path,
        all_overlay_path,
        frozen_path,
        local_manifest_path,
        validation_path,
        final_path,
        *report_paths,
    ]
    write_json(output_hash_path, _output_hashes(output_paths))
    frozen_after = _frozen_input_hashes(local_v3_hashes)
    if frozen_after != frozen_hashes:
        raise RD16QEvaluationError("Frozen RD16-Q inputs changed during evaluation.")
    if not deterministic_replay_match:
        raise RD16QEvaluationError("RD16-Q deterministic replay mismatch.")
    if validation["causality_audit_pass"] is not True:
        raise RD16QEvaluationError("RD16-Q causality audit failed.")
    return final_report


__all__ = [
    "ALL_DOMAIN_OVERLAY_ID",
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "RD16QEvaluationError",
    "SCHEMA_VERSION",
    "DomainDecision",
    "_validation_payload",
    "classify_domain",
    "run_rd16q_research",
]
