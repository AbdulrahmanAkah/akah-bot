"""RD19-P2C-R1 conformance-corrected and optimized discovery engine.

This module intentionally preserves the frozen RD19-P2 parameter matrix and
hard gates. It only repairs implementation semantics and execution efficiency.
"""

from __future__ import annotations

import math
import shutil
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

from spotbot.research import rd19_p2a_engine as p2a
from spotbot.research import rd19_p2c_discovery as p2c

SCHEMA_VERSION: Final = "rd19-p2c-r1-engine-v1"
STAGE: Final = "RD19_P2C_R1_CONFORMANCE_CORRECTION_REPLAY_2019_2023"
DECISION: Final = "RD19_P2C_R1_CONFORMANCE_CORRECTION_REPLAY_COMPLETE"
CANDIDATE_ID: Final = "RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1"
EXPECTED_RUNS: Final = 216
INITIAL_EQUITY: Final = 100_000.0
DATA_CUTOFF: Final = pd.Timestamp("2024-01-01T00:00:00+00:00")
HOUR_NS: Final = int(pd.Timedelta(hours=1).value)

PARTITIONS: Final = {
    "DISCOVERY_CORE": (
        pd.Timestamp("2019-01-01T00:00:00Z"),
        pd.Timestamp("2021-12-31T23:00:00Z"),
    ),
    "VALIDATION_2022": (
        pd.Timestamp("2022-01-01T00:00:00Z"),
        pd.Timestamp("2022-12-31T23:00:00Z"),
    ),
    "STRESS_2023": (
        pd.Timestamp("2023-01-01T00:00:00Z"),
        pd.Timestamp("2023-12-31T23:00:00Z"),
    ),
}

REPAIR_IDS: Final = (
    "PULLBACK_LOOKBACK_12_ENFORCED",
    "CONTRACTION_MEASURED_PRE_BREAKOUT",
    "TOP_K_APPLIED_AFTER_ENTRY_AND_COST_FILTERS",
    "MARKET_GATE_NOT_DOUBLE_APPLIED_AT_DAILY_RANK_REFRESH",
    "THESIS_AND_MAX_HOLD_EXIT_NEXT_BAR",
    "TRAIL_UPDATE_EFFECTIVE_NEXT_BAR",
    "GAP_THROUGH_STOP_FILLED_AT_OPEN",
    "HOT_LOOP_PANDAS_SNAPSHOT_REMOVED",
    "FEATURE_STORE_REUSED_BY_SIGNATURE",
    "RAW_EVIDENCE_KEPT_LOCAL_NOT_COMMITTED",
)


class P2CR1Error(RuntimeError):
    """Raised when the corrected replay violates the frozen research contract."""


@dataclass(frozen=True)
class FastPairFrame:
    timestamps_ns: np.ndarray
    columns: dict[str, np.ndarray]

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> FastPairFrame:
        timestamps_ns = (
            pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
            .astype("int64")
            .to_numpy(copy=True)
        )
        if len(timestamps_ns) and not bool(np.all(timestamps_ns[1:] > timestamps_ns[:-1])):
            raise P2CR1Error("feature timestamps must be strictly increasing")
        columns: dict[str, np.ndarray] = {}
        for column in frame.columns:
            if column == "timestamp":
                continue
            series = frame[column]
            if pd.api.types.is_bool_dtype(series.dtype):
                columns[column] = series.to_numpy(dtype=bool, copy=True)
            elif pd.api.types.is_numeric_dtype(series.dtype):
                columns[column] = pd.to_numeric(series, errors="raise").to_numpy(
                    dtype=float,
                    copy=True,
                )
        return cls(timestamps_ns=timestamps_ns, columns=columns)

    def index_at_ns(self, timestamp_ns: int) -> int:
        index = int(np.searchsorted(self.timestamps_ns, timestamp_ns))
        if index >= len(self.timestamps_ns):
            return -1
        return index if int(self.timestamps_ns[index]) == timestamp_ns else -1

    def value(self, index: int, column: str) -> float:
        values = self.columns.get(column)
        if values is None:
            raise P2CR1Error(f"feature column unavailable: {column}")
        return float(values[index])

    def flag(self, index: int, column: str) -> bool:
        values = self.columns.get(column)
        if values is None:
            raise P2CR1Error(f"feature flag unavailable: {column}")
        return bool(values[index])


