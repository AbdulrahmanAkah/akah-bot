from datetime import UTC, datetime

import pandas as pd
import pytest

from spotbot.research.protocol_v2 import (
    ResearchProtocolV2,
    ResearchProtocolV2ConfigurationError,
    ResearchProtocolV2DataError,
    WalkForwardFold,
    default_btc_research_protocol_v2,
    split_walk_forward_research_frame,
)

UTC = UTC
RESEARCH_START = datetime(
    2021,
    7,
    20,
    tzinfo=UTC,
)


def research_frame() -> pd.DataFrame:
    timestamps = pd.date_range(
        RESEARCH_START,
        datetime(
            2025,
            1,
            1,
            tzinfo=UTC,
        ),
        freq="1h",
        inclusive="left",
    )

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "value": range(
                len(timestamps)
            ),
        }
    )


def test_default_protocol_has_expanding_folds() -> None:
    protocol = (
        default_btc_research_protocol_v2(
            research_start=RESEARCH_START,
        )
    )

    assert protocol.protocol_id == (
        "BTC_RESEARCH_PROTOCOL_V2"
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
        protocol.folds[0]
        .train_end_exclusive
        < protocol.folds[1]
        .train_end_exclusive
        < protocol.folds[2]
        .train_end_exclusive
    )

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


def test_noncontiguous_fold_is_rejected() -> None:
    with pytest.raises(
        ResearchProtocolV2ConfigurationError,
        match="contiguous",
    ):
        WalkForwardFold(
            name="INVALID",
            train_start=RESEARCH_START,
            train_end_exclusive=datetime(
                2022,
                1,
                1,
                tzinfo=UTC,
            ),
            evaluation_start=datetime(
                2022,
                2,
                1,
                tzinfo=UTC,
            ),
            evaluation_end_exclusive=datetime(
                2023,
                1,
                1,
                tzinfo=UTC,
            ),
        )


def test_fold_chain_must_end_at_research_end() -> None:
    fold = WalkForwardFold(
        name="ONLY",
        train_start=RESEARCH_START,
        train_end_exclusive=datetime(
            2022,
            1,
            1,
            tzinfo=UTC,
        ),
        evaluation_start=datetime(
            2022,
            1,
            1,
            tzinfo=UTC,
        ),
        evaluation_end_exclusive=datetime(
            2023,
            1,
            1,
            tzinfo=UTC,
        ),
    )

    with pytest.raises(
        ResearchProtocolV2ConfigurationError,
        match="Final fold",
    ):
        ResearchProtocolV2(
            protocol_id="INVALID",
            research_start=RESEARCH_START,
            research_end_exclusive=datetime(
                2025,
                1,
                1,
                tzinfo=UTC,
            ),
            test_start=datetime(
                2025,
                1,
                1,
                tzinfo=UTC,
            ),
            test_end_exclusive=datetime(
                2026,
                1,
                1,
                tzinfo=UTC,
            ),
            holdout_start=datetime(
                2026,
                1,
                1,
                tzinfo=UTC,
            ),
            holdout_end_exclusive=datetime(
                2026,
                7,
                24,
                1,
                tzinfo=UTC,
            ),
            folds=(fold,),
        )


def test_actual_calendar_fold_counts() -> None:
    protocol = (
        default_btc_research_protocol_v2(
            research_start=RESEARCH_START,
        )
    )

    partitions = (
        split_walk_forward_research_frame(
            research_frame(),
            protocol=protocol,
            expected_frequency="1h",
        )
    )

    assert len(
        partitions["WF_2022"].train
    ) == 3_960

    assert len(
        partitions["WF_2022"].evaluation
    ) == 8_760

    assert len(
        partitions["WF_2023"].train
    ) == 12_720

    assert len(
        partitions["WF_2023"].evaluation
    ) == 8_760

    assert len(
        partitions["WF_2024"].train
    ) == 21_480

    assert len(
        partitions["WF_2024"].evaluation
    ) == 8_784


def test_locked_test_timestamp_is_rejected() -> None:
    protocol = (
        default_btc_research_protocol_v2(
            research_start=RESEARCH_START,
        )
    )

    frame = research_frame()

    locked_row = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(
                    "2025-01-01T00:00:00Z"
                )
            ],
            "value": [len(frame)],
        }
    )

    expanded = pd.concat(
        [frame, locked_row],
        ignore_index=True,
    )

    with pytest.raises(
        ResearchProtocolV2DataError,
        match="locked periods",
    ):
        split_walk_forward_research_frame(
            expanded,
            protocol=protocol,
            expected_frequency="1h",
        )


def test_gap_is_rejected() -> None:
    protocol = (
        default_btc_research_protocol_v2(
            research_start=RESEARCH_START,
        )
    )

    frame = research_frame().drop(
        index=[5_000]
    ).reset_index(drop=True)

    with pytest.raises(
        ResearchProtocolV2DataError,
        match="gap",
    ):
        split_walk_forward_research_frame(
            frame,
            protocol=protocol,
            expected_frequency="1h",
        )


def test_duplicate_timestamp_is_rejected() -> None:
    protocol = (
        default_btc_research_protocol_v2(
            research_start=RESEARCH_START,
        )
    )

    frame = research_frame()

    duplicated = pd.concat(
        [
            frame.iloc[:100],
            frame.iloc[[99]],
            frame.iloc[100:],
        ],
        ignore_index=True,
    )

    with pytest.raises(
        ResearchProtocolV2DataError,
        match="duplicate",
    ):
        split_walk_forward_research_frame(
            duplicated,
            protocol=protocol,
            expected_frequency="1h",
        )