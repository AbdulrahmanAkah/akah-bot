from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from spotbot.core.engine import PortfolioSnapshot
from spotbot.core.models import Candle, MarketType, OrderRequest, Side
from spotbot.strategies.scored_breakout import (
    ScoredBreakoutConfig,
    ScoredOrderRecord,
    atr_quality_score,
    clip01,
    extension_quality_score,
    linear_score,
    rsi_entry_score,
    rsi_health_score,
)

STRATEGY_ID = "AKAH_SCORED_BREAKOUT_V2"
STRATEGY_NAME = "Akah Scored Breakout V2"


@dataclass(frozen=True, slots=True)
class ScoredBreakoutV2Config(ScoredBreakoutConfig):
    # Eligibility is intentionally broader than RD14. Score remains the ranking key.
    entry_threshold: float = 60.0
    breakout_floor: float = 12.0
    risk_floor: float = 8.0
    thesis_critical_threshold: float = 15.0
    thesis_confirmed_threshold: float = 24.0
    thesis_confirmed_bars: int = 2
    profit_protection_activation_r: float = 1.5
    health_exit_cooldown_bars: int = 3
    stop_exit_cooldown_bars: int = 5

    def validate(self) -> None:
        ScoredBreakoutConfig.validate(self)
        if not 0 <= self.thesis_critical_threshold <= self.thesis_confirmed_threshold <= 60:
            raise ValueError("Thesis-health thresholds must be ordered inside [0, 60].")
        if self.thesis_confirmed_bars < 1:
            raise ValueError("Thesis confirmation bars must be positive.")
        if self.profit_protection_activation_r <= 0:
            raise ValueError("Profit-protection activation must be positive.")


@dataclass(slots=True)
class CandidateRecordV2:
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
    raw_entry_score: float = 0.0
    overextension_penalty: float = 0.0
    correlation_penalty: float = 0.0
    market_risk_penalty: float = 0.0
    market_regime: str = "UNKNOWN"


@dataclass(slots=True)
class HealthRecordV2:
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
    thesis_health_score: float
    profit_retention_health_score: float
    profit_floor_r: float | None


@dataclass(slots=True)
class PositionStateV2:
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
    recent_closes: list[float] = field(default_factory=list)


def overextension_penalty(*, extension_z: float, rsi: float, range_ratio: float) -> float:
    """Penalty for chasing a move after several correlated signals become extreme."""
    extension = linear_score(extension_z, 2.0, 5.0, 10.0) if extension_z > 2.0 else 0.0
    rsi_penalty = linear_score(rsi, 80.0, 92.0, 4.0) if rsi > 80.0 else 0.0
    range_penalty = linear_score(range_ratio, 2.5, 4.0, 2.0) if range_ratio > 2.5 else 0.0
    return min(extension + rsi_penalty + range_penalty, 16.0)


def profit_floor_r(mfe_r: float, activation_r: float = 1.5) -> float | None:
    """Minimum R that should remain after a sufficiently large favorable excursion."""
    if not math.isfinite(mfe_r):
        raise ValueError("MFE must be finite.")
    if mfe_r < activation_r:
        return None
    if mfe_r < 3.0:
        return max(0.50, 0.40 * mfe_r)
    if mfe_r < 6.0:
        return max(1.50, 0.55 * mfe_r)
    return max(3.00, 0.65 * mfe_r)


