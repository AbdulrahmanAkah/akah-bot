from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path.cwd()

RESEARCH_START = pd.Timestamp(
    "2021-01-01T00:00:00Z"
)

RESEARCH_END_EXCLUSIVE = pd.Timestamp(
    "2025-01-01T00:00:00Z"
)

DEFAULT_RAW_ROOT = (
    ROOT
    / "data/raw"
)

OUTPUT_ROOT = (
    ROOT
    / "data/research/ams-v3/"
    "kucoin-spot-usdt"
)

FOUR_HOUR_PATH = (
    OUTPUT_ROOT
    / "ams-v3-kucoin-spot-usdt-4h.parquet"
)

EIGHT_HOUR_PATH = (
    OUTPUT_ROOT
    / "ams-v3-kucoin-spot-usdt-8h.parquet"
)

DAILY_PATH = (
    OUTPUT_ROOT
    / "ams-v3-kucoin-spot-usdt-1d.parquet"
)

REGISTRATION_PATH = (
    ROOT
    / "reports/research/"
    "ams-v3-4h-dataset-registration-v1.json"
)

MANIFEST_PATH = (
    ROOT
    / "reports/research/"
    "ams-v3-4h-dataset-manifest-v1.json"
)

READINESS_PATH = (
    ROOT
    / "reports/research/"
    "ams-v3-mtf-data-readiness-v1.json"
)

EXPERIMENT_PATH = (
    ROOT
    / "reports/research/"
    "ams-v3-experiment-ledger-v1.json"
)

PROJECT_PATH = (
    ROOT
    / "reports/research/"
    "project-research-ledger-v3.json"
)

SUMMARY_PATH = Path(
    r"C:\SIRAJ\Reports\ams-v3-kucoin-4h-build-summary.json"
)

ALIASES: dict[str, tuple[str, ...]] = {
    "RNDR": (
        "RNDR/USDT",
        "RENDER/USDT",
    ),
    "RENDER": (
        "RENDER/USDT",
        "RNDR/USDT",
    ),
    "MATIC": (
        "MATIC/USDT",
        "POL/USDT",
    ),
    "POL": (
        "POL/USDT",
        "MATIC/USDT",
    ),
    "XNO": (
        "XNO/USDT",
        "NANO/USDT",
    ),
    "NANO": (
        "NANO/USDT",
        "XNO/USDT",
    ),
    "BCH": (
        "BCH/USDT",
        "BCHABC/USDT",
    ),
}


class DatasetBuildError(RuntimeError):
    """Raised when the AMS V3 dataset cannot be built safely."""


