from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.run_rd16pit_a2 import control_replay  # noqa: E402
from spotbot.research import rd16m_evaluation as rd16m  # noqa: E402
from spotbot.research.rd16c_common import ROOT  # noqa: E402
from spotbot.research.rd16d_common import (  # noqa: E402
    BASE_FEE_RATE,
    COST_MULTIPLIERS,
    INITIAL_EQUITY,
)
from spotbot.research.rd16d_metrics import build_equity_curve  # noqa: E402
from spotbot.research.rd16l_registration import load_source_ledgers  # noqa: E402

SCHEMA_VERSION: Final = "rd16-pit-a2a-cash-equity-floor-provenance-v1"
SOURCE_COMMIT: Final = "3700cc452990a737947ee2a1ffd0eaf20571698a"
STAGE: Final = "RD16_PIT_A2A_CASH_EQUITY_FLOOR_PROVENANCE_AUDIT"
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00Z")

A2_ROOT: Final = ROOT / "data" / "research" / "rd16pit_a2"
A2A_ROOT: Final = ROOT / "data" / "research" / "rd16pit_a2a"
REPORTS_ROOT: Final = ROOT / "reports" / "research"

SCOPES: Final = (
    "FROZEN_V3_CONTROL",
    "PIT_DYNAMIC_REROUTE",
)
FLOOR_TYPES: Final = (
    "MINIMUM_CASH",
    "MINIMUM_EQUITY",
)
COMPARE_COLUMNS: Final = (
    "cash",
    "market_value",
    "equity",
    "open_positions",
    "gross_exposure",
    "cumulative_fees",
    "drawdown",
)


class A2AError(RuntimeError):
    pass


def timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def finite(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise A2AError(f"{field} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise A2AError(f"{field} must be numeric.") from error
    if not math.isfinite(numeric):
        raise A2AError(f"{field} must be finite.")
    return numeric


def scalar_int(value: object, *, field: str) -> int:
    numeric = finite(value, field=field)
    if not numeric.is_integer():
        raise A2AError(f"{field} must be integer-compatible.")
    return int(numeric)


def records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], frame.to_dict(orient="records"))


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, pd.Timestamp):
        return timestamp(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(item) for item in value]
    return str(value)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            json_safe(dict(payload)),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def frame_hash(frame: pd.DataFrame, columns: Sequence[str]) -> str:
    working = frame.loc[:, list(columns)].copy()
    for column in working.columns:
        if pd.api.types.is_datetime64_any_dtype(working[column]):
            working[column] = pd.to_datetime(
                cast(Any, working[column]),
                utc=True,
            ).map(lambda value: timestamp(value).isoformat())
    payload = working.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return sha256_bytes(payload)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_trades(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "trade_id",
        "symbol",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
        "quantity",
        "entry_price",
        "exit_price",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise A2AError(f"Trade columns missing: {missing}")
    result = frame.copy()
    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
    ):
        result[column] = pd.to_datetime(
            cast(Any, result[column]),
            utc=True,
            errors="raise",
        )
        if bool(result[column].ge(SEALED_CUTOFF).any()):
            raise A2AError(f"Sealed cutoff violation in {column}.")
    for column in ("quantity", "entry_price", "exit_price"):
        result[column] = pd.to_numeric(
            cast(Any, result[column]),
            errors="raise",
        )
    if bool(result["trade_id"].astype(str).duplicated().any()):
        raise A2AError("Trade IDs must be unique.")
    return result.sort_values(
        ["entry_open_time", "symbol", "signal_close"],
        kind="stable",
    ).reset_index(drop=True)


def close_price_maps(
    hourly_frames: Mapping[str, pd.DataFrame],
) -> dict[str, dict[pd.Timestamp, float]]:
    output: dict[str, dict[pd.Timestamp, float]] = {}
    for symbol, raw in hourly_frames.items():
        frame = raw.loc[:, ["timestamp", "close"]].copy()
        frame["timestamp"] = pd.to_datetime(
            cast(Any, frame["timestamp"]),
            utc=True,
            errors="raise",
        )
        output[symbol] = {
            timestamp(raw_time): finite(raw_close, field="hourly_close")
            for raw_time, raw_close in frame.itertuples(index=False, name=None)
        }
    return output


