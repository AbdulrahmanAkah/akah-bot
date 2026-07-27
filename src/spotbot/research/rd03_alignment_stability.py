# mypy: disable-error-code="arg-type,call-overload,operator,redundant-cast"
"""RD03-D0 immutable alignment-tier stability diagnostics for MD01-M05.

The module measures completed trades after simulation. It does not change
alignment classification, multipliers, candidates, entries, sizes, or exits.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, Final, cast

import pandas as pd

SCHEMA_VERSION: Final = "ams-rd03-d0-alignment-tier-stability-v1"
RESEARCH_LOCK: Final = pd.Timestamp("2025-01-01T00:00:00Z")
EXPECTED_FOLDS: Final[tuple[str, ...]] = ("WF01", "WF02", "WF03")
EXPECTED_TIERS: Final[tuple[str, ...]] = (
    "FULL",
    "MEDIUM",
    "FOUR_HOUR_ONLY",
)
MIN_TIER_TRADES_PER_FOLD: Final = 5
MIN_MEDIUM_TRADES_AGGREGATE: Final = 20
MFE_THRESHOLD: Final = 0.10
DEEP_MAE_THRESHOLD: Final = -0.10


class AlignmentStabilityError(RuntimeError):
    """Raised when alignment-tier evidence violates its diagnostic contract."""


def _record_dict(record: Any) -> dict[str, Any]:
    if is_dataclass(record) and not isinstance(record, type):
        return cast(dict[str, Any], asdict(record))
    if isinstance(record, Mapping):
        return {str(key): value for key, value in record.items()}
    raise AlignmentStabilityError(f"Unsupported trade record type: {type(record).__name__}")


def _finite_numeric(frame: pd.DataFrame, columns: Sequence[str]) -> None:
    for column in columns:
        numeric = pd.to_numeric(frame[column], errors="raise")
        if not bool(numeric.map(math.isfinite).all()):
            raise AlignmentStabilityError(f"Trade column {column!r} contains a non-finite value.")
        frame[column] = numeric.astype("float64")


def trades_frame(
    trades: Iterable[Any],
    *,
    fold_id: str,
) -> pd.DataFrame:
    """Return a detached immutable diagnostic frame for one fold."""

    if fold_id not in EXPECTED_FOLDS:
        raise AlignmentStabilityError(f"Unexpected fold id: {fold_id}")

    rows = [_record_dict(trade) for trade in trades]
    frame = pd.DataFrame(rows)
    required = {
        "trade_id",
        "entry_time",
        "exit_time",
        "alignment_tier",
        "return_fraction",
        "net_pnl",
        "gross_pnl",
        "holding_hours",
        "mfe",
        "mae",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise AlignmentStabilityError(f"Trade ledger is missing required columns: {missing}")
    if frame.empty:
        raise AlignmentStabilityError(f"Fold {fold_id} has no completed trades.")

    frame = frame.copy()
    frame.insert(0, "fold_id", fold_id)
    frame["trade_id"] = frame["trade_id"].astype(str)
    frame["alignment_tier"] = frame["alignment_tier"].astype(str)
    frame["entry_time"] = pd.to_datetime(
        frame["entry_time"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    frame["exit_time"] = pd.to_datetime(
        frame["exit_time"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")

    unknown = sorted(set(frame["alignment_tier"].unique()).difference(EXPECTED_TIERS))
    if unknown:
        raise AlignmentStabilityError(f"Unexpected alignment tiers: {unknown}")
    if bool(frame["trade_id"].duplicated().any()):
        raise AlignmentStabilityError(f"Fold {fold_id} contains duplicate trade ids.")
    if bool((frame["entry_time"] >= frame["exit_time"]).any()):
        raise AlignmentStabilityError("Trade entry must precede exit.")
    if bool((frame["exit_time"] > RESEARCH_LOCK).any()):
        raise AlignmentStabilityError("Post-lock trade detected.")

    numeric_columns = (
        "return_fraction",
        "net_pnl",
        "gross_pnl",
        "holding_hours",
        "mfe",
        "mae",
    )
    _finite_numeric(frame, numeric_columns)
    if bool((frame["holding_hours"] <= 0.0).any()):
        raise AlignmentStabilityError("Trade holding hours must be positive.")

    frame["is_winner"] = frame["net_pnl"].gt(0.0)
    frame["eligible_mfe_10pct"] = frame["mfe"].ge(MFE_THRESHOLD)
    frame["deep_mae_10pct"] = frame["mae"].le(DEEP_MAE_THRESHOLD)
    frame["trade_logic_changed"] = False
    return frame


def _safe_mean(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.mean()) if not values.empty else None


def _safe_median(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return float(values.median()) if not values.empty else None


def _profit_factor(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    gains = float(values.loc[values.gt(0.0)].sum())
    losses = float(-values.loc[values.lt(0.0)].sum())
    if losses <= 0.0:
        return None
    return gains / losses


def _mean_without_extreme(
    series: pd.Series,
    *,
    remove: str,
) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) <= 1:
        return None
    index = values.idxmin() if remove == "worst" else values.idxmax()
    reduced = values.drop(index=index)
    return float(reduced.mean())


def _maximum_absolute_pnl_share(series: pd.Series) -> float | None:
    values = pd.to_numeric(series, errors="coerce").dropna().abs()
    denominator = float(values.sum())
    if denominator <= 0.0:
        return None
    return float(values.max() / denominator)


def aggregate_alignment(
    frame: pd.DataFrame,
    *,
    group_columns: Sequence[str],
) -> pd.DataFrame:
    """Aggregate deterministic tier diagnostics without selecting a policy."""

    missing = sorted(set(group_columns).difference(frame.columns))
    if missing:
        raise AlignmentStabilityError(f"Alignment frame is missing group columns: {missing}")

    rows: list[dict[str, Any]] = []
    grouped: Any
    if group_columns:
        grouped = frame.groupby(
            list(group_columns),
            dropna=False,
            sort=True,
        )
    else:
        grouped = [((), frame)]

    for keys, group in grouped:
        key_values = keys if isinstance(keys, tuple) else (keys,)
        row: dict[str, Any] = {
            column: value
            for column, value in zip(
                group_columns,
                key_values,
                strict=True,
            )
        }
        returns = cast(pd.Series, group["return_fraction"])
        net_pnl = cast(pd.Series, group["net_pnl"])
        eligible = cast(pd.Series, group["eligible_mfe_10pct"]).astype(bool)
        deep = cast(pd.Series, group["deep_mae_10pct"]).astype(bool)

        row.update(
            {
                "trade_count": len(group),
                "win_rate": float(cast(pd.Series, group["is_winner"]).astype(bool).mean()),
                "mean_net_return": _safe_mean(returns),
                "median_net_return": _safe_median(returns),
                "total_net_pnl": float(pd.to_numeric(net_pnl, errors="raise").sum()),
                "profit_factor": _profit_factor(net_pnl),
                "mean_holding_hours": _safe_mean(cast(pd.Series, group["holding_hours"])),
                "median_holding_hours": _safe_median(cast(pd.Series, group["holding_hours"])),
                "mean_mfe": _safe_mean(cast(pd.Series, group["mfe"])),
                "median_mfe": _safe_median(cast(pd.Series, group["mfe"])),
                "mean_mae": _safe_mean(cast(pd.Series, group["mae"])),
                "median_mae": _safe_median(cast(pd.Series, group["mae"])),
                "mfe_10pct_count": int(eligible.sum()),
                "mfe_10pct_rate": float(eligible.mean()),
                "deep_mae_10pct_count": int(deep.sum()),
                "deep_mae_10pct_rate": float(deep.mean()),
                "best_case_mean_without_worst_trade": _mean_without_extreme(
                    returns,
                    remove="worst",
                ),
                "worst_case_mean_without_best_trade": _mean_without_extreme(
                    returns,
                    remove="best",
                ),
                "maximum_absolute_pnl_share": _maximum_absolute_pnl_share(net_pnl),
            }
        )
        rows.append(row)

    return pd.DataFrame(rows)


def build_medium_full_comparison(
    fold_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Compare MEDIUM with FULL independently inside each walk-forward fold."""

    required = {
        "fold_id",
        "alignment_tier",
        "trade_count",
        "win_rate",
        "mean_net_return",
        "median_net_return",
        "total_net_pnl",
        "best_case_mean_without_worst_trade",
        "worst_case_mean_without_best_trade",
    }
    missing = sorted(required.difference(fold_summary.columns))
    if missing:
        raise AlignmentStabilityError(f"Fold summary is missing comparison columns: {missing}")

    rows: list[dict[str, Any]] = []
    for fold_id in EXPECTED_FOLDS:
        fold = fold_summary.loc[fold_summary["fold_id"].eq(fold_id)]
        medium = fold.loc[fold["alignment_tier"].eq("MEDIUM")]
        full = fold.loc[fold["alignment_tier"].eq("FULL")]

        if medium.empty or full.empty:
            rows.append(
                {
                    "fold_id": fold_id,
                    "medium_trade_count": (
                        int(medium.iloc[0]["trade_count"]) if not medium.empty else 0
                    ),
                    "full_trade_count": (int(full.iloc[0]["trade_count"]) if not full.empty else 0),
                    "valid_comparison": False,
                    "mean_return_gap": None,
                    "median_return_gap": None,
                    "win_rate_gap": None,
                    "total_net_pnl_gap": None,
                    "favourable_outlier_adjusted_mean_gap": None,
                    "medium_mean_negative": None,
                    "medium_weaker_mean": None,
                    "medium_weaker_median": None,
                    "medium_weaker_win_rate": None,
                    "medium_weaker_after_favourable_outlier_adjustment": None,
                }
            )
            continue

        medium_row = medium.iloc[0]
        full_row = full.iloc[0]
        medium_count = int(medium_row["trade_count"])
        full_count = int(full_row["trade_count"])
        valid = medium_count >= MIN_TIER_TRADES_PER_FOLD and full_count >= MIN_TIER_TRADES_PER_FOLD

        medium_best = medium_row["best_case_mean_without_worst_trade"]
        full_worst = full_row["worst_case_mean_without_best_trade"]
        outlier_gap = (
            float(medium_best) - float(full_worst)
            if pd.notna(medium_best) and pd.notna(full_worst)
            else None
        )
        mean_gap = float(medium_row["mean_net_return"]) - float(full_row["mean_net_return"])
        median_gap = float(medium_row["median_net_return"]) - float(full_row["median_net_return"])
        win_gap = float(medium_row["win_rate"]) - float(full_row["win_rate"])

        rows.append(
            {
                "fold_id": fold_id,
                "medium_trade_count": medium_count,
                "full_trade_count": full_count,
                "valid_comparison": valid,
                "mean_return_gap": mean_gap,
                "median_return_gap": median_gap,
                "win_rate_gap": win_gap,
                "total_net_pnl_gap": float(medium_row["total_net_pnl"])
                - float(full_row["total_net_pnl"]),
                "favourable_outlier_adjusted_mean_gap": outlier_gap,
                "medium_mean_negative": (float(medium_row["mean_net_return"]) < 0.0),
                "medium_weaker_mean": mean_gap < 0.0,
                "medium_weaker_median": median_gap < 0.0,
                "medium_weaker_win_rate": win_gap < 0.0,
                "medium_weaker_after_favourable_outlier_adjustment": (
                    outlier_gap < 0.0 if outlier_gap is not None else False
                ),
            }
        )

    return pd.DataFrame(rows)


