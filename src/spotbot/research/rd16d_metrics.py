from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, cast

import numpy as np
import pandas as pd

from spotbot.research.rd16d_common import (
    BASE_FEE_RATE,
    INITIAL_EQUITY,
    STRATEGIC_MONTHLY_TARGET,
    RD16DInputError,
    iso,
    timestamp,
)

MAXIMUM_POSITIONS: Final = 3
MAXIMUM_OPEN_RISK_FRACTION: Final = 0.015
HOLDING_BUCKETS: Final = (
    (1, 6, "01_06_BARS"),
    (7, 12, "07_12_BARS"),
    (13, 24, "13_24_BARS"),
    (25, 36, "25_36_BARS"),
    (37, 48, "37_48_BARS"),
)


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    classification: str
    strategic_objective_met: bool
    gates: dict[str, bool]


def _finite_float(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise RD16DInputError(f"{name} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise RD16DInputError(f"{name} must be numeric.") from error
    if not math.isfinite(result):
        raise RD16DInputError(f"{name} must be finite.")
    return result


def _optional_float(value: object) -> float | None:
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    gross_profit = float(numeric[numeric > 0.0].sum())
    gross_loss = abs(float(numeric[numeric < 0.0].sum()))
    if gross_loss == 0.0:
        return None
    return gross_profit / gross_loss


def _maximum_streak(values: Sequence[bool], target: bool) -> int:
    maximum = 0
    current = 0
    for value in values:
        if value is target:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def _normalize_trade_times(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
    ):
        if column not in normalized.columns:
            raise RD16DInputError(f"Trade ledger missing column: {column}")
        parsed = pd.to_datetime(
            normalized[column],
            utc=True,
            errors="coerce",
        )
        if bool(parsed.isna().any()):
            raise RD16DInputError(f"Trade ledger has invalid timestamps in {column}.")
        normalized[column] = parsed.astype("datetime64[ns, UTC]")
    return normalized.sort_values(
        by=["entry_open_time", "symbol", "signal_close"],
        kind="stable",
    ).reset_index(drop=True)


def market_regime_from_row(row: Mapping[str, object]) -> str:
    daily_close = _finite_float(row["1d_close"], name="1d_close")
    daily_ema50 = _finite_float(row["1d_ema50"], name="1d_ema50")
    daily_ema200 = _finite_float(row["1d_ema200"], name="1d_ema200")
    weekly_close = _finite_float(row["1w_close"], name="1w_close")
    weekly_ema40 = _finite_float(row["1w_ema40"], name="1w_ema40")

    if daily_close > daily_ema200 and daily_ema50 > daily_ema200 and weekly_close > weekly_ema40:
        return "STRONG_BULL"
    if daily_close > daily_ema50 and weekly_close > weekly_ema40:
        return "BULL"
    if daily_close < daily_ema200 and weekly_close < weekly_ema40:
        return "BEAR"
    return "TRANSITION"


def volatility_regime_from_row(row: Mapping[str, object]) -> str:
    ratio = _finite_float(row["4h_atr_ratio"], name="4h_atr_ratio")
    if ratio <= 0.80:
        return "LOW_VOLATILITY"
    if ratio <= 1.20:
        return "NORMAL_VOLATILITY"
    return "HIGH_VOLATILITY"


def enrich_trades(
    trades: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
    feature_frames: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    normalized = _normalize_trade_times(trades)
    required_numeric = (
        "entry_price",
        "exit_price",
        "risk_per_unit",
        "risk_budget",
        "quantity",
        "gross_pnl",
        "fees",
        "net_pnl",
        "bars_held",
    )
    missing = sorted(set(required_numeric).difference(normalized.columns))
    if missing:
        raise RD16DInputError(f"Trade ledger missing numeric columns: {missing}")

    hourly_positions: dict[str, dict[pd.Timestamp, int]] = {}
    normalized_hourly: dict[str, pd.DataFrame] = {}
    feature_records: dict[str, dict[pd.Timestamp, dict[str, object]]] = {}

    for symbol, raw_hourly in hourly_frames.items():
        hourly = raw_hourly.copy()
        hourly["timestamp"] = pd.to_datetime(hourly["timestamp"], utc=True, errors="raise").astype(
            "datetime64[ns, UTC]"
        )
        hourly = hourly.sort_values("timestamp", kind="stable").reset_index(drop=True)
        normalized_hourly[symbol] = hourly
        hourly_positions[symbol] = {
            timestamp(value): position
            for position, value in enumerate(hourly["timestamp"].tolist())
        }

    for symbol, raw_features in feature_frames.items():
        features = raw_features.copy()
        features["timestamp"] = pd.to_datetime(
            features["timestamp"], utc=True, errors="raise"
        ).astype("datetime64[ns, UTC]")
        records: dict[pd.Timestamp, dict[str, object]] = {}
        for raw in features.to_dict(orient="records"):
            record = cast(dict[str, object], raw)
            records[timestamp(record["timestamp"])] = record
        feature_records[symbol] = records

    enriched_records: list[dict[str, object]] = []
    for raw in normalized.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        symbol = str(record["symbol"])
        if symbol not in normalized_hourly or symbol not in feature_records:
            raise RD16DInputError(f"Missing market data for trade symbol: {symbol}")
        entry_bar_close = timestamp(record["entry_bar_close"])
        exit_bar_close = timestamp(record["exit_bar_close"])
        entry_position = hourly_positions[symbol].get(entry_bar_close)
        exit_position = hourly_positions[symbol].get(exit_bar_close)
        if entry_position is None or exit_position is None:
            raise RD16DInputError(
                f"Trade bar not found for {symbol}: {entry_bar_close} -> {exit_bar_close}"
            )
        if exit_position < entry_position:
            raise RD16DInputError("Trade exit precedes entry.")
        path = normalized_hourly[symbol].iloc[entry_position : exit_position + 1]
        entry_price = _finite_float(record["entry_price"], name="entry_price")
        risk_per_unit = _finite_float(record["risk_per_unit"], name="risk_per_unit")
        risk_budget = _finite_float(record["risk_budget"], name="risk_budget")
        if risk_per_unit <= 0.0 or risk_budget <= 0.0:
            raise RD16DInputError("Trade risk must be positive.")
        maximum_high = float(pd.to_numeric(path["high"], errors="raise").max())
        minimum_low = float(pd.to_numeric(path["low"], errors="raise").min())
        gross_pnl = _finite_float(record["gross_pnl"], name="gross_pnl")
        net_pnl = _finite_float(record["net_pnl"], name="net_pnl")
        gross_r = gross_pnl / risk_budget
        net_r = net_pnl / risk_budget
        mfe_r = (maximum_high - entry_price) / risk_per_unit
        mae_r = (minimum_low - entry_price) / risk_per_unit
        exit_efficiency = net_r / mfe_r if mfe_r > 0.0 else None
        signal_close = timestamp(record["signal_close"])
        feature = feature_records[symbol].get(signal_close)
        if feature is None:
            raise RD16DInputError(f"Feature row missing for {symbol} at {signal_close}.")

        enriched_records.append(
            {
                **record,
                "gross_r": gross_r,
                "net_r": net_r,
                "mfe_r": mfe_r,
                "mae_r": mae_r,
                "exit_efficiency": exit_efficiency,
                "giveback_r": mfe_r - gross_r,
                "maximum_high": maximum_high,
                "minimum_low": minimum_low,
                "market_regime": market_regime_from_row(feature),
                "volatility_regime": volatility_regime_from_row(feature),
                "entry_year": signal_close.year,
                "entry_month": signal_close.strftime("%Y-%m"),
                "exit_year": exit_bar_close.year,
                "exit_month": exit_bar_close.strftime("%Y-%m"),
            }
        )
    return pd.DataFrame.from_records(enriched_records)


def _close_price_maps(
    hourly_frames: Mapping[str, pd.DataFrame],
) -> dict[str, dict[pd.Timestamp, float]]:
    result: dict[str, dict[pd.Timestamp, float]] = {}
    for symbol, raw in hourly_frames.items():
        frame = raw.loc[:, ["timestamp", "close"]].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").astype(
            "datetime64[ns, UTC]"
        )
        result[symbol] = {
            timestamp(raw_timestamp): _finite_float(raw_close, name="close")
            for raw_timestamp, raw_close in frame.itertuples(index=False, name=None)
        }
    return result


def build_equity_curve(
    trades: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
    timeline: pd.DatetimeIndex,
    cost_multiplier: float = 1.0,
) -> pd.DataFrame:
    if cost_multiplier <= 0.0 or not math.isfinite(cost_multiplier):
        raise ValueError("cost_multiplier must be positive and finite.")
    normalized = _normalize_trade_times(trades)
    close_maps = _close_price_maps(hourly_frames)
    entry_events: dict[pd.Timestamp, list[dict[str, object]]] = {}
    exit_events: dict[pd.Timestamp, list[dict[str, object]]] = {}
    for raw in normalized.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        entry_events.setdefault(timestamp(record["entry_open_time"]), []).append(record)
        exit_events.setdefault(timestamp(record["exit_bar_close"]), []).append(record)

    cash = INITIAL_EQUITY
    cumulative_fees = 0.0
    open_positions: dict[str, dict[str, object]] = {}
    rows: list[dict[str, object]] = []

    for raw_timestamp in timeline:
        current = timestamp(raw_timestamp)
        for record in exit_events.get(current, []):
            trade_id = str(record["trade_id"])
            position = open_positions.pop(trade_id, None)
            if position is None:
                raise RD16DInputError(f"Exit without open position: {trade_id} at {current}")
            quantity = _finite_float(record["quantity"], name="quantity")
            exit_price = _finite_float(record["exit_price"], name="exit_price")
            exit_fee = quantity * exit_price * BASE_FEE_RATE * cost_multiplier
            cash += quantity * exit_price - exit_fee
            cumulative_fees += exit_fee

        for record in entry_events.get(current, []):
            trade_id = str(record["trade_id"])
            if trade_id in open_positions:
                raise RD16DInputError(f"Duplicate open trade ID: {trade_id}")
            quantity = _finite_float(record["quantity"], name="quantity")
            entry_price = _finite_float(record["entry_price"], name="entry_price")
            entry_fee = quantity * entry_price * BASE_FEE_RATE * cost_multiplier
            cash -= quantity * entry_price + entry_fee
            cumulative_fees += entry_fee
            open_positions[trade_id] = record

        market_value = 0.0
        for position in open_positions.values():
            symbol = str(position["symbol"])
            entry_time = timestamp(position["entry_open_time"])
            if current == entry_time:
                mark = _finite_float(position["entry_price"], name="entry_price")
            else:
                raw_mark = close_maps.get(symbol, {}).get(current)
                if raw_mark is None:
                    raise RD16DInputError(f"Missing hourly mark for {symbol} at {current}.")
                mark = raw_mark
            quantity = _finite_float(position["quantity"], name="quantity")
            market_value += quantity * mark

        equity = cash + market_value
        rows.append(
            {
                "timestamp": current,
                "cash": cash,
                "market_value": market_value,
                "equity": equity,
                "open_positions": len(open_positions),
                "gross_exposure": (market_value / equity if equity != 0.0 else None),
                "cumulative_fees": cumulative_fees,
            }
        )

    if open_positions:
        raise RD16DInputError(f"Open positions remain after timeline: {sorted(open_positions)}")
    curve = pd.DataFrame.from_records(rows)
    peaks = pd.to_numeric(curve["equity"], errors="raise").cummax()
    curve["drawdown"] = pd.to_numeric(curve["equity"], errors="raise") / peaks - 1.0
    return curve


def _daily_equity(curve: pd.DataFrame) -> pd.Series:
    working = curve.loc[:, ["timestamp", "equity"]].copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    return working.set_index("timestamp")["equity"].resample("1D").last().dropna()


def _return_statistics(daily: pd.Series) -> tuple[float | None, float | None, float | None]:
    if daily.empty or bool((daily <= 0.0).any()):
        return None, None, None
    returns = daily.pct_change().dropna()
    if returns.empty:
        return None, None, None
    mean = float(returns.mean())
    std = float(returns.std(ddof=1))
    downside = returns[returns < 0.0]
    downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sharpe = mean / std * math.sqrt(365.25) if std > 0.0 else None
    sortino = mean / downside_std * math.sqrt(365.25) if downside_std > 0.0 else None
    volatility = std * math.sqrt(365.25)
    return sharpe, sortino, volatility


def performance_metrics(
    curve: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    cost_multiplier: float,
) -> dict[str, object]:
    if curve.empty:
        raise RD16DInputError("Equity curve cannot be empty.")
    start = _finite_float(curve.iloc[0]["equity"], name="starting_equity")
    final = _finite_float(curve.iloc[-1]["equity"], name="final_equity")
    first_timestamp = timestamp(curve.iloc[0]["timestamp"])
    last_timestamp = timestamp(curve.iloc[-1]["timestamp"])
    years = max((last_timestamp - first_timestamp).total_seconds() / (365.25 * 86400.0), 1e-12)
    net_return = final / start - 1.0
    cagr = (final / start) ** (1.0 / years) - 1.0 if final > 0.0 else None
    months = years * 12.0
    monthly_geometric = (
        (final / start) ** (1.0 / months) - 1.0 if final > 0.0 and months > 0.0 else None
    )
    drawdown = pd.to_numeric(curve["drawdown"], errors="raise")
    maximum_drawdown = abs(float(drawdown.min()))
    daily = _daily_equity(curve)
    sharpe, sortino, volatility = _return_statistics(daily)
    ulcer_index = float(np.sqrt(np.mean(np.square(drawdown.to_numpy(dtype=float)))))
    adjusted_pnl = (
        pd.to_numeric(trades["gross_pnl"], errors="raise")
        - pd.to_numeric(trades["fees"], errors="raise") * cost_multiplier
    )
    wins = adjusted_pnl > 0.0
    losses = adjusted_pnl < 0.0
    ordered_wins = wins.tolist()
    gross_profit = float(adjusted_pnl[wins].sum())
    gross_loss = abs(float(adjusted_pnl[losses].sum()))
    r_values = adjusted_pnl / pd.to_numeric(trades["risk_budget"], errors="raise")
    exposure = pd.to_numeric(curve["open_positions"], errors="raise") > 0
    gross_exposure = pd.to_numeric(curve["gross_exposure"], errors="coerce")
    total_fees = float(pd.to_numeric(trades["fees"], errors="raise").sum() * cost_multiplier)
    total_notional = float(pd.to_numeric(trades["notional"], errors="raise").sum())
    return {
        "starting_equity": start,
        "final_equity": final,
        "net_return": net_return,
        "cagr": cagr,
        "monthly_geometric_return": monthly_geometric,
        "maximum_drawdown": maximum_drawdown,
        "calmar_ratio": (
            cagr / maximum_drawdown if cagr is not None and maximum_drawdown > 0.0 else None
        ),
        "recovery_factor": (net_return / maximum_drawdown if maximum_drawdown > 0.0 else None),
        "annualized_sharpe": sharpe,
        "annualized_sortino": sortino,
        "annualized_volatility": volatility,
        "ulcer_index": ulcer_index,
        "trade_count": len(trades),
        "winning_trades": int(wins.sum()),
        "losing_trades": int(losses.sum()),
        "breakeven_trades": int((adjusted_pnl == 0.0).sum()),
        "win_rate": float(wins.mean()) if len(trades) else None,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0.0 else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "expectancy_per_trade": float(adjusted_pnl.mean()) if len(trades) else None,
        "average_r": float(r_values.mean()) if len(trades) else None,
        "median_r": float(r_values.median()) if len(trades) else None,
        "payoff_ratio": (
            float(adjusted_pnl[wins].mean()) / abs(float(adjusted_pnl[losses].mean()))
            if bool(wins.any()) and bool(losses.any())
            else None
        ),
        "average_holding_bars": (
            float(pd.to_numeric(trades["bars_held"], errors="raise").mean())
            if len(trades)
            else None
        ),
        "median_holding_bars": (
            float(pd.to_numeric(trades["bars_held"], errors="raise").median())
            if len(trades)
            else None
        ),
        "maximum_winning_streak": _maximum_streak(ordered_wins, True),
        "maximum_losing_streak": _maximum_streak(ordered_wins, False),
        "total_fees": total_fees,
        "turnover_on_initial_equity": total_notional / INITIAL_EQUITY,
        "exposure_fraction": float(exposure.mean()),
        "average_gross_exposure": (
            float(gross_exposure.mean()) if bool(gross_exposure.notna().any()) else None
        ),
        "maximum_positions_observed": int(
            pd.to_numeric(curve["open_positions"], errors="raise").max()
        ),
        "minimum_cash": float(pd.to_numeric(curve["cash"], errors="raise").min()),
        "minimum_equity": float(pd.to_numeric(curve["equity"], errors="raise").min()),
        "capital_feasible": bool(
            float(pd.to_numeric(curve["cash"], errors="raise").min()) >= -1e-6
            and float(pd.to_numeric(curve["equity"], errors="raise").min()) > 0.0
        ),
        "cost_multiplier": cost_multiplier,
    }


def period_return_rows(
    curve: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    family_id: str,
    period: str,
) -> list[dict[str, object]]:
    daily = _daily_equity(curve)
    daily_index = pd.DatetimeIndex(daily.index)
    if period == "year":
        keys = daily_index.year.astype(str)
        trade_keys = pd.to_datetime(trades["entry_open_time"], utc=True).dt.year.astype(str)
    elif period == "month":
        keys = daily_index.strftime("%Y-%m")
        trade_keys = pd.to_datetime(trades["entry_open_time"], utc=True).dt.strftime("%Y-%m")
    else:
        raise ValueError(f"Unsupported period: {period}")

    rows: list[dict[str, object]] = []
    previous_equity = INITIAL_EQUITY
    for key in pd.Index(keys).unique().tolist():
        mask = keys == key
        values = daily[mask]
        if values.empty:
            continue
        end_equity = float(values.iloc[-1])
        period_return = end_equity / previous_equity - 1.0 if previous_equity != 0.0 else None
        rows.append(
            {
                "family_id": family_id,
                "period": str(key),
                "start_equity": previous_equity,
                "end_equity": end_equity,
                "return": period_return,
                "trade_count": int((trade_keys == str(key)).sum()),
            }
        )
        previous_equity = end_equity
    return rows


def _group_performance_rows(
    trades: pd.DataFrame,
    *,
    family_id: str,
    group_column: str,
    output_column: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, group in trades.groupby(group_column, sort=True, dropna=False):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "family_id": family_id,
                output_column: str(key),
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": float(pnl.sum()) / INITIAL_EQUITY,
                "win_rate": float((pnl > 0.0).mean()),
                "profit_factor": _profit_factor(pnl),
                "average_r": float((pnl / risk).mean()),
                "median_r": float((pnl / risk).median()),
                "average_mfe_r": float(pd.to_numeric(group["mfe_r"], errors="raise").mean()),
                "average_mae_r": float(pd.to_numeric(group["mae_r"], errors="raise").mean()),
                "average_holding_bars": float(
                    pd.to_numeric(group["bars_held"], errors="raise").mean()
                ),
            }
        )
    return rows


def asset_attribution_rows(trades: pd.DataFrame, *, family_id: str) -> list[dict[str, object]]:
    return _group_performance_rows(
        trades,
        family_id=family_id,
        group_column="symbol",
        output_column="symbol",
    )


def regime_performance_rows(trades: pd.DataFrame, *, family_id: str) -> list[dict[str, object]]:
    rows = _group_performance_rows(
        trades,
        family_id=family_id,
        group_column="market_regime",
        output_column="market_regime",
    )
    volatility = _group_performance_rows(
        trades,
        family_id=family_id,
        group_column="volatility_regime",
        output_column="volatility_regime",
    )
    for row in rows:
        row["regime_type"] = "MARKET_TREND"
        row["regime"] = row.pop("market_regime")
    for row in volatility:
        row["regime_type"] = "VOLATILITY"
        row["regime"] = row.pop("volatility_regime")
    return [*rows, *volatility]


def exit_reason_rows(trades: pd.DataFrame, *, family_id: str) -> list[dict[str, object]]:
    rows = _group_performance_rows(
        trades,
        family_id=family_id,
        group_column="exit_reason",
        output_column="exit_reason",
    )
    for row in rows:
        reason = row["exit_reason"]
        group = trades[trades["exit_reason"] == reason]
        efficiencies = pd.to_numeric(group["exit_efficiency"], errors="coerce")
        row["average_exit_efficiency"] = (
            float(efficiencies.mean()) if bool(efficiencies.notna().any()) else None
        )
        row["average_giveback_r"] = float(pd.to_numeric(group["giveback_r"], errors="raise").mean())
    return rows


def holding_period_rows(trades: pd.DataFrame, *, family_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    holding = pd.to_numeric(trades["bars_held"], errors="raise")
    for lower, upper, label in HOLDING_BUCKETS:
        group = trades[(holding >= lower) & (holding <= upper)]
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "family_id": family_id,
                "holding_bucket": label,
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": float(pnl.sum()) / INITIAL_EQUITY,
                "win_rate": float((pnl > 0.0).mean()) if len(group) else None,
                "profit_factor": _profit_factor(pnl),
                "average_r": float((pnl / risk).mean()) if len(group) else None,
            }
        )
    return rows


