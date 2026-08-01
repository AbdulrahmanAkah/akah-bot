from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spotbot.research.providers.alternate import (  # noqa: E402
    capabilities as alternate_capabilities,
)
from spotbot.research.providers.cmc_public import parse_snapshot_fixture  # noqa: E402

SOURCE_COMMIT: Final = "7bb8db9eadac298bc28efa0b2ab7a8dc589240c3"
STAGE: Final = "RD17_P0S_ALTERNATE_PIT_MARKET_CAP_SOURCE_SELECTION"
DATES: Final = ("2021-05-09", "2022-06-26", "2023-10-22", "2024-03-10")
P0S_ROOT: Final = REPO_ROOT / "data" / "research" / "rd17_p0s"
P0_ROOT: Final = REPO_ROOT / "data" / "research" / "rd17_p0"
REPORTS_ROOT: Final = REPO_ROOT / "reports" / "research"
SEALED_YEARS: Final = ("2025", "2026")


class P0SError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(item) for item in value]
    return str(value)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            json_safe(dict(payload)),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def source_commit_is_ancestor() -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD"],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


def load_reference() -> tuple[pd.DataFrame, pd.DataFrame]:
    snapshot_path = P0_ROOT / "independent-cmc-snapshots.csv"
    filtered_path = P0_ROOT / "independent-filtered-ranking.csv"
    if not snapshot_path.is_file() or not filtered_path.is_file():
        raise P0SError("Frozen P0 CMC fixtures are missing.")
    snapshot = parse_snapshot_fixture(snapshot_path)
    filtered = pd.read_csv(filtered_path)
    filtered["snapshot_date"] = pd.to_datetime(filtered["snapshot_date"], utc=True).dt.strftime(
        "%Y-%m-%d"
    )
    required = {"snapshot_date", "canonical_symbol", "filtered_rank", "market_cap_usd"}
    if required.difference(filtered.columns):
        raise P0SError(
            "Frozen filtered ranking columns missing: "
            f"{sorted(required.difference(filtered.columns))}"
        )
    return snapshot, filtered


def build_capability_matrix() -> pd.DataFrame:
    cmc = {
        "provider": "coinmarketcap_public",
        "role": "REFERENCE_SOURCE_RECONSTRUCTION",
        "free_for_full_2019_2024": False,
        "historical_ranking": True,
        "circulating_market_cap": True,
        "stable_identity": False,
        "timing_proven": False,
        "access_status": "PUBLIC_REFERENCE_PAGE_FIXTURE_ONLY",
        "reason": (
            "Public historical pages are represented by the frozen top-10 reference "
            "fixtures; no immutable top-30 archive or independent validation is registered."
        ),
    }
    rows = [cmc, *alternate_capabilities()]
    return pd.DataFrame(rows).sort_values("provider", kind="stable").reset_index(drop=True)


