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
    "entry_signal_time",
)

EXIT_TIME_ALIASES: Final[tuple[str, ...]] = (
    "exit_time",
    "exit_timestamp",
    "exit_snapshot_time",
    "closed_at",
    "close_time",
    "exit_signal_time",
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
    "net_trade_return_after_round_trip_cost",
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

ENTRY_PRICE_ALIASES: Final[tuple[str, ...]] = (
    "entry_price",
    "fill_entry_price",
    "open_price",
)

EXIT_PRICE_ALIASES: Final[tuple[str, ...]] = (
    "exit_price",
    "fill_exit_price",
    "close_price",
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



def _resolve_entry_atr_column(
    frame: pd.DataFrame,
    *,
    atr_days: int,
) -> str:
    excluded_tokens = (
        "expansion",
        "minimum",
        "maximum",
        "stop",
        "trail",
        "multiple",
        "percentile",
        "rank",
    )

    scored: list[tuple[int, str]] = []

    for raw_column in frame.columns:
        column = str(raw_column)
        lowered = column.casefold()

        if (
            "atr" not in lowered
            and "average_true_range" not in lowered
        ):
            continue

        if any(
            token in lowered
            for token in excluded_tokens
        ):
            continue

        score = 0

        if lowered == f"atr_{atr_days}":
            score = 100
        elif lowered == f"atr{atr_days}":
            score = 95
        elif lowered == "atr":
            score = 90
        elif lowered == "average_true_range":
            score = 85
        elif (
            lowered.startswith("atr_")
            and str(atr_days) in lowered
        ):
            score = 80
        elif lowered.startswith("atr"):
            score = 70
        else:
            score = 60

        try:
            pd.to_numeric(
                frame[column],
                errors="raise",
            )
        except (TypeError, ValueError):
            continue

        scored.append(
            (
                score,
                column,
            )
        )

    if not scored:
        raise F01CanonicalTranslationError(
            "Entry signal frame does not provide a usable ATR "
            "column for R-multiple derivation."
        )

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1],
        )
    )

    best_score = scored[0][0]

    best_columns = [
        column
        for score, column in scored
        if score == best_score
    ]

    if len(best_columns) != 1:
        raise F01CanonicalTranslationError(
            "Entry signal frame provides ambiguous ATR columns: "
            f"{best_columns}."
        )

    return best_columns[0]