def concentration_row(trades: pd.DataFrame, *, family_id: str) -> dict[str, object]:
    pnl = pd.to_numeric(trades["net_pnl"], errors="raise")
    positive = pnl[pnl > 0.0].sort_values(ascending=False)
    gross_profit = float(positive.sum())
    losses = pnl[pnl < 0.0].abs().sort_values(ascending=False)
    gross_loss = float(losses.sum())

    def positive_share(count: int) -> float | None:
        if gross_profit <= 0.0:
            return None
        return float(positive.head(count).sum()) / gross_profit

    profit_weights = positive / gross_profit if gross_profit > 0.0 else pd.Series(dtype=float)
    asset_positive = (
        trades.assign(_positive=pnl.clip(lower=0.0))
        .groupby("symbol", sort=True)["_positive"]
        .sum()
        .sort_values(ascending=False)
    )
    year_positive = (
        trades.assign(_positive=pnl.clip(lower=0.0))
        .groupby("entry_year", sort=True)["_positive"]
        .sum()
        .sort_values(ascending=False)
    )
    top_asset_share = (
        _finite_float(asset_positive.iloc[0], name="top_asset_profit") / gross_profit
        if gross_profit > 0.0 and not asset_positive.empty
        else None
    )
    top_year_share = (
        _finite_float(year_positive.iloc[0], name="top_year_profit") / gross_profit
        if gross_profit > 0.0 and not year_positive.empty
        else None
    )
    return {
        "family_id": family_id,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "top_1_trade_profit_share": positive_share(1),
        "top_3_trade_profit_share": positive_share(3),
        "top_5_trade_profit_share": positive_share(5),
        "top_10_trade_profit_share": positive_share(10),
        "positive_trade_hhi": (
            float(np.square(profit_weights.to_numpy(dtype=float)).sum())
            if not profit_weights.empty
            else None
        ),
        "top_asset_profit_share": top_asset_share,
        "top_asset": str(asset_positive.index[0]) if not asset_positive.empty else "",
        "top_year_profit_share": top_year_share,
        "top_year": str(year_positive.index[0]) if not year_positive.empty else "",
        "largest_loss_share": (
            _finite_float(
                losses.iloc[0],
                name="largest_loss",
            )
            / gross_loss
            if gross_loss > 0.0 and not losses.empty
            else None
        ),
        "net_return_without_top_1": float(pnl.sum() - positive.head(1).sum()) / INITIAL_EQUITY,
        "net_return_without_top_3": float(pnl.sum() - positive.head(3).sum()) / INITIAL_EQUITY,
        "net_return_without_top_5": float(pnl.sum() - positive.head(5).sum()) / INITIAL_EQUITY,
        "net_return_without_top_10": float(pnl.sum() - positive.head(10).sum()) / INITIAL_EQUITY,
    }


