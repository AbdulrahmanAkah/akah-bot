from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import uuid4

import pandas as pd

from spotbot.data.timeframes import timeframe_to_timedelta
from spotbot.data.validator import REQUIRED_COLUMNS, validate_candles

_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")


class StorageIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredDataset:
    data_path: Path
    metadata_path: Path
    rows: int
    sha256: str


def _safe_component(value: str) -> str:
    cleaned = _SAFE_COMPONENT.sub("-", value.strip())
    cleaned = cleaned.strip(".-")

    if not cleaned:
        raise ValueError(
            "Storage path component cannot be empty."
        )

    return cleaned


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


class ParquetCandleStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def dataset_path(
        self,
        *,
        exchange_id: str,
        symbol: str,
        timeframe: str,
    ) -> Path:
        timeframe_to_timedelta(timeframe)

        exchange_component = _safe_component(
            exchange_id
        )
        symbol_component = _safe_component(
            symbol.replace("/", "-").replace(":", "-")
        )
        timeframe_component = _safe_component(
            timeframe
        )

        return (
            self.root
            / exchange_component
            / symbol_component
            / f"{timeframe_component}.parquet"
        )

    @staticmethod
    def metadata_path(data_path: Path) -> Path:
        return data_path.with_suffix(
            ".metadata.json"
        )

    def save(
        self,
        frame: pd.DataFrame,
        *,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        overwrite: bool = False,
    ) -> StoredDataset:
        report = validate_candles(
            frame,
            symbol=symbol,
            expected_frequency=timeframe,
        )

        if not report.is_valid:
            raise StorageIntegrityError(
                "Refusing to store invalid candle data."
            )

        data_path = self.dataset_path(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=timeframe,
        )
        metadata_path = self.metadata_path(
            data_path
        )

        if data_path.exists() and not overwrite:
            raise FileExistsError(
                f"Dataset already exists: {data_path}"
            )

        data_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        normalized = frame.loc[
            :,
            list(REQUIRED_COLUMNS),
        ].copy()

        normalized["timestamp"] = pd.to_datetime(
            normalized["timestamp"],
            utc=True,
        )

        normalized = normalized.sort_values(
            by="timestamp",
            kind="stable",
        ).reset_index(drop=True)

        timestamp_values = cast(
            list[pd.Timestamp],
            normalized["timestamp"].tolist(),
        )

        temporary_data_path = data_path.with_name(
            f".{data_path.name}.{uuid4().hex}.tmp"
        )

        temporary_metadata_path = metadata_path.with_name(
            f".{metadata_path.name}.{uuid4().hex}.tmp"
        )

        try:
            normalized.to_parquet(
                temporary_data_path,
                index=False,
                engine="pyarrow",
            )

            digest = _sha256(
                temporary_data_path
            )

            metadata: dict[str, object] = {
                "schema_version": (
                    "spotbot-candles-v1"
                ),
                "exchange_id": exchange_id,
                "symbol": symbol,
                "timeframe": timeframe,
                "rows": len(normalized),
                "first_timestamp": (
                    timestamp_values[0].isoformat()
                ),
                "last_timestamp": (
                    timestamp_values[-1].isoformat()
                ),
                "sha256": digest,
            }

            temporary_metadata_path.write_text(
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            os.replace(
                temporary_data_path,
                data_path,
            )
            os.replace(
                temporary_metadata_path,
                metadata_path,
            )

        finally:
            temporary_data_path.unlink(
                missing_ok=True
            )
            temporary_metadata_path.unlink(
                missing_ok=True
            )

        return StoredDataset(
            data_path=data_path,
            metadata_path=metadata_path,
            rows=len(normalized),
            sha256=digest,
        )

    def load(
        self,
        *,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        verify_integrity: bool = True,
    ) -> pd.DataFrame:
        data_path = self.dataset_path(
            exchange_id=exchange_id,
            symbol=symbol,
            timeframe=timeframe,
        )
        metadata_path = self.metadata_path(
            data_path
        )

        if not data_path.exists():
            raise FileNotFoundError(data_path)

        if not metadata_path.exists():
            raise StorageIntegrityError(
                f"Missing metadata file: {metadata_path}"
            )

        if verify_integrity:
            parsed: object = json.loads(
                metadata_path.read_text(
                    encoding="utf-8"
                )
            )

            if not isinstance(parsed, dict):
                raise StorageIntegrityError(
                    "Metadata must be a JSON object."
                )

            metadata = cast(
                dict[str, object],
                parsed,
            )
            expected_hash = metadata.get(
                "sha256"
            )

            if not isinstance(
                expected_hash,
                str,
            ):
                raise StorageIntegrityError(
                    "Metadata SHA-256 is missing."
                )

            actual_hash = _sha256(data_path)

            if actual_hash != expected_hash:
                raise StorageIntegrityError(
                    "Parquet checksum mismatch."
                )

        frame = pd.read_parquet(
            str(data_path)
        )

        report = validate_candles(
            frame,
            symbol=symbol,
            expected_frequency=timeframe,
        )

        if not report.is_valid:
            raise StorageIntegrityError(
                "Stored candle data failed validation."
            )

        return frame