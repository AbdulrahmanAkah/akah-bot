from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.research.rd16c_common import (
    BRANCH,
    CONTEXT_TIMEFRAMES,
    EXCHANGE_ID,
    LOCAL_INPUT_ROOT,
    PILOT_SYMBOLS,
    REPORTS_ROOT,
    ROOT,
    SEALED_CUTOFF,
    SIGNAL_TIMEFRAME,
    dataframe_content_hash,
    read_json_object,
    sha256_path,
)

BASELINE_COMMIT: Final = "7fc076aaef85d9c4cd454569c235f728bef50df7"
RD16C_ROOT: Final = ROOT / "data" / "research" / "rd16c"
RD16D_ROOT: Final = ROOT / "data" / "research" / "rd16d"
LOCAL_LEDGER_ROOT: Final = ROOT / "data" / "raw" / "rd16c"
LOCAL_OUTPUT_ROOT: Final = ROOT / "data" / "raw" / "rd16d"

FAMILY_IDS: Final = (
    "MTF_TREND_BREAKOUT",
    "MTF_PULLBACK_RECLAIM",
    "MTF_COMPRESSION_EXPANSION",
    "MTF_RANGE_RECLAIM",
)

INITIAL_EQUITY: Final = 100_000.0
BASE_FEE_RATE: Final = 0.001
COST_MULTIPLIERS: Final = (1.0, 1.5, 2.0, 3.0)
STRATEGIC_MONTHLY_TARGET: Final = 0.24
STRATEGIC_ANNUALIZED_TARGET: Final = (1.0 + STRATEGIC_MONTHLY_TARGET) ** 12 - 1.0


class RD16DError(RuntimeError):
    pass


