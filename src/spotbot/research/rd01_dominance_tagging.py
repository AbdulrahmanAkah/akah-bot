# mypy: disable-error-code="redundant-cast"
"""RD01-D1 causal dominance tagging for immutable MD01 ledgers.

The functions in this module create derived tables only.  They never mutate an
MD01FoldResult or alter any trading decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, cast

import pandas as pd

from spotbot.research.rd01_dominance import (
    DominanceDataError,
    tag_events_causally,
)

D1_SCHEMA_VERSION = "ams-rd01-d1-dominance-trade-tags-v1"

DOMINANCE_FEATURE_COLUMNS: tuple[str, ...] = (
    "day",
    "available_at",
    "btc_dominance_pct",
    "eth_dominance_pct",
    "stablecoin_dominance_pct",
    "altcoin_share_pct",
    "btc_dominance_change_7d_pp",
    "btc_dominance_change_28d_pp",
    "btc_dominance_change_84d_pp",
    "stablecoin_dominance_change_7d_pp",
    "stablecoin_dominance_change_28d_pp",
    "stablecoin_dominance_change_84d_pp",
)


def _record_dict(record: Any) -> dict[str, Any]:
    """Convert a dataclass or mapping ledger record into a detached dict."""

    if is_dataclass(record) and not isinstance(record, type):
        return cast(dict[str, Any], asdict(record))

    if isinstance(record, Mapping):
        return {str(key): value for key, value in record.items()}

    raise DominanceDataError(f"Unsupported ledger record type: {type(record).__name__}")


def records_frame(records: Iterable[Any]) -> pd.DataFrame:
    """Return a detached DataFrame for immutable ledger records."""

    rows = [_record_dict(record) for record in records]
    return pd.DataFrame(rows)


def dominance_quadrant(
    btc_change_28d_pp: Any,
    stablecoin_change_28d_pp: Any,
) -> str:
    """Classify an outcome-independent directional dominance quadrant."""

    if pd.isna(btc_change_28d_pp) or pd.isna(stablecoin_change_28d_pp):
        return "INSUFFICIENT_LOOKBACK"

    btc_change = float(btc_change_28d_pp)
    stable_change = float(stablecoin_change_28d_pp)

    if btc_change > 0.0 and stable_change > 0.0:
        return "BTC_UP_STABLE_UP"
    if btc_change > 0.0 and stable_change <= 0.0:
        return "BTC_UP_STABLE_DOWN"
    if btc_change <= 0.0 and stable_change > 0.0:
        return "BTC_DOWN_STABLE_UP"
    return "BTC_DOWN_STABLE_DOWN"


def attach_dominance_tags(
    records: pd.DataFrame,
    dominance: pd.DataFrame,
    *,
    event_time_column: str,
    prefix: str,
    maximum_age_days: int = 3,
) -> pd.DataFrame:
    """Attach causal dominance columns to one ledger table."""

    if records.empty:
        columns = list(records.columns)

        for column in DOMINANCE_FEATURE_COLUMNS:
            columns.append(f"{prefix}{column}")

        columns.extend(
            [
                f"{prefix}dominance_age_hours",
                f"{prefix}dominance_quadrant",
                f"{prefix}dominance_tag_status",
            ]
        )
        return pd.DataFrame(columns=columns)

    missing_features = sorted(set(DOMINANCE_FEATURE_COLUMNS).difference(dominance.columns))

    if missing_features:
        raise DominanceDataError(f"Dominance frame is missing D1 features: {missing_features}")

    right = dominance.loc[
        :,
        list(DOMINANCE_FEATURE_COLUMNS),
    ].copy()
    tagged = tag_events_causally(
        records,
        right,
        event_time_column=event_time_column,
        maximum_age_days=maximum_age_days,
    )

    rename = {column: f"{prefix}{column}" for column in DOMINANCE_FEATURE_COLUMNS}
    rename["dominance_age_hours"] = f"{prefix}dominance_age_hours"
    tagged = tagged.rename(columns=rename)

    btc_column = f"{prefix}btc_dominance_change_28d_pp"
    stable_column = f"{prefix}stablecoin_dominance_change_28d_pp"
    available_column = f"{prefix}available_at"
    tagged[f"{prefix}dominance_quadrant"] = [
        dominance_quadrant(btc, stable)
        for btc, stable in zip(
            cast(pd.Series, tagged[btc_column]),
            cast(pd.Series, tagged[stable_column]),
            strict=True,
        )
    ]
    tagged[f"{prefix}dominance_tag_status"] = [
        "TAGGED" if pd.notna(value) else "NO_CAUSAL_OBSERVATION"
        for value in cast(pd.Series, tagged[available_column])
    ]
    return pd.DataFrame(tagged)


def tag_candidate_ledger(
    candidates: Sequence[Any],
    dominance: pd.DataFrame,
) -> pd.DataFrame:
    """Tag candidate signals at their completed signal-bar close."""

    frame = records_frame(candidates)

    if frame.empty:
        return attach_dominance_tags(
            frame,
            dominance,
            event_time_column="signal_bar_close",
            prefix="signal_",
        )

    if "signal_bar_close" not in frame:
        raise DominanceDataError("Candidate ledger lacks signal_bar_close.")

    return attach_dominance_tags(
        frame,
        dominance,
        event_time_column="signal_bar_close",
        prefix="signal_",
    )


def tag_selection_ledger(
    selections: Sequence[Any],
    dominance: pd.DataFrame,
) -> pd.DataFrame:
    """Tag weekly selections at their registered decision timestamp."""

    frame = records_frame(selections)

    if frame.empty:
        return attach_dominance_tags(
            frame,
            dominance,
            event_time_column="timestamp",
            prefix="selection_",
        )

    if "timestamp" not in frame:
        raise DominanceDataError("Selection ledger lacks timestamp.")

    return attach_dominance_tags(
        frame,
        dominance,
        event_time_column="timestamp",
        prefix="selection_",
    )


def tag_fill_ledger(
    fills: Sequence[Any],
    dominance: pd.DataFrame,
) -> pd.DataFrame:
    """Tag immutable fills at execution time."""

    frame = records_frame(fills)

    if frame.empty:
        return attach_dominance_tags(
            frame,
            dominance,
            event_time_column="timestamp",
            prefix="fill_",
        )

    if "timestamp" not in frame:
        raise DominanceDataError("Fill ledger lacks timestamp.")

    return attach_dominance_tags(
        frame,
        dominance,
        event_time_column="timestamp",
        prefix="fill_",
    )


def tag_trade_ledger(
    trades: Sequence[Any],
    dominance: pd.DataFrame,
) -> pd.DataFrame:
    """Tag each trade independently at entry and exit."""

    frame = records_frame(trades)

    if frame.empty:
        return frame

    required = {"trade_id", "entry_time", "exit_time"}
    missing = sorted(required.difference(frame.columns))

    if missing:
        raise DominanceDataError(f"Trade ledger is missing columns: {missing}")

    entry = attach_dominance_tags(
        frame,
        dominance,
        event_time_column="entry_time",
        prefix="entry_",
    )
    exit_base = frame.loc[:, ["trade_id", "exit_time"]].copy()
    exit_tags = attach_dominance_tags(
        exit_base,
        dominance,
        event_time_column="exit_time",
        prefix="exit_",
    )

    return pd.DataFrame(
        entry.merge(
            exit_tags,
            on=["trade_id", "exit_time"],
            how="left",
            validate="one_to_one",
        )
    )


def financial_fingerprint(result: Any) -> str:
    """Hash financial state to prove D1 did not mutate the fold result."""

    payload = {
        "fold_id": str(result.fold_id),
        "status": str(result.status),
        "initial_capital": float(result.initial_capital),
        "final_cash": float(result.final_cash),
        "open_positions_after_fold": int(result.open_positions_after_fold),
        "fills": [_record_dict(record) for record in result.fills],
        "trades": [_record_dict(record) for record in result.trades],
        "equity_curve": [
            [pd.Timestamp(timestamp).isoformat(), float(value)]
            for timestamp, value in result.equity_curve
        ],
        "reconciliation": _record_dict(result.reconciliation),
    }

    def default(value: Any) -> Any:
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        raise TypeError(f"Unsupported fingerprint value: {type(value).__name__}")

    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def tag_fold_result(
    result: Any,
    dominance: pd.DataFrame,
) -> dict[str, Any]:
    """Create all D1 ledgers and prove exact financial invariance."""

    before = financial_fingerprint(result)
    ledgers = {
        "candidates": tag_candidate_ledger(
            tuple(result.candidates),
            dominance,
        ),
        "selections": tag_selection_ledger(
            tuple(result.selections),
            dominance,
        ),
        "fills": tag_fill_ledger(
            tuple(result.fills),
            dominance,
        ),
        "trades": tag_trade_ledger(
            tuple(result.trades),
            dominance,
        ),
    }
    after = financial_fingerprint(result)

    if before != after:
        raise DominanceDataError("D1 tagging mutated the immutable fold result.")

    return {
        "schema_version": D1_SCHEMA_VERSION,
        "fold_id": str(result.fold_id),
        "financial_fingerprint_before": before,
        "financial_fingerprint_after": after,
        "financial_invariance": before == after,
        "trade_logic_changed": False,
        "ledgers": ledgers,
    }