def trade_distribution_row(trades: pd.DataFrame, *, family_id: str) -> dict[str, object]:
    net_r = pd.to_numeric(trades["net_r"], errors="raise")
    mfe = pd.to_numeric(trades["mfe_r"], errors="raise")
    mae = pd.to_numeric(trades["mae_r"], errors="raise")
    holding = pd.to_numeric(trades["bars_held"], errors="raise")
    quantiles = net_r.quantile([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
    p05 = float(quantiles.loc[0.05])
    p95 = float(quantiles.loc[0.95])
    return {
        "family_id": family_id,
        "net_r_p05": p05,
        "net_r_p10": float(quantiles.loc[0.10]),
        "net_r_p25": float(quantiles.loc[0.25]),
        "net_r_p50": float(quantiles.loc[0.50]),
        "net_r_p75": float(quantiles.loc[0.75]),
        "net_r_p90": float(quantiles.loc[0.90]),
        "net_r_p95": p95,
        "net_r_skew": float(cast(float, net_r.skew())),
        "tail_ratio": p95 / abs(p05) if p05 < 0.0 else None,
        "mfe_r_median": float(mfe.median()),
        "mfe_r_p90": float(mfe.quantile(0.90)),
        "mae_r_median": float(mae.median()),
        "mae_r_p10": float(mae.quantile(0.10)),
        "holding_bars_p50": float(holding.median()),
        "holding_bars_p90": float(holding.quantile(0.90)),
    }


def rolling_window_rows(curve: pd.DataFrame, *, family_id: str) -> list[dict[str, object]]:
    daily = _daily_equity(curve)
    rows: list[dict[str, object]] = []
    for days in (90, 180, 365):
        rolling = daily / daily.shift(days) - 1.0
        valid = rolling.replace([np.inf, -np.inf], np.nan).dropna()
        rows.append(
            {
                "family_id": family_id,
                "window_days": days,
                "observation_count": len(valid),
                "minimum_return": float(valid.min()) if len(valid) else None,
                "p10_return": float(valid.quantile(0.10)) if len(valid) else None,
                "median_return": float(valid.median()) if len(valid) else None,
                "mean_return": float(valid.mean()) if len(valid) else None,
                "p90_return": float(valid.quantile(0.90)) if len(valid) else None,
                "maximum_return": float(valid.max()) if len(valid) else None,
                "positive_fraction": float((valid > 0.0).mean()) if len(valid) else None,
            }
        )
    return rows


def drawdown_episode_rows(
    curve: pd.DataFrame,
    *,
    family_id: str,
    limit: int = 10,
) -> list[dict[str, object]]:
    working = curve.loc[:, ["timestamp", "equity"]].copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    equity = pd.to_numeric(working["equity"], errors="raise").to_numpy(dtype=float)
    times = [timestamp(value) for value in working["timestamp"].tolist()]
    episodes: list[dict[str, object]] = []
    peak_index = 0
    trough_index = 0
    in_drawdown = False

    for index in range(1, len(equity)):
        if equity[index] >= equity[peak_index]:
            if in_drawdown:
                depth = equity[trough_index] / equity[peak_index] - 1.0
                episodes.append(
                    {
                        "family_id": family_id,
                        "peak_time": iso(times[peak_index]),
                        "trough_time": iso(times[trough_index]),
                        "recovery_time": iso(times[index]),
                        "drawdown": abs(depth),
                        "hours_to_trough": int(
                            (times[trough_index] - times[peak_index]).total_seconds() / 3600
                        ),
                        "hours_to_recovery": int(
                            (times[index] - times[trough_index]).total_seconds() / 3600
                        ),
                        "recovered": True,
                    }
                )
            peak_index = index
            trough_index = index
            in_drawdown = False
        else:
            in_drawdown = True
            if equity[index] < equity[trough_index]:
                trough_index = index

    if in_drawdown:
        depth = equity[trough_index] / equity[peak_index] - 1.0
        episodes.append(
            {
                "family_id": family_id,
                "peak_time": iso(times[peak_index]),
                "trough_time": iso(times[trough_index]),
                "recovery_time": "",
                "drawdown": abs(depth),
                "hours_to_trough": int(
                    (times[trough_index] - times[peak_index]).total_seconds() / 3600
                ),
                "hours_to_recovery": None,
                "recovered": False,
            }
        )
    return sorted(
        episodes,
        key=lambda row: _finite_float(row["drawdown"], name="drawdown"),
        reverse=True,
    )[:limit]


def replay_admission_rows(
    evaluated: pd.DataFrame,
    admitted: pd.DataFrame,
    *,
    family_id: str,
) -> list[dict[str, object]]:
    normalized = _normalize_trade_times(evaluated)
    ordered = normalized.sort_values(
        by=["entry_open_time", "symbol", "signal_close"],
        kind="stable",
    ).reset_index(drop=True)
    open_trades: list[dict[str, object]] = []
    annotated: list[dict[str, object]] = []

    for raw in ordered.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        entry_time = timestamp(record["entry_open_time"])
        open_trades = [
            trade for trade in open_trades if timestamp(trade["exit_bar_close"]) > entry_time
        ]
        symbol = str(record["symbol"])
        if any(str(trade["symbol"]) == symbol for trade in open_trades):
            reason = "REJECTED_SAME_ASSET"
        elif len(open_trades) >= MAXIMUM_POSITIONS:
            reason = "REJECTED_MAX_POSITIONS"
        else:
            risk_budget = _finite_float(record["risk_budget"], name="risk_budget")
            open_risk = (
                sum(
                    _finite_float(trade["risk_budget"], name="risk_budget") for trade in open_trades
                )
                + risk_budget
            ) / INITIAL_EQUITY
            if risk_budget <= 0.0:
                reason = "REJECTED_INVALID_RISK"
            elif open_risk > MAXIMUM_OPEN_RISK_FRACTION + 1e-12:
                reason = "REJECTED_MAX_OPEN_RISK"
            else:
                reason = "ADMITTED"
                open_trades.append(record)
        annotated.append({**record, "admission_reason": reason})

    annotated_frame = pd.DataFrame.from_records(annotated)
    admitted_count = int((annotated_frame["admission_reason"] == "ADMITTED").sum())
    if admitted_count != len(admitted):
        raise RD16DInputError(
            f"Admission replay mismatch for {family_id}: "
            f"expected {len(admitted)}, got {admitted_count}"
        )

    rows: list[dict[str, object]] = []
    for raw_reason, group in annotated_frame.groupby("admission_reason", sort=True):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "family_id": family_id,
                "admission_reason": str(raw_reason),
                "candidate_count": len(group),
                "hypothetical_net_pnl": float(pnl.sum()),
                "hypothetical_return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "hypothetical_win_rate": float((pnl > 0.0).mean()),
                "hypothetical_profit_factor": _profit_factor(pnl),
                "hypothetical_average_r": float((pnl / risk).mean()),
            }
        )
    return rows


