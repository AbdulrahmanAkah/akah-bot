"""Re-evaluate the immutable universe gate from source feasibility evidence."""

from __future__ import annotations

from ams_md01r2_common import (
    R1_CENSUS,
    READINESS,
    REPORTS,
    SOURCE_FEASIBILITY,
    atomic_json,
    atomic_text,
    copy_external,
    load_json,
)

from spotbot.research.ams_md01r2_universe import evaluate_gate, gate_as_dict


def main() -> None:
    census = load_json(R1_CENSUS)
    feasibility = load_json(SOURCE_FEASIBILITY)
    included = int(census["counts"]["included_candidates"])
    resolved = int(census["counts"]["resolved_memberships"])
    membership_ratio = resolved / included if included else 0.0
    gate = evaluate_gate(
        membership_resolution=membership_ratio,
        dynamic_four_hour_coverage=0.0,
        delisted_four_hour_coverage=0.0,
        boundary_violations=0,
        material_mapping_conflicts=0,
    )
    report = {
        "schema_version": "ams-md01r2-universe-readiness-v1",
        "status": gate.status,
        "source_feasibility": feasibility["status"],
        "gate": gate_as_dict(gate),
        "counts": {
            "census_candidates": census["counts"]["census_candidates"],
            "included_candidates": included,
            "resolved_memberships": resolved,
            "historically_delisted_candidates": census["counts"][
                "historically_delisted_candidates"
            ],
            "dynamic_assets_with_registered_4h": 0,
        },
        "dynamic_matrix_authorized": False,
        "dominance_phase_authorized": False,
        "adaptive_intelligence_phase_authorized": False,
        "paired_configurations_executed": 0,
        "paired_configurations_remaining": 12,
        "cost_executions_completed": 0,
        "cost_executions_remaining": 36,
        "next_action": "BOUNDED_NON_IDENTIFICATION_ANALYSIS",
        "test_2025_accessed": False,
        "holdout_2026_accessed": False,
    }
    atomic_json(READINESS, report)
    md_name = "ams-md01r2-universe-readiness-v1.md"
    atomic_text(
        REPORTS / md_name,
        "\n".join(
            [
                "# AMS-MD01R2 Universe Readiness",
                "",
                f"- Universe gate: **{gate.status}**",
                f"- Membership resolution: {membership_ratio:.4%}",
                "- Dynamic 4H coverage: 0.0000%",
                "- Delisted 4H coverage: 0.0000%",
                "- Dynamic matrix authorized: false",
                "",
                "The registered Phase A gate did not pass. Phases B and C are blocked.",
                "",
            ]
        ),
    )
    copy_external([READINESS.name, md_name])
    print(f"UNIVERSE_GATE={gate.status}")
    print(f"MEMBERSHIP_RESOLUTION={membership_ratio:.8f}")
    print("DYNAMIC_4H_COVERAGE=0.00000000")
    print("DELISTED_4H_COVERAGE=0.00000000")
    print("DYNAMIC_MATRIX_AUTHORIZED=false")


if __name__ == "__main__":
    main()