@dataclass(frozen=True)
class FeatureStore:
    pairs: dict[str, FastPairFrame]
    signature: tuple[object, ...]

    def pair(self, pair: str) -> FastPairFrame | None:
        return self.pairs.get(pair)


def feature_signature(config: Mapping[str, object]) -> tuple[object, ...]:
    """Return the feature-computation signature, excluding routing-only knobs."""
    keys_defaults = (
        ("atr_window_bars", 24),
        ("momentum_fast_bars", None),
        ("momentum_slow_bars", None),
        ("momentum_skip_bars", 24),
        ("persistence_window_bars", None),
        ("trend_fast_ema_bars", None),
        ("trend_slow_ema_bars", None),
        ("pullback_ema_bars", 24),
        ("pullback_lookback_bars", 12),
        ("breakout_lookback_bars", 24),
        ("atr_reference_window_bars", 168),
        ("btc_ema_bars", 168),
        ("breadth_ema_bars", 168),
        ("btc_ema_slope_lookback_bars", 24),
    )
    return tuple(config.get(key, default) for key, default in keys_defaults)


def prepare_feature_frame_corrected(
    raw: pd.DataFrame,
    config: Mapping[str, object],
) -> pd.DataFrame:
    """Build causal features with repaired pullback and contraction semantics."""
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

    pullback_lookback = int(config.get("pullback_lookback_bars", 12))
    touch_on_bar = frame["low"] <= frame["entry_ema"]
    frame["pullback_touch_prior_window"] = (
        touch_on_bar.shift(1)
        .rolling(
            pullback_lookback,
            min_periods=pullback_lookback,
        )
        .max()
        .fillna(False)
        .astype(bool)
    )

    # Contraction belongs to the state before the breakout bar. The breakout
    # bar itself may expand ATR and must not invalidate the preceding squeeze.
    frame["prior_atr"] = frame["atr"].shift(1)
    frame["prior_atr_reference"] = frame["atr_reference"].shift(1)
    return frame


def build_feature_store(
    raw_frames: Mapping[str, pd.DataFrame],
    config: Mapping[str, object],
) -> FeatureStore:
    signature = feature_signature(config)
    pairs: dict[str, FastPairFrame] = {}
    for pair, raw in sorted(raw_frames.items()):
        featured = prepare_feature_frame_corrected(raw, config)
        pairs[pair] = FastPairFrame.from_frame(featured)
    return FeatureStore(pairs=pairs, signature=signature)


def _finite_values(frame: FastPairFrame, index: int, columns: tuple[str, ...]) -> bool:
    for column in columns:
        value = frame.value(index, column)
        if not math.isfinite(value):
            return False
    return True


def trend_eligible(frame: FastPairFrame, index: int) -> bool:
    if not _finite_values(
        frame,
        index,
        (
            "close",
            "trend_fast_ema",
            "trend_slow_ema",
            "momentum_fast",
            "momentum_slow",
            "trend_persistence",
            "atr_percent",
        ),
    ):
        return False
    close = frame.value(index, "close")
    fast = frame.value(index, "trend_fast_ema")
    slow = frame.value(index, "trend_slow_ema")
    return bool(
        close > fast
        and fast > slow
        and frame.value(index, "momentum_fast") > 0.0
        and frame.value(index, "momentum_slow") > 0.0
    )


