"""RD18-P3X-A1 planning and evidence primitives.

This module is intentionally standard-library only.  Planning, checkpoint
inspection, input reconciliation, and validation must remain usable when the
host blocks pandas or pyarrow native extensions.  Network and dataframe-heavy
operations live behind explicit runner modes.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

STAGE: Final = "RD18_P3X_A1_FULL_C2_HOURLY_DATA_AND_GENERATOR_BUILD"
EXPECTED_C2_PAIRS: Final = 364
SEALED_CUTOFF: Final = datetime(2025, 1, 1, tzinfo=UTC)
RESEARCH_START: Final = datetime(2019, 1, 1, tzinfo=UTC)
SIGNAL_TIMEFRAME: Final = "1h"
CONTEXT_TIMEFRAMES: Final = ("4h", "1d", "1w")
MINIMUM_FEATURE_WARMUP_HOURS: Final = 5_040
CONTROL_SYMBOLS: Final = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "LINK/USDT",
    "AVAX/USDT",
    "NEAR/USDT",
)
EXPECTED_P3X_HASH: Final = "3308de65f3eaaa4ac7f6c1779fd11bd96a91e43c6b174ca793f38e37ead122c7"
EXPECTED_CONTROL_COUNTS: Final = {
    "candidates": 688,
    "evaluated": 688,
    "trades": 567,
}
P3R_RECORDED_CONTROL_CONTENT_HASHES: Final = {
    "candidates": "ab52853c5f78b87d61a66d63f5ed8e1d1357b7c343c4ba628ca3cd2e89c47622",
    "evaluated": "8d06034b9305bf67fca1baf2f850bf50906538204e4dc8ef6c5d2b8b341dfd61",
    "trades": "be1af238dfaac5b832fd5c3ca54188242cf02a785af4d268a33c0878c75ff862",
}

DECISION_TOOLING_READY: Final = "RD18_P3X_A1_EXECUTION_TOOLING_READY"
DECISION_CONTROL_PARITY_REQUIRED: Final = "RD18_P3X_A1_CONTROL_PARITY_REQUIRED"
DECISION_DATA_ACQUISITION_REQUIRED: Final = "RD18_P3X_A1_C2_HOURLY_ACQUISITION_REQUIRED"
DECISION_ENVIRONMENT_BLOCKED: Final = "RD18_P3X_A1_ENVIRONMENT_BLOCKED"
DECISION_ASSET_GATE_BLOCKED: Final = "RD18_P3X_A1_ASSET_GATE_GENERALIZATION_REQUIRED"
DECISION_INPUT_FAILED: Final = "RD18_P3X_A1_INPUT_RECONCILIATION_FAILED"

NEXT_EXECUTION: Final = "RD18_P3X_A1_CONTROL_PARITY_AND_C2_DATA_EXECUTION"
NEXT_ASSET_GATE: Final = "RD18_P3X_A1B_CAUSAL_ASSET_GATE_GENERALIZATION_PROTOCOL"
NEXT_INPUT_REPAIR: Final = "RD18_BLOCKED_PENDING_P3X_INPUT_REPAIR"

PLAN_FIELDS: Final = (
    "pair",
    "symbol",
    "required_since_open",
    "required_until_exclusive",
    "logical_path",
    "local_file_present",
    "source_manifest_present",
    "source_hash_match",
    "source_window_complete",
    "derived_context_complete",
    "evidence_source",
    "current_market_state",
    "checkpoint_state",
    "action",
    "blocking_reason",
)

CHECKPOINT_STATES: Final = frozenset(
    {
        "PENDING",
        "IN_PROGRESS",
        "COMPLETE",
        "FAILED_RETRYABLE",
        "FAILED_PERMANENT",
        "CURRENT_API_MARKET_UNAVAILABLE",
        "HISTORICAL_SOURCE_REQUIRED",
        "ENVIRONMENT_BLOCKED",
    }
)


class A1Error(ValueError):
    """Raised when A1 inputs are malformed or internally contradictory."""


@dataclass(frozen=True, slots=True)
class PairRequirement:
    pair: str
    symbol: str
    required_since_open: datetime
    required_until_exclusive: datetime

    @property
    def logical_path(self) -> str:
        return f"kucoin/{self.pair}/1h.parquet"


@dataclass(frozen=True, slots=True)
class SourceRecord:
    symbol: str
    logical_path: str
    first_close: datetime
    last_close: datetime
    sha256: str


def parse_timestamp(value: object) -> datetime:
    text = str(value).strip()
    if not text:
        raise A1Error("timestamp cannot be empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise A1Error(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def pair_to_symbol(pair: str) -> str:
    normalized = pair.strip().upper()
    if normalized.endswith("-USDT"):
        return normalized[:-5] + "/USDT"
    if normalized.endswith("/USDT"):
        return normalized
    raise A1Error(f"not a USDT pair: {pair!r}")


def symbol_to_pair(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith("/USDT"):
        return normalized[:-5] + "-USDT"
    if normalized.endswith("-USDT"):
        return normalized
    raise A1Error(f"not a USDT symbol: {symbol!r}")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise A1Error(f"cannot read JSON object: {path}") from exc
    if not isinstance(raw, dict):
        raise A1Error(f"JSON input must be an object: {path}")
    return dict(raw)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, rows: Iterable[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fields),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def load_c2_requirements(path: Path) -> list[PairRequirement]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if not rows:
        raise A1Error("C2 coverage audit is empty")
    required = {
        "pair",
        "product_eligible",
        "first_valid_open",
        "last_valid_open",
    }
    missing = required.difference(rows[0])
    if missing:
        raise A1Error(f"C2 coverage columns missing: {sorted(missing)}")

    requirements: list[PairRequirement] = []
    for row in rows:
        if not parse_bool(row["product_eligible"]):
            continue
        pair = symbol_to_pair(row["pair"])
        first_open = parse_timestamp(row["first_valid_open"])
        last_open = parse_timestamp(row["last_valid_open"])
        if last_open >= SEALED_CUTOFF:
            raise A1Error(f"post-2024 C2 observation: {pair}")
        requirements.append(
            PairRequirement(
                pair=pair,
                symbol=pair_to_symbol(pair),
                required_since_open=max(first_open, RESEARCH_START),
                required_until_exclusive=SEALED_CUTOFF,
            )
        )
    requirements.sort(key=lambda item: item.pair)
    pairs = [item.pair for item in requirements]
    if len(pairs) != len(set(pairs)):
        raise A1Error("duplicate C2 pair")
    if len(requirements) != EXPECTED_C2_PAIRS:
        raise A1Error(f"expected {EXPECTED_C2_PAIRS} corrected C2 pairs, found {len(requirements)}")
    return requirements


def load_source_manifest(path: Path) -> dict[str, SourceRecord]:
    manifest = load_json(path)
    if manifest.get("exchange") != "kucoin" or manifest.get("timeframe") != "1h":
        raise A1Error("source manifest is not KuCoin Spot 1h")
    if parse_timestamp(manifest.get("sealed_cutoff")) != SEALED_CUTOFF:
        raise A1Error("source manifest cutoff differs from A1")
    raw_assets = manifest.get("assets")
    if not isinstance(raw_assets, dict):
        raise A1Error("source manifest assets are missing")
    result: dict[str, SourceRecord] = {}
    for raw_symbol, raw_value in raw_assets.items():
        if not isinstance(raw_value, dict):
            raise A1Error(f"invalid source manifest row: {raw_symbol}")
        symbol = pair_to_symbol(str(raw_symbol))
        value = dict(raw_value)
        result[symbol] = SourceRecord(
            symbol=symbol,
            logical_path=str(value["logical_path"]),
            first_close=parse_timestamp(value["first_close"]),
            last_close=parse_timestamp(value["last_close"]),
            sha256=str(value["sha256"]),
        )
    return result


def load_checkpoint(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        return {}
    payload = load_json(path)
    raw_pairs = payload.get("pairs", {})
    if not isinstance(raw_pairs, dict):
        raise A1Error("checkpoint pairs must be an object")
    result: dict[str, dict[str, object]] = {}
    for raw_pair, raw_value in raw_pairs.items():
        if not isinstance(raw_value, dict):
            raise A1Error(f"invalid checkpoint row: {raw_pair}")
        pair = symbol_to_pair(str(raw_pair))
        value = dict(raw_value)
        state = str(value.get("state", "PENDING"))
        if state not in CHECKPOINT_STATES:
            raise A1Error(f"unknown checkpoint state for {pair}: {state}")
        result[pair] = value
    return result


def reconcile_inputs(repo_root: Path) -> dict[str, object]:
    p3x_manifest = repo_root / "data/research/rd18_p3x/output-manifest.json"
    frozen_candidate = repo_root / "data/research/rd18_p3r/frozen-strategy-candidate.json"
    p3x = load_json(p3x_manifest)
    candidate = load_json(frozen_candidate)
    checks = {
        "p3x_manifest_exists": p3x_manifest.is_file(),
        "p3x_hash_match": p3x.get("deterministic_hash") == EXPECTED_P3X_HASH,
        "candidate_architecture": candidate.get("architecture_id") == "COMPOSITE_ALPHA_V3",
        "candidate_variant": candidate.get("source_variant_id") == "STRONG_BULL_HOLD_96",
        "candidate_count": candidate.get("registered_ledger", {}).get("candidate_count") == 688,
        "trade_count": candidate.get("registered_ledger", {}).get("trade_count") == 567,
        "sealed_cutoff": candidate.get("fixed_configuration", {}).get("signal_timeframe")
        == SIGNAL_TIMEFRAME,
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "expected_p3x_hash": EXPECTED_P3X_HASH,
        "actual_p3x_hash": p3x.get("deterministic_hash"),
    }


def lineage_hashes(repo_root: Path) -> dict[str, object]:
    paths = (
        "src/spotbot/research/rd16c_common.py",
        "src/spotbot/research/rd16c_features.py",
        "src/spotbot/research/rd16c_families.py",
        "src/spotbot/research/rd16c_smoke.py",
        "src/spotbot/research/rd16d_metrics.py",
        "src/spotbot/research/rd16e_components.py",
        "src/spotbot/research/rd16h_expansion.py",
        "src/spotbot/research/rd16i_architecture.py",
        "src/spotbot/research/rd16k_remediation.py",
        "src/spotbot/research/rd16l_architecture.py",
    )
    rows: list[dict[str, object]] = []
    for relative in paths:
        path = repo_root / relative
        rows.append(
            {
                "path": relative,
                "exists": path.is_file(),
                "sha256": sha256_path(path) if path.is_file() else "",
            }
        )
    return {
        "schema_version": "rd18-p3x-a1-lineage-hashes-v1",
        "files": rows,
        "all_present": all(bool(row["exists"]) for row in rows),
        "hash_count": sum(bool(row["sha256"]) for row in rows),
    }


def asset_gate_audit(repo_root: Path) -> dict[str, object]:
    path = repo_root / "src/spotbot/research/rd16e_components.py"
    text = path.read_text(encoding="utf-8")
    required_tokens = {
        "allowed_assets_constant": "ALLOWED_ASSETS",
        "trend_static_btc": '"BTC/USDT"',
        "trend_static_link": '"LINK/USDT"',
        "compression_static_near": '"NEAR/USDT"',
        "asset_mask": "def asset_mask",
        "full_stack": '"FULL_REMEDIATION_STACK"',
    }
    token_status = {name: token in text for name, token in required_tokens.items()}
    static_gate_present = all(token_status.values())
    return {
        "schema_version": "rd18-p3x-a1-asset-gate-audit-v1",
        "source": str(path),
        "token_status": token_status,
        "pilot_static_asset_gate_present": static_gate_present,
        "legacy_control_policy": "PRESERVE_EXACTLY_FOR_SIX_SYMBOL_PARITY",
        "broad_c2_policy": "BLOCK_UNTIL_CAUSAL_GENERALIZATION_IS_PREREGISTERED",
        "classification": (
            "PILOT_STATIC_ASSET_GATE_BLOCKS_BREADTH_GENERALIZATION"
            if static_gate_present
            else "ASSET_GATE_SOURCE_DRIFT_REQUIRES_REVIEW"
        ),
    }


def _file_hash_matches(path: Path, expected: str) -> bool:
    return bool(expected) and path.is_file() and sha256_path(path) == expected


def build_acquisition_plan(
    repo_root: Path,
    requirements: Sequence[PairRequirement],
    sources: Mapping[str, SourceRecord],
    checkpoint: Mapping[str, Mapping[str, object]],
    *,
    current_market_symbols: set[str] | None,
) -> list[dict[str, object]]:
    store_root = repo_root / "data/raw/rd16b"
    rows: list[dict[str, object]] = []
    for requirement in requirements:
        source = sources.get(requirement.symbol)
        checkpoint_row = dict(checkpoint.get(requirement.pair, {}))
        checkpoint_state = str(checkpoint_row.get("state", "PENDING"))
        checkpoint_complete = checkpoint_state == "COMPLETE"

        checkpoint_logical_path = str(checkpoint_row.get("logical_path", requirement.logical_path))
        logical_path = requirement.logical_path
        if source is not None:
            logical_path = source.logical_path
        if checkpoint_complete:
            logical_path = checkpoint_logical_path
        data_path = store_root / logical_path
        local_file_present = data_path.is_file()

        evidence_hash = ""
        evidence_first_close: datetime | None = None
        evidence_last_close: datetime | None = None
        evidence_source = "NONE"
        if checkpoint_complete:
            raw_hash = checkpoint_row.get("sha256")
            raw_first = checkpoint_row.get("first_close")
            raw_last = checkpoint_row.get("last_close")
            if isinstance(raw_hash, str) and raw_hash and raw_first and raw_last:
                evidence_hash = raw_hash
                evidence_first_close = parse_timestamp(raw_first)
                evidence_last_close = parse_timestamp(raw_last)
                evidence_source = "A1_VERIFIED_CHECKPOINT"
        if evidence_source == "NONE" and source is not None:
            evidence_hash = source.sha256
            evidence_first_close = source.first_close
            evidence_last_close = source.last_close
            evidence_source = "RD16B_SOURCE_MANIFEST"

        hash_match = _file_hash_matches(data_path, evidence_hash)
        required_first_close = requirement.required_since_open + timedelta(hours=1)
        window_complete = bool(
            evidence_first_close is not None
            and evidence_last_close is not None
            and evidence_first_close <= required_first_close
            and evidence_last_close >= requirement.required_until_exclusive
        )

        raw_derived = checkpoint_row.get("derived_sha256", {})
        checkpoint_derived = raw_derived if isinstance(raw_derived, dict) else {}
        derived_context_complete = True
        for timeframe in CONTEXT_TIMEFRAMES:
            derived_path = store_root / f"kucoin/{requirement.pair}/{timeframe}.parquet"
            if checkpoint_complete and evidence_source == "A1_VERIFIED_CHECKPOINT":
                expected = checkpoint_derived.get(timeframe)
                derived_ready = (
                    isinstance(expected, str)
                    and bool(expected)
                    and _file_hash_matches(derived_path, expected)
                )
            else:
                derived_ready = derived_path.is_file()
            derived_context_complete = derived_context_complete and derived_ready

        if local_file_present and hash_match and window_complete and derived_context_complete:
            action = "READY_LOCAL"
            reason = ""
        elif current_market_symbols is None:
            action = "NETWORK_MARKET_PROBE_REQUIRED"
            reason = "current KuCoin Spot inventory was not queried"
        elif requirement.symbol in current_market_symbols:
            action = "DOWNLOAD_OR_BACKFILL_CURRENT_API"
            reason = ""
        else:
            action = "HISTORICAL_MARKET_SOURCE_REQUIRED"
            reason = "pair is absent from the current KuCoin Spot inventory"

        if (
            checkpoint_state
            in {
                "HISTORICAL_SOURCE_REQUIRED",
                "CURRENT_API_MARKET_UNAVAILABLE",
            }
            and action != "READY_LOCAL"
        ):
            action = "HISTORICAL_MARKET_SOURCE_REQUIRED"
            checkpoint_error = str(checkpoint_row.get("error", "")).strip()
            reason = checkpoint_error or (
                "current KuCoin API cannot satisfy the frozen historical window"
            )

        if checkpoint_state == "COMPLETE" and action != "READY_LOCAL":
            action = "CHECKPOINT_REVALIDATION_REQUIRED"
            reason = "checkpoint says COMPLETE but local source validation does not"

        current_state = "UNPROBED"
        if current_market_symbols is not None:
            current_state = (
                "CURRENT_SPOT_MARKET_PRESENT"
                if requirement.symbol in current_market_symbols
                else "CURRENT_SPOT_MARKET_ABSENT"
            )
        rows.append(
            {
                "pair": requirement.pair,
                "symbol": requirement.symbol,
                "required_since_open": iso(requirement.required_since_open),
                "required_until_exclusive": iso(requirement.required_until_exclusive),
                "logical_path": logical_path,
                "local_file_present": local_file_present,
                "source_manifest_present": source is not None,
                "source_hash_match": hash_match,
                "source_window_complete": window_complete,
                "derived_context_complete": derived_context_complete,
                "evidence_source": evidence_source,
                "current_market_state": current_state,
                "checkpoint_state": checkpoint_state,
                "action": action,
                "blocking_reason": reason,
            }
        )
    return rows


def summarize_plan(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {}
    for row in rows:
        action = str(row["action"])
        counts[action] = counts.get(action, 0) + 1
    ready = counts.get("READY_LOCAL", 0)
    return {
        "c2_pairs": len(rows),
        "action_counts": dict(sorted(counts.items())),
        "ready_pairs": ready,
        "ready_fraction": ready / len(rows) if rows else 0.0,
        "all_ready": ready == EXPECTED_C2_PAIRS,
    }


def deterministic_manifest(root: Path, names: Sequence[str]) -> dict[str, object]:
    files: list[dict[str, object]] = []
    digest = hashlib.sha256()
    for name in sorted(names):
        path = root / name
        file_hash = sha256_path(path)
        files.append({"path": name, "bytes": path.stat().st_size, "sha256": file_hash})
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
    return {
        "schema_version": "rd18-p3x-a1-runtime-output-manifest-v1",
        "network_requests": 0,
        "files": files,
        "deterministic_hash": digest.hexdigest(),
    }


def decision_for_plan(
    *,
    input_ready: bool,
    environment_ready: bool,
    control_parity_passed: bool,
    all_data_ready: bool,
    broad_asset_gate_ready: bool,
) -> tuple[str, str]:
    if not input_ready:
        return DECISION_INPUT_FAILED, NEXT_INPUT_REPAIR
    if not environment_ready:
        return DECISION_ENVIRONMENT_BLOCKED, NEXT_EXECUTION
    if not control_parity_passed:
        return DECISION_CONTROL_PARITY_REQUIRED, NEXT_EXECUTION
    if not all_data_ready:
        return DECISION_DATA_ACQUISITION_REQUIRED, NEXT_EXECUTION
    if not broad_asset_gate_ready:
        return DECISION_ASSET_GATE_BLOCKED, NEXT_ASSET_GATE
    return DECISION_TOOLING_READY, NEXT_EXECUTION


__all__ = [
    "A1Error",
    "CHECKPOINT_STATES",
    "CONTEXT_TIMEFRAMES",
    "CONTROL_SYMBOLS",
    "DECISION_ASSET_GATE_BLOCKED",
    "DECISION_CONTROL_PARITY_REQUIRED",
    "DECISION_DATA_ACQUISITION_REQUIRED",
    "DECISION_ENVIRONMENT_BLOCKED",
    "DECISION_INPUT_FAILED",
    "DECISION_TOOLING_READY",
    "EXPECTED_C2_PAIRS",
    "P3R_RECORDED_CONTROL_CONTENT_HASHES",
    "EXPECTED_CONTROL_COUNTS",
    "EXPECTED_P3X_HASH",
    "MINIMUM_FEATURE_WARMUP_HOURS",
    "NEXT_ASSET_GATE",
    "NEXT_EXECUTION",
    "NEXT_INPUT_REPAIR",
    "PLAN_FIELDS",
    "PairRequirement",
    "SEALED_CUTOFF",
    "SIGNAL_TIMEFRAME",
    "STAGE",
    "SourceRecord",
    "asset_gate_audit",
    "build_acquisition_plan",
    "decision_for_plan",
    "deterministic_manifest",
    "iso",
    "lineage_hashes",
    "load_c2_requirements",
    "load_checkpoint",
    "load_json",
    "load_source_manifest",
    "pair_to_symbol",
    "parse_timestamp",
    "reconcile_inputs",
    "sha256_path",
    "summarize_plan",
    "symbol_to_pair",
    "write_csv",
    "write_json",
]
