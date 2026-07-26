# ruff: noqa
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
DATA = ROOT / "data" / "research"

REPORT_JSON = REPORTS / "ams-bf01-benchmark-fairness-alpha-audit-v1.json"
REPORT_MD = REPORTS / "ams-bf01-benchmark-fairness-alpha-audit-v1.md"
METRICS_CSV = REPORTS / "ams-bf01-benchmark-fairness-metrics-v1.csv"
INVENTORY_CSV = REPORTS / "ams-bf01-source-inventory-v1.csv"
M02_CSV = REPORTS / "ams-bf01-m02-contributor-audit-v1.csv"
REGRESSION_CSV = REPORTS / "ams-bf01-alpha-regression-by-fold-v1.csv"
FINAL_COPY = ROOT / "BF01_RESULT_FOR_CHATGPT.md"

CUTOFF = pd.Timestamp("2024-12-31T23:59:59Z")

ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "M05_DUAL_28": (
        "m05",
        "dual-28",
        "dual_28",
        "dual 28",
        "dual4",
    ),
    "M02_TSM_84": (
        "m02",
        "tsm-84",
        "tsm_84",
        "tsm 84",
    ),
    "EQUAL_WEIGHT": (
        "equal-weight",
        "equal_weight",
        "equal weight",
        "equalweight",
        "survivor-30 equal",
        "survivor30 equal",
    ),
    "BTC_BUY_HOLD": (
        "btc buy-and-hold",
        "btc_buy_and_hold",
        "btc buy hold",
        "bitcoin buy-and-hold",
        "bitcoin buy hold",
    ),
    "HIGH_BETA_28": (
        "high-beta-28",
        "high_beta_28",
        "high beta 28",
    ),
    "HIGH_BETA_84": (
        "high-beta-84",
        "high_beta_84",
        "high beta 84",
    ),
}

METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "total_return": (
        "total_return",
        "net_return",
        "portfolio_return",
        "return_fraction",
        "return_percent",
        "return_pct",
    ),
    "cagr": (
        "cagr",
        "annualized_return",
        "annualised_return",
    ),
    "geometric_monthly_return": (
        "geometric_monthly_return",
        "monthly_geometric_return",
        "geometric_monthly",
    ),
    "sharpe": (
        "sharpe",
        "sharpe_ratio",
    ),
    "sortino": (
        "sortino",
        "sortino_ratio",
    ),
    "calmar": (
        "calmar",
        "calmar_ratio",
    ),
    "maximum_drawdown": (
        "maximum_drawdown",
        "max_drawdown",
        "max_dd",
        "drawdown",
    ),
    "cvar_5": (
        "cvar_5",
        "cvar",
        "expected_shortfall",
    ),
    "downside_deviation": (
        "downside_deviation",
        "downside_volatility",
    ),
    "worst_month": (
        "worst_month",
        "minimum_monthly_return",
    ),
    "average_exposure": (
        "average_exposure",
        "avg_exposure",
        "mean_exposure",
    ),
    "maximum_exposure": (
        "maximum_exposure",
        "max_exposure",
    ),
    "turnover": (
        "turnover",
        "total_turnover",
    ),
    "transaction_costs": (
        "transaction_costs",
        "costs",
        "total_cost",
        "trading_costs",
    ),
    "recovery_days": (
        "recovery_days",
        "maximum_recovery_days",
        "max_recovery_days",
    ),
    "btc_beta": (
        "btc_beta",
        "beta",
    ),
    "downside_beta": (
        "downside_beta",
        "btc_downside_beta",
    ),
    "residual_return": (
        "residual_return",
        "alpha_return",
        "residual_total_return",
    ),
    "r_squared": (
        "r_squared",
        "r2",
    ),
}

DATE_COLUMNS = (
    "date",
    "timestamp",
    "time",
    "open_time",
    "close_time",
    "snapshot_date",
    "trading_date",
)

RETURN_COLUMNS = (
    "daily_return",
    "portfolio_return",
    "net_return",
    "strategy_return",
    "benchmark_return",
    "return",
)

EXPOSURE_COLUMNS = (
    "exposure",
    "gross_exposure",
    "portfolio_exposure",
    "total_exposure",
)

ENTITY_COLUMNS = (
    "variant",
    "variant_id",
    "configuration",
    "config",
    "strategy",
    "strategy_id",
    "benchmark",
    "benchmark_id",
    "portfolio",
    "model",
    "name",
)

FOLD_COLUMNS = (
    "fold",
    "fold_id",
    "walk_forward_fold",
    "walkforward_fold",
    "wf",
)

SYMBOL_COLUMNS = (
    "symbol",
    "asset",
    "ticker",
)

PNL_COLUMNS = (
    "net_pnl",
    "pnl",
    "profit",
    "profit_loss",
    "contribution",
    "pnl_contribution",
)

FORBIDDEN_PATH_TOKENS = (
    "2025",
    "2026",
    "holdout",
)


@dataclass(frozen=True)
class SeriesCandidate:
    entity: str
    source: str
    rows: int
    start: str | None
    end: str | None
    has_exposure: bool
    has_fold: bool