def entry_filter_reason(
    frame: FastPairFrame,
    index: int,
    config: Mapping[str, object],
) -> str:
    required = (
        "close",
        "atr",
        "trend_fast_ema",
        "entry_ema",
        "prior_close",
        "breakout_high",
        "prior_atr",
        "prior_atr_reference",
    )
    if not _finite_values(frame, index, required):
        return "MISSING_ENTRY_FEATURE"

    close = frame.value(index, "close")
    atr = frame.value(index, "atr")
    if atr <= 0.0:
        return "INVALID_ATR"
    extension = (close - frame.value(index, "trend_fast_ema")) / atr
    if extension > float(config["maximum_extension_atr"]):
        return "EXTENSION_GUARD"

    family = str(config["entry_family"])
    if family == "CONFIRMED_PULLBACK":
        if not frame.flag(index, "pullback_touch_prior_window"):
            return "PULLBACK_NO_TOUCH_IN_FROZEN_LOOKBACK"
        if bool(config.get("recovery_requires_close_above_ema", True)) and close <= frame.value(
            index, "entry_ema"
        ):
            return "PULLBACK_RECOVERY_BELOW_EMA"
        if bool(
            config.get(
                "recovery_requires_close_above_prior_close",
                True,
            )
        ) and close <= frame.value(index, "prior_close"):
            return "PULLBACK_RECOVERY_NOT_ABOVE_PRIOR_CLOSE"
        return "PASS"

    if family == "VOLATILITY_CONTRACTION_BREAKOUT":
        if close <= frame.value(index, "breakout_high"):
            return "BREAKOUT_NOT_CONFIRMED"
        prior_reference = frame.value(index, "prior_atr_reference")
        prior_atr = frame.value(index, "prior_atr")
        if prior_reference <= 0.0 or prior_atr <= 0.0:
            return "CONTRACTION_REFERENCE_INVALID"
        ratio = prior_atr / prior_reference
        if ratio > float(config["maximum_atr_to_reference_ratio"]):
            return "PRE_BREAKOUT_CONTRACTION_NOT_MET"
        return "PASS"

    raise P2CR1Error(f"unsupported entry family: {family}")


def market_gate_reason(
    store: FeatureStore,
    members: tuple[str, ...],
    timestamp_ns: int,
    config: Mapping[str, object],
) -> str:
    if not members:
        return "MEMBERSHIP_MISSING"

    closes: list[float] = []
    breadth_emas: list[float] = []
    returns: list[float] = []
    for pair in members:
        frame = store.pair(pair)
        if frame is None:
            return "MEMBER_SOURCE_MISSING"
        index = frame.index_at_ns(timestamp_ns)
        if index < 0:
            return "MEMBER_BAR_MISSING"
        if not _finite_values(
            frame,
            index,
            ("close", "breadth_ema", "return_168h"),
        ):
            return "MEMBER_GATE_FEATURE_MISSING"
        closes.append(frame.value(index, "close"))
        breadth_emas.append(frame.value(index, "breadth_ema"))
        returns.append(frame.value(index, "return_168h"))

    btc = store.pair("BTC-USDT")
    if btc is None:
        return "BTC_SOURCE_MISSING"
    btc_index = btc.index_at_ns(timestamp_ns)
    if btc_index < 0:
        return "BTC_BAR_MISSING"
    required_btc = ["close", "market_ema"]
    if bool(config["require_btc_ema_positive_slope"]):
        required_btc.append("market_ema_slope")
    if not _finite_values(btc, btc_index, tuple(required_btc)):
        return "BTC_GATE_FEATURE_MISSING"

    btc_close = btc.value(btc_index, "close")
    btc_ema = btc.value(btc_index, "market_ema")
    if bool(config["require_btc_above_ema"]) and btc_close <= btc_ema:
        return "BTC_BELOW_EMA"
    if (
        bool(config["require_btc_ema_positive_slope"])
        and btc.value(btc_index, "market_ema_slope") <= 0.0
    ):
        return "BTC_EMA_SLOPE_NONPOSITIVE"

    breadth = float(np.mean(np.asarray(closes) > np.asarray(breadth_emas)))
    if breadth < float(config["minimum_breadth_fraction"]):
        return "BREADTH_BELOW_THRESHOLD"

    if bool(config["require_positive_median_168h_return"]):
        median_return = float(np.median(np.asarray(returns, dtype=float)))
        if not math.isfinite(median_return) or median_return <= 0.0:
            return "MEDIAN_168H_RETURN_NONPOSITIVE"
    return "PASS"