def build_benchmark_daily(
    daily_frames: Mapping[str, pd.DataFrame],
) -> pd.DataFrame:
    close_series: dict[str, pd.Series] = {}
    for symbol, raw in daily_frames.items():
        frame = raw.loc[:, ["timestamp", "close"]].copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise").astype(
            "datetime64[ns, UTC]"
        )
        series = frame.set_index("timestamp")["close"].astype(float).sort_index()
        close_series[symbol] = series
    closes = pd.concat(close_series, axis=1).sort_index()
    returns = closes.pct_change(fill_method=None)
    equal_weight_return = returns.mean(axis=1, skipna=True).fillna(0.0)
    equal_weight_equity = (1.0 + equal_weight_return).cumprod()
    btc_close = closes["BTC/USDT"].dropna()
    btc_return = btc_close.pct_change(fill_method=None).fillna(0.0)
    btc_equity = (1.0 + btc_return).cumprod()
    btc_ema50 = btc_close.ewm(span=50, adjust=False, min_periods=50).mean()
    btc_ema200 = btc_close.ewm(span=200, adjust=False, min_periods=120).mean()
    btc_momentum90 = btc_close / btc_close.shift(90) - 1.0
    regime = pd.Series("TRANSITION", index=btc_close.index, dtype="object")
    bull = (btc_close > btc_ema200) & (btc_ema50 > btc_ema200) & (btc_momentum90 > 0.0)
    bear = (btc_close < btc_ema200) & (btc_ema50 < btc_ema200) & (btc_momentum90 < 0.0)
    regime.loc[bull] = "BULL"
    regime.loc[bear] = "BEAR"
    result = pd.DataFrame(
        {
            "timestamp": equal_weight_equity.index,
            "equal_weight_return": equal_weight_return.to_numpy(dtype=float),
            "equal_weight_equity": equal_weight_equity.to_numpy(dtype=float),
        }
    ).set_index("timestamp")
    result["btc_return"] = btc_return.reindex(result.index).fillna(0.0)
    result["btc_equity"] = btc_equity.reindex(result.index).ffill().fillna(1.0)
    result["market_regime"] = regime.reindex(result.index).ffill().fillna("TRANSITION")
    return result.reset_index()


