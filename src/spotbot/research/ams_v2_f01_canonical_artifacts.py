from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from spotbot.research.ams_v2_family_adapters import (
    AmsV2CanonicalArtifactError,
    AmsV2FamilyId,
    validate_canonical_portfolio_frame,
    validate_canonical_trade_frame,
)
from spotbot.research.ams_v2_walk_forward_orchestrator import (
    AmsV2FoldDefinition,
)

F01_CANONICAL_ARTIFACT_VERSION: Final[str] = (
    "AMS_V2_F01_CANONICAL_ARTIFACTS_V1"
)

F01_CANONICAL_EXECUTION_STATUS: Final[str] = (
    "CANONICAL_TRANSLATION_REGISTERED_NOT_TRIAL_EXECUTABLE"
)


TRADE_ID_ALIASES: Final[tuple[str, ...]] = (
    "trade_id",
    "id",
)

SYMBOL_ALIASES: Final[tuple[str, ...]] = (
    "symbol",
    "asset",
    "ticker",
)

ENTRY_TIME_ALIASES: Final[tuple[str, ...]] = (
    "entry_time",
    "entry_timestamp",
    "entry_snapshot_time",
    "opened_at",
    "open_time",
)

EXIT_TIME_ALIASES: Final[tuple[str, ...]] = (
    "exit_time",
    "exit_timestamp",
    "exit_snapshot_time",
    "closed_at",
    "close_time",
)

GROSS_PNL_ALIASES: Final[tuple[str, ...]] = (
    "base_price_gross_pnl",
    "gross_pnl",
    "gross_return",
    "gross_return_fraction",
    "return_before_cost",
    "price_return",
)

NET_PNL_ALIASES: Final[tuple[str, ...]] = (
    "net_pnl",
    "net_return",
    "net_return_fraction",
    "return_after_cost",
    "realized_return",
)

R_MULTIPLE_ALIASES: Final[tuple[str, ...]] = (
    "r_multiple",
    "realized_r_multiple",
    "trade_r_multiple",
)

TRANSACTION_COST_ALIASES: Final[tuple[str, ...]] = (
    "transaction_cost",
    "total_transaction_cost",
    "transaction_cost_fraction",
    "cost_fraction",
    "round_trip_cost_fraction",
)

SNAPSHOT_TIME_ALIASES: Final[tuple[str, ...]] = (
    "snapshot_time",
    "timestamp",
    "time",
    "date",
)

EQUITY_ALIASES: Final[tuple[str, ...]] = (
    "equity",
    "portfolio_equity",
    "ending_equity",
)


class F01CanonicalTranslationError(
    AmsV2CanonicalArtifactError
):
    pass


@dataclass(frozen=True, slots=True)
class F01CanonicalArtifacts:
    canonical_trades: pd.DataFrame
    canonical_portfolio: pd.DataFrame

    def to_summary(self) -> dict[str, int]:
        return {
            "canonical_trade_rows": len(
                self.canonical_trades
            ),
            "canonical_portfolio_rows": len(
                self.canonical_portfolio
            ),
        }


def _resolve_column(
    frame: pd.DataFrame,
    aliases: tuple[str, ...],
    *,
    field_name: str,
    required: bool = True,
) -> str | None:
    matches = [
        alias
        for alias in aliases
        if alias in frame.columns
    ]

    if len(matches) > 1:
        reference = frame[matches[0]]

        for candidate_name in matches[1:]:
            if not reference.equals(
                frame[candidate_name]
            ):
                raise F01CanonicalTranslationError(
                    f"Conflicting aliases for {field_name}: "
                    f"{matches}."
                )

    if matches:
        return matches[0]

    if required:
        raise F01CanonicalTranslationError(
            f"Raw artifact does not provide {field_name}; "
            f"accepted aliases={list(aliases)}."
        )

    return None


