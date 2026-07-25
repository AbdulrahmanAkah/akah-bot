from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from spotbot.research.ams_v2_regime_features import (
    REGIME_FEATURE_COLUMNS,
    AmsV2RegimeFeatureConfigurationError,
    AmsV2RegimeFeatureDataError,
    AmsV2RegimeFeaturePolicy,
    build_ams_v2_regime_feature_frame,
    validate_ams_v2_regime_feature_frame,
)


def policy() -> AmsV2RegimeFeaturePolicy:
    return AmsV2RegimeFeaturePolicy(
        research_start=datetime(
            2021,
            11,
            1,
            tzinfo=UTC,
        ),
        research_end_exclusive=datetime(
            2022,
            2,
            1,
            tzinfo=UTC,
        ),
        volatility_percentile_lookback_days=60,
    )


def sample_frames() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    timestamps = pd.date_range(
        "2020-01-01",
        "2022-01-31",
        freq="1D",
        tz="UTC",
    )

    symbols = (
        "BTC/USDT",
        "ALT1/USDT",
        "ALT2/USDT",
        "ALT3/USDT",
    )

    history_rows: list[
        dict[str, object]
    ] = []

    for symbol_index, symbol in enumerate(
        symbols
    ):
        time_index = np.arange(
            len(timestamps),
            dtype=float,
        )

        trend = (
            100.0
            + (
                0.08
                + 0.02 * symbol_index
            )
            * time_index
        )

        cycle = (
            2.0
            * np.sin(
                time_index
                / (
                    11.0
                    + symbol_index
                )
            )
        )

        close = (
            trend
            + cycle
            + 8.0 * symbol_index
        )

        for timestamp, value in zip(
            timestamps,
            close,
            strict=True,
        ):
            history_rows.append(
                {
                    "symbol": symbol,
                    "close_time": timestamp,
                    "close": float(value),
                }
            )

    universe_times = pd.date_range(
        "2021-01-01",
        "2022-01-31",
        freq="1D",
        tz="UTC",
    )

    universe_rows: list[
        dict[str, object]
    ] = []

    for timestamp in universe_times:
        for symbol in symbols:
            universe_rows.append(
                {
                    "snapshot_time": timestamp,
                    "symbol": symbol,
                    "eligible": True,
                }
            )

    return (
        pd.DataFrame(
            history_rows
        ),
        pd.DataFrame(
            universe_rows
        ),
    )


def test_feature_frame_has_registered_features() -> None:
    history, universe = sample_frames()

    frame = build_ams_v2_regime_feature_frame(
        history,
        universe,
        policy=policy(),
    )

    assert set(
        REGIME_FEATURE_COLUMNS
    ).issubset(
        frame.columns
    )

    assert not frame.empty
    assert bool(
        frame["complete_features"].any()
    )

    assert bool(
        (
            frame["lagged_periods"]
            == 1
        ).all()
    )


def test_current_snapshot_close_cannot_change_features() -> None:
    history, universe = sample_frames()

    original = build_ams_v2_regime_feature_frame(
        history,
        universe,
        policy=policy(),
    )

    target_time = pd.Timestamp(
        "2021-12-15",
        tz="UTC",
    )

    mask = (
        (
            history["symbol"]
            == "BTC/USDT"
        )
        & (
            history["close_time"]
            == target_time
        )
    )

    assert int(mask.sum()) == 1

    changed_history = history.copy()

    changed_history.loc[
        mask,
        "close",
    ] = 1_000_000.0

    changed = build_ams_v2_regime_feature_frame(
        changed_history,
        universe,
        policy=policy(),
    )

    original_row = original.loc[
        original["snapshot_time"]
        == target_time,
        list(
            REGIME_FEATURE_COLUMNS
        ),
    ].reset_index(drop=True)

    changed_row = changed.loc[
        changed["snapshot_time"]
        == target_time,
        list(
            REGIME_FEATURE_COLUMNS
        ),
    ].reset_index(drop=True)

    pd.testing.assert_frame_equal(
        original_row,
        changed_row,
    )


def test_future_bars_cannot_change_earlier_features() -> None:
    history, universe = sample_frames()

    original = build_ams_v2_regime_feature_frame(
        history,
        universe,
        policy=policy(),
    )

    cutoff = pd.Timestamp(
        "2021-12-15",
        tz="UTC",
    )

    changed_history = history.copy()

    future_mask = (
        changed_history["close_time"]
        > cutoff
    )

    changed_history.loc[
        future_mask,
        "close",
    ] = (
        changed_history.loc[
            future_mask,
            "close",
        ]
        * 1000.0
    )

    changed = build_ams_v2_regime_feature_frame(
        changed_history,
        universe,
        policy=policy(),
    )

    original_earlier = original.loc[
        original["snapshot_time"]
        <= cutoff
    ].reset_index(drop=True)

    changed_earlier = changed.loc[
        changed["snapshot_time"]
        <= cutoff
    ].reset_index(drop=True)

    pd.testing.assert_frame_equal(
        original_earlier,
        changed_earlier,
    )


