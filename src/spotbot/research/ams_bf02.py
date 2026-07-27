"""Aligned daily-series evidence for AMS BF02."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any, cast

import pandas as pd

from spotbot.research.beta_diagnostics import (
    causal_volatility_matched_exposure,
    estimate_beta,
)

RESEARCH_LOCK = pd.Timestamp("2025-01-01T00:00:00Z")


class BF02Error(RuntimeError):
    """Raised when aligned BF02 evidence violates its data contract."""


def utc_timestamp(value: Any) -> pd.Timestamp:
    """Return one timezone-aware UTC timestamp."""

    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")

    return timestamp.tz_convert("UTC")


def _require_columns(
    frame: pd.DataFrame,
    columns: set[str],
    *,
    source: str,
) -> None:
    missing = sorted(columns - set(frame.columns))

    if missing:
        raise BF02Error(f"{source} is missing required columns: {missing}")


def _apply_fill(
    fill: Any,
    *,
    positions: dict[str, tuple[str, float]],
    last_prices: dict[str, float],
    tolerance: float,
) -> float:
    position_id = str(fill.position_id)
    symbol = str(fill.symbol)
    quantity = float(fill.position_quantity_after)
    price = float(fill.price)
    cash = float(fill.cash_after)

    if not math.isfinite(cash) or cash < -tolerance:
        raise BF02Error("Fill ledger produced negative or invalid cash.")

    if not math.isfinite(price) or price <= 0.0:
        raise BF02Error("Fill ledger contains an invalid price.")

    last_prices[symbol] = price

    if abs(quantity) <= tolerance:
        positions.pop(position_id, None)
    else:
        if quantity < 0.0:
            raise BF02Error("Short quantity detected in spot-only evidence.")

        positions[position_id] = (
            symbol,
            quantity,
        )

    return max(cash, 0.0)


def reconstruct_portfolio_state(
    result: Any,
    four_hour: pd.DataFrame,
    *,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    tolerance: float = 1e-5,
) -> tuple[pd.DataFrame, float]:
    """Rebuild equity, cash and exposure from immutable fills and prices."""

    start = utc_timestamp(validation_start)
    end = utc_timestamp(validation_end)

    if end > RESEARCH_LOCK:
        raise BF02Error("Post-lock data requested.")

    _require_columns(
        four_hour,
        {
            "symbol",
            "bar_open_time",
            "bar_close_time",
            "close",
        },
        source="four_hour",
    )

    bars = four_hour.copy()
    bars["bar_open_time"] = pd.to_datetime(
        bars["bar_open_time"],
        utc=True,
        errors="raise",
    )
    bars["bar_close_time"] = pd.to_datetime(
        bars["bar_close_time"],
        utc=True,
        errors="raise",
    )
    bars["close"] = pd.to_numeric(
        bars["close"],
        errors="raise",
    )

    bars = bars.loc[bars["bar_open_time"].ge(start) & bars["bar_open_time"].lt(end)].copy()

    bars = bars.sort_values(
        [
            "bar_close_time",
            "symbol",
        ],
        kind="stable",
    )

    if bars.empty:
        raise BF02Error("Fold contains no four-hour bars.")

    grouped = [
        (
            utc_timestamp(timestamp),
            group.copy(),
        )
        for timestamp, group in bars.groupby(
            "bar_close_time",
            sort=True,
        )
    ]

    fills = sorted(
        tuple(result.fills),
        key=lambda fill: utc_timestamp(fill.timestamp),
    )

    positions: dict[str, tuple[str, float]] = {}
    last_prices: dict[str, float] = {}
    cash = float(result.initial_capital)
    fill_index = 0
    rows: list[dict[str, Any]] = []

    for close_timestamp, group in grouped:
        while fill_index < len(fills):
            fill = fills[fill_index]
            fill_timestamp = utc_timestamp(fill.timestamp)

            if fill_timestamp >= close_timestamp:
                break

            cash = _apply_fill(
                fill,
                positions=positions,
                last_prices=last_prices,
                tolerance=tolerance,
            )
            fill_index += 1

        for row in group.itertuples(index=False):
            symbol = str(row.symbol)
            price = float(cast(Any, row.close))

            if math.isfinite(price) and price > 0.0:
                last_prices[symbol] = price

        gross_market_value = 0.0

        for symbol, quantity in positions.values():
            mark_price = last_prices.get(symbol)

            if mark_price is None:
                raise BF02Error(f"No mark price is available for {symbol}.")

            gross_market_value += quantity * mark_price

        equity = cash + gross_market_value

        if not math.isfinite(equity) or equity <= 0.0:
            raise BF02Error("Invalid reconstructed portfolio equity.")

        gross_exposure = gross_market_value / equity

        if gross_exposure < -tolerance or gross_exposure > 1.0 + tolerance:
            raise BF02Error("Reconstructed exposure violates spot-only bounds.")

        rows.append(
            {
                "timestamp": close_timestamp,
                "equity": equity,
                "cash": cash,
                "gross_exposure": min(
                    max(gross_exposure, 0.0),
                    1.0,
                ),
                "open_positions": len(positions),
            }
        )

        # Fills exactly at this close are next-bar-open fills, except the
        # end-of-fold liquidation. Both affect the following state, not the
        # just-completed bar that produced the registered equity curve.
        while fill_index < len(fills):
            fill = fills[fill_index]
            fill_timestamp = utc_timestamp(fill.timestamp)

            if fill_timestamp != close_timestamp:
                break

            cash = _apply_fill(
                fill,
                positions=positions,
                last_prices=last_prices,
                tolerance=tolerance,
            )
            fill_index += 1

    while fill_index < len(fills):
        fill = fills[fill_index]
        fill_timestamp = utc_timestamp(fill.timestamp)

        if fill_timestamp > end:
            raise BF02Error("Fill ledger extends beyond the fold boundary.")

        cash = _apply_fill(
            fill,
            positions=positions,
            last_prices=last_prices,
            tolerance=tolerance,
        )
        fill_index += 1

    state = pd.DataFrame(rows)

    reference = pd.DataFrame(
        [
            {
                "timestamp": utc_timestamp(timestamp),
                "reference_equity": float(value),
            }
            for timestamp, value in result.equity_curve
        ]
    )

    if reference.empty:
        raise BF02Error("Registered M05 equity curve is empty.")

    if bool(reference["timestamp"].duplicated().any()):
        raise BF02Error("Registered equity curve has duplicate timestamps.")

    comparison = state.merge(
        reference,
        on="timestamp",
        how="inner",
        validate="one_to_one",
    )

    if len(comparison) != len(reference):
        raise BF02Error("Reconstructed and registered equity timestamps do not align.")

    maximum_error = float((comparison["equity"] - comparison["reference_equity"]).abs().max())

    if maximum_error > tolerance:
        raise BF02Error(
            "Fill-ledger reconstruction does not match the registered "
            f"equity curve: {maximum_error}"
        )

    final_cash_value: Any = getattr(
        result,
        "final_cash",
        reference["reference_equity"].iloc[-1],
    )
    final_cash = float(final_cash_value)

    if abs(cash - final_cash) > tolerance:
        raise BF02Error("Final fill-ledger cash does not match registered final cash.")

    last_index = state.index[-1]
    state.at[
        last_index,
        "equity",
    ] = final_cash
    state.at[
        last_index,
        "cash",
    ] = final_cash
    state.at[
        last_index,
        "gross_exposure",
    ] = 0.0
    state.at[
        last_index,
        "open_positions",
    ] = 0

    return state, maximum_error


def daily_strategy_state(
    state: pd.DataFrame,
    *,
    initial_capital: float,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
) -> pd.DataFrame:
    """Convert validated four-hour portfolio state into daily closes."""

    start = utc_timestamp(validation_start)
    end = utc_timestamp(validation_end)

    if state.empty:
        raise BF02Error("Cannot resample an empty strategy state.")

    baseline = pd.DataFrame(
        [
            {
                "timestamp": start,
                "equity": float(initial_capital),
                "cash": float(initial_capital),
                "gross_exposure": 0.0,
                "open_positions": 0,
            }
        ]
    )

    combined = pd.concat(
        [
            baseline,
            state,
        ],
        ignore_index=True,
    )

    combined["timestamp"] = pd.to_datetime(
        combined["timestamp"],
        utc=True,
        errors="raise",
    )

    combined = combined.sort_values(
        "timestamp",
        kind="stable",
    )

    indexed = combined.set_index("timestamp")

    resampled = indexed.resample(
        "1D",
        closed="right",
        label="right",
    ).agg(
        {
            "equity": "last",
            "cash": "last",
            "gross_exposure": "mean",
            "open_positions": "max",
        }
    )

    daily = pd.DataFrame(resampled)
    daily_index = pd.DatetimeIndex(daily.index)
    daily_mask = (daily_index >= start) & (daily_index <= end)
    daily = pd.DataFrame(daily.loc[daily_mask]).copy()

    daily = daily.rename(
        columns={
            "equity": "m05_equity",
            "cash": "m05_cash",
            "gross_exposure": "m05_average_gross_exposure",
            "open_positions": "m05_maximum_open_positions",
        }
    )

    daily["m05_daily_return"] = daily["m05_equity"].pct_change(fill_method=None)

    return daily


def daily_benchmark_returns(
    daily_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Build BTC and equal-weight Survivor-30 daily returns."""

    _require_columns(
        daily_frame,
        {
            "symbol",
            "bar_close_time",
            "close",
        },
        source="daily",
    )

    frame = daily_frame.copy()
    frame["bar_close_time"] = pd.to_datetime(
        frame["bar_close_time"],
        utc=True,
        errors="raise",
    )
    frame["close"] = pd.to_numeric(
        frame["close"],
        errors="raise",
    )

    close_times = frame["bar_close_time"]

    filtered_frame = frame.loc[close_times <= RESEARCH_LOCK]
    frame = pd.DataFrame(filtered_frame).copy()

    prices = frame.pivot_table(
        index="bar_close_time",
        columns="symbol",
        values="close",
        aggfunc="last",
    ).sort_index()

    if "BTC" not in prices.columns:
        raise BF02Error("BTC is missing from the daily benchmark frame.")

    returns = prices.pct_change(fill_method=None)

    result = pd.DataFrame(
        index=returns.index,
    )
    result["btc_close"] = prices["BTC"]
    result["btc_daily_return"] = returns["BTC"]
    result["equal_weight_daily_return"] = returns.mean(
        axis=1,
        skipna=True,
    )

    return result


