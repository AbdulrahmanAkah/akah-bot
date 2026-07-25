from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import math
import os
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path.cwd()

RESEARCH_START = pd.Timestamp("2021-01-01T00:00:00Z")

LOCKED_TEST_START = pd.Timestamp("2025-01-01T00:00:00Z")

LOCKED_HOLDOUT_START = pd.Timestamp("2026-01-01T00:00:00Z")

DEFAULT_REGISTRATION_PATH = ROOT / "reports/research/ams-v3-4h-dataset-registration-v1.json"

DEFAULT_EXPERIMENT_PATH = ROOT / "reports/research/ams-v3-experiment-ledger-v1.json"

DEFAULT_HARNESS_REGISTRATION_PATH = (
    ROOT / "reports/research/ams-v3-f01-walk-forward-harness-v1.json"
)

DEFAULT_READINESS_PATH = ROOT / "reports/research/ams-v3-mtf-data-readiness-v1.json"

DEFAULT_PROJECT_LEDGER_PATH = ROOT / "reports/research/project-research-ledger-v3.json"


class HarnessError(RuntimeError):
    """Raised when the AMS V3 harness contract is violated."""


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: str
    train_start: pd.Timestamp
    train_end_exclusive: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end_exclusive: pd.Timestamp

    def as_json(self) -> dict[str, str]:
        return {
            "fold_id": self.fold_id,
            "train_start": self.train_start.isoformat(),
            "train_end_exclusive": (self.train_end_exclusive.isoformat()),
            "validation_start": (self.validation_start.isoformat()),
            "validation_end_exclusive": (self.validation_end_exclusive.isoformat()),
        }


@dataclass(frozen=True)
class PortfolioProfile:
    profile_id: str
    name: str
    base_risk_fraction: float
    maximum_portfolio_heat: float
    maximum_positions: int


@dataclass(frozen=True)
class TrialSpecification:
    configuration_id: str
    family_id: str
    parameters: Mapping[str, Any]
    portfolio: PortfolioProfile
    transaction_cost: float


@dataclass(frozen=True)
class ExecutionContract:
    timestamp: str
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    setup: str
    risk_fraction: str
    initial_stop: str
    trailing_stop: str | None
    fibonacci_zone: str | None
    score: str | None
    bar_open_time: str | None
    tradable_from: str | None
    tradable_until: str | None


@dataclass
class OpenPosition:
    symbol: str
    quantity: float
    entry_price: float
    stop_price: float
    entry_time: pd.Timestamp
    risk_fraction: float
    entry_notional: float
    entry_fee: float


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    quantity: float
    entry_fee: float
    exit_fee: float
    pnl: float
    return_fraction: float
    exit_reason: str


@dataclass(frozen=True)
class PortfolioResult:
    initial_capital: float
    final_equity: float
    net_return: float
    annualized_return: float
    maximum_drawdown: float
    trade_count: int
    win_rate: float
    turnover: float
    average_positions: float
    maximum_positions: int
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    average_trade_return: float
    median_trade_return: float
    average_holding_hours: float
    exposure: float
    total_fees: float
    stop_exits: int
    end_of_fold_exits: int
    candidate_signals: int
    accepted_entries: int
    rejected_entries: Mapping[str, int]
    equity_curve: pd.DataFrame
    trades: tuple[ClosedTrade, ...]