def benchmark_capture_rows(
    family_curves: Mapping[str, pd.DataFrame],
    benchmark: pd.DataFrame,
) -> list[dict[str, object]]:
    benchmark_working = benchmark.copy()
    benchmark_working["timestamp"] = pd.to_datetime(benchmark_working["timestamp"], utc=True)
    benchmark_working = benchmark_working.set_index("timestamp")
    rows: list[dict[str, object]] = []
    for family_id, curve in family_curves.items():
        family_daily = _daily_equity(curve)
        joined = benchmark_working.join(
            family_daily.rename("family_equity"),
            how="inner",
        ).dropna(subset=["family_equity"])
        previous_family = INITIAL_EQUITY
        previous_equal = 1.0
        previous_btc = 1.0
        joined_index = pd.DatetimeIndex(joined.index)
        for year in sorted(joined_index.year.unique().tolist()):
            group = joined[joined_index.year == year]
            if group.empty:
                continue
            family_end = float(group["family_equity"].iloc[-1])
            equal_end = float(group["equal_weight_equity"].iloc[-1])
            btc_end = float(group["btc_equity"].iloc[-1])
            family_return = family_end / previous_family - 1.0
            equal_return = equal_end / previous_equal - 1.0
            btc_return = btc_end / previous_btc - 1.0
            rows.append(
                {
                    "family_id": family_id,
                    "year": int(year),
                    "family_return": family_return,
                    "equal_weight_return": equal_return,
                    "btc_return": btc_return,
                    "equal_weight_upside_capture": (
                        family_return / equal_return if equal_return > 0.0 else None
                    ),
                    "btc_upside_capture": (
                        family_return / btc_return if btc_return > 0.0 else None
                    ),
                    "equal_weight_downside_capture": (
                        family_return / equal_return if equal_return < 0.0 else None
                    ),
                }
            )
            previous_family = family_end
            previous_equal = equal_end
            previous_btc = btc_end
    return rows


