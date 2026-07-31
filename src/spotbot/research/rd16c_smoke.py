from __future__ import annotations

import hashlib
import json
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
    LOCAL_OUTPUT_ROOT,
    PILOT_SYMBOLS,
    RD16C_ROOT,
    REPORTS_ROOT,
    SEALED_CUTOFF,
    SIGNAL_TIMEFRAME,
    RD16CInputError,
    dataframe_content_hash,
    frozen_input_hashes,
    iso,
    sha256_path,
    verify_rd16b_ready,
    write_csv,
    write_json,
)
from spotbot.research.rd16c_families import (
    FAMILY_REGISTRY,
    FamilyRegistration,
    build_candidate_frame,
)
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16c_reporting import write_reports

SCHEMA_VERSION: Final = "rd16c-registered-families-smoke-v1"
DECISION_COMPLETED: Final = "RD16C_REGISTERED_INTRADAY_STRATEGY_FAMILIES_SMOKE_TESTS_COMPLETED"
DECISION_REMEDIATE: Final = "RD16C_REGISTERED_FAMILY_REMEDIATION_REQUIRED"
NEXT_READY: Final = "RD16D_FIXED_INTRADAY_FAMILY_BASELINE_EVALUATION"
NEXT_REMEDIATE: Final = "RD16C_REGISTERED_FAMILY_REMEDIATION"

INITIAL_EQUITY: Final = 100_000.0
RISK_PER_TRADE_FRACTION: Final = 0.005
MAXIMUM_OPEN_RISK_FRACTION: Final = 0.015
MAXIMUM_POSITIONS: Final = 3
FEE_RATE: Final = 0.001
MAXIMUM_NOTIONAL_PER_POSITION: Final = INITIAL_EQUITY / MAXIMUM_POSITIONS / (1.0 + FEE_RATE)
PROFIT_FLOOR_TRIGGER_R: Final = 1.5
PROFIT_FLOOR_LOCK_R: Final = 0.25
SECOND_PROFIT_TRIGGER_R: Final = 2.5
SECOND_PROFIT_LOCK_R: Final = 1.0

REGISTRATION_FIELDS: Final = (
    "family_id",
    "description",
    "stop_atr_multiple",
    "maximum_holding_bars",
    "fixed_parameters",
)
SUMMARY_FIELDS: Final = (
    "family_id",
    "status",
    "candidate_count",
    "candidate_assets",
    "evaluated_count",
    "admitted_trade_count",
    "traded_assets",
    "diagnostic_net_return",
    "diagnostic_profit_factor",
    "diagnostic_win_rate",
    "next_bar_violations",
    "future_context_violations",
    "maximum_positions_observed",
    "maximum_open_risk_fraction",
    "rejected_max_positions",
    "rejected_same_asset",
    "rejected_invalid_risk",
)
COVERAGE_FIELDS: Final = (
    "family_id",
    "symbol",
    "candidate_count",
    "evaluated_count",
    "admitted_trade_count",
    "first_signal_close",
    "last_signal_close",
)
CAUSAL_FIELDS: Final = (
    "family_id",
    "symbol",
    "candidate_count",
    "next_bar_violations",
    "future_4h_context_violations",
    "future_1d_context_violations",
    "future_1w_context_violations",
)
CONSTRAINT_FIELDS: Final = (
    "family_id",
    "spot_only",
    "long_only",
    "no_leverage",
    "no_margin",
    "no_short",
    "no_dca",
    "no_kelly",
    "no_pyramiding",
    "no_averaging_down",
    "maximum_positions_respected",
    "maximum_open_risk_respected",
    "next_bar_execution",
    "hard_stop_first",
)


