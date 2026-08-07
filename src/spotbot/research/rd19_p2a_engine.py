"""RD19-P2A frozen discovery engine and technical dry-run helpers."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

SCHEMA_VERSION: Final = "rd19-p2a-engine-v1"
STAGE: Final = "RD19_P2A_DISCOVERY_ENGINE_IMPLEMENTATION_AND_TECHNICAL_DRY_RUN"
DECISION: Final = "RD19_P2A_ENGINE_IMPLEMENTATION_AND_TECHNICAL_DRY_RUN_COMPLETE"
NEXT_STAGE: Final = "RD19_P2B_DISCOVERY_EXECUTION_AUTHORIZATION"
CANDIDATE_ID: Final = "RD19_COST_AWARE_CROSS_SECTIONAL_TREND_CONVEXITY_V1"
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00+00:00")
BASE_FEE_RATE: Final = 0.001
REQUIRED_BAR_COLUMNS: Final = frozenset({"timestamp", "open", "high", "low", "close", "volume"})


class P2AEngineError(RuntimeError):
    """Raised when the frozen RD19-P2A engine contract is violated."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise P2AEngineError(f"JSON missing: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise P2AEngineError(f"JSON object expected: {path}")
    return cast(dict[str, Any], value)


def finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise P2AEngineError(f"{name} cannot be boolean")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise P2AEngineError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise P2AEngineError(f"{name} must be finite")
    return result


def normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(REQUIRED_BAR_COLUMNS.difference(frame.columns))
    if missing:
        raise P2AEngineError(f"hourly bar columns missing: {missing}")
    result = frame.loc[:, sorted(REQUIRED_BAR_COLUMNS)].copy()
    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
        errors="raise",
    ).astype("datetime64[ns, UTC]")
    result = result.sort_values("timestamp", kind="stable").reset_index(drop=True)
    if result.empty:
        raise P2AEngineError("hourly bars cannot be empty")
    if bool(result["timestamp"].duplicated().any()):
        raise P2AEngineError("hourly bars contain duplicate timestamps")
    if bool((result["timestamp"] >= SEALED_CUTOFF).any()):
        raise P2AEngineError("hourly bars cross the sealed 2025 cutoff")
    for column in ("open", "high", "low", "close", "volume"):
        result[column] = pd.to_numeric(result[column], errors="raise")
    if bool((result[["open", "high", "low", "close"]] <= 0.0).any().any()):
        raise P2AEngineError("OHLC values must be positive")
    if bool((result["high"] < result[["open", "close", "low"]].max(axis=1)).any()):
        raise P2AEngineError("high is inconsistent with OHLC")
    if bool((result["low"] > result[["open", "close", "high"]].min(axis=1)).any()):
        raise P2AEngineError("low is inconsistent with OHLC")
    return result


def _ema(values: pd.Series, span: int) -> pd.Series:
    return values.ewm(span=span, adjust=False, min_periods=span).mean()


def _atr(frame: pd.DataFrame, window: int) -> pd.Series:
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        (
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ),
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window, min_periods=window).mean()


def feature_frame(frame: pd.DataFrame, config: Mapping[str, object]) -> pd.DataFrame:
    result = normalize_bars(frame)
    close = result["close"]
    fast = int(config["momentum_fast_bars"])
    slow = int(config["momentum_slow_bars"])
    skip = int(config["momentum_skip_bars"])
    persistence_window = int(config["persistence_window_bars"])
    trend_fast = int(config["trend_fast_ema_bars"])
    trend_slow = int(config["trend_slow_ema_bars"])
    atr_window = int(config.get("atr_window_bars", 24))

    result["trend_fast_ema"] = _ema(close, trend_fast)
    result["trend_slow_ema"] = _ema(close, trend_slow)
    result["entry_ema"] = _ema(close, int(config.get("pullback_ema_bars", 24)))
    result["atr"] = _atr(result, atr_window)
    result["atr_percent"] = result["atr"] / close
    result["momentum_fast"] = close.shift(skip) / close.shift(fast + skip) - 1.0
    result["momentum_slow"] = close.shift(skip) / close.shift(slow + skip) - 1.0
    above_fast = (close > result["trend_fast_ema"]).astype(float)
    result["trend_persistence"] = above_fast.rolling(
        persistence_window,
        min_periods=persistence_window,
    ).mean()
    result["prior_close"] = close.shift(1)
    result["prior_low"] = result["low"].shift(1)
    result["prior_high"] = result["high"].shift(1)
    result["breakout_high"] = (
        result["high"]
        .shift(1)
        .rolling(
            int(config.get("breakout_lookback_bars", 24)),
            min_periods=int(config.get("breakout_lookback_bars", 24)),
        )
        .max()
    )
    reference_window = int(config.get("atr_reference_window_bars", 168))
    result["atr_reference"] = (
        result["atr"]
        .rolling(
            reference_window,
            min_periods=reference_window,
        )
        .median()
    )
    return result


