"""Deterministic, Windows-safe atomic research-output writers.

The writers in this module serialize into a uniquely named file in the
destination directory, close every serialization handle, and only then
replace the destination.  Keeping the temporary file beside its destination
also makes the final replace atomic on the supported local filesystems.
"""

from __future__ import annotations

import csv
import json
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    import pandas as pd


class AtomicOutputError(ValueError):
    """Raised when an atomic output request is unsafe or invalid."""


Writer = Callable[[Path], None]
Validator = Callable[[Path], None]
ParquetCompression = Literal["snappy", "gzip", "brotli", "lz4", "zstd"]


def _normalized_path(path: Path) -> str:
    """Return a Windows-case-insensitive absolute comparison key."""

    resolved = path.expanduser().resolve(strict=False)
    return os.path.normcase(os.path.abspath(os.fspath(resolved)))


def _reject_source_collision(source: Path | None, destination: Path) -> None:
    if source is not None and _normalized_path(source) == _normalized_path(destination):
        raise AtomicOutputError(
            f"source and destination resolve to the same path: {source} == {destination}"
        )


def _temporary_path(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=os.fspath(destination.parent),
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary = Path(name)
    if _normalized_path(temporary) == _normalized_path(destination):
        temporary.unlink(missing_ok=True)
        raise AtomicOutputError("temporary path collides with destination")
    return temporary


def _atomic_write(
    destination: Path,
    writer: Writer,
    *,
    source: Path | None = None,
    validator: Validator | None = None,
) -> Path:
    destination = Path(destination)
    _reject_source_collision(source, destination)
    temporary: Path | None = None
    try:
        temporary = _temporary_path(destination)
        writer(temporary)
        if validator is not None:
            validator(temporary)
        # All writer and validator handles must be closed before this call.
        os.replace(temporary, destination)
        temporary = None
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write(
    destination: Path,
    writer: Writer,
    *,
    source: Path | None = None,
    validator: Validator | None = None,
) -> Path:
    """Run a caller-supplied serializer under the atomic lifecycle."""

    return _atomic_write(destination, writer, source=source, validator=validator)


def atomic_write_text(
    destination: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
    source: Path | None = None,
    validate_text: bool = False,
) -> Path:
    """Write text atomically, preserving the requested newline policy."""

    def writer(temporary: Path) -> None:
        with temporary.open("w", encoding=encoding, newline=newline) as handle:
            handle.write(text)
            handle.flush()

    def validator(temporary: Path) -> None:
        if temporary.read_text(encoding=encoding) != text:
            raise AtomicOutputError("temporary text validation failed")

    return _atomic_write(
        Path(destination),
        writer,
        source=source,
        validator=validator if validate_text else None,
    )


def atomic_write_json(
    destination: Path,
    value: object,
    *,
    source: Path | None = None,
) -> Path:
    """Serialize a JSON value deterministically and replace atomically."""

    serialized = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    def writer(temporary: Path) -> None:
        with temporary.open("w", encoding="utf-8", newline=None) as handle:
            handle.write(serialized)
            handle.flush()

    def validator(temporary: Path) -> None:
        json.loads(temporary.read_text(encoding="utf-8"))

    return _atomic_write(
        Path(destination),
        writer,
        source=source,
        validator=validator,
    )


def atomic_write_csv(
    destination: Path,
    rows: Iterable[Mapping[str, object]],
    fields: Sequence[str],
    *,
    source: Path | None = None,
) -> Path:
    """Write a deterministic CSV with the repository's existing CSV format."""

    frozen_rows = tuple(rows)

    def writer(temporary: Path) -> None:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            output = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
            output.writeheader()
            for row in frozen_rows:
                output.writerow({field: row.get(field, "") for field in fields})
            handle.flush()

    return _atomic_write(Path(destination), writer, source=source)


def atomic_write_parquet(
    destination: Path,
    frame: pd.DataFrame,
    *,
    source: Path | None = None,
    compression: ParquetCompression | None = "zstd",
    validate: Callable[[pd.DataFrame], None] | None = None,
) -> Path:
    """Materialize and atomically write a Parquet DataFrame."""

    materialized = frame.copy(deep=True)

    def writer(temporary: Path) -> None:
        materialized.to_parquet(temporary, index=False, compression=compression)

    def validator(temporary: Path) -> None:
        if validate is not None:
            import pandas as pd  # noqa: PLC0415

            checked = pd.read_parquet(temporary)
            try:
                validate(checked)
            finally:
                del checked

    return _atomic_write(
        Path(destination),
        writer,
        source=source,
        validator=validator if validate is not None else None,
    )


def atomic_write_bytes(
    destination: Path,
    payload: bytes,
    *,
    source: Path | None = None,
) -> Path:
    """Write already-serialized bytes atomically."""

    def writer(temporary: Path) -> None:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()

    return _atomic_write(Path(destination), writer, source=source)


__all__ = [
    "AtomicOutputError",
    "atomic_write",
    "atomic_write_bytes",
    "atomic_write_csv",
    "atomic_write_json",
    "atomic_write_parquet",
    "atomic_write_text",
]
