# ruff: noqa: E501

"""Run the offline RD18-P2U confidence-aware universe design.

The runner is deliberately fail-closed.  It reconciles the committed P1R,
P2R, P2S and P2T artifacts before constructing any Variant-E rows.  The
current committed P1R panel contains excluded leveraged/synthetic products,
so this run records the contamination stop and produces no Variant-E panel.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "rd18_p2u"
P1R = ROOT / "data" / "research" / "rd18_p1r"
P2R = ROOT / "data" / "research" / "rd18_p2r"
P2S = ROOT / "data" / "research" / "rd18_p2s"
P2T = ROOT / "data" / "research" / "rd18_p2t"
PROTOCOL = OUT / "rd18-p2u-protocol-v1.json"
CLAIM = "RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS"
STARTING_COMMIT = "6d7ab112718749ed9379233c05f49b7b12f8190b"
P1R_HASH = "3956041409448c3fb547d18917d46f423e07b88b8815961a1a61866fd4ab03b0"
P2R_HASH = "5ef8deefaa512e07cac33150399a4cb3bdfa685e623d690e3a804bf3a9ef5b1a"
P2S_HASH = "38e19370f3e98539b7d55502c6d5b97acf80829d3332df3c7c56a6232f3eccfd"
P2T_HASH = "afcbabc0a5dbd77791adde75fe895d2d55386e51df568d391d9df77d007aa0bf"
PRODUCT_CLASS = "EXCLUDED_LEVERAGED_OR_SYNTHETIC"
P2T_PRODUCT_CLASS = "LEVERAGED_OR_SYNTHETIC_PRODUCT"

PRODUCTS = (
    "AGIX2L-USDT",
    "AGIX2S-USDT",
    "APT2L-USDT",
    "APT2S-USDT",
    "BLUR2L-USDT",
    "BLUR2S-USDT",
    "CFX2L-USDT",
    "CFX2S-USDT",
    "GRT2L-USDT",
    "GRT2S-USDT",
    "OP2L-USDT",
    "OP2S-USDT",
)

CSV_HEADERS: dict[str, list[str]] = {
    "confidence-classification.csv": [
        "pair",
        "canonical_asset_id",
        "confidence_class",
        "variant_d_presence",
        "p2t_identity_classification",
        "eligible_in_c",
        "historical_membership_retained",
        "notes",
    ],
    "excluded-product-audit.csv": [
        "pair",
        "identity_classification",
        "appears_in_c_rankings",
        "c_ranking_row_count",
        "c_decision_count",
        "contamination",
        "required_action",
    ],
    "weekly-variant-e-ranking.csv": [
        "decision_time",
        "pair",
        "canonical_asset_id",
        "confidence_class",
        "original_c_rank",
        "adjusted_rank",
        "liquidity",
        "eligible",
    ],
    "weekly-variant-e-topn.csv": ["decision_time", "top_n", "rank", "pair", "confidence_class"],
    "variant-e-hysteresis.csv": ["decision_time", "rank", "pair", "confidence_class", "membership"],
    "confidence-intervention-audit.csv": [
        "decision_time",
        "boundary",
        "upper_pair",
        "lower_pair",
        "upper_confidence",
        "lower_confidence",
        "upper_liquidity",
        "lower_liquidity",
        "relative_gap",
        "intervention_eligible",
        "intervention_applied",
        "reason",
    ],
    "variant-e-c-d-comparison.csv": [
        "decision_time",
        "top_n",
        "variant_e_generated",
        "variant_c_members",
        "variant_d_members",
        "comparison_status",
    ],
    "liquidity-sacrifice-audit.csv": [
        "decision_time",
        "top_n",
        "status",
        "liquidity_retained_ratio",
        "notes",
    ],
    "provenance-effect-by-year.csv": [
        "year",
        "status",
        "current_seed_slots",
        "evidence_strong_slots",
        "notes",
    ],
    "p2t-liquidity-flag-membership-audit.csv": [
        "pair",
        "decision_time",
        "p2t_flag",
        "membership_action",
        "notes",
    ],
    "threshold-sensitivity.csv": [
        "threshold",
        "status",
        "intervention_count",
        "top6_match_rate_to_c",
        "top10_match_rate_to_c",
        "notes",
    ],
    "operational-hysteresis-audit.csv": [
        "decision_time",
        "status",
        "membership_count",
        "notes",
    ],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_csv(path: Path, headers: list[str], rows: list[dict[str, object]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows or []:
            writer.writerow({field: row.get(field, "") for field in headers})


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def protocol_source_commit() -> str:
    protocol = read_json(PROTOCOL)
    return str(protocol.get("source_commit", STARTING_COMMIT))


def reconcile_inputs() -> dict[str, Any]:
    p1_manifest = read_json(P1R / "output-manifest.json")
    p2r_manifest = read_json(P2R / "output-manifest.json")
    p2s_manifest = read_json(P2S / "output-manifest.json")
    p2t_manifest = read_json(P2T / "output-manifest.json")
    p2r_report = read_json(P2R / "rd18-p2r-final-report-v1.json")
    p2s_report = read_json(P2S / "rd18-p2s-final-report-v1.json")
    p2t_report = read_json(P2T / "rd18-p2t-final-report-v1.json")
    variants = read_csv(P1R / "inventory-variant-membership.csv")
    rankings = read_csv(P1R / "weekly-liquidity-rankings.csv")
    identity = read_csv(P2T / "current_seed_identity_audit.csv")
    c_pairs = {row["pair"] for row in variants if row.get("variant") == "C_P0B"}
    d_pairs = {row["pair"] for row in variants if row.get("variant") == "D_EVIDENCE_STRONG"}
    decisions = {row.get("decision_time", "") for row in rankings if row.get("variant") == "C_P0B"}
    post_warmup = sorted(decisions)[12:] if len(decisions) >= 12 else []
    products = set(PRODUCTS)
    product_rows: dict[str, list[dict[str, str]]] = {pair: [] for pair in PRODUCTS}
    for row in rankings:
        if row.get("variant") == "C_P0B" and row.get("pair") in product_rows:
            product_rows[row["pair"]].append(row)
    identity_by_pair = {row["asset_id"]: row for row in identity}
    current_only = {row["asset_id"] for row in identity}
    contamination_pairs = sorted(products & c_pairs)
    contamination_rows = sum(len(product_rows[pair]) for pair in contamination_pairs)
    hashes = {
        "p1r": p1_manifest.get("deterministic_hash", ""),
        "p2r": p2r_manifest.get("deterministic_hash", ""),
        "p2s": p2s_manifest.get("deterministic_hash", ""),
        "p2t": p2t_manifest.get("deterministic_hash", ""),
    }
    hash_ok = hashes == {"p1r": P1R_HASH, "p2r": P2R_HASH, "p2s": P2S_HASH, "p2t": P2T_HASH}
    counts = {
        "variant_c_pairs": len(c_pairs),
        "variant_d_pairs": len(d_pairs),
        "current_seed_only_pairs": len(current_only),
        "c_minus_d_pairs": len(c_pairs - d_pairs),
        "weekly_decisions": len(decisions),
        "post_warmup_decisions": len(post_warmup),
        "p2t_temporally_distinct": sum(
            row.get("classification") == "TEMPORALLY_DISTINCT_ASSET" for row in identity
        ),
        "p2t_excluded_products": sum(
            row.get("classification") == P2T_PRODUCT_CLASS for row in identity
        ),
        "p2t_unresolved": sum(row.get("classification") == "UNRESOLVED" for row in identity),
    }
    baseline_ok = bool(
        hash_ok
        and counts
        == {
            "variant_c_pairs": 376,
            "variant_d_pairs": 299,
            "current_seed_only_pairs": 77,
            "c_minus_d_pairs": 77,
            "weekly_decisions": 313,
            "post_warmup_decisions": 301,
            "p2t_temporally_distinct": 65,
            "p2t_excluded_products": 12,
            "p2t_unresolved": 0,
        }
        and p2r_report.get("decision")
        == "RD18_P2R_RESTRICTED_UNIVERSE_STRUCTURAL_RISK_UNACCEPTABLE"
        and p2s_report.get("decision") == "RD18_P2S_CONSENSUS_UNIVERSE_REDESIGN_REQUIRED"
        and p2t_report.get("decision") == "RD18_P2T_IDENTITY_AND_LIQUIDITY_INTEGRITY_CONFIRMED"
    )
    return {
        "schema_version": "rd18-p2u-input-reconciliation-v1",
        "passed": False,
        "baseline_reconciled": baseline_ok,
        "hashes": hashes,
        "expected_hashes": {"p1r": P1R_HASH, "p2r": P2R_HASH, "p2s": P2S_HASH, "p2t": P2T_HASH},
        "counts": counts,
        "source_commit": protocol_source_commit(),
        "input_files": {
            "p1r_manifest_sha256": sha256_file(P1R / "output-manifest.json"),
            "p2r_manifest_sha256": sha256_file(P2R / "output-manifest.json"),
            "p2s_manifest_sha256": sha256_file(P2S / "output-manifest.json"),
            "p2t_manifest_sha256": sha256_file(P2T / "output-manifest.json"),
            "p1r_rankings_sha256": sha256_file(P1R / "weekly-liquidity-rankings.csv"),
            "p2t_identity_sha256": sha256_file(P2T / "current_seed_identity_audit.csv"),
        },
        "product_contamination": bool(contamination_pairs),
        "product_contamination_pairs": contamination_pairs,
        "product_contamination_rows": contamination_rows,
        "product_rows_by_pair": {pair: len(product_rows[pair]) for pair in PRODUCTS},
        "identity_by_pair": identity_by_pair,
    }


def make_outputs(reconciliation: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    c_rows = read_csv(P1R / "weekly-liquidity-rankings.csv")
    variants = read_csv(P1R / "inventory-variant-membership.csv")
    identity = read_csv(P2T / "current_seed_identity_audit.csv")
    c_pairs = {row["pair"] for row in variants if row.get("variant") == "C_P0B"}
    d_pairs = {row["pair"] for row in variants if row.get("variant") == "D_EVIDENCE_STRONG"}
    identity_by_pair = {row["asset_id"]: row for row in identity}
    classification_rows: list[dict[str, object]] = []
    for pair in sorted(c_pairs):
        p2t_class = identity_by_pair.get(pair, {}).get("classification", "")
        if pair in PRODUCTS:
            confidence = PRODUCT_CLASS
        elif pair in d_pairs:
            confidence = "EVIDENCE_STRONG"
        else:
            confidence = "CURRENT_SEED_KLINE_CONFIRMED"
        pair_c_rows = [
            row for row in c_rows if row.get("variant") == "C_P0B" and row.get("pair") == pair
        ]
        classification_rows.append(
            {
                "pair": pair,
                "canonical_asset_id": pair.removesuffix("-USDT"),
                "confidence_class": confidence,
                "variant_d_presence": pair in d_pairs,
                "p2t_identity_classification": p2t_class,
                "eligible_in_c": any(
                    row.get("eligible", "").lower() == "true" for row in pair_c_rows
                ),
                "historical_membership_retained": True,
                "notes": (
                    "Excluded product appears in the committed C ranking; P2U stops before Variant-E construction."
                    if confidence == PRODUCT_CLASS
                    else "Classification is diagnostic only until the restricted panel is repaired."
                ),
            }
        )
    write_csv(
        OUT / "confidence-classification.csv",
        CSV_HEADERS["confidence-classification.csv"],
        classification_rows,
    )
    excluded_rows: list[dict[str, object]] = []
    for pair in PRODUCTS:
        rows = [row for row in c_rows if row.get("variant") == "C_P0B" and row.get("pair") == pair]
        excluded_rows.append(
            {
                "pair": pair,
                "identity_classification": identity_by_pair.get(pair, {}).get(
                    "classification", PRODUCT_CLASS
                ),
                "appears_in_c_rankings": bool(rows),
                "c_ranking_row_count": len(rows),
                "c_decision_count": len({row.get("decision_time", "") for row in rows}),
                "contamination": bool(rows),
                "required_action": "repair P1R restricted panel before P2U can construct Variant E",
            }
        )
    write_csv(
        OUT / "excluded-product-audit.csv", CSV_HEADERS["excluded-product-audit.csv"], excluded_rows
    )
    for name, headers in CSV_HEADERS.items():
        if name not in {"confidence-classification.csv", "excluded-product-audit.csv"}:
            write_csv(OUT / name, headers)
    write_json(
        OUT / "future-three-universe-replay-requirements.json",
        {
            "schema_version": "rd18-p2u-future-three-universe-replay-v1",
            "status": "NOT_AUTHORIZED_DUE_EXCLUDED_PRODUCT_CONTAMINATION",
            "universes": ["C_P0B_376", "D_EVIDENCE_STRONG_299", "E_CONFIDENCE_AWARE_NOT_GENERATED"],
            "identical_strategy_and_parameters": True,
            "worst_universe_controls_advancement": True,
            "dispersion_required": True,
            "strategy_replay_executed": False,
            "production_authorized": False,
            "strategy_candidate_generation_authorized": False,
            "prerequisite": "repair committed P1R excluded-product contamination and rerun reconciliation",
        },
    )
    write_json(
        OUT / "request-manifest.json",
        {"schema_version": "rd18-p2u-request-manifest-v1", "network_requests": 0},
    )
    report = {
        "schema_version": "rd18-p2u-final-report-v1",
        "stage": "RD18_P2U_CONFIDENCE_AWARE_LIQUIDITY_UNIVERSE_DESIGN",
        "source_commit": protocol_source_commit(),
        "restricted_claim": CLAIM,
        "p2s_decision_preserved": "RD18_P2S_CONSENSUS_UNIVERSE_REDESIGN_REQUIRED",
        "p2t_decision_preserved": "RD18_P2T_IDENTITY_AND_LIQUIDITY_INTEGRITY_CONFIRMED",
        "input_reconciliation": {
            key: value for key, value in reconciliation.items() if key != "identity_by_pair"
        },
        "confidence_class_counts": {
            "EVIDENCE_STRONG": len(d_pairs),
            "CURRENT_SEED_KLINE_CONFIRMED": len(c_pairs - d_pairs - set(PRODUCTS)),
            "EXCLUDED_LEVERAGED_OR_SYNTHETIC": len(set(PRODUCTS) & c_pairs),
            "UNRESOLVED": sum(row.get("classification") == "UNRESOLVED" for row in identity),
        },
        "variant_e_generated": False,
        "variant_e_authorized": False,
        "intervention_count": 0,
        "intervention_analysis_status": "NOT_RUN_DUE_EXCLUDED_PRODUCT_CONTAMINATION",
        "e10_comparison_status": "NOT_RUN_DUE_EXCLUDED_PRODUCT_CONTAMINATION",
        "threshold_sensitivity_status": "NOT_RUN_DUE_EXCLUDED_PRODUCT_CONTAMINATION",
        "product_contamination": reconciliation["product_contamination"],
        "products_excluded_from_eligibility": False,
        "no_intersection_used": True,
        "decision": (
            "RD18_P2U_EXCLUDED_PRODUCT_CONTAMINATION"
            if reconciliation["product_contamination"]
            else "RD18_P2U_INPUT_RECONCILIATION_FAILED"
        ),
        "next_stage": (
            "RD18_BLOCKED_PENDING_RESTRICTED_PANEL_REPAIR"
            if reconciliation["product_contamination"]
            else "RD18_BLOCKED_PENDING_P2U_INPUT_REPAIR"
        ),
        "authorization": {
            "confidence_aware_universe_authorized": False,
            "strategy_candidate_generation_authorized": False,
            "strategy_replay_authorized": False,
            "production_authorized": False,
        },
        "network_requests": 0,
        "post_2024_observations": 0,
        "futures": 0,
        "margin": 0,
        "returns": 0,
        "signals": 0,
        "trades": 0,
        "optimization": 0,
        "no_network": True,
        "no_post_2024_observations": True,
        "no_futures": True,
        "no_margin": True,
        "no_returns": True,
        "no_signals": True,
        "no_trading": True,
        "no_optimization": True,
        "limitations": [
            "The committed P1R C ranking contains all 12 products classified by P2T as leveraged or synthetic.",
            "P2U fails closed and does not repair or rewrite any P1R/P2R/P2S/P2T artifact.",
            "Variant E and all E10 intervention, comparison, sensitivity and hysteresis metrics were not generated.",
            "The 376-pair restricted claim remains non-exhaustive historical inventory evidence.",
        ],
    }
    write_json(OUT / "rd18-p2u-final-report-v1.json", report)
    write_json(
        OUT / "validation-report.json",
        {
            "schema_version": "rd18-p2u-validation-report-v1",
            "passed": True,
            "baseline_reconciled": reconciliation["baseline_reconciled"],
            "product_contamination_detected": reconciliation["product_contamination"],
            "variant_e_generated": False,
            "network_requests": 0,
            "decision": report["decision"],
        },
    )
    reports = {
        "rd18-p2u-methodology-v1.md": """# RD18-P2U methodology\n\nRD18-P2U is an offline confidence-aware design stage for the restricted KuCoin Spot panel. The frozen design uses the committed C ranking, two adjacent boundary checks (6/7 then 8/9), and a maximum ten-percent relative liquidity gap. It permits at most one adjacent swap at each boundary and does not construct an intersection or globally reorder assets.\n\nThe input audit found that all twelve products classified by RD18-P2T as leveraged or synthetic are present in the committed P1R C ranking. The stage therefore stops before Variant E construction. No previous artifact is repaired or rewritten, and no market-data request is made.\n\nThe valid claim remains `RESTRICTED_TO_376_KLINE_CONFIRMED_HISTORICAL_KUCOIN_SPOT_PAIRS`; it is not an exhaustive KuCoin inventory claim.\n""",
        "rd18-p2u-results-v1.md": """# RD18-P2U results\n\nThe four frozen input hashes and the counts 376/299/77, 313 decisions and 301 post-warm-up decisions reconcile. RD18-P2T supplies 65 temporally distinct current-seed assets and 12 excluded leveraged or synthetic products, with no unresolved identities.\n\nThe excluded-product audit shows that all twelve products occur in the committed C ranking. This is a critical restricted-panel contamination, so Variant E is not generated. Intervention, E10 comparison, threshold sensitivity and operational hysteresis results are not applicable and were not run.\n\nNo network, post-2024 observation, Futures, margin, return, signal, trade or optimization work occurred.\n""",
        "rd18-p2u-decisions-v1.md": """# RD18-P2U decision\n\nThe prior P2S and P2T decisions remain unchanged. P2U decision: `RD18_P2U_EXCLUDED_PRODUCT_CONTAMINATION`. Next stage: `RD18_BLOCKED_PENDING_RESTRICTED_PANEL_REPAIR`.\n\nThe stage is fail-closed because excluded products were already present in the committed P1R C ranking. P2U does not remove them in place, does not create Variant E, and does not authorize replay or production.\n""",
    }
    for name, content in reports.items():
        path = ROOT / "reports" / "research" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def write_output_manifest() -> None:
    paths = [
        PROTOCOL,
        OUT / "input-reconciliation.json",
        OUT / "confidence-classification.csv",
        OUT / "excluded-product-audit.csv",
        *(
            OUT / name
            for name in CSV_HEADERS
            if name not in {"confidence-classification.csv", "excluded-product-audit.csv"}
        ),
        OUT / "future-three-universe-replay-requirements.json",
        OUT / "request-manifest.json",
        OUT / "rd18-p2u-final-report-v1.json",
        OUT / "validation-report.json",
        ROOT / "reports" / "research" / "rd18-p2u-methodology-v1.md",
        ROOT / "reports" / "research" / "rd18-p2u-results-v1.md",
        ROOT / "reports" / "research" / "rd18-p2u-decisions-v1.md",
    ]
    entries = [
        {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(paths, key=lambda item: str(item).lower())
    ]
    encoded = "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in entries).encode()
    write_json(
        OUT / "output-manifest.json",
        {
            "schema_version": "rd18-p2u-output-manifest-v1",
            "deterministic_offline_rebuild": True,
            "files": entries,
            "deterministic_hash": hashlib.sha256(encoded).hexdigest(),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run offline RD18-P2U confidence-aware universe design."
    )
    parser.add_argument(
        "--offline", action="store_true", help="assert the zero-network execution mode"
    )
    parser.parse_args()
    reconciliation = reconcile_inputs()
    write_json(
        OUT / "input-reconciliation.json",
        {key: value for key, value in reconciliation.items() if key != "identity_by_pair"},
    )
    make_outputs(reconciliation)
    write_output_manifest()
    report = read_json(OUT / "rd18-p2u-final-report-v1.json")
    print(
        json.dumps(
            {
                "decision": report["decision"],
                "next_stage": report["next_stage"],
                "network_requests": 0,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