def _numeric_series(
    frame: pd.DataFrame,
    column: str,
    *,
    field_name: str,
) -> pd.Series:
    try:
        converted = pd.to_numeric(
            frame[column],
            errors="raise",
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise F01CanonicalTranslationError(
            f"{field_name} is not numeric."
        ) from error

    result = pd.Series(
        converted,
        index=frame.index,
        dtype="float64",
    )

    if not bool(
        np.isfinite(
            result.to_numpy(dtype=float)
        ).all()
    ):
        raise F01CanonicalTranslationError(
            f"{field_name} contains non-finite values."
        )

    return result


def _timestamp_series(
    frame: pd.DataFrame,
    column: str,
    *,
    field_name: str,
) -> pd.Series:
    try:
        converted = pd.to_datetime(
            frame[column],
            utc=True,
            errors="raise",
        )
    except (
        TypeError,
        ValueError,
    ) as error:
        raise F01CanonicalTranslationError(
            f"{field_name} is not a valid UTC timestamp."
        ) from error

    return pd.Series(
        converted,
        index=frame.index,
    )


def _empty_canonical_trade_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_id": pd.Series(
                dtype="object"
            ),
            "configuration_id": pd.Series(
                dtype="object"
            ),
            "family_id": pd.Series(
                dtype="object"
            ),
            "fold_name": pd.Series(
                dtype="object"
            ),
            "symbol": pd.Series(
                dtype="object"
            ),
            "entry_time": pd.Series(
                dtype="datetime64[ns, UTC]"
            ),
            "exit_time": pd.Series(
                dtype="datetime64[ns, UTC]"
            ),
            "base_price_gross_pnl": pd.Series(
                dtype="float64"
            ),
            "net_pnl": pd.Series(
                dtype="float64"
            ),
            "r_multiple": pd.Series(
                dtype="float64"
            ),
            "transaction_cost": pd.Series(
                dtype="float64"
            ),
        }
    )