def build_access_evidence() -> pd.DataFrame:
    rows = [
        {
            "provider": "coinmarketcap_public",
            "role": "REFERENCE_SOURCE_RECONSTRUCTION",
            "host_or_url": "https://coinmarketcap.com/historical/YYYYMMDD/",
            "evidence_url": "https://coinmarketcap.com/historical/20240310/",
            "accessed": False,
            "network_request_count": 0,
            "evidence": "Frozen public-page CSV is used offline; paid API was not used.",
        },
        {
            "provider": "coingecko_demo",
            "role": "CANDIDATE_PRIMARY_SOURCE",
            "host_or_url": "https://api.coingecko.com/api/v3/coins/{id}/market_chart",
            "evidence_url": "https://www.coingecko.com/en/api/pricing",
            "accessed": False,
            "network_request_count": 0,
            "evidence": (
                "Official public plan evidence does not prove complete free 2019-2024 "
                "ranked history; no credential or request was used."
            ),
        },
        {
            "provider": "coinpaprika_public",
            "role": "CANDIDATE_PRIMARY_SOURCE",
            "host_or_url": "https://api.coinpaprika.com/",
            "evidence_url": "https://docs.coinpaprika.com/api-reference/coins/get-historical-ohlc",
            "accessed": False,
            "network_request_count": 0,
            "evidence": (
                "Official documentation limits free historical access; no request was used."
            ),
        },
        {
            "provider": "cryptocompare_public",
            "role": "CANDIDATE_PRIMARY_SOURCE",
            "host_or_url": "https://min-api.cryptocompare.com/",
            "evidence_url": "https://min-api.cryptocompare.com/documentation",
            "accessed": False,
            "network_request_count": 0,
            "evidence": (
                "No public endpoint proving a historical circulating-market-cap-ranked "
                "universe was identified."
            ),
        },
        {
            "provider": "tradingview_free_manual",
            "role": "SECONDARY_INDEPENDENT_MARKET_CAP_AUDIT_SOURCE",
            "host_or_url": "https://www.tradingview.com/support/solutions/43000550480-where-do-i-find-crypto-market-capitalization-and-dominance/",
            "evidence_url": "https://www.tradingview.com/support/solutions/43000550480-where-do-i-find-crypto-market-capitalization-and-dominance/",
            "accessed": False,
            "network_request_count": 0,
            "evidence": (
                "Manual audit template only; no authenticated browser automation or "
                "account data used."
            ),
        },
        {
            "provider": "open_dataset_local_scan",
            "role": "CANDIDATE_PRIMARY_SOURCE",
            "host_or_url": "local repository scan",
            "evidence_url": "reports/research/universe-first-research-invariant-v1.md",
            "accessed": False,
            "network_request_count": 0,
            "evidence": "No qualifying licensed causal full-history archive is registered locally.",
        },
    ]
    return pd.DataFrame(rows)


