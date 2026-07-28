"""Resume-safe acquisition and freeze of official Binance spot 4H archives."""

from __future__ import annotations

import io
import json
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from spotbot.research.rd07_binance_source import (
    ArchiveRequest,
    parse_checksum,
    sha256,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
DATA_ROOT = ROOT / "data" / "research" / "rd07" / "binance-spot-4h"
MANIFEST_PATH = DATA_ROOT / "source-manifest-v1.json"
COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "base_volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
)


def atomic_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    for attempt in range(10):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.05 * (attempt + 1))


def fetch_bytes(url: str, retries: int = 2) -> tuple[bytes | None, str]:
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "SIRAJ-RD07/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read(), "OK"
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None, "HTTP_404"
            if attempt == retries:
                return None, f"HTTP_{error.code}"
        except (TimeoutError, urllib.error.URLError) as error:
            if attempt == retries:
                return None, f"NETWORK_FAILURE:{type(error).__name__}"
        time.sleep(1 + attempt)
    return None, "NETWORK_FAILURE"


def download_one(request: ArchiveRequest) -> dict[str, object]:
    pair_dir = DATA_ROOT / request.binance_pair
    pair_dir.mkdir(parents=True, exist_ok=True)
    path = pair_dir / request.filename
    checksum_path = path.with_suffix(f"{path.suffix}.CHECKSUM")
    checksum_bytes, checksum_status = fetch_bytes(f"{request.url}.CHECKSUM")
    if checksum_bytes is None:
        return {
            "canonical_symbol": request.canonical_symbol,
            "binance_pair": request.binance_pair,
            "month": request.month,
            "path": str(path.relative_to(ROOT)),
            "download_status": checksum_status,
            "checksum_match": False,
        }
    official = parse_checksum(checksum_bytes.decode("utf-8"))
    if path.exists() and sha256(path) == official:
        checksum_path.write_bytes(checksum_bytes)
        status = "REUSED_VERIFIED"
    else:
        payload, status = fetch_bytes(request.url)
        if payload is None:
            return {
                "canonical_symbol": request.canonical_symbol,
                "binance_pair": request.binance_pair,
                "month": request.month,
                "path": str(path.relative_to(ROOT)),
                "download_status": status,
                "checksum_match": False,
            }
        temporary = path.with_suffix(".zip.tmp")
        temporary.write_bytes(payload)
        observed = sha256(temporary)
        if observed != official:
            temporary.unlink()
            return {
                "canonical_symbol": request.canonical_symbol,
                "binance_pair": request.binance_pair,
                "month": request.month,
                "path": str(path.relative_to(ROOT)),
                "download_status": "CHECKSUM_MISMATCH",
                "checksum_match": False,
                "official_sha256": official,
                "observed_sha256": observed,
            }
        temporary.replace(path)
        checksum_path.write_bytes(checksum_bytes)
        status = "DOWNLOADED_VERIFIED"
    return {
        "canonical_symbol": request.canonical_symbol,
        "binance_pair": request.binance_pair,
        "month": request.month,
        "path": str(path.relative_to(ROOT)),
        "download_status": status,
        "checksum_match": True,
        "official_sha256": official,
        "local_sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


def read_archive(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise ValueError(f"unexpected archive members: {path}")
        raw = archive.read(names[0])
    frame = pd.read_csv(io.BytesIO(raw), header=None, names=COLUMNS)
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    return frame


def main() -> None:
    protocol = json.loads(
        (REPORTS / "ams-rd07-protocol-registration-v1.json").read_text(encoding="utf-8")
    )
    if protocol["next_stage"] != "RD07-BINANCE-SPOT-SOURCE-FREEZE":
        raise RuntimeError("RD07 source freeze is not authorized")
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    membership = pd.read_csv(REPORTS / "ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv")
    symbols = sorted(membership["canonical_symbol"].astype(str).unique())
    special = {"POL": "MATIC"}
    mappings = [
        {
            "kucoin_canonical_symbol": symbol,
            "kucoin_pair": f"{symbol}-USDT",
            "binance_usdt_pair": f"{special.get(symbol, symbol)}USDT",
            "mapping_basis": (
                "REGISTERED_POL_MATIC_IDENTITY" if symbol == "POL" else "CANONICAL_SYMBOL_MATCH"
            ),
            "notes": (
                "No economic identities are merged" if symbol != "POL" else "POL uses MATIC history"
            ),
        }
        for symbol in symbols
    ]
    months = pd.period_range("2021-01", "2024-12", freq="M").astype(str).tolist()
    requests = [
        ArchiveRequest(
            str(row["kucoin_canonical_symbol"]),
            str(row["binance_usdt_pair"]),
            month,
        )
        for row in mappings
        for month in months
    ]
    existing: dict[str, dict[str, object]] = {}
    if MANIFEST_PATH.exists():
        for item in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["archives"]:
            existing[f"{item['binance_pair']}:{item['month']}"] = item
    results: dict[str, dict[str, object]] = dict(existing)
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(download_one, request): request for request in requests}
        for future in as_completed(futures):
            item = future.result()
            key = f"{item['binance_pair']}:{item['month']}"
            results[key] = item
            atomic_json(
                MANIFEST_PATH,
                {
                    "source": "https://data.binance.vision",
                    "market": "spot",
                    "interval": "4h",
                    "research_months": ["2021-01", "2024-12"],
                    "archives": [value for _, value in sorted(results.items())],
                    "updated_at_utc": datetime.now(UTC).isoformat(),
                },
            )
    archive_rows = list(results.values())
    mapping_rows: list[dict[str, object]] = []
    quality_rows: list[dict[str, object]] = []
    for mapping in mappings:
        symbol = str(mapping["kucoin_canonical_symbol"])
        pair = str(mapping["binance_usdt_pair"])
        valid = [
            item
            for item in archive_rows
            if item["binance_pair"] == pair and item.get("checksum_match") is True
        ]
        frames = [read_archive(ROOT / str(item["path"])) for item in valid]
        if frames:
            combined = pd.concat(frames, ignore_index=True).drop_duplicates("open_time")
            combined = combined.sort_values("open_time")
            combined["canonical_symbol"] = symbol
            parquet = DATA_ROOT / f"{pair}-4h-2021-2024.parquet"
            combined.to_parquet(parquet, index=False)
            numeric = combined[
                [
                    "open",
                    "high",
                    "low",
                    "close",
                    "base_volume",
                    "quote_asset_volume",
                    "number_of_trades",
                    "taker_buy_quote_asset_volume",
                ]
            ].apply(pd.to_numeric, errors="coerce")
            mapping_rows.append(
                {
                    **mapping,
                    "first_binance_bar": combined["open_time"].min(),
                    "last_binance_bar": combined["close_time"].max(),
                    "download_status": "SOURCE_READY",
                    "coverage_status": "PARTIAL_OR_COMPLETE",
                    "parquet_path": str(parquet.relative_to(ROOT)),
                    "parquet_sha256": sha256(parquet),
                }
            )
            gaps = combined["open_time"].diff().ne(pd.Timedelta(hours=4))
            returns = np.log(numeric["close"]).diff()
            median = float(returns.median())
            mad = float((returns - median).abs().median())
            robust = (
                (returns - median) / (1.4826 * mad)
                if mad > 0
                else pd.Series(np.nan, index=returns.index)
            )
            quality_rows.append(
                {
                    "symbol": symbol,
                    "row_count": len(combined),
                    "duplicate_count": int(combined.duplicated("open_time").sum()),
                    "gap_count": int(gaps.iloc[1:].sum()),
                    "null_nonfinite_count": int((~np.isfinite(numeric)).sum().sum()),
                    "flat_bar_share": float(
                        (
                            (numeric["open"] == numeric["high"])
                            & (numeric["high"] == numeric["low"])
                            & (numeric["low"] == numeric["close"])
                        ).mean()
                    ),
                    "zero_quote_volume_share": float((numeric["quote_asset_volume"] == 0).mean()),
                    "zero_trade_count_share": float((numeric["number_of_trades"] == 0).mean()),
                    "zero_taker_buy_share": float(
                        (numeric["taker_buy_quote_asset_volume"] == 0).mean()
                    ),
                    "taker_exceeds_quote_count": int(
                        (
                            numeric["taker_buy_quote_asset_volume"] > numeric["quote_asset_volume"]
                        ).sum()
                    ),
                    "largest_robust_return_outlier": float(robust.abs().max()),
                    "symbol_excluded": False,
                }
            )
        else:
            mapping_rows.append(
                {
                    **mapping,
                    "first_binance_bar": "",
                    "last_binance_bar": "",
                    "download_status": "NO_VERIFIED_ARCHIVE",
                    "coverage_status": "UNAVAILABLE",
                    "parquet_path": "",
                    "parquet_sha256": "",
                }
            )
    mapping_path = REPORTS / "ams-rd07-binance-symbol-mapping-v1.csv"
    pd.DataFrame(mapping_rows).to_csv(mapping_path, index=False, lineterminator="\n")
    pd.DataFrame(quality_rows).to_csv(
        REPORTS / "ams-rd07-binance-data-quality-v1.csv", index=False, lineterminator="\n"
    )
    report = {
        "status": "COMPLETE",
        "decision": "RD07_BINANCE_SPOT_SOURCE_FREEZE_COMPLETE",
        "declared_symbols": len(symbols),
        "source_ready_symbols": sum(
            row["download_status"] == "SOURCE_READY" for row in mapping_rows
        ),
        "requested_archives": len(requests),
        "verified_archives": sum(item.get("checksum_match") is True for item in archive_rows),
        "http_404_archives": sum(item["download_status"] == "HTTP_404" for item in archive_rows),
        "network_failures": sum(
            str(item["download_status"]).startswith("NETWORK_FAILURE") for item in archive_rows
        ),
        "raw_data_path": str(DATA_ROOT.relative_to(ROOT)),
        "manifest_sha256": sha256(MANIFEST_PATH),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "next_stage": "RD07-COVERAGE-AUDIT",
    }
    atomic_json(REPORTS / "ams-rd07-binance-source-freeze-v1.json", report)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