def bull_window_rows(
    family_curves: Mapping[str, pd.DataFrame],
    benchmark: pd.DataFrame,
    *,
    minimum_days: int = 30,
) -> list[dict[str, object]]:
    working = benchmark.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    working = working.sort_values("timestamp", kind="stable").reset_index(drop=True)
    is_bull = working["market_regime"] == "BULL"
    group_id = (is_bull != is_bull.shift(1, fill_value=False)).cumsum()
    windows: list[tuple[pd.Timestamp, pd.Timestamp, float]] = []
    for _, group in working[is_bull].groupby(group_id[is_bull], sort=True):
        if len(group) < minimum_days:
            continue
        start = timestamp(group.iloc[0]["timestamp"])
        end = timestamp(group.iloc[-1]["timestamp"])
        benchmark_return = (
            _finite_float(group.iloc[-1]["equal_weight_equity"], name="benchmark_end")
            / _finite_float(group.iloc[0]["equal_weight_equity"], name="benchmark_start")
            - 1.0
        )
        windows.append((start, end, benchmark_return))

    rows: list[dict[str, object]] = []
    for family_id, curve in family_curves.items():
        daily = _daily_equity(curve)
        for index, (start, end, benchmark_return) in enumerate(windows, start=1):
            selected = daily[(daily.index >= start) & (daily.index <= end)]
            if len(selected) < 2:
                continue
            family_return = float(selected.iloc[-1] / selected.iloc[0] - 1.0)
            high_opportunity = benchmark_return > 2.0
            adequacy = family_return >= 1.0 or (
                benchmark_return > 0.0 and family_return / benchmark_return >= 0.40
            )
            rows.append(
                {
                    "family_id": family_id,
                    "window_id": index,
                    "start": iso(start),
                    "end": iso(end),
                    "days": int((end - start).days + 1),
                    "family_return": family_return,
                    "equal_weight_return": benchmark_return,
                    "capture_ratio": (
                        family_return / benchmark_return if benchmark_return > 0.0 else None
                    ),
                    "high_opportunity_window": high_opportunity,
                    "strategic_bull_adequacy": adequacy if high_opportunity else None,
                }
            )
    return rows


