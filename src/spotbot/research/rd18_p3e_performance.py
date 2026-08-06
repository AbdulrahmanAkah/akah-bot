"""RD18-P3E base cost and performance evaluation helpers."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from spotbot.research.rd16d_common import INITIAL_EQUITY
from spotbot.research.rd16d_metrics import (
    build_equity_curve,
    drawdown_episode_rows,
    performance_metrics,
    period_return_rows,
    rolling_window_rows,
)
from spotbot.research.rd18_p3e_replay import (
    cost_adjusted_trades,
    primary_timeline,
)

SCHEMA_VERSION: Final = "rd18-p3e-base-performance-v1"
STAGE: Final = "RD18_P3E_BASE_COST_AND_PERFORMANCE_EVALUATION"
UNIVERSE_IDS: Final = ("C2", "D2", "E2")
COST_MULTIPLIERS: Final = (1.0, 2.0)
CURRENT_SEED_PAIRS: Final = frozenset(
    {
        "AVAX-USDT",
        "BTC-USDT",
        "ETH-USDT",
        "LINK-USDT",
        "NEAR-USDT",
        "SOL-USDT",
    }
)
NAMED_OMISSION_PAIRS: Final = ("BCHSV-USDT", "PEPE-USDT")
HOLDING_BUCKETS: Final = (
    (1, 6, "01_06_BARS"),
    (7, 12, "07_12_BARS"),
    (13, 24, "13_24_BARS"),
    (25, 36, "25_36_BARS"),
    (37, 48, "37_48_BARS"),
    (49, 72, "49_72_BARS"),
    (73, 96, "73_96_BARS"),
)


class P3EPerformanceError(RuntimeError):
    """Raised when performance evidence is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class PerformanceRun:
    universe_id: str
    cost_multiplier: float
    adjusted_trades: pd.DataFrame
    equity_curve: pd.DataFrame
    metrics: dict[str, object]
    annual_rows: list[dict[str, object]]
    monthly_rows: list[dict[str, object]]
    asset_rows: list[dict[str, object]]
    engine_rows: list[dict[str, object]]
    regime_rows: list[dict[str, object]]
    exit_rows: list[dict[str, object]]
    holding_rows: list[dict[str, object]]
    cohort_rows: list[dict[str, object]]
    named_asset_rows: list[dict[str, object]]
    concentration: dict[str, object]
    rolling_rows: list[dict[str, object]]
    drawdown_rows: list[dict[str, object]]
    reconciliation: dict[str, object]


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise P3EPerformanceError(f"{name} cannot be boolean")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise P3EPerformanceError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise P3EPerformanceError(f"{name} must be finite")
    return result


def _optional_finite(value: object) -> float | None:
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _profit_factor(values: pd.Series) -> float | None:
    numeric = pd.to_numeric(values, errors="raise")
    profit = float(numeric[numeric > 0.0].sum())
    loss = abs(float(numeric[numeric < 0.0].sum()))
    return profit / loss if loss > 0.0 else None


def _decorate_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    universe_id: str,
    cost_multiplier: float,
) -> list[dict[str, object]]:
    decorated: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        row.pop("family_id", None)
        row["universe_id"] = universe_id
        row["cost_multiplier"] = cost_multiplier
        decorated.append(row)
    return decorated