def resolve_variants(protocol: Mapping[str, object]) -> list[dict[str, object]]:
    common = protocol.get("common_parameters")
    levels = protocol.get("parameter_levels")
    matrix = protocol.get("variant_matrix")
    factor_order = protocol.get("factor_order")
    if not isinstance(common, dict):
        raise P2AEngineError("common_parameters must be an object")
    if not isinstance(levels, dict):
        raise P2AEngineError("parameter_levels must be an object")
    if not isinstance(matrix, list):
        raise P2AEngineError("variant_matrix must be a list")
    if not isinstance(factor_order, list):
        raise P2AEngineError("factor_order must be a list")

    variants: list[dict[str, object]] = []
    for raw in matrix:
        if not isinstance(raw, dict):
            raise P2AEngineError("variant row must be an object")
        config: dict[str, object] = dict(common)
        variant_id = str(raw.get("variant_id", ""))
        if not variant_id:
            raise P2AEngineError("variant_id is missing")
        selected_levels: dict[str, str] = {}
        for factor_raw in factor_order:
            factor = str(factor_raw)
            level_id = str(raw.get(factor, ""))
            factor_levels = levels.get(factor)
            if not isinstance(factor_levels, dict):
                raise P2AEngineError(f"factor levels missing: {factor}")
            selected: dict[str, object] | None = None
            for level_name, value in factor_levels.items():
                if isinstance(value, dict) and str(value.get("level_id", "")) == level_id:
                    selected = cast(dict[str, object], value)
                    selected_levels[factor] = str(level_name)
                    break
            if selected is None:
                raise P2AEngineError(f"variant {variant_id} has unknown level {factor}/{level_id}")
            for key, value in selected.items():
                if key != "level_id":
                    config[key] = value
            config[f"{factor.lower()}_level_id"] = level_id
        config["variant_id"] = variant_id
        config["selected_levels"] = selected_levels
        variants.append(config)
    if len(variants) != 12:
        raise P2AEngineError(f"expected 12 variants, found {len(variants)}")
    return variants


def _percentile(values: pd.Series) -> pd.Series:
    return values.rank(method="average", pct=True)


def market_gate(
    snapshot: pd.DataFrame,
    *,
    btc_row: Mapping[str, object],
    config: Mapping[str, object],
) -> bool:
    btc_close = finite(btc_row["close"], name="btc close")
    btc_ema = finite(btc_row["market_ema"], name="btc market ema")
    if bool(config["require_btc_above_ema"]) and btc_close <= btc_ema:
        return False
    if bool(config["require_btc_ema_positive_slope"]):
        slope = finite(btc_row["market_ema_slope"], name="btc market ema slope")
        if slope <= 0.0:
            return False
    breadth = float(
        (
            pd.to_numeric(snapshot["close"], errors="raise")
            > pd.to_numeric(snapshot["breadth_ema"], errors="raise")
        ).mean()
    )
    if breadth < finite(
        config["minimum_breadth_fraction"],
        name="minimum breadth",
    ):
        return False
    if bool(config["require_positive_median_168h_return"]):
        median_return = float(
            pd.to_numeric(
                snapshot["return_168h"],
                errors="coerce",
            ).median()
        )
        if not math.isfinite(median_return) or median_return <= 0.0:
            return False
    return True


