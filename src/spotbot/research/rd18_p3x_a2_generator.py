# mypy: disable-error-code="no-any-return"
"""RD18-P3X-A2 causal C2 pre-router signal generator.

This module freezes the two registered signal families, replaces the pilot-only
static asset gate with the A1B monthly causal gate, and applies the A1C explicit
corporate-action exclusions. It does not replay trades, route positions,
calculate returns, optimize thresholds, or authorize production use.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import pandas as pd

from spotbot.research.rd16c_common import dataframe_content_hash
from spotbot.research.rd16c_families import REGISTRY_BY_ID, build_candidate_frame
from spotbot.research.rd16c_features import (
    FeatureDataError,
    build_feature_frame,
)
from spotbot.research.rd16d_metrics import (
    market_regime_from_row,
    volatility_regime_from_row,
)
from spotbot.research.rd16e_components import (
    attach_signal_features,
    fee_buffer_mask,
    regime_mask,
    structural_mask,
    volatility_mask,
)
from spotbot.research.rd18_p3x_a1 import SEALED_CUTOFF, symbol_to_pair
from spotbot.research.rd18_p3x_a1b_asset_gate import eligibility_mask

SCHEMA_VERSION: Final = "rd18-p3x-a2-pre-router-generator-v1"
STAGE: Final = "RD18_P3X_A2_C2_GENERATOR_BUILD"
ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V3"
SOURCE_ARCHITECTURE_ID: Final = "COMPOSITE_ALPHA_V2"
SOURCE_VARIANT_ID: Final = "STRONG_BULL_HOLD_96"

TREND_FAMILY_ID: Final = "MTF_TREND_BREAKOUT"
COMPRESSION_FAMILY_ID: Final = "MTF_COMPRESSION_EXPANSION"
TREND_ENGINE_ID: Final = "TREND_CONTINUATION_CORE_V3"
COMPRESSION_ENGINE_ID: Final = "COMPRESSION_EXPANSION_SPECIALIST_V3"
COMPRESSION_COOLDOWN_HOURS: Final = 24

FAMILY_IDS: Final = (TREND_FAMILY_ID, COMPRESSION_FAMILY_ID)
ENGINE_BY_FAMILY: Final = {
    TREND_FAMILY_ID: TREND_ENGINE_ID,
    COMPRESSION_FAMILY_ID: COMPRESSION_ENGINE_ID,
}
PRIORITY_BY_FAMILY: Final = {
    TREND_FAMILY_ID: 10,
    COMPRESSION_FAMILY_ID: 20,
}

FORBIDDEN_OUTCOME_COLUMNS: Final = frozenset(
    {
        "exit_bar_close",
        "exit_price",
        "exit_reason",
        "bars_held",
        "quantity",
        "notional",
        "risk_budget",
        "gross_pnl",
        "fees",
        "net_pnl",
        "mfe_r",
        "mae_r",
        "router_decision",
        "positions_before",
        "positions_after",
        "open_risk_before",
        "open_risk_after",
    }
)

CANDIDATE_FIELDS: Final = (
    "candidate_id",
    "schema_version",
    "stage",
    "architecture_id",
    "source_architecture_id",
    "source_variant_id",
    "engine_id",
    "engine_priority",
    "family_id",
    "source_rule",
    "router_status",
    "pair",
    "symbol",
    "signal_close",
    "signal_month",
    "entry_open_time",
    "entry_bar_close",
    "entry_price",
    "atr14_at_signal",
    "signal_low",
    "signal_high",
    "market_regime",
    "volatility_regime",
    "4h_context_close",
    "1d_context_close",
    "1w_context_close",
    "a1b_eligible",
    "a1b_reason",
    "a1b_input_window_sha256",
    "a1c_identity_ready",
    "regime_ready",
    "volatility_ready",
    "structure_ready",
    "fee_buffer_ready",
    "cooldown_ready",
)

AUDIT_FIELDS: Final = (
    *CANDIDATE_FIELDS,
    "selected_pre_router",
    "rejection_reason",
)

SUMMARY_FIELDS: Final = (
    "pair",
    "symbol",
    "raw_signal_rows",
    "selected_candidate_rows",
    "trend_raw_rows",
    "trend_selected_rows",
    "compression_raw_rows",
    "compression_selected_rows",
    "first_signal_close",
    "last_signal_close",
    "candidate_content_sha256",
    "audit_content_sha256",
    "generation_status",
    "generation_reason",
)


class A2GeneratorError(ValueError):
    """Raised when A2 generator inputs violate the frozen contract."""


@dataclass(frozen=True, slots=True)
class SymbolGenerationResult:
    candidates: pd.DataFrame
    audit: pd.DataFrame
    summary: dict[str, object]


def _utc_series(values: pd.Series, *, column: str) -> pd.Series:
    parsed = pd.to_datetime(values, utc=True, errors="raise")
    if bool(parsed.isna().any()):
        raise A2GeneratorError(f"invalid timestamps in {column}")
    return parsed.astype("datetime64[ns, UTC]")


def _month_start(values: pd.Series) -> pd.Series:
    timestamps = _utc_series(values, column="signal_close")
    return timestamps.dt.tz_localize(None).dt.to_period("M").dt.to_timestamp().dt.tz_localize("UTC")


def _boolean_series(values: pd.Series, *, column: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    if bool(~normalized.isin({"true", "false", "1", "0"}).any()):
        raise A2GeneratorError(f"invalid boolean values in {column}")
    return normalized.isin({"true", "1"})


def _empty_frame(fields: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=list(fields))


def validate_eligibility_ledger(
    eligibility: pd.DataFrame,
    *,
    expected_symbols: int | None = None,
    expected_months: int | None = None,
) -> pd.DataFrame:
    required = {
        "month_start",
        "symbol",
        "eligible",
        "reason",
        "input_window_sha256",
    }
    missing = sorted(required.difference(eligibility.columns))
    if missing:
        raise A2GeneratorError(f"A1B eligibility columns missing: {missing}")

    ledger = eligibility.loc[:, sorted(required)].copy()
    ledger["month_start"] = _utc_series(
        ledger["month_start"],
        column="month_start",
    )
    ledger["symbol"] = ledger["symbol"].astype(str)
    ledger["eligible"] = _boolean_series(ledger["eligible"], column="eligible")
    ledger["reason"] = ledger["reason"].astype(str)
    ledger["input_window_sha256"] = ledger["input_window_sha256"].astype(str)

    if bool(ledger.duplicated(["month_start", "symbol"]).any()):
        raise A2GeneratorError("A1B eligibility has duplicate symbol-month rows")
    if bool((ledger["eligible"] & (ledger["reason"] != "ELIGIBLE")).any()):
        raise A2GeneratorError("eligible A1B rows must have reason ELIGIBLE")
    if bool((~ledger["eligible"] & (ledger["reason"] == "ELIGIBLE")).any()):
        raise A2GeneratorError("rejected A1B rows cannot have reason ELIGIBLE")

    if expected_symbols is not None:
        observed_symbols = int(ledger["symbol"].nunique())
        if observed_symbols != expected_symbols:
            raise A2GeneratorError(
                f"expected {expected_symbols} A1B symbols, found {observed_symbols}"
            )
    if expected_months is not None:
        observed_months = int(ledger["month_start"].nunique())
        if observed_months != expected_months:
            raise A2GeneratorError(
                f"expected {expected_months} A1B months, found {observed_months}"
            )
    return ledger.sort_values(
        ["month_start", "symbol"],
        kind="stable",
    ).reset_index(drop=True)


def _regime_context(feature_frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "timestamp",
        "1d_close",
        "1d_ema50",
        "1d_ema200",
        "1w_close",
        "1w_ema40",
        "4h_atr_ratio",
    }
    missing = sorted(required.difference(feature_frame.columns))
    if missing:
        raise A2GeneratorError(f"feature regime columns missing: {missing}")

    selected = feature_frame.loc[:, sorted(required)].copy()
    selected["timestamp"] = _utc_series(
        selected["timestamp"],
        column="timestamp",
    )
    records = selected.to_dict(orient="records")
    selected["market_regime"] = [
        market_regime_from_row(cast(Mapping[str, object], row)) for row in records
    ]
    selected["volatility_regime"] = [
        volatility_regime_from_row(cast(Mapping[str, object], row)) for row in records
    ]
    return selected.loc[
        :,
        ["timestamp", "market_regime", "volatility_regime"],
    ].rename(columns={"timestamp": "signal_close"})


def _attach_context_and_features(
    candidates: pd.DataFrame,
    *,
    feature_frame: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame:
    if candidates.empty:
        return candidates.copy()

    working = candidates.copy()
    working["signal_close"] = _utc_series(
        working["signal_close"],
        column="signal_close",
    )
    context = _regime_context(feature_frame)
    working = working.merge(
        context,
        on="signal_close",
        how="left",
        validate="many_to_one",
        sort=False,
    )
    if bool(working[["market_regime", "volatility_regime"]].isna().any().any()):
        raise A2GeneratorError(f"{symbol}: signal regime context is missing")
    return attach_signal_features(
        working,
        feature_frames={symbol: feature_frame},
    )


def _a1b_decisions(
    working: pd.DataFrame,
    eligibility: pd.DataFrame,
    *,
    family_id: str,
) -> pd.DataFrame:
    if working.empty:
        return pd.DataFrame(
            columns=[
                "a1b_eligible",
                "a1b_reason",
                "a1b_input_window_sha256",
            ],
            index=working.index,
        )

    mask = eligibility_mask(
        working,
        eligibility=eligibility,
        family_id=family_id,
    )
    keys = working.loc[:, ["symbol", "signal_close"]].copy()
    keys["signal_month"] = _month_start(keys["signal_close"])

    ledger = eligibility.loc[
        :,
        [
            "month_start",
            "symbol",
            "eligible",
            "reason",
            "input_window_sha256",
        ],
    ].copy()
    ledger["month_start"] = _utc_series(
        ledger["month_start"],
        column="month_start",
    )
    ledger = ledger.rename(
        columns={
            "month_start": "signal_month",
            "eligible": "a1b_eligible",
            "reason": "a1b_reason",
            "input_window_sha256": "a1b_input_window_sha256",
        }
    )
    merged = keys.merge(
        ledger,
        on=["signal_month", "symbol"],
        how="left",
        validate="many_to_one",
        sort=False,
    )
    if bool(merged["a1b_eligible"].isna().any()):
        raise A2GeneratorError("signal rows lack an explicit A1B symbol-month decision")
    if mask.astype(bool).tolist() != merged["a1b_eligible"].astype(bool).tolist():
        raise A2GeneratorError("A1B mask and ledger merge disagree")

    return merged.loc[
        :,
        [
            "a1b_eligible",
            "a1b_reason",
            "a1b_input_window_sha256",
        ],
    ].set_axis(working.index)


def _compression_cooldown_mask(
    working: pd.DataFrame,
    preselected: pd.Series,
) -> pd.Series:
    result = pd.Series(False, index=working.index, dtype=bool)
    ordered = working.loc[preselected].sort_values(
        ["signal_close", "candidate_id"],
        kind="stable",
    )
    previous: pd.Timestamp | None = None
    minimum = pd.Timedelta(hours=COMPRESSION_COOLDOWN_HOURS)
    for raw_index, raw_time in ordered.loc[:, ["signal_close"]].itertuples(
        index=True,
        name=None,
    ):
        signal_time = pd.Timestamp(raw_time)
        if signal_time.tzinfo is None:
            signal_time = signal_time.tz_localize("UTC")
        else:
            signal_time = signal_time.tz_convert("UTC")
        if previous is not None and signal_time - previous < minimum:
            continue
        result.at[raw_index] = True
        previous = signal_time
    return result


def _source_rule(family_id: str) -> str:
    if family_id == TREND_FAMILY_ID:
        return (
            "EVIDENCE_EXPANSION: A1B+regime+volatility+structure; "
            "fee buffer outside STRONG_BULL; 12h router cooldown pending"
        )
    if family_id == COMPRESSION_FAMILY_ID:
        return (
            "FULL_REMEDIATION_STACK: A1B+regime+volatility+structure+fee buffer+24h signal cooldown"
        )
    raise KeyError(f"unknown family: {family_id}")


def _rejection_reason(
    row: Mapping[str, object],
    *,
    family_id: str,
) -> str:
    if not bool(row["a1c_identity_ready"]):
        return "A1C_CORPORATE_ACTION_EXCLUSION"
    if not bool(row["a1b_eligible"]):
        return f"A1B::{row['a1b_reason']}"
    if not bool(row["regime_ready"]):
        return "REGIME_GATE"
    if not bool(row["volatility_ready"]):
        return "VOLATILITY_GATE"
    if not bool(row["structure_ready"]):
        return "STRUCTURAL_CONFIRMATION"
    requires_fee = family_id == COMPRESSION_FAMILY_ID or (
        family_id == TREND_FAMILY_ID and str(row["market_regime"]) != "STRONG_BULL"
    )
    if requires_fee and not bool(row["fee_buffer_ready"]):
        return "FEE_BUFFER"
    if family_id == COMPRESSION_FAMILY_ID and not bool(row["cooldown_ready"]):
        return "ENGINE_COOLDOWN_24H"
    return "SELECTED_PRE_ROUTER"


def classify_enriched_candidates(
    enriched: pd.DataFrame,
    *,
    eligibility: pd.DataFrame,
    excluded_pairs: frozenset[str],
    family_id: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if family_id not in FAMILY_IDS:
        raise A2GeneratorError(f"unsupported family: {family_id}")
    if enriched.empty:
        return _empty_frame(CANDIDATE_FIELDS), _empty_frame(AUDIT_FIELDS)

    required = {
        "family_id",
        "symbol",
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "entry_price",
        "atr14_at_signal",
        "signal_low",
        "signal_high",
        "market_regime",
        "volatility_regime",
        "4h_context_close",
        "1d_context_close",
        "1w_context_close",
    }
    missing = sorted(required.difference(enriched.columns))
    if missing:
        raise A2GeneratorError(f"enriched candidate columns missing: {missing}")

    working = enriched.copy()
    if set(working["family_id"].astype(str).unique()) != {family_id}:
        raise A2GeneratorError("candidate family does not match requested family")

    for column in (
        "signal_close",
        "entry_open_time",
        "entry_bar_close",
        "4h_context_close",
        "1d_context_close",
        "1w_context_close",
    ):
        working[column] = _utc_series(working[column], column=column)

    cutoff = pd.Timestamp(SEALED_CUTOFF)
    if bool((working["signal_close"] >= cutoff).any()):
        raise A2GeneratorError("signal at or after sealed cutoff")
    if bool((working["entry_bar_close"] > cutoff).any()):
        raise A2GeneratorError("entry bar after sealed cutoff")
    for context in (
        "4h_context_close",
        "1d_context_close",
        "1w_context_close",
    ):
        if bool((working[context] > working["signal_close"]).any()):
            raise A2GeneratorError(f"future context detected in {context}")

    working["pair"] = working["symbol"].map(symbol_to_pair)
    engine_id = ENGINE_BY_FAMILY[family_id]
    working["candidate_id"] = (
        "RD18A2::"
        + engine_id
        + "::"
        + working["pair"].astype(str)
        + "::"
        + working["signal_close"].map(lambda value: pd.Timestamp(value).isoformat())
    )
    if bool(working["candidate_id"].duplicated().any()):
        raise A2GeneratorError("candidate IDs are not unique")

    decisions = _a1b_decisions(
        working,
        eligibility,
        family_id=family_id,
    )
    for column in decisions.columns:
        working[column] = decisions[column]

    working["a1c_identity_ready"] = ~working["pair"].isin(excluded_pairs)
    working["regime_ready"] = regime_mask(working, family_id).astype(bool)
    working["volatility_ready"] = volatility_mask(
        working,
        family_id,
    ).astype(bool)
    working["structure_ready"] = structural_mask(
        working,
        family_id,
    ).astype(bool)
    working["fee_buffer_ready"] = fee_buffer_mask(
        working,
        family_id,
    ).astype(bool)

    base = (
        working["a1c_identity_ready"].astype(bool)
        & working["a1b_eligible"].astype(bool)
        & working["regime_ready"].astype(bool)
        & working["volatility_ready"].astype(bool)
        & working["structure_ready"].astype(bool)
    )
    if family_id == TREND_FAMILY_ID:
        preselected = base & (
            (working["market_regime"].astype(str) == "STRONG_BULL")
            | working["fee_buffer_ready"].astype(bool)
        )
        working["cooldown_ready"] = True
        selected = preselected
    else:
        preselected = base & working["fee_buffer_ready"].astype(bool)
        cooldown = _compression_cooldown_mask(working, preselected)
        working["cooldown_ready"] = cooldown
        selected = preselected & cooldown

    working["schema_version"] = SCHEMA_VERSION
    working["stage"] = STAGE
    working["architecture_id"] = ARCHITECTURE_ID
    working["source_architecture_id"] = SOURCE_ARCHITECTURE_ID
    working["source_variant_id"] = SOURCE_VARIANT_ID
    working["engine_id"] = engine_id
    working["engine_priority"] = PRIORITY_BY_FAMILY[family_id]
    working["source_rule"] = _source_rule(family_id)
    working["router_status"] = "PENDING_SEALED_REPLAY"
    working["signal_month"] = _month_start(working["signal_close"]).map(
        lambda value: pd.Timestamp(value).isoformat()
    )
    working["selected_pre_router"] = selected.astype(bool)
    working["rejection_reason"] = [
        _rejection_reason(
            cast(Mapping[str, object], row),
            family_id=family_id,
        )
        for row in working.to_dict(orient="records")
    ]

    if bool(
        (
            working["selected_pre_router"] != (working["rejection_reason"] == "SELECTED_PRE_ROUTER")
        ).any()
    ):
        raise A2GeneratorError("selected flag and rejection reason disagree")

    audit = working.loc[:, list(AUDIT_FIELDS)].copy()
    candidates = audit.loc[audit["selected_pre_router"], list(CANDIDATE_FIELDS)].copy()
    forbidden = sorted(FORBIDDEN_OUTCOME_COLUMNS.intersection(candidates.columns))
    if forbidden:
        raise A2GeneratorError(f"outcome columns leaked into A2: {forbidden}")

    return (
        candidates.sort_values(
            ["signal_close", "engine_priority", "candidate_id"],
            kind="stable",
        ).reset_index(drop=True),
        audit.sort_values(
            ["signal_close", "engine_priority", "candidate_id"],
            kind="stable",
        ).reset_index(drop=True),
    )


def _no_feature_rows_result(
    *,
    symbol: str,
    eligibility: pd.DataFrame,
) -> SymbolGenerationResult:
    if "eligible" not in eligibility.columns:
        raise A2GeneratorError(f"{symbol}: A1B eligibility column is missing")
    eligible = _boolean_series(
        eligibility["eligible"],
        column="eligible",
    )
    if bool(eligible.any()):
        eligible_months = eligibility.loc[eligible, "month_start"].astype(str).tolist()
        raise A2GeneratorError(
            f"{symbol}: no causal feature rows remain, but A1B authorizes months: {eligible_months}"
        )

    candidates = _empty_frame(CANDIDATE_FIELDS)
    audit = _empty_frame(AUDIT_FIELDS)
    summary: dict[str, object] = {
        "pair": symbol_to_pair(symbol),
        "symbol": symbol,
        "raw_signal_rows": 0,
        "selected_candidate_rows": 0,
        "trend_raw_rows": 0,
        "trend_selected_rows": 0,
        "compression_raw_rows": 0,
        "compression_selected_rows": 0,
        "first_signal_close": "",
        "last_signal_close": "",
        "candidate_content_sha256": dataframe_content_hash(candidates),
        "audit_content_sha256": dataframe_content_hash(audit),
        "generation_status": "NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP",
        "generation_reason": "NO_ROWS_AFTER_RD16C_CAUSAL_FEATURE_WARMUP",
    }
    return SymbolGenerationResult(
        candidates=candidates,
        audit=audit,
        summary=summary,
    )


def generate_symbol(
    frames: Mapping[str, pd.DataFrame],
    *,
    symbol: str,
    eligibility: pd.DataFrame,
    excluded_pairs: frozenset[str],
) -> SymbolGenerationResult:
    required_timeframes = {"1h", "4h", "1d", "1w"}
    missing = sorted(required_timeframes.difference(frames))
    if missing:
        raise A2GeneratorError(f"{symbol}: missing timeframes: {missing}")

    try:
        feature_frame = build_feature_frame(frames, symbol=symbol)
    except FeatureDataError as error:
        if "no rows remain after feature warm-up." not in str(error):
            raise
        return _no_feature_rows_result(
            symbol=symbol,
            eligibility=eligibility,
        )
    candidate_parts: list[pd.DataFrame] = []
    audit_parts: list[pd.DataFrame] = []

    for family_id in FAMILY_IDS:
        base = build_candidate_frame(
            feature_frame,
            symbol=symbol,
            registration=REGISTRY_BY_ID[family_id],
        )
        if base.empty:
            continue
        base["family_id"] = family_id
        enriched = _attach_context_and_features(
            base,
            feature_frame=feature_frame,
            symbol=symbol,
        )
        candidates, audit = classify_enriched_candidates(
            enriched,
            eligibility=eligibility,
            excluded_pairs=excluded_pairs,
            family_id=family_id,
        )
        candidate_parts.append(candidates)
        audit_parts.append(audit)

    candidates = (
        pd.concat(candidate_parts, ignore_index=True)
        if candidate_parts
        else _empty_frame(CANDIDATE_FIELDS)
    )
    audit = pd.concat(audit_parts, ignore_index=True) if audit_parts else _empty_frame(AUDIT_FIELDS)
    candidates = (
        candidates.loc[:, list(CANDIDATE_FIELDS)]
        .sort_values(
            ["signal_close", "engine_priority", "candidate_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
    audit = (
        audit.loc[:, list(AUDIT_FIELDS)]
        .sort_values(
            ["signal_close", "engine_priority", "candidate_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )

    pair = symbol_to_pair(symbol)
    trend_audit = audit.loc[audit["family_id"] == TREND_FAMILY_ID]
    compression_audit = audit.loc[audit["family_id"] == COMPRESSION_FAMILY_ID]
    trend_candidates = candidates.loc[candidates["family_id"] == TREND_FAMILY_ID]
    compression_candidates = candidates.loc[candidates["family_id"] == COMPRESSION_FAMILY_ID]

    signal_times = (
        _utc_series(
            audit["signal_close"],
            column="signal_close",
        )
        if not audit.empty
        else pd.Series(dtype="datetime64[ns, UTC]")
    )

    summary: dict[str, object] = {
        "pair": pair,
        "symbol": symbol,
        "raw_signal_rows": len(audit),
        "selected_candidate_rows": len(candidates),
        "trend_raw_rows": len(trend_audit),
        "trend_selected_rows": len(trend_candidates),
        "compression_raw_rows": len(compression_audit),
        "compression_selected_rows": len(compression_candidates),
        "first_signal_close": (
            pd.Timestamp(signal_times.min()).isoformat() if not signal_times.empty else ""
        ),
        "last_signal_close": (
            pd.Timestamp(signal_times.max()).isoformat() if not signal_times.empty else ""
        ),
        "candidate_content_sha256": dataframe_content_hash(candidates),
        "audit_content_sha256": dataframe_content_hash(audit),
        "generation_status": "GENERATED",
        "generation_reason": "",
    }
    return SymbolGenerationResult(
        candidates=candidates,
        audit=audit,
        summary=summary,
    )


def deterministic_manifest(
    root: Path,
    relative_paths: Sequence[str],
    *,
    flags: Mapping[str, object],
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for name in sorted(set(relative_paths)):
        path = root / name
        if not path.is_file():
            raise A2GeneratorError(f"manifest file is missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3x-a2-output-manifest-v1",
        "files": files,
        "deterministic_hash": aggregate.hexdigest(),
        **dict(flags),
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


__all__ = [
    "ARCHITECTURE_ID",
    "AUDIT_FIELDS",
    "A2GeneratorError",
    "CANDIDATE_FIELDS",
    "COMPRESSION_ENGINE_ID",
    "COMPRESSION_FAMILY_ID",
    "ENGINE_BY_FAMILY",
    "FAMILY_IDS",
    "FORBIDDEN_OUTCOME_COLUMNS",
    "SCHEMA_VERSION",
    "SOURCE_ARCHITECTURE_ID",
    "SOURCE_VARIANT_ID",
    "STAGE",
    "SUMMARY_FIELDS",
    "SymbolGenerationResult",
    "TREND_ENGINE_ID",
    "TREND_FAMILY_ID",
    "classify_enriched_candidates",
    "deterministic_manifest",
    "generate_symbol",
    "validate_eligibility_ledger",
    "write_json",
]