def align_daily_evidence(
    strategy: pd.DataFrame,
    benchmarks: pd.DataFrame,
    *,
    fold_id: str,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    volatility_lookback: int = 28,
) -> pd.DataFrame:
    """Inner-align validated strategy and benchmark observations."""

    start = utc_timestamp(validation_start)
    end = utc_timestamp(validation_end)

    aligned = strategy.join(
        benchmarks,
        how="inner",
    )

    aligned = aligned.loc[(aligned.index > start) & (aligned.index <= end)].copy()

    aligned = aligned.dropna(
        subset=[
            "m05_equity",
            "m05_cash",
            "m05_average_gross_exposure",
            "m05_daily_return",
            "btc_close",
            "btc_daily_return",
            "equal_weight_daily_return",
        ]
    )

    if len(aligned) < 250:
        raise BF02Error(f"Fold {fold_id} has insufficient aligned daily observations.")

    if bool(aligned.index.duplicated().any()):
        raise BF02Error(f"Fold {fold_id} has duplicate aligned timestamps.")

    if aligned.index.max() > RESEARCH_LOCK:
        raise BF02Error("Aligned evidence accessed post-lock data.")

    exposure = aligned["m05_average_gross_exposure"].clip(
        lower=0.0,
        upper=1.0,
    )

    if not exposure.equals(aligned["m05_average_gross_exposure"]):
        raise BF02Error("M05 exposure is outside the spot-only interval.")

    aligned["exposure_matched_equal_weight_return"] = (
        aligned["equal_weight_daily_return"] * exposure
    )

    equal_weight_volatility_exposure = causal_volatility_matched_exposure(
        aligned["m05_daily_return"],
        aligned["equal_weight_daily_return"],
        lookback=volatility_lookback,
    )

    btc_volatility_exposure = causal_volatility_matched_exposure(
        aligned["m05_daily_return"],
        aligned["btc_daily_return"],
        lookback=volatility_lookback,
    )

    aligned["volatility_matched_equal_weight_exposure"] = equal_weight_volatility_exposure

    aligned["volatility_matched_equal_weight_return"] = (
        aligned["equal_weight_daily_return"] * equal_weight_volatility_exposure
    )

    aligned["volatility_matched_btc_exposure"] = btc_volatility_exposure

    aligned["volatility_matched_btc_return"] = aligned["btc_daily_return"] * btc_volatility_exposure

    aligned.insert(
        0,
        "fold_id",
        fold_id,
    )
    aligned.insert(
        1,
        "timestamp",
        aligned.index,
    )

    return pd.DataFrame(aligned.reset_index(drop=True))


