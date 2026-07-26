"""Exact-schema extraction and validation for AMS BF01 V2."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

MetricUnit = Literal["fraction", "percent", "currency", "ratio", "days", "count"]
MetricScope = Literal["aggregate", "fold", "metadata"]
MetricStatus = Literal["VALID", "NOT_EVALUATED"]

DATE_COLUMNS: tuple[str, ...] = (
    "date",
    "timestamp",
    "time",
    "open_time",
    "close_time",
    "snapshot_date",
    "snapshot_time",
    "trading_date",
)

_EXACT_ENTITY_IDS: dict[str, str] = {
    "MD01-M02": "M02_TSM_84",
    "MD01-M05": "M05_DUAL_28",
    "B00": "MD01_B00_CASH",
    "B01": "MD01_B01_BTC_BUY_HOLD",
    "B02": "MD01_B02_EQUAL_WEIGHT",
    "HIGH_BETA_28": "HIGH_BETA_28",
    "HIGH_BETA_84": "HIGH_BETA_84",
}

_MD01_BENCHMARK_NAMES: dict[str, str] = {
    "B00": "CASH",
    "B01": "BTC_BUY_AND_HOLD",
    "B02": "EQUAL_WEIGHT_ELIGIBLE_UNIVERSE",
}

_RD01_BENCHMARK_ENTITIES: dict[str, str] = {
    "BTC_BUY_AND_HOLD": "RD01_BTC_BUY_HOLD",
    "EQUAL_WEIGHT_SURVIVOR_30": "SURVIVOR_30_EQUAL_WEIGHT",
    "HIGH_BETA_28": "HIGH_BETA_28",
    "HIGH_BETA_84": "HIGH_BETA_84",
}

_FOLD_IDS: tuple[str, ...] = ("WF01", "WF02", "WF03")


@dataclass(frozen=True)
class MetricRecord:
    """A typed metric with explicit scope, unit and source evidence."""

    entity: str
    metric: str
    value: float | int | None
    unit: MetricUnit
    scope: MetricScope
    source_path: str
    status: MetricStatus = "VALID"
    fold_id: str | None = None


@dataclass(frozen=True)
class ContributorRobustness:
    """M02 contributor robustness must remain unevaluated without a ledger."""

    status: str
    judgement: str
    reason: str


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object and reject empty or non-object sources."""
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise ValueError(f"empty JSON source: {path}")
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError(f"JSON root must be an object: {path}")
    return cast(dict[str, Any], payload)


def resolve_entity_exact(identifier: object) -> str | None:
    """Resolve only complete registered IDs; never use substring matching."""
    if not isinstance(identifier, str):
        return None
    return _EXACT_ENTITY_IDS.get(identifier.strip().upper())


def parse_fraction(value: object) -> float:
    """Parse a source fraction exactly; percent strings are divided once."""
    if isinstance(value, bool):
        raise TypeError("boolean is not a numeric metric")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        number = (
            float(cleaned[:-1].strip()) / 100.0
            if cleaned.endswith("%")
            else float(cleaned)
        )
    else:
        raise TypeError(f"unsupported numeric value: {type(value).__name__}")
    if not math.isfinite(number):
        raise ValueError("metric must be finite")
    return number


def render_percent(value: object) -> str:
    """Render a stored fraction as percent exactly once."""
    return f"{parse_fraction(value) * 100.0:.2f}%"


def _require_mapping(value: object, source_path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"expected object at {source_path}")
    return cast(Mapping[str, Any], value)


def _require_sequence(value: object, source_path: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"expected array at {source_path}")
    return value


def validate_spot_return(value: object, source_path: str) -> float:
    """Spot total/fold returns must remain strictly above -100%."""
    number = parse_fraction(value)
    if number <= -1.0:
        raise ValueError(f"spot return must be greater than -100% at {source_path}")
    return number


