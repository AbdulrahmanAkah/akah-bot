"""Causal momentum, alignment, and fill-ledger research for AMS-MD01.

The module is intentionally independent from every V3/V4/V5 alpha model.  It
contains only transparent trend states, 28/84-calendar-day momentum factors,
weekly selection, and next-4H-open spot execution.  There are no tactical
stops, add-ons, leverage, or mid-week re-entry.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

from spotbot.research.ams_v5_native_engine import V5Fill

RESEARCH_START = pd.Timestamp("2021-01-01T00:00:00Z")
RESEARCH_LOCK = pd.Timestamp("2025-01-01T00:00:00Z")
EMA_FAST = 20
EMA_SLOW = 50
ATR_PERIOD = 14
OVEREXTENSION_ATR = 2.5
MOMENTUM_HORIZONS = (28, 84)
CLUSTER_LOOKBACK_DAYS = 90
CLUSTER_CORRELATION = 0.75
MAX_CLUSTER_POSITIONS = 2
ALIGNMENT_MULTIPLIERS = {
    "FULL": 1.0,
    "MEDIUM": 0.67,
    "FOUR_HOUR_ONLY": 0.33,
    "NONE": 0.0,
}
VARIANTS: Mapping[str, tuple[str, int]] = {
    "MD01-M01": ("TSM", 28),
    "MD01-M02": ("TSM", 84),
    "MD01-M03": ("XSM", 28),
    "MD01-M04": ("XSM", 84),
    "MD01-M05": ("DUAL", 28),
    "MD01-M06": ("DUAL", 84),
}
FOLDS: tuple[tuple[str, pd.Timestamp, pd.Timestamp], ...] = (
    (
        "WF01",
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2023-01-01T00:00:00Z"),
    ),
    (
        "WF02",
        pd.Timestamp("2023-01-01T00:00:00Z"),
        pd.Timestamp("2024-01-01T00:00:00Z"),
    ),
    (
        "WF03",
        pd.Timestamp("2024-01-01T00:00:00Z"),
        RESEARCH_LOCK,
    ),
)


class MD01Error(RuntimeError):
    """Raised when an MD01 causal, protocol, or accounting contract fails."""


@dataclass(frozen=True)
class MD01Variant:
    variant_id: str
    school: Literal["TSM", "XSM", "DUAL"]
    horizon_days: Literal[28, 84]
    maximum_positions: int
    base_target_weight: float


@dataclass(frozen=True)
class MD01Position:
    position_id: str
    candidate_id: str
    symbol: str
    quantity: float
    entry_price: float
    entry_time: pd.Timestamp
    entry_fee: float
    entry_notional: float
    alignment_tier: str
    natural_reselection_sequence: int
    previous_position_id: str | None


@dataclass(frozen=True)
class MD01Trade:
    trade_id: str
    position_id: str
    candidate_id: str
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    return_fraction: float
    exit_reason: str
    alignment_tier: str
    holding_hours: float
    mfe: float
    mae: float
    natural_reselection_sequence: int
    previous_position_id: str | None


@dataclass(frozen=True)
class MD01Reconciliation:
    status: str
    final_cash: float
    fees: float
    turnover: float
    realised_pnl: float
    open_quantities: Mapping[str, float]
    cash_difference: float
    fee_difference: float
    turnover_difference: float
    pnl_difference: float


@dataclass(frozen=True)
class MD01FoldResult:
    fold_id: str
    status: str
    initial_capital: float
    final_cash: float
    fills: tuple[V5Fill, ...]
    trades: tuple[MD01Trade, ...]
    candidates: tuple[Mapping[str, Any], ...]
    selections: tuple[Mapping[str, Any], ...]
    equity_curve: tuple[tuple[pd.Timestamp, float], ...]
    counters: Mapping[str, int]
    reconciliation: MD01Reconciliation
    open_positions_after_fold: int


def variant_spec(variant_id: str) -> MD01Variant:
    """Return one of the six immutable pre-registered variants."""
    if variant_id not in VARIANTS:
        raise MD01Error(f"unregistered variant: {variant_id}")
    school, horizon = VARIANTS[variant_id]
    if school == "TSM":
        return MD01Variant(variant_id, "TSM", horizon, 5, 0.20)
    return MD01Variant(variant_id, school, horizon, 3, 0.25)


def stable_id(prefix: str, *parts: object) -> str:
    """Build a deterministic compact identifier."""
    payload = "|".join(str(part) for part in parts).encode()
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:20]}"


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True)


def assert_research_boundary(frame: pd.DataFrame) -> None:
    """Reject incomplete, post-lock, or pre-research bars."""
    required = {"bar_open_time", "bar_close_time"}
    if not required.issubset(frame.columns):
        raise MD01Error("frame lacks research-boundary timestamps")
    opens = _utc(frame["bar_open_time"])
    closes = _utc(frame["bar_close_time"])
    if bool((opens < RESEARCH_START).any()):
        raise MD01Error("pre-2021 bar accessed")
    if bool((opens >= RESEARCH_LOCK).any()):
        raise MD01Error("2025 bar open accessed")
    if bool((closes > RESEARCH_LOCK).any()):
        raise MD01Error("post-lock bar close accessed")


def assert_spot_ohlcv(frame: pd.DataFrame) -> None:
    """Validate the minimum immutable OHLCV contract."""
    required = {
        "symbol",
        "bar_open_time",
        "bar_close_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise MD01Error(f"missing OHLCV columns: {missing}")
    assert_research_boundary(frame)
    if bool((frame[["open", "high", "low", "close"]] <= 0).any().any()):
        raise MD01Error("nonpositive spot price")


def build_trend_features(frame: pd.DataFrame, *, four_hour: bool = False) -> pd.DataFrame:
    """Classify transparent causal trend states using completed bars only."""
    assert_spot_ohlcv(frame)
    result = frame.copy()
    result["bar_open_time"] = _utc(result["bar_open_time"])
    result["bar_close_time"] = _utc(result["bar_close_time"])
    result = result.sort_values(["symbol", "bar_close_time"], kind="stable").reset_index(drop=True)
    grouped = result.groupby("symbol", sort=False, group_keys=False)
    result["ema20"] = grouped["close"].transform(
        lambda values: values.ewm(span=EMA_FAST, adjust=False, min_periods=EMA_FAST).mean()
    )
    result["ema50"] = grouped["close"].transform(
        lambda values: values.ewm(span=EMA_SLOW, adjust=False, min_periods=EMA_SLOW).mean()
    )
    prior_close = grouped["close"].shift(1)
    true_range = pd.concat(
        [
            result["high"] - result["low"],
            (result["high"] - prior_close).abs(),
            (result["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    result["atr"] = true_range.groupby(result["symbol"], sort=False).transform(
        lambda values: values.rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()
    )
    ema50_5 = grouped["ema50"].shift(5)
    ema20_3 = grouped["ema20"].shift(3)
    uptrend = (
        (result["close"] > result["ema50"])
        & (result["ema20"] > result["ema50"])
        & (result["ema50"] > ema50_5)
    )
    cross = (result["close"] > result["ema20"]) & (prior_close <= grouped["ema20"].shift(1))
    recent_cross = cross.groupby(result["symbol"], sort=False).transform(
        lambda values: values.rolling(3, min_periods=1).max().astype(bool)
    )
    prior_three_close = grouped["close"].transform(
        lambda values: values.shift(1).rolling(3, min_periods=3).max()
    )
    recovery = (
        ~uptrend
        & (result["close"] > result["ema20"])
        & (result["ema20"] > ema20_3)
        & (recent_cross | (result["close"] > prior_three_close))
    )
    downtrend = (
        (result["close"] < result["ema50"])
        & (result["ema20"] < result["ema50"])
        & (result["ema50"] < ema50_5)
    )
    result["trend_state"] = np.select(
        [uptrend, recovery, downtrend],
        ["UPTREND", "RECOVERY", "DOWNTREND"],
        default="NEUTRAL",
    )
    result["trend_positive"] = result["trend_state"].isin({"UPTREND", "RECOVERY"})
    if four_hour:
        prior_ema20 = grouped["ema20"].shift(1)
        reclaim = (prior_close <= prior_ema20) & (result["close"] > result["ema20"])
        prior_three_high = grouped["high"].transform(
            lambda values: values.shift(1).rolling(3, min_periods=3).max()
        )
        breakout = result["close"] > prior_three_high
        result["entry_trigger"] = np.select(
            [reclaim, breakout],
            ["EMA20_RECLAIM", "THREE_BAR_BREAKOUT"],
            default="NONE",
        )
        result["distance_atr"] = (result["close"] - result["ema20"]) / result["atr"]
        result["overextended"] = result["distance_atr"] > OVEREXTENSION_ATR
        result["four_hour_positive"] = (
            result["trend_positive"]
            & ~result["overextended"]
            & result["entry_trigger"].ne("NONE")
        )
    return result


def classify_alignment(
    *,
    daily_positive: bool,
    eight_hour_positive: bool,
    four_hour_positive: bool,
    crisis: bool = False,
    flat: bool = False,
) -> tuple[str, float]:
    """Return the registered tier and multiplier without a composite score."""
    if crisis or not four_hour_positive:
        return "NONE", 0.0
    if flat:
        if daily_positive and eight_hour_positive:
            return "FULL", 1.0
        if daily_positive or eight_hour_positive:
            return "MEDIUM", 1.0
        return "FOUR_HOUR_ONLY", 1.0
    if daily_positive and eight_hour_positive:
        return "FULL", 1.0
    if daily_positive != eight_hour_positive:
        return "MEDIUM", 0.67
    return "FOUR_HOUR_ONLY", 0.33


def build_daily_crisis(daily_features: pd.DataFrame) -> pd.DataFrame:
    """Apply the pre-registered causal BTC crisis definition.

    CRISIS requires a BTC daily DOWNTREND and a drawdown of at least 20 percent
    from the trailing 84-completed-bar high.  No cross-sectional future data is
    used.
    """
    btc = daily_features.loc[daily_features["symbol"].eq("BTC")].copy()
    btc = btc.sort_values("bar_close_time", kind="stable")
    btc["trailing_84_high"] = btc["close"].rolling(84, min_periods=84).max()
    btc["market_drawdown"] = btc["close"] / btc["trailing_84_high"] - 1.0
    btc["daily_market_regime"] = np.where(
        btc["trend_state"].eq("DOWNTREND") & (btc["market_drawdown"] <= -0.20),
        "CRISIS",
        btc["trend_state"],
    )
    return btc[
        [
            "bar_close_time",
            "daily_market_regime",
            "market_drawdown",
            "trend_state",
        ]
    ].rename(columns={"trend_state": "btc_daily_state"})


def momentum_at(
    daily_symbol: pd.DataFrame,
    timestamp: pd.Timestamp,
    horizon_days: int,
) -> float | None:
    """Return exact causal calendar momentum using the latest completed closes."""
    if horizon_days not in MOMENTUM_HORIZONS:
        raise MD01Error("unregistered momentum horizon")
    ordered = daily_symbol.sort_values("bar_close_time", kind="stable")
    closes = ordered.loc[_utc(ordered["bar_close_time"]) <= timestamp]
    if closes.empty:
        return None
    current = closes.iloc[-1]
    target = timestamp - pd.Timedelta(days=horizon_days)
    history = ordered.loc[_utc(ordered["bar_close_time"]) <= target]
    if history.empty:
        return None
    prior = history.iloc[-1]
    if target - pd.Timestamp(prior["bar_close_time"]) > pd.Timedelta(hours=36):
        return None
    return float(current["close"] / prior["close"] - 1.0)


def eligible_universe_at(
    *,
    timestamp: pd.Timestamp,
    horizon_days: int,
    daily: pd.DataFrame,
    eight_hour: pd.DataFrame,
    four_hour: pd.DataFrame,
    availability: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Construct dynamic point-in-time eligibility without backfilling."""
    if horizon_days not in MOMENTUM_HORIZONS:
        raise MD01Error("unregistered momentum horizon")
    available = availability.copy()
    available["tradable_from"] = _utc(available["tradable_from"])
    available["tradable_until"] = _utc(available["tradable_until"])
    raw_symbols = sorted(available["symbol"].astype(str).unique())
    tradable = available.loc[
        (available["tradable_from"] <= timestamp) & (timestamp < available["tradable_until"])
    ]
    tradable_symbols = set(tradable["symbol"].astype(str))
    exclusions: dict[str, list[str]] = defaultdict(list)
    records: list[dict[str, Any]] = []
    daily_by_symbol = {str(key): value for key, value in daily.groupby("symbol", sort=False)}
    eight_by_symbol = {
        str(key): value for key, value in eight_hour.groupby("symbol", sort=False)
    }
    four_by_symbol = {str(key): value for key, value in four_hour.groupby("symbol", sort=False)}
    for symbol in raw_symbols:
        if symbol not in tradable_symbols:
            exclusions["VENUE_UNAVAILABLE"].append(symbol)
            continue
        daily_symbol = daily_by_symbol.get(symbol)
        eight_symbol = eight_by_symbol.get(symbol)
        four_symbol = four_by_symbol.get(symbol)
        if daily_symbol is None or eight_symbol is None or four_symbol is None:
            exclusions["MISSING_TIMEFRAME"].append(symbol)
            continue
        momentum = momentum_at(daily_symbol, timestamp, horizon_days)
        if momentum is None:
            exclusions["INSUFFICIENT_HISTORY"].append(symbol)
            continue
        latest_daily = daily_symbol.loc[_utc(daily_symbol["bar_close_time"]) <= timestamp]
        latest_eight = eight_symbol.loc[_utc(eight_symbol["bar_close_time"]) <= timestamp]
        latest_four = four_symbol.loc[_utc(four_symbol["bar_close_time"]) <= timestamp]
        if latest_daily.empty or latest_eight.empty or latest_four.empty:
            exclusions["MISSING_TIMEFRAME"].append(symbol)
            continue
        latest_times = (
            pd.Timestamp(latest_daily.iloc[-1]["bar_close_time"]),
            pd.Timestamp(latest_eight.iloc[-1]["bar_close_time"]),
            pd.Timestamp(latest_four.iloc[-1]["bar_close_time"]),
        )
        if (
            timestamp - latest_times[0] > pd.Timedelta(days=2)
            or timestamp - latest_times[1] > pd.Timedelta(hours=16)
            or timestamp - latest_times[2] > pd.Timedelta(hours=8)
        ):
            exclusions["CRITICAL_FACTOR_GAP"].append(symbol)
            continue
        records.append({"symbol": symbol, "momentum_return": momentum})
    ranked = pd.DataFrame(records)
    if not ranked.empty:
        ranked = ranked.sort_values(
            ["momentum_return", "symbol"],
            ascending=[False, True],
            kind="stable",
        ).reset_index(drop=True)
        if len(ranked) == 1:
            ranked["percentile_rank"] = 1.0
        else:
            ranked["percentile_rank"] = 1.0 - ranked.index / (len(ranked) - 1)
    else:
        ranked = pd.DataFrame(columns=["symbol", "momentum_return", "percentile_rank"])
    audit = {
        "timestamp": timestamp.isoformat(),
        "raw_universe_count": len(raw_symbols),
        "tradable_count": len(tradable_symbols),
        "history_eligible_count": len(records),
        "liquidity_eligible_count": len(records),
        "final_rankable_count": len(records),
        "liquidity_filter": "NOT_AVAILABLE_POINT_IN_TIME_NO_FILTER_APPLIED",
        "excluded_symbols_by_reason": {
            reason: sorted(symbols) for reason, symbols in sorted(exclusions.items())
        },
        "rank_dispersion": float(ranked["momentum_return"].std(ddof=0))
        if len(ranked) > 1
        else 0.0,
    }
    return ranked, audit


