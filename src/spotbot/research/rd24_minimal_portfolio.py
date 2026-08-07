"""RD24 parallel minimal portfolio evaluator for RD23-qualified families.

Consumes frozen RD23 signal events. It does not regenerate signals or alter family
definitions. Each standalone portfolio and the deterministic union use the same
causal 1h execution, equal-slot notional sizing, capacity cap, and 168h hold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
import pandas as pd

SCHEMA_VERSION: Final = "rd24-parallel-minimal-portfolio-engine-v1"
STAGE: Final = "RD24_QUALIFIED_FAMILY_MINIMAL_PORTFOLIO_EVALUATION_PARALLEL"

DATA_START: Final = pd.Timestamp("2019-01-01T00:00:00Z")
DATA_CUTOFF: Final = pd.Timestamp("2022-01-01T00:00:00Z")
HOLDING_HOURS: Final = 168
BASE_ROUND_TRIP_COST: Final = 0.0025
COST_MULTIPLIERS: Final = (1.0, 2.0)
INITIAL_EQUITY: Final = 100_000.0
MAXIMUM_POSITIONS: Final = 5
MAXIMUM_GROSS_EXPOSURE: Final = 0.90
TARGET_SLOT_NOTIONAL_FRACTION: Final = MAXIMUM_GROSS_EXPOSURE / MAXIMUM_POSITIONS
LIQUIDITY_CAPACITY_FRACTION_24H: Final = 0.005
MINIMUM_TRADES: Final = 75
MINIMUM_PROFIT_FACTOR_2X: Final = 1.05
MAXIMUM_DRAWDOWN_HARD: Final = 0.20
MINIMUM_BREAK_EVEN_COST_MULTIPLIER: Final = 2.0

QUALIFIED_FAMILIES: Final = (
    "MOMENTUM_BREAKOUT",
    "VOLATILITY_EXPANSION",
    "RELATIVE_STRENGTH_ROTATION",
    "MOMENTUM_ACCELERATION",
)

PERIODS: Final = {
    "DISCOVERY_2019_2020": (
        pd.Timestamp("2019-01-01T00:00:00Z"),
        pd.Timestamp("2021-01-01T00:00:00Z"),
    ),
    "TEMPORAL_REPLICATION_2021": (
        pd.Timestamp("2021-01-01T00:00:00Z"),
        pd.Timestamp("2022-01-01T00:00:00Z"),
    ),
}


class RD24Error(RuntimeError):
    """Raised when the frozen RD24 minimal portfolio contract is violated."""


@dataclass
class Position:
    pair: str
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    scheduled_exit_time: pd.Timestamp
    entry_price: float
    quantity: float
    entry_notional: float
    entry_cost: float
    membership_rank: int
    support_families: tuple[str, ...]
    period_id: str
    last_mark: float


def period_for(timestamp: pd.Timestamp) -> str:
    for name, (start, end) in PERIODS.items():
        if start <= timestamp < end:
            return name
    raise RD24Error(f"timestamp outside RD24 selection periods: {timestamp}")


def normalize_economic_bars(raw: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(raw.columns))
    if missing:
        raise RD24Error(f"raw bars missing columns: {missing}")
    frame = raw.loc[:, ["timestamp", "open", "high", "low", "close", "volume"]].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    frame = (
        frame.sort_values("timestamp", kind="stable")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )
    if len(frame) and frame["timestamp"].max() >= DATA_CUTOFF:
        raise RD24Error("2022 or later bar entered RD24 memory")
    if bool((frame[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise RD24Error("non-positive OHLC price observed")
    if bool((frame["volume"] < 0.0).any()):
        raise RD24Error("negative volume observed")
    frame["quote_turnover_proxy"] = frame["volume"] * frame["close"]
    frame["trailing_24h_quote_turnover_proxy"] = (
        frame["quote_turnover_proxy"].rolling(24, min_periods=24).sum()
    )
    return frame


def fast_lookup(frame: pd.DataFrame) -> dict[int, int]:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").dt.as_unit("ns")
    values = timestamps.astype("int64").to_numpy()
    return {int(value): int(index) for index, value in enumerate(values)}


def prepare_frozen_events(events: pd.DataFrame) -> pd.DataFrame:
    required = {
        "universe_id",
        "period_id",
        "timestamp",
        "family_id",
        "pair",
        "membership_rank",
    }
    missing = sorted(required.difference(events.columns))
    if missing:
        raise RD24Error(f"RD23 signal ledger missing columns: {missing}")
    frame = events.loc[:, list(required)].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["membership_rank"] = pd.to_numeric(frame["membership_rank"], errors="raise").astype(int)
    frame["family_id"] = frame["family_id"].astype(str)
    frame["pair"] = frame["pair"].astype(str)
    frame["universe_id"] = frame["universe_id"].astype(str)
    frame["period_id"] = frame["period_id"].astype(str)
    frame = frame.loc[frame["family_id"].isin(QUALIFIED_FAMILIES)].copy()
    if frame.empty:
        raise RD24Error("qualified RD23 signal ledger is empty")
    if bool((frame["timestamp"] < DATA_START).any()) or bool(
        (frame["timestamp"] >= DATA_CUTOFF).any()
    ):
        raise RD24Error("signal timestamp crossed RD24 data boundary")
    if bool(~frame["universe_id"].isin({"C2", "D2", "E2"}).any()):
        raise RD24Error("unexpected universe in signal ledger")
    for record in frame[["timestamp", "period_id"]].to_dict(orient="records"):
        if period_for(pd.Timestamp(record["timestamp"])) != str(record["period_id"]):
            raise RD24Error("signal period label drifted")
    return frame.sort_values(
        ["universe_id", "timestamp", "family_id", "membership_rank", "pair"],
        kind="stable",
    ).reset_index(drop=True)


def standalone_events(
    events: pd.DataFrame,
    *,
    universe_id: str,
    family_id: str,
) -> pd.DataFrame:
    frame = events.loc[
        (events["universe_id"] == universe_id) & (events["family_id"] == family_id)
    ].copy()
    frame["support_families"] = family_id
    return frame.sort_values(
        ["timestamp", "membership_rank", "pair"],
        kind="stable",
    ).reset_index(drop=True)


def union_events(
    events: pd.DataFrame,
    *,
    universe_id: str,
    families: tuple[str, ...],
) -> pd.DataFrame:
    allowed = set(families)
    frame = events.loc[
        (events["universe_id"] == universe_id) & (events["family_id"].isin(allowed))
    ].copy()
    rows: list[dict[str, Any]] = []
    grouped = frame.groupby(["timestamp", "pair"], sort=True)
    for (timestamp, pair), group in grouped:
        family_set = tuple(sorted(set(group["family_id"].astype(str))))
        ranks = pd.to_numeric(group["membership_rank"], errors="raise").astype(int)
        periods = sorted(set(group["period_id"].astype(str)))
        if len(periods) != 1:
            raise RD24Error("union event spans multiple period labels")
        rows.append(
            {
                "timestamp": pd.Timestamp(timestamp),
                "pair": str(pair),
                "membership_rank": int(ranks.min()),
                "period_id": periods[0],
                "support_families": "|".join(family_set),
                "support_count": len(family_set),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "pair",
                "membership_rank",
                "period_id",
                "support_families",
                "support_count",
            ]
        )
    return (
        pd.DataFrame.from_records(rows)
        .sort_values(
            ["timestamp", "membership_rank", "pair"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _bar_at(
    pair: str,
    timestamp: pd.Timestamp,
    frames: dict[str, pd.DataFrame],
    lookups: dict[str, dict[int, int]],
) -> pd.Series | None:
    frame = frames.get(pair)
    if frame is None:
        return None
    index = lookups.get(pair, {}).get(int(timestamp.value))
    if index is None:
        return None
    return frame.iloc[index]


def _marked_equity(
    *,
    cash: float,
    positions: dict[str, Position],
) -> tuple[float, float]:
    gross = sum(position.quantity * position.last_mark for position in positions.values())
    return cash + gross, gross


def replay_portfolio(
    *,
    portfolio_id: str,
    universe_id: str,
    cost_multiplier: float,
    events: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, int]]:
    if cost_multiplier not in COST_MULTIPLIERS:
        raise RD24Error("unsupported cost multiplier")
    lookups = {pair: fast_lookup(frame) for pair, frame in frames.items()}
    side_cost = BASE_ROUND_TRIP_COST * cost_multiplier / 2.0

    scheduled: dict[int, list[dict[str, Any]]] = {}
    for raw in events.to_dict(orient="records"):
        signal_time = pd.Timestamp(raw["timestamp"])
        entry_time = signal_time + pd.Timedelta(hours=1)
        exit_time = signal_time + pd.Timedelta(hours=HOLDING_HOURS + 1)
        item = {
            **raw,
            "signal_time": signal_time,
            "entry_time": entry_time,
            "scheduled_exit_time": exit_time,
        }
        scheduled.setdefault(int(entry_time.value), []).append(item)

    cash = INITIAL_EQUITY
    positions: dict[str, Position] = {}
    trades: list[dict[str, Any]] = []
    daily_rows: list[dict[str, Any]] = []
    hourly_equity_values: list[float] = []
    counters = {
        "signal_events": len(events),
        "missing_entry_bar": 0,
        "missing_exit_bar_precheck": 0,
        "same_pair_open": 0,
        "position_slots_full": 0,
        "gross_limit_rejection": 0,
        "capacity_unavailable": 0,
        "capacity_capped_entries": 0,
        "cash_capped_entries": 0,
        "admitted_entries": 0,
        "scheduled_exits": 0,
    }

    for timestamp in pd.date_range(DATA_START, DATA_CUTOFF, freq="h", inclusive="left"):
        # Exit first at the current bar open.
        exiting = [
            pair
            for pair, position in positions.items()
            if position.scheduled_exit_time == timestamp
        ]
        for pair in sorted(exiting):
            position = positions[pair]
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is None:
                raise RD24Error(f"scheduled exit bar missing after admission: {pair} {timestamp}")
            exit_price = float(bar["open"])
            exit_notional = position.quantity * exit_price
            exit_cost = exit_notional * side_cost
            gross_pnl = exit_notional - position.entry_notional
            net_pnl = gross_pnl - position.entry_cost - exit_cost
            cash += exit_notional - exit_cost
            trades.append(
                {
                    "portfolio_id": portfolio_id,
                    "universe_id": universe_id,
                    "cost_multiplier": cost_multiplier,
                    "pair": pair,
                    "signal_time": position.signal_time,
                    "entry_time": position.entry_time,
                    "exit_time": timestamp,
                    "holding_hours": HOLDING_HOURS,
                    "entry_price": position.entry_price,
                    "exit_price": exit_price,
                    "quantity": position.quantity,
                    "entry_notional": position.entry_notional,
                    "exit_notional": exit_notional,
                    "entry_cost": position.entry_cost,
                    "exit_cost": exit_cost,
                    "gross_pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "period_id": position.period_id,
                    "membership_rank": position.membership_rank,
                    "support_families": "|".join(position.support_families),
                    "support_count": len(position.support_families),
                }
            )
            del positions[pair]
            counters["scheduled_exits"] += 1

        # Refresh open-position marks to the current bar open before sizing entries.
        for pair, position in positions.items():
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is not None:
                position.last_mark = float(bar["open"])

        equity_open, gross_open = _marked_equity(cash=cash, positions=positions)

        # Entries are deterministic: better PIT membership rank, then pair.
        entries = sorted(
            scheduled.get(int(timestamp.value), []),
            key=lambda item: (int(item["membership_rank"]), str(item["pair"])),
        )
        for item in entries:
            pair = str(item["pair"])
            if pair in positions:
                counters["same_pair_open"] += 1
                continue
            if len(positions) >= MAXIMUM_POSITIONS:
                counters["position_slots_full"] += 1
                continue

            entry_bar = _bar_at(pair, timestamp, frames, lookups)
            if entry_bar is None:
                counters["missing_entry_bar"] += 1
                continue
            exit_bar = _bar_at(
                pair,
                pd.Timestamp(item["scheduled_exit_time"]),
                frames,
                lookups,
            )
            if exit_bar is None:
                counters["missing_exit_bar_precheck"] += 1
                continue

            signal_bar = _bar_at(
                pair,
                pd.Timestamp(item["signal_time"]),
                frames,
                lookups,
            )
            if signal_bar is None:
                raise RD24Error("frozen signal timestamp missing from raw frame")
            capacity_source = float(signal_bar["trailing_24h_quote_turnover_proxy"])
            if not math.isfinite(capacity_source) or capacity_source <= 0.0:
                counters["capacity_unavailable"] += 1
                continue

            equity_open, gross_open = _marked_equity(cash=cash, positions=positions)
            if equity_open <= 0.0:
                continue
            gross_numerator = equity_open * MAXIMUM_GROSS_EXPOSURE - gross_open
            gross_room = max(
                0.0,
                gross_numerator / (1.0 + MAXIMUM_GROSS_EXPOSURE * side_cost),
            )
            if gross_room <= 0.0:
                counters["gross_limit_rejection"] += 1
                continue

            target_notional = equity_open * TARGET_SLOT_NOTIONAL_FRACTION
            capacity_notional = capacity_source * LIQUIDITY_CAPACITY_FRACTION_24H
            notional = min(target_notional, gross_room, capacity_notional)
            if notional < target_notional - 1e-9 and capacity_notional <= min(
                target_notional, gross_room
            ):
                counters["capacity_capped_entries"] += 1

            max_cash_notional = cash / (1.0 + side_cost)
            if max_cash_notional <= 0.0:
                continue
            if notional > max_cash_notional:
                counters["cash_capped_entries"] += 1
                notional = max_cash_notional
            if notional <= 0.0:
                continue

            entry_price = float(entry_bar["open"])
            quantity = notional / entry_price
            entry_cost = notional * side_cost
            cash -= notional + entry_cost
            if cash < -1e-7:
                raise RD24Error("negative cash after entry")
            cash = max(cash, 0.0)
            support = tuple(
                sorted(family for family in str(item["support_families"]).split("|") if family)
            )
            positions[pair] = Position(
                pair=pair,
                signal_time=pd.Timestamp(item["signal_time"]),
                entry_time=timestamp,
                scheduled_exit_time=pd.Timestamp(item["scheduled_exit_time"]),
                entry_price=entry_price,
                quantity=quantity,
                entry_notional=notional,
                entry_cost=entry_cost,
                membership_rank=int(item["membership_rank"]),
                support_families=support,
                period_id=str(item["period_id"]),
                last_mark=entry_price,
            )
            counters["admitted_entries"] += 1

        # Mark at completed current-bar close for drawdown accounting.
        for pair, position in positions.items():
            bar = _bar_at(pair, timestamp, frames, lookups)
            if bar is not None:
                position.last_mark = float(bar["close"])
        equity_close, gross_close = _marked_equity(cash=cash, positions=positions)
        if equity_close < -1e-7:
            raise RD24Error("negative equity observed")
        hourly_equity_values.append(equity_close)
        if timestamp.hour == 23:
            daily_rows.append(
                {
                    "portfolio_id": portfolio_id,
                    "universe_id": universe_id,
                    "cost_multiplier": cost_multiplier,
                    "timestamp": timestamp,
                    "equity": equity_close,
                    "cash": cash,
                    "gross_exposure": gross_close,
                    "gross_exposure_fraction": (
                        gross_close / equity_close if equity_close > 0.0 else math.nan
                    ),
                    "open_positions": len(positions),
                }
            )

    if positions:
        raise RD24Error("open positions remained at RD24 cutoff")
    trade_frame = pd.DataFrame.from_records(trades)
    daily_frame = pd.DataFrame.from_records(daily_rows)

    equity = np.asarray(hourly_equity_values, dtype=float)
    running_peak = np.maximum.accumulate(equity)
    drawdowns = np.divide(
        running_peak - equity,
        running_peak,
        out=np.zeros_like(equity),
        where=running_peak > 0.0,
    )
    final_equity = float(equity[-1]) if len(equity) else INITIAL_EQUITY
    metrics = performance_metrics(
        trade_frame=trade_frame,
        final_equity=final_equity,
        maximum_drawdown=float(drawdowns.max()) if len(drawdowns) else 0.0,
    )
    metrics.update(
        {
            "portfolio_id": portfolio_id,
            "universe_id": universe_id,
            "cost_multiplier": cost_multiplier,
            "minimum_cash": (
                float(daily_frame["cash"].min()) if len(daily_frame) else INITIAL_EQUITY
            ),
        }
    )
    return trade_frame, daily_frame, metrics, counters


def performance_metrics(
    *,
    trade_frame: pd.DataFrame,
    final_equity: float,
    maximum_drawdown: float,
) -> dict[str, Any]:
    if trade_frame.empty:
        return {
            "trade_count": 0,
            "final_equity": final_equity,
            "net_return": final_equity / INITIAL_EQUITY - 1.0,
            "net_pnl": final_equity - INITIAL_EQUITY,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "maximum_drawdown": maximum_drawdown,
            "turnover": 0.0,
        }
    pnl = pd.to_numeric(trade_frame["net_pnl"], errors="raise").astype(float)
    positive = float(pnl.loc[pnl > 0.0].sum())
    negative = float(-pnl.loc[pnl < 0.0].sum())
    if negative > 0.0:
        pf = positive / negative
    elif positive > 0.0:
        pf = math.inf
    else:
        pf = 0.0
    entry_notional = pd.to_numeric(trade_frame["entry_notional"], errors="raise").astype(float)
    exit_notional = pd.to_numeric(trade_frame["exit_notional"], errors="raise").astype(float)
    return {
        "trade_count": len(trade_frame),
        "final_equity": final_equity,
        "net_return": final_equity / INITIAL_EQUITY - 1.0,
        "net_pnl": final_equity - INITIAL_EQUITY,
        "profit_factor": pf,
        "win_rate": float((pnl > 0.0).mean()),
        "maximum_drawdown": maximum_drawdown,
        "turnover": float((entry_notional.sum() + exit_notional.sum()) / INITIAL_EQUITY),
    }


def period_metrics(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if trades.empty:
        return pd.DataFrame(
            columns=[
                "portfolio_id",
                "universe_id",
                "cost_multiplier",
                "period_id",
                "trade_count",
                "net_pnl",
                "profit_factor",
            ]
        )
    grouped = trades.groupby(
        ["portfolio_id", "universe_id", "cost_multiplier", "period_id"],
        sort=True,
    )
    for keys, group in grouped:
        portfolio_id, universe_id, cost_multiplier, period_id = keys
        pnl = pd.to_numeric(group["net_pnl"], errors="raise").astype(float)
        positive = float(pnl.loc[pnl > 0.0].sum())
        negative = float(-pnl.loc[pnl < 0.0].sum())
        pf = positive / negative if negative > 0.0 else (math.inf if positive > 0.0 else 0.0)
        rows.append(
            {
                "portfolio_id": portfolio_id,
                "universe_id": universe_id,
                "cost_multiplier": cost_multiplier,
                "period_id": period_id,
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "profit_factor": pf,
            }
        )
    return pd.DataFrame.from_records(rows)


def concentration_diagnostics(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "total_net_pnl": 0.0,
            "positive_net_pnl_pool": 0.0,
            "largest_winner_net_pnl": 0.0,
            "largest_winner_positive_pnl_share": 0.0,
            "net_pnl_without_largest_winner": 0.0,
            "top_asset": None,
            "top_asset_positive_contribution_share": 0.0,
            "minimum_loao_remaining_net_pnl": 0.0,
            "minimum_loyo_remaining_net_pnl": 0.0,
        }
    frame = trades.copy()
    pnl = pd.to_numeric(frame["net_pnl"], errors="raise").astype(float)
    total = float(pnl.sum())
    positive_pool = float(pnl.loc[pnl > 0.0].sum())
    largest = float(pnl.max())
    largest_share = largest / positive_pool if positive_pool > 0.0 else 0.0
    asset_pnl = frame.assign(_pnl=pnl).groupby("pair", sort=True)["_pnl"].sum()
    positive_asset = asset_pnl.loc[asset_pnl > 0.0]
    if len(positive_asset):
        top_asset = str(positive_asset.idxmax())
        top_asset_share = (
            float(positive_asset.max()) / positive_pool if positive_pool > 0.0 else 0.0
        )
    else:
        top_asset = None
        top_asset_share = 0.0
    loao = [total - float(value) for value in asset_pnl.values]
    years = pd.to_datetime(frame["entry_time"], utc=True, errors="raise").dt.year
    year_pnl = frame.assign(_pnl=pnl, _year=years).groupby("_year", sort=True)["_pnl"].sum()
    loyo = [total - float(value) for value in year_pnl.values]
    return {
        "total_net_pnl": total,
        "positive_net_pnl_pool": positive_pool,
        "largest_winner_net_pnl": largest,
        "largest_winner_positive_pnl_share": largest_share,
        "net_pnl_without_largest_winner": total - largest,
        "top_asset": top_asset,
        "top_asset_positive_contribution_share": top_asset_share,
        "minimum_loao_remaining_net_pnl": min(loao) if loao else total,
        "minimum_loyo_remaining_net_pnl": min(loyo) if loyo else total,
    }


def fixed_path_pf1_break_even_multiplier(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    gross = pd.to_numeric(trades["gross_pnl"], errors="raise").astype(float).to_numpy()
    entry = pd.to_numeric(trades["entry_notional"], errors="raise").astype(float).to_numpy()
    exit_ = pd.to_numeric(trades["exit_notional"], errors="raise").astype(float).to_numpy()

    def pf(multiplier: float) -> float:
        costs = BASE_ROUND_TRIP_COST * multiplier / 2.0 * (entry + exit_)
        pnl = gross - costs
        positive = float(pnl[pnl > 0.0].sum())
        negative = float(-pnl[pnl < 0.0].sum())
        if negative <= 0.0:
            return math.inf if positive > 0.0 else 0.0
        return positive / negative

    if pf(0.0) < 1.0:
        return 0.0
    high = 2.0
    while high < 128.0 and pf(high) >= 1.0:
        high *= 2.0
    if high >= 128.0 and pf(high) >= 1.0:
        return high
    low = 0.0
    for _ in range(80):
        mid = (low + high) / 2.0
        if pf(mid) >= 1.0:
            low = mid
        else:
            high = mid
    return low


def family_attribution(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for raw in trades.to_dict(orient="records"):
        support = [family for family in str(raw["support_families"]).split("|") if family]
        if not support:
            continue
        share = float(raw["net_pnl"]) / len(support)
        for family in support:
            rows.append(
                {
                    "portfolio_id": raw["portfolio_id"],
                    "universe_id": raw["universe_id"],
                    "cost_multiplier": raw["cost_multiplier"],
                    "family_id": family,
                    "attributed_net_pnl": share,
                    "trade_weight": 1.0 / len(support),
                }
            )
    if not rows:
        return pd.DataFrame(
            columns=[
                "portfolio_id",
                "universe_id",
                "cost_multiplier",
                "family_id",
                "attributed_net_pnl",
                "trade_weight",
            ]
        )
    frame = pd.DataFrame.from_records(rows)
    return frame.groupby(
        ["portfolio_id", "universe_id", "cost_multiplier", "family_id"],
        as_index=False,
        sort=True,
    ).agg(
        attributed_net_pnl=("attributed_net_pnl", "sum"),
        attributed_trade_equivalents=("trade_weight", "sum"),
    )


def standalone_hard_gate_rows(
    *,
    run_metrics: pd.DataFrame,
    period_frame: pd.DataFrame,
    concentrations: pd.DataFrame,
    break_even: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict[str, Any]] = []
    passed_families: list[str] = []
    for family in QUALIFIED_FAMILIES:
        family_pass = True
        for universe in ("C2", "D2", "E2"):
            base = run_metrics.loc[
                (run_metrics["portfolio_id"] == family)
                & (run_metrics["universe_id"] == universe)
                & (run_metrics["cost_multiplier"] == 1.0)
            ]
            stress = run_metrics.loc[
                (run_metrics["portfolio_id"] == family)
                & (run_metrics["universe_id"] == universe)
                & (run_metrics["cost_multiplier"] == 2.0)
            ]
            if len(base) != 1 or len(stress) != 1:
                raise RD24Error("standalone run metric cardinality drifted")
            base_row = base.iloc[0]
            stress_row = stress.iloc[0]
            period_subset = period_frame.loc[
                (period_frame["portfolio_id"] == family)
                & (period_frame["universe_id"] == universe)
                & (period_frame["cost_multiplier"] == 2.0)
            ]
            concentration = concentrations.loc[
                (concentrations["portfolio_id"] == family)
                & (concentrations["universe_id"] == universe)
                & (concentrations["cost_multiplier"] == 2.0)
            ]
            be = break_even.loc[
                (break_even["portfolio_id"] == family) & (break_even["universe_id"] == universe)
            ]
            if len(concentration) != 1 or len(be) != 1:
                raise RD24Error("standalone diagnostic cardinality drifted")
            periods_positive = len(period_subset) == len(PERIODS) and bool(
                (period_subset["net_pnl"] > 0.0).all()
            )
            conc = concentration.iloc[0]
            checks = {
                "BASE_NET_RETURN_POSITIVE": float(base_row["net_return"]) > 0.0,
                "STRESS_2X_NET_RETURN_POSITIVE": float(stress_row["net_return"]) > 0.0,
                "STRESS_2X_PROFIT_FACTOR_GTE_1_05": (
                    float(stress_row["profit_factor"]) >= MINIMUM_PROFIT_FACTOR_2X
                ),
                "STRESS_2X_MAX_DRAWDOWN_LTE_20PCT": (
                    float(stress_row["maximum_drawdown"]) <= MAXIMUM_DRAWDOWN_HARD
                ),
                "STRESS_2X_TRADES_GTE_75": int(stress_row["trade_count"]) >= MINIMUM_TRADES,
                "BOTH_SELECTION_PERIODS_NET_PNL_POSITIVE": periods_positive,
                "STRESS_2X_LARGEST_WINNER_REMOVAL_POSITIVE": (
                    float(conc["net_pnl_without_largest_winner"]) > 0.0
                ),
                "STRESS_2X_LOAO_MIN_REMAINING_PNL_POSITIVE": (
                    float(conc["minimum_loao_remaining_net_pnl"]) > 0.0
                ),
                "STRESS_2X_LOYO_MIN_REMAINING_PNL_POSITIVE": (
                    float(conc["minimum_loyo_remaining_net_pnl"]) > 0.0
                ),
                "PF1_BREAK_EVEN_COST_MULTIPLIER_GTE_2": (
                    float(be.iloc[0]["pf1_break_even_cost_multiplier"])
                    >= MINIMUM_BREAK_EVEN_COST_MULTIPLIER
                ),
                "CASH_FEASIBLE": float(stress_row["minimum_cash"]) >= -1e-8,
            }
            for gate_id, passed in checks.items():
                rows.append(
                    {
                        "portfolio_id": family,
                        "universe_id": universe,
                        "gate_id": gate_id,
                        "passed": bool(passed),
                    }
                )
                family_pass = family_pass and bool(passed)
        if family_pass:
            passed_families.append(family)
    return pd.DataFrame.from_records(rows), passed_families


def validate_constants() -> None:
    if HOLDING_HOURS != 168:
        raise RD24Error("RD23-selected horizon drifted")
    if not math.isclose(TARGET_SLOT_NOTIONAL_FRACTION, 0.18):
        raise RD24Error("equal-slot notional fraction drifted")
    if not math.isclose(BASE_ROUND_TRIP_COST * 2.0, 0.005):
        raise RD24Error("2x cost contract drifted")
    if len(QUALIFIED_FAMILIES) != 4:
        raise RD24Error("qualified family count drifted")