def independent_equity_curve(
    trades: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
    timeline: pd.DatetimeIndex,
    cost_multiplier: float,
) -> pd.DataFrame:
    if cost_multiplier <= 0.0 or not math.isfinite(cost_multiplier):
        raise A2AError("cost_multiplier must be positive and finite.")
    normalized = normalized_trades(trades)
    close_maps = close_price_maps(hourly_frames)

    entry_events: dict[pd.Timestamp, list[dict[str, object]]] = {}
    exit_events: dict[pd.Timestamp, list[dict[str, object]]] = {}
    for row in records(normalized):
        entry_events.setdefault(timestamp(row["entry_open_time"]), []).append(row)
        exit_events.setdefault(timestamp(row["exit_bar_close"]), []).append(row)

    cash = INITIAL_EQUITY
    cumulative_fees = 0.0
    open_positions: dict[str, dict[str, object]] = {}
    rows: list[dict[str, object]] = []

    for raw_time in timeline:
        current = timestamp(raw_time)
        cash_before_events = cash
        exit_notional = 0.0
        exit_fees = 0.0
        entry_notional = 0.0
        entry_fees = 0.0
        exiting_ids: list[str] = []
        entering_ids: list[str] = []

        for row in exit_events.get(current, []):
            trade_id = str(row["trade_id"])
            if open_positions.pop(trade_id, None) is None:
                raise A2AError(f"Exit without open position: {trade_id}")
            quantity = finite(row["quantity"], field="quantity")
            exit_price = finite(row["exit_price"], field="exit_price")
            notional = quantity * exit_price
            fee = notional * BASE_FEE_RATE * cost_multiplier
            exit_notional += notional
            exit_fees += fee
            cash += notional - fee
            cumulative_fees += fee
            exiting_ids.append(trade_id)

        for row in entry_events.get(current, []):
            trade_id = str(row["trade_id"])
            if trade_id in open_positions:
                raise A2AError(f"Duplicate open trade: {trade_id}")
            quantity = finite(row["quantity"], field="quantity")
            entry_price = finite(row["entry_price"], field="entry_price")
            notional = quantity * entry_price
            fee = notional * BASE_FEE_RATE * cost_multiplier
            entry_notional += notional
            entry_fees += fee
            cash -= notional + fee
            cumulative_fees += fee
            open_positions[trade_id] = row
            entering_ids.append(trade_id)

        market_value = 0.0
        symbols: list[str] = []
        for position in open_positions.values():
            symbol = str(position["symbol"])
            symbols.append(symbol)
            entry_time = timestamp(position["entry_open_time"])
            if current == entry_time:
                mark = finite(position["entry_price"], field="entry_price")
            else:
                mark_value = close_maps.get(symbol, {}).get(current)
                if mark_value is None:
                    raise A2AError(f"Missing mark for {symbol} at {current}.")
                mark = mark_value
            market_value += finite(position["quantity"], field="quantity") * mark

        equity = cash + market_value
        cash_identity = cash_before_events + exit_notional - exit_fees - entry_notional - entry_fees
        rows.append(
            {
                "timestamp": current,
                "cash_before_events": cash_before_events,
                "exit_notional": exit_notional,
                "exit_fees": exit_fees,
                "entry_notional": entry_notional,
                "entry_fees": entry_fees,
                "cash": cash,
                "free_cash": cash,
                "reserved_cash": 0.0,
                "market_value": market_value,
                "equity": equity,
                "open_positions": len(open_positions),
                "gross_exposure": (market_value / equity if equity != 0.0 else None),
                "cumulative_fees": cumulative_fees,
                "cash_identity_error": cash - cash_identity,
                "equity_identity_error": equity - (cash + market_value),
                "entering_trade_ids": "|".join(sorted(entering_ids)),
                "exiting_trade_ids": "|".join(sorted(exiting_ids)),
                "open_trade_ids": "|".join(sorted(open_positions)),
                "open_symbols": "|".join(sorted(set(symbols))),
            }
        )

    if open_positions:
        raise A2AError(f"Open positions remain after timeline: {sorted(open_positions)}")

    curve = pd.DataFrame(rows)
    peaks = pd.to_numeric(
        cast(Any, curve["equity"]),
        errors="raise",
    ).cummax()
    curve["drawdown"] = pd.to_numeric(cast(Any, curve["equity"]), errors="raise") / peaks - 1.0
    return curve


