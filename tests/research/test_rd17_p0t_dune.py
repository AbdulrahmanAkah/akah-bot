from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from spotbot.research.rd17_p0t_dune import (
    ASSETS,
    DECISION_COVERAGE,
    DECISION_PASS,
    DuneProbeError,
    build_supply_price_sql,
    build_top_holders_sql,
    classify_probe,
    load_frozen_snapshot_dates,
    validate_sql_safety,
)


def test_future_dates_rejected(tmp_path: Path) -> None:
    path = tmp_path / "snapshots.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["snapshot_date"])
        writer.writeheader()
        writer.writerow({"snapshot_date": "2024-01-01"})
        writer.writerow({"snapshot_date": "2025-01-01"})
    with pytest.raises(DuneProbeError, match="Forbidden"):
        load_frozen_snapshot_dates(path)


def test_sql_is_bounded() -> None:
    dates = (date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1), date(2024, 1, 1))
    supply = build_supply_price_sql(dates)
    holders = build_top_holders_sql(dates)
    validate_sql_safety(supply)
    validate_sql_safety(holders)
    assert "2025-" not in supply and "2026-" not in supply
    assert "balances.erc20_daily" in supply
    assert "prices_external.day" in supply
    assert "UNCLASSIFIED_HISTORICALLY" in holders


def _supply_rows(dates: tuple[date, ...]) -> list[dict[str, object]]:
    return [
        {
            "asset_id": asset.asset_id,
            "snapshot_date": day.isoformat(),
            "onchain_supply_component": 1.0,
            "external_price_usd": 1.0,
        }
        for day in dates
        for asset in ASSETS
    ]


def _holder_rows(dates: tuple[date, ...]) -> list[dict[str, object]]:
    return [
        {"asset_id": asset.asset_id, "snapshot_date": day.isoformat()}
        for day in dates
        for asset in ASSETS
    ]


def test_complete_component_probe_never_proves_circulation() -> None:
    dates = (date(2021, 1, 1), date(2022, 1, 1))
    report = classify_probe(dates, _supply_rows(dates), _holder_rows(dates))
    assert report["decision"] == DECISION_PASS
    assert report["circulating_supply_proven"] is False
    assert report["top30_universe_reconstruction_authorized"] is False


def test_missing_price_fails_coverage() -> None:
    dates = (date(2021, 1, 1),)
    rows = _supply_rows(dates)
    rows[0]["external_price_usd"] = None
    report = classify_probe(dates, rows, _holder_rows(dates))
    assert report["decision"] == DECISION_COVERAGE