def utc_now() -> str:
    return (
        datetime.now(
            tz=UTC
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
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
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_json(
    path: Path,
) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise DatasetBuildError(
            f"Expected JSON object: {path}"
        )

    return payload


def file_sha256(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def canonical_frame_sha256(
    frame: pd.DataFrame,
) -> str:
    ordered = frame.sort_values(
        [
            "symbol",
            "bar_open_time",
        ],
        kind="mergesort",
    ).reset_index(
        drop=True
    )

    text = ordered.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.12g",
        date_format="%Y-%m-%dT%H:%M:%S.%fZ",
    )

    return hashlib.sha256(
        text.encode(
            "utf-8"
        )
    ).hexdigest()


def load_module(
    path: Path,
    name: str,
) -> ModuleType:
    specification = (
        importlib.util.spec_from_file_location(
            name,
            path,
        )
    )

    if (
        specification is None
        or specification.loader is None
    ):
        raise DatasetBuildError(
            f"Could not load module: {path}"
        )

    module = importlib.util.module_from_spec(
        specification
    )

    sys.modules[name] = module

    specification.loader.exec_module(
        module
    )

    return module


def normalize_base_symbol(
    raw_symbol: object,
) -> str:
    value = re.sub(
        r"[^A-Z0-9]",
        "",
        str(
            raw_symbol
        ).upper(),
    )

    for suffix in (
        "USDT",
        "USDC",
        "BUSD",
        "USD",
    ):
        if (
            value.endswith(
                suffix
            )
            and len(value) > len(suffix)
        ):
            value = value[
                : -len(suffix)
            ]

            break

    if value in {
        "",
        "USD",
        "USDT",
        "USDC",
        "BUSD",
    }:
        raise DatasetBuildError(
            f"Invalid base symbol: {raw_symbol!r}"
        )

    return value


def candidate_symbols(
    base_symbol: str,
) -> tuple[str, ...]:
    base = normalize_base_symbol(
        base_symbol
    )

    candidates = (
        ALIASES.get(
            base,
            (),
        )
        + (
            f"{base}/USDT",
        )
    )

    return tuple(
        dict.fromkeys(
            candidates
        )
    )


def load_research_universe() -> tuple[
    tuple[str, ...],
    dict[str, dict[str, str]],
]:
    loader_path = (
        ROOT
        / "scripts/research/"
        "run_ams_v1_h01.py"
    )

    loader = load_module(
        loader_path,
        "_ams_v3_kucoin_universe_loader",
    )

    history = loader.load_history()

    if not isinstance(
        history,
        pd.DataFrame,
    ):
        raise DatasetBuildError(
            "Historical loader did not return a DataFrame."
        )

    symbol_column = next(
        (
            column
            for column in (
                "symbol",
                "asset",
                "ticker",
            )
            if column in history.columns
        ),
        None,
    )

    if symbol_column is None:
        raise DatasetBuildError(
            "Historical symbol column was not found."
        )

    timestamp_column = next(
        (
            column
            for column in (
                "snapshot_time",
                "timestamp",
                "time",
                "date",
            )
            if column in history.columns
        ),
        None,
    )

    raw_timestamps = (
        history.index
        if timestamp_column is None
        else history[
            timestamp_column
        ]
    )

    timestamps = pd.to_datetime(
        raw_timestamps,
        utc=True,
        errors="raise",
    )

    if timestamps.max() >= RESEARCH_END_EXCLUSIVE:
        raise DatasetBuildError(
            "Historical universe contains post-2024 data."
        )

    normalized = pd.DataFrame(
        {
            "symbol": [
                normalize_base_symbol(
                    value
                )
                for value in history[
                    symbol_column
                ].tolist()
            ],
            "timestamp": timestamps,
        }
    )

    coverage: dict[
        str,
        dict[str, str],
    ] = {}

    for symbol, group in normalized.groupby(
        "symbol",
        sort=True,
    ):
        minimum = pd.Timestamp(
            group[
                "timestamp"
            ].min()
        )

        maximum = pd.Timestamp(
            group[
                "timestamp"
            ].max()
        )

        coverage[str(symbol)] = {
            "universe_first_timestamp": (
                minimum.isoformat()
            ),
            "universe_last_timestamp": (
                maximum.isoformat()
            ),
        }

    symbols = sorted(
        coverage
    )

    if "BTC" not in symbols:
        symbols.insert(
            0,
            "BTC",
        )

        coverage["BTC"] = {
            "universe_first_timestamp": (
                RESEARCH_START.isoformat()
            ),
            "universe_last_timestamp": (
                (
                    RESEARCH_END_EXCLUSIVE
                    - pd.Timedelta(
                        days=1
                    )
                ).isoformat()
            ),
        }

    return (
        tuple(
            symbols
        ),
        coverage,
    )


def symbol_slug(
    unified_symbol: str,
) -> str:
    return (
        unified_symbol
        .replace(
            "/",
            "-",
        )
        .replace(
            ":",
            "-",
        )
    )


def source_dataset_path(
    raw_root: Path,
    unified_symbol: str,
) -> Path:
    return (
        raw_root
        / "kucoin"
        / symbol_slug(
            unified_symbol
        )
        / "4h.parquet"
    )


def run_sync(
    *,
    unified_symbol: str,
    raw_root: Path,
) -> dict[str, Any]:
    environment = os.environ.copy()

    python_path = str(
        ROOT
        / "src"
    )

    existing_python_path = environment.get(
        "PYTHONPATH",
        "",
    )

    environment["PYTHONPATH"] = (
        python_path
        + (
            os.pathsep
            + existing_python_path
            if existing_python_path
            else ""
        )
    )

    command = [
        sys.executable,
        "-m",
        "spotbot.cli.sync_data",
        "--exchange",
        "kucoin",
        "--symbol",
        unified_symbol,
        "--timeframe",
        "4h",
        "--since",
        "2021-01-01T00:00:00Z",
        "--until",
        "2025-01-01T00:00:00Z",
        "--root",
        str(
            raw_root
        ),
    ]

    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
    )

    dataset_path = source_dataset_path(
        raw_root,
        unified_symbol,
    )

    return {
        "symbol": unified_symbol,
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-3000:],
        "stderr_tail": completed.stderr[-3000:],
        "dataset_path": str(
            dataset_path
        ),
        "dataset_exists": (
            dataset_path.is_file()
        ),
    }


