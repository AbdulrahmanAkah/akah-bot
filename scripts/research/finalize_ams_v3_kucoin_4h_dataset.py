from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path.cwd()

BASE_BUILDER_PATH = (
    ROOT
    / "scripts/research/"
    "build_ams_v3_kucoin_4h_dataset.py"
)

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

AVAILABILITY_PATH = (
    OUTPUT_ROOT
    / "ams-v3-kucoin-spot-usdt-availability.parquet"
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

SUMMARY_PATH = Path(
    r"C:\SIRAJ\Reports\ams-v3-kucoin-4h-final-summary.json"
)

MINIMUM_ELIGIBLE_SYMBOLS = 12
MINIMUM_COVERAGE_RATIO = 0.50


class FinalizationError(RuntimeError):
    """Raised when the venue-specific dataset cannot be finalized."""


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
        raise FinalizationError(
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


base = load_module(
    BASE_BUILDER_PATH,
    "_ams_v3_kucoin_base_builder",
)


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


def source_path(
    raw_root: Path,
    unified_symbol: str,
) -> Path:
    return base.source_dataset_path(
        raw_root,
        unified_symbol,
    )


def create_kucoin_exchange() -> Any:
    ccxt = importlib.import_module(
        "ccxt"
    )

    exchange_class = ccxt.kucoin

    exchange = exchange_class(
        {
            "enableRateLimit": True,
            "timeout": 60000,
        }
    )

    exchange.load_markets()

    return exchange


def discover_first_candle(
    exchange: Any,
    *,
    unified_symbol: str,
) -> dict[str, Any]:
    markets = exchange.markets

    if unified_symbol not in markets:
        return {
            "status": "MARKET_NOT_AVAILABLE",
            "symbol": unified_symbol,
            "first_open_time": None,
            "error": None,
        }

    market = markets[
        unified_symbol
    ]

    if not bool(
        market.get(
            "spot",
            False,
        )
    ):
        return {
            "status": "NOT_SPOT",
            "symbol": unified_symbol,
            "first_open_time": None,
            "error": None,
        }

    probe_times = [
        RESEARCH_START,
    ]

    probe_times.extend(
        pd.date_range(
            start=(
                RESEARCH_START
                + pd.Timedelta(
                    days=90
                )
            ),
            end=(
                RESEARCH_END_EXCLUSIVE
                - pd.Timedelta(
                    hours=4
                )
            ),
            freq="90D",
            tz="UTC",
        ).tolist()
    )

    observed_errors: list[str] = []

    for probe_time in probe_times:
        try:
            candles = exchange.fetch_ohlcv(
                unified_symbol,
                timeframe="4h",
                since=int(
                    pd.Timestamp(
                        probe_time
                    ).timestamp()
                    * 1000
                ),
                limit=1,
            )

        except BaseException as error:
            observed_errors.append(
                f"{type(error).__name__}:"
                f"{error}"
            )

            continue

        if not candles:
            continue

        first_open = pd.to_datetime(
            int(
                candles[0][0]
            ),
            unit="ms",
            utc=True,
        )

        if (
            first_open
            >= RESEARCH_END_EXCLUSIVE
        ):
            return {
                "status": (
                    "LISTED_AFTER_RESEARCH_WINDOW"
                ),
                "symbol": unified_symbol,
                "first_open_time": (
                    first_open.isoformat()
                ),
                "error": None,
            }

        return {
            "status": "FOUND",
            "symbol": unified_symbol,
            "first_open_time": (
                first_open.isoformat()
            ),
            "error": None,
        }

    return {
        "status": "NO_RESEARCH_WINDOW_CANDLES",
        "symbol": unified_symbol,
        "first_open_time": None,
        "error": (
            " | ".join(
                observed_errors[-5:]
            )
            if observed_errors
            else None
        ),
    }


def run_adaptive_sync(
    *,
    raw_root: Path,
    unified_symbol: str,
    first_open_time: str,
) -> dict[str, Any]:
    environment = os.environ.copy()

    source_root = str(
        ROOT
        / "src"
    )

    existing_python_path = (
        environment.get(
            "PYTHONPATH",
            "",
        )
    )

    environment["PYTHONPATH"] = (
        source_root
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
        first_open_time,
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

    path = source_path(
        raw_root,
        unified_symbol,
    )

    return {
        "symbol": unified_symbol,
        "first_open_time": first_open_time,
        "command": command,
        "returncode": completed.returncode,
        "dataset_path": str(
            path
        ),
        "dataset_exists": path.is_file(),
        "stdout_tail": (
            completed.stdout[-3000:]
        ),
        "stderr_tail": (
            completed.stderr[-3000:]
        ),
    }


def validate_venue_dataset(
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
    minimum_eligible_symbols: int = (
        MINIMUM_ELIGIBLE_SYMBOLS
    ),
    minimum_coverage_ratio: float = (
        MINIMUM_COVERAGE_RATIO
    ),
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

    venue_unavailable_symbols = sorted(
        set(
            expected_symbols
        ).difference(
            available_symbols
        )
    )

    missing_internal_count = 0
    symbol_records: dict[
        str,
        dict[str, Any],
    ] = {}

    listing_delay_symbols: list[str] = []
    early_delisting_symbols: list[str] = []

    for symbol, group in frame.groupby(
        "symbol",
        sort=True,
    ):
        symbol_name = str(
            symbol
        )

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

        missing_internal_count += int(
            len(
                missing_internal
            )
        )

        universe_record = (
            universe_coverage[
                symbol_name
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

        required_start = max(
            RESEARCH_START,
            universe_first,
        )

        required_end = min(
            RESEARCH_END_EXCLUSIVE,
            universe_last
            + pd.Timedelta(
                days=1
            ),
        )

        venue_first = pd.Timestamp(
            ordered[
                "bar_open_time"
            ].min()
        )

        venue_last = pd.Timestamp(
            ordered[
                "bar_close_time"
            ].max()
        )

        listing_delay_hours = max(
            0.0,
            (
                venue_first
                - required_start
            ).total_seconds()
            / 3600.0,
        )

        delisting_advance_hours = max(
            0.0,
            (
                required_end
                - venue_last
            ).total_seconds()
            / 3600.0,
        )

        if listing_delay_hours > 48.0:
            listing_delay_symbols.append(
                symbol_name
            )

        if delisting_advance_hours > 48.0:
            early_delisting_symbols.append(
                symbol_name
            )

        symbol_records[
            symbol_name
        ] = {
            "row_count": int(
                len(
                    ordered
                )
            ),
            "universe_first_timestamp": (
                universe_first.isoformat()
            ),
            "universe_last_timestamp": (
                universe_last.isoformat()
            ),
            "research_effective_start": (
                required_start.isoformat()
            ),
            "research_effective_end_exclusive": (
                required_end.isoformat()
            ),
            "venue_tradable_from": (
                venue_first.isoformat()
            ),
            "venue_tradable_until": (
                venue_last.isoformat()
            ),
            "venue_listing_delay_hours": (
                listing_delay_hours
            ),
            "venue_delisting_advance_hours": (
                delisting_advance_hours
            ),
            "missing_internal_bar_count": (
                int(
                    len(
                        missing_internal
                    )
                )
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
            item.get(
                "valid",
                False,
            )
        )
        for item in alias_transitions
    )

    eligible_symbol_count = len(
        available_symbols
    )

    coverage_ratio = (
        eligible_symbol_count
        / len(
            expected_symbols
        )
        if expected_symbols
        else 0.0
    )

    benchmark_available = (
        "BTC"
        in available_symbols
    )

    result = {
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
        "pre_research_bar_count": int(
            frame[
                "bar_open_time"
            ].lt(
                RESEARCH_START
            ).sum()
        ),
        "post_2024_bar_count": int(
            frame[
                "bar_open_time"
            ].ge(
                RESEARCH_END_EXCLUSIVE
            ).sum()
        ),
        "missing_internal_bar_count": (
            missing_internal_count
        ),
        "invalid_alias_transition_count": (
            invalid_transition_count
        ),
        "expected_symbol_count": len(
            expected_symbols
        ),
        "eligible_symbol_count": (
            eligible_symbol_count
        ),
        "coverage_ratio": coverage_ratio,
        "minimum_eligible_symbol_count": (
            minimum_eligible_symbols
        ),
        "minimum_coverage_ratio": (
            minimum_coverage_ratio
        ),
        "benchmark_available": (
            benchmark_available
        ),
        "venue_unavailable_symbols": (
            venue_unavailable_symbols
        ),
        "venue_listing_delay_symbols": sorted(
            listing_delay_symbols
        ),
        "venue_early_delisting_symbols": sorted(
            early_delisting_symbols
        ),
        "alias_transitions": (
            alias_transitions
        ),
        "symbols": symbol_records,
    }

    result["passed"] = all(
        (
            duplicate_count == 0,
            result[
                "invalid_price_count"
            ] == 0,
            result[
                "invalid_ohlc_count"
            ] == 0,
            result[
                "invalid_volume_count"
            ] == 0,
            result[
                "misaligned_utc_bar_count"
            ] == 0,
            duration_error_count == 0,
            result[
                "pre_research_bar_count"
            ] == 0,
            result[
                "post_2024_bar_count"
            ] == 0,
            missing_internal_count == 0,
            invalid_transition_count == 0,
            benchmark_available,
            (
                eligible_symbol_count
                >= minimum_eligible_symbols
            ),
            (
                coverage_ratio
                >= minimum_coverage_ratio
            ),
        )
    )

    return result


def build_availability_frame(
    validation: dict[str, Any],
) -> pd.DataFrame:
    symbol_records = validation[
        "symbols"
    ]

    rows: list[
        dict[str, Any]
    ] = []

    for symbol, record in sorted(
        symbol_records.items()
    ):
        rows.append(
            {
                "symbol": symbol,
                "exchange": "kucoin",
                "tradable_from": (
                    record[
                        "venue_tradable_from"
                    ]
                ),
                "tradable_until": (
                    record[
                        "venue_tradable_until"
                    ]
                ),
                "listing_delay_hours": (
                    record[
                        "venue_listing_delay_hours"
                    ]
                ),
                "delisting_advance_hours": (
                    record[
                        "venue_delisting_advance_hours"
                    ]
                ),
                "source_symbols": ",".join(
                    record[
                        "source_symbols"
                    ]
                ),
            }
        )

    availability = pd.DataFrame(
        rows
    )

    availability[
        "tradable_from"
    ] = pd.to_datetime(
        availability[
            "tradable_from"
        ],
        utc=True,
    )

    availability[
        "tradable_until"
    ] = pd.to_datetime(
        availability[
            "tradable_until"
        ],
        utc=True,
    )

    return availability


def save_availability(
    frame: pd.DataFrame,
) -> dict[str, Any]:
    AVAILABILITY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    frame.to_parquet(
        AVAILABILITY_PATH,
        index=False,
        compression="zstd",
    )

    return {
        "path": str(
            AVAILABILITY_PATH.relative_to(
                ROOT
            )
        ).replace(
            "\\",
            "/",
        ),
        "bytes": (
            AVAILABILITY_PATH.stat().st_size
        ),
        "file_sha256": base.file_sha256(
            AVAILABILITY_PATH
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
    }


def build_dataset(
    *,
    raw_root: Path,
    source_commit: str,
) -> dict[str, Any]:
    symbols, universe_coverage = (
        base.load_research_universe()
    )

    exchange = create_kucoin_exchange()

    discovery_records: list[
        dict[str, Any]
    ] = []

    sync_records: list[
        dict[str, Any]
    ] = []

    frames: list[
        pd.DataFrame
    ] = []

    alias_transitions: list[
        dict[str, Any]
    ] = []

    for position, base_symbol in enumerate(
        symbols,
        start=1,
    ):
        print(
            f"venue_symbol={position}/"
            f"{len(symbols)}:{base_symbol}",
            flush=True,
        )

        symbol_frames: list[
            pd.DataFrame
        ] = []

        for unified_symbol in (
            base.candidate_symbols(
                base_symbol
            )
        ):
            path = source_path(
                raw_root,
                unified_symbol,
            )

            if not path.is_file():
                discovery = discover_first_candle(
                    exchange,
                    unified_symbol=(
                        unified_symbol
                    ),
                )

                discovery[
                    "base_symbol"
                ] = base_symbol

                discovery_records.append(
                    discovery
                )

                if (
                    discovery[
                        "status"
                    ]
                    != "FOUND"
                ):
                    continue

                first_open_time = str(
                    discovery[
                        "first_open_time"
                    ]
                )

                sync = run_adaptive_sync(
                    raw_root=raw_root,
                    unified_symbol=(
                        unified_symbol
                    ),
                    first_open_time=(
                        first_open_time
                    ),
                )

                sync[
                    "base_symbol"
                ] = base_symbol

                sync_records.append(
                    sync
                )

                if (
                    sync[
                        "returncode"
                    ]
                    != 0
                    or not sync[
                        "dataset_exists"
                    ]
                ):
                    continue

            try:
                source_frame = (
                    base.read_source_dataset(
                        raw_root=raw_root,
                        base_symbol=base_symbol,
                        unified_symbol=(
                            unified_symbol
                        ),
                    )
                )

            except BaseException as error:
                sync_records.append(
                    {
                        "base_symbol": (
                            base_symbol
                        ),
                        "symbol": (
                            unified_symbol
                        ),
                        "returncode": -1,
                        "dataset_path": str(
                            path
                        ),
                        "dataset_exists": (
                            path.is_file()
                        ),
                        "read_error": {
                            "type": (
                                type(
                                    error
                                ).__name__
                            ),
                            "message": str(
                                error
                            ),
                        },
                    }
                )

                continue

            if not source_frame.empty:
                symbol_frames.append(
                    source_frame
                )

        if not symbol_frames:
            continue

        merged, transitions = (
            base.merge_alias_frames(
                base_symbol=base_symbol,
                frames=symbol_frames,
            )
        )

        frames.append(
            merged
        )

        alias_transitions.extend(
            transitions
        )

    if not frames:
        raise FinalizationError(
            "No KuCoin research frames were available."
        )

    four_hour = pd.concat(
        frames,
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

    validation = validate_venue_dataset(
        four_hour,
        expected_symbols=symbols,
        universe_coverage=(
            universe_coverage
        ),
        alias_transitions=(
            alias_transitions
        ),
    )

    eight_hour, incomplete_8h = (
        base.resample_complete(
            four_hour,
            rule="8h",
            expected_four_hour_bars=2,
        )
    )

    daily, incomplete_1d = (
        base.resample_complete(
            four_hour,
            rule="1D",
            expected_four_hour_bars=6,
        )
    )

    repeated_8h, _ = (
        base.resample_complete(
            four_hour,
            rule="8h",
            expected_four_hour_bars=2,
        )
    )

    repeated_1d, _ = (
        base.resample_complete(
            four_hour,
            rule="1D",
            expected_four_hour_bars=6,
        )
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
        base.canonical_frame_sha256(
            eight_hour
        )
        == base.canonical_frame_sha256(
            repeated_8h
        )
    )

    validation[
        "deterministic_1d_resampling"
    ] = (
        base.canonical_frame_sha256(
            daily
        )
        == base.canonical_frame_sha256(
            repeated_1d
        )
    )

    validation["passed"] = bool(
        validation[
            "passed"
        ]
        and validation[
            "deterministic_8h_resampling"
        ]
        and validation[
            "deterministic_1d_resampling"
        ]
    )

    availability = (
        build_availability_frame(
            validation
        )
    )

    datasets = {
        "four_hour": base.save_dataset(
            four_hour,
            FOUR_HOUR_PATH,
        ),
        "eight_hour": base.save_dataset(
            eight_hour,
            EIGHT_HOUR_PATH,
        ),
        "daily": base.save_dataset(
            daily,
            DAILY_PATH,
        ),
        "availability": (
            save_availability(
                availability
            )
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
            "REPAIR_AMS_V3_KUCOIN_"
            "VENUE_DATA_INTEGRITY"
        )
    )

    manifest = {
        "schema_version": (
            "ams-v3-kucoin-venue-dataset-"
            "manifest-v2"
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
        "universe_policy": (
            "RESEARCH_UNIVERSE_INTERSECTED_"
            "WITH_POINT_IN_TIME_KUCOIN_"
            "SPOT_AVAILABILITY"
        ),
        "minimum_eligible_symbols": (
            MINIMUM_ELIGIBLE_SYMBOLS
        ),
        "minimum_coverage_ratio": (
            MINIMUM_COVERAGE_RATIO
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
        "discovery_records": (
            discovery_records
        ),
        "sync_records": sync_records,
        "validation": validation,
        "datasets": datasets,
        "registered_trials_consumed": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }

    base.write_json(
        MANIFEST_PATH,
        manifest,
    )

    manifest_sha256 = (
        base.file_sha256(
            MANIFEST_PATH
        )
    )

    registration = {
        "schema_version": (
            "ams-v3-4h-dataset-"
            "registration-v2"
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
        "universe_policy": (
            "POINT_IN_TIME_KUCOIN_"
            "SPOT_ELIGIBILITY"
        ),
        "expected_symbol_count": len(
            symbols
        ),
        "registered_symbol_count": int(
            four_hour[
                "symbol"
            ].nunique()
        ),
        "coverage_ratio": validation[
            "coverage_ratio"
        ],
        "venue_unavailable_symbols": (
            validation[
                "venue_unavailable_symbols"
            ]
        ),
        "venue_listing_delay_symbols": (
            validation[
                "venue_listing_delay_symbols"
            ]
        ),
        "venue_early_delisting_symbols": (
            validation[
                "venue_early_delisting_symbols"
            ]
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

    base.write_json(
        REGISTRATION_PATH,
        registration,
    )

    registration_sha256 = (
        base.file_sha256(
            REGISTRATION_PATH
        )
    )

    if status == "PASS":
        base.update_ledgers(
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
        "universe_policy": (
            "POINT_IN_TIME_KUCOIN_"
            "SPOT_ELIGIBILITY"
        ),
        "expected_symbol_count": len(
            symbols
        ),
        "registered_symbol_count": int(
            four_hour[
                "symbol"
            ].nunique()
        ),
        "coverage_ratio": validation[
            "coverage_ratio"
        ],
        "venue_unavailable_symbols": (
            validation[
                "venue_unavailable_symbols"
            ]
        ),
        "venue_listing_delay_symbols": (
            validation[
                "venue_listing_delay_symbols"
            ]
        ),
        "venue_early_delisting_symbols": (
            validation[
                "venue_early_delisting_symbols"
            ]
        ),
        "missing_internal_bar_count": (
            validation[
                "missing_internal_bar_count"
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
        "availability_rows": datasets[
            "availability"
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

    base.write_json(
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
        raise FinalizationError(
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
