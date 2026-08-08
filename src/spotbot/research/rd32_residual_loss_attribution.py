"""RD32 residual-loss attribution engine.

This module is intentionally pure and filesystem-free. It accepts only canonical,
already-normalized RD31 result frames. Source-column adaptation belongs to RD32-P1.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final

import pandas as pd

SCHEMA_VERSION: Final = "rd32-residual-loss-attribution-engine-v1"
STAGE: Final = "RD32_P0B_RESIDUAL_LOSS_ATTRIBUTION_ENGINE_PRE_EXECUTION"

POLICY_ID: Final = "REGIME_HYSTERESIS_ADMISSION_GOVERNOR"
PORTFOLIO_ID: Final = "UNION_FOCUS"
COST_MULTIPLIER: Final = 2.0
PERIOD_ID: Final = "ROBUSTNESS_2022"
UNIVERSES: Final = ("C2", "D2", "E2")

FAMILY_MB: Final = "MOMENTUM_BREAKOUT"
FAMILY_RS: Final = "RELATIVE_STRENGTH_ROTATION"
FAMILY_BUCKET_MB: Final = "MB"
FAMILY_BUCKET_RS: Final = "RS"
FAMILY_BUCKET_OVERLAP: Final = "OVERLAP"

CLASS_CROSSED: Final = "CROSSED_TO_LOCKED"
CLASS_NO_CROSS: Final = "NO_LOCK_CROSS"

POST_LOCK_DAMAGE_THRESHOLD: Final = 0.50
MINIMUM_CROSSED_TRADE_COUNT: Final = 10
IDENTITY_ABS_TOLERANCE: Final = 1e-9

DECISION_SUPPORTED: Final = "RD32_RESIDUAL_LOSS_SUPPORTS_PORTFOLIO_DERISKING_RESEARCH"
DECISION_NOT_SUPPORTED: Final = (
    "RD32_RESIDUAL_LOSS_DOES_NOT_SUPPORT_PORTFOLIO_DERISKING_"
    "RETURN_TO_ADMISSION_OR_SIGNAL_FAMILY_REDESIGN"
)

JOIN_KEY: Final = (
    "policy_id",
    "portfolio_id",
    "universe_id",
    "cost_multiplier",
    "pair",
    "entry_time",
    "exit_time",
)

TRADE_REQUIRED_COLUMNS: Final = (
    *JOIN_KEY,
    "period_id",
    "net_pnl",
    "support_families",
    "entry_market_context",
    "entry_governor_state",
    "exit_reason",
)
DETERIORATION_REQUIRED_COLUMNS: Final = (
    *JOIN_KEY,
    "post_lock_net_contribution",
    "first_lock_time",
)

CRISIS_WINDOWS: Final = (
    ("TERRA_UST_DEPEG", pd.Timestamp("2022-05-09T00:00:00Z")),
    (
        "THREE_ARROWS_LIQUIDATION_ORDER",
        pd.Timestamp("2022-06-27T00:00:00Z"),
    ),
    ("FTX_BANKRUPTCY", pd.Timestamp("2022-11-11T00:00:00Z")),
)
CRISIS_WINDOW_HOURS: Final = 72


class RD32Error(RuntimeError):
    """Raised when the frozen RD32 attribution contract is violated."""


@dataclass(frozen=True)
class AttributionResult:
    trade_attribution: pd.DataFrame
    primary_metrics: pd.DataFrame
    gate_evaluation: pd.DataFrame
    diagnostics: dict[str, pd.DataFrame]
    decision: str


def _require_columns(
    frame: pd.DataFrame,
    required: Iterable[str],
    *,
    label: str,
) -> None:
    missing = sorted(set(required).difference(frame.columns))
    if missing:
        raise RD32Error(f"{label} missing canonical columns: {missing}")


def _normalize_utc_series(series: pd.Series, *, label: str) -> pd.Series:
    try:
        parsed = pd.to_datetime(series, utc=True, errors="raise")
    except Exception as exc:
        raise RD32Error(f"{label} contains invalid timestamps") from exc
    if bool(parsed.isna().any()):
        raise RD32Error(f"{label} contains missing timestamps")
    return parsed


def _finite_numeric(
    series: pd.Series,
    *,
    label: str,
) -> pd.Series:
    try:
        numeric = pd.to_numeric(series, errors="raise").astype(float)
    except Exception as exc:
        raise RD32Error(f"{label} must be numeric") from exc
    if bool(numeric.isna().any()):
        raise RD32Error(f"{label} contains NaN")
    if not bool(numeric.map(math.isfinite).all()):
        raise RD32Error(f"{label} contains non-finite values")
    return numeric


def _normalize_support(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [item.strip() for item in value.split("|") if item.strip()]
    elif isinstance(value, (tuple, list, set, frozenset)):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise RD32Error(f"unsupported support_families value: {value!r}")
    unique = tuple(sorted(set(items)))
    if not unique:
        raise RD32Error("empty support_families")
    allowed = {FAMILY_MB, FAMILY_RS}
    unknown = sorted(set(unique).difference(allowed))
    if unknown:
        raise RD32Error(f"unknown support family: {unknown}")
    if len(items) != len(set(items)):
        raise RD32Error("duplicate support family observed")
    return unique


def family_bucket(value: Any) -> str:
    support = _normalize_support(value)
    if support == (FAMILY_MB,):
        return FAMILY_BUCKET_MB
    if support == (FAMILY_RS,):
        return FAMILY_BUCKET_RS
    if support == tuple(sorted((FAMILY_MB, FAMILY_RS))):
        return FAMILY_BUCKET_OVERLAP
    raise RD32Error(f"ambiguous support-family set: {support}")


def validate_trades(raw: pd.DataFrame) -> pd.DataFrame:
    _require_columns(raw, TRADE_REQUIRED_COLUMNS, label="trade frame")
    frame = raw.loc[:, list(TRADE_REQUIRED_COLUMNS)].copy()
    frame["cost_multiplier"] = _finite_numeric(
        frame["cost_multiplier"],
        label="trade cost_multiplier",
    )
    frame["net_pnl"] = _finite_numeric(frame["net_pnl"], label="trade net_pnl")
    frame["entry_time"] = _normalize_utc_series(
        frame["entry_time"],
        label="trade entry_time",
    )
    frame["exit_time"] = _normalize_utc_series(
        frame["exit_time"],
        label="trade exit_time",
    )
    if bool((frame["exit_time"] < frame["entry_time"]).any()):
        raise RD32Error("trade exit_time precedes entry_time")
    for column in (
        "policy_id",
        "portfolio_id",
        "universe_id",
        "period_id",
        "pair",
        "entry_market_context",
        "entry_governor_state",
        "exit_reason",
    ):
        if bool(frame[column].isna().any()):
            raise RD32Error(f"trade {column} contains missing values")
        frame[column] = frame[column].astype(str)
        if bool((frame[column].str.len() == 0).any()):
            raise RD32Error(f"trade {column} contains empty values")
    frame["support_families"] = frame["support_families"].map(
        lambda value: "|".join(_normalize_support(value))
    )
    duplicate = frame.duplicated(list(JOIN_KEY), keep=False)
    if bool(duplicate.any()):
        raise RD32Error("duplicate trade join key")
    return frame


def validate_deterioration(raw: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        raw,
        DETERIORATION_REQUIRED_COLUMNS,
        label="deterioration frame",
    )
    frame = raw.loc[:, list(DETERIORATION_REQUIRED_COLUMNS)].copy()
    frame["cost_multiplier"] = _finite_numeric(
        frame["cost_multiplier"],
        label="deterioration cost_multiplier",
    )
    frame["post_lock_net_contribution"] = _finite_numeric(
        frame["post_lock_net_contribution"],
        label="post_lock_net_contribution",
    )
    for column in ("entry_time", "exit_time", "first_lock_time"):
        frame[column] = _normalize_utc_series(
            frame[column],
            label=f"deterioration {column}",
        )
    if bool((frame["exit_time"] < frame["entry_time"]).any()):
        raise RD32Error("deterioration exit_time precedes entry_time")
    if bool((frame["first_lock_time"] < frame["entry_time"]).any()):
        raise RD32Error("first_lock_time precedes trade entry_time")
    if bool((frame["first_lock_time"] > frame["exit_time"]).any()):
        raise RD32Error("first_lock_time exceeds trade exit_time")
    for column in (
        "policy_id",
        "portfolio_id",
        "universe_id",
        "pair",
    ):
        if bool(frame[column].isna().any()):
            raise RD32Error(f"deterioration {column} contains missing values")
        frame[column] = frame[column].astype(str)
        if bool((frame[column].str.len() == 0).any()):
            raise RD32Error(f"deterioration {column} contains empty values")
    duplicate = frame.duplicated(list(JOIN_KEY), keep=False)
    if bool(duplicate.any()):
        raise RD32Error("duplicate deterioration join key")
    return frame


def _scope_mask(frame: pd.DataFrame, *, include_period: bool) -> pd.Series:
    mask = (
        (frame["policy_id"] == POLICY_ID)
        & (frame["portfolio_id"] == PORTFOLIO_ID)
        & (frame["cost_multiplier"] == COST_MULTIPLIER)
        & frame["universe_id"].isin(UNIVERSES)
    )
    if include_period:
        mask &= frame["period_id"] == PERIOD_ID
    return mask


def _crisis_tag(first_lock_time: pd.Timestamp | pd.NaT) -> str:
    if pd.isna(first_lock_time):
        return "NONE"
    tags: list[str] = []
    delta = pd.Timedelta(hours=CRISIS_WINDOW_HOURS)
    for crisis_id, anchor in CRISIS_WINDOWS:
        if anchor - delta <= first_lock_time <= anchor + delta:
            tags.append(crisis_id)
    return "|".join(tags) if tags else "NONE"


def _empty_diagnostic(
    dimensions: list[str],
) -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            *dimensions,
            "trade_count",
            "final_net_pnl_sum",
            "pre_lock_net_contribution_sum",
            "post_lock_net_contribution_sum",
        ]
    )


def _aggregate_diagnostic(
    frame: pd.DataFrame,
    dimensions: list[str],
) -> pd.DataFrame:
    if frame.empty:
        return _empty_diagnostic(dimensions)
    result = (
        frame.groupby(dimensions, as_index=False, sort=True, dropna=False)
        .agg(
            trade_count=("final_trade_net_pnl", "size"),
            final_net_pnl_sum=("final_trade_net_pnl", "sum"),
            pre_lock_net_contribution_sum=("pre_lock_net_contribution", "sum"),
            post_lock_net_contribution_sum=("post_lock_net_contribution", "sum"),
        )
        .sort_values(dimensions, kind="stable")
        .reset_index(drop=True)
    )
    return result


def _attribution_frame(
    trades_raw: pd.DataFrame,
    deterioration_raw: pd.DataFrame,
) -> pd.DataFrame:
    trades = validate_trades(trades_raw)
    deterioration = validate_deterioration(deterioration_raw)

    primary_trades = trades.loc[_scope_mask(trades, include_period=True)].copy()
    primary_deterioration = deterioration.loc[
        _scope_mask(deterioration, include_period=False)
    ].copy()

    observed_universes = tuple(sorted(primary_trades["universe_id"].unique()))
    if observed_universes != tuple(sorted(UNIVERSES)):
        raise RD32Error(
            "primary trade frame must contain every frozen universe exactly "
            f"at least once: {observed_universes}"
        )

    trade_keys = primary_trades.loc[:, list(JOIN_KEY)]
    det_keys = primary_deterioration.loc[:, list(JOIN_KEY)]
    if len(primary_deterioration):
        det_match = det_keys.merge(
            trade_keys,
            on=list(JOIN_KEY),
            how="left",
            indicator=True,
            validate="one_to_one",
        )
        if bool((det_match["_merge"] != "both").any()):
            raise RD32Error("unmatched primary deterioration row")

    merged = primary_trades.merge(
        primary_deterioration,
        on=list(JOIN_KEY),
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    crossed = merged["_merge"] == "both"
    merged["classification"] = CLASS_NO_CROSS
    merged.loc[crossed, "classification"] = CLASS_CROSSED

    merged["final_trade_net_pnl"] = merged.pop("net_pnl").astype(float)
    merged["post_lock_net_contribution"] = merged["post_lock_net_contribution"].fillna(0.0)
    merged["pre_lock_net_contribution"] = (
        merged["final_trade_net_pnl"] - merged["post_lock_net_contribution"]
    )

    if bool(merged.loc[~crossed, "first_lock_time"].notna().any()):
        raise RD32Error("NO_LOCK_CROSS row unexpectedly has first_lock_time")
    merged["first_lock_transition_episode"] = "NONE"
    merged.loc[crossed, "first_lock_transition_episode"] = merged.loc[
        crossed, "first_lock_time"
    ].map(lambda value: "LOCK@" + pd.Timestamp(value).isoformat())
    merged["crisis_tag"] = merged["first_lock_time"].map(_crisis_tag)
    merged["family_bucket"] = merged["support_families"].map(family_bucket)

    reconstructed = merged["pre_lock_net_contribution"] + merged["post_lock_net_contribution"]
    delta = (reconstructed - merged["final_trade_net_pnl"]).abs()
    if bool((delta > IDENTITY_ABS_TOLERANCE).any()):
        raise RD32Error("accounting identity failure")

    merged = merged.drop(columns=["_merge"])
    return merged.sort_values(
        [
            "universe_id",
            "entry_time",
            "pair",
            "exit_time",
        ],
        kind="stable",
    ).reset_index(drop=True)


def _damage_fraction(total_pnl: float, post_lock_sum: float) -> float | None:
    if total_pnl >= 0.0:
        return None
    return max(0.0, -post_lock_sum / abs(total_pnl))


def _primary_metrics(attribution: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for universe_id in UNIVERSES:
        group = attribution.loc[attribution["universe_id"] == universe_id]
        crossed = group.loc[group["classification"] == CLASS_CROSSED]
        no_cross = group.loc[group["classification"] == CLASS_NO_CROSS]
        total_pnl = float(group["final_trade_net_pnl"].sum())
        post_lock_sum = float(crossed["post_lock_net_contribution"].sum())
        median_post = float(crossed["post_lock_net_contribution"].median()) if len(crossed) else 0.0
        rows.append(
            {
                "universe_id": universe_id,
                "total_2022_net_pnl": total_pnl,
                "total_2022_trade_count": int(len(group)),
                "crossed_to_locked_trade_count": int(len(crossed)),
                "no_lock_cross_trade_count": int(len(no_cross)),
                "crossed_final_net_pnl_sum": float(crossed["final_trade_net_pnl"].sum()),
                "no_lock_cross_final_net_pnl_sum": float(no_cross["final_trade_net_pnl"].sum()),
                "pre_lock_net_contribution_sum": float(group["pre_lock_net_contribution"].sum()),
                "post_lock_net_contribution_sum": post_lock_sum,
                "median_post_lock_net_contribution": median_post,
                "negative_post_lock_trade_count": int(
                    (crossed["post_lock_net_contribution"] < 0.0).sum()
                ),
                "positive_post_lock_trade_count": int(
                    (crossed["post_lock_net_contribution"] > 0.0).sum()
                ),
                "post_lock_damage_fraction_of_total_loss": _damage_fraction(
                    total_pnl,
                    post_lock_sum,
                ),
            }
        )
    return (
        pd.DataFrame.from_records(rows)
        .sort_values(
            "universe_id",
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _evaluate_gates(metrics: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    rows: list[dict[str, Any]] = []
    all_pass = True
    for row in metrics.to_dict(orient="records"):
        fraction = row["post_lock_damage_fraction_of_total_loss"]
        gates = {
            "TOTAL_2022_NET_PNL_LT_0": row["total_2022_net_pnl"] < 0.0,
            "POST_LOCK_NET_CONTRIBUTION_SUM_LT_0": (row["post_lock_net_contribution_sum"] < 0.0),
            "POST_LOCK_DAMAGE_FRACTION_OF_TOTAL_LOSS_GTE_0_50": (
                fraction is not None and fraction >= POST_LOCK_DAMAGE_THRESHOLD
            ),
            "CROSSED_TO_LOCKED_TRADE_COUNT_GTE_10": (
                row["crossed_to_locked_trade_count"] >= MINIMUM_CROSSED_TRADE_COUNT
            ),
            "MEDIAN_POST_LOCK_NET_CONTRIBUTION_LT_0": (
                row["median_post_lock_net_contribution"] < 0.0
            ),
        }
        universe_pass = all(gates.values())
        all_pass = all_pass and universe_pass
        for gate_id, passed in gates.items():
            rows.append(
                {
                    "universe_id": row["universe_id"],
                    "gate_id": gate_id,
                    "passed": bool(passed),
                }
            )
        rows.append(
            {
                "universe_id": row["universe_id"],
                "gate_id": "ALL_PREREGISTERED_DERISKING_ROUTE_GATES",
                "passed": bool(universe_pass),
            }
        )
    decision = DECISION_SUPPORTED if all_pass else DECISION_NOT_SUPPORTED
    gates = (
        pd.DataFrame.from_records(rows)
        .sort_values(
            ["universe_id", "gate_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    return gates, decision


def _diagnostics(attribution: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "pair": _aggregate_diagnostic(attribution, ["universe_id", "pair"]),
        "family_bucket": _aggregate_diagnostic(
            attribution,
            ["universe_id", "family_bucket"],
        ),
        "entry_market_context": _aggregate_diagnostic(
            attribution,
            ["universe_id", "entry_market_context"],
        ),
        "entry_governor_state": _aggregate_diagnostic(
            attribution,
            ["universe_id", "entry_governor_state"],
        ),
        "first_lock_transition_episode": _aggregate_diagnostic(
            attribution,
            ["universe_id", "first_lock_transition_episode"],
        ),
        "exit_reason": _aggregate_diagnostic(
            attribution,
            ["universe_id", "exit_reason"],
        ),
        "crisis_tag": _aggregate_diagnostic(
            attribution,
            ["universe_id", "crisis_tag"],
        ),
    }


def execute_attribution(
    trades: pd.DataFrame,
    deterioration: pd.DataFrame,
) -> AttributionResult:
    """Execute the frozen RD32 accounting attribution on canonical frames."""
    attribution = _attribution_frame(trades, deterioration)
    metrics = _primary_metrics(attribution)
    gates, decision = _evaluate_gates(metrics)
    return AttributionResult(
        trade_attribution=attribution,
        primary_metrics=metrics,
        gate_evaluation=gates,
        diagnostics=_diagnostics(attribution),
        decision=decision,
    )


def contract_summary() -> dict[str, Any]:
    """Return the frozen non-I/O contract for audit/tests."""
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "policy_id": POLICY_ID,
        "portfolio_id": PORTFOLIO_ID,
        "cost_multiplier": COST_MULTIPLIER,
        "period_id": PERIOD_ID,
        "universes": list(UNIVERSES),
        "post_lock_damage_threshold": POST_LOCK_DAMAGE_THRESHOLD,
        "minimum_crossed_trade_count": MINIMUM_CROSSED_TRADE_COUNT,
        "identity_abs_tolerance": IDENTITY_ABS_TOLERANCE,
        "canonical_input_only": True,
        "filesystem_io": False,
        "network_io": False,
        "raw_market_data": False,
        "economic_replay": False,
        "actual_rd31_attribution_execution": False,
        "2024_access": False,
        "post_2024_access": False,
        "production_authorized": False,
        "forced_exit_counterfactual_decision_evidence": False,
        "source_schema_adapter_stage": "RD32_P1_ONLY",
    }
