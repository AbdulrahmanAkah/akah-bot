import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from spotbot.research.features import (
    TimeframeFeatureSpec,
)
from spotbot.research.protocol import (
    HoldoutLockedError,
    ResearchCoverageError,
    ResearchPeriod,
    ResearchPlan,
    build_protocol_manifest,
    default_btc_research_plan,
    split_feature_frame,
    write_protocol_manifest,
)

START = datetime(
    2026,
    1,
    1,
    tzinfo=UTC,
)


def small_plan() -> ResearchPlan:
    return ResearchPlan(
        schema_version="test-v1",
        periods=(
            ResearchPeriod(
                "development",
                START + timedelta(hours=1),
                START + timedelta(hours=3),
            ),
            ResearchPeriod(
                "validation",
                START + timedelta(hours=3),
                START + timedelta(hours=5),
            ),
            ResearchPeriod(
                "test",
                START + timedelta(hours=5),
                START + timedelta(hours=7),
            ),
            ResearchPeriod(
                "holdout",
                START + timedelta(hours=7),
                START + timedelta(hours=9),
                locked=True,
            ),
        ),
    )


def feature_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                start=START + timedelta(hours=1),
                periods=8,
                freq="1h",
            ),
            "feature": list(range(8)),
        }
    )


def test_default_plan_has_locked_holdout() -> None:
    plan = default_btc_research_plan(
        dataset_end_exclusive=datetime(
            2026,
            7,
            23,
            1,
            tzinfo=UTC,
        )
    )

    assert plan.period("development").start == (
        datetime(2021, 7, 20, tzinfo=UTC)
    )
    assert plan.period("holdout").locked
    assert plan.period("holdout").end == (
        datetime(
            2026,
            7,
            23,
            1,
            tzinfo=UTC,
        )
    )


def test_non_contiguous_plan_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="contiguous",
    ):
        ResearchPlan(
            schema_version="test-v1",
            periods=(
                ResearchPeriod(
                    "first",
                    START,
                    START + timedelta(hours=1),
                ),
                ResearchPeriod(
                    "second",
                    START + timedelta(hours=2),
                    START + timedelta(hours=3),
                ),
            ),
        )


def test_feature_frame_is_split_exactly() -> None:
    partitions = split_feature_frame(
        feature_frame(),
        plan=small_plan(),
        expected_frequency="1h",
    )

    assert partitions.row_counts() == {
        "development": 2,
        "validation": 2,
        "test": 2,
        "holdout": 2,
    }


def test_duplicate_timestamp_is_rejected() -> None:
    source = feature_frame()
    source.loc[1, "timestamp"] = source.loc[
        0,
        "timestamp",
    ]

    with pytest.raises(
        ResearchCoverageError,
        match="duplicate",
    ):
        split_feature_frame(
            source,
            plan=small_plan(),
            expected_frequency="1h",
        )


def test_holdout_requires_explicit_unlock() -> None:
    partitions = split_feature_frame(
        feature_frame(),
        plan=small_plan(),
        expected_frequency="1h",
    )

    with pytest.raises(
        HoldoutLockedError,
        match="locked",
    ):
        partitions.get("holdout")

    unlocked = partitions.get(
        "holdout",
        unlock_locked=True,
    )

    assert len(unlocked) == 2


def test_protocol_manifest_is_written(
    tmp_path: Path,
) -> None:
    plan = small_plan()
    partitions = split_feature_frame(
        feature_frame(),
        plan=plan,
        expected_frequency="1h",
    )

    specs = {
        timeframe: TimeframeFeatureSpec(
            fast_ema=2,
            slow_ema=3,
        )
        for timeframe in ("1h", "4h", "1d")
    }

    source_hashes = {
        timeframe: "a" * 64
        for timeframe in ("1h", "4h", "1d")
    }

    manifest = build_protocol_manifest(
        exchange_id="fake",
        symbol="BTC/USDT",
        signal_timeframe="1h",
        context_timeframes=("4h", "1d"),
        plan=plan,
        partitions=partitions,
        source_hashes=source_hashes,
        feature_specs=specs,
    )

    path = write_protocol_manifest(
        manifest,
        path=tmp_path / "protocol.json",
    )

    parsed = json.loads(
        path.read_text(encoding="utf-8")
    )

    assert parsed["total_rows"] == 8
    assert parsed["periods"][-1]["locked"]
    assert parsed["holdout_policy"] == (
        "locked-until-final-model-selection"
    )