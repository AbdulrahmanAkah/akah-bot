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
from spotbot.research.rd16l_architecture import (
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
)
from spotbot.research.rd16n_signals import SignalHypothesis
from spotbot.research.rd16o_signals import (
    ARCHITECTURE_ID,
    HYPOTHESIS_REGISTRY,
    build_second_gen_candidates,
    build_second_gen_feature_frames,
)

SCHEMA_VERSION: Final = "rd16o-intraday-alpha-engine-redesign-v1"
DECISION: Final = (
    "RD16O_INTRADAY_ALPHA_ENGINE_REDESIGN_AND_SECOND_GENERATION_SIGNAL_RESEARCH_COMPLETED"
)
EVIDENCE_CLASSIFICATION: Final = "SECOND_GENERATION_INTRADAY_ALPHA_EVIDENCE_EXTRACTED"
NEXT_ASSEMBLY: Final = "RD16P_COMPOSITE_ALPHA_V4_CANDIDATE_ASSEMBLY_AND_INTERACTION_TEST"
NEXT_REFINEMENT: Final = "RD16P_TARGETED_SECOND_GENERATION_ALPHA_REFINEMENT"
NEXT_REDESIGN: Final = "RD16P_MULTITIMEFRAME_STRUCTURE_AND_CROSS_SECTIONAL_PORTFOLIO_RESEARCH"
NEXT_PREHOLDOUT: Final = "RD16P_COMPOSITE_ALPHA_V4_PREHOLDOUT_FREEZE_AND_VALIDATION"
ALL_SECOND_GEN_VARIANT_ID: Final = "ALL_SECOND_GENERATION_ENGINES_OVERLAY"

RD16L_ROOT: Final = ROOT / "data" / "research" / "rd16l"
RD16M_ROOT: Final = ROOT / "data" / "research" / "rd16m"
RD16N_ROOT: Final = ROOT / "data" / "research" / "rd16n"
RD16O_ROOT: Final = ROOT / "data" / "research" / "rd16o"
RD16O_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16o"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

FAMILY_FIELDS: Final = (
    "hypothesis_id",
    "engine_id",
    "role",
    "decision",
    "carry_forward",
    "candidate_count",
    "candidate_assets",
    "standalone_trade_count",
    "standalone_traded_assets",
    "standalone_net_return",
    "standalone_monthly_geometric_return",
    "standalone_profit_factor",
    "standalone_maximum_drawdown",
    "standalone_two_x_net_return",
    "standalone_two_x_profit_factor",
    "standalone_two_x_capital_feasible",
    "standalone_positive_active_year_fraction",
    "overlay_new_trade_count",
    "overlay_net_return",
    "overlay_monthly_geometric_return",
    "overlay_profit_factor",
    "overlay_maximum_drawdown",
    "overlay_two_x_net_return",
    "overlay_two_x_profit_factor",
    "overlay_two_x_capital_feasible",
    "overlay_mean_high_opportunity_capture",
    "overlay_delta_net_return_vs_v3",
    "overlay_delta_monthly_return_vs_v3",
    "overlay_delta_profit_factor_vs_v3",
    "overlay_delta_maximum_drawdown_vs_v3",
    "overlay_delta_two_x_return_vs_v3",
    "overlay_delta_capture_vs_v3",
    "new_engine_non_strong_bull_net_pnl",
    "strategic_objective_met",
    "rationale",
)

DECISION_FIELDS: Final = (
    "hypothesis_id",
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
    "hypothesis_id",
    "candidate_count",
    "candidate_assets",
    "evaluated_count",
    "standalone_trade_count",
    "overlay_new_trade_count",
    "first_signal_close",
    "last_signal_close",
)