class RD16DInputError(RD16DError):
    pass


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            dict(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    *,
    fieldnames: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(fieldnames),
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def iso(value: object) -> str:
    return timestamp(value).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_rd16c_ready() -> dict[str, Any]:
    report = read_json_object(RD16C_ROOT / "rd16c-final-report-v1.json")
    expected = {
        "decision": ("RD16C_REGISTERED_INTRADAY_STRATEGY_FAMILIES_SMOKE_TESTS_COMPLETED"),
        "technical_status": "COMPLETED",
        "evidence_classification": "READY_FOR_FIXED_BASELINE",
        "families_passed": 4,
        "families_total": 4,
        "next_stage": ("RD16D_FIXED_INTRADAY_FAMILY_BASELINE_EVALUATION"),
        "winner_selected": False,
        "optimization_performed": False,
    }
    for key, expected_value in expected.items():
        if report.get(key) != expected_value:
            raise RD16DInputError(f"RD16-C readiness mismatch for {key}: {report.get(key)!r}")

    technical = report.get("technical_gates")
    if not isinstance(technical, dict):
        raise RD16DInputError("RD16-C technical_gates is missing.")
    required_true = (
        "all_four_families_registered",
        "all_four_families_smoke_pass",
        "all_constraints_pass",
        "all_causal_checks_pass",
        "deterministic_replay_match",
        "frozen_inputs_unchanged",
        "spot_only",
        "long_only",
    )
    for key in required_true:
        if technical.get(key) is not True:
            raise RD16DInputError(f"RD16-C technical gate failed: {key}")
    forbidden_true = (
        "test_2025_accessed",
        "holdout_2026_accessed",
        "dune_api_called",
        "optimization_performed",
        "winner_selected",
    )
    for key in forbidden_true:
        if technical.get(key) is True:
            raise RD16DInputError(f"RD16-C forbidden flag is true: {key}")
    return report


def _verify_rd16c_output_hashes() -> dict[str, str]:
    manifest = read_json_object(RD16C_ROOT / "output-hashes.json")
    verified: dict[str, str] = {}
    for raw_name, raw_digest in sorted(manifest.items()):
        if not isinstance(raw_name, str) or not isinstance(raw_digest, str):
            raise RD16DInputError("RD16-C output hash manifest is invalid.")
        path = RD16C_ROOT / raw_name
        if not path.is_file():
            raise RD16DInputError(f"RD16-C output is missing: {path}")
        actual = sha256_path(path)
        if actual != raw_digest:
            raise RD16DInputError(
                f"RD16-C output hash mismatch for {raw_name}: expected {raw_digest}, got {actual}"
            )
        verified[f"rd16c:{raw_name}"] = actual
    return verified


def _ledger_manifest() -> dict[str, Any]:
    manifest = read_json_object(RD16C_ROOT / "local-ledger-manifest-v1.json")
    raw_families = manifest.get("families")
    if not isinstance(raw_families, dict):
        raise RD16DInputError("RD16-C local ledger manifest is invalid.")
    return cast(dict[str, Any], raw_families)


def load_local_ledgers() -> dict[str, dict[str, pd.DataFrame]]:
    families_manifest = _ledger_manifest()
    loaded: dict[str, dict[str, pd.DataFrame]] = {}

    for family_id in FAMILY_IDS:
        raw_family = families_manifest.get(family_id)
        if not isinstance(raw_family, dict):
            raise RD16DInputError(f"RD16-C local ledger manifest missing family: {family_id}")
        family_manifest = cast(dict[str, Any], raw_family)
        family_frames: dict[str, pd.DataFrame] = {}
        for name in ("candidates", "evaluated", "trades"):
            raw_entry = family_manifest.get(name)
            if not isinstance(raw_entry, dict):
                raise RD16DInputError(f"RD16-C ledger manifest missing {family_id}:{name}")
            entry = cast(dict[str, Any], raw_entry)
            relative = entry.get("logical_path")
            file_hash = entry.get("file_sha256")
            content_hash = entry.get("content_sha256")
            rows = entry.get("rows")
            if not isinstance(relative, str):
                raise RD16DInputError(f"RD16-C ledger path missing for {family_id}:{name}")
            path = LOCAL_LEDGER_ROOT / relative
            if not path.is_file():
                raise RD16DInputError(f"RD16-C local ledger missing: {path}")
            if not isinstance(file_hash, str) or sha256_path(path) != file_hash:
                raise RD16DInputError(f"RD16-C ledger file hash mismatch: {family_id}:{name}")
            frame = pd.read_parquet(str(path))
            if not isinstance(rows, int) or len(frame) != rows:
                raise RD16DInputError(f"RD16-C ledger row mismatch: {family_id}:{name}")
            if not isinstance(content_hash, str) or dataframe_content_hash(frame) != content_hash:
                raise RD16DInputError(f"RD16-C ledger content hash mismatch: {family_id}:{name}")
            family_frames[name] = frame
        loaded[family_id] = family_frames
    return loaded


def frozen_input_hashes() -> dict[str, str]:
    tracked = {
        "config/assets.yaml": ROOT / "config" / "assets.yaml",
        "rd16c/rd16c-final-report-v1.json": (RD16C_ROOT / "rd16c-final-report-v1.json"),
        "rd16c/validation-report.json": (RD16C_ROOT / "validation-report.json"),
        "rd16c/output-hashes.json": RD16C_ROOT / "output-hashes.json",
        "rd16c/local-ledger-manifest-v1.json": (RD16C_ROOT / "local-ledger-manifest-v1.json"),
        "rd16c/family-registration.csv": (RD16C_ROOT / "family-registration.csv"),
    }
    hashes: dict[str, str] = {}
    for name, path in tracked.items():
        if not path.is_file():
            raise RD16DInputError(f"Frozen RD16-D input missing: {path}")
        hashes[name] = sha256_path(path)
    hashes.update(_verify_rd16c_output_hashes())

    families_manifest = _ledger_manifest()
    for family_id in FAMILY_IDS:
        raw_family = families_manifest.get(family_id)
        if not isinstance(raw_family, dict):
            raise RD16DInputError(f"Ledger manifest missing family: {family_id}")
        family_manifest = cast(dict[str, Any], raw_family)
        for name in ("candidates", "evaluated", "trades"):
            raw_entry = family_manifest.get(name)
            if not isinstance(raw_entry, dict):
                raise RD16DInputError(f"Ledger manifest missing {family_id}:{name}")
            entry = cast(dict[str, Any], raw_entry)
            relative = entry.get("logical_path")
            if not isinstance(relative, str):
                raise RD16DInputError(f"Ledger path missing {family_id}:{name}")
            path = LOCAL_LEDGER_ROOT / relative
            if not path.is_file():
                raise RD16DInputError(f"Local ledger missing: {path}")
            hashes[f"local:{family_id}:{name}"] = sha256_path(path)
    return dict(sorted(hashes.items()))


__all__ = [
    "BASELINE_COMMIT",
    "BASE_FEE_RATE",
    "BRANCH",
    "CONTEXT_TIMEFRAMES",
    "COST_MULTIPLIERS",
    "EXCHANGE_ID",
    "FAMILY_IDS",
    "INITIAL_EQUITY",
    "LOCAL_INPUT_ROOT",
    "LOCAL_LEDGER_ROOT",
    "LOCAL_OUTPUT_ROOT",
    "PILOT_SYMBOLS",
    "RD16C_ROOT",
    "RD16DInputError",
    "RD16D_ROOT",
    "REPORTS_ROOT",
    "SEALED_CUTOFF",
    "SIGNAL_TIMEFRAME",
    "STRATEGIC_ANNUALIZED_TARGET",
    "STRATEGIC_MONTHLY_TARGET",
    "dataframe_content_hash",
    "frozen_input_hashes",
    "iso",
    "load_local_ledgers",
    "sha256_path",
    "sha256_text",
    "timestamp",
    "verify_rd16c_ready",
    "write_csv",
    "write_json",
]
