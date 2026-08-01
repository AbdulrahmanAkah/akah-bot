from __future__ import annotations

import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
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
    verify_local_dataset_hashes,
)
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16d_common import (
    BASE_FEE_RATE,
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
    enrich_trades,
    performance_metrics,
    period_return_rows,
)
from spotbot.research.rd16l_architecture import (
    MAXIMUM_OPEN_RISK_FRACTION,
    MAXIMUM_POSITIONS,
)
from spotbot.research.rd16n_signals import (
    ARCHITECTURE_ID,
    HYPOTHESIS_REGISTRY,
    SignalHypothesis,
    build_extended_feature_frames,
    build_hypothesis_candidates,
)

SCHEMA_VERSION: Final = "rd16n-intraday-alpha-engine-diversification-v1"
DECISION: Final = "RD16N_INTRADAY_ALPHA_ENGINE_DIVERSIFICATION_AND_NEW_SIGNAL_RESEARCH_COMPLETED"
EVIDENCE_CLASSIFICATION: Final = "NEW_INTRADAY_ALPHA_HYPOTHESIS_EVIDENCE_EXTRACTED"
NEXT_ASSEMBLY: Final = "RD16O_COMPOSITE_ALPHA_V4_CANDIDATE_ASSEMBLY_AND_INTERACTION_TEST"
NEXT_REDESIGN: Final = "RD16O_INTRADAY_ALPHA_ENGINE_REDESIGN_AND_SECOND_GENERATION_SIGNAL_RESEARCH"
NEXT_PREHOLDOUT: Final = "RD16O_COMPOSITE_ALPHA_V4_PREHOLDOUT_FREEZE_AND_VALIDATION"

RD16L_ROOT: Final = ROOT / "data" / "research" / "rd16l"
RD16M_ROOT: Final = ROOT / "data" / "research" / "rd16m"
RD16N_ROOT: Final = ROOT / "data" / "research" / "rd16n"
RD16L_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16l"
RD16N_LOCAL_ROOT: Final = ROOT / "data" / "raw" / "rd16n"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

BASE_RISK_FRACTION: Final = 0.005
STRONG_BULL_RISK_FRACTION: Final = 0.0075
PROFIT_FLOOR_TRIGGER_R: Final = 1.5
PROFIT_FLOOR_LOCK_R: Final = 0.25
SECOND_PROFIT_TRIGGER_R: Final = 2.5
SECOND_PROFIT_LOCK_R: Final = 1.0
ALL_NEW_VARIANT_ID: Final = "ALL_SIX_NEW_ENGINES_OVERLAY"

FAMILY_SUMMARY_FIELDS: Final = (
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
    "standalone_top_3_trade_profit_share",
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
    "symbol",
    "candidate_count",
    "evaluated_count",
    "standalone_trade_count",
    "overlay_new_trade_count",
    "first_signal_close",
    "last_signal_close",
)