def validate_drawdown(value: object, source_path: str) -> float:
    """Drawdown magnitude must be in [0, 1]."""
    number = parse_fraction(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"drawdown outside [0, 1] at {source_path}")
    return number


def validate_exposure(value: object, source_path: str) -> float:
    """Spot exposure must be in [0, 1]."""
    number = parse_fraction(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"exposure outside [0, 1] at {source_path}")
    return number


def validate_ratio(value: object, source_path: str) -> float:
    number = parse_fraction(value)
    if not math.isfinite(number):
        raise ValueError(f"ratio must be finite at {source_path}")
    return number


def compounded_return(fold_returns: Sequence[float]) -> float:
    """Compound independent fold returns without treating fold zero as aggregate."""
    equity = 1.0
    for index, value in enumerate(fold_returns):
        equity *= 1.0 + validate_spot_return(value, f"fold_returns/{index}")
    return equity - 1.0


def extract_benchmark_comparison(
    payload: Mapping[str, Any],
    *,
    root_key: str = "benchmarks",
    cost_mode: str = "BASE_COST",
) -> list[MetricRecord]:
    """Extract exact benchmark aggregate and fold metrics from the MD01 schema."""
    root = _require_mapping(payload.get(root_key), root_key)
    records: list[MetricRecord] = []
    for benchmark_id in ("B00", "B01", "B02"):
        benchmark_path = f"{root_key}/{benchmark_id}"
        benchmark = _require_mapping(root.get(benchmark_id), benchmark_path)
        name = benchmark.get("name")
        expected_name = _MD01_BENCHMARK_NAMES[benchmark_id]
        if name != expected_name:
            raise ValueError(f"benchmark ID/name conflict at {benchmark_path}")
        entity = _EXACT_ENTITY_IDS[benchmark_id]
        cost_path = f"{benchmark_path}/{cost_mode}"
        cost = _require_mapping(benchmark.get(cost_mode), cost_path)
        aggregate_return = validate_spot_return(
            cost.get("compounded_return"), f"{cost_path}/compounded_return"
        )
        records.append(
            MetricRecord(
                entity=entity,
                metric="total_return",
                value=aggregate_return,
                unit="fraction",
                scope="aggregate",
                source_path=f"{cost_path}/compounded_return",
            )
        )
        for key, unit in (
            ("mean_calmar", "ratio"),
            ("mean_maximum_drawdown", "fraction"),
            ("recovery_time_days", "days"),
            ("turnover", "currency"),
            ("worst_month", "fraction"),
            ("worst_year", "fraction"),
        ):
            if key not in cost or cost[key] is None:
                continue
            source_path = f"{cost_path}/{key}"
            raw = cost[key]
            if key == "mean_maximum_drawdown":
                value: float | int = validate_drawdown(raw, source_path)
            elif unit in {"fraction", "ratio"}:
                value = validate_ratio(raw, source_path)
            elif unit == "days":
                value = int(raw)
            else:
                value = parse_fraction(raw)
            records.append(
                MetricRecord(
                    entity=entity,
                    metric=key,
                    value=value,
                    unit=cast(MetricUnit, unit),
                    scope="aggregate",
                    source_path=source_path,
                )
            )
        folds = _require_sequence(cost.get("folds"), f"{cost_path}/folds")
        for index, fold_value in enumerate(folds):
            fold_path = f"{cost_path}/folds/{index}"
            fold = _require_mapping(fold_value, fold_path)
            fold_id = _FOLD_IDS[index] if index < len(_FOLD_IDS) else f"FOLD_{index + 1}"
            for key, unit in (
                ("net_return", "fraction"),
                ("cagr", "fraction"),
                ("maximum_drawdown", "fraction"),
                ("exposure", "fraction"),
                ("sharpe", "ratio"),
                ("sortino", "ratio"),
                ("calmar", "ratio"),
                ("recovery_time_days", "days"),
                ("turnover", "currency"),
                ("fees", "currency"),
                ("worst_month", "fraction"),
                ("worst_year", "fraction"),
            ):
                if key not in fold or fold[key] is None:
                    continue
                source_path = f"{fold_path}/{key}"
                raw = fold[key]
                if key in {"net_return", "cagr", "worst_month", "worst_year"}:
                    value = validate_spot_return(raw, source_path)
                elif key == "maximum_drawdown":
                    value = validate_drawdown(raw, source_path)
                elif key == "exposure":
                    value = validate_exposure(raw, source_path)
                elif unit == "ratio":
                    value = validate_ratio(raw, source_path)
                elif unit == "days":
                    value = int(raw)
                else:
                    value = parse_fraction(raw)
                records.append(
                    MetricRecord(
                        entity=entity,
                        metric=key,
                        value=value,
                        unit=cast(MetricUnit, unit),
                        scope="fold",
                        source_path=source_path,
                        fold_id=fold_id,
                    )
                )
    return records


