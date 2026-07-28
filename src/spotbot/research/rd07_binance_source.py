"""Official Binance spot archive URL and checksum helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines"


@dataclass(frozen=True)
class ArchiveRequest:
    canonical_symbol: str
    binance_pair: str
    month: str

    @property
    def filename(self) -> str:
        return f"{self.binance_pair}-4h-{self.month}.zip"

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.binance_pair}/4h/{self.filename}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksum(text: str) -> str:
    value = text.strip().split()[0].lower()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("invalid official checksum")
    return value
