from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from spotbot.research.rd17_p0t_dune import (
    ASSETS,
    DuneClient,
    DuneProbeError,
    build_supply_price_sql,
    build_top_holders_sql,
    canonical_json_bytes,
    classify_probe,
    load_frozen_snapshot_dates,
    result_rows,
    sha256_bytes,
)


def atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(content)
    temp.replace(path)


def atomic_text(path: Path, content: str) -> None:
    atomic_bytes(path, content.encode("utf-8"))


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    columns = sorted({str(key) for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in columns})


def git_head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, encoding="utf-8"
    ).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--api-key-env", default="DUNE_API_KEY")
    parser.add_argument("--max-snapshot-count", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.repo.resolve()
    output = root / "data" / "research" / "rd17_p0t_dune"
    snapshot_csv = root / "data" / "research" / "rd17_p0" / "independent-cmc-snapshots.csv"
    dates = load_frozen_snapshot_dates(snapshot_csv)
    if len(dates) > args.max_snapshot_count:
        raise DuneProbeError(
            f"Expected <= {args.max_snapshot_count} frozen dates, found {len(dates)}"
        )
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise DuneProbeError(f"Set {args.api_key_env}; the key is never persisted.")

    supply_sql = build_supply_price_sql(dates)
    holders_sql = build_top_holders_sql(dates)
    atomic_text(output / "supply-price-probe.sql", supply_sql)
    atomic_text(output / "top-holders-probe.sql", holders_sql)

    client = DuneClient(api_key)
    supply_raw = client.run_sql(supply_sql)
    holders_raw = client.run_sql(holders_sql)
    supply_bytes = canonical_json_bytes(supply_raw)
    holders_bytes = canonical_json_bytes(holders_raw)
    atomic_bytes(output / "raw" / "dune-supply-price-response.json", supply_bytes)
    atomic_bytes(output / "raw" / "dune-top-holders-response.json", holders_bytes)

    supply_rows = result_rows(supply_raw)
    holder_rows = result_rows(holders_raw)
    write_csv(output / "dune-supply-price-components.csv", supply_rows)
    write_csv(output / "dune-historical-top-holders.csv", holder_rows)

    report = classify_probe(dates, supply_rows, holder_rows)
    report.update(
        {
            "source_commit": git_head(root),
            "frozen_snapshot_dates": [item.isoformat() for item in dates],
            "probe_assets": [item.asset_id for item in ASSETS],
            "raw_supply_response_sha256": sha256_bytes(supply_bytes),
            "raw_holders_response_sha256": sha256_bytes(holders_bytes),
            "dune_api_key_persisted": False,
            "dune_performance_tier": "small",
        }
    )
    atomic_bytes(output / "rd17-p0t-dune-final-report-v1.json", canonical_json_bytes(report))
    result_md = "\n".join(
        [
            "# RD17-P0T-DUNE Results",
            "",
            f"- Decision: `{report['decision']}`",
            f"- Frozen dates: `{', '.join(report['frozen_snapshot_dates'])}`",
            f"- Supply/price rows: `{report['observed_supply_price_rows']}/{report['expected_asset_snapshot_rows']}`",
            f"- Supply component coverage: `{report['supply_component_coverage_passed']}`",
            f"- External price coverage: `{report['external_price_coverage_passed']}`",
            f"- Historical holder coverage: `{report['historical_top_holder_coverage_passed']}`",
            "- Circulating supply proven: `False`",
            "- Top-30 reconstruction authorized: `False`",
            "",
        ]
    )
    atomic_text(root / "reports" / "research" / "rd17-p0t-dune-results-v1.md", result_md)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DuneProbeError as error:
        print(f"RD17-P0T-DUNE BLOCKED: {error}", file=sys.stderr)
        raise SystemExit(2) from error