def _tier_record(
    aggregate_summary: pd.DataFrame,
    tier: str,
) -> dict[str, Any] | None:
    match = aggregate_summary.loc[aggregate_summary["alignment_tier"].eq(tier)]
    if match.empty:
        return None
    return cast(dict[str, Any], match.iloc[0].to_dict())


def evaluate_alignment_stability(
    comparisons: pd.DataFrame,
    aggregate_summary: pd.DataFrame,
) -> dict[str, Any]:
    """Apply the pre-registered D0 gate for a possible RD03-D1 replay."""

    valid = comparisons.loc[comparisons["valid_comparison"].astype(bool)].copy()
    medium = _tier_record(aggregate_summary, "MEDIUM")
    full = _tier_record(aggregate_summary, "FULL")
    four_hour = _tier_record(
        aggregate_summary,
        "FOUR_HOUR_ONLY",
    )
    if medium is None or full is None:
        raise AlignmentStabilityError("Aggregate FULL and MEDIUM tiers are required.")

    valid_folds = len(valid)
    all_mean_weaker = bool(
        valid_folds == len(EXPECTED_FOLDS) and valid["medium_weaker_mean"].astype(bool).all()
    )
    median_weaker_folds = int(valid["medium_weaker_median"].astype(bool).sum())
    win_rate_weaker_folds = int(valid["medium_weaker_win_rate"].astype(bool).sum())
    negative_mean_folds = int(valid["medium_mean_negative"].astype(bool).sum())
    outlier_robust_folds = int(
        valid["medium_weaker_after_favourable_outlier_adjustment"].astype(bool).sum()
    )

    aggregate_mean_gap = float(medium["mean_net_return"]) - float(full["mean_net_return"])
    aggregate_median_gap = float(medium["median_net_return"]) - float(full["median_net_return"])
    aggregate_win_rate_gap = float(medium["win_rate"]) - float(full["win_rate"])
    aggregate_medium_sample_sufficient = int(medium["trade_count"]) >= MIN_MEDIUM_TRADES_AGGREGATE
    four_hour_sample_sufficient = bool(
        four_hour is not None and int(four_hour["trade_count"]) >= MIN_MEDIUM_TRADES_AGGREGATE
    )

    weakness_gate = bool(
        valid_folds == len(EXPECTED_FOLDS)
        and aggregate_medium_sample_sufficient
        and all_mean_weaker
        and median_weaker_folds >= 2
        and win_rate_weaker_folds >= 2
        and negative_mean_folds >= 2
        and outlier_robust_folds >= 2
        and float(medium["mean_net_return"]) < 0.0
        and aggregate_mean_gap < 0.0
        and aggregate_win_rate_gap < 0.0
    )

    if weakness_gate:
        decision = "MEDIUM_WEAKNESS_CANDIDATE"
    elif valid_folds == len(EXPECTED_FOLDS) and all_mean_weaker and aggregate_mean_gap < 0.0:
        decision = "ALIGNMENT_TIERS_SEPARATE_NO_WEIGHT_CHANGE"
    else:
        decision = "INCONCLUSIVE"

    return {
        "decision": decision,
        "valid_comparison_folds": valid_folds,
        "required_valid_folds": len(EXPECTED_FOLDS),
        "all_valid_fold_mean_gaps_negative": all_mean_weaker,
        "median_weaker_folds": median_weaker_folds,
        "win_rate_weaker_folds": win_rate_weaker_folds,
        "medium_negative_mean_folds": negative_mean_folds,
        "outlier_robust_weaker_folds": outlier_robust_folds,
        "aggregate_medium_trade_count": int(medium["trade_count"]),
        "aggregate_full_trade_count": int(full["trade_count"]),
        "aggregate_medium_mean_net_return": float(medium["mean_net_return"]),
        "aggregate_full_mean_net_return": float(full["mean_net_return"]),
        "aggregate_mean_return_gap": aggregate_mean_gap,
        "aggregate_median_return_gap": aggregate_median_gap,
        "aggregate_win_rate_gap": aggregate_win_rate_gap,
        "aggregate_medium_sample_sufficient": (aggregate_medium_sample_sufficient),
        "four_hour_only_sample_sufficient": four_hour_sample_sufficient,
        "rd03_d1_weight_replay_research_authorized": weakness_gate,
        "weight_change_authorized": False,
        "trade_logic_changed": False,
    }


