"""Precommitted qualification rules; market replay is intentionally hard-disabled."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

PROTOCOL = "AKAH_GATE3_PRECOMMITTED_QUALIFICATION_V1"
PRIMARY_GRAMMARS = ("FS_ICT_2022_CORE_CRYPTO_LONG", "FS_CLASSICAL_FULL_LONG")


def specification():
    return {
        "protocol_id": PROTOCOL,
        "version": 2,
        "scope_status": "PROSPECTIVE_BLOCKED",
        "funded_grammars": [],
        "primary_claim_family": list(PRIMARY_GRAMMARS),
        "claim_family_must_not_shrink": True,
        "window": {"since": "2022-01-01T00:00:00Z", "until_exclusive": "2024-01-01T00:00:00Z"},
        "costs_round_trip": {"1X": 0.0025, "2X": 0.005},
        "risk": {
            "contract": "AKAH_CURRENT_MTM_THESIS_RISK_V1",
            "initial_equity": 100000,
            "new_thesis": 0.005,
            "open_stop_risk": 0.025,
            "gross_mtm": 0.90,
            "asset_mtm": 0.18,
            "distinct_assets": 5,
            "cluster": "CRYPTO_SPOT_LONG_ZERO_DIVERSIFICATION_CREDIT",
        },
        "capital_capacity": 0.005,
        "unknown_capacity": "NO_NEW_RISK",
        "quantity_normalizer": "UNRESOLVED_HISTORICAL_PIT_AUTHORITY_REQUIRED",
        "selector": "AKAH_SHARED_FEASIBILITY_FIFO_LIQUIDITY_V1",
        "router": "AKAH_STRUCTURAL_ROUTER_V1",
        "hard_rules": [
            "2022_2X_NET_GT_0",
            "2023_2X_NET_GT_0",
            "COMBINED_1X_2X_NET_GT_0",
            "HOURLY_MTM_MDD_LE_20_PERCENT_1X_2X",
            "ALL_RISK_EXECUTION_LIMITS_PASS",
            "CONCENTRATION_PASS",
            "UNCERTAINTY_PASS",
        ],
        "concentration": {
            "unit": "CAMPAIGN_ALL_LEGS_AND_FEES",
            "scenario": "2X",
            "campaign_residual": "P-max(0,max_campaign_net)>0",
            "asset_residual": "P-max(0,max_asset_net)>0",
            "annual_and_top3_top5": "DIAGNOSTIC_ONLY",
            "interpretation": "DELETION_ATTRIBUTION_NOT_COUNTERFACTUAL_REPLAY",
        },
        "uncertainty": {
            "series": "DAILY_NET_MTM_LOG_RETURN_INCLUDING_CASH_DAYS",
            "estimator": "arch.bootstrap.optimal_block_length:stationary",
            "within_year_block_length": "MAX_ACROSS_PREREGISTERED_ARMS",
            "stratify": "YEAR",
            "paired_indices": True,
            "replications": 9999,
            "seed": "AKAH_GATE3_UNCERTAINTY_V1",
            "family_alpha": 0.05,
            "correction": "BONFERRONI_FIXED_PRIMARY_FAMILY",
            "LCB": "theta-quantile(theta_star-theta,1-.05/M)>0",
            "year_combination": "ORIGINAL_DAY_WEIGHTS",
            "insufficient_support": "EVIDENCE_INCONCLUSIVE",
        },
        "roles": {
            "HARD_SAFETY": "NEVER_ABLATE",
            "DEFINING_ROLE": "ALTERNATE_GRAMMAR",
            "ALPHA_ROLE": "PAIRED_LCB_GT_0_AND_EACH_YEAR_NET_DELTA_GE_0_AND_RISK_PASS_AND_INTERVENTIONS",  # noqa: E501 - frozen source literal
            "RISK_FEASIBILITY_ROLE": "FULL_PASS_ABLATED_RISK_FAIL_WITH_UNCERTAINTY",
            "profit_drawdown_tradeoff": "TRADEOFF_UNRESOLVED",
        },
        "outputs": [
            "hourly_equity",
            "daily_equity",
            "campaign_ledger",
            "asset_attribution",
            "risk_audit",
            "execution_audit",
            "role_interventions",
            "qualification",
        ],
        "statuses": [
            "TECHNICAL_FAIL",
            "ECONOMIC_NOT_QUALIFIED",
            "EVIDENCE_INCONCLUSIVE",
            "QUALIFIED_EXPOSED_RESEARCH",
        ],
        "economic_replay_authorized": False,
        "production_authorized": False,
        "semantic_change": "NEW_VERSION_DELTA_GATE1_GATE2_RETEST_INVALIDATES_OLD_RUNNER",
    }


def config_hash(config):
    return (
        hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode())
        .hexdigest()
        .upper()
    )


def validate_preconditions(certificate: dict, frozen: dict, source_root: Path):
    required = (
        "gate1_funded_scope",
        "gate2_funded_scope",
        "management_binding",
        "source_binding",
        "accounting_reconciliation",
        "quantity_normalization",
        "no_hard_risk_breach",
        "no_fake_fill",
        "no_post_result_semantic_change",
        "protected_years_closed",
    )
    missing = [key for key in required if certificate.get(key) is not True]
    if not certificate.get("funded_grammars"):
        missing.append("NONEMPTY_COMPLETE_FUNDED_SCOPE")
    for relative, expected in frozen.items():
        target = (source_root / relative).resolve()
        if not target.is_relative_to(source_root.resolve()) or not target.is_file():
            missing.append(f"SOURCE_BINDING:{relative}")
        elif hashlib.sha256(target.read_bytes()).hexdigest().upper() != expected:
            missing.append(f"SOURCE_HASH_DRIFT:{relative}")
    return missing


def replay(*_args, **_kwargs):
    raise PermissionError(
        "ECONOMIC_REPLAY_DISABLED_BY_THIS_MISSION; HUMAN_AUTHORIZATION_AND_NEW_GOVERNED_RUNNER_REQUIRED"  # noqa: E501 - frozen source literal
    )


def concentration(campaign_net: np.ndarray, asset_net: np.ndarray):
    total = float(np.sum(campaign_net))
    return (
        total - max(0.0, float(np.max(campaign_net, initial=0.0))) > 0
        and total - max(0.0, float(np.max(asset_net, initial=0.0))) > 0
    )


def basic_lcb(theta: float, replicates: np.ndarray, primary_claim_count: int):
    if primary_claim_count < 1 or len(replicates) != 9999 or not np.isfinite(replicates).all():
        raise ValueError("UNCERTAINTY_SUPPORT_OR_CLAIM_FAMILY_INVALID")
    return theta - float(np.quantile(replicates - theta, 1 - 0.05 / primary_claim_count))


def stationary_indices(n: int, block_length: float, rng: np.random.Generator):
    if n < 2 or not np.isfinite(block_length) or block_length <= 0 or block_length >= n:
        raise ValueError("EVIDENCE_INCONCLUSIVE_BLOCK_SUPPORT")
    indices = np.empty(n, dtype=int)
    indices[0] = rng.integers(n)
    for k in range(1, n):
        indices[k] = (
            rng.integers(n)
            if rng.random() < 1 / max(1.0, block_length)
            else (indices[k - 1] + 1) % n
        )
    return indices


if __name__ == "__main__":
    replay()