def extract_rd01_benchmarks(payload: Mapping[str, Any]) -> list[MetricRecord]:
    """Extract only registered RD01 benchmark metrics; metadata stays metadata."""
    benchmarks = _require_mapping(payload.get("benchmarks"), "benchmarks")
    records: list[MetricRecord] = []
    for source_id in (
        "BTC_BUY_AND_HOLD",
        "EQUAL_WEIGHT_SURVIVOR_30",
        "HIGH_BETA_28",
        "HIGH_BETA_84",
    ):
        source_path = f"benchmarks/{source_id}"
        entity = _RD01_BENCHMARK_ENTITIES[source_id]
        value = benchmarks.get(source_id)
        if source_id in {"BTC_BUY_AND_HOLD", "EQUAL_WEIGHT_SURVIVOR_30"}:
            records.append(
                MetricRecord(
                    entity=entity,
                    metric="total_return",
                    value=validate_spot_return(value, source_path),
                    unit="fraction",
                    scope="aggregate",
                    source_path=source_path,
                )
            )
            continue
        benchmark = _require_mapping(value, source_path)
        records.extend(
            [
                MetricRecord(
                    entity=entity,
                    metric="total_return",
                    value=validate_spot_return(
                        benchmark.get("net_compounded_return"),
                        f"{source_path}/net_compounded_return",
                    ),
                    unit="fraction",
                    scope="aggregate",
                    source_path=f"{source_path}/net_compounded_return",
                ),
                MetricRecord(
                    entity=entity,
                    metric="average_exposure",
                    value=validate_exposure(
                        benchmark.get("average_exposure"),
                        f"{source_path}/average_exposure",
                    ),
                    unit="fraction",
                    scope="aggregate",
                    source_path=f"{source_path}/average_exposure",
                ),
                MetricRecord(
                    entity=entity,
                    metric="maximum_exposure",
                    value=validate_exposure(
                        benchmark.get("maximum_exposure"),
                        f"{source_path}/maximum_exposure",
                    ),
                    unit="fraction",
                    scope="aggregate",
                    source_path=f"{source_path}/maximum_exposure",
                ),
                MetricRecord(
                    entity=entity,
                    metric="selection_count",
                    value=int(benchmark["selection_count"]),
                    unit="count",
                    scope="aggregate",
                    source_path=f"{source_path}/selection_count",
                ),
                MetricRecord(
                    entity=entity,
                    metric="turnover",
                    value=parse_fraction(benchmark["turnover"]),
                    unit="ratio",
                    scope="aggregate",
                    source_path=f"{source_path}/turnover",
                ),
                MetricRecord(
                    entity=entity,
                    metric="window_days",
                    value=int(benchmark["window_days"]),
                    unit="days",
                    scope="metadata",
                    source_path=f"{source_path}/window_days",
                ),
            ]
        )
    return records


