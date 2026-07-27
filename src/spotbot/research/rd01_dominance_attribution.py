# mypy: disable-error-code="arg-type,call-overload,operator,redundant-cast"
"""RD01-D2 fold attribution and BTC-beta controls."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from typing import Any, cast

import pandas as pd

from spotbot.research.beta_diagnostics import estimate_beta
from spotbot.research.rd01_dominance import DominanceDataError
from spotbot.research.rd01_dominance_tagging import attach_dominance_tags

D2_SCHEMA_VERSION = "ams-rd01-d2-dominance-attribution-v1"

DAILY_RETURN_COLUMNS: tuple[str, ...] = (
    "m05_daily_return",
    "btc_daily_return",
    "equal_weight_daily_return",
    "exposure_matched_equal_weight_return",
    "volatility_matched_equal_weight_return",
    "volatility_matched_btc_return",
)


def compounded_return(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()

    if clean.empty:
        return 0.0

    if bool((clean <= -1.0).any()):
        raise DominanceDataError("Return series contains an impossible spot return.")

    return float((1.0 + clean).prod() - 1.0)


def maximum_drawdown(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna()

    if clean.empty:
        return 0.0

    wealth = (1.0 + clean).cumprod()
    peaks = wealth.cummax()
    return float((1.0 - wealth / peaks).max())


def return_statistics(values: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    observations = len(clean)

    if not observations:
        return {
            "observations": 0,
            "compounded_return": 0.0,
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe": None,
            "maximum_drawdown": 0.0,
            "mean_daily_return": None,
            "positive_day_ratio": None,
        }

    compounded = compounded_return(clean)
    mean = float(clean.mean())
    standard_deviation = float(clean.std(ddof=1)) if observations > 1 else 0.0
    annualized_volatility = standard_deviation * math.sqrt(365.0)
    annualized_return = (1.0 + compounded) ** (365.0 / observations) - 1.0
    sharpe = mean / standard_deviation * math.sqrt(365.0) if standard_deviation > 0.0 else None

    return {
        "observations": observations,
        "compounded_return": compounded,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe": sharpe,
        "maximum_drawdown": maximum_drawdown(clean),
        "mean_daily_return": mean,
        "positive_day_ratio": float((clean > 0.0).mean()),
    }


def tag_daily_series(
    daily: pd.DataFrame,
    dominance: pd.DataFrame,
) -> pd.DataFrame:
    """Attach the latest causal dominance state to each BF02 day."""

    required = {
        "fold_id",
        "timestamp",
        *DAILY_RETURN_COLUMNS,
    }
    missing = sorted(required.difference(daily.columns))

    if missing:
        raise DominanceDataError(f"BF02 daily series is missing columns: {missing}")

    frame = daily.copy()
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"],
        utc=True,
        errors="raise",
    )
    return attach_dominance_tags(
        frame,
        dominance,
        event_time_column="timestamp",
        prefix="regime_",
        maximum_age_days=3,
    )


def daily_attribution_rows(
    tagged_daily: pd.DataFrame,
    *,
    minimum_observations: int = 20,
) -> list[dict[str, Any]]:
    """Calculate fold and aggregate return/beta diagnostics by quadrant."""

    required = {
        "fold_id",
        "regime_dominance_quadrant",
        *DAILY_RETURN_COLUMNS,
    }
    missing = sorted(required.difference(tagged_daily.columns))

    if missing:
        raise DominanceDataError(f"Tagged daily series is missing columns: {missing}")

    rows: list[dict[str, Any]] = []
    scopes: list[tuple[str, pd.DataFrame]] = [
        ("AGGREGATE", tagged_daily),
    ]
    scopes.extend(
        (
            str(fold_id),
            pd.DataFrame(group),
        )
        for fold_id, group in tagged_daily.groupby(
            "fold_id",
            sort=True,
        )
    )

    for fold_id, scope in scopes:
        grouped = scope.groupby(
            "regime_dominance_quadrant",
            sort=True,
            dropna=False,
        )

        for quadrant, group in grouped:
            quadrant_name = str(quadrant)
            observations = len(group)
            status = (
                "VALID"
                if (
                    quadrant_name != "INSUFFICIENT_LOOKBACK"
                    and observations >= minimum_observations
                )
                else "INSUFFICIENT_SAMPLE"
            )
            metrics = {
                column: return_statistics(cast(pd.Series, group[column]))
                for column in DAILY_RETURN_COLUMNS
            }
            btc_beta = estimate_beta(
                cast(pd.Series, group["m05_daily_return"]),
                cast(pd.Series, group["btc_daily_return"]),
            )
            equal_weight_beta = estimate_beta(
                cast(pd.Series, group["m05_daily_return"]),
                cast(pd.Series, group["equal_weight_daily_return"]),
            )
            m05_return = float(metrics["m05_daily_return"]["compounded_return"])
            exposure_return = float(
                metrics["exposure_matched_equal_weight_return"]["compounded_return"]
            )
            rows.append(
                {
                    "fold_id": fold_id,
                    "dominance_quadrant": quadrant_name,
                    "status": status,
                    "observations": observations,
                    "m05_minus_exposure_matched_return": (m05_return - exposure_return),
                    "m05_minus_equal_weight_return": (
                        m05_return
                        - float(metrics["equal_weight_daily_return"]["compounded_return"])
                    ),
                    "beta_vs_btc": asdict(btc_beta),
                    "beta_vs_equal_weight": asdict(equal_weight_beta),
                    "metrics": metrics,
                }
            )

    return rows


def trade_attribution_rows(
    tagged_trades: pd.DataFrame,
    *,
    minimum_trades: int = 3,
) -> list[dict[str, Any]]:
    """Attribute completed-trade quality to entry dominance quadrants."""

    if tagged_trades.empty:
        return []

    required = {
        "rd01_fold_id",
        "entry_dominance_quadrant",
        "net_pnl",
        "return_fraction",
        "mfe",
        "mae",
        "holding_hours",
    }
    missing = sorted(required.difference(tagged_trades.columns))

    if missing:
        raise DominanceDataError(f"Tagged trade ledger is missing columns: {missing}")

    rows: list[dict[str, Any]] = []
    scopes: list[tuple[str, pd.DataFrame]] = [
        ("AGGREGATE", tagged_trades),
    ]
    scopes.extend(
        (
            str(fold_id),
            pd.DataFrame(group),
        )
        for fold_id, group in tagged_trades.groupby(
            "rd01_fold_id",
            sort=True,
        )
    )

    for fold_id, scope in scopes:
        grouped = scope.groupby(
            "entry_dominance_quadrant",
            sort=True,
            dropna=False,
        )

        for quadrant, group in grouped:
            pnl = pd.to_numeric(
                cast(pd.Series, group["net_pnl"]),
                errors="coerce",
            ).dropna()
            returns = pd.to_numeric(
                cast(pd.Series, group["return_fraction"]),
                errors="coerce",
            ).dropna()
            wins = pnl[pnl > 0.0]
            losses = pnl[pnl < 0.0]
            gross_profit = float(wins.sum())
            gross_loss = float(-losses.sum())
            trade_count = len(group)
            rows.append(
                {
                    "fold_id": fold_id,
                    "dominance_quadrant": str(quadrant),
                    "status": (
                        "VALID"
                        if (
                            str(quadrant) != "INSUFFICIENT_LOOKBACK"
                            and trade_count >= minimum_trades
                        )
                        else "INSUFFICIENT_SAMPLE"
                    ),
                    "trade_count": trade_count,
                    "net_pnl": float(pnl.sum()),
                    "mean_net_pnl": (float(pnl.mean()) if not pnl.empty else None),
                    "mean_return_fraction": (float(returns.mean()) if not returns.empty else None),
                    "win_rate": (float((pnl > 0.0).mean()) if not pnl.empty else None),
                    "profit_factor": (gross_profit / gross_loss if gross_loss > 0.0 else None),
                    "mean_mfe": float(
                        pd.to_numeric(
                            cast(pd.Series, group["mfe"]),
                            errors="coerce",
                        ).mean()
                    ),
                    "mean_mae": float(
                        pd.to_numeric(
                            cast(pd.Series, group["mae"]),
                            errors="coerce",
                        ).mean()
                    ),
                    "mean_holding_hours": float(
                        pd.to_numeric(
                            cast(pd.Series, group["holding_hours"]),
                            errors="coerce",
                        ).mean()
                    ),
                }
            )

    return rows


def stability_rows(
    daily_rows: Iterable[Mapping[str, Any]],
    trade_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize cross-fold sign stability without selecting an overlay."""

    daily = [dict(row) for row in daily_rows if row["fold_id"] != "AGGREGATE"]
    trades = [dict(row) for row in trade_rows if row["fold_id"] != "AGGREGATE"]
    quadrants = sorted(
        {str(row["dominance_quadrant"]) for row in daily}
        | {str(row["dominance_quadrant"]) for row in trades}
    )
    output: list[dict[str, Any]] = []

    for quadrant in quadrants:
        daily_matches = [
            row
            for row in daily
            if row["dominance_quadrant"] == quadrant and row["status"] == "VALID"
        ]
        trade_matches = [
            row
            for row in trades
            if row["dominance_quadrant"] == quadrant and row["status"] == "VALID"
        ]
        excess_signs = [
            math.copysign(
                1.0,
                float(row["m05_minus_exposure_matched_return"]),
            )
            if float(row["m05_minus_exposure_matched_return"]) != 0.0
            else 0.0
            for row in daily_matches
        ]
        expectancy_signs = [
            math.copysign(
                1.0,
                float(row["mean_net_pnl"]),
            )
            if row["mean_net_pnl"] not in {None, 0.0}
            else 0.0
            for row in trade_matches
        ]
        output.append(
            {
                "dominance_quadrant": quadrant,
                "valid_daily_folds": len(daily_matches),
                "valid_trade_folds": len(trade_matches),
                "daily_excess_positive_folds": sum(sign > 0.0 for sign in excess_signs),
                "daily_excess_negative_folds": sum(sign < 0.0 for sign in excess_signs),
                "trade_expectancy_positive_folds": sum(sign > 0.0 for sign in expectancy_signs),
                "trade_expectancy_negative_folds": sum(sign < 0.0 for sign in expectancy_signs),
                "daily_excess_sign_consistent": (
                    len(excess_signs) >= 2
                    and len(set(excess_signs)) == 1
                    and excess_signs[0] != 0.0
                ),
                "trade_expectancy_sign_consistent": (
                    len(expectancy_signs) >= 2
                    and len(set(expectancy_signs)) == 1
                    and expectancy_signs[0] != 0.0
                ),
            }
        )

    return output
