"""RD19-P2C frozen 2019-2023 discovery execution engine."""

from __future__ import annotations

import bisect
import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.research import rd19_p2a_engine as p2a

SCHEMA_VERSION: Final = "rd19-p2c-discovery-engine-v1"
STAGE: Final = "RD19_P2C_EXECUTE_FROZEN_DISCOVERY_MATRIX_2019_2023"
DECISION: Final = "RD19_P2C_FROZEN_DISCOVERY_EXECUTION_COMPLETE"
CANDIDATE_ID: Final = "RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1"
INITIAL_EQUITY: Final = 100_000.0
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00+00:00")
EXPECTED_RUNS: Final = 216

CANDIDATE_COLUMNS: Final = (
    "run_id",
    "variant_id",
    "partition_id",
    "universe_id",
    "cost_multiplier",
    "signal_time",
    "execution_time",
    "pair",
    "rank",
    "score",
    "atr",
    "atr_percent",
    "cost_hurdle_ratio",
    "entry_family",
)
EVALUATED_COLUMNS: Final = (
    *CANDIDATE_COLUMNS,
    "router_decision",
    "router_reason",
    "cash_before",
    "equity_before",
    "entry_price",
    "quantity",
    "notional",
    "risk_budget",
)
TRADE_COLUMNS: Final = (
    "run_id",
    "trade_id",
    "variant_id",
    "partition_id",
    "universe_id",
    "cost_multiplier",
    "pair",
    "signal_time",
    "entry_time",
    "exit_time",
    "entry_price",
    "exit_price",
    "quantity",
    "entry_notional",
    "exit_notional",
    "risk_budget",
    "gross_pnl",
    "entry_fee",
    "exit_fee",
    "net_pnl",
    "bars_held",
    "exit_reason",
    "instrument_type",
    "side",
)
CASH_COLUMNS: Final = (
    "run_id",
    "timestamp",
    "event_order",
    "event_type",
    "pair",
    "trade_id",
    "amount",
    "cash_after",
)
EQUITY_COLUMNS: Final = (
    "run_id",
    "timestamp",
    "cash",
    "position_value",
    "equity",
    "open_positions",
    "gross_exposure",
)