def extract_variant_diagnostics(
    payload: Mapping[str, Any], variant_id: str
) -> tuple[list[MetricRecord], ContributorRobustness]:
    """Extract concentration summary without inventing contributor robustness."""
    entity = resolve_entity_exact(variant_id)
    if entity is None or not variant_id.startswith("MD01-"):
        raise ValueError(f"unregistered MD01 variant: {variant_id}")
    variants = _require_mapping(payload.get("variants"), "variants")
    variant_path = f"variants/{variant_id}"
    variant = _require_mapping(variants.get(variant_id), variant_path)
    concentration = _require_mapping(
        variant.get("concentration"), f"{variant_path}/concentration"
    )
    records: list[MetricRecord] = []
    for key in ("hhi", "top_1", "top_3", "top_5"):
        source_path = f"{variant_path}/concentration/{key}"
        records.append(
            MetricRecord(
                entity=entity,
                metric=f"concentration_{key}",
                value=validate_exposure(concentration.get(key), source_path),
                unit="fraction",
                scope="aggregate",
                source_path=source_path,
            )
        )
    fold_values = _require_sequence(
        variant.get("fold_returns"), f"{variant_path}/fold_returns"
    )
    validated_folds: list[float] = []
    for index, raw in enumerate(fold_values):
        source_path = f"{variant_path}/fold_returns/{index}"
        value = validate_spot_return(raw, source_path)
        validated_folds.append(value)
        records.append(
            MetricRecord(
                entity=entity,
                metric="net_return",
                value=value,
                unit="fraction",
                scope="fold",
                source_path=source_path,
                fold_id=_FOLD_IDS[index] if index < len(_FOLD_IDS) else f"FOLD_{index + 1}",
            )
        )
    records.extend(
        [
            MetricRecord(
                entity=entity,
                metric="total_return",
                value=compounded_return(validated_folds),
                unit="fraction",
                scope="aggregate",
                source_path=f"{variant_path}/fold_returns[compounded]",
            ),
            MetricRecord(
                entity=entity,
                metric="net_pnl",
                value=parse_fraction(variant.get("net_pnl")),
                unit="currency",
                scope="aggregate",
                source_path=f"{variant_path}/net_pnl",
            ),
            MetricRecord(
                entity=entity,
                metric="trade_count",
                value=int(variant["trade_count"]),
                unit="count",
                scope="aggregate",
                source_path=f"{variant_path}/trade_count",
            ),
        ]
    )
    robustness = ContributorRobustness(
        status="NOT_EVALUATED",
        judgement="NOT_EVALUATED",
        reason=(
            "The concentration summary contains no per-symbol contribution ledger "
            "and no leave-one-asset-out outcomes."
        ),
    )
    return records, robustness


def extract_beta_folds(
    payload: Mapping[str, Any], variant_id: str
) -> list[MetricRecord]:
    """Extract whitelisted beta fields for an exact variant and explicit folds."""
    entity = resolve_entity_exact(variant_id)
    if entity is None:
        raise ValueError(f"unregistered variant: {variant_id}")
    estimates = _require_sequence(payload.get("fold_estimates"), "fold_estimates")
    records: list[MetricRecord] = []
    metric_units: tuple[tuple[str, MetricUnit], ...] = (
        ("alpha_intercept", "fraction"),
        ("beta", "ratio"),
        ("downside_beta", "ratio"),
        ("upside_beta", "ratio"),
        ("correlation", "ratio"),
        ("r_squared", "ratio"),
        ("residual_return", "fraction"),
        ("residual_volatility", "fraction"),
        ("volatility_matched_btc_return", "fraction"),
        ("maximum_btc_exposure", "fraction"),
        ("observations", "count"),
    )
    for index, estimate_value in enumerate(estimates):
        estimate_path = f"fold_estimates/{index}"
        estimate = _require_mapping(estimate_value, estimate_path)
        if estimate.get("variant_id") != variant_id:
            continue
        fold_id = str(estimate.get("fold_id"))
        if fold_id not in _FOLD_IDS:
            raise ValueError(f"unregistered fold_id at {estimate_path}/fold_id")
        for key, unit in metric_units:
            if key not in estimate or estimate[key] is None:
                continue
            source_path = f"{estimate_path}/{key}"
            raw = estimate[key]
            if key in {"residual_return", "volatility_matched_btc_return"}:
                value: float | int = validate_spot_return(raw, source_path)
            elif key in {"maximum_btc_exposure", "r_squared"}:
                value = validate_exposure(raw, source_path)
            elif unit == "count":
                value = int(raw)
            else:
                value = validate_ratio(raw, source_path)
            records.append(
                MetricRecord(
                    entity=entity,
                    metric=key,
                    value=value,
                    unit=unit,
                    scope="fold",
                    source_path=source_path,
                    fold_id=fold_id,
                )
            )
    return records


