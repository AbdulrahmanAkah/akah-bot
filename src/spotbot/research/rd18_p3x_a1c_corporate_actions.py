# mypy: disable-error-code="no-any-return"
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

SCHEMA_VERSION: Final = "rd18-p3x-a1c-corporate-action-build-v1"
REPORT_SCHEMA_VERSION: Final = "rd18-p3x-a1c-runtime-report-v1"
SEALED_CUTOFF: Final = datetime(2025, 1, 1, tzinfo=UTC)

EXPECTED_PAIRS: Final = frozenset({"ETN-USDT", "STRAX-USDT"})
ALLOWED_EVENT_TYPES: Final = frozenset(
    {
        "TOKEN_SWAP",
        "REDENOMINATION",
        "CHAIN_MIGRATION",
        "CONTRACT_MIGRATION",
        "SYMBOL_REASSIGNMENT",
    }
)
EXPECTED_TERMINAL_CLASSIFICATIONS: Final = {
    "ETN-USDT": "DOCUMENTED_CHAIN_MIGRATION_SEGMENTS_NOT_STRATEGY_READY",
    "STRAX-USDT": "DOCUMENTED_TOKEN_SWAP_SEGMENTS_NOT_STRATEGY_READY",
}

EVENT_FIELDS: Final = (
    "pair",
    "symbol",
    "venue",
    "event_id",
    "event_type",
    "official_trading_closed_at",
    "official_trading_reopened_at",
    "expected_missing_intervals",
    "diagnostic_sha256",
    "official_source_count",
    "raw_series_policy",
    "normalization_authorized",
    "strategy_use_authorized",
    "terminal_classification",
)

SEGMENT_FIELDS: Final = (
    "pair",
    "symbol",
    "event_id",
    "segment_id",
    "segment_type",
    "start_inclusive",
    "end_exclusive",
    "raw_rows_authorized",
    "synthetic_rows_authorized",
    "normalization_authorized",
    "strategy_use_authorized",
    "identity_continuity_with_previous",
    "classification",
)

