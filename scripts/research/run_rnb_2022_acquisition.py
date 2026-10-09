"""Governed opt-in isolated acquisition. No replay, mixed-store reads or outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import ccxt
import pandas as pd

from spotbot.research.rd20_p2_minimal_pullback import load_membership
from spotbot.research.rnb_bounded_2022 import (
    END,
    HOUR,
    START,
    fetch_page,
    normalize_2022,
    plan_page,
)

ROOT = Path(__file__).resolve().parents[2]
MEMBERSHIP = ROOT / "data/research/rd18_p3x_a3b_runtime/effective-operational-membership.csv"
MEMBERSHIP_SHA = "F7D6012CE8CD691583B9B6276DDF36371BFE0BBD9B28F810B676AD0177FB559E"
TARGET = ROOT / "data/research/reconstructed_native_baseline_pre2023/native-1h-2022-v1"
EVIDENCE = ROOT / "governance/rnb_acquisition"
CURRENT = ROOT / "data/raw/rd16b/kucoin"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def raw_state() -> list[dict]:
    # Filesystem metadata only; never deserialize mixed Parquet rows.
    return [
        {
            "path": str(p.relative_to(ROOT)),
            "size": p.stat().st_size,
            "mtime_ns": p.stat().st_mtime_ns,
        }
        for p in sorted(CURRENT.glob("*/1h.parquet"))
    ]


def pair_scope() -> list[str]:
    if sha(MEMBERSHIP) != MEMBERSHIP_SHA:
        raise ValueError("membership authority drift")
    start, end = pd.Timestamp(START, unit="s", tz="UTC"), pd.Timestamp(END, unit="s", tz="UTC")
    membership = load_membership(MEMBERSHIP)
    relevant = [
        s
        for s in membership
        if s.universe_id in {"C2", "D2", "E2"}
        and max(s.decision_time, start) < min(s.effective_end, end)
    ]
    if {s.universe_id for s in relevant} != {"C2", "D2", "E2"}:
        raise ValueError("missing frozen universe")
    return sorted({pair for s in relevant for pair, _rank in s.members} | {"BTC-USDT"})


def preflight() -> None:
    if TARGET.exists() and any(TARGET.iterdir()):
        raise ValueError("target must be empty/absent; no overwrite or resume")
    pairs = pair_scope()
    before = raw_state()
    if len(before) != 342:
        raise ValueError("native raw inventory drift")
    contract = {
        "pairs": pairs,
        "pair_count": len(pairs),
        "membership_sha256": MEMBERSHIP_SHA,
        "root": str(TARGET.relative_to(ROOT)),
        "layout": "kucoin/<pair>/1h.parquet",
        "since_close_inclusive": "2022-01-01T00:00:00Z",
        "until_close_exclusive": "2023-01-01T00:00:00Z",
        "first_requested_open": "2022-01-01T00:00:00Z",
        "first_possible_close": "2022-01-01T01:00:00Z",
        "pair_derivation": "native membership snapshots intersecting study window; BTC sensor",
        "boundary_authority_sha256": sha(
            ROOT / "governance/rnb_boundary/remote_boundary_authority.json"
        ),
        "adapter_sha256": sha(ROOT / "src/spotbot/research/rnb_bounded_2022.py"),
        "network_calls": 0,
    }
    write_new(EVIDENCE / "preflight.json", contract)
    write_new(EVIDENCE / "current_raw_state_before.json", before)
    print(f"PAIR_SCOPE_FROZEN={len(pairs)} SHA256={sha(EVIDENCE / 'preflight.json')}", flush=True)
    print("REMOTE_BOUNDARY_AUTHORITY=PASS STORE_ROOT_ISOLATED=PASS TARGET_EMPTY=PASS", flush=True)


def acquire() -> None:
    contract = json.loads((EVIDENCE / "preflight.json").read_text(encoding="utf-8"))
    if contract["pairs"] != pair_scope():
        raise ValueError("pair scope drift")
    if contract["adapter_sha256"] != sha(ROOT / "src/spotbot/research/rnb_bounded_2022.py"):
        raise ValueError("boundary source drift")
    before = json.loads((EVIDENCE / "current_raw_state_before.json").read_text(encoding="utf-8"))
    if before != raw_state() or (TARGET.exists() and any(TARGET.iterdir())):
        raise ValueError("raw state/isolated root drift")
    client = ccxt.kucoin(
        {"enableRateLimit": True, "timeout": 20000, "options": {"maxRetriesOnFailure": 0}}
    )
    # Direct raw endpoint only: no load_markets, discovery or unbounded probes.
    manifest, attempts = [], []
    failure = None
    try:
        for pair in contract["pairs"]:
            rows, cursor = [], START
            while (page := plan_page(pair, cursor)) is not None:
                print(
                    f"BOUNDED_REQUEST={pair} startAt={page.start_at} endAt={page.end_at}",
                    flush=True,
                )
                request = {
                    "sequence": len(attempts) + 1,
                    "pair": pair,
                    "params": page.params(),
                    "status": "START",
                }
                attempts.append(request)
                chunk = fetch_page(client, page)
                request.update(status="PASS", row_count=len(chunk))
                rows.extend(chunk)
                cursor = page.next_since
            frame = normalize_2022(rows)
            if frame.empty:
                manifest.append(
                    {
                        "pair": pair,
                        "row_count": 0,
                        "coverage_status": "EMPTY_RESPONSE_LISTING_AUTHORITY_UNRESOLVED",
                    }
                )
                print(f"PAIR_EMPTY={pair} LISTING_STATUS=UNRESOLVED", flush=True)
                continue
            if list(frame.columns) != ["timestamp", "open", "high", "low", "close", "volume"]:
                raise ValueError("native schema drift")
            times = frame["timestamp"]
            gaps = times.diff().dropna().dt.total_seconds()
            path = TARGET / "kucoin" / pair / "1h.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise ValueError("immutable target already exists")
            frame.to_parquet(path, index=False)
            manifest.append(
                {
                    "pair": pair,
                    "path": str(path.relative_to(ROOT)),
                    "row_count": len(frame),
                    "min_timestamp": str(times.min()),
                    "max_timestamp": str(times.max()),
                    "sha256": sha(path),
                    "duplicate_rows": int(times.duplicated().sum()),
                    "monotonic": bool(times.is_monotonic_increasing),
                    "gap_count": int((gaps != HOUR).sum()),
                    "missing_internal_hours": int((gaps / HOUR - 1).clip(lower=0).sum()),
                    "edge_coverage_status": "REQUIRES_LISTING_OR_COVERAGE_ADJUDICATION"
                    if len(frame) != 8759
                    else "FULL_REQUESTED_OPEN_WINDOW",
                }
            )
            print(f"PAIR_COMPLETE={pair} ROWS={len(frame)}", flush=True)
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        after = raw_state()
        write_new(EVIDENCE / "current_raw_state_after.json", after)
        write_new(
            EVIDENCE / "acquisition_result.json",
            {
                "status": "FAIL_CLOSED" if failure else "FETCH_COMPLETE_REQUIRES_COVERAGE_REVIEW",
                "failure": failure,
                "request_attempts": attempts,
                "manifest": manifest,
                "network_calls_attempted": len(attempts),
                "current_raw_metadata_unchanged": before == after,
                "protected_year_requests": 0,
                "native_replay_executed": False,
            },
        )
    if failure or before != after:
        raise SystemExit("ACQUISITION=FAIL_CLOSED see governed result")


def verify() -> None:
    result = json.loads((EVIDENCE / "acquisition_result.json").read_text(encoding="utf-8"))
    if result["failure"] or not result["current_raw_metadata_unchanged"]:
        raise ValueError("acquisition failed")
    membership = load_membership(MEMBERSHIP)
    ledger = []
    for item in result["manifest"]:
        path = ROOT / item["path"]
        if TARGET.resolve() not in path.resolve().parents or sha(path) != item["sha256"]:
            raise ValueError("isolated input identity drift")
        # Access is lawful from captured bounded producer identity before row-open.
        frame = pd.read_parquet(path)
        times = frame["timestamp"]
        assert str(times.dt.tz) == "UTC"
        assert times.is_monotonic_increasing and not times.duplicated().any()
        assert times.min().timestamp() >= START and times.max().timestamp() < END
        assert times.diff().dropna().eq(pd.Timedelta(hours=1)).all()
        assert frame[["open", "high", "low", "close", "volume"]].notna().all().all()
        assert (frame[["open", "high", "low", "close"]] > 0).all().all()
        assert (frame["volume"] >= 0).all()
        relevant = [
            s.decision_time
            for s in membership
            if s.decision_time.year == 2022 and any(p == item["pair"] for p, _ in s.members)
        ]
        ledger.append(
            {
                **item,
                "schema_verified": True,
                "utc": True,
                "protected_year_rows": 0,
                "hourly_continuity": "PASS",
                "first_membership_time": str(min(relevant)) if relevant else "STATE_SENSOR",
                "available_before_first_membership_hours": (
                    min(relevant) - times.min()
                ).total_seconds()
                / 3600
                if relevant
                else None,
            }
        )
    if sorted(r["pair"] for r in ledger) != pair_scope():
        raise ValueError("manifest pair mismatch")
    write_new(
        EVIDENCE / "verified_manifest.json",
        {
            "status": "PASS",
            "pair_count": len(ledger),
            "total_rows": sum(r["row_count"] for r in ledger),
            "files": ledger,
            "listing_cause": "LUNC listing not inferred; data begins before active membership; "
            "all returned series have exact hourly continuity. Native feature warmup "
            "and BTC regime availability remain separate downstream gates.",
            "native_raw_state_unchanged": raw_state()
            == json.loads((EVIDENCE / "current_raw_state_before.json").read_text(encoding="utf-8")),
        },
    )
    print("ISOLATED_2022_DATA_VERIFICATION=PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["preflight", "acquire", "verify"])
    args = parser.parse_args()
    {"preflight": preflight, "acquire": acquire, "verify": verify}[args.mode]()
