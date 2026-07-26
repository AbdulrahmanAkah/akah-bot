"""Run the exact-schema AMS BF01 V2 audit."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from spotbot.research.ams_bf01_v2 import (
    MetricRecord,
    build_audit,
    extract_benchmark_comparison,
    extract_beta_folds,
    extract_rd01_benchmarks,
    extract_variant_diagnostics,
    load_json,
    render_percent,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"

MD01_BENCHMARKS = REPORTS / "ams-md01-benchmark-comparison-v1.json"
RD01_BENCHMARKS = REPORTS / "ams-rd01-benchmark-comparison-v2.json"
RD01_BETA = REPORTS / "ams-rd01-btc-beta-diagnostics-v1.json"
RD01_CONCENTRATION = REPORTS / "ams-rd01-concentration-diagnostics-v1.json"

SOURCE_PATHS = (
    MD01_BENCHMARKS,
    RD01_BENCHMARKS,
    RD01_BETA,
    RD01_CONCENTRATION,
)

INVENTORY_CSV = REPORTS / "ams-bf01-source-inventory-v2.csv"
METRICS_CSV = REPORTS / "ams-bf01-benchmark-fairness-metrics-v2.csv"
M02_CSV = REPORTS / "ams-bf01-m02-contributors-v2.csv"
REGRESSION_CSV = REPORTS / "ams-bf01-regression-v2.csv"
REPORT_JSON = REPORTS / "ams-bf01-benchmark-fairness-alpha-audit-v2.json"
REPORT_MD = REPORTS / "ams-bf01-benchmark-fairness-alpha-audit-v2.md"
FINAL_COPY = ROOT / "BF01_V2_RESULT_FOR_CHATGPT.md"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(
    path: Path,
    fieldnames: tuple[str, ...],
    rows: Sequence[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def _source_inventory(
    paths: Sequence[Path],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for path in paths:
        payload = load_json(path)
        rows.append(
            {
                "source": path.relative_to(ROOT).as_posix(),
                "status": "READ",
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "schema_version": payload.get("schema_version"),
            }
        )

    return rows


def _metric_rows(
    records: Sequence[MetricRecord],
) -> list[dict[str, Any]]:
    return [
        {
            "entity": record.entity,
            "metric": record.metric,
            "value": record.value,
            "unit": record.unit,
            "scope": record.scope,
            "fold_id": record.fold_id,
            "status": record.status,
            "source_path": record.source_path,
        }
        for record in records
    ]


def _regression_rows(
    records: Sequence[MetricRecord],
) -> list[dict[str, Any]]:
    rows_by_key: dict[
        tuple[str, str],
        dict[str, Any],
    ] = {}

    for record in records:
        if record.fold_id is None:
            continue

        key = (record.entity, record.fold_id)
        row = rows_by_key.setdefault(
            key,
            {
                "entity": record.entity,
                "fold_id": record.fold_id,
            },
        )
        row[record.metric] = record.value

    return [
        rows_by_key[key]
        for key in sorted(rows_by_key)
    ]


def _markdown(result: dict[str, Any]) -> str:
    benchmark = result["benchmark_audit"]
    m02 = result["m02_tsm84"]["contributor_robustness"]

    lines = [
        "# AMS BF01 V2 — Exact-Schema Benchmark Fairness Audit",
        "",
        "## النتيجة التنفيذية",
        "",
        f"- Research result: `{result['research_result']}`",
        f"- Safety stop: `{result['safety_stop']}`",
        "- Entity matching: `EXACT_ONLY`",
        "- Aggregate/fold separation: `ENFORCED`",
        "- Metric units: `EXPLICIT`",
        "- Domain gates: `ENFORCED`",
        (
            "- Alpha value judgement: "
            f"`{benchmark['alpha_value_judgement']}`"
        ),
        (
            "- M02 contributor robustness: "
            f"`{m02['judgement']}`"
        ),
        "",
        "## Raw return evidence",
        "",
        (
            "- M05 DUAL-28: "
            f"`{render_percent(benchmark['m05_total_return'])}`"
        ),
        (
            "- Equal-weight Survivor-30: "
            f"`{render_percent(benchmark['equal_weight_total_return'])}`"
        ),
        (
            "- M05 minus Equal-weight: "
            f"`{render_percent(benchmark['m05_minus_equal_weight'])}`"
        ),
        "",
        (
            "هذه مقارنة خام فقط. لا يُسمح بتحويلها إلى حكم Alpha "
            "لأن السلاسل اليومية المحاذاة والمتحقق منها غير متاحة "
            "في المصادر الحالية."
        ),
        "",
        "## M02 / TSM-84",
        "",
        f"- Status: `{m02['status']}`",
        f"- Judgement: `{m02['judgement']}`",
        f"- Reason: {m02['reason']}",
        "",
        "## الملفات الناتجة",
        "",
        "- `reports/research/ams-bf01-source-inventory-v2.csv`",
        (
            "- `reports/research/"
            "ams-bf01-benchmark-fairness-metrics-v2.csv`"
        ),
        "- `reports/research/ams-bf01-m02-contributors-v2.csv`",
        "- `reports/research/ams-bf01-regression-v2.csv`",
        (
            "- `reports/research/"
            "ams-bf01-benchmark-fairness-alpha-audit-v2.json`"
        ),
        (
            "- `reports/research/"
            "ams-bf01-benchmark-fairness-alpha-audit-v2.md`"
        ),
        "- `BF01_V2_RESULT_FOR_CHATGPT.md`",
        "",
        "## Safety boundaries",
        "",
        "- Survivor universe only; not point-in-time.",
        (
            "- No promotion, production, live trading, MD02, "
            "Kelly or leverage authorization."
        ),
        "- 2025 and 2026 remain unaccessed.",
        "",
    ]

    return "\n".join(lines)


def main() -> None:
    md01_benchmarks = load_json(MD01_BENCHMARKS)
    rd01_benchmarks = load_json(RD01_BENCHMARKS)
    beta = load_json(RD01_BETA)
    concentration = load_json(RD01_CONCENTRATION)

    benchmark_records = [
        *extract_benchmark_comparison(md01_benchmarks),
        *extract_rd01_benchmarks(rd01_benchmarks),
    ]

    m05_records, _ = extract_variant_diagnostics(
        concentration,
        "MD01-M05",
    )
    m02_records, m02_robustness = extract_variant_diagnostics(
        concentration,
        "MD01-M02",
    )

    beta_records = [
        *extract_beta_folds(beta, "MD01-M05"),
        *extract_beta_folds(beta, "MD01-M02"),
    ]

    all_records = [
        *benchmark_records,
        *m05_records,
        *m02_records,
        *beta_records,
    ]

    result = build_audit(
        benchmark_records=benchmark_records,
        diagnostic_records=[
            *m05_records,
            *m02_records,
        ],
        beta_records=beta_records,
        m02_robustness=m02_robustness,
    )

    inventory_rows = _source_inventory(SOURCE_PATHS)
    metric_rows = _metric_rows(all_records)
    regression_rows = _regression_rows(beta_records)

    m02_rows: list[dict[str, Any]] = [
        {
            "status": m02_robustness.status,
            "judgement": m02_robustness.judgement,
            "reason": m02_robustness.reason,
            "symbol": "",
            "pnl": "",
            "contribution_share": "",
            "leave_one_total": "",
            "rank": "",
        }
    ]

    result["source_inventory"] = inventory_rows
    result["generated_files"] = [
        path.relative_to(ROOT).as_posix()
        for path in (
            INVENTORY_CSV,
            METRICS_CSV,
            M02_CSV,
            REGRESSION_CSV,
            REPORT_JSON,
            REPORT_MD,
            FINAL_COPY,
        )
    ]

    REPORTS.mkdir(
        parents=True,
        exist_ok=True,
    )

    _write_csv(
        INVENTORY_CSV,
        (
            "source",
            "status",
            "size_bytes",
            "sha256",
            "schema_version",
        ),
        inventory_rows,
    )

    _write_csv(
        METRICS_CSV,
        (
            "entity",
            "metric",
            "value",
            "unit",
            "scope",
            "fold_id",
            "status",
            "source_path",
        ),
        metric_rows,
    )

    _write_csv(
        M02_CSV,
        (
            "status",
            "judgement",
            "reason",
            "symbol",
            "pnl",
            "contribution_share",
            "leave_one_total",
            "rank",
        ),
        m02_rows,
    )

    _write_csv(
        REGRESSION_CSV,
        (
            "entity",
            "fold_id",
            "alpha_intercept",
            "beta",
            "downside_beta",
            "upside_beta",
            "correlation",
            "r_squared",
            "residual_return",
            "residual_volatility",
            "volatility_matched_btc_return",
            "maximum_btc_exposure",
            "observations",
        ),
        regression_rows,
    )

    REPORT_JSON.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    markdown = _markdown(result)

    REPORT_MD.write_text(
        markdown,
        encoding="utf-8",
    )
    FINAL_COPY.write_text(
        markdown,
        encoding="utf-8",
    )

    print("تم انجاز المهمة وانشاء ملف في داخل المستودع")


if __name__ == "__main__":
    main()