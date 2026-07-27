"""Run RD04-D0 point-in-time universe readiness diagnostics."""

from __future__ import annotations

import math
import subprocess
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ams_md01_common import atomic_json, atomic_text, load_registered_data

from spotbot.research.ams_md01_momentum import FOLDS, simulate_md01_fold
from spotbot.research.rd01_dominance import (
    decode_json_bytes,
    fetch_coinmetrics_dominance_history,
)
from spotbot.research.rd01_dominance_tagging import (
    financial_fingerprint,
    records_frame,
)
from spotbot.research.rd04_pit_universe import (
    DECISION_BLOCKED,
    DECISION_EXPAND,
    DECISION_READY,
    SCHEMA_VERSION,
    TARGET_UNIVERSE_SIZE,
    build_candidate_frequency,
    build_readiness_decision,
    build_symbol_contribution,
    build_weekly_market_cap_snapshots,
    parse_market_cap_panel,
    sha256_bytes,
    validate_rd04_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
RAW_PATH = (
    ROOT
    / "data"
    / "research"
    / "rd01"
    / "dominance"
    / "raw"
    / "coinmetrics-community-market-cap-panel-2021-2024.json"
)
SNAPSHOT_CSV = REPORTS / "ams-rd04-d0-weekly-market-cap-candidates-v1.csv"
SNAPSHOT_SUMMARY_CSV = REPORTS / "ams-rd04-d0-weekly-snapshot-summary-v1.csv"
FREQUENCY_CSV = REPORTS / "ams-rd04-d0-candidate-frequency-v1.csv"
GAP_MANIFEST_CSV = REPORTS / "ams-rd04-d0-local-data-gap-manifest-v1.csv"
CONTRIBUTION_CSV = REPORTS / "ams-rd04-d0-m05-symbol-contribution-v1.csv"
REPORT_JSON = REPORTS / "ams-rd04-d0-pit-universe-readiness-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d0-pit-universe-readiness-v1.md"
FINAL_COPY = ROOT / "RD04_D0_RESULT_FOR_CHATGPT.md"
EXPECTED_TRADES = 147


def source_commit() -> str:
    """Return the exact source commit used to generate evidence."""

    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def finite(value: Any) -> Any:
    """Convert pandas and numpy values into strict JSON values."""

    if isinstance(value, Mapping):
        return {str(key): finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return finite(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    """Write deterministic CSV with ISO timestamps."""

    output = frame.copy()
    for column in output.columns:
        if pd.api.types.is_datetime64_any_dtype(output[column].dtype):
            output[column] = pd.to_datetime(output[column], utc=True, errors="raise").map(
                lambda value: value.isoformat()
            )
    atomic_text(path, output.to_csv(index=False, lineterminator="\n"))


def load_market_cap_bytes() -> tuple[bytes, str]:
    """Reuse RD01 raw evidence, downloading only when the local copy is absent."""

    if RAW_PATH.is_file():
        return RAW_PATH.read_bytes(), f"file://{RAW_PATH.relative_to(ROOT).as_posix()}"
    url, content = fetch_coinmetrics_dominance_history()
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_bytes(content)
    return content, url


def registered_symbol_intersection(
    frames: Mapping[str, pd.DataFrame],
) -> list[str]:
    """Return symbols available in every registered local dataset."""

    symbol_sets: list[set[str]] = []
    for name in ("four_hour", "eight_hour", "daily", "availability"):
        frame = frames[name]
        if "symbol" not in frame.columns:
            raise RuntimeError(f"Registered dataset {name} lacks symbol.")
        symbol_sets.append(set(frame["symbol"].astype(str).str.upper()))
    common = set.intersection(*symbol_sets)
    return sorted(common)


def markdown(report: Mapping[str, Any]) -> str:
    """Render the compact review copy."""

    readiness = report["readiness"]
    validation = report["validation"]
    concentration = report["m05_symbol_concentration"]
    gaps = report["largest_data_gaps"]
    lines = [
        "# AMS RD04-D0 — Point-in-Time Universe Readiness",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{readiness['decision']}`",
        f"- Reason: `{readiness['reason']}`",
        f"- Weekly snapshots: `{readiness['snapshot_count']}`",
        f"- Complete top-{TARGET_UNIVERSE_SIZE} snapshots: "
        f"`{readiness['complete_snapshot_count']}`",
        f"- Missing local assets: `{readiness['missing_local_asset_count']}`",
        f"- Minimum registered overlap: `{readiness['minimum_registered_overlap_rate']:.6f}`",
        f"- Median registered overlap: `{readiness['median_registered_overlap_rate']:.6f}`",
        f"- Financial invariance: `{validation['financial_invariance']}`",
        "- Universe change authorized: `NO`",
        "- Trade logic changed: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Existing M05 contribution concentration",
        "",
        f"- Symbols with trades: `{concentration['symbol_count']}`",
        f"- Top-1 share of positive symbol PnL: `{concentration['top_1_positive_pnl_share']}`",
        f"- Top-3 share of positive symbol PnL: `{concentration['top_3_positive_pnl_share']}`",
        f"- Absolute-PnL HHI: `{concentration['absolute_pnl_hhi']}`",
        "",
        "## Largest local-data gaps",
        "",
        "| Asset | Weekly appearances | Best rank | Mean rank |",
        "|---|---:|---:|---:|",
    ]
    for record in gaps:
        lines.append(
            "| "
            f"`{record['canonical_symbol']}` | "
            f"{record['snapshot_appearances']} | "
            f"{record['best_rank']} | "
            f"{float(record['mean_rank']):.3f} |"
        )
    lines.extend(
        [
            "",
            "## Decision meaning",
            "",
            f"- `{DECISION_READY}`: market-cap candidates and all required local "
            "OHLCV/availability data are complete; only then may D1 replay research run.",
            f"- `{DECISION_EXPAND}`: the market-cap history is usable, but the local "
            "dataset must be expanded before any point-in-time universe replay.",
            f"- `{DECISION_BLOCKED}`: the market-cap panel itself is incomplete.",
            "",
            "## Interpretation boundary",
            "",
            "- D0 is a data-readiness and survivor-concentration audit only.",
            "- Raw market-cap rank does not prove venue tradability or strategy eligibility.",
            "- No fixed-universe member is removed and no new asset is traded.",
            "- No ranking, alignment, weight, entry, exit, or portfolio cash is changed.",
            "- No 2025 test data or 2026 holdout data are accessed.",
            "- No production, live trading, MD02, Kelly, leverage, pyramiding, or "
            "averaging down is authorized.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    frames, dataset_hashes = load_registered_data()
    registered_symbols = registered_symbol_intersection(frames)
    raw_bytes, raw_url = load_market_cap_bytes()
    payload = decode_json_bytes(raw_bytes, source="Coin Metrics RD04")
    panel = parse_market_cap_panel(payload)
    candidates, snapshot_summary = build_weekly_market_cap_snapshots(
        panel,
        registered_symbols,
    )
    frequency = build_candidate_frequency(candidates)
    gap_manifest = frequency.loc[~frequency["local_data_available"].astype(bool)].copy()

    fold_trades: list[pd.DataFrame] = []
    fingerprints: list[dict[str, Any]] = []
    for fold_id, start, end in FOLDS:
        result = simulate_md01_fold(
            four_hour=frames["four_hour"],
            daily=frames["daily"],
            eight_hour=frames["eight_hour"],
            availability=frames["availability"],
            variant_id="MD01-M05",
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
            transaction_cost=0.002,
        )
        before = financial_fingerprint(result)
        trade_frame = records_frame(tuple(result.trades))
        trade_frame.insert(0, "fold_id", fold_id)
        after = financial_fingerprint(result)
        if result.status != "PASS":
            raise RuntimeError(f"Fold {fold_id} is not reconciled: {result.status}")
        if before != after:
            raise RuntimeError(f"RD04-D0 mutated fold {fold_id}.")
        fold_trades.append(trade_frame)
        fingerprints.append(
            {
                "fold_id": fold_id,
                "before": before,
                "after": after,
                "invariant": before == after,
                "trade_count": len(result.trades),
            }
        )

    trades = pd.concat(fold_trades, ignore_index=True)
    contribution, concentration = build_symbol_contribution(trades)
    financial_invariance = all(bool(record["invariant"]) for record in fingerprints)
    validation = validate_rd04_evidence(
        candidates,
        snapshot_summary,
        trades,
        expected_trade_count=EXPECTED_TRADES,
        registered_symbol_count=len(registered_symbols),
        financial_invariance=financial_invariance,
    )
    if validation["status"] != "COMPLETE":
        raise RuntimeError(f"RD04-D0 validation failed: {validation}")

    readiness = build_readiness_decision(snapshot_summary, frequency)
    largest_gaps = (
        gap_manifest.sort_values(
            ["snapshot_appearances", "mean_rank", "canonical_symbol"],
            ascending=[False, True, True],
            kind="stable",
        )
        .head(20)
        .to_dict(orient="records")
    )
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D0",
        "status": "COMPLETE",
        "source_commit": source_commit(),
        "variant_id": "MD01-M05",
        "upstream": {
            "rd03_evidence_commit": "15940b3aed531a5698da5e15f74e3c820eda77a2",
            "rd02_d1_evidence_commit": "36864598014094fedf1c900b05e834b126a0fd2f",
            "md01_final_decision": "REVISE_UNIVERSE_WITHOUT_2025",
        },
        "raw_market_cap_source": {
            "url": raw_url,
            "bytes": len(raw_bytes),
            "sha256": sha256_bytes(raw_bytes),
            "panel_rows": len(panel),
            "panel_assets": int(panel["asset"].nunique()),
        },
        "dataset_hashes": dataset_hashes,
        "registered_symbols": registered_symbols,
        "registered_symbol_count": len(registered_symbols),
        "validation": validation,
        "financial_fingerprints": fingerprints,
        "readiness": readiness,
        "m05_symbol_concentration": concentration,
        "largest_data_gaps": largest_gaps,
        "outputs": {
            "weekly_candidates": SNAPSHOT_CSV.relative_to(ROOT).as_posix(),
            "weekly_snapshot_summary": SNAPSHOT_SUMMARY_CSV.relative_to(ROOT).as_posix(),
            "candidate_frequency": FREQUENCY_CSV.relative_to(ROOT).as_posix(),
            "local_data_gap_manifest": GAP_MANIFEST_CSV.relative_to(ROOT).as_posix(),
            "m05_symbol_contribution": CONTRIBUTION_CSV.relative_to(ROOT).as_posix(),
        },
        "authorizations": {
            "rd04_d1_pit_universe_replay_research_authorized": bool(
                readiness["rd04_d1_pit_universe_replay_research_authorized"]
            ),
            "universe_change_authorized": False,
            "ranking_change_authorized": False,
            "entry_change_authorized": False,
            "weight_change_authorized": False,
            "exit_change_authorized": False,
            "ati_v1_authorized": False,
            "production_ready": False,
            "live_ready": False,
        },
        "safety": {
            "trade_logic_changed": False,
            "portfolio_simulation_changed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
            "kelly_used": False,
            "leverage_used": False,
            "pyramiding_authorized": False,
            "averaging_down_authorized": False,
        },
        "generated_at": datetime.now(tz=UTC).isoformat(),
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    write_csv(SNAPSHOT_CSV, candidates)
    write_csv(SNAPSHOT_SUMMARY_CSV, snapshot_summary)
    write_csv(FREQUENCY_CSV, frequency)
    write_csv(GAP_MANIFEST_CSV, gap_manifest)
    write_csv(CONTRIBUTION_CSV, contribution)
    atomic_json(REPORT_JSON, finite(report))
    review = markdown(report)
    atomic_text(REPORT_MD, review)
    atomic_text(FINAL_COPY, review)

    print("RD04_D0_STATUS=COMPLETE")
    print(f"DECISION={readiness['decision']}")
    print(f"SNAPSHOT_COUNT={readiness['snapshot_count']}")
    print(f"COMPLETE_SNAPSHOTS={readiness['complete_snapshot_count']}")
    print(f"PANEL_ASSETS={report['raw_market_cap_source']['panel_assets']}")
    print(f"MISSING_LOCAL_ASSETS={readiness['missing_local_asset_count']}")
    print(
        "RD04_D1_PIT_UNIVERSE_REPLAY_RESEARCH_AUTHORIZED="
        f"{readiness['rd04_d1_pit_universe_replay_research_authorized']}"
    )
    print("FINANCIAL_INVARIANCE=True")
    print("UNIVERSE_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