def classify_family(
    metrics: Mapping[str, object],
    *,
    cost_2x: Mapping[str, object],
    concentration: Mapping[str, object],
    yearly_rows: Sequence[Mapping[str, object]],
    bull_rows: Sequence[Mapping[str, object]],
) -> ClassificationResult:
    active_years = [row for row in yearly_rows if int(cast(int, row["trade_count"])) > 0]
    positive_year_fraction = (
        sum((_optional_float(row["return"]) or 0.0) > 0.0 for row in active_years)
        / len(active_years)
        if active_years
        else 0.0
    )
    high_opportunity_rows = [row for row in bull_rows if row["high_opportunity_window"] is True]
    bull_adequate = (
        all(row["strategic_bull_adequacy"] is True for row in high_opportunity_rows)
        if high_opportunity_rows
        else False
    )

    profit_factor = _optional_float(metrics.get("profit_factor"))
    cost_2x_pf = _optional_float(cost_2x.get("profit_factor"))
    cost_2x_return = _optional_float(cost_2x.get("net_return"))
    monthly = _optional_float(metrics.get("monthly_geometric_return"))
    gates = {
        "capital_feasible": metrics.get("capital_feasible") is True,
        "net_return_positive": (_optional_float(metrics.get("net_return")) or 0.0) > 0.0,
        "profit_factor_gte_1_20": profit_factor is not None and profit_factor >= 1.20,
        "profit_factor_gte_1_50": profit_factor is not None and profit_factor >= 1.50,
        "maximum_drawdown_lte_30pct": (
            (_optional_float(metrics.get("maximum_drawdown")) or math.inf) <= 0.30
        ),
        "two_x_cost_positive": cost_2x_return is not None and cost_2x_return > 0.0,
        "two_x_cost_profit_factor_gte_1": cost_2x_pf is not None and cost_2x_pf >= 1.0,
        "positive_active_year_fraction_gte_50pct": positive_year_fraction >= 0.50,
        "top_3_trade_profit_share_lte_35pct": (
            (_optional_float(concentration.get("top_3_trade_profit_share")) or math.inf) <= 0.35
        ),
        "top_asset_profit_share_lte_50pct": (
            (_optional_float(concentration.get("top_asset_profit_share")) or math.inf) <= 0.50
        ),
        "trade_count_gte_100": int(cast(int, metrics["trade_count"])) >= 100,
        "monthly_target_24pct_met": monthly is not None and monthly >= STRATEGIC_MONTHLY_TARGET,
        "high_opportunity_bull_adequacy": bull_adequate,
    }
    minimum_robustness = (
        "capital_feasible",
        "net_return_positive",
        "profit_factor_gte_1_20",
        "maximum_drawdown_lte_30pct",
        "two_x_cost_positive",
        "two_x_cost_profit_factor_gte_1",
        "positive_active_year_fraction_gte_50pct",
        "top_3_trade_profit_share_lte_35pct",
        "top_asset_profit_share_lte_50pct",
        "trade_count_gte_100",
    )
    if not gates["capital_feasible"]:
        classification = "CAPITAL_INFEASIBLE"
    elif not gates["net_return_positive"] or profit_factor is None or profit_factor < 1.0:
        classification = "FAILED_ECONOMIC_BASELINE"
    elif all(gates[name] for name in minimum_robustness):
        classification = "ROBUST_POSITIVE_BASELINE"
    else:
        classification = "FRAGILE_POSITIVE_BASELINE"
    strategic = bool(
        gates["monthly_target_24pct_met"]
        and gates["high_opportunity_bull_adequacy"]
        and classification == "ROBUST_POSITIVE_BASELINE"
    )
    return ClassificationResult(
        classification=classification,
        strategic_objective_met=strategic,
        gates=gates,
    )


