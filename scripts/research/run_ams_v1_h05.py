from __future__ import annotations

import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from spotbot.research.compression_expansion import (
    CompressionExpansionPolicy,
    build_compression_expansion_signals,
    build_compression_expansion_weights,
)
from spotbot.research.momentum_reacceleration import (
    MomentumReaccelerationPolicy,
    run_daily_portfolio_backtest,
)

ROOT = Path.cwd()

PROTOCOL_ID = "AMS-V1"

HYPOTHESIS_ID = (
    "AMS-V1-H05-"
    "COMPRESSION-EXPANSION"
)

SCHEMA_VERSION = (
    "ams-v1-h05-compression-"
    "expansion-result-v1"
)

EXPECTED_BRANCH = (
    "research/"
    "ams-v1-h05-compression-expansion"
)

EXPECTED_PARAMETER_HASH = (
    "0989a3d8986d027c395f2866e4a7f712"
    "c479e5019e57e072fd88f5f993e99eb4"
)

RESEARCH_START = datetime(
    2021,
    1,
    1,
    tzinfo=UTC,
)

RESEARCH_END_EXCLUSIVE = datetime(
    2025,
    1,
    1,
    tzinfo=UTC,
)

LOCKED_TEST_START = pd.Timestamp(
    "2025-01-01",
    tz="UTC",
)

MONTHLY_TARGET = 0.24

FROZEN_PARAMETERS: dict[str, Any] = {
    "breakout_lookback_days": 20,
    "compression_lookback_days": 60,
    "compression_percentile_maximum": 0.2,
    "initial_stop_atr": 2.5,
    "maximum_holding_days": 30,
    "maximum_positions": 2,
    "minimum_turnover_expansion": 1.5,
    "ranking_maximum": 10,
    "trailing_stop_atr": 4.0,
    "transaction_cost_fraction": 0.002,
}

HISTORY_DIRECTORY = (
    ROOT
    / "data/research/"
    "multi_asset_daily/kucoin_direct_v3"
)

RANKING_PATH = (
    ROOT
    / "data/research/asset_ranking/v1/"
    "asset-ranking-engine-v1.parquet"
)

OUTPUT_DIRECTORY = (
    ROOT
    / "data/research/strategy_results/"
    "ams_v1_h05_compression_expansion"
)

REPORT_DIRECTORY = (
    ROOT
    / "reports/research"
)

REPORT_PATH = (
    REPORT_DIRECTORY
    / "ams-v1-h05-compression-expansion.json"
)

MONTHLY_PATH = (
    REPORT_DIRECTORY
    / (
        "ams-v1-h05-compression-"
        "expansion-monthly.csv"
    )
)

TRADES_PATH = (
    REPORT_DIRECTORY
    / (
        "ams-v1-h05-compression-"
        "expansion-trades.csv"
    )
)

SIGNALS_PATH = (
    OUTPUT_DIRECTORY
    / (
        "ams-v1-h05-compression-"
        "expansion-signals.parquet"
    )
)

WEIGHTS_PATH = (
    OUTPUT_DIRECTORY
    / (
        "ams-v1-h05-compression-"
        "expansion-weights.parquet"
    )
)

DAILY_PATH = (
    OUTPUT_DIRECTORY
    / (
        "ams-v1-h05-compression-"
        "expansion-daily-results.parquet"
    )
)

TRADES_PARQUET_PATH = (
    OUTPUT_DIRECTORY
    / (
        "ams-v1-h05-compression-"
        "expansion-trades.parquet"
    )
)

HYPOTHESIS_LEDGER_PATH = (
    REPORT_DIRECTORY
    / (
        "aggressive-multi-strategy-"
        "hypothesis-ledger-v1.json"
    )
)

PROJECT_LEDGER_PATH = (
    REPORT_DIRECTORY
    / "project-research-ledger-v3.json"
)