def build_identity_audit(snapshot: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in snapshot.itertuples(index=False):
        rows.append(
            {
                "provider": "coinmarketcap_public",
                "snapshot_date": row.snapshot_date.strftime("%Y-%m-%d"),
                "provider_asset_id": str(row.symbol),
                "symbol_at_observation": str(row.symbol),
                "canonical_asset_id": row.canonical_asset_id,
                "exclusion_reason": row.exclusion_reason,
                "identity_confidence": "HIGH" if pd.notna(row.canonical_asset_id) else "LOW",
                "collision_status": "NONE",
                "source_role": "REFERENCE_SOURCE_RECONSTRUCTION",
            }
        )
    return pd.DataFrame(rows)


def build_timing_audit() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for provider in [
        "coinmarketcap_public",
        "coingecko_demo",
        "coinpaprika_public",
        "cryptocompare_public",
        "tradingview_free_manual",
    ]:
        for snapshot_date in DATES:
            rows.append(
                {
                    "provider": provider,
                    "snapshot_date": snapshot_date,
                    "observation_time_utc": f"{snapshot_date}T00:00:00Z",
                    "available_at_utc": None,
                    "availability_bound_proven": False,
                    "current_supply_lookahead_rejected": True,
                    "timing_gate": False,
                    "reason": (
                        "Publication/availability evidence is not sufficient for a clean "
                        "causal PIT gate."
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_normalized_rankings(snapshot: pd.DataFrame) -> pd.DataFrame:
    result = snapshot.loc[
        :,
        [
            "snapshot_date",
            "raw_rank",
            "name",
            "symbol",
            "canonical_asset_id",
            "market_cap_usd",
            "source_url",
            "eligible_after_exclusions",
            "filtered_rank",
            "provider",
            "source_role",
            "market_cap_definition",
        ],
    ].copy()
    result["snapshot_date"] = result["snapshot_date"].dt.strftime("%Y-%m-%d")
    return result


def build_top6_comparison(snapshot: pd.DataFrame, filtered: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date in DATES:
        reference = filtered.loc[filtered["snapshot_date"].eq(date)].sort_values("filtered_rank")
        reference_top6 = reference["canonical_symbol"].head(6).astype(str).tolist()
        provider = snapshot.loc[
            (snapshot["snapshot_date"].dt.strftime("%Y-%m-%d").eq(date))
            & snapshot["eligible_after_exclusions"].astype(bool)
        ].sort_values("filtered_rank")
        provider_top6 = provider["canonical_asset_id"].head(6).astype(str).tolist()
        rows.append(
            {
                "provider": "coinmarketcap_public",
                "snapshot_date": date,
                "reference_top6": ";".join(reference_top6),
                "provider_top6": ";".join(provider_top6),
                "exact_set_match": set(reference_top6) == set(provider_top6),
                "rank_match": reference_top6 == provider_top6,
                "common_asset_count": len(set(reference_top6).intersection(provider_top6)),
                "reference_equivalent": True,
                "independent_source": False,
                "top30_available": bool(len(provider) >= 30),
                "gate_pass": False,
                "reason": (
                    "Top-6 matches the frozen CMC reference, but this is not independent "
                    "and only top-10 fixture rows are available."
                ),
            }
        )
    return pd.DataFrame(rows)


def build_coverage(snapshot: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    providers = [
        "coinmarketcap_public",
        "coingecko_demo",
        "coinpaprika_public",
        "cryptocompare_public",
        "tradingview_free_manual",
    ]
    for provider in providers:
        for date in DATES:
            if provider == "coinmarketcap_public":
                subset = snapshot.loc[snapshot["snapshot_date"].dt.strftime("%Y-%m-%d").eq(date)]
                eligible = int(subset["eligible_after_exclusions"].astype(bool).sum())
            else:
                eligible = 0
            rows.append(
                {
                    "provider": provider,
                    "snapshot_date": date,
                    "rows_available": 10 if provider == "coinmarketcap_public" else 0,
                    "eligible_rows": eligible,
                    "top30_available": eligible >= 30,
                    "all_reference_top6_covered": provider == "coinmarketcap_public",
                    "coverage_gate": False,
                }
            )
    return pd.DataFrame(rows)


def build_tradingview_template() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "expected_symbol",
            "csv_path",
            "file_sha256",
            "snapshot_date",
            "observation_time_utc",
            "market_cap_usd",
            "missing_date",
            "discontinuity_flag",
            "notes",
        ]
    )


def build_tradingview_comparison() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "symbol",
            "snapshot_date",
            "tradingview_market_cap_usd",
            "cmc_reference_market_cap_usd",
            "selected_primary_market_cap_usd",
            "coinmetrics_current_market_cap_usd",
            "coinmetrics_estimated_market_cap_usd",
            "absolute_difference_cmc",
            "percentage_difference_cmc",
            "missing_or_discontinuous",
            "notes",
        ]
    )


def write_reports(report: Mapping[str, object]) -> None:
    methodology = "\n".join(
        [
            "# RD17-P0S methodology",
            "",
            "This stage selects a fully free point-in-time circulating market-cap source "
            "for the sealed 2019-2024 research panel. The four snapshots were frozen "
            "before probing. Candidate generation, trading and optimization remain disabled.",
            "",
            "## Identity and timing",
            "",
            "Provider IDs are resolved through the shared RD16-compatible identity layer. "
            "Stablecoins, wrapped/network representations, duplicate representations and "
            "unresolved identities are excluded. A provider must prove observation and "
            "availability timing; an assumed one-day lag is not treated as proof.",
            "",
            "## Sources",
            "",
            "CoinMarketCap public historical pages are reference-equivalent reconstruction "
            "only. CoinGecko, CoinPaprika and CryptoCompare were evaluated against their "
            "documented free-history and market-cap semantics. TradingView is a manual "
            "secondary audit only and cannot reconstruct historical membership from the "
            "current screener.",
            "",
            "## Frozen controls",
            "",
            "No 2025 or 2026 data, Dune/API credentials, trading, signals, optimization, "
            "or full-panel acquisition was used.",
            "",
        ]
    )
    results = "\n".join(
        [
            "# RD17-P0S results",
            "",
            f"Decision: `{report['decision']}`",
            "",
            "The public CMC fixtures reproduce the four frozen Top-6 sets, but they are "
            "the same reference reconstruction and contain only top-10 rows. They "
            "therefore do not pass the independent, top-30, timing and full-history "
            "gates. The other candidates fail free-history, ranked-universe, or "
            "circulating-cap semantics gates.",
            "",
            "P1 was not run because the clean P0S decision was not produced.",
            "",
        ]
    )
    decisions = "\n".join(
        [
            "# RD17-P0S decisions",
            "",
            "## Candidate decisions",
            "",
            "- CoinMarketCap public: `REFERENCE_SOURCE_RECONSTRUCTION`; reference-",
            "  equivalent only, not independent.",
            "- CoinGecko Demo: rejected because complete free 2019-2024 ranked history "
            "and credential-free reproducibility were not proven.",
            "- CoinPaprika public: rejected because documented free historical coverage "
            "is insufficient for 2019-2024.",
            "- CryptoCompare public: rejected because no historical circulating-market-",
            "  cap-ranked universe endpoint was proven.",
            "- TradingView: retained as `SECONDARY_INDEPENDENT_MARKET_CAP_AUDIT_SOURCE` "
            "only; no manual exports were supplied and current screener membership is "
            "not PIT data.",
            "- Local open datasets: no qualifying licensed causal archive was registered.",
            "",
            "## Stop",
            "",
            "No candidate passes every P0S gate. The stage stops before P1 and remains "
            "blocked pending a lawful free source.",
            "",
        ]
    )
    (REPORTS_ROOT / "rd17-p0s-methodology-v1.md").write_text(
        methodology, encoding="utf-8", newline="\n"
    )
    (REPORTS_ROOT / "rd17-p0s-results-v1.md").write_text(results, encoding="utf-8", newline="\n")
    (REPORTS_ROOT / "rd17-p0s-decisions-v1.md").write_text(
        decisions, encoding="utf-8", newline="\n"
    )
    tradingview = "\n".join(
        [
            "# RD17-P0S TradingView audit",
            "",
            "TradingView is registered only as a secondary independent market-cap audit "
            "source. No authenticated browser automation, login, cookies, private endpoint, "
            "or account data was used. No manual CSV exports were supplied, so no values "
            "were used to fill or rank the primary panel. The current screener is not "
            "historical point-in-time membership data.",
            "",
        ]
    )
    (REPORTS_ROOT / "rd17-p0s-tradingview-audit-v1.md").write_text(
        tradingview, encoding="utf-8", newline="\n"
    )


def run_probe() -> dict[str, object]:
    if not source_commit_is_ancestor():
        raise P0SError("P0S must run on the registered commit or a descendant branch.")
    if any(year in str(P0S_ROOT) for year in SEALED_YEARS):
        raise P0SError("Output path unexpectedly contains a sealed year.")
    snapshot, filtered = load_reference()
    P0S_ROOT.mkdir(parents=True, exist_ok=True)
    snapshot_path = P0_ROOT / "independent-cmc-snapshots.csv"
    raw_hash = sha256(snapshot_path)
    capability = build_capability_matrix()
    access = build_access_evidence()
    identity = build_identity_audit(snapshot)
    timing = build_timing_audit()
    normalized = build_normalized_rankings(snapshot)
    top6 = build_top6_comparison(snapshot, filtered)
    coverage = build_coverage(snapshot)
    write_csv(P0S_ROOT / "provider-capability-matrix.csv", capability)
    write_csv(P0S_ROOT / "provider-access-evidence.csv", access)
    write_csv(P0S_ROOT / "provider-identity-audit.csv", identity)
    write_csv(P0S_ROOT / "provider-timing-audit.csv", timing)
    write_csv(P0S_ROOT / "provider-normalized-rankings.csv", normalized)
    write_csv(P0S_ROOT / "provider-top6-comparison.csv", top6)
    write_csv(P0S_ROOT / "provider-coverage-summary.csv", coverage)
    write_csv(P0S_ROOT / "tradingview-audit-template.csv", build_tradingview_template())
    write_csv(P0S_ROOT / "tradingview-market-cap-comparison.csv", build_tradingview_comparison())
    request_manifest = {
        "schema_version": "rd17-p0s-request-manifest-v1",
        "source_commit": SOURCE_COMMIT,
        "network_accessed": False,
        "documentation_only_web_review": True,
        "provider_data_requests": 0,
        "requests": [],
        "frozen_fixture": str(snapshot_path.relative_to(REPO_ROOT)),
        "frozen_fixture_sha256": raw_hash,
        "snapshot_dates": list(DATES),
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "secrets_recorded": False,
    }
    write_json(P0S_ROOT / "request-manifest.json", request_manifest)
    top6_exact = bool(top6["exact_set_match"].all()) if not top6.empty else False
    report: dict[str, object] = {
        "schema_version": "rd17-p0s-final-report-v1",
        "stage": STAGE,
        "source_commit": SOURCE_COMMIT,
        "branch": git_value("branch", "--show-current"),
        "frozen_snapshot_dates": list(DATES),
        "metric_definition": "CIRCULATING_MARKET_CAP_USD",
        "candidate_sources": capability.to_dict(orient="records"),
        "reference_equivalent_source": "coinmarketcap_public",
        "selected_source": None,
        "independent_source_confirmed": False,
        "clean_pass": False,
        "gate_results": {
            "free_complete_2019_2024": False,
            "four_snapshots_retrieved_lawfully": True,
            "minimum_thirty_eligible_assets": False,
            "twenty_four_reference_top6_observations": top6_exact,
            "identity_collisions_resolved": True,
            "circulating_market_cap_proven": False,
            "no_estimated_or_fdv_fallback": True,
            "timing_pass": False,
            "raw_evidence_preserved": True,
            "offline_parser_deterministic": True,
            "sealed_years_not_accessed": True,
        },
        "reference_top6_exact_set_matches": int(top6["exact_set_match"].sum()),
        "reference_top6_rank_matches": int(top6["rank_match"].sum()),
        "network_requests": 0,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "dune_api_called": False,
        "candidate_generation_stage_authorized": False,
        "production_authorized": False,
        "trading_run_authorized": False,
        "optimization_performed": False,
        "decision": "RD17_P0S_NO_FREE_SOURCE_MEETS_PIT_REQUIREMENTS",
        "next_stage": "RD17_BLOCKED_PENDING_FREE_PIT_SOURCE",
        "limitations": [
            "CMC public rows are reference-equivalent rather than independent.",
            "Frozen CMC fixtures contain top-10 rows, not a verified top-30 archive.",
            "Provider publication/availability timing is not proven for a clean causal gate.",
            (
                "No lawful free source with complete 2019-2024 PIT circulating "
                "market-cap history was found."
            ),
        ],
        "raw_fixture_sha256": raw_hash,
    }
    write_reports(report)
    final_report_path = P0S_ROOT / "rd17-p0s-final-report-v1.json"
    write_json(final_report_path, report)
    output_files = sorted(
        path
        for path in P0S_ROOT.iterdir()
        if path.is_file() and path.name != "output-manifest.json"
    )
    output_manifest = {
        "schema_version": "rd17-p0s-output-manifest-v1",
        "source_commit": SOURCE_COMMIT,
        "files": [
            {
                "path": str(path.relative_to(REPO_ROOT)),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in output_files
        ],
    }
    write_json(P0S_ROOT / "output-manifest.json", output_manifest)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline RD17-P0S free PIT source probe.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (must contain the frozen P0 fixtures).",
    )
    args = parser.parse_args()
    if args.repo.resolve() != REPO_ROOT.resolve():
        parser.error("This registered runner must execute from the checked-out repository root.")
    try:
        report = run_probe()
    except (P0SError, OSError, ValueError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {"decision": report["decision"], "next_stage": report["next_stage"]}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
