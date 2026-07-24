from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, sqrt
from statistics import fmean, median
from typing import Literal

import numpy as np
import pandas as pd

OneHourExitMode = Literal[
    "FAST_IMMEDIATE",
    "FAST_CONFIRMATION",
    "SLOW_IMMEDIATE",
    "DISABLED",
]


ExitReason = Literal[
    "STOP",
    "TREND_EXIT",
    "TIME_EXIT",
    "END_OF_DATA",
]


REQUIRED_SIMULATION_COLUMNS = (
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "raw_entry_signal",
    "stop_price",
    "1h_ema_fast",
    "1h_ema_slow",
    "4h_close",
    "4h_ema_fast",
    "1d_close",
    "1d_ema_fast",
)


class TradeSimulationError(RuntimeError):
    pass


class SimulationConfigurationError(
    TradeSimulationError
):
    pass


class SimulationDataError(TradeSimulationError):
    pass


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    initial_cash: float = 1_000.0
    risk_fraction: float = 0.005
    maximum_position_fraction: float = 0.35
    fee_rate: float = 0.001
    slippage_rate: float = 0.0005
    maximum_holding_bars: int = 240

    def __post_init__(self) -> None:
        if (
            not isfinite(self.initial_cash)
            or self.initial_cash <= 0.0
        ):
            raise SimulationConfigurationError(
                "initial_cash must be positive "
                "and finite."
            )

        fractions = {
            "risk_fraction": self.risk_fraction,
            "maximum_position_fraction": (
                self.maximum_position_fraction
            ),
        }

        for name, value in fractions.items():
            if (
                not isfinite(value)
                or value <= 0.0
                or value > 1.0
            ):
                raise SimulationConfigurationError(
                    f"{name} must be within (0, 1]."
                )

        rates = {
            "fee_rate": self.fee_rate,
            "slippage_rate": self.slippage_rate,
        }

        for name, value in rates.items():
            if (
                not isfinite(value)
                or value < 0.0
                or value >= 1.0
            ):
                raise SimulationConfigurationError(
                    f"{name} must be within [0, 1)."
                )

        if self.maximum_holding_bars < 1:
            raise SimulationConfigurationError(
                "maximum_holding_bars must be "
                "at least 1."
            )

    def to_dict(self) -> dict[str, float | int]:
        return {
            "initial_cash": self.initial_cash,
            "risk_fraction": self.risk_fraction,
            "maximum_position_fraction": (
                self.maximum_position_fraction
            ),
            "fee_rate": self.fee_rate,
            "slippage_rate": self.slippage_rate,
            "maximum_holding_bars": (
                self.maximum_holding_bars
            ),
        }


@dataclass(frozen=True, slots=True)
class TradeRecord:
    signal_timestamp: datetime
    entry_bar_timestamp: datetime
    exit_bar_timestamp: datetime
    exit_reason: ExitReason
    entry_base_price: float
    entry_price: float
    exit_base_price: float
    exit_price: float
    stop_price: float
    quantity: float
    entry_notional: float
    entry_fee: float
    exit_fee: float
    gross_pnl: float
    net_pnl: float
    initial_risk: float
    r_multiple: float
    holding_bars: int
    slippage_cost: float

    def to_dict(self) -> dict[str, object]:
        return {
            "signal_timestamp": (
                self.signal_timestamp.isoformat()
            ),
            "entry_bar_timestamp": (
                self.entry_bar_timestamp.isoformat()
            ),
            "exit_bar_timestamp": (
                self.exit_bar_timestamp.isoformat()
            ),
            "exit_reason": self.exit_reason,
            "entry_base_price": (
                self.entry_base_price
            ),
            "entry_price": self.entry_price,
            "exit_base_price": (
                self.exit_base_price
            ),
            "exit_price": self.exit_price,
            "stop_price": self.stop_price,
            "quantity": self.quantity,
            "entry_notional": self.entry_notional,
            "entry_fee": self.entry_fee,
            "exit_fee": self.exit_fee,
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "initial_risk": self.initial_risk,
            "r_multiple": self.r_multiple,
            "holding_bars": self.holding_bars,
            "slippage_cost": self.slippage_cost,
        }