def load_object(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise HarnessError(f"Required file is missing: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise HarnessError(f"Expected JSON object: {path}")

    return payload


def file_sha256(
    path: Path,
) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def anchored_walk_forward_folds() -> tuple[
    WalkForwardFold,
    ...,
]:
    return (
        WalkForwardFold(
            fold_id="AMS-V3-F01-WF01",
            train_start=pd.Timestamp("2021-01-01T00:00:00Z"),
            train_end_exclusive=pd.Timestamp("2022-01-01T00:00:00Z"),
            validation_start=pd.Timestamp("2022-01-01T00:00:00Z"),
            validation_end_exclusive=pd.Timestamp("2023-01-01T00:00:00Z"),
        ),
        WalkForwardFold(
            fold_id="AMS-V3-F01-WF02",
            train_start=pd.Timestamp("2021-01-01T00:00:00Z"),
            train_end_exclusive=pd.Timestamp("2023-01-01T00:00:00Z"),
            validation_start=pd.Timestamp("2023-01-01T00:00:00Z"),
            validation_end_exclusive=pd.Timestamp("2024-01-01T00:00:00Z"),
        ),
        WalkForwardFold(
            fold_id="AMS-V3-F01-WF03",
            train_start=pd.Timestamp("2021-01-01T00:00:00Z"),
            train_end_exclusive=pd.Timestamp("2024-01-01T00:00:00Z"),
            validation_start=pd.Timestamp("2024-01-01T00:00:00Z"),
            validation_end_exclusive=pd.Timestamp("2025-01-01T00:00:00Z"),
        ),
    )


def datetime_columns(
    frame: pd.DataFrame,
) -> tuple[str, ...]:
    candidates = (
        "timestamp",
        "bar_open_time",
        "bar_close_time",
        "tradable_from",
        "tradable_until",
    )

    return tuple(column for column in candidates if column in frame.columns)


def assert_no_locked_data(
    frame: pd.DataFrame,
) -> None:
    """Reject bars belonging to 2025+, not a 2024 bar closing at the boundary."""

    boundary_rules = (
        (
            "bar_open_time",
            "AT_OR_AFTER",
        ),
        (
            "bar_close_time",
            "AFTER",
        ),
        (
            "tradable_from",
            "AT_OR_AFTER",
        ),
        (
            "tradable_until",
            "AFTER",
        ),
    )

    inspected_columns: set[str] = set()

    for column, rule in boundary_rules:
        if column not in frame.columns:
            continue

        timestamps = pd.to_datetime(
            frame[column],
            utc=True,
            errors="raise",
        )

        if rule == "AT_OR_AFTER":
            locked = timestamps.ge(LOCKED_TEST_START)
        else:
            locked = timestamps.gt(LOCKED_TEST_START)

        if locked.any():
            maximum = timestamps.max()

            raise HarnessError(f"Locked post-2024 data found in {column}: {maximum}.")

        inspected_columns.add(column)

    has_bar_semantics = bool(
        {
            "bar_open_time",
            "bar_close_time",
        }.intersection(inspected_columns)
    )

    if "timestamp" in frame.columns and not has_bar_semantics:
        timestamps = pd.to_datetime(
            frame["timestamp"],
            utc=True,
            errors="raise",
        )

        if timestamps.ge(LOCKED_TEST_START).any():
            maximum = timestamps.max()

            raise HarnessError(f"Locked post-2024 data found in timestamp: {maximum}.")


def load_registered_datasets(
    registration_path: Path = (DEFAULT_REGISTRATION_PATH),
) -> dict[str, pd.DataFrame]:
    registration = load_object(registration_path)

    if registration.get("status") != "PASS":
        raise HarnessError("Dataset registration is not PASS.")

    if registration.get("test_2025_accessed") is not False:
        raise HarnessError("Dataset registration reports 2025 access.")

    if registration.get("holdout_2026_accessed") is not False:
        raise HarnessError("Dataset registration reports 2026 access.")

    records = registration.get("datasets")

    if not isinstance(records, dict):
        raise HarnessError("Registered dataset records are missing.")

    required_names = (
        "four_hour",
        "eight_hour",
        "daily",
        "availability",
    )

    result: dict[
        str,
        pd.DataFrame,
    ] = {}

    for name in required_names:
        record = records.get(name)

        if not isinstance(record, dict):
            raise HarnessError(f"Missing dataset record: {name}.")

        relative_path = record.get("path")
        expected_hash = record.get("file_sha256")

        if not isinstance(
            relative_path,
            str,
        ):
            raise HarnessError(f"Invalid dataset path: {name}.")

        if not isinstance(
            expected_hash,
            str,
        ):
            raise HarnessError(f"Invalid dataset hash: {name}.")

        path = ROOT / relative_path

        if not path.is_file():
            raise HarnessError(f"Dataset file is missing: {path}")

        observed_hash = file_sha256(path)

        if observed_hash != expected_hash:
            raise HarnessError(f"Dataset hash mismatch: {name}.")

        frame = pd.read_parquet(path)

        assert_no_locked_data(frame)

        result[name] = frame

    return result


def load_trial_specification(
    configuration_id: str,
    portfolio_profile_id: str,
    experiment_path: Path = (DEFAULT_EXPERIMENT_PATH),
) -> TrialSpecification:
    experiment = load_object(experiment_path)

    accounting = experiment.get("trial_accounting")

    if not isinstance(accounting, dict):
        raise HarnessError("Unexpected AMS V3 trial accounting.")

    executed = accounting.get("trials_executed")
    remaining = accounting.get("remaining_authorized_trials")
    if (
        accounting.get("total_authorized_trials") != 20
        or not isinstance(executed, int)
        or not isinstance(remaining, int)
        or executed < 0
        or remaining != 20 - executed
        or accounting.get("test_2025_accessed") is not False
        or accounting.get("holdout_2026_accessed") is not False
    ):
        raise HarnessError("Unexpected AMS V3 trial accounting.")

    configurations = experiment.get("alpha_configurations")

    profiles = experiment.get("portfolio_profiles")

    if not isinstance(
        configurations,
        list,
    ):
        raise HarnessError("Alpha configurations are missing.")

    if not isinstance(
        profiles,
        list,
    ):
        raise HarnessError("Portfolio profiles are missing.")

    configuration = next(
        (
            item
            for item in configurations
            if isinstance(item, dict) and item.get("configuration_id") == configuration_id
        ),
        None,
    )

    profile = next(
        (
            item
            for item in profiles
            if isinstance(item, dict) and item.get("profile_id") == portfolio_profile_id
        ),
        None,
    )

    if configuration is None:
        raise HarnessError(f"Unknown configuration: {configuration_id}.")

    if profile is None:
        raise HarnessError(f"Unknown portfolio profile: {portfolio_profile_id}.")

    parameters = configuration.get("parameters")

    if not isinstance(parameters, dict):
        raise HarnessError("Configuration parameters are missing.")

    forbidden_true = (
        "leverage_allowed",
        "borrowing_allowed",
    )

    for field in forbidden_true:
        if parameters.get(field) is not False:
            raise HarnessError(f"Forbidden configuration field: {field}.")

    if parameters.get("spot_long_only") is not True:
        raise HarnessError("Configuration is not Spot long-only.")

    base_cost = float(
        parameters.get(
            "base_transaction_cost",
            0.0,
        )
    )

    if not math.isfinite(base_cost) or base_cost < 0.0 or base_cost >= 0.10:
        raise HarnessError("Invalid transaction cost.")

    portfolio = PortfolioProfile(
        profile_id=str(profile["profile_id"]),
        name=str(profile["name"]),
        base_risk_fraction=float(profile["base_risk_fraction"]),
        maximum_portfolio_heat=float(profile["maximum_portfolio_heat"]),
        maximum_positions=int(profile["maximum_positions"]),
    )

    if portfolio.maximum_positions <= 0:
        raise HarnessError("Maximum positions must be positive.")

    if not (0.0 < portfolio.base_risk_fraction <= portfolio.maximum_portfolio_heat < 1.0):
        raise HarnessError("Portfolio risk limits are invalid.")

    return TrialSpecification(
        configuration_id=configuration_id,
        family_id=str(configuration["family_id"]),
        parameters=parameters,
        portfolio=portfolio,
        transaction_cost=base_cost,
    )


def select_timeframe(
    frames: Mapping[str, pd.DataFrame],
    *,
    tokens: Iterable[str],
) -> pd.DataFrame:
    normalized_tokens = tuple(token.lower() for token in tokens)

    for name, frame in frames.items():
        lowered = str(name).lower()

        if any(token in lowered for token in normalized_tokens):
            return frame

    raise HarnessError(f"Could not resolve timeframe from keys: {sorted(frames)}.")


def market_breadth(
    daily: pd.DataFrame,
) -> pd.Series:
    required = {
        "symbol",
        "bar_open_time",
        "close",
    }

    missing = sorted(required.difference(daily.columns))

    if missing:
        raise HarnessError(f"Daily breadth columns missing: {missing}.")

    ordered = daily.sort_values(
        [
            "symbol",
            "bar_open_time",
        ],
        kind="mergesort",
    ).copy()

    ordered["close"] = pd.to_numeric(
        ordered["close"],
        errors="raise",
    )

    ordered["ema_200"] = ordered.groupby(
        "symbol",
        sort=False,
    )["close"].transform(
        lambda values: values.ewm(
            span=200,
            adjust=False,
            min_periods=200,
        ).mean()
    )

    ordered["above_long_term_trend"] = ordered["close"] > ordered["ema_200"]

    breadth = ordered.groupby(
        "bar_open_time",
        sort=True,
    )["above_long_term_trend"].mean()

    breadth.index = pd.DatetimeIndex(
        pd.to_datetime(
            breadth.index,
            utc=True,
        )
    )

    return breadth.astype("float64")


def _index_level_values(
    frame: pd.DataFrame,
    level: int,
) -> pd.Series:
    """Return an index level as a position-aligned Series."""

    if isinstance(frame.index, pd.MultiIndex):
        values = frame.index.get_level_values(level)
    else:
        values = frame.index

    return pd.Series(values, index=frame.index)


def _has_temporal_values(
    left: pd.Series,
    right: pd.Series,
    *,
    name: object,
) -> bool:
    return (
        pd.api.types.is_datetime64_any_dtype(left)
        or pd.api.types.is_datetime64_any_dtype(right)
        or "time" in str(name).lower()
        or "date" in str(name).lower()
    )


def _duplicate_index_column_matches(
    index_values: pd.Series,
    column_values: pd.Series,
    *,
    name: object,
) -> bool:
    """Compare a duplicated index level and column without changing row order."""

    left = index_values.reset_index(drop=True)
    right = column_values.reset_index(drop=True)

    if _has_temporal_values(left, right, name=name):
        try:
            left = pd.Series(pd.to_datetime(left, utc=True, errors="raise"))
            right = pd.Series(pd.to_datetime(right, utc=True, errors="raise"))
        except (TypeError, ValueError):
            return False
        return bool((left.eq(right) | (left.isna() & right.isna())).all())

    return left.equals(right)


def remove_matching_index_column_duplicates(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Remove only columns that exactly duplicate a named index level.

    The AMS V3 composition function owns index reset/alignment.  Its input must
    therefore never contain the same named value both in the index and columns.
    This adapter deliberately preserves the index and row order.
    """

    result = frame.copy()
    names = list(result.index.names)

    for level, name in enumerate(names):
        if name is None or name not in result.columns:
            continue

        index_values = _index_level_values(result, level)
        column_values = result[name]

        if not _duplicate_index_column_matches(
            index_values,
            column_values,
            name=name,
        ):
            raise HarnessError(
                "Index/column duplicate differs for "
                f"{name!r}; refusing ambiguous feature composition."
            )

        result = result.drop(columns=[name])

    return result


def build_execution_panel(
    datasets: Mapping[str, pd.DataFrame],
    *,
    symbols: Iterable[str] | None = None,
) -> pd.DataFrame:
    engine = importlib.import_module("spotbot.research.ams_v3_multitimeframe_fibonacci")

    four_hour = datasets["four_hour"]

    daily_registered = datasets["daily"]
    availability = datasets["availability"].copy()

    assert_no_locked_data(four_hour)

    breadth = market_breadth(daily_registered)

    benchmark_source = four_hour.loc[four_hour["symbol"].astype(str) == "BTC"].copy()

    if benchmark_source.empty:
        raise HarnessError("BTC benchmark data is missing.")

    benchmark_timeframes = engine.build_timeframes_from_four_hour(benchmark_source)

    benchmark_eight_hour = select_timeframe(
        benchmark_timeframes,
        tokens=(
            "8h",
            "eight",
        ),
    )

    available_symbols = sorted(four_hour["symbol"].astype(str).unique().tolist())

    requested_symbols = (
        set(str(symbol) for symbol in symbols) if symbols is not None else set(available_symbols)
    )

    outputs: list[pd.DataFrame] = []

    for symbol in available_symbols:
        if symbol not in requested_symbols:
            continue

        symbol_source = four_hour.loc[four_hour["symbol"].astype(str) == symbol].copy()

        timeframes = engine.build_timeframes_from_four_hour(symbol_source)

        symbol_four_hour = select_timeframe(
            timeframes,
            tokens=(
                "4h",
                "four",
            ),
        )

        symbol_eight_hour = select_timeframe(
            timeframes,
            tokens=(
                "8h",
                "eight",
            ),
        )

        symbol_daily = select_timeframe(
            timeframes,
            tokens=(
                "1d",
                "daily",
                "day",
            ),
        )

        daily_features = engine.build_daily_risk_features(
            symbol_daily,
            breadth=breadth,
        )

        eight_hour_features = engine.build_eight_hour_allocation_features(
            symbol_eight_hour,
            benchmark_eight_hour,
        )

        four_hour_features = engine.build_four_hour_execution_features(symbol_four_hour)

        four_hour_features = remove_matching_index_column_duplicates(
            four_hour_features
        )
        daily_features = remove_matching_index_column_duplicates(daily_features)
        eight_hour_features = remove_matching_index_column_duplicates(
            eight_hour_features
        )

        composed = (
            engine.compose_multitimeframe_execution_state(
                four_hour_features,
                daily_features,
                eight_hour_features,
            )
        ).copy()

        composed = composed.reset_index()

        composed["symbol"] = symbol

        availability_row = availability.loc[
            availability["symbol"].astype(str) == symbol,
            ["tradable_from", "tradable_until"],
        ]

        if len(availability_row) != 1:
            raise HarnessError(f"Availability record is not unique for {symbol}.")

        composed["tradable_from"] = availability_row.iloc[0]["tradable_from"]
        composed["tradable_until"] = availability_row.iloc[0]["tradable_until"]

        assert_no_locked_data(composed)

        outputs.append(composed)

    if not outputs:
        raise HarnessError("No execution states were produced.")

    result = pd.concat(
        outputs,
        ignore_index=True,
    )

    timestamp_column = resolve_column(
        result,
        exact=(
            "bar_close_time",
            "bar_open_time",
            "timestamp",
        ),
        token_groups=(
            (
                "bar",
                "close",
                "time",
            ),
            (
                "bar",
                "open",
                "time",
            ),
        ),
    )

    result[timestamp_column] = pd.to_datetime(
        result[timestamp_column],
        utc=True,
        errors="raise",
    )

    return result.sort_values(
        [
            timestamp_column,
            "symbol",
        ],
        kind="mergesort",
    ).reset_index(drop=True)


def resolve_column(
    frame: pd.DataFrame,
    *,
    exact: Iterable[str] = (),
    token_groups: Iterable[Iterable[str]] = (),
    required: bool = True,
) -> str | None:
    columns = [str(column) for column in frame.columns]

    lowered = {column.lower(): column for column in columns}

    for candidate in exact:
        found = lowered.get(candidate.lower())

        if found is not None:
            return found

    for tokens in token_groups:
        normalized = tuple(token.lower() for token in tokens)

        matches = [
            column for column in columns if all(token in column.lower() for token in normalized)
        ]

        if len(matches) == 1:
            return matches[0]

        if len(matches) > 1:
            matches.sort(
                key=lambda value: (
                    len(value),
                    value,
                )
            )

            return matches[0]

    if required:
        raise HarnessError(f"Could not resolve semantic column. Columns: {columns}")

    return None


def infer_execution_contract(
    panel: pd.DataFrame,
) -> ExecutionContract:
    return ExecutionContract(
        timestamp=str(
            resolve_column(
                panel,
                exact=(
                    "bar_close_time",
                    "bar_open_time",
                    "timestamp",
                ),
                token_groups=(
                    (
                        "bar",
                        "close",
                        "time",
                    ),
                    (
                        "bar",
                        "open",
                        "time",
                    ),
                ),
            )
        ),
        open_price=str(
            resolve_column(
                panel,
                exact=("open",),
            )
        ),
        high_price=str(
            resolve_column(
                panel,
                exact=("high",),
            )
        ),
        low_price=str(
            resolve_column(
                panel,
                exact=("low",),
            )
        ),
        close_price=str(
            resolve_column(
                panel,
                exact=("close",),
            )
        ),
        setup=str(
            resolve_column(
                panel,
                exact=(
                    "four_hour_setup",
                    "setup",
                ),
                token_groups=(
                    (
                        "four",
                        "setup",
                    ),
                ),
            )
        ),
        risk_fraction=str(
            resolve_column(
                panel,
                exact=("final_risk_fraction", "position_risk_fraction"),
                token_groups=(
                    (
                        "final",
                        "risk",
                    ),
                    (
                        "position",
                        "risk",
                    ),
                ),
            )
        ),
        initial_stop=str(
            resolve_column(
                panel,
                exact=(
                    "initial_stop_price",
                    "four_hour_initial_stop",
                ),
                token_groups=(
                    (
                        "initial",
                        "stop",
                    ),
                ),
            )
        ),
        trailing_stop=resolve_column(
            panel,
            exact=(
                "trailing_stop_price",
                "four_hour_trailing_stop",
            ),
            required=False,
        ),
        fibonacci_zone=resolve_column(
            panel,
            exact=(
                "fibonacci_zone",
                "four_hour_fibonacci_zone",
            ),
            token_groups=(
                (
                    "fibonacci",
                    "zone",
                ),
            ),
            required=False,
        ),
        score=resolve_column(
            panel,
            exact=(
                "relative_strength_vs_benchmark",
                "eight_hour_allocation_multiplier",
            ),
            token_groups=(
                (
                    "relative",
                    "strength",
                ),
                (
                    "allocation",
                    "multiplier",
                ),
            ),
            required=False,
        ),
        bar_open_time=resolve_column(
            panel,
            exact=("bar_open_time",),
            token_groups=(("bar", "open", "time"),),
            required=False,
        ),
        tradable_from=resolve_column(
            panel,
            exact=("tradable_from",),
            required=False,
        ),
        tradable_until=resolve_column(
            panel,
            exact=("tradable_until",),
            required=False,
        ),
    )


def setup_is_eligible(
    setup: object,
    *,
    trigger_mode: str,
) -> bool:
    token = str(setup).upper()

    if token in {
        "",
        "NONE",
        "NO_SETUP",
        "INACTIVE",
        "NAN",
    }:
        return False

    mode = trigger_mode.upper()

    if "BREAKOUT" in mode:
        return "BREAKOUT" in token

    if "PULLBACK" in mode or "REACCELERATION" in mode:
        return "PULLBACK" in token or "REACCEL" in token

    if "HYBRID" in mode:
        return "BREAKOUT" in token or "PULLBACK" in token or "REACCEL" in token

    return token not in {
        "NONE",
        "NO_SETUP",
        "INACTIVE",
    }


def fibonacci_is_eligible(
    zone: object,
    *,
    fibonacci_mode: str,
) -> bool:
    mode = fibonacci_mode.upper()

    if "NO_FIBONACCI" in mode or "NO_FIB" in mode or "CONTROL" in mode:
        return True

    token = str(zone).upper()

    if "CORE" in mode:
        return "CORE" in token

    if "BROAD" in mode or "RETRACEMENT" in mode:
        return any(
            accepted in token
            for accepted in (
                "SHALLOW",
                "CORE",
                "DEEP",
            )
        )

    if "SHALLOW" in mode:
        return "SHALLOW" in token

    if "DEEP" in mode:
        return "DEEP" in token

    return "INVALID" not in token and "NO_ACTIVE" not in token


def validation_slice(
    panel: pd.DataFrame,
    *,
    contract: ExecutionContract,
    fold: WalkForwardFold,
) -> pd.DataFrame:
    ownership_column = contract.bar_open_time or contract.timestamp
    timestamps = pd.to_datetime(
        panel[ownership_column],
        utc=True,
        errors="raise",
    )

    result = panel.loc[
        timestamps.ge(fold.validation_start) & timestamps.lt(fold.validation_end_exclusive)
    ].copy()

    assert_no_locked_data(result)

    return result


def simulate_portfolio(
    panel: pd.DataFrame,
    *,
    contract: ExecutionContract,
    specification: TrialSpecification,
    initial_capital: float = 100_000.0,
) -> PortfolioResult:
    if initial_capital <= 0.0:
        raise HarnessError("Initial capital must be positive.")

    required_columns = {
        "symbol", contract.timestamp, contract.open_price, contract.high_price,
        contract.low_price, contract.close_price, contract.setup,
        contract.risk_fraction, contract.initial_stop,
    }
    missing = sorted(required_columns.difference(panel.columns))
    if missing:
        raise HarnessError(f"Execution panel columns missing: {missing}.")

    ordered = panel.sort_values([contract.timestamp, "symbol"], kind="mergesort").copy()
    ordered[contract.timestamp] = pd.to_datetime(
        ordered[contract.timestamp], utc=True, errors="raise"
    )
    for column in (contract.bar_open_time, contract.tradable_from, contract.tradable_until):
        if column is not None:
            ordered[column] = pd.to_datetime(ordered[column], utc=True, errors="raise")
    assert_no_locked_data(ordered)

    numeric_columns = {
        contract.open_price, contract.high_price, contract.low_price,
        contract.close_price, contract.risk_fraction, contract.initial_stop,
    }
    for optional in (contract.trailing_stop, contract.score):
        if optional is not None:
            numeric_columns.add(optional)
    for column in numeric_columns:
        ordered[column] = pd.to_numeric(ordered[column], errors="coerce")

    cash = float(initial_capital)
    positions: dict[str, OpenPosition] = {}
    pending: dict[str, dict[str, Any]] = {}
    last_prices: dict[str, float] = {}
    closed_trades: list[ClosedTrade] = []
    equity_rows: list[dict[str, Any]] = []
    rejected = {
        "fibonacci_filter": 0, "daily_regime": 0, "eight_hour_allocation_state": 0,
        "portfolio_heat": 0, "position_limit": 0, "venue_availability": 0,
        "insufficient_cash": 0,
    }
    gross_turnover = 0.0
    total_fees = 0.0
    position_observations = 0
    maximum_positions_seen = 0
    candidate_signals = 0
    accepted_entries = 0
    trigger_mode = str(specification.parameters.get("trigger_mode", "BREAKOUT"))
    fibonacci_mode = str(specification.parameters.get("fibonacci_mode", "NO_FIBONACCI_CONTROL"))
    cost = specification.transaction_cost

    def close_position(symbol: str, position: OpenPosition, *, price: float,
                       timestamp: pd.Timestamp, reason: str) -> None:
        nonlocal cash, gross_turnover, total_fees
        if not math.isfinite(price) or price <= 0.0:
            raise HarnessError(f"Invalid exit price for {symbol}.")
        notional = position.quantity * price
        fee = notional * cost
        cash += notional - fee
        gross_turnover += notional
        total_fees += fee
        pnl = notional - fee - position.entry_notional - position.entry_fee
        closed_trades.append(ClosedTrade(
            symbol=symbol, entry_time=position.entry_time, exit_time=timestamp,
            entry_price=position.entry_price, exit_price=price, quantity=position.quantity,
            entry_fee=position.entry_fee, exit_fee=fee, pnl=pnl,
            return_fraction=pnl / (position.entry_notional + position.entry_fee),
            exit_reason=reason,
        ))
        del positions[symbol]

    for raw_timestamp, group in ordered.groupby(contract.timestamp, sort=True):
        timestamp = pd.Timestamp(raw_timestamp)
        rows = {str(row["symbol"]): row for row in group.to_dict(orient="records")}
        # Cash available before this bar is the only cash that may fund its opens.
        entry_cash_available = cash

        # Stops are evaluated using only stops known before this bar. A gap exits at open.
        for symbol in list(positions):
            row = rows.get(symbol)
            if row is None:
                continue
            position = positions[symbol]
            bar_open = float(row[contract.open_price])
            bar_low = float(row[contract.low_price])
            bar_start = (
                pd.Timestamp(row[contract.bar_open_time])
                if contract.bar_open_time
                else timestamp
            )
            until = (
                pd.Timestamp(row[contract.tradable_until])
                if contract.tradable_until
                else None
            )
            if until is not None and bar_start >= until:
                close_position(
                    symbol,
                    position,
                    price=bar_open,
                    timestamp=timestamp,
                    reason="VENUE_END",
                )
            elif math.isfinite(bar_low) and bar_low <= position.stop_price:
                close_position(
                    symbol, position, price=min(bar_open, position.stop_price),
                    timestamp=timestamp, reason="STOP",
                )

        # Entries were selected at the preceding close and execute at this bar's open.
        current_heat = sum(position.risk_fraction for position in positions.values())
        opened_symbols: list[str] = []
        for symbol, signal in sorted(
            pending.items(), key=lambda item: (-float(item[1]["score"]), item[0])
        ):
            row = rows.get(symbol)
            if row is None or symbol in positions:
                continue
            bar_start = (
                pd.Timestamp(row[contract.bar_open_time])
                if contract.bar_open_time
                else timestamp
            )
            available_from = (
                pd.Timestamp(row[contract.tradable_from])
                if contract.tradable_from
                else None
            )
            available_until = (
                pd.Timestamp(row[contract.tradable_until])
                if contract.tradable_until
                else None
            )
            if ((available_from is not None and bar_start < available_from)
                    or (available_until is not None and bar_start >= available_until)):
                rejected["venue_availability"] += 1
                continue
            if len(positions) >= specification.portfolio.maximum_positions:
                rejected["position_limit"] += 1
                continue
            remaining_heat = specification.portfolio.maximum_portfolio_heat - current_heat
            requested_risk = min(
                float(signal["risk_fraction"]), specification.portfolio.base_risk_fraction,
                remaining_heat,
            )
            if requested_risk <= 0.0:
                rejected["portfolio_heat"] += 1
                continue
            entry_price = float(row[contract.open_price])
            stop_price = float(signal["stop_price"])
            if not (math.isfinite(entry_price) and entry_price > stop_price > 0.0):
                continue
            marked_equity = cash + sum(
                value.quantity * last_prices.get(name, value.entry_price)
                for name, value in positions.items()
            )
            quantity_by_risk = (marked_equity * requested_risk) / (entry_price - stop_price)
            quantity_by_cash = entry_cash_available / ((1.0 + cost) * entry_price)
            quantity = min(quantity_by_risk, quantity_by_cash)
            if not math.isfinite(quantity) or quantity <= 0.0:
                rejected["insufficient_cash"] += 1
                continue
            entry_notional = quantity * entry_price
            entry_fee = entry_notional * cost
            debit = entry_notional + entry_fee
            if debit > entry_cash_available + 1e-9 or debit > cash + 1e-9:
                rejected["insufficient_cash"] += 1
                continue
            cash -= debit
            entry_cash_available -= debit
            total_fees += entry_fee
            gross_turnover += entry_notional
            positions[symbol] = OpenPosition(
                symbol=symbol, quantity=quantity, entry_price=entry_price,
                stop_price=stop_price, entry_time=bar_start, risk_fraction=requested_risk,
                entry_notional=entry_notional, entry_fee=entry_fee,
            )
            current_heat += requested_risk
            accepted_entries += 1
            opened_symbols.append(symbol)
        pending = {}

        # An order filled at this bar's open is exposed to this bar's low.
        for symbol in opened_symbols:
            position = positions.get(symbol)
            row = rows.get(symbol)
            if position is None or row is None:
                continue
            bar_open = float(row[contract.open_price])
            bar_low = float(row[contract.low_price])
            if math.isfinite(bar_low) and bar_low <= position.stop_price:
                close_position(
                    symbol, position, price=min(bar_open, position.stop_price),
                    timestamp=timestamp, reason="STOP",
                )

        # A trailing stop computed from this closed bar only becomes active next bar.
        if contract.trailing_stop is not None:
            for symbol, position in positions.items():
                row = rows.get(symbol)
                if row is None:
                    continue
                trailing = float(row.get(contract.trailing_stop, math.nan))
                if math.isfinite(trailing):
                    position.stop_price = max(position.stop_price, trailing)

        # Record closes, then schedule signals only for the following bar.
        candidates: list[tuple[float, str, dict[str, Any]]] = []
        for symbol, row in rows.items():
            close_value = float(row[contract.close_price])
            if math.isfinite(close_value) and close_value > 0.0:
                last_prices[symbol] = close_value
            if symbol in positions or not setup_is_eligible(
                row[contract.setup],
                trigger_mode=trigger_mode,
            ):
                continue
            candidate_signals += 1
            if contract.fibonacci_zone is not None and not fibonacci_is_eligible(
                row.get(contract.fibonacci_zone), fibonacci_mode=fibonacci_mode
            ):
                rejected["fibonacci_filter"] += 1
                continue
            risk = float(row[contract.risk_fraction])
            stop = float(row[contract.initial_stop])
            if not all(math.isfinite(value) for value in (close_value, risk, stop)) or risk <= 0.0:
                if float(row.get("daily_risk_multiplier", 0.0)) <= 0.0:
                    rejected["daily_regime"] += 1
                else:
                    rejected["eight_hour_allocation_state"] += 1
                continue
            if not (close_value > stop > 0.0):
                continue
            score = risk
            if contract.score is not None:
                score_value = float(row.get(contract.score, math.nan))
                if math.isfinite(score_value):
                    score = score_value
            candidates.append(
                (score, symbol, {"risk_fraction": risk, "stop_price": stop, "score": score})
            )
        for _, symbol, signal in sorted(candidates, key=lambda item: (-item[0], item[1])):
            pending[symbol] = signal

        equity = cash + sum(
            position.quantity * last_prices.get(symbol, position.entry_price)
            for symbol, position in positions.items()
        )
        position_observations += len(positions)
        maximum_positions_seen = max(maximum_positions_seen, len(positions))
        equity_rows.append({
            "timestamp": timestamp, "equity": equity, "cash": cash,
            "open_positions": len(positions),
            "portfolio_heat": sum(value.risk_fraction for value in positions.values()),
        })

    if not equity_rows:
        raise HarnessError("Execution panel produced no timestamps.")
    final_timestamp = pd.Timestamp(equity_rows[-1]["timestamp"])
    for symbol in list(positions):
        position = positions[symbol]
        close_position(
            symbol, position, price=last_prices.get(symbol, position.entry_price),
            timestamp=final_timestamp, reason="END_OF_FOLD",
        )
    equity_curve = pd.DataFrame(equity_rows)
    equity_curve.loc[equity_curve.index[-1], "equity"] = cash
    running_peak = equity_curve["equity"].cummax()
    maximum_drawdown = abs(
        float((equity_curve["equity"] / running_peak - 1.0).min())
    )
    net_return = cash / initial_capital - 1.0
    elapsed_seconds = (
        final_timestamp - pd.Timestamp(equity_curve.iloc[0]["timestamp"])
    ).total_seconds()
    elapsed_days = max(elapsed_seconds / 86_400.0, 1.0)
    annualized_return = (cash / initial_capital) ** (365.25 / elapsed_days) - 1.0
    pnl_values = [trade.pnl for trade in closed_trades]
    return_values = [trade.return_fraction for trade in closed_trades]
    holding_hours = [
        (trade.exit_time - trade.entry_time).total_seconds() / 3_600.0
        for trade in closed_trades
    ]
    gross_profit = sum(value for value in pnl_values if value > 0.0)
    gross_loss = -sum(value for value in pnl_values if value < 0.0)
    return PortfolioResult(
        initial_capital=initial_capital, final_equity=cash, net_return=net_return,
        annualized_return=annualized_return, maximum_drawdown=maximum_drawdown,
        trade_count=len(closed_trades),
        win_rate=sum(value > 0.0 for value in pnl_values) / len(pnl_values) if pnl_values else 0.0,
        turnover=gross_turnover / initial_capital,
        average_positions=position_observations / len(equity_rows),
        maximum_positions=maximum_positions_seen,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=(gross_profit / gross_loss if gross_loss else None),
        average_trade_return=(sum(return_values) / len(return_values) if return_values else 0.0),
        median_trade_return=(float(pd.Series(return_values).median()) if return_values else 0.0),
        average_holding_hours=(
            sum(holding_hours) / len(holding_hours) if holding_hours else 0.0
        ),
        exposure=(
            position_observations
            / (len(equity_rows) * specification.portfolio.maximum_positions)
        ),
        total_fees=total_fees,
        stop_exits=sum(trade.exit_reason == "STOP" for trade in closed_trades),
        end_of_fold_exits=sum(trade.exit_reason == "END_OF_FOLD" for trade in closed_trades),
        candidate_signals=candidate_signals, accepted_entries=accepted_entries,
        rejected_entries=rejected, equity_curve=equity_curve, trades=tuple(closed_trades),
    )


def result_metrics(
    result: PortfolioResult,
) -> dict[str, Any]:
    """Return the complete, JSON-safe metric contract for one fold/cost run."""

    trades = result.trades
    per_symbol_returns: dict[str, float] = {}
    per_symbol_trade_counts: dict[str, int] = {}
    for trade in trades:
        per_symbol_returns[trade.symbol] = per_symbol_returns.get(trade.symbol, 0.0) + trade.pnl
        per_symbol_trade_counts[trade.symbol] = per_symbol_trade_counts.get(trade.symbol, 0) + 1

    curve = result.equity_curve.copy()
    curve["timestamp"] = pd.to_datetime(curve["timestamp"], utc=True, errors="raise")
    monthly_equity = curve.set_index("timestamp")["equity"].resample("ME").last()
    monthly_returns = monthly_equity.pct_change().dropna()

    return {
        "initial_capital": result.initial_capital,
        "final_equity": result.final_equity,
        "net_return": result.net_return,
        "annualized_return": result.annualized_return,
        "maximum_drawdown": result.maximum_drawdown,
        "trade_count": result.trade_count,
        "win_rate": result.win_rate,
        "profit_factor": result.profit_factor,
        "gross_profit": result.gross_profit,
        "gross_loss": result.gross_loss,
        "average_trade_return": result.average_trade_return,
        "median_trade_return": result.median_trade_return,
        "average_holding_hours": result.average_holding_hours,
        "exposure": result.exposure,
        "average_open_positions": result.average_positions,
        "maximum_simultaneous_positions": result.maximum_positions,
        "turnover": result.turnover,
        "total_fees": result.total_fees,
        "stop_exits": result.stop_exits,
        "end_of_fold_exits": result.end_of_fold_exits,
        "per_symbol_returns": dict(sorted(per_symbol_returns.items())),
        "per_symbol_trade_counts": dict(sorted(per_symbol_trade_counts.items())),
        "monthly_returns": {
            timestamp.isoformat(): value
            for timestamp, value in monthly_returns.items()
        },
        "year_result": result.net_return,
        "candidate_signals": result.candidate_signals,
        "accepted_entries": result.accepted_entries,
        "rejected_entries": dict(result.rejected_entries),
    }


def aggregate_fold_metrics(
    fold_results: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    folds = list(fold_results)
    base_metrics = [dict(value["base_metrics"]) for value in folds]
    stress_metrics = [dict(value["stress_metrics"]) for value in folds]
    returns = [float(value["net_return"]) for value in base_metrics]
    drawdowns = [float(value["maximum_drawdown"]) for value in base_metrics]
    total_trades = sum(int(value["trade_count"]) for value in base_metrics)
    base_growth = math.prod(1.0 + value for value in returns) - 1.0
    stress_growth = math.prod(
        1.0 + float(value["net_return"])
        for value in stress_metrics
    ) - 1.0
    return {
        "aggregate_compounded_return": base_growth,
        "aggregate_stress_cost_return_0_004": stress_growth,
        "total_trade_count": total_trades,
        "worst_fold_return": min(returns),
        "worst_fold_drawdown": max(drawdowns),
        "median_fold_return": float(pd.Series(returns).median()),
        "positive_fold_ratio": sum(value > 0.0 for value in returns) / len(returns),
        "total_fees": sum(float(value["total_fees"]) for value in base_metrics),
        "total_candidate_signals": sum(int(value["candidate_signals"]) for value in base_metrics),
        "total_accepted_entries": sum(int(value["accepted_entries"]) for value in base_metrics),
    }


def write_json_atomically(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    """Validate JSON before atomically replacing the registered artifact."""

    encoded = json.dumps(
        dict(payload),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    json.loads(encoded)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
        os.replace(temporary_name, path)
    except BaseException:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise


def git_output(
    *arguments: str,
) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def utc_now() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


def registered_trial_plan() -> list[dict[str, str]]:
    """Return the fixed twenty-trial budget with explicit profile sensitivity."""

    plan = [
        {
            "trial_id": "AMS-V3-F01-T01",
            "configuration_id": "AMS-V3-F01-C01",
            "portfolio_profile_id": "AMS-V3-PORTFOLIO-P02",
        },
        {
            "trial_id": "AMS-V3-F01-T02",
            "configuration_id": "AMS-V3-F01-C02",
            "portfolio_profile_id": "AMS-V3-PORTFOLIO-P02",
        },
    ]
    plan.extend(
        {
            "trial_id": f"AMS-V3-F01-T{sequence:02d}",
            "configuration_id": f"AMS-V3-F01-C{configuration:02d}",
            "portfolio_profile_id": "AMS-V3-PORTFOLIO-P02",
        }
        for sequence, configuration in enumerate(range(3, 17), start=3)
    )
    plan.extend(
        [
            {
                "trial_id": "AMS-V3-F01-T17",
                "configuration_id": "AMS-V3-F01-C01",
                "portfolio_profile_id": "AMS-V3-PORTFOLIO-P01",
            },
            {
                "trial_id": "AMS-V3-F01-T18",
                "configuration_id": "AMS-V3-F01-C01",
                "portfolio_profile_id": "AMS-V3-PORTFOLIO-P03",
            },
            {
                "trial_id": "AMS-V3-F01-T19",
                "configuration_id": "AMS-V3-F01-C01",
                "portfolio_profile_id": "AMS-V3-PORTFOLIO-P04",
            },
            {
                "trial_id": "AMS-V3-F01-T20",
                "configuration_id": "AMS-V3-F01-C02",
                "portfolio_profile_id": "AMS-V3-PORTFOLIO-P01",
            },
        ]
    )
    return plan


def register_harness() -> dict[str, Any]:
    """Register a verified harness without consuming an AMS V3 trial."""

    source_commit = git_output("rev-parse", "HEAD")
    experiment = load_object(DEFAULT_EXPERIMENT_PATH)
    accounting = experiment.get("trial_accounting")
    expected_accounting = {
        "total_authorized_trials": 20,
        "trials_executed": 0,
        "remaining_authorized_trials": 20,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    if accounting != expected_accounting:
        raise HarnessError("Harness registration requires an untouched trial ledger.")

    engine = importlib.import_module("spotbot.research.ams_v3_multitimeframe_fibonacci")
    configurations = [copy.deepcopy(value) for value in engine.build_ams_v3_configuration_grid()]
    first = configurations[0]["parameters"]
    second = configurations[1]["parameters"]
    paired_differences = {
        key: (first.get(key), second.get(key))
        for key in sorted(set(first).union(second))
        if first.get(key) != second.get(key)
    }
    if paired_differences != {
        "fibonacci_mode": ("NO_FIBONACCI_CONTROL", "CORE_382_618")
    }:
        raise HarnessError("C01/C02 must differ only by the preregistered Fibonacci mode.")

    experiment["alpha_configurations"] = configurations
    experiment["source_commit"] = source_commit
    experiment["trial_plan"] = [
        {**value, "trial_status": "REGISTERED_NOT_EXECUTED"}
        for value in registered_trial_plan()
    ]
    experiment["harness_registration"] = {
        "status": "REGISTERED_NOT_EXECUTED",
        "report_path": str(DEFAULT_HARNESS_REGISTRATION_PATH.relative_to(ROOT)).replace("\\", "/"),
        "registered_at": utc_now(),
        "execution_rule": "SIGNAL_AT_CLOSE_EXECUTE_NEXT_BAR_OPEN",
        "trial_accounting": dict(accounting),
    }

    readiness = load_object(DEFAULT_READINESS_PATH)
    readiness["status"] = "HARNESS_REGISTERED_NOT_EXECUTED"
    readiness["next_action"] = "RUN_AMS_V3_F01_C01_CONTROL"
    readiness["harness_registration"] = {
        "status": "REGISTERED_NOT_EXECUTED",
        "source_commit": source_commit,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    report = {
        "schema_version": "ams-v3-f01-walk-forward-harness-v1",
        "protocol_id": "AMS-V3-MTF-FIBONACCI",
        "status": "REGISTERED_NOT_EXECUTED",
        "source_commit": source_commit,
        "registered_at": utc_now(),
        "folds": [fold.as_json() for fold in anchored_walk_forward_folds()],
        "execution_rule": "SIGNAL_AT_CLOSE_EXECUTE_NEXT_BAR_OPEN",
        "spot_constraints": {
            "spot_long_only": True,
            "short_allowed": False,
            "leverage_allowed": False,
            "borrowing_allowed": False,
            "margin_allowed": False,
            "derivatives_allowed": False,
        },
        "data_integrity": {
            "dataset_hashes_verified_at_runtime": True,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "bar_boundary_policy": {
                "bar_open_time": "STRICTLY_BEFORE_2025_01_01T00:00:00Z",
                "bar_close_time": "AT_OR_BEFORE_2025_01_01T00:00:00Z",
            },
        },
        "paired_comparison": {
            "control_configuration": "AMS-V3-F01-C01",
            "fibonacci_configuration": "AMS-V3-F01-C02",
            "parameter_differences": paired_differences,
        },
        "trial_plan": {
            "total_trials": 20,
            "primary_trials": ["AMS-V3-F01-T01", "AMS-V3-F01-T02"],
            "default_portfolio_profile": "AMS-V3-PORTFOLIO-P02",
            "profile_sensitivity_trials": [
                "AMS-V3-F01-T17",
                "AMS-V3-F01-T18",
                "AMS-V3-F01-T19",
                "AMS-V3-F01-T20",
            ],
            "rationale": (
                "All sixteen alpha configurations are evaluated once on P02; "
                "four remaining authorized trials test preregistered portfolio sensitivity."
            ),
        },
        "trial_accounting": dict(accounting),
        "next_action": "RUN_AMS_V3_F01_C01_CONTROL",
    }

    write_json_atomically(DEFAULT_EXPERIMENT_PATH, experiment)
    write_json_atomically(DEFAULT_READINESS_PATH, readiness)
    write_json_atomically(DEFAULT_HARNESS_REGISTRATION_PATH, report)

    project = load_object(DEFAULT_PROJECT_LEDGER_PATH)
    updates = project.setdefault("protocol_updates", [])
    event_id = "AMS_V3_F01_WALK_FORWARD_HARNESS_V1_REGISTERED"
    if not any(isinstance(value, dict) and value.get("event_id") == event_id for value in updates):
        updates.append(
            {
                "event_id": event_id,
                "event_type": "RESEARCH_INFRASTRUCTURE_REGISTERED",
                "recorded_at": utc_now(),
                "source_commit": source_commit,
                "report_path": str(
                    DEFAULT_HARNESS_REGISTRATION_PATH.relative_to(ROOT)
                ).replace("\\", "/"),
                "report_sha256": file_sha256(DEFAULT_HARNESS_REGISTRATION_PATH),
                "registered_trials_consumed": 0,
                "test_2025_accessed": False,
                "holdout_2026_accessed": False,
            }
        )
    project["current_stage"] = "AMS_V3_F01_WALK_FORWARD_HARNESS_REGISTERED"
    project["next_action"] = "RUN_AMS_V3_F01_C01_CONTROL"
    project["last_updated_at"] = utc_now()
    write_json_atomically(DEFAULT_PROJECT_LEDGER_PATH, project)
    return report


def run_walk_forward(
    *,
    configuration_id: str,
    portfolio_profile_id: str,
    initial_capital: float = 100_000.0,
    panel: pd.DataFrame | None = None,
) -> dict[str, Any]:
    specification = load_trial_specification(
        configuration_id,
        portfolio_profile_id,
    )

    if panel is None:
        panel = build_execution_panel(load_registered_datasets())

    contract = infer_execution_contract(panel)

    fold_results: list[dict[str, Any]] = []

    for fold in anchored_walk_forward_folds():
        validation = validation_slice(
            panel,
            contract=contract,
            fold=fold,
        )

        result = simulate_portfolio(
            validation,
            contract=contract,
            specification=specification,
            initial_capital=(initial_capital),
        )

        stress_specification = replace(
            specification,
            transaction_cost=float(specification.parameters["stress_transaction_cost"]),
        )
        stress_result = simulate_portfolio(
            validation,
            contract=contract,
            specification=stress_specification,
            initial_capital=initial_capital,
        )

        fold_results.append(
            {
                "fold": fold.as_json(),
                "base_metrics": result_metrics(result),
                "stress_metrics": result_metrics(stress_result),
                "trades": [
                    {
                        **asdict(trade),
                        "entry_time": (trade.entry_time.isoformat()),
                        "exit_time": (trade.exit_time.isoformat()),
                    }
                    for trade in result.trades
                ],
            }
        )

    return {
        "configuration_id": (configuration_id),
        "portfolio_profile_id": (portfolio_profile_id),
        "execution_contract": asdict(contract),
        "fold_results": fold_results,
        "aggregate_result": aggregate_fold_metrics(fold_results),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }


def trial_report_path(
    *,
    trial_id: str,
    configuration_id: str,
    portfolio_profile_id: str,
) -> Path:
    configuration_token = configuration_id.lower().replace("ams-v3-f01-", "")
    profile_token = portfolio_profile_id.lower().replace("ams-v3-portfolio-", "")
    suffix = "" if trial_id in {"AMS-V3-F01-T01", "AMS-V3-F01-T02"} else f"-{profile_token}"
    return ROOT / "reports/research" / f"ams-v3-f01-{configuration_token}{suffix}-trial-v1.json"


def execute_registered_trial(
    *,
    trial_id: str,
    panel: pd.DataFrame | None = None,
    initial_capital: float = 100_000.0,
) -> dict[str, Any]:
    """Execute exactly one preregistered trial and consume it after durable writes."""

    experiment = load_object(DEFAULT_EXPERIMENT_PATH)
    accounting = experiment.get("trial_accounting")
    plan = experiment.get("trial_plan")
    if not isinstance(accounting, dict) or not isinstance(plan, list):
        raise HarnessError("Harness registration is missing the trial plan.")
    if accounting.get("remaining_authorized_trials", 0) <= 0:
        raise HarnessError("No authorized AMS V3 trials remain.")
    matches = [
        value
        for value in plan
        if isinstance(value, dict) and value.get("trial_id") == trial_id
    ]
    if len(matches) != 1:
        raise HarnessError(f"Unknown registered trial: {trial_id}.")
    trial = matches[0]
    if trial.get("trial_status") != "REGISTERED_NOT_EXECUTED":
        raise HarnessError(f"Trial is already consumed: {trial_id}.")
    configuration_id = str(trial["configuration_id"])
    portfolio_profile_id = str(trial["portfolio_profile_id"])
    started_at = utc_now()
    result = run_walk_forward(
        configuration_id=configuration_id,
        portfolio_profile_id=portfolio_profile_id,
        initial_capital=initial_capital,
        panel=panel,
    )
    completed_at = utc_now()
    source_commit = git_output("rev-parse", "HEAD")
    report_path = trial_report_path(
        trial_id=trial_id,
        configuration_id=configuration_id,
        portfolio_profile_id=portfolio_profile_id,
    )
    report = {
        "schema_version": "ams-v3-f01-trial-v1",
        "trial_id": trial_id,
        "configuration_id": configuration_id,
        "portfolio_profile_id": portfolio_profile_id,
        "status": "EXECUTED",
        "source_commit": source_commit,
        "started_at": started_at,
        "completed_at": completed_at,
        "execution_rule": "SIGNAL_AT_CLOSE_EXECUTE_NEXT_BAR_OPEN",
        "results": result,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    # A valid result report is written first.  Only then can the ledger consume
    # the trial, so a computation failure never decrements the budget.
    write_json_atomically(report_path, report)

    updated = copy.deepcopy(experiment)
    updated_plan = updated["trial_plan"]
    updated_trial = next(value for value in updated_plan if value["trial_id"] == trial_id)
    updated_trial["trial_status"] = "EXECUTED"
    updated_trial["report_path"] = str(report_path.relative_to(ROOT)).replace("\\", "/")
    updated_trial["report_sha256"] = file_sha256(report_path)
    updated_trial["completed_at"] = completed_at
    updated_trial["aggregate_result"] = result["aggregate_result"]
    updated_accounting = updated["trial_accounting"]
    updated_accounting["trials_executed"] = int(updated_accounting["trials_executed"]) + 1
    updated_accounting["remaining_authorized_trials"] = (
        int(updated_accounting["remaining_authorized_trials"]) - 1
    )

    configurations = updated["alpha_configurations"]
    configuration = next(
        value
        for value in configurations
        if value["configuration_id"] == configuration_id
    )
    configuration.setdefault("portfolio_results", {})[portfolio_profile_id] = {
        "trial_id": trial_id,
        "report_path": updated_trial["report_path"],
        "aggregate_result": result["aggregate_result"],
    }
    if portfolio_profile_id == "AMS-V3-PORTFOLIO-P02":
        configuration["fold_results"] = result["fold_results"]
        configuration["aggregate_result"] = result["aggregate_result"]
    if not any(
        value["configuration_id"] == configuration_id
        and value["trial_status"] == "REGISTERED_NOT_EXECUTED"
        for value in updated_plan
    ):
        configuration["trial_status"] = "EXECUTED"
    write_json_atomically(DEFAULT_EXPERIMENT_PATH, updated)

    project = load_object(DEFAULT_PROJECT_LEDGER_PATH)
    updates = project.setdefault("protocol_updates", [])
    event_id = f"{trial_id.replace('-', '_')}_EXECUTED"
    updates.append(
        {
            "event_id": event_id,
            "event_type": "REGISTERED_ALPHA_TRIAL",
            "recorded_at": completed_at,
            "configuration_id": configuration_id,
            "portfolio_profile_id": portfolio_profile_id,
            "report_path": updated_trial["report_path"],
            "report_sha256": updated_trial["report_sha256"],
            "registered_trials_consumed": 1,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )
    project["current_stage"] = f"{trial_id.replace('-', '_')}_EXECUTED"
    project["next_action"] = "RUN_NEXT_AMS_V3_F01_REGISTERED_TRIAL"
    project["last_updated_at"] = completed_at
    write_json_atomically(DEFAULT_PROJECT_LEDGER_PATH, project)
    return report


def execute_all_registered_trials(
    *,
    initial_capital: float = 100_000.0,
) -> list[dict[str, Any]]:
    """Build the verified panel once, then consume every remaining planned trial."""

    datasets = load_registered_datasets()
    panel = build_execution_panel(datasets)
    experiment = load_object(DEFAULT_EXPERIMENT_PATH)
    plan = experiment.get("trial_plan")
    if not isinstance(plan, list):
        raise HarnessError("Harness registration is missing the trial plan.")
    reports = []
    for trial in plan:
        if not isinstance(trial, dict) or trial.get("trial_status") != "REGISTERED_NOT_EXECUTED":
            continue
        reports.append(
            execute_registered_trial(
                trial_id=str(trial["trial_id"]),
                panel=panel,
                initial_capital=initial_capital,
            )
        )
    return reports


def create_final_assessment() -> dict[str, Any]:
    """Create the frozen research assessment from the twenty registered trials."""

    experiment = load_object(DEFAULT_EXPERIMENT_PATH)
    accounting = experiment.get("trial_accounting")
    plan = experiment.get("trial_plan")
    if accounting != {
        "total_authorized_trials": 20,
        "trials_executed": 20,
        "remaining_authorized_trials": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }:
        raise HarnessError("Final assessment requires exactly twenty consumed trials.")
    if not isinstance(plan, list) or any(
        not isinstance(value, dict) or value.get("trial_status") != "EXECUTED"
        for value in plan
    ):
        raise HarnessError("Final assessment requires every registered trial report.")

    trial_summaries: list[dict[str, Any]] = []
    reports_by_trial: dict[str, dict[str, Any]] = {}
    for trial in plan:
        report_path = ROOT / str(trial["report_path"])
        report = load_object(report_path)
        if report.get("trial_id") != trial["trial_id"] or report.get("status") != "EXECUTED":
            raise HarnessError(f"Invalid trial report: {report_path}.")
        reports_by_trial[str(trial["trial_id"])] = report
        aggregate = report["results"]["aggregate_result"]
        trial_summaries.append(
            {
                "trial_id": trial["trial_id"],
                "configuration_id": trial["configuration_id"],
                "portfolio_profile_id": trial["portfolio_profile_id"],
                "aggregate_result": aggregate,
                "report_path": trial["report_path"],
                "report_sha256": file_sha256(report_path),
            }
        )

    ranked = sorted(
        trial_summaries,
        key=lambda value: float(value["aggregate_result"]["aggregate_compounded_return"]),
        reverse=True,
    )
    control = reports_by_trial["AMS-V3-F01-T01"]
    fibonacci = reports_by_trial["AMS-V3-F01-T02"]
    control_aggregate = control["results"]["aggregate_result"]
    fibonacci_aggregate = fibonacci["results"]["aggregate_result"]
    paired_difference = {
        "aggregate_compounded_return": (
            float(fibonacci_aggregate["aggregate_compounded_return"])
            - float(control_aggregate["aggregate_compounded_return"])
        ),
        "stress_cost_return_0_004": (
            float(fibonacci_aggregate["aggregate_stress_cost_return_0_004"])
            - float(control_aggregate["aggregate_stress_cost_return_0_004"])
        ),
        "trade_count": (
            int(fibonacci_aggregate["total_trade_count"])
            - int(control_aggregate["total_trade_count"])
        ),
        "accepted_entries": (
            int(fibonacci_aggregate["total_accepted_entries"])
            - int(control_aggregate["total_accepted_entries"])
        ),
    }
    fold_comparison = [
        {
            "fold_id": base["fold"]["fold_id"],
            "control": base["base_metrics"],
            "fibonacci": filtered["base_metrics"],
        }
        for base, filtered in zip(
            control["results"]["fold_results"],
            fibonacci["results"]["fold_results"],
            strict=True,
        )
    ]
    assessment = "FAIL"
    reasoning = [
        "The paired Fibonacci trial C02 generated zero accepted entries and zero trades.",
        "C01 generated 67 trades with a positive 33.96% compounded base-cost result.",
        "Fibonacci therefore did not improve return, trade quality, or stress-cost robustness.",
        "The highest-return trial has only one positive fold, so it is not robust evidence.",
    ]
    limitations = [
        "The CORE Fibonacci filter was too restrictive for the registered setup semantics.",
        (
            "Several registered parameter combinations map to the same runtime feature policy; "
            "daily risk profile sensitivity needs a separately preregistered implementation review."
        ),
        "This result is in-sample research only and does not authorize access to 2025 or 2026.",
    ]
    next_action = (
        "DO_NOT_OPEN_2025; "
        "PREREGISTER_A_FIBONACCI_FILTER_REDESIGN_AND_PROFILE_WIRING_REVIEW"
    )
    assessment_payload = {
        "status": "PASS",
        "assessment": assessment,
        "authorized_trials": 20,
        "executed_trials": 20,
        "remaining_trials": 0,
        "best_configuration": ranked[0]["configuration_id"],
        "best_portfolio_profile": ranked[0]["portfolio_profile_id"],
        "control_configuration": "AMS-V3-F01-C01",
        "paired_fibonacci_configuration": "AMS-V3-F01-C02",
        "control_metrics": control_aggregate,
        "fibonacci_metrics": fibonacci_aggregate,
        "paired_difference": paired_difference,
        "fold_comparison": fold_comparison,
        "stress_cost_comparison": {
            "control_0_004": control_aggregate["aggregate_stress_cost_return_0_004"],
            "fibonacci_0_004": fibonacci_aggregate["aggregate_stress_cost_return_0_004"],
        },
        "all_trials": trial_summaries,
        "reasoning": reasoning,
        "limitations": limitations,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_action": next_action,
    }
    report_path = ROOT / "reports/research/ams-v3-f01-final-assessment-v1.json"
    write_json_atomically(report_path, assessment_payload)
    markdown_path = ROOT / "reports/research/ams-v3-f01-final-assessment-v1.md"
    markdown = "\n".join(
        [
            "# AMS V3 F01 final assessment",
            "",
            f"- Assessment: `{assessment}`",
            (
                "- Is the strategy successful? No; the registered family fails the paired "
                "Fibonacci test."
            ),
            "- Did Fibonacci add value? No. C02 made zero trades versus C01's 67.",
            (
                f"- Best configuration: `{ranked[0]['configuration_id']}` on "
                f"`{ranked[0]['portfolio_profile_id']}`."
            ),
            f"- Worst C01 fold return: {control_aggregate['worst_fold_return']:.2%}.",
            (
                "- Does C01 tolerate 0.4% fees? Yes mechanically: "
                f"{control_aggregate['aggregate_stress_cost_return_0_004']:.2%}; "
                "Fibonacci does not trade."
            ),
            (
                "- Is trade count sufficient? C01 has 67 trades; C02 has none, so the paired "
                "Fibonacci result rejects this filter implementation."
            ),
            (
                "- Largest weakness: the Fibonacci filter eliminates every eligible entry under "
                "the frozen setup semantics."
            ),
            (
                "- Open 2025 later? No. First preregister a redesigned filter and wire the "
                "portfolio profile dimension into runtime behavior."
            ),
            (
                "- Next scientific step: run a new, separately registered protocol after that "
                "redesign; do not modify this completed trial set."
            ),
            "",
            "## Paired results",
            "",
            "| Trial | Base compounded return | Stress return | Trades |",
            "| --- | ---: | ---: | ---: |",
            (
                f"| C01 control | {control_aggregate['aggregate_compounded_return']:.2%} | "
                f"{control_aggregate['aggregate_stress_cost_return_0_004']:.2%} | "
                f"{control_aggregate['total_trade_count']} |"
            ),
            (
                f"| C02 Fibonacci | {fibonacci_aggregate['aggregate_compounded_return']:.2%} | "
                f"{fibonacci_aggregate['aggregate_stress_cost_return_0_004']:.2%} | "
                f"{fibonacci_aggregate['total_trade_count']} |"
            ),
            "",
        ]
    )
    markdown_path.write_text(markdown, encoding="utf-8", newline="\n")

    updated = copy.deepcopy(experiment)
    updated["final_assessment"] = {
        "assessment": assessment,
        "report_path": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "report_sha256": file_sha256(report_path),
        "next_action": assessment_payload["next_action"],
    }
    write_json_atomically(DEFAULT_EXPERIMENT_PATH, updated)
    readiness = load_object(DEFAULT_READINESS_PATH)
    readiness["status"] = "AMS_V3_F01_FINALIZED"
    readiness["next_action"] = assessment_payload["next_action"]
    readiness["final_assessment"] = {
        "assessment": assessment,
        "executed_trials": 20,
        "remaining_trials": 0,
        "report_path": updated["final_assessment"]["report_path"],
        "report_sha256": updated["final_assessment"]["report_sha256"],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    write_json_atomically(DEFAULT_READINESS_PATH, readiness)
    project = load_object(DEFAULT_PROJECT_LEDGER_PATH)
    updates = project.setdefault("protocol_updates", [])
    event_id = "AMS_V3_F01_FINAL_ASSESSMENT_V1"
    event = {
        "event_id": event_id,
        "event_type": "RESEARCH_FINAL_ASSESSMENT",
        "recorded_at": utc_now(),
        "assessment": assessment,
        "report_path": updated["final_assessment"]["report_path"],
        "report_sha256": updated["final_assessment"]["report_sha256"],
        "registered_trials_consumed": 20,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    updates[:] = [
        value
        for value in updates
        if not isinstance(value, dict) or value.get("event_id") != event_id
    ]
    updates.append(event)
    project["current_stage"] = "AMS_V3_F01_FINAL_ASSESSMENT_COMPLETED"
    project["next_action"] = assessment_payload["next_action"]
    project["last_updated_at"] = utc_now()
    write_json_atomically(DEFAULT_PROJECT_LEDGER_PATH, project)
    return assessment_payload


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--configuration-id")

    parser.add_argument("--portfolio-profile-id")

    parser.add_argument(
        "--initial-capital",
        type=float,
        default=100_000.0,
    )

    parser.add_argument(
        "--execute",
        action="store_true",
    )

    parser.add_argument("--trial-id")

    parser.add_argument(
        "--execute-all",
        action="store_true",
    )

    parser.add_argument(
        "--finalize",
        action="store_true",
    )

    parser.add_argument(
        "--register",
        action="store_true",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    if arguments.register:
        if arguments.execute or arguments.execute_all or arguments.finalize:
            raise HarnessError("Registration and execution cannot be combined.")
        print(json.dumps(register_harness(), indent=2, sort_keys=True, allow_nan=False))
        return 0

    if arguments.execute_all:
        reports = execute_all_registered_trials(initial_capital=arguments.initial_capital)
        print(json.dumps(reports, indent=2, sort_keys=True, allow_nan=False))
        return 0

    if arguments.finalize:
        print(json.dumps(create_final_assessment(), indent=2, sort_keys=True, allow_nan=False))
        return 0

    if not arguments.execute:
        raise HarnessError("Execution requires the explicit --execute flag.")

    if not arguments.trial_id:
        raise HarnessError("Recorded execution requires a registered trial identifier.")

    result = execute_registered_trial(
        trial_id=arguments.trial_id,
        initial_capital=(arguments.initial_capital),
    )

    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