def compare_curves(
    official: pd.DataFrame,
    independent: pd.DataFrame,
    *,
    scope: str,
    multiplier: float,
    saved: pd.DataFrame | None,
) -> dict[str, object]:
    if len(official) != len(independent):
        raise A2AError("Official and independent curves have different lengths.")
    official_time = pd.to_datetime(
        cast(Any, official["timestamp"]),
        utc=True,
    )
    independent_time = pd.to_datetime(
        cast(Any, independent["timestamp"]),
        utc=True,
    )
    timestamps_equal = bool(official_time.equals(independent_time))

    maximum_deltas: dict[str, float] = {}
    exact_columns: dict[str, bool] = {}
    for column in COMPARE_COLUMNS:
        left = pd.to_numeric(cast(Any, official[column]), errors="coerce")
        right = pd.to_numeric(
            cast(Any, independent[column]),
            errors="coerce",
        )
        delta = (left - right).abs()
        maximum = float(delta.fillna(0.0).max())
        maximum_deltas[column] = maximum
        exact_columns[column] = bool(
            np.allclose(
                left.to_numpy(dtype=float),
                right.to_numpy(dtype=float),
                rtol=0.0,
                atol=1e-8,
                equal_nan=True,
            )
        )

    saved_match: bool | None = None
    if saved is not None:
        if len(saved) != len(official):
            saved_match = False
        else:
            saved_match = all(
                bool(
                    np.allclose(
                        pd.to_numeric(
                            cast(Any, saved[column]),
                            errors="coerce",
                        ).to_numpy(dtype=float),
                        pd.to_numeric(
                            cast(Any, official[column]),
                            errors="coerce",
                        ).to_numpy(dtype=float),
                        rtol=0.0,
                        atol=1e-8,
                        equal_nan=True,
                    )
                )
                for column in COMPARE_COLUMNS
            ) and bool(
                pd.to_datetime(
                    cast(Any, saved["timestamp"]),
                    utc=True,
                ).equals(official_time)
            )

    return {
        "scope": scope,
        "cost_multiplier": multiplier,
        "row_count": len(official),
        "timestamps_equal": timestamps_equal,
        "official_independent_match": (timestamps_equal and all(exact_columns.values())),
        "saved_official_match": saved_match,
        "official_curve_hash": frame_hash(
            official,
            ("timestamp", *COMPARE_COLUMNS),
        ),
        "independent_curve_hash": frame_hash(
            independent,
            ("timestamp", *COMPARE_COLUMNS),
        ),
        **{f"max_abs_delta_{column}": value for column, value in maximum_deltas.items()},
    }