@dataclass(frozen=True, slots=True)
class SimulationMetrics:
    starting_equity: float
    final_equity: float
    total_return: float
    cagr: float | None
    maximum_drawdown: float
    annualized_sharpe: float | None
    trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: float | None
    profit_factor: float | None
    average_net_pnl: float | None
    average_r_multiple: float | None
    median_r_multiple: float | None
    total_fees: float
    total_slippage_cost: float
    exposure_fraction: float
    rejected_entries: int

    def to_dict(self) -> dict[str, object]:
        return {
            "starting_equity": self.starting_equity,
            "final_equity": self.final_equity,
            "total_return": self.total_return,
            "cagr": self.cagr,
            "maximum_drawdown": (
                self.maximum_drawdown
            ),
            "annualized_sharpe": (
                self.annualized_sharpe
            ),
            "trade_count": self.trade_count,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "breakeven_trades": (
                self.breakeven_trades
            ),
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "average_net_pnl": (
                self.average_net_pnl
            ),
            "average_r_multiple": (
                self.average_r_multiple
            ),
            "median_r_multiple": (
                self.median_r_multiple
            ),
            "total_fees": self.total_fees,
            "total_slippage_cost": (
                self.total_slippage_cost
            ),
            "exposure_fraction": (
                self.exposure_fraction
            ),
            "rejected_entries": (
                self.rejected_entries
            ),
        }


@dataclass(frozen=True, slots=True)
class ExitPolicy:
    one_hour_mode: OneHourExitMode = (
        "FAST_IMMEDIATE"
    )
    confirmation_bars: int = 1
    use_four_hour_exit: bool = True
    use_daily_exit: bool = True

    def __post_init__(self) -> None:
        valid_modes = {
            "FAST_IMMEDIATE",
            "FAST_CONFIRMATION",
            "SLOW_IMMEDIATE",
            "DISABLED",
        }

        if self.one_hour_mode not in valid_modes:
            raise SimulationConfigurationError(
                "Unsupported one-hour exit mode: "
                f"{self.one_hour_mode}."
            )

        if self.confirmation_bars < 1:
            raise SimulationConfigurationError(
                "confirmation_bars must be "
                "at least 1."
            )

        if (
            self.one_hour_mode
            == "FAST_CONFIRMATION"
            and self.confirmation_bars < 2
        ):
            raise SimulationConfigurationError(
                "FAST_CONFIRMATION requires "
                "at least two confirmation bars."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "one_hour_mode": self.one_hour_mode,
            "confirmation_bars": (
                self.confirmation_bars
            ),
            "use_four_hour_exit": (
                self.use_four_hour_exit
            ),
            "use_daily_exit": (
                self.use_daily_exit
            ),
        }


def default_exit_policy() -> ExitPolicy:
    return ExitPolicy()

@dataclass(slots=True)
class SimulationResult:
    config: SimulationConfig
    trades: tuple[TradeRecord, ...]
    equity_curve: pd.DataFrame
    metrics: SimulationMetrics


@dataclass(frozen=True, slots=True)
class _PendingEntry:
    signal_timestamp: datetime
    stop_price: float


@dataclass(slots=True)
class _OpenPosition:
    signal_timestamp: datetime
    entry_bar_timestamp: datetime
    entry_bar_index: int
    entry_base_price: float
    entry_price: float
    stop_price: float
    quantity: float
    entry_notional: float
    entry_fee: float
    initial_risk: float
    entry_slippage_cost: float


def default_simulation_config(
) -> SimulationConfig:
    return SimulationConfig()


