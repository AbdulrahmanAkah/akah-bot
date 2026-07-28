"""Write RD05 P0 registries without reading market bars or evaluating signals."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

from spotbot.research.rd05_protocol_registration import (
    REGIMES,
    SAFETY,
    SIGNAL_FAMILIES,
    STAGES,
    TRIAL_BUDGET,
    build_protocol,
    label_rows,
    text_contract_valid,
    validate_protocol,
    variant_rows,
)

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports" / "research"
OUT = {
    name: REPORTS / file
    for name, file in {
        "protocol": "ams-rd05-protocol-registration-v1.json",
        "markdown": "ams-rd05-protocol-registration-v1.md",
        "source": "ams-rd05-source-registry-v1.csv",
        "labels": "ams-rd05-label-registry-v1.csv",
        "families": "ams-rd05-signal-family-registry-v1.csv",
        "variants": "ams-rd05-signal-variant-registry-v1.csv",
        "regimes": "ams-rd05-regime-registry-v1.csv",
        "metrics": "ams-rd05-metric-registry-v1.csv",
        "trials": "ams-rd05-trial-budget-v1.csv",
        "validation": "ams-rd05-validation-protocol-v1.csv",
        "stages": "ams-rd05-stage-ledger-v1.csv",
        "authorization": "ams-rd05-authorization-ledger-v1.csv",
        "upstream": "ams-rd05-upstream-reconciliation-v1.csv",
        "literature": "ams-rd05-literature-source-registry-v1.csv",
    }.items()
}
UPSTREAM = {
    "RD04_FINAL": "reports/research/ams-rd04-final-adjudication-v1.json",
    "RD04_CANDIDATES": "reports/research/ams-rd04-final-rd05-candidate-program-v1.csv",
    "RD04_ROOT_CAUSES": "reports/research/ams-rd04-final-root-cause-ledger-v1.csv",
    "RD04_OPEN_QUESTIONS": "reports/research/ams-rd04-final-open-questions-v1.csv",
    "RD04_AUTHORIZATION": "reports/research/ams-rd04-final-authorization-ledger-v1.csv",
    "D0C_DATASET": "reports/research/ams-rd04-d0c-adjudicated-dataset-registration-v1.json",
    "D5A_TURNOVER": "reports/research/ams-rd04-d5a-turnover-dataset-registration-v1.json",
}
PIT_MEMBERSHIP_HASH = "17cf3cca1400c071afe75b86342b09718aba2f84992777f18ffb17436f9a138b"


class RegistrationError(RuntimeError):
    """Raised when frozen RD05 sources cannot be reconciled."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def load_json(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise RegistrationError(f"not a JSON object: {path}")
    return result


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise RegistrationError(f"empty registry: {path}")
    buffer = StringIO(newline="")
    fields = list(rows[0])
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(path, buffer.getvalue())


def upstream() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    jsons: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for identifier, relative in UPSTREAM.items():
        path = ROOT / relative
        exists = path.is_file()
        digest = sha256(path) if exists else "MISSING"
        row: dict[str, Any] = {
            "source_id": identifier,
            "path": relative,
            "exists": exists,
            "sha256": digest,
            "status": "NOT_RECORDED",
            "decision": "NOT_RECORDED",
            "reconciliation_pass": exists,
        }
        if not exists:
            rows.append(row)
            continue
        hashes[identifier] = digest
        if path.suffix == ".json":
            report = load_json(path)
            jsons[identifier] = report
            row["status"] = report.get("status", "NOT_RECORDED")
            row["decision"] = mapping(report.get("decision")).get("decision", "NOT_RECORDED")
        rows.append(row)
    if not all(row["reconciliation_pass"] for row in rows):
        raise RegistrationError("required upstream artifact missing")
    final = jsons["RD04_FINAL"]
    decision = mapping(final.get("final_adjudication"))
    if (
        final.get("status") != "COMPLETE"
        or decision.get("rd05_authorization") != "RD05_PROTOCOL_REGISTRATION_ONLY"
    ):
        raise RegistrationError("RD04 did not authorize RD05 protocol registration only")
    for relative, expected in mapping(final.get("output_hashes")).items():
        if (
            not isinstance(relative, str)
            or not isinstance(expected, str)
            or sha256(ROOT / relative) != expected
        ):
            raise RegistrationError("RD04 final evidence hash mismatch")
    return jsons, rows, hashes