def return_metrics(
    returns: pd.Series,
) -> dict[str, Any]:
    """Calculate deterministic daily-return diagnostics."""

    numeric = pd.Series(
        pd.to_numeric(
            returns,
            errors="coerce",
        ),
        index=returns.index,
        dtype="float64",
    )

    values = [float(cast(Any, value)) for value in numeric.dropna().tolist()]

    if not values:
        raise BF02Error("Return series is empty.")

    if any(not math.isfinite(value) or value <= -1.0 for value in values):
        raise BF02Error("Return series contains an invalid spot return.")

    observations = len(values)
    compounded = math.prod(1.0 + value for value in values) - 1.0

    mean_return = sum(values) / observations

    if observations > 1:
        variance = sum((value - mean_return) ** 2 for value in values) / (observations - 1)
        standard_deviation = math.sqrt(max(variance, 0.0))
    else:
        standard_deviation = 0.0

    annualized_volatility = standard_deviation * math.sqrt(365.0)

    sharpe = (
        mean_return / standard_deviation * math.sqrt(365.0) if standard_deviation > 0.0 else None
    )

    wealth = 1.0
    running_peak = 1.0
    maximum_drawdown = 0.0

    for value in values:
        wealth *= 1.0 + value
        running_peak = max(
            running_peak,
            wealth,
        )
        maximum_drawdown = max(
            maximum_drawdown,
            1.0 - wealth / running_peak,
        )

    annualized_return = (1.0 + compounded) ** (365.0 / observations) - 1.0

    return {
        "observations": observations,
        "compounded_return": compounded,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe": sharpe,
        "maximum_drawdown": maximum_drawdown,
        "worst_day": min(values),
        "positive_day_ratio": (sum(value > 0.0 for value in values) / observations),
    }


