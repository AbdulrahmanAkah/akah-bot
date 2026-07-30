from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from spotbot.core.engine import PortfolioSnapshot
from spotbot.core.models import Candle, MarketType, OrderRequest, Side

STRATEGY_ID = "AKAH_SCORED_BREAKOUT_V1"
STRATEGY_NAME = "Akah Scored Breakout V1"


def clip01(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("clip01 requires a finite value.")
    return min(max(value, 0.0), 1.0)


def linear_score(
    value: float,
    low: float,
    high: float,
    max_points: float,
) -> float:
    values = (value, low, high, max_points)
    if not all(math.isfinite(item) for item in values):
        raise ValueError("linear_score requires finite values.")
    if high <= low:
        raise ValueError("linear_score requires high > low.")
    if max_points < 0:
        raise ValueError("max_points cannot be negative.")
    return max_points * clip01((value - low) / (high - low))


def rsi_entry_score(rsi: float) -> float:
    if not math.isfinite(rsi):
        raise ValueError("RSI must be finite.")
    if rsi <= 40 or rsi >= 85:
        return 0.0
    if rsi < 60:
        return 8.0 * (rsi - 40.0) / 20.0
    if rsi <= 70:
        return 8.0
    return 8.0 * (85.0 - rsi) / 15.0


def atr_quality_score(atr_fraction: float) -> float:
    if not math.isfinite(atr_fraction):
        raise ValueError("ATR fraction must be finite.")
    if atr_fraction <= 0.003 or atr_fraction >= 0.120:
        return 0.0
    if atr_fraction < 0.020:
        return 8.0 * (atr_fraction - 0.003) / 0.017
    if atr_fraction <= 0.050:
        return 8.0
    return 8.0 * (0.120 - atr_fraction) / 0.070


def extension_quality_score(extension_z: float) -> float:
    if not math.isfinite(extension_z):
        raise ValueError("Extension must be finite.")
    if extension_z <= -0.50 or extension_z >= 4.0:
        return 0.0
    if extension_z < 0.50:
        return 6.0 * (extension_z + 0.50)
    if extension_z <= 2.0:
        return 6.0
    return 6.0 * (4.0 - extension_z) / 2.0


def rsi_health_score(rsi: float) -> float:
    if not math.isfinite(rsi):
        raise ValueError("RSI must be finite.")
    if rsi <= 35:
        return 0.0
    if rsi < 55:
        return 8.0 * (rsi - 35.0) / 20.0
    if rsi <= 80:
        return 8.0
    if rsi < 90:
        return 8.0 - 4.0 * (rsi - 80.0) / 10.0
    return 4.0


@dataclass(frozen=True, slots=True)
class ScoredBreakoutConfig:
    entry_threshold: float = 70.0
    breakout_floor: float = 15.0
    risk_floor: float = 10.0
    confirmed_health_threshold: float = 35.0
    immediate_health_threshold: float = 20.0
    confirmed_health_bars: int = 2
    health_exit_cooldown_bars: int = 3
    stop_exit_cooldown_bars: int = 5
    risk_per_trade: float = 0.01
    initial_stop_atr: float = 2.0
    breakout_weight: float = 25.0
    trend_weight: float = 15.0
    momentum_weight: float = 15.0
    volume_weight: float = 10.0
    relative_strength_weight: float = 15.0
    risk_execution_weight: float = 20.0

    def validate(self) -> None:
        entry_weights = (
            self.breakout_weight,
            self.trend_weight,
            self.momentum_weight,
            self.volume_weight,
            self.relative_strength_weight,
            self.risk_execution_weight,
        )
        if not math.isclose(sum(entry_weights), 100.0, abs_tol=1e-9):
            raise ValueError("Entry score weights must sum to 100.")
        if min(entry_weights) < 0:
            raise ValueError("Entry score weights cannot be negative.")
        if not 0 <= self.entry_threshold <= 100:
            raise ValueError("Entry threshold must be in [0, 100].")
        if not 0 <= self.immediate_health_threshold <= self.confirmed_health_threshold:
            raise ValueError("Health thresholds are invalid.")
        if self.confirmed_health_bars < 1:
            raise ValueError("Confirmed health bars must be positive.")
        if not 0 < self.risk_per_trade <= 1:
            raise ValueError("Risk per trade must be in (0, 1].")


@dataclass(slots=True)
class CandidateRecord:
    timestamp: datetime
    asset: str
    cohort: str
    total_entry_score: float
    breakout_score: float
    trend_score: float
    momentum_score: float
    volume_score: float
    relative_strength_score: float
    risk_execution_score: float
    breakout_floor_pass: bool
    risk_floor_pass: bool
    hard_gate_pass: bool
    cooldown_active: bool
    portfolio_slot_available: bool
    entry_eligible: bool
    accepted_for_entry: bool = False
    rejection_reason: str = ""
    signal_id: str = ""
    order_id: str = ""
    breakout_level: float = 0.0
    atr_14: float = 0.0


@dataclass(slots=True)
class HealthRecord:
    timestamp: datetime
    asset: str
    cohort: str
    trade_id: str
    bars_held: int
    total_health_score: float
    structure_retention_score: float
    trend_continuation_score: float
    momentum_persistence_score: float
    r_state_score: float
    volatility_stability_score: float
    time_efficiency_score: float
    current_r: float
    mfe_r: float
    giveback_r: float
    consecutive_low_health_bars: int
    initial_stop: float
    exit_triggered: bool
    exit_reason: str


@dataclass(frozen=True, slots=True)
class ScoredOrderRecord:
    order_id: str
    signal_id: str
    created_at: datetime
    symbol: str
    side: Side
    reason: str
    stop_loss: float | None


@dataclass(slots=True)
class PositionState:
    signal_timestamp: datetime
    breakout_level: float
    entry_atr: float
    initial_stop: float
    entry_score: float
    entry_price: float = 0.0
    initial_risk: float = 0.0
    highest_close: float = 0.0
    mfe_r: float = 0.0
    bars_held: int = 0
    consecutive_low_health_bars: int = 0
    recent_highest_closes: list[float] = field(default_factory=list)


class ScoredBreakoutStrategy:
    def __init__(
        self,
        *,
        features: dict[str, dict[datetime, dict[str, float]]],
        cohort: str,
        config: ScoredBreakoutConfig | None = None,
    ) -> None:
        self.config = config or ScoredBreakoutConfig()
        self.config.validate()
        self.features = features
        self.cohort = cohort
        self.candidates: list[CandidateRecord] = []
        self.health_records: list[HealthRecord] = []
        self.orders: list[ScoredOrderRecord] = []
        self._positions: dict[str, PositionState] = {}
        self._pending_entries: dict[str, PositionState] = {}
        self._cooldown: dict[str, int] = {symbol: 0 for symbol in features}
        self._was_open: dict[str, bool] = {symbol: False for symbol in features}
        self._pending_health_exit: dict[str, str] = {}
        self._sequence = 0

    @staticmethod
    def _scaled(score: float, source_cap: float, target_cap: float) -> float:
        return min(max(score / source_cap * target_cap, 0.0), target_cap)

    def _entry_components(
        self,
        values: dict[str, float],
        portfolio: PortfolioSnapshot,
    ) -> tuple[float, float, float, float, float, float]:
        atr = values["atr_14"]
        penetration = (values["close"] - values["previous_high_20"]) / atr
        penetration_score = linear_score(penetration, -0.25, 1.0, 12.0)
        close_location = (
            (values["close"] - values["low"]) / (values["high"] - values["low"])
            if values["high"] > values["low"]
            else 0.5
        )
        close_location_score = linear_score(close_location, 0.50, 0.90, 7.0)
        range_score = linear_score(values["true_range"] / atr, 0.80, 2.0, 6.0)
        breakout = min(penetration_score + close_location_score + range_score, 25.0)

        price_ema = linear_score(
            (values["close"] - values["ema_200"]) / atr,
            -1.0,
            2.0,
            5.0,
        )
        slope = linear_score(values["ema_200_slope_20"], -0.01, 0.03, 5.0)
        spread = linear_score(
            (values["ema_50"] - values["ema_200"]) / atr,
            -1.0,
            2.0,
            5.0,
        )
        trend = min(price_ema + slope + spread, 15.0)

        momentum = min(
            rsi_entry_score(values["rsi_14"])
            + linear_score(values["rsi_delta_5"], -5.0, 10.0, 4.0)
            + linear_score(values["roc_20"], -0.05, 0.15, 3.0),
            15.0,
        )
        volume = min(
            linear_score(values["current_volume_ratio"], 0.70, 1.50, 6.0)
            + linear_score(values["recent_volume_ratio"], 0.80, 1.40, 4.0),
            10.0,
        )
        relative = min(
            8.0 * values["roc_20_rank"] + 7.0 * values["roc_60_rank"],
            15.0,
        )

        equity = portfolio.equity
        max_notional = equity * 0.25
        risk_budget = equity * self.config.risk_per_trade
        raw_quantity = risk_budget / (2.0 * atr)
        raw_notional = raw_quantity * values["close"]
        usable = min(raw_notional, max_notional, max(portfolio.cash, 0.0))
        efficiency = usable / max_notional if max_notional > 0 else 0.0
        risk = min(
            atr_quality_score(values["atr_fraction"])
            + extension_quality_score(values["extension_z"])
            + 6.0 * clip01(efficiency),
            20.0,
        )

        return (
            self._scaled(breakout, 25.0, self.config.breakout_weight),
            self._scaled(trend, 15.0, self.config.trend_weight),
            self._scaled(momentum, 15.0, self.config.momentum_weight),
            self._scaled(volume, 10.0, self.config.volume_weight),
            self._scaled(relative, 15.0, self.config.relative_strength_weight),
            self._scaled(risk, 20.0, self.config.risk_execution_weight),
        )

    def _record_order(
        self,
        *,
        candle: Candle,
        side: Side,
        reason: str,
        stop_loss: float | None,
        signal_id: str,
    ) -> OrderRequest:
        self._sequence += 1
        order_id = f"RD14-{self.cohort}-{self._sequence:07d}"
        self.orders.append(
            ScoredOrderRecord(
                order_id=order_id,
                signal_id=signal_id,
                created_at=candle.timestamp,
                symbol=candle.symbol,
                side=side,
                reason=reason,
                stop_loss=stop_loss,
            )
        )
        return OrderRequest(
            symbol=candle.symbol,
            side=side,
            created_at=candle.timestamp,
            execute_after=candle.timestamp,
            market_type=MarketType.SPOT,
            stop_loss=stop_loss,
            risk_fraction=self.config.risk_per_trade if side is Side.BUY else None,
            reason=reason,
        )

    def _candidate(
        self,
        candle: Candle,
        portfolio: PortfolioSnapshot,
        values: dict[str, float],
    ) -> OrderRequest | None:
        components = self._entry_components(values, portfolio)
        total = min(sum(components), 100.0)
        breakout, trend, momentum, volume, relative, risk = components
        cooldown_active = self._cooldown[candle.symbol] > 0
        slot_available = len(portfolio.positions) < 2
        hard_gate = (
            all(math.isfinite(value) for value in values.values())
            and values["atr_14"] > 0
            and values["close"] > 0
            and 0 < values["atr_fraction"] <= 0.15
            and portfolio.position(candle.symbol) is None
            and portfolio.cash > 0
        )
        breakout_pass = breakout >= self.config.breakout_floor
        risk_pass = risk >= self.config.risk_floor
        eligible = (
            hard_gate
            and total >= self.config.entry_threshold
            and breakout_pass
            and risk_pass
            and slot_available
            and not cooldown_active
        )
        reason = ""
        if not hard_gate:
            reason = "hard_gate_failure"
        elif total < self.config.entry_threshold:
            reason = "entry_score_below_threshold"
        elif not breakout_pass:
            reason = "breakout_floor_failure"
        elif not risk_pass:
            reason = "risk_floor_failure"
        elif cooldown_active:
            reason = "cooldown_active"
        elif not slot_available:
            reason = "portfolio_slot_unavailable"
        candidate = CandidateRecord(
            timestamp=candle.timestamp,
            asset=candle.symbol,
            cohort=self.cohort,
            total_entry_score=total,
            breakout_score=breakout,
            trend_score=trend,
            momentum_score=momentum,
            volume_score=volume,
            relative_strength_score=relative,
            risk_execution_score=risk,
            breakout_floor_pass=breakout_pass,
            risk_floor_pass=risk_pass,
            hard_gate_pass=hard_gate,
            cooldown_active=cooldown_active,
            portfolio_slot_available=slot_available,
            entry_eligible=eligible,
            rejection_reason=reason,
            breakout_level=values["previous_high_20"],
            atr_14=values["atr_14"],
        )
        self.candidates.append(candidate)
        if not eligible:
            return None
        signal_id = f"RD14-SIG-{len(self.candidates):08d}"
        candidate.signal_id = signal_id
        stop = values["close"] - self.config.initial_stop_atr * values["atr_14"]
        if stop <= 0 or stop >= values["close"]:
            candidate.entry_eligible = False
            candidate.rejection_reason = "invalid_initial_stop"
            return None
        order = self._record_order(
            candle=candle,
            side=Side.BUY,
            reason="SCORED_BREAKOUT_ENTRY",
            stop_loss=stop,
            signal_id=signal_id,
        )
        candidate.order_id = self.orders[-1].order_id
        self._pending_entries[candle.symbol] = PositionState(
            signal_timestamp=candle.timestamp,
            breakout_level=values["previous_high_20"],
            entry_atr=values["atr_14"],
            initial_stop=stop,
            entry_score=total,
        )
        return order

    @staticmethod
    def _time_score(
        bars_held: int,
        current_r: float,
        new_high_last_10: bool,
    ) -> float:
        if bars_held <= 10:
            return 10.0
        if bars_held <= 20:
            return 10.0 if current_r >= 0.5 else 7.0 if current_r >= 0 else 4.0
        if bars_held <= 30:
            if current_r >= 1:
                return 10.0
            if current_r >= 0.5:
                return 7.0
            return 4.0 if current_r >= 0 else 1.0
        if new_high_last_10 and current_r >= 1:
            return 8.0
        if current_r >= 1:
            return 6.0
        if current_r >= 0.5:
            return 4.0
        return max(0.0, 4.0 - (bars_held - 30.0) / 10.0)

    def _health(
        self,
        candle: Candle,
        values: dict[str, float],
        state: PositionState,
    ) -> tuple[float, tuple[float, float, float, float, float, float], float, float]:
        atr = values["atr_14"]
        state.bars_held += 1
        state.highest_close = max(state.highest_close, candle.close)
        state.recent_highest_closes.append(state.highest_close)
        state.recent_highest_closes = state.recent_highest_closes[-10:]
        current_r = (candle.close - state.entry_price) / state.initial_risk
        state.mfe_r = max(state.mfe_r, current_r)
        giveback = state.mfe_r - current_r
        structure = min(
            linear_score((candle.close - state.breakout_level) / atr, -1.0, 1.0, 12.0)
            + linear_score((candle.close - values["ema_20"]) / atr, -1.0, 1.0, 7.0)
            + 6.0 * clip01(1.0 - (state.highest_close - candle.close) / atr / 3.0),
            25.0,
        )
        trend = min(
            linear_score((candle.close - values["ema_50"]) / atr, -1.5, 1.5, 8.0)
            + linear_score(values["ema_50_slope_10"], -0.01, 0.02, 6.0)
            + linear_score(
                (values["ema_50"] - values["ema_200"]) / atr,
                -1.0,
                2.0,
                6.0,
            ),
            20.0,
        )
        momentum = min(
            rsi_health_score(values["rsi_14"])
            + linear_score(values["rsi_delta_5"], -7.5, 7.5, 3.0)
            + linear_score(values["roc_10"], -0.05, 0.10, 4.0),
            15.0,
        )
        r_state = min(
            linear_score(current_r, -1.0, 2.0, 10.0) + 10.0 * clip01(1.0 - giveback / 2.0),
            20.0,
        )
        atr_expansion = atr / state.entry_atr
        volatility = (
            10.0
            if atr_expansion <= 1.2
            else 10.0 * (2.0 - atr_expansion) / 0.8
            if atr_expansion < 2.0
            else 0.0
        )
        new_high = (
            state.highest_close == max(state.recent_highest_closes)
            if state.recent_highest_closes
            else False
        )
        time_score = self._time_score(state.bars_held, current_r, new_high)
        components = (structure, trend, momentum, r_state, volatility, time_score)
        return min(sum(components), 100.0), components, current_r, giveback

    def _position_order(
        self,
        candle: Candle,
        values: dict[str, float],
        state: PositionState,
    ) -> OrderRequest | None:
        total, components, current_r, giveback = self._health(candle, values, state)
        if total <= self.config.confirmed_health_threshold:
            state.consecutive_low_health_bars += 1
        else:
            state.consecutive_low_health_bars = 0
        reason = ""
        if total <= self.config.immediate_health_threshold:
            reason = "HEALTH_SCORE_CRITICAL"
        elif state.consecutive_low_health_bars >= self.config.confirmed_health_bars:
            reason = "HEALTH_SCORE_CONFIRMED_DETERIORATION"
        triggered = bool(reason)
        self.health_records.append(
            HealthRecord(
                timestamp=candle.timestamp,
                asset=candle.symbol,
                cohort=self.cohort,
                trade_id=f"{candle.symbol}-{state.signal_timestamp.isoformat()}",
                bars_held=state.bars_held,
                total_health_score=total,
                structure_retention_score=components[0],
                trend_continuation_score=components[1],
                momentum_persistence_score=components[2],
                r_state_score=components[3],
                volatility_stability_score=components[4],
                time_efficiency_score=components[5],
                current_r=current_r,
                mfe_r=state.mfe_r,
                giveback_r=giveback,
                consecutive_low_health_bars=state.consecutive_low_health_bars,
                initial_stop=state.initial_stop,
                exit_triggered=triggered,
                exit_reason=reason,
            )
        )
        if not triggered:
            return None
        self._pending_health_exit[candle.symbol] = reason
        return self._record_order(
            candle=candle,
            side=Side.SELL,
            reason=reason,
            stop_loss=None,
            signal_id=f"RD14-EXIT-{len(self.health_records):08d}",
        )

    def on_candle_close(
        self,
        candle: Candle,
        portfolio: PortfolioSnapshot,
    ) -> list[OrderRequest]:
        values = self.features.get(candle.symbol, {}).get(candle.timestamp)
        position = portfolio.position(candle.symbol)
        was_open = self._was_open[candle.symbol]
        if position is None and was_open:
            reason = self._pending_health_exit.pop(candle.symbol, "")
            self._cooldown[candle.symbol] = (
                self.config.health_exit_cooldown_bars
                if reason
                else self.config.stop_exit_cooldown_bars
            )
            self._positions.pop(candle.symbol, None)
        self._was_open[candle.symbol] = position is not None
        if values is None:
            if position is None and self._cooldown[candle.symbol] > 0:
                self._cooldown[candle.symbol] -= 1
            return []
        if position is None:
            order = self._candidate(candle, portfolio, values)
            if self._cooldown[candle.symbol] > 0:
                self._cooldown[candle.symbol] -= 1
            return [order] if order is not None else []
        state = self._positions.get(candle.symbol)
        if state is None:
            state = self._pending_entries.pop(candle.symbol)
            state.entry_price = position.average_price
            state.initial_risk = max(position.average_price - position.stop_loss, 1e-12)
            state.highest_close = candle.close
            self._positions[candle.symbol] = state
        order = self._position_order(candle, values, state)
        return [order] if order is not None else []

    def rank_key(self, order: OrderRequest) -> tuple[float, ...]:
        candidate = next(
            item
            for item in reversed(self.candidates)
            if item.asset == order.symbol and item.timestamp == order.created_at
        )
        return (
            candidate.total_entry_score,
            candidate.breakout_score,
            candidate.relative_strength_score,
            candidate.risk_execution_score,
            candidate.volume_score,
        )