def source_rows(d0c: Mapping[str, Any], turnover: Mapping[str, Any]) -> list[dict[str, Any]]:
    datasets = mapping(d0c.get("datasets"))
    rows: list[dict[str, Any]] = []
    for key, sid, timeframe in (
        ("four_hour", "OHLCV_4H", "4H"),
        ("eight_hour", "OHLCV_8H", "8H"),
        ("daily", "OHLCV_1D", "1D"),
        ("availability", "AVAILABILITY", "INTERVAL"),
    ):
        item = mapping(datasets.get(key))
        rows.append(
            {
                "source_id": sid,
                "path": item.get("path", "NOT_RECORDED"),
                "registered_sha256": item.get("file_sha256", "NOT_RECORDED"),
                "timeframe": timeframe,
                "first_time": item.get("first_bar_open_time", "NOT_RECORDED"),
                "last_time": item.get("last_bar_close_time", "NOT_RECORDED"),
                "row_count": item.get("row_count", "NOT_RECORDED"),
                "symbol_count": item.get("symbol_count", "NOT_RECORDED"),
                "causal_availability": "CLOSED_BARS_OR_PIT_INTERVALS_IN_LATER_P1",
                "allowed_stages": "P1|P2",
                "prohibited_uses": "P0_COMPUTATION",
                "verification_status": "UPSTREAM_REGISTERED_NOT_READ_IN_P0",
            }
        )
    quote = mapping(mapping(turnover.get("datasets")).get("four_hour"))
    rows.extend(
        (
            {
                "source_id": "PIT_MEMBERSHIP",
                "path": "reports/research/ams-rd04-d0c-venue-eligible-weekly-candidates-v1.csv",
                "registered_sha256": PIT_MEMBERSHIP_HASH,
                "timeframe": "WEEKLY_MONDAY_UTC",
                "first_time": "2022-01-03T00:00:00Z",
                "last_time": "2024-12-30T00:00:00Z",
                "row_count": 4710,
                "symbol_count": 66,
                "causal_availability": "MONDAY_DECISION_SNAPSHOTS",
                "allowed_stages": "P1|P2",
                "prohibited_uses": "P0_COMPUTATION",
                "verification_status": "UPSTREAM_REGISTERED_NOT_READ_IN_P0",
            },
            {
                "source_id": "QUOTE_TURNOVER_4H",
                "path": quote.get("path", "NOT_RECORDED"),
                "registered_sha256": quote.get("file_sha256", "NOT_RECORDED"),
                "timeframe": "4H",
                "first_time": "2021-01-01T00:00:00Z",
                "last_time": "2025-01-01T00:00:00Z",
                "row_count": quote.get("row_count", "NOT_RECORDED"),
                "symbol_count": quote.get("pair_count", "NOT_RECORDED"),
                "causal_availability": "PENDING_P1_NATIVE_FIELD_CONTRACT",
                "allowed_stages": "P1_ONLY",
                "prohibited_uses": "P0_COMPUTATION|S1_UNTIL_P1_PASS",
                "verification_status": "BLOCKED_PENDING_DATA_CONTRACT",
            },
        )
    )
    return rows


