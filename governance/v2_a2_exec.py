"""Bounded Phase A recovery audit. No native replay or outcome projection.

Reproduces the previously governed observation window as a *coverage* surface.
It must not certify that entry + max hold is the actual native lifecycle end.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds

from spotbot.governance import task_completion_gate as gate
from spotbot.research.rd27_later_trigger_v2_shadow_replay import replay_v2_shadow_position
from spotbot.research.rd27_observable_memory_adapter import (
    CANONICAL_FIELDS,
    normalize_4h_snapshots,
)

ROOT = Path(__file__).resolve().parents[1]
TASK = "CAUSAL_EXIT_BRAIN_V2_PHASE_A_COHORT_COVERAGE_AUDIT_RECOVERY_V2"
PREFIX = ROOT / "governance/v2_a2"
CONTROL = "reports/research/ams-rd04-d5c1-labelled-pit-control-trades-v1.csv"
BAR = ("data/research/rd04/kucoin-spot-usdt-adjudicated-v1/"
       "ams-rd04-d0c-kucoin-adjudicated-4h.parquet")
EXPECTED = {
    CONTROL: "782CEA4D8037E6D2C72FBE7B37FF69F10E66DC728396E6B4B58C28559BEEB225",
    BAR: "1C72416F889137B68FF48008C5760E809D0A94A5647569BAB631E96904CEBD72",
    "governance/AKAH_BOT_EXIT_BRAIN_RESEARCH_DIRECTION_V1.json":
        "7CC2058A75C5B9F959E1176DD7B47E066C45A6BDF4B19278F339ED6BD97E20A5",
    "governance/AKAH_BOT_V2_COHORT_OBSERVATION_REFERENCE_DIAGNOSTIC_PROTOCOL_V1.json":
        "6A64B7600261CC105064F250A3D5E6E794A90432C08C9218FC6A9A234B25BFD7",
    "governance/AKAH_BOT_V2_PHASE_A_COHORT_COVERAGE_AUDIT_PROTOCOL_V1.json":
        "CF713ABE14F6B4085B95BEFE06A4508BF71BFD300BF6CEAC64ACDFEE1F7CACD4",
    "governance/AKAH_BOT_V2_PHASE_B_OBSERVATION_OPPORTUNITY_PROTOCOL_V1.json":
        "FC805957ECC389EACA3DDD8F9F640F4960AB8DA027A6C2C5FC275F5619DB3DD4",
    "governance/AKAH_BOT_V2_PHASE_C_TIMING_REFERENCE_DEPENDENCE_PROTOCOL_V1.json":
        "B6BA4548C7BD6E955682FAA00C58784317ED0F8CAD5AB3B486FCB6142C837C1A",
}
SAFE_CONTROL = (
    "trade_id", "position_id", "canonical_symbol", "symbol", "entry_time",
    "entry_price", "fold_id", "portfolio_mode", "universe_mode",
)


def emit(message):
    print(message, flush=True)


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def digest(path):
    h = hashlib.sha256()
    processed = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            h.update(chunk)
            processed += len(chunk)
            if processed % (256 << 20) == 0:
                emit(f"SHA_PROGRESS_BYTES={processed}")
    return h.hexdigest().upper()


def save_json(suffix, value):
    path = Path(str(PREFIX) + suffix + ".json")
    gate.save_json(path, value)
    return path


def save_csv(suffix, rows):
    path = Path(str(PREFIX) + suffix + ".csv")
    pd.DataFrame(rows).to_csv(path, index=False, lineterminator="\n")
    return path


def project(relative, fields):
    with (ROOT / relative).open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    selected = [field for field in fields if field in header]
    return pd.read_csv(ROOT / relative, usecols=selected, dtype=str, keep_default_na=False)


def utc(value):
    return pd.Timestamp(value).tz_convert("UTC")


def iso(value):
    return None if value is None or pd.isna(value) else pd.Timestamp(value).isoformat()


def timestamp_bounds(schema, start, end):
    """Fail closed on unknown timezone semantics; preserve each field's Arrow type."""
    result = {}
    for name in ("bar_open_time", "bar_close_time"):
        dtype = schema.field(name).type
        need(pa.types.is_timestamp(dtype), f"NOT_TIMESTAMP:{name}:{dtype}")
        need(dtype.tz == "UTC", f"UNAUTHORIZED_TIMEZONE_SEMANTICS:{name}:{dtype}")
        bounds = tuple(pa.scalar(value.to_pydatetime(), type=dtype) for value in (start, end))
        need(all(bound.type == dtype for bound in bounds), f"FILTER_TYPE_MISMATCH:{name}")
        result[name] = bounds
    return result