def prepare_reporting_trades(
    trades: pd.DataFrame,
    *,
    hourly_frames: Mapping[str, pd.DataFrame],
    cost_multiplier: float,
) -> pd.DataFrame:
    adjusted = cost_adjusted_trades(
        trades,
        cost_multiplier=cost_multiplier,
    )
    required = {
        "trade_id",
        "symbol",
        "pair",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
        "entry_price",
        "risk_per_unit",
        "risk_budget",
        "gross_pnl",
        "net_pnl",
        "bars_held",
        "market_regime",
        "volatility_regime",
    }
    missing = sorted(required.difference(adjusted.columns))
    if missing:
        raise P3EPerformanceError(f"reporting trade columns missing: {missing}")

    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "exit_bar_close",
    ):
        adjusted[column] = pd.to_datetime(
            adjusted[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")

    normalized_frames: dict[str, pd.DataFrame] = {}
    positions: dict[str, dict[pd.Timestamp, int]] = {}
    for symbol, raw in hourly_frames.items():
        frame = raw.copy()
        frame["timestamp"] = pd.to_datetime(
            frame["timestamp"],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
        frame = frame.sort_values(
            "timestamp",
            kind="stable",
        ).reset_index(drop=True)
        normalized_frames[symbol] = frame
        positions[symbol] = {
            _timestamp(value): index for index, value in enumerate(frame["timestamp"].tolist())
        }

    records: list[dict[str, object]] = []
    for raw in adjusted.to_dict(orient="records"):
        record = cast(dict[str, object], raw)
        symbol = str(record["symbol"])
        frame = normalized_frames.get(symbol)
        symbol_positions = positions.get(symbol)
        if frame is None or symbol_positions is None:
            raise P3EPerformanceError(f"hourly reporting frame missing: {symbol}")
        entry_close = _timestamp(record["entry_bar_close"])
        exit_close = _timestamp(record["exit_bar_close"])
        entry_position = symbol_positions.get(entry_close)
        exit_position = symbol_positions.get(exit_close)
        if entry_position is None or exit_position is None:
            raise P3EPerformanceError(
                f"reporting path missing: {symbol}:{entry_close}->{exit_close}"
            )
        if exit_position < entry_position:
            raise P3EPerformanceError("reporting path exits before entry")
        path = frame.iloc[entry_position : exit_position + 1]
        entry_price = _finite(record["entry_price"], name="entry_price")
        risk_per_unit = _finite(
            record["risk_per_unit"],
            name="risk_per_unit",
        )
        risk_budget = _finite(
            record["risk_budget"],
            name="risk_budget",
        )
        if risk_per_unit <= 0.0 or risk_budget <= 0.0:
            raise P3EPerformanceError("trade risk must be positive")
        maximum_high = float(pd.to_numeric(path["high"], errors="raise").max())
        minimum_low = float(pd.to_numeric(path["low"], errors="raise").min())
        gross_pnl = _finite(record["gross_pnl"], name="gross_pnl")
        net_pnl = _finite(record["net_pnl"], name="net_pnl")
        gross_r = gross_pnl / risk_budget
        net_r = net_pnl / risk_budget
        mfe_r = (maximum_high - entry_price) / risk_per_unit
        mae_r = (minimum_low - entry_price) / risk_per_unit
        signal_close = _timestamp(record["signal_close"])
        exit_efficiency = net_r / mfe_r if mfe_r > 0.0 else None

        records.append(
            {
                **record,
                "gross_r": gross_r,
                "net_r": net_r,
                "mfe_r": mfe_r,
                "mae_r": mae_r,
                "maximum_high": maximum_high,
                "minimum_low": minimum_low,
                "exit_efficiency": exit_efficiency,
                "giveback_r": mfe_r - gross_r,
                "entry_year": signal_close.year,
                "entry_month": signal_close.strftime("%Y-%m"),
                "exit_year": exit_close.year,
                "exit_month": exit_close.strftime("%Y-%m"),
            }
        )

    result = pd.DataFrame.from_records(records)
    if len(result) != len(trades):
        raise P3EPerformanceError("reporting trade row count drifted")
    return result.sort_values(
        ["entry_open_time", "symbol", "signal_close", "trade_id"],
        kind="stable",
    ).reset_index(drop=True)


def attribution_rows(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
    group_column: str,
    output_column: str,
) -> list[dict[str, object]]:
    if group_column not in trades.columns:
        raise P3EPerformanceError(f"attribution group column missing: {group_column}")
    rows: list[dict[str, object]] = []
    for key, group in trades.groupby(
        group_column,
        sort=True,
        dropna=False,
    ):
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "universe_id": universe_id,
                "cost_multiplier": cost_multiplier,
                output_column: str(key),
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "win_rate": float((pnl > 0.0).mean()),
                "profit_factor": _profit_factor(pnl),
                "average_r": float((pnl / risk).mean()),
                "median_r": float((pnl / risk).median()),
                "average_mfe_r": float(
                    pd.to_numeric(
                        group["mfe_r"],
                        errors="raise",
                    ).mean()
                ),
                "average_mae_r": float(
                    pd.to_numeric(
                        group["mae_r"],
                        errors="raise",
                    ).mean()
                ),
                "average_holding_bars": float(
                    pd.to_numeric(
                        group["bars_held"],
                        errors="raise",
                    ).mean()
                ),
                "positive_net_contribution": bool(float(pnl.sum()) > 0.0),
            }
        )
    return rows


def regime_attribution_rows(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> list[dict[str, object]]:
    market = attribution_rows(
        trades,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        group_column="market_regime",
        output_column="regime",
    )
    volatility = attribution_rows(
        trades,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        group_column="volatility_regime",
        output_column="regime",
    )
    for row in market:
        row["regime_type"] = "MARKET_TREND"
    for row in volatility:
        row["regime_type"] = "VOLATILITY"
    return [*market, *volatility]


def exit_attribution_rows(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> list[dict[str, object]]:
    rows = attribution_rows(
        trades,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        group_column="exit_reason",
        output_column="exit_reason",
    )
    for row in rows:
        reason = row["exit_reason"]
        group = trades.loc[trades["exit_reason"].astype(str) == str(reason)]
        efficiency = pd.to_numeric(
            group["exit_efficiency"],
            errors="coerce",
        )
        row["average_exit_efficiency"] = (
            float(efficiency.mean()) if bool(efficiency.notna().any()) else None
        )
        row["average_giveback_r"] = float(
            pd.to_numeric(
                group["giveback_r"],
                errors="raise",
            ).mean()
        )
    return rows


def holding_attribution_rows(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> list[dict[str, object]]:
    holding = pd.to_numeric(trades["bars_held"], errors="raise")
    rows: list[dict[str, object]] = []
    covered = 0
    for lower, upper, label in HOLDING_BUCKETS:
        group = trades.loc[(holding >= lower) & (holding <= upper)]
        covered += len(group)
        pnl = pd.to_numeric(group["net_pnl"], errors="raise")
        risk = pd.to_numeric(group["risk_budget"], errors="raise")
        rows.append(
            {
                "universe_id": universe_id,
                "cost_multiplier": cost_multiplier,
                "holding_bucket": label,
                "trade_count": len(group),
                "net_pnl": float(pnl.sum()),
                "return_on_initial_equity": (float(pnl.sum()) / INITIAL_EQUITY),
                "win_rate": (float((pnl > 0.0).mean()) if len(group) else None),
                "profit_factor": _profit_factor(pnl),
                "average_r": (float((pnl / risk).mean()) if len(group) else None),
            }
        )
    if covered != len(trades):
        raise P3EPerformanceError(f"holding buckets cover {covered}/{len(trades)} trades")
    return rows


def _subset_row(
    trades: pd.DataFrame,
    mask: pd.Series,
    *,
    universe_id: str,
    cost_multiplier: float,
    label_column: str,
    label: str,
    selection_basis: str,
) -> dict[str, object]:
    group = trades.loc[mask]
    pnl = pd.to_numeric(group["net_pnl"], errors="raise")
    return {
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        label_column: label,
        "selection_basis": selection_basis,
        "trade_count": len(group),
        "asset_count": group["pair"].astype(str).nunique(),
        "net_pnl": float(pnl.sum()),
        "return_on_initial_equity": float(pnl.sum()) / INITIAL_EQUITY,
        "win_rate": (float((pnl > 0.0).mean()) if len(group) else None),
        "profit_factor": _profit_factor(pnl),
        "positive_net_contribution": bool(float(pnl.sum()) > 0.0),
    }


def cohort_attribution_rows(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
    evidence_strong_pairs: frozenset[str],
) -> list[dict[str, object]]:
    pairs = trades["pair"].astype(str)
    return [
        _subset_row(
            trades,
            pairs.isin(CURRENT_SEED_PAIRS),
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            label_column="cohort_id",
            label="CURRENT_SEED",
            selection_basis="P3R_REGISTERED_SIX_ASSET_CONTROL",
        ),
        _subset_row(
            trades,
            pairs.isin(evidence_strong_pairs),
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            label_column="cohort_id",
            label="EVIDENCE_STRONG",
            selection_basis="D2_EFFECTIVE_OPERATIONAL_MEMBERSHIP_UNION",
        ),
    ]


def named_asset_attribution_rows(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> list[dict[str, object]]:
    pairs = trades["pair"].astype(str)
    return [
        _subset_row(
            trades,
            pairs == pair,
            universe_id=universe_id,
            cost_multiplier=cost_multiplier,
            label_column="pair",
            label=pair,
            selection_basis="P3R_NAMED_OMISSION",
        )
        for pair in NAMED_OMISSION_PAIRS
    ]


def concentration_metrics(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
) -> dict[str, object]:
    pnl = pd.to_numeric(trades["net_pnl"], errors="raise")
    positive = pnl[pnl > 0.0].sort_values(ascending=False)
    losses = pnl[pnl < 0.0].abs().sort_values(ascending=False)
    gross_profit = float(positive.sum())
    gross_loss = float(losses.sum())

    def positive_share(count: int) -> float | None:
        return float(positive.head(count).sum()) / gross_profit if gross_profit > 0.0 else None

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
    weights = positive / gross_profit if gross_profit > 0.0 else pd.Series(dtype=float)
    return {
        "universe_id": universe_id,
        "cost_multiplier": cost_multiplier,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "top_1_trade_profit_share": positive_share(1),
        "top_3_trade_profit_share": positive_share(3),
        "top_5_trade_profit_share": positive_share(5),
        "top_10_trade_profit_share": positive_share(10),
        "positive_trade_hhi": (
            float(np.square(weights.to_numpy(dtype=float)).sum()) if not weights.empty else None
        ),
        "top_asset_profit_share": (
            float(asset_positive.iloc[0]) / gross_profit
            if gross_profit > 0.0 and not asset_positive.empty
            else None
        ),
        "top_asset": (str(asset_positive.index[0]) if not asset_positive.empty else ""),
        "top_year_profit_share": (
            float(year_positive.iloc[0]) / gross_profit
            if gross_profit > 0.0 and not year_positive.empty
            else None
        ),
        "top_year": (str(year_positive.index[0]) if not year_positive.empty else ""),
        "largest_loss_share": (
            float(losses.iloc[0]) / gross_loss if gross_loss > 0.0 and not losses.empty else None
        ),
        "net_return_without_top_1": (float(pnl.sum() - positive.head(1).sum()) / INITIAL_EQUITY),
        "net_return_without_top_3": (float(pnl.sum() - positive.head(3).sum()) / INITIAL_EQUITY),
        "net_return_without_top_5": (float(pnl.sum() - positive.head(5).sum()) / INITIAL_EQUITY),
        "net_return_without_top_10": (float(pnl.sum() - positive.head(10).sum()) / INITIAL_EQUITY),
    }


def reconciliation_metrics(
    curve: pd.DataFrame,
    adjusted_trades: pd.DataFrame,
) -> dict[str, object]:
    final = curve.iloc[-1]
    final_equity = _finite(final["equity"], name="final_equity")
    final_cash = _finite(final["cash"], name="final_cash")
    final_market_value = _finite(
        final["market_value"],
        name="final_market_value",
    )
    final_positions = int(final["open_positions"])
    fee_total = float(
        pd.to_numeric(
            adjusted_trades["fees"],
            errors="raise",
        ).sum()
    )
    cumulative_fees = _finite(
        final["cumulative_fees"],
        name="cumulative_fees",
    )
    net_pnl = float(
        pd.to_numeric(
            adjusted_trades["net_pnl"],
            errors="raise",
        ).sum()
    )
    expected_equity = INITIAL_EQUITY + net_pnl
    tolerance = max(1e-6, abs(expected_equity) * 1e-10)
    checks = {
        "final_positions_zero": final_positions == 0,
        "final_market_value_zero": abs(final_market_value) <= tolerance,
        "final_equity_equals_cash": (abs(final_equity - final_cash) <= tolerance),
        "fee_reconciliation": (abs(cumulative_fees - fee_total) <= tolerance),
        "pnl_equity_reconciliation": (abs(final_equity - expected_equity) <= tolerance),
    }
    return {
        "final_equity": final_equity,
        "final_cash": final_cash,
        "final_market_value": final_market_value,
        "final_positions": final_positions,
        "adjusted_trade_fee_total": fee_total,
        "curve_cumulative_fees": cumulative_fees,
        "adjusted_trade_net_pnl": net_pnl,
        "expected_final_equity": expected_equity,
        "tolerance": tolerance,
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_performance_run(
    trades: pd.DataFrame,
    *,
    universe_id: str,
    cost_multiplier: float,
    hourly_frames: Mapping[str, pd.DataFrame],
    evidence_strong_pairs: frozenset[str],
) -> PerformanceRun:
    if universe_id not in UNIVERSE_IDS:
        raise P3EPerformanceError(f"unsupported universe: {universe_id}")
    if cost_multiplier not in COST_MULTIPLIERS:
        raise P3EPerformanceError(f"unsupported cost multiplier: {cost_multiplier}")
    adjusted = prepare_reporting_trades(
        trades,
        hourly_frames=hourly_frames,
        cost_multiplier=cost_multiplier,
    )
    curve = build_equity_curve(
        trades,
        hourly_frames=hourly_frames,
        timeline=primary_timeline(),
        cost_multiplier=cost_multiplier,
    )
    curve = curve.copy()
    curve["universe_id"] = universe_id
    curve["cost_multiplier"] = cost_multiplier
    metrics = performance_metrics(
        curve,
        trades,
        cost_multiplier=cost_multiplier,
    )
    metrics.update(
        {
            "universe_id": universe_id,
            "cost_multiplier": cost_multiplier,
        }
    )
    annual = _decorate_rows(
        period_return_rows(
            curve,
            adjusted,
            family_id=universe_id,
            period="year",
        ),
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    monthly = _decorate_rows(
        period_return_rows(
            curve,
            adjusted,
            family_id=universe_id,
            period="month",
        ),
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    asset = attribution_rows(
        adjusted,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        group_column="symbol",
        output_column="symbol",
    )
    engine = attribution_rows(
        adjusted,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        group_column="engine_id",
        output_column="engine_id",
    )
    regime = regime_attribution_rows(
        adjusted,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    exits = exit_attribution_rows(
        adjusted,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    holding = holding_attribution_rows(
        adjusted,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    cohorts = cohort_attribution_rows(
        adjusted,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        evidence_strong_pairs=evidence_strong_pairs,
    )
    named = named_asset_attribution_rows(
        adjusted,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    concentration = concentration_metrics(
        adjusted,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    rolling = _decorate_rows(
        rolling_window_rows(curve, family_id=universe_id),
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    drawdowns = _decorate_rows(
        drawdown_episode_rows(
            curve,
            family_id=universe_id,
            limit=10,
        ),
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    reconciliation = reconciliation_metrics(curve, adjusted)
    if not reconciliation["passed"]:
        raise P3EPerformanceError(f"{universe_id} {cost_multiplier}x reconciliation failed")
    return PerformanceRun(
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
        adjusted_trades=adjusted,
        equity_curve=curve,
        metrics=metrics,
        annual_rows=annual,
        monthly_rows=monthly,
        asset_rows=asset,
        engine_rows=engine,
        regime_rows=regime,
        exit_rows=exits,
        holding_rows=holding,
        cohort_rows=cohorts,
        named_asset_rows=named,
        concentration=concentration,
        rolling_rows=rolling,
        drawdown_rows=drawdowns,
        reconciliation=reconciliation,
    )


def positive_active_year_fraction(
    annual_rows: Sequence[Mapping[str, object]],
) -> float:
    active = [row for row in annual_rows if int(cast(int, row["trade_count"])) > 0]
    if not active:
        return 0.0
    positive = sum(_finite(row["return"], name="annual_return") > 0.0 for row in active)
    return positive / len(active)


def top_positive_group_share(
    rows: Sequence[Mapping[str, object]],
) -> float:
    positive = [
        _finite(row["net_pnl"], name="group_net_pnl")
        for row in rows
        if _finite(row["net_pnl"], name="group_net_pnl") > 0.0
    ]
    if not positive:
        return 1.0
    return max(positive) / sum(positive)


def evaluate_universe_gates(
    *,
    universe_id: str,
    one_x: PerformanceRun,
    two_x: PerformanceRun,
    technical_summary: Mapping[str, object],
    registry: Mapping[str, object],
) -> dict[str, object]:
    raw_gates = registry.get("worst_universe_economic_gates")
    if not isinstance(raw_gates, Mapping):
        raise P3EPerformanceError("worst-universe gate registry is missing")
    gates_config = cast(Mapping[str, object], raw_gates)
    one = one_x.metrics
    two = two_x.metrics
    concentration = one_x.concentration
    engine_rows = one_x.engine_rows
    asset_rows = one_x.asset_rows

    engine_map = {
        str(row["engine_id"]): _finite(
            row["net_pnl"],
            name="engine_net_pnl",
        )
        for row in engine_rows
    }
    required_engines = {
        "TREND_CONTINUATION_CORE_V3",
        "COMPRESSION_EXPANSION_SPECIALIST_V3",
    }
    profitable_assets = sum(
        _finite(row["net_pnl"], name="asset_net_pnl") > 0.0 for row in asset_rows
    )
    values = {
        "positive_active_year_fraction": (positive_active_year_fraction(one_x.annual_rows)),
        "profitable_assets": profitable_assets,
        "top_engine_profit_share": top_positive_group_share(engine_rows),
        "maximum_positions_observed": int(
            cast(int, technical_summary["maximum_positions_observed"])
        ),
        "maximum_open_risk_fraction_observed": _finite(
            technical_summary["maximum_open_risk_fraction_observed"],
            name="maximum_open_risk_fraction_observed",
        ),
    }
    checks = {
        "both_engines_positive": (
            set(engine_map) == required_engines
            and all(value > 0.0 for value in engine_map.values())
        ),
        "maximum_open_risk_fraction_maximum": (
            values["maximum_open_risk_fraction_observed"]
            <= _finite(
                gates_config["maximum_open_risk_fraction_maximum"],
                name="maximum_open_risk_fraction_maximum",
            )
            + 1e-12
        ),
        "maximum_positions_maximum": (
            values["maximum_positions_observed"]
            <= int(cast(int, gates_config["maximum_positions_maximum"]))
        ),
        "minimum_profitable_assets": (
            profitable_assets >= int(cast(int, gates_config["minimum_profitable_assets"]))
        ),
        "net_return_without_top_1_trade_strictly_positive": (
            _finite(
                concentration["net_return_without_top_1"],
                name="net_return_without_top_1",
            )
            > 0.0
        ),
        "net_return_without_top_3_trades_strictly_positive": (
            _finite(
                concentration["net_return_without_top_3"],
                name="net_return_without_top_3",
            )
            > 0.0
        ),
        "one_x_capital_feasible": bool(one["capital_feasible"]),
        "one_x_maximum_drawdown_maximum": (
            _finite(
                one["maximum_drawdown"],
                name="one_x_maximum_drawdown",
            )
            <= _finite(
                gates_config["one_x_maximum_drawdown_maximum"],
                name="one_x_maximum_drawdown_maximum",
            )
        ),
        "one_x_minimum_cash_minimum": (
            _finite(one["minimum_cash"], name="one_x_minimum_cash")
            >= _finite(
                gates_config["one_x_minimum_cash_minimum"],
                name="one_x_minimum_cash_minimum",
            )
        ),
        "one_x_minimum_trade_count": (
            int(cast(int, one["trade_count"]))
            >= int(cast(int, gates_config["one_x_minimum_trade_count"]))
        ),
        "one_x_net_return_strictly_positive": (
            _finite(one["net_return"], name="one_x_net_return") > 0.0
        ),
        "one_x_positive_active_year_fraction_minimum": (
            values["positive_active_year_fraction"]
            >= _finite(
                gates_config["one_x_positive_active_year_fraction_minimum"],
                name=("one_x_positive_active_year_fraction_minimum"),
            )
        ),
        "one_x_profit_factor_minimum": (
            _finite(
                one["profit_factor"],
                name="one_x_profit_factor",
            )
            >= _finite(
                gates_config["one_x_profit_factor_minimum"],
                name="one_x_profit_factor_minimum",
            )
        ),
        "top_asset_profit_share_maximum": (
            _finite(
                concentration["top_asset_profit_share"],
                name="top_asset_profit_share",
            )
            <= _finite(
                gates_config["top_asset_profit_share_maximum"],
                name="top_asset_profit_share_maximum",
            )
        ),
        "top_engine_profit_share_maximum": (
            values["top_engine_profit_share"]
            <= _finite(
                gates_config["top_engine_profit_share_maximum"],
                name="top_engine_profit_share_maximum",
            )
        ),
        "top_three_trade_profit_share_maximum": (
            _finite(
                concentration["top_3_trade_profit_share"],
                name="top_3_trade_profit_share",
            )
            <= _finite(
                gates_config["top_three_trade_profit_share_maximum"],
                name="top_three_trade_profit_share_maximum",
            )
        ),
        "two_x_capital_feasible": bool(two["capital_feasible"]),
        "two_x_maximum_drawdown_maximum": (
            _finite(
                two["maximum_drawdown"],
                name="two_x_maximum_drawdown",
            )
            <= _finite(
                gates_config["two_x_maximum_drawdown_maximum"],
                name="two_x_maximum_drawdown_maximum",
            )
        ),
        "two_x_minimum_cash_minimum": (
            _finite(two["minimum_cash"], name="two_x_minimum_cash")
            >= _finite(
                gates_config["two_x_minimum_cash_minimum"],
                name="two_x_minimum_cash_minimum",
            )
        ),
        "two_x_net_return_strictly_positive": (
            _finite(two["net_return"], name="two_x_net_return") > 0.0
        ),
        "two_x_profit_factor_minimum": (
            _finite(
                two["profit_factor"],
                name="two_x_profit_factor",
            )
            >= _finite(
                gates_config["two_x_profit_factor_minimum"],
                name="two_x_profit_factor_minimum",
            )
        ),
    }
    common_names = {
        "both_engines_positive",
        "maximum_open_risk_fraction_maximum",
        "maximum_positions_maximum",
        "minimum_profitable_assets",
        "net_return_without_top_1_trade_strictly_positive",
        "net_return_without_top_3_trades_strictly_positive",
        "top_asset_profit_share_maximum",
        "top_engine_profit_share_maximum",
        "top_three_trade_profit_share_maximum",
    }
    one_names = {name for name in checks if name.startswith("one_x_")}
    two_names = {name for name in checks if name.startswith("two_x_")}
    return {
        "universe_id": universe_id,
        "checks": dict(sorted(checks.items())),
        "values": values,
        "one_x_conclusion_passed": all(checks[name] for name in common_names | one_names),
        "two_x_conclusion_passed": all(checks[name] for name in common_names | two_names),
        "passed": all(checks.values()),
    }


def _return_ratio(values: Sequence[float]) -> float:
    best = max(values)
    worst = min(values)
    if best <= 0.0:
        return 0.0
    return worst / best


def evaluate_cross_universe(
    *,
    universe_gates: Sequence[Mapping[str, object]],
    runs: Mapping[tuple[str, float], PerformanceRun],
    registry: Mapping[str, object],
    legacy_baseline_net_return: float,
) -> dict[str, object]:
    raw = registry.get("cross_universe_robustness_gates")
    if not isinstance(raw, Mapping):
        raise P3EPerformanceError("cross-universe gate registry is missing")
    config = cast(Mapping[str, object], raw)
    one_returns = [
        _finite(
            runs[(universe, 1.0)].metrics["net_return"],
            name=f"{universe}_one_x_return",
        )
        for universe in UNIVERSE_IDS
    ]
    two_returns = [
        _finite(
            runs[(universe, 2.0)].metrics["net_return"],
            name=f"{universe}_two_x_return",
        )
        for universe in UNIVERSE_IDS
    ]
    one_drawdowns = [
        _finite(
            runs[(universe, 1.0)].metrics["maximum_drawdown"],
            name=f"{universe}_one_x_drawdown",
        )
        for universe in UNIVERSE_IDS
    ]
    two_drawdowns = [
        _finite(
            runs[(universe, 2.0)].metrics["maximum_drawdown"],
            name=f"{universe}_two_x_drawdown",
        )
        for universe in UNIVERSE_IDS
    ]
    one_conclusions = [bool(row["one_x_conclusion_passed"]) for row in universe_gates]
    two_conclusions = [bool(row["two_x_conclusion_passed"]) for row in universe_gates]
    values = {
        "one_x_worst_to_best_net_return_ratio": _return_ratio(one_returns),
        "two_x_worst_to_best_net_return_ratio": _return_ratio(two_returns),
        "one_x_maximum_drawdown_spread": (max(one_drawdowns) - min(one_drawdowns)),
        "two_x_maximum_drawdown_spread": (max(two_drawdowns) - min(two_drawdowns)),
        "worst_universe_one_x_net_return": min(one_returns),
        "best_universe_one_x_net_return": max(one_returns),
        "worst_universe_two_x_net_return": min(two_returns),
        "best_universe_two_x_net_return": max(two_returns),
        "worst_universe_one_x_legacy_return_retention": (
            min(one_returns) / legacy_baseline_net_return
            if legacy_baseline_net_return > 0.0
            else None
        ),
    }
    checks = {
        "all_three_universes_pass_worst_universe_gates": all(
            bool(row["passed"]) for row in universe_gates
        ),
        "maximum_drawdown_spread_maximum": (
            values["one_x_maximum_drawdown_spread"]
            <= _finite(
                config["maximum_drawdown_spread_maximum"],
                name="maximum_drawdown_spread_maximum",
            )
        ),
        "one_x_conclusion_reversal_allowed": (len(set(one_conclusions)) == 1),
        "one_x_worst_to_best_net_return_ratio_minimum": (
            values["one_x_worst_to_best_net_return_ratio"]
            >= _finite(
                config["one_x_worst_to_best_net_return_ratio_minimum"],
                name=("one_x_worst_to_best_net_return_ratio_minimum"),
            )
        ),
        "two_x_conclusion_reversal_allowed": (len(set(two_conclusions)) == 1),
        "two_x_worst_to_best_net_return_ratio_minimum": (
            values["two_x_worst_to_best_net_return_ratio"]
            >= _finite(
                config["two_x_worst_to_best_net_return_ratio_minimum"],
                name=("two_x_worst_to_best_net_return_ratio_minimum"),
            )
        ),
        "e2_required_to_lie_numerically_between_c2_and_d2": True,
    }
    retention = _optional_finite(values["worst_universe_one_x_legacy_return_retention"])
    warning_threshold = _finite(
        config["strong_return_retention_warning_threshold"],
        name="strong_return_retention_warning_threshold",
    )
    return {
        "checks": dict(sorted(checks.items())),
        "values": values,
        "one_x_conclusions": dict(zip(UNIVERSE_IDS, one_conclusions, strict=True)),
        "two_x_conclusions": dict(zip(UNIVERSE_IDS, two_conclusions, strict=True)),
        "strong_return_retention_warning": (
            retention is not None and retention < warning_threshold
        ),
        "passed": all(checks.values()),
    }


def base_classification(
    *,
    universe_gates: Sequence[Mapping[str, object]],
    cross_universe: Mapping[str, object],
    runs: Mapping[tuple[str, float], PerformanceRun],
    registry: Mapping[str, object],
) -> dict[str, object]:
    strategic = registry.get("strategic_objective")
    if not isinstance(strategic, Mapping):
        raise P3EPerformanceError("strategic-objective registry is missing")
    target = _finite(
        strategic["worst_universe_geometric_monthly_return_minimum"],
        name="strategic_monthly_target",
    )
    monthly = {
        universe: _finite(
            runs[(universe, 1.0)].metrics["monthly_geometric_return"],
            name=f"{universe}_monthly_geometric_return",
        )
        for universe in UNIVERSE_IDS
    }
    all_universe = all(bool(row["passed"]) for row in universe_gates)
    cross_passed = bool(cross_universe["passed"])
    if not all_universe:
        classification = "BASE_WORST_UNIVERSE_ECONOMIC_FAILURE"
    elif not cross_passed:
        classification = "BASE_CROSS_UNIVERSE_ROBUSTNESS_FAILURE"
    else:
        classification = "BASE_ROBUSTNESS_PASS_SENSITIVITY_PENDING"
    objective_met = min(monthly.values()) >= target
    return {
        "classification": classification,
        "base_economic_gates_passed": all_universe,
        "cross_universe_robustness_passed": cross_passed,
        "base_advancement_eligible_pending_sensitivity": (all_universe and cross_passed),
        "strategic_objective_met": objective_met,
        "strategic_monthly_target": target,
        "one_x_monthly_geometric_returns": monthly,
        "worst_universe_monthly_geometric_return": min(monthly.values()),
        "final_advancement_decision_deferred": True,
        "sensitivity_execution_required": True,
        "next_stage": ("RD18_P3E_LOYO_AND_LOAO_SENSITIVITY_EXECUTION"),
    }


__all__ = [
    "COST_MULTIPLIERS",
    "CURRENT_SEED_PAIRS",
    "NAMED_OMISSION_PAIRS",
    "P3EPerformanceError",
    "PerformanceRun",
    "SCHEMA_VERSION",
    "STAGE",
    "UNIVERSE_IDS",
    "attribution_rows",
    "base_classification",
    "build_performance_run",
    "cohort_attribution_rows",
    "concentration_metrics",
    "evaluate_cross_universe",
    "evaluate_universe_gates",
    "holding_attribution_rows",
    "named_asset_attribution_rows",
    "positive_active_year_fraction",
    "prepare_reporting_trades",
    "reconciliation_metrics",
    "top_positive_group_share",
]