CAUSAL_FIELDS: Final = (
    "hypothesis_id",
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

REGIME_FIELDS: Final = (
    "hypothesis_id",
    "market_regime",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
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


class RD16OEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SecondGenDecision:
    decision: str
    carry_forward: bool
    rationale: str
    strategic_objective_met: bool
    gates: dict[str, bool]


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16OEvaluationError(f"{name} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16OEvaluationError(f"{name} must be numeric.") from error
    if not math.isfinite(numeric):
        raise RD16OEvaluationError(f"{name} must be finite.")
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


def _optional_delta(value: object, baseline: float) -> float | None:
    numeric = _optional_float(value)
    return numeric - baseline if numeric is not None else None


def _verify_rd16n_ready() -> dict[str, Any]:
    report = read_json_object(RD16N_ROOT / "rd16n-final-report-v1.json")
    expected = {
        "decision": (
            "RD16N_INTRADAY_ALPHA_ENGINE_DIVERSIFICATION_AND_NEW_SIGNAL_RESEARCH_COMPLETED"
        ),
        "technical_status": "COMPLETED",
        "evidence_classification": ("NEW_INTRADAY_ALPHA_HYPOTHESIS_EVIDENCE_EXTRACTED"),
        "architecture_id": ARCHITECTURE_ID,
        "hypotheses_evaluated": 6,
        "retained_hypothesis_count": 0,
        "promising_hypothesis_count": 0,
        "strategic_objective_met_count": 0,
        "next_stage": (
            "RD16O_INTRADAY_ALPHA_ENGINE_REDESIGN_AND_SECOND_GENERATION_SIGNAL_RESEARCH"
        ),
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16OEvaluationError(f"RD16-N readiness mismatch for {key}: {report.get(key)!r}")

    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16OEvaluationError("RD16-N technical gates are missing.")
    required_true = (
        "all_causality_checks_pass",
        "frozen_v3_trades_preserved",
        "raw_market_data_verified",
        "rd16l_local_ledgers_verified",
        "rd16m_outputs_verified",
        "rd16m_ready",
        "same_symbol_overlap_prohibited",
        "spot_only",
        "long_only",
    )
    for key in required_true:
        if technical.get(key) is not True:
            raise RD16OEvaluationError(f"RD16-N technical gate failed: {key}")
    forbidden_true = (
        "architecture_changed",
        "dune_api_called",
        "holdout_2026_accessed",
        "optimization_performed",
        "production_authorized",
        "test_2025_accessed",
        "winner_selected",
    )
    for key in forbidden_true:
        if technical.get(key) is True:
            raise RD16OEvaluationError(f"RD16-N forbidden flag is true: {key}")
    return report


def _verify_rd16n_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16N_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(
            raw_digest,
            str,
        ):
            raise RD16OEvaluationError("RD16-N output hash manifest is invalid.")
        data_path = RD16N_ROOT / raw_name
        report_path = REPORTS_ROOT / raw_name
        path = data_path if data_path.is_file() else report_path
        if not path.is_file():
            raise RD16OEvaluationError(f"Missing RD16-N output: {raw_name}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16OEvaluationError(f"RD16-N output hash mismatch for {raw_name}.")
        verified[f"rd16n:{raw_name}"] = actual
    return verified


def _frozen_input_hashes(
    local_v3_hashes: Mapping[str, str],
) -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16n/rd16n-final-report-v1.json": (RD16N_ROOT / "rd16n-final-report-v1.json"),
        "rd16n/validation-report.json": (RD16N_ROOT / "validation-report.json"),
        "rd16n/output-hashes.json": (RD16N_ROOT / "output-hashes.json"),
        "rd16n/family-summary.csv": RD16N_ROOT / "family-summary.csv",
        "rd16n/component-decisions.csv": (RD16N_ROOT / "component-decisions.csv"),
        "rd16m/rd16m-final-report-v1.json": (RD16M_ROOT / "rd16m-final-report-v1.json"),
        "rd16l/local-ledger-manifest-v1.json": (RD16L_ROOT / "local-ledger-manifest-v1.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16OEvaluationError(f"Frozen RD16-O input is missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16n_outputs())
    hashes.update(local_v3_hashes)
    hashes.update(verify_local_dataset_hashes(LOCAL_INPUT_ROOT))
    return dict(sorted(hashes.items()))


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


def classify_second_gen_hypothesis(
    *,
    hypothesis: SignalHypothesis,
    candidate_count: int,
    candidate_assets: int,
    standalone_traded_assets: int,
    standalone: rd16n.PortfolioEvidence,
    overlay: rd16n.PortfolioEvidence,
    overlay_new_trades: pd.DataFrame,
    baseline: Mapping[str, float],
) -> SecondGenDecision:
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

    non_strong = overlay_new_trades.loc[
        overlay_new_trades["market_regime"].astype(str) != "STRONG_BULL"
    ]
    non_strong_pnl = (
        float(
            pd.to_numeric(
                non_strong["net_pnl"],
                errors="raise",
            ).sum()
        )
        if not non_strong.empty
        else 0.0
    )
    if hypothesis.role == "OFFENSIVE":
        role_evidence = delta_capture >= 0.005
    else:
        role_evidence = non_strong_pnl > 0.0

    gates = {
        "candidate_count_between_24_and_800": (24 <= candidate_count <= 800),
        "candidate_assets_gte_4": candidate_assets >= 4,
        "standalone_traded_assets_gte_4": (standalone_traded_assets >= 4),
        "standalone_trade_count_gte_40": (int(cast(int, standalone_1x["trade_count"])) >= 40),
        "standalone_net_return_positive": standalone_return > 0.0,
        "standalone_profit_factor_gte_1_20": standalone_pf >= 1.20,
        "standalone_drawdown_lte_30pct": standalone_drawdown <= 0.30,
        "standalone_two_x_positive": standalone_2x_return > 0.0,
        "standalone_two_x_profit_factor_gte_1": (_metric_profit_factor(standalone_2x) >= 1.0),
        "standalone_two_x_capital_feasible": bool(standalone_2x["capital_feasible"]),
        "standalone_positive_year_fraction_gte_50pct": (
            standalone.positive_active_year_fraction >= 0.50
        ),
        "overlay_delta_net_return_gte_5pp": delta_return >= 0.05,
        "overlay_profit_factor_preserved": (overlay_pf >= baseline["profit_factor"] - 0.05),
        "overlay_drawdown_not_worse_by_more_than_3pp": (
            overlay_drawdown <= baseline["maximum_drawdown"] + 0.03
        ),
        "overlay_capital_feasible": bool(overlay_1x["capital_feasible"]),
        "overlay_two_x_capital_feasible": bool(overlay_2x["capital_feasible"]),
        "overlay_two_x_return_not_below_v3": (overlay_2x_return >= baseline["two_x_net_return"]),
        "role_specific_evidence": role_evidence,
    }
    robust = all(gates.values())
    promising = (
        standalone_return > 0.0
        and standalone_pf >= 1.10
        and standalone_2x_return > 0.0
        and delta_return > 0.0
        and bool(overlay_2x["capital_feasible"])
    )
    strategic = (
        robust and overlay_monthly is not None and overlay_monthly >= STRATEGIC_MONTHLY_TARGET
    )

    if robust:
        decision = "RETAIN_FOR_COMPOSITE_V4_ASSEMBLY"
        carry_forward = True
        rationale = (
            "Passes all second-generation standalone, stressed-cost, "
            "additive-overlay, capital, and role-specific gates."
        )
    elif promising:
        decision = "PROMISING_BUT_FRAGILE"
        carry_forward = False
        failed = [key for key, passed in gates.items() if not passed]
        rationale = (
            "Positive second-generation standalone and additive evidence, "
            f"but fixed retention gates failed: {', '.join(failed)}."
        )
    else:
        decision = "REJECT_SECOND_GENERATION_ENGINE"
        carry_forward = False
        failed = [key for key, passed in gates.items() if not passed]
        rationale = f"Insufficient second-generation evidence; failed gates: {', '.join(failed)}."
    return SecondGenDecision(
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
    evaluated: pd.DataFrame,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if evaluated.empty:
        return rows
    for decision, group in evaluated.groupby(
        "router_decision",
        sort=True,
    ):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        rows.append(
            {
                "scope": scope,
                "variant_id": variant_id,
                "router_decision": str(decision),
                "candidate_count": len(group),
                "hypothetical_net_pnl": float(pnl.sum()),
                "hypothetical_return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "hypothetical_profit_factor": (_profit_factor_series(pnl)),
            }
        )
    return rows


def _profit_factor_series(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = float(numeric[numeric > 0.0].sum())
    gross_loss = abs(float(numeric[numeric < 0.0].sum()))
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def _regime_rows(
    trades: pd.DataFrame,
    *,
    hypothesis_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    if trades.empty:
        return rows
    for regime, group in trades.groupby("market_regime", sort=True):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        rows.append(
            {
                "hypothesis_id": hypothesis_id,
                "market_regime": str(regime),
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "win_rate": float((pnl > 0.0).mean()),
                "profit_factor": _profit_factor_series(pnl),
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


def _causal_row(
    candidates: pd.DataFrame,
    *,
    hypothesis_id: str,
) -> dict[str, object]:
    if candidates.empty:
        return {
            "hypothesis_id": hypothesis_id,
            "candidate_count": 0,
            "next_bar_violations": 0,
            "future_4h_context_violations": 0,
            "future_1d_context_violations": 0,
            "future_1w_context_violations": 0,
            "sealed_cutoff_violations": 0,
        }
    signal = pd.to_datetime(
        candidates["signal_close"],
        utc=True,
        errors="raise",
    )
    entry = pd.to_datetime(
        candidates["entry_bar_close"],
        utc=True,
        errors="raise",
    )
    cutoff = pd.Timestamp(SEALED_CUTOFF)
    return {
        "hypothesis_id": hypothesis_id,
        "candidate_count": len(candidates),
        "next_bar_violations": int(((entry - signal) != pd.Timedelta(hours=1)).sum()),
        "future_4h_context_violations": int(
            (
                pd.to_datetime(
                    candidates["4h_context_close"],
                    utc=True,
                    errors="raise",
                )
                > signal
            ).sum()
        ),
        "future_1d_context_violations": int(
            (
                pd.to_datetime(
                    candidates["1d_context_close"],
                    utc=True,
                    errors="raise",
                )
                > signal
            ).sum()
        ),
        "future_1w_context_violations": int(
            (
                pd.to_datetime(
                    candidates["1w_context_close"],
                    utc=True,
                    errors="raise",
                )
                > signal
            ).sum()
        ),
        "sealed_cutoff_violations": int((signal >= cutoff).sum()),
    }


def _write_local_frame(
    path: Path,
    frame: pd.DataFrame,
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return {
        "logical_path": path.relative_to(RD16O_LOCAL_ROOT).as_posix(),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _output_hashes(paths: Sequence[Path]) -> dict[str, str]:
    return {path.name: sha256_path(path) for path in paths}


def _write_reports(
    *,
    final_report: Mapping[str, object],
    family_rows: Sequence[Mapping[str, object]],
    all_row: Mapping[str, object],
) -> list[Path]:
    results_path = REPORTS_ROOT / "rd16o-second-generation-alpha-results-v1.md"
    decisions_path = REPORTS_ROOT / "rd16o-second-generation-carry-forward-decisions-v1.md"
    audit_path = REPORTS_ROOT / "rd16o-causality-capacity-audit-v1.md"

    results_lines = [
        "# RD16-O Second-Generation Intraday Alpha Results",
        "",
        f"- Decision: `{final_report['decision']}`",
        (f"- Hypotheses evaluated: {final_report['hypotheses_evaluated']}"),
        (f"- Retained hypotheses: {final_report['retained_hypotheses']}"),
        (f"- Promising hypotheses: {final_report['promising_hypotheses']}"),
        (
            "- All-second-generation overlay return: "
            f"{_finite(all_row['net_return'], name='all_return'):.2%}"
        ),
        (f"- All-second-generation overlay PF: {_metric_profit_factor(all_row):.3f}"),
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
        "# RD16-O Second-Generation Carry-Forward Decisions",
        "",
    ]
    for row in family_rows:
        decision_lines.extend(
            [
                f"## {row['hypothesis_id']}",
                "",
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
        "# RD16-O Causality and Capacity Audit",
        "",
        "- Signals use completed 1H bars only.",
        "- Entries use the next 1H bar open.",
        "- Cross-sectional ranks and breadth use same-time completed bars.",
        "- Frozen V3 trades are never displaced.",
        "- Maximum five positions and 2.25% open risk are preserved.",
        "- Same-symbol overlap remains prohibited.",
        "- 2025 and 2026 remain sealed.",
        "",
    ]
    audit_path.write_text(
        "\n".join(audit_lines),
        encoding="utf-8",
        newline="\n",
    )
    return [results_path, decisions_path, audit_path]


def run_rd16o_research() -> dict[str, object]:
    source_report = _verify_rd16n_ready()
    v3_ledgers, local_v3_hashes = rd16n._load_v3_ledgers()
    baseline_trades = v3_ledgers["trades"].copy()
    frozen_hashes = _frozen_input_hashes(local_v3_hashes)
    baseline = _baseline_values()

    all_market, hourly_frames, daily_frames = rd16n._load_market_frames()
    feature_frames = {
        symbol: build_feature_frame(frames, symbol=symbol) for symbol, frames in all_market.items()
    }
    second_gen_frames = build_second_gen_feature_frames(feature_frames)
    bar_positions = rd16n._bar_position_maps(hourly_frames)
    timeline = rd16n._timeline(hourly_frames)
    benchmark = build_benchmark_daily(daily_frames)

    if RD16O_LOCAL_ROOT.exists():
        shutil.rmtree(RD16O_LOCAL_ROOT)
    RD16O_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    RD16O_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    family_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    causal_rows: list[dict[str, object]] = []
    routing_rows: list[dict[str, object]] = []
    regime_rows: list[dict[str, object]] = []
    bull_rows: list[dict[str, object]] = []
    all_evaluated_frames: list[pd.DataFrame] = []
    retained: list[str] = []
    promising: list[str] = []
    rejected: list[str] = []
    strategic_count = 0

    local_manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "families": {},
        "variants": {},
    }
    family_manifest = cast(
        dict[str, object],
        local_manifest["families"],
    )
    variant_manifest = cast(
        dict[str, object],
        local_manifest["variants"],
    )

    for hypothesis in HYPOTHESIS_REGISTRY:
        candidates = build_second_gen_candidates(
            second_gen_frames,
            hypothesis=hypothesis,
        )
        evaluated = rd16n.evaluate_candidates(
            candidates,
            hourly_frames=hourly_frames,
            bar_positions=bar_positions,
        )
        standalone_evaluated, standalone_trades = rd16n.route_standalone_candidates(
            evaluated,
            hypothesis=hypothesis,
        )
        overlay_evaluated, overlay_new = rd16n.route_overlay_candidates(
            baseline_trades,
            evaluated,
            variant_id=hypothesis.hypothesis_id,
        )

        standalone_enriched = (
            enrich_trades(
                standalone_trades,
                hourly_frames=hourly_frames,
                feature_frames=feature_frames,
            )
            if not standalone_trades.empty
            else rd16n._empty_enriched_frame(standalone_trades)
        )
        overlay_new_enriched = (
            enrich_trades(
                overlay_new,
                hourly_frames=hourly_frames,
                feature_frames=feature_frames,
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
            variant_id=(f"RD16O-STANDALONE::{hypothesis.hypothesis_id}"),
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        overlay_evidence = rd16n._evaluate_portfolio(
            overlay_combined,
            variant_id=(f"RD16O-OVERLAY::{hypothesis.hypothesis_id}"),
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )

        candidate_assets = int(candidates["symbol"].astype(str).nunique())
        traded_assets = int(standalone_enriched["symbol"].astype(str).nunique())
        decision = classify_second_gen_hypothesis(
            hypothesis=hypothesis,
            candidate_count=len(candidates),
            candidate_assets=candidate_assets,
            standalone_traded_assets=traded_assets,
            standalone=standalone_evidence,
            overlay=overlay_evidence,
            overlay_new_trades=overlay_new_enriched,
            baseline=baseline,
        )

        if decision.carry_forward:
            retained.append(hypothesis.hypothesis_id)
        elif decision.decision == "PROMISING_BUT_FRAGILE":
            promising.append(hypothesis.hypothesis_id)
        else:
            rejected.append(hypothesis.hypothesis_id)
        if decision.strategic_objective_met:
            strategic_count += 1

        standalone_1x = standalone_evidence.metrics[1.0]
        standalone_2x = standalone_evidence.metrics[2.0]
        overlay_1x = overlay_evidence.metrics[1.0]
        overlay_2x = overlay_evidence.metrics[2.0]
        non_strong = overlay_new_enriched.loc[
            overlay_new_enriched["market_regime"].astype(str) != "STRONG_BULL"
        ]
        non_strong_pnl = (
            float(
                pd.to_numeric(
                    non_strong["net_pnl"],
                    errors="raise",
                ).sum()
            )
            if not non_strong.empty
            else 0.0
        )
        family_row = {
            "hypothesis_id": hypothesis.hypothesis_id,
            "engine_id": hypothesis.engine_id,
            "role": hypothesis.role,
            "decision": decision.decision,
            "carry_forward": decision.carry_forward,
            "candidate_count": len(candidates),
            "candidate_assets": candidate_assets,
            "standalone_trade_count": standalone_1x["trade_count"],
            "standalone_traded_assets": traded_assets,
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
            "overlay_new_trade_count": len(overlay_new_enriched),
            "overlay_net_return": overlay_1x["net_return"],
            "overlay_monthly_geometric_return": (overlay_1x["monthly_geometric_return"]),
            "overlay_profit_factor": overlay_1x["profit_factor"],
            "overlay_maximum_drawdown": (overlay_1x["maximum_drawdown"]),
            "overlay_two_x_net_return": overlay_2x["net_return"],
            "overlay_two_x_profit_factor": (overlay_2x["profit_factor"]),
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
            "overlay_delta_monthly_return_vs_v3": (
                _optional_delta(
                    overlay_1x["monthly_geometric_return"],
                    baseline["monthly_geometric_return"],
                )
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
            "new_engine_non_strong_bull_net_pnl": non_strong_pnl,
            "strategic_objective_met": (decision.strategic_objective_met),
            "rationale": decision.rationale,
        }
        family_rows.append(family_row)
        decision_rows.append(
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "decision": decision.decision,
                "carry_forward": decision.carry_forward,
                "rationale": decision.rationale,
                "standalone_net_return": (standalone_1x["net_return"]),
                "standalone_profit_factor": (standalone_1x["profit_factor"]),
                "overlay_delta_net_return_vs_v3": (family_row["overlay_delta_net_return_vs_v3"]),
                "overlay_profit_factor": (overlay_1x["profit_factor"]),
                "overlay_two_x_capital_feasible": (overlay_2x["capital_feasible"]),
                "overlay_delta_capture_vs_v3": (family_row["overlay_delta_capture_vs_v3"]),
            }
        )
        coverage_rows.append(
            {
                "hypothesis_id": hypothesis.hypothesis_id,
                "candidate_count": len(candidates),
                "candidate_assets": candidate_assets,
                "evaluated_count": len(evaluated),
                "standalone_trade_count": len(standalone_enriched),
                "overlay_new_trade_count": len(overlay_new_enriched),
                "first_signal_close": (
                    candidates["signal_close"].min() if not candidates.empty else None
                ),
                "last_signal_close": (
                    candidates["signal_close"].max() if not candidates.empty else None
                ),
            }
        )
        causal_rows.append(
            _causal_row(
                candidates,
                hypothesis_id=hypothesis.hypothesis_id,
            )
        )
        cost_rows.extend(
            _cost_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        cost_rows.extend(
            _cost_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        routing_rows.extend(
            _routing_rows(
                standalone_evaluated,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        routing_rows.extend(
            _routing_rows(
                overlay_evaluated,
                scope="OVERLAY",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        regime_rows.extend(
            _regime_rows(
                overlay_new_enriched,
                hypothesis_id=hypothesis.hypothesis_id,
            )
        )
        bull_rows.extend(
            _bull_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        all_evaluated_frames.append(evaluated)

        family_dir = RD16O_LOCAL_ROOT / "families" / hypothesis.hypothesis_id.lower()
        family_manifest[hypothesis.hypothesis_id] = {
            "candidates": _write_local_frame(
                family_dir / "candidates.parquet",
                candidates,
            ),
            "evaluated": _write_local_frame(
                family_dir / "evaluated.parquet",
                evaluated,
            ),
            "standalone_evaluated": _write_local_frame(
                family_dir / "standalone-evaluated.parquet",
                standalone_evaluated,
            ),
            "standalone_trades": _write_local_frame(
                family_dir / "standalone-trades.parquet",
                standalone_enriched,
            ),
            "overlay_evaluated": _write_local_frame(
                family_dir / "overlay-evaluated.parquet",
                overlay_evaluated,
            ),
            "overlay_new_trades": _write_local_frame(
                family_dir / "overlay-new-trades.parquet",
                overlay_new_enriched,
            ),
            "overlay_combined_trades": _write_local_frame(
                family_dir / "overlay-combined-trades.parquet",
                overlay_combined,
            ),
        }

    all_evaluated = pd.concat(
        all_evaluated_frames,
        ignore_index=True,
        sort=False,
    )
    all_overlay_evaluated, all_overlay_new = rd16n.route_overlay_candidates(
        baseline_trades,
        all_evaluated,
        variant_id=ALL_SECOND_GEN_VARIANT_ID,
    )
    all_overlay_new_enriched = (
        enrich_trades(
            all_overlay_new,
            hourly_frames=hourly_frames,
            feature_frames=feature_frames,
        )
        if not all_overlay_new.empty
        else rd16n._empty_enriched_frame(all_overlay_new)
    )
    all_combined = (
        pd.concat(
            [baseline_trades, all_overlay_new_enriched],
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
    all_evidence = rd16n._evaluate_portfolio(
        all_combined,
        variant_id=ALL_SECOND_GEN_VARIANT_ID,
        hourly_frames=hourly_frames,
        timeline=timeline,
        benchmark=benchmark,
    )
    all_1x = all_evidence.metrics[1.0]
    all_2x = all_evidence.metrics[2.0]
    all_row = {
        "variant_id": ALL_SECOND_GEN_VARIANT_ID,
        "new_trade_count": len(all_overlay_new_enriched),
        "trade_count": all_1x["trade_count"],
        "net_return": all_1x["net_return"],
        "monthly_geometric_return": (all_1x["monthly_geometric_return"]),
        "profit_factor": all_1x["profit_factor"],
        "gross_profit": all_1x.get("gross_profit"),
        "gross_loss": all_1x.get("gross_loss"),
        "maximum_drawdown": all_1x["maximum_drawdown"],
        "minimum_cash": all_1x["minimum_cash"],
        "capital_feasible": all_1x["capital_feasible"],
        "two_x_net_return": all_2x["net_return"],
        "two_x_profit_factor": all_2x["profit_factor"],
        "two_x_minimum_cash": all_2x["minimum_cash"],
        "two_x_capital_feasible": all_2x["capital_feasible"],
        "mean_high_opportunity_capture": (all_evidence.mean_high_opportunity_capture),
        "delta_net_return_vs_v3": (
            _finite(
                all_1x["net_return"],
                name="all_return",
            )
            - baseline["net_return"]
        ),
        "delta_profit_factor_vs_v3": (_metric_profit_factor(all_1x) - baseline["profit_factor"]),
        "delta_maximum_drawdown_vs_v3": (
            _finite(
                all_1x["maximum_drawdown"],
                name="all_drawdown",
            )
            - baseline["maximum_drawdown"]
        ),
        "delta_two_x_return_vs_v3": (
            _finite(
                all_2x["net_return"],
                name="all_two_x_return",
            )
            - baseline["two_x_net_return"]
        ),
        "delta_capture_vs_v3": (
            all_evidence.mean_high_opportunity_capture - baseline["mean_high_opportunity_capture"]
        ),
        "robust_additive_overlay": bool(
            _finite(all_1x["net_return"], name="all_return") > baseline["net_return"]
            and _metric_profit_factor(all_1x) >= baseline["profit_factor"] - 0.05
            and _finite(
                all_1x["maximum_drawdown"],
                name="all_drawdown",
            )
            <= baseline["maximum_drawdown"] + 0.03
            and bool(all_1x["capital_feasible"])
            and bool(all_2x["capital_feasible"])
        ),
    }
    cost_rows.extend(
        _cost_rows(
            all_evidence,
            scope="ALL_SECOND_GEN_OVERLAY",
            variant_id=ALL_SECOND_GEN_VARIANT_ID,
        )
    )
    routing_rows.extend(
        _routing_rows(
            all_overlay_evaluated,
            scope="ALL_SECOND_GEN_OVERLAY",
            variant_id=ALL_SECOND_GEN_VARIANT_ID,
        )
    )
    bull_rows.extend(
        _bull_rows(
            all_evidence,
            scope="ALL_SECOND_GEN_OVERLAY",
            variant_id=ALL_SECOND_GEN_VARIANT_ID,
        )
    )
    all_dir = RD16O_LOCAL_ROOT / "variants" / "all-second-gen"
    variant_manifest[ALL_SECOND_GEN_VARIANT_ID] = {
        "evaluated": _write_local_frame(
            all_dir / "evaluated.parquet",
            all_overlay_evaluated,
        ),
        "new_trades": _write_local_frame(
            all_dir / "new-trades.parquet",
            all_overlay_new_enriched,
        ),
        "combined_trades": _write_local_frame(
            all_dir / "combined-trades.parquet",
            all_combined,
        ),
    }

    causal_pass = all(
        int(cast(int, row[key])) == 0
        for row in causal_rows
        for key in (
            "next_bar_violations",
            "future_4h_context_violations",
            "future_1d_context_violations",
            "future_1w_context_violations",
            "sealed_cutoff_violations",
        )
    )
    if not causal_pass:
        raise RD16OEvaluationError("RD16-O causality or sealed-period audit failed.")

    if strategic_count > 0:
        next_stage = NEXT_PREHOLDOUT
    elif retained:
        next_stage = NEXT_ASSEMBLY
    elif promising:
        next_stage = NEXT_REFINEMENT
    else:
        next_stage = NEXT_REDESIGN

    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "architecture_id": ARCHITECTURE_ID,
        "source_stage_decision": source_report["decision"],
        "hypotheses_evaluated": len(HYPOTHESIS_REGISTRY),
        "retained_hypothesis_count": len(retained),
        "promising_hypothesis_count": len(promising),
        "rejected_hypothesis_count": len(rejected),
        "retained_hypotheses": retained,
        "promising_hypotheses": promising,
        "rejected_hypotheses": rejected,
        "strategic_objective_met_count": strategic_count,
        "strategic_objective_met": strategic_count > 0,
        "pre_registered_all_second_gen_overlay": all_row,
        "next_stage": next_stage,
        "architecture_changed": False,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "limitations": [
            "RD16-O uses development-period evidence only.",
            "Five hypotheses were frozen before execution.",
            "V3 trades are preserved and never displaced.",
            "Second-generation filters are not optimized in this stage.",
            "2025 and 2026 remain sealed.",
        ],
        "technical_gates": {
            "rd16n_ready": True,
            "rd16n_outputs_verified": True,
            "rd16l_local_ledgers_verified": True,
            "raw_market_data_verified": True,
            "five_hypotheses_pre_registered": True,
            "all_causality_checks_pass": causal_pass,
            "frozen_v3_trades_preserved": True,
            "maximum_positions_configured": (MAXIMUM_POSITIONS == 5),
            "maximum_open_risk_configured": (MAXIMUM_OPEN_RISK_FRACTION == 0.0225),
            "same_symbol_overlap_prohibited": True,
            "spot_only": True,
            "long_only": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "architecture_changed": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
        },
    }

    write_csv(
        RD16O_ROOT / "family-summary.csv",
        family_rows,
        fieldnames=FAMILY_FIELDS,
    )
    write_csv(
        RD16O_ROOT / "component-decisions.csv",
        decision_rows,
        fieldnames=DECISION_FIELDS,
    )
    write_csv(
        RD16O_ROOT / "cost-stress.csv",
        cost_rows,
        fieldnames=COST_FIELDS,
    )
    write_csv(
        RD16O_ROOT / "family-coverage.csv",
        coverage_rows,
        fieldnames=COVERAGE_FIELDS,
    )
    write_csv(
        RD16O_ROOT / "causality-audit.csv",
        causal_rows,
        fieldnames=CAUSAL_FIELDS,
    )
    write_csv(
        RD16O_ROOT / "routing-decision-summary.csv",
        routing_rows,
        fieldnames=ROUTING_FIELDS,
    )
    write_csv(
        RD16O_ROOT / "new-engine-regime-attribution.csv",
        regime_rows,
        fieldnames=REGIME_FIELDS,
    )
    write_csv(
        RD16O_ROOT / "bull-window-capture.csv",
        bull_rows,
        fieldnames=BULL_FIELDS,
    )
    write_csv(
        RD16O_ROOT / "all-second-generation-overlay-summary.csv",
        [all_row],
        fieldnames=tuple(all_row),
    )
    write_json(
        RD16O_ROOT / "frozen-input-hashes.json",
        frozen_hashes,
    )
    write_json(
        RD16O_ROOT / "local-output-manifest-v1.json",
        local_manifest,
    )
    write_json(
        RD16O_ROOT / "rd16o-final-report-v1.json",
        final_report,
    )
    validation = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "hypotheses_evaluated": len(HYPOTHESIS_REGISTRY),
        "causality_pass": causal_pass,
        "retained_hypothesis_count": len(retained),
        "promising_hypothesis_count": len(promising),
        "strategic_objective_met_count": strategic_count,
    }
    write_json(
        RD16O_ROOT / "validation-report.json",
        validation,
    )

    report_paths = _write_reports(
        final_report=final_report,
        family_rows=family_rows,
        all_row=all_row,
    )
    tracked_outputs = [
        RD16O_ROOT / "family-summary.csv",
        RD16O_ROOT / "component-decisions.csv",
        RD16O_ROOT / "cost-stress.csv",
        RD16O_ROOT / "family-coverage.csv",
        RD16O_ROOT / "causality-audit.csv",
        RD16O_ROOT / "routing-decision-summary.csv",
        RD16O_ROOT / "new-engine-regime-attribution.csv",
        RD16O_ROOT / "bull-window-capture.csv",
        RD16O_ROOT / "all-second-generation-overlay-summary.csv",
        RD16O_ROOT / "frozen-input-hashes.json",
        RD16O_ROOT / "local-output-manifest-v1.json",
        RD16O_ROOT / "rd16o-final-report-v1.json",
        RD16O_ROOT / "validation-report.json",
        *report_paths,
    ]
    write_json(
        RD16O_ROOT / "output-hashes.json",
        _output_hashes(tracked_outputs),
    )
    return final_report


__all__ = [
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "RD16OEvaluationError",
    "SecondGenDecision",
    "classify_second_gen_hypothesis",
    "run_rd16o_research",
]