def canonicalize_f01_trade_records(
    raw_trade_records: pd.DataFrame,
    *,
    configuration_id: str,
    fold: AmsV2FoldDefinition,
) -> pd.DataFrame:
    if not configuration_id.strip():
        raise F01CanonicalTranslationError(
            "configuration_id cannot be empty."
        )

    if raw_trade_records.empty:
        empty = _empty_canonical_trade_frame()

        return validate_canonical_trade_frame(
            empty,
            configuration_id=configuration_id,
            family_id=AmsV2FamilyId.F01,
            fold=fold,
        )

    raw = raw_trade_records.copy()

    symbol_column = _resolve_column(
        raw,
        SYMBOL_ALIASES,
        field_name="symbol",
    )

    entry_time_column = _resolve_column(
        raw,
        ENTRY_TIME_ALIASES,
        field_name="entry_time",
    )

    exit_time_column = _resolve_column(
        raw,
        EXIT_TIME_ALIASES,
        field_name="exit_time",
    )

    gross_pnl_column = _resolve_column(
        raw,
        GROSS_PNL_ALIASES,
        field_name="base_price_gross_pnl",
    )

    net_pnl_column = _resolve_column(
        raw,
        NET_PNL_ALIASES,
        field_name="net_pnl",
    )

    r_multiple_column = _resolve_column(
        raw,
        R_MULTIPLE_ALIASES,
        field_name="r_multiple",
    )

    cost_column = _resolve_column(
        raw,
        TRANSACTION_COST_ALIASES,
        field_name="transaction_cost",
        required=False,
    )

    trade_id_column = _resolve_column(
        raw,
        TRADE_ID_ALIASES,
        field_name="trade_id",
        required=False,
    )

    if (
        symbol_column is None
        or entry_time_column is None
        or exit_time_column is None
        or gross_pnl_column is None
        or net_pnl_column is None
        or r_multiple_column is None
    ):
        raise F01CanonicalTranslationError(
            "Required F01 trade mapping is incomplete."
        )

    symbol = (
        raw[symbol_column]
        .astype(str)
        .str.strip()
    )

    if (
        symbol.eq("").any()
        or symbol.str.lower().eq(
            "nan"
        ).any()
    ):
        raise F01CanonicalTranslationError(
            "Raw F01 trades contain an empty symbol."
        )

    entry_time = _timestamp_series(
        raw,
        entry_time_column,
        field_name="entry_time",
    )

    exit_time = _timestamp_series(
        raw,
        exit_time_column,
        field_name="exit_time",
    )

    gross_pnl = _numeric_series(
        raw,
        gross_pnl_column,
        field_name="base_price_gross_pnl",
    )

    net_pnl = _numeric_series(
        raw,
        net_pnl_column,
        field_name="net_pnl",
    )

    r_multiple = _numeric_series(
        raw,
        r_multiple_column,
        field_name="r_multiple",
    )

    if cost_column is None:
        transaction_cost = (
            gross_pnl - net_pnl
        )

        if (
            transaction_cost
            < -1e-12
        ).any():
            raise F01CanonicalTranslationError(
                "Cannot derive a non-negative transaction "
                "cost from gross and net PnL."
            )

        transaction_cost = (
            transaction_cost
            .clip(lower=0.0)
            .astype("float64")
        )
    else:
        transaction_cost = _numeric_series(
            raw,
            cost_column,
            field_name="transaction_cost",
        )

        if (
            transaction_cost < 0.0
        ).any():
            raise F01CanonicalTranslationError(
                "Raw transaction cost cannot be negative."
            )

    staging = pd.DataFrame(
        {
            "_original_order": range(
                len(raw)
            ),
            "symbol": symbol,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "base_price_gross_pnl": (
                gross_pnl
            ),
            "net_pnl": net_pnl,
            "r_multiple": r_multiple,
            "transaction_cost": (
                transaction_cost
            ),
        }
    )

    staging = (
        staging.sort_values(
            [
                "exit_time",
                "entry_time",
                "symbol",
                "_original_order",
            ]
        )
        .reset_index(drop=True)
    )

    if trade_id_column is None:
        trade_ids = pd.Series(
            [
                (
                    f"{configuration_id}-"
                    f"{fold.name}-T"
                    f"{index:05d}"
                )
                for index in range(
                    1,
                    len(staging) + 1,
                )
            ],
            dtype="object",
        )
    else:
        raw_ids = (
            raw[trade_id_column]
            .astype(str)
            .str.strip()
        )

        if (
            raw_ids.eq("").any()
            or raw_ids.str.lower().eq(
                "nan"
            ).any()
        ):
            raise F01CanonicalTranslationError(
                "Raw trade IDs contain an empty value."
            )

        id_frame = pd.DataFrame(
            {
                "_original_order": range(
                    len(raw)
                ),
                "trade_id": raw_ids,
            }
        )

        trade_ids = (
            staging[
                ["_original_order"]
            ]
            .merge(
                id_frame,
                on="_original_order",
                how="left",
                validate="one_to_one",
            )["trade_id"]
            .reset_index(drop=True)
        )

    canonical = pd.DataFrame(
        {
            "trade_id": trade_ids,
            "configuration_id": (
                configuration_id
            ),
            "family_id": (
                AmsV2FamilyId.F01.value
            ),
            "fold_name": fold.name,
            "symbol": staging["symbol"],
            "entry_time": (
                staging["entry_time"]
            ),
            "exit_time": (
                staging["exit_time"]
            ),
            "base_price_gross_pnl": (
                staging[
                    "base_price_gross_pnl"
                ]
            ),
            "net_pnl": staging["net_pnl"],
            "r_multiple": (
                staging["r_multiple"]
            ),
            "transaction_cost": (
                staging[
                    "transaction_cost"
                ]
            ),
        }
    )

    return validate_canonical_trade_frame(
        canonical,
        configuration_id=configuration_id,
        family_id=AmsV2FamilyId.F01,
        fold=fold,
    )


