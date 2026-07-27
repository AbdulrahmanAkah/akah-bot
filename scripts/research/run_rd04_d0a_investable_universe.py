"""Run RD04-D0A investable-universe normalization diagnostics."""

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
    default_fetcher,
)
from spotbot.research.rd01_dominance_tagging import financial_fingerprint
from spotbot.research.rd04_investable_universe import (
    DECISION_BLOCKED,
    DECISION_EXPAND,
    DECISION_READY,
    SCHEMA_VERSION,
    TARGET_UNIVERSE_SIZE,
    build_normalization_decision,
    build_normalized_weekly_snapshots,
    build_refined_gap_manifest,
    normalize_market_cap_panel,
    parse_stablecoin_symbols,
    validate_normalized_evidence,
)
from spotbot.research.rd04_pit_universe import (
    parse_market_cap_panel,
    rebalance_schedule,
    sha256_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
MARKET_CAP_RAW = (
    ROOT
    / "data"
    / "research"
    / "rd01"
    / "dominance"
    / "raw"
    / "coinmetrics-community-market-cap-panel-2021-2024.json"
)
STABLECOIN_RAW = (
    ROOT
    / "data"
    / "research"
    / "rd04"
    / "eligibility"
    / "raw"
    / "defillama-stablecoins-catalogue.json"
)
STABLECOIN_URL = "https://stablecoins.llama.fi/stablecoins?includePrices=false"

CANDIDATES_CSV = REPORTS / "ams-rd04-d0a-normalized-weekly-candidates-v1.csv"
SUMMARY_CSV = REPORTS / "ams-rd04-d0a-normalized-snapshot-summary-v1.csv"
IDENTITY_CSV = REPORTS / "ams-rd04-d0a-asset-identity-audit-v1.csv"
STABLECOINS_CSV = REPORTS / "ams-rd04-d0a-stablecoin-symbols-v1.csv"
GAPS_CSV = REPORTS / "ams-rd04-d0a-refined-data-gap-manifest-v1.csv"
REPORT_JSON = REPORTS / "ams-rd04-d0a-investable-universe-normalization-v1.json"
REPORT_MD = REPORTS / "ams-rd04-d0a-investable-universe-normalization-v1.md"
FINAL_COPY = ROOT / "RD04_D0A_RESULT_FOR_CHATGPT.md"
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
    return sorted(set.intersection(*symbol_sets))


def load_stablecoin_catalogue() -> tuple[bytes, str]:
    """Load the frozen catalogue, downloading it only when absent."""

    if STABLECOIN_RAW.is_file():
        return STABLECOIN_RAW.read_bytes(), f"file://{STABLECOIN_RAW.relative_to(ROOT).as_posix()}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "spot-speculation-bot-rd04-d0a/1.0",
    }
    content = default_fetcher(STABLECOIN_URL, headers)
    STABLECOIN_RAW.parent.mkdir(parents=True, exist_ok=True)
    STABLECOIN_RAW.write_bytes(content)
    return content, STABLECOIN_URL


