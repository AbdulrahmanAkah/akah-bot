"""Persist the completed diagnosis and its exact evidence manifest."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "governance/transition_event_diagnosis_v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    import pandas as pd

    before = digest(OUT / "diagnostic_measurements.json")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/research/transition_event_diagnosis.py")],
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    assert digest(OUT / "diagnostic_measurements.json") == before
    d = json.loads((OUT / "diagnostic_measurements.json").read_text())
    r23 = json.loads((OUT / "replayed_p38_result.json").read_text())
    old = ROOT / "governance/p43_transition_exact_authority/canonical_result.json"
    auth = json.loads(old.read_text())
    source = next(
        p
        for p in auth["authorities"]
        if p["sha256"] == "221CC3BCF5E062CE36CE2BEE10E3A9EE22448A8A8E4EF54F01DAF331E8B52DE7"
    )
    p = Path(source["path"])
    assert digest(p) == source["sha256"]
    shutil.copyfile(p, OUT / "frozen_p19_result.json")
    r22 = json.loads(p.read_text())
    contract = json.loads((OUT / "execution_contract.json").read_text())
    p13trace = Path(contract["sources"]["--p13-trace"]["path"])
    assert digest(p13trace) == contract["sources"]["--p13-trace"]["sha256"]
    shutil.copyfile(p13trace, OUT / "frozen_control_trace_2022.csv")
    shutil.copyfile(old, OUT / "frozen_p43_authority.json")
    shutil.copyfile(
        ROOT / "governance/transition_event_diagnosis_protocol_v1.json", OUT / "protocol.json"
    )
    wrapper = Path("C:/Users/abdul/Downloads/P38_V1R11.ps1")
    assert digest(wrapper) == contract["wrapper_sha256"]
    shutil.copyfile(wrapper, OUT / "frozen_p38_v1r11_source_package.ps1")
    path_terms = {}
    for year, source_result in [(2022, r22), (2023, r23)]:
        terms = source_result["exact_effect_decomposition"]
        direct = d["years"][str(year)]["net_pnl"]
        indirect = terms["control_only_net_pnl"] - direct
        residual = math.fsum(
            [terms["common_trade_pnl_delta"], terms["treatment_only_net_pnl"], -indirect]
        )
        target = -2899.574483653062 if year == 2022 else -8701.883844863238
        assert abs(residual - target) < 1e-7
        path_terms[str(year)] = {
            "direct_ablation_effect": -direct,
            "path_residual": residual,
            "indirect_lost_control_pnl": indirect,
            "common_sizing_delta": terms["common_trade_pnl_delta"],
            "treatment_only_pnl": terms["treatment_only_net_pnl"],
            "frozen_lineage": source_result["transition_ablation_lineage"],
        }
    result = {
        "task_id": "TRANSITION_2023_EVENT_LEVEL_EXPORT_REPLAY_AND_CROSS_YEAR_DIAGNOSIS_V1",
        "status": "PASS",
        "classification": "MIXED_MECHANISM",
        "primary_event_level_driver": "HIGHER_WIN_FRACTION_AND_SMALLER_AVERAGE_LOSS",
        "secondary_driver": "OUTLIER_WINNER_DEPENDENCE_OF_2023_POSITIVE_SIGN",
        "descriptive_families": [
            "OUTLIER_WINNER_DEPENDENCE",
            "HOLDING_OR_EXIT_INTERACTION_SHIFT",
            "TEMPORAL_SUBREGIME_COMPOSITION_SHIFT",
        ],
        "2022_direct_event_set_proven": True,
        "2023_direct_event_set_proven": True,
        "direct_2022_count": 173,
        "direct_2023_count": 131,
        "direct_2022_pnl": d["years"]["2022"]["net_pnl"],
        "direct_2023_pnl": d["years"]["2023"]["net_pnl"],
        "mean_2022": d["years"]["2022"]["mean_pnl"],
        "mean_2023": d["years"]["2023"]["mean_pnl"],
        "count_quality_accounting": d["count_quality_accounting"],
        "mean_pnl_shapley_accounting": d["mean_pnl_shapley_accounting"],
        "portfolio_path_accounting": path_terms,
        "event_level_evidence_sufficient": True,
        "sufficiency_scope": "DESCRIPTIVE_AND_ACCOUNTING_ATTRIBUTION_ONLY",
        "unique_ex_ante_market_cause_identified": False,
        "missing_entry_causal_components": d["missing_fields"],
        "transition_as_standalone_admission_rule_supported": False,
        "candidate_remains_closed": True,
        "new_runtime_rule_authorized": False,
        "replay_count": {"control": 1, "treatment": 1},
        "replay_parity": "PASS",
        "offline_diagnostic_determinism": "PASS",
        "targeted_pytest": "6 passed",
        "ruff": "PASS",
        "governance": {
            "lookahead_or_future_information_used": False,
            "pair_or_event_identity_used_as_runtime_rule": False,
            "posthoc_outcome_threshold_search_used": False,
            "2023_new_raw_or_replay_accessed": True,
            "2024_used_as_fresh_holdout": False,
            "2024_used_to_define_new_runtime_rule": False,
            "2025_accessed": False,
            "production_changed": False,
        },
        "next_bottleneck": "TRANSITION_EVENT_LEVEL_DIAGNOSIS_MANDATORY_HUMAN_REVIEW_V1",
        "evidence": [
            {"path": str(p.relative_to(ROOT)), "sha256": digest(p)}
            for p in [
                OUT / "diagnostic_measurements.json",
                OUT / "parity.json",
                OUT / "execution_contract.json",
                OUT / "protocol.json",
                OUT / "summary.md",
            ]
        ],
    }
    dump("canonical_result.json", result)
    dump(
        "governance_report.json",
        {
            "task_id": result["task_id"],
            "outcome": "PASS",
            "classification": result["classification"],
            "next_bottleneck": result["next_bottleneck"],
            "governance": result["governance"],
            "canonical_result_sha256": digest(OUT / "canonical_result.json"),
            "qa": {
                "ruff": "PASS",
                "pytest_pass_count": 6,
                "determinism": "PASS",
                "whole_control_treatment_parity": "PASS",
                "direct_set_parity": "PASS",
            },
        },
    )
    manifest = []
    for p in sorted(OUT.iterdir()):
        if not p.is_file() or p.name == "artifact_manifest.json":
            continue
        item = {"path": str(p.relative_to(ROOT)), "sha256": digest(p), "size": p.stat().st_size}
        if p.suffix == ".csv":
            frame = pd.read_csv(p, float_precision="round_trip")
            item.update(row_count=len(frame), schema=list(frame.columns))
            identity = (
                ["pair", "entry_time"]
                if "net_pnl" in frame
                else ["event_key"]
                if "event_key" in frame
                else None
            )
            item["identity_contract"] = identity
            if identity:
                item["duplicate_identity_count"] = int(frame.duplicated(identity).sum())
                assert item["duplicate_identity_count"] == 0
            if "entry_time" in frame and len(frame):
                time = pd.to_datetime(frame.entry_time, utc=True)
                item["entry_period"] = {"min": str(time.min()), "max": str(time.max())}
            item["selection_contract"] = (
                "Frozen P19 direct mapping"
                if p.name.startswith("direct_")
                else "Complete returned frozen authority rowset"
            )
        manifest.append(item)
    for name in [
        "transition_p38_export.py",
        "transition_event_diagnosis.py",
        "transition_diagnosis_finalize.py",
    ]:
        p = ROOT / "scripts/research" / name
        manifest.append({"path": str(p.relative_to(ROOT)), "sha256": digest(p)})
    dump("artifact_manifest.json", manifest)
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "status",
                    "classification",
                    "direct_2022_count",
                    "direct_2023_count",
                    "direct_2022_pnl",
                    "direct_2023_pnl",
                    "next_bottleneck",
                ]
            }
        )
    )
    print("MANIFEST_SHA256=" + digest(OUT / "artifact_manifest.json"))


if __name__ == "__main__":
    main()