def _validate_source(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing = set(
        REQUIRED_SIMULATION_COLUMNS
    ).difference(frame.columns)

    if missing:
        raise SimulationDataError(
            "Simulation source is missing "
            f"columns: {sorted(missing)}."
        )

    result = frame.loc[
        :,
        list(REQUIRED_SIMULATION_COLUMNS),
    ].copy()

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
        errors="coerce",
    )

    if bool(
        result["timestamp"].isna().any()
    ):
        raise SimulationDataError(
            "Simulation source contains "
            "invalid timestamps."
        )

    if bool(
        result["timestamp"].duplicated().any()
    ):
        raise SimulationDataError(
            "Simulation source contains "
            "duplicate timestamps."
        )

    if not bool(
        result["timestamp"].is_monotonic_increasing
    ):
        raise SimulationDataError(
            "Simulation source must be "
            "chronologically ordered."
        )

    numeric_columns = [
        column
        for column in (
            REQUIRED_SIMULATION_COLUMNS
        )
        if column
        not in {
            "timestamp",
            "raw_entry_signal",
        }
    ]

    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    numeric_values = result[
        numeric_columns
    ].to_numpy(dtype=float)

    if not bool(
        np.isfinite(numeric_values).all()
    ):
        raise SimulationDataError(
            "Simulation source contains "
            "non-finite numeric values."
        )

    if bool(
        result["raw_entry_signal"]
        .isna()
        .any()
    ):
        raise SimulationDataError(
            "Simulation source contains "
            "missing signal values."
        )

    result["raw_entry_signal"] = (
        result["raw_entry_signal"]
        .astype(bool)
    )

    open_values = result["open"].to_numpy(
        dtype=float
    )
    high_values = result["high"].to_numpy(
        dtype=float
    )
    low_values = result["low"].to_numpy(
        dtype=float
    )
    close_values = result["close"].to_numpy(
        dtype=float
    )

    invalid_ohlc = (
        (open_values <= 0.0)
        | (high_values <= 0.0)
        | (low_values <= 0.0)
        | (close_values <= 0.0)
        | (
            high_values
            < np.maximum(
                open_values,
                close_values,
            )
        )
        | (
            low_values
            > np.minimum(
                open_values,
                close_values,
            )
        )
        | (high_values < low_values)
    )

    if bool(invalid_ohlc.any()):
        raise SimulationDataError(
            "Simulation source contains "
            "invalid OHLC values."
        )

    signal_mask = result[
        "raw_entry_signal"
    ].to_numpy(dtype=bool)

    signal_stops = result.loc[
        signal_mask,
        "stop_price",
    ].to_numpy(dtype=float)

    if bool((signal_stops <= 0.0).any()):
        raise SimulationDataError(
            "Signal stop prices must be positive."
        )

    return result


def _close_position(
    *,
    position: _OpenPosition,
    exit_bar_timestamp: datetime,
    exit_base_price: float,
    exit_reason: ExitReason,
    holding_bars: int,
    config: SimulationConfig,
) -> tuple[TradeRecord, float]:
    exit_price = (
        exit_base_price
        * (1.0 - config.slippage_rate)
    )

    exit_notional = (
        position.quantity * exit_price
    )
    exit_fee = (
        exit_notional * config.fee_rate
    )

    gross_pnl = (
        exit_price - position.entry_price
    ) * position.quantity

    net_pnl = (
        gross_pnl
        - position.entry_fee
        - exit_fee
    )

    r_multiple = (
        net_pnl / position.initial_risk
    )

    exit_slippage_cost = (
        exit_base_price - exit_price
    ) * position.quantity

    trade = TradeRecord(
        signal_timestamp=(
            position.signal_timestamp
        ),
        entry_bar_timestamp=(
            position.entry_bar_timestamp
        ),
        exit_bar_timestamp=(
            exit_bar_timestamp
        ),
        exit_reason=exit_reason,
        entry_base_price=(
            position.entry_base_price
        ),
        entry_price=position.entry_price,
        exit_base_price=exit_base_price,
        exit_price=exit_price,
        stop_price=position.stop_price,
        quantity=position.quantity,
        entry_notional=(
            position.entry_notional
        ),
        entry_fee=position.entry_fee,
        exit_fee=exit_fee,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        initial_risk=(
            position.initial_risk
        ),
        r_multiple=r_multiple,
        holding_bars=holding_bars,
        slippage_cost=(
            position.entry_slippage_cost
            + exit_slippage_cost
        ),
    )

    cash_proceeds = (
        exit_notional - exit_fee
    )

    return trade, cash_proceeds