def expected_opens(entry, end):
    first = entry.ceil("4h")
    last = end - pd.Timedelta(hours=4)
    return pd.date_range(first, last, freq="4h") if first <= last else pd.DatetimeIndex([])


def timestamp_equal(left, right):
    return (pd.isna(left) and pd.isna(right)) or left == right


def run(report):
    bindings = report["authority_bindings"]
    for relative, expected in EXPECTED.items():
        emit(("BAR4H_SHA_VERIFY" if relative == BAR else "AUTHORITY_SHA_VERIFY") + "=START")
        actual = digest(ROOT / relative)
        need(actual == expected, f"SHA_DRIFT:{relative}:{actual}")
        bindings[relative] = actual
        emit(("BAR4H_SHA_VERIFY" if relative == BAR else "AUTHORITY_SHA_VERIFY") + "=PASS")

    # These exact children were recorded in the governed execution reports.
    for parent in ("governance/spec_exec_v1_rpt.json",
                   "governance/trigger_v2_shadow_parity_v1_rpt.json"):
        bindings[parent] = digest(ROOT / parent)
        for child in load(parent)["evidence"]:
            relative = child["path"]
            actual = digest(ROOT / relative)
            need(actual == child["sha256"], f"GOVERNED_CHILD_DRIFT:{relative}")
            bindings[relative] = actual

    manifest = load("governance/spec_exec_v1_input.json")
    start = utc(manifest["window_start"])
    end = utc(manifest["protected_boundary_exclusive"])
    cutoff = utc(manifest["admission_cutoff_exclusive"])
    hold = manifest["native_rd27_max_hold_hours"]
    need(start == pd.Timestamp("2022-01-01", tz="UTC"), "START_DRIFT")
    need(end == pd.Timestamp("2023-01-01", tz="UTC"), "END_DRIFT")
    need(hold == 168, "MAX_HOLD_DRIFT")
    need(cutoff == end - pd.Timedelta(hours=hold), "CUTOFF_DRIFT")
    need(manifest["observation_censoring_convention"] ==
         "ENTRY_PLUS_NATIVE_RD27_MAX_HOLD_HOURS", "PRIOR_WINDOW_DRIFT")

    roster = project(CONTROL, SAFE_CONTROL)
    need(len(roster) == 153 and roster.trade_id.nunique() == 153, "ROSTER_IDENTITY_DRIFT")
    need(roster.trade_id.ne("").all(), "EMPTY_TRADE_ID")
    roster["entry_time"] = pd.to_datetime(roster.entry_time, utc=True, errors="raise")
    roster["entry_price"] = pd.to_numeric(roster.entry_price, errors="raise")
    need(roster.entry_price.gt(0).all(), "INVALID_ENTRY_PRICE")
    original = project("governance/spec_exec_v1_roster.csv", (
        "trade_id", "entry_time", "canonical_symbol", "source_symbol",
        "bound_4h_symbol", "status", "reason",
    ))
    need(original.trade_id.is_unique and set(original.trade_id) == set(roster.trade_id),
         "PREVIOUS_ROSTER_IDENTITY_DRIFT")
    original = original.set_index("trade_id")
    prior = project("governance/spec_exec_v1_lifecycles.csv", (
        "trade_id", "lifecycle_id", "entry_time", "observed_through", "symbol",
    ))
    need(prior.trade_id.is_unique, "PREVIOUS_LIFECYCLE_DUPLICATES")
    prior = prior.set_index("trade_id")
    parity = project("governance/trigger_v2_shadow_parity_v1_rows.csv", (
        "trade_id", "symbol", "expected_memory_time", "integrated_memory_time",
        "expected_v2_candidate_time", "integrated_v2_candidate_time",
    ))
    previous_ids = set(original.index[original.status == "ELIGIBLE"])
    need(parity.trade_id.is_unique and set(parity.trade_id) == previous_ids,
         "PARITY_IDENTITY_DRIFT")
    need(set(prior.index) == previous_ids, "PRIOR_WINDOW_IDENTITY_DRIFT")
    parity_counts = {}
    for label, expected_field, integrated_field in (
        ("MEMORY", "expected_memory_time", "integrated_memory_time"),
        ("V2", "expected_v2_candidate_time", "integrated_v2_candidate_time"),
    ):
        for field in (expected_field, integrated_field):
            parity[field] = pd.to_datetime(parity[field].replace("", None), utc=True,
                                          errors="raise")
        mismatches = [str(row.trade_id) for row in parity.itertuples()
                      if not timestamp_equal(getattr(row, expected_field),
                                             getattr(row, integrated_field))]
        need(not mismatches, f"PARITY_{label}_DRIFT:{mismatches}")
        parity_counts[label] = int(parity[expected_field].notna().sum())
        emit(f"PARITY_{label}_PAIR=PASS count={parity_counts[label]} mismatch=0")
    parity = parity.set_index("trade_id")

    window_mask = roster.entry_time.ge(start) & roster.entry_time.lt(cutoff)
    # Symbol identity is an exact field binding, never a suffix/fuzzy transformation.
    for row in roster.itertuples(index=False):
        old = original.loc[row.trade_id]
        need(utc(old.entry_time) == row.entry_time, f"ENTRY_DRIFT:{row.trade_id}")
        need(old.canonical_symbol == row.canonical_symbol, f"SYMBOL_DRIFT:{row.trade_id}")
    symbols = sorted(set(roster.loc[window_mask, "canonical_symbol"]))
    dataset = ds.dataset(ROOT / BAR, format="parquet")
    schema = dataset.schema
    need(tuple(schema.names) == CANONICAL_FIELDS, "CANONICAL_SCHEMA_DRIFT")
    bounds = timestamp_bounds(schema, start, end)
    schema_evidence = {"fields": {field.name: str(field.type) for field in schema},
                       "scalar_types": {}, "compatibility": "PASS"}
    for name, (lower, upper) in bounds.items():
        emit(f"{name.upper()}_ARROW_TYPE={schema.field(name).type}")
        emit(f"AUTHORIZED_START_SCALAR_TYPE={name}:{lower.type}")
        emit(f"AUTHORIZED_END_SCALAR_TYPE={name}:{upper.type}")
        schema_evidence["scalar_types"][name] = {
            "start_type": str(lower.type), "end_type": str(upper.type),
            "start": iso(start), "end_exclusive": iso(end),
        }
    emit("TIMESTAMP_FILTER_TYPE_COMPATIBILITY=PASS")
    emit("BAR4H_SCHEMA_PREFLIGHT=PASS")
    save_json("_schema", schema_evidence)
    lower, upper = bounds["bar_open_time"]
    close_lower, close_upper = bounds["bar_close_time"]
    expression = ((ds.field("bar_open_time") >= lower)
                  & (ds.field("bar_open_time") < upper)
                  & (ds.field("bar_close_time") >= close_lower)
                  & (ds.field("bar_close_time") < close_upper)
                  & ds.field("symbol").isin(symbols))
    emit("BAR4H_2022_READ=START")
    bars = dataset.to_table(columns=list(CANONICAL_FIELDS), filter=expression).to_pandas()
    need(bars.bar_open_time.dt.year.eq(2022).all()
         and bars.bar_close_time.dt.year.eq(2022).all(), "PROTECTED_BOUNDARY_VIOLATION")
    need(bars.bar_open_time.eq(bars.bar_open_time.dt.floor("4h")).all(), "4H_GRID_DRIFT")
    emit(f"BAR4H_2022_READ=PASS rows={len(bars)}")
    grouped = {symbol: frame.sort_values(["bar_open_time", "bar_close_time"])
               for symbol, frame in bars.groupby("symbol", sort=True)}
    audit, coverage, events = [], [], []
    covered_ids, recon_mismatches = set(), []
    protocol = load("governance/AKAH_BOT_V2_PHASE_A_COHORT_COVERAGE_AUDIT_PROTOCOL_V1.json")
    required = protocol["required_outputs"]["lifecycle_audit"]["required_fields"]

    for index, row in enumerate(roster.sort_values("trade_id").to_dict("records"), 1):
        trade = row["trade_id"]
        entry = row["entry_time"]
        old = original.loc[trade]
        in_window = start <= entry < cutoff
        boundary = entry + pd.Timedelta(hours=hold) if in_window else None
        record = dict.fromkeys(required)
        record.update(
            canonical_trade_id=trade, lifecycle_id=trade,
            canonical_symbol=row["canonical_symbol"],
            fold_id=row.get("fold_id"), portfolio_mode=row.get("portfolio_mode"),
            universe_mode=row.get("universe_mode"),
            identity_binding_status="EXACT_TRADE_ID", roster_sha256=EXPECTED[CONTROL],
            input_manifest_id="governance/spec_exec_v1_input.json",
            entry_time_utc=iso(entry), entry_price=row["entry_price"],
            study_window_start=iso(start), study_window_end=iso(boundary),
            entry_inside_authorized_window=in_window,
            source_artifact_identity=EXPECTED[BAR],
            original_eligibility_status=old.status,
            audited_eligibility_status="OUTSIDE_AUTHORIZED_SCOPE",
            primary_exclusion_reason="OUTSIDE_AUTHORIZED_SCOPE",
            additional_reason_flags=[], terminal_status="NOT_EVALUATED_OUTSIDE_SCOPE",
            evidence_reference="governance/spec_exec_v1_input.json#observation_censoring_convention",
            coverage_status="NOT_READ_OUTSIDE_AUTHORIZED_WINDOW",
            window_semantics="HISTORICAL_ENTRY_PLUS_168H_NOT_NATIVE_CLOSE",
            native_lifecycle_eligibility_certified=False,
        )
        if in_window:
            opens = expected_opens(entry, boundary)
            frame = grouped.get(row["canonical_symbol"], bars.iloc[:0])
            selected = frame.loc[frame.bar_open_time.ge(entry)
                                 & frame.bar_close_time.le(boundary)]
            normalized = normalize_4h_snapshots(selected)
            snapshots = normalized.snapshots
            available = {snap.bar_open_time: snap for snap in snapshots}
            missing = [time for time in opens if time not in available]
            need(set(available).issubset(set(opens)), f"UNEXPECTED_BAR_GRID:{trade}")
            has_coverage = bool(len(opens)) and not missing
            record.update(
                expected_completed_bar_count=len(opens),
                available_valid_completed_bar_count=len(available), missing_bar_count=len(missing),
                conflicting_duplicate_count=0,
                identical_duplicates=normalized.duplicates_deduplicated,
                first_coverage_gap_time=(iso(missing[0] + pd.Timedelta(hours=4))
                                         if missing else None),
                complete_entry_to_observation_end_coverage=has_coverage,
                coverage_status="COMPLETE" if has_coverage else "INCOMPLETE",
                audited_eligibility_status=("COVERAGE_ELIGIBLE_NATIVE_BOUNDARY_UNVERIFIED"
                                            if has_coverage else "DATA_UNAVAILABLE"),
                primary_exclusion_reason=None if has_coverage else "DATA_UNAVAILABLE",
                terminal_status="TERMINAL_ORDER_UNRESOLVED",
                additional_reason_flags=["NATIVE_TERMINAL_AUTHORITY_NOT_BOUND"],
                first_available_bar_close=iso(snapshots[0].bar_close_time) if snapshots else None,
                last_available_bar_close=iso(snapshots[-1].bar_close_time) if snapshots else None,
                first_full_post_entry_bar_close=iso(opens[0] + pd.Timedelta(hours=4))
                if len(opens) else None,
                memory_evaluable_bar_count=len(opens) if has_coverage else None,
                entry_spanning_bar_identity=(json.dumps([row["canonical_symbol"],
                                                        iso(entry.floor("4h")),
                                                        iso(entry.ceil("4h"))])
                                             if entry != entry.floor("4h") else None),
            )
            memory = candidate = None
            if has_coverage:
                covered_ids.add(trade)
                replay = replay_v2_shadow_position(
                    position_id=trade, symbol=row["canonical_symbol"], entry_time=entry,
                    entry_price=row["entry_price"], observed_through=boundary,
                    primitive_rows=selected.to_dict("records"),
                )
                memory, candidate = replay.first_memory_time, replay.candidate_time
                record.update(first_memory_time=iso(memory), first_v2_time=iso(candidate),
                              event_scope="HISTORICAL_WINDOW_ONLY_NATIVE_VALIDITY_UNCERTIFIED",
                              first_causal_evaluation_time=iso(snapshots[0].bar_close_time),
                              last_verified_causal_evaluation_time=iso(snapshots[-1].bar_close_time))
                post = [snap for snap in snapshots
                        if memory is not None and snap.bar_close_time > memory]
                record["post_memory_evaluable_bar_count"] = len(post) if memory else None
                record["first_post_memory_evaluation_time"] = (
                    iso(post[0].bar_close_time) if post else None)
                if trade in previous_ids:
                    need(utc(prior.loc[trade].observed_through) == boundary,
                         f"HISTORICAL_WINDOW_DRIFT:{trade}")
                    need(old.bound_4h_symbol == row["canonical_symbol"],
                         f"EXACT_SYMBOL_BINDING_DRIFT:{trade}")
                    for label, actual, field in (
                        ("MEMORY", memory, "integrated_memory_time"),
                        ("V2", candidate, "integrated_v2_candidate_time"),
                    ):
                        if not timestamp_equal(pd.NaT if actual is None else actual,
                                               parity.loc[trade, field]):
                            recon_mismatches.append({"trade_id": trade, "event": label,
                                                     "actual": iso(actual),
                                                     "prior": iso(parity.loc[trade, field])})
                for sequence, snap in enumerate(snapshots):
                    types = ["COMPLETED_BAR_EVALUATION"]
                    if snap.bar_close_time == memory:
                        types.append("FIRST_MEMORY")
                    if snap.bar_close_time == candidate:
                        types.append("FIRST_V2")
                    for event_type in types:
                        events.append(dict(lifecycle_id=trade, event_type=event_type,
                                           event_time=iso(snap.bar_close_time),
                                           snapshot_identity=json.dumps(
                                               [str(x) for x in snap.identity]),
                                           snapshot_close_time=iso(snap.bar_close_time),
                                           information_available_time=iso(snap.bar_close_time),
                                           runtime_sequence_index=None,
                                           historical_snapshot_index=sequence,
                                           evidence_reference=EXPECTED[BAR],
                                           event_scope="HISTORICAL_WINDOW_NOT_NATIVE_CERTIFIED"))
            for time in opens:
                coverage.append(dict(lifecycle_id=trade, interval_start=iso(time),
                                     interval_end=iso(time + pd.Timedelta(hours=4)),
                                     expected_bar_identities=json.dumps(
                                         [row["canonical_symbol"], iso(time)]),
                                     available_bar_identities=(iso(time)
                                                               if time in available else None),
                                     validity_status="VALID" if time in available else "MISSING",
                                     conflict_status="NONE", gap_before_or_after_memory=(
                                         "NO_GAP" if time in available else "MEMORY_NOT_CERTIFIED"),
                                     reconstructability_after_gap="YES" if has_coverage else "NO",
                                     window_semantics="HISTORICAL_NOT_NATIVE"))
        audit.append(record)
        if index % 25 == 0 or index == len(roster):
            emit(f"PHASE_A_PROGRESS={index}/{len(roster)}")

    save_csv("_audit", audit)
    save_csv("_coverage", coverage)
    save_csv("_events", events)
    reconciliation = {
        "canonical_roster": len(roster), "previous_eligible": len(previous_ids),
        "historical_window_coverage_eligible": len(covered_ids),
        "audited_eligible": None, "audited_eligible_status": "NATIVE_BOUNDARY_UNCERTIFIED",
        "exact_33_identity_reproduction": previous_ids == covered_ids,
        "identity_reproduction_scope": "PREVIOUS_HISTORICAL_WINDOW_COHORT_ONLY",
        "previous_memory": parity_counts["MEMORY"], "previous_v2": parity_counts["V2"],
        "parity_memory_mismatch_count": 0, "parity_v2_mismatch_count": 0,
        "reconstruction_mismatches": recon_mismatches,
        "previous_only_identities": sorted(previous_ids - covered_ids),
        "audited_only_identities": sorted(covered_ids - previous_ids),
        "historical_coverage_eligible_identities": sorted(covered_ids),
        "primary_exclusion_reason_counts": pd.Series(
            [row["primary_exclusion_reason"] for row in audit]).dropna().value_counts().to_dict(),
        "unresolved_native_boundary_identities": sorted(covered_ids),
        "source_years_returned": sorted(bars.bar_open_time.dt.year.unique().tolist()),
        "no_native_close_inferred_from_max_hold": True,
    }
    save_json("_reconcile", reconciliation)
    report["phase_a"] = reconciliation
    need(not recon_mismatches, "RECONSTRUCTION_PARITY_MISMATCH")
    # Frozen Phase A explicitly blocks certification when the native boundary
    # is required but absent. The historical input manifest supplies a ceiling,
    # not per-identity native runtime terminal events or their loop ordering.
    raise RuntimeError("NATIVE_TERMINAL_BOUNDARY_NOT_BOUND_BY_AUTHORIZED_INPUTS")


