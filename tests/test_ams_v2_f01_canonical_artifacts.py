from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.ams_v2_f01_canonical_artifacts import (
    F01_CANONICAL_ARTIFACT_VERSION,
    F01_CANONICAL_EXECUTION_STATUS,
    F01CanonicalTranslationError,
    assert_f01_canonical_not_trial_executable,
    build_f01_canonical_artifacts,
    canonicalize_f01_portfolio,
    canonicalize_f01_trade_records,
)
from spotbot.research.ams_v2_walk_forward_orchestrator import (
    default_ams_v2_fold_definitions,
)


def fold():
    return default_ams_v2_fold_definitions()[0]


def raw_trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [
                "ETH/USDT",
                "BTC/USDT",
            ],
            "entry_timestamp": [
                datetime(
                    2022,
                    4,
                    1,
                    tzinfo=UTC,
                ),
                datetime(
                    2022,
                    2,
                    1,
                    tzinfo=UTC,
                ),
            ],
            "exit_timestamp": [
                datetime(
                    2022,
                    4,
                    10,
                    tzinfo=UTC,
                ),
                datetime(
                    2022,
                    2,
                    10,
                    tzinfo=UTC,
                ),
            ],
            "gross_return": [
                -0.10,
                0.20,
            ],
            "net_return": [
                -0.12,
                0.18,
            ],
            "realized_r_multiple": [
                -1.0,
                2.0,
            ],
        }
    )


def raw_portfolio() -> pd.DataFrame:
    snapshots = [
        datetime(
            2022,
            1,
            1,
            tzinfo=UTC,
        ),
        datetime(
            2022,
            6,
            1,
            tzinfo=UTC,
        ),
        datetime(
            2022,
            12,
            31,
            tzinfo=UTC,
        ),
    ]

    return pd.DataFrame(
        {
            "snapshot_time": snapshots,
            "equity": [
                1.0,
                0.9,
                1.2,
            ],
        }
    )


def test_contract_is_not_trial_executable() -> None:
    assert F01_CANONICAL_ARTIFACT_VERSION == (
        "AMS_V2_F01_CANONICAL_ARTIFACTS_V1"
    )

    assert F01_CANONICAL_EXECUTION_STATUS == (
        "CANONICAL_TRANSLATION_REGISTERED_"
        "NOT_TRIAL_EXECUTABLE"
    )

    assert_f01_canonical_not_trial_executable()


def test_trade_aliases_and_cost_derivation() -> None:
    canonical = (
        canonicalize_f01_trade_records(
            raw_trades(),
            configuration_id=(
                "AMS-V2-F01-C01"
            ),
            fold=fold(),
        )
    )

    assert list(
        canonical["symbol"]
    ) == [
        "BTC/USDT",
        "ETH/USDT",
    ]

    assert list(
        canonical["trade_id"]
    ) == [
        (
            "AMS-V2-F01-C01-"
            "WF_2022-T00001"
        ),
        (
            "AMS-V2-F01-C01-"
            "WF_2022-T00002"
        ),
    ]

    assert list(
        canonical[
            "transaction_cost"
        ]
    ) == pytest.approx(
        [
            0.02,
            0.02,
        ]
    )


def test_explicit_trade_ids_are_preserved() -> None:
    frame = raw_trades()

    frame["trade_id"] = [
        "ORIGINAL-2",
        "ORIGINAL-1",
    ]

    canonical = (
        canonicalize_f01_trade_records(
            frame,
            configuration_id=(
                "AMS-V2-F01-C01"
            ),
            fold=fold(),
        )
    )

    assert list(
        canonical["trade_id"]
    ) == [
        "ORIGINAL-1",
        "ORIGINAL-2",
    ]


def test_missing_r_multiple_is_rejected() -> None:
    frame = raw_trades().drop(
        columns=[
            "realized_r_multiple",
        ]
    )

    with pytest.raises(
        F01CanonicalTranslationError,
        match="r_multiple",
    ):
        canonicalize_f01_trade_records(
            frame,
            configuration_id=(
                "AMS-V2-F01-C01"
            ),
            fold=fold(),
        )


def test_conflicting_aliases_are_rejected() -> None:
    frame = raw_trades()

    frame["gross_pnl"] = [
        99.0,
        99.0,
    ]

    with pytest.raises(
        F01CanonicalTranslationError,
        match="Conflicting aliases",
    ):
        canonicalize_f01_trade_records(
            frame,
            configuration_id=(
                "AMS-V2-F01-C01"
            ),
            fold=fold(),
        )