def diagnostic_text(
    *,
    metrics: Mapping[str, object],
    cost_2x: Mapping[str, object],
    concentration: Mapping[str, object],
    classification: ClassificationResult,
    asset_rows: Sequence[Mapping[str, object]],
    regime_rows: Sequence[Mapping[str, object]],
    exit_rows: Sequence[Mapping[str, object]],
) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    weaknesses: list[str] = []
    net_return = _optional_float(metrics.get("net_return")) or 0.0
    pf = _optional_float(metrics.get("profit_factor"))
    drawdown = _optional_float(metrics.get("maximum_drawdown"))
    cost_return = _optional_float(cost_2x.get("net_return")) or 0.0
    top3 = _optional_float(concentration.get("top_3_trade_profit_share"))
    top_asset = _optional_float(concentration.get("top_asset_profit_share"))

    if net_return > 0.0:
        strengths.append(f"Positive fixed-baseline net return: {net_return:.2%}.")
    if pf is not None and pf >= 1.20:
        strengths.append(f"Profit factor clears the 1.20 baseline gate: {pf:.3f}.")
    if cost_return > 0.0:
        strengths.append(f"Remains profitable at 2x recorded transaction cost: {cost_return:.2%}.")
    if drawdown is not None and drawdown <= 0.30:
        strengths.append(f"Maximum drawdown remains within 30%: {drawdown:.2%}.")
    if top3 is not None and top3 <= 0.35:
        strengths.append(f"Top-three trade concentration is controlled: {top3:.2%}.")
    positive_assets = sum((_optional_float(row.get("net_pnl")) or 0.0) > 0.0 for row in asset_rows)
    if positive_assets >= 4:
        strengths.append(f"Positive contribution is distributed across {positive_assets} assets.")

    if not classification.gates["capital_feasible"]:
        weaknesses.append(
            "The frozen sizing path becomes capital-infeasible; "
            "the ledger continues beyond available capital."
        )
    if net_return <= 0.0:
        weaknesses.append(f"The full-period fixed baseline loses capital: {net_return:.2%}.")
    if pf is None or pf < 1.0:
        weaknesses.append(f"Profit factor is below break-even: {pf!r}.")
    elif pf < 1.20:
        weaknesses.append(f"Profit factor is positive but below the 1.20 baseline gate: {pf:.3f}.")
    if cost_return <= 0.0:
        weaknesses.append(f"The edge disappears at 2x cost: {cost_return:.2%}.")
    if drawdown is not None and drawdown > 0.30:
        weaknesses.append(f"Maximum drawdown exceeds 30%: {drawdown:.2%}.")
    if top3 is not None and top3 > 0.35:
        weaknesses.append(f"Profit is concentrated in the top three trades: {top3:.2%}.")
    if top_asset is not None and top_asset > 0.50:
        weaknesses.append(
            f"More than half of positive profit comes from one asset: {top_asset:.2%}."
        )
    if not classification.gates["positive_active_year_fraction_gte_50pct"]:
        weaknesses.append("Fewer than half of active calendar years are profitable.")
    if not classification.gates["monthly_target_24pct_met"]:
        monthly = _optional_float(metrics.get("monthly_geometric_return"))
        weaknesses.append(
            "The geometric monthly return is far below the 24% research objective"
            + (f": {monthly:.2%}." if monthly is not None else ".")
        )

    negative_regimes = [
        str(row["regime"])
        for row in regime_rows
        if row.get("regime_type") == "MARKET_TREND"
        and (_optional_float(row.get("net_pnl")) or 0.0) < 0.0
    ]
    if negative_regimes:
        weaknesses.append(
            "Negative contribution in market regimes: " + ", ".join(sorted(negative_regimes)) + "."
        )
    weakest_exit = min(
        exit_rows,
        key=lambda row: _optional_float(row.get("net_pnl")) or 0.0,
        default=None,
    )
    weakest_exit_pnl = (
        _optional_float(weakest_exit.get("net_pnl")) if weakest_exit is not None else None
    )
    if weakest_exit is not None and weakest_exit_pnl is not None and weakest_exit_pnl < 0.0:
        weaknesses.append(
            f"Weakest exit bucket is {weakest_exit['exit_reason']} with "
            f"{weakest_exit_pnl:.2f} net PnL."
        )

    return strengths[:6], weaknesses[:8]
