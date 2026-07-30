from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from spotbot.core.engine import PortfolioSnapshot
from spotbot.core.models import Candle, MarketType, OrderRequest, Side

STRATEGY_ID = "AKAH_REGIME_MOMENTUM_BREAKOUT_V1"
STRATEGY_NAME = "Akah Regime-Adaptive Momentum Breakout V1"


@dataclass(frozen=True, slots=True)
class RegimeMomentumBreakoutConfig:
    ema_fast_period: int = 50
    ema_slow_period: int = 200
    atr_period: int = 14
    rsi_period: int = 14
    breakout_period: int = 20
    volume_period: int = 20
    rsi_entry_minimum: float = 52.0
    rsi_entry_maximum: float = 75.0
    volume_multiplier: float = 1.10
    atr_fraction_minimum: float = 0.005
    atr_fraction_maximum: float = 0.08
    risk_per_trade: float = 0.01
    initial_stop_atr: float = 2.0
    trailing_activation_r: float = 1.0
    trailing_stop_atr: float = 2.5
    rsi_exit_threshold: float = 45.0
    maximum_holding_bars: int = 30
    enable_long_term_trend: bool = True
    enable_medium_term_alignment: bool = True
    enable_rsi_entry_filter: bool = True
    enable_volume_confirmation: bool = True
    enable_volatility_sanity: bool = True
    enable_trailing_stop: bool = True
    enable_ema50_exit: bool = True
    enable_rsi_exit: bool = True
    enable_time_stop: bool = True

    def validate(self) -> None:
        periods = (
            self.ema_fast_period,
            self.ema_slow_period,
            self.atr_period,
            self.rsi_period,
            self.breakout_period,
            self.volume_period,
            self.maximum_holding_bars,
        )
        if any(period <= 0 for period in periods):
            raise ValueError("All indicator and holding periods must be positive.")
        if self.ema_fast_period >= self.ema_slow_period:
            raise ValueError("Fast EMA period must be shorter than slow EMA period.")
        if not 0 < self.risk_per_trade <= 1:
            raise ValueError("risk_per_trade must be in (0, 1].")
        if self.rsi_entry_minimum > self.rsi_entry_maximum:
            raise ValueError("RSI entry range is invalid.")


@dataclass(frozen=True, slots=True)
class IndicatorSnapshot:
    timestamp: datetime
    close: float
    ema_50: float
    ema_200: float
    atr_14: float
    rsi_14: float
    previous_high_20: float
    previous_volume_mean_20: float
    current_volume: float
    atr_fraction: float


@dataclass(frozen=True, slots=True)
class SignalRecord:
    signal_id: str
    timestamp: datetime
    symbol: str
    side: Side
    reason: str
    indicators: IndicatorSnapshot
    stop_loss: float | None


@dataclass(frozen=True, slots=True)
class StrategyOrderRecord:
    order_id: str
    signal_id: str
    created_at: datetime
    symbol: str
    side: Side
    reason: str
    stop_loss: float | None


