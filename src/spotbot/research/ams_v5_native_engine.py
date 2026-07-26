"""Self-contained, causal AMS V5R1 spot-only research engine.

The fill ledger is the accounting source of truth.  Signals are created from a
closed bar and every entry, add-on, or confirmed discretionary exit is executed
at the next bar open.  The module deliberately has no V4 strategy dependency.
"""

from __future__ import annotations

import hashlib
import itertools
import math
import operator
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

RESEARCH_LOCK = pd.Timestamp("2025-01-01T00:00:00Z")
CLUSTER_LOOKBACK_DAYS = 90
CLUSTER_CORRELATION = 0.75
RECONCILIATION_TOLERANCE = 1e-7
ENTRY_FILL_TYPES = frozenset({"ENTRY", "ADD_ON"})
EXIT_FILL_TYPES = frozenset(
    {
        "STOP_EXIT",
        "TRAILING_EXIT",
        "STRUCTURE_EXIT",
        "STAGNATION_EXIT",
        "VENUE_EXIT",
        "END_OF_FOLD_EXIT",
    }
)
_DAILY_CLOSE_CACHE: dict[str, pd.DataFrame] = {}
_CLUSTER_SNAPSHOT_CACHE: dict[str, dict[pd.Timestamp, dict[str, str]]] = {}


class V5NativeError(RuntimeError):
    """Raised when a V5R1 causal or accounting contract is violated."""


@dataclass(frozen=True)
class V5PortfolioProfile:
    profile_id: str
    base_risk: float
    max_initial_risk: float
    max_position_risk: float
    max_heat: float
    max_positions: int
    max_cluster: int = 2


@dataclass(frozen=True)
class V5Parameters:
    configuration_id: str
    family: str
    stop_model: str
    fibonacci_mode: str
    threshold: int = 55
    cost: float = 0.002


@dataclass
class V5SetupCandidate:
    candidate_id: str
    fold_id: str
    configuration_id: str
    symbol: str
    signal_open: pd.Timestamp
    signal_close: pd.Timestamp
    scheduled_open: pd.Timestamp
    family: str
    actual_family: str
    score: float
    relative_strength: float
    threshold: int
    d1_score: float
    eight_hour_score: float
    four_hour_score: float
    fibonacci: float
    entry_reference: float
    structural_stop_reference: float
    atr: float
    stop_atr: float
    requested_risk: float = 0.0
    accepted: bool = False
    rejection_reason: str | None = None
    action: Literal["ENTRY", "ADD_ON", "REENTRY"] = "ENTRY"
    original_position_id: str | None = None
    reentry_sequence: int = 0
    cluster_id: str = ""
    cluster_window_start: pd.Timestamp | None = None
    cluster_window_end: pd.Timestamp | None = None
    cluster_open_position_count: int = 0
    cluster_limit: int = 2


@dataclass(frozen=True)
class V5ScheduledEntry:
    candidate_id: str
    symbol: str
    entry_time: pd.Timestamp
    action: Literal["ENTRY", "ADD_ON", "REENTRY"]
    position_id: str | None = None


@dataclass(frozen=True)
class V5Fill:
    fill_id: str
    candidate_id: str
    position_id: str
    symbol: str
    timestamp: pd.Timestamp
    fill_type: str
    price: float
    quantity: float
    notional: float
    fee: float
    cash_before: float
    cash_after: float
    position_quantity_before: float
    position_quantity_after: float
    portfolio_heat_before: float
    portfolio_heat_after: float
    reason: str


@dataclass
class V5OpenPosition:
    position_id: str
    candidate_id: str
    symbol: str
    quantity: float
    initial_quantity: float
    average_entry: float
    stop: float
    initial_stop: float
    initial_risk_per_unit: float
    risk_fraction: float
    total_risk_fraction: float
    entry_time: pd.Timestamp
    entry_notional: float
    entry_fees: float
    reentry_sequence: int = 0
    original_position_id: str | None = None
    mfe_r: float = 0.0
    mae_r: float = 0.0
    bars_held: int = 0
    add_on_used: bool = False
    trailing_activated: bool = False
    trailing_activation_reason: str | None = None
    consecutive_structure_failures: int = 0


@dataclass(frozen=True)
class V5ClosedTrade:
    trade_id: str
    position_id: str
    candidate_id: str
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    average_entry: float
    exit_price: float
    quantity: float
    realised_pnl: float
    return_fraction: float
    reason: str
    mae_r: float
    mfe_r: float
    bars_held: int
    add_on_used: bool
    reentry_sequence: int
    original_position_id: str | None


@dataclass
class V5RejectionCounters:
    values: dict[str, int] = field(default_factory=dict)

    def add(self, key: str) -> None:
        self.values[key] = self.values.get(key, 0) + 1


@dataclass(frozen=True)
class V5ReconciliationResult:
    status: str
    final_cash: float
    fees: float
    turnover: float
    realised_pnl: float
    open_quantities: Mapping[str, float]
    cash_difference: float
    fees_difference: float
    turnover_difference: float
    pnl_difference: float


@dataclass(frozen=True)
class V5FoldResult:
    fold_id: str
    status: str
    initial_capital: float
    final_cash: float
    candidates: tuple[V5SetupCandidate, ...]
    scheduled_entries: tuple[V5ScheduledEntry, ...]
    fills: tuple[V5Fill, ...]
    trades: tuple[V5ClosedTrade, ...]
    equity_curve: tuple[tuple[pd.Timestamp, float], ...]
    rejections: Mapping[str, int]
    reconciliation: V5ReconciliationResult
    open_positions_after_fold: int


@dataclass(frozen=True)
class V5ThresholdSelection:
    selected_threshold: int
    train_hash_sha256: str
    validation_inspected: bool
    metrics_by_threshold: Mapping[int, Mapping[str, Any]]
    normalized_components: Mapping[int, Mapping[str, float]]
    quality_scores: Mapping[int, float]
    exclusions: Mapping[int, str]


@dataclass
class _ReentryState:
    original_position_id: str
    stop_timestamp: pd.Timestamp
    earliest_signal_time: pd.Timestamp
    used: bool = False
    crisis: bool = False
    structural_invalidation: bool = False


def profiles() -> tuple[V5PortfolioProfile, ...]:
    """Return the two pre-registered V5R1 risk profiles."""
    return (
        V5PortfolioProfile("AMS-V5R1-P01", 0.007, 0.0095, 0.012, 0.045, 5),
        V5PortfolioProfile("AMS-V5R1-P02", 0.0095, 0.013, 0.016, 0.065, 6),
    )