def _entry_pass(row: Mapping[str, object], config: Mapping[str, object]) -> bool:
    close = finite(row["close"], name="close")
    atr = finite(row["atr"], name="atr")
    if atr <= 0.0:
        return False
    extension = (close - finite(row["trend_fast_ema"], name="trend fast ema")) / atr
    if extension > finite(config["maximum_extension_atr"], name="extension"):
        return False

    family = str(config["entry_family"])
    if family == "CONFIRMED_PULLBACK":
        return all(
            (
                finite(row["prior_low"], name="prior low")
                <= finite(row["entry_ema"], name="entry ema"),
                close > finite(row["entry_ema"], name="entry ema"),
                close > finite(row["prior_close"], name="prior close"),
            )
        )
    if family == "VOLATILITY_CONTRACTION_BREAKOUT":
        reference = finite(row["atr_reference"], name="atr reference")
        if reference <= 0.0:
            return False
        return all(
            (
                close > finite(row["breakout_high"], name="breakout high"),
                atr / reference
                <= finite(
                    config["maximum_atr_to_reference_ratio"],
                    name="ATR contraction ratio",
                ),
            )
        )
    raise P2AEngineError(f"unsupported entry family: {family}")


def candidate_snapshot(
    frames: Mapping[str, pd.DataFrame],
    *,
    signal_time: pd.Timestamp,
    config: Mapping[str, object],
    round_trip_cost_rate: float,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    market_ema_bars = int(config["btc_ema_bars"])
    slope_lookback = int(config.get("btc_ema_slope_lookback_bars", 24))
    breadth_ema_bars = int(config["breadth_ema_bars"])

    for pair, raw in sorted(frames.items()):
        featured = feature_frame(raw, config)
        featured["market_ema"] = _ema(featured["close"], market_ema_bars)
        featured["breadth_ema"] = _ema(featured["close"], breadth_ema_bars)
        featured["return_168h"] = featured["close"] / featured["close"].shift(168) - 1.0
        featured["market_ema_slope"] = featured["market_ema"] - featured["market_ema"].shift(
            slope_lookback
        )
        match = featured.loc[featured["timestamp"] == signal_time]
        if match.empty:
            continue
        row = match.iloc[-1].to_dict()
        row["pair"] = pair
        rows.append(row)

    snapshot = pd.DataFrame.from_records(rows)
    if snapshot.empty:
        return snapshot
    required_numeric = [
        "close",
        "trend_fast_ema",
        "trend_slow_ema",
        "momentum_fast",
        "momentum_slow",
        "trend_persistence",
        "atr",
        "atr_percent",
        "market_ema",
        "breadth_ema",
        "return_168h",
    ]
    snapshot = snapshot.dropna(subset=required_numeric).copy()
    if snapshot.empty:
        return snapshot
    btc = snapshot.loc[snapshot["pair"].astype(str) == "BTC-USDT"]
    if btc.empty:
        raise P2AEngineError("BTC-USDT is required for the market gate")
    if not market_gate(snapshot, btc_row=btc.iloc[0].to_dict(), config=config):
        return snapshot.iloc[0:0].copy()

    snapshot = snapshot.loc[
        (snapshot["close"] > snapshot["trend_fast_ema"])
        & (snapshot["trend_fast_ema"] > snapshot["trend_slow_ema"])
        & (snapshot["momentum_fast"] > 0.0)
        & (snapshot["momentum_slow"] > 0.0)
    ].copy()
    if snapshot.empty:
        return snapshot
    snapshot["momentum_fast_rank"] = _percentile(snapshot["momentum_fast"])
    snapshot["momentum_slow_rank"] = _percentile(snapshot["momentum_slow"])
    snapshot["persistence_rank"] = _percentile(snapshot["trend_persistence"])
    weights = cast(dict[str, object], config["ranking_score_weights"])
    snapshot["score"] = (
        snapshot["momentum_fast_rank"]
        * finite(weights["relative_momentum_fast"], name="fast weight")
        + snapshot["momentum_slow_rank"]
        * finite(weights["relative_momentum_slow"], name="slow weight")
        + snapshot["persistence_rank"]
        * finite(weights["trend_persistence"], name="persistence weight")
    )
    effective_cost = round_trip_cost_rate * finite(
        config["effective_cost_uncertainty_multiplier"],
        name="cost uncertainty",
    )
    snapshot["cost_hurdle_ratio"] = snapshot["atr_percent"] / effective_cost
    snapshot = snapshot.loc[
        snapshot["cost_hurdle_ratio"]
        >= finite(
            config["minimum_atr_to_effective_round_trip_cost"],
            name="cost hurdle",
        )
    ].copy()
    if snapshot.empty:
        return snapshot
    snapshot["entry_pass"] = [
        _entry_pass(row, config) for row in snapshot.to_dict(orient="records")
    ]
    snapshot = snapshot.loc[snapshot["entry_pass"]].copy()
    if snapshot.empty:
        return snapshot
    snapshot = snapshot.sort_values(
        ["score", "atr_percent", "pair"],
        ascending=[False, True, True],
        kind="stable",
    ).head(int(config["top_k"]))
    snapshot["rank"] = np.arange(1, len(snapshot) + 1)
    snapshot["signal_time"] = signal_time
    snapshot["variant_id"] = str(config["variant_id"])
    return snapshot.reset_index(drop=True)


def simulate_trade(
    frame: pd.DataFrame,
    candidate: Mapping[str, object],
    config: Mapping[str, object],
    *,
    cost_multiplier: float,
    starting_equity: float,
) -> dict[str, object]:
    bars = feature_frame(frame, config)
    signal_time = pd.Timestamp(cast(Any, candidate["signal_time"]))
    match = bars.index[bars["timestamp"] == signal_time]
    if len(match) != 1:
        raise P2AEngineError("signal timestamp not found exactly once")
    signal_index = int(match[0])
    entry_index = signal_index + 1
    if entry_index >= len(bars):
        raise P2AEngineError("next-bar entry is unavailable")
    entry = bars.iloc[entry_index]
    entry_price = finite(entry["open"], name="entry price")
    signal_atr = finite(candidate["atr"], name="signal ATR")
    stop_distance = signal_atr * finite(
        config["initial_stop_atr"],
        name="initial stop ATR",
    )
    initial_stop = entry_price - stop_distance
    if initial_stop <= 0.0:
        raise P2AEngineError("initial stop must remain positive")
    risk_budget = starting_equity * finite(
        config["risk_per_position_fraction_of_equity"],
        name="risk fraction",
    )
    quantity = risk_budget / stop_distance
    notional_cap = starting_equity * finite(
        config["maximum_single_asset_exposure_fraction"],
        name="single asset cap",
    )
    quantity = min(quantity, notional_cap / entry_price)
    if quantity <= 0.0:
        raise P2AEngineError("position quantity must be positive")

    fee_rate = BASE_FEE_RATE * cost_multiplier
    entry_fee = quantity * entry_price * fee_rate
    required_cash = quantity * entry_price + entry_fee
    if required_cash > starting_equity + 1e-9:
        raise P2AEngineError("fixture trade exceeds available cash")
    cash_after_entry = starting_equity - required_cash

    high_water = entry_price
    active_stop = initial_stop
    exit_reason = "MAX_HOLDING_SAFEGUARD"
    exit_price = finite(bars.iloc[-1]["close"], name="last close")
    exit_time = pd.Timestamp(bars.iloc[-1]["timestamp"])
    maximum_holding = int(config["maximum_holding_bars"])
    trail_active = False

    end = min(len(bars), entry_index + maximum_holding + 1)
    for position in range(entry_index, end):
        row = bars.iloc[position]
        high = finite(row["high"], name="high")
        low = finite(row["low"], name="low")
        close = finite(row["close"], name="close")
        atr = finite(row["atr"], name="ATR")
        high_water = max(high_water, high)
        open_r = (high_water - entry_price) / stop_distance
        if open_r >= finite(config["trail_activation_r"], name="trail activation"):
            trail_active = True
            active_stop = max(
                active_stop,
                high_water - atr * finite(config["trail_atr"], name="trail ATR"),
            )
        thesis_ema = finite(row["trend_fast_ema"], name="thesis EMA")
        if low <= active_stop:
            exit_price = active_stop
            exit_time = pd.Timestamp(row["timestamp"])
            exit_reason = "STRUCTURAL_TRAIL" if trail_active else "INITIAL_STOP"
            break
        if close < thesis_ema:
            exit_price = close
            exit_time = pd.Timestamp(row["timestamp"])
            exit_reason = "THESIS_INVALIDATION"
            break
        if position == end - 1:
            exit_price = close
            exit_time = pd.Timestamp(row["timestamp"])

    exit_fee = quantity * exit_price * fee_rate
    gross_pnl = quantity * (exit_price - entry_price)
    net_pnl = gross_pnl - entry_fee - exit_fee
    final_cash = cash_after_entry + quantity * exit_price - exit_fee
    if final_cash < -1e-7:
        raise P2AEngineError("fixture routing produced negative cash")

    return {
        "variant_id": str(config["variant_id"]),
        "pair": str(candidate["pair"]),
        "signal_time": signal_time,
        "entry_time": pd.Timestamp(entry["timestamp"]),
        "exit_time": exit_time,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "quantity": quantity,
        "notional": quantity * entry_price,
        "risk_budget": risk_budget,
        "entry_fee": entry_fee,
        "exit_fee": exit_fee,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "minimum_cash": min(cash_after_entry, final_cash),
        "final_cash": final_cash,
        "bars_held": int((exit_time - pd.Timestamp(entry["timestamp"])) / pd.Timedelta(hours=1))
        + 1,
        "exit_reason": exit_reason,
        "instrument_type": "SPOT",
        "side": "LONG",
        "cost_multiplier": cost_multiplier,
    }


def synthetic_frames(
    config: Mapping[str, object],
    *,
    periods: int = 2400,
) -> dict[str, pd.DataFrame]:
    if periods < 2200:
        raise P2AEngineError("synthetic fixture requires at least 2200 bars")
    timestamps = pd.date_range(
        "2024-01-01T00:00:00Z",
        periods=periods,
        freq="h",
    )
    pairs = [
        "BTC-USDT",
        "ETH-USDT",
        "SOL-USDT",
        "LINK-USDT",
        "AVAX-USDT",
        "ADA-USDT",
    ]
    result: dict[str, pd.DataFrame] = {}
    family = str(config["entry_family"])

    for index, pair in enumerate(pairs):
        base = 100.0 + index * 7.0
        drift = 0.00012 + index * 0.00001
        x = np.arange(periods, dtype=float)
        close = base * np.exp(drift * x)
        close *= 1.0 + 0.0025 * np.sin(x / (15.0 + index))
        signal = periods - 181

        if family == "CONFIRMED_PULLBACK":
            close[signal - 8 : signal] *= np.linspace(0.992, 0.976, 8)
            close[signal] = close[signal - 1] * 1.018
        else:
            anchor = close[signal - 180]
            contraction = anchor * (
                1.0
                + np.linspace(0.0, 0.035 + index * 0.001, 180)
                + 0.00035 * np.sin(np.arange(180) / 6.0)
            )
            close[signal - 180 : signal] = contraction
            close[signal] = float(np.max(contraction[-24:])) * 1.04

        future = np.arange(periods - signal - 1, dtype=float)
        close[signal + 1 :] = close[signal] * (1.0 + 0.0018 * future - 0.000004 * future**2)
        close[signal + 1 :] = np.maximum(
            close[signal + 1 :],
            close[signal] * 0.85,
        )

        open_ = np.r_[close[0], close[:-1]]
        spread = np.maximum(close * 0.05, 0.05)
        if family == "VOLATILITY_CONTRACTION_BREAKOUT":
            spread[signal - 24 : signal + 1] = np.maximum(
                close[signal - 24 : signal + 1] * 0.035,
                0.05,
            )
        else:
            spread[:] = np.maximum(close * 0.025, 0.05)
        high = np.maximum(open_, close) + spread
        low = np.minimum(open_, close) - spread
        if family == "CONFIRMED_PULLBACK":
            low[signal - 1] = min(low[signal - 1], close[signal - 1] * 0.985)
        volume = 1_000_000.0 + index * 50_000.0 + x * 10.0
        result[pair] = pd.DataFrame(
            {
                "timestamp": timestamps,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    return result


def dry_run_variant(
    config: Mapping[str, object],
    *,
    cost_multiplier: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames = synthetic_frames(config)
    signal_time = pd.Timestamp(next(iter(frames.values())).iloc[-181]["timestamp"])
    candidates = candidate_snapshot(
        frames,
        signal_time=signal_time,
        config=config,
        round_trip_cost_rate=2.0 * BASE_FEE_RATE * cost_multiplier,
    )
    if candidates.empty:
        raise P2AEngineError(f"fixture produced no candidates for {config['variant_id']}")
    trades = pd.DataFrame.from_records(
        [
            simulate_trade(
                frames[str(row["pair"])],
                row,
                config,
                cost_multiplier=cost_multiplier,
                starting_equity=float(config["initial_equity"]),
            )
            for row in candidates.to_dict(orient="records")
        ]
    )
    if trades.empty:
        raise P2AEngineError(f"fixture produced no trades for {config['variant_id']}")
    return candidates, trades
