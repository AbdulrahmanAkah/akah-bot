"""Hash-bound technical closure and honest reserve authority inventory; no replay."""

from __future__ import annotations

import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "governance/four_source_repairs_v10"
DOWNLOADS = Path("C:/Users/abdul/Downloads")
TASK = "AKAH_FOUR_SOURCE_REPAIRS_AND_UNUSED_RESERVE_PREPARATION_V10"
START = "720c45c38d3edfd2042430d253cdbafb94ae8277"
DIRS = (
    "src/spotbot/research/multi_school_fidelity/integration_v10",
    "tests/research/integration_v10",
    "scripts/research/integration_v10",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def ref(path):
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    try:
        name = p.relative_to(ROOT).as_posix()
    except ValueError:
        name = str(p)
    return dict(path=name, sha256=sha(p), bytes=p.stat().st_size)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def save(name, data):
    p = OUT / name
    p.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
    return ref(p)


def inventory():
    # Metadata only: never open SVG/CSV/raw data, economic result or sealed map.
    directories = []
    patterns = (
        "AKAH_GATE2_BLIND_FIDELITY_OUT_*",
        "AKAH_MASTER_GATE2_GATE3_PRECOMMIT_V1_*",
        "AKAH_RESERVE_DIAGNOSTIC_REV781_*",
        "AKAH_FINAL_GATE2_TO_GATE3_REPLAY_READY_MEGA_V3_HANDOFF",
    )
    allowed = {"GATE2_BUILD_STATUS.json", "SAMPLING_AUDIT.json", "06_GATE2_SAMPLING_AUDIT.json"}
    for pattern in patterns:
        for directory in sorted(DOWNLOADS.glob(pattern)):
            if not directory.is_dir():
                continue
            paths = [p for p in directory.rglob("*") if p.is_file()]
            metadata = []
            for p in paths:
                if p.name not in allowed:
                    continue
                if any("SEALED" in part.upper() or "TRACE" in part.upper() for part in p.parts):
                    continue
                data = json.loads(p.read_text(encoding="utf-8-sig"))
                metadata_keys = data if isinstance(data, dict) else {}
                metadata.append(
                    dict(
                        ref(p),
                        case_count=metadata_keys.get("case_count"),
                        protocol_id=metadata_keys.get("protocol_id"),
                        outcomes_used=metadata_keys.get("outcomes_used"),
                        schema_type=type(data).__name__,
                        inspection="SAMPLING_METADATA_ONLY_NO_CASE_PAYLOAD",
                    )
                )
            directories.append(
                dict(
                    path=str(directory),
                    file_count=len(paths),
                    svg_names_count=sum(p.suffix == ".svg" for p in paths),
                    csv_names_count=sum(p.suffix == ".csv" for p in paths),
                    metadata=metadata,
                    disposition="OLD_VERSION_NOT_V10_BOUND_RESERVE",
                    chart_payloads_opened=False,
                )
            )
    exposed = []
    names = (
        "AKAH_RESERVE_DIAGNOSTIC_LOCKED_RESPONSES_REV781.json",
        "AKAH_GATE2_CODEX_AI_DIAGNOSTIC_REVIEW_20261002.json",
        "AKAH_GATE2_INDEPENDENT_DOMAIN_REVIEWER_LOCKED_RESPONSES_AI_V1.json",
    )
    for name in names:
        p = DOWNLOADS / name
        if p.is_file():
            exposed.append(ref(p))
    current_prior = ref("governance/producer_integration_bundle_v9/producer_binding_matrix.json")
    authority = json.loads((ROOT / current_prior["path"]).read_text())
    assert authority["historical_market_producer_recertification"] is False
    return dict(
        search_scope=patterns,
        directories=directories,
        locked_response_bindings=exposed,
        old_primary_cases_excluded=98,
        old_reserve_cases_excluded=90,
        previous_source_matrix=current_prior,
        actual_v9_historical_certification=False,
        v10_certified_market_corpus_found=False,
        new_version_chart_packet_generated=False,
        no_market_payloads_read=True,
        no_general_downloads_content_search=True,
        qualification="FINITE_SCOPED_AUTHORITY_SEARCH_NOT_EXHAUSTIVE_RAW_MARKET_SCAN",
    )


def main():
    active = json.loads((ROOT / ".akah_bot/active_task.json").read_text())
    assert active["task_id"] == TASK and active["starting_head"] == START
    assert active["starting_charter_revision"] == 781
    assert git("rev-parse", "HEAD") == START and not git("diff", "--name-only")
    assert not git("diff", "--cached", "--name-only")
    old = json.loads(
        (
            ROOT / "governance/producer_integration_bundle_v9/input_authority_manifest.json"
        ).read_text()
    )
    preserved = []
    for x in old["inputs"] + old["preserved_source_blobs"] + old["authorities"]:
        assert sha(ROOT / x["path"]) == x["sha256"], x["path"]
        preserved.append(x)
    sources = []
    for directory in DIRS:
        for p in sorted((ROOT / directory).glob("*")):
            if p.suffix == ".py" or p.name == ".gitattributes":
                if p.suffix == ".py":
                    compile(p.read_text(encoding="utf-8-sig"), str(p), "exec")
                rel = p.relative_to(ROOT).as_posix()
                assert (
                    subprocess.run(
                        ["git", "check-ignore", "--", rel], cwd=ROOT, capture_output=True
                    ).returncode
                    == 1
                )
                sources.append(ref(p))
    for name in (
        "research_protocol.json",
        "IMPLEMENTATION_CONTRACT.md",
        "SUMMARY.md",
        ".gitattributes",
    ):
        sources.append(ref(OUT / name))
    digest = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest().upper()
    tree = ET.parse(OUT / "synthetic_results.xml")
    totals = {
        k: sum(int(s.get(k, "0")) for s in tree.iter("testsuite"))
        for k in ("tests", "failures", "errors", "skipped")
    }
    new = sum("integration_v10" in x.get("classname", "") for x in tree.iter("testcase"))
    assert totals["tests"] == 397 and new == 58
    assert not any(totals[k] for k in ("failures", "errors", "skipped"))
    repairs = [
        dict(
            id="R1",
            defect="GENERIC_FIRST_PARENT_STOP_OWNER",
            status="CLOSED_TECHNICALLY",
            closure=(
                "Explicit typed recomputation, source graph, metadata and owner parity; "
                "actual kernel uses that binding"
            ),
        ),
        dict(
            id="R2",
            defect="WYCKOFF_INCOMPLETE_LIVE_DEPENDENCIES",
            status="CLOSED_TECHNICALLY",
            closure=(
                "All readiness/stage/PNF/context sources live through open; "
                "actual stage-fill receipt maps cause to campaign; B0 unchanged"
            ),
        ),
        dict(
            id="R3",
            defect="FEASIBILITY_TRUE_BEFORE_SAME_ASSET_ARBITRATION",
            status="CLOSED_TECHNICALLY",
            closure=(
                "Exact admission preview on isolated current kernel; "
                "final sequential admission still mandatory"
            ),
        ),
        dict(
            id="R4",
            defect="HIDDEN_NONTRUNCATED_ELLIOTT_SCOPE",
            status="CLOSED_TECHNICALLY",
            closure=(
                "Declared NONTRUNCATED_IMPULSE_PROFILE; truncated fifth "
                "unsupported diagnostic; no new trading rule"
            ),
        ),
    ]
    refs = []
    refs.append(
        save(
            "input_authority_manifest.json",
            dict(
                source_version_sha256=digest,
                inputs=sources,
                preserved_sources_and_authorities=preserved,
            ),
        )
    )
    refs.append(
        save(
            "repair_closure_matrix.json",
            dict(
                repairs=repairs,
                four_repairs_closed=True,
                native_price_targets_and_risk_rules_changed=False,
                related_stage_campaign_identity_bug_repaired=True,
            ),
        )
    )
    refs.append(save("reserve_authority_inventory.json", inventory()))
    blockers = [
        "V10_HISTORICAL_SEMANTIC_PRODUCER_CERTIFICATION_MISSING",
        "V10_FRESH_UNUSED_MARKET_PREFIX_FRAME_NOT_MATERIALIZED",
        "EXACT_VERSION_INDEPENDENT_RESERVE_REVIEW_NOT_EXECUTED",
    ]
    refs.append(
        save(
            "reserve_preparation_contract.json",
            dict(
                source_version_sha256=digest,
                stage="PREPARATION_ONLY_NOT_REVIEWABLE_MARKET_CORPUS",
                observed_market_rows_read=0,
                eligible_period=["2022-01-01T00:00:00Z", "2024-01-01T00:00:00Z"],
                end_exclusive=True,
                forbid_2024_2025=True,
                exclusion=(
                    "All old primary, supplemental and reviewed reserve prefixes; "
                    "no relabelled duplicates"
                ),
                lineage_required=[
                    "source authority SHA256",
                    "source version SHA256",
                    "asset/checkpoint audit identity",
                    "prefix content SHA256",
                    "detector known_at/evidence parents",
                    "owner/stop proof/invalidation",
                    "router context",
                    "complete native management scope",
                ],
                audit_identity_is_runtime_rule=False,
                blind_view="completed prefix only; no future/PnL/engine decision/reviewer labels",
                freeze_before_sampling=True,
                deterministic_sampling_not_outcome_selected=True,
                no_forced_positive_cases=True,
                require_current_semantic_certified_producer=True,
                pair_checkpoint_and_prefix_hash_overlap_check=True,
                numeric_quota="NOT_REDEFINED_IN_THIS_REPAIR_MISSION",
                reserve_reviewer_metadata=(
                    "Preserve real AI/human identity; no false independent human attestation"
                ),
                forbidden_substitution=(
                    "Synthetic mechanics or old charts do not certify fresh market fidelity"
                ),
                stop_condition=(
                    "No chart packet claimed ready before upstream exact-version authorities exist"
                ),
                blockers=blockers,
            ),
        )
    )
    refs.append(
        save(
            "producer_integration_matrix.json",
            dict(
                routes=[
                    "HARMONIC",
                    "ELLIOTT",
                    "WYCKOFF",
                    "ICT_SESSION",
                    "H2",
                    "CLASSICAL",
                    "H1",
                    "H3",
                    "DOW_CONTEXT_ONLY",
                ],
                test_scope="REAL_ALGORITHMS_ON_SYNTHETIC_SOURCES_NOT_HISTORICAL_REPLAY",
                H3="ISOLATED_COMPOSITION_NOT_FULL_HISTORICAL_SOURCE_STREAM",
                Classical_H1="LEGACY_ENVELOPE_WITH_EXPLICIT_SOURCE_STOP",
                Wyckoff="READINESS_AND_CAUSE_REQUIRE_SUPPLIED_SEMANTIC_AUTHORITY",
                Elliott="RECURSIVE_PROOF_INPUT_NOT_EXHAUSTIVE_AUTOMATIC_COUNT_GENERATOR",
                historical_market_producers_recertified=False,
                funded_grammars=[],
            ),
        )
    )
    refs.append(
        save(
            "evidence_snapshot.json",
            dict(
                task_id=TASK,
                starting_head=START,
                starting_revision=781,
                tests=totals,
                new_tests=new,
                junit=ref(OUT / "synthetic_results.xml"),
                all_old_sources_unchanged=True,
                synthetic_only=True,
                sources=sources,
                regression_warnings={
                    "count": 12,
                    "origin": "UNCHANGED_ARCH_CONSTANT_SYNTHETIC_SERIES_BOOTSTRAP_TEST",
                    "test": "test_arch_api_stationary_9999_paired_cash_days_and_determinism",
                    "failures": 0,
                    "ignored_to_change_acceptance": False,
                },
            ),
        )
    )
    refs.append(
        save(
            "governance_report.json",
            dict(
                task_id=TASK,
                technical_repairs="PASS",
                overall_requested_scope="PARTIAL_RESERVE_AUTHORITY_BLOCKED",
                independent_reserve_certification=False,
                economic_conclusion="NONE",
                complete_verify="REQUIRED_AFTER_IMPLEMENTATION_COMMIT",
                governance_sync="NOT_PERFORMED_PUSH_NO_REQUIRED_BEFORE_NEXT_GOVERNED_TASK",
                unrelated_untracked_files="PRESERVED_NOT_STAGED",
            ),
        )
    )
    result = dict(
        task_id=TASK,
        classification="FOUR_TECHNICAL_REPAIRS_PASS_FRESH_MARKET_RESERVE_NOT_READY",
        technical_repair_status="PASS",
        four_repairs_closed=True,
        full_mission_status="BLOCKED_ON_FRESH_MARKET_RESERVE_AUTHORITY",
        synthetic_tests=totals,
        new_tests=new,
        source_version_sha256=digest,
        artifact_bindings=refs,
        protocol_sha256=sha(OUT / "research_protocol.json"),
        unused_market_reserve_ready=False,
        independent_review_executed=False,
        reserve_cases_generated=0,
        reserve_blockers=blockers,
        ready_for_gate3_replay=False,
        funded_grammars=[],
        old_sources_unchanged=True,
        economic_replay_executed=False,
        market_rows_accessed=False,
        pnl_read=False,
        **{"2024_rows_accessed": False, "2025_rows_accessed": False},
        model_fit=False,
        threshold_search=False,
        production_changed=False,
        push=False,
        economic_conclusion="NONE",
        next_bottleneck="V10_CERTIFIED_HISTORICAL_SOURCE_PREFIXES_AND_UNUSED_MARKET_RESERVE",
    )
    save("canonical_result.json", result)
    print(
        json.dumps(
            dict(
                tests=totals,
                new_tests=new,
                source_version_sha256=digest,
                result_sha256=sha(OUT / "canonical_result.json"),
                technical="PASS",
                market_reserve="NOT_READY",
            )
        )
    )


if __name__ == "__main__":
    main()