class RegimeMomentumBreakoutStrategy:
    """Streaming, close-evaluated strategy with next-bar execution orders."""

    def __init__(
        self,
        *,
        config: RegimeMomentumBreakoutConfig | None = None,
        id_prefix: str = "",
    ) -> None:
        self.config = config or RegimeMomentumBreakoutConfig()
        self.config.validate()
        self.id_prefix = id_prefix
        self.signals: list[SignalRecord] = []
        self.orders: list[StrategyOrderRecord] = []
        self.indicator_history: list[IndicatorSnapshot] = []
        self._highs: deque[float] = deque(maxlen=self.config.breakout_period)
        self._volumes: deque[float] = deque(maxlen=self.config.volume_period)
        self._true_ranges: deque[float] = deque(maxlen=self.config.atr_period)
        self._gains: deque[float] = deque(maxlen=self.config.rsi_period)
        self._losses: deque[float] = deque(maxlen=self.config.rsi_period)
        self._previous_close: float | None = None
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._bar_count = 0
        self._position_was_open = False
        self._entry_price = 0.0
        self._initial_risk = 0.0
        self._highest_close = 0.0
        self._bars_held = 0

    @staticmethod
    def _ema(previous: float | None, value: float, period: int) -> float:
        if previous is None:
            return value
        alpha = 2.0 / (period + 1.0)
        return alpha * value + (1.0 - alpha) * previous

    def _snapshot(self, candle: Candle) -> IndicatorSnapshot | None:
        previous_high = (
            max(self._highs) if len(self._highs) == self.config.breakout_period else None
        )
        previous_volume = (
            sum(self._volumes) / len(self._volumes)
            if len(self._volumes) == self.config.volume_period
            else None
        )

        if self._previous_close is None:
            true_range = candle.high - candle.low
            gain = 0.0
            loss = 0.0
        else:
            true_range = max(
                candle.high - candle.low,
                abs(candle.high - self._previous_close),
                abs(candle.low - self._previous_close),
            )
            change = candle.close - self._previous_close
            gain = max(change, 0.0)
            loss = max(-change, 0.0)

        self._true_ranges.append(true_range)
        self._gains.append(gain)
        self._losses.append(loss)
        self._ema_fast = self._ema(
            self._ema_fast,
            candle.close,
            self.config.ema_fast_period,
        )
        self._ema_slow = self._ema(
            self._ema_slow,
            candle.close,
            self.config.ema_slow_period,
        )
        self._bar_count += 1

        ready = (
            self._bar_count >= self.config.ema_slow_period
            and len(self._true_ranges) == self.config.atr_period
            and len(self._gains) == self.config.rsi_period
            and previous_high is not None
            and previous_volume is not None
        )

        snapshot: IndicatorSnapshot | None = None
        if ready:
            assert previous_high is not None
            assert previous_volume is not None
            atr = sum(self._true_ranges) / len(self._true_ranges)
            average_gain = sum(self._gains) / len(self._gains)
            average_loss = sum(self._losses) / len(self._losses)
            if average_loss == 0:
                rsi = 100.0 if average_gain > 0 else 50.0
            else:
                relative_strength = average_gain / average_loss
                rsi = 100.0 - (100.0 / (1.0 + relative_strength))

            assert self._ema_fast is not None
            assert self._ema_slow is not None
            snapshot = IndicatorSnapshot(
                timestamp=candle.timestamp,
                close=candle.close,
                ema_50=self._ema_fast,
                ema_200=self._ema_slow,
                atr_14=atr,
                rsi_14=rsi,
                previous_high_20=previous_high,
                previous_volume_mean_20=previous_volume,
                current_volume=candle.volume,
                atr_fraction=atr / candle.close,
            )
            self.indicator_history.append(snapshot)

        self._highs.append(candle.high)
        self._volumes.append(candle.volume)
        self._previous_close = candle.close
        return snapshot

    def _record_order(
        self,
        *,
        candle: Candle,
        side: Side,
        reason: str,
        indicators: IndicatorSnapshot,
        stop_loss: float | None = None,
    ) -> OrderRequest:
        sequence = len(self.signals) + 1
        signal_id = f"{self.id_prefix}SIG-{sequence:06d}"
        order_id = f"{self.id_prefix}ORD-{sequence:06d}"
        self.signals.append(
            SignalRecord(
                signal_id=signal_id,
                timestamp=candle.timestamp,
                symbol=candle.symbol,
                side=side,
                reason=reason,
                indicators=indicators,
                stop_loss=stop_loss,
            )
        )
        self.orders.append(
            StrategyOrderRecord(
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

    def _entry_order(
        self,
        *,
        candle: Candle,
        indicators: IndicatorSnapshot,
    ) -> OrderRequest | None:
        conditions = (
            not self.config.enable_long_term_trend or indicators.close > indicators.ema_200,
            not self.config.enable_medium_term_alignment or indicators.ema_50 > indicators.ema_200,
            not self.config.enable_rsi_entry_filter
            or self.config.rsi_entry_minimum <= indicators.rsi_14 <= self.config.rsi_entry_maximum,
            indicators.close > indicators.previous_high_20,
            not self.config.enable_volume_confirmation
            or candle.volume >= self.config.volume_multiplier * indicators.previous_volume_mean_20,
            not self.config.enable_volatility_sanity
            or self.config.atr_fraction_minimum
            <= indicators.atr_fraction
            <= self.config.atr_fraction_maximum,
        )
        if not all(conditions):
            return None

        stop_loss = indicators.close - self.config.initial_stop_atr * indicators.atr_14
        if stop_loss <= 0:
            return None
        return self._record_order(
            candle=candle,
            side=Side.BUY,
            reason="regime_momentum_breakout_entry",
            indicators=indicators,
            stop_loss=stop_loss,
        )

    def _exit_order(
        self,
        *,
        candle: Candle,
        indicators: IndicatorSnapshot,
    ) -> OrderRequest | None:
        self._highest_close = max(self._highest_close, candle.close)
        self._bars_held += 1
        trailing_active = (
            self._initial_risk > 0
            and self._highest_close
            >= self._entry_price + self.config.trailing_activation_r * self._initial_risk
        )
        trailing_stop = self._highest_close - self.config.trailing_stop_atr * indicators.atr_14

        reason: str | None = None
        if self.config.enable_trailing_stop and trailing_active and candle.close <= trailing_stop:
            reason = "trailing_stop_close"
        elif self.config.enable_ema50_exit and candle.close < indicators.ema_50:
            reason = "momentum_failure_close_below_ema50"
        elif self.config.enable_rsi_exit and indicators.rsi_14 < self.config.rsi_exit_threshold:
            reason = "rsi_failure_below_45"
        elif self.config.enable_time_stop and self._bars_held >= self.config.maximum_holding_bars:
            reason = "time_stop_30_bars"

        if reason is None:
            return None
        return self._record_order(
            candle=candle,
            side=Side.SELL,
            reason=reason,
            indicators=indicators,
        )

    def on_candle_close(
        self,
        candle: Candle,
        portfolio: PortfolioSnapshot,
    ) -> list[OrderRequest]:
        indicators = self._snapshot(candle)
        position = portfolio.position(candle.symbol)

        if position is None:
            self._position_was_open = False
            self._entry_price = 0.0
            self._initial_risk = 0.0
            self._highest_close = 0.0
            self._bars_held = 0
            if indicators is None:
                return []
            order = self._entry_order(candle=candle, indicators=indicators)
            return [order] if order is not None else []

        if not self._position_was_open:
            self._position_was_open = True
            self._entry_price = position.average_price
            self._initial_risk = max(position.average_price - position.stop_loss, 0.0)
            self._highest_close = candle.close
            self._bars_held = 0

        if indicators is None:
            return []
        order = self._exit_order(candle=candle, indicators=indicators)
        return [order] if order is not None else []