def rows() -> dict[str, list[dict[str, Any]]]:
    primary = [
        "SPEARMAN_RANK_IC",
        "MEAN_RANK_IC",
        "MEDIAN_RANK_IC",
        "IC_INFORMATION_RATIO",
        "POSITIVE_IC_PERIOD_SHARE",
        "TOP_QUINTILE_MINUS_UNIVERSE_MEAN",
        "TOP_QUINTILE_HIT_RATE",
        "QUANTILE_MONOTONICITY",
        "FOLD_SIGN_CONSISTENCY",
        "REGIME_SIGN_CONSISTENCY",
    ]
    secondary = [
        "TOP_MINUS_BOTTOM_DIAGNOSTIC",
        "MFE_MAE_BY_QUINTILE",
        "SCORE_TURNOVER",
        "SYMBOL_CONCENTRATION",
        "EFFECTIVE_SAMPLE_SIZE",
        "MISSING_LABEL_SHARE",
    ]
    folds = [("WF01", "2021", "2022"), ("WF02", "2021-2022", "2023"), ("WF03", "2021-2023", "2024")]
    literature = [
        (
            "LIT-01",
            "Common Risk Factors in Cryptocurrency",
            "Liu, Tsyvinski, Wu",
            2022,
            "https://doi.org/10.1111/jofi.13119",
        ),
        (
            "LIT-02",
            "Cross-sectional Momentum in Cryptocurrency Markets",
            "Drogen, Hoffstein, Otte",
            2023,
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4322637",
        ),
        (
            "LIT-03",
            "Cryptocurrency Momentum and Reversal",
            "Dobrynskaya",
            2023,
            "https://publications.hse.ru/en/articles/811744977",
        ),
        (
            "LIT-04",
            "Time Series Momentum",
            "Moskowitz, Ooi, Pedersen",
            2012,
            "https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf",
        ),
        (
            "LIT-05",
            "Investor attention in cryptocurrency markets",
            "Smales",
            2022,
            "https://doi.org/10.1016/j.irfa.2021.101972",
        ),
        (
            "LIT-06",
            "The Probability of Backtest Overfitting",
            "Bailey, Borwein, Lopez de Prado, Zhu",
            2016,
            "https://doi.org/10.2139/ssrn.2326253",
        ),
        (
            "LIT-07",
            "The Deflated Sharpe Ratio",
            "Bailey, Lopez de Prado",
            2014,
            "https://doi.org/10.2139/ssrn.2460551",
        ),
    ]
    return {
        "labels": label_rows(),
        "families": list(SIGNAL_FAMILIES),
        "variants": variant_rows(),
        "regimes": [dict(item, execution_status="REGISTERED_NOT_COMPUTED") for item in REGIMES],
        "metrics": [
            {"metric_id": name, "tier": "PRIMARY", "portfolio_metric": False} for name in primary
        ]
        + [
            {"metric_id": name, "tier": "SECONDARY", "portfolio_metric": False}
            for name in secondary
        ],
        "trials": [
            {"budget_key": k, "declared_count": v, "execution_status": "NOT_EXECUTED"}
            for k, v in TRIAL_BUDGET.items()
        ],
        "validation": [
            {
                "fold_id": f,
                "train": t,
                "validation": v,
                "purge_embargo_days": 28,
                "random_shuffle_allowed": False,
            }
            for f, t, v in folds
        ],
        "stages": [
            {
                "stage_id": stage,
                "purpose": "GATED_RD05_STAGE",
                "next_stage_authorization": "CLOSED_UNTIL_PRIOR_PASS",
                "prohibited_operations": "UNREGISTERED_EXECUTION",
            }
            for stage in STAGES
        ],
        "authorization": [
            {
                "flag": k,
                "value": v,
                "passed": v is True
                if k.startswith("no_") or k in {"spot_only", "long_only"}
                else v is False,
            }
            for k, v in SAFETY.items()
        ]
        + [
            {
                "flag": "rd05_signal_data_contract_and_panel_build_authorized",
                "value": True,
                "passed": True,
            }
        ],
        "literature": [
            {
                "source_id": i,
                "title": title,
                "authors": authors,
                "year": year,
                "source_type": "METHODOLOGICAL_BACKGROUND",
                "economic_claim": "not treated as local evidence",
                "methodological_use_in_rd05": "registry design only",
                "not_treated_as_local_evidence": True,
                "verification_status": "VERIFIED",
                "url": url,
            }
            for i, title, authors, year, url in literature
        ],
    }


def markdown(protocol: Mapping[str, Any]) -> str:
    decision = mapping(protocol["decision"])
    return "\n".join(
        [
            "# RD05 Alpha Discovery Protocol Registration",
            "",
            f"- Status: `{protocol['status']}`",
            f"- Decision: `{decision['decision']}`",
            f"- Next: `{decision['next_stage']}`",
            f"- Frozen variants: `{protocol['signal_variant_count']}`",
            "",
            "RD05 tests primitive predictive content before ranking, portfolio construction,",
            "and exits.",
            "P0 computed no bars, signals, labels, returns, models, backtests, or portfolios.",
            "Only P1 source-contract and panel-build registration is authorized next.",
            "Portfolio simulation remains false.",
            "",
        ]
    )


def run() -> dict[str, Any]:
    validate_protocol()
    loaded, upstream_rows, hashes = upstream()
    protocol = build_protocol(hashes)
    protocol["generated_at_utc"] = datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")
    protocol["source_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    protocol["upstream_reconciliation_failures"] = 0
    all_rows = rows()
    all_rows["source"] = source_rows(loaded["D0C_DATASET"], loaded["D5A_TURNOVER"])
    all_rows["upstream"] = upstream_rows
    for name, path in OUT.items():
        if name in {"protocol", "markdown"}:
            continue
        write_csv(path, all_rows[name])
    protocol["output_hashes"] = {
        path.relative_to(ROOT).as_posix(): sha256(path)
        for name, path in OUT.items()
        if name not in {"protocol", "markdown"}
    }
    atomic_text(OUT["protocol"], json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    rendered = markdown(protocol) + "\n"
    if not text_contract_valid(rendered):
        raise RegistrationError("text contract failed")
    atomic_text(OUT["markdown"], rendered)
    atomic_text(ROOT / "RD05_PROTOCOL_REGISTRATION_FOR_CHATGPT.md", rendered)
    atomic_text(ROOT / "RD05_PROTOCOL_RESULT_FOR_CHATGPT.md", rendered)
    return protocol


def main() -> None:
    protocol = run()
    print(f"RD05_STATUS={protocol['status']}")
    print(f"RD05_DECISION={mapping(protocol['decision'])['decision']}")
    print(f"NEXT_STAGE={mapping(protocol['decision'])['next_stage']}")
    print("SIGNAL_EXECUTION=NOT_EXECUTED")
    print("PORTFOLIO_SIMULATION_AUTHORIZED=false")
    print("TEST_2025_ACCESSED=false")
    print("HOLDOUT_2026_ACCESSED=false")


if __name__ == "__main__":
    main()
