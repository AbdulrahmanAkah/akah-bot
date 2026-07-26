"""Neutral I/O, registered-data, and reporting helpers for AMS-MD01."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spotbot.research.ams_md01_momentum import RESEARCH_LOCK, assert_spot_ohlcv

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
OUTSIDE = Path(r"C:\SIRAJ\Reports")
REGISTRATION = REPORTS / "ams-v3-4h-dataset-registration-v1.json"
PROTOCOL = REPORTS / "ams-md01-protocol-v1.json"
LEDGER = REPORTS / "ams-md01-experiment-ledger-v1.json"
READINESS = REPORTS / "ams-md01-data-readiness-v1.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _finite(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(_finite(value), stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(value)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def copy_external(names: Sequence[str]) -> None:
    OUTSIDE.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = REPORTS / name
        target = OUTSIDE / name
        shutil.copy2(source, target)
        if sha256(source) != sha256(target):
            raise RuntimeError(f"external report hash mismatch: {name}")


def load_registration() -> dict[str, Any]:
    return json.loads(REGISTRATION.read_text(encoding="utf-8"))


def load_registered_data() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    registration = load_registration()
    frames: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for name in ("four_hour", "eight_hour", "daily", "availability"):
        record = registration["datasets"][name]
        path = ROOT / record["path"]
        actual = sha256(path)
        if actual != record["file_sha256"]:
            raise RuntimeError(f"registered dataset hash mismatch: {name}")
        frame = pd.read_parquet(path)
        if name != "availability":
            assert_spot_ohlcv(frame)
        frames[name] = frame
        hashes[name] = actual
    availability = frames["availability"]
    for column in ("tradable_from", "tradable_until"):
        availability[column] = pd.to_datetime(availability[column], utc=True)
    if bool((availability["tradable_from"] >= RESEARCH_LOCK).all()):
        raise RuntimeError("availability contains no research-period symbols")
    return frames, hashes


def verify_report_hashes(records: Mapping[str, str]) -> None:
    mismatches = [
        name for name, expected in records.items() if sha256(REPORTS / name) != expected
    ]
    if mismatches:
        raise RuntimeError(f"report hash mismatch: {mismatches}")


def load_protocol() -> dict[str, Any]:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def load_ledger() -> dict[str, Any]:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def write_registered_state(
    protocol: Mapping[str, Any],
    ledger: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> None:
    atomic_json(PROTOCOL, protocol)
    atomic_json(LEDGER, ledger)
    atomic_json(READINESS, readiness)

