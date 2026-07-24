from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

REQUIRED_ENTRY_FILTER_COLUMNS = (
    "timestamp",
    "close",
    "volume",
    "raw_entry_signal",
    "1h_ema_fast",
    "1h_atr",
    "1h_rsi",
    "1h_volume_median",
    "stop_distance_atr",
)


class EntryFilterError(RuntimeError):
    pass


class EntryFilterConfigurationError(
    EntryFilterError
):
    pass


class EntryFilterDataError(EntryFilterError):
    pass


@dataclass(frozen=True, slots=True)
class EntryFilterConfig:
    minimum_rsi: float | None = None
    maximum_rsi: float | None = None
    minimum_stop_distance_atr: (
        float | None
    ) = None
    maximum_stop_distance_atr: (
        float | None
    ) = None
    minimum_entry_extension_atr: (
        float | None
    ) = None
    maximum_entry_extension_atr: (
        float | None
    ) = None
    minimum_volume_ratio: float | None = None

    def __post_init__(self) -> None:
        self._validate_optional_finite(
            self.minimum_rsi,
            name="minimum_rsi",
        )
        self._validate_optional_finite(
            self.maximum_rsi,
            name="maximum_rsi",
        )
        self._validate_optional_finite(
            self.minimum_stop_distance_atr,
            name=(
                "minimum_stop_distance_atr"
            ),
        )
        self._validate_optional_finite(
            self.maximum_stop_distance_atr,
            name=(
                "maximum_stop_distance_atr"
            ),
        )
        self._validate_optional_finite(
            self.minimum_entry_extension_atr,
            name=(
                "minimum_entry_extension_atr"
            ),
        )
        self._validate_optional_finite(
            self.maximum_entry_extension_atr,
            name=(
                "maximum_entry_extension_atr"
            ),
        )
        self._validate_optional_finite(
            self.minimum_volume_ratio,
            name="minimum_volume_ratio",
        )

        for name, value in {
            "minimum_rsi": self.minimum_rsi,
            "maximum_rsi": self.maximum_rsi,
        }.items():
            if (
                value is not None
                and not 0.0 <= value <= 100.0
            ):
                raise (
                    EntryFilterConfigurationError(
                        f"{name} must be within "
                        "[0, 100]."
                    )
                )

        for name, value in {
            "minimum_stop_distance_atr": (
                self.minimum_stop_distance_atr
            ),
            "maximum_stop_distance_atr": (
                self.maximum_stop_distance_atr
            ),
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
        }.items():
            if (
                value is not None
                and value < 0.0
            ):
                raise (
                    EntryFilterConfigurationError(
                        f"{name} cannot be negative."
                    )
                )

        self._validate_bounds(
            self.minimum_rsi,
            self.maximum_rsi,
            name="RSI",
        )
        self._validate_bounds(
            self.minimum_stop_distance_atr,
            self.maximum_stop_distance_atr,
            name="stop distance",
        )
        self._validate_bounds(
            self.minimum_entry_extension_atr,
            self.maximum_entry_extension_atr,
            name="entry extension",
        )

    @staticmethod
    def _validate_optional_finite(
        value: float | None,
        *,
        name: str,
    ) -> None:
        if (
            value is not None
            and not isfinite(value)
        ):
            raise EntryFilterConfigurationError(
                f"{name} must be finite."
            )

    @staticmethod
    def _validate_bounds(
        minimum: float | None,
        maximum: float | None,
        *,
        name: str,
    ) -> None:
        if (
            minimum is not None
            and maximum is not None
            and minimum > maximum
        ):
            raise EntryFilterConfigurationError(
                f"{name} minimum cannot be "
                "greater than maximum."
            )

    def to_dict(
        self,
    ) -> dict[str, float | None]:
        return {
            "minimum_rsi": self.minimum_rsi,
            "maximum_rsi": self.maximum_rsi,
            "minimum_stop_distance_atr": (
                self.minimum_stop_distance_atr
            ),
            "maximum_stop_distance_atr": (
                self.maximum_stop_distance_atr
            ),
            "minimum_entry_extension_atr": (
                self.minimum_entry_extension_atr
            ),
            "maximum_entry_extension_atr": (
                self.maximum_entry_extension_atr
            ),
            "minimum_volume_ratio": (
                self.minimum_volume_ratio
            ),
        }