def _derive_r_multiple_from_entry_signals(
    *,
    entry_signal_frame: pd.DataFrame,
    symbols: pd.Series,
    entry_times: pd.Series,
    entry_prices: pd.Series,
    net_pnl: pd.Series,
    initial_stop_atr: float,
    atr_days: int,
) -> pd.Series:
    if (
        not math.isfinite(initial_stop_atr)
        or initial_stop_atr <= 0.0
    ):
        raise F01CanonicalTranslationError(
            "initial_stop_atr must be positive and finite."
        )

    if atr_days <= 0:
        raise F01CanonicalTranslationError(
            "atr_days must be positive."
        )

    signal_symbol_column = _resolve_column(
        entry_signal_frame,
        SYMBOL_ALIASES,
        field_name="entry signal symbol",
    )

    signal_time_column = _resolve_column(
        entry_signal_frame,
        SNAPSHOT_TIME_ALIASES,
        field_name="entry signal time",
    )

    if (
        signal_symbol_column is None
        or signal_time_column is None
    ):
        raise F01CanonicalTranslationError(
            "Entry signal frame mapping is incomplete."
        )

    atr_column = _resolve_entry_atr_column(
        entry_signal_frame,
        atr_days=atr_days,
    )

    signal_symbols = (
        entry_signal_frame[
            signal_symbol_column
        ]
        .astype(str)
        .str.strip()
    )

    signal_times = _timestamp_series(
        entry_signal_frame,
        signal_time_column,
        field_name="entry signal time",
    )

    signal_atr = _numeric_series(
        entry_signal_frame,
        atr_column,
        field_name="entry signal ATR",
    )

    signals = pd.DataFrame(
        {
            "_signal_symbol": signal_symbols,
            "_signal_entry_time": signal_times,
            "_entry_atr": signal_atr,
        }
    )

    grouped = signals.groupby(
        [
            "_signal_symbol",
            "_signal_entry_time",
        ],
        sort=False,
    )["_entry_atr"]

    spread = (
        grouped.max()
        - grouped.min()
    )

    if (
        spread > 1e-12
    ).any():
        raise F01CanonicalTranslationError(
            "Entry signal frame contains conflicting ATR "
            "values for the same symbol and timestamp."
        )

    signals = (
        signals.sort_values(
            [
                "_signal_entry_time",
                "_signal_symbol",
            ]
        )
        .drop_duplicates(
            subset=[
                "_signal_symbol",
                "_signal_entry_time",
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    trades = pd.DataFrame(
        {
            "_row_order": range(
                len(symbols)
            ),
            "_signal_symbol": (
                symbols.astype(str)
                .str.strip()
                .to_numpy()
            ),
            "_signal_entry_time": (
                entry_times.to_numpy()
            ),
            "_entry_price": (
                entry_prices.to_numpy(
                    dtype=float
                )
            ),
            "_net_pnl": (
                net_pnl.to_numpy(
                    dtype=float
                )
            ),
        }
    )

    merged = trades.merge(
        signals,
        on=[
            "_signal_symbol",
            "_signal_entry_time",
        ],
        how="left",
        validate="many_to_one",
    )

    merged = merged.sort_values(
        "_row_order"
    ).reset_index(drop=True)

    if merged["_entry_atr"].isna().any():
        missing = merged.loc[
            merged["_entry_atr"].isna(),
            [
                "_signal_symbol",
                "_signal_entry_time",
            ],
        ]

        raise F01CanonicalTranslationError(
            "Could not match entry ATR for raw F01 trades: "
            f"{missing.to_dict(orient='records')[:5]}."
        )

    if (
        merged["_entry_price"] <= 0.0
    ).any():
        raise F01CanonicalTranslationError(
            "Raw F01 entry prices must be positive."
        )

    initial_risk_fraction = (
        initial_stop_atr
        * merged["_entry_atr"]
        / merged["_entry_price"]
    )

    if (
        initial_risk_fraction <= 0.0
    ).any():
        raise F01CanonicalTranslationError(
            "Derived F01 initial risk must be positive."
        )

    r_multiple = (
        merged["_net_pnl"]
        / initial_risk_fraction
    )

    if not bool(
        np.isfinite(
            r_multiple.to_numpy(
                dtype=float
            )
        ).all()
    ):
        raise F01CanonicalTranslationError(
            "Derived F01 R-multiple contains non-finite values."
        )

    return pd.Series(
        r_multiple.to_numpy(
            dtype=float
        ),
        index=symbols.index,
        dtype="float64",
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
    entry_signal_frame: pd.DataFrame | None = None,
    initial_stop_atr: float | None = None,
    atr_days: int | None = None,
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
        required=False,
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
        required=False,
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

    entry_price_column = _resolve_column(
        raw,
        ENTRY_PRICE_ALIASES,
        field_name="entry_price",
        required=False,
    )

    exit_price_column = _resolve_column(
        raw,
        EXIT_PRICE_ALIASES,
        field_name="exit_price",
        required=False,
    )

    if (
        symbol_column is None
        or entry_time_column is None
        or exit_time_column is None
        or net_pnl_column is None
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

    entry_price: pd.Series | None = None

    if entry_price_column is not None:
        entry_price = _numeric_series(
            raw,
            entry_price_column,
            field_name="entry_price",
        )

        if (
            entry_price <= 0.0
        ).any():
            raise F01CanonicalTranslationError(
                "Raw F01 entry prices must be positive."
            )

    if gross_pnl_column is None:
        if (
            entry_price is None
            or exit_price_column is None
        ):
            raise F01CanonicalTranslationError(
                "Raw artifact must provide gross PnL or both "
                "entry_price and exit_price."
            )

        exit_price = _numeric_series(
            raw,
            exit_price_column,
            field_name="exit_price",
        )

        if (
            exit_price <= 0.0
        ).any():
            raise F01CanonicalTranslationError(
                "Raw F01 exit prices must be positive."
            )

        gross_pnl = (
            exit_price
            / entry_price
            - 1.0
        ).astype("float64")
    else:
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

    if r_multiple_column is None:
        if (
            entry_signal_frame is None
            or initial_stop_atr is None
            or atr_days is None
            or entry_price is None
        ):
            raise F01CanonicalTranslationError(
                "Raw artifact does not provide r_multiple; "
                "entry signals, initial_stop_atr, atr_days, "
                "and entry_price are required for derivation."
            )

        r_multiple = (
            _derive_r_multiple_from_entry_signals(
                entry_signal_frame=entry_signal_frame,
                symbols=symbol,
                entry_times=entry_time,
                entry_prices=entry_price,
                net_pnl=net_pnl,
                initial_stop_atr=initial_stop_atr,
                atr_days=atr_days,
            )
        )
    else:
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
    entry_signal_frame: pd.DataFrame | None = None,
    initial_stop_atr: float | None = None,
    atr_days: int | None = None,
) -> F01CanonicalArtifacts:
    canonical_trades = (
        canonicalize_f01_trade_records(
            raw_trade_records,
            configuration_id=(
                configuration_id
            ),
            fold=fold,
            entry_signal_frame=entry_signal_frame,
            initial_stop_atr=initial_stop_atr,
            atr_days=atr_days,
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