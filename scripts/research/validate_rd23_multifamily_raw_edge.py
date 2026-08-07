from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd23_multifamily_raw_edge import (  # noqa: E402
    DATA_CUTOFF,
    FAMILIES,
    FORWARD_HORIZONS,
    PERIODS,
)

OUTPUT = Path("data/research/rd23_p2_runtime")
OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "family-signal-funnel.csv",
    "signal-events.csv",
    "family-overlap-matrix.csv",
    "overlap-summary.json",
    "forward-event-returns.csv",
    "raw-edge-metrics.csv",
    "family-horizon-hard-gates.csv",
    "family-selection.csv",
    "qualified-family-freeze.json",
    "rd23-p2-multifamily-raw-edge-report-v1.json",
)


class ValidationError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--offline", action="store_true")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValidationError(f"JSON object expected: {path}")
    return value


def validate_manifest(output: Path) -> None:
    manifest = load_json(output / "output-manifest.json")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValidationError("manifest files list missing")
    observed_names = [str(item["path"]) for item in files]
    if observed_names != list(OUTPUT_NAMES):
        raise ValidationError("manifest output file order/scope drifted")
    for item in files:
        path = output / str(item["path"])
        if not path.is_file():
            raise ValidationError(f"manifest file missing: {path}")
        if int(item["bytes"]) != path.stat().st_size:
            raise ValidationError(f"manifest byte mismatch: {path}")
        if str(item["sha256"]) != sha256(path):
            raise ValidationError(f"manifest SHA mismatch: {path}")
    for field in (
        "portfolio_replay_executed",
        "position_sizing_executed",
        "historical_exit_simulation_executed",
        "2022_2023_used_for_selection",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if manifest.get(field) is not False:
            raise ValidationError(f"manifest prohibited flag not false: {field}")


def expected_decision(qualified_count: int) -> str:
    if qualified_count >= 2:
        return (
            "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT_MULTIPLE_FAMILIES_CONFIRMED_"
            "RD24_PARALLEL_MINIMAL_PORTFOLIO_AUTHORIZED"
        )
    if qualified_count == 1:
        return (
            "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT_ONE_FAMILY_CONFIRMED_"
            "RD24_MINIMAL_PORTFOLIO_AUTHORIZED"
        )
    return "RD23_P2_MULTIFAMILY_RAW_EDGE_TOURNAMENT_NO_FAMILY_CONFIRMED"


def validate(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise ValidationError(f"output directory missing: {output}")
    validate_manifest(output)

    report = load_json(output / "rd23-p2-multifamily-raw-edge-report-v1.json")
    audit = load_json(output / "input-and-conformance-audit.json")
    freeze = load_json(output / "qualified-family-freeze.json")
    overlap = load_json(output / "overlap-summary.json")
    funnel = pd.read_csv(output / "family-signal-funnel.csv")
    events = pd.read_csv(output / "signal-events.csv", low_memory=False)
    forward = pd.read_csv(output / "forward-event-returns.csv", low_memory=False)
    metrics = pd.read_csv(output / "raw-edge-metrics.csv", low_memory=False)
    selection = pd.read_csv(output / "family-selection.csv", low_memory=False)

    if report.get("passed") is not True:
        raise ValidationError("report did not pass")
    if set(report.get("families", [])) != set(FAMILIES):
        raise ValidationError("report family registry drifted")
    if int(report.get("family_count", -1)) != len(FAMILIES):
        raise ValidationError("report family count drifted")

    for field in (
        "portfolio_replay_executed",
        "position_sizing_executed",
        "historical_exit_simulation_executed",
        "2022_2023_used_for_selection",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise ValidationError(f"report prohibited flag not false: {field}")

    if audit.get("2022_2023_used_for_selection") is not False:
        raise ValidationError("audit indicates 2022/2023 selection access")
    if audit.get("2024_accessed") is not False:
        raise ValidationError("audit indicates 2024 access")

    if set(funnel["family_id"].astype(str)) != set(FAMILIES):
        raise ValidationError("funnel does not contain all families")
    if set(funnel["period_id"].astype(str)) != set(PERIODS):
        raise ValidationError("funnel period registry drifted")
    if set(funnel["universe_id"].astype(str)) != {"C2", "D2", "E2"}:
        raise ValidationError("funnel universe registry drifted")

    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True, errors="raise")
    if bool((events["timestamp"] >= DATA_CUTOFF).any()):
        raise ValidationError("2022+ signal observed")
    if set(events["family_id"].astype(str)).difference(FAMILIES):
        raise ValidationError("unknown family in signal events")
    if set(events["period_id"].astype(str)).difference(PERIODS):
        raise ValidationError("unknown period in signal events")

    for column in ("signal_time", "entry_time", "exit_time"):
        forward[column] = pd.to_datetime(forward[column], utc=True, errors="raise")
    if bool((forward["exit_time"] >= DATA_CUTOFF).any()):
        raise ValidationError("2022+ forward outcome observed")
    if set(pd.to_numeric(forward["horizon_hours"], errors="raise").astype(int)) != set(
        FORWARD_HORIZONS
    ):
        raise ValidationError("forward horizon registry drifted")
    if set(pd.to_numeric(forward["cost_multiplier"], errors="raise").astype(float)) != {
        1.0,
        2.0,
    }:
        raise ValidationError("forward cost matrix drifted")

    if set(metrics["family_id"].astype(str)).difference(FAMILIES):
        raise ValidationError("unknown family in metrics")
    if len(selection) != len(FAMILIES):
        raise ValidationError("selection must contain exactly one row per family")
    if set(selection["family_id"].astype(str)) != set(FAMILIES):
        raise ValidationError("selection family registry drifted")

    confirmed = selection.loc[selection["raw_edge_confirmed"].astype(bool)].copy()
    qualified = confirmed["family_id"].astype(str).tolist()
    decision = expected_decision(len(qualified))
    if report.get("decision") != decision:
        raise ValidationError("report decision disagrees with selected families")
    if freeze.get("decision") != decision:
        raise ValidationError("qualified-family freeze decision drifted")
    if freeze.get("qualified_families") != qualified:
        raise ValidationError("qualified-family freeze list drifted")
    if int(freeze.get("qualified_family_count", -1)) != len(qualified):
        raise ValidationError("qualified family count drifted")

    for row in confirmed.to_dict(orient="records"):
        horizon = int(float(row["selected_horizon_hours"]))
        if horizon not in FORWARD_HORIZONS:
            raise ValidationError("qualified family has unauthorized horizon")
        key = f"h{horizon}_passed"
        if key not in row or not bool(row[key]):
            raise ValidationError("qualified family selected a failed horizon")

    if not math.isfinite(float(overlap.get("multi_family_event_key_share", math.nan))):
        raise ValidationError("overlap summary is not finite")
    if int(overlap.get("unique_event_keys", -1)) <= 0:
        raise ValidationError("overlap summary has no event keys")

    return {
        "status": "PASS",
        "decision": decision,
        "qualified_family_count": len(qualified),
        "qualified_families": qualified,
        "signal_event_count": len(events),
        "forward_row_count": len(forward),
        "2022_2023_used_for_selection": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    if not args.offline:
        raise ValidationError("RD23 validator currently supports --offline only")
    result = validate(args.repo_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print(f"RD23_VALIDATION_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2) from exc