def _validate_source(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing = set(
        REQUIRED_ENTRY_FILTER_COLUMNS
    ).difference(frame.columns)

    if missing:
        raise EntryFilterDataError(
            "Entry-filter source is missing "
            f"columns: {sorted(missing)}."
        )

    result = frame.copy()

    result["timestamp"] = pd.to_datetime(
        result["timestamp"],
        utc=True,
        errors="coerce",
    )

    if bool(
        result["timestamp"].isna().any()
    ):
        raise EntryFilterDataError(
            "Entry-filter source contains "
            "invalid timestamps."
        )

    if bool(
        result["timestamp"].duplicated().any()
    ):
        raise EntryFilterDataError(
            "Entry-filter source contains "
            "duplicate timestamps."
        )

    if not bool(
        result["timestamp"]
        .is_monotonic_increasing
    ):
        raise EntryFilterDataError(
            "Entry-filter source must be "
            "chronologically ordered."
        )

    raw_signal_values = result[
        "raw_entry_signal"
    ].tolist()

    if not all(
        isinstance(
            value,
            (bool, np.bool_),
        )
        for value in raw_signal_values
    ):
        raise EntryFilterDataError(
            "raw_entry_signal must contain "
            "Boolean values only."
        )

    numeric_columns = (
        "close",
        "volume",
        "1h_ema_fast",
        "1h_atr",
        "1h_rsi",
        "1h_volume_median",
        "stop_distance_atr",
    )

    for column in numeric_columns:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    values = result[
        list(numeric_columns)
    ].to_numpy(dtype=float)

    if not bool(
        np.isfinite(values).all()
    ):
        raise EntryFilterDataError(
            "Entry-filter source contains "
            "non-finite numeric values."
        )

    if bool(
        (
            result["1h_atr"]
            <= 0.0
        ).any()
    ):
        raise EntryFilterDataError(
            "ATR values must be positive."
        )

    if bool(
        (
            result["1h_volume_median"]
            <= 0.0
        ).any()
    ):
        raise EntryFilterDataError(
            "Volume medians must be positive."
        )

    return result


def apply_entry_filter(
    frame: pd.DataFrame,
    *,
    config: EntryFilterConfig,
) -> pd.DataFrame:
    result = _validate_source(frame)

    original_signal = (
        result["raw_entry_signal"]
        .astype(bool)
    )

    entry_extension_atr = (
        (
            result["close"]
            - result["1h_ema_fast"]
        )
        / result["1h_atr"]
    ).astype("float64")

    volume_ratio = (
        result["volume"]
        / result["1h_volume_median"]
    ).astype("float64")

    filter_ok = pd.Series(
        True,
        index=result.index,
        dtype=bool,
    )

    if config.minimum_rsi is not None:
        filter_ok &= (
            result["1h_rsi"]
            >= config.minimum_rsi
        )

    if config.maximum_rsi is not None:
        filter_ok &= (
            result["1h_rsi"]
            <= config.maximum_rsi
        )

    if (
        config.minimum_stop_distance_atr
        is not None
    ):
        filter_ok &= (
            result["stop_distance_atr"]
            >= (
                config
                .minimum_stop_distance_atr
            )
        )

    if (
        config.maximum_stop_distance_atr
        is not None
    ):
        filter_ok &= (
            result["stop_distance_atr"]
            <= (
                config
                .maximum_stop_distance_atr
            )
        )

    if (
        config.minimum_entry_extension_atr
        is not None
    ):
        filter_ok &= (
            entry_extension_atr
            >= (
                config
                .minimum_entry_extension_atr
            )
        )

    if (
        config.maximum_entry_extension_atr
        is not None
    ):
        filter_ok &= (
            entry_extension_atr
            <= (
                config
                .maximum_entry_extension_atr
            )
        )

    if (
        config.minimum_volume_ratio
        is not None
    ):
        filter_ok &= (
            volume_ratio
            >= config.minimum_volume_ratio
        )

    filtered_signal = (
        original_signal
        & filter_ok
    )

    result["v1_raw_entry_signal"] = (
        original_signal
    )
    result["entry_extension_atr"] = (
        entry_extension_atr
    )
    result["volume_ratio"] = (
        volume_ratio
    )
    result["entry_filter_ok"] = (
        filter_ok.astype(bool)
    )
    result["v2_entry_signal"] = (
        filtered_signal.astype(bool)
    )

    # Simulator compatibility: the simulator
    # consumes raw_entry_signal.
    result["raw_entry_signal"] = (
        filtered_signal.astype(bool)
    )

    return result