def _calculate_metrics(
    *,
    config: SimulationConfig,
    trades: list[TradeRecord],
    equity_curve: pd.DataFrame,
    exposed_bars: int,
    rejected_entries: int,
) -> SimulationMetrics:
    equity = pd.to_numeric(
        equity_curve["equity"],
        errors="raise",
    ).astype("float64")

    final_equity = float(
        equity.iloc[-1]
    )

    total_return = (
        final_equity / config.initial_cash
        - 1.0
    )

    running_maximum = equity.cummax()
    drawdowns = (
        equity / running_maximum - 1.0
    )
    maximum_drawdown = float(
        -drawdowns.min()
    )

    timestamps = pd.DatetimeIndex(
        equity_curve["timestamp"]
    )

    elapsed_seconds = float(
        (
            timestamps[-1]
            - timestamps[0]
        ).total_seconds()
    )

    elapsed_years = (
        elapsed_seconds
        / (365.25 * 24.0 * 60.0 * 60.0)
    )

    cagr: float | None = None

    if (
        elapsed_years > 0.0
        and final_equity > 0.0
    ):
        cagr = (
            (
                final_equity
                / config.initial_cash
            )
            ** (1.0 / elapsed_years)
            - 1.0
        )

    returns = equity.pct_change().dropna()
    annualized_sharpe: float | None = None

    if len(returns) >= 2:
        return_standard_deviation = float(
            returns.std(ddof=1)
        )

        if (
            isfinite(
                return_standard_deviation
            )
            and return_standard_deviation
            > 0.0
        ):
            annualized_sharpe = (
                float(returns.mean())
                / return_standard_deviation
                * sqrt(24.0 * 365.25)
            )

    net_results = [
        trade.net_pnl
        for trade in trades
    ]
    r_multiples = [
        trade.r_multiple
        for trade in trades
    ]

    winning_results = [
        value
        for value in net_results
        if value > 0.0
    ]
    losing_results = [
        value
        for value in net_results
        if value < 0.0
    ]

    breakeven_count = (
        len(net_results)
        - len(winning_results)
        - len(losing_results)
    )

    win_rate: float | None = None
    average_net_pnl: float | None = None
    average_r_multiple: float | None = None
    median_r_multiple: float | None = None

    if trades:
        win_rate = (
            len(winning_results)
            / len(trades)
        )
        average_net_pnl = fmean(
            net_results
        )
        average_r_multiple = fmean(
            r_multiples
        )
        median_r_multiple = median(
            r_multiples
        )

    gross_profit = sum(
        winning_results
    )
    gross_loss = abs(
        sum(losing_results)
    )

    profit_factor: float | None = None

    if gross_loss > 0.0:
        profit_factor = (
            gross_profit / gross_loss
        )

    total_fees = sum(
        trade.entry_fee + trade.exit_fee
        for trade in trades
    )

    total_slippage_cost = sum(
        trade.slippage_cost
        for trade in trades
    )

    exposure_fraction = (
        exposed_bars / len(equity_curve)
    )

    return SimulationMetrics(
        starting_equity=(
            config.initial_cash
        ),
        final_equity=final_equity,
        total_return=total_return,
        cagr=cagr,
        maximum_drawdown=(
            maximum_drawdown
        ),
        annualized_sharpe=(
            annualized_sharpe
        ),
        trade_count=len(trades),
        winning_trades=len(
            winning_results
        ),
        losing_trades=len(
            losing_results
        ),
        breakeven_trades=(
            breakeven_count
        ),
        win_rate=win_rate,
        profit_factor=profit_factor,
        average_net_pnl=(
            average_net_pnl
        ),
        average_r_multiple=(
            average_r_multiple
        ),
        median_r_multiple=(
            median_r_multiple
        ),
        total_fees=total_fees,
        total_slippage_cost=(
            total_slippage_cost
        ),
        exposure_fraction=(
            exposure_fraction
        ),
        rejected_entries=(
            rejected_entries
        ),
    )