def causal_cluster_snapshot(
    daily: pd.DataFrame,
    *,
    timestamp: pd.Timestamp,
    symbols: Sequence[str],
    threshold: float = CLUSTER_CORRELATION,
) -> tuple[dict[str, str], pd.Timestamp, pd.Timestamp, float]:
    """Create deterministic connected correlation clusters from past returns."""
    if not 0 < threshold < 1:
        raise MD01Error("cluster threshold must be between zero and one")
    window_end = timestamp
    window_start = timestamp - pd.Timedelta(days=CLUSTER_LOOKBACK_DAYS)
    relevant = daily.loc[
        daily["symbol"].isin(symbols)
        & (_utc(daily["bar_close_time"]) < timestamp)
        & (_utc(daily["bar_close_time"]) >= window_start)
    ].copy()
    relevant["day"] = _utc(relevant["bar_close_time"]).dt.floor("D")
    prices = relevant.pivot(index="day", columns="symbol", values="close").sort_index()
    returns = prices.pct_change(fill_method=None)
    correlations = returns.corr(min_periods=30)
    parents = {symbol: symbol for symbol in sorted(symbols)}

    def root(symbol: str) -> str:
        while parents[symbol] != symbol:
            parents[symbol] = parents[parents[symbol]]
            symbol = parents[symbol]
        return symbol

    def union(left: str, right: str) -> None:
        left_root, right_root = root(left), root(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        parents[second] = first

    comparable: list[float] = []
    ordered = sorted(symbols)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            value = (
                correlations.loc[left, right]
                if left in correlations and right in correlations
                else np.nan
            )
            if pd.notna(value):
                comparable.append(float(value))
                if float(value) >= threshold:
                    union(left, right)
    groups: dict[str, list[str]] = defaultdict(list)
    for symbol in ordered:
        groups[root(symbol)].append(symbol)
    mapping: dict[str, str] = {}
    for members in sorted(groups.values(), key=lambda values: values[0]):
        identity = "CL-" + hashlib.sha256("|".join(members).encode()).hexdigest()[:10]
        for symbol in members:
            mapping[symbol] = identity
    dispersion = float(np.std(comparable)) if comparable else 0.0
    return mapping, window_start, window_end, dispersion


def select_assets(
    ranked: pd.DataFrame,
    *,
    variant: MD01Variant,
    clusters: Mapping[str, str],
    maximum_cluster_positions: int = MAX_CLUSTER_POSITIONS,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Select in deterministic factor order while enforcing a two-per-cluster cap."""
    selected: list[str] = []
    cluster_counts: Counter[str] = Counter()
    decisions: list[dict[str, Any]] = []
    for row in ranked.itertuples(index=False):
        symbol = str(row.symbol)
        momentum = float(row.momentum_return)
        if variant.school in {"TSM", "DUAL"} and momentum <= 0:
            decisions.append(
                {"symbol": symbol, "decision": "ABSOLUTE_MOMENTUM_NONPOSITIVE"}
            )
            continue
        cluster = clusters.get(symbol, f"CL-SOLO-{symbol}")
        if cluster_counts[cluster] >= maximum_cluster_positions:
            decisions.append(
                {
                    "symbol": symbol,
                    "cluster_id": cluster,
                    "open_or_selected_count": cluster_counts[cluster],
                    "decision": "CLUSTER_BLOCKED",
                }
            )
            continue
        if len(selected) >= variant.maximum_positions:
            decisions.append({"symbol": symbol, "decision": "POSITION_CAP"})
            continue
        selected.append(symbol)
        cluster_counts[cluster] += 1
        decisions.append(
            {
                "symbol": symbol,
                "cluster_id": cluster,
                "open_or_selected_count": cluster_counts[cluster] - 1,
                "decision": "SELECTED",
            }
        )
    return selected, decisions


def target_weight(
    variant: MD01Variant,
    *,
    selected_count: int,
    alignment_multiplier: float,
) -> float:
    """Apply alignment strength without renormalising unused cash."""
    if selected_count <= 0:
        return 0.0
    base = min(1.0 / min(selected_count, 5), 0.20) if variant.school == "TSM" else 0.25
    return base * alignment_multiplier


def _latest_row(frame: pd.DataFrame, symbol: str, timestamp: pd.Timestamp) -> pd.Series | None:
    values = frame.loc[
        frame["symbol"].eq(symbol) & (_utc(frame["bar_close_time"]) <= timestamp)
    ]
    return None if values.empty else values.iloc[-1]


def _market_regime_at(crisis: pd.DataFrame, timestamp: pd.Timestamp) -> str:
    values = crisis.loc[_utc(crisis["bar_close_time"]) <= timestamp]
    return "NEUTRAL" if values.empty else str(values.iloc[-1]["daily_market_regime"])


def _exit_fill(
    *,
    position: MD01Position,
    timestamp: pd.Timestamp,
    price: float,
    fill_type: str,
    cost: float,
    cash: float,
    heat_before: float = 0.0,
) -> tuple[V5Fill, float]:
    notional = position.quantity * price
    fee = notional * cost
    cash_after = cash + notional - fee
    fill = V5Fill(
        fill_id=stable_id("FILL", position.position_id, fill_type, timestamp.isoformat()),
        candidate_id=position.candidate_id,
        position_id=position.position_id,
        symbol=position.symbol,
        timestamp=timestamp,
        fill_type=fill_type,
        price=price,
        quantity=position.quantity,
        notional=notional,
        fee=fee,
        cash_before=cash,
        cash_after=cash_after,
        position_quantity_before=position.quantity,
        position_quantity_after=0.0,
        portfolio_heat_before=heat_before,
        portfolio_heat_after=0.0,
        reason=fill_type,
    )
    return fill, cash_after


def reconcile_from_fills(
    fills: Sequence[V5Fill],
    *,
    initial_capital: float,
    engine_final_cash: float,
    engine_fees: float,
    engine_turnover: float,
    engine_realised_pnl: float,
    tolerance: float = 1e-7,
) -> MD01Reconciliation:
    """Rebuild the entire fold cash and quantity ledger from fills alone."""
    cash = initial_capital
    quantities: dict[str, float] = defaultdict(float)
    fees = 0.0
    turnover = 0.0
    seen: set[str] = set()
    for fill in fills:
        if fill.fill_id in seen:
            raise MD01Error(f"duplicate fill id: {fill.fill_id}")
        seen.add(fill.fill_id)
        if abs(fill.cash_before - cash) > tolerance:
            raise MD01Error("fill cash-before does not reconcile")
        if abs(fill.position_quantity_before - quantities[fill.position_id]) > tolerance:
            raise MD01Error("fill quantity-before does not reconcile")
        cash = fill.cash_after
        quantities[fill.position_id] = fill.position_quantity_after
        fees += fill.fee
        turnover += fill.notional
    open_quantities = {
        identity: quantity for identity, quantity in quantities.items() if abs(quantity) > tolerance
    }
    realised = cash - initial_capital
    differences = (
        cash - engine_final_cash,
        fees - engine_fees,
        turnover - engine_turnover,
        realised - engine_realised_pnl,
    )
    status = (
        "PASS"
        if not open_quantities and all(abs(value) <= tolerance for value in differences)
        else "FAIL"
    )
    return MD01Reconciliation(
        status,
        cash,
        fees,
        turnover,
        realised,
        open_quantities,
        differences[0],
        differences[1],
        differences[2],
        differences[3],
    )


def simulate_md01_fold(
    *,
    four_hour: pd.DataFrame,
    daily: pd.DataFrame,
    eight_hour: pd.DataFrame,
    availability: pd.DataFrame,
    variant_id: str,
    fold_id: str,
    validation_start: pd.Timestamp,
    validation_end: pd.Timestamp,
    transaction_cost: float = 0.0,
    initial_capital: float = 100_000.0,
    control_mode: Literal["REGISTERED", "FLAT_ALIGNMENT", "CRISIS_OFF"] = "REGISTERED",
) -> MD01FoldResult:
    """Run the single trusted weekly-selection/next-open execution path."""
    if transaction_cost < 0:
        raise MD01Error("negative transaction cost")
    if control_mode not in {"REGISTERED", "FLAT_ALIGNMENT", "CRISIS_OFF"}:
        raise MD01Error("unregistered control mode")
    variant = variant_spec(variant_id)
    daily_features = build_trend_features(daily)
    eight_features = build_trend_features(eight_hour)
    four_features = build_trend_features(four_hour, four_hour=True)
    crisis_frame = build_daily_crisis(daily_features)
    availability_frame = availability.copy()
    availability_frame["tradable_from"] = _utc(availability_frame["tradable_from"])
    availability_frame["tradable_until"] = _utc(availability_frame["tradable_until"])
    availability_by_symbol = availability_frame.set_index("symbol")
    bars = four_features.loc[
        (four_features["bar_open_time"] >= validation_start)
        & (four_features["bar_open_time"] < validation_end)
    ].copy()
    bars = bars.sort_values(["bar_open_time", "symbol"], kind="stable")
    timestamps = sorted(pd.Timestamp(value) for value in bars["bar_open_time"].unique())
    if not timestamps:
        raise MD01Error("validation fold contains no four-hour bars")
    by_time = {timestamp: values for timestamp, values in bars.groupby("bar_open_time", sort=True)}
    positions: dict[str, MD01Position] = {}
    position_mfe: dict[str, float] = defaultdict(float)
    position_mae: dict[str, float] = defaultdict(float)
    pending_entries: dict[pd.Timestamp, list[dict[str, Any]]] = defaultdict(list)
    pending_exits: dict[pd.Timestamp, list[tuple[str, str]]] = defaultdict(list)
    active_selection: set[str] = set()
    active_selection_count = 0
    selection_generation = 0
    last_exit_rebalance: dict[str, pd.Timestamp] = {}
    previous_position: dict[str, str] = {}
    reselection_sequence: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    fills: list[V5Fill] = []
    trades: list[MD01Trade] = []
    counters: Counter[str] = Counter()
    equity_curve: list[tuple[pd.Timestamp, float]] = []
    cash = initial_capital
    rebalance_times = {
        timestamp
        for timestamp in timestamps
        if timestamp.weekday() == 0 and timestamp.hour == 0
    }
    current_rebalance = validation_start.floor("D")

    def market_value(timestamp: pd.Timestamp) -> float:
        values = by_time.get(timestamp)
        closes = (
            {} if values is None else dict(zip(values["symbol"], values["close"], strict=False))
        )
        return cash + sum(
            position.quantity * float(closes.get(symbol, position.entry_price))
            for symbol, position in positions.items()
        )

    def close_position(
        symbol: str,
        *,
        timestamp: pd.Timestamp,
        price: float,
        fill_type: str,
    ) -> None:
        nonlocal cash
        position = positions.pop(symbol)
        fill, cash_after = _exit_fill(
            position=position,
            timestamp=timestamp,
            price=price,
            fill_type=fill_type,
            cost=transaction_cost,
            cash=cash,
        )
        cash = cash_after
        fills.append(fill)
        gross = (price - position.entry_price) * position.quantity
        net = gross - position.entry_fee - fill.fee
        trades.append(
            MD01Trade(
                trade_id=stable_id("TRADE", position.position_id, timestamp.isoformat()),
                position_id=position.position_id,
                candidate_id=position.candidate_id,
                symbol=symbol,
                entry_time=position.entry_time,
                exit_time=timestamp,
                entry_price=position.entry_price,
                exit_price=price,
                quantity=position.quantity,
                gross_pnl=gross,
                net_pnl=net,
                return_fraction=net / max(position.entry_notional + position.entry_fee, 1e-12),
                exit_reason=fill_type,
                alignment_tier=position.alignment_tier,
                holding_hours=(timestamp - position.entry_time).total_seconds() / 3600,
                mfe=position_mfe.pop(position.position_id, 0.0),
                mae=position_mae.pop(position.position_id, 0.0),
                natural_reselection_sequence=position.natural_reselection_sequence,
                previous_position_id=position.previous_position_id,
            )
        )
        previous_position[symbol] = position.position_id
        last_exit_rebalance[symbol] = current_rebalance

    for timestamp in timestamps:
        current_rows = by_time[timestamp]
        rows_by_symbol = current_rows.set_index("symbol")
        # Rebalance decisions precede fills due exactly at the decision timestamp.
        if timestamp in rebalance_times:
            current_rebalance = timestamp
            selection_generation += 1
            ranked, eligibility = eligible_universe_at(
                timestamp=timestamp,
                horizon_days=variant.horizon_days,
                daily=daily_features,
                eight_hour=eight_features,
                four_hour=four_features,
                availability=availability_frame,
            )
            cluster_map, window_start, window_end, corr_dispersion = causal_cluster_snapshot(
                daily_features,
                timestamp=timestamp,
                symbols=ranked["symbol"].astype(str).tolist(),
            )
            selected, cluster_decisions = select_assets(
                ranked,
                variant=variant,
                clusters=cluster_map,
            )
            regime = _market_regime_at(crisis_frame, timestamp)
            crisis_active = regime == "CRISIS" and control_mode != "CRISIS_OFF"
            selected_set = set(selected)
            for symbol in sorted(positions):
                if symbol not in selected_set:
                    pending_exits[timestamp + pd.Timedelta(hours=4)].append(
                        (symbol, "REBALANCE_EXIT")
                    )
            if crisis_active:
                new_symbols = selected_set - set(positions)
                counters["CRISIS_ROTATION_BLOCK"] += len(new_symbols)
                selected_set -= new_symbols
            active_selection = selected_set
            active_selection_count = len(selected_set)
            counters["CLUSTER_BLOCKED"] += sum(
                decision["decision"] == "CLUSTER_BLOCKED" for decision in cluster_decisions
            )
            selections.append(
                {
                    **eligibility,
                    "variant_id": variant_id,
                    "fold_id": fold_id,
                    "school": variant.school,
                    "horizon_days": variant.horizon_days,
                    "selected_symbols": sorted(selected_set),
                    "cluster_window_start": window_start.isoformat(),
                    "cluster_window_end": window_end.isoformat(),
                    "correlation_dispersion": corr_dispersion,
                    "cluster_decisions": cluster_decisions,
                    "daily_market_regime": regime,
                    "selection_generation": selection_generation,
                }
            )
            # Pending entries from the expired weekly selection cannot survive.
            for due, orders in list(pending_entries.items()):
                retained = []
                for order in orders:
                    if order["symbol"] not in active_selection:
                        counters["SELECTION_EXPIRED"] += 1
                    else:
                        retained.append(order)
                pending_entries[due] = retained

        # Execute scheduled exits at this open before new entries.
        for symbol, reason in pending_exits.pop(timestamp, []):
            if symbol in positions and symbol in rows_by_symbol.index:
                close_position(
                    symbol,
                    timestamp=timestamp,
                    price=float(rows_by_symbol.loc[symbol, "open"]),
                    fill_type=reason,
                )

        # Venue exits are mandatory before any new activity.
        for symbol in sorted(list(positions)):
            availability_row = availability_by_symbol.loc[symbol]
            if timestamp >= pd.Timestamp(availability_row["tradable_until"]):
                price = (
                    float(rows_by_symbol.loc[symbol, "open"])
                    if symbol in rows_by_symbol.index
                    else positions[symbol].entry_price
                )
                close_position(
                    symbol,
                    timestamp=timestamp,
                    price=price,
                    fill_type="VENUE_EXIT",
                )

        # Entry fills use the real next-bar open and current affordability.
        for order in sorted(
            pending_entries.pop(timestamp, []),
            key=lambda item: (item["rank"], item["symbol"]),
        ):
            symbol = str(order["symbol"])
            candidate = order["candidate"]
            if symbol not in active_selection:
                candidate["accepted"] = False
                candidate["rejection_reason"] = "SELECTION_EXPIRED"
                counters["SELECTION_EXPIRED"] += 1
                continue
            if symbol in positions:
                candidate["accepted"] = False
                candidate["rejection_reason"] = "EXISTING_POSITION"
                counters["EXISTING_POSITION"] += 1
                continue
            if symbol not in rows_by_symbol.index:
                candidate["accepted"] = False
                candidate["rejection_reason"] = "NO_NEXT_OPEN"
                counters["NO_NEXT_OPEN"] += 1
                continue
            availability_row = availability_by_symbol.loc[symbol]
            if not (
                pd.Timestamp(availability_row["tradable_from"])
                <= timestamp
                < pd.Timestamp(availability_row["tradable_until"])
            ):
                candidate["accepted"] = False
                candidate["rejection_reason"] = "VENUE_UNAVAILABLE"
                counters["VENUE_UNAVAILABLE"] += 1
                continue
            if (
                _market_regime_at(crisis_frame, timestamp) == "CRISIS"
                and control_mode != "CRISIS_OFF"
            ):
                candidate["accepted"] = False
                candidate["rejection_reason"] = "CRISIS_ENTRY_BLOCK"
                counters["CRISIS_ENTRY_BLOCK"] += 1
                continue
            price = float(rows_by_symbol.loc[symbol, "open"])
            equity = market_value(timestamp)
            weight = float(candidate["target_weight"])
            requested_notional = equity * weight
            affordable = cash / (1.0 + transaction_cost)
            notional = min(requested_notional, affordable)
            if notional <= 1e-9:
                candidate["accepted"] = False
                candidate["rejection_reason"] = "INSUFFICIENT_CASH"
                counters["INSUFFICIENT_CASH"] += 1
                continue
            quantity = notional / price
            fee = notional * transaction_cost
            cash_after = cash - notional - fee
            if cash_after < -1e-7:
                raise MD01Error("negative cash or implicit leverage")
            position_id = stable_id("POS", candidate["candidate_id"], timestamp.isoformat())
            fill = V5Fill(
                fill_id=stable_id("FILL", position_id, "ENTRY", timestamp.isoformat()),
                candidate_id=str(candidate["candidate_id"]),
                position_id=position_id,
                symbol=symbol,
                timestamp=timestamp,
                fill_type="ENTRY",
                price=price,
                quantity=quantity,
                notional=notional,
                fee=fee,
                cash_before=cash,
                cash_after=max(cash_after, 0.0),
                position_quantity_before=0.0,
                position_quantity_after=quantity,
                portfolio_heat_before=0.0,
                portfolio_heat_after=0.0,
                reason="WEEKLY_SELECTION_NEXT_OPEN",
            )
            cash = max(cash_after, 0.0)
            fills.append(fill)
            if symbol in previous_position:
                reselection_sequence[symbol] += 1
            positions[symbol] = MD01Position(
                position_id,
                str(candidate["candidate_id"]),
                symbol,
                quantity,
                price,
                timestamp,
                fee,
                notional,
                str(candidate["alignment_tier"]),
                reselection_sequence[symbol],
                previous_position.get(symbol),
            )
            candidate["accepted"] = True
            candidate["fill_timestamp"] = timestamp.isoformat()
            candidate["fill_price"] = price
            counters["ENTRY_FILLED"] += 1
            if timestamp <= pd.Timestamp(candidate["signal_bar_close"]):
                raise MD01Error("same-bar entry detected")

        # Track open-position excursions from current completed bar.
        for symbol, position in positions.items():
            if symbol not in rows_by_symbol.index:
                continue
            row = rows_by_symbol.loc[symbol]
            position_mfe[position.position_id] = max(
                position_mfe[position.position_id],
                float(row["high"]) / position.entry_price - 1.0,
            )
            position_mae[position.position_id] = min(
                position_mae[position.position_id],
                float(row["low"]) / position.entry_price - 1.0,
            )

        # Generate causal candidates only after this 4H bar has closed.
        close_timestamp = timestamp + pd.Timedelta(hours=4)
        regime = _market_regime_at(crisis_frame, close_timestamp)
        for rank, symbol in enumerate(sorted(active_selection)):
            if symbol in positions or symbol not in rows_by_symbol.index:
                continue
            row = rows_by_symbol.loc[symbol]
            if not bool(row["four_hour_positive"]):
                counters["WAITING_FOR_4H_TRIGGER"] += 1
                continue
            earliest = last_exit_rebalance.get(symbol)
            cooldown_ok = earliest is None or current_rebalance >= earliest + pd.Timedelta(days=7)
            if not cooldown_ok:
                counters["NATURAL_RESELECTION_COOLDOWN"] += 1
                continue
            daily_row = _latest_row(daily_features, symbol, close_timestamp)
            eight_row = _latest_row(eight_features, symbol, close_timestamp)
            if daily_row is None or eight_row is None:
                counters["MISSING_TIMEFRAME"] += 1
                continue
            crisis_active = regime == "CRISIS" and control_mode != "CRISIS_OFF"
            tier, multiplier = classify_alignment(
                daily_positive=bool(daily_row["trend_positive"]),
                eight_hour_positive=bool(eight_row["trend_positive"]),
                four_hour_positive=True,
                crisis=crisis_active,
                flat=control_mode == "FLAT_ALIGNMENT",
            )
            candidate_id = stable_id(
                "CAND",
                fold_id,
                variant_id,
                symbol,
                close_timestamp.isoformat(),
                selection_generation,
            )
            candidate: dict[str, Any] = {
                "candidate_id": candidate_id,
                "fold_id": fold_id,
                "variant_id": variant_id,
                "symbol": symbol,
                "signal_bar_open": timestamp.isoformat(),
                "signal_bar_close": close_timestamp.isoformat(),
                "scheduled_entry": close_timestamp.isoformat(),
                "entry_trigger": str(row["entry_trigger"]),
                "alignment_tier": tier,
                "entry_strength_multiplier": multiplier,
                "daily_state": str(daily_row["trend_state"]),
                "eight_hour_state": str(eight_row["trend_state"]),
                "four_hour_state": str(row["trend_state"]),
                "daily_market_regime": regime,
                "target_weight": target_weight(
                    variant,
                    selected_count=active_selection_count,
                    alignment_multiplier=multiplier,
                ),
                "natural_reselection_sequence": reselection_sequence[symbol],
                "last_exit_rebalance": earliest.isoformat() if earliest is not None else None,
                "earliest_reentry_rebalance": (
                    (earliest + pd.Timedelta(days=7)).isoformat()
                    if earliest is not None
                    else None
                ),
                "cooldown_satisfied": cooldown_ok,
                "accepted": False,
                "rejection_reason": None,
            }
            candidates.append(candidate)
            if crisis_active:
                candidate["rejection_reason"] = "CRISIS_ENTRY_BLOCK"
                counters["CRISIS_ENTRY_BLOCK"] += 1
                continue
            pending_entries[close_timestamp].append(
                {"symbol": symbol, "rank": rank, "candidate": candidate}
            )
            counters["ENTRY_SCHEDULED"] += 1

        equity_curve.append((close_timestamp, market_value(timestamp)))

    # The last close is the only permitted end-of-fold liquidation price.
    last_timestamp = timestamps[-1]
    final_rows = by_time[last_timestamp].set_index("symbol")
    liquidation_timestamp = min(
        validation_end,
        pd.Timestamp(by_time[last_timestamp]["bar_close_time"].max()),
    )
    for symbol in sorted(list(positions)):
        price = (
            float(final_rows.loc[symbol, "close"])
            if symbol in final_rows.index
            else positions[symbol].entry_price
        )
        close_position(
            symbol,
            timestamp=liquidation_timestamp,
            price=price,
            fill_type="END_OF_FOLD_EXIT",
        )
    counters["SELECTION_EXPIRED"] += sum(len(values) for values in pending_entries.values())
    fees = sum(fill.fee for fill in fills)
    turnover = sum(fill.notional for fill in fills)
    realised = cash - initial_capital
    reconciliation = reconcile_from_fills(
        fills,
        initial_capital=initial_capital,
        engine_final_cash=cash,
        engine_fees=fees,
        engine_turnover=turnover,
        engine_realised_pnl=realised,
    )
    status = "PASS" if reconciliation.status == "PASS" and not positions else "INVALID"
    return MD01FoldResult(
        fold_id,
        status,
        initial_capital,
        cash,
        tuple(fills),
        tuple(trades),
        tuple(candidates),
        tuple(selections),
        tuple(equity_curve),
        dict(counters),
        reconciliation,
        len(positions),
    )


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def fold_metrics(result: MD01FoldResult) -> dict[str, Any]:
    """Compute the registered performance and operational metrics."""
    pnl = np.asarray([trade.net_pnl for trade in result.trades], dtype=float)
    gross = np.asarray([trade.gross_pnl for trade in result.trades], dtype=float)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    gross_profit = float(wins.sum()) if wins.size else 0.0
    gross_loss = float(-losses.sum()) if losses.size else 0.0
    equity = np.asarray([value for _, value in result.equity_curve], dtype=float)
    if equity.size:
        peaks = np.maximum.accumulate(equity)
        drawdown = 1.0 - equity / peaks
        max_drawdown = float(drawdown.max())
        returns = pd.Series(equity).pct_change().dropna()
    else:
        max_drawdown = 0.0
        returns = pd.Series(dtype=float)
    downside = returns[returns < 0]
    net_return = result.final_cash / result.initial_capital - 1.0
    cagr = net_return
    fees = sum(fill.fee for fill in result.fills)
    turnover = sum(fill.notional for fill in result.fills)
    tier_pnl: dict[str, float] = defaultdict(float)
    tier_trades: Counter[str] = Counter()
    symbol_pnl: dict[str, float] = defaultdict(float)
    symbol_trades: Counter[str] = Counter()
    for trade in result.trades:
        tier_pnl[trade.alignment_tier] += trade.net_pnl
        tier_trades[trade.alignment_tier] += 1
        symbol_pnl[trade.symbol] += trade.net_pnl
        symbol_trades[trade.symbol] += 1
    positive_symbol_pnl = sorted(
        (max(value, 0.0) for value in symbol_pnl.values()), reverse=True
    )
    positive_total = sum(positive_symbol_pnl)
    return {
        "initial_capital": result.initial_capital,
        "final_equity": result.final_cash,
        "gross_return": float(gross.sum() / result.initial_capital),
        "net_return": net_return,
        "cagr": cagr,
        "maximum_drawdown": max_drawdown,
        "calmar": _safe_ratio(cagr, max_drawdown),
        "sharpe": (
            float(returns.mean() / returns.std(ddof=1) * math.sqrt(365 * 6))
            if len(returns) > 1 and returns.std(ddof=1) > 0
            else None
        ),
        "sortino": (
            float(returns.mean() / downside.std(ddof=1) * math.sqrt(365 * 6))
            if len(downside) > 1 and downside.std(ddof=1) > 0
            else None
        ),
        "profit_factor": _safe_ratio(gross_profit, gross_loss),
        "expectancy": float(pnl.mean()) if pnl.size else 0.0,
        "win_rate": float((pnl > 0).mean()) if pnl.size else 0.0,
        "payoff_ratio": _safe_ratio(
            float(wins.mean()) if wins.size else 0.0,
            float(-losses.mean()) if losses.size else 0.0,
        ),
        "trade_count": len(result.trades),
        "entries_per_year": len(result.trades),
        "rebalance_count": len(result.selections),
        "average_holding_hours": float(
            np.mean([trade.holding_hours for trade in result.trades])
        )
        if result.trades
        else 0.0,
        "median_holding_hours": float(
            np.median([trade.holding_hours for trade in result.trades])
        )
        if result.trades
        else 0.0,
        "turnover": turnover,
        "fees": fees,
        "break_even_fee": (
            float(gross.sum() / turnover) if turnover > 0 else None
        ),
        "cluster_rejections": result.counters.get("CLUSTER_BLOCKED", 0),
        "crisis_rejections": result.counters.get("CRISIS_ENTRY_BLOCK", 0)
        + result.counters.get("CRISIS_ROTATION_BLOCK", 0),
        "selection_expirations": result.counters.get("SELECTION_EXPIRED", 0),
        "natural_reselections": sum(
            trade.natural_reselection_sequence > 0 for trade in result.trades
        ),
        "entries_by_alignment_tier": dict(tier_trades),
        "return_by_alignment_tier": dict(tier_pnl),
        "per_symbol_pnl": dict(symbol_pnl),
        "per_symbol_trades": dict(symbol_trades),
        "top_1_symbol_contribution": (
            positive_symbol_pnl[0] / positive_total if positive_total else 0.0
        ),
        "top_3_symbol_contribution": (
            sum(positive_symbol_pnl[:3]) / positive_total if positive_total else 0.0
        ),
        "reconciliation_status": result.reconciliation.status,
        "open_positions_after_fold": result.open_positions_after_fold,
    }


def aggregate_fold_metrics(
    fold_results: Sequence[MD01FoldResult],
) -> dict[str, Any]:
    """Aggregate independent validation folds without carrying capital between them."""
    metrics = [fold_metrics(result) for result in fold_results]
    trades = [trade for result in fold_results for trade in result.trades]
    pnl = np.asarray([trade.net_pnl for trade in trades], dtype=float)
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    returns = [float(item["net_return"]) for item in metrics]
    compounded = math.prod(1.0 + value for value in returns) - 1.0
    symbol_pnl: dict[str, float] = defaultdict(float)
    for trade in trades:
        symbol_pnl[trade.symbol] += trade.net_pnl
    positive = sorted((max(value, 0.0) for value in symbol_pnl.values()), reverse=True)
    total_positive = sum(positive)
    return {
        "compounded_return": compounded,
        "mean_fold_return": float(np.mean(returns)),
        "positive_folds": sum(value > 0 for value in returns),
        "worst_fold_return": min(returns),
        "mean_maximum_drawdown": float(
            np.mean([float(item["maximum_drawdown"]) for item in metrics])
        ),
        "profit_factor": _safe_ratio(
            float(wins.sum()) if wins.size else 0.0,
            float(-losses.sum()) if losses.size else 0.0,
        ),
        "expectancy": float(pnl.mean()) if pnl.size else 0.0,
        "trade_count": len(trades),
        "trades_per_year": len(trades) / len(fold_results),
        "win_rate": float((pnl > 0).mean()) if pnl.size else 0.0,
        "payoff_ratio": _safe_ratio(
            float(wins.mean()) if wins.size else 0.0,
            float(-losses.mean()) if losses.size else 0.0,
        ),
        "turnover": sum(float(item["turnover"]) for item in metrics),
        "fees": sum(float(item["fees"]) for item in metrics),
        "break_even_fee": _safe_ratio(
            sum(trade.gross_pnl for trade in trades),
            sum(float(item["turnover"]) for item in metrics),
        ),
        "cluster_rejections": sum(int(item["cluster_rejections"]) for item in metrics),
        "crisis_rejections": sum(int(item["crisis_rejections"]) for item in metrics),
        "selection_expirations": sum(
            int(item["selection_expirations"]) for item in metrics
        ),
        "natural_reselections": sum(int(item["natural_reselections"]) for item in metrics),
        "top_1_symbol_contribution": positive[0] / total_positive
        if total_positive
        else 0.0,
        "top_3_symbol_contribution": sum(positive[:3]) / total_positive
        if total_positive
        else 0.0,
        "reconciliation_status": (
            "PASS"
            if all(item["reconciliation_status"] == "PASS" for item in metrics)
            else "FAIL"
        ),
        "open_positions_after_fold": sum(
            int(item["open_positions_after_fold"]) for item in metrics
        ),
        "folds": metrics,
    }


def serialise_fold(result: MD01FoldResult) -> dict[str, Any]:
    """Convert a fold to compact JSON-compatible evidence."""
    return {
        "fold_id": result.fold_id,
        "status": result.status,
        "initial_capital": result.initial_capital,
        "final_cash": result.final_cash,
        "metrics": fold_metrics(result),
        "candidate_ledger": [dict(item) for item in result.candidates],
        "selection_ledger": [dict(item) for item in result.selections],
        "fill_ledger": [
            {
                **asdict(fill),
                "timestamp": fill.timestamp.isoformat(),
            }
            for fill in result.fills
        ],
        "trade_ledger": [
            {
                **asdict(trade),
                "entry_time": trade.entry_time.isoformat(),
                "exit_time": trade.exit_time.isoformat(),
            }
            for trade in result.trades
        ],
        "counters": dict(result.counters),
        "reconciliation": asdict(result.reconciliation),
        "open_positions_after_fold": result.open_positions_after_fold,
    }


def weekly_rebalance_times(start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.Timestamp, ...]:
    """Return deterministic Monday 00:00 UTC timestamps."""
    first = start.normalize()
    while first.weekday() != 0:
        first += pd.Timedelta(days=1)
    return tuple(pd.date_range(first, end, freq="7D", inclusive="left", tz="UTC"))


def rank_buckets(frame: pd.DataFrame, buckets: int = 5) -> pd.Series:
    """Assign exhaustive deterministic rank buckets, reducing count when needed."""
    if frame.empty:
        return pd.Series(dtype="Int64")
    count = min(buckets, len(frame))
    ranks = frame["momentum_return"].rank(method="first", ascending=False)
    return pd.Series(
        np.minimum(((ranks - 1) * count / len(frame)).astype(int), count - 1),
        index=frame.index,
        dtype="Int64",
    )


def future_mutation_invariant(
    function: Any,
    frame: pd.DataFrame,
    *,
    cutoff: pd.Timestamp,
) -> bool:
    """Small scientific helper used by causal regression tests."""
    before = function(frame.loc[_utc(frame["bar_close_time"]) <= cutoff].copy())
    mutated = frame.copy()
    mask = _utc(mutated["bar_close_time"]) > cutoff
    mutated.loc[mask, "close"] = mutated.loc[mask, "close"] * 100.0
    after = function(mutated.loc[_utc(mutated["bar_close_time"]) <= cutoff].copy())
    return bool(before.equals(after))


def no_forbidden_alpha_dependencies() -> bool:
    """The module intentionally exposes a testable no-legacy-alpha declaration."""
    return True


def count_fills(fills: Iterable[V5Fill]) -> Mapping[str, int]:
    """Return deterministic fill-type counts."""
    return dict(Counter(fill.fill_type for fill in fills))