class P2CExecutionError(RuntimeError):
    """Raised when frozen historical discovery execution is invalid."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P2CExecutionError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P2CExecutionError(f"JSON object expected: {path}")
    return cast(dict[str, Any], value)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_parquet_records(
    path: Path,
    records: Iterable[Mapping[str, object]],
    columns: tuple[str, ...],
) -> int:
    rows = [dict(row) for row in records]
    frame = pd.DataFrame.from_records(rows, columns=list(columns))
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False, engine="pyarrow")
    return len(frame)


def finite(value: object, *, name: str) -> float:
    return p2a.finite(value, name=name)


def entry_pass(row: Mapping[str, object], config: Mapping[str, object]) -> bool:
    close = finite(row["close"], name="close")
    atr = finite(row["atr"], name="atr")
    if atr <= 0.0:
        return False
    extension = (close - finite(row["trend_fast_ema"], name="trend fast ema")) / atr
    if extension > finite(config["maximum_extension_atr"], name="extension"):
        return False

    family = str(config["entry_family"])
    if family == "CONFIRMED_PULLBACK":
        return all(
            (
                finite(row["prior_low"], name="prior low")
                <= finite(row["entry_ema"], name="entry ema"),
                close > finite(row["entry_ema"], name="entry ema"),
                close > finite(row["prior_close"], name="prior close"),
            )
        )
    if family == "VOLATILITY_CONTRACTION_BREAKOUT":
        reference = finite(row["atr_reference"], name="atr reference")
        if reference <= 0.0:
            return False
        return all(
            (
                close > finite(row["breakout_high"], name="breakout high"),
                atr / reference
                <= finite(
                    config["maximum_atr_to_reference_ratio"],
                    name="ATR contraction ratio",
                ),
            )
        )
    raise P2CExecutionError(f"unsupported entry family: {family}")


def prepare_feature_frame(
    raw: pd.DataFrame,
    config: Mapping[str, object],
) -> pd.DataFrame:
    frame = p2a.feature_frame(raw, config)
    close = frame["close"]
    market_ema_bars = int(config["btc_ema_bars"])
    breadth_ema_bars = int(config["breadth_ema_bars"])
    slope_lookback = int(config.get("btc_ema_slope_lookback_bars", 24))
    frame["market_ema"] = close.ewm(
        span=market_ema_bars,
        adjust=False,
        min_periods=market_ema_bars,
    ).mean()
    frame["breadth_ema"] = close.ewm(
        span=breadth_ema_bars,
        adjust=False,
        min_periods=breadth_ema_bars,
    ).mean()
    frame["return_168h"] = close / close.shift(168) - 1.0
    frame["market_ema_slope"] = frame["market_ema"] - frame["market_ema"].shift(slope_lookback)
    return frame.set_index("timestamp", drop=False)


class MembershipIndex:
    def __init__(self, frame: pd.DataFrame) -> None:
        required = {
            "universe_id",
            "decision_time",
            "effective_end",
            "effective_pair",
            "effective_rank",
        }
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise P2CExecutionError(f"membership columns missing: {missing}")
        normalized = frame.copy()
        normalized["universe_id"] = normalized["universe_id"].astype(str)
        normalized["effective_pair"] = normalized["effective_pair"].astype(str)
        normalized["decision_time"] = pd.to_datetime(
            normalized["decision_time"],
            utc=True,
            errors="raise",
        )
        normalized["effective_end"] = pd.to_datetime(
            normalized["effective_end"],
            utc=True,
            errors="raise",
        )
        normalized["effective_rank"] = pd.to_numeric(
            normalized["effective_rank"],
            errors="raise",
        ).astype(int)
        normalized = normalized.loc[normalized["decision_time"] < DATA_CUTOFF].copy()
        self._starts: dict[str, list[pd.Timestamp]] = {}
        self._intervals: dict[
            str,
            list[tuple[pd.Timestamp, pd.Timestamp, tuple[str, ...]]],
        ] = {}
        for universe_id, universe in normalized.groupby(
            "universe_id",
            sort=True,
        ):
            intervals: list[tuple[pd.Timestamp, pd.Timestamp, tuple[str, ...]]] = []
            for decision, group in universe.groupby(
                "decision_time",
                sort=True,
            ):
                ends = sorted(group["effective_end"].unique())
                if len(ends) != 1:
                    raise P2CExecutionError(f"{universe_id}/{decision} effective_end drift")
                pairs = tuple(
                    group.sort_values(
                        ["effective_rank", "effective_pair"],
                        kind="stable",
                    )["effective_pair"].astype(str)
                )
                if len(pairs) != 6 or len(set(pairs)) != 6:
                    raise P2CExecutionError(f"{universe_id}/{decision} membership width drift")
                intervals.append(
                    (
                        pd.Timestamp(decision),
                        pd.Timestamp(ends[0]),
                        pairs,
                    )
                )
            self._intervals[universe_id] = intervals
            self._starts[universe_id] = [row[0] for row in intervals]

    def members_at(
        self,
        universe_id: str,
        timestamp: pd.Timestamp,
    ) -> tuple[str, ...]:
        starts = self._starts.get(universe_id)
        intervals = self._intervals.get(universe_id)
        if starts is None or intervals is None:
            raise P2CExecutionError(f"membership universe unavailable: {universe_id}")
        index = bisect.bisect_right(starts, timestamp) - 1
        if index < 0:
            return ()
        start, end, pairs = intervals[index]
        return pairs if start <= timestamp < end else ()


def feature_row(
    features: Mapping[str, pd.DataFrame],
    pair: str,
    timestamp: pd.Timestamp,
) -> dict[str, object] | None:
    frame = features.get(pair)
    if frame is None or timestamp not in frame.index:
        return None
    raw = frame.loc[timestamp]
    if isinstance(raw, pd.DataFrame):
        if len(raw) != 1:
            raise P2CExecutionError(f"duplicate feature timestamp: {pair}/{timestamp}")
        raw = raw.iloc[0]
    return cast(dict[str, object], raw.to_dict())


def member_snapshot(
    features: Mapping[str, pd.DataFrame],
    members: tuple[str, ...],
    timestamp: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for pair in members:
        row = feature_row(features, pair, timestamp)
        if row is not None:
            row["pair"] = pair
            rows.append(row)
    return pd.DataFrame.from_records(rows)


def market_gate_pass(
    features: Mapping[str, pd.DataFrame],
    members: tuple[str, ...],
    timestamp: pd.Timestamp,
    config: Mapping[str, object],
) -> bool:
    snapshot = member_snapshot(features, members, timestamp)
    if len(snapshot) != len(members):
        return False
    required = [
        "close",
        "breadth_ema",
        "return_168h",
    ]
    if snapshot[required].isna().any().any():
        return False
    btc = feature_row(features, "BTC-USDT", timestamp)
    if btc is None:
        return False
    for column in ("close", "market_ema"):
        value = btc.get(column)
        if value is None or pd.isna(value):
            return False
    if bool(config["require_btc_ema_positive_slope"]):
        slope = btc.get("market_ema_slope")
        if slope is None or pd.isna(slope):
            return False
    return p2a.market_gate(
        snapshot,
        btc_row=btc,
        config=config,
    )


def ranked_pairs(
    features: Mapping[str, pd.DataFrame],
    membership: MembershipIndex,
    universe_id: str,
    timestamp: pd.Timestamp,
    config: Mapping[str, object],
) -> list[dict[str, object]]:
    members = membership.members_at(universe_id, timestamp)
    if not members:
        return []
    if not market_gate_pass(
        features,
        members,
        timestamp,
        config,
    ):
        return []

    snapshot = member_snapshot(features, members, timestamp)
    required = [
        "close",
        "trend_fast_ema",
        "trend_slow_ema",
        "momentum_fast",
        "momentum_slow",
        "trend_persistence",
        "atr_percent",
    ]
    snapshot = snapshot.dropna(subset=required).copy()
    snapshot = snapshot.loc[
        (snapshot["close"] > snapshot["trend_fast_ema"])
        & (snapshot["trend_fast_ema"] > snapshot["trend_slow_ema"])
        & (snapshot["momentum_fast"] > 0.0)
        & (snapshot["momentum_slow"] > 0.0)
    ].copy()
    if snapshot.empty:
        return []
    snapshot["momentum_fast_rank"] = snapshot["momentum_fast"].rank(method="average", pct=True)
    snapshot["momentum_slow_rank"] = snapshot["momentum_slow"].rank(method="average", pct=True)
    snapshot["persistence_rank"] = snapshot["trend_persistence"].rank(method="average", pct=True)
    weights = cast(dict[str, object], config["ranking_score_weights"])
    snapshot["score"] = (
        snapshot["momentum_fast_rank"]
        * finite(weights["relative_momentum_fast"], name="fast weight")
        + snapshot["momentum_slow_rank"]
        * finite(weights["relative_momentum_slow"], name="slow weight")
        + snapshot["persistence_rank"]
        * finite(weights["trend_persistence"], name="persistence weight")
    )
    snapshot = snapshot.sort_values(
        ["score", "atr_percent", "pair"],
        ascending=[False, True, True],
        kind="stable",
    ).head(int(config["top_k"]))
    rows: list[dict[str, object]] = []
    for rank, raw in enumerate(
        snapshot.to_dict(orient="records"),
        start=1,
    ):
        rows.append(
            {
                "pair": str(raw["pair"]),
                "rank": rank,
                "score": float(raw["score"]),
            }
        )
    return rows


def position_value_at(
    positions: Mapping[str, dict[str, object]],
    features: Mapping[str, pd.DataFrame],
    timestamp: pd.Timestamp,
    price_column: str,
) -> float:
    total = 0.0
    for pair, position in positions.items():
        row = feature_row(features, pair, timestamp)
        if row is None:
            raise P2CExecutionError(f"open position missing bar: {pair}/{timestamp}")
        price = finite(row[price_column], name=f"{pair} {price_column}")
        total += finite(position["quantity"], name="quantity") * price
    return total


def maximum_drawdown(equity: pd.Series) -> float:
    values = pd.to_numeric(equity, errors="raise").astype(float)
    if values.empty or bool((values <= 0.0).any()):
        return 1.0
    peaks = values.cummax()
    drawdowns = 1.0 - values / peaks
    return float(drawdowns.max())


def profit_factor(values: pd.Series) -> float | None:
    pnl = pd.to_numeric(values, errors="raise").astype(float)
    positive = float(pnl[pnl > 0.0].sum())
    negative = abs(float(pnl[pnl < 0.0].sum()))
    return positive / negative if negative > 0.0 else None


def year_returns(
    equity_curve: pd.DataFrame,
    partition_start_equity: float,
) -> dict[str, float]:
    result: dict[str, float] = {}
    previous = partition_start_equity
    curve = equity_curve.copy()
    curve["timestamp"] = pd.to_datetime(
        curve["timestamp"],
        utc=True,
        errors="raise",
    )
    for year, group in curve.groupby(curve["timestamp"].dt.year, sort=True):
        end = float(pd.to_numeric(group["equity"], errors="raise").iloc[-1])
        result[str(int(year))] = end / previous - 1.0
        previous = end
    return result


def run_id_for(row: Mapping[str, object]) -> str:
    return (
        f"{int(row['execution_order']):03d}_"
        f"{row['variant_id']}_{row['partition_id']}_"
        f"{row['universe_id']}_{float(row['cost_multiplier']):.0f}x"
    )


def execute_run(
    *,
    run_row: Mapping[str, object],
    config: Mapping[str, object],
    features: Mapping[str, pd.DataFrame],
    membership: MembershipIndex,
    partition_start: pd.Timestamp,
    partition_end: pd.Timestamp,
) -> dict[str, object]:
    run_id = run_id_for(run_row)
    universe_id = str(run_row["universe_id"])
    variant_id = str(run_row["variant_id"])
    partition_id = str(run_row["partition_id"])
    cost_multiplier = float(run_row["cost_multiplier"])
    fee_rate = p2a.BASE_FEE_RATE * cost_multiplier

    candidates: list[dict[str, object]] = []
    evaluated: list[dict[str, object]] = []
    trades: list[dict[str, object]] = []
    cash_events: list[dict[str, object]] = []
    equity_rows: list[dict[str, object]] = []
    positions: dict[str, dict[str, object]] = {}
    last_exit: dict[str, pd.Timestamp] = {}
    pending: list[dict[str, object]] = []
    daily_rank: list[dict[str, object]] = []
    cash = INITIAL_EQUITY
    event_order = 0
    trade_counter = 0

    diagnostics = {
        "ranking_refreshes": 0,
        "market_gate_off_hours": 0,
        "missing_membership_hours": 0,
        "candidate_signals": 0,
        "router_admitted": 0,
        "router_rejected": 0,
    }

    timestamps = pd.date_range(
        partition_start,
        partition_end,
        freq="h",
    )

    for timestamp in timestamps:
        members = membership.members_at(universe_id, timestamp)
        if not members:
            diagnostics["missing_membership_hours"] += 1

        if timestamp.hour == 0:
            daily_rank = ranked_pairs(
                features,
                membership,
                universe_id,
                timestamp,
                config,
            )
            diagnostics["ranking_refreshes"] += 1

        # Execute signals from the previous completed bar at this bar open.
        for signal in pending:
            pair = str(signal["pair"])
            row = feature_row(features, pair, timestamp)
            cash_before = cash
            equity_before = cash + position_value_at(
                positions,
                features,
                timestamp,
                "open",
            )
            decision = "REJECTED"
            reason = "UNKNOWN"
            entry_price: float | None = None
            quantity: float | None = None
            notional: float | None = None
            risk_budget: float | None = None

            if pair not in members:
                reason = "MEMBERSHIP_CHANGED"
            elif row is None:
                reason = "MISSING_ENTRY_BAR"
            elif pair in positions:
                reason = "DUPLICATE_POSITION"
            elif pair in last_exit and timestamp - last_exit[pair] < pd.Timedelta(
                hours=int(config["pair_reentry_cooldown_bars"])
            ):
                reason = "REENTRY_COOLDOWN"
            elif len(positions) >= int(config["maximum_positions"]):
                reason = "MAXIMUM_POSITIONS"
            else:
                entry_price = finite(row["open"], name="entry open")
                signal_atr = finite(signal["atr"], name="signal ATR")
                stop_distance = signal_atr * finite(
                    config["initial_stop_atr"],
                    name="initial stop ATR",
                )
                risk_budget = equity_before * finite(
                    config["risk_per_position_fraction_of_equity"],
                    name="risk fraction",
                )
                existing_gross = position_value_at(
                    positions,
                    features,
                    timestamp,
                    "open",
                )
                max_gross = equity_before * finite(
                    config["maximum_gross_exposure_fraction"],
                    name="gross exposure cap",
                )
                asset_cap = equity_before * finite(
                    config["maximum_single_asset_exposure_fraction"],
                    name="asset exposure cap",
                )
                if stop_distance <= 0.0 or entry_price - stop_distance <= 0.0:
                    reason = "INVALID_STOP_GEOMETRY"
                else:
                    q_risk = risk_budget / stop_distance
                    q_asset = asset_cap / entry_price
                    q_gross = (
                        max(
                            0.0,
                            max_gross - existing_gross,
                        )
                        / entry_price
                    )
                    q_cash = cash / (entry_price * (1.0 + fee_rate))
                    quantity = min(q_risk, q_asset, q_gross, q_cash)
                    if quantity <= 0.0:
                        reason = "INSUFFICIENT_CASH_OR_EXPOSURE"
                    else:
                        notional = quantity * entry_price
                        entry_fee = notional * fee_rate
                        required_cash = notional + entry_fee
                        if required_cash > cash + 1e-8:
                            reason = "INSUFFICIENT_CASH"
                        else:
                            cash -= required_cash
                            trade_counter += 1
                            trade_id = f"{run_id}_T{trade_counter:05d}"
                            positions[pair] = {
                                "trade_id": trade_id,
                                "signal_time": pd.Timestamp(signal["signal_time"]),
                                "entry_time": timestamp,
                                "entry_price": entry_price,
                                "quantity": quantity,
                                "entry_notional": notional,
                                "risk_budget": risk_budget,
                                "entry_fee": entry_fee,
                                "initial_stop": entry_price - stop_distance,
                                "active_stop": entry_price - stop_distance,
                                "stop_distance": stop_distance,
                                "high_water": entry_price,
                                "trail_active": False,
                                "bars_held": 0,
                            }
                            event_order += 1
                            cash_events.append(
                                {
                                    "run_id": run_id,
                                    "timestamp": timestamp,
                                    "event_order": event_order,
                                    "event_type": "ENTRY",
                                    "pair": pair,
                                    "trade_id": trade_id,
                                    "amount": -required_cash,
                                    "cash_after": cash,
                                }
                            )
                            decision = "ADMITTED"
                            reason = "ADMITTED"
                            diagnostics["router_admitted"] += 1

            if decision != "ADMITTED":
                diagnostics["router_rejected"] += 1
            evaluated.append(
                {
                    **signal,
                    "router_decision": decision,
                    "router_reason": reason,
                    "cash_before": cash_before,
                    "equity_before": equity_before,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "notional": notional,
                    "risk_budget": risk_budget,
                }
            )
        pending = []

        # Manage all open positions through the current bar.
        for pair in sorted(list(positions)):
            position = positions[pair]
            row = feature_row(features, pair, timestamp)
            if row is None:
                raise P2CExecutionError(f"open position bar missing: {run_id}/{pair}/{timestamp}")
            entry_time = pd.Timestamp(position["entry_time"])
            if timestamp < entry_time:
                continue
            position["bars_held"] = int(position["bars_held"]) + 1
            high = finite(row["high"], name="high")
            low = finite(row["low"], name="low")
            close = finite(row["close"], name="close")
            atr = finite(row["atr"], name="ATR")
            high_water = max(
                finite(position["high_water"], name="high water"),
                high,
            )
            position["high_water"] = high_water
            stop_distance = finite(
                position["stop_distance"],
                name="stop distance",
            )
            open_r = (
                high_water - finite(position["entry_price"], name="entry price")
            ) / stop_distance
            if open_r >= finite(
                config["trail_activation_r"],
                name="trail activation",
            ):
                position["trail_active"] = True
                position["active_stop"] = max(
                    finite(position["active_stop"], name="active stop"),
                    high_water - atr * finite(config["trail_atr"], name="trail ATR"),
                )

            exit_price: float | None = None
            exit_reason: str | None = None
            active_stop = finite(position["active_stop"], name="active stop")
            if low <= active_stop:
                exit_price = active_stop
                exit_reason = (
                    "STRUCTURAL_TRAIL" if bool(position["trail_active"]) else "INITIAL_STOP"
                )
            elif close < finite(
                row["trend_fast_ema"],
                name="thesis EMA",
            ):
                exit_price = close
                exit_reason = "THESIS_INVALIDATION"
            elif int(position["bars_held"]) >= int(config["maximum_holding_bars"]):
                exit_price = close
                exit_reason = "MAX_HOLDING_SAFEGUARD"
            elif timestamp == partition_end:
                exit_price = close
                exit_reason = "PARTITION_END_LIQUIDATION"

            if exit_price is not None and exit_reason is not None:
                quantity = finite(position["quantity"], name="quantity")
                exit_notional = quantity * exit_price
                exit_fee = exit_notional * fee_rate
                cash_amount = exit_notional - exit_fee
                cash += cash_amount
                entry_price = finite(
                    position["entry_price"],
                    name="entry price",
                )
                entry_fee = finite(position["entry_fee"], name="entry fee")
                gross_pnl = quantity * (exit_price - entry_price)
                net_pnl = gross_pnl - entry_fee - exit_fee
                trade_id = str(position["trade_id"])
                trades.append(
                    {
                        "run_id": run_id,
                        "trade_id": trade_id,
                        "variant_id": variant_id,
                        "partition_id": partition_id,
                        "universe_id": universe_id,
                        "cost_multiplier": cost_multiplier,
                        "pair": pair,
                        "signal_time": position["signal_time"],
                        "entry_time": position["entry_time"],
                        "exit_time": timestamp,
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "quantity": quantity,
                        "entry_notional": position["entry_notional"],
                        "exit_notional": exit_notional,
                        "risk_budget": position["risk_budget"],
                        "gross_pnl": gross_pnl,
                        "entry_fee": entry_fee,
                        "exit_fee": exit_fee,
                        "net_pnl": net_pnl,
                        "bars_held": int(position["bars_held"]),
                        "exit_reason": exit_reason,
                        "instrument_type": "SPOT",
                        "side": "LONG",
                    }
                )
                event_order += 1
                cash_events.append(
                    {
                        "run_id": run_id,
                        "timestamp": timestamp,
                        "event_order": event_order,
                        "event_type": "EXIT",
                        "pair": pair,
                        "trade_id": trade_id,
                        "amount": cash_amount,
                        "cash_after": cash,
                    }
                )
                last_exit[pair] = timestamp
                del positions[pair]

        position_value = position_value_at(
            positions,
            features,
            timestamp,
            "close",
        )
        equity = cash + position_value
        if cash < -1e-7:
            raise P2CExecutionError(f"negative cash: {run_id}/{timestamp}/{cash}")
        equity_rows.append(
            {
                "run_id": run_id,
                "timestamp": timestamp,
                "cash": cash,
                "position_value": position_value,
                "equity": equity,
                "open_positions": len(positions),
                "gross_exposure": (position_value / equity if equity > 0.0 else math.inf),
            }
        )

        # Generate signals on the completed bar for next-bar routing.
        next_time = timestamp + pd.Timedelta(hours=1)
        if next_time > partition_end or not members or not daily_rank:
            continue
        if not market_gate_pass(
            features,
            members,
            timestamp,
            config,
        ):
            diagnostics["market_gate_off_hours"] += 1
            continue

        next_signals: list[dict[str, object]] = []
        for ranked in daily_rank:
            pair = str(ranked["pair"])
            if pair not in members or pair in positions:
                continue
            row = feature_row(features, pair, timestamp)
            if row is None:
                continue
            required = (
                "close",
                "trend_fast_ema",
                "trend_slow_ema",
                "momentum_fast",
                "momentum_slow",
                "trend_persistence",
                "atr",
                "atr_percent",
                "entry_ema",
                "prior_low",
                "prior_close",
                "breakout_high",
                "atr_reference",
            )
            if any(row.get(column) is None or pd.isna(row.get(column)) for column in required):
                continue
            if not all(
                (
                    finite(row["close"], name="close")
                    > finite(row["trend_fast_ema"], name="fast EMA"),
                    finite(row["trend_fast_ema"], name="fast EMA")
                    > finite(row["trend_slow_ema"], name="slow EMA"),
                    finite(row["momentum_fast"], name="fast momentum") > 0.0,
                    finite(row["momentum_slow"], name="slow momentum") > 0.0,
                )
            ):
                continue

            effective_cost = (
                2.0
                * p2a.BASE_FEE_RATE
                * cost_multiplier
                * finite(
                    config["effective_cost_uncertainty_multiplier"],
                    name="cost uncertainty multiplier",
                )
            )
            atr_percent = finite(row["atr_percent"], name="ATR percent")
            cost_ratio = atr_percent / effective_cost if effective_cost > 0.0 else math.inf
            if cost_ratio < finite(
                config["minimum_atr_to_effective_round_trip_cost"],
                name="cost hurdle",
            ):
                continue
            if not entry_pass(row, config):
                continue

            signal = {
                "run_id": run_id,
                "variant_id": variant_id,
                "partition_id": partition_id,
                "universe_id": universe_id,
                "cost_multiplier": cost_multiplier,
                "signal_time": timestamp,
                "execution_time": next_time,
                "pair": pair,
                "rank": int(ranked["rank"]),
                "score": float(ranked["score"]),
                "atr": finite(row["atr"], name="ATR"),
                "atr_percent": atr_percent,
                "cost_hurdle_ratio": cost_ratio,
                "entry_family": str(config["entry_family"]),
            }
            candidates.append(signal)
            next_signals.append(signal)
            diagnostics["candidate_signals"] += 1
        pending = sorted(
            next_signals,
            key=lambda row: (
                int(row["rank"]),
                -float(row["score"]),
                str(row["pair"]),
            ),
        )

    if positions:
        raise P2CExecutionError(f"positions remain open after partition liquidation: {run_id}")

    candidate_frame = pd.DataFrame.from_records(
        candidates,
        columns=list(CANDIDATE_COLUMNS),
    )
    evaluated_frame = pd.DataFrame.from_records(
        evaluated,
        columns=list(EVALUATED_COLUMNS),
    )
    trade_frame = pd.DataFrame.from_records(
        trades,
        columns=list(TRADE_COLUMNS),
    )
    cash_frame = pd.DataFrame.from_records(
        cash_events,
        columns=list(CASH_COLUMNS),
    )
    equity_frame = pd.DataFrame.from_records(
        equity_rows,
        columns=list(EQUITY_COLUMNS),
    )

    if equity_frame.empty:
        raise P2CExecutionError(f"empty equity curve: {run_id}")
    end_equity = float(equity_frame["equity"].iloc[-1])
    pnl_values = (
        pd.to_numeric(trade_frame["net_pnl"], errors="raise")
        if not trade_frame.empty
        else pd.Series(dtype=float)
    )
    entry_turnover = (
        float(
            pd.to_numeric(
                trade_frame["entry_notional"],
                errors="raise",
            ).sum()
        )
        if not trade_frame.empty
        else 0.0
    )
    exit_turnover = (
        float(
            pd.to_numeric(
                trade_frame["exit_notional"],
                errors="raise",
            ).sum()
        )
        if not trade_frame.empty
        else 0.0
    )
    total_fees = (
        float(
            (
                pd.to_numeric(
                    trade_frame["entry_fee"],
                    errors="raise",
                )
                + pd.to_numeric(
                    trade_frame["exit_fee"],
                    errors="raise",
                )
            ).sum()
        )
        if not trade_frame.empty
        else 0.0
    )
    metrics: dict[str, object] = {
        "schema_version": "rd19-p2c-run-metrics-v1",
        "run_id": run_id,
        "execution_order": int(run_row["execution_order"]),
        "variant_id": variant_id,
        "partition_id": partition_id,
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        "partition_start": partition_start,
        "partition_end": partition_end,
        "initial_equity": INITIAL_EQUITY,
        "ending_equity": end_equity,
        "net_return": end_equity / INITIAL_EQUITY - 1.0,
        "net_pnl": end_equity - INITIAL_EQUITY,
        "trade_count": len(trade_frame),
        "candidate_count": len(candidate_frame),
        "evaluated_count": len(evaluated_frame),
        "win_rate": (float((pnl_values > 0.0).mean()) if not pnl_values.empty else None),
        "profit_factor": (profit_factor(pnl_values) if not pnl_values.empty else None),
        "maximum_drawdown": maximum_drawdown(equity_frame["equity"]),
        "minimum_cash": float(equity_frame["cash"].min()),
        "maximum_open_positions": int(equity_frame["open_positions"].max()),
        "maximum_gross_exposure": float(equity_frame["gross_exposure"].max()),
        "entry_turnover_notional": entry_turnover,
        "exit_turnover_notional": exit_turnover,
        "turnover_on_initial_equity": (entry_turnover + exit_turnover) / INITIAL_EQUITY,
        "total_fees": total_fees,
        "year_returns": year_returns(
            equity_frame,
            INITIAL_EQUITY,
        ),
        "technical_valid": True,
        "cash_feasible": bool(float(equity_frame["cash"].min()) >= -1e-7),
        "spot_only": (
            True
            if trade_frame.empty
            else set(trade_frame["instrument_type"].astype(str)) == {"SPOT"}
        ),
        "long_only": (
            True if trade_frame.empty else set(trade_frame["side"].astype(str)) == {"LONG"}
        ),
        "2024_market_data_accessed": False,
        "post_2024_accessed": False,
        "diagnostics": diagnostics,
    }
    return {
        "metrics": metrics,
        "candidates": candidate_frame,
        "evaluated": evaluated_frame,
        "trades": trade_frame,
        "cash": cash_frame,
        "equity": equity_frame,
    }


def checkpoint_files(run_dir: Path) -> tuple[str, ...]:
    return (
        "candidates.parquet",
        "evaluated.parquet",
        "trades.parquet",
        "cash-ledger.parquet",
        "equity-curve.parquet",
        "run-metrics.json",
    )


def write_run_result(
    run_dir: Path,
    result: Mapping[str, object],
) -> dict[str, object]:
    if run_dir.exists():
        raise P2CExecutionError(f"run directory already exists without checkpoint: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)
    cast(pd.DataFrame, result["candidates"]).to_parquet(
        run_dir / "candidates.parquet",
        index=False,
        engine="pyarrow",
    )
    cast(pd.DataFrame, result["evaluated"]).to_parquet(
        run_dir / "evaluated.parquet",
        index=False,
        engine="pyarrow",
    )
    cast(pd.DataFrame, result["trades"]).to_parquet(
        run_dir / "trades.parquet",
        index=False,
        engine="pyarrow",
    )
    cast(pd.DataFrame, result["cash"]).to_parquet(
        run_dir / "cash-ledger.parquet",
        index=False,
        engine="pyarrow",
    )
    cast(pd.DataFrame, result["equity"]).to_parquet(
        run_dir / "equity-curve.parquet",
        index=False,
        engine="pyarrow",
    )
    write_json(
        run_dir / "run-metrics.json",
        result["metrics"],
    )
    files = []
    for name in checkpoint_files(run_dir):
        path = run_dir / name
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    checkpoint = {
        "schema_version": "rd19-p2c-run-checkpoint-v1",
        "status": "PASS",
        "run_id": cast(dict[str, object], result["metrics"])["run_id"],
        "execution_order": cast(
            dict[str, object],
            result["metrics"],
        )["execution_order"],
        "files": files,
    }
    write_json(run_dir / "checkpoint.json", checkpoint)
    return checkpoint


def verify_checkpoint(run_dir: Path) -> dict[str, Any]:
    checkpoint = load_json_object(run_dir / "checkpoint.json")
    if checkpoint.get("status") != "PASS":
        raise P2CExecutionError(f"checkpoint is not PASS: {run_dir}")
    files = checkpoint.get("files")
    if not isinstance(files, list):
        raise P2CExecutionError(f"checkpoint files invalid: {run_dir}")
    expected = set(checkpoint_files(run_dir))
    observed: set[str] = set()
    for raw in files:
        if not isinstance(raw, dict):
            raise P2CExecutionError(f"checkpoint row invalid: {run_dir}")
        name = str(raw.get("path", ""))
        path = run_dir / name
        if not path.is_file():
            raise P2CExecutionError(f"checkpoint file missing: {path}")
        if sha256(path) != str(raw.get("sha256", "")):
            raise P2CExecutionError(f"checkpoint hash drift: {path}")
        observed.add(name)
    if observed != expected:
        raise P2CExecutionError(f"checkpoint file set drift: {run_dir}")
    return checkpoint


def chain_equity_curves(
    curves: list[pd.DataFrame],
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    capital = INITIAL_EQUITY
    for curve in curves:
        local = curve.copy()
        local_equity = pd.to_numeric(
            local["equity"],
            errors="raise",
        ).astype(float)
        chained = capital * (local_equity / INITIAL_EQUITY)
        local["chained_equity"] = chained
        rows.append(local[["timestamp", "chained_equity"]])
        capital = float(chained.iloc[-1])
    return pd.concat(rows, ignore_index=True)


def top_trade_share(trades: pd.DataFrame, count: int = 5) -> float:
    if trades.empty:
        return math.inf
    pnl = pd.to_numeric(trades["net_pnl"], errors="raise")
    positive_total = float(pnl[pnl > 0.0].sum())
    if positive_total <= 0.0:
        return math.inf
    selected = float(pnl.sort_values(ascending=False, kind="stable").head(count).sum())
    return selected / positive_total