def test_universe_membership_is_lagged_one_day() -> None:
    history, universe = sample_frames()

    activation_time = pd.Timestamp(
        "2021-12-10",
        tz="UTC",
    )

    alt_mask = (
        universe["symbol"]
        == "ALT3/USDT"
    )

    universe.loc[
        alt_mask,
        "eligible",
    ] = False

    universe.loc[
        alt_mask
        & (
            universe["snapshot_time"]
            >= activation_time
        ),
        "eligible",
    ] = True

    frame = build_ams_v2_regime_feature_frame(
        history,
        universe,
        policy=policy(),
    )

    activation_count = int(
        frame.loc[
            frame["snapshot_time"]
            == activation_time,
            "eligible_asset_count",
        ].iloc[0]
    )

    next_day_count = int(
        frame.loc[
            frame["snapshot_time"]
            == (
                activation_time
                + pd.Timedelta(days=1)
            ),
            "eligible_asset_count",
        ].iloc[0]
    )

    assert activation_count == 3
    assert next_day_count == 4


def test_correlation_and_percentages_are_bounded() -> None:
    history, universe = sample_frames()

    frame = build_ams_v2_regime_feature_frame(
        history,
        universe,
        policy=policy(),
    )

    complete = frame.loc[
        frame["complete_features"]
    ]

    assert bool(
        complete[
            "average_pairwise_correlation_30d"
        ].between(
            -1.0,
            1.0,
        ).all()
    )

    assert bool(
        complete[
            "eligible_asset_breadth_above_ema_50"
        ].between(
            0.0,
            1.0,
        ).all()
    )

    assert bool(
        complete[
            "realized_volatility_percentile_20d"
        ].between(
            0.0,
            1.0,
        ).all()
    )


def test_locked_2025_history_is_rejected() -> None:
    history, universe = sample_frames()

    future = history.tail(1).copy()

    future["symbol"] = "BTC/USDT"
    future["close_time"] = pd.Timestamp(
        "2025-01-01",
        tz="UTC",
    )

    with pytest.raises(
        AmsV2RegimeFeatureDataError,
        match="locked 2025",
    ):
        build_ams_v2_regime_feature_frame(
            pd.concat(
                [
                    history,
                    future,
                ],
                ignore_index=True,
            ),
            universe,
            policy=policy(),
        )


def test_missing_benchmark_is_rejected() -> None:
    history, universe = sample_frames()

    history = history.loc[
        history["symbol"]
        != "BTC/USDT"
    ]

    with pytest.raises(
        AmsV2RegimeFeatureDataError,
        match="Benchmark symbol",
    ):
        build_ams_v2_regime_feature_frame(
            history,
            universe,
            policy=policy(),
        )


def test_duplicate_history_row_is_rejected() -> None:
    history, universe = sample_frames()

    duplicate = pd.concat(
        [
            history,
            history.iloc[
                [
                    0
                ]
            ],
        ],
        ignore_index=True,
    )

    with pytest.raises(
        AmsV2RegimeFeatureDataError,
        match="Duplicate history",
    ):
        build_ams_v2_regime_feature_frame(
            duplicate,
            universe,
            policy=policy(),
        )


def test_naive_research_timestamp_is_rejected() -> None:
    with pytest.raises(
        AmsV2RegimeFeatureConfigurationError,
        match="timezone-aware",
    ):
        AmsV2RegimeFeaturePolicy(
            research_start=datetime(
                2021,
                1,
                1,
            ),
            research_end_exclusive=datetime(
                2022,
                1,
                1,
                tzinfo=UTC,
            ),
        )


def test_validation_rejects_unlagged_cutoff() -> None:
    history, universe = sample_frames()

    frame = build_ams_v2_regime_feature_frame(
        history,
        universe,
        policy=policy(),
    )

    frame.loc[
        frame.index[0],
        "feature_information_cutoff",
    ] = frame.loc[
        frame.index[0],
        "snapshot_time",
    ]

    with pytest.raises(
        AmsV2RegimeFeatureDataError,
        match="cutoff",
    ):
        validate_ams_v2_regime_feature_frame(
            frame,
            policy=policy(),
        )