CAUSAL_FIELDS: Final = (
    "hypothesis_id",
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

REGIME_FIELDS: Final = (
    "hypothesis_id",
    "market_regime",
    "trade_count",
    "net_pnl",
    "return_on_initial_equity",
    "win_rate",
    "profit_factor",
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


class RD16NEvaluationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PortfolioEvidence:
    trades: pd.DataFrame
    curves: dict[float, pd.DataFrame]
    metrics: dict[float, dict[str, object]]
    annual_rows: tuple[dict[str, object], ...]
    bull_rows: tuple[dict[str, object], ...]
    concentration: dict[str, object]
    positive_active_year_fraction: float
    mean_high_opportunity_capture: float


@dataclass(frozen=True, slots=True)
class HypothesisDecision:
    decision: str
    carry_forward: bool
    rationale: str
    strategic_objective_met: bool
    gates: dict[str, bool]


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16NEvaluationError(f"{name} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16NEvaluationError(f"{name} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16NEvaluationError(f"{name} must be finite.")
    return result


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    raw_records = frame.to_dict(orient="records")
    return [{str(key): value for key, value in raw.items()} for raw in raw_records]


def _empty_enriched_frame(
    source: pd.DataFrame,
) -> pd.DataFrame:
    frame = source.iloc[0:0].copy()
    object_columns = (
        "trade_id",
        "router_decision",
        "overlay_variant_id",
        "exit_reason",
        "side",
        "instrument_type",
        "volatility_regime",
        "entry_month",
        "exit_month",
    )
    numeric_columns = (
        "initial_stop",
        "risk_per_unit",
        "risk_budget",
        "quantity",
        "notional",
        "exit_price",
        "bars_held",
        "gross_pnl",
        "fees",
        "net_pnl",
        "return_on_initial_equity",
        "gross_r",
        "net_r",
        "mfe_r",
        "mae_r",
        "exit_efficiency",
        "giveback_r",
        "maximum_high",
        "minimum_low",
        "entry_year",
        "exit_year",
    )
    for column in object_columns:
        if column not in frame.columns:
            frame[column] = pd.Series(dtype="object")
    for column in numeric_columns:
        if column not in frame.columns:
            frame[column] = pd.Series(dtype="float64")
    if "engine_agreement" not in frame.columns:
        frame["engine_agreement"] = pd.Series(dtype="bool")
    if "exit_bar_close" not in frame.columns:
        frame["exit_bar_close"] = pd.Series(dtype="datetime64[ns, UTC]")
    return frame


def _profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    gross_profit = float(numeric[numeric > 0.0].sum())
    gross_loss = abs(float(numeric[numeric < 0.0].sum()))
    return gross_profit / gross_loss if gross_loss > 0.0 else None


def _metric_profit_factor(
    metrics: Mapping[str, object],
) -> float:
    raw = _optional_float(metrics.get("profit_factor"))
    if raw is not None:
        return raw
    gross_profit = _optional_float(metrics.get("gross_profit")) or 0.0
    gross_loss = _optional_float(metrics.get("gross_loss")) or 0.0
    if gross_profit > 0.0 and gross_loss == 0.0:
        return math.inf
    return 0.0


def _format_metric(value: object, *, digits: int = 3) -> str:
    numeric = _optional_float(value)
    if numeric is None:
        return ""
    return f"{numeric:.{digits}f}"


def _write_rows(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    fieldnames: Sequence[str],
) -> None:
    write_csv(path, rows, fieldnames=fieldnames)


def _verify_rd16m_ready() -> dict[str, Any]:
    report = read_json_object(RD16M_ROOT / "rd16m-final-report-v1.json")
    expected = {
        "decision": ("RD16M_FIXED_COMPOSITE_ALPHA_V3_BASELINE_EVALUATION_COMPLETED"),
        "technical_status": "COMPLETED",
        "classification": "ROBUST_POSITIVE_COMPOSITE_ALPHA_V3_BASELINE",
        "architecture_id": ARCHITECTURE_ID,
        "trade_count": 567,
        "maximum_positions_configured": MAXIMUM_POSITIONS,
        "maximum_open_risk_fraction_configured": (MAXIMUM_OPEN_RISK_FRACTION),
        "two_x_capital_feasible": True,
        "strategic_objective_met": False,
        "next_stage": ("RD16N_INTRADAY_ALPHA_ENGINE_DIVERSIFICATION_AND_NEW_SIGNAL_RESEARCH"),
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16NEvaluationError(f"RD16-M readiness mismatch for {key}: {report.get(key)!r}")
    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16NEvaluationError("RD16-M technical gates are missing.")
    for key in (
        "rd16l_ready",
        "rd16l_outputs_verified",
        "rd16l_local_ledgers_verified",
        "frozen_inputs_unchanged",
        "deterministic_replay_match",
        "registered_economics_match_retained_source",
        "maximum_positions_respected",
        "sealed_cutoff_respected",
        "spot_only",
        "long_only",
    ):
        if technical.get(key) is not True:
            raise RD16NEvaluationError(f"RD16-M technical gate failed: {key}")
    for key in (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
        "production_authorized",
        "architecture_changed",
    ):
        if technical.get(key) is True:
            raise RD16NEvaluationError(f"RD16-M forbidden flag is true: {key}")
    return report


def _verify_rd16m_outputs() -> dict[str, str]:
    manifest = read_json_object(RD16M_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(
            raw_digest,
            str,
        ):
            raise RD16NEvaluationError("RD16-M output hash manifest is invalid.")
        path = RD16M_ROOT / raw_name
        if not path.is_file():
            report_path = REPORTS_ROOT / raw_name
            if not report_path.is_file():
                raise RD16NEvaluationError(f"Missing RD16-M output: {raw_name}")
            path = report_path
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16NEvaluationError(f"RD16-M output hash mismatch for {raw_name}.")
        verified[f"rd16m:{raw_name}"] = actual
    return verified


def _load_v3_ledgers() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    manifest = read_json_object(RD16L_ROOT / "local-ledger-manifest-v1.json")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, dict):
        raise RD16NEvaluationError("RD16-L local ledger manifest is invalid.")
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("candidates", "evaluated", "trades"):
        raw_entry = raw_entries.get(name)
        if not isinstance(raw_entry, dict):
            raise RD16NEvaluationError(f"Missing RD16-L ledger entry: {name}")
        relative = raw_entry.get("logical_path")
        file_hash = raw_entry.get("file_sha256")
        content_hash = raw_entry.get("content_sha256")
        rows = raw_entry.get("rows")
        if not isinstance(relative, str):
            raise RD16NEvaluationError(f"Invalid RD16-L ledger path: {name}")
        path = RD16L_LOCAL_ROOT / relative
        if not path.is_file():
            raise RD16NEvaluationError(f"Missing RD16-L local ledger: {path}")
        actual_file_hash = sha256_path(path)
        if not isinstance(file_hash, str) or actual_file_hash != file_hash:
            raise RD16NEvaluationError(f"RD16-L local file hash mismatch: {name}")
        frame = pd.read_parquet(str(path))
        if not isinstance(rows, int) or len(frame) != rows:
            raise RD16NEvaluationError(f"RD16-L local row mismatch: {name}")
        if not isinstance(content_hash, str) or dataframe_content_hash(frame) != content_hash:
            raise RD16NEvaluationError(f"RD16-L local content hash mismatch: {name}")
        frames[name] = frame
        hashes[f"local:rd16l:{name}"] = actual_file_hash
    return frames, hashes


def _frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16m/rd16m-final-report-v1.json": (RD16M_ROOT / "rd16m-final-report-v1.json"),
        "rd16m/validation-report.json": (RD16M_ROOT / "validation-report.json"),
        "rd16m/output-hashes.json": (RD16M_ROOT / "output-hashes.json"),
        "rd16m/composite-v3-baseline-summary.csv": (
            RD16M_ROOT / "composite-v3-baseline-summary.csv"
        ),
        "rd16m/cost-stress.csv": RD16M_ROOT / "cost-stress.csv",
        "rd16m/bull-window-capture.csv": (RD16M_ROOT / "bull-window-capture.csv"),
        "rd16l/local-ledger-manifest-v1.json": (RD16L_ROOT / "local-ledger-manifest-v1.json"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16NEvaluationError(f"Frozen RD16-N input is missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16m_outputs())
    _, local_hashes = _load_v3_ledgers()
    hashes.update(local_hashes)
    hashes.update(verify_local_dataset_hashes(LOCAL_INPUT_ROOT))
    return dict(sorted(hashes.items()))


def _load_market_frames() -> tuple[
    dict[str, dict[str, pd.DataFrame]],
    dict[str, pd.DataFrame],
    dict[str, pd.DataFrame],
]:
    store = ParquetCandleStore(LOCAL_INPUT_ROOT)
    all_frames: dict[str, dict[str, pd.DataFrame]] = {}
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
            for timeframe in (
                SIGNAL_TIMEFRAME,
                *CONTEXT_TIMEFRAMES,
            )
        }
        all_frames[symbol] = frames
        hourly_frames[symbol] = frames[SIGNAL_TIMEFRAME]
        daily_frames[symbol] = frames["1d"]
    return all_frames, hourly_frames, daily_frames


def _timeline(
    hourly_frames: Mapping[str, pd.DataFrame],
) -> pd.DatetimeIndex:
    btc = hourly_frames["BTC/USDT"]
    parsed = pd.to_datetime(
        btc["timestamp"],
        utc=True,
        errors="raise",
    )
    return pd.DatetimeIndex(parsed.astype("datetime64[ns, UTC]"))


def _bar_position_maps(
    hourly_frames: Mapping[str, pd.DataFrame],
) -> dict[str, dict[pd.Timestamp, int]]:
    result: dict[str, dict[pd.Timestamp, int]] = {}
    for symbol, raw in hourly_frames.items():
        frame = raw.copy()
        frame["timestamp"] = pd.to_datetime(
            frame["timestamp"],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
        result[symbol] = {
            _timestamp(value): position
            for position, value in enumerate(frame["timestamp"].tolist())
        }
    return result


def evaluate_candidate(
    candidate: Mapping[str, object],
    *,
    bars: pd.DataFrame,
    bar_positions: Mapping[pd.Timestamp, int],
) -> dict[str, object] | None:
    entry_bar_close = _timestamp(candidate["entry_bar_close"])
    entry_position = bar_positions.get(entry_bar_close)
    if entry_position is None:
        return None

    entry_price = _finite(
        candidate["entry_price"],
        name="entry_price",
    )
    atr = _finite(
        candidate["atr14_at_signal"],
        name="atr14_at_signal",
    )
    stop_multiple = _finite(
        candidate["stop_atr_multiple"],
        name="stop_atr_multiple",
    )
    maximum_holding_bars = int(
        _finite(
            candidate["maximum_holding_bars"],
            name="maximum_holding_bars",
        )
    )
    risk_per_unit = atr * stop_multiple
    initial_stop = entry_price - risk_per_unit
    if (
        entry_price <= 0.0
        or atr <= 0.0
        or risk_per_unit <= 0.0
        or initial_stop <= 0.0
        or maximum_holding_bars <= 0
    ):
        return None

    current_stop = initial_stop
    profit_floor_active = False
    exit_price = entry_price
    exit_bar_close = entry_bar_close
    exit_reason = "TIME_EXIT"
    bars_held = 0
    last_position = min(
        entry_position + maximum_holding_bars - 1,
        len(bars) - 1,
    )

    for position in range(entry_position, last_position + 1):
        row = bars.iloc[position]
        bar_low = _finite(row["low"], name="bar_low")
        bar_high = _finite(row["high"], name="bar_high")
        bar_close = _finite(row["close"], name="bar_close")
        bar_timestamp = _timestamp(row["timestamp"])
        bars_held = position - entry_position + 1

        if bar_low <= current_stop:
            exit_price = current_stop
            exit_bar_close = bar_timestamp
            exit_reason = "PROFIT_FLOOR" if profit_floor_active else "HARD_STOP"
            break

        next_stop = current_stop
        if bar_high >= entry_price + SECOND_PROFIT_TRIGGER_R * risk_per_unit:
            next_stop = max(
                next_stop,
                entry_price + SECOND_PROFIT_LOCK_R * risk_per_unit,
            )
            profit_floor_active = True
        elif bar_high >= entry_price + PROFIT_FLOOR_TRIGGER_R * risk_per_unit:
            next_stop = max(
                next_stop,
                entry_price + PROFIT_FLOOR_LOCK_R * risk_per_unit,
            )
            profit_floor_active = True
        current_stop = next_stop

        if position == last_position:
            exit_price = bar_close
            exit_bar_close = bar_timestamp
            exit_reason = "TIME_EXIT"

    market_regime = str(candidate["market_regime"])
    risk_fraction = (
        STRONG_BULL_RISK_FRACTION if market_regime == "STRONG_BULL" else BASE_RISK_FRACTION
    )
    risk_budget = INITIAL_EQUITY * risk_fraction
    quantity = risk_budget / risk_per_unit
    if quantity <= 0.0:
        return None

    entry_fee = quantity * entry_price * BASE_FEE_RATE
    exit_fee = quantity * exit_price * BASE_FEE_RATE
    gross_pnl = quantity * (exit_price - entry_price)
    fees = entry_fee + exit_fee
    net_pnl = gross_pnl - fees

    return {
        **dict(candidate),
        "initial_stop": initial_stop,
        "risk_per_unit": risk_per_unit,
        "risk_budget": risk_budget,
        "quantity": quantity,
        "notional": quantity * entry_price,
        "exit_bar_close": exit_bar_close,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "bars_held": bars_held,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "net_pnl": net_pnl,
        "return_on_initial_equity": (net_pnl / INITIAL_EQUITY),
        "engine_agreement": False,
        "side": "LONG",
        "instrument_type": "SPOT",
    }


def evaluate_candidates(
    candidates: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
    bar_positions: Mapping[
        str,
        Mapping[pd.Timestamp, int],
    ],
) -> pd.DataFrame:
    evaluated_records: list[dict[str, object]] = []
    for candidate in _records(candidates):
        symbol = str(candidate["symbol"])
        evaluated = evaluate_candidate(
            candidate,
            bars=hourly_frames[symbol],
            bar_positions=bar_positions[symbol],
        )
        if evaluated is not None:
            evaluated_records.append(evaluated)
    if not evaluated_records:
        return pd.DataFrame(
            columns=[
                *candidates.columns.tolist(),
                "initial_stop",
                "risk_per_unit",
                "risk_budget",
                "quantity",
                "notional",
                "exit_bar_close",
                "exit_price",
                "exit_reason",
                "bars_held",
                "gross_pnl",
                "fees",
                "net_pnl",
                "return_on_initial_equity",
                "engine_agreement",
                "side",
                "instrument_type",
            ]
        )
    return pd.DataFrame.from_records(evaluated_records)


def intervals_overlap(
    left_entry: object,
    left_exit: object,
    right_entry: object,
    right_exit: object,
) -> bool:
    return _timestamp(left_entry) < _timestamp(right_exit) and _timestamp(right_entry) < _timestamp(
        left_exit
    )


def _active_at(
    positions: Sequence[Mapping[str, object]],
    current: pd.Timestamp,
) -> list[Mapping[str, object]]:
    return [
        position
        for position in positions
        if (
            _timestamp(position["entry_open_time"]) <= current
            and current < _timestamp(position["exit_bar_close"])
        )
    ]


def route_standalone_candidates(
    evaluated: pd.DataFrame,
    *,
    hypothesis: SignalHypothesis,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = evaluated.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "candidate_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    active: list[dict[str, object]] = []
    admitted: list[dict[str, object]] = []
    annotated: list[dict[str, object]] = []
    last_signal: dict[str, pd.Timestamp] = {}

    for record in _records(ordered):
        entry = _timestamp(record["entry_open_time"])
        signal = _timestamp(record["signal_close"])
        symbol = str(record["symbol"])
        active = [position for position in active if _timestamp(position["exit_bar_close"]) > entry]
        positions_before = len(active)
        open_risk_before = sum(
            _finite(
                position["risk_budget"],
                name="active_risk_budget",
            )
            for position in active
        )
        risk_budget = _finite(
            record["risk_budget"],
            name="risk_budget",
        )
        decision = "ADMITTED"
        detail = "Passed fixed standalone router."

        if any(str(position["symbol"]) == symbol for position in active):
            decision = "REJECTED_SAME_SYMBOL_ACTIVE"
            detail = "A position in this symbol is already active."
        else:
            previous = last_signal.get(symbol)
            if previous is not None and signal - previous < pd.Timedelta(
                hours=hypothesis.cooldown_hours
            ):
                decision = "REJECTED_ENGINE_COOLDOWN"
                detail = "Fixed same-symbol cooldown has not elapsed."
            elif positions_before >= MAXIMUM_POSITIONS:
                decision = "REJECTED_MAX_POSITIONS"
                detail = "Maximum configured positions reached."
            elif (
                open_risk_before + risk_budget > INITIAL_EQUITY * MAXIMUM_OPEN_RISK_FRACTION + 1e-9
            ):
                decision = "REJECTED_MAX_OPEN_RISK"
                detail = "Maximum open-risk budget reached."

        positions_after = positions_before
        open_risk_after = open_risk_before
        trade_id: str | None = None
        if decision == "ADMITTED":
            trade_id = f"RD16N-STANDALONE-{hypothesis.hypothesis_id}-{len(admitted) + 1:06d}"
            admitted_record = dict(record)
            admitted_record["trade_id"] = trade_id
            admitted_record["router_decision"] = decision
            admitted.append(admitted_record)
            active.append(admitted_record)
            last_signal[symbol] = signal
            positions_after += 1
            open_risk_after += risk_budget

        annotated_record = dict(record)
        annotated_record["router_decision"] = decision
        annotated_record["router_detail"] = detail
        annotated_record["positions_before"] = positions_before
        annotated_record["positions_after"] = positions_after
        annotated_record["open_risk_before"] = open_risk_before
        annotated_record["open_risk_after"] = open_risk_after
        annotated_record["trade_id"] = trade_id
        annotated.append(annotated_record)

    annotated_frame = pd.DataFrame.from_records(annotated)
    if annotated_frame.empty:
        annotated_frame = ordered.iloc[0:0].copy()
        for column in (
            "router_decision",
            "router_detail",
            "trade_id",
        ):
            annotated_frame[column] = pd.Series(dtype="object")
        for column in (
            "positions_before",
            "positions_after",
            "open_risk_before",
            "open_risk_after",
        ):
            annotated_frame[column] = pd.Series(dtype="float64")
    admitted_frame = pd.DataFrame.from_records(admitted)
    if admitted_frame.empty:
        admitted_frame = ordered.iloc[0:0].copy()
        admitted_frame["trade_id"] = pd.Series(dtype="object")
        admitted_frame["router_decision"] = pd.Series(dtype="object")
    return annotated_frame, admitted_frame


def _candidate_capacity_passes(
    candidate: Mapping[str, object],
    *,
    existing: Sequence[Mapping[str, object]],
) -> tuple[bool, str]:
    entry = _timestamp(candidate["entry_open_time"])
    exit_time = _timestamp(candidate["exit_bar_close"])
    candidate_risk = _finite(
        candidate["risk_budget"],
        name="candidate_risk_budget",
    )
    relevant_times = {entry}
    for position in existing:
        position_entry = _timestamp(position["entry_open_time"])
        if entry <= position_entry < exit_time:
            relevant_times.add(position_entry)

    for current in sorted(relevant_times):
        active = _active_at(existing, current)
        if len(active) + 1 > MAXIMUM_POSITIONS:
            return False, "REJECTED_MAX_POSITIONS"
        open_risk = sum(
            _finite(
                position["risk_budget"],
                name="existing_risk_budget",
            )
            for position in active
        )
        if open_risk + candidate_risk > INITIAL_EQUITY * MAXIMUM_OPEN_RISK_FRACTION + 1e-9:
            return False, "REJECTED_MAX_OPEN_RISK"
    return True, "ADMITTED"


def route_overlay_candidates(
    baseline_trades: pd.DataFrame,
    new_evaluated: pd.DataFrame,
    *,
    variant_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    baseline = _records(
        baseline_trades.sort_values(
            by=[
                "entry_open_time",
                "symbol",
                "signal_close",
                "trade_id",
            ],
            kind="stable",
        )
    )
    ordered = new_evaluated.sort_values(
        by=[
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "candidate_id",
        ],
        kind="stable",
    ).reset_index(drop=True)
    admitted: list[dict[str, object]] = []
    annotated: list[dict[str, object]] = []
    last_signal: dict[tuple[str, str], pd.Timestamp] = {}

    for record in _records(ordered):
        entry = _timestamp(record["entry_open_time"])
        exit_time = _timestamp(record["exit_bar_close"])
        signal = _timestamp(record["signal_close"])
        symbol = str(record["symbol"])
        engine_id = str(record["engine_id"])
        cooldown_hours = int(
            _finite(
                record["cooldown_hours"],
                name="cooldown_hours",
            )
        )
        existing: list[Mapping[str, object]] = [
            *baseline,
            *admitted,
        ]
        active_at_entry = _active_at(existing, entry)
        positions_before = len(active_at_entry)
        open_risk_before = sum(
            _finite(
                position["risk_budget"],
                name="open_risk_before",
            )
            for position in active_at_entry
        )
        decision = "ADMITTED"
        detail = "Passed frozen-V3 additive overlay router."

        same_symbol_overlap = any(
            str(position["symbol"]) == symbol
            and intervals_overlap(
                entry,
                exit_time,
                position["entry_open_time"],
                position["exit_bar_close"],
            )
            for position in existing
        )
        if same_symbol_overlap:
            decision = "REJECTED_SAME_SYMBOL_OVERLAP"
            detail = (
                "Candidate would overlap a frozen V3 or admitted "
                "new-engine position in the same symbol."
            )
        else:
            previous = last_signal.get((symbol, engine_id))
            if previous is not None and signal - previous < pd.Timedelta(hours=cooldown_hours):
                decision = "REJECTED_ENGINE_COOLDOWN"
                detail = "Fixed new-engine cooldown has not elapsed."
            else:
                passed, capacity_decision = _candidate_capacity_passes(
                    record,
                    existing=existing,
                )
                if not passed:
                    decision = capacity_decision
                    detail = (
                        "Candidate would violate frozen V3 future position or open-risk capacity."
                    )

        positions_after = positions_before
        open_risk_after = open_risk_before
        trade_id: str | None = None
        if decision == "ADMITTED":
            trade_id = f"RD16N-OVERLAY-{variant_id}-{len(admitted) + 1:06d}"
            admitted_record = dict(record)
            admitted_record["trade_id"] = trade_id
            admitted_record["router_decision"] = decision
            admitted_record["overlay_variant_id"] = variant_id
            admitted.append(admitted_record)
            last_signal[(symbol, engine_id)] = signal
            positions_after += 1
            open_risk_after += _finite(
                record["risk_budget"],
                name="risk_budget",
            )

        annotated_record = dict(record)
        annotated_record["router_decision"] = decision
        annotated_record["router_detail"] = detail
        annotated_record["positions_before"] = positions_before
        annotated_record["positions_after"] = positions_after
        annotated_record["open_risk_before"] = open_risk_before
        annotated_record["open_risk_after"] = open_risk_after
        annotated_record["trade_id"] = trade_id
        annotated_record["overlay_variant_id"] = variant_id
        annotated.append(annotated_record)

    annotated_frame = pd.DataFrame.from_records(annotated)
    if annotated_frame.empty:
        annotated_frame = ordered.iloc[0:0].copy()
        for column in (
            "router_decision",
            "router_detail",
            "trade_id",
            "overlay_variant_id",
        ):
            annotated_frame[column] = pd.Series(dtype="object")
        for column in (
            "positions_before",
            "positions_after",
            "open_risk_before",
            "open_risk_after",
        ):
            annotated_frame[column] = pd.Series(dtype="float64")
    admitted_frame = pd.DataFrame.from_records(admitted)
    if admitted_frame.empty:
        admitted_frame = ordered.iloc[0:0].copy()
        admitted_frame["trade_id"] = pd.Series(dtype="object")
        admitted_frame["router_decision"] = pd.Series(dtype="object")
        admitted_frame["overlay_variant_id"] = pd.Series(dtype="object")
    return annotated_frame, admitted_frame


def _mean_high_opportunity_capture(
    rows: Sequence[Mapping[str, object]],
) -> float:
    values = [
        _finite(row["capture_ratio"], name="capture_ratio")
        for row in rows
        if (bool(row["high_opportunity_window"]) and row.get("capture_ratio") is not None)
    ]
    return sum(values) / len(values) if values else 0.0


def _positive_active_year_fraction(
    rows: Sequence[Mapping[str, object]],
) -> float:
    active = [row for row in rows if int(cast(int, row["trade_count"])) > 0]
    if not active:
        return 0.0
    positive = sum((_optional_float(row["return"]) or 0.0) > 0.0 for row in active)
    return positive / len(active)


def _evaluate_portfolio(
    trades: pd.DataFrame,
    *,
    variant_id: str,
    hourly_frames: Mapping[str, pd.DataFrame],
    timeline: pd.DatetimeIndex,
    benchmark: pd.DataFrame,
) -> PortfolioEvidence:
    curves: dict[float, pd.DataFrame] = {}
    metrics: dict[float, dict[str, object]] = {}
    for multiplier in COST_MULTIPLIERS:
        curve = build_equity_curve(
            trades,
            hourly_frames=hourly_frames,
            timeline=timeline,
            cost_multiplier=multiplier,
        )
        curves[multiplier] = curve
        metrics[multiplier] = performance_metrics(
            curve,
            trades,
            cost_multiplier=multiplier,
        )

    annual_rows = tuple(
        period_return_rows(
            curves[1.0],
            trades,
            family_id=variant_id,
            period="year",
        )
    )
    bull_rows = tuple(
        bull_window_rows(
            {variant_id: curves[1.0]},
            benchmark,
        )
    )
    concentration = concentration_row(
        trades,
        family_id=variant_id,
    )
    return PortfolioEvidence(
        trades=trades,
        curves=curves,
        metrics=metrics,
        annual_rows=annual_rows,
        bull_rows=bull_rows,
        concentration=concentration,
        positive_active_year_fraction=(_positive_active_year_fraction(annual_rows)),
        mean_high_opportunity_capture=(_mean_high_opportunity_capture(bull_rows)),
    )


def _baseline_values(
    report: Mapping[str, object],
) -> dict[str, float]:
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


def classify_hypothesis(
    *,
    hypothesis: SignalHypothesis,
    candidate_count: int,
    candidate_assets: int,
    standalone_traded_assets: int,
    standalone: PortfolioEvidence,
    overlay: PortfolioEvidence,
    overlay_new_trades: pd.DataFrame,
    baseline: Mapping[str, float],
) -> HypothesisDecision:
    standalone_1x = standalone.metrics[1.0]
    standalone_2x = standalone.metrics[2.0]
    overlay_1x = overlay.metrics[1.0]
    overlay_2x = overlay.metrics[2.0]

    standalone_return = _finite(
        standalone_1x["net_return"],
        name="standalone_net_return",
    )
    standalone_pf = _metric_profit_factor(standalone_1x)
    overlay_return = _finite(
        overlay_1x["net_return"],
        name="overlay_net_return",
    )
    overlay_pf = _metric_profit_factor(overlay_1x)
    overlay_drawdown = _finite(
        overlay_1x["maximum_drawdown"],
        name="overlay_drawdown",
    )
    overlay_monthly = _finite(
        overlay_1x["monthly_geometric_return"],
        name="overlay_monthly_return",
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

    role_evidence = (
        delta_capture >= 0.001
        if hypothesis.role == "OFFENSIVE"
        else (non_strong_pnl > 0.0 and overlay_drawdown <= baseline["maximum_drawdown"] + 0.01)
    )

    gates = {
        "candidate_count_gte_75": candidate_count >= 75,
        "candidate_assets_gte_4": candidate_assets >= 4,
        "standalone_trade_count_gte_50": (int(cast(int, standalone_1x["trade_count"])) >= 50),
        "standalone_traded_assets_gte_4": (standalone_traded_assets >= 4),
        "standalone_net_return_positive": (standalone_return > 0.0),
        "standalone_profit_factor_gte_1_15": (standalone_pf >= 1.15),
        "standalone_drawdown_lte_30pct": (
            _finite(
                standalone_1x["maximum_drawdown"],
                name="standalone_drawdown",
            )
            <= 0.30
        ),
        "standalone_two_x_positive": (
            _finite(
                standalone_2x["net_return"],
                name="standalone_two_x_return",
            )
            > 0.0
        ),
        "standalone_two_x_profit_factor_gte_1": (
            _finite(
                standalone_2x["profit_factor"],
                name="standalone_two_x_profit_factor",
            )
            >= 1.0
        ),
        "standalone_two_x_capital_feasible": bool(standalone_2x["capital_feasible"]),
        "standalone_positive_year_fraction_gte_50pct": (
            standalone.positive_active_year_fraction >= 0.50
        ),
        "standalone_top3_share_lte_50pct": (
            (_optional_float(standalone.concentration.get("top_3_trade_profit_share")) or math.inf)
            <= 0.50
        ),
        "overlay_delta_net_return_gte_5pp": (delta_return >= 0.05),
        "overlay_profit_factor_preserved": (overlay_pf >= baseline["profit_factor"] - 0.05),
        "overlay_drawdown_not_worse_by_more_than_3pp": (
            overlay_drawdown <= baseline["maximum_drawdown"] + 0.03
        ),
        "overlay_capital_feasible": bool(overlay_1x["capital_feasible"]),
        "overlay_two_x_capital_feasible": bool(overlay_2x["capital_feasible"]),
        "overlay_two_x_return_not_below_v3": (
            _finite(
                overlay_2x["net_return"],
                name="overlay_two_x_return",
            )
            >= baseline["two_x_net_return"]
        ),
        "role_specific_evidence": role_evidence,
    }
    required = tuple(gates)
    robust = all(gates[key] for key in required)
    promising = (
        standalone_return > 0.0
        and standalone_pf >= 1.05
        and delta_return > 0.0
        and bool(overlay_2x["capital_feasible"])
    )
    strategic = robust and overlay_monthly >= STRATEGIC_MONTHLY_TARGET

    if robust:
        decision = "RETAIN_FOR_COMPOSITE_V4_ASSEMBLY"
        carry_forward = True
        rationale = (
            "Passes all fixed standalone, stressed-cost, additive "
            "overlay, and role-specific evidence gates."
        )
    elif promising:
        decision = "PROMISING_BUT_FRAGILE"
        carry_forward = False
        failed = [key for key, passed in gates.items() if not passed]
        rationale = (
            "Positive standalone and overlay evidence, but fixed "
            f"retention gates failed: {', '.join(failed)}."
        )
    else:
        decision = "REJECT_NEW_ENGINE"
        carry_forward = False
        failed = [key for key, passed in gates.items() if not passed]
        rationale = f"Insufficient robust new-engine evidence; failed gates: {', '.join(failed)}."

    return HypothesisDecision(
        decision=decision,
        carry_forward=carry_forward,
        rationale=rationale,
        strategic_objective_met=strategic,
        gates=gates,
    )


def _routing_rows(
    evaluated: pd.DataFrame,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for decision, group in evaluated.groupby(
        "router_decision",
        sort=True,
        dropna=False,
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
                "hypothetical_profit_factor": (_profit_factor(pnl)),
            }
        )
    return rows


def _regime_rows(
    trades: pd.DataFrame,
    *,
    hypothesis_id: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for regime, group in trades.groupby(
        "market_regime",
        sort=True,
        dropna=False,
    ):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        rows.append(
            {
                "hypothesis_id": hypothesis_id,
                "market_regime": str(regime),
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "win_rate": float((pnl > 0.0).mean()),
                "profit_factor": _profit_factor(pnl),
            }
        )
    return rows


def _coverage_and_causality(
    *,
    hypothesis_id: str,
    candidates: pd.DataFrame,
    evaluated: pd.DataFrame,
    standalone: pd.DataFrame,
    overlay_new: pd.DataFrame,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
]:
    coverage: list[dict[str, object]] = []
    causal: list[dict[str, object]] = []
    cutoff = pd.Timestamp(SEALED_CUTOFF)

    for symbol in PILOT_SYMBOLS:
        candidate_group = candidates.loc[candidates["symbol"].astype(str) == symbol]
        evaluated_group = evaluated.loc[evaluated["symbol"].astype(str) == symbol]
        standalone_group = standalone.loc[standalone["symbol"].astype(str) == symbol]
        overlay_group = overlay_new.loc[overlay_new["symbol"].astype(str) == symbol]
        if candidate_group.empty:
            first_signal = ""
            last_signal = ""
            next_bar_violations = 0
            future_4h = 0
            future_1d = 0
            future_1w = 0
            sealed = 0
        else:
            signal = pd.to_datetime(
                candidate_group["signal_close"],
                utc=True,
                errors="raise",
            )
            entry_close = pd.to_datetime(
                candidate_group["entry_bar_close"],
                utc=True,
                errors="raise",
            )
            first_signal = _timestamp(signal.min()).isoformat()
            last_signal = _timestamp(signal.max()).isoformat()
            next_bar_violations = int((entry_close - signal != pd.Timedelta(hours=1)).sum())
            future_4h = int(
                (
                    pd.to_datetime(
                        candidate_group["4h_context_close"],
                        utc=True,
                        errors="raise",
                    )
                    > signal
                ).sum()
            )
            future_1d = int(
                (
                    pd.to_datetime(
                        candidate_group["1d_context_close"],
                        utc=True,
                        errors="raise",
                    )
                    > signal
                ).sum()
            )
            future_1w = int(
                (
                    pd.to_datetime(
                        candidate_group["1w_context_close"],
                        utc=True,
                        errors="raise",
                    )
                    > signal
                ).sum()
            )
            sealed = int((signal >= cutoff).sum())

        coverage.append(
            {
                "hypothesis_id": hypothesis_id,
                "symbol": symbol,
                "candidate_count": len(candidate_group),
                "evaluated_count": len(evaluated_group),
                "standalone_trade_count": len(standalone_group),
                "overlay_new_trade_count": len(overlay_group),
                "first_signal_close": first_signal,
                "last_signal_close": last_signal,
            }
        )
        causal.append(
            {
                "hypothesis_id": hypothesis_id,
                "symbol": symbol,
                "candidate_count": len(candidate_group),
                "next_bar_violations": next_bar_violations,
                "future_4h_context_violations": future_4h,
                "future_1d_context_violations": future_1d,
                "future_1w_context_violations": future_1w,
                "sealed_cutoff_violations": sealed,
            }
        )
    return coverage, causal


def _cost_rows(
    evidence: PortfolioEvidence,
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
                "maximum_drawdown": (metrics["maximum_drawdown"]),
                "profit_factor": metrics["profit_factor"],
                "minimum_cash": metrics["minimum_cash"],
                "minimum_equity": metrics["minimum_equity"],
                "capital_feasible": metrics["capital_feasible"],
            }
        )
    return rows


def _annual_output_rows(
    evidence: PortfolioEvidence,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    return [
        {
            "scope": scope,
            "variant_id": variant_id,
            "period": row["period"],
            "start_equity": row["start_equity"],
            "end_equity": row["end_equity"],
            "return": row["return"],
            "trade_count": row["trade_count"],
        }
        for row in evidence.annual_rows
    ]


def _bull_output_rows(
    evidence: PortfolioEvidence,
    *,
    scope: str,
    variant_id: str,
) -> list[dict[str, object]]:
    return [
        {
            "scope": scope,
            "variant_id": variant_id,
            "window_id": row["window_id"],
            "start": row["start"],
            "end": row["end"],
            "days": row["days"],
            "portfolio_return": row["family_return"],
            "equal_weight_return": row["equal_weight_return"],
            "capture_ratio": row["capture_ratio"],
            "high_opportunity_window": (row["high_opportunity_window"]),
            "strategic_bull_adequacy": (row["strategic_bull_adequacy"]),
        }
        for row in evidence.bull_rows
    ]


def _write_local_frame(
    path: Path,
    frame: pd.DataFrame,
) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return {
        "logical_path": path.relative_to(RD16N_LOCAL_ROOT).as_posix(),
        "rows": len(frame),
        "file_sha256": sha256_path(path),
        "content_sha256": dataframe_content_hash(frame),
    }


def _write_reports(
    *,
    final_report: Mapping[str, object],
    family_rows: Sequence[Mapping[str, object]],
    all_new_row: Mapping[str, object],
) -> list[Path]:
    results_path = REPORTS_ROOT / "rd16n-intraday-alpha-diversification-results-v1.md"
    decisions_path = REPORTS_ROOT / "rd16n-new-engine-carry-forward-decisions-v1.md"
    audit_path = REPORTS_ROOT / "rd16n-causality-capacity-audit-v1.md"

    lines = [
        "# RD16-N Intraday Alpha Diversification Results",
        "",
        f"- Decision: `{final_report['decision']}`",
        (f"- Hypotheses evaluated: {final_report['hypotheses_evaluated']}"),
        (f"- Retained hypotheses: {final_report['retained_hypotheses']}"),
        (f"- Promising hypotheses: {final_report['promising_hypotheses']}"),
        (f"- Strategic objective met count: {final_report['strategic_objective_met_count']}"),
        (
            "- Pre-registered all-new overlay return: "
            f"{_finite(all_new_row['net_return'], name='all_new_return'):.2%}"
        ),
        (f"- Pre-registered all-new overlay PF: {_format_metric(all_new_row['profit_factor'])}"),
        "",
        f"Next: `{final_report['next_stage']}`",
        "",
    ]
    results_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
        newline="\n",
    )

    decision_lines = [
        "# RD16-N New-Engine Carry-Forward Decisions",
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
                    f"{_finite(row['standalone_net_return'], name='standalone_return'):.2%} / "
                    f"{_format_metric(row['standalone_profit_factor'])}"
                ),
                (
                    "- Overlay delta return / capture: "
                    f"{_finite(row['overlay_delta_net_return_vs_v3'], name='delta_return'):.2%} / "
                    f"{_finite(row['overlay_delta_capture_vs_v3'], name='delta_capture'):.2%}"
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
        "# RD16-N Causality and Capacity Audit",
        "",
        "- Signal decisions use completed 1H bars only.",
        "- All entries use the next 1H bar open.",
        "- 4H, 1D and 1W context timestamps cannot exceed signal close.",
        "- Frozen V3 trades are never displaced by a new engine.",
        "- New overlays must preserve five-position and 2.25% open-risk limits.",
        "- Same-symbol overlap is prohibited.",
        "- 2025 and 2026 remain sealed.",
        "",
    ]
    audit_path.write_text(
        "\n".join(audit_lines),
        encoding="utf-8",
        newline="\n",
    )
    return [results_path, decisions_path, audit_path]


def run_rd16n_research() -> dict[str, object]:
    source_report = _verify_rd16m_ready()
    frozen_hashes = _frozen_input_hashes()
    v3_ledgers, _ = _load_v3_ledgers()
    baseline_trades = v3_ledgers["trades"].copy()

    all_market, hourly_frames, daily_frames = _load_market_frames()
    feature_frames = {
        symbol: build_feature_frame(
            frames,
            symbol=symbol,
        )
        for symbol, frames in all_market.items()
    }
    extended_frames = build_extended_feature_frames(feature_frames)
    bar_positions = _bar_position_maps(hourly_frames)
    timeline = _timeline(hourly_frames)
    benchmark = build_benchmark_daily(daily_frames)
    baseline = _baseline_values(source_report)

    if RD16N_LOCAL_ROOT.exists():
        shutil.rmtree(RD16N_LOCAL_ROOT)
    RD16N_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    RD16N_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    family_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    causal_rows: list[dict[str, object]] = []
    routing_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    bull_rows: list[dict[str, object]] = []
    regime_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    all_evaluated_frames: list[pd.DataFrame] = []
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

    retained: list[str] = []
    promising: list[str] = []
    rejected: list[str] = []
    strategic_count = 0

    for hypothesis in HYPOTHESIS_REGISTRY:
        candidates = build_hypothesis_candidates(
            extended_frames,
            hypothesis=hypothesis,
        )
        evaluated = evaluate_candidates(
            candidates,
            hourly_frames=hourly_frames,
            bar_positions=bar_positions,
        )
        standalone_evaluated, standalone_trades = route_standalone_candidates(
            evaluated,
            hypothesis=hypothesis,
        )
        overlay_evaluated, overlay_new = route_overlay_candidates(
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
            else _empty_enriched_frame(standalone_trades)
        )
        overlay_new_enriched = (
            enrich_trades(
                overlay_new,
                hourly_frames=hourly_frames,
                feature_frames=feature_frames,
            )
            if not overlay_new.empty
            else _empty_enriched_frame(overlay_new)
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

        standalone_evidence = _evaluate_portfolio(
            standalone_enriched,
            variant_id=(f"STANDALONE::{hypothesis.hypothesis_id}"),
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )
        overlay_evidence = _evaluate_portfolio(
            overlay_combined,
            variant_id=(f"OVERLAY::{hypothesis.hypothesis_id}"),
            hourly_frames=hourly_frames,
            timeline=timeline,
            benchmark=benchmark,
        )

        candidate_assets = int(candidates["symbol"].astype(str).nunique())
        standalone_traded_assets = int(standalone_enriched["symbol"].astype(str).nunique())
        decision = classify_hypothesis(
            hypothesis=hypothesis,
            candidate_count=len(candidates),
            candidate_assets=candidate_assets,
            standalone_traded_assets=standalone_traded_assets,
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
        overlay_non_strong = overlay_new_enriched.loc[
            overlay_new_enriched["market_regime"].astype(str) != "STRONG_BULL"
        ]
        non_strong_pnl = (
            float(
                pd.to_numeric(
                    overlay_non_strong["net_pnl"],
                    errors="raise",
                ).sum()
            )
            if not overlay_non_strong.empty
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
            "standalone_trade_count": (standalone_1x["trade_count"]),
            "standalone_traded_assets": (standalone_traded_assets),
            "standalone_net_return": (standalone_1x["net_return"]),
            "standalone_monthly_geometric_return": (standalone_1x["monthly_geometric_return"]),
            "standalone_profit_factor": (standalone_1x["profit_factor"]),
            "standalone_maximum_drawdown": (standalone_1x["maximum_drawdown"]),
            "standalone_two_x_net_return": (standalone_2x["net_return"]),
            "standalone_two_x_profit_factor": (standalone_2x["profit_factor"]),
            "standalone_two_x_capital_feasible": (standalone_2x["capital_feasible"]),
            "standalone_positive_active_year_fraction": (
                standalone_evidence.positive_active_year_fraction
            ),
            "standalone_top_3_trade_profit_share": (
                standalone_evidence.concentration.get("top_3_trade_profit_share")
            ),
            "overlay_new_trade_count": len(overlay_new_enriched),
            "overlay_net_return": overlay_1x["net_return"],
            "overlay_monthly_geometric_return": (overlay_1x["monthly_geometric_return"]),
            "overlay_profit_factor": (overlay_1x["profit_factor"]),
            "overlay_maximum_drawdown": (overlay_1x["maximum_drawdown"]),
            "overlay_two_x_net_return": (overlay_2x["net_return"]),
            "overlay_two_x_profit_factor": (overlay_2x["profit_factor"]),
            "overlay_two_x_capital_feasible": (overlay_2x["capital_feasible"]),
            "overlay_mean_high_opportunity_capture": (
                overlay_evidence.mean_high_opportunity_capture
            ),
            "overlay_delta_net_return_vs_v3": (
                _finite(
                    overlay_1x["net_return"],
                    name="overlay_net_return",
                )
                - baseline["net_return"]
            ),
            "overlay_delta_monthly_return_vs_v3": (
                _finite(
                    overlay_1x["monthly_geometric_return"],
                    name="overlay_monthly_return",
                )
                - baseline["monthly_geometric_return"]
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
            "new_engine_non_strong_bull_net_pnl": (non_strong_pnl),
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
        annual_rows.extend(
            _annual_output_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        annual_rows.extend(
            _annual_output_rows(
                overlay_evidence,
                scope="OVERLAY",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        bull_rows.extend(
            _bull_output_rows(
                standalone_evidence,
                scope="STANDALONE",
                variant_id=hypothesis.hypothesis_id,
            )
        )
        bull_rows.extend(
            _bull_output_rows(
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
            if not overlay_new_enriched.empty
            else []
        )
        coverage, causal = _coverage_and_causality(
            hypothesis_id=hypothesis.hypothesis_id,
            candidates=candidates,
            evaluated=evaluated,
            standalone=standalone_enriched,
            overlay_new=overlay_new_enriched,
        )
        coverage_rows.extend(coverage)
        causal_rows.extend(causal)

        family_directory = RD16N_LOCAL_ROOT / "families" / hypothesis.hypothesis_id.lower()
        family_manifest[hypothesis.hypothesis_id] = {
            "candidates": _write_local_frame(
                family_directory / "candidates.parquet",
                candidates,
            ),
            "evaluated": _write_local_frame(
                family_directory / "evaluated.parquet",
                evaluated,
            ),
            "standalone_evaluated": _write_local_frame(
                family_directory / "standalone-evaluated.parquet",
                standalone_evaluated,
            ),
            "standalone_trades": _write_local_frame(
                family_directory / "standalone-trades.parquet",
                standalone_enriched,
            ),
            "overlay_evaluated": _write_local_frame(
                family_directory / "overlay-evaluated.parquet",
                overlay_evaluated,
            ),
            "overlay_new_trades": _write_local_frame(
                family_directory / "overlay-new-trades.parquet",
                overlay_new_enriched,
            ),
            "overlay_combined_trades": _write_local_frame(
                family_directory / "overlay-combined-trades.parquet",
                overlay_combined,
            ),
        }
        all_evaluated_frames.append(evaluated)

    all_new_evaluated = pd.concat(
        all_evaluated_frames,
        ignore_index=True,
        sort=False,
    )
    all_overlay_evaluated, all_overlay_new = route_overlay_candidates(
        baseline_trades,
        all_new_evaluated,
        variant_id=ALL_NEW_VARIANT_ID,
    )
    all_overlay_new_enriched = (
        enrich_trades(
            all_overlay_new,
            hourly_frames=hourly_frames,
            feature_frames=feature_frames,
        )
        if not all_overlay_new.empty
        else _empty_enriched_frame(all_overlay_new)
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
    all_evidence = _evaluate_portfolio(
        all_combined,
        variant_id=ALL_NEW_VARIANT_ID,
        hourly_frames=hourly_frames,
        timeline=timeline,
        benchmark=benchmark,
    )
    all_1x = all_evidence.metrics[1.0]
    all_2x = all_evidence.metrics[2.0]
    all_new_row = {
        "variant_id": ALL_NEW_VARIANT_ID,
        "new_trade_count": len(all_overlay_new_enriched),
        "trade_count": all_1x["trade_count"],
        "net_return": all_1x["net_return"],
        "monthly_geometric_return": (all_1x["monthly_geometric_return"]),
        "profit_factor": all_1x["profit_factor"],
        "maximum_drawdown": all_1x["maximum_drawdown"],
        "minimum_cash": all_1x["minimum_cash"],
        "capital_feasible": all_1x["capital_feasible"],
        "two_x_net_return": all_2x["net_return"],
        "two_x_profit_factor": all_2x["profit_factor"],
        "two_x_minimum_cash": all_2x["minimum_cash"],
        "two_x_capital_feasible": (all_2x["capital_feasible"]),
        "mean_high_opportunity_capture": (all_evidence.mean_high_opportunity_capture),
        "delta_net_return_vs_v3": (
            _finite(
                all_1x["net_return"],
                name="all_new_net_return",
            )
            - baseline["net_return"]
        ),
        "delta_profit_factor_vs_v3": (_metric_profit_factor(all_1x) - baseline["profit_factor"]),
        "delta_maximum_drawdown_vs_v3": (
            _finite(
                all_1x["maximum_drawdown"],
                name="all_new_drawdown",
            )
            - baseline["maximum_drawdown"]
        ),
        "delta_two_x_return_vs_v3": (
            _finite(
                all_2x["net_return"],
                name="all_new_two_x_return",
            )
            - baseline["two_x_net_return"]
        ),
        "delta_capture_vs_v3": (
            all_evidence.mean_high_opportunity_capture - baseline["mean_high_opportunity_capture"]
        ),
        "robust_additive_overlay": bool(
            _finite(
                all_1x["net_return"],
                name="all_new_net_return",
            )
            > baseline["net_return"]
            and _metric_profit_factor(all_1x) >= baseline["profit_factor"] - 0.05
            and _finite(
                all_1x["maximum_drawdown"],
                name="all_new_drawdown",
            )
            <= baseline["maximum_drawdown"] + 0.05
            and bool(all_1x["capital_feasible"])
            and bool(all_2x["capital_feasible"])
        ),
    }
    cost_rows.extend(
        _cost_rows(
            all_evidence,
            scope="ALL_NEW_OVERLAY",
            variant_id=ALL_NEW_VARIANT_ID,
        )
    )
    annual_rows.extend(
        _annual_output_rows(
            all_evidence,
            scope="ALL_NEW_OVERLAY",
            variant_id=ALL_NEW_VARIANT_ID,
        )
    )
    bull_rows.extend(
        _bull_output_rows(
            all_evidence,
            scope="ALL_NEW_OVERLAY",
            variant_id=ALL_NEW_VARIANT_ID,
        )
    )
    routing_rows.extend(
        _routing_rows(
            all_overlay_evaluated,
            scope="ALL_NEW_OVERLAY",
            variant_id=ALL_NEW_VARIANT_ID,
        )
    )

    all_variant_directory = RD16N_LOCAL_ROOT / "variants" / "all-six-overlay"
    variant_manifest[ALL_NEW_VARIANT_ID] = {
        "evaluated": _write_local_frame(
            all_variant_directory / "evaluated.parquet",
            all_overlay_evaluated,
        ),
        "new_trades": _write_local_frame(
            all_variant_directory / "new-trades.parquet",
            all_overlay_new_enriched,
        ),
        "combined_trades": _write_local_frame(
            all_variant_directory / "combined-trades.parquet",
            all_combined,
        ),
        "equity_cost_1_0x": _write_local_frame(
            all_variant_directory / "equity-cost-1_0x.parquet",
            all_evidence.curves[1.0],
        ),
        "equity_cost_2_0x": _write_local_frame(
            all_variant_directory / "equity-cost-2_0x.parquet",
            all_evidence.curves[2.0],
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
        raise RD16NEvaluationError("RD16-N causal or sealed-period audit failed.")

    strategic_objective_met = strategic_count > 0
    if strategic_objective_met:
        next_stage = NEXT_PREHOLDOUT
    elif retained:
        next_stage = NEXT_ASSEMBLY
    else:
        next_stage = NEXT_REDESIGN

    final_report: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "decision": DECISION,
        "technical_status": "COMPLETED",
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "architecture_id": ARCHITECTURE_ID,
        "source_baseline_decision": source_report["decision"],
        "hypotheses_evaluated": len(HYPOTHESIS_REGISTRY),
        "retained_hypothesis_count": len(retained),
        "promising_hypothesis_count": len(promising),
        "rejected_hypothesis_count": len(rejected),
        "retained_hypotheses": retained,
        "promising_hypotheses": promising,
        "rejected_hypotheses": rejected,
        "strategic_objective_met_count": strategic_count,
        "strategic_objective_met": strategic_objective_met,
        "pre_registered_all_new_overlay": all_new_row,
        "winner_selected": False,
        "optimization_performed": False,
        "architecture_changed": False,
        "production_authorized": False,
        "next_stage": next_stage,
        "limitations": [
            "RD16-N is development-period new-signal research.",
            "The six hypotheses and thresholds were frozen before execution.",
            "Frozen V3 trades are preserved and never displaced.",
            "Retention is gate-based and is not winner selection.",
            "2025 and 2026 remain sealed.",
        ],
        "technical_gates": {
            "rd16m_ready": True,
            "rd16m_outputs_verified": True,
            "rd16l_local_ledgers_verified": True,
            "raw_market_data_verified": True,
            "six_hypotheses_pre_registered": (len(HYPOTHESIS_REGISTRY) == 6),
            "all_causality_checks_pass": causal_pass,
            "frozen_v3_trades_preserved": True,
            "maximum_positions_configured": (MAXIMUM_POSITIONS == 5),
            "maximum_open_risk_configured": (abs(MAXIMUM_OPEN_RISK_FRACTION - 0.0225) <= 1e-12),
            "spot_only": True,
            "long_only": True,
            "same_symbol_overlap_prohibited": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
            "architecture_changed": False,
            "production_authorized": False,
        },
    }

    _write_rows(
        RD16N_ROOT / "hypothesis-registry.csv",
        [hypothesis.to_record() for hypothesis in HYPOTHESIS_REGISTRY],
        fieldnames=tuple(HYPOTHESIS_REGISTRY[0].to_record()),
    )
    _write_rows(
        RD16N_ROOT / "family-summary.csv",
        family_rows,
        fieldnames=FAMILY_SUMMARY_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "component-decisions.csv",
        decision_rows,
        fieldnames=DECISION_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "cost-stress.csv",
        cost_rows,
        fieldnames=COST_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "family-coverage.csv",
        coverage_rows,
        fieldnames=COVERAGE_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "causality-audit.csv",
        causal_rows,
        fieldnames=CAUSAL_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "routing-decision-summary.csv",
        routing_rows,
        fieldnames=ROUTING_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "annual-performance.csv",
        annual_rows,
        fieldnames=ANNUAL_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "bull-window-capture.csv",
        bull_rows,
        fieldnames=BULL_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "new-engine-regime-attribution.csv",
        regime_rows,
        fieldnames=REGIME_FIELDS,
    )
    _write_rows(
        RD16N_ROOT / "all-new-overlay-summary.csv",
        [all_new_row],
        fieldnames=tuple(all_new_row),
    )
    write_json(
        RD16N_ROOT / "frozen-input-hashes.json",
        frozen_hashes,
    )
    write_json(
        RD16N_ROOT / "local-output-manifest-v1.json",
        local_manifest,
    )
    write_json(
        RD16N_ROOT / "rd16n-final-report-v1.json",
        final_report,
    )
    write_json(
        RD16N_ROOT / "validation-report.json",
        {
            "schema_version": SCHEMA_VERSION,
            "status": "PASS",
            "hypotheses_evaluated": len(HYPOTHESIS_REGISTRY),
            "causality_pass": causal_pass,
            "retained_hypothesis_count": len(retained),
            "promising_hypothesis_count": len(promising),
            "strategic_objective_met_count": strategic_count,
        },
    )

    report_paths = _write_reports(
        final_report=final_report,
        family_rows=family_rows,
        all_new_row=all_new_row,
    )
    tracked_outputs = [
        RD16N_ROOT / "hypothesis-registry.csv",
        RD16N_ROOT / "family-summary.csv",
        RD16N_ROOT / "component-decisions.csv",
        RD16N_ROOT / "cost-stress.csv",
        RD16N_ROOT / "family-coverage.csv",
        RD16N_ROOT / "causality-audit.csv",
        RD16N_ROOT / "routing-decision-summary.csv",
        RD16N_ROOT / "annual-performance.csv",
        RD16N_ROOT / "bull-window-capture.csv",
        RD16N_ROOT / "new-engine-regime-attribution.csv",
        RD16N_ROOT / "all-new-overlay-summary.csv",
        RD16N_ROOT / "frozen-input-hashes.json",
        RD16N_ROOT / "local-output-manifest-v1.json",
        RD16N_ROOT / "rd16n-final-report-v1.json",
        RD16N_ROOT / "validation-report.json",
        *report_paths,
    ]
    write_json(
        RD16N_ROOT / "output-hashes.json",
        {path.name: sha256_path(path) for path in tracked_outputs},
    )
    return final_report


__all__ = [
    "ALL_NEW_VARIANT_ID",
    "DECISION",
    "EVIDENCE_CLASSIFICATION",
    "HypothesisDecision",
    "PortfolioEvidence",
    "RD16NEvaluationError",
    "classify_hypothesis",
    "evaluate_candidate",
    "evaluate_candidates",
    "intervals_overlap",
    "route_overlay_candidates",
    "route_standalone_candidates",
    "run_rd16n_research",
]
