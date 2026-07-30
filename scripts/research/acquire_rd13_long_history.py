from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from spotbot.research.daily_history import DailyHistoryPolicy
from spotbot.research.kucoin_daily_history import (
    build_kucoin_daily_windows,
    merge_kucoin_daily_pages,
    parse_kucoin_spot_daily_rows,
)

ASSETS = ("BTC/USDT", "ETH/USDT", "ADA/USDT", "AVAX/USDT", "DOT/USDT")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
START = datetime(2017, 1, 1, tzinfo=UTC)
FETCH_END_OPEN_EXCLUSIVE = datetime(2024, 12, 31, tzinfo=UTC)
RESEARCH_END_CLOSE_EXCLUSIVE = datetime(2025, 1, 1, tzinfo=UTC)
OUTPUT_ROOT = REPOSITORY_ROOT / "data" / "research" / "rd13" / "acquired" / "kucoin"
MANIFEST = REPOSITORY_ROOT / "data" / "research" / "rd13" / "rd13-acquisition-manifest-v1.json"
ENDPOINT = "https://api.kucoin.com/api/v1/market/candles"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _request_rows(symbol: str, start: datetime, end: datetime) -> list[list[object]]:
    parameters = {
        "symbol": symbol.replace("/", "-"),
        "type": "1day",
        "startAt": str(int(start.timestamp())),
        "endAt": str(int(end.timestamp()) - 1),
    }
    request = Request(
        f"{ENDPOINT}?{urlencode(parameters)}",
        headers={"Accept": "application/json", "User-Agent": "spotbot-rd13/1.0"},
        method="GET",
    )
    for attempt in range(1, 5):
        try:
            with urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code") != "200000" or not isinstance(payload.get("data"), list):
                raise RuntimeError(f"Invalid KuCoin response for {symbol}.")
            return list(payload["data"])
        except (OSError, TimeoutError, json.JSONDecodeError):
            if attempt == 4:
                raise
            time.sleep(float(2 ** (attempt - 1)))
    raise AssertionError("unreachable")


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    policy = DailyHistoryPolicy(
        history_start_open=START,
        research_end_close_exclusive=RESEARCH_END_CLOSE_EXCLUSIVE,
    )
    windows = build_kucoin_daily_windows(policy=policy, maximum_calendar_days=1400)
    results: list[dict[str, object]] = []
    for symbol in ASSETS:
        pages = [
            parse_kucoin_spot_daily_rows(
                _request_rows(symbol, window.start_open, window.end_open_exclusive),
                policy=policy,
            )
            for window in windows
        ]
        frame = merge_kucoin_daily_pages(pages, policy=policy)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        if bool((frame["timestamp"] >= pd.Timestamp(RESEARCH_END_CLOSE_EXCLUSIVE)).any()):
            raise RuntimeError(f"Forbidden timestamp returned for {symbol}.")
        slug = symbol.replace("/", "_")
        path = OUTPUT_ROOT / f"{slug}.parquet"
        frame.to_parquet(path, index=False)
        results.append(
            {
                "symbol": symbol,
                "provider": "kucoin",
                "path": path.relative_to(REPOSITORY_ROOT).as_posix(),
                "frequency": "1d",
                "first_timestamp": pd.Timestamp(frame.iloc[0]["timestamp"]).isoformat(),
                "last_timestamp": pd.Timestamp(frame.iloc[-1]["timestamp"]).isoformat(),
                "row_count": len(frame),
                "page_count": len(pages),
                "missing_daily_interval_count": len(
                    pd.date_range(
                        frame.iloc[0]["timestamp"],
                        frame.iloc[-1]["timestamp"],
                        freq="1D",
                    ).difference(pd.DatetimeIndex(frame["timestamp"]))
                ),
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "schema_version": "rd13-acquisition-manifest-v1",
        "batch_count": 1,
        "provider": "kucoin",
        "market_type": "spot",
        "authentication_used": False,
        "start_inclusive": START.isoformat(),
        "fetch_end_open_exclusive": FETCH_END_OPEN_EXCLUSIVE.isoformat(),
        "research_end_close_exclusive": RESEARCH_END_CLOSE_EXCLUSIVE.isoformat(),
        "assets": results,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
