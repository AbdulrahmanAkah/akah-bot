from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.run_rd16pit_a1 import (  # noqa: E402
    bool_count,
    bool_mean,
    build_weekly_membership,
    classify_decision,
    descriptive_stability,
    discover_panels,
    find_v3_ledger,
    leave_one_out,
    leave_top_trades_out,
    load_a0_attribution,
    load_safe_panels,
    masked_numeric_sum,
    merge_a0_and_v3,
    normalize_v3_ledger,
    resolution_summary,
    resolve_membership,
    scalar_int,
    scenario_net_pnl,
    scenario_summary,
    status_masks,
    summarize_group,
    unresolved_year_symbol_summary,
    write_csv,
    write_json,
)

SCHEMA_VERSION: Final = "rd16-pit-a1b-historical-membership-remediation-v1"
SOURCE_COMMIT: Final = "5d7594ab8f5745502a7c34aa50111294b119a815"
API_ROOT: Final = "https://community-api.coinmetrics.io/v4"
ENDPOINT: Final = f"{API_ROOT}/timeseries/asset-metrics"
START_DATE: Final = "2018-12-30"
END_DATE: Final = "2020-12-31"
EARLIEST_ALLOWED: Final = pd.Timestamp("2018-12-30T00:00:00Z")
LATEST_ALLOWED_EXCLUSIVE: Final = pd.Timestamp("2021-01-01T00:00:00Z")
PAGE_SIZE: Final = 10_000
MAX_PAGES: Final = 250
MAX_ROWS: Final = 1_000_000
REQUEST_TIMEOUT_SECONDS: Final = 90
MAX_RETRIES: Final = 6
USER_AGENT: Final = "akah-bot-rd16pit-a1b/1.0"
METRICS: Final = ("CapMrktCurUSD", "CapMrktEstUSD")


class A1BError(RuntimeError):
    pass