def validate_alignment_evidence(
    frame: pd.DataFrame,
    *,
    expected_trade_count: int,
    financial_invariance: bool,
) -> dict[str, Any]:
    """Validate completeness and immutable-research boundaries."""

    required = {
        "fold_id",
        "trade_id",
        "entry_time",
        "exit_time",
        "alignment_tier",
        "return_fraction",
        "net_pnl",
        "trade_logic_changed",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise AlignmentStabilityError(f"Alignment frame is missing validation columns: {missing}")

    folds = sorted(str(value) for value in frame["fold_id"].unique())
    tiers = sorted(str(value) for value in frame["alignment_tier"].unique())
    exits = pd.to_datetime(
        frame["exit_time"],
        utc=True,
        errors="raise",
    )

    checks: dict[str, Any] = {
        "expected_trade_count": expected_trade_count,
        "observed_trade_count": len(frame),
        "trade_count_matches": len(frame) == expected_trade_count,
        "trade_ids_unique": not bool(frame["trade_id"].duplicated().any()),
        "observed_folds": folds,
        "folds_match": folds == list(EXPECTED_FOLDS),
        "observed_tiers": tiers,
        "tiers_allowed": set(tiers).issubset(EXPECTED_TIERS),
        "financial_invariance": financial_invariance,
        "no_2025_access": bool((exits <= RESEARCH_LOCK).all()),
        "no_2026_access": True,
        "trade_logic_changed": bool(frame["trade_logic_changed"].astype(bool).any()),
    }
    safe = bool(
        checks["trade_count_matches"]
        and checks["trade_ids_unique"]
        and checks["folds_match"]
        and checks["tiers_allowed"]
        and checks["financial_invariance"]
        and checks["no_2025_access"]
        and checks["no_2026_access"]
        and not checks["trade_logic_changed"]
    )
    checks["status"] = "COMPLETE" if safe else "INVALID"
    return checks
