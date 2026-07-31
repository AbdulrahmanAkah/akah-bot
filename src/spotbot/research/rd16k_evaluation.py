from __future__ import annotations

import hashlib
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.research.rd16c_common import (
    BRANCH,
    CONTEXT_TIMEFRAMES,
    EXCHANGE_ID,
    LOCAL_INPUT_ROOT,
    PILOT_SYMBOLS,
    ROOT,
    SEALED_CUTOFF,
    SIGNAL_TIMEFRAME,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
)
from spotbot.research.rd16d_common import (
    COST_MULTIPLIERS,
    INITIAL_EQUITY,
    STRATEGIC_MONTHLY_TARGET,
    write_csv,
    write_json,
)
from spotbot.research.rd16d_metrics import (
    build_benchmark_daily,
    build_equity_curve,
    bull_window_rows,
    concentration_row,
    performance_metrics,
    period_return_rows,
)
from spotbot.research.rd16i_architecture import ARCHITECTURE_ID, MAXIMUM_POSITIONS
from spotbot.research.rd16k_remediation import (
    BASELINE_VARIANT_ID,
    VARIANT_REGISTRY,
    baseline_replay_matches,
    rebuild_candidate_paths,
    route_remediation_candidates,
    same_symbol_overlap_absent,
)

SCHEMA_VERSION: Final = "rd16k-capital-efficiency-bull-capture-remediation-v1"
DECISION: Final = (
    "RD16K_COMPOSITE_ALPHA_V2_CAPITAL_EFFICIENCY_AND_BULL_CAPTURE_REMEDIATION_COMPLETED"
)
EVIDENCE_CLASSIFICATION: Final = "CAPITAL_EFFICIENCY_AND_BULL_CAPTURE_EVIDENCE_EXTRACTED"
NEXT_REGISTER: Final = "RD16L_REGISTERED_COMPOSITE_ALPHA_V3_ARCHITECTURE"
NEXT_DIVERSIFY: Final = "RD16L_INTRADAY_ALPHA_ENGINE_DIVERSIFICATION_AND_NEW_SIGNAL_RESEARCH"

RD16I_ROOT: Final = ROOT / "data" / "research" / "rd16i"
RD16J_ROOT: Final = ROOT / "data" / "research" / "rd16j"
RD16K_ROOT: Final = ROOT / "data" / "research" / "rd16k"
RD16I_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16i"
RD16K_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16k"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

VARIANT_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "decision",
    "carry_forward",
    "description",
    "per_trade_notional_cap_fraction",
    "portfolio_notional_cap_fraction",
    "maximum_open_risk_fraction",
    "strong_bull_holding_bars",
    "candidate_count",
    "trade_count",
    "net_return",
    "cagr",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "win_rate",
    "total_fees",
    "turnover_on_initial_equity",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
    "two_x_net_return",
    "two_x_profit_factor",
    "two_x_minimum_cash",
    "two_x_capital_feasible",
    "maximum_positions_observed",
    "maximum_open_risk_fraction_observed",
    "maximum_open_notional_fraction_observed",
    "fourth_or_fifth_position_observed",
    "positive_active_year_fraction",
    "top_3_trade_profit_share",
    "top_engine_profit_share",
    "both_engines_positive",
    "mean_high_opportunity_capture",
    "high_opportunity_bull_adequacy",
    "delta_net_return_vs_baseline",
    "delta_monthly_return_vs_baseline",
    "delta_maximum_drawdown_vs_baseline",
    "delta_two_x_return_vs_baseline",
    "delta_two_x_minimum_cash_vs_baseline",
    "delta_high_opportunity_capture_vs_baseline",
    "strategic_objective_met",
    "rationale",
)

COST_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "cost_multiplier",
    "net_return",
    "monthly_geometric_return",
    "maximum_drawdown",
    "profit_factor",
    "total_fees",
    "minimum_cash",
    "minimum_equity",
    "capital_feasible",
)

CAPITAL_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "per_trade_notional_cap_fraction",
    "portfolio_notional_cap_fraction",
    "maximum_open_risk_fraction_configured",
    "maximum_open_risk_fraction_observed",
    "maximum_open_notional_fraction_observed",
    "maximum_positions_configured",
    "maximum_positions_observed",
    "fourth_or_fifth_position_observed",
    "trade_count",
    "turnover_on_initial_equity",
    "minimum_cash_1x",
    "minimum_cash_2x",
    "capital_feasible_1x",
    "capital_feasible_2x",
)

CAPACITY_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "router_decision",
    "candidate_count",
    "hypothetical_net_pnl",
    "hypothetical_return_on_initial_equity",
)

ENGINE_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "engine_id",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "profit_factor",
    "positive_net_contribution",
)

ANNUAL_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "period",
    "start_equity",
    "end_equity",
    "return",
    "trade_count",
)

BULL_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "window_id",
    "start",
    "end",
    "days",
    "architecture_return",
    "equal_weight_return",
    "capture_ratio",
    "high_opportunity_window",
    "strategic_bull_adequacy",
)