TERMINAL_FIELDS: Final = (
    "pair",
    "symbol",
    "event_id",
    "event_type",
    "checkpoint_state",
    "plan_action",
    "terminal_classification",
    "strategy_use_authorized",
    "candidate_generation_authorized",
    "normalization_authorized",
    "raw_gap_filling_authorized",
    "next_stage",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class A1CError(RuntimeError):
    """Raised when the fail-closed A1C contract is violated."""


@dataclass(frozen=True, slots=True)
class A1CBuildResult:
    events: list[dict[str, object]]
    segments: list[dict[str, object]]
    terminals: list[dict[str, object]]
    report: dict[str, object]


def parse_utc(value: object, *, field: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise A1CError(f"{field} is empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise A1CError(f"{field} is not ISO-8601: {text}") from exc
    if parsed.tzinfo is None:
        raise A1CError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def load_json(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise A1CError(f"expected JSON object: {path}")
    return cast(dict[str, object], raw)


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


def write_csv(
    path: Path,
    rows: list[dict[str, object]],
    fields: tuple[str, ...],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            lineterminator="\n",
            extrasaction="raise",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_manifest(
    output_dir: Path,
    names: tuple[str, ...],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    aggregate = hashlib.sha256()
    for name in sorted(names):
        path = output_dir / name
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        rows.append(
            {
                "path": name,
                "bytes": len(payload),
                "sha256": digest,
            }
        )
        aggregate.update(name.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(digest.encode("ascii"))
        aggregate.update(b"\n")
    return {
        "schema_version": "rd18-p3x-a1c-output-manifest-v1",
        "deterministic_hash": aggregate.hexdigest(),
        "files": rows,
        "network_requests": 0,
        "raw_market_data_written": False,
        "synthetic_candles_written": False,
        "normalization_executed": False,
        "strategy_candidate_generation_executed": False,
        "strategy_replay_executed": False,
        "return_calculation_executed": False,
    }


def _require_dict(
    value: object,
    *,
    field: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise A1CError(f"{field} must be an object")
    return cast(dict[str, object], value)


def _require_list(
    value: object,
    *,
    field: str,
) -> list[object]:
    if not isinstance(value, list):
        raise A1CError(f"{field} must be a list")
    return cast(list[object], value)


def _require_false(
    value: object,
    *,
    field: str,
) -> None:
    if value is not False:
        raise A1CError(f"{field} must be false")


def _validate_protocol(protocol: dict[str, object]) -> None:
    if protocol.get("schema_version") != "rd18-p3x-a1c-causal-corporate-action-policy-v1":
        raise A1CError("A1C protocol schema mismatch")
    authorizations = _require_dict(
        protocol.get("authorizations"),
        field="protocol.authorizations",
    )
    for field in (
        "broad_candidate_generation",
        "normalization_execution",
        "production",
        "return_calculation",
        "strategy_replay",
    ):
        _require_false(
            authorizations.get(field),
            field=f"protocol.authorizations.{field}",
        )
    rules = _require_dict(
        protocol.get("decision_rules"),
        field="protocol.decision_rules",
    )
    raw_policy = _require_dict(
        rules.get("raw_data_policy"),
        field="protocol.decision_rules.raw_data_policy",
    )
    expected_false = (
        "fill_suspended_hours",
        "stitch_pre_and_post_segments",
        "write_synthetic_candles",
    )
    for field in expected_false:
        _require_false(
            raw_policy.get(field),
            field=f"protocol.raw_data_policy.{field}",
        )


def _validated_sources(value: object, *, pair: str) -> list[str]:
    raw_sources = _require_list(
        value,
        field=f"{pair}.official_sources",
    )
    sources = [str(item).strip() for item in raw_sources]
    if len(sources) < 2:
        raise A1CError(f"{pair} requires at least two official sources")
    if any(not source.startswith("https://") for source in sources):
        raise A1CError(f"{pair} official sources must use HTTPS")
    if len(set(sources)) != len(sources):
        raise A1CError(f"{pair} official sources contain duplicates")
    return sources


def _event_integrity(
    pair: str,
    event: dict[str, object],
) -> tuple[int, str]:
    report = _require_dict(
        event.get("expected_integrity_report"),
        field=f"{pair}.expected_integrity_report",
    )
    counts: dict[str, int] = {}
    for field in ("duplicates", "invalid", "missing"):
        value = report.get(field)
        if isinstance(value, bool):
            raise A1CError(f"{pair}.{field} cannot be boolean")
        try:
            counts[field] = int(str(value))
        except (TypeError, ValueError) as exc:
            raise A1CError(f"{pair}.{field} must be integer-like") from exc
        if counts[field] < 0:
            raise A1CError(f"{pair}.{field} cannot be negative")
    if counts["duplicates"] != 0 or counts["invalid"] != 0:
        raise A1CError(
            f"{pair} registered corporate-action integrity must have "
            "zero duplicates and zero invalid rows"
        )
    if counts["missing"] <= 0:
        raise A1CError(f"{pair} must register a positive missing interval count")

    evidence = _require_dict(
        event.get("diagnostic_evidence"),
        field=f"{pair}.diagnostic_evidence",
    )
    digest = str(evidence.get("sha256", ""))
    if _SHA256.fullmatch(digest) is None:
        raise A1CError(f"{pair} diagnostic SHA-256 is invalid")
    _require_false(
        evidence.get("raw_market_data_written"),
        field=f"{pair}.diagnostic_evidence.raw_market_data_written",
    )
    return counts["missing"], digest


def _validate_event(
    pair: str,
    event: dict[str, object],
    *,
    required_since_open: str,
    plan_action: str,
    checkpoint_state: str,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    dict[str, object],
]:
    if pair not in EXPECTED_PAIRS:
        raise A1CError(f"unexpected registered pair: {pair}")
    if plan_action != "CORPORATE_ACTION_POLICY_REQUIRED":
        raise A1CError(f"{pair} A1 plan action must be CORPORATE_ACTION_POLICY_REQUIRED")
    if checkpoint_state != "CORPORATE_ACTION_POLICY_REQUIRED":
        raise A1CError(f"{pair} checkpoint state must be CORPORATE_ACTION_POLICY_REQUIRED")

    symbol = str(event.get("symbol", ""))
    expected_symbol = pair.replace("-", "/", 1)
    if symbol != expected_symbol:
        raise A1CError(f"{pair} symbol mismatch: {symbol} != {expected_symbol}")
    venue = str(event.get("venue", ""))
    if venue != "kucoin":
        raise A1CError(f"{pair} venue must be kucoin")

    event_id = str(event.get("event_id", "")).strip()
    if not event_id:
        raise A1CError(f"{pair} event_id is empty")
    event_type = str(event.get("event_type", ""))
    if event_type not in ALLOWED_EVENT_TYPES:
        raise A1CError(f"{pair} event_type is unsupported: {event_type}")

    closed = parse_utc(
        event.get("official_trading_closed_at"),
        field=f"{pair}.official_trading_closed_at",
    )
    reopened = parse_utc(
        event.get("official_trading_reopened_at"),
        field=f"{pair}.official_trading_reopened_at",
    )
    required_start = parse_utc(
        required_since_open,
        field=f"{pair}.required_since_open",
    )
    if not required_start < closed < reopened <= SEALED_CUTOFF:
        raise A1CError(f"{pair} event boundaries violate the sealed historical window")

    before = parse_utc(
        event.get("observed_last_close_before_gap"),
        field=f"{pair}.observed_last_close_before_gap",
    )
    raw_after = event.get("observed_first_open_after_gap")
    after_field = "observed_first_open_after_gap"
    if raw_after is None:
        raw_after = event.get("observed_first_close_after_gap")
        after_field = "observed_first_close_after_gap"
    after = parse_utc(raw_after, field=f"{pair}.{after_field}")
    if not closed <= before < reopened <= after:
        raise A1CError(f"{pair} observed boundaries do not surround the event interval")

    sources = _validated_sources(event.get("official_sources"), pair=pair)
    missing, diagnostic_sha = _event_integrity(pair, event)

    if event.get("raw_series_policy") != "PRESERVE_GAP_AND_BLOCK_CONCATENATION":
        raise A1CError(f"{pair} raw series policy mismatch")
    _require_false(
        event.get("normalization_authorized"),
        field=f"{pair}.normalization_authorized",
    )
    _require_false(
        event.get("strategy_use_authorized"),
        field=f"{pair}.strategy_use_authorized",
    )

    terminal_classification = EXPECTED_TERMINAL_CLASSIFICATIONS[pair]
    event_row: dict[str, object] = {
        "pair": pair,
        "symbol": symbol,
        "venue": venue,
        "event_id": event_id,
        "event_type": event_type,
        "official_trading_closed_at": iso(closed),
        "official_trading_reopened_at": iso(reopened),
        "expected_missing_intervals": missing,
        "diagnostic_sha256": diagnostic_sha,
        "official_source_count": len(sources),
        "raw_series_policy": "PRESERVE_GAP_AND_BLOCK_CONCATENATION",
        "normalization_authorized": False,
        "strategy_use_authorized": False,
        "terminal_classification": terminal_classification,
    }

    segment_common: dict[str, object] = {
        "pair": pair,
        "symbol": symbol,
        "event_id": event_id,
        "synthetic_rows_authorized": False,
        "normalization_authorized": False,
        "strategy_use_authorized": False,
    }
    segments = [
        {
            **segment_common,
            "segment_id": f"{event_id}:PRE_EVENT",
            "segment_type": "PRE_EVENT_IDENTITY",
            "start_inclusive": iso(required_start),
            "end_exclusive": iso(closed),
            "raw_rows_authorized": True,
            "identity_continuity_with_previous": False,
            "classification": "PRESERVED_DISTINCT_NOT_STRATEGY_READY",
        },
        {
            **segment_common,
            "segment_id": f"{event_id}:EVENT_GAP",
            "segment_type": "SUSPENSION_OR_MIGRATION_GAP",
            "start_inclusive": iso(closed),
            "end_exclusive": iso(reopened),
            "raw_rows_authorized": False,
            "identity_continuity_with_previous": False,
            "classification": "PRESERVE_EMPTY_INTERVAL_NO_SYNTHETIC_ROWS",
        },
        {
            **segment_common,
            "segment_id": f"{event_id}:POST_EVENT",
            "segment_type": "POST_EVENT_IDENTITY",
            "start_inclusive": iso(reopened),
            "end_exclusive": iso(SEALED_CUTOFF),
            "raw_rows_authorized": True,
            "identity_continuity_with_previous": False,
            "classification": "PRESERVED_DISTINCT_NOT_STRATEGY_READY",
        },
    ]

    terminal = {
        "pair": pair,
        "symbol": symbol,
        "event_id": event_id,
        "event_type": event_type,
        "checkpoint_state": checkpoint_state,
        "plan_action": plan_action,
        "terminal_classification": terminal_classification,
        "strategy_use_authorized": False,
        "candidate_generation_authorized": False,
        "normalization_authorized": False,
        "raw_gap_filling_authorized": False,
        "next_stage": "RD18_P3X_A2_C2_GENERATOR_BUILD_WITH_A1B_GATE_AND_A1C_EXCLUSIONS",
    }
    return event_row, segments, terminal


def build_a1c(
    *,
    registry: dict[str, object],
    protocol: dict[str, object],
    plan_rows: list[dict[str, str]],
    checkpoint: dict[str, object],
) -> A1CBuildResult:
    _validate_protocol(protocol)

    if registry.get("schema_version") != "rd18-p3x-a1-corporate-action-registry-v1":
        raise A1CError("corporate-action registry schema mismatch")
    default_policy = _require_dict(
        registry.get("default_policy"),
        field="registry.default_policy",
    )
    for field in (
        "normalization_authorized",
        "raw_gap_filling_authorized",
        "strategy_use_authorized",
    ):
        _require_false(
            default_policy.get(field),
            field=f"registry.default_policy.{field}",
        )

    events_raw = _require_dict(
        registry.get("events"),
        field="registry.events",
    )
    if set(events_raw) != EXPECTED_PAIRS:
        raise A1CError(f"registered pair set mismatch: {sorted(events_raw)}")

    plan_by_pair = {str(row.get("pair", "")): row for row in plan_rows}
    if len(plan_by_pair) != len(plan_rows):
        raise A1CError("A1 plan contains duplicate pairs")
    checkpoint_pairs = _require_dict(
        checkpoint.get("pairs"),
        field="checkpoint.pairs",
    )

    event_rows: list[dict[str, object]] = []
    segment_rows: list[dict[str, object]] = []
    terminal_rows: list[dict[str, object]] = []

    for pair in sorted(EXPECTED_PAIRS):
        plan_row = plan_by_pair.get(pair)
        if plan_row is None:
            raise A1CError(f"{pair} is missing from the A1 plan")
        checkpoint_row = checkpoint_pairs.get(pair)
        if not isinstance(checkpoint_row, dict):
            raise A1CError(f"{pair} is missing from the A1 checkpoint")

        event = _require_dict(
            events_raw.get(pair),
            field=f"registry.events.{pair}",
        )
        event_row, segments, terminal = _validate_event(
            pair,
            event,
            required_since_open=str(
                plan_row.get("required_since_open", "")
                or plan_row.get("required_since_open_utc", "")
                or plan_row.get("required_since_open_time", "")
            ),
            plan_action=str(plan_row.get("action", "")),
            checkpoint_state=str(checkpoint_row.get("state", "")),
        )
        event_rows.append(event_row)
        segment_rows.extend(segments)
        terminal_rows.append(terminal)

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "stage": "RD18_P3X_A1C_CAUSAL_CORPORATE_ACTION_POLICY",
        "passed": True,
        "events": len(event_rows),
        "segments": len(segment_rows),
        "terminal_classifications": len(terminal_rows),
        "registered_pairs": sorted(EXPECTED_PAIRS),
        "strategy_ready_events": 0,
        "sealed_cutoff": iso(SEALED_CUTOFF),
        "authorizations": {
            "broad_candidate_generation": False,
            "normalization_execution": False,
            "production": False,
            "raw_gap_filling": False,
            "return_calculation": False,
            "strategy_replay": False,
            "synthetic_candle_writes": False,
        },
        "checks": {
            "event_registry_exact_pair_set": True,
            "checkpoint_states_terminal": True,
            "plan_actions_terminal": True,
            "pre_post_identity_distinct": True,
            "event_gaps_preserved": True,
            "normalization_prohibited": True,
            "strategy_use_prohibited": True,
            "post_2024_access_prohibited": True,
        },
        "decision": "RD18_P3X_A1C_COMPLETE_WITH_EXPLICIT_EXCLUSIONS",
        "next_stage": "RD18_P3X_A2_C2_GENERATOR_BUILD_WITH_A1B_GATE_AND_A1C_EXCLUSIONS",
    }
    return A1CBuildResult(
        events=event_rows,
        segments=segment_rows,
        terminals=terminal_rows,
        report=report,
    )


__all__ = [
    "A1CBuildResult",
    "A1CError",
    "EVENT_FIELDS",
    "REPORT_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "SEALED_CUTOFF",
    "SEGMENT_FIELDS",
    "TERMINAL_FIELDS",
    "build_a1c",
    "deterministic_manifest",
    "load_json",
    "parse_utc",
    "sha256_path",
    "write_csv",
    "write_json",
]
