"""Run the AMS BF02 aligned daily-series evidence stage."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
from ams_md01_common import load_registered_data

from spotbot.research.ams_bf02 import (
    align_daily_evidence,
    build_audit,
    daily_benchmark_returns,
    daily_strategy_state,
    reconstruct_portfolio_state,
)
from spotbot.research.ams_md01_momentum import (
    FOLDS,
    simulate_md01_fold,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

DAILY_CSV = REPORTS / "ams-bf02-aligned-daily-series-v1.csv"
METRICS_CSV = REPORTS / "ams-bf02-fold-metrics-v1.csv"
REPORT_JSON = REPORTS / "ams-bf02-aligned-daily-series-evidence-v1.json"
REPORT_MD = REPORTS / "ams-bf02-aligned-daily-series-evidence-v1.md"
FINAL_COPY = ROOT / "BF02_RESULT_FOR_CHATGPT.md"


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def metric_rows(
    audit: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for record in audit["fold_metrics"]:
        rows.append(
            {
                "scope": "fold",
                "fold_id": record["fold_id"],
                "observations": record["observations"],
                "m05_compounded_return": record["m05"]["compounded_return"],
                "equal_weight_compounded_return": record["equal_weight"]["compounded_return"],
                "exposure_matched_equal_weight_return": record["exposure_matched_equal_weight"][
                    "compounded_return"
                ],
                "volatility_matched_equal_weight_return": record["volatility_matched_equal_weight"][
                    "compounded_return"
                ],
                "btc_compounded_return": record["btc"]["compounded_return"],
                "average_gross_exposure": record["average_gross_exposure"],
                "maximum_gross_exposure": record["maximum_gross_exposure"],
                "beta_vs_equal_weight": record["beta_vs_equal_weight"]["beta"],
                "alpha_vs_equal_weight_daily": record["beta_vs_equal_weight"]["alpha_intercept"],
                "r_squared_vs_equal_weight": record["beta_vs_equal_weight"]["r_squared"],
                "beta_vs_btc": record["beta_vs_btc"]["beta"],
                "alpha_vs_btc_daily": record["beta_vs_btc"]["alpha_intercept"],
                "maximum_reconstruction_error": record["maximum_reconstruction_error"],
            }
        )

    aggregate = audit["aggregate_metrics"]

    rows.append(
        {
            "scope": "aggregate",
            "fold_id": "ALL",
            "observations": aggregate["observations"],
            "m05_compounded_return": aggregate["m05"]["compounded_return"],
            "equal_weight_compounded_return": aggregate["equal_weight"]["compounded_return"],
            "exposure_matched_equal_weight_return": aggregate["exposure_matched_equal_weight"][
                "compounded_return"
            ],
            "volatility_matched_equal_weight_return": aggregate["volatility_matched_equal_weight"][
                "compounded_return"
            ],
            "btc_compounded_return": aggregate["btc"]["compounded_return"],
            "average_gross_exposure": aggregate["average_gross_exposure"],
            "maximum_gross_exposure": aggregate["maximum_gross_exposure"],
            "beta_vs_equal_weight": aggregate["beta_vs_equal_weight"]["beta"],
            "alpha_vs_equal_weight_daily": aggregate["beta_vs_equal_weight"]["alpha_intercept"],
            "r_squared_vs_equal_weight": aggregate["beta_vs_equal_weight"]["r_squared"],
            "beta_vs_btc": aggregate["beta_vs_btc"]["beta"],
            "alpha_vs_btc_daily": aggregate["beta_vs_btc"]["alpha_intercept"],
            "maximum_reconstruction_error": audit["validation"]["maximum_reconstruction_error"],
        }
    )

    return rows


def markdown(
    audit: dict[str, Any],
) -> str:
    aggregate = audit["aggregate_metrics"]
    authorizations = audit["comparison_authorizations"]

    lines = [
        "# AMS BF02 — Aligned Daily-Series Evidence",
        "",
        "## Executive result",
        "",
        (f"- Research result: `{audit['research_result']}`"),
        (f"- Safety stop: `{audit['safety_stop']}`"),
        (f"- Aligned-series status: `{audit['aligned_series_status']}`"),
        (f"- Alpha judgement: `{authorizations['alpha_value_judgement']}`"),
        (f"- Aligned observations: `{audit['validation']['aligned_observations']}`"),
        (
            "- Maximum reconstruction error: "
            f"`{audit['validation']['maximum_reconstruction_error']}`"
        ),
        "",
        "## Aggregate comparison",
        "",
        (f"- M05 compounded return: `{aggregate['m05']['compounded_return']:.6f}`"),
        (
            "- Equal-weight compounded return: "
            f"`{aggregate['equal_weight']['compounded_return']:.6f}`"
        ),
        (
            "- Exposure-matched equal-weight return: "
            f"`{aggregate['exposure_matched_equal_weight']['compounded_return']:.6f}`"
        ),
        (
            "- Causal volatility-matched equal-weight return: "
            f"`{aggregate['volatility_matched_equal_weight']['compounded_return']:.6f}`"
        ),
        (f"- BTC compounded return: `{aggregate['btc']['compounded_return']:.6f}`"),
        (f"- M05 beta versus equal-weight: `{aggregate['beta_vs_equal_weight']['beta']}`"),
        (
            "- M05 daily alpha intercept versus equal-weight: "
            f"`{aggregate['beta_vs_equal_weight']['alpha_intercept']}`"
        ),
        "",
        "## Fold evidence",
        "",
        "| Fold | Observations | M05 | Equal weight | Exposure matched | Alpha/day |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for record in audit["fold_metrics"]:
        lines.append(
            "| "
            f"`{record['fold_id']}` | "
            f"{record['observations']} | "
            f"{record['m05']['compounded_return']:.6f} | "
            f"{record['equal_weight']['compounded_return']:.6f} | "
            f"{record['exposure_matched_equal_weight']['compounded_return']:.6f} | "
            f"{record['beta_vs_equal_weight']['alpha_intercept']} |"
        )

    lines.extend(
        [
            "",
            "## Authorizations",
            "",
            "- Raw return comparison: `AUTHORIZED`",
            "- Risk-adjusted comparison: `AUTHORIZED`",
            "- Exposure-matched comparison: `AUTHORIZED`",
            "- Causal volatility-matched comparison: `AUTHORIZED`",
            "- Production, MD02, Kelly and leverage: `NOT_AUTHORIZED`",
            "",
            "## Generated files",
            "",
            "- `reports/research/ams-bf02-aligned-daily-series-v1.csv`",
            "- `reports/research/ams-bf02-fold-metrics-v1.csv`",
            "- `reports/research/ams-bf02-aligned-daily-series-evidence-v1.json`",
            "- `reports/research/ams-bf02-aligned-daily-series-evidence-v1.md`",
            "- `BF02_RESULT_FOR_CHATGPT.md`",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    frames, dataset_hashes = load_registered_data()

    benchmarks = daily_benchmark_returns(frames["daily"])

    fold_frames: list[pd.DataFrame] = []
    reconstruction_errors: dict[str, float] = {}

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

        state, maximum_error = reconstruct_portfolio_state(
            result,
            frames["four_hour"],
            validation_start=start,
            validation_end=end,
        )

        strategy = daily_strategy_state(
            state,
            initial_capital=result.initial_capital,
            validation_start=start,
            validation_end=end,
        )

        aligned = align_daily_evidence(
            strategy,
            benchmarks,
            fold_id=fold_id,
            validation_start=start,
            validation_end=end,
        )

        fold_frames.append(aligned)
        reconstruction_errors[fold_id] = maximum_error

    audit = build_audit(
        fold_frames,
        reconstruction_errors=reconstruction_errors,
        dataset_hashes=dataset_hashes,
    )

    audit["source_commit"] = subprocess.check_output(
        [
            "git",
            "rev-parse",
            "HEAD",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
    ).strip()

    audit["generated_files"] = [
        path.relative_to(ROOT).as_posix()
        for path in (
            DAILY_CSV,
            METRICS_CSV,
            REPORT_JSON,
            REPORT_MD,
            FINAL_COPY,
        )
    ]

    combined = pd.concat(
        fold_frames,
        ignore_index=True,
    )

    combined["timestamp"] = pd.to_datetime(
        combined["timestamp"],
        utc=True,
        errors="raise",
    ).map(lambda value: value.isoformat())

    REPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    combined.to_csv(
        DAILY_CSV,
        index=False,
        encoding="utf-8",
        lineterminator="\n",
    )

    rows = metric_rows(audit)

    with METRICS_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=tuple(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)

    write_json(
        REPORT_JSON,
        audit,
    )

    report_markdown = markdown(audit)

    REPORT_MD.write_text(
        report_markdown,
        encoding="utf-8",
    )
    FINAL_COPY.write_text(
        report_markdown,
        encoding="utf-8",
    )

    print("BF02_STATUS=COMPLETE")
    print(f"ALIGNED_OBSERVATIONS={audit['validation']['aligned_observations']}")
    print(f"MAX_RECONSTRUCTION_ERROR={audit['validation']['maximum_reconstruction_error']}")
    print(f"ALPHA_JUDGEMENT={audit['comparison_authorizations']['alpha_value_judgement']}")
    print(f"M05_RETURN={audit['aggregate_metrics']['m05']['compounded_return']}")
    print(f"EQUAL_WEIGHT_RETURN={audit['aggregate_metrics']['equal_weight']['compounded_return']}")


if __name__ == "__main__":
    main()