def canonicalize_source_frame(
    frame: pd.DataFrame,
    *,
    base_symbol: str,
    source_symbol: str,
) -> pd.DataFrame:
    required_columns = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    missing = sorted(
        required_columns.difference(
            frame.columns
        )
    )

    if missing:
        raise DatasetBuildError(
            f"Missing source columns for "
            f"{source_symbol}: {missing}"
        )

    result = frame.loc[
        :,
        [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    ].copy()

    result[
        "bar_close_time"
    ] = pd.to_datetime(
        result[
            "timestamp"
        ],
        utc=True,
        errors="raise",
    )

    result = result.loc[
        result[
            "bar_close_time"
        ].gt(
            RESEARCH_START
        )
        & result[
            "bar_close_time"
        ].le(
            RESEARCH_END_EXCLUSIVE
        )
    ].copy()

    for column in (
        "open",
        "high",
        "low",
        "close",
        "volume",
    ):
        result[column] = pd.to_numeric(
            result[column],
            errors="raise",
        ).astype(
            "float64"
        )

    result[
        "bar_open_time"
    ] = (
        result[
            "bar_close_time"
        ]
        - pd.Timedelta(
            hours=4
        )
    )

    result["symbol"] = base_symbol
    result["source_exchange"] = "kucoin"
    result["source_symbol"] = source_symbol

    return result.loc[
        :,
        [
            "symbol",
            "source_exchange",
            "source_symbol",
            "bar_open_time",
            "bar_close_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    ].sort_values(
        "bar_open_time",
        kind="mergesort",
    ).reset_index(
        drop=True
    )


def read_source_dataset(
    *,
    raw_root: Path,
    base_symbol: str,
    unified_symbol: str,
) -> pd.DataFrame:
    path = source_dataset_path(
        raw_root,
        unified_symbol,
    )

    if not path.is_file():
        raise DatasetBuildError(
            f"Source dataset was not created: {path}"
        )

    source = pd.read_parquet(
        path
    )

    return canonicalize_source_frame(
        source,
        base_symbol=base_symbol,
        source_symbol=unified_symbol,
    )


def merge_alias_frames(
    *,
    base_symbol: str,
    frames: list[pd.DataFrame],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    combined = pd.concat(
        frames,
        ignore_index=True,
    ).sort_values(
        [
            "bar_open_time",
            "source_symbol",
        ],
        kind="mergesort",
    )

    overlap_count = int(
        combined.duplicated(
            subset=[
                "bar_open_time",
            ],
            keep=False,
        ).sum()
    )

    combined = combined.drop_duplicates(
        subset=[
            "bar_open_time",
        ],
        keep="first",
    ).sort_values(
        "bar_open_time",
        kind="mergesort",
    ).reset_index(
        drop=True
    )

    transitions: list[
        dict[str, Any]
    ] = []

    source_values = combined[
        "source_symbol"
    ].astype(
        str
    )

    transition_positions = np.flatnonzero(
        source_values.ne(
            source_values.shift(
                1
            )
        ).to_numpy()
    )

    for position in transition_positions:
        if position == 0:
            continue

        previous_close = float(
            combined.iloc[
                position - 1
            ][
                "close"
            ]
        )

        current_open = float(
            combined.iloc[
                position
            ][
                "open"
            ]
        )

        ratio = (
            current_open
            / previous_close
        )

        transitions.append(
            {
                "symbol": base_symbol,
                "timestamp": (
                    pd.Timestamp(
                        combined.iloc[
                            position
                        ][
                            "bar_open_time"
                        ]
                    ).isoformat()
                ),
                "from_source_symbol": str(
                    combined.iloc[
                        position - 1
                    ][
                        "source_symbol"
                    ]
                ),
                "to_source_symbol": str(
                    combined.iloc[
                        position
                    ][
                        "source_symbol"
                    ]
                ),
                "boundary_price_ratio": ratio,
                "valid": (
                    0.50
                    <= ratio
                    <= 2.00
                ),
            }
        )

    combined.attrs[
        "alias_overlap_row_count"
    ] = overlap_count

    return (
        combined,
        transitions,
    )


def validate_four_hour_dataset(
    frame: pd.DataFrame,
    *,
    expected_symbols: tuple[str, ...],
    universe_coverage: dict[
        str,
        dict[str, str],
    ],
    alias_transitions: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    duplicate_count = int(
        frame.duplicated(
            subset=[
                "symbol",
                "bar_open_time",
            ],
            keep=False,
        ).sum()
    )

    invalid_price_mask = frame[
        [
            "open",
            "high",
            "low",
            "close",
        ]
    ].le(
        0.0
    ).any(
        axis=1
    )

    invalid_ohlc_mask = (
        frame["high"].lt(
            frame[
                [
                    "open",
                    "close",
                    "low",
                ]
            ].max(
                axis=1
            )
        )
        | frame["low"].gt(
            frame[
                [
                    "open",
                    "close",
                    "high",
                ]
            ].min(
                axis=1
            )
        )
    )

    invalid_volume_mask = frame[
        "volume"
    ].lt(
        0.0
    )

    open_times = pd.DatetimeIndex(
        pd.to_datetime(
            frame[
                "bar_open_time"
            ],
            utc=True,
        )
    )

    close_times = pd.DatetimeIndex(
        pd.to_datetime(
            frame[
                "bar_close_time"
            ],
            utc=True,
        )
    )

    misaligned_mask = np.asarray(
        (
            open_times.minute != 0
        )
        | (
            open_times.second != 0
        )
        | (
            open_times.microsecond != 0
        )
        | (
            open_times.hour % 4 != 0
        )
        | (
            close_times.minute != 0
        )
        | (
            close_times.second != 0
        )
        | (
            close_times.microsecond != 0
        )
        | (
            close_times.hour % 4 != 0
        ),
        dtype=bool,
    )

    duration_error_count = int(
        (
            frame[
                "bar_close_time"
            ]
            - frame[
                "bar_open_time"
            ]
        ).ne(
            pd.Timedelta(
                hours=4
            )
        ).sum()
    )

    available_symbols = set(
        frame[
            "symbol"
        ].astype(
            str
        ).unique()
    )

    missing_symbols = sorted(
        set(
            expected_symbols
        ).difference(
            available_symbols
        )
    )

    missing_internal_count = 0
    coverage_start_gap_symbols: list[str] = []
    coverage_end_gap_symbols: list[str] = []

    symbol_records: dict[
        str,
        dict[str, Any],
    ] = {}

    for symbol, group in frame.groupby(
        "symbol",
        sort=True,
    ):
        ordered = group.sort_values(
            "bar_open_time"
        )

        index = pd.DatetimeIndex(
            pd.to_datetime(
                ordered[
                    "bar_open_time"
                ],
                utc=True,
            )
        )

        expected_index = pd.date_range(
            start=index.min(),
            end=index.max(),
            freq="4h",
            tz="UTC",
        )

        missing_internal = (
            expected_index.difference(
                index
            )
        )

        missing_internal_count += len(
            missing_internal
        )

        universe_record = (
            universe_coverage[
                str(symbol)
            ]
        )

        universe_first = pd.Timestamp(
            universe_record[
                "universe_first_timestamp"
            ]
        )

        universe_last = pd.Timestamp(
            universe_record[
                "universe_last_timestamp"
            ]
        )

        dataset_first = pd.Timestamp(
            ordered[
                "bar_open_time"
            ].min()
        )

        dataset_last = pd.Timestamp(
            ordered[
                "bar_close_time"
            ].max()
        )

        start_gap = (
            dataset_first
            > universe_first
            + pd.Timedelta(
                days=2
            )
        )

        end_gap = (
            dataset_last
            < universe_last
            - pd.Timedelta(
                days=2
            )
        )

        if start_gap:
            coverage_start_gap_symbols.append(
                str(symbol)
            )

        if end_gap:
            coverage_end_gap_symbols.append(
                str(symbol)
            )

        symbol_records[
            str(symbol)
        ] = {
            "row_count": int(
                len(
                    ordered
                )
            ),
            "first_bar_open_time": (
                dataset_first.isoformat()
            ),
            "last_bar_close_time": (
                dataset_last.isoformat()
            ),
            "universe_first_timestamp": (
                universe_first.isoformat()
            ),
            "universe_last_timestamp": (
                universe_last.isoformat()
            ),
            "missing_internal_bar_count": (
                len(
                    missing_internal
                )
            ),
            "coverage_start_gap": (
                start_gap
            ),
            "coverage_end_gap": (
                end_gap
            ),
            "source_symbols": sorted(
                ordered[
                    "source_symbol"
                ].astype(
                    str
                ).unique().tolist()
            ),
        }

    invalid_transition_count = sum(
        not bool(
            transition[
                "valid"
            ]
        )
        for transition in alias_transitions
    )

    checks = {
        "duplicate_symbol_timestamp_count": (
            duplicate_count
        ),
        "invalid_price_count": int(
            invalid_price_mask.sum()
        ),
        "invalid_ohlc_count": int(
            invalid_ohlc_mask.sum()
        ),
        "invalid_volume_count": int(
            invalid_volume_mask.sum()
        ),
        "misaligned_utc_bar_count": int(
            misaligned_mask.sum()
        ),
        "invalid_duration_count": (
            duration_error_count
        ),
        "post_2024_bar_count": int(
            frame[
                "bar_open_time"
            ].ge(
                RESEARCH_END_EXCLUSIVE
            ).sum()
        ),
        "missing_internal_bar_count": int(
            missing_internal_count
        ),
        "missing_symbols": missing_symbols,
        "coverage_start_gap_symbols": sorted(
            coverage_start_gap_symbols
        ),
        "coverage_end_gap_symbols": sorted(
            coverage_end_gap_symbols
        ),
        "invalid_alias_transition_count": int(
            invalid_transition_count
        ),
        "alias_transitions": alias_transitions,
        "symbols": symbol_records,
    }

    checks["passed"] = (
        duplicate_count == 0
        and checks[
            "invalid_price_count"
        ] == 0
        and checks[
            "invalid_ohlc_count"
        ] == 0
        and checks[
            "invalid_volume_count"
        ] == 0
        and checks[
            "misaligned_utc_bar_count"
        ] == 0
        and duration_error_count == 0
        and checks[
            "post_2024_bar_count"
        ] == 0
        and missing_internal_count == 0
        and not missing_symbols
        and not coverage_start_gap_symbols
        and not coverage_end_gap_symbols
        and invalid_transition_count == 0
    )

    return checks


def resample_complete(
    frame: pd.DataFrame,
    *,
    rule: str,
    expected_four_hour_bars: int,
) -> tuple[pd.DataFrame, int]:
    outputs: list[pd.DataFrame] = []
    incomplete_group_count = 0

    for symbol, group in frame.groupby(
        "symbol",
        sort=True,
    ):
        ordered = group.sort_values(
            "bar_open_time"
        ).set_index(
            "bar_open_time"
        )

        grouped = ordered.resample(
            rule,
            origin="start_day",
            closed="left",
            label="right",
        )

        counts = grouped[
            "close"
        ].count()

        incomplete_group_count += int(
            counts.ne(
                expected_four_hour_bars
            ).sum()
        )

        aggregated = grouped.agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )

        aggregated = aggregated.loc[
            counts.eq(
                expected_four_hour_bars
            )
        ].dropna(
            subset=[
                "open",
                "high",
                "low",
                "close",
            ]
        )

        if aggregated.empty:
            continue

        aggregated.index.name = (
            "bar_close_time"
        )

        aggregated = aggregated.reset_index()

        duration = pd.Timedelta(
            rule
        )

        aggregated[
            "bar_open_time"
        ] = (
            aggregated[
                "bar_close_time"
            ]
            - duration
        )

        aggregated["symbol"] = str(
            symbol
        )

        aggregated[
            "source_exchange"
        ] = "kucoin"

        outputs.append(
            aggregated.loc[
                :,
                [
                    "symbol",
                    "source_exchange",
                    "bar_open_time",
                    "bar_close_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ],
            ]
        )

    if not outputs:
        raise DatasetBuildError(
            f"No complete {rule} bars were generated."
        )

    return (
        pd.concat(
            outputs,
            ignore_index=True,
        ).sort_values(
            [
                "symbol",
                "bar_open_time",
            ],
            kind="mergesort",
        ).reset_index(
            drop=True
        ),
        incomplete_group_count,
    )


def save_dataset(
    frame: pd.DataFrame,
    path: Path,
) -> dict[str, Any]:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    frame.to_parquet(
        path,
        index=False,
        compression="zstd",
    )

    return {
        "path": str(
            path.relative_to(
                ROOT
            )
        ).replace(
            "\\",
            "/",
        ),
        "bytes": path.stat().st_size,
        "file_sha256": file_sha256(
            path
        ),
        "content_sha256": (
            canonical_frame_sha256(
                frame
            )
        ),
        "row_count": int(
            len(
                frame
            )
        ),
        "symbol_count": int(
            frame[
                "symbol"
            ].nunique()
        ),
        "first_bar_open_time": (
            pd.Timestamp(
                frame[
                    "bar_open_time"
                ].min()
            ).isoformat()
        ),
        "last_bar_close_time": (
            pd.Timestamp(
                frame[
                    "bar_close_time"
                ].max()
            ).isoformat()
        ),
    }


def update_ledgers(
    *,
    source_commit: str,
    registration_sha256: str,
    manifest_sha256: str,
    datasets: dict[str, Any],
    validation: dict[str, Any],
) -> None:
    readiness = load_json(
        READINESS_PATH
    )

    readiness.update(
        {
            "status": (
                "READY_FOR_AMS_V3_TRIALS"
            ),
            "four_hour_dataset_registered": (
                True
            ),
            "dataset_exchange": "kucoin",
            "dataset_registration_path": (
                "reports/research/"
                "ams-v3-4h-dataset-registration-v1.json"
            ),
            "dataset_registration_sha256": (
                registration_sha256
            ),
            "dataset_manifest_path": (
                "reports/research/"
                "ams-v3-4h-dataset-manifest-v1.json"
            ),
            "dataset_manifest_sha256": (
                manifest_sha256
            ),
            "datasets": datasets,
            "validation": validation,
            "registered_trials_consumed": 0,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "next_action": (
                "BUILD_AMS_V3_F01_"
                "WALK_FORWARD_HARNESS"
            ),
        }
    )

    write_json(
        READINESS_PATH,
        readiness,
    )

    experiment = load_json(
        EXPERIMENT_PATH
    )

    accounting = experiment.get(
        "trial_accounting"
    )

    expected_accounting = {
        "total_authorized_trials": 20,
        "trials_executed": 0,
        "remaining_authorized_trials": 20,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    if accounting != expected_accounting:
        raise DatasetBuildError(
            "Trial accounting changed before "
            "dataset registration."
        )

    experiment[
        "data_registration"
    ] = {
        "status": "REGISTERED",
        "exchange": "kucoin",
        "source_commit": source_commit,
        "registration_path": (
            "reports/research/"
            "ams-v3-4h-dataset-registration-v1.json"
        ),
        "registration_sha256": (
            registration_sha256
        ),
        "manifest_path": (
            "reports/research/"
            "ams-v3-4h-dataset-manifest-v1.json"
        ),
        "manifest_sha256": (
            manifest_sha256
        ),
        "datasets": datasets,
        "registered_trials_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    write_json(
        EXPERIMENT_PATH,
        experiment,
    )

    project = load_json(
        PROJECT_PATH
    )

    updates = project.setdefault(
        "protocol_updates",
        [],
    )

    if not isinstance(
        updates,
        list,
    ):
        raise DatasetBuildError(
            "protocol_updates must be a list."
        )

    event_id = (
        "AMS_V3_KUCOIN_4H_DATASET_V1_REGISTERED"
    )

    if any(
        isinstance(
            item,
            dict,
        )
        and item.get(
            "event_id"
        )
        == event_id
        for item in updates
    ):
        raise DatasetBuildError(
            "Dataset registration event already exists."
        )

    updates.append(
        {
            "event_id": event_id,
            "event_type": (
                "RESEARCH_DATASET_REGISTERED"
            ),
            "recorded_at": utc_now(),
            "source_commit": source_commit,
            "exchange": "kucoin",
            "registration_sha256": (
                registration_sha256
            ),
            "manifest_sha256": (
                manifest_sha256
            ),
            "registered_trials_consumed": 0,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )

    project["current_stage"] = (
        "AMS_V3_KUCOIN_4H_DATASET_V1_REGISTERED"
    )

    project["next_action"] = (
        "BUILD_AMS_V3_F01_WALK_FORWARD_HARNESS"
    )

    project["last_updated_at"] = utc_now()

    write_json(
        PROJECT_PATH,
        project,
    )


def build_dataset(
    *,
    raw_root: Path,
    source_commit: str,
) -> dict[str, Any]:
    symbols, universe_coverage = (
        load_research_universe()
    )

    sync_records: list[
        dict[str, Any]
    ] = []

    available_frames: list[
        pd.DataFrame
    ] = []

    missing_symbols: list[str] = []
    alias_transitions: list[
        dict[str, Any]
    ] = []

    for position, base_symbol in enumerate(
        symbols,
        start=1,
    ):
        print(
            f"sync_symbol={position}/{len(symbols)}:"
            f"{base_symbol}",
            flush=True,
        )

        symbol_frames: list[
            pd.DataFrame
        ] = []

        for unified_symbol in candidate_symbols(
            base_symbol
        ):
            sync_record = run_sync(
                unified_symbol=unified_symbol,
                raw_root=raw_root,
            )

            sync_record["base_symbol"] = (
                base_symbol
            )

            sync_records.append(
                sync_record
            )

            if (
                sync_record[
                    "returncode"
                ]
                != 0
                or not sync_record[
                    "dataset_exists"
                ]
            ):
                continue

            try:
                source_frame = (
                    read_source_dataset(
                        raw_root=raw_root,
                        base_symbol=base_symbol,
                        unified_symbol=(
                            unified_symbol
                        ),
                    )
                )

            except BaseException as error:
                sync_record[
                    "read_error"
                ] = {
                    "type": (
                        type(
                            error
                        ).__name__
                    ),
                    "message": str(
                        error
                    ),
                }

                continue

            if not source_frame.empty:
                symbol_frames.append(
                    source_frame
                )

        if not symbol_frames:
            missing_symbols.append(
                base_symbol
            )

            continue

        merged, transitions = (
            merge_alias_frames(
                base_symbol=base_symbol,
                frames=symbol_frames,
            )
        )

        alias_transitions.extend(
            transitions
        )

        available_frames.append(
            merged
        )

    if not available_frames:
        raise DatasetBuildError(
            "No KuCoin 4H datasets were available."
        )

    four_hour = pd.concat(
        available_frames,
        ignore_index=True,
    ).sort_values(
        [
            "symbol",
            "bar_open_time",
        ],
        kind="mergesort",
    ).reset_index(
        drop=True
    )

    validation = validate_four_hour_dataset(
        four_hour,
        expected_symbols=symbols,
        universe_coverage=universe_coverage,
        alias_transitions=alias_transitions,
    )

    validation[
        "sync_missing_symbols"
    ] = sorted(
        missing_symbols
    )

    eight_hour, incomplete_8h = (
        resample_complete(
            four_hour,
            rule="8h",
            expected_four_hour_bars=2,
        )
    )

    daily, incomplete_1d = (
        resample_complete(
            four_hour,
            rule="1D",
            expected_four_hour_bars=6,
        )
    )

    repeated_8h, _ = resample_complete(
        four_hour,
        rule="8h",
        expected_four_hour_bars=2,
    )

    repeated_1d, _ = resample_complete(
        four_hour,
        rule="1D",
        expected_four_hour_bars=6,
    )

    validation[
        "incomplete_8h_group_count"
    ] = incomplete_8h

    validation[
        "incomplete_1d_group_count"
    ] = incomplete_1d

    validation[
        "deterministic_8h_resampling"
    ] = (
        canonical_frame_sha256(
            eight_hour
        )
        == canonical_frame_sha256(
            repeated_8h
        )
    )

    validation[
        "deterministic_1d_resampling"
    ] = (
        canonical_frame_sha256(
            daily
        )
        == canonical_frame_sha256(
            repeated_1d
        )
    )

    validation["passed"] = bool(
        validation[
            "passed"
        ]
        and not missing_symbols
        and validation[
            "deterministic_8h_resampling"
        ]
        and validation[
            "deterministic_1d_resampling"
        ]
    )

    datasets = {
        "four_hour": save_dataset(
            four_hour,
            FOUR_HOUR_PATH,
        ),
        "eight_hour": save_dataset(
            eight_hour,
            EIGHT_HOUR_PATH,
        ),
        "daily": save_dataset(
            daily,
            DAILY_PATH,
        ),
    }

    status = (
        "PASS"
        if validation[
            "passed"
        ]
        else "BLOCKED"
    )

    next_action = (
        "BUILD_AMS_V3_F01_WALK_FORWARD_HARNESS"
        if status == "PASS"
        else (
            "REPAIR_AMS_V3_KUCOIN_4H_COVERAGE"
        )
    )

    manifest = {
        "schema_version": (
            "ams-v3-kucoin-4h-dataset-manifest-v1"
        ),
        "status": status,
        "generated_at": utc_now(),
        "source_commit": source_commit,
        "exchange": "kucoin",
        "market_type": "spot",
        "quote_asset": "USDT",
        "source_timeframe": "4h",
        "source_timestamp_semantics": (
            "BAR_CLOSE_TIME"
        ),
        "research_start": (
            RESEARCH_START.isoformat()
        ),
        "research_end_exclusive": (
            RESEARCH_END_EXCLUSIVE.isoformat()
        ),
        "expected_symbols": list(
            symbols
        ),
        "universe_coverage": (
            universe_coverage
        ),
        "sync_records": sync_records,
        "validation": validation,
        "datasets": datasets,
        "registered_trials_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    write_json(
        MANIFEST_PATH,
        manifest,
    )

    manifest_sha256 = file_sha256(
        MANIFEST_PATH
    )

    registration = {
        "schema_version": (
            "ams-v3-4h-dataset-registration-v1"
        ),
        "status": status,
        "registered_at": utc_now(),
        "source_commit": source_commit,
        "exchange": "kucoin",
        "market_type": "spot",
        "quote_asset": "USDT",
        "source_timeframe": "4h",
        "derived_timeframes": [
            "8h",
            "1d",
        ],
        "expected_symbol_count": len(
            symbols
        ),
        "registered_symbol_count": int(
            four_hour[
                "symbol"
            ].nunique()
        ),
        "validation": validation,
        "datasets": datasets,
        "manifest_path": (
            "reports/research/"
            "ams-v3-4h-dataset-manifest-v1.json"
        ),
        "manifest_sha256": (
            manifest_sha256
        ),
        "registered_trials_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_action": next_action,
    }

    write_json(
        REGISTRATION_PATH,
        registration,
    )

    registration_sha256 = file_sha256(
        REGISTRATION_PATH
    )

    if status == "PASS":
        update_ledgers(
            source_commit=source_commit,
            registration_sha256=(
                registration_sha256
            ),
            manifest_sha256=(
                manifest_sha256
            ),
            datasets=datasets,
            validation=validation,
        )

    summary = {
        "status": status,
        "source_commit": source_commit,
        "exchange": "kucoin",
        "expected_symbol_count": len(
            symbols
        ),
        "registered_symbol_count": int(
            four_hour[
                "symbol"
            ].nunique()
        ),
        "missing_symbols": validation[
            "missing_symbols"
        ],
        "coverage_start_gap_symbols": (
            validation[
                "coverage_start_gap_symbols"
            ]
        ),
        "coverage_end_gap_symbols": (
            validation[
                "coverage_end_gap_symbols"
            ]
        ),
        "missing_internal_bar_count": (
            validation[
                "missing_internal_bar_count"
            ]
        ),
        "invalid_alias_transition_count": (
            validation[
                "invalid_alias_transition_count"
            ]
        ),
        "four_hour_rows": datasets[
            "four_hour"
        ][
            "row_count"
        ],
        "eight_hour_rows": datasets[
            "eight_hour"
        ][
            "row_count"
        ],
        "daily_rows": datasets[
            "daily"
        ][
            "row_count"
        ],
        "registration_sha256": (
            registration_sha256
        ),
        "manifest_sha256": (
            manifest_sha256
        ),
        "trials_executed": 0,
        "remaining_authorized_trials": 20,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_action": next_action,
    }

    write_json(
        SUMMARY_PATH,
        summary,
    )

    print(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )

    return summary


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--raw-root",
        type=Path,
        default=DEFAULT_RAW_ROOT,
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    source_commit = os.environ.get(
        "SIRAJ_DATASET_SOURCE_COMMIT",
        "",
    ).strip()

    if not source_commit:
        raise DatasetBuildError(
            "SIRAJ_DATASET_SOURCE_COMMIT is required."
        )

    result = build_dataset(
        raw_root=arguments.raw_root.resolve(),
        source_commit=source_commit,
    )

    return (
        0
        if result[
            "status"
        ]
        == "PASS"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