def markdown(report: Mapping[str, Any]) -> str:
    """Render the compact review copy."""

    decision = report["normalization_decision"]
    validation = report["validation"]
    gaps = report["largest_refined_gaps"]
    identity = report["identity_summary"]
    lines = [
        "# AMS RD04-D0A — Investable Universe Normalization",
        "",
        "## Executive result",
        "",
        f"- Status: `{report['status']}`",
        f"- Decision: `{decision['decision']}`",
        f"- Reason: `{decision['reason']}`",
        f"- Weekly snapshots: `{decision['snapshot_count']}`",
        f"- Complete normalized top-{TARGET_UNIVERSE_SIZE} snapshots: "
        f"`{decision['complete_snapshot_count']}`",
        f"- Refined missing local assets: `{decision['missing_local_asset_count']}`",
        f"- Stablecoin symbols frozen: `{identity['stablecoin_symbol_count']}`",
        f"- Raw asset identities excluded as stablecoins: "
        f"`{identity['stablecoin_raw_asset_count']}`",
        f"- Raw asset identities canonicalized: `{identity['aliased_raw_asset_count']}`",
        f"- Minimum registered overlap: `{decision['minimum_registered_overlap_rate']:.6f}`",
        f"- Financial invariance: `{validation['financial_invariance']}`",
        "- Universe change authorized: `NO`",
        "- Trade logic changed: `NO`",
        "- ATI-V1 authorized: `NO`",
        "",
        "## Largest refined local-data gaps",
        "",
        "| Canonical asset | Weekly appearances | Best rank | Mean rank | Source forms |",
        "|---|---:|---:|---:|---|",
    ]
    for record in gaps:
        lines.append(
            "| "
            f"`{record['canonical_symbol']}` | "
            f"{record['snapshot_appearances']} | "
            f"{record['best_rank']} | "
            f"{float(record['mean_rank']):.3f} | "
            f"`{record['source_asset_forms']}` |"
        )
    lines.extend(
        [
            "",
            "## Identity contract",
            "",
            "- Stablecoins are removed before ranking.",
            "- Coin Metrics network-specific suffix forms are mapped to the parent asset.",
            "- WBTC/WETH and registered migration aliases are collapsed to one parent identity.",
            "- Duplicate forms use one maximum market-cap observation; they are never summed.",
            "- Ranking is rebuilt after exclusions so every snapshot still contains 30 assets.",
            "",
            "## Decision meaning",
            "",
            f"- `{DECISION_EXPAND}` authorizes only RD04-D0B data-acquisition research.",
            f"- `{DECISION_READY}` authorizes only RD04-D1 point-in-time replay research.",
            f"- `{DECISION_BLOCKED}` means identity or normalized coverage is incomplete.",
            "",
            "## Interpretation boundary",
            "",
            "- No fixed-universe member is removed from the registered simulation.",
            "- No normalized candidate is traded in D0A.",
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
    if not MARKET_CAP_RAW.is_file():
        raise RuntimeError("RD04-D0A requires the frozen RD01 Coin Metrics market-cap payload.")

    market_cap_bytes = MARKET_CAP_RAW.read_bytes()
    market_cap_payload = decode_json_bytes(market_cap_bytes, source="Coin Metrics RD04-D0A")
    raw_panel = parse_market_cap_panel(market_cap_payload)

    stablecoin_bytes, stablecoin_url = load_stablecoin_catalogue()
    stablecoin_payload = decode_json_bytes(stablecoin_bytes, source="DefiLlama RD04-D0A")
    stablecoin_symbols = parse_stablecoin_symbols(stablecoin_payload)

    canonical_panel, identity_audit = normalize_market_cap_panel(
        raw_panel,
        stablecoin_symbols,
    )
    candidates, snapshot_summary = build_normalized_weekly_snapshots(
        canonical_panel,
        registered_symbols,
        rebalance_schedule(),
    )
    gap_manifest = build_refined_gap_manifest(candidates)
    decision = build_normalization_decision(snapshot_summary, gap_manifest)

    fingerprints: list[dict[str, Any]] = []
    observed_trade_count = 0
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
        after = financial_fingerprint(result)
        if result.status != "PASS":
            raise RuntimeError(f"Fold {fold_id} is not reconciled: {result.status}")
        if before != after:
            raise RuntimeError(f"RD04-D0A mutated fold {fold_id}.")
        observed_trade_count += len(result.trades)
        fingerprints.append(
            {
                "fold_id": fold_id,
                "before": before,
                "after": after,
                "invariant": before == after,
                "trade_count": len(result.trades),
            }
        )

    financial_invariance = all(bool(record["invariant"]) for record in fingerprints)
    validation = validate_normalized_evidence(
        candidates,
        snapshot_summary,
        expected_trade_count=EXPECTED_TRADES,
        observed_trade_count=observed_trade_count,
        financial_invariance=financial_invariance,
    )
    if validation["status"] != "COMPLETE":
        raise RuntimeError(f"RD04-D0A validation failed: {validation}")

    stablecoin_frame = pd.DataFrame({"stablecoin_symbol": sorted(stablecoin_symbols)})
    identity_summary = {
        "raw_asset_count": int(identity_audit["asset"].nunique()),
        "canonical_investable_asset_count": int(canonical_panel["canonical_asset"].nunique()),
        "stablecoin_symbol_count": len(stablecoin_symbols),
        "stablecoin_raw_asset_count": int(identity_audit["stablecoin_excluded"].astype(bool).sum()),
        "aliased_raw_asset_count": int(identity_audit["normalization_rule"].ne("IDENTITY").sum()),
    }
    largest_gaps = gap_manifest.head(20).to_dict(orient="records")

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "research_stage": "RD04-D0A",
        "status": "COMPLETE",
        "source_commit": source_commit(),
        "variant_id": "MD01-M05",
        "upstream": {
            "rd04_d0_evidence_commit": "893cfa3d66cc54fad294944f514847560148b82f",
            "rd03_evidence_commit": "15940b3aed531a5698da5e15f74e3c820eda77a2",
            "md01_final_decision": "REVISE_UNIVERSE_WITHOUT_2025",
        },
        "raw_sources": {
            "coinmetrics_market_cap": {
                "path": MARKET_CAP_RAW.relative_to(ROOT).as_posix(),
                "bytes": len(market_cap_bytes),
                "sha256": sha256_bytes(market_cap_bytes),
            },
            "defillama_stablecoin_catalogue": {
                "url": stablecoin_url,
                "path": STABLECOIN_RAW.relative_to(ROOT).as_posix(),
                "bytes": len(stablecoin_bytes),
                "sha256": sha256_bytes(stablecoin_bytes),
            },
        },
        "dataset_hashes": dataset_hashes,
        "registered_symbols": registered_symbols,
        "identity_summary": identity_summary,
        "normalization_decision": decision,
        "validation": validation,
        "financial_fingerprints": fingerprints,
        "largest_refined_gaps": largest_gaps,
        "outputs": {
            "normalized_weekly_candidates": CANDIDATES_CSV.relative_to(ROOT).as_posix(),
            "normalized_snapshot_summary": SUMMARY_CSV.relative_to(ROOT).as_posix(),
            "asset_identity_audit": IDENTITY_CSV.relative_to(ROOT).as_posix(),
            "stablecoin_symbols": STABLECOINS_CSV.relative_to(ROOT).as_posix(),
            "refined_data_gap_manifest": GAPS_CSV.relative_to(ROOT).as_posix(),
        },
        "authorizations": {
            "rd04_d0b_data_expansion_research_authorized": bool(
                decision["rd04_d0b_data_expansion_research_authorized"]
            ),
            "rd04_d1_pit_universe_replay_research_authorized": bool(
                decision["rd04_d1_pit_universe_replay_research_authorized"]
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
    write_csv(CANDIDATES_CSV, candidates)
    write_csv(SUMMARY_CSV, snapshot_summary)
    write_csv(IDENTITY_CSV, identity_audit)
    write_csv(STABLECOINS_CSV, stablecoin_frame)
    write_csv(GAPS_CSV, gap_manifest)
    atomic_json(REPORT_JSON, finite(report))
    review = markdown(report)
    atomic_text(REPORT_MD, review)
    atomic_text(FINAL_COPY, review)

    print("RD04_D0A_STATUS=COMPLETE")
    print(f"DECISION={decision['decision']}")
    print(f"SNAPSHOT_COUNT={decision['snapshot_count']}")
    print(f"NORMALIZED_CANDIDATE_ROWS={len(candidates)}")
    print(f"REFINED_MISSING_LOCAL_ASSETS={decision['missing_local_asset_count']}")
    print(
        "RD04_D0B_DATA_EXPANSION_RESEARCH_AUTHORIZED="
        f"{decision['rd04_d0b_data_expansion_research_authorized']}"
    )
    print(
        "RD04_D1_PIT_UNIVERSE_REPLAY_RESEARCH_AUTHORIZED="
        f"{decision['rd04_d1_pit_universe_replay_research_authorized']}"
    )
    print("FINANCIAL_INVARIANCE=True")
    print("UNIVERSE_CHANGE_AUTHORIZED=False")
    print("TRADE_LOGIC_CHANGED=False")
    print("ATI_V1_AUTHORIZED=False")


if __name__ == "__main__":
    main()