def test_identical_portfolio_duplicates_collapse() -> None:
    frame = raw_portfolio()

    duplicate = frame.iloc[
        [1]
    ].copy()

    frame = pd.concat(
        [
            frame,
            duplicate,
        ],
        ignore_index=True,
    )

    canonical = canonicalize_f01_portfolio(
        frame,
        fold=fold(),
        transaction_cost_fraction=0.002,
    )

    assert len(canonical) == 3

    assert list(
        canonical[
            "transaction_cost_fraction"
        ]
    ) == [
        0.002,
        0.002,
        0.002,
    ]


def test_conflicting_portfolio_duplicates_rejected() -> None:
    frame = raw_portfolio()

    duplicate = frame.iloc[
        [1]
    ].copy()

    duplicate["equity"] = 0.7

    frame = pd.concat(
        [
            frame,
            duplicate,
        ],
        ignore_index=True,
    )

    with pytest.raises(
        F01CanonicalTranslationError,
        match="conflicting equity",
    ):
        canonicalize_f01_portfolio(
            frame,
            fold=fold(),
            transaction_cost_fraction=0.002,
        )


def test_combined_artifacts() -> None:
    artifacts = (
        build_f01_canonical_artifacts(
            raw_trade_records=(
                raw_trades()
            ),
            raw_daily_portfolio=(
                raw_portfolio()
            ),
            configuration_id=(
                "AMS-V2-F01-C01"
            ),
            fold=fold(),
            transaction_cost_fraction=0.002,
        )
    )

    assert artifacts.to_summary() == {
        "canonical_trade_rows": 2,
        "canonical_portfolio_rows": 3,
    }


def test_empty_trade_frame_is_supported() -> None:
    empty = pd.DataFrame()

    canonical = (
        canonicalize_f01_trade_records(
            empty,
            configuration_id=(
                "AMS-V2-F01-C01"
            ),
            fold=fold(),
        )
    )

    assert canonical.empty

    assert list(
        canonical.columns
    ) == [
        "trade_id",
        "configuration_id",
        "family_id",
        "fold_name",
        "symbol",
        "entry_time",
        "exit_time",
        "base_price_gross_pnl",
        "net_pnl",
        "r_multiple",
        "transaction_cost",
    ]

def test_real_breakout_trade_schema_is_canonicalized() -> None:
    raw = pd.DataFrame(
        {
            "symbol": [
                "BTC/USDT",
            ],
            "entry_signal_time": [
                datetime(
                    2022,
                    2,
                    1,
                    tzinfo=UTC,
                ),
            ],
            "exit_signal_time": [
                datetime(
                    2022,
                    2,
                    10,
                    tzinfo=UTC,
                ),
            ],
            "entry_price": [
                100.0,
            ],
            "exit_price": [
                120.0,
            ],
            "net_trade_return_after_round_trip_cost": [
                0.196,
            ],
            "holding_days": [
                9,
            ],
            "exit_reason": [
                "TRAILING_STOP",
            ],
        }
    )

    entry_signals = pd.DataFrame(
        {
            "snapshot_time": [
                datetime(
                    2022,
                    2,
                    1,
                    tzinfo=UTC,
                ),
            ],
            "symbol": [
                "BTC/USDT",
            ],
            "atr_14": [
                4.0,
            ],
        }
    )

    canonical = canonicalize_f01_trade_records(
        raw,
        configuration_id="AMS-V2-F01-C02",
        fold=fold(),
        entry_signal_frame=entry_signals,
        initial_stop_atr=2.5,
        atr_days=14,
    )

    assert canonical[
        "base_price_gross_pnl"
    ].iloc[0] == pytest.approx(
        0.20
    )

    assert canonical[
        "net_pnl"
    ].iloc[0] == pytest.approx(
        0.196
    )

    assert canonical[
        "transaction_cost"
    ].iloc[0] == pytest.approx(
        0.004
    )

    assert canonical[
        "r_multiple"
    ].iloc[0] == pytest.approx(
        1.96
    )

    assert canonical[
        "entry_time"
    ].iloc[0] == pd.Timestamp(
        "2022-02-01T00:00:00Z"
    )

    assert canonical[
        "exit_time"
    ].iloc[0] == pd.Timestamp(
        "2022-02-10T00:00:00Z"
    )