def scalar_float(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise A1BError(f"{field} cannot be boolean.")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise A1BError(f"{field} is not numeric: {value!r}") from error
    if not math.isfinite(result):
        raise A1BError(f"{field} is not finite: {value!r}")
    return result


def request_parameters(next_page_token: str | None = None) -> dict[str, str]:
    parameters = {
        "assets": "*",
        "metrics": ",".join(METRICS),
        "frequency": "1d",
        "start_time": START_DATE,
        "end_time": END_DATE,
        "end_inclusive": "true",
        "page_size": str(PAGE_SIZE),
        "paging_from": "start",
        "sort": "time",
        "ignore_unsupported_errors": "true",
        "ignore_forbidden_errors": "true",
        "null_as_zero": "false",
    }
    if next_page_token:
        parameters["next_page_token"] = next_page_token
    return parameters


def request_url(next_page_token: str | None = None) -> str:
    return f"{ENDPOINT}?{urllib.parse.urlencode(request_parameters(next_page_token))}"


def validate_request_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "community-api.coinmetrics.io":
        raise A1BError(f"Unsafe Coin Metrics URL: {url}")
    if parsed.path != "/v4/timeseries/asset-metrics":
        raise A1BError(f"Unexpected Coin Metrics endpoint path: {parsed.path}")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    token_values = query.get("next_page_token")
    token = token_values[0] if token_values else None
    expected = request_parameters(token)
    for key, value in expected.items():
        if query.get(key) != [value]:
            raise A1BError(f"Request parameter drift for {key}: {query.get(key)!r}")
    if "2025" in url or "2026" in url:
        raise A1BError("Sealed-period token found in acquisition URL.")


def fetch_json_page(url: str) -> Mapping[str, Any]:
    validate_request_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            with urllib.request.urlopen(
                request,
                timeout=REQUEST_TIMEOUT_SECONDS,
            ) as response:
                status = scalar_int(response.status, field="http_status")
                if status != 200:
                    raise A1BError(f"Coin Metrics returned HTTP {status}.")
                raw = response.read()
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, Mapping):
                    raise A1BError("Coin Metrics response is not a JSON object.")
                return cast(Mapping[str, Any], payload)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {408, 425, 429, 500, 502, 503, 504}:
                body = error.read().decode("utf-8", errors="replace")[:1000]
                raise A1BError(f"Coin Metrics HTTP {error.code}: {body}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
        if attempt + 1 < MAX_RETRIES:
            time.sleep(float(2**attempt))
    raise A1BError(f"Coin Metrics request failed after retries: {last_error}")


def acquire_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    token: str | None = None
    page_count = 0
    tokens_seen: set[str] = set()

    while True:
        page_count += 1
        if page_count > MAX_PAGES:
            raise A1BError(f"Pagination exceeded {MAX_PAGES} pages.")
        payload = fetch_json_page(request_url(token))
        data = payload.get("data")
        if not isinstance(data, list):
            raise A1BError("Coin Metrics response is missing a data list.")
        for record in data:
            if isinstance(record, Mapping):
                rows.append(dict(record))
        if len(rows) > MAX_ROWS:
            raise A1BError(f"Acquisition exceeded {MAX_ROWS} rows.")

        raw_token = payload.get("next_page_token")
        if raw_token in (None, ""):
            break
        token = str(raw_token)
        if token in tokens_seen:
            raise A1BError("Coin Metrics pagination token repeated.")
        tokens_seen.add(token)

    metadata = {
        "page_count": page_count,
        "raw_row_count": len(rows),
        "request_start": START_DATE,
        "request_end": END_DATE,
        "page_size": PAGE_SIZE,
        "metrics": list(METRICS),
        "assets_selector": "*",
        "frequency": "1d",
    }
    return rows, metadata


def positive_metric(record: Mapping[str, Any], metric: str) -> float | None:
    raw = record.get(metric)
    if raw is None:
        return None
    try:
        value = scalar_float(raw, field=metric)
    except A1BError:
        return None
    return value if value > 0.0 else None


def canonicalize_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    canonical: list[dict[str, object]] = []
    for record in rows:
        asset = str(record.get("asset") or "").strip().lower()
        raw_time = record.get("time")
        if not asset or raw_time is None:
            continue
        timestamp = pd.Timestamp(cast(Any, raw_time))
        timestamp = (
            timestamp.tz_localize("UTC")
            if timestamp.tzinfo is None
            else timestamp.tz_convert("UTC")
        )
        if not EARLIEST_ALLOWED <= timestamp < LATEST_ALLOWED_EXCLUSIVE:
            raise A1BError(f"Out-of-window timestamp received: {timestamp.isoformat()}")
        current = positive_metric(record, "CapMrktCurUSD")
        estimated = positive_metric(record, "CapMrktEstUSD")
        if current is not None:
            market_cap = current
            source = "CapMrktCurUSD"
        elif estimated is not None:
            market_cap = estimated
            source = "CapMrktEstUSD"
        else:
            continue
        canonical.append(
            {
                "asset": asset,
                "time": timestamp,
                "market_cap_usd": market_cap,
                "market_cap_source": source,
            }
        )

    frame = pd.DataFrame(
        canonical,
        columns=["asset", "time", "market_cap_usd", "market_cap_source"],
    )
    if frame.empty:
        raise A1BError("Coin Metrics acquisition produced no usable market-cap rows.")
    frame = (
        frame.sort_values(["asset", "time", "market_cap_source"], kind="stable")
        .drop_duplicates(["asset", "time"], keep="first")
        .reset_index(drop=True)
    )
    first_time = pd.Timestamp(cast(Any, frame["time"].min()))
    last_time = pd.Timestamp(cast(Any, frame["time"].max()))
    if first_time < EARLIEST_ALLOWED:
        raise A1BError("Canonical panel starts before the approved boundary.")
    if last_time >= LATEST_ALLOWED_EXCLUSIVE:
        raise A1BError("Canonical panel reaches the sealed boundary.")
    return frame


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_coverage(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for raw_asset, group in panel.groupby("asset", sort=True):
        sources = group["market_cap_source"].astype(str)
        rows.append(
            {
                "asset": str(raw_asset),
                "row_count": len(group),
                "first_time": pd.Timestamp(cast(Any, group["time"].min())),
                "last_time": pd.Timestamp(cast(Any, group["time"].max())),
                "current_cap_rows": bool_count(sources.eq("CapMrktCurUSD")),
                "estimated_cap_rows": bool_count(sources.eq("CapMrktEstUSD")),
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["row_count", "asset"], ascending=[False, True], kind="stable")
        .reset_index(drop=True)
    )


def complete_membership_only(
    weekly: pd.DataFrame,
    snapshots: pd.DataFrame,
) -> pd.DataFrame:
    complete_times = pd.to_datetime(
        cast(Any, snapshots.loc[snapshots["snapshot_complete"].astype(bool), "rebalance_time"]),
        utc=True,
    )
    complete_weeks = set(pd.DatetimeIndex(complete_times).tolist())
    if weekly.empty or not complete_weeks:
        return weekly.iloc[0:0].copy()
    return weekly.loc[
        pd.to_datetime(weekly["rebalance_time"], utc=True).isin(complete_weeks)
    ].copy()


def decision_for_a1b(
    attribution: pd.DataFrame,
    scenarios: pd.DataFrame,
) -> tuple[str, str, list[str]]:
    decision, next_stage, reasons = classify_decision(attribution, scenarios)
    if next_stage == "RD16_PIT_A1B_HISTORICAL_MEMBERSHIP_DATA_REMEDIATION":
        next_stage = "RD16_PIT_A1C_ALTERNATE_SOURCE_OR_RESEARCH_STOP"
    return decision, next_stage, reasons


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()

    root = repo / "data" / "research" / "rd16pit_a1b"
    raw_root = root / "raw"
    reports = repo / "reports" / "research"
    raw_root.mkdir(parents=True, exist_ok=True)

    raw_rows, acquisition = acquire_rows()
    panel = canonicalize_rows(raw_rows)
    panel_path = raw_root / "coinmetrics-community-market-cap-panel-2018-2020.parquet"
    panel.to_parquet(panel_path, index=False)

    coverage = asset_coverage(panel)
    acquisition.update(
        {
            "schema_version": "rd16-pit-a1b-acquisition-manifest-v1",
            "endpoint": ENDPOINT,
            "usable_row_count": len(panel),
            "unique_asset_count": len(set(panel["asset"].astype(str))),
            "first_timestamp": pd.Timestamp(cast(Any, panel["time"].min())).isoformat(),
            "last_timestamp": pd.Timestamp(cast(Any, panel["time"].max())).isoformat(),
            "panel_path": panel_path.relative_to(repo).as_posix(),
            "panel_sha256": sha256_file(panel_path),
            "network_host_allowlist": ["community-api.coinmetrics.io"],
            "sealed_cutoff": "2021-01-01T00:00:00Z",
            "sealed_cutoff_respected": True,
            "catalog_endpoint_accessed": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        }
    )
    write_json(root / "acquisition-manifest.json", acquisition)
    write_csv(root / "panel-asset-coverage.csv", coverage)

    discovery = discover_panels(repo)
    combined_panel, panel_status = load_safe_panels(repo, discovery)
    weekly, snapshots = build_weekly_membership(combined_panel)
    causal_weekly = complete_membership_only(weekly, snapshots)

    v3 = normalize_v3_ledger(pd.read_parquet(find_v3_ledger(repo)))
    a0 = load_a0_attribution(repo)
    merged = merge_a0_and_v3(a0, v3)
    attribution = resolve_membership(merged, causal_weekly)

    scenarios = scenario_summary(attribution)
    by_year = summarize_group(attribution, ["year"], status_column="fixed6_pit_status")
    by_symbol = summarize_group(
        attribution,
        ["symbol"],
        status_column="fixed6_pit_status",
    )
    by_engine = summarize_group(
        attribution,
        ["engine_id"],
        status_column="fixed6_pit_status",
    )
    unresolved = unresolved_year_symbol_summary(attribution)
    leave_symbol = leave_one_out(attribution, "symbol")
    leave_year = leave_one_out(attribution, "year")
    leave_top = leave_top_trades_out(attribution)
    bootstrap, ess = descriptive_stability(attribution)
    resolution = resolution_summary(attribution, snapshots, panel_status)

    decision, next_stage, reasons = decision_for_a1b(attribution, scenarios)
    masks = status_masks(attribution, "fixed6_pit_status")
    unresolved_mask = masks["unresolved"]
    eligible_mask = masks["eligible"]
    non_pit_mask = masks["non_pit"]
    resolved_ratio = bool_mean(~unresolved_mask)

    write_csv(root / "historical-panel-discovery.csv", discovery)
    write_csv(root / "weekly-membership-2019-2024.csv", weekly)
    write_csv(root / "weekly-snapshot-summary.csv", snapshots)
    write_csv(root / "membership-resolution-summary.csv", resolution)
    write_csv(root / "trade-membership-attribution.csv", attribution)
    write_csv(root / "attribution-by-year.csv", by_year)
    write_csv(root / "attribution-by-symbol.csv", by_symbol)
    write_csv(root / "attribution-by-engine.csv", by_engine)
    write_csv(root / "unresolved-by-year-symbol.csv", unresolved)
    write_csv(root / "bounded-scenarios.csv", scenarios)
    write_csv(root / "leave-one-symbol-out.csv", leave_symbol)
    write_csv(root / "leave-one-year-out.csv", leave_year)
    write_csv(root / "leave-top-trades-out.csv", leave_top)
    write_csv(root / "descriptive-bootstrap.csv", bootstrap)
    write_csv(root / "effective-sample-size.csv", ess)

    final = {
        "schema_version": SCHEMA_VERSION,
        "decision": decision,
        "source_commit": SOURCE_COMMIT,
        "audit_scope": "A1B_HISTORICAL_MEMBERSHIP_DATA_REMEDIATION",
        "v3_trade_count": len(attribution),
        "membership_resolved_trade_count": bool_count(~unresolved_mask),
        "membership_unresolved_trade_count": bool_count(unresolved_mask),
        "membership_resolved_trade_ratio": resolved_ratio,
        "pit_eligible_trade_count": bool_count(eligible_mask),
        "non_pit_trade_count": bool_count(non_pit_mask),
        "unresolved_trade_count": bool_count(unresolved_mask),
        "pit_eligible_net_pnl": masked_numeric_sum(attribution, eligible_mask, "net_pnl"),
        "non_pit_net_pnl": masked_numeric_sum(attribution, non_pit_mask, "net_pnl"),
        "unresolved_net_pnl": masked_numeric_sum(attribution, unresolved_mask, "net_pnl"),
        "observed_net_pnl": scenario_net_pnl(scenarios, "OBSERVED_FIXED6"),
        "confirmed_pit_only_net_pnl": scenario_net_pnl(
            scenarios,
            "CONFIRMED_PIT_ONLY",
        ),
        "strict_bounded_net_pnl": scenario_net_pnl(
            scenarios,
            "STRICT_REMOVE_ALL_UNCERTAIN_POSITIVE",
        ),
        "acquired_panel_path": panel_path.relative_to(repo).as_posix(),
        "acquired_panel_sha256": acquisition["panel_sha256"],
        "acquired_panel_rows": len(panel),
        "acquired_panel_assets": len(set(panel["asset"].astype(str))),
        "acquired_panel_first_timestamp": pd.Timestamp(cast(Any, panel["time"].min())).isoformat(),
        "acquired_panel_last_timestamp": pd.Timestamp(cast(Any, panel["time"].max())).isoformat(),
        "complete_weekly_snapshot_count": bool_count(snapshots["snapshot_complete"].astype(bool)),
        "total_weekly_snapshot_count": len(snapshots),
        "complete_2019_2020_snapshot_count": bool_count(
            snapshots.loc[
                pd.to_datetime(snapshots["rebalance_time"], utc=True).dt.year.isin([2019, 2020]),
                "snapshot_complete",
            ].astype(bool)
        ),
        "decision_reasons": reasons,
        "next_stage": next_stage,
        "dynamic_v3_replay_performed": False,
        "bootstrap_role": "DESCRIPTIVE_ONLY_NOT_A_CONFIRMATION_GATE",
        "benjamini_hochberg_applied": False,
        "network_hosts_accessed": ["community-api.coinmetrics.io"],
        "catalog_endpoint_accessed": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
        "optimization_performed": False,
        "production_authorized": False,
    }
    write_json(root / "rd16pit-a1b-final-report-v1.json", final)

    results_lines = [
        "# RD16-PIT-A1B Historical Membership Remediation",
        "",
        f"- Decision: **{decision}**",
        f"- V3 trades audited: {len(attribution)}",
        f"- Membership resolved ratio: {resolved_ratio:.4%}",
        f"- Acquired panel rows: {len(panel)}",
        f"- Acquired panel assets: {len(set(panel['asset'].astype(str)))}",
        (
            "- Complete weekly snapshots: "
            f"{bool_count(snapshots['snapshot_complete'].astype(bool))}/"
            f"{len(snapshots)}"
        ),
        f"- PIT-eligible net PnL: {final['pit_eligible_net_pnl']:.2f}",
        f"- Non-PIT net PnL: {final['non_pit_net_pnl']:.2f}",
        f"- Unresolved net PnL: {final['unresolved_net_pnl']:.2f}",
        f"- Strict bounded net PnL: {final['strict_bounded_net_pnl']:.2f}",
        "",
        "Only the Coin Metrics Community asset-metrics endpoint was accessed,",
        "with hard request bounds ending on 2020-12-31. No catalog endpoint,",
        "2025 test data, or 2026 holdout data was accessed.",
        "",
        "A1B remains a ledger attribution and bounded audit. It does not replay",
        "portfolio routing, cash, drawdown, or concurrent position admission.",
        "",
        f"Next stage: `{next_stage}`",
        "",
    ]
    decision_lines = [
        "# RD16-PIT-A1B Decision",
        "",
        f"Decision: **{decision}**",
        "",
        "## Reasons",
        "",
        *[f"- {reason}" for reason in reasons],
        "",
        "## Restrictions",
        "",
        "- RD16-U remains stopped.",
        "- A2 is not inferred from filtered ledger arithmetic.",
        "- No 2025 or 2026 data was accessed.",
        "- Bootstrap output is descriptive only.",
        "",
    ]
    (reports / "rd16-pit-a1b-results-v1.md").write_text(
        "\n".join(results_lines),
        encoding="utf-8",
        newline="\n",
    )
    (reports / "rd16-pit-a1b-decisions-v1.md").write_text(
        "\n".join(decision_lines),
        encoding="utf-8",
        newline="\n",
    )

    print(
        json.dumps(
            {
                "decision": decision,
                "v3_trade_count": len(attribution),
                "membership_resolved_trade_ratio": resolved_ratio,
                "pit_eligible_trade_count": bool_count(eligible_mask),
                "non_pit_trade_count": bool_count(non_pit_mask),
                "unresolved_trade_count": bool_count(unresolved_mask),
                "pit_eligible_net_pnl": final["pit_eligible_net_pnl"],
                "non_pit_net_pnl": final["non_pit_net_pnl"],
                "unresolved_net_pnl": final["unresolved_net_pnl"],
                "strict_bounded_net_pnl": final["strict_bounded_net_pnl"],
                "acquired_panel_rows": len(panel),
                "acquired_panel_assets": len(set(panel["asset"].astype(str))),
                "complete_weekly_snapshot_count": bool_count(
                    snapshots["snapshot_complete"].astype(bool)
                ),
                "next_stage": next_stage,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