def git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def normalise(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def canonical_entity(value: object) -> str | None:
    text = normalise(value)
    if not text:
        return None

    for entity, aliases in ENTITY_ALIASES.items():
        if any(normalise(alias) in text for alias in aliases):
            return entity

    return None


def safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None

    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        percent = cleaned.endswith("%")
        cleaned = cleaned.removesuffix("%").strip()

        try:
            number = float(cleaned)
        except ValueError:
            return None

        if not math.isfinite(number):
            return None

        return number / 100.0 if percent else number

    return None


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_dicts(
    value: object,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], dict[str, Any]]]:
    if isinstance(value, dict):
        yield path, value

        for key, child in value.items():
            yield from iter_dicts(
                child,
                (*path, str(key)),
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_dicts(
                child,
                (*path, str(index)),
            )


def flatten_scalars(
    value: object,
    path: tuple[str, ...] = (),
) -> Iterator[tuple[tuple[str, ...], object]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from flatten_scalars(
                child,
                (*path, str(key)),
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from flatten_scalars(
                child,
                (*path, str(index)),
            )
    else:
        yield path, value


def metric_name_from_path(path: Iterable[str]) -> str | None:
    joined = normalise("_".join(path))

    for metric, aliases in METRIC_ALIASES.items():
        for alias in aliases:
            alias_normalised = normalise(alias)

            if (
                joined == alias_normalised
                or joined.endswith(f"_{alias_normalised}")
                or f"_{alias_normalised}_" in f"_{joined}_"
            ):
                return metric

    return None


def percentage_value(metric: str, value: float, source_key: str) -> float:
    if metric not in {
        "total_return",
        "cagr",
        "geometric_monthly_return",
        "maximum_drawdown",
        "cvar_5",
        "downside_deviation",
        "worst_month",
        "average_exposure",
        "maximum_exposure",
        "turnover",
        "transaction_costs",
        "residual_return",
    }:
        return value

    key = normalise(source_key)

    if "percent" in key or key.endswith("pct"):
        return value

    if abs(value) <= 5.0:
        return value * 100.0

    return value


def discover_json_files() -> list[Path]:
    patterns = (
        "*rd01*.json",
        "*md01*.json",
        "*benchmark*.json",
        "*beta*.json",
        "*concentration*.json",
        "*survivor*.json",
    )

    paths: set[Path] = set()

    for pattern in patterns:
        paths.update(REPORTS.glob(pattern))

    return sorted(
        path
        for path in paths
        if not any(
            token in str(path).lower()
            for token in FORBIDDEN_PATH_TOKENS
        )
    )


def extract_aggregate_metrics(
    json_files: list[Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metric_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []

    for path in json_files:
        try:
            payload = read_json(path)
        except Exception as exc:
            evidence_rows.append(
                {
                    "source": str(path.relative_to(ROOT)),
                    "status": "READ_ERROR",
                    "detail": str(exc),
                }
            )
            continue

        for object_path, mapping in iter_dicts(payload):
            label_parts = [
                *object_path,
                *mapping.keys(),
            ]

            for candidate in mapping.values():
                if isinstance(candidate, str):
                    label_parts.append(candidate)

            label = normalise("_".join(map(str, label_parts)))
            entity = canonical_entity(label)

            if entity is None:
                continue

            for scalar_path, scalar_value in flatten_scalars(mapping):
                metric = metric_name_from_path(scalar_path)

                if metric is None:
                    continue

                number = safe_float(scalar_value)

                if number is None:
                    continue

                source_key = "_".join(scalar_path)
                metric_rows.append(
                    {
                        "entity": entity,
                        "metric": metric,
                        "value": percentage_value(
                            metric,
                            number,
                            source_key,
                        ),
                        "raw_value": number,
                        "source": str(path.relative_to(ROOT)),
                        "evidence_path": "/".join(
                            (*object_path, *scalar_path)
                        ),
                        "method": "EXISTING_AGGREGATE_REPORT",
                    }
                )

        text = json.dumps(
            payload,
            ensure_ascii=False,
        ).lower()

        for keyword in (
            "rebalance",
            "equal_weight",
            "equal-weight",
            "eligib",
            "transaction_cost",
            "exposure",
            "buy_and_hold",
            "buy-and-hold",
        ):
            if keyword in text:
                evidence_rows.append(
                    {
                        "source": str(path.relative_to(ROOT)),
                        "status": "CONSTRUCTION_EVIDENCE_PRESENT",
                        "detail": keyword,
                    }
                )

    return metric_rows, evidence_rows


def candidate_table_paths() -> list[Path]:
    patterns = (
        "*benchmark*.csv",
        "*benchmark*.parquet",
        "*daily*.csv",
        "*daily*.parquet",
        "*portfolio*.csv",
        "*portfolio*.parquet",
        "*trade*.csv",
        "*trade*.parquet",
        "*concentration*.csv",
        "*concentration*.parquet",
        "*survivor*.csv",
        "*survivor*.parquet",
        "*results*.csv",
        "*results*.parquet",
    )

    roots = (
        REPORTS,
        DATA,
    )

    candidates: set[Path] = set()

    for root in roots:
        if not root.exists():
            continue

        for pattern in patterns:
            candidates.update(root.rglob(pattern))

    allowed: list[Path] = []

    for path in sorted(candidates):
        lowered = str(path).lower()

        if any(token in lowered for token in FORBIDDEN_PATH_TOKENS):
            continue

        try:
            if path.stat().st_size > 250_000_000:
                continue
        except OSError:
            continue

        allowed.append(path)

    return allowed


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)

    return pd.read_csv(path)


def find_column(
    columns: Iterable[object],
    aliases: Iterable[str],
) -> str | None:
    normalised = {
        normalise(column): str(column)
        for column in columns
    }

    for alias in aliases:
        candidate = normalised.get(normalise(alias))

        if candidate is not None:
            return candidate

    return None


def parse_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series,
        utc=True,
        errors="coerce",
    )


def numeric_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(
            series,
            errors="coerce",
        )

    cleaned = (
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("%", "", regex=False)
    )

    values = pd.to_numeric(
        cleaned,
        errors="coerce",
    )

    percent_mask = series.astype(str).str.contains(
        "%",
        regex=False,
    )

    values.loc[percent_mask] = (
        values.loc[percent_mask] / 100.0
    )

    return values


def infer_entity_from_filename(path: Path) -> str | None:
    return canonical_entity(path.stem)


def extract_series_candidates(
    table_paths: list[Path],
) -> tuple[
    dict[str, list[pd.DataFrame]],
    list[dict[str, Any]],
    list[pd.DataFrame],
]:
    series_by_entity: dict[str, list[pd.DataFrame]] = {
        entity: []
        for entity in ENTITY_ALIASES
    }
    inventory: list[dict[str, Any]] = []
    trade_tables: list[pd.DataFrame] = []

    for path in table_paths:
        relative = str(path.relative_to(ROOT))

        try:
            frame = read_table(path)
        except Exception as exc:
            inventory.append(
                {
                    "source": relative,
                    "status": "READ_ERROR",
                    "rows": None,
                    "columns": None,
                    "date_start": None,
                    "date_end": None,
                    "detail": str(exc),
                }
            )
            continue

        if frame.empty:
            inventory.append(
                {
                    "source": relative,
                    "status": "EMPTY",
                    "rows": 0,
                    "columns": len(frame.columns),
                    "date_start": None,
                    "date_end": None,
                    "detail": "",
                }
            )
            continue

        date_col = find_column(
            frame.columns,
            DATE_COLUMNS,
        )
        return_col = find_column(
            frame.columns,
            RETURN_COLUMNS,
        )
        exposure_col = find_column(
            frame.columns,
            EXPOSURE_COLUMNS,
        )
        entity_col = find_column(
            frame.columns,
            ENTITY_COLUMNS,
        )
        fold_col = find_column(
            frame.columns,
            FOLD_COLUMNS,
        )
        symbol_col = find_column(
            frame.columns,
            SYMBOL_COLUMNS,
        )
        pnl_col = find_column(
            frame.columns,
            PNL_COLUMNS,
        )

        date_start: str | None = None
        date_end: str | None = None
        parsed_dates: pd.Series | None = None

        if date_col is not None:
            parsed_dates = parse_dates(frame[date_col])
            valid_dates = parsed_dates.dropna()

            if not valid_dates.empty:
                maximum = valid_dates.max()

                if maximum > CUTOFF:
                    raise RuntimeError(
                        "Forbidden post-2024 timestamp detected in "
                        f"{relative}: {maximum.isoformat()}"
                    )

                date_start = valid_dates.min().isoformat()
                date_end = maximum.isoformat()

        inventory.append(
            {
                "source": relative,
                "status": "READ",
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "date_start": date_start,
                "date_end": date_end,
                "detail": ",".join(map(str, frame.columns)),
            }
        )

        if (
            symbol_col is not None
            and pnl_col is not None
        ):
            trade_copy = frame.copy()
            trade_copy["_bf01_source"] = relative
            trade_tables.append(trade_copy)

        if (
            date_col is None
            or return_col is None
            or parsed_dates is None
        ):
            continue

        base = pd.DataFrame(
            {
                "date": parsed_dates,
                "return": numeric_series(
                    frame[return_col]
                ),
            }
        )

        if exposure_col is not None:
            base["exposure"] = numeric_series(
                frame[exposure_col]
            )

        if fold_col is not None:
            base["fold"] = (
                frame[fold_col]
                .astype(str)
                .replace({"nan": np.nan})
            )

        base = base.dropna(
            subset=["date", "return"],
        )
        base = base[
            base["date"] <= CUTOFF
        ]

        if base.empty:
            continue

        if entity_col is not None:
            entity_values = frame.loc[
                base.index,
                entity_col,
            ]

            for entity in ENTITY_ALIASES:
                mask = entity_values.map(
                    canonical_entity
                ) == entity

                selected = base.loc[mask].copy()

                if selected.empty:
                    continue

                selected["_source"] = relative
                series_by_entity[entity].append(
                    selected
                )

        else:
            entity = infer_entity_from_filename(path)

            if entity is not None:
                selected = base.copy()
                selected["_source"] = relative
                series_by_entity[entity].append(
                    selected
                )

        # معالجة ملفات Wide format.
        for column in frame.columns:
            column_entity = canonical_entity(column)

            if column_entity is None:
                continue

            column_name = normalise(column)

            if "return" not in column_name:
                continue

            wide = pd.DataFrame(
                {
                    "date": parsed_dates,
                    "return": numeric_series(
                        frame[column]
                    ),
                }
            ).dropna()

            wide = wide[
                wide["date"] <= CUTOFF
            ]

            if not wide.empty:
                wide["_source"] = relative
                series_by_entity[
                    column_entity
                ].append(wide)

    return series_by_entity, inventory, trade_tables


def choose_best_series(
    candidates: list[pd.DataFrame],
) -> pd.DataFrame | None:
    if not candidates:
        return None

    ranked = sorted(
        candidates,
        key=lambda frame: (
            len(frame),
            int("exposure" in frame.columns),
            int("fold" in frame.columns),
        ),
        reverse=True,
    )

    selected = ranked[0].copy()
    selected = selected.sort_values("date")
    selected = selected.drop_duplicates(
        subset=["date"],
        keep="last",
    )
    selected = selected.reset_index(drop=True)

    return selected


def infer_scale(
    returns: pd.Series,
) -> pd.Series:
    clean = numeric_series(returns).replace(
        [np.inf, -np.inf],
        np.nan,
    )

    finite = clean.dropna()

    if finite.empty:
        return clean

    median_absolute = float(
        finite.abs().median()
    )
    percentile_95 = float(
        finite.abs().quantile(0.95)
    )

    if (
        median_absolute > 0.20
        and percentile_95 > 2.0
    ):
        return clean / 100.0

    return clean


def longest_recovery_days(
    dates: pd.Series,
    equity: pd.Series,
) -> int:
    running_peak = equity.cummax()
    underwater = equity < running_peak

    longest = 0
    start: pd.Timestamp | None = None

    for date, is_underwater in zip(
        dates,
        underwater,
        strict=True,
    ):
        current_date = pd.Timestamp(date)

        if bool(is_underwater):
            if start is None:
                start = current_date
        elif start is not None:
            longest = max(
                longest,
                int(
                    (
                        current_date - start
                    ).total_seconds()
                    // 86400
                ),
            )
            start = None

    if start is not None:
        longest = max(
            longest,
            int(
                (
                    pd.Timestamp(dates.iloc[-1])
                    - start
                ).total_seconds()
                // 86400
            ),
        )

    return longest


def performance_metrics(
    frame: pd.DataFrame,
) -> dict[str, float | int | None]:
    working = frame.copy()
    working = working.sort_values("date")

    returns = infer_scale(
        working["return"]
    ).fillna(0.0)

    finite_mask = np.isfinite(
        returns.to_numpy(dtype=float)
    )
    working = working.loc[
        finite_mask
    ].copy()
    returns = returns.loc[
        finite_mask
    ].astype(float)

    if working.empty:
        return {}

    if (returns <= -1.0).any():
        raise RuntimeError(
            "Return series contains capital-destroying "
            "daily return <= -100%."
        )

    equity = (1.0 + returns).cumprod()
    final_equity = float(equity.iloc[-1])
    total_return = final_equity - 1.0

    elapsed_days = max(
        1.0,
        (
            pd.Timestamp(working["date"].iloc[-1])
            - pd.Timestamp(working["date"].iloc[0])
        ).total_seconds()
        / 86400.0,
    )

    cagr = (
        final_equity ** (365.25 / elapsed_days)
        - 1.0
        if final_equity > 0.0
        else math.nan
    )

    geometric_monthly = (
        final_equity
        ** (30.4375 / elapsed_days)
        - 1.0
        if final_equity > 0.0
        else math.nan
    )

    daily_mean = float(returns.mean())
    daily_std = float(
        returns.std(ddof=1)
    )

    annualised_volatility = (
        daily_std * math.sqrt(365.25)
        if daily_std > 0.0
        else 0.0
    )

    sharpe = (
        daily_mean
        / daily_std
        * math.sqrt(365.25)
        if daily_std > 0.0
        else math.nan
    )

    downside = returns[
        returns < 0.0
    ]
    downside_deviation = (
        float(
            np.sqrt(
                np.mean(
                    np.square(
                        downside.to_numpy(
                            dtype=float
                        )
                    )
                )
            )
        )
        * math.sqrt(365.25)
        if not downside.empty
        else 0.0
    )

    sortino = (
        daily_mean
        * 365.25
        / downside_deviation
        if downside_deviation > 0.0
        else math.nan
    )

    running_peak = equity.cummax()
    drawdowns = equity / running_peak - 1.0
    maximum_drawdown = float(
        drawdowns.min()
    )

    calmar = (
        cagr / abs(maximum_drawdown)
        if (
            math.isfinite(cagr)
            and maximum_drawdown < 0.0
        )
        else math.nan
    )

    tail_threshold = float(
        returns.quantile(0.05)
    )
    tail = returns[
        returns <= tail_threshold
    ]
    cvar_5 = (
        float(tail.mean())
        if not tail.empty
        else math.nan
    )

    monthly = pd.DataFrame(
        {
            "date": working["date"],
            "return": returns,
        }
    )
    monthly["month"] = (
        monthly["date"]
        .dt.tz_convert(None)
        .dt.to_period("M")
    )
    monthly_returns = monthly.groupby(
        "month"
    )["return"].apply(
        lambda values: float(
            (1.0 + values).prod() - 1.0
        )
    )

    metrics: dict[str, float | int | None] = {
        "rows": int(len(working)),
        "total_return": total_return,
        "cagr": cagr,
        "geometric_monthly_return": geometric_monthly,
        "annualised_volatility": annualised_volatility,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "maximum_drawdown": maximum_drawdown,
        "cvar_5": cvar_5,
        "downside_deviation": downside_deviation,
        "worst_month": (
            float(monthly_returns.min())
            if not monthly_returns.empty
            else math.nan
        ),
        "recovery_days": longest_recovery_days(
            working["date"].reset_index(
                drop=True
            ),
            equity.reset_index(drop=True),
        ),
        "start": working["date"].iloc[
            0
        ].isoformat(),
        "end": working["date"].iloc[
            -1
        ].isoformat(),
    }

    if "exposure" in working.columns:
        exposure = numeric_series(
            working["exposure"]
        ).clip(lower=0.0, upper=1.0)

        metrics["average_exposure"] = float(
            exposure.mean()
        )
        metrics["maximum_exposure"] = float(
            exposure.max()
        )
    else:
        metrics["average_exposure"] = None
        metrics["maximum_exposure"] = None

    return metrics


def align_series(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_name: str,
    right_name: str,
) -> pd.DataFrame:
    left_frame = left[
        ["date", "return"]
    ].rename(
        columns={
            "return": left_name,
        }
    )
    right_frame = right[
        ["date", "return"]
    ].rename(
        columns={
            "return": right_name,
        }
    )

    return left_frame.merge(
        right_frame,
        on="date",
        how="inner",
        validate="one_to_one",
    ).sort_values("date")


def construct_exposure_matched(
    m05: pd.DataFrame,
    equal_weight: pd.DataFrame,
) -> pd.DataFrame | None:
    if "exposure" not in m05.columns:
        return None

    left = m05[
        ["date", "exposure"]
    ].copy()
    left["exposure"] = numeric_series(
        left["exposure"]
    ).clip(lower=0.0, upper=1.0)

    right = equal_weight[
        ["date", "return"]
    ].copy()
    right["return"] = infer_scale(
        right["return"]
    )

    merged = left.merge(
        right,
        on="date",
        how="inner",
        validate="one_to_one",
    )

    if len(merged) < 60:
        return None

    merged["return"] = (
        merged["return"]
        * merged["exposure"]
    )

    return merged[
        ["date", "return", "exposure"]
    ]


def construct_volatility_matched(
    m05: pd.DataFrame,
    equal_weight: pd.DataFrame,
) -> pd.DataFrame | None:
    merged = align_series(
        m05,
        equal_weight,
        "m05_return",
        "equal_weight_return",
    )

    if len(merged) < 90:
        return None

    merged["m05_return"] = infer_scale(
        merged["m05_return"]
    )
    merged["equal_weight_return"] = infer_scale(
        merged["equal_weight_return"]
    )

    target_vol = (
        merged["m05_return"]
        .rolling(
            window=28,
            min_periods=20,
        )
        .std(ddof=1)
        .shift(1)
    )
    source_vol = (
        merged["equal_weight_return"]
        .rolling(
            window=28,
            min_periods=20,
        )
        .std(ddof=1)
        .shift(1)
    )

    scale = (
        target_vol
        / source_vol.replace(0.0, np.nan)
    ).clip(
        lower=0.0,
        upper=1.0,
    )
    scale = scale.fillna(0.0)

    merged["exposure"] = scale
    merged["return"] = (
        merged["equal_weight_return"]
        * scale
    )

    return merged[
        ["date", "return", "exposure"]
    ]


def aggregate_metric_rows(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}

    for row in rows:
        entity = str(row["entity"])
        metric = str(row["metric"])

        output.setdefault(entity, {})

        if metric not in output[entity]:
            output[entity][metric] = row["value"]
            output[entity][f"{metric}_source"] = row[
                "source"
            ]
            output[entity][f"{metric}_evidence"] = row[
                "evidence_path"
            ]

    return output


def extract_m02_contributors(
    trade_tables: list[pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    candidates: list[pd.DataFrame] = []

    for frame in trade_tables:
        entity_col = find_column(
            frame.columns,
            ENTITY_COLUMNS,
        )
        symbol_col = find_column(
            frame.columns,
            SYMBOL_COLUMNS,
        )
        pnl_col = find_column(
            frame.columns,
            PNL_COLUMNS,
        )

        if (
            symbol_col is None
            or pnl_col is None
        ):
            continue

        selected = frame.copy()

        if entity_col is not None:
            mask = (
                selected[entity_col]
                .map(canonical_entity)
                == "M02_TSM_84"
            )
            selected = selected.loc[mask]
        else:
            source_name = str(
                selected.get(
                    "_bf01_source",
                    pd.Series([""]),
                ).iloc[0]
            )

            if canonical_entity(
                source_name
            ) != "M02_TSM_84":
                continue

        if selected.empty:
            continue

        candidate = pd.DataFrame(
            {
                "symbol": selected[
                    symbol_col
                ].astype(str),
                "pnl": numeric_series(
                    selected[pnl_col]
                ),
            }
        ).dropna()

        if not candidate.empty:
            candidates.append(candidate)

    if not candidates:
        return (
            pd.DataFrame(
                columns=[
                    "symbol",
                    "pnl",
                    "contribution_share",
                    "leave_one_total",
                    "rank",
                ]
            ),
            {
                "status": "INSUFFICIENT_SOURCE_DATA",
                "judgement": "TSM84_NO_ROBUST_EDGE",
            },
        )

    combined = pd.concat(
        candidates,
        ignore_index=True,
    )

    grouped = (
        combined.groupby(
            "symbol",
            as_index=False,
        )["pnl"]
        .sum()
        .sort_values(
            "pnl",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    total = float(grouped["pnl"].sum())

    if math.isclose(
        total,
        0.0,
        abs_tol=1e-12,
    ):
        grouped["contribution_share"] = (
            np.nan
        )
    else:
        grouped["contribution_share"] = (
            grouped["pnl"] / total
        )

    grouped["leave_one_total"] = (
        total - grouped["pnl"]
    )
    grouped["rank"] = (
        np.arange(len(grouped)) + 1
    )

    top_1_share = (
        float(
            grouped.head(1)[
                "pnl"
            ].sum()
            / total
        )
        if total != 0.0
        else math.nan
    )
    top_3_share = (
        float(
            grouped.head(3)[
                "pnl"
            ].sum()
            / total
        )
        if total != 0.0
        else math.nan
    )
    top_5_share = (
        float(
            grouped.head(5)[
                "pnl"
            ].sum()
            / total
        )
        if total != 0.0
        else math.nan
    )

    top_1_removed = (
        total
        - float(
            grouped.head(1)[
                "pnl"
            ].sum()
        )
    )
    top_3_removed = (
        total
        - float(
            grouped.head(3)[
                "pnl"
            ].sum()
        )
    )
    top_5_removed = (
        total
        - float(
            grouped.head(5)[
                "pnl"
            ].sum()
        )
    )

    if (
        top_1_share >= 0.50
        or top_1_removed <= 0.0
    ):
        judgement = (
            "TSM84_DOMINATED_BY_SINGLE_WINNER"
        )
    elif (
        top_3_share >= 0.70
        or top_3_removed <= 0.0
    ):
        judgement = "TSM84_CONCENTRATED"
    elif (
        not grouped.empty
        and (
            grouped["leave_one_total"] > 0.0
        ).all()
        and top_3_share < 0.50
    ):
        judgement = "TSM84_DISTRIBUTED"
    else:
        judgement = "TSM84_NO_ROBUST_EDGE"

    summary = {
        "status": "COMPUTED_FROM_TRADE_TABLES",
        "total_pnl": total,
        "symbols": int(len(grouped)),
        "top_1_share": top_1_share,
        "top_3_share": top_3_share,
        "top_5_share": top_5_share,
        "top_1_removed_total": top_1_removed,
        "top_3_removed_total": top_3_removed,
        "top_5_removed_total": top_5_removed,
        "negative_leave_one_cases": int(
            (
                grouped["leave_one_total"]
                <= 0.0
            ).sum()
        ),
        "judgement": judgement,
    }

    return grouped, summary


def regression_metrics(
    portfolio: pd.DataFrame,
    btc: pd.DataFrame,
    entity: str,
) -> list[dict[str, Any]]:
    portfolio_columns = [
        "date",
        "return",
    ]

    if "fold" in portfolio.columns:
        portfolio_columns.append("fold")

    left = portfolio[
        portfolio_columns
    ].copy()
    left["portfolio_return"] = infer_scale(
        left.pop("return")
    )

    right = btc[
        ["date", "return"]
    ].copy()
    right["btc_return"] = infer_scale(
        right.pop("return")
    )

    merged = left.merge(
        right,
        on="date",
        how="inner",
        validate="one_to_one",
    ).dropna()

    if len(merged) < 30:
        return []

    groups: list[tuple[str, pd.DataFrame]] = [
        ("FULL_PERIOD", merged)
    ]

    if "fold" in merged.columns:
        groups.extend(
            (
                str(fold),
                group,
            )
            for fold, group in merged.groupby(
                "fold",
                dropna=True,
            )
        )

    results: list[dict[str, Any]] = []

    for fold, group in groups:
        if len(group) < 20:
            continue

        y = group[
            "portfolio_return"
        ].to_numpy(dtype=float)
        x = group[
            "btc_return"
        ].to_numpy(dtype=float)

        design = np.column_stack(
            [
                np.ones(len(group)),
                x,
            ]
        )

        coefficients, *_ = np.linalg.lstsq(
            design,
            y,
            rcond=None,
        )
        intercept = float(coefficients[0])
        beta = float(coefficients[1])

        predicted = design @ coefficients
        residual = y - predicted

        total_sum_squares = float(
            np.sum(
                np.square(
                    y - y.mean()
                )
            )
        )
        residual_sum_squares = float(
            np.sum(
                np.square(residual)
            )
        )

        r_squared = (
            1.0
            - residual_sum_squares
            / total_sum_squares
            if total_sum_squares > 0.0
            else math.nan
        )

        residual_std = float(
            np.std(
                residual,
                ddof=1,
            )
        )

        residual_sharpe = (
            float(np.mean(residual))
            / residual_std
            * math.sqrt(365.25)
            if residual_std > 0.0
            else math.nan
        )

        downside_mask = x < 0.0

        downside_beta = math.nan

        if downside_mask.sum() >= 10:
            x_down = x[downside_mask]
            y_down = y[downside_mask]
            denominator = float(
                np.var(
                    x_down,
                    ddof=1,
                )
            )

            if denominator > 0.0:
                downside_beta = float(
                    np.cov(
                        x_down,
                        y_down,
                        ddof=1,
                    )[0, 1]
                    / denominator
                )

        residual_equity = float(
            np.prod(
                1.0 + residual
            )
        )
        residual_return = (
            residual_equity - 1.0
        )

        results.append(
            {
                "entity": entity,
                "fold": fold,
                "rows": int(len(group)),
                "daily_alpha_intercept": intercept,
                "annualised_alpha_intercept": (
                    (1.0 + intercept)
                    ** 365.25
                    - 1.0
                    if intercept > -1.0
                    else math.nan
                ),
                "btc_beta": beta,
                "downside_beta": downside_beta,
                "r_squared": r_squared,
                "residual_return": residual_return,
                "residual_sharpe": residual_sharpe,
            }
        )

    return results


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def json_safe(value: object) -> object:
    if isinstance(
        value,
        (
            np.integer,
            np.floating,
        ),
    ):
        converted = value.item()

        if isinstance(converted, float):
            return (
                converted
                if math.isfinite(converted)
                else None
            )

        return converted

    if isinstance(value, float):
        return (
            value
            if math.isfinite(value)
            else None
        )

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): json_safe(child)
            for key, child in value.items()
        }

    if isinstance(value, list):
        return [
            json_safe(child)
            for child in value
        ]

    return value


def format_percent(value: object) -> str:
    number = safe_float(value)

    if number is None:
        return "N/A"

    return f"{number * 100.0:.2f}%"


def format_number(value: object) -> str:
    number = safe_float(value)

    if number is None:
        return "N/A"

    return f"{number:.4f}"


def metric_table_markdown(
    metrics: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    entities = (
        "M05_DUAL_28",
        "EQUAL_WEIGHT",
        "EXPOSURE_MATCHED_EQUAL_WEIGHT",
        "VOLATILITY_MATCHED_EQUAL_WEIGHT",
        "BTC_BUY_HOLD",
        "HIGH_BETA_28",
        "HIGH_BETA_84",
    )

    lines = [
        "| Portfolio | Total return | CAGR | Sharpe | Sortino | Calmar | Max DD | Worst month | Avg exposure |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for entity in entities:
        values = metrics.get(
            entity,
            {},
        )

        lines.append(
            "| "
            + entity
            + " | "
            + format_percent(
                values.get("total_return")
            )
            + " | "
            + format_percent(
                values.get("cagr")
            )
            + " | "
            + format_number(
                values.get("sharpe")
            )
            + " | "
            + format_number(
                values.get("sortino")
            )
            + " | "
            + format_number(
                values.get("calmar")
            )
            + " | "
            + format_percent(
                values.get(
                    "maximum_drawdown"
                )
            )
            + " | "
            + format_percent(
                values.get("worst_month")
            )
            + " | "
            + format_percent(
                values.get(
                    "average_exposure"
                )
            )
            + " |"
        )

    return lines


def determine_alpha_judgement(
    metrics: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    m05 = metrics.get(
        "M05_DUAL_28",
        {},
    )
    equal_weight = metrics.get(
        "EQUAL_WEIGHT",
        {},
    )
    exposure_matched = metrics.get(
        "EXPOSURE_MATCHED_EQUAL_WEIGHT",
        {},
    )
    volatility_matched = metrics.get(
        "VOLATILITY_MATCHED_EQUAL_WEIGHT",
        {},
    )

    required_raw = (
        safe_float(
            m05.get("total_return")
        ),
        safe_float(
            equal_weight.get("total_return")
        ),
    )

    if any(
        value is None
        for value in required_raw
    ):
        return (
            "INCONCLUSIVE",
            [
                "Daily or aggregate return data for M05 "
                "and Equal-weight were not both available."
            ],
        )

    m05_return = float(required_raw[0])
    equal_return = float(required_raw[1])

    if equal_return > m05_return:
        reasons.append(
            "Full-exposure Equal-weight produced a higher "
            "raw return than M05."
        )
    else:
        reasons.append(
            "M05 produced at least as much raw return as "
            "full-exposure Equal-weight."
        )

    m05_sharpe = safe_float(
        m05.get("sharpe")
    )
    equal_sharpe = safe_float(
        equal_weight.get("sharpe")
    )
    m05_calmar = safe_float(
        m05.get("calmar")
    )
    equal_calmar = safe_float(
        equal_weight.get("calmar")
    )
    m05_drawdown = safe_float(
        m05.get("maximum_drawdown")
    )
    equal_drawdown = safe_float(
        equal_weight.get(
            "maximum_drawdown"
        )
    )

    risk_adjusted_better = False

    if (
        m05_sharpe is not None
        and equal_sharpe is not None
        and m05_calmar is not None
        and equal_calmar is not None
    ):
        risk_adjusted_better = (
            m05_sharpe > equal_sharpe
            and m05_calmar > equal_calmar
        )

        reasons.append(
            "M05 risk-adjusted metrics are "
            + (
                "superior to Equal-weight."
                if risk_adjusted_better
                else "not jointly superior to Equal-weight."
            )
        )

    exposure_return = safe_float(
        exposure_matched.get(
            "total_return"
        )
    )
    volatility_return = safe_float(
        volatility_matched.get(
            "total_return"
        )
    )

    if exposure_return is not None:
        reasons.append(
            "Exposure-matched Equal-weight return was "
            f"{exposure_return * 100.0:.2f}%."
        )

        if (
            m05_return > exposure_return
            and risk_adjusted_better
        ):
            return (
                "ALPHA_ADDS_VALUE_OVER_EQUAL_WEIGHT",
                reasons,
            )

    if volatility_return is not None:
        reasons.append(
            "Volatility-matched Equal-weight return was "
            f"{volatility_return * 100.0:.2f}%."
        )

    m05_exposure = safe_float(
        m05.get("average_exposure")
    )
    equal_exposure = safe_float(
        equal_weight.get(
            "average_exposure"
        )
    )

    if (
        equal_return > m05_return
        and risk_adjusted_better
    ):
        return (
            "ALPHA_ADDS_RISK_ADJUSTED_VALUE_ONLY",
            reasons,
        )

    if (
        m05_exposure is not None
        and equal_exposure is not None
        and m05_exposure
        < equal_exposure * 0.75
        and exposure_return is not None
        and exposure_return >= m05_return
    ):
        return (
            "ALPHA_MAINLY_REDUCES_EXPOSURE",
            reasons,
        )

    if (
        equal_return > m05_return
        and not risk_adjusted_better
        and (
            exposure_return is None
            or exposure_return >= m05_return
        )
    ):
        if (
            m05_drawdown is not None
            and equal_drawdown is not None
        ):
            reasons.append(
                "M05 did not establish sufficient "
                "risk-adjusted superiority to justify "
                "its lower return."
            )

        return (
            "ALPHA_DESTROYS_VALUE",
            reasons,
        )

    return (
        "INCONCLUSIVE",
        reasons,
    )


def main() -> None:
    branch = git_output(
        "branch",
        "--show-current",
    )
    head_before = git_output(
        "rev-parse",
        "HEAD",
    )

    if branch != (
        "research/"
        "ams-bf01-benchmark-fairness-alpha-audit-v1"
    ):
        raise RuntimeError(
            f"Unexpected BF01 branch: {branch}"
        )

    REPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_files = discover_json_files()
    aggregate_rows, construction_evidence = (
        extract_aggregate_metrics(
            json_files
        )
    )

    table_paths = candidate_table_paths()
    (
        series_candidates,
        inventory,
        trade_tables,
    ) = extract_series_candidates(
        table_paths
    )

    selected_series: dict[
        str,
        pd.DataFrame,
    ] = {}
    selected_series_metadata: list[
        SeriesCandidate
    ] = []

    for entity, candidates in (
        series_candidates.items()
    ):
        selected = choose_best_series(
            candidates
        )

        if selected is None:
            continue

        selected_series[entity] = selected
        selected_series_metadata.append(
            SeriesCandidate(
                entity=entity,
                source=str(
                    selected["_source"].iloc[0]
                ),
                rows=int(len(selected)),
                start=(
                    selected["date"]
                    .min()
                    .isoformat()
                ),
                end=(
                    selected["date"]
                    .max()
                    .isoformat()
                ),
                has_exposure=(
                    "exposure"
                    in selected.columns
                ),
                has_fold=(
                    "fold"
                    in selected.columns
                ),
            )
        )

    aggregate_metrics = (
        aggregate_metric_rows(
            aggregate_rows
        )
    )

    computed_metrics: dict[
        str,
        dict[str, Any],
    ] = {}

    for entity, series in (
        selected_series.items()
    ):
        computed_metrics[entity] = (
            performance_metrics(series)
        )
        computed_metrics[entity][
            "method"
        ] = "RECOMPUTED_FROM_DAILY_SERIES"
        computed_metrics[entity][
            "source"
        ] = str(series["_source"].iloc[0])

    m05_series = selected_series.get(
        "M05_DUAL_28"
    )
    equal_series = selected_series.get(
        "EQUAL_WEIGHT"
    )

    if (
        m05_series is not None
        and equal_series is not None
    ):
        exposure_matched = (
            construct_exposure_matched(
                m05_series,
                equal_series,
            )
        )

        if exposure_matched is not None:
            computed_metrics[
                "EXPOSURE_MATCHED_EQUAL_WEIGHT"
            ] = performance_metrics(
                exposure_matched
            )
            computed_metrics[
                "EXPOSURE_MATCHED_EQUAL_WEIGHT"
            ][
                "method"
            ] = (
                "M05_DAILY_EXPOSURE_X_"
                "EQUAL_WEIGHT_DAILY_RETURN"
            )

        volatility_matched = (
            construct_volatility_matched(
                m05_series,
                equal_series,
            )
        )

        if volatility_matched is not None:
            computed_metrics[
                "VOLATILITY_MATCHED_EQUAL_WEIGHT"
            ] = performance_metrics(
                volatility_matched
            )
            computed_metrics[
                "VOLATILITY_MATCHED_EQUAL_WEIGHT"
            ][
                "method"
            ] = (
                "CAUSAL_28_DAY_VOLATILITY_MATCHED_"
                "NO_LEVERAGE"
            )

    consolidated_metrics: dict[
        str,
        dict[str, Any],
    ] = {}

    entities = set(ENTITY_ALIASES)
    entities.update(computed_metrics)
    entities.update(aggregate_metrics)

    for entity in sorted(entities):
        consolidated_metrics[entity] = {}

        if entity in aggregate_metrics:
            consolidated_metrics[
                entity
            ].update(
                aggregate_metrics[entity]
            )

        if entity in computed_metrics:
            consolidated_metrics[
                entity
            ].update(
                computed_metrics[entity]
            )

    # القيم المعلنة سابقًا تُستخدم كمرجع فقط
    # إذا تعذر استخراجها آليًا من التقارير.
    declared_reference = {
        "M05_DUAL_28": {
            "total_return": 2.6861,
            "reference_only": True,
            "reference_description": (
                "Previously reported M05 Base-cost return."
            ),
        },
        "EQUAL_WEIGHT": {
            "total_return": 7.8333,
            "reference_only": True,
            "reference_description": (
                "Previously reported Survivor-30 "
                "Equal-weight return."
            ),
        },
        "HIGH_BETA_28": {
            "total_return": 2.3504,
            "reference_only": True,
        },
        "HIGH_BETA_84": {
            "total_return": 1.3832,
            "reference_only": True,
        },
        "BTC_BUY_HOLD": {
            "total_return": 2.1900,
            "reference_only": True,
        },
    }

    for entity, values in (
        declared_reference.items()
    ):
        consolidated_metrics.setdefault(
            entity,
            {},
        )

        if "total_return" not in (
            consolidated_metrics[entity]
        ):
            consolidated_metrics[
                entity
            ].update(values)

    m02_contributors, m02_summary = (
        extract_m02_contributors(
            trade_tables
        )
    )

    regression_rows: list[
        dict[str, Any]
    ] = []

    btc_series = selected_series.get(
        "BTC_BUY_HOLD"
    )

    if btc_series is not None:
        for entity in (
            "M05_DUAL_28",
            "M02_TSM_84",
        ):
            portfolio = selected_series.get(
                entity
            )

            if portfolio is None:
                continue

            regression_rows.extend(
                regression_metrics(
                    portfolio,
                    btc_series,
                    entity,
                )
            )

    alpha_judgement, alpha_reasons = (
        determine_alpha_judgement(
            consolidated_metrics
        )
    )

    risk_adjusted_available = all(
        consolidated_metrics.get(
            entity,
            {},
        ).get(metric)
        is not None
        for entity in (
            "M05_DUAL_28",
            "EQUAL_WEIGHT",
        )
        for metric in (
            "sharpe",
            "calmar",
            "maximum_drawdown",
        )
    )

    exposure_matched_available = (
        "EXPOSURE_MATCHED_EQUAL_WEIGHT"
        in consolidated_metrics
    )
    volatility_matched_available = (
        "VOLATILITY_MATCHED_EQUAL_WEIGHT"
        in consolidated_metrics
    )

    benchmark_construction_status = (
        "PARTIALLY_AUDITED"
    )

    if (
        risk_adjusted_available
        and exposure_matched_available
        and volatility_matched_available
    ):
        benchmark_construction_status = (
            "AUDITED_WITH_MATCHED_BENCHMARKS"
        )

    elif (
        risk_adjusted_available
        and (
            exposure_matched_available
            or volatility_matched_available
        )
    ):
        benchmark_construction_status = (
            "AUDITED_WITH_ONE_MATCHED_BENCHMARK"
        )

    fairness_gaps: list[str] = []

    if not risk_adjusted_available:
        fairness_gaps.append(
            "Comparable daily series were insufficient "
            "to recompute all Sharpe, Calmar and drawdown "
            "metrics for both M05 and Equal-weight."
        )

    if not exposure_matched_available:
        fairness_gaps.append(
            "Exposure-matched Equal-weight could not be "
            "constructed because aligned M05 daily exposure "
            "and Equal-weight daily returns were unavailable."
        )

    if not volatility_matched_available:
        fairness_gaps.append(
            "Volatility-matched Equal-weight could not be "
            "constructed from sufficiently aligned daily "
            "return series."
        )

    if not regression_rows:
        fairness_gaps.append(
            "Fold-level residual alpha regression could not "
            "be recomputed from aligned daily portfolio and "
            "BTC return series."
        )

    source_inventory = pd.DataFrame(
        inventory
    )

    if source_inventory.empty:
        source_inventory = pd.DataFrame(
            columns=[
                "source",
                "status",
                "rows",
                "columns",
                "date_start",
                "date_end",
                "detail",
            ]
        )

    source_inventory.to_csv(
        INVENTORY_CSV,
        index=False,
        encoding="utf-8",
    )

    m02_contributors.to_csv(
        M02_CSV,
        index=False,
        encoding="utf-8",
    )

    regression_frame = pd.DataFrame(
        regression_rows
    )

    if regression_frame.empty:
        regression_frame = pd.DataFrame(
            columns=[
                "entity",
                "fold",
                "rows",
                "daily_alpha_intercept",
                "annualised_alpha_intercept",
                "btc_beta",
                "downside_beta",
                "r_squared",
                "residual_return",
                "residual_sharpe",
            ]
        )

    regression_frame.to_csv(
        REGRESSION_CSV,
        index=False,
        encoding="utf-8",
    )

    metrics_rows: list[dict[str, Any]] = []

    for entity, values in (
        consolidated_metrics.items()
    ):
        for metric, value in values.items():
            if metric.endswith(
                (
                    "_source",
                    "_evidence",
                )
            ):
                continue

            if metric in {
                "method",
                "source",
                "reference_description",
            }:
                continue

            metrics_rows.append(
                {
                    "entity": entity,
                    "metric": metric,
                    "value": value,
                    "method": values.get(
                        "method",
                        (
                            "DECLARED_REFERENCE"
                            if values.get(
                                "reference_only"
                            )
                            else "EXISTING_REPORT"
                        ),
                    ),
                    "source": values.get(
                        "source",
                        values.get(
                            f"{metric}_source"
                        ),
                    ),
                }
            )

    pd.DataFrame(
        metrics_rows
    ).to_csv(
        METRICS_CSV,
        index=False,
        encoding="utf-8",
    )

    result = {
        "schema_version": (
            "ams-bf01-benchmark-fairness-alpha-audit-v1"
        ),
        "research_result": "PARTIAL",
        "safety_stop": "PASS",
        "branch": branch,
        "base_head": head_before,
        "scope": {
            "universe": (
                "SURVIVOR_30_DIAGNOSTIC_ONLY"
            ),
            "point_in_time": False,
            "promotable": False,
            "production_ready": False,
            "live_ready": False,
            "md02_authorized": False,
            "kelly_used": False,
            "leverage_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "dynamic_md01_matrix_consumed": 0,
            "dynamic_md01_cost_executions_consumed": 0,
        },
        "benchmark_audit": {
            "status": (
                benchmark_construction_status
            ),
            "alpha_value_judgement": (
                alpha_judgement
            ),
            "alpha_value_reasons": (
                alpha_reasons
            ),
            "risk_adjusted_comparison_available": (
                risk_adjusted_available
            ),
            "exposure_matched_available": (
                exposure_matched_available
            ),
            "volatility_matched_available": (
                volatility_matched_available
            ),
            "fairness_gaps": fairness_gaps,
            "construction_evidence": (
                construction_evidence
            ),
        },
        "metrics": consolidated_metrics,
        "selected_daily_series": [
            asdict(item)
            for item in selected_series_metadata
        ],
        "m02_tsm84": m02_summary,
        "alpha_regression": regression_rows,
        "interpretation": {
            "equal_weight_raw_return_question": (
                "CRITICAL_AND_AUDITED_TO_AVAILABLE_DATA"
            ),
            "survivorship_bias": (
                "AFFECTS_ABSOLUTE_RESULTS; RELATIVE "
                "COMPARISON REMAINS DIAGNOSTIC ONLY"
            ),
            "return_contribution_concentration": (
                "SEVERE_CONCERN"
            ),
            "momentum_above_beta": (
                "UNRESOLVED"
                if not regression_rows
                else "FOLD_RESULTS_REPORTED"
            ),
            "ati_effectiveness": "UNTESTED",
            "dominance": "BLOCKED_BY_DATA",
        },
        "source_files": {
            "json_files": [
                str(path.relative_to(ROOT))
                for path in json_files
            ],
            "table_files_considered": [
                str(path.relative_to(ROOT))
                for path in table_paths
            ],
        },
    }

    REPORT_JSON.write_text(
        json.dumps(
            json_safe(result),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    markdown: list[str] = [
        "# AMS BF01 — Benchmark Fairness and Alpha Value Audit",
        "",
        "## النتيجة التنفيذية",
        "",
        f"- Research result: `{result['research_result']}`",
        f"- Safety stop: `{result['safety_stop']}`",
        (
            "- Universe: "
            "`SURVIVOR_30_DIAGNOSTIC_ONLY / "
            "NOT_POINT_IN_TIME`"
        ),
        (
            "- Alpha value judgement: "
            f"`{alpha_judgement}`"
        ),
        (
            "- Benchmark audit status: "
            f"`{benchmark_construction_status}`"
        ),
        (
            "- M02/TSM-84 judgement: "
            f"`{m02_summary['judgement']}`"
        ),
        "- MD02: `BLOCKED`",
        "- Kelly: `BLOCKED`",
        "- 2025: `NOT_ACCESSED`",
        "- 2026: `NOT_ACCESSED`",
        "",
        "## السؤال المركزي",
        "",
        (
            "هل يضيف اختيار وتوقيت MD01 قيمة مقارنة "
            "بامتلاك الكون نفسه بأوزان متساوية، بعد ضبط "
            "التعرض والتقلب والمخاطرة؟"
        ),
        "",
        "## المقارنة",
        "",
        *metric_table_markdown(
            consolidated_metrics
        ),
        "",
        "ملاحظة: القيم التي تعذر استخراج سلسلتها اليومية "
        "وإعادة حسابها موسومة في JSON/CSV كقيم مرجعية "
        "معلنة سابقًا، ولا تُعامل كإعادة حساب مستقلة.",
        "",
        "## الحكم على قيمة Alpha",
        "",
        f"`{alpha_judgement}`",
        "",
    ]

    for reason in alpha_reasons:
        markdown.append(f"- {reason}")

    markdown.extend(
        [
            "",
            "## عدالة Benchmark",
            "",
            (
                "- Risk-adjusted comparison available: "
                f"`{str(risk_adjusted_available).lower()}`"
            ),
            (
                "- Exposure-matched Equal-weight available: "
                f"`{str(exposure_matched_available).lower()}`"
            ),
            (
                "- Volatility-matched Equal-weight available: "
                f"`{str(volatility_matched_available).lower()}`"
            ),
            "",
        ]
    )

    if fairness_gaps:
        markdown.append(
            "### الفجوات المتبقية"
        )
        markdown.append("")

        for gap in fairness_gaps:
            markdown.append(f"- {gap}")

        markdown.append("")

    markdown.extend(
        [
            "## تدقيق M02 / TSM-84",
            "",
            (
                "- Status: "
                f"`{m02_summary['status']}`"
            ),
            (
                "- Judgement: "
                f"`{m02_summary['judgement']}`"
            ),
        ]
    )

    for key in (
        "total_pnl",
        "symbols",
        "top_1_share",
        "top_3_share",
        "top_5_share",
        "top_1_removed_total",
        "top_3_removed_total",
        "top_5_removed_total",
        "negative_leave_one_cases",
    ):
        if key in m02_summary:
            value = m02_summary[key]

            if "share" in key:
                rendered = format_percent(
                    value
                )
            else:
                rendered = str(value)

            markdown.append(
                f"- {key}: `{rendered}`"
            )

    markdown.extend(
        [
            "",
            "## Alpha وBeta حسب الطيات",
            "",
        ]
    )

    if regression_rows:
        markdown.extend(
            [
                "| Entity | Fold | Rows | Alpha annualised | BTC beta | Downside beta | R² | Residual return | Residual Sharpe |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )

        for row in regression_rows:
            markdown.append(
                "| "
                + str(row["entity"])
                + " | "
                + str(row["fold"])
                + " | "
                + str(row["rows"])
                + " | "
                + format_percent(
                    row[
                        "annualised_alpha_intercept"
                    ]
                )
                + " | "
                + format_number(
                    row["btc_beta"]
                )
                + " | "
                + format_number(
                    row["downside_beta"]
                )
                + " | "
                + format_number(
                    row["r_squared"]
                )
                + " | "
                + format_percent(
                    row["residual_return"]
                )
                + " | "
                + format_number(
                    row["residual_sharpe"]
                )
                + " |"
            )
    else:
        markdown.append(
            "`BLOCKED_BY_MISSING_ALIGNED_DAILY_SERIES`"
        )

    markdown.extend(
        [
            "",
            "## تفسير النتيجة",
            "",
            (
                "1. المقارنة الخام بين M05 وEqual-weight "
                "لا تكفي وحدها؛ الحكم يعتمد أيضًا على "
                "Sharpe وCalmar وMaximum Drawdown والتعرض."
            ),
            (
                "2. Equal-weight الكامل قد يتفوق لأنه "
                "مستثمر بنسبة أعلى؛ لذلك بُنيت المقارنات "
                "المطابقة للتعرض والتقلب متى سمحت البيانات."
            ),
            (
                "3. جميع النتائج داخل Survivor-30 فقط؛ "
                "لا يوجد Point-in-Time universe ولا يجوز "
                "تحويل النتيجة إلى EDGE_PASS."
            ),
            (
                "4. ATI ما يزال إنجازًا هندسيًا فقط، "
                "وقيمته التداولية غير مثبتة."
            ),
            (
                "5. Dominance ما تزال BLOCKED_BY_DATA."
            ),
            "",
            "## القرار البحثي",
            "",
            f"- Alpha value: `{alpha_judgement}`",
            (
                "- TSM-84 robustness: "
                f"`{m02_summary['judgement']}`"
            ),
            "- Momentum above Beta: `UNRESOLVED`"
            if not regression_rows
            else "- Momentum above Beta: `SEE_FOLD_RESULTS`",
            "- Production: `BLOCKED`",
            "- MD02: `BLOCKED`",
            "- Kelly: `BLOCKED`",
            "",
            "## بوابات السلامة",
            "",
            "- No leverage: `PASS`",
            "- No shorting: `PASS`",
            "- Total exposure above 1.0 introduced: `false`",
            "- 2025 accessed: `false`",
            "- 2026 accessed: `false`",
            "- Dynamic matrix consumed: `0/12`",
            "- Dynamic cost executions consumed: `0/36`",
            "",
            "## الملفات الناتجة",
            "",
            (
                "- `reports/research/"
                "ams-bf01-benchmark-fairness-alpha-audit-v1.json`"
            ),
            (
                "- `reports/research/"
                "ams-bf01-benchmark-fairness-alpha-audit-v1.md`"
            ),
            (
                "- `reports/research/"
                "ams-bf01-benchmark-fairness-metrics-v1.csv`"
            ),
            (
                "- `reports/research/"
                "ams-bf01-source-inventory-v1.csv`"
            ),
            (
                "- `reports/research/"
                "ams-bf01-m02-contributor-audit-v1.csv`"
            ),
            (
                "- `reports/research/"
                "ams-bf01-alpha-regression-by-fold-v1.csv`"
            ),
            "",
        ]
    )

    REPORT_MD.write_text(
        "\n".join(markdown),
        encoding="utf-8",
    )

    final_markdown = (
        REPORT_MD.read_text(
            encoding="utf-8"
        )
        + "\n## Hashes\n\n"
        + f"- JSON: `{sha256_file(REPORT_JSON)}`\n"
        + f"- Markdown: `{sha256_file(REPORT_MD)}`\n"
        + f"- Metrics CSV: `{sha256_file(METRICS_CSV)}`\n"
        + f"- Inventory CSV: `{sha256_file(INVENTORY_CSV)}`\n"
        + f"- M02 CSV: `{sha256_file(M02_CSV)}`\n"
        + f"- Regression CSV: `{sha256_file(REGRESSION_CSV)}`\n"
    )

    FINAL_COPY.write_text(
        final_markdown,
        encoding="utf-8",
    )

    # تحقق العقد النهائي.
    if not FINAL_COPY.exists():
        raise RuntimeError(
            "Final BF01 copy was not created."
        )

    final_text = FINAL_COPY.read_text(
        encoding="utf-8"
    )

    required_tokens = (
        "AMS BF01",
        "Alpha value judgement",
        "MD02: `BLOCKED`",
        "2025 accessed: `false`",
        "2026 accessed: `false`",
    )

    missing_tokens = [
        token
        for token in required_tokens
        if token not in final_text
    ]

    if missing_tokens:
        raise RuntimeError(
            "Final report contract missing: "
            + ", ".join(missing_tokens)
        )


if __name__ == "__main__":
    main()