from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.protocol_v3 import (
    MultiAssetProtocolV3DataError,
    default_multi_asset_research_protocol_v3,
    validate_multi_asset_research_frame,
)

UTC = UTC
RESEARCH_START = datetime(
    2021,
    7,
    20,
    tzinfo=UTC,
)


def test_default_protocol_v3_boundaries() -> None:
    protocol = (
        default_multi_asset_research_protocol_v3(
            research_start=RESEARCH_START,
        )
    )

    assert protocol.protocol_id == (
        "MULTI_ASSET_RESEARCH_PROTOCOL_V3"
    )

    assert [
        fold.name
        for fold in protocol.folds
    ] == [
        "WF_2022",
        "WF_2023",
        "WF_2024",
    ]

    assert (
        protocol.research_end_exclusive
        == protocol.test_start
    )

    assert (
        protocol.test_end_exclusive
        == protocol.holdout_start
    )

    serialized = protocol.to_dict()

    assert serialized["test_status"] == (
        "LOCKED"
    )

    assert serialized[
        "holdout_status"
    ] == "LOCKED"


def test_multi_asset_research_frame_accepts_symbols() -> None:
    protocol = (
        default_multi_asset_research_protocol_v3(
            research_start=RESEARCH_START,
        )
    )

    frame = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(
                    "2022-01-01T00:00:00Z"
                ),
                pd.Timestamp(
                    "2022-01-01T00:00:00Z"
                ),
            ],
            "symbol": [
                "BTC/USDT",
                "ETH/USDT",
            ],
        }
    )

    result = validate_multi_asset_research_frame(
        frame,
        protocol=protocol,
    )

    assert len(result) == 2


def test_locked_test_timestamp_is_rejected() -> None:
    protocol = (
        default_multi_asset_research_protocol_v3(
            research_start=RESEARCH_START,
        )
    )

    frame = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(
                    "2025-01-01T00:00:00Z"
                )
            ],
            "symbol": [
                "BTC/USDT"
            ],
        }
    )

    with pytest.raises(
        MultiAssetProtocolV3DataError,
        match="locked test or holdout",
    ):
        validate_multi_asset_research_frame(
            frame,
            protocol=protocol,
        )


def test_duplicate_symbol_timestamp_is_rejected() -> None:
    protocol = (
        default_multi_asset_research_protocol_v3(
            research_start=RESEARCH_START,
        )
    )

    frame = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(
                    "2023-01-01T00:00:00Z"
                ),
                pd.Timestamp(
                    "2023-01-01T00:00:00Z"
                ),
            ],
            "symbol": [
                "BTC/USDT",
                "BTC/USDT",
            ],
        }
    )

    with pytest.raises(
        MultiAssetProtocolV3DataError,
        match="duplicate",
    ):
        validate_multi_asset_research_frame(
            frame,
            protocol=protocol,
        )

def test_protocol_v3_uses_canonical_holdout_boundary() -> None:
    protocol = (
        default_multi_asset_research_protocol_v3(
            research_start=RESEARCH_START,
        )
    )

    assert protocol.holdout_end_exclusive == datetime(
        2026,
        7,
        23,
        1,
        tzinfo=UTC,
    )