CONCENTRATION_FIELDS: Final = (
    "architecture_id",
    "variant_id",
    "top_1_trade_profit_share",
    "top_3_trade_profit_share",
    "top_5_trade_profit_share",
    "top_10_trade_profit_share",
    "positive_trade_hhi",
    "top_asset_profit_share",
    "top_asset",
    "top_year_profit_share",
    "top_year",
    "net_return_without_top_3",
    "top_engine_profit_share",
    "top_engine",
)

DECISION_FIELDS: Final = (
    "variant_id",
    "decision",
    "carry_forward",
    "rationale",
    "net_return",
    "monthly_geometric_return",
    "profit_factor",
    "maximum_drawdown",
    "two_x_net_return",
    "two_x_profit_factor",
    "two_x_minimum_cash",
    "two_x_capital_feasible",
    "mean_high_opportunity_capture",
    "delta_net_return_vs_baseline",
    "delta_high_opportunity_capture_vs_baseline",
    "maximum_positions_observed",
)


class RD16KEvaluationError(RuntimeError):
    pass


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16KEvaluationError(f"{name} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16KEvaluationError(f"{name} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16KEvaluationError(f"{name} must be finite.")
    return result


def _profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = float(numeric[numeric > 0.0].sum())
    gross_loss = abs(float(numeric[numeric < 0.0].sum()))
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def _verify_rd16j_ready() -> dict[str, Any]:
    report = read_json_object(RD16J_ROOT / "rd16j-final-report-v1.json")
    expected = {
        "decision": "RD16J_FIXED_COMPOSITE_ALPHA_V2_BASELINE_EVALUATION_COMPLETED",
        "technical_status": "COMPLETED",
        "evidence_classification": ("COMPREHENSIVE_COMPOSITE_ALPHA_V2_BASELINE_COMPLETE"),
        "architecture_id": ARCHITECTURE_ID,
        "classification": "ROBUST_POSITIVE_V2_WITH_COST_CAPACITY_CONSTRAINT",
        "trade_count": 596,
        "maximum_positions_configured": MAXIMUM_POSITIONS,
        "two_x_capital_feasible": False,
        "strategic_objective_met": False,
        "next_stage": ("RD16K_COMPOSITE_ALPHA_V2_CAPITAL_EFFICIENCY_AND_BULL_CAPTURE_REMEDIATION"),
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16KEvaluationError(f"RD16-J readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16KEvaluationError("RD16-J technical_gates is missing.")
    for key in (
        "rd16i_ready",
        "rd16i_outputs_verified",
        "rd16i_local_ledgers_verified",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "sealed_cutoff_respected",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16KEvaluationError(f"RD16-J technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
        "production_authorized",
    ):
        if technical.get(key) is True:
            raise RD16KEvaluationError(f"RD16-J forbidden flag is true: {key}")
    return report


def _verify_rd16j_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16J_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16KEvaluationError("RD16-J output hash manifest is invalid.")
        path = RD16J_ROOT / raw_name
        if not path.is_file():
            path = REPORTS_ROOT / raw_name
        if not path.is_file():
            raise RD16KEvaluationError(f"Missing RD16-J output: {raw_name}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16KEvaluationError(
                f"RD16-J output hash mismatch for {raw_name}: {actual} != {raw_digest}"
            )
        verified[f"rd16j:{raw_name}"] = actual
    return verified


def _load_rd16i_candidates() -> tuple[pd.DataFrame, dict[str, str]]:
    manifest = read_json_object(RD16I_ROOT / "local-ledger-manifest-v1.json")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, dict):
        raise RD16KEvaluationError("RD16-I local ledger manifest is invalid.")
    raw_entry = raw_entries.get("candidates")
    if not isinstance(raw_entry, dict):
        raise RD16KEvaluationError("RD16-I candidates entry is missing.")
    relative = raw_entry.get("logical_path")
    file_hash = raw_entry.get("file_sha256")
    content_hash = raw_entry.get("content_sha256")
    rows = raw_entry.get("rows")
    if not isinstance(relative, str):
        raise RD16KEvaluationError("RD16-I candidate path is invalid.")
    path = RD16I_LOCAL_ROOT / relative
    if not path.is_file():
        raise RD16KEvaluationError(f"Missing RD16-I candidate ledger: {path}")
    actual_file_hash = sha256_path(path)
    if not isinstance(file_hash, str) or actual_file_hash != file_hash:
        raise RD16KEvaluationError("RD16-I candidate file hash mismatch.")
    frame = pd.read_parquet(str(path))
    if not isinstance(rows, int) or len(frame) != rows:
        raise RD16KEvaluationError("RD16-I candidate row count mismatch.")
    actual_content_hash = dataframe_content_hash(frame)
    if not isinstance(content_hash, str) or actual_content_hash != content_hash:
        raise RD16KEvaluationError("RD16-I candidate content hash mismatch.")
    return frame, {"local:rd16i:candidates": actual_file_hash}


def _frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16i/rd16i-final-report-v1.json": RD16I_ROOT / "rd16i-final-report-v1.json",
        "rd16i/rd16i-protocol-v1.json": RD16I_ROOT / "rd16i-protocol-v1.json",
        "rd16i/local-ledger-manifest-v1.json": (RD16I_ROOT / "local-ledger-manifest-v1.json"),
        "rd16j/rd16j-final-report-v1.json": RD16J_ROOT / "rd16j-final-report-v1.json",
        "rd16j/rd16j-protocol-v1.json": RD16J_ROOT / "rd16j-protocol-v1.json",
        "rd16j/output-hashes.json": RD16J_ROOT / "output-hashes.json",
        "rd16j/composite-v2-baseline-summary.csv": (
            RD16J_ROOT / "composite-v2-baseline-summary.csv"
        ),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16KEvaluationError(f"Frozen RD16-K input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16j_outputs())
    _, local_hashes = _load_rd16i_candidates()
    hashes.update(local_hashes)
    return dict(sorted(hashes.items()))


def _load_market_frames() -> tuple[
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    store = ParquetCandleStore(LOCAL_INPUT_ROOT)
    hourly_frames: dict[str, pd.DataFrame] = {}
    daily_frames: dict[str, pd.DataFrame] = {}
    for symbol in PILOT_SYMBOLS:
        frames = {
            timeframe: store.load(
                exchange_id=EXCHANGE_ID,
                symbol=symbol,
                timeframe=timeframe,
                verify_integrity=True,
            )
            for timeframe in (SIGNAL_TIMEFRAME, *CONTEXT_TIMEFRAMES)
        }
        hourly_frames[symbol] = frames[SIGNAL_TIMEFRAME]
        daily_frames[symbol] = frames["1d"]
    return hourly_frames, daily_frames


def _timeline(hourly_frames: Mapping[str, pd.DataFrame]) -> pd.DatetimeIndex:
    btc = hourly_frames["BTC/USDT"]
    parsed = pd.to_datetime(btc["timestamp"], utc=True, errors="raise")
    return pd.DatetimeIndex(parsed.astype("datetime64[ns, UTC]"))


def sealed_cutoff_respected(*frames: pd.DataFrame) -> bool:
    cutoff = pd.Timestamp(SEALED_CUTOFF)
    for frame in frames:
        for column in ("signal_close", "entry_open_time", "exit_bar_close"):
            if column not in frame.columns or frame.empty:
                continue
            values = pd.to_datetime(frame[column], utc=True, errors="raise")
            if bool((values >= cutoff).any()):
                return False
    return True


def _positive_active_year_fraction(rows: Sequence[Mapping[str, object]]) -> float:
    active = [row for row in rows if int(cast(int, row["trade_count"])) > 0]
    if not active:
        return 0.0
    positive = sum(_finite(row["return"], name="annual_return") > 0.0 for row in active)
    return positive / len(active)


def _engine_rows(
    trades: pd.DataFrame,
    *,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_engine, group in trades.groupby("engine_id", sort=True, dropna=False):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "variant_id": variant_id,
                "engine_id": str(raw_engine),
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": float(pnl.sum()) / INITIAL_EQUITY,
                "profit_factor": _profit_factor(pnl),
                "positive_net_contribution": bool(float(pnl.sum()) > 0.0),
            }
        )
    return rows


def _top_engine_share(rows: Sequence[Mapping[str, object]]) -> tuple[float, str]:
    positive = [row for row in rows if _finite(row["net_pnl"], name="engine_net_pnl") > 0.0]
    if not positive:
        return 1.0, ""
    total = sum(_finite(row["net_pnl"], name="engine_net_pnl") for row in positive)
    top = max(positive, key=lambda row: _finite(row["net_pnl"], name="engine_net_pnl"))
    return _finite(top["net_pnl"], name="top_engine_pnl") / total, str(top["engine_id"])


def _mean_high_capture(rows: Sequence[Mapping[str, object]]) -> float:
    values = [
        _finite(row["capture_ratio"], name="capture_ratio")
        for row in rows
        if bool(row["high_opportunity_window"]) and row["capture_ratio"] is not None
    ]
    return sum(values) / len(values) if values else 0.0


def _high_opportunity_adequate(rows: Sequence[Mapping[str, object]]) -> bool:
    high = [row for row in rows if bool(row["high_opportunity_window"])]
    return bool(high) and all(bool(row["strategic_bull_adequacy"]) for row in high)


def _capacity_rows(
    evaluated: pd.DataFrame,
    *,
    variant_id: str,
) -> list[dict[str, object]]:
    decisions = (
        "ADMITTED",
        "REJECTED_ENGINE_CONFLICT",
        "REJECTED_SAME_SYMBOL_ACTIVE",
        "REJECTED_ENGINE_COOLDOWN",
        "REJECTED_MAX_POSITIONS",
        "REJECTED_MAX_OPEN_RISK",
        "REJECTED_PORTFOLIO_NOTIONAL",
        "REJECTED_INVALID_SIZE",
    )
    rows: list[dict[str, object]] = []
    for decision in decisions:
        group = evaluated.loc[evaluated["router_decision"].astype(str) == decision]
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "variant_id": variant_id,
                "router_decision": decision,
                "candidate_count": len(group),
                "hypothetical_net_pnl": float(pnl.sum()),
                "hypothetical_return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
            }
        )
    return rows


def classify_variant(
    summary: Mapping[str, object],
    *,
    baseline: Mapping[str, object],
) -> tuple[str, bool, str]:
    if str(summary["variant_id"]) == BASELINE_VARIANT_ID:
        return "REFERENCE_BASELINE", False, "Frozen RD16-J comparison baseline."
    gates = {
        "capital_feasible": bool(summary["capital_feasible"]),
        "two_x_capital_feasible": bool(summary["two_x_capital_feasible"]),
        "two_x_positive": _finite(summary["two_x_net_return"], name="two_x_return") > 0.0,
        "two_x_pf": _finite(summary["two_x_profit_factor"], name="two_x_pf") >= 1.0,
        "profit_factor": _finite(summary["profit_factor"], name="profit_factor") >= 1.20,
        "drawdown": _finite(summary["maximum_drawdown"], name="drawdown") <= 0.30,
        "positive_years": (
            _finite(summary["positive_active_year_fraction"], name="positive_years") >= 0.50
        ),
        "top_three": (_finite(summary["top_3_trade_profit_share"], name="top_three") <= 0.35),
        "top_engine": (_finite(summary["top_engine_profit_share"], name="top_engine") <= 0.80),
        "both_engines": bool(summary["both_engines_positive"]),
        "trade_count": int(cast(int, summary["trade_count"])) >= 100,
        "return_preserved": (
            _finite(summary["net_return"], name="net_return")
            >= 0.85 * _finite(baseline["net_return"], name="baseline_return")
        ),
        "capture_not_regressed": (
            _finite(summary["mean_high_opportunity_capture"], name="capture")
            >= _finite(baseline["mean_high_opportunity_capture"], name="baseline_capture")
        ),
    }
    retained = all(gates.values())
    if retained:
        return (
            "RETAIN_FOR_COMPOSITE_V3_REGISTRATION",
            True,
            "Passes all fixed capital, robustness, return-preservation, and bull-capture gates.",
        )
    promising = (
        gates["capital_feasible"]
        and gates["two_x_capital_feasible"]
        and gates["two_x_positive"]
        and gates["two_x_pf"]
        and gates["profit_factor"]
        and gates["drawdown"]
    )
    if promising:
        return (
            "PROMISING_BUT_FRAGILE",
            False,
            "Restores stressed-cost capital feasibility but fails one or more retention gates.",
        )
    return (
        "REJECT_REMEDIATION",
        False,
        "Does not restore sufficient robust capital efficiency and bull-capture evidence.",
    )


def _save_local_variant(
    *,
    variant_id: str,
    candidates: pd.DataFrame,
    evaluated: pd.DataFrame,
    trades: pd.DataFrame,
    curves: Mapping[float, pd.DataFrame],
) -> dict[str, object]:
    variant_root = RD16K_LOCAL_ROOT / variant_id.lower()
    variant_root.mkdir(parents=True, exist_ok=True)
    entries: dict[str, object] = {}
    frames = {
        "candidates": candidates,
        "evaluated": evaluated,
        "trades": trades,
    }
    for name, frame in frames.items():
        path = variant_root / f"{name}.parquet"
        frame.to_parquet(path, index=False, engine="pyarrow")
        entries[name] = {
            "logical_path": str(path.relative_to(RD16K_LOCAL_ROOT)).replace("\\", "/"),
            "rows": len(frame),
            "file_sha256": sha256_path(path),
            "content_sha256": dataframe_content_hash(frame),
        }
    for multiplier, curve in sorted(curves.items()):
        label = str(multiplier).replace(".", "_")
        path = variant_root / f"equity-cost-{label}x.parquet"
        curve.to_parquet(path, index=False, engine="pyarrow")
        entries[f"equity_cost_{label}x"] = {
            "logical_path": str(path.relative_to(RD16K_LOCAL_ROOT)).replace("\\", "/"),
            "rows": len(curve),
            "file_sha256": sha256_path(path),
            "content_sha256": dataframe_content_hash(curve),
        }
    return entries


def _write_reports(
    summaries: Sequence[Mapping[str, object]],
    decisions: Sequence[Mapping[str, object]],
    cost_rows: Sequence[Mapping[str, object]],
    bull_rows: Sequence[Mapping[str, object]],
) -> None:
    results = [
        "# RD16-K Capital Efficiency and Bull Capture Results v1",
        "",
        "| Variant | Decision | Return | Monthly | PF | DD | 2x feasible | Capture |",
        "|---|---|---:|---:|---:|---:|:---:|---:|",
    ]
    for row in summaries:
        results.append(
            f"| {row['variant_id']} | {row['decision']} | "
            f"{_finite(row['net_return'], name='return'):.2%} | "
            f"{_finite(row['monthly_geometric_return'], name='monthly'):.2%} | "
            f"{_finite(row['profit_factor'], name='pf'):.3f} | "
            f"{_finite(row['maximum_drawdown'], name='dd'):.2%} | "
            f"{bool(row['two_x_capital_feasible'])} | "
            f"{_finite(row['mean_high_opportunity_capture'], name='capture'):.2%} |"
        )
    (REPORTS_ROOT / "rd16k-capital-efficiency-bull-capture-results-v1.md").write_text(
        "\n".join(results) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    capital = [
        "# RD16-K Capital and Cost Audit v1",
        "",
        "| Variant | Cost | Return | PF | Minimum cash | Feasible |",
        "|---|---:|---:|---:|---:|:---:|",
    ]
    for row in cost_rows:
        capital.append(
            f"| {row['variant_id']} | {_finite(row['cost_multiplier'], name='cost'):.1f}x | "
            f"{_finite(row['net_return'], name='return'):.2%} | "
            f"{_finite(row['profit_factor'], name='pf'):.3f} | "
            f"{_finite(row['minimum_cash'], name='cash'):,.2f} | "
            f"{bool(row['capital_feasible'])} |"
        )
    (REPORTS_ROOT / "rd16k-capital-cost-audit-v1.md").write_text(
        "\n".join(capital) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    bull = [
        "# RD16-K Bull Capture Audit v1",
        "",
        "| Variant | Window | Architecture | Benchmark | Capture | High opportunity |",
        "|---|---:|---:|---:|---:|:---:|",
    ]
    for row in bull_rows:
        capture = row["capture_ratio"]
        capture_text = "" if capture is None else f"{_finite(capture, name='capture'):.2%}"
        bull.append(
            f"| {row['variant_id']} | {row['window_id']} | "
            f"{_finite(row['architecture_return'], name='architecture_return'):.2%} | "
            f"{_finite(row['equal_weight_return'], name='benchmark_return'):.2%} | "
            f"{capture_text} | {bool(row['high_opportunity_window'])} |"
        )
    (REPORTS_ROOT / "rd16k-bull-capture-audit-v1.md").write_text(
        "\n".join(bull) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    carry = [
        "# RD16-K Carry-Forward Decisions v1",
        "",
        "Carry-forward means eligibility for RD16-L registration only.",
        "",
    ]
    for row in decisions:
        carry.append(f"- `{row['variant_id']}` — **{row['decision']}**: {row['rationale']}")
    (REPORTS_ROOT / "rd16k-carry-forward-decisions-v1.md").write_text(
        "\n".join(carry) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _hash_payload(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_rd16k() -> dict[str, object]:
    RD16K_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    if RD16K_LOCAL_ROOT.exists():
        shutil.rmtree(RD16K_LOCAL_ROOT)
    RD16K_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)

    rd16j_report = _verify_rd16j_ready()
    frozen_before = _frozen_input_hashes()
    source_candidates, _ = _load_rd16i_candidates()
    hourly_frames, daily_frames = _load_market_frames()
    timeline = _timeline(hourly_frames)
    benchmark = build_benchmark_daily(daily_frames)

    baseline_variant = next(
        variant for variant in VARIANT_REGISTRY if variant.variant_id == BASELINE_VARIANT_ID
    )
    baseline_replayed = rebuild_candidate_paths(
        source_candidates,
        hourly_frames=hourly_frames,
        variant=baseline_variant,
    )
    replay_match = baseline_replay_matches(source_candidates, baseline_replayed)
    if not replay_match:
        raise RD16KEvaluationError(
            "Frozen 48-bar candidate exit replay does not match RD16-I candidates."
        )

    raw_results: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    capital_rows: list[dict[str, object]] = []
    capacity_rows: list[dict[str, object]] = []
    engine_rows_all: list[dict[str, object]] = []
    annual_rows_all: list[dict[str, object]] = []
    bull_rows_all: list[dict[str, object]] = []
    concentration_rows: list[dict[str, object]] = []
    local_variants: dict[str, object] = {}

    for variant in VARIANT_REGISTRY:
        rebuilt = (
            baseline_replayed.copy()
            if variant.variant_id == BASELINE_VARIANT_ID
            else rebuild_candidate_paths(
                source_candidates,
                hourly_frames=hourly_frames,
                variant=variant,
            )
        )
        routed = route_remediation_candidates(rebuilt, variant=variant)
        if not sealed_cutoff_respected(
            routed.candidates,
            routed.evaluated,
            routed.trades,
        ):
            raise RD16KEvaluationError(f"Variant {variant.variant_id} violated the sealed cutoff.")
        if not same_symbol_overlap_absent(routed.trades):
            raise RD16KEvaluationError(f"Variant {variant.variant_id} has same-symbol overlap.")

        curves: dict[float, pd.DataFrame] = {}
        metrics_by_cost: dict[float, dict[str, object]] = {}
        for multiplier in COST_MULTIPLIERS:
            curve = build_equity_curve(
                routed.trades,
                hourly_frames=hourly_frames,
                timeline=timeline,
                cost_multiplier=multiplier,
            )
            metrics = performance_metrics(
                curve,
                routed.trades,
                cost_multiplier=multiplier,
            )
            curves[multiplier] = curve
            metrics_by_cost[multiplier] = metrics
            cost_rows.append(
                {
                    "architecture_id": ARCHITECTURE_ID,
                    "variant_id": variant.variant_id,
                    "cost_multiplier": multiplier,
                    "net_return": metrics["net_return"],
                    "monthly_geometric_return": metrics["monthly_geometric_return"],
                    "maximum_drawdown": metrics["maximum_drawdown"],
                    "profit_factor": metrics["profit_factor"],
                    "total_fees": metrics["total_fees"],
                    "minimum_cash": metrics["minimum_cash"],
                    "minimum_equity": metrics["minimum_equity"],
                    "capital_feasible": metrics["capital_feasible"],
                }
            )

        base_curve = curves[1.0]
        metrics = metrics_by_cost[1.0]
        cost_2x = metrics_by_cost[2.0]
        annual = period_return_rows(
            base_curve,
            routed.trades,
            family_id=ARCHITECTURE_ID,
            period="year",
        )
        annual_rows = [
            {
                "architecture_id": ARCHITECTURE_ID,
                "variant_id": variant.variant_id,
                **{key: value for key, value in row.items() if key != "family_id"},
            }
            for row in annual
        ]
        annual_rows_all.extend(annual_rows)
        engines = _engine_rows(routed.trades, variant_id=variant.variant_id)
        engine_rows_all.extend(engines)
        top_engine_share, top_engine = _top_engine_share(engines)
        concentration = concentration_row(
            routed.trades,
            family_id=ARCHITECTURE_ID,
        )
        concentration_record = {
            "architecture_id": ARCHITECTURE_ID,
            "variant_id": variant.variant_id,
            **{
                key: concentration.get(key)
                for key in CONCENTRATION_FIELDS
                if key
                not in {
                    "architecture_id",
                    "variant_id",
                    "top_engine_profit_share",
                    "top_engine",
                }
            },
            "top_engine_profit_share": top_engine_share,
            "top_engine": top_engine,
        }
        concentration_rows.append(concentration_record)

        raw_bull = bull_window_rows(
            {ARCHITECTURE_ID: base_curve},
            benchmark,
        )
        bull_rows = []
        for row in raw_bull:
            record = dict(row)
            record["architecture_id"] = record.pop("family_id")
            record["variant_id"] = variant.variant_id
            record["architecture_return"] = record.pop("family_return")
            bull_rows.append(record)
        bull_rows_all.extend(bull_rows)
        mean_capture = _mean_high_capture(bull_rows)
        bull_adequate = _high_opportunity_adequate(bull_rows)
        positive_year_fraction = _positive_active_year_fraction(annual_rows)
        both_engines_positive = len(engines) == 2 and all(
            bool(row["positive_net_contribution"]) for row in engines
        )

        raw_result = {
            "architecture_id": ARCHITECTURE_ID,
            "variant_id": variant.variant_id,
            "description": variant.description,
            "per_trade_notional_cap_fraction": variant.per_trade_notional_cap_fraction,
            "portfolio_notional_cap_fraction": variant.portfolio_notional_cap_fraction,
            "maximum_open_risk_fraction": variant.maximum_open_risk_fraction,
            "strong_bull_holding_bars": variant.strong_bull_holding_bars,
            "candidate_count": len(routed.candidates),
            "trade_count": len(routed.trades),
            "net_return": metrics["net_return"],
            "cagr": metrics["cagr"],
            "monthly_geometric_return": metrics["monthly_geometric_return"],
            "maximum_drawdown": metrics["maximum_drawdown"],
            "profit_factor": metrics["profit_factor"],
            "win_rate": metrics["win_rate"],
            "total_fees": metrics["total_fees"],
            "turnover_on_initial_equity": metrics["turnover_on_initial_equity"],
            "minimum_cash": metrics["minimum_cash"],
            "minimum_equity": metrics["minimum_equity"],
            "capital_feasible": metrics["capital_feasible"],
            "two_x_net_return": cost_2x["net_return"],
            "two_x_profit_factor": cost_2x["profit_factor"],
            "two_x_minimum_cash": cost_2x["minimum_cash"],
            "two_x_capital_feasible": cost_2x["capital_feasible"],
            "maximum_positions_observed": routed.maximum_positions_observed,
            "maximum_open_risk_fraction_observed": (routed.maximum_open_risk_fraction_observed),
            "maximum_open_notional_fraction_observed": (
                routed.maximum_open_notional_fraction_observed
            ),
            "fourth_or_fifth_position_observed": (routed.maximum_positions_observed >= 4),
            "positive_active_year_fraction": positive_year_fraction,
            "top_3_trade_profit_share": concentration["top_3_trade_profit_share"],
            "top_engine_profit_share": top_engine_share,
            "both_engines_positive": both_engines_positive,
            "mean_high_opportunity_capture": mean_capture,
            "high_opportunity_bull_adequacy": bull_adequate,
        }
        raw_results.append(raw_result)
        capital_rows.append(
            {
                "architecture_id": ARCHITECTURE_ID,
                "variant_id": variant.variant_id,
                "per_trade_notional_cap_fraction": variant.per_trade_notional_cap_fraction,
                "portfolio_notional_cap_fraction": variant.portfolio_notional_cap_fraction,
                "maximum_open_risk_fraction_configured": (variant.maximum_open_risk_fraction),
                "maximum_open_risk_fraction_observed": (routed.maximum_open_risk_fraction_observed),
                "maximum_open_notional_fraction_observed": (
                    routed.maximum_open_notional_fraction_observed
                ),
                "maximum_positions_configured": MAXIMUM_POSITIONS,
                "maximum_positions_observed": routed.maximum_positions_observed,
                "fourth_or_fifth_position_observed": (routed.maximum_positions_observed >= 4),
                "trade_count": len(routed.trades),
                "turnover_on_initial_equity": metrics["turnover_on_initial_equity"],
                "minimum_cash_1x": metrics["minimum_cash"],
                "minimum_cash_2x": cost_2x["minimum_cash"],
                "capital_feasible_1x": metrics["capital_feasible"],
                "capital_feasible_2x": cost_2x["capital_feasible"],
            }
        )
        capacity_rows.extend(_capacity_rows(routed.evaluated, variant_id=variant.variant_id))
        local_variants[variant.variant_id] = _save_local_variant(
            variant_id=variant.variant_id,
            candidates=routed.candidates,
            evaluated=routed.evaluated,
            trades=routed.trades,
            curves=curves,
        )

    baseline = next(row for row in raw_results if row["variant_id"] == BASELINE_VARIANT_ID)
    tracked_summary = pd.read_csv(RD16J_ROOT / "composite-v2-baseline-summary.csv")
    if len(tracked_summary) != 1:
        raise RD16KEvaluationError("RD16-J summary must contain exactly one row.")
    tracked = tracked_summary.iloc[0].to_dict()
    baseline_checks = {
        "net_return": 1e-10,
        "monthly_geometric_return": 1e-10,
        "maximum_drawdown": 1e-10,
        "profit_factor": 1e-10,
        "minimum_cash": 1e-8,
    }
    baseline_economic_match = all(
        abs(
            _finite(baseline[key], name=f"baseline_{key}")
            - _finite(tracked[key], name=f"tracked_{key}")
        )
        <= tolerance
        for key, tolerance in baseline_checks.items()
    ) and int(cast(int, baseline["trade_count"])) == int(tracked["trade_count"])
    tracked_cost = pd.read_csv(RD16J_ROOT / "cost-stress.csv")
    tracked_two_x = tracked_cost.loc[tracked_cost["cost_multiplier"] == 2.0]
    if len(tracked_two_x) != 1:
        raise RD16KEvaluationError("RD16-J 2x cost row must be unique.")
    baseline_economic_match = (
        baseline_economic_match
        and abs(
            _finite(baseline["two_x_net_return"], name="baseline_two_x_return")
            - _finite(tracked_two_x.iloc[0]["net_return"], name="tracked_two_x_return")
        )
        <= 1e-10
    )
    if not baseline_economic_match:
        raise RD16KEvaluationError("RD16-K baseline routing or economics do not reproduce RD16-J.")

    summaries: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    retained: list[str] = []
    promising_count = 0
    strategic_count = 0
    for raw in raw_results:
        row = dict(raw)
        row["delta_net_return_vs_baseline"] = _finite(
            row["net_return"], name="net_return"
        ) - _finite(baseline["net_return"], name="baseline_return")
        row["delta_monthly_return_vs_baseline"] = _finite(
            row["monthly_geometric_return"], name="monthly"
        ) - _finite(baseline["monthly_geometric_return"], name="baseline_monthly")
        row["delta_maximum_drawdown_vs_baseline"] = _finite(
            row["maximum_drawdown"], name="drawdown"
        ) - _finite(baseline["maximum_drawdown"], name="baseline_drawdown")
        row["delta_two_x_return_vs_baseline"] = _finite(
            row["two_x_net_return"], name="two_x_return"
        ) - _finite(baseline["two_x_net_return"], name="baseline_two_x_return")
        row["delta_two_x_minimum_cash_vs_baseline"] = _finite(
            row["two_x_minimum_cash"], name="two_x_cash"
        ) - _finite(baseline["two_x_minimum_cash"], name="baseline_two_x_cash")
        row["delta_high_opportunity_capture_vs_baseline"] = _finite(
            row["mean_high_opportunity_capture"], name="capture"
        ) - _finite(
            baseline["mean_high_opportunity_capture"],
            name="baseline_capture",
        )
        strategic = bool(
            _finite(
                row["monthly_geometric_return"],
                name="monthly_geometric_return",
            )
            >= STRATEGIC_MONTHLY_TARGET
            and bool(row["high_opportunity_bull_adequacy"])
        )
        row["strategic_objective_met"] = strategic
        decision, carry, rationale = classify_variant(row, baseline=baseline)
        row["decision"] = decision
        row["carry_forward"] = carry
        row["rationale"] = rationale
        summaries.append(row)
        decisions.append({key: row[key] for key in DECISION_FIELDS})
        if carry:
            retained.append(str(row["variant_id"]))
        if decision == "PROMISING_BUT_FRAGILE":
            promising_count += 1
        if strategic:
            strategic_count += 1

    local_manifest = {
        "schema_version": SCHEMA_VERSION,
        "architecture_id": ARCHITECTURE_ID,
        "root_committed": False,
        "variants": local_variants,
    }
    frozen_after = _frozen_input_hashes()
    frozen_unchanged = frozen_before == frozen_after
    next_stage = NEXT_REGISTER if retained else NEXT_DIVERSIFY

    report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "architecture_id": ARCHITECTURE_ID,
        "source_baseline_decision": rd16j_report["decision"],
        "variants_evaluated": len(summaries),
        "retained_variant_count": len(retained),
        "promising_variant_count": promising_count,
        "retained_variants": retained,
        "strategic_objective_met_count": strategic_count,
        "next_stage": next_stage,
        "baseline_replay_match": replay_match,
        "baseline_economic_match": baseline_economic_match,
        "optimization_performed": False,
        "winner_selected": False,
        "production_authorized": False,
        "technical_gates": {
            "rd16j_ready": True,
            "rd16j_outputs_verified": True,
            "rd16i_local_candidates_verified": True,
            "all_ten_variants_evaluated": len(summaries) == len(VARIANT_REGISTRY),
            "baseline_exit_replay_match": replay_match,
            "baseline_economic_match": baseline_economic_match,
            "deterministic_inputs_unchanged": frozen_unchanged,
            "sealed_cutoff_respected": True,
            "same_symbol_overlap_prohibited": True,
            "spot_only": True,
            "long_only": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
            "production_authorized": False,
        },
        "limitations": [
            "RD16-K is an in-sample remediation study over the frozen development period.",
            "The ten variants are preregistered fixed alternatives, not a parameter sweep.",
            "A 2x cost cash-feasibility gate is mandatory for carry-forward.",
            "2025 and 2026 remain sealed.",
        ],
    }

    write_csv(RD16K_ROOT / "variant-summary.csv", summaries, fieldnames=VARIANT_FIELDS)
    write_csv(
        RD16K_ROOT / "component-decisions.csv",
        decisions,
        fieldnames=DECISION_FIELDS,
    )
    write_csv(RD16K_ROOT / "cost-stress.csv", cost_rows, fieldnames=COST_FIELDS)
    write_csv(
        RD16K_ROOT / "capital-efficiency.csv",
        capital_rows,
        fieldnames=CAPITAL_FIELDS,
    )
    write_csv(
        RD16K_ROOT / "capacity-audit.csv",
        capacity_rows,
        fieldnames=CAPACITY_FIELDS,
    )
    write_csv(
        RD16K_ROOT / "engine-attribution.csv",
        engine_rows_all,
        fieldnames=ENGINE_FIELDS,
    )
    write_csv(
        RD16K_ROOT / "annual-performance.csv",
        annual_rows_all,
        fieldnames=ANNUAL_FIELDS,
    )
    write_csv(
        RD16K_ROOT / "bull-window-capture.csv",
        bull_rows_all,
        fieldnames=BULL_FIELDS,
    )
    write_csv(
        RD16K_ROOT / "concentration-analysis.csv",
        concentration_rows,
        fieldnames=CONCENTRATION_FIELDS,
    )
    write_json(RD16K_ROOT / "frozen-input-hashes.json", frozen_before)
    write_json(RD16K_ROOT / "local-output-manifest-v1.json", local_manifest)
    write_json(RD16K_ROOT / "rd16k-final-report-v1.json", report)

    validation = {
        "schema_version": SCHEMA_VERSION,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "report_sha256": _hash_payload(report),
        "variant_count": len(summaries),
        "retained_variant_count": len(retained),
        "baseline_replay_match": replay_match,
        "baseline_economic_match": baseline_economic_match,
        "frozen_inputs_unchanged": frozen_unchanged,
        "sealed_cutoff_respected": True,
    }
    write_json(RD16K_ROOT / "validation-report.json", validation)
    _write_reports(summaries, decisions, cost_rows, bull_rows_all)

    output_paths = [
        path
        for path in RD16K_ROOT.iterdir()
        if path.is_file() and path.name not in {"rd16k-protocol-v1.json", "output-hashes.json"}
    ]
    output_paths.extend(
        [
            REPORTS_ROOT / "rd16k-capital-efficiency-bull-capture-results-v1.md",
            REPORTS_ROOT / "rd16k-capital-cost-audit-v1.md",
            REPORTS_ROOT / "rd16k-bull-capture-audit-v1.md",
            REPORTS_ROOT / "rd16k-carry-forward-decisions-v1.md",
        ]
    )
    output_hashes = {path.name: sha256_path(path) for path in sorted(output_paths)}
    write_json(RD16K_ROOT / "output-hashes.json", output_hashes)
    return report


__all__ = [
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "NEXT_DIVERSIFY",
    "NEXT_REGISTER",
    "RD16KEvaluationError",
    "SCHEMA_VERSION",
    "classify_variant",
    "run_rd16k",
    "sealed_cutoff_respected",
]