class ScoredBreakoutV2Strategy:
    def __init__(
        self,
        *,
        features: dict[str, dict[datetime, dict[str, float]]],
        cohort: str,
        config: ScoredBreakoutV2Config | None = None,
    ) -> None:
        self.config = config or ScoredBreakoutV2Config()
        self.config.validate()
        self.features = features
        self.cohort = cohort
        self.candidates: list[CandidateRecordV2] = []
        self.health_records: list[HealthRecordV2] = []
        self.orders: list[ScoredOrderRecord] = []
        self._positions: dict[str, PositionStateV2] = {}
        self._pending_entries: dict[str, PositionStateV2] = {}
        self._cooldown: dict[str, int] = {symbol: 0 for symbol in features}
        self._was_open: dict[str, bool] = {symbol: False for symbol in features}
        self._pending_health_exit: dict[str, str] = {}
        self._sequence = 0

    @staticmethod
    def _scaled(score: float, source_cap: float, target_cap: float) -> float:
        return min(max(score / source_cap * target_cap, 0.0), target_cap)

    def _market_regime(self, timestamp: datetime) -> tuple[str, float]:
        btc = self.features.get("BTC/USDT", {}).get(timestamp)
        if btc is None:
            return "UNKNOWN", 6.0
        if btc["close"] > btc["ema_200"] and btc["ema_50"] > btc["ema_200"]:
            return "BULL", 0.0
        if btc["close"] < btc["ema_200"] and btc["ema_50"] < btc["ema_200"]:
            return "BEAR", 10.0
        return "SIDEWAYS_TRANSITION", 4.0

    def _entry_components(
        self,
        values: dict[str, float],
        portfolio: PortfolioSnapshot,
        timestamp: datetime,
    ) -> tuple[tuple[float, float, float, float, float, float], float, float, float, str]:
        atr = values["atr_14"]
        penetration = (values["close"] - values["previous_high_20"]) / atr
        penetration_score = linear_score(penetration, -0.25, 1.0, 12.0)
        close_location = (
            (values["close"] - values["low"]) / (values["high"] - values["low"])
            if values["high"] > values["low"]
            else 0.5
        )
        breakout = min(
            penetration_score
            + linear_score(close_location, 0.50, 0.90, 7.0)
            + linear_score(values["true_range"] / atr, 0.80, 2.0, 6.0),
            25.0,
        )
        trend = min(
            linear_score((values["close"] - values["ema_200"]) / atr, -1.0, 2.0, 5.0)
            + linear_score(values["ema_200_slope_20"], -0.01, 0.03, 5.0)
            + linear_score((values["ema_50"] - values["ema_200"]) / atr, -1.0, 2.0, 5.0),
            15.0,
        )
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
        relative = min(8.0 * values["roc_20_rank"] + 7.0 * values["roc_60_rank"], 15.0)

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

        components = [
            self._scaled(breakout, 25.0, self.config.breakout_weight),
            self._scaled(trend, 15.0, self.config.trend_weight),
            self._scaled(momentum, 15.0, self.config.momentum_weight),
            self._scaled(volume, 10.0, self.config.volume_weight),
            self._scaled(relative, 15.0, self.config.relative_strength_weight),
            self._scaled(risk, 20.0, self.config.risk_execution_weight),
        ]
        raw_total = min(sum(components), 100.0)

        chase_penalty = overextension_penalty(
            extension_z=values["extension_z"],
            rsi=values["rsi_14"],
            range_ratio=values["true_range"] / atr,
        )
        # Apply the chase penalty to the components that generated it, keeping reconciliation exact.
        for index, share in ((0, 0.45), (2, 0.35), (5, 0.20)):
            components[index] = max(0.0, components[index] - chase_penalty * share)

        # Trend and momentum are correlated; impose diminishing returns above a combined 24 points.
        correlation_penalty = max(0.0, components[1] + components[2] - 24.0) * 0.50
        components[2] = max(0.0, components[2] - correlation_penalty)

        regime, market_penalty = self._market_regime(timestamp)
        trend_cut = min(components[1], market_penalty * 0.55)
        components[1] -= trend_cut
        components[4] = max(0.0, components[4] - (market_penalty - trend_cut))

        return (
            (
                components[0],
                components[1],
                components[2],
                components[3],
                components[4],
                components[5],
            ),
            raw_total,
            chase_penalty,
            correlation_penalty,
            regime,
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
        order_id = f"RD15-{self.cohort}-{self._sequence:07d}"
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
        components, raw_total, chase_penalty, correlation_penalty, regime = self._entry_components(
            values, portfolio, candle.timestamp
        )
        total = min(sum(components), 100.0)
        breakout, trend, momentum, volume, relative, risk = components
        market_penalty = max(raw_total - chase_penalty - correlation_penalty - total, 0.0)
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
        else:
            reason = ""
        candidate = CandidateRecordV2(
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
            raw_entry_score=raw_total,
            overextension_penalty=chase_penalty,
            correlation_penalty=correlation_penalty,
            market_risk_penalty=market_penalty,
            market_regime=regime,
        )
        self.candidates.append(candidate)
        if not eligible:
            return None
        signal_id = f"RD15-SIG-{len(self.candidates):08d}"
        candidate.signal_id = signal_id
        stop = values["close"] - self.config.initial_stop_atr * values["atr_14"]
        if stop <= 0 or stop >= values["close"]:
            candidate.entry_eligible = False
            candidate.rejection_reason = "invalid_initial_stop"
            return None
        order = self._record_order(
            candle=candle,
            side=Side.BUY,
            reason="SCORED_BREAKOUT_V2_ENTRY",
            stop_loss=stop,
            signal_id=signal_id,
        )
        candidate.order_id = self.orders[-1].order_id
        self._pending_entries[candle.symbol] = PositionStateV2(
            signal_timestamp=candle.timestamp,
            breakout_level=values["previous_high_20"],
            entry_atr=values["atr_14"],
            initial_stop=stop,
            entry_score=total,
        )
        return order

    @staticmethod
    def _time_score(bars_held: int, current_r: float, new_high_last_10: bool) -> float:
        if bars_held <= 10:
            return 10.0
        if bars_held <= 30:
            if current_r >= 1.0:
                return 10.0
            if current_r >= 0.5:
                return 7.0
            return 4.0 if current_r >= 0 else 1.0
        if new_high_last_10 and current_r >= 1.0:
            return 8.0
        if current_r >= 1.0:
            return 6.0
        if current_r >= 0.5:
            return 4.0
        return max(0.0, 4.0 - (bars_held - 30.0) / 10.0)

    def _health(
        self,
        candle: Candle,
        values: dict[str, float],
        state: PositionStateV2,
    ) -> tuple[float, tuple[float, float, float, float, float, float], float, float, float, float]:
        atr = values["atr_14"]
        state.bars_held += 1
        state.highest_close = max(state.highest_close, candle.close)
        state.recent_closes.append(candle.close)
        state.recent_closes = state.recent_closes[-10:]
        current_r = (candle.close - state.entry_price) / state.initial_risk
        state.mfe_r = max(state.mfe_r, current_r)
        giveback = state.mfe_r - current_r

        structure = min(
            linear_score((candle.close - state.breakout_level) / atr, -1.0, 1.0, 10.0)
            + linear_score((candle.close - values["ema_20"]) / atr, -1.0, 1.0, 6.0)
            + 4.0 * clip01(1.0 - (state.highest_close - candle.close) / atr / 3.0),
            20.0,
        )
        trend = min(
            linear_score((candle.close - values["ema_50"]) / atr, -1.5, 1.5, 7.0)
            + linear_score(values["ema_50_slope_10"], -0.01, 0.02, 5.0)
            + linear_score((values["ema_50"] - values["ema_200"]) / atr, -1.0, 2.0, 6.0),
            18.0,
        )
        momentum = min(
            self._scaled(rsi_health_score(values["rsi_14"]), 8.0, 6.0)
            + linear_score(values["rsi_delta_5"], -7.5, 7.5, 2.0)
            + linear_score(values["roc_10"], -0.05, 0.10, 4.0),
            12.0,
        )
        atr_expansion = atr / state.entry_atr
        volatility = (
            10.0
            if atr_expansion <= 1.2
            else 10.0 * (2.0 - atr_expansion) / 0.8
            if atr_expansion < 2.0
            else 0.0
        )
        thesis = structure + trend + momentum + volatility

        current_r_score = linear_score(current_r, -1.0, 3.0, 15.0)
        retention_score = 15.0 * clip01(1.0 - giveback / max(1.5, state.mfe_r * 0.55))
        r_state = min(current_r_score + retention_score, 30.0)
        new_high = bool(state.recent_closes) and candle.close >= max(state.recent_closes)
        time_score = self._time_score(state.bars_held, current_r, new_high)
        profit_health = r_state + time_score
        components = (structure, trend, momentum, r_state, volatility, time_score)
        return min(sum(components), 100.0), components, current_r, giveback, thesis, profit_health

    def _position_order(
        self,
        candle: Candle,
        values: dict[str, float],
        state: PositionStateV2,
    ) -> OrderRequest | None:
        total, components, current_r, giveback, thesis, profit_health = self._health(
            candle, values, state
        )
        floor = profit_floor_r(state.mfe_r, self.config.profit_protection_activation_r)
        if thesis <= self.config.thesis_confirmed_threshold:
            state.consecutive_low_health_bars += 1
        else:
            state.consecutive_low_health_bars = 0

        if thesis <= self.config.thesis_critical_threshold:
            reason = "THESIS_HEALTH_CRITICAL"
        elif floor is not None and current_r <= floor and giveback >= 0.75:
            reason = "PROFIT_PROTECTION_FLOOR"
        elif thesis <= 18.0 and profit_health <= 15.0:
            reason = "COMBINED_HEALTH_FAILURE"
        elif state.consecutive_low_health_bars >= self.config.thesis_confirmed_bars:
            reason = "THESIS_HEALTH_CONFIRMED_DETERIORATION"
        else:
            reason = ""

        self.health_records.append(
            HealthRecordV2(
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
                exit_triggered=bool(reason),
                exit_reason=reason,
                thesis_health_score=thesis,
                profit_retention_health_score=profit_health,
                profit_floor_r=floor,
            )
        )
        if not reason:
            return None
        self._pending_health_exit[candle.symbol] = reason
        return self._record_order(
            candle=candle,
            side=Side.SELL,
            reason=reason,
            stop_loss=None,
            signal_id=f"RD15-EXIT-{len(self.health_records):08d}",
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
