"""Resumable, checksummed pilot acquisition helpers for RD09."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from spotbot.research.rd09_source_selection import validate_pilot_range

MAX_ATTEMPTS: Final = 3


@dataclass(frozen=True)
class FetchResult:
    path: Path
    request_url: str
    retrieved_at_utc: str
    http_status: int
    sha256: str
    size_bytes: int
    resumed: bool
    response_headers: dict[str, str]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_json(
    *,
    url: str,
    destination: Path,
    start: str | None = None,
    end: str | None = None,
    attempts: int = MAX_ATTEMPTS,
) -> FetchResult:
    if (start is None) != (end is None):
        raise ValueError("start and end must be supplied together")
    if start is not None and end is not None:
        validate_pilot_range(start, end)
    if destination.exists() and destination.stat().st_size > 0:
        json.loads(destination.read_text(encoding="utf-8"))
        return FetchResult(
            destination,
            url,
            datetime.now(UTC).isoformat(),
            200,
            file_sha256(destination),
            destination.stat().st_size,
            True,
            {},
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "spot-speculation-bot-rd09-feasibility/1"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                status = int(response.status)
                body = response.read()
                headers = {
                    key.lower(): value
                    for key, value in response.headers.items()
                    if key.lower()
                    in {"content-type", "etag", "last-modified", "x-ratelimit-remaining"}
                }
            json.loads(body.decode("utf-8"))
            temporary = destination.with_suffix(f"{destination.suffix}.tmp")
            temporary.write_bytes(body)
            temporary.replace(destination)
            return FetchResult(
                destination,
                url,
                datetime.now(UTC).isoformat(),
                status,
                file_sha256(destination),
                len(body),
                False,
                headers,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            last_error = error
            if isinstance(error, urllib.error.HTTPError) and error.code == 404:
                break
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(f"pilot acquisition failed for {url}") from last_error


def append_manifest(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]]
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise TypeError("request manifest must be a list")
        records = [dict(item) for item in loaded]
    else:
        records = []
    identity = (record["source_id"], record["request_url"], record["destination"])
    filtered = [
        item
        for item in records
        if (item["source_id"], item["request_url"], item["destination"]) != identity
    ]
    filtered.append(record)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(filtered, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)