def build_daily_rank_cache(
    store: FeatureStore,
    membership: p2c.MembershipIndex,
    universe_id: str,
    config: Mapping[str, object],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[int, tuple[dict[str, object], ...]]:
    """Rank all trend-eligible members daily; do not apply market gate here."""
    weights = cast(dict[str, object], config["ranking_score_weights"])
    cache: dict[int, tuple[dict[str, object], ...]] = {}

    for timestamp in pd.date_range(
        start.normalize(),
        end.normalize(),
        freq="D",
    ):
        timestamp_ns = int(timestamp.value)
        members = membership.members_at(universe_id, timestamp)
        rows: list[dict[str, object]] = []
        for pair in members:
            frame = store.pair(pair)
            if frame is None:
                continue
            index = frame.index_at_ns(timestamp_ns)
            if index < 0 or not trend_eligible(frame, index):
                continue
            rows.append(
                {
                    "pair": pair,
                    "momentum_fast": frame.value(index, "momentum_fast"),
                    "momentum_slow": frame.value(index, "momentum_slow"),
                    "trend_persistence": frame.value(index, "trend_persistence"),
                    "atr_percent": frame.value(index, "atr_percent"),
                }
            )
        if not rows:
            cache[timestamp_ns] = ()
            continue

        snapshot = pd.DataFrame.from_records(rows)
        snapshot["momentum_fast_rank"] = snapshot["momentum_fast"].rank(
            method="average",
            pct=True,
        )
        snapshot["momentum_slow_rank"] = snapshot["momentum_slow"].rank(
            method="average",
            pct=True,
        )
        snapshot["persistence_rank"] = snapshot["trend_persistence"].rank(
            method="average",
            pct=True,
        )
        snapshot["score"] = (
            snapshot["momentum_fast_rank"] * float(weights["relative_momentum_fast"])
            + snapshot["momentum_slow_rank"] * float(weights["relative_momentum_slow"])
            + snapshot["persistence_rank"] * float(weights["trend_persistence"])
        )
        snapshot = snapshot.sort_values(
            ["score", "atr_percent", "pair"],
            ascending=[False, True, True],
            kind="stable",
        ).reset_index(drop=True)
        cache[timestamp_ns] = tuple(
            {
                "pair": str(raw["pair"]),
                "rank": rank,
                "score": float(raw["score"]),
            }
            for rank, raw in enumerate(
                snapshot.to_dict(orient="records"),
                start=1,
            )
        )
    return cache


def partition_id_at(timestamp: pd.Timestamp) -> str:
    if timestamp < PARTITIONS["VALIDATION_2022"][0]:
        return "DISCOVERY_CORE"
    if timestamp < PARTITIONS["STRESS_2023"][0]:
        return "VALIDATION_2022"
    return "STRESS_2023"


def _funnel_template() -> Counter[str]:
    return Counter(
        {
            "hours_total": 0,
            "membership_missing_hours": 0,
            "market_gate_off_hours": 0,
            "no_daily_rank_hours": 0,
            "ranked_asset_checks": 0,
            "rank_membership_changed_rejections": 0,
            "missing_feature_rejections": 0,
            "trend_rejections": 0,
            "extension_rejections": 0,
            "pullback_touch_rejections": 0,
            "pullback_recovery_rejections": 0,
            "breakout_rejections": 0,
            "contraction_rejections": 0,
            "cost_hurdle_rejections": 0,
            "candidate_signals": 0,
            "top_k_saturation_hours": 0,
            "partition_final_bar_skips": 0,
        }
    )


def build_candidate_plans(
    store: FeatureStore,
    membership: p2c.MembershipIndex,
    universe_id: str,
    config: Mapping[str, object],
    daily_rank_cache: Mapping[int, tuple[dict[str, object], ...]],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[
    dict[float, dict[int, tuple[dict[str, object], ...]]],
    list[dict[str, object]],
]:
    """Build sparse hourly candidate plans for both frozen cost multipliers."""
    costs = (1.0, 2.0)
    plans: dict[float, dict[int, tuple[dict[str, object], ...]]] = {cost: {} for cost in costs}
    counters: dict[tuple[float, str], Counter[str]] = {
        (cost, partition): _funnel_template() for cost in costs for partition in PARTITIONS
    }
    final_bars = {int(end_ts.value) for _, end_ts in PARTITIONS.values()}
    top_k = int(config["top_k"])

    for timestamp in pd.date_range(start, end, freq="h"):
        timestamp_ns = int(timestamp.value)
        partition_id = partition_id_at(timestamp)
        members = membership.members_at(universe_id, timestamp)

        for cost in costs:
            counters[(cost, partition_id)]["hours_total"] += 1

        if not members:
            for cost in costs:
                counters[(cost, partition_id)]["membership_missing_hours"] += 1
            continue

        gate_reason = market_gate_reason(
            store,
            members,
            timestamp_ns,
            config,
        )
        if gate_reason != "PASS":
            for cost in costs:
                counter = counters[(cost, partition_id)]
                counter["market_gate_off_hours"] += 1
                counter[f"market_gate_{gate_reason.lower()}"] += 1
            continue

        day_ns = int(timestamp.normalize().value)
        ranked = daily_rank_cache.get(day_ns, ())
        if not ranked:
            for cost in costs:
                counters[(cost, partition_id)]["no_daily_rank_hours"] += 1
            continue

        if timestamp_ns in final_bars:
            for cost in costs:
                counters[(cost, partition_id)]["partition_final_bar_skips"] += 1
            continue

        for cost in costs:
            counter = counters[(cost, partition_id)]
            selected: list[dict[str, object]] = []
            effective_cost = (
                2.0
                * p2a.BASE_FEE_RATE
                * cost
                * float(config["effective_cost_uncertainty_multiplier"])
            )

            for ranked_row in ranked:
                if len(selected) >= top_k:
                    break
                counter["ranked_asset_checks"] += 1
                pair = str(ranked_row["pair"])
                if pair not in members:
                    counter["rank_membership_changed_rejections"] += 1
                    continue
                frame = store.pair(pair)
                if frame is None:
                    counter["missing_feature_rejections"] += 1
                    continue
                index = frame.index_at_ns(timestamp_ns)
                if index < 0:
                    counter["missing_feature_rejections"] += 1
                    continue
                if not trend_eligible(frame, index):
                    counter["trend_rejections"] += 1
                    continue

                entry_reason = entry_filter_reason(frame, index, config)
                if entry_reason != "PASS":
                    if entry_reason == "EXTENSION_GUARD":
                        counter["extension_rejections"] += 1
                    elif entry_reason == "PULLBACK_NO_TOUCH_IN_FROZEN_LOOKBACK":
                        counter["pullback_touch_rejections"] += 1
                    elif entry_reason.startswith("PULLBACK_RECOVERY"):
                        counter["pullback_recovery_rejections"] += 1
                    elif entry_reason == "BREAKOUT_NOT_CONFIRMED":
                        counter["breakout_rejections"] += 1
                    elif "CONTRACTION" in entry_reason:
                        counter["contraction_rejections"] += 1
                    else:
                        counter["missing_feature_rejections"] += 1
                    continue

                atr_percent = frame.value(index, "atr_percent")
                if not math.isfinite(atr_percent):
                    counter["missing_feature_rejections"] += 1
                    continue
                cost_ratio = atr_percent / effective_cost if effective_cost > 0.0 else math.inf
                if cost_ratio < float(config["minimum_atr_to_effective_round_trip_cost"]):
                    counter["cost_hurdle_rejections"] += 1
                    continue

                selected.append(
                    {
                        "signal_time": timestamp,
                        "execution_time": timestamp + pd.Timedelta(hours=1),
                        "pair": pair,
                        "rank": int(ranked_row["rank"]),
                        "score": float(ranked_row["score"]),
                        "atr": frame.value(index, "atr"),
                        "atr_percent": atr_percent,
                        "cost_hurdle_ratio": cost_ratio,
                        "entry_family": str(config["entry_family"]),
                    }
                )
                counter["candidate_signals"] += 1

            if len(selected) >= top_k:
                counter["top_k_saturation_hours"] += 1
            if selected:
                plans[cost][timestamp_ns] = tuple(selected)

    funnel_rows: list[dict[str, object]] = []
    for cost in costs:
        for partition_id in PARTITIONS:
            row = {
                "variant_id": str(config["variant_id"]),
                "universe_id": universe_id,
                "cost_multiplier": cost,
                "partition_id": partition_id,
                **dict(counters[(cost, partition_id)]),
            }
            funnel_rows.append(row)
    return plans, funnel_rows


def _position_value(
    positions: Mapping[str, dict[str, object]],
    store: FeatureStore,
    timestamp_ns: int,
    price_column: str,
) -> float:
    total = 0.0
    for pair, position in positions.items():
        frame = store.pair(pair)
        if frame is None:
            raise P2CR1Error(f"open position source missing: {pair}")
        index = frame.index_at_ns(timestamp_ns)
        if index < 0:
            raise P2CR1Error(f"open position bar missing: {pair}/{timestamp_ns}")
        total += float(position["quantity"]) * frame.value(index, price_column)
    return total


def execute_run_fast(
    *,
    run_row: Mapping[str, object],
    config: Mapping[str, object],
    store: FeatureStore,
    membership: p2c.MembershipIndex,
    candidate_plan: Mapping[int, tuple[dict[str, object], ...]],
    partition_start: pd.Timestamp,
    partition_end: pd.Timestamp,
) -> dict[str, object]:
    """Execute one corrected run with next-bar causal discretionary exits."""
    run_id = p2c.run_id_for(run_row)
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
    pending_exits: dict[str, str] = {}
    pending_entries: list[dict[str, object]] = []
    last_exit: dict[str, pd.Timestamp] = {}
    cash = INITIAL_EQUITY
    event_order = 0
    trade_counter = 0
    diagnostics = Counter(
        {
            "router_admitted": 0,
            "router_rejected": 0,
            "stop_exits": 0,
            "next_bar_thesis_exits": 0,
            "next_bar_max_holding_exits": 0,
            "partition_end_liquidations": 0,
            "gap_through_stop_fills": 0,
        }
    )

    def close_position(
        pair: str,
        timestamp: pd.Timestamp,
        exit_price: float,
        exit_reason: str,
    ) -> None:
        nonlocal cash, event_order
        position = positions[pair]
        quantity = float(position["quantity"])
        exit_notional = quantity * exit_price
        exit_fee = exit_notional * fee_rate
        cash_amount = exit_notional - exit_fee
        cash += cash_amount
        entry_price = float(position["entry_price"])
        entry_fee = float(position["entry_fee"])
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

    for timestamp in pd.date_range(
        partition_start,
        partition_end,
        freq="h",
    ):
        timestamp_ns = int(timestamp.value)
        members = membership.members_at(universe_id, timestamp)

        # Discretionary close signals are formed on the prior completed bar and
        # execute at this bar's open.
        for pair in sorted(list(pending_exits)):
            if pair not in positions:
                pending_exits.pop(pair, None)
                continue
            frame = store.pair(pair)
            if frame is None:
                raise P2CR1Error(f"pending exit source missing: {pair}")
            index = frame.index_at_ns(timestamp_ns)
            if index < 0:
                raise P2CR1Error(f"pending exit bar missing: {pair}/{timestamp}")
            reason = pending_exits.pop(pair)
            close_position(
                pair,
                timestamp,
                frame.value(index, "open"),
                reason,
            )
            if reason == "THESIS_INVALIDATION":
                diagnostics["next_bar_thesis_exits"] += 1
            elif reason == "MAX_HOLDING_SAFEGUARD":
                diagnostics["next_bar_max_holding_exits"] += 1

        # Route prior-bar candidates at the current open.
        for signal in pending_entries:
            pair = str(signal["pair"])
            frame = store.pair(pair)
            cash_before = cash
            equity_before = cash + _position_value(
                positions,
                store,
                timestamp_ns,
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
            elif frame is None:
                reason = "MISSING_ENTRY_SOURCE"
            else:
                index = frame.index_at_ns(timestamp_ns)
                if index < 0:
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
                    entry_price = frame.value(index, "open")
                    signal_atr = float(signal["atr"])
                    stop_distance = signal_atr * float(config["initial_stop_atr"])
                    risk_budget = equity_before * float(
                        config["risk_per_position_fraction_of_equity"]
                    )
                    existing_gross = _position_value(
                        positions,
                        store,
                        timestamp_ns,
                        "open",
                    )
                    max_gross = equity_before * float(config["maximum_gross_exposure_fraction"])
                    asset_cap = equity_before * float(
                        config["maximum_single_asset_exposure_fraction"]
                    )
                    if stop_distance <= 0.0 or entry_price - stop_distance <= 0.0:
                        reason = "INVALID_STOP_GEOMETRY"
                    else:
                        q_risk = risk_budget / stop_distance
                        q_asset = asset_cap / entry_price
                        q_gross = max(0.0, max_gross - existing_gross) / entry_price
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
        pending_entries = []

        # Protective stops are active during the current bar using only levels
        # known before the bar. A newly tightened trail becomes effective on
        # the next bar, avoiding OHLC path ambiguity.
        for pair in sorted(list(positions)):
            position = positions[pair]
            frame = store.pair(pair)
            if frame is None:
                raise P2CR1Error(f"open position source missing: {pair}")
            index = frame.index_at_ns(timestamp_ns)
            if index < 0:
                raise P2CR1Error(f"open position bar missing: {pair}/{timestamp}")

            position["bars_held"] = int(position["bars_held"]) + 1
            open_price = frame.value(index, "open")
            high = frame.value(index, "high")
            low = frame.value(index, "low")
            close = frame.value(index, "close")
            active_stop = float(position["active_stop"])

            stop_hit = False
            stop_price = active_stop
            if open_price <= active_stop:
                stop_hit = True
                stop_price = open_price
                diagnostics["gap_through_stop_fills"] += 1
            elif low <= active_stop:
                stop_hit = True

            if stop_hit:
                reason = "STRUCTURAL_TRAIL" if bool(position["trail_active"]) else "INITIAL_STOP"
                close_position(pair, timestamp, stop_price, reason)
                diagnostics["stop_exits"] += 1
                continue

            if timestamp == partition_end:
                close_position(
                    pair,
                    timestamp,
                    close,
                    "PARTITION_END_LIQUIDATION",
                )
                diagnostics["partition_end_liquidations"] += 1
                continue

            thesis_ema = frame.value(index, "trend_fast_ema")
            if close < thesis_ema:
                pending_exits[pair] = "THESIS_INVALIDATION"
                continue
            if int(position["bars_held"]) >= int(config["maximum_holding_bars"]):
                pending_exits[pair] = "MAX_HOLDING_SAFEGUARD"
                continue

            # Update trail only after the current bar survived the pre-existing
            # stop. The new stop applies from the next bar onward.
            high_water = max(float(position["high_water"]), high)
            position["high_water"] = high_water
            stop_distance = float(position["stop_distance"])
            open_r = (high_water - float(position["entry_price"])) / stop_distance
            if open_r >= float(config["trail_activation_r"]):
                position["trail_active"] = True
                atr = frame.value(index, "atr")
                position["active_stop"] = max(
                    active_stop,
                    high_water - atr * float(config["trail_atr"]),
                )

        position_value = _position_value(
            positions,
            store,
            timestamp_ns,
            "close",
        )
        equity = cash + position_value
        if cash < -1e-7:
            raise P2CR1Error(f"negative cash: {run_id}/{timestamp}/{cash}")

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

        if timestamp < partition_end:
            planned = candidate_plan.get(timestamp_ns, ())
            if planned:
                pending_entries = []
                for raw_signal in planned:
                    signal = {
                        "run_id": run_id,
                        "variant_id": variant_id,
                        "partition_id": partition_id,
                        "universe_id": universe_id,
                        "cost_multiplier": cost_multiplier,
                        **raw_signal,
                    }
                    candidates.append(signal)
                    pending_entries.append(signal)

    if positions:
        raise P2CR1Error(f"positions remain open after corrected partition liquidation: {run_id}")
    if pending_exits:
        raise P2CR1Error(f"pending exits remain after partition: {run_id}/{sorted(pending_exits)}")

    candidate_frame = pd.DataFrame.from_records(
        candidates,
        columns=list(p2c.CANDIDATE_COLUMNS),
    )
    evaluated_frame = pd.DataFrame.from_records(
        evaluated,
        columns=list(p2c.EVALUATED_COLUMNS),
    )
    trade_frame = pd.DataFrame.from_records(
        trades,
        columns=list(p2c.TRADE_COLUMNS),
    )
    cash_frame = pd.DataFrame.from_records(
        cash_events,
        columns=list(p2c.CASH_COLUMNS),
    )
    equity_frame = pd.DataFrame.from_records(
        equity_rows,
        columns=list(p2c.EQUITY_COLUMNS),
    )

    if equity_frame.empty:
        raise P2CR1Error(f"empty corrected equity curve: {run_id}")

    end_equity = float(equity_frame["equity"].iloc[-1])
    pnl_values = (
        pd.to_numeric(trade_frame["net_pnl"], errors="raise")
        if not trade_frame.empty
        else pd.Series(dtype=float)
    )
    entry_turnover = (
        float(pd.to_numeric(trade_frame["entry_notional"], errors="raise").sum())
        if not trade_frame.empty
        else 0.0
    )
    exit_turnover = (
        float(pd.to_numeric(trade_frame["exit_notional"], errors="raise").sum())
        if not trade_frame.empty
        else 0.0
    )
    total_fees = (
        float(
            (
                pd.to_numeric(trade_frame["entry_fee"], errors="raise")
                + pd.to_numeric(trade_frame["exit_fee"], errors="raise")
            ).sum()
        )
        if not trade_frame.empty
        else 0.0
    )

    metrics: dict[str, object] = {
        "schema_version": "rd19-p2c-r1-run-metrics-v1",
        "correction_engine_schema": SCHEMA_VERSION,
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
        "profit_factor": (p2c.profit_factor(pnl_values) if not pnl_values.empty else None),
        "maximum_drawdown": p2c.maximum_drawdown(equity_frame["equity"]),
        "minimum_cash": float(equity_frame["cash"].min()),
        "maximum_open_positions": int(equity_frame["open_positions"].max()),
        "maximum_gross_exposure": float(equity_frame["gross_exposure"].max()),
        "entry_turnover_notional": entry_turnover,
        "exit_turnover_notional": exit_turnover,
        "turnover_on_initial_equity": (entry_turnover + exit_turnover) / INITIAL_EQUITY,
        "total_fees": total_fees,
        "year_returns": p2c.year_returns(
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
        "diagnostics": dict(diagnostics),
    }
    return {
        "metrics": metrics,
        "candidates": candidate_frame,
        "evaluated": evaluated_frame,
        "trades": trade_frame,
        "cash": cash_frame,
        "equity": equity_frame,
    }


def write_run_result_atomic(
    run_dir: Path,
    result: Mapping[str, object],
) -> dict[str, Any]:
    """Write a run checkpoint atomically so interruption remains resumable."""
    if (run_dir / "checkpoint.json").is_file():
        return p2c.verify_checkpoint(run_dir)
    if run_dir.exists():
        raise P2CR1Error(f"non-checkpoint run directory exists: {run_dir}")
    temporary = run_dir.with_name(run_dir.name + ".tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    checkpoint = p2c.write_run_result(temporary, result)
    temporary.replace(run_dir)
    return cast(dict[str, Any], checkpoint)