def canonicalize_f01_portfolio(
    raw_daily_portfolio: pd.DataFrame,
    *,
    fold: AmsV2FoldDefinition,
    transaction_cost_fraction: float,
) -> pd.DataFrame:
    if (
        not math.isfinite(
            transaction_cost_fraction
        )
        or not (
            0.0
            <= transaction_cost_fraction
            <= 0.01
        )
    ):
        raise F01CanonicalTranslationError(
            "transaction_cost_fraction must be inside "
            "[0, 0.01]."
        )

    snapshot_column = _resolve_column(
        raw_daily_portfolio,
        SNAPSHOT_TIME_ALIASES,
        field_name="snapshot_time",
    )

    equity_column = _resolve_column(
        raw_daily_portfolio,
        EQUITY_ALIASES,
        field_name="equity",
    )

    if (
        snapshot_column is None
        or equity_column is None
    ):
        raise F01CanonicalTranslationError(
            "Required portfolio mapping is incomplete."
        )

    snapshot_time = _timestamp_series(
        raw_daily_portfolio,
        snapshot_column,
        field_name="snapshot_time",
    )

    equity = _numeric_series(
        raw_daily_portfolio,
        equity_column,
        field_name="equity",
    )

    staging = pd.DataFrame(
        {
            "snapshot_time": snapshot_time,
            "equity": equity,
        }
    )

    if (
        staging["equity"] <= 0.0
    ).any():
        raise F01CanonicalTranslationError(
            "Portfolio equity must remain positive."
        )

    if staging[
        "snapshot_time"
    ].duplicated().any():
        grouped = staging.groupby(
            "snapshot_time",
            sort=True,
        )["equity"]

        spread = (
            grouped.max()
            - grouped.min()
        )

        if (
            spread > 1e-12
        ).any():
            raise F01CanonicalTranslationError(
                "Duplicate portfolio snapshots contain "
                "conflicting equity values."
            )

        staging = (
            staging.sort_values(
                "snapshot_time"
            )
            .drop_duplicates(
                subset=[
                    "snapshot_time",
                ],
                keep="last",
            )
            .reset_index(drop=True)
        )
    else:
        staging = (
            staging.sort_values(
                "snapshot_time"
            )
            .reset_index(drop=True)
        )

    canonical = pd.DataFrame(
        {
            "snapshot_time": (
                staging[
                    "snapshot_time"
                ]
            ),
            "equity": staging["equity"],
            "transaction_cost_fraction": (
                transaction_cost_fraction
            ),
        }
    )

    return validate_canonical_portfolio_frame(
        canonical,
        fold=fold,
        expected_cost=(
            transaction_cost_fraction
        ),
        artifact_name=(
            "F01 canonical portfolio"
        ),
    )


def build_f01_canonical_artifacts(
    *,
    raw_trade_records: pd.DataFrame,
    raw_daily_portfolio: pd.DataFrame,
    configuration_id: str,
    fold: AmsV2FoldDefinition,
    transaction_cost_fraction: float,
) -> F01CanonicalArtifacts:
    canonical_trades = (
        canonicalize_f01_trade_records(
            raw_trade_records,
            configuration_id=(
                configuration_id
            ),
            fold=fold,
        )
    )

    canonical_portfolio = (
        canonicalize_f01_portfolio(
            raw_daily_portfolio,
            fold=fold,
            transaction_cost_fraction=(
                transaction_cost_fraction
            ),
        )
    )

    return F01CanonicalArtifacts(
        canonical_trades=canonical_trades,
        canonical_portfolio=(
            canonical_portfolio
        ),
    )


def assert_f01_canonical_not_trial_executable(
) -> None:
    if F01_CANONICAL_EXECUTION_STATUS != (
        "CANONICAL_TRANSLATION_REGISTERED_"
        "NOT_TRIAL_EXECUTABLE"
    ):
        raise F01CanonicalTranslationError(
            "F01 trial execution was enabled before "
            "fold-harness authorization."
        )