def main():
    active = load(".akah_bot/active_task.json")
    need(active["task_id"] == TASK, "ACTIVE_TASK_MISMATCH")
    charter = gate.load_charter(ROOT)
    need(charter["current_state"]["current_bottleneck"] == TASK, "BOTTLENECK_DRIFT")
    need(gate.sha256_file(ROOT / gate.CHARTER_REL) == active["starting_charter_sha256"],
         "CHARTER_DRIFT")
    report = {
        "task_id": TASK, "task_start_revision": active["starting_charter_revision"],
        "task_start_head": active["starting_head"], "branch": active["starting_branch"],
        "objective": active["objective"], "authority_bindings": {},
        "event_type": "V2_PHASE_A_COHORT_COVERAGE_RECOVERY",
        "firewall": {"outcome_fields_read": False, "economic_test": False,
                     "source_mutation": False, "native_replay_executed": False,
                     "2023_new_raw_or_replay_accessed": False, "2025_accessed": False,
                     "production_changed": False},
    }
    try:
        run(report)
    except Exception as exc:
        report.update(
            status="FAIL_CLOSED", resolution_class=str(exc),
            summary=f"Phase A stopped: {type(exc).__name__}: {exc}",
            north_star_effect=("Preserves causal validity; historical window parity "
                               "is not native lifecycle authority."),
            next_bottleneck="CAUSAL_EXIT_BRAIN_V2_PHASE_A_NATIVE_TERMINAL_BOUNDARY_AUTHORITY_REVIEW_V1",
            state_updates={"v2_phase_a_audit": "FAIL_CLOSED",
                           "v2_phase_a_recovery_v2": "FAIL_CLOSED",
                           "v2_phase_b_admitted": False, "v2_phase_c_admitted": False,
                           "economics_authorized": False},
            error_type=type(exc).__name__, error=str(exc),
        )
    report["evidence"] = [{"path": str(path.relative_to(ROOT)).replace("\\", "/"),
                           "sha256": digest(path)}
                          for path in sorted((ROOT / "governance").glob("v2_a2_*"))
                          if path.suffix in (".json", ".csv")
                          and not path.name.endswith(("_rpt.json", "_gov.json"))]
    save_json("_rpt", report)
    emit("PHASE_A=" + report["status"])
    emit("RESOLUTION_CLASS=" + report["resolution_class"])
    return 2 if report["status"] == "FAIL_CLOSED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