def floor_signature(row: Mapping[str, object]) -> str:
    payload = {
        "timestamp": timestamp(row["timestamp"]).isoformat(),
        "cash_before_events": finite(
            row["cash_before_events"],
            field="cash_before_events",
        ),
        "exit_notional": finite(row["exit_notional"], field="exit_notional"),
        "exit_fees": finite(row["exit_fees"], field="exit_fees"),
        "entry_notional": finite(
            row["entry_notional"],
            field="entry_notional",
        ),
        "entry_fees": finite(row["entry_fees"], field="entry_fees"),
        "cash": finite(row["cash"], field="cash"),
        "market_value": finite(row["market_value"], field="market_value"),
        "equity": finite(row["equity"], field="equity"),
        "open_trade_ids": str(row["open_trade_ids"]),
        "entering_trade_ids": str(row["entering_trade_ids"]),
        "exiting_trade_ids": str(row["exiting_trade_ids"]),
    }
    return sha256_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def floor_summary_rows(
    curve: pd.DataFrame,
    *,
    scope: str,
    multiplier: float,
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for floor_type, column in (
        ("MINIMUM_CASH", "cash"),
        ("MINIMUM_EQUITY", "equity"),
    ):
        values = pd.to_numeric(cast(Any, curve[column]), errors="raise")
        minimum = float(values.min())
        matches = np.isclose(
            values.to_numpy(dtype=float),
            minimum,
            rtol=0.0,
            atol=1e-8,
        )
        positions = np.flatnonzero(matches)
        if len(positions) == 0:
            raise A2AError(f"No floor row found for {scope} {floor_type}.")
        position = int(positions[0])
        row = cast(dict[str, object], curve.iloc[position].to_dict())
        output.append(
            {
                "scope": scope,
                "cost_multiplier": multiplier,
                "floor_type": floor_type,
                "floor_value": minimum,
                "floor_timestamp": timestamp(row["timestamp"]),
                "floor_occurrence_count": int(len(positions)),
                "row_position": position,
                "cash": finite(row["cash"], field="cash"),
                "free_cash": finite(row["free_cash"], field="free_cash"),
                "reserved_cash": finite(
                    row["reserved_cash"],
                    field="reserved_cash",
                ),
                "market_value": finite(
                    row["market_value"],
                    field="market_value",
                ),
                "equity": finite(row["equity"], field="equity"),
                "open_positions": scalar_int(
                    row["open_positions"],
                    field="open_positions",
                ),
                "open_trade_ids": str(row["open_trade_ids"]),
                "open_symbols": str(row["open_symbols"]),
                "entering_trade_ids": str(row["entering_trade_ids"]),
                "exiting_trade_ids": str(row["exiting_trade_ids"]),
                "cumulative_fees": finite(
                    row["cumulative_fees"],
                    field="cumulative_fees",
                ),
                "event_signature": floor_signature(row),
            }
        )
    return output


def floor_event_window(
    curve: pd.DataFrame,
    floor_rows: Sequence[Mapping[str, object]],
    *,
    radius: int = 6,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for floor in floor_rows:
        center = scalar_int(
            floor["row_position"],
            field="row_position",
        )
        start = max(0, center - radius)
        end = min(len(curve), center + radius + 1)
        for position in range(start, end):
            row = cast(dict[str, object], curve.iloc[position].to_dict())
            rows.append(
                {
                    "scope": floor["scope"],
                    "cost_multiplier": floor["cost_multiplier"],
                    "floor_type": floor["floor_type"],
                    "floor_timestamp": floor["floor_timestamp"],
                    "offset_steps": position - center,
                    **row,
                }
            )
    return pd.DataFrame(rows)


def open_positions_at_floor(
    trades: pd.DataFrame,
    hourly_frames: Mapping[str, pd.DataFrame],
    floor_rows: Sequence[Mapping[str, object]],
) -> pd.DataFrame:
    normalized = normalized_trades(trades)
    close_maps = close_price_maps(hourly_frames)
    rows: list[dict[str, object]] = []
    for floor in floor_rows:
        current = timestamp(floor["floor_timestamp"])
        multiplier = finite(
            floor["cost_multiplier"],
            field="cost_multiplier",
        )
        active = normalized.loc[
            normalized["entry_open_time"].le(current) & normalized["exit_bar_close"].gt(current)
        ]
        for trade in records(active):
            symbol = str(trade["symbol"])
            entry_time = timestamp(trade["entry_open_time"])
            if current == entry_time:
                mark = finite(trade["entry_price"], field="entry_price")
            else:
                mark_value = close_maps.get(symbol, {}).get(current)
                if mark_value is None:
                    raise A2AError(f"Missing floor mark for {symbol} at {current}.")
                mark = mark_value
            quantity = finite(trade["quantity"], field="quantity")
            entry_price = finite(trade["entry_price"], field="entry_price")
            exit_price = finite(trade["exit_price"], field="exit_price")
            rows.append(
                {
                    "scope": floor["scope"],
                    "cost_multiplier": multiplier,
                    "floor_type": floor["floor_type"],
                    "floor_timestamp": current,
                    "trade_id": str(trade["trade_id"]),
                    "source_candidate_id": str(
                        trade.get(
                            "source_v2_candidate_id",
                            trade.get("source_trade_id", ""),
                        )
                    ),
                    "symbol": symbol,
                    "engine_id": str(trade.get("engine_id", "")),
                    "entry_open_time": entry_time,
                    "exit_bar_close": timestamp(trade["exit_bar_close"]),
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "mark_price": mark,
                    "position_market_value": quantity * mark,
                    "entry_notional": quantity * entry_price,
                    "entry_fee_at_multiplier": (
                        quantity * entry_price * BASE_FEE_RATE * multiplier
                    ),
                    "planned_exit_notional": quantity * exit_price,
                    "planned_exit_fee_at_multiplier": (
                        quantity * exit_price * BASE_FEE_RATE * multiplier
                    ),
                    "risk_budget": trade.get("risk_budget"),
                }
            )
    return pd.DataFrame(rows)


def compare_floors(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for multiplier in COST_MULTIPLIERS:
        for floor_type in FLOOR_TYPES:
            subset = summary.loc[
                summary["cost_multiplier"].eq(multiplier) & summary["floor_type"].eq(floor_type)
            ]
            by_scope = {str(row["scope"]): row for row in records(subset)}
            if set(by_scope) != set(SCOPES):
                raise A2AError(f"Missing floor scope for {multiplier} {floor_type}.")
            control = by_scope["FROZEN_V3_CONTROL"]
            dynamic = by_scope["PIT_DYNAMIC_REROUTE"]
            same_value = math.isclose(
                finite(control["floor_value"], field="control_floor"),
                finite(dynamic["floor_value"], field="dynamic_floor"),
                rel_tol=0.0,
                abs_tol=1e-8,
            )
            same_timestamp = timestamp(control["floor_timestamp"]) == timestamp(
                dynamic["floor_timestamp"]
            )
            same_open_ids = str(control["open_trade_ids"]) == str(dynamic["open_trade_ids"])
            same_signature = str(control["event_signature"]) == str(dynamic["event_signature"])
            if not same_value:
                explanation = "DIFFERENT_FLOOR_VALUE"
            elif same_timestamp and same_open_ids and same_signature:
                explanation = "SAME_VALUE_SHARED_TIMESTAMP_AND_EVENT_STATE"
            else:
                explanation = "SAME_VALUE_DISTINCT_TIMESTAMP_OR_EVENT_STATE"
            rows.append(
                {
                    "cost_multiplier": multiplier,
                    "floor_type": floor_type,
                    "control_value": control["floor_value"],
                    "dynamic_value": dynamic["floor_value"],
                    "same_value": same_value,
                    "control_timestamp": control["floor_timestamp"],
                    "dynamic_timestamp": dynamic["floor_timestamp"],
                    "same_timestamp": same_timestamp,
                    "same_open_trade_ids": same_open_ids,
                    "same_event_signature": same_signature,
                    "explanation": explanation,
                }
            )
    return pd.DataFrame(rows)


def classify_audit(
    curve_comparison: pd.DataFrame,
    identity_checks: pd.DataFrame,
    floor_comparison: pd.DataFrame,
) -> tuple[str, str]:
    curve_ok = bool(curve_comparison["official_independent_match"].astype(bool).all())
    saved_values = curve_comparison["saved_official_match"].dropna()
    saved_ok = bool(saved_values.astype(bool).all())
    identity_ok = bool(identity_checks["identity_match"].astype(bool).all())
    if not curve_ok or not saved_ok or not identity_ok:
        return (
            "A2_LIQUIDITY_PROVENANCE_MISMATCH",
            "RD16_PIT_A2_REPAIR_REQUIRED",
        )
    equal = floor_comparison.loc[floor_comparison["same_value"].astype(bool)]
    if equal.empty:
        return (
            "A2_LIQUIDITY_METRICS_CONFIRMED_NO_EQUAL_FLOORS",
            "RD17_P0_UNIVERSE_PROTOCOL_AND_MANUAL_RANK_VERIFICATION",
        )
    shared = (
        equal["same_timestamp"].astype(bool)
        & equal["same_open_trade_ids"].astype(bool)
        & equal["same_event_signature"].astype(bool)
    )
    if bool(shared.all()):
        return (
            "A2_LIQUIDITY_METRICS_CONFIRMED_SHARED_FLOOR_EVENT",
            "RD17_P0_UNIVERSE_PROTOCOL_AND_MANUAL_RANK_VERIFICATION",
        )
    return (
        "A2_LIQUIDITY_METRICS_CONFIRMED_MIXED_FLOOR_ORIGIN",
        "RD17_P0_UNIVERSE_PROTOCOL_AND_MANUAL_RANK_VERIFICATION",
    )


def output_manifest(paths: Sequence[Path]) -> dict[str, object]:
    return {
        "schema_version": "rd16-pit-a2a-output-manifest-v1",
        "entries": {
            path.relative_to(ROOT).as_posix(): {
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in paths
        },
    }


def write_reports(final: Mapping[str, object]) -> None:
    result_lines = [
        "# RD16-PIT-A2A Cash and Equity Floor Provenance Results",
        "",
        f"- Decision: `{final['decision']}`",
        f"- Independent curve reconstruction match: "
        f"{final['independent_curve_reconstruction_match']}",
        f"- Saved A2 curve match: {final['saved_a2_curve_match']}",
        f"- Accounting identity match: {final['accounting_identity_match']}",
        f"- Equal floor pairs: {final['equal_floor_pair_count']}",
        f"- Shared-event equal floor pairs: {final['shared_event_equal_floor_pair_count']}",
        "",
        "Cash is modeled as free cash. Reserved cash is explicitly zero in "
        "the RD16 accounting model.",
        "",
        "The audit reconstructs every hourly row independently from entry, "
        "exit, fee, and mark-price events.",
    ]
    decision_lines = [
        "# RD16-PIT-A2A Decision",
        "",
        f"Decision: **{final['decision']}**",
        "",
        f"Next stage: `{final['next_stage']}`",
        "",
        "RD16-U remains stopped. Production remains unauthorized.",
        "",
        "The A2 decision is interpreted as 1x feasible and 2x transaction-"
        "cost stress infeasible, subject to the provenance result above.",
    ]
    (REPORTS_ROOT / "rd16-pit-a2a-results-v1.md").write_text(
        "\n".join(result_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (REPORTS_ROOT / "rd16-pit-a2a-decisions-v1.md").write_text(
        "\n".join(decision_lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def run_a2a() -> dict[str, object]:
    A2A_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    final_a2_path = A2_ROOT / "rd16pit-a2-final-report-v1.json"
    if not final_a2_path.is_file():
        raise A2AError("A2 final report is missing.")
    a2_report = cast(
        dict[str, object],
        json.loads(final_a2_path.read_text(encoding="utf-8")),
    )
    if a2_report.get("decision") != "PIT_DYNAMIC_REPLAY_CAPITAL_INFEASIBLE":
        raise A2AError("A2A requires the completed A2 capital decision.")

    source = load_source_ledgers()
    control, exact = control_replay(source)
    if not all(exact.values()):
        raise A2AError("A2 control replay is not exact.")
    control_trades = control["trades"]

    dynamic_path = A2_ROOT / "raw" / "pit-dynamic-trades.parquet"
    if not dynamic_path.is_file():
        raise A2AError("A2 dynamic trade ledger is missing.")
    dynamic_trades = pd.read_parquet(dynamic_path)
    if len(control_trades) != 567 or len(dynamic_trades) != 430:
        raise A2AError("Unexpected A2 trade counts.")

    hourly_frames, _daily_frames = rd16m._load_market_frames()
    timeline = rd16m._timeline(hourly_frames)
    performance = pd.read_csv(A2_ROOT / "performance-summary.csv")

    scope_trades = {
        "FROZEN_V3_CONTROL": control_trades,
        "PIT_DYNAMIC_REROUTE": dynamic_trades,
    }
    comparison_rows: list[dict[str, object]] = []
    identity_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    window_frames: list[pd.DataFrame] = []
    position_frames: list[pd.DataFrame] = []

    for scope, trades in scope_trades.items():
        for multiplier in COST_MULTIPLIERS:
            official = build_equity_curve(
                trades,
                hourly_frames=hourly_frames,
                timeline=timeline,
                cost_multiplier=multiplier,
            )
            independent = independent_equity_curve(
                trades,
                hourly_frames=hourly_frames,
                timeline=timeline,
                cost_multiplier=multiplier,
            )
            saved: pd.DataFrame | None = None
            if scope == "PIT_DYNAMIC_REROUTE" and multiplier in (1.0, 2.0):
                suffix = "1x" if multiplier == 1.0 else "2x"
                saved = pd.read_parquet(A2_ROOT / "raw" / f"pit-dynamic-equity-{suffix}.parquet")
            comparison_rows.append(
                compare_curves(
                    official,
                    independent,
                    scope=scope,
                    multiplier=multiplier,
                    saved=saved,
                )
            )

            maximum_cash_identity = float(
                pd.to_numeric(
                    cast(Any, independent["cash_identity_error"]),
                    errors="raise",
                )
                .abs()
                .max()
            )
            maximum_equity_identity = float(
                pd.to_numeric(
                    cast(Any, independent["equity_identity_error"]),
                    errors="raise",
                )
                .abs()
                .max()
            )
            reported = performance.loc[
                performance["scope"].astype(str).eq(scope)
                & pd.to_numeric(
                    cast(Any, performance["cost_multiplier"]),
                    errors="raise",
                ).eq(multiplier)
            ]
            if len(reported) != 1:
                raise A2AError(f"Missing reported performance row for {scope} {multiplier}.")
            reported_row = cast(
                dict[str, object],
                reported.iloc[0].to_dict(),
            )
            minimum_cash = float(
                pd.to_numeric(
                    cast(Any, independent["cash"]),
                    errors="raise",
                ).min()
            )
            minimum_equity = float(
                pd.to_numeric(
                    cast(Any, independent["equity"]),
                    errors="raise",
                ).min()
            )
            reported_match = math.isclose(
                minimum_cash,
                finite(reported_row["minimum_cash"], field="minimum_cash"),
                rel_tol=0.0,
                abs_tol=1e-8,
            ) and math.isclose(
                minimum_equity,
                finite(
                    reported_row["minimum_equity"],
                    field="minimum_equity",
                ),
                rel_tol=0.0,
                abs_tol=1e-8,
            )
            identity_rows.append(
                {
                    "scope": scope,
                    "cost_multiplier": multiplier,
                    "max_abs_cash_identity_error": maximum_cash_identity,
                    "max_abs_equity_identity_error": maximum_equity_identity,
                    "reported_minima_match": reported_match,
                    "identity_match": (
                        maximum_cash_identity <= 1e-8
                        and maximum_equity_identity <= 1e-8
                        and reported_match
                    ),
                }
            )

            floors = floor_summary_rows(
                independent,
                scope=scope,
                multiplier=multiplier,
            )
            summary_rows.extend(floors)
            window_frames.append(floor_event_window(independent, floors))
            positions = open_positions_at_floor(
                trades,
                hourly_frames,
                floors,
            )
            if not positions.empty:
                position_frames.append(positions)

    curve_comparison = pd.DataFrame(comparison_rows)
    identity_checks = pd.DataFrame(identity_rows)
    floor_summary = pd.DataFrame(summary_rows)
    event_window = pd.concat(window_frames, ignore_index=True)
    open_positions = (
        pd.concat(position_frames, ignore_index=True) if position_frames else pd.DataFrame()
    )
    floor_comparison = compare_floors(floor_summary)
    decision, next_stage = classify_audit(
        curve_comparison,
        identity_checks,
        floor_comparison,
    )

    equal = floor_comparison.loc[floor_comparison["same_value"].astype(bool)]
    shared = equal.loc[
        equal["same_timestamp"].astype(bool)
        & equal["same_open_trade_ids"].astype(bool)
        & equal["same_event_signature"].astype(bool)
    ]
    validation = {
        "schema_version": "rd16-pit-a2a-validation-v1",
        "control_replay_exact": True,
        "independent_curve_reconstruction_match": bool(
            curve_comparison["official_independent_match"].astype(bool).all()
        ),
        "saved_a2_curve_match": bool(
            curve_comparison["saved_official_match"].dropna().astype(bool).all()
        ),
        "accounting_identity_match": bool(identity_checks["identity_match"].astype(bool).all()),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "optimization_performed": False,
        "production_authorized": False,
        "rd16_u_authorized": False,
    }

    output_paths = (
        A2A_ROOT / "curve-reconstruction-comparison.csv",
        A2A_ROOT / "accounting-identity-checks.csv",
        A2A_ROOT / "floor-summary.csv",
        A2A_ROOT / "floor-comparison.csv",
        A2A_ROOT / "floor-event-window.csv",
        A2A_ROOT / "floor-open-positions.csv",
    )
    for path, frame in zip(
        output_paths,
        (
            curve_comparison,
            identity_checks,
            floor_summary,
            floor_comparison,
            event_window,
            open_positions,
        ),
        strict=True,
    ):
        write_frame(path, frame)

    write_json(A2A_ROOT / "validation-report.json", validation)
    final: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "source_commit": SOURCE_COMMIT,
        "decision": decision,
        "next_stage": next_stage,
        "a2_original_decision": a2_report["decision"],
        "a2_decision_interpretation": ("ONE_X_FEASIBLE_TWO_X_TRANSACTION_COST_STRESS_INFEASIBLE"),
        **validation,
        "curve_scope_count": len(curve_comparison),
        "equal_floor_pair_count": len(equal),
        "shared_event_equal_floor_pair_count": len(shared),
        "distinct_origin_equal_floor_pair_count": len(equal) - len(shared),
        "cash_model": "FREE_CASH_EQUALS_CASH_RESERVED_CASH_ZERO",
        "equity_identity": "EQUITY_EQUALS_CASH_PLUS_MARKET_VALUE",
        "fee_model": "ENTRY_AND_EXIT_NOTIONAL_TIMES_BASE_FEE_TIMES_MULTIPLIER",
        "full_top6_candidate_coverage_fraction": a2_report["full_top6_candidate_coverage_fraction"],
        "validation_scope": a2_report["validation_scope"],
        "liquidity_metrics_confirmed": (decision != "A2_LIQUIDITY_PROVENANCE_MISMATCH"),
        "rd17_trading_run_authorized": False,
        "universe_protocol_stage_authorized": (decision != "A2_LIQUIDITY_PROVENANCE_MISMATCH"),
    }
    write_json(A2A_ROOT / "rd16pit-a2a-final-report-v1.json", final)
    write_reports(final)

    manifest_inputs = (
        *output_paths,
        A2A_ROOT / "validation-report.json",
        A2A_ROOT / "rd16pit-a2a-final-report-v1.json",
        REPORTS_ROOT / "rd16-pit-a2a-results-v1.md",
        REPORTS_ROOT / "rd16-pit-a2a-decisions-v1.md",
    )
    write_json(
        A2A_ROOT / "output-manifest.json",
        output_manifest(manifest_inputs),
    )

    print(
        json.dumps(
            json_safe(
                {
                    "decision": decision,
                    "next_stage": next_stage,
                    "equal_floor_pair_count": len(equal),
                    "shared_event_equal_floor_pair_count": len(shared),
                    "distinct_origin_equal_floor_pair_count": (len(equal) - len(shared)),
                    **validation,
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    if repo != ROOT.resolve():
        raise A2AError(f"Expected repository {ROOT.resolve()}, found {repo}.")
    run_a2a()


if __name__ == "__main__":
    main()