def records_as_dicts(records: Sequence[MetricRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]


def aggregate_value(
    records: Sequence[MetricRecord], entity: str, metric: str
) -> float | int | None:
    matches = [
        record
        for record in records
        if record.entity == entity
        and record.metric == metric
        and record.scope == "aggregate"
        and record.status == "VALID"
    ]
    if not matches:
        return None
    values = {record.value for record in matches}
    if len(values) != 1:
        raise ValueError(f"conflicting aggregate values for {entity}/{metric}")
    return matches[0].value


def build_audit(
    *,
    benchmark_records: Sequence[MetricRecord],
    diagnostic_records: Sequence[MetricRecord],
    beta_records: Sequence[MetricRecord],
    m02_robustness: ContributorRobustness,
) -> dict[str, Any]:
    """Build a conservative V2 audit without authorising unsupported comparisons."""
    all_records = [*benchmark_records, *diagnostic_records, *beta_records]
    m05_return = aggregate_value(all_records, "M05_DUAL_28", "total_return")
    equal_weight_return = aggregate_value(
        all_records, "SURVIVOR_30_EQUAL_WEIGHT", "total_return"
    )
    raw_gap: float | None = None
    if isinstance(m05_return, (int, float)) and isinstance(equal_weight_return, (int, float)):
        raw_gap = float(m05_return) - float(equal_weight_return)
    return {
        "schema_version": "ams-bf01-benchmark-fairness-alpha-audit-v2",
        "research_result": "PARTIAL",
        "safety_stop": "PASS",
        "scope": {
            "universe": "SURVIVOR_30_DIAGNOSTIC_ONLY",
            "point_in_time": False,
            "promotable": False,
            "production_ready": False,
            "live_ready": False,
            "md02_authorized": False,
            "kelly_used": False,
            "leverage_used": False,
            "test_2025_accessed": False,
            "holdout_2026_accessed": False,
        },
        "benchmark_audit": {
            "raw_return_comparison_available": raw_gap is not None,
            "m05_total_return": m05_return,
            "equal_weight_total_return": equal_weight_return,
            "m05_minus_equal_weight": raw_gap,
            "risk_adjusted_comparison_authorized": False,
            "exposure_matched_comparison_authorized": False,
            "volatility_matched_comparison_authorized": False,
            "alpha_value_judgement": "INCONCLUSIVE",
            "reason": (
                "Aligned validated M05 and Equal-weight daily series were not supplied; "
                "raw aggregate returns alone cannot establish or destroy alpha."
            ),
        },
        "m02_tsm84": {
            "contributor_robustness": asdict(m02_robustness),
        },
        "metrics": records_as_dicts(all_records),
        "invariants": {
            "exact_entity_matching": True,
            "aggregate_fold_separation": True,
            "explicit_metric_units": True,
            "single_percent_scaling": True,
            "snapshot_time_alias_present": "snapshot_time" in DATE_COLUMNS,
            "metadata_metric_separation": True,
            "domain_gates_enabled": True,
            "missing_data_returns_not_evaluated": True,
        },
    }
