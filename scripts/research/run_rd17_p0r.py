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
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.research.run_rd16pit_a1 import canonical, exclusion  # noqa: E402
from spotbot.research.rd16c_common import ROOT  # noqa: E402

SCHEMA_VERSION: Final = "rd17-p0r-source-metric-diagnosis-v1"
SOURCE_COMMIT: Final = "aa893f3c71a9d67801174505653e89c753dc13b9"
STAGE: Final = "RD17_P0R_SOURCE_METRIC_DIAGNOSIS"
ENDPOINT: Final = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
METRICS: Final = ("CapMrktCurUSD", "CapMrktEstUSD")
SNAPSHOT_DATES: Final = (
    "2021-05-09",
    "2022-06-26",
    "2023-10-22",
    "2024-03-10",
)
POLICIES: Final = (
    "CURRENT_ONLY",
    "ESTIMATED_ONLY",
    "CURRENT_THEN_ESTIMATED_FALLBACK",
)
PAGE_SIZE: Final = 10_000
MAX_PAGES: Final = 20
MAX_RETRIES: Final = 6
REQUEST_TIMEOUT_SECONDS: Final = 90
USER_AGENT: Final = "akah-bot-rd17-p0r/1.0"
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00Z")

P0_ROOT: Final = ROOT / "data" / "research" / "rd17_p0"
P0R_ROOT: Final = ROOT / "data" / "research" / "rd17_p0r"
RAW_ROOT: Final = P0R_ROOT / "raw"
REPORTS_ROOT: Final = ROOT / "reports" / "research"


class P0RError(RuntimeError):
    pass


def utc(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def finite(value: object, *, field: str) -> float:
    if isinstance(value, bool):
        raise P0RError(f"{field} cannot be boolean.")
    try:
        numeric = float(cast(str | int | float, value))
    except (TypeError, ValueError) as error:
        raise P0RError(f"{field} must be numeric.") from error
    if not math.isfinite(numeric):
        raise P0RError(f"{field} must be finite.")
    return numeric


def scalar_int(value: object, *, field: str) -> int:
    numeric = finite(value, field=field)
    if not numeric.is_integer():
        raise P0RError(f"{field} must be integer-compatible.")
    return int(numeric)


def is_missing_scalar(value: object) -> bool:
    return bool(pd.isna(cast(Any, value)))


def records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], frame.to_dict(orient="records"))


def json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, pd.Timestamp):
        return utc(value).isoformat()
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
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


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    elif path.suffix == ".csv":
        frame.to_csv(path, index=False, lineterminator="\n")
    else:
        raise P0RError(f"Unsupported output path: {path}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_parameters(
    snapshot_date: str,
    next_page_token: str | None = None,
) -> dict[str, str]:
    parameters = {
        "assets": "*",
        "metrics": ",".join(METRICS),
        "frequency": "1d",
        "start_time": snapshot_date,
        "end_time": snapshot_date,
        "end_inclusive": "true",
        "page_size": str(PAGE_SIZE),
        "paging_from": "start",
        "sort": "asset",
        "ignore_unsupported_errors": "true",
        "ignore_forbidden_errors": "true",
        "null_as_zero": "false",
    }
    if next_page_token:
        parameters["next_page_token"] = next_page_token
    return parameters


def request_url(
    snapshot_date: str,
    next_page_token: str | None = None,
) -> str:
    query = urllib.parse.urlencode(request_parameters(snapshot_date, next_page_token))
    return f"{ENDPOINT}?{query}"


def validate_request_url(url: str, snapshot_date: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "community-api.coinmetrics.io"
        or parsed.path != "/v4/timeseries/asset-metrics"
    ):
        raise P0RError(f"Unsafe Coin Metrics URL: {url}")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    token_values = query.get("next_page_token")
    token = token_values[0] if token_values else None
    expected = request_parameters(snapshot_date, token)
    for key, value in expected.items():
        if query.get(key) != [value]:
            raise P0RError(f"Request parameter drift for {key}: {query.get(key)!r}")
    if "2025" in url or "2026" in url:
        raise P0RError("Sealed-period token found in request URL.")