def git_output(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    return completed.stdout.strip()


def utc_now() -> str:
    return (
        datetime.now(tz=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def json_default(value: object) -> object:
    if isinstance(
        value,
        (pd.Timestamp, datetime),
    ):
        return value.isoformat()

    if hasattr(value, "item"):
        return value.item()  # type: ignore[no-any-return]

    raise TypeError(
        f"Unsupported JSON value: {type(value)!r}"
    )


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
            default=json_default,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def parameter_hash(
    parameters: dict[str, Any],
) -> str:
    canonical = json.dumps(
        parameters,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")

    return hashlib.sha256(
        canonical
    ).hexdigest()


def load_history() -> pd.DataFrame:
    paths = sorted(
        HISTORY_DIRECTORY.glob(
            "*.parquet"
        )
    )

    if not paths:
        raise FileNotFoundError(
            "No KuCoin history Parquets were found."
        )

    history = pd.concat(
        [
            pd.read_parquet(path)
            for path in paths
        ],
        ignore_index=True,
    )

    history["open_time"] = pd.to_datetime(
        history["open_time"],
        utc=True,
        errors="raise",
    )

    history["close_time"] = pd.to_datetime(
        history["close_time"],
        utc=True,
        errors="raise",
    )

    if (
        history["open_time"]
        >= LOCKED_TEST_START
    ).any():
        raise RuntimeError(
            "Locked 2025+ open-time history entered H05."
        )

    if (
        history["close_time"]
        > LOCKED_TEST_START
    ).any():
        raise RuntimeError(
            "Locked post-2024 close-time history entered H05."
        )

    return history


def load_ranking() -> pd.DataFrame:
    if not RANKING_PATH.exists():
        raise FileNotFoundError(
            RANKING_PATH
        )

    ranking = pd.read_parquet(
        RANKING_PATH
    )

    ranking["snapshot_time"] = pd.to_datetime(
        ranking["snapshot_time"],
        utc=True,
        errors="raise",
    )

    if (
        ranking["snapshot_time"]
        >= LOCKED_TEST_START
    ).any():
        raise RuntimeError(
            "Locked 2025+ ranking entered H05."
        )

    return ranking


def h05_policy(
    *,
    transaction_cost_fraction: float,
) -> CompressionExpansionPolicy:
    return CompressionExpansionPolicy(
        research_start=RESEARCH_START,
        research_end_exclusive=(
            RESEARCH_END_EXCLUSIVE
        ),
        breakout_lookback_days=(
            FROZEN_PARAMETERS[
                "breakout_lookback_days"
            ]
        ),
        compression_lookback_days=(
            FROZEN_PARAMETERS[
                "compression_lookback_days"
            ]
        ),
        compression_percentile_maximum=(
            FROZEN_PARAMETERS[
                "compression_percentile_maximum"
            ]
        ),
        ranking_maximum=(
            FROZEN_PARAMETERS[
                "ranking_maximum"
            ]
        ),
        maximum_positions=(
            FROZEN_PARAMETERS[
                "maximum_positions"
            ]
        ),
        minimum_turnover_expansion=(
            FROZEN_PARAMETERS[
                "minimum_turnover_expansion"
            ]
        ),
        initial_stop_atr=(
            FROZEN_PARAMETERS[
                "initial_stop_atr"
            ]
        ),
        trailing_stop_atr=(
            FROZEN_PARAMETERS[
                "trailing_stop_atr"
            ]
        ),
        maximum_holding_days=(
            FROZEN_PARAMETERS[
                "maximum_holding_days"
            ]
        ),
        transaction_cost_fraction=(
            transaction_cost_fraction
        ),
    )

def portfolio_policy(
    *,
    transaction_cost_fraction: float,
) -> MomentumReaccelerationPolicy:
    return MomentumReaccelerationPolicy(
        research_start=RESEARCH_START,
        research_end_exclusive=(
            RESEARCH_END_EXCLUSIVE
        ),
        benchmark_symbol="BTC/USDT",
        maximum_rank=(
            FROZEN_PARAMETERS[
                "ranking_maximum"
            ]
        ),
        maximum_positions=(
            FROZEN_PARAMETERS[
                "maximum_positions"
            ]
        ),
        transaction_cost_fraction=(
            transaction_cost_fraction
        ),
    )


def run_variant(
    history: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    transaction_cost_fraction: float,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    weights, trades = (
        build_compression_expansion_weights(
            history,
            signals,
            policy=h05_policy(
                transaction_cost_fraction=(
                    transaction_cost_fraction
                )
            ),
        )
    )

    daily = run_daily_portfolio_backtest(
        history,
        weights,
        policy=portfolio_policy(
            transaction_cost_fraction=(
                transaction_cost_fraction
            )
        ),
    )

    return (
        weights,
        trades,
        daily,
    )


def maximum_drawdown(
    equity: pd.Series,
) -> float:
    drawdown = (
        equity
        / equity.cummax()
        - 1.0
    )

    return float(
        drawdown.min()
    )


def annualized_volatility(
    returns: pd.Series,
) -> float:
    if len(returns) < 2:
        return 0.0

    return float(
        returns.std(ddof=1)
        * math.sqrt(365.0)
    )


def sharpe_ratio(
    returns: pd.Series,
) -> float:
    volatility = annualized_volatility(
        returns
    )

    if volatility <= 0.0:
        return 0.0

    return float(
        returns.mean()
        * 365.0
        / volatility
    )


def performance_metrics(
    daily: pd.DataFrame,
) -> dict[str, Any]:
    if daily.empty:
        raise RuntimeError(
            "Daily results are empty."
        )

    timestamps = pd.to_datetime(
        daily["snapshot_time"],
        utc=True,
        errors="raise",
    )

    equity = pd.to_numeric(
        daily["equity"],
        errors="raise",
    )

    returns = pd.to_numeric(
        daily["net_return"],
        errors="raise",
    )

    final_equity = float(
        equity.iloc[-1]
    )

    capital_survived = (
        math.isfinite(final_equity)
        and final_equity > 0.0
    )

    elapsed_days = max(
        float(
            (
                timestamps.iloc[-1]
                - timestamps.iloc[0]
            ).total_seconds()
            / 86_400.0
        ),
        1.0,
    )

    total_return = (
        final_equity
        - 1.0
    )

    annual_capital_multiple = (
        final_equity
        ** (
            365.2425
            / elapsed_days
        )
        if capital_survived
        else 0.0
    )

    geometric_monthly_return = (
        final_equity
        ** (
            30.436875
            / elapsed_days
        )
        - 1.0
        if capital_survived
        else -1.0
    )

    max_drawdown = maximum_drawdown(
        equity
    )

    return_to_drawdown = (
        total_return
        / abs(max_drawdown)
        if max_drawdown < 0.0
        else 0.0
    )

    return {
        "start_time": (
            timestamps.iloc[0]
        ),
        "end_time": (
            timestamps.iloc[-1]
        ),
        "observations": int(
            len(daily)
        ),
        "final_equity": (
            final_equity
        ),
        "total_return": (
            total_return
        ),
        "geometric_monthly_return": (
            geometric_monthly_return
        ),
        "annual_capital_multiple": (
            annual_capital_multiple
        ),
        "annual_compound_return": (
            annual_capital_multiple
            - 1.0
        ),
        "maximum_drawdown": (
            max_drawdown
        ),
        "annualized_volatility": (
            annualized_volatility(
                returns
            )
        ),
        "sharpe_ratio": (
            sharpe_ratio(
                returns
            )
        ),
        "return_to_drawdown_ratio": (
            return_to_drawdown
        ),
        "positive_day_fraction": float(
            (
                returns > 0.0
            ).mean()
        ),
        "capital_survived": (
            capital_survived
        ),
        "average_exposure": float(
            daily["exposure"].mean()
        ),
        "maximum_exposure": float(
            daily["exposure"].max()
        ),
        "average_active_positions": float(
            daily[
                "active_positions"
            ].mean()
        ),
        "maximum_active_positions": int(
            daily[
                "active_positions"
            ].max()
        ),
        "total_turnover": float(
            daily["turnover"].sum()
        ),
        "total_transaction_cost": float(
            daily[
                "transaction_cost"
            ].sum()
        ),
    }


def benchmark_metrics(
    daily: pd.DataFrame,
) -> dict[str, Any]:
    frame = pd.DataFrame(
        {
            "snapshot_time": (
                daily["snapshot_time"]
            ),
            "net_return": (
                daily["benchmark_return"]
            ),
        }
    )

    frame["equity"] = (
        1.0
        + frame["net_return"]
    ).cumprod()

    frame["exposure"] = 1.0
    frame["active_positions"] = 1
    frame["turnover"] = 0.0
    frame["transaction_cost"] = 0.0

    return performance_metrics(
        frame
    )


def monthly_results(
    daily: pd.DataFrame,
) -> pd.DataFrame:
    frame = daily[
        [
            "snapshot_time",
            "net_return",
            "benchmark_return",
        ]
    ].copy()

    frame["snapshot_time"] = pd.to_datetime(
        frame["snapshot_time"],
        utc=True,
        errors="raise",
    )

    frame["month"] = (
        frame["snapshot_time"]
        .dt.tz_convert(None)
        .dt.to_period("M")
        .astype(str)
    )

    monthly = (
        frame.groupby(
            "month",
            as_index=False,
        )
        .agg(
            strategy_return=(
                "net_return",
                lambda values: (
                    1.0 + values
                ).prod()
                - 1.0,
            ),
            benchmark_return=(
                "benchmark_return",
                lambda values: (
                    1.0 + values
                ).prod()
                - 1.0,
            ),
            observations=(
                "net_return",
                "size",
            ),
        )
    )

    monthly["strategy_positive"] = (
        monthly["strategy_return"]
        > 0.0
    )

    monthly["target_met"] = (
        monthly["strategy_return"]
        >= MONTHLY_TARGET
    )

    return monthly


def trade_statistics(
    trades: pd.DataFrame,
) -> dict[str, Any]:
    if trades.empty:
        return {
            "trade_count": 0,
            "win_rate": 0.0,
            "average_trade_return": 0.0,
            "median_trade_return": 0.0,
            "best_trade_return": 0.0,
            "worst_trade_return": 0.0,
            "average_holding_days": 0.0,
            "exit_reason_counts": {},
        }

    returns = pd.to_numeric(
        trades[
            (
                "net_trade_return_after_"
                "round_trip_cost"
            )
        ],
        errors="raise",
    )

    reasons = (
        trades["exit_reason"]
        .value_counts()
        .sort_index()
        .to_dict()
    )

    return {
        "trade_count": int(
            len(trades)
        ),
        "win_rate": float(
            (
                returns > 0.0
            ).mean()
        ),
        "average_trade_return": float(
            returns.mean()
        ),
        "median_trade_return": float(
            returns.median()
        ),
        "best_trade_return": float(
            returns.max()
        ),
        "worst_trade_return": float(
            returns.min()
        ),
        "average_holding_days": float(
            trades["holding_days"].mean()
        ),
        "exit_reason_counts": {
            str(key): int(value)
            for key, value
            in reasons.items()
        },
    }


def technical_validation(
    signals: pd.DataFrame,
    weights: pd.DataFrame,
    daily: pd.DataFrame,
) -> dict[str, bool]:
    exposure = (
        weights.groupby(
            "snapshot_time"
        )["target_weight"]
        .sum()
    )

    positions = (
        weights.groupby(
            "snapshot_time"
        )["selected"]
        .sum()
    )

    finite_columns = daily[
        [
            "gross_return",
            "turnover",
            "transaction_cost",
            "net_return",
            "equity",
            "exposure",
            "active_positions",
        ]
    ]

    checks = {
        "signals_nonempty": (
            not signals.empty
        ),
        "candidates_exist": bool(
            signals["candidate"].any()
        ),
        "weights_nonempty": (
            not weights.empty
        ),
        "no_negative_weights": bool(
            (
                weights["target_weight"]
                >= 0.0
            ).all()
        ),
        "exposure_never_exceeds_one": bool(
            (
                exposure
                <= 1.0 + 1e-12
            ).all()
        ),
        "position_limit_respected": bool(
            (
                positions
                <= FROZEN_PARAMETERS[
                    "maximum_positions"
                ]
            ).all()
        ),
        "daily_results_nonempty": (
            not daily.empty
        ),
        "daily_values_finite": bool(
            finite_columns
            .apply(
                lambda column: column.map(
                    math.isfinite
                )
            )
            .all()
            .all()
        ),
        "no_locked_test_dates": bool(
            (
                pd.to_datetime(
                    daily["snapshot_time"],
                    utc=True,
                )
                < LOCKED_TEST_START
            ).all()
        ),
    }

    return checks


def registration_from_ledger(
    ledger: dict[str, Any],
) -> dict[str, Any]:
    matches = [
        item
        for item in ledger.get(
            "evaluation_order",
            [],
        )
        if item.get(
            "hypothesis_id"
        )
        == HYPOTHESIS_ID
    ]

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one H05 registration."
        )

    return matches[0]


def update_ledgers(
    result: dict[str, Any],
) -> None:
    hypothesis_ledger = json.loads(
        HYPOTHESIS_LEDGER_PATH.read_text(
            encoding="utf-8"
        )
    )

    registration = registration_from_ledger(
        hypothesis_ledger
    )

    if (
        registration.get("status")
        != "REGISTERED"
    ):
        raise RuntimeError(
            "H05 registration is not REGISTERED."
        )

    if (
        registration.get("parameters")
        != FROZEN_PARAMETERS
    ):
        raise RuntimeError(
            "Frozen H05 parameters do not match."
        )

    results = hypothesis_ledger.setdefault(
        "results",
        [],
    )

    if any(
        item.get("hypothesis_id")
        == HYPOTHESIS_ID
        for item in results
    ):
        raise RuntimeError(
            "A binding H05 result already exists."
        )

    results.append(result)

    hypothesis_ledger["status"] = (
        "IN_PROGRESS"
    )

    hypothesis_ledger[
        "last_updated_at"
    ] = utc_now()

    write_json(
        HYPOTHESIS_LEDGER_PATH,
        hypothesis_ledger,
    )

    project_ledger = json.loads(
        PROJECT_LEDGER_PATH.read_text(
            encoding="utf-8"
        )
    )

    project_results = (
        project_ledger.setdefault(
            "aggressive_multi_strategy_results",
            [],
        )
    )

    if any(
        item.get("hypothesis_id")
        == HYPOTHESIS_ID
        for item in project_results
    ):
        raise RuntimeError(
            "Project ledger already contains H05."
        )

    project_results.append(
        {
            "hypothesis_id": HYPOTHESIS_ID,
            "family": (
                "VOLATILITY_COMPRESSION_EXPANSION"
            ),
            "decision": (
                result["decision"]
            ),
            "technical_status": (
                result["technical_status"]
            ),
            "geometric_monthly_return": (
                result["performance"][
                    "geometric_monthly_return"
                ]
            ),
            "annual_capital_multiple": (
                result["performance"][
                    "annual_capital_multiple"
                ]
            ),
            "maximum_drawdown": (
                result["performance"][
                    "maximum_drawdown"
                ]
            ),
            "report_path": str(
                REPORT_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
            "binding": True,
            "recorded_at": (
                result["completed_at"]
            ),
        }
    )

    project_ledger[
        "last_updated_at"
    ] = utc_now()

    write_json(
        PROJECT_LEDGER_PATH,
        project_ledger,
    )


def main() -> None:
    branch = git_output(
        "branch",
        "--show-current",
    )

    status = git_output(
        "status",
        "--porcelain",
    )

    if branch != EXPECTED_BRANCH:
        raise RuntimeError(
            f"Unexpected branch: {branch}"
        )

    if status:
        raise RuntimeError(
            "Working tree must be clean before H05."
        )

    if not HYPOTHESIS_LEDGER_PATH.exists():
        raise FileNotFoundError(
            HYPOTHESIS_LEDGER_PATH
        )

    if not PROJECT_LEDGER_PATH.exists():
        raise FileNotFoundError(
            PROJECT_LEDGER_PATH
        )

    observed_hash = parameter_hash(
        FROZEN_PARAMETERS
    )

    if (
        observed_hash
        != EXPECTED_PARAMETER_HASH
    ):
        raise RuntimeError(
            "Frozen H05 parameter hash mismatch: "
            f"{observed_hash}"
        )

    hypothesis_ledger = json.loads(
        HYPOTHESIS_LEDGER_PATH.read_text(
            encoding="utf-8"
        )
    )

    registration = registration_from_ledger(
        hypothesis_ledger
    )

    if (
        registration.get("parameters")
        != FROZEN_PARAMETERS
    ):
        raise RuntimeError(
            "H05 registration parameters changed."
        )

    if any(
        item.get("hypothesis_id")
        == HYPOTHESIS_ID
        for item in hypothesis_ledger.get(
            "results",
            [],
        )
    ):
        raise RuntimeError(
            "H05 already has a binding result."
        )

    print(
        "[1/7] Loading frozen research inputs..."
    )

    history = load_history()
    ranking = load_ranking()

    print(
        f"history rows={len(history):,}, "
        f"ranking rows={len(ranking):,}"
    )

    print(
        "[2/7] Building causal H05 signals..."
    )

    signals = build_compression_expansion_signals(
        history,
        ranking,
        policy=h05_policy(
            transaction_cost_fraction=(
                FROZEN_PARAMETERS[
                    "transaction_cost_fraction"
                ]
            )
        ),
    )

    candidate_count = int(
        signals["candidate"].sum()
    )

    print(
        f"signals={len(signals):,}, "
        f"candidates={candidate_count:,}"
    )

    print(
        "[3/7] Building positions "
        "and primary backtest..."
    )

    (
        primary_weights,
        primary_trades,
        primary_daily,
    ) = run_variant(
        history,
        signals,
        transaction_cost_fraction=(
            FROZEN_PARAMETERS[
                "transaction_cost_fraction"
            ]
        ),
    )

    performance = performance_metrics(
        primary_daily
    )

    benchmark = benchmark_metrics(
        primary_daily
    )

    monthly = monthly_results(
        primary_daily
    )

    trades = trade_statistics(
        primary_trades
    )

    checks = technical_validation(
        signals,
        primary_weights,
        primary_daily,
    )

    technical_pass = all(
        checks.values()
    )

    print(
        "[4/7] Running transaction-cost sensitivity..."
    )

    sensitivity: list[
        dict[str, Any]
    ] = []

    for cost in (
        0.0,
        0.002,
        0.004,
    ):
        (
            _,
            variant_trades,
            variant_daily,
        ) = run_variant(
            history,
            signals,
            transaction_cost_fraction=cost,
        )

        metrics = performance_metrics(
            variant_daily
        )

        sensitivity.append(
            {
                "transaction_cost_fraction": cost,
                "trade_count": int(
                    len(variant_trades)
                ),
                "final_equity": (
                    metrics["final_equity"]
                ),
                "total_return": (
                    metrics["total_return"]
                ),
                "geometric_monthly_return": (
                    metrics[
                        "geometric_monthly_return"
                    ]
                ),
                "maximum_drawdown": (
                    metrics[
                        "maximum_drawdown"
                    ]
                ),
            }
        )

    objective_pass = (
        technical_pass
        and performance["capital_survived"]
        and performance[
            "geometric_monthly_return"
        ]
        >= MONTHLY_TARGET
    )

    decision = (
        "PROMOTE_H05_TO_ROBUSTNESS"
        if objective_pass
        else "REJECT_H05"
    )

    technical_status = (
        "PASS"
        if technical_pass
        else "FAIL"
    )

    result = {
        "schema_version": SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "family": (
            "VOLATILITY_COMPRESSION_EXPANSION"
        ),
        "binding": True,
        "single_pass": True,
        "completed_at": utc_now(),
        "source_commit": git_output(
            "rev-parse",
            "HEAD",
        ),
        "parameter_hash_sha256": (
            observed_hash
        ),
        "parameters": FROZEN_PARAMETERS,
        "research_window": {
            "start": RESEARCH_START,
            "end_exclusive": (
                RESEARCH_END_EXCLUSIVE
            ),
            "locked_test_start": (
                LOCKED_TEST_START
            ),
        },
        "execution_model": {
            "market": "SPOT_ONLY",
            "long_only": True,
            "borrowing": False,
            "leverage": False,
            "short_selling": False,
            "derivatives": False,
            "signal_time": (
                "DAILY_CANDLE_CLOSE"
            ),
            "portfolio_application": (
                "NEXT_DAILY_RETURN_PERIOD"
            ),
            "atr_days": 14,
            "stop_model": (
                "DAILY_OHLC_TRIGGER_"
                "WITH_EXIT_AT_DAILY_CLOSE"
            ),
            "survivorship_bias_remaining": True,
        },
        "technical_status": (
            technical_status
        ),
        "technical_validation": checks,
        "objective": {
            "geometric_monthly_return_target": (
                MONTHLY_TARGET
            ),
            "annual_capital_multiple_equivalent": (
                (
                    1.0 + MONTHLY_TARGET
                )
                ** 12
            ),
            "objective_met": (
                objective_pass
            ),
        },
        "decision": decision,
        "performance": performance,
        "benchmark": benchmark,
        "trade_statistics": trades,
        "monthly_statistics": {
            "month_count": int(
                len(monthly)
            ),
            "positive_month_fraction": float(
                monthly[
                    "strategy_positive"
                ].mean()
            ),
            "target_month_fraction": float(
                monthly[
                    "target_met"
                ].mean()
            ),
            "best_month": float(
                monthly[
                    "strategy_return"
                ].max()
            ),
            "worst_month": float(
                monthly[
                    "strategy_return"
                ].min()
            ),
        },
        "transaction_cost_sensitivity": (
            sensitivity
        ),
        "artifacts": {
            "signals": str(
                SIGNALS_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
            "weights": str(
                WEIGHTS_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
            "daily_results": str(
                DAILY_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
            "trades_parquet": str(
                TRADES_PARQUET_PATH.relative_to(
                    ROOT
                )
            ).replace("\\", "/"),
            "monthly_csv": str(
                MONTHLY_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
            "trades_csv": str(
                TRADES_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
            "report": str(
                REPORT_PATH.relative_to(ROOT)
            ).replace("\\", "/"),
        },
        "limitations": [
            (
                "Bootstrap point-in-time universe still "
                "has survivorship bias because delisted "
                "asset history is incomplete."
            ),
            (
                "2025 test and 2026 holdout data remain locked."
            ),
            (
                "Daily OHLC data cannot determine exact "
                "intraday stop sequence or fill price."
            ),
        ],
    }

    print(
        "[5/7] Writing H05 research artifacts..."
    )

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    signals.to_parquet(
        SIGNALS_PATH,
        index=False,
    )

    primary_weights.to_parquet(
        WEIGHTS_PATH,
        index=False,
    )

    primary_daily.to_parquet(
        DAILY_PATH,
        index=False,
    )

    primary_trades.to_parquet(
        TRADES_PARQUET_PATH,
        index=False,
    )

    monthly.to_csv(
        MONTHLY_PATH,
        index=False,
    )

    primary_trades.to_csv(
        TRADES_PATH,
        index=False,
    )

    write_json(
        REPORT_PATH,
        result,
    )

    print(
        "[6/7] Updating binding research ledgers..."
    )

    update_ledgers(
        result
    )

    print(
        "[7/7] H05 binding result complete."
    )

    summary = {
        "hypothesis_id": HYPOTHESIS_ID,
        "technical_status": (
            technical_status
        ),
        "decision": decision,
        "candidate_signals": (
            candidate_count
        ),
        "trade_count": (
            trades["trade_count"]
        ),
        "final_equity": (
            performance["final_equity"]
        ),
        "total_return": (
            performance["total_return"]
        ),
        "geometric_monthly_return": (
            performance[
                "geometric_monthly_return"
            ]
        ),
        "monthly_target": (
            MONTHLY_TARGET
        ),
        "annual_capital_multiple": (
            performance[
                "annual_capital_multiple"
            ]
        ),
        "maximum_drawdown": (
            performance[
                "maximum_drawdown"
            ]
        ),
        "sharpe_ratio": (
            performance["sharpe_ratio"]
        ),
        "benchmark_total_return": (
            benchmark["total_return"]
        ),
        "benchmark_maximum_drawdown": (
            benchmark[
                "maximum_drawdown"
            ]
        ),
    }

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()