def configuration_grid() -> tuple[V5Parameters, ...]:
    variants = (
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_BALANCED"),
        ("SHALLOW_PULLBACK_RECLAIM", "STRUCTURE_WIDE"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_BALANCED"),
        ("DEEP_PULLBACK_RECOVERY", "STRUCTURE_WIDE"),
        ("MOMENTUM_REACCELERATION", "STRUCTURE_BALANCED"),
        ("HYBRID_ALL_THREE", "STRUCTURE_BALANCED"),
    )
    result: list[V5Parameters] = []
    sequence = 1
    for family, stop_model in variants:
        for fibonacci_mode in ("NO_FIBONACCI", "SOFT_FIBONACCI_SCORE"):
            result.append(
                V5Parameters(
                    f"AMS-V5R1-A{sequence:02d}",
                    family,
                    stop_model,
                    fibonacci_mode,
                )
            )
            sequence += 1
    return tuple(result)


def assert_boundary(frame: pd.DataFrame) -> None:
    """Enforce the bar-ownership research lock without reading post-lock bars."""
    for column, strict in (("bar_open_time", True), ("bar_close_time", False)):
        if column not in frame:
            raise V5NativeError(f"missing {column}")
        values = pd.to_datetime(frame[column], utc=True)
        violation = values.ge(RESEARCH_LOCK) if strict else values.gt(RESEARCH_LOCK)
        if bool(violation.any()):
            raise V5NativeError(f"locked {column}")


def _availability_frame(availability: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "tradable_from", "tradable_until"}
    if not required.issubset(availability.columns):
        raise V5NativeError("availability columns missing")
    result = availability[list(required)].copy()
    result["tradable_from"] = pd.to_datetime(result["tradable_from"], utc=True)
    result["tradable_until"] = pd.to_datetime(result["tradable_until"], utc=True)
    return result


def build_features(four_hour: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    """Build causal native 4H, 8H-like, and daily-environment features."""
    assert_boundary(four_hour)
    source = four_hour.copy()
    source["bar_open_time"] = pd.to_datetime(source["bar_open_time"], utc=True)
    source["bar_close_time"] = pd.to_datetime(source["bar_close_time"], utc=True)
    source = source.sort_values(["symbol", "bar_close_time"], kind="mergesort")
    built: list[pd.DataFrame] = []
    for _symbol, raw in source.groupby("symbol", sort=True):
        frame = raw.copy()
        previous_close = frame["close"].shift(1)
        true_range = pd.concat(
            [
                frame["high"] - frame["low"],
                (frame["high"] - previous_close).abs(),
                (frame["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr"] = true_range.rolling(14, min_periods=14).mean()
        frame["ema21"] = frame["close"].ewm(span=21, adjust=False).mean()
        frame["ema55"] = frame["close"].ewm(span=55, adjust=False).mean()
        frame["ema200"] = frame["close"].ewm(span=200, adjust=False).mean()
        frame["trend_slope"] = frame["ema21"].pct_change(12)
        frame["relative_strength"] = frame["close"].pct_change(42)
        frame["pullback_depth_atr"] = ((frame["ema21"] - frame["low"]) / frame["atr"]).clip(
            lower=0.0
        )
        trend = (
            (frame["close"] > frame["ema55"])
            & (frame["ema21"] > frame["ema55"])
            & (frame["trend_slope"] > -0.002)
        )
        reclaim = (
            (frame["close"] > frame["ema21"])
            & (frame["close"] > frame["open"])
            & (previous_close <= frame["ema21"].shift(1))
        )
        prior_low = frame["low"].rolling(12, min_periods=6).min().shift(1)
        frame["shallow"] = trend & frame["pullback_depth_atr"].between(0.5, 1.5) & reclaim
        frame["deep"] = (
            trend
            & frame["pullback_depth_atr"].between(1.5, 3.0)
            & reclaim
            & (frame["low"] >= prior_low)
        )
        prior_high = frame["high"].rolling(8, min_periods=4).max().shift(1)
        short_range = (frame["high"] - frame["low"]).rolling(4, min_periods=4).mean()
        long_range = (frame["high"] - frame["low"]).rolling(20, min_periods=8).mean()
        frame["reaccel"] = (
            trend
            & (short_range.shift(1) < long_range.shift(1) * 0.8)
            & (frame["close"] > prior_high)
            & (((frame["close"] - frame["ema21"]) / frame["atr"]) < 3.2)
        )
        frame["family"] = np.select(
            [frame["shallow"], frame["deep"], frame["reaccel"]],
            [
                "SHALLOW_PULLBACK_RECLAIM",
                "DEEP_PULLBACK_RECOVERY",
                "MOMENTUM_REACCELERATION",
            ],
            default="NONE",
        )
        daily_trend = (frame["close"] > frame["ema200"]).astype(float)
        frame["d1_score"] = 4.0 + 8.0 * daily_trend
        frame["eight_hour_score"] = (
            5.0
            + 8.0 * trend.astype(float)
            + (frame["trend_slope"].clip(0, 0.02) * 250.0)
        ).clip(0, 18)
        setup = (frame["family"] != "NONE").astype(float)
        frame["four_hour_score"] = 25.0 * setup
        momentum = ((frame["close"] - previous_close) / frame["atr"]).clip(-1, 1)
        frame["momentum_score"] = (6.0 + 6.0 * momentum).clip(0, 12)
        frame["structure_score"] = 10.0 * trend.astype(float)
        if "volume" in frame:
            median_volume = frame["volume"].rolling(42, min_periods=12).median()
            frame["liquidity_score"] = (
                4.0 + 4.0 * (frame["volume"] / median_volume - 1).clip(-1, 1)
            ).clip(0, 8)
        else:
            frame["liquidity_score"] = 4.0
        frame["fib"] = np.select(
            [
                frame["pullback_depth_atr"].between(0.8, 1.2),
                frame["pullback_depth_atr"].between(0.5, 1.5),
                frame["pullback_depth_atr"] > 3.0,
            ],
            [5.0, 3.0, -5.0],
            default=0.0,
        )
        base_score = (
            frame["d1_score"]
            + frame["eight_hour_score"]
            + frame["relative_strength"].clip(-0.1, 0.1) * 50.0
            + frame["four_hour_score"]
            + frame["momentum_score"]
            + frame["structure_score"]
            + frame["liquidity_score"]
        )
        frame["score_no_fib"] = base_score.clip(0, 100)
        frame["score_soft_fib"] = (base_score + frame["fib"]).clip(0, 100)
        frame["overextended"] = ((frame["close"] - frame["ema21"]) / frame["atr"]) > 3.2
        frame["higher_low"] = np.where(
            frame["low"] > frame["low"].rolling(8, min_periods=4).min().shift(1),
            frame["low"],
            np.nan,
        )
        frame["structure_reference"] = prior_low
        frame["structure_failure"] = frame["close"] < frame["ema55"]
        frame["eight_hour_weak"] = frame["eight_hour_score"] < 8.0
        frame["conviction_declined"] = frame["score_no_fib"] < 45.0
        frame["new_bullish_structure"] = frame["higher_low"].notna() & trend
        frame["crisis"] = (frame["close"] < frame["ema200"]) & (frame["trend_slope"] < -0.01)
        built.append(frame)
    panel = pd.concat(built, ignore_index=True)
    panel = panel.merge(_availability_frame(availability), on="symbol", how="left")
    if panel[["tradable_from", "tradable_until"]].isna().any().any():
        raise V5NativeError("availability missing for symbol")
    assert_boundary(panel)
    return panel.sort_values(["bar_open_time", "symbol"], kind="mergesort").reset_index(drop=True)


def risk_multiplier(score: float) -> float:
    if score < 60:
        return 0.70
    if score < 70:
        return 0.90
    if score < 80:
        return 1.00
    return 1.20


def drawdown_multiplier(drawdown: float) -> float:
    if drawdown < 0.08:
        return 1.00
    if drawdown < 0.12:
        return 0.85
    if drawdown < 0.16:
        return 0.65
    if drawdown < 0.20:
        return 0.40
    if drawdown <= 0.24:
        return 0.20
    return 0.0


def stop_distance(entry: float, atr: float, structural: float, model: str) -> float | None:
    if not all(math.isfinite(value) for value in (entry, atr, structural)) or atr <= 0:
        return None
    if model == "V4_T12_STRUCTURE":
        minimum, maximum = 2.2, 3.8
    else:
        minimum, maximum = (2.2, 3.4) if model == "STRUCTURE_BALANCED" else (2.6, 4.0)
    structural_distance = entry - structural
    if structural_distance <= 0 or structural_distance / atr > maximum:
        return None
    return max(structural_distance, minimum * atr)


def trailing_stop(
    current: float,
    entry: float,
    atr: float,
    mfe_r: float,
    higher_low: float | None,
    *,
    highest_price: float | None = None,
) -> tuple[float, str | None]:
    """Return a monotonic stop; the caller applies it only to later bars."""
    if mfe_r < 2.25 and higher_low is None:
        return current, None
    high = highest_price if highest_price is not None else entry + mfe_r * max(entry - current, 0)
    chandelier = high - 3.5 * atr
    structure = higher_low - 0.25 * atr if higher_low is not None else -math.inf
    reason = "HIGHER_LOW" if higher_low is not None else "MFE_2_25R"
    return max(current, chandelier, structure), reason


def _candidate_family_matches(actual: str, configured: str) -> bool:
    return actual != "NONE" and (
        configured in {"HYBRID_ALL_THREE", "HYBRID"} or actual == configured
    )


def make_candidate(
    row: Mapping[str, Any],
    params: V5Parameters,
    fold_id: str,
    *,
    action: Literal["ENTRY", "ADD_ON", "REENTRY"] = "ENTRY",
    original_position_id: str | None = None,
    reentry_sequence: int = 0,
) -> V5SetupCandidate | None:
    actual = str(row["family"])
    if not _candidate_family_matches(actual, params.family):
        return None
    score = float(
        row["score_soft_fib"]
        if params.fibonacci_mode == "SOFT_FIBONACCI_SCORE"
        else row["score_no_fib"]
    )
    atr = float(row["atr"])
    structural = float(row.get("structure_reference", row["low"] - 0.25 * atr))
    distance = (
        (2.2 if params.stop_model == "STRUCTURE_BALANCED" else 2.6) * atr
        if action == "ADD_ON"
        else stop_distance(float(row["close"]), atr, structural, params.stop_model)
    )
    if distance is None:
        return None
    signal_close = pd.Timestamp(row["bar_close_time"])
    identity = (
        f"{params.configuration_id}|{fold_id}|{row['symbol']}|"
        f"{signal_close.isoformat()}|{action}|{reentry_sequence}"
    )
    candidate_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
    return V5SetupCandidate(
        candidate_id=candidate_id,
        fold_id=fold_id,
        configuration_id=params.configuration_id,
        symbol=str(row["symbol"]),
        signal_open=pd.Timestamp(row["bar_open_time"]),
        signal_close=signal_close,
        scheduled_open=signal_close,
        family=params.family,
        actual_family=actual,
        score=score,
        relative_strength=float(row.get("relative_strength", 0.0)),
        threshold=params.threshold,
        d1_score=float(row["d1_score"]),
        eight_hour_score=float(row["eight_hour_score"]),
        four_hour_score=float(row["four_hour_score"]),
        fibonacci=float(row["fib"]) if params.fibonacci_mode == "SOFT_FIBONACCI_SCORE" else 0.0,
        entry_reference=float(row["close"]),
        structural_stop_reference=float(row["close"]) - distance,
        atr=atr,
        stop_atr=distance / atr,
        action=action,
        original_position_id=original_position_id,
        reentry_sequence=reentry_sequence,
    )


def correlation_clusters(
    frame: pd.DataFrame,
    as_of: pd.Timestamp,
    window_days: int = CLUSTER_LOOKBACK_DAYS,
) -> dict[str, str]:
    """Return deterministic causal connected components from daily returns."""
    as_of = pd.Timestamp(as_of)
    symbols = sorted(str(value) for value in frame["symbol"].unique())
    daily_close = (
        frame.set_index("bar_close_time")
        .groupby("symbol")["close"]
        .resample("1D")
        .last()
        .unstack(0)
    )
    return _clusters_from_daily_close(daily_close, symbols, as_of, window_days)


def _clusters_from_daily_close(
    daily_close: pd.DataFrame,
    symbols: Sequence[str],
    as_of: pd.Timestamp,
    window_days: int = CLUSTER_LOOKBACK_DAYS,
) -> dict[str, str]:
    eligible = daily_close.loc[
        (daily_close.index < as_of)
        & (daily_close.index >= as_of - pd.Timedelta(days=window_days))
    ]
    if eligible.empty:
        return {symbol: symbol for symbol in symbols}
    daily = eligible.pct_change(fill_method=None)
    correlations = daily.corr(min_periods=20)
    parent = {symbol: symbol for symbol in symbols}

    def find(symbol: str) -> str:
        while parent[symbol] != symbol:
            parent[symbol] = parent[parent[symbol]]
            symbol = parent[symbol]
        return symbol

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for index, left in enumerate(symbols):
        if left not in correlations:
            continue
        for right in symbols[index + 1 :]:
            correlation = (
                float(cast(Any, correlations.at[left, right]))
                if right in correlations
                else np.nan
            )
            if correlation >= CLUSTER_CORRELATION:
                union(left, right)
    return {symbol: find(symbol) for symbol in symbols}


def _frame_hash(frame: pd.DataFrame) -> str:
    ordered = frame.sort_values(["bar_open_time", "symbol"], kind="mergesort")
    hashed = np.asarray(pd.util.hash_pandas_object(ordered, index=True)).tobytes()
    return hashlib.sha256(hashed).hexdigest()


def _cluster_cache_key(frame: pd.DataFrame) -> str:
    columns = frame[["symbol", "bar_close_time", "close"]]
    hashed = np.asarray(pd.util.hash_pandas_object(columns, index=False)).tobytes()
    return hashlib.sha256(hashed).hexdigest()


def choose_threshold(metrics_by_threshold: dict[int, dict[str, float]]) -> dict[str, Any]:
    """Apply the exact pre-registered train-only objective."""
    allowed = {50, 55}
    if set(metrics_by_threshold) != allowed:
        raise V5NativeError("thresholds must be exactly 50 and 55")
    excluded: dict[int, str] = {}
    eligible: dict[int, dict[str, float]] = {}
    for threshold, values in metrics_by_threshold.items():
        if values["profit_factor"] < 1.10:
            excluded[threshold] = "TRAIN_PROFIT_FACTOR_BELOW_1_10"
        elif values["maximum_drawdown"] > 0.30:
            excluded[threshold] = "TRAIN_DRAWDOWN_ABOVE_30_PERCENT"
        elif bool(values.get("safety_failure", 0.0)):
            excluded[threshold] = "TRAIN_SAFETY_FAILURE"
        else:
            eligible[threshold] = values
    if not eligible:
        return {
            "selected": 55,
            "excluded": excluded,
            "quality_scores": {},
            "normalized": {},
        }
    component_names = (
        "expectancy",
        "profit_factor",
        "calmar",
        "activity_alignment",
        "stress_resilience",
    )
    normalized: dict[int, dict[str, float]] = {}
    for threshold, values in eligible.items():
        normalized[threshold] = {}
        for component in component_names:
            minimum = min(item[component] for item in eligible.values())
            maximum = max(item[component] for item in eligible.values())
            normalized[threshold][component] = (
                1.0 if maximum == minimum else (values[component] - minimum) / (maximum - minimum)
            )
    weights = {
        "expectancy": 0.35,
        "profit_factor": 0.25,
        "calmar": 0.20,
        "activity_alignment": 0.10,
        "stress_resilience": 0.10,
    }
    scores = {
        threshold: sum(weights[name] * normalized[threshold][name] for name in component_names)
        for threshold in eligible
    }
    return {
        "selected": max(scores, key=lambda value: (scores[value], value)),
        "excluded": excluded,
        "quality_scores": scores,
        "normalized": normalized,
    }


def _fold_metrics(result: V5FoldResult) -> dict[str, float]:
    returns = np.asarray([trade.return_fraction for trade in result.trades], dtype=float)
    profits = np.asarray([trade.realised_pnl for trade in result.trades], dtype=float)
    gross_profit = float(profits[profits > 0].sum()) if profits.size else 0.0
    gross_loss = float(-profits[profits < 0].sum()) if profits.size else 0.0
    profit_factor = (
        gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    )
    equity = np.asarray([value for _, value in result.equity_curve], dtype=float)
    if equity.size:
        running_peak = np.maximum.accumulate(equity)
        maximum_drawdown = float(np.max(1.0 - equity / running_peak))
    else:
        maximum_drawdown = 0.0
    net_return = result.final_cash / result.initial_capital - 1.0
    calmar = net_return / maximum_drawdown if maximum_drawdown > 0 else max(net_return, 0.0)
    expectancy = float(returns.mean()) if returns.size else 0.0
    years = max(
        (
            result.equity_curve[-1][0] - result.equity_curve[0][0]
        ).total_seconds()
        / (365.25 * 86400)
        if len(result.equity_curve) > 1
        else 1.0,
        1 / 365.25,
    )
    trades_per_year = len(result.trades) / years
    activity_alignment = max(0.0, 1.0 - abs(trades_per_year - 170.0) / 170.0)
    return {
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "maximum_drawdown": maximum_drawdown,
        "calmar": calmar,
        "activity_alignment": activity_alignment,
        "stress_resilience": net_return,
        "safety_failure": float(result.status != "PASS"),
    }


def select_native_fold_threshold(
    *,
    train_panel: pd.DataFrame,
    configuration: V5Parameters,
    portfolio_profile: V5PortfolioProfile,
    base_transaction_cost: float = 0.002,
    stress_transaction_cost: float = 0.004,
    initial_capital: float = 100_000.0,
    fold_id: str = "TRAIN",
) -> V5ThresholdSelection:
    """Run thresholds 50/55 on Train only; this API accepts no validation data."""
    assert_boundary(train_panel)
    raw_metrics: dict[int, dict[str, float]] = {}
    for threshold in (50, 55):
        base = simulate_native_fold(
            four_hour_panel=train_panel,
            configuration=configuration,
            portfolio_profile=portfolio_profile,
            selected_threshold=threshold,
            transaction_cost=base_transaction_cost,
            initial_capital=initial_capital,
            fold_id=f"{fold_id}-T{threshold}-BASE",
        )
        stress = simulate_native_fold(
            four_hour_panel=train_panel,
            configuration=configuration,
            portfolio_profile=portfolio_profile,
            selected_threshold=threshold,
            transaction_cost=stress_transaction_cost,
            initial_capital=initial_capital,
            fold_id=f"{fold_id}-T{threshold}-STRESS",
        )
        metrics = _fold_metrics(base)
        metrics["stress_resilience"] = _fold_metrics(stress)["expectancy"]
        raw_metrics[threshold] = metrics
    decision = choose_threshold(raw_metrics)
    return V5ThresholdSelection(
        selected_threshold=int(decision["selected"]),
        train_hash_sha256=_frame_hash(train_panel),
        validation_inspected=False,
        metrics_by_threshold=raw_metrics,
        normalized_components=decision["normalized"],
        quality_scores=decision["quality_scores"],
        exclusions=decision["excluded"],
    )


def reconcile_native_fold_from_fills(
    fills: Sequence[V5Fill],
    *,
    initial_capital: float,
    engine_final_cash: float | None = None,
    engine_fees: float | None = None,
    engine_turnover: float | None = None,
    engine_realised_pnl: float | None = None,
) -> V5ReconciliationResult:
    """Rebuild cash, quantities, fees, turnover, and realised PnL from fills."""
    cash = initial_capital
    fees = 0.0
    turnover = 0.0
    quantities: dict[str, float] = {}
    entry_cost: dict[str, float] = {}
    realised_pnl = 0.0
    for fill in fills:
        if abs(fill.cash_before - cash) > RECONCILIATION_TOLERANCE:
            raise V5NativeError(f"cash_before mismatch at {fill.fill_id}")
        fees += fill.fee
        turnover += fill.notional
        before_quantity = quantities.get(fill.position_id, 0.0)
        if fill.fill_type in ENTRY_FILL_TYPES:
            cash -= fill.notional + fill.fee
            quantities[fill.position_id] = before_quantity + fill.quantity
            entry_cost[fill.position_id] = (
                entry_cost.get(fill.position_id, 0.0) + fill.notional + fill.fee
            )
        elif fill.fill_type in EXIT_FILL_TYPES:
            if fill.quantity > before_quantity + RECONCILIATION_TOLERANCE:
                raise V5NativeError(f"exit quantity exceeds position at {fill.fill_id}")
            cash += fill.notional - fill.fee
            quantities[fill.position_id] = before_quantity - fill.quantity
            if quantities[fill.position_id] <= RECONCILIATION_TOLERANCE:
                realised_pnl += fill.notional - fill.fee - entry_cost.pop(fill.position_id, 0.0)
                quantities.pop(fill.position_id, None)
        else:
            raise V5NativeError(f"unknown fill type {fill.fill_type}")
        if abs(fill.cash_after - cash) > RECONCILIATION_TOLERANCE:
            raise V5NativeError(f"cash_after mismatch at {fill.fill_id}")
        if abs(fill.position_quantity_before - before_quantity) > RECONCILIATION_TOLERANCE:
            raise V5NativeError(f"quantity_before mismatch at {fill.fill_id}")
        after_quantity = quantities.get(fill.position_id, 0.0)
        if abs(fill.position_quantity_after - after_quantity) > RECONCILIATION_TOLERANCE:
            raise V5NativeError(f"quantity_after mismatch at {fill.fill_id}")
    expected_cash = cash if engine_final_cash is None else engine_final_cash
    expected_fees = fees if engine_fees is None else engine_fees
    expected_turnover = turnover if engine_turnover is None else engine_turnover
    expected_pnl = realised_pnl if engine_realised_pnl is None else engine_realised_pnl
    differences = (
        expected_cash - cash,
        expected_fees - fees,
        expected_turnover - turnover,
        expected_pnl - realised_pnl,
    )
    status = (
        "PASS"
        if not quantities and all(abs(value) <= RECONCILIATION_TOLERANCE for value in differences)
        else "FAIL"
    )
    return V5ReconciliationResult(
        status,
        cash,
        fees,
        turnover,
        realised_pnl,
        dict(quantities),
        differences[0],
        differences[1],
        differences[2],
        differences[3],
    )


def reconcile_fills(initial_cash: float, fills: list[V5Fill]) -> dict[str, float]:
    """Backward-compatible projection used by early V5R1 unit tests."""
    result = reconcile_native_fold_from_fills(fills, initial_capital=initial_cash)
    return {"cash": result.final_cash, "fees": result.fees, "turnover": result.turnover}


def _heat(positions: Mapping[str, V5OpenPosition]) -> float:
    return sum(position.total_risk_fraction for position in positions.values())


def _equity(
    cash: float,
    positions: Mapping[str, V5OpenPosition],
    prices: Mapping[str, float],
) -> float:
    return cash + sum(
        position.quantity * prices.get(symbol, position.average_entry)
        for symbol, position in positions.items()
    )


def _position_id(configuration_id: str, fold_id: str, symbol: str, sequence: int) -> str:
    raw = f"{configuration_id}|{fold_id}|{symbol}|{sequence}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _fill(
    fills: list[V5Fill],
    *,
    fold_id: str,
    candidate_id: str,
    position_id: str,
    symbol: str,
    timestamp: pd.Timestamp,
    fill_type: str,
    price: float,
    quantity: float,
    fee_rate: float,
    cash: float,
    quantity_before: float,
    quantity_after: float,
    heat_before: float,
    heat_after: float,
    reason: str,
) -> tuple[float, V5Fill]:
    notional = price * quantity
    fee = notional * fee_rate
    cash_after = (
        cash - notional - fee if fill_type in ENTRY_FILL_TYPES else cash + notional - fee
    )
    record = V5Fill(
        fill_id=f"{fold_id}-F{len(fills) + 1:08d}",
        candidate_id=candidate_id,
        position_id=position_id,
        symbol=symbol,
        timestamp=timestamp,
        fill_type=fill_type,
        price=price,
        quantity=quantity,
        notional=notional,
        fee=fee,
        cash_before=cash,
        cash_after=cash_after,
        position_quantity_before=quantity_before,
        position_quantity_after=quantity_after,
        portfolio_heat_before=heat_before,
        portfolio_heat_after=heat_after,
        reason=reason,
    )
    fills.append(record)
    return cash_after, record


def _close_position(
    *,
    positions: dict[str, V5OpenPosition],
    symbol: str,
    price: float,
    timestamp: pd.Timestamp,
    fill_type: str,
    fee_rate: float,
    cash: float,
    fills: list[V5Fill],
    trades: list[V5ClosedTrade],
    fold_id: str,
) -> float:
    position = positions[symbol]
    heat_before = _heat(positions)
    cash, fill = _fill(
        fills,
        fold_id=fold_id,
        candidate_id=position.candidate_id,
        position_id=position.position_id,
        symbol=symbol,
        timestamp=timestamp,
        fill_type=fill_type,
        price=price,
        quantity=position.quantity,
        fee_rate=fee_rate,
        cash=cash,
        quantity_before=position.quantity,
        quantity_after=0.0,
        heat_before=heat_before,
        heat_after=heat_before - position.total_risk_fraction,
        reason=fill_type,
    )
    pnl = fill.notional - fill.fee - position.entry_notional - position.entry_fees
    trades.append(
        V5ClosedTrade(
            trade_id=f"{fold_id}-T{len(trades) + 1:08d}",
            position_id=position.position_id,
            candidate_id=position.candidate_id,
            symbol=symbol,
            entry_time=position.entry_time,
            exit_time=timestamp,
            average_entry=position.average_entry,
            exit_price=price,
            quantity=position.quantity,
            realised_pnl=pnl,
            return_fraction=pnl / max(position.entry_notional + position.entry_fees, 1e-12),
            reason=fill_type,
            mae_r=position.mae_r,
            mfe_r=position.mfe_r,
            bars_held=position.bars_held,
            add_on_used=position.add_on_used,
            reentry_sequence=position.reentry_sequence,
            original_position_id=position.original_position_id,
        )
    )
    del positions[symbol]
    return cash


def _reject(candidate: V5SetupCandidate, counters: V5RejectionCounters, reason: str) -> None:
    candidate.accepted = False
    candidate.rejection_reason = reason
    counters.add(reason)


def _cluster_snapshot(
    daily_close: pd.DataFrame,
    symbols: Sequence[str],
    as_of: pd.Timestamp,
    cache: dict[pd.Timestamp, dict[str, str]],
) -> tuple[dict[str, str], pd.Timestamp, pd.Timestamp]:
    day = as_of.normalize()
    if day not in cache:
        cache[day] = _clusters_from_daily_close(daily_close, symbols, day)
    return cache[day], day - pd.Timedelta(days=CLUSTER_LOOKBACK_DAYS), day


def simulate_native_fold(
    *,
    four_hour_panel: pd.DataFrame,
    configuration: V5Parameters,
    portfolio_profile: V5PortfolioProfile,
    selected_threshold: int,
    transaction_cost: float,
    initial_capital: float = 100_000.0,
    fold_id: str = "FOLD",
    daily_panel: pd.DataFrame | None = None,
    eight_hour_panel: pd.DataFrame | None = None,
    availability: pd.DataFrame | None = None,
    allow_add_on: bool = True,
    allow_reentry: bool = True,
) -> V5FoldResult:
    """Run the single native event path used by tests, Shadow, and V5R1 trials."""
    del daily_panel, eight_hour_panel, availability
    if selected_threshold not in {50, 55}:
        raise V5NativeError("selected threshold must be 50 or 55")
    if transaction_cost < 0 or initial_capital <= 0:
        raise V5NativeError("invalid capital or transaction cost")
    assert_boundary(four_hour_panel)
    required = {
        "symbol",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "atr",
        "family",
        "score_no_fib",
        "score_soft_fib",
        "d1_score",
        "eight_hour_score",
        "four_hour_score",
        "fib",
        "tradable_from",
        "tradable_until",
    }
    missing = required - set(four_hour_panel.columns)
    if missing:
        raise V5NativeError(f"fold panel missing columns: {sorted(missing)}")
    frame = four_hour_panel.copy()
    for column in ("bar_open_time", "bar_close_time", "tradable_from", "tradable_until"):
        frame[column] = pd.to_datetime(frame[column], utc=True)
    frame = frame.sort_values(["bar_open_time", "symbol"], kind="mergesort").reset_index(drop=True)
    params = V5Parameters(
        configuration.configuration_id,
        configuration.family,
        configuration.stop_model,
        configuration.fibonacci_mode,
        selected_threshold,
        transaction_cost,
    )
    cash = initial_capital
    peak_equity = initial_capital
    positions: dict[str, V5OpenPosition] = {}
    pending: list[V5ScheduledEntry] = []
    pending_exits: dict[str, tuple[str, pd.Timestamp]] = {}
    candidate_by_id: dict[str, V5SetupCandidate] = {}
    candidates: list[V5SetupCandidate] = []
    scheduled_ledger: list[V5ScheduledEntry] = []
    fills: list[V5Fill] = []
    trades: list[V5ClosedTrade] = []
    equity_curve: list[tuple[pd.Timestamp, float]] = []
    rejections = V5RejectionCounters()
    reentry: dict[str, _ReentryState] = {}
    position_sequences: dict[str, int] = {}
    last_prices: dict[str, float] = {}
    symbols = sorted(str(value) for value in frame["symbol"].unique())
    cluster_key = _cluster_cache_key(frame)
    if cluster_key not in _DAILY_CLOSE_CACHE:
        _DAILY_CLOSE_CACHE[cluster_key] = (
            frame.set_index("bar_close_time")
            .groupby("symbol")["close"]
            .resample("1D")
            .last()
            .unstack(0)
        )
    daily_close = _DAILY_CLOSE_CACHE[cluster_key]
    cluster_cache = _CLUSTER_SNAPSHOT_CACHE.setdefault(cluster_key, {})

    records = frame.to_dict(orient="records")
    grouped = itertools.groupby(records, key=operator.itemgetter("bar_open_time"))
    for raw_bar_open, raw_rows in grouped:
        timestamp = pd.Timestamp(cast(Any, raw_bar_open))
        batch = list(raw_rows)
        rows: dict[str, Mapping[str, Any]] = {
            str(record["symbol"]): cast(dict[str, Any], record) for record in batch
        }
        for symbol, row in rows.items():
            last_prices[symbol] = float(row["open"])

        # Known venue boundaries are applied before any new activity.
        for symbol in sorted(list(positions)):
            if symbol not in rows:
                continue
            current_row = rows[symbol]
            if timestamp >= pd.Timestamp(current_row["tradable_until"]):
                cash = _close_position(
                    positions=positions,
                    symbol=symbol,
                    price=float(current_row["open"]),
                    timestamp=timestamp,
                    fill_type="VENUE_EXIT",
                    fee_rate=transaction_cost,
                    cash=cash,
                    fills=fills,
                    trades=trades,
                    fold_id=fold_id,
                )

        # Pending entries and add-ons execute at the actual next open.
        due = [item for item in pending if item.entry_time == timestamp]
        pending = [item for item in pending if item.entry_time != timestamp]
        due.sort(
            key=lambda item: (
                -candidate_by_id[item.candidate_id].score,
                -candidate_by_id[item.candidate_id].relative_strength,
                item.symbol,
            )
        )
        for scheduled in due:
            candidate = candidate_by_id[scheduled.candidate_id]
            if scheduled.symbol not in rows:
                _reject(candidate, rejections, "GAP_MISSING_NEXT_BAR")
                continue
            row = rows[scheduled.symbol]
            # Bar-close timestamps are exclusive and equal the next bar's open
            # timestamp; ordering is proven by the later bar_open, not by adding
            # an artificial epsilon to the exchange timestamp.
            if timestamp < candidate.signal_close or timestamp <= candidate.signal_open:
                raise V5NativeError("same-bar execution attempted")
            if not (
                timestamp >= pd.Timestamp(row["tradable_from"])
                and timestamp < pd.Timestamp(row["tradable_until"])
            ):
                _reject(candidate, rejections, "VENUE_UNAVAILABLE")
                continue
            open_price = float(row["open"])
            atr = float(row["atr"])
            distance = open_price - candidate.structural_stop_reference
            maximum_atr = (
                3.8
                if params.stop_model == "V4_T12_STRUCTURE"
                else (3.4 if params.stop_model == "STRUCTURE_BALANCED" else 4.0)
            )
            if scheduled.action != "ADD_ON" and distance <= 0:
                _reject(candidate, rejections, "GAP_INVALIDATED_STOP")
                continue
            if scheduled.action != "ADD_ON" and distance / atr > maximum_atr:
                _reject(candidate, rejections, "GAP_OVEREXTENSION")
                continue
            clusters, window_start, window_end = _cluster_snapshot(
                daily_close,
                symbols,
                timestamp,
                cluster_cache,
            )
            cluster_id = clusters.get(scheduled.symbol, scheduled.symbol)
            cluster_count = sum(
                clusters.get(symbol, symbol) == cluster_id for symbol in positions
            )
            candidate.cluster_id = cluster_id
            candidate.cluster_window_start = window_start
            candidate.cluster_window_end = window_end
            candidate.cluster_open_position_count = cluster_count
            candidate.cluster_limit = portfolio_profile.max_cluster
            current_heat = _heat(positions)
            current_equity = _equity(cash, positions, last_prices)
            peak_equity = max(peak_equity, current_equity)
            drawdown = max(0.0, 1.0 - current_equity / peak_equity)
            throttle = drawdown_multiplier(drawdown)

            if scheduled.action == "ADD_ON":
                if not allow_add_on:
                    _reject(candidate, rejections, "ADD_ON_DISABLED")
                    continue
                position = positions.get(scheduled.symbol)
                if position is None:
                    _reject(candidate, rejections, "ADD_ON_POSITION_CLOSED")
                    continue
                if position.add_on_used:
                    _reject(candidate, rejections, "ADD_ON_ALREADY_USED")
                    continue
                if open_price - position.average_entry < 1.25 * position.initial_risk_per_unit:
                    _reject(candidate, rejections, "ADD_ON_BELOW_1_25R")
                    continue
                if bool(row.get("overextended", False)):
                    _reject(candidate, rejections, "ADD_ON_OVEREXTENSION")
                    continue
                added_risk = position.risk_fraction * 0.25
                if position.total_risk_fraction + added_risk > portfolio_profile.max_position_risk:
                    _reject(candidate, rejections, "ADD_ON_POSITION_RISK_LIMIT")
                    continue
                if current_heat + added_risk > portfolio_profile.max_heat:
                    _reject(candidate, rejections, "ADD_ON_PORTFOLIO_HEAT")
                    continue
                if cluster_count > portfolio_profile.max_cluster:
                    _reject(candidate, rejections, "ADD_ON_CLUSTER_LIMIT")
                    continue
                quantity = position.initial_quantity * 0.25
                notional = quantity * open_price
                fee = notional * transaction_cost
                if notional + fee > cash + RECONCILIATION_TOLERANCE:
                    _reject(candidate, rejections, "ADD_ON_INSUFFICIENT_CASH")
                    continue
                before_quantity = position.quantity
                after_quantity = before_quantity + quantity
                cash, _ = _fill(
                    fills,
                    fold_id=fold_id,
                    candidate_id=candidate.candidate_id,
                    position_id=position.position_id,
                    symbol=scheduled.symbol,
                    timestamp=timestamp,
                    fill_type="ADD_ON",
                    price=open_price,
                    quantity=quantity,
                    fee_rate=transaction_cost,
                    cash=cash,
                    quantity_before=before_quantity,
                    quantity_after=after_quantity,
                    heat_before=current_heat,
                    heat_after=current_heat + added_risk,
                    reason="NEXT_BAR_OPEN_ADD_ON",
                )
                position.entry_notional += notional
                position.entry_fees += fee
                position.quantity = after_quantity
                position.average_entry = (
                    position.average_entry * before_quantity + open_price * quantity
                ) / after_quantity
                position.total_risk_fraction += added_risk
                position.add_on_used = True
                candidate.accepted = True
                continue

            if scheduled.symbol in positions:
                _reject(candidate, rejections, "EXISTING_POSITION")
                continue
            if len(positions) >= portfolio_profile.max_positions:
                _reject(candidate, rejections, "POSITION_LIMIT")
                continue
            if cluster_count >= portfolio_profile.max_cluster:
                _reject(candidate, rejections, "ENTRY_CLUSTER_LIMIT")
                continue
            requested_risk = min(
                portfolio_profile.max_initial_risk,
                portfolio_profile.base_risk * risk_multiplier(candidate.score) * throttle,
            )
            candidate.requested_risk = requested_risk
            if requested_risk <= 0:
                _reject(candidate, rejections, "DRAWDOWN_THROTTLE")
                continue
            if current_heat + requested_risk > portfolio_profile.max_heat:
                _reject(candidate, rejections, "PORTFOLIO_HEAT")
                continue
            quantity = min(
                current_equity * requested_risk / distance,
                cash / (open_price * (1.0 + transaction_cost)),
            )
            notional = quantity * open_price
            fee = notional * transaction_cost
            if quantity <= 0 or notional + fee > cash + RECONCILIATION_TOLERANCE:
                _reject(candidate, rejections, "INSUFFICIENT_CASH")
                continue
            position_sequences[scheduled.symbol] = position_sequences.get(scheduled.symbol, 0) + 1
            position_id = _position_id(
                params.configuration_id,
                fold_id,
                scheduled.symbol,
                position_sequences[scheduled.symbol],
            )
            cash, _ = _fill(
                fills,
                fold_id=fold_id,
                candidate_id=candidate.candidate_id,
                position_id=position_id,
                symbol=scheduled.symbol,
                timestamp=timestamp,
                fill_type="ENTRY",
                price=open_price,
                quantity=quantity,
                fee_rate=transaction_cost,
                cash=cash,
                quantity_before=0.0,
                quantity_after=quantity,
                heat_before=current_heat,
                heat_after=current_heat + requested_risk,
                reason=(
                    "NEXT_BAR_OPEN_REENTRY"
                    if scheduled.action == "REENTRY"
                    else "NEXT_BAR_OPEN_ENTRY"
                ),
            )
            positions[scheduled.symbol] = V5OpenPosition(
                position_id=position_id,
                candidate_id=candidate.candidate_id,
                symbol=scheduled.symbol,
                quantity=quantity,
                initial_quantity=quantity,
                average_entry=open_price,
                stop=candidate.structural_stop_reference,
                initial_stop=candidate.structural_stop_reference,
                initial_risk_per_unit=distance,
                risk_fraction=requested_risk,
                total_risk_fraction=requested_risk,
                entry_time=timestamp,
                entry_notional=notional,
                entry_fees=fee,
                reentry_sequence=candidate.reentry_sequence,
                original_position_id=candidate.original_position_id,
            )
            candidate.accepted = True
            if scheduled.action == "REENTRY" and scheduled.symbol in reentry:
                reentry[scheduled.symbol].used = True

        # Stops use the stop known before this bar.  New trailing levels apply later.
        for symbol in sorted(list(positions)):
            if symbol not in rows:
                continue
            stop_row = rows[symbol]
            position = positions[symbol]
            exit_price: float | None = None
            if float(stop_row["open"]) <= position.stop:
                exit_price = float(stop_row["open"])
            elif float(stop_row["low"]) <= position.stop:
                exit_price = position.stop
            if exit_price is not None:
                fill_type = "TRAILING_EXIT" if position.trailing_activated else "STOP_EXIT"
                stopped_position_id = position.position_id
                cash = _close_position(
                    positions=positions,
                    symbol=symbol,
                    price=exit_price,
                    timestamp=timestamp,
                    fill_type=fill_type,
                    fee_rate=transaction_cost,
                    cash=cash,
                    fills=fills,
                    trades=trades,
                    fold_id=fold_id,
                )
                if fill_type == "STOP_EXIT":
                    reentry[symbol] = _ReentryState(
                        stopped_position_id,
                        timestamp,
                        timestamp + pd.Timedelta(hours=8),
                        used=position.reentry_sequence >= 1,
                    )

        # Confirmed close-based exits were scheduled on the prior bar.
        for symbol, (fill_type, execution_time) in sorted(list(pending_exits.items())):
            if execution_time != timestamp or symbol not in positions:
                continue
            if symbol in rows:
                exit_row = rows[symbol]
                cash = _close_position(
                    positions=positions,
                    symbol=symbol,
                    price=float(exit_row["open"]),
                    timestamp=timestamp,
                    fill_type=fill_type,
                    fee_rate=transaction_cost,
                    cash=cash,
                    fills=fills,
                    trades=trades,
                    fold_id=fold_id,
                )
            del pending_exits[symbol]

        # Update excursions, then schedule exits and update trailing for future bars.
        for symbol in sorted(list(positions)):
            if symbol not in rows:
                continue
            position_row = rows[symbol]
            position = positions[symbol]
            position.bars_held += 1
            risk = max(position.initial_risk_per_unit, 1e-12)
            position.mfe_r = max(
                position.mfe_r,
                (float(position_row["high"]) - position.average_entry) / risk,
            )
            position.mae_r = min(
                position.mae_r,
                (float(position_row["low"]) - position.average_entry) / risk,
            )
            structure_failed = bool(position_row.get("structure_failure", False))
            position.consecutive_structure_failures = (
                position.consecutive_structure_failures + 1 if structure_failed else 0
            )
            if position.consecutive_structure_failures >= 2:
                pending_exits[symbol] = (
                    "STRUCTURE_EXIT",
                    pd.Timestamp(position_row["bar_close_time"]),
                )
                if symbol in reentry:
                    reentry[symbol].structural_invalidation = True
            stagnation = (
                position.bars_held >= 24
                and position.mfe_r < 0.75
                and bool(position_row.get("eight_hour_weak", False))
                and bool(position_row.get("conviction_declined", False))
                and not bool(position_row.get("new_bullish_structure", False))
            )
            if stagnation:
                pending_exits[symbol] = (
                    "STAGNATION_EXIT",
                    pd.Timestamp(position_row["bar_close_time"]),
                )
            higher_low_raw = position_row.get("higher_low", np.nan)
            higher_low = (
                float(higher_low_raw)
                if pd.notna(higher_low_raw) and float(higher_low_raw) > position.average_entry
                else None
            )
            new_stop, activation = trailing_stop(
                position.stop,
                position.average_entry,
                float(position_row["atr"]),
                position.mfe_r,
                higher_low,
                highest_price=position.average_entry
                + position.mfe_r * position.initial_risk_per_unit,
            )
            if activation is not None:
                position.trailing_activated = True
                position.trailing_activation_reason = (
                    position.trailing_activation_reason or activation
                )
                position.stop = max(position.stop, new_stop)

        close_prices = {symbol: float(row["close"]) for symbol, row in rows.items()}
        last_prices.update(close_prices)
        equity = _equity(cash, positions, last_prices)
        peak_equity = max(peak_equity, equity)
        close_time = max(pd.Timestamp(record["bar_close_time"]) for record in batch)
        equity_curve.append((close_time, equity))

        # Closed-bar signals create next-open work.  Nothing executes on this close.
        for symbol, row in rows.items():
            action: Literal["ENTRY", "ADD_ON", "REENTRY"] = "ENTRY"
            original_position_id: str | None = None
            reentry_sequence = 0
            if symbol in positions:
                action = "ADD_ON"
                original_position_id = positions[symbol].position_id
            elif symbol in reentry:
                state = reentry[symbol]
                if not allow_reentry:
                    continue
                if state.used:
                    action = "REENTRY"
                    reentry_sequence = 2
                elif close_time < state.earliest_signal_time:
                    probe = make_candidate(
                        row,
                        params,
                        fold_id,
                        action="REENTRY",
                        original_position_id=state.original_position_id,
                        reentry_sequence=1,
                    )
                    if probe is not None:
                        candidates.append(probe)
                        candidate_by_id[probe.candidate_id] = probe
                        _reject(probe, rejections, "REENTRY_COOLDOWN")
                    continue
                elif bool(row.get("crisis", False)) or state.structural_invalidation:
                    action = "REENTRY"
                    reentry_sequence = 1
                else:
                    action = "REENTRY"
                    original_position_id = state.original_position_id
                    reentry_sequence = 1
            new_candidate = make_candidate(
                row,
                params,
                fold_id,
                action=action,
                original_position_id=original_position_id,
                reentry_sequence=reentry_sequence,
            )
            if new_candidate is None:
                continue
            candidates.append(new_candidate)
            candidate_by_id[new_candidate.candidate_id] = new_candidate
            if new_candidate.score < selected_threshold:
                _reject(new_candidate, rejections, "BELOW_THRESHOLD")
                continue
            if bool(row.get("overextended", False)):
                _reject(new_candidate, rejections, "OVEREXTENSION")
                continue
            if action == "ADD_ON":
                position = positions[symbol]
                if position.add_on_used:
                    _reject(new_candidate, rejections, "ADD_ON_ALREADY_USED")
                    continue
                if float(row["close"]) - position.average_entry < (
                    1.25 * position.initial_risk_per_unit
                ):
                    _reject(new_candidate, rejections, "ADD_ON_BELOW_1_25R")
                    continue
            if action == "REENTRY":
                state = reentry[symbol]
                if state.used or reentry_sequence > 1:
                    _reject(new_candidate, rejections, "REENTRY_ALREADY_USED")
                    continue
                if bool(row.get("crisis", False)):
                    _reject(new_candidate, rejections, "REENTRY_CRISIS")
                    continue
                if state.structural_invalidation:
                    _reject(new_candidate, rejections, "REENTRY_STRUCTURAL_INVALIDATION")
                    continue
                if float(row["eight_hour_score"]) <= 0:
                    _reject(new_candidate, rejections, "REENTRY_INVALID_8H_TREND")
                    continue
            if close_time > pd.Timestamp(frame["bar_open_time"].max()):
                _reject(new_candidate, rejections, "FOLD_END_NO_NEXT_OPEN")
                continue
            scheduled = V5ScheduledEntry(
                new_candidate.candidate_id,
                symbol,
                close_time,
                action,
                original_position_id,
            )
            pending.append(scheduled)
            scheduled_ledger.append(scheduled)

    # Pending orders cannot cross the validation boundary.
    for scheduled in pending:
        candidate = candidate_by_id[scheduled.candidate_id]
        if candidate.rejection_reason is None and not candidate.accepted:
            _reject(candidate, rejections, "FOLD_END_PENDING_CANCELLED")

    # Every remaining position is liquidated with an explicit fill and fee.
    if not frame.empty:
        final_timestamp = pd.Timestamp(frame["bar_close_time"].max())
        final_rows = (
            frame.sort_values(["bar_close_time", "symbol"], kind="mergesort")
            .groupby("symbol", sort=False)
            .tail(1)
            .set_index("symbol")
        )
        for symbol in sorted(list(positions)):
            final_value = final_rows.at[symbol, "close"] if symbol in final_rows.index else None
            price = (
                float(cast(Any, final_value))
                if final_value is not None
                else last_prices[symbol]
            )
            cash = _close_position(
                positions=positions,
                symbol=symbol,
                price=price,
                timestamp=final_timestamp,
                fill_type="END_OF_FOLD_EXIT",
                fee_rate=transaction_cost,
                cash=cash,
                fills=fills,
                trades=trades,
                fold_id=fold_id,
            )
        equity_curve.append((final_timestamp, cash))

    fees = sum(fill.fee for fill in fills)
    turnover = sum(fill.notional for fill in fills)
    realised_pnl = sum(trade.realised_pnl for trade in trades)
    reconciliation = reconcile_native_fold_from_fills(
        fills,
        initial_capital=initial_capital,
        engine_final_cash=cash,
        engine_fees=fees,
        engine_turnover=turnover,
        engine_realised_pnl=realised_pnl,
    )
    status = "PASS" if reconciliation.status == "PASS" and not positions else "INVALID"
    return V5FoldResult(
        fold_id=fold_id,
        status=status,
        initial_capital=initial_capital,
        final_cash=cash,
        candidates=tuple(candidates),
        scheduled_entries=tuple(scheduled_ledger),
        fills=tuple(fills),
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
        rejections=dict(rejections.values),
        reconciliation=reconciliation,
        open_positions_after_fold=len(positions),
    )


def simulate_fold(
    frame: pd.DataFrame,
    params: V5Parameters,
    profile: V5PortfolioProfile,
    capital: float = 100_000.0,
) -> tuple[float, list[V5ClosedTrade], list[V5Fill], V5RejectionCounters]:
    """Compatibility wrapper around the one authoritative native Fold path."""
    result = simulate_native_fold(
        four_hour_panel=frame,
        configuration=params,
        portfolio_profile=profile,
        selected_threshold=params.threshold,
        transaction_cost=params.cost,
        initial_capital=capital,
    )
    return (
        result.final_cash,
        list(result.trades),
        list(result.fills),
        V5RejectionCounters(dict(result.rejections)),
    )


def result_as_json(result: V5FoldResult) -> dict[str, Any]:
    """Serialize a Fold result without NaN or pandas timestamp ambiguity."""

    def clean(value: Any) -> Any:
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {str(key): clean(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        if hasattr(value, "__dataclass_fields__"):
            return clean(asdict(value))
        if isinstance(value, np.generic):
            return value.item()
        return value

    return cast(dict[str, Any], clean(result))


__all__ = [
    "CLUSTER_LOOKBACK_DAYS",
    "RESEARCH_LOCK",
    "V5ClosedTrade",
    "V5Fill",
    "V5FoldResult",
    "V5NativeError",
    "V5OpenPosition",
    "V5Parameters",
    "V5PortfolioProfile",
    "V5ReconciliationResult",
    "V5ScheduledEntry",
    "V5SetupCandidate",
    "V5ThresholdSelection",
    "assert_boundary",
    "build_features",
    "choose_threshold",
    "configuration_grid",
    "correlation_clusters",
    "drawdown_multiplier",
    "make_candidate",
    "profiles",
    "reconcile_fills",
    "reconcile_native_fold_from_fills",
    "result_as_json",
    "risk_multiplier",
    "select_native_fold_threshold",
    "simulate_fold",
    "simulate_native_fold",
    "stop_distance",
    "trailing_stop",
]