def simulate_trend_pullback(
    frame: pd.DataFrame,
    *,
    config: SimulationConfig,
    exit_policy: ExitPolicy | None = None,
) -> SimulationResult:
    source = _validate_source(frame)

    active_exit_policy = (
        default_exit_policy()
        if exit_policy is None
        else exit_policy
    )

    timestamps = pd.DatetimeIndex(
        source["timestamp"]
    )
    open_values = source[
        "open"
    ].to_numpy(dtype=float)
    high_values = source[
        "high"
    ].to_numpy(dtype=float)
    low_values = source[
        "low"
    ].to_numpy(dtype=float)
    close_values = source[
        "close"
    ].to_numpy(dtype=float)
    signals = source[
        "raw_entry_signal"
    ].to_numpy(dtype=bool)
    stop_values = source[
        "stop_price"
    ].to_numpy(dtype=float)
    one_hour_fast = source[
        "1h_ema_fast"
    ].to_numpy(dtype=float)
    one_hour_slow = source[
        "1h_ema_slow"
    ].to_numpy(dtype=float)
    four_hour_close = source[
        "4h_close"
    ].to_numpy(dtype=float)
    four_hour_fast = source[
        "4h_ema_fast"
    ].to_numpy(dtype=float)
    daily_close = source[
        "1d_close"
    ].to_numpy(dtype=float)
    daily_fast = source[
        "1d_ema_fast"
    ].to_numpy(dtype=float)

    del high_values

    cash = config.initial_cash
    position: _OpenPosition | None = None
    pending_entry: _PendingEntry | None = None
    pending_exit: ExitReason | None = None

    trades: list[TradeRecord] = []
    equity_records: list[
        dict[str, object]
    ] = []

    rejected_entries = 0
    exposed_bars = 0
    one_hour_failure_streak = 0
    last_index = len(source) - 1

    for index in range(len(source)):
        timestamp = (
            timestamps[index]
            .to_pydatetime()
        )

        if (
            pending_exit is not None
            and position is not None
        ):
            holding_bars = max(
                1,
                index
                - position.entry_bar_index,
            )

            trade, proceeds = (
                _close_position(
                    position=position,
                    exit_bar_timestamp=timestamp,
                    exit_base_price=float(
                        open_values[index]
                    ),
                    exit_reason=pending_exit,
                    holding_bars=holding_bars,
                    config=config,
                )
            )

            cash += proceeds
            trades.append(trade)
            position = None
            pending_exit = None

        if (
            pending_entry is not None
            and position is None
        ):
            one_hour_failure_streak = 0

            entry_base_price = float(
                open_values[index]
            )
            stop_price = (
                pending_entry.stop_price
            )

            entry_price = (
                entry_base_price
                * (
                    1.0
                    + config.slippage_rate
                )
            )

            if (
                entry_base_price <= stop_price
                or entry_price <= stop_price
            ):
                rejected_entries += 1

            else:
                planned_stop_exit_price = (
                    stop_price
                    * (
                        1.0
                        - config.slippage_rate
                    )
                )

                loss_per_unit_at_stop = (
                    entry_price
                    - planned_stop_exit_price
                    + (
                        entry_price
                        * config.fee_rate
                    )
                    + (
                        planned_stop_exit_price
                        * config.fee_rate
                    )
                )

                risk_budget = (
                    cash
                    * config.risk_fraction
                )

                risk_quantity = (
                    risk_budget
                    / loss_per_unit_at_stop
                )

                position_cap_quantity = (
                    cash
                    * (
                        config
                        .maximum_position_fraction
                    )
                    / entry_price
                )

                cash_cap_quantity = (
                    cash
                    / (
                        entry_price
                        * (
                            1.0
                            + config.fee_rate
                        )
                    )
                )

                quantity = min(
                    risk_quantity,
                    position_cap_quantity,
                    cash_cap_quantity,
                )

                if (
                    not isfinite(quantity)
                    or quantity <= 0.0
                ):
                    rejected_entries += 1

                else:
                    entry_notional = (
                        quantity * entry_price
                    )
                    entry_fee = (
                        entry_notional
                        * config.fee_rate
                    )

                    cash -= (
                        entry_notional
                        + entry_fee
                    )

                    initial_risk = (
                        loss_per_unit_at_stop
                        * quantity
                    )

                    position = _OpenPosition(
                        signal_timestamp=(
                            pending_entry
                            .signal_timestamp
                        ),
                        entry_bar_timestamp=(
                            timestamp
                        ),
                        entry_bar_index=index,
                        entry_base_price=(
                            entry_base_price
                        ),
                        entry_price=(
                            entry_price
                        ),
                        stop_price=stop_price,
                        quantity=quantity,
                        entry_notional=(
                            entry_notional
                        ),
                        entry_fee=entry_fee,
                        initial_risk=(
                            initial_risk
                        ),
                        entry_slippage_cost=(
                            (
                                entry_price
                                - entry_base_price
                            )
                            * quantity
                        ),
                    )

            pending_entry = None

        exposed_this_bar = (
            position is not None
        )

        if position is not None:
            stop_exit_base: float | None = None

            if (
                float(open_values[index])
                <= position.stop_price
            ):
                stop_exit_base = float(
                    open_values[index]
                )

            elif (
                float(low_values[index])
                <= position.stop_price
            ):
                stop_exit_base = (
                    position.stop_price
                )

            if stop_exit_base is not None:
                holding_bars = max(
                    1,
                    index
                    - position.entry_bar_index,
                )

                trade, proceeds = (
                    _close_position(
                        position=position,
                        exit_bar_timestamp=(
                            timestamp
                        ),
                        exit_base_price=(
                            stop_exit_base
                        ),
                        exit_reason="STOP",
                        holding_bars=(
                            holding_bars
                        ),
                        config=config,
                    )
                )

                cash += proceeds
                trades.append(trade)
                position = None
                pending_exit = None

        if exposed_this_bar:
            exposed_bars += 1

        if (
            index == last_index
            and position is not None
        ):
            holding_bars = (
                index
                - position.entry_bar_index
                + 1
            )

            trade, proceeds = (
                _close_position(
                    position=position,
                    exit_bar_timestamp=timestamp,
                    exit_base_price=float(
                        close_values[index]
                    ),
                    exit_reason="END_OF_DATA",
                    holding_bars=holding_bars,
                    config=config,
                )
            )

            cash += proceeds
            trades.append(trade)
            position = None
            pending_exit = None

        if position is None:
            position_value = 0.0

        else:
            liquidation_price = (
                float(close_values[index])
                * (
                    1.0
                    - config.slippage_rate
                )
            )

            liquidation_notional = (
                position.quantity
                * liquidation_price
            )

            liquidation_fee = (
                liquidation_notional
                * config.fee_rate
            )

            position_value = (
                liquidation_notional
                - liquidation_fee
            )

        equity_records.append(
            {
                "timestamp": timestamp,
                "cash": cash,
                "position_value": (
                    position_value
                ),
                "equity": (
                    cash + position_value
                ),
            }
        )

        if index == last_index:
            continue

        if position is not None:
            bars_held_at_close = (
                index
                - position.entry_bar_index
                + 1
            )

            below_one_hour_fast = bool(
                float(close_values[index])
                < float(one_hour_fast[index])
            )

            if below_one_hour_fast:
                one_hour_failure_streak += 1
            else:
                one_hour_failure_streak = 0

            one_hour_failed = False

            if (
                active_exit_policy.one_hour_mode
                == "FAST_IMMEDIATE"
            ):
                one_hour_failed = (
                    below_one_hour_fast
                )

            elif (
                active_exit_policy.one_hour_mode
                == "FAST_CONFIRMATION"
            ):
                one_hour_failed = (
                    one_hour_failure_streak
                    >= active_exit_policy
                    .confirmation_bars
                )

            elif (
                active_exit_policy.one_hour_mode
                == "SLOW_IMMEDIATE"
            ):
                one_hour_failed = bool(
                    float(close_values[index])
                    < float(one_hour_slow[index])
                )

            four_hour_failed = (
                active_exit_policy
                .use_four_hour_exit
                and (
                    float(
                        four_hour_close[index]
                    )
                    < float(
                        four_hour_fast[index]
                    )
                )
            )

            daily_failed = (
                active_exit_policy.use_daily_exit
                and (
                    float(daily_close[index])
                    < float(daily_fast[index])
                )
            )

            trend_failed = (
                one_hour_failed
                or four_hour_failed
                or daily_failed
            )

            if trend_failed:
                pending_exit = "TREND_EXIT"

            elif (
                bars_held_at_close
                >= config.maximum_holding_bars
            ):
                pending_exit = "TIME_EXIT"

        elif bool(signals[index]):
            pending_entry = _PendingEntry(
                signal_timestamp=timestamp,
                stop_price=float(
                    stop_values[index]
                ),
            )

    equity_curve = pd.DataFrame.from_records(
        equity_records,
        columns=[
            "timestamp",
            "cash",
            "position_value",
            "equity",
        ],
    )

    if equity_curve.empty:
        raise SimulationDataError(
            "Simulation produced an empty "
            "equity curve."
        )

    metrics = _calculate_metrics(
        config=config,
        trades=trades,
        equity_curve=equity_curve,
        exposed_bars=exposed_bars,
        rejected_entries=rejected_entries,
    )

    return SimulationResult(
        config=config,
        trades=tuple(trades),
        equity_curve=equity_curve,
        metrics=metrics,
    )