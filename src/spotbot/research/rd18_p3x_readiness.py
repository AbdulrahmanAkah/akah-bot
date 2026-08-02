"""Offline readiness and acquisition planning for RD18-P3X.

P3X does not calculate strategy returns.  It proves whether the repository can
regenerate the frozen COMPOSITE_ALPHA_V3 candidate stream for every corrected
C2 asset and, by containment, for the D2 and E2 research scenarios.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final

STAGE: Final = "RD18_P3X_FULL_UNIVERSE_CANDIDATE_PIPELINE_AND_DATA_READINESS"
EXPECTED_C2_PAIRS: Final = 364
RESEARCH_START: Final = "2019-01-01T00:00:00+00:00"
SEALED_CUTOFF: Final = "2025-01-01T00:00:00+00:00"
REQUIRED_TIMEFRAME: Final = "1h"

DECISION_READY: Final = "RD18_P3X_FULL_UNIVERSE_INPUTS_READY_FOR_DRY_RUN"
DECISION_DATA_REQUIRED: Final = "RD18_P3X_FULL_C2_HOURLY_DATA_ACQUISITION_REQUIRED"
DECISION_GENERATOR_REQUIRED: Final = "RD18_P3X_RAW_CANDIDATE_GENERATOR_EXTRACTION_REQUIRED"
DECISION_BOTH_REQUIRED: Final = "RD18_P3X_DATA_AND_GENERATOR_BUILD_REQUIRED"
DECISION_INPUT_FAILED: Final = "RD18_P3X_INPUT_RECONCILIATION_FAILED"

NEXT_READY: Final = "RD18_P3X_DRY_RUN_THREE_UNIVERSE_CANDIDATE_ROUTING"
NEXT_DATA: Final = "RD18_P3X_A1_FULL_C2_HOURLY_DATA_ACQUISITION"
NEXT_GENERATOR: Final = "RD18_P3X_A1_RAW_CANDIDATE_GENERATOR_EXTRACTION"
NEXT_BOTH: Final = "RD18_P3X_A1_FULL_C2_HOURLY_DATA_AND_GENERATOR_BUILD"
NEXT_INPUT: Final = "RD18_BLOCKED_PENDING_P3R_OR_P1R2_REPAIR"

EXPECTED_INPUT_HASHES: Final = {
    "P1R2": "0cc3d273e55aa1d1425de97b47fb5cad7610c6c2c7da6aec348850a635947048",
    "P2U2": "f61ed396977e8b85faaad5e670e193d216a5d6e1c87bee8406301cbe0666b227",
    "P3R": "df4644d52cbcf60b878d5b6f979846cc756139b329a23c58ed0f068dfd50e4cb",
}
INPUT_MANIFEST_PATHS: Final = {
    "P1R2": "data/research/rd18_p1r2/output-manifest.json",
    "P2U2": "data/research/rd18_p2u2/output-manifest.json",
    "P3R": "data/research/rd18_p3r/output-manifest.json",
}

ALLOWED_CANDIDATE_DECISIONS: Final = frozenset(
    {
        "CANDIDATE",
        "NO_SIGNAL",
        "FEATURE_WARMUP_NOT_READY",
        "DATA_UNAVAILABLE_BLOCK",
    }
)

ACQUISITION_FIELDS: Final = (
    "pair",
    "symbol",
    "required_first_close",
    "required_last_close",
    "source_present",
    "source_logical_path",
    "source_file_present",
    "source_hash_match",
    "source_first_close",
    "source_last_close",
    "committed_readiness_status",
    "coverage_status",
    "blocking_reasons",
)

SOURCE_AUDIT_FIELDS: Final = (
    "symbol",
    "logical_path",
    "file_present",
    "manifest_sha256",
    "actual_sha256",
    "hash_match",
    "manifest_rows",
    "first_close",
    "last_close",
    "committed_readiness_status",
    "committed_missing_intervals",
    "committed_invalid_rows",
    "committed_future_context_violations",
    "status",
)


class P3XReadinessError(ValueError):
    """Raised when frozen P3X inputs are malformed or contradictory."""


@dataclass(frozen=True, slots=True)
class PairRequirement:
    pair: str
    applicable_start: str
    applicable_end: str
    first_valid_open: str
    last_valid_open: str

    @property
    def symbol(self) -> str:
        return pair_to_symbol(self.pair)

    @property
    def required_first_close(self) -> str:
        start = max(parse_timestamp(self.first_valid_open), parse_timestamp(RESEARCH_START))
        return iso(start + timedelta(hours=1))

    @property
    def required_last_close(self) -> str:
        return SEALED_CUTOFF


@dataclass(frozen=True, slots=True)
class HourlySource:
    symbol: str
    logical_path: str
    rows: int
    first_close: str
    last_close: str
    sha256: str
    acquisition_status: str


@dataclass(frozen=True, slots=True)
class CandidateCoverage:
    expected_rows: int
    observed_rows: int
    duplicate_rows: int
    missing_rows: int
    invalid_decisions: int

    @property
    def complete(self) -> bool:
        return (
            self.expected_rows == self.observed_rows
            and self.duplicate_rows == 0
            and self.missing_rows == 0
            and self.invalid_decisions == 0
        )

    @property
    def coverage_rate(self) -> float:
        return self.observed_rows / self.expected_rows if self.expected_rows else 1.0


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def parse_timestamp(value: object) -> datetime:
    text = str(value).strip()
    if not text:
        raise P3XReadinessError("timestamp cannot be empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise P3XReadinessError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def pair_to_symbol(pair: str) -> str:
    normalized = str(pair).strip().upper()
    if normalized.endswith("-USDT"):
        return normalized[:-5] + "/USDT"
    if normalized.endswith("/USDT"):
        return normalized
    raise P3XReadinessError(f"not a USDT pair: {pair!r}")


def symbol_to_pair(symbol: str) -> str:
    normalized = str(symbol).strip().upper()
    if normalized.endswith("/USDT"):
        return normalized[:-5] + "-USDT"
    if normalized.endswith("-USDT"):
        return normalized
    raise P3XReadinessError(f"not a USDT symbol: {symbol!r}")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise P3XReadinessError(f"expected JSON object: {path}")
    return value



def reconcile_input_manifests(repo_root: Path) -> dict[str, Any]:
    rows: dict[str, dict[str, object]] = {}
    for stage, relative in INPUT_MANIFEST_PATHS.items():
        path = repo_root / relative
        exists = path.is_file()
        actual = ""
        schema = ""
        if exists:
            value = load_json(path)
            actual = str(value.get("deterministic_hash", ""))
            schema = str(value.get("schema_version", ""))
        expected = EXPECTED_INPUT_HASHES[stage]
        rows[stage] = {
            "path": relative,
            "exists": exists,
            "schema_version": schema,
            "expected_deterministic_hash": expected,
            "actual_deterministic_hash": actual,
            "match": exists and actual == expected,
        }
    return {
        "inputs": rows,
        "all_inputs_match": all(bool(row["match"]) for row in rows.values()),
    }

def load_c2_requirements(path: Path) -> list[PairRequirement]:
    rows = load_csv(path)
    required_columns = {
        "pair",
        "product_eligible",
        "applicable_start",
        "applicable_end",
        "first_valid_open",
        "last_valid_open",
    }
    if not rows:
        raise P3XReadinessError("C2 coverage audit is empty")
    missing = required_columns.difference(rows[0])
    if missing:
        raise P3XReadinessError(f"C2 coverage columns missing: {sorted(missing)}")
    requirements: list[PairRequirement] = []
    for row in rows:
        if not parse_bool(row["product_eligible"]):
            continue
        requirement = PairRequirement(
            pair=symbol_to_pair(row["pair"]),
            applicable_start=iso(parse_timestamp(row["applicable_start"])),
            applicable_end=iso(parse_timestamp(row["applicable_end"])),
            first_valid_open=iso(parse_timestamp(row["first_valid_open"])),
            last_valid_open=iso(parse_timestamp(row["last_valid_open"])),
        )
        if parse_timestamp(requirement.last_valid_open) >= parse_timestamp(SEALED_CUTOFF):
            raise P3XReadinessError(f"post-2024 C2 observation: {requirement.pair}")
        requirements.append(requirement)
    requirements.sort(key=lambda item: item.pair)
    pairs = [item.pair for item in requirements]
    if len(pairs) != len(set(pairs)):
        raise P3XReadinessError("duplicate C2 pair requirement")
    return requirements


def load_hourly_sources(path: Path) -> dict[str, HourlySource]:
    manifest = load_json(path)
    if manifest.get("exchange") != "kucoin" or manifest.get("timeframe") != REQUIRED_TIMEFRAME:
        raise P3XReadinessError("RD16B source manifest is not KuCoin 1h")
    if manifest.get("sealed_cutoff") != SEALED_CUTOFF:
        raise P3XReadinessError("RD16B sealed cutoff does not match P3X")
    raw_assets = manifest.get("assets")
    if not isinstance(raw_assets, dict):
        raise P3XReadinessError("RD16B source manifest has no assets object")
    sources: dict[str, HourlySource] = {}
    for raw_symbol, raw in raw_assets.items():
        if not isinstance(raw, dict):
            raise P3XReadinessError(f"invalid source row for {raw_symbol}")
        symbol = pair_to_symbol(str(raw_symbol))
        source = HourlySource(
            symbol=symbol,
            logical_path=str(raw["logical_path"]),
            rows=int(raw["rows"]),
            first_close=iso(parse_timestamp(raw["first_close"])),
            last_close=iso(parse_timestamp(raw["last_close"])),
            sha256=str(raw["sha256"]),
            acquisition_status=str(raw.get("acquisition_status", "")),
        )
        if source.symbol in sources:
            raise P3XReadinessError(f"duplicate source symbol: {source.symbol}")
        sources[source.symbol] = source
    return sources


def load_committed_readiness(path: Path) -> dict[str, dict[str, str]]:
    return {pair_to_symbol(row["symbol"]): row for row in load_csv(path)}


def feature_lookback_audit(feature_source: Path) -> dict[str, Any]:
    text = feature_source.read_text(encoding="utf-8")
    required_tokens = {
        "signal_ema50": "span=50",
        "daily_ema200_minimum": "min_periods=120",
        "weekly_ema40_minimum": "min_periods=30",
        "causal_merge": 'direction="backward"',
        "future_context_guard": "future context detected",
    }
    token_status = {name: token in text for name, token in required_tokens.items()}
    # 30 completed weekly observations dominate the 120-day daily and 50-bar intraday minima.
    lookbacks = {
        "signal_hours": 50,
        "four_hour_hours": 50 * 4,
        "daily_hours": 120 * 24,
        "weekly_hours": 30 * 7 * 24,
    }
    return {
        "source": str(feature_source),
        "token_status": token_status,
        "all_frozen_tokens_present": all(token_status.values()),
        "minimum_feature_warmup_hours": max(lookbacks.values()),
        "minimum_feature_warmup_days": max(lookbacks.values()) / 24,
        "lookbacks": lookbacks,
        "interpretation": (
            "Warm-up unavailability must be emitted explicitly; "
            "it cannot be converted to NO_SIGNAL."
        ),
    }


def generator_readiness_audit(architecture_source: Path, feature_source: Path) -> dict[str, Any]:
    architecture = architecture_source.read_text(encoding="utf-8")
    features = feature_source.read_text(encoding="utf-8")
    ledger_registration = "def prepare_v3_ledgers" in architecture
    raw_feature_import = "build_feature_frame" in architecture
    raw_ohlcv_argument = bool(
        re.search(r"def\s+\w+\([^)]*(ohlcv|frames|candles)", architecture, re.I)
    )
    feature_builder_present = "def build_feature_frame" in features
    raw_capable = (
        ledger_registration
        and raw_feature_import
        and raw_ohlcv_argument
        and feature_builder_present
    )
    return {
        "architecture_source": str(architecture_source),
        "feature_source": str(feature_source),
        "ledger_registration_present": ledger_registration,
        "raw_feature_import_present": raw_feature_import,
        "raw_ohlcv_entrypoint_present": raw_ohlcv_argument,
        "feature_builder_present": feature_builder_present,
        "raw_candidate_regeneration_capable": raw_capable,
        "classification": (
            "RAW_OHLCV_CANDIDATE_GENERATOR_AVAILABLE"
            if raw_capable
            else "LEDGER_REGISTRATION_ONLY_GENERATOR_EXTRACTION_REQUIRED"
        ),
        "required_remediation": (
            []
            if raw_capable
            else [
                "Extract the retained Trend and Compression engines into a deterministic "
                "raw-OHLCV entrypoint.",
                "Prove exact six-symbol candidate/no-signal parity before evaluating "
                "any new asset.",
                "Freeze source hashes and reject outcome-dependent changes.",
            ]
        ),
    }


def audit_sources(
    repo_root: Path,
    sources: Mapping[str, HourlySource],
    committed_readiness: Mapping[str, Mapping[str, str]],
    *,
    verify_hashes: bool,
) -> list[dict[str, object]]:
    root = repo_root / "data" / "raw" / "rd16b"
    rows: list[dict[str, object]] = []
    for symbol in sorted(sources):
        source = sources[symbol]
        file_path = root / source.logical_path
        file_present = file_path.is_file()
        actual_hash = sha256_path(file_path) if file_present and verify_hashes else ""
        hash_match = actual_hash == source.sha256 if actual_hash else False
        readiness = dict(committed_readiness.get(symbol, {}))
        committed_status = readiness.get("status", "MISSING_READINESS_ROW")
        status = "SOURCE_READY"
        reasons: list[str] = []
        if not file_present:
            status = "SOURCE_FILE_MISSING"
            reasons.append("file_missing")
        elif verify_hashes and not hash_match:
            status = "SOURCE_HASH_MISMATCH"
            reasons.append("hash_mismatch")
        if committed_status != "PASS":
            status = "COMMITTED_READINESS_NOT_PASS"
            reasons.append("committed_readiness_not_pass")
        rows.append(
            {
                "symbol": symbol,
                "logical_path": source.logical_path,
                "file_present": file_present,
                "manifest_sha256": source.sha256,
                "actual_sha256": actual_hash,
                "hash_match": hash_match,
                "manifest_rows": source.rows,
                "first_close": source.first_close,
                "last_close": source.last_close,
                "committed_readiness_status": committed_status,
                "committed_missing_intervals": readiness.get("missing_intervals", ""),
                "committed_invalid_rows": readiness.get("invalid_rows", ""),
                "committed_future_context_violations": readiness.get(
                    "future_context_violations", ""
                ),
                "status": status if not reasons else status,
            }
        )
    return rows


def acquisition_plan(
    requirements: Sequence[PairRequirement],
    sources: Mapping[str, HourlySource],
    source_audit: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    audit_by_symbol = {str(row["symbol"]): row for row in source_audit}
    rows: list[dict[str, object]] = []
    cutoff = parse_timestamp(SEALED_CUTOFF)
    for requirement in requirements:
        symbol = requirement.symbol
        source = sources.get(symbol)
        audit = audit_by_symbol.get(symbol, {})
        reasons: list[str] = []
        status = "READY"
        if source is None:
            status = "SOURCE_MANIFEST_ABSENT"
            reasons.append("no_1h_source_manifest")
        else:
            if not bool(audit.get("file_present", False)):
                status = "SOURCE_FILE_ABSENT"
                reasons.append("source_file_missing")
            if not bool(audit.get("source_hash_match", audit.get("hash_match", False))):
                status = "SOURCE_HASH_NOT_VERIFIED_OR_MISMATCH"
                reasons.append("source_hash_not_verified_or_mismatch")
            if audit.get("committed_readiness_status") != "PASS":
                status = "SOURCE_READINESS_NOT_PASS"
                reasons.append("committed_readiness_not_pass")
            if parse_timestamp(source.first_close) > parse_timestamp(
                requirement.required_first_close
            ):
                status = "SOURCE_WINDOW_START_LATE"
                reasons.append("hourly_history_starts_after_first_valid_daily_open")
            if parse_timestamp(source.last_close) < cutoff:
                status = "SOURCE_WINDOW_END_EARLY"
                reasons.append("hourly_history_does_not_reach_sealed_cutoff")
        rows.append(
            {
                "pair": requirement.pair,
                "symbol": symbol,
                "required_first_close": requirement.required_first_close,
                "required_last_close": requirement.required_last_close,
                "source_present": source is not None,
                "source_logical_path": source.logical_path if source else "",
                "source_file_present": bool(audit.get("file_present", False)),
                "source_hash_match": bool(audit.get("hash_match", False)),
                "source_first_close": source.first_close if source else "",
                "source_last_close": source.last_close if source else "",
                "committed_readiness_status": audit.get("committed_readiness_status", ""),
                "coverage_status": status,
                "blocking_reasons": ";".join(reasons),
            }
        )
    return rows


def candidate_coverage_audit(
    expected_memberships: Iterable[tuple[str, str]],
    decisions: Iterable[Mapping[str, object]],
) -> CandidateCoverage:
    expected = {(str(week), pair_to_symbol(symbol)) for week, symbol in expected_memberships}
    observed_keys: list[tuple[str, str]] = []
    invalid = 0
    for row in decisions:
        key = (str(row.get("decision_timestamp", "")), pair_to_symbol(str(row.get("symbol", ""))))
        observed_keys.append(key)
        if str(row.get("candidate_decision", "")) not in ALLOWED_CANDIDATE_DECISIONS:
            invalid += 1
    observed = set(observed_keys)
    return CandidateCoverage(
        expected_rows=len(expected),
        observed_rows=len(observed & expected),
        duplicate_rows=len(observed_keys) - len(observed),
        missing_rows=len(expected - observed),
        invalid_decisions=invalid,
    )


def classify_decision(
    *,
    c2_count: int,
    ready_source_pairs: int,
    generator_ready: bool,
    feature_tokens_ready: bool,
) -> tuple[str, str]:
    if c2_count != EXPECTED_C2_PAIRS or not feature_tokens_ready:
        return DECISION_INPUT_FAILED, NEXT_INPUT
    data_ready = ready_source_pairs == c2_count
    if data_ready and generator_ready:
        return DECISION_READY, NEXT_READY
    if not data_ready and not generator_ready:
        return DECISION_BOTH_REQUIRED, NEXT_BOTH
    if not data_ready:
        return DECISION_DATA_REQUIRED, NEXT_DATA
    return DECISION_GENERATOR_REQUIRED, NEXT_GENERATOR


def summarize(
    requirements: Sequence[PairRequirement],
    sources: Mapping[str, HourlySource],
    plan: Sequence[Mapping[str, object]],
    generator: Mapping[str, object],
    lookback: Mapping[str, object],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for row in plan:
        key = str(row["coverage_status"])
        status_counts[key] = status_counts.get(key, 0) + 1
    ready = status_counts.get("READY", 0)
    decision, next_stage = classify_decision(
        c2_count=len(requirements),
        ready_source_pairs=ready,
        generator_ready=bool(generator["raw_candidate_regeneration_capable"]),
        feature_tokens_ready=bool(lookback["all_frozen_tokens_present"]),
    )
    source_scope = {item.symbol for item in requirements}
    manifest_scope = set(sources)
    return {
        "schema_version": "rd18-p3x-readiness-report-v1",
        "stage": STAGE,
        "decision": decision,
        "next_stage": next_stage,
        "scope": {
            "c2_required_pairs": len(requirements),
            "hourly_manifest_pairs": len(sources),
            "hourly_manifest_pairs_inside_c2": len(source_scope & manifest_scope),
            "manifest_pair_coverage_fraction": (
                len(source_scope & manifest_scope) / len(requirements) if requirements else 0.0
            ),
            "ready_pair_count": ready,
            "ready_pair_fraction": ready / len(requirements) if requirements else 0.0,
            "coverage_status_counts": dict(sorted(status_counts.items())),
        },
        "generator": dict(generator),
        "feature_lookback": dict(lookback),
        "authorizations": {
            "full_c2_hourly_data_acquisition_authorized": decision
            in {DECISION_DATA_REQUIRED, DECISION_BOTH_REQUIRED},
            "raw_candidate_generator_extraction_authorized": decision
            in {DECISION_GENERATOR_REQUIRED, DECISION_BOTH_REQUIRED},
            "three_universe_candidate_dry_run_authorized": decision == DECISION_READY,
            "strategy_replay_authorized": False,
            "return_calculation_authorized": False,
            "candidate_generation_for_performance_authorized": False,
            "production_authorized": False,
        },
        "constraints": {
            "offline": True,
            "spot_only": True,
            "long_only": True,
            "post_2024_access": False,
            "returns_calculated": False,
            "trades_generated": False,
            "optimization_performed": False,
            "missing_data_may_be_silent_no_signal": False,
        },
        "limitations": [
            "This stage is a data and generator readiness audit; it does not replay "
            "strategy economics.",
            "A manifest entry is not sufficient for readiness unless its window and "
            "committed validation pass.",
            "COMPOSITE_ALPHA_V3 currently registers/reroutes a prepared ledger; "
            "raw-OHLCV parity must be proved before breadth expansion.",
        ],
    }


def deterministic_manifest(output_dir: Path, names: Sequence[str]) -> dict[str, Any]:
    files: list[dict[str, object]] = []
    digest = hashlib.sha256()
    for name in sorted(names):
        path = output_dir / name
        file_hash = sha256_path(path)
        files.append({"path": name, "bytes": path.stat().st_size, "sha256": file_hash})
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return {
        "schema_version": "rd18-p3x-runtime-output-manifest-v1",
        "network_requests": 0,
        "files": files,
        "deterministic_hash": digest.hexdigest(),
    }


def report_jsonable(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe deep copy and reject non-finite numbers."""

    encoded = json.dumps(report, allow_nan=False, sort_keys=True)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise P3XReadinessError("report must remain a JSON object")
    return decoded


__all__ = [
    "ACQUISITION_FIELDS",
    "ALLOWED_CANDIDATE_DECISIONS",
    "CandidateCoverage",
    "DECISION_BOTH_REQUIRED",
    "DECISION_DATA_REQUIRED",
    "DECISION_GENERATOR_REQUIRED",
    "DECISION_INPUT_FAILED",
    "DECISION_READY",
    "EXPECTED_C2_PAIRS",
    "EXPECTED_INPUT_HASHES",
    "HourlySource",
    "NEXT_BOTH",
    "P3XReadinessError",
    "PairRequirement",
    "RESEARCH_START",
    "SOURCE_AUDIT_FIELDS",
    "SEALED_CUTOFF",
    "acquisition_plan",
    "audit_sources",
    "candidate_coverage_audit",
    "classify_decision",
    "deterministic_manifest",
    "feature_lookback_audit",
    "generator_readiness_audit",
    "load_c2_requirements",
    "load_committed_readiness",
    "load_hourly_sources",
    "pair_to_symbol",
    "reconcile_input_manifests",
    "report_jsonable",
    "sha256_path",
    "summarize",
    "symbol_to_pair",
]