def fetch_page(url: str, snapshot_date: str) -> Mapping[str, Any]:
    validate_request_url(url, snapshot_date)
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
                if scalar_int(response.status, field="http_status") != 200:
                    raise P0RError(f"Coin Metrics returned HTTP {response.status}.")
                payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, Mapping):
                    raise P0RError("Coin Metrics response is not a JSON object.")
                return cast(Mapping[str, Any], payload)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {
                408,
                425,
                429,
                500,
                502,
                503,
                504,
            }:
                body = error.read().decode(
                    "utf-8",
                    errors="replace",
                )[:1000]
                raise P0RError(f"Coin Metrics HTTP {error.code}: {body}") from error
        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as error:
            last_error = error
        if attempt + 1 < MAX_RETRIES:
            time.sleep(float(2**attempt))
    raise P0RError(f"Coin Metrics request failed after retries: {last_error}")


def acquire_snapshot(
    snapshot_date: str,
) -> tuple[list[dict[str, Any]], dict[str, object]]:
    rows: list[dict[str, Any]] = []
    token: str | None = None
    seen_tokens: set[str] = set()
    page_count = 0
    while True:
        page_count += 1
        if page_count > MAX_PAGES:
            raise P0RError("Coin Metrics pagination exceeded limit.")
        payload = fetch_page(
            request_url(snapshot_date, token),
            snapshot_date,
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise P0RError("Coin Metrics response lacks data list.")
        for raw in data:
            if isinstance(raw, Mapping):
                rows.append(dict(raw))
        raw_token = payload.get("next_page_token")
        if raw_token in (None, ""):
            break
        token = str(raw_token)
        if token in seen_tokens:
            raise P0RError("Coin Metrics pagination token repeated.")
        seen_tokens.add(token)
    return rows, {
        "snapshot_date": snapshot_date,
        "page_count": page_count,
        "raw_row_count": len(rows),
        "request_url_without_token": request_url(snapshot_date),
    }


def optional_positive(
    record: Mapping[str, Any],
    metric: str,
) -> float | None:
    raw = record.get(metric)
    if raw is None:
        return None
    try:
        value = finite(raw, field=metric)
    except P0RError:
        return None
    return value if value > 0.0 else None


def canonicalize(
    acquired: Sequence[tuple[str, list[dict[str, Any]]]],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for requested_date, records_for_date in acquired:
        expected = pd.Timestamp(requested_date, tz="UTC")
        for record in records_for_date:
            asset = str(record.get("asset") or "").strip().lower()
            raw_time = record.get("time")
            if not asset or raw_time is None:
                continue
            observed = utc(raw_time).normalize()
            if observed != expected:
                raise P0RError(
                    f"Unexpected Coin Metrics date {observed} for request {requested_date}."
                )
            symbol = canonical(asset)
            reason = exclusion(asset)
            rows.append(
                {
                    "snapshot_date": observed,
                    "source_asset": asset,
                    "canonical_symbol": symbol,
                    "exclusion_reason": reason,
                    "current_market_cap_usd": optional_positive(
                        record,
                        "CapMrktCurUSD",
                    ),
                    "estimated_market_cap_usd": optional_positive(
                        record,
                        "CapMrktEstUSD",
                    ),
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise P0RError("Coin Metrics acquisition produced no rows.")
    return frame.sort_values(
        ["snapshot_date", "source_asset"],
        kind="stable",
    ).reset_index(drop=True)


def metric_value(
    row: Mapping[str, object],
    policy: str,
) -> tuple[float | None, str | None]:
    current_raw = row.get("current_market_cap_usd")
    estimated_raw = row.get("estimated_market_cap_usd")
    current = (
        finite(current_raw, field="current_market_cap_usd")
        if current_raw is not None and not is_missing_scalar(current_raw)
        else None
    )
    estimated = (
        finite(estimated_raw, field="estimated_market_cap_usd")
        if estimated_raw is not None and not is_missing_scalar(estimated_raw)
        else None
    )
    if policy == "CURRENT_ONLY":
        return current, "CapMrktCurUSD" if current is not None else None
    if policy == "ESTIMATED_ONLY":
        return (
            estimated,
            "CapMrktEstUSD" if estimated is not None else None,
        )
    if policy == "CURRENT_THEN_ESTIMATED_FALLBACK":
        if current is not None:
            return current, "CapMrktCurUSD"
        if estimated is not None:
            return estimated, "CapMrktEstUSD"
        return None, None
    raise P0RError(f"Unknown metric policy: {policy}")


def build_policy_rankings(raw: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    eligible = raw.loc[raw["canonical_symbol"].notna() & raw["exclusion_reason"].isna()].copy()
    for policy in POLICIES:
        policy_rows: list[dict[str, object]] = []
        for row in records(eligible):
            value, metric_source = metric_value(row, policy)
            if value is None:
                continue
            policy_rows.append(
                {
                    "snapshot_date": utc(row["snapshot_date"]),
                    "policy": policy,
                    "canonical_symbol": str(row["canonical_symbol"]),
                    "market_cap_usd": value,
                    "metric_source": metric_source,
                    "source_asset": str(row["source_asset"]),
                }
            )
        policy_frame = pd.DataFrame(policy_rows)
        if policy_frame.empty:
            continue
        policy_frame = (
            policy_frame.sort_values(
                [
                    "snapshot_date",
                    "canonical_symbol",
                    "market_cap_usd",
                    "source_asset",
                ],
                ascending=[True, True, False, True],
                kind="stable",
            )
            .drop_duplicates(
                ["snapshot_date", "canonical_symbol"],
                keep="first",
            )
            .sort_values(
                [
                    "snapshot_date",
                    "market_cap_usd",
                    "canonical_symbol",
                ],
                ascending=[True, False, True],
                kind="stable",
            )
            .reset_index(drop=True)
        )
        policy_frame["market_cap_rank"] = (
            policy_frame.groupby("snapshot_date", sort=True).cumcount() + 1
        )
        rows.extend(records(policy_frame))
    return pd.DataFrame(rows)


def load_independent_top6() -> pd.DataFrame:
    path = P0_ROOT / "independent-filtered-ranking.csv"
    frame = pd.read_csv(path)
    frame["snapshot_date"] = pd.to_datetime(
        cast(Any, frame["snapshot_date"]),
        utc=True,
        errors="raise",
    ).dt.normalize()
    frame["filtered_rank"] = pd.to_numeric(
        cast(Any, frame["filtered_rank"]),
        errors="raise",
    )
    frame = frame.loc[frame["filtered_rank"].le(6)].copy()
    frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.upper()
    return frame


def load_registered_local() -> pd.DataFrame:
    path = P0_ROOT / "local-top10-snapshots.csv"
    frame = pd.read_csv(path)
    frame["manual_snapshot_date"] = pd.to_datetime(
        cast(Any, frame["manual_snapshot_date"]),
        utc=True,
        errors="raise",
    ).dt.normalize()
    frame["market_cap_usd"] = pd.to_numeric(
        cast(Any, frame["market_cap_usd"]),
        errors="raise",
    )
    frame["market_cap_rank"] = pd.to_numeric(
        cast(Any, frame["market_cap_rank"]),
        errors="raise",
    ).astype(int)
    frame["canonical_symbol"] = frame["canonical_symbol"].astype(str).str.upper()
    return frame


def policy_comparison(
    rankings: pd.DataFrame,
    independent: pd.DataFrame,
    registered: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    comparison_rows: list[dict[str, object]] = []
    ranking_frames: list[pd.DataFrame] = [rankings.copy()]

    registered_rankings = registered.loc[
        registered["market_cap_rank"].le(10),
        [
            "manual_snapshot_date",
            "canonical_symbol",
            "market_cap_usd",
            "market_cap_rank",
        ],
    ].rename(columns={"manual_snapshot_date": "snapshot_date"})
    registered_rankings["policy"] = "REGISTERED_LOCAL_PANEL"
    registered_rankings["metric_source"] = "REGISTERED_VALUE"
    registered_rankings["source_asset"] = registered_rankings["canonical_symbol"].str.lower()
    ranking_frames.append(registered_rankings)
    all_rankings = pd.concat(ranking_frames, ignore_index=True)

    for policy in (*POLICIES, "REGISTERED_LOCAL_PANEL"):
        for date_text in SNAPSHOT_DATES:
            date = pd.Timestamp(date_text, tz="UTC")
            expected = set(
                independent.loc[
                    independent["snapshot_date"].eq(date),
                    "canonical_symbol",
                ].astype(str)
            )
            actual = set(
                all_rankings.loc[
                    all_rankings["snapshot_date"].eq(date)
                    & all_rankings["policy"].eq(policy)
                    & pd.to_numeric(
                        cast(
                            Any,
                            all_rankings["market_cap_rank"],
                        ),
                        errors="raise",
                    ).le(6),
                    "canonical_symbol",
                ].astype(str)
            )
            overlap = expected & actual
            union = expected | actual
            comparison_rows.append(
                {
                    "snapshot_date": date,
                    "policy": policy,
                    "independent_top6": "|".join(sorted(expected)),
                    "policy_top6": "|".join(sorted(actual)),
                    "overlap_count": len(overlap),
                    "exact_set_match": expected == actual,
                    "jaccard_similarity": (len(overlap) / len(union) if union else 0.0),
                    "missing_from_policy": "|".join(sorted(expected - actual)),
                    "extra_in_policy": "|".join(sorted(actual - expected)),
                }
            )
    return all_rankings, pd.DataFrame(comparison_rows)


def independent_coverage(
    raw: pd.DataFrame,
    independent: pd.DataFrame,
) -> pd.DataFrame:
    lookup = {
        (
            utc(row["snapshot_date"]),
            str(row["canonical_symbol"]),
        ): row
        for row in records(
            raw.loc[raw["canonical_symbol"].notna() & raw["exclusion_reason"].isna()]
        )
    }
    rows: list[dict[str, object]] = []
    for row in records(independent):
        key = (
            utc(row["snapshot_date"]),
            str(row["canonical_symbol"]),
        )
        found = lookup.get(key)
        current = found.get("current_market_cap_usd") if found is not None else None
        estimated = found.get("estimated_market_cap_usd") if found is not None else None
        current_available = current is not None and not is_missing_scalar(current)
        estimated_available = estimated is not None and not is_missing_scalar(estimated)
        rows.append(
            {
                "snapshot_date": key[0],
                "canonical_symbol": key[1],
                "independent_filtered_rank": scalar_int(
                    row["filtered_rank"],
                    field="filtered_rank",
                ),
                "coinmetrics_asset_present": found is not None,
                "current_metric_available": current_available,
                "estimated_metric_available": estimated_available,
                "current_market_cap_usd": current,
                "estimated_market_cap_usd": estimated,
                "coverage_failure": (
                    "ASSET_ABSENT"
                    if found is None
                    else ("CURRENT_METRIC_MISSING" if not current_available else "NONE")
                ),
            }
        )
    return pd.DataFrame(rows)


def relative_error(left: float, right: float) -> float:
    denominator = max(abs(right), 1.0)
    return abs(left - right) / denominator


def local_metric_provenance(
    raw: pd.DataFrame,
    registered: pd.DataFrame,
) -> pd.DataFrame:
    lookup = {
        (
            utc(row["snapshot_date"]),
            str(row["canonical_symbol"]),
        ): row
        for row in records(
            raw.loc[raw["canonical_symbol"].notna() & raw["exclusion_reason"].isna()]
        )
    }
    rows: list[dict[str, object]] = []
    for row in records(registered):
        date = utc(row["manual_snapshot_date"])
        symbol = str(row["canonical_symbol"])
        local_value = finite(
            row["market_cap_usd"],
            field="registered_market_cap_usd",
        )
        found = lookup.get((date, symbol))
        current: float | None = None
        estimated: float | None = None
        if found is not None:
            raw_current = found.get("current_market_cap_usd")
            raw_estimated = found.get("estimated_market_cap_usd")
            if raw_current is not None and not is_missing_scalar(raw_current):
                current = finite(
                    raw_current,
                    field="current_market_cap_usd",
                )
            if raw_estimated is not None and not is_missing_scalar(raw_estimated):
                estimated = finite(
                    raw_estimated,
                    field="estimated_market_cap_usd",
                )
        current_error = relative_error(local_value, current) if current is not None else None
        estimated_error = relative_error(local_value, estimated) if estimated is not None else None
        if current_error is None and estimated_error is None:
            inferred = "NO_LIVE_METRIC"
        elif estimated_error is None:
            inferred = "CLOSER_TO_CURRENT"
        elif current_error is None:
            inferred = "CLOSER_TO_ESTIMATED"
        elif current_error <= estimated_error:
            inferred = "CLOSER_TO_CURRENT"
        else:
            inferred = "CLOSER_TO_ESTIMATED"
        rows.append(
            {
                "snapshot_date": date,
                "canonical_symbol": symbol,
                "registered_rank": scalar_int(
                    row["market_cap_rank"],
                    field="registered_rank",
                ),
                "registered_market_cap_usd": local_value,
                "live_current_market_cap_usd": current,
                "live_estimated_market_cap_usd": estimated,
                "relative_error_to_current": current_error,
                "relative_error_to_estimated": estimated_error,
                "inferred_registered_metric": inferred,
            }
        )
    return pd.DataFrame(rows)


def policy_summary(comparison: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for policy, group in comparison.groupby("policy", sort=True):
        rows.append(
            {
                "policy": str(policy),
                "snapshot_count": len(group),
                "exact_top6_match_count": scalar_int(
                    cast(
                        Any,
                        group["exact_set_match"].astype(bool).sum(),
                    ),
                    field="exact_top6_match_count",
                ),
                "minimum_overlap": scalar_int(
                    cast(Any, group["overlap_count"].min()),
                    field="minimum_overlap",
                ),
                "mean_overlap": float(
                    pd.to_numeric(
                        cast(Any, group["overlap_count"]),
                        errors="raise",
                    ).mean()
                ),
                "mean_jaccard_similarity": float(
                    pd.to_numeric(
                        cast(
                            Any,
                            group["jaccard_similarity"],
                        ),
                        errors="raise",
                    ).mean()
                ),
            }
        )
    return pd.DataFrame(rows)


def summary_row(
    summary: pd.DataFrame,
    policy: str,
) -> dict[str, object]:
    matches = summary.loc[summary["policy"].astype(str).eq(policy)]
    if len(matches) != 1:
        raise P0RError(f"Policy summary missing for {policy}.")
    return cast(dict[str, object], matches.iloc[0].to_dict())


def classify(
    summary: pd.DataFrame,
    coverage: pd.DataFrame,
    provenance: pd.DataFrame,
) -> tuple[str, str, dict[str, object]]:
    current = summary_row(summary, "CURRENT_ONLY")
    estimated = summary_row(summary, "ESTIMATED_ONLY")
    fallback = summary_row(
        summary,
        "CURRENT_THEN_ESTIMATED_FALLBACK",
    )
    registered = summary_row(summary, "REGISTERED_LOCAL_PANEL")

    current_exact = scalar_int(
        current["exact_top6_match_count"],
        field="current_exact_top6_match_count",
    )
    missing_current = scalar_int(
        cast(
            Any,
            (~coverage["current_metric_available"].astype(bool)).sum(),
        ),
        field="missing_current_metric_count",
    )
    estimated_closer = scalar_int(
        cast(
            Any,
            provenance["inferred_registered_metric"].astype(str).eq("CLOSER_TO_ESTIMATED").sum(),
        ),
        field="registered_rows_closer_to_estimated",
    )
    gates: dict[str, object] = {
        "current_only_exact_top6_all_four": current_exact == 4,
        "independent_top6_current_coverage_complete": (missing_current == 0),
        "missing_independent_top6_current_metric_count": (missing_current),
        "registered_rows_closer_to_estimated": estimated_closer,
        "current_only_exact_match_count": current_exact,
        "estimated_only_exact_match_count": scalar_int(
            estimated["exact_top6_match_count"],
            field="estimated_exact_top6_match_count",
        ),
        "fallback_exact_match_count": scalar_int(
            fallback["exact_top6_match_count"],
            field="fallback_exact_top6_match_count",
        ),
        "registered_exact_match_count": scalar_int(
            registered["exact_top6_match_count"],
            field="registered_exact_top6_match_count",
        ),
        "current_only_mean_jaccard": finite(
            current["mean_jaccard_similarity"],
            field="current_only_mean_jaccard",
        ),
        "registered_mean_jaccard": finite(
            registered["mean_jaccard_similarity"],
            field="registered_mean_jaccard",
        ),
    }

    if bool(gates["current_only_exact_top6_all_four"]) and bool(
        gates["independent_top6_current_coverage_complete"]
    ):
        return (
            "RD17_P0R_CURRENT_METRIC_AND_SOURCE_CONFIRMED",
            "RD17_P1_FROZEN_ENGINE_FULL_PIT_CANDIDATE_GENERATION",
            gates,
        )
    if missing_current > 0:
        return (
            "RD17_P0R_COINMETRICS_COMMUNITY_COVERAGE_INSUFFICIENT",
            "RD17_P0S_ALTERNATE_PIT_MARKET_CAP_SOURCE_SELECTION",
            gates,
        )
    return (
        "RD17_P0R_MARKET_CAP_SEMANTICS_OR_SOURCE_UNRESOLVED",
        "RD17_P0R_ADDITIONAL_SOURCE_DIAGNOSIS_REQUIRED",
        gates,
    )


def write_reports(final: Mapping[str, object]) -> None:
    gates = cast(Mapping[str, object], final["diagnostic_gates"])
    results = [
        "# RD17-P0R Source and Metric Diagnosis",
        "",
        f"- Decision: `{final['decision']}`",
        f"- Current-only exact Top-6 matches: {gates['current_only_exact_match_count']}/4",
        f"- Registered exact Top-6 matches: {gates['registered_exact_match_count']}/4",
        f"- Missing independent Top-6 current metrics: "
        f"{gates['missing_independent_top6_current_metric_count']}",
        f"- Registered rows closer to estimated metric: "
        f"{gates['registered_rows_closer_to_estimated']}",
        "",
        "The registered current-then-estimated fallback is not accepted as "
        "a circulating-cap universe definition.",
    ]
    decisions = [
        "# RD17-P0R Decision",
        "",
        f"Decision: **{final['decision']}**",
        "",
        f"Next stage: `{final['next_stage']}`",
        "",
        "RD17-P1 candidate generation remains unauthorized unless both "
        "metric semantics and historical Top-6 asset coverage pass.",
        "",
        "No optimization, trading replay, or production authorization was performed.",
    ]
    (REPORTS_ROOT / "rd17-p0r-results-v1.md").write_text(
        "\n".join(results) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (REPORTS_ROOT / "rd17-p0r-decisions-v1.md").write_text(
        "\n".join(decisions) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def output_manifest(paths: Sequence[Path]) -> dict[str, object]:
    return {
        "schema_version": "rd17-p0r-output-manifest-v1",
        "entries": {
            path.relative_to(ROOT).as_posix(): {
                "sha256": file_sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in paths
        },
    }


def run_p0r() -> dict[str, object]:
    P0R_ROOT.mkdir(parents=True, exist_ok=True)
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    p0_report_path = P0_ROOT / "rd17-p0-final-report-v1.json"
    if not p0_report_path.is_file():
        raise P0RError("RD17-P0 final report is missing.")
    p0_report = cast(
        dict[str, object],
        json.loads(p0_report_path.read_text(encoding="utf-8")),
    )
    if p0_report.get("decision") != ("RD17_P0_UNIVERSE_METHOD_REJECTED"):
        raise P0RError("P0R requires the recorded P0 rejection.")

    acquired: list[tuple[str, list[dict[str, Any]]]] = []
    request_rows: list[dict[str, object]] = []
    for snapshot_date in SNAPSHOT_DATES:
        rows, metadata = acquire_snapshot(snapshot_date)
        acquired.append((snapshot_date, rows))
        request_rows.append(metadata)

    raw = canonicalize(acquired)
    if bool(
        pd.to_datetime(
            cast(Any, raw["snapshot_date"]),
            utc=True,
        )
        .ge(SEALED_CUTOFF)
        .any()
    ):
        raise P0RError("Sealed cutoff violation in acquired data.")

    independent = load_independent_top6()
    registered = load_registered_local()
    rankings = build_policy_rankings(raw)
    all_rankings, comparison = policy_comparison(
        rankings,
        independent,
        registered,
    )
    coverage = independent_coverage(raw, independent)
    provenance = local_metric_provenance(raw, registered)
    summary = policy_summary(comparison)
    decision, next_stage, gates = classify(
        summary,
        coverage,
        provenance,
    )

    output_frames = {
        RAW_ROOT / "coinmetrics-four-snapshot-metrics.parquet": raw,
        P0R_ROOT / "metric-policy-rankings.csv": all_rankings,
        P0R_ROOT / "metric-policy-comparison.csv": comparison,
        P0R_ROOT / "metric-policy-summary.csv": summary,
        P0R_ROOT / "independent-top6-coverage.csv": coverage,
        P0R_ROOT / "local-metric-provenance.csv": provenance,
    }
    for path, frame in output_frames.items():
        write_frame(path, frame)

    request_manifest = {
        "schema_version": "rd17-p0r-request-manifest-v1",
        "endpoint": ENDPOINT,
        "metrics": list(METRICS),
        "snapshot_dates": list(SNAPSHOT_DATES),
        "requests": request_rows,
        "network_hosts_accessed": ["community-api.coinmetrics.io"],
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    write_json(P0R_ROOT / "request-manifest.json", request_manifest)

    final: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE,
        "source_commit": SOURCE_COMMIT,
        "decision": decision,
        "next_stage": next_stage,
        "p0_decision": p0_report["decision"],
        "diagnostic_gates": gates,
        "registered_fallback_policy": ("CURRENT_THEN_ESTIMATED_FALLBACK"),
        "registered_fallback_valid_for_circulating_cap": False,
        "metric_semantics_diagnosed": True,
        "alternate_source_required": (
            next_stage == "RD17_P0S_ALTERNATE_PIT_MARKET_CAP_SOURCE_SELECTION"
        ),
        "candidate_generation_stage_authorized": (
            next_stage == "RD17_P1_FROZEN_ENGINE_FULL_PIT_CANDIDATE_GENERATION"
        ),
        "rd17_trading_run_authorized": False,
        "optimization_performed": False,
        "production_authorized": False,
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    write_json(
        P0R_ROOT / "rd17-p0r-final-report-v1.json",
        final,
    )
    write_reports(final)

    manifest_inputs = (
        *output_frames.keys(),
        P0R_ROOT / "request-manifest.json",
        P0R_ROOT / "rd17-p0r-final-report-v1.json",
        REPORTS_ROOT / "rd17-p0r-results-v1.md",
        REPORTS_ROOT / "rd17-p0r-decisions-v1.md",
    )
    write_json(
        P0R_ROOT / "output-manifest.json",
        output_manifest(manifest_inputs),
    )

    print(
        json.dumps(
            json_safe(
                {
                    "decision": decision,
                    "next_stage": next_stage,
                    **gates,
                    "metric_semantics_diagnosed": True,
                    "alternate_source_required": final["alternate_source_required"],
                    "candidate_generation_stage_authorized": final[
                        "candidate_generation_stage_authorized"
                    ],
                    "rd17_trading_run_authorized": False,
                    "test_2025_accessed": False,
                    "holdout_2026_accessed": False,
                }
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    if repo != ROOT.resolve():
        raise P0RError(f"Expected repository {ROOT.resolve()}, found {repo}.")
    run_p0r()


if __name__ == "__main__":
    main()