def beta_metrics(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> dict[str, Any]:
    """Return synchronous beta evidence plus annualized intercept."""

    payload: dict[str, Any] = asdict(
        estimate_beta(
            portfolio_returns,
            benchmark_returns,
        )
    )

    alpha = payload["alpha_intercept"]

    payload["annualized_alpha_intercept"] = (
        float((1.0 + float(alpha)) ** 365.0 - 1.0)
        if alpha is not None and float(alpha) > -1.0
        else None
    )

    return payload


def evidence_metrics(
    frame: pd.DataFrame,
) -> dict[str, Any]:
    """Compute one complete fold or aggregate evidence record."""

    return {
        "observations": int(len(frame)),
        "start": utc_timestamp(frame["timestamp"].iloc[0]).isoformat(),
        "end": utc_timestamp(frame["timestamp"].iloc[-1]).isoformat(),
        "average_gross_exposure": float(frame["m05_average_gross_exposure"].mean()),
        "maximum_gross_exposure": float(frame["m05_average_gross_exposure"].max()),
        "m05": return_metrics(frame["m05_daily_return"]),
        "equal_weight": return_metrics(frame["equal_weight_daily_return"]),
        "exposure_matched_equal_weight": return_metrics(
            frame["exposure_matched_equal_weight_return"]
        ),
        "volatility_matched_equal_weight": return_metrics(
            frame["volatility_matched_equal_weight_return"]
        ),
        "btc": return_metrics(frame["btc_daily_return"]),
        "volatility_matched_btc": return_metrics(frame["volatility_matched_btc_return"]),
        "beta_vs_equal_weight": beta_metrics(
            frame["m05_daily_return"],
            frame["equal_weight_daily_return"],
        ),
        "beta_vs_btc": beta_metrics(
            frame["m05_daily_return"],
            frame["btc_daily_return"],
        ),
    }


def alpha_judgement(
    *,
    aggregate_alpha: float | None,
    fold_alphas: Sequence[float | None],
    m05_return: float,
    exposure_matched_return: float,
) -> str:
    """Issue a conservative judgement only when every fold agrees."""

    valid = [float(value) for value in fold_alphas if value is not None]

    if aggregate_alpha is None or len(valid) != len(fold_alphas):
        return "INCONCLUSIVE"

    if (
        aggregate_alpha > 0.0
        and all(value > 0.0 for value in valid)
        and m05_return > exposure_matched_return
    ):
        return "POSITIVE"

    if (
        aggregate_alpha < 0.0
        and all(value < 0.0 for value in valid)
        and m05_return < exposure_matched_return
    ):
        return "NEGATIVE"

    return "INCONCLUSIVE"


def build_audit(
    fold_frames: Sequence[pd.DataFrame],
    *,
    reconstruction_errors: Mapping[str, float],
    dataset_hashes: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the final aligned-series BF02 evidence object."""

    if len(fold_frames) != 3:
        raise BF02Error("BF02 requires exactly three validation folds.")

    fold_records: list[dict[str, Any]] = []

    for frame in fold_frames:
        fold_id = str(frame["fold_id"].iloc[0])
        metrics = evidence_metrics(frame)
        metrics["fold_id"] = fold_id
        metrics["maximum_reconstruction_error"] = float(reconstruction_errors[fold_id])
        fold_records.append(metrics)

    combined = pd.concat(
        fold_frames,
        ignore_index=True,
    )

    aggregate = evidence_metrics(combined)

    aggregate_alpha = aggregate["beta_vs_equal_weight"]["alpha_intercept"]

    fold_alphas = [record["beta_vs_equal_weight"]["alpha_intercept"] for record in fold_records]

    judgement = alpha_judgement(
        aggregate_alpha=(float(aggregate_alpha) if aggregate_alpha is not None else None),
        fold_alphas=[(float(value) if value is not None else None) for value in fold_alphas],
        m05_return=float(aggregate["m05"]["compounded_return"]),
        exposure_matched_return=float(
            aggregate["exposure_matched_equal_weight"]["compounded_return"]
        ),
    )

    maximum_error = max(float(value) for value in reconstruction_errors.values())

    return {
        "schema_version": ("ams-bf02-aligned-daily-series-evidence-v1"),
        "research_result": "COMPLETE",
        "safety_stop": "PASS",
        "aligned_series_status": "VALIDATED",
        "comparison_authorizations": {
            "raw_return_comparison_authorized": True,
            "risk_adjusted_comparison_authorized": True,
            "exposure_matched_comparison_authorized": True,
            "causal_volatility_matched_comparison_authorized": True,
            "alpha_value_judgement": judgement,
        },
        "validation": {
            "fold_count": len(fold_frames),
            "aligned_observations": int(len(combined)),
            "maximum_reconstruction_error": (maximum_error),
            "reconstruction_errors": dict(reconstruction_errors),
            "timestamps_unique_within_fold": True,
            "no_forward_fill_of_returns": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
        "scope": {
            "universe": ("SURVIVOR_30_DIAGNOSTIC_ONLY"),
            "variant": "M05_DUAL_28",
            "point_in_time": False,
            "promotable": False,
            "production_ready": False,
            "live_ready": False,
            "md02_authorized": False,
            "kelly_used": False,
            "leverage_used": False,
        },
        "dataset_hashes": dict(dataset_hashes),
        "fold_metrics": fold_records,
        "aggregate_metrics": aggregate,
    }