@dataclass(frozen=True, slots=True)
class FamilyRun:
    registration: FamilyRegistration
    candidates: pd.DataFrame
    evaluated: pd.DataFrame
    trades: pd.DataFrame
    summary: dict[str, object]
    coverage_rows: tuple[dict[str, object], ...]
    causal_rows: tuple[dict[str, object], ...]
    constraint_row: dict[str, object]


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _float(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16CInputError(f"{name} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16CInputError(f"{name} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16CInputError(f"{name} must be finite.")
    return result


def _integer(value: object, *, name: str) -> int:
    if isinstance(value, bool):
        raise RD16CInputError(f"{name} cannot be boolean.")
    try:
        return int(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16CInputError(f"{name} must be integer-compatible.") from error


def _normalize_hourly(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["timestamp"] = pd.to_datetime(
        normalized["timestamp"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    normalized = normalized.sort_values(
        "timestamp",
        kind="stable",
    ).reset_index(drop=True)
    if bool((normalized["timestamp"] > pd.Timestamp(SEALED_CUTOFF)).any()):
        raise RD16CInputError("A 2025+ candle was detected in RD16-C input.")
    return normalized


def _bar_position_map(
    bars: pd.DataFrame,
) -> dict[pd.Timestamp, int]:
    return {
        _timestamp(value): position for position, value in enumerate(bars["timestamp"].tolist())
    }


def _evaluate_candidate(
    candidate: Mapping[str, object],
    *,
    bars: pd.DataFrame,
    registration: FamilyRegistration,
    bar_positions: Mapping[pd.Timestamp, int] | None = None,
) -> dict[str, object] | None:
    entry_bar_close = _timestamp(candidate["entry_bar_close"])
    positions = bar_positions if bar_positions is not None else _bar_position_map(bars)
    entry_position = positions.get(entry_bar_close)
    if entry_position is None:
        return None
    entry_price = _float(
        candidate["entry_price"],
        name="entry_price",
    )
    atr = _float(
        candidate["atr14_at_signal"],
        name="atr14_at_signal",
    )
    risk_per_unit = registration.stop_atr_multiple * atr
    initial_stop = entry_price - risk_per_unit
    if entry_price <= 0.0 or atr <= 0.0 or risk_per_unit <= 0.0 or initial_stop <= 0.0:
        return None

    current_stop = initial_stop
    profit_floor_active = False
    exit_price = entry_price
    exit_bar_close = entry_bar_close
    exit_reason = "TIME_EXIT"
    bars_held = 0
    last_position = min(
        entry_position + registration.maximum_holding_bars - 1,
        len(bars) - 1,
    )

    for position in range(entry_position, last_position + 1):
        row = bars.iloc[position]
        bar_low = _float(row["low"], name="bar_low")
        bar_high = _float(row["high"], name="bar_high")
        bar_close = _float(row["close"], name="bar_close")
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

    risk_budget = INITIAL_EQUITY * RISK_PER_TRADE_FRACTION
    quantity = min(
        risk_budget / risk_per_unit,
        MAXIMUM_NOTIONAL_PER_POSITION / entry_price,
    )
    if quantity <= 0.0:
        return None
    entry_fee = quantity * entry_price * FEE_RATE
    exit_fee = quantity * exit_price * FEE_RATE
    gross_pnl = quantity * (exit_price - entry_price)
    net_pnl = gross_pnl - entry_fee - exit_fee

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
        "fees": entry_fee + exit_fee,
        "net_pnl": net_pnl,
        "return_on_initial_equity": net_pnl / INITIAL_EQUITY,
        "side": "LONG",
        "instrument_type": "SPOT",
    }


def _admit_trades(
    evaluated: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int | float]]:
    if evaluated.empty:
        return evaluated.copy(), {
            "maximum_positions_observed": 0,
            "maximum_open_risk_fraction": 0.0,
            "rejected_max_positions": 0,
            "rejected_same_asset": 0,
            "rejected_invalid_risk": 0,
        }

    ordered = evaluated.sort_values(
        by=["entry_open_time", "symbol", "signal_close"],
        kind="stable",
    ).reset_index(drop=True)
    open_trades: list[dict[str, object]] = []
    admitted: list[dict[str, object]] = []
    rejected_max_positions = 0
    rejected_same_asset = 0
    rejected_invalid_risk = 0
    maximum_positions_observed = 0
    maximum_open_risk_fraction = 0.0

    for raw_record in ordered.to_dict(orient="records"):
        record = cast(dict[str, object], raw_record)
        entry_open_time = _timestamp(record["entry_open_time"])
        open_trades = [
            open_trade
            for open_trade in open_trades
            if _timestamp(open_trade["exit_bar_close"]) > entry_open_time
        ]
        symbol = str(record["symbol"])
        if any(str(open_trade["symbol"]) == symbol for open_trade in open_trades):
            rejected_same_asset += 1
            continue
        if len(open_trades) >= MAXIMUM_POSITIONS:
            rejected_max_positions += 1
            continue
        risk_budget = _float(
            record["risk_budget"],
            name="risk_budget",
        )
        if risk_budget <= 0.0:
            rejected_invalid_risk += 1
            continue
        open_risk_fraction = (
            sum(
                _float(
                    open_trade["risk_budget"],
                    name="open_risk_budget",
                )
                for open_trade in open_trades
            )
            + risk_budget
        ) / INITIAL_EQUITY
        if open_risk_fraction > MAXIMUM_OPEN_RISK_FRACTION + 1e-12:
            rejected_max_positions += 1
            continue

        admitted_record = dict(record)
        admitted_record["trade_id"] = f"{record['family_id']}:{len(admitted) + 1:06d}"
        admitted.append(admitted_record)
        open_trades.append(admitted_record)
        maximum_positions_observed = max(
            maximum_positions_observed,
            len(open_trades),
        )
        maximum_open_risk_fraction = max(
            maximum_open_risk_fraction,
            open_risk_fraction,
        )

    return pd.DataFrame.from_records(admitted), {
        "maximum_positions_observed": maximum_positions_observed,
        "maximum_open_risk_fraction": maximum_open_risk_fraction,
        "rejected_max_positions": rejected_max_positions,
        "rejected_same_asset": rejected_same_asset,
        "rejected_invalid_risk": rejected_invalid_risk,
    }


def _diagnostic_profit_factor(trades: pd.DataFrame) -> float | None:
    if trades.empty:
        return None
    pnl = pd.to_numeric(trades["net_pnl"], errors="coerce")
    gross_profit = float(pnl[pnl > 0.0].sum())
    gross_loss = abs(float(pnl[pnl < 0.0].sum()))
    if gross_loss == 0.0:
        return None
    return gross_profit / gross_loss


def _family_run(
    registration: FamilyRegistration,
    *,
    feature_frames: Mapping[str, pd.DataFrame],
    hourly_frames: Mapping[str, pd.DataFrame],
    bar_position_maps: Mapping[str, Mapping[pd.Timestamp, int]],
) -> FamilyRun:
    candidate_frames: list[pd.DataFrame] = []
    coverage_rows: list[dict[str, object]] = []
    causal_rows: list[dict[str, object]] = []

    for symbol in PILOT_SYMBOLS:
        candidates = build_candidate_frame(
            feature_frames[symbol],
            symbol=symbol,
            registration=registration,
        )
        candidate_frames.append(candidates)
        if candidates.empty:
            first_signal = ""
            last_signal = ""
        else:
            first_signal = iso(candidates["signal_close"].min())
            last_signal = iso(candidates["signal_close"].max())
        next_bar_violations = 0
        future_4h = 0
        future_1d = 0
        future_1w = 0
        if not candidates.empty:
            signal_close = pd.to_datetime(candidates["signal_close"], utc=True)
            entry_bar_close = pd.to_datetime(candidates["entry_bar_close"], utc=True)
            next_bar_violations = int(
                (entry_bar_close - signal_close != pd.Timedelta(hours=1)).sum()
            )
            future_4h = int(
                (pd.to_datetime(candidates["4h_context_close"], utc=True) > signal_close).sum()
            )
            future_1d = int(
                (pd.to_datetime(candidates["1d_context_close"], utc=True) > signal_close).sum()
            )
            future_1w = int(
                (pd.to_datetime(candidates["1w_context_close"], utc=True) > signal_close).sum()
            )
        coverage_rows.append(
            {
                "family_id": registration.family_id,
                "symbol": symbol,
                "candidate_count": len(candidates),
                "evaluated_count": 0,
                "admitted_trade_count": 0,
                "first_signal_close": first_signal,
                "last_signal_close": last_signal,
            }
        )
        causal_rows.append(
            {
                "family_id": registration.family_id,
                "symbol": symbol,
                "candidate_count": len(candidates),
                "next_bar_violations": next_bar_violations,
                "future_4h_context_violations": future_4h,
                "future_1d_context_violations": future_1d,
                "future_1w_context_violations": future_1w,
            }
        )

    candidates_all = (
        pd.concat(candidate_frames, ignore_index=True)
        if any(not frame.empty for frame in candidate_frames)
        else pd.DataFrame()
    )
    evaluated_records: list[dict[str, object]] = []
    if not candidates_all.empty:
        for raw_candidate in candidates_all.to_dict(orient="records"):
            candidate = cast(dict[str, object], raw_candidate)
            symbol = str(candidate["symbol"])
            evaluated = _evaluate_candidate(
                candidate,
                bars=hourly_frames[symbol],
                registration=registration,
                bar_positions=bar_position_maps[symbol],
            )
            if evaluated is not None:
                evaluated_records.append(evaluated)
    evaluated_frame = pd.DataFrame.from_records(evaluated_records)
    trades, admission = _admit_trades(evaluated_frame)

    for row in coverage_rows:
        symbol = str(row["symbol"])
        if not evaluated_frame.empty:
            row["evaluated_count"] = int((evaluated_frame["symbol"] == symbol).sum())
        if not trades.empty:
            row["admitted_trade_count"] = int((trades["symbol"] == symbol).sum())

    candidate_assets = sum(
        _integer(row["candidate_count"], name="candidate_count") > 0 for row in coverage_rows
    )
    traded_assets = sum(
        _integer(
            row["admitted_trade_count"],
            name="admitted_trade_count",
        )
        > 0
        for row in coverage_rows
    )
    next_bar_violations = sum(
        _integer(
            row["next_bar_violations"],
            name="next_bar_violations",
        )
        for row in causal_rows
    )
    future_context_violations = sum(
        _integer(
            row["future_4h_context_violations"],
            name="future_4h_context_violations",
        )
        + _integer(
            row["future_1d_context_violations"],
            name="future_1d_context_violations",
        )
        + _integer(
            row["future_1w_context_violations"],
            name="future_1w_context_violations",
        )
        for row in causal_rows
    )
    diagnostic_net_return = (
        float(pd.to_numeric(trades["net_pnl"], errors="coerce").sum()) / INITIAL_EQUITY
        if not trades.empty
        else 0.0
    )
    diagnostic_win_rate = (
        float((pd.to_numeric(trades["net_pnl"], errors="coerce") > 0.0).mean())
        if not trades.empty
        else 0.0
    )
    status = "PASS"
    if (
        len(candidates_all) == 0
        or len(trades) == 0
        or candidate_assets < 2
        or traded_assets < 2
        or next_bar_violations != 0
        or future_context_violations != 0
        or int(admission["maximum_positions_observed"]) > MAXIMUM_POSITIONS
        or float(admission["maximum_open_risk_fraction"]) > MAXIMUM_OPEN_RISK_FRACTION + 1e-12
    ):
        status = "FAIL"

    summary: dict[str, object] = {
        "family_id": registration.family_id,
        "status": status,
        "candidate_count": len(candidates_all),
        "candidate_assets": candidate_assets,
        "evaluated_count": len(evaluated_frame),
        "admitted_trade_count": len(trades),
        "traded_assets": traded_assets,
        "diagnostic_net_return": diagnostic_net_return,
        "diagnostic_profit_factor": _diagnostic_profit_factor(trades),
        "diagnostic_win_rate": diagnostic_win_rate,
        "next_bar_violations": next_bar_violations,
        "future_context_violations": future_context_violations,
        **admission,
    }
    constraint_row = {
        "family_id": registration.family_id,
        "spot_only": True,
        "long_only": bool(trades.empty or (trades["instrument_type"] == "SPOT").all()),
        "no_leverage": bool(
            trades.empty
            or (
                pd.to_numeric(trades["notional"], errors="coerce")
                <= MAXIMUM_NOTIONAL_PER_POSITION + 1e-9
            ).all()
        ),
        "no_margin": True,
        "no_short": bool(trades.empty or (trades["side"] == "LONG").all()),
        "no_dca": True,
        "no_kelly": True,
        "no_pyramiding": True,
        "no_averaging_down": True,
        "maximum_positions_respected": (
            int(admission["maximum_positions_observed"]) <= MAXIMUM_POSITIONS
        ),
        "maximum_open_risk_respected": (
            float(admission["maximum_open_risk_fraction"]) <= MAXIMUM_OPEN_RISK_FRACTION + 1e-12
        ),
        "next_bar_execution": next_bar_violations == 0,
        "hard_stop_first": True,
    }
    return FamilyRun(
        registration=registration,
        candidates=candidates_all,
        evaluated=evaluated_frame,
        trades=trades,
        summary=summary,
        coverage_rows=tuple(coverage_rows),
        causal_rows=tuple(causal_rows),
        constraint_row=constraint_row,
    )


def _run_all_families(
    *,
    feature_frames: Mapping[str, pd.DataFrame],
    hourly_frames: Mapping[str, pd.DataFrame],
    bar_position_maps: Mapping[str, Mapping[pd.Timestamp, int]],
) -> tuple[FamilyRun, ...]:
    return tuple(
        _family_run(
            registration,
            feature_frames=feature_frames,
            hourly_frames=hourly_frames,
            bar_position_maps=bar_position_maps,
        )
        for registration in FAMILY_REGISTRY
    )


def _save_local_ledgers(
    runs: Sequence[FamilyRun],
    *,
    local_output_root: Path,
) -> dict[str, object]:
    if local_output_root.exists():
        shutil.rmtree(local_output_root)
    local_output_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "root_committed": False,
        "families": {},
    }
    families_manifest: dict[str, object] = {}
    for run in runs:
        family_id = run.registration.family_id
        family_directory = local_output_root / family_id.lower()
        family_directory.mkdir(parents=True, exist_ok=True)
        entries: dict[str, object] = {}
        for name, frame in (
            ("candidates", run.candidates),
            ("evaluated", run.evaluated),
            ("trades", run.trades),
        ):
            path = family_directory / f"{name}.parquet"
            frame.to_parquet(path, index=False, engine="pyarrow")
            entries[name] = {
                "logical_path": str(path.relative_to(local_output_root)).replace("\\", "/"),
                "rows": len(frame),
                "file_sha256": sha256_path(path),
                "content_sha256": dataframe_content_hash(frame),
            }
        families_manifest[family_id] = entries
    manifest["families"] = families_manifest
    return manifest


def _output_hashes() -> dict[str, str]:
    names = (
        "family-registration.csv",
        "family-smoke-summary.csv",
        "asset-family-coverage.csv",
        "causality-audit.csv",
        "constraint-audit.csv",
        "local-ledger-manifest-v1.json",
        "frozen-input-hashes.json",
        "rd16c-final-report-v1.json",
        "validation-report.json",
    )
    return {name: sha256_path(RD16C_ROOT / name) for name in names}


def _serialize_run_hashes(
    runs: Sequence[FamilyRun],
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for run in runs:
        family_id = run.registration.family_id
        hashes[f"{family_id}:candidates"] = dataframe_content_hash(run.candidates)
        hashes[f"{family_id}:evaluated"] = dataframe_content_hash(run.evaluated)
        hashes[f"{family_id}:trades"] = dataframe_content_hash(run.trades)
        summary_payload = json.dumps(
            run.summary,
            sort_keys=True,
            allow_nan=False,
            default=str,
        )
        hashes[f"{family_id}:summary"] = hashlib.sha256(summary_payload.encode("utf-8")).hexdigest()
    return dict(sorted(hashes.items()))


def run_rd16c(
    *,
    store_root: Path = LOCAL_INPUT_ROOT,
    local_output_root: Path = LOCAL_OUTPUT_ROOT,
) -> dict[str, Any]:
    verify_rd16b_ready()
    frozen_before = frozen_input_hashes(store_root)
    store = ParquetCandleStore(store_root)
    feature_frames: dict[str, pd.DataFrame] = {}
    hourly_frames: dict[str, pd.DataFrame] = {}
    bar_position_maps: dict[str, dict[pd.Timestamp, int]] = {}

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
        hourly = _normalize_hourly(frames[SIGNAL_TIMEFRAME])
        hourly_frames[symbol] = hourly
        bar_position_maps[symbol] = _bar_position_map(hourly)
        feature_frames[symbol] = build_feature_frame(
            frames,
            symbol=symbol,
        )

    first_runs = _run_all_families(
        feature_frames=feature_frames,
        hourly_frames=hourly_frames,
        bar_position_maps=bar_position_maps,
    )
    replay_runs = _run_all_families(
        feature_frames=feature_frames,
        hourly_frames=hourly_frames,
        bar_position_maps=bar_position_maps,
    )
    first_hashes = _serialize_run_hashes(first_runs)
    replay_hashes = _serialize_run_hashes(replay_runs)
    deterministic_replay_match = first_hashes == replay_hashes
    frozen_after = frozen_input_hashes(store_root)
    frozen_inputs_unchanged = frozen_before == frozen_after
    local_manifest = _save_local_ledgers(
        first_runs,
        local_output_root=local_output_root,
    )

    registration_rows = [registration.to_record() for registration in FAMILY_REGISTRY]
    summary_rows = [run.summary for run in first_runs]
    coverage_rows = [row for run in first_runs for row in run.coverage_rows]
    causal_rows = [row for run in first_runs for row in run.causal_rows]
    constraint_rows = [run.constraint_row for run in first_runs]

    families_passed = sum(row["status"] == "PASS" for row in summary_rows)
    all_constraints_pass = all(
        all(bool(value) for key, value in row.items() if key != "family_id")
        for row in constraint_rows
    )
    all_causal_pass = all(
        _integer(
            row["next_bar_violations"],
            name="next_bar_violations",
        )
        == 0
        and _integer(
            row["future_4h_context_violations"],
            name="future_4h_context_violations",
        )
        == 0
        and _integer(
            row["future_1d_context_violations"],
            name="future_1d_context_violations",
        )
        == 0
        and _integer(
            row["future_1w_context_violations"],
            name="future_1w_context_violations",
        )
        == 0
        for row in causal_rows
    )
    technical_pass = (
        families_passed == len(FAMILY_REGISTRY)
        and deterministic_replay_match
        and frozen_inputs_unchanged
        and all_constraints_pass
        and all_causal_pass
    )
    classification = "READY_FOR_FIXED_BASELINE" if technical_pass else "REMEDIATION_REQUIRED"
    decision = DECISION_COMPLETED if technical_pass else DECISION_REMEDIATE
    next_stage = NEXT_READY if technical_pass else NEXT_REMEDIATE

    final: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "branch": BRANCH,
        "baseline_commit": ("715b771d72114e38bc5fbe4816e942dcb41f45cf"),
        "decision": decision,
        "technical_status": ("COMPLETED" if technical_pass else "FAILED"),
        "evidence_classification": classification,
        "families_passed": families_passed,
        "families_total": len(FAMILY_REGISTRY),
        "assets_total": len(PILOT_SYMBOLS),
        "next_stage": next_stage,
        "performance_used_as_gate": False,
        "winner_selected": False,
        "optimization_performed": False,
        "family_summaries": summary_rows,
        "technical_gates": {
            "all_four_families_registered": (len(FAMILY_REGISTRY) == 4),
            "all_four_families_smoke_pass": (families_passed == 4),
            "all_constraints_pass": all_constraints_pass,
            "all_causal_checks_pass": all_causal_pass,
            "deterministic_replay_match": (deterministic_replay_match),
            "frozen_inputs_unchanged": frozen_inputs_unchanged,
            "spot_only": True,
            "long_only": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dune_api_called": False,
            "optimization_performed": False,
            "winner_selected": False,
        },
        "limitations": [
            "RD16-C is a smoke test, not a strategic performance evaluation.",
            "Diagnostic returns do not determine pass/fail and are not used to rank families.",
            "The pilot universe remains fixed and is not yet a point-in-time production universe.",
            "Detailed candidate and trade ledgers remain local under data/raw/rd16c.",
        ],
    }
    validation = {
        "status": "PASS" if technical_pass else "FAIL",
        **cast(dict[str, object], final["technical_gates"]),
    }

    write_csv(
        RD16C_ROOT / "family-registration.csv",
        registration_rows,
        fieldnames=REGISTRATION_FIELDS,
    )
    write_csv(
        RD16C_ROOT / "family-smoke-summary.csv",
        summary_rows,
        fieldnames=SUMMARY_FIELDS,
    )
    write_csv(
        RD16C_ROOT / "asset-family-coverage.csv",
        coverage_rows,
        fieldnames=COVERAGE_FIELDS,
    )
    write_csv(
        RD16C_ROOT / "causality-audit.csv",
        causal_rows,
        fieldnames=CAUSAL_FIELDS,
    )
    write_csv(
        RD16C_ROOT / "constraint-audit.csv",
        constraint_rows,
        fieldnames=CONSTRAINT_FIELDS,
    )
    write_json(
        RD16C_ROOT / "local-ledger-manifest-v1.json",
        local_manifest,
    )
    write_json(
        RD16C_ROOT / "frozen-input-hashes.json",
        frozen_before,
    )
    write_json(
        RD16C_ROOT / "rd16c-final-report-v1.json",
        final,
    )
    write_json(
        RD16C_ROOT / "validation-report.json",
        validation,
    )
    write_reports(
        final=final,
        registration_rows=registration_rows,
        summary_rows=summary_rows,
        coverage_rows=coverage_rows,
        constraint_rows=constraint_rows,
        reports_root=REPORTS_ROOT,
    )
    write_json(
        RD16C_ROOT / "output-hashes.json",
        _output_hashes(),
    )
    return final
