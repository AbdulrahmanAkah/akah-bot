import pandas as pd
import pytest

from spotbot.data.validator import validate_candles


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01",
                periods=3,
                freq="1h",
                tz="UTC",
            ),
            "open": [100.0, 101.0, 102.0],
            "high": [103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 104.0],
            "volume": [1_000.0, 1_100.0, 1_200.0],
        }
    )


def test_valid_frame_passes_validation() -> None:
    report = validate_candles(
        valid_frame(),
        symbol="BTC/USDT",
        expected_frequency="1h",
    )

    assert report.rows == 3
    assert report.duplicate_timestamps == 0
    assert report.missing_intervals == 0
    assert report.invalid_rows == 0
    assert report.is_valid


def test_duplicate_and_missing_timestamp_are_detected() -> None:
    frame = valid_frame()

    frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    frame.loc[2, "timestamp"] = pd.Timestamp(
        "2026-01-01 02:00:00",
        tz="UTC",
    )

    report = validate_candles(
        frame,
        symbol="BTC/USDT",
        expected_frequency="1h",
    )

    assert report.duplicate_timestamps == 1
    assert report.missing_intervals == 1
    assert not report.is_valid


def test_invalid_ohlc_row_is_detected() -> None:
    frame = valid_frame()

    frame.loc[1, "high"] = 90.0

    report = validate_candles(
        frame,
        symbol="BTC/USDT",
        expected_frequency="1h",
    )

    assert report.invalid_rows == 1
    assert not report.is_valid


def test_missing_required_column_is_rejected() -> None:
    frame = valid_frame().drop(columns=["volume"])

    with pytest.raises(ValueError, match="Missing columns"):
        validate_candles(
            frame,
            symbol="BTC/USDT",
            expected_frequency="1h",
        )


def test_non_numeric_value_is_detected() -> None:
    frame = valid_frame()

    frame["open"] = frame["open"].astype(object)
    frame.loc[1, "open"] = "not-a-price"

    report = validate_candles(
        frame,
        symbol="BTC/USDT",
        expected_frequency="1h",
    )

    assert report.invalid_rows == 1
    assert not report.is_valid