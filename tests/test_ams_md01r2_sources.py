from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.ams_md01r2_sources import (
    EvidenceLevel,
    evidence_fingerprint,
    validate_effective_time,
    validate_ohlcv_boundary,
)


def test_publication_time_is_not_substituted_for_effective_time() -> None:
    effective, evidence = validate_effective_time(
        publication_time=pd.Timestamp("2024-01-01T00:00:00Z"),
        stated_effective_time=None,
    )
    assert effective is None
    assert evidence is EvidenceLevel.UNRESOLVED


def test_explicit_effective_time_is_normalised_to_utc() -> None:
    effective, evidence = validate_effective_time(
        publication_time=pd.Timestamp("2024-01-01T00:00:00Z"),
        stated_effective_time=pd.Timestamp("2024-01-02T03:00:00+03:00"),
    )
    assert effective == pd.Timestamp("2024-01-02T00:00:00Z")
    assert evidence is EvidenceLevel.EXCHANGE_ANNOUNCEMENT_EFFECTIVE_TIME


def test_last_2024_four_hour_bar_is_allowed() -> None:
    validate_ohlcv_boundary(
        pd.DataFrame(
            {
                "bar_open_time": ["2024-12-31T20:00:00Z"],
                "bar_close_time": ["2025-01-01T00:00:00Z"],
            }
        )
    )


@pytest.mark.parametrize(
    ("open_time", "close_time"),
    [
        ("2025-01-01T00:00:00Z", "2025-01-01T04:00:00Z"),
        ("2024-12-31T20:00:00Z", "2025-01-01T00:00:01Z"),
    ],
)
def test_locked_candles_are_rejected(open_time: str, close_time: str) -> None:
    with pytest.raises(ValueError):
        validate_ohlcv_boundary(
            pd.DataFrame(
                {"bar_open_time": [open_time], "bar_close_time": [close_time]}
            )
        )


def test_evidence_fingerprint_is_order_sensitive_and_reproducible() -> None:
    records = [{"symbol": "BTC-USDT", "status": "CURRENT"}, {"symbol": "ARRR-USDT"}]
    assert evidence_fingerprint(records) == evidence_fingerprint(records)
    assert evidence_fingerprint(records) != evidence_fingerprint(records[::-1])

