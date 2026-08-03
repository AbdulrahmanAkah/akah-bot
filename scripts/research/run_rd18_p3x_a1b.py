from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd18_p3x_a1 import load_json, write_csv  # noqa: E402
from spotbot.research.rd18_p3x_a1b_asset_gate import (  # noqa: E402
    ELIGIBILITY_FIELDS,
    REJECTION_FIELDS,
    SEALED_CUTOFF,
    THRESHOLD_FIELDS,
    build_monthly_gate_from_loader,
    deterministic_manifest,
    write_json,
)

EXPECTED_PAIRS = 364


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Build the preregistered RD18-P3X-A1B monthly causal asset "
            "eligibility ledgers without generating strategy candidates."
        )
    )
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument(
        "--a1-runtime",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1_runtime",
    )
    result.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/research/rd18_p3x_a1b_runtime",
    )
    result.add_argument(
        "--write-ledgers",
        action="store_true",
        help="Required acknowledgement for deterministic local ledger writes.",
    )
    return result


def _read_plan(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if len(frame) != EXPECTED_PAIRS:
        raise RuntimeError(f"expected {EXPECTED_PAIRS} A1 plan rows, found {len(frame)}")
    if bool(frame["pair"].duplicated().any()):
        raise RuntimeError("A1 plan contains duplicate pairs")
    return frame.sort_values("pair", kind="stable").reset_index(drop=True)


def _gate_inputs(
    repo: Path,
    plan: pd.DataFrame,
) -> tuple[
    list[str],
    dict[str, str],
    dict[str, bool],
    dict[str, Path],
]:
    symbols: list[str] = []
    actions: dict[str, str] = {}
    identities: dict[str, bool] = {}
    paths: dict[str, Path] = {}

    for row in plan.to_dict(orient="records"):
        symbol = str(row["symbol"])
        action = str(row["action"])
        symbols.append(symbol)
        actions[symbol] = action
        identities[symbol] = action != "CORPORATE_ACTION_POLICY_REQUIRED"

        if action != "READY_LOCAL":
            continue

        logical_path = Path(str(row["logical_path"]))
        source_path = repo / "data/raw/rd16b" / logical_path
        if not source_path.is_file():
            raise RuntimeError(f"READY_LOCAL source is missing for {symbol}: {source_path}")
        paths[symbol] = source_path

    return symbols, actions, identities, paths


def main() -> int:
    args = parser().parse_args()
    if not args.write_ledgers:
        raise SystemExit("A1B requires --write-ledgers")

    repo = args.repo_root.resolve()
    a1_runtime = args.a1_runtime.resolve()
    output = args.output_dir.resolve()
    plan_path = a1_runtime / "full-c2-hourly-acquisition-plan.csv"
    report_path = a1_runtime / "rd18-p3x-a1-runtime-report-v1.json"

    if not plan_path.is_file():
        raise SystemExit(f"A1 acquisition plan is missing: {plan_path}")
    if not report_path.is_file():
        raise SystemExit(f"A1 runtime report is missing: {report_path}")

    a1_report = load_json(report_path)
    counts = dict(a1_report.get("acquisition", {}).get("action_counts", {}))
    terminal_actions = {
        "CORPORATE_ACTION_POLICY_REQUIRED",
        "HISTORICAL_MARKET_SOURCE_REQUIRED",
        "READY_LOCAL",
    }
    if set(counts).difference(terminal_actions):
        raise SystemExit(f"A1B requires terminal A1 classifications only; found {counts}")
    if sum(int(value) for value in counts.values()) != EXPECTED_PAIRS:
        raise SystemExit(f"A1B requires {EXPECTED_PAIRS} classified pairs; found {counts}")
    if int(counts.get("READY_LOCAL", 0)) <= 0:
        raise SystemExit("A1B requires at least one READY_LOCAL pair")

    plan = _read_plan(plan_path)
    symbols, actions, identities, paths = _gate_inputs(
        repo,
        plan,
    )

    def load_frame(symbol: str) -> pd.DataFrame | None:
        path = paths.get(symbol)
        if path is None:
            return None
        return pd.read_parquet(path)

    result = build_monthly_gate_from_loader(
        symbols=symbols,
        frame_loader=load_frame,
        source_actions=actions,
        identity_ready=identities,
        cutoff=SEALED_CUTOFF,
    )

    output.mkdir(parents=True, exist_ok=True)
    eligibility_name = "monthly-asset-eligibility-ledger.csv"
    thresholds_name = "monthly-liquidity-threshold-ledger.csv"
    rejections_name = "monthly-asset-rejection-ledger.csv"
    report_name = "rd18-p3x-a1b-runtime-report-v1.json"

    write_csv(
        output / eligibility_name,
        result.eligibility.to_dict(orient="records"),
        ELIGIBILITY_FIELDS,
    )
    write_csv(
        output / thresholds_name,
        result.thresholds.to_dict(orient="records"),
        THRESHOLD_FIELDS,
    )
    write_csv(
        output / rejections_name,
        result.rejections.to_dict(orient="records"),
        REJECTION_FIELDS,
    )
    write_json(output / report_name, result.report)

    names = (
        eligibility_name,
        thresholds_name,
        rejections_name,
        report_name,
    )
    manifest = deterministic_manifest(output, names)
    write_json(output / "output-manifest.json", manifest)

    response = {
        **result.report,
        "output_dir": str(output),
        "output_manifest": str(output / "output-manifest.json"),
        "network_requests": 0,
    }
    print(json.dumps(response, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
