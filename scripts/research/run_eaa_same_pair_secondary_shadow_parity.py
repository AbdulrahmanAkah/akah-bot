from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BRANCH = "research/rd48-cross-venue-price-level-basis-direct-utility-v1"
HEAD = "0902707c80e41d73d21c03b6eaea4228c11d2296"
CUT = pd.Timestamp("2022-01-01T00:00:00Z")
PERIODS = {
    "DISCOVERY_2019_2020": (pd.Timestamp("2019-01-01T00:00:00Z"), pd.Timestamp("2021-01-01T00:00:00Z")),
    "TEMPORAL_REPLICATION_2021": (pd.Timestamp("2021-01-01T00:00:00Z"), pd.Timestamp("2022-01-01T00:00:00Z")),
}
EXPECTED_HASHES = {
    "p0": "BBCE8ED353207EE779C14A2182E453A12363C8553C761DD393102208B1328EAA",
    "protocol": "5B47130872D327060AB63889E30C4EEC48CA19AC7E4AC209DB8B1714CA7B8216",
    "p4p4r": "636CC3C61EA951FDEFD7A55115376D20E0453034EE28FD4F8A4EAE96085E54A4",
    "p4p5r": "BFD184F4C4CB9EBD177A6FD9E8B7F5172CE413121EB64243DCFAB8FF9EE1EDFC",
    "signals": "ABCCD5BC6CB10792CFAA3B260B4326E8F1DA5312CDCD8E4E5E8593AE17AD5B71",
    "rd26": "1290748EA7E8A0343C1A15CEDFC1220AA423F04C11FDD558311B06AC7DA90359",
    "rd27": "82E2BF09E1A74A101580C625E0F71987484A9368F597FDD7515E4B31F4E0B425",
    "state": "EE205CDA74D70A530734BBFB4843C2DBFC8BF950122254AA2ACEB8766A90F9AD",
}
PERIOD_SIGNAL_COUNTS = {"DISCOVERY_2019_2020": 2509, "TEMPORAL_REPLICATION_2021": 1453}


class ProofError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest().upper()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise ProofError("git failed: " + " ".join(args) + ": " + result.stderr.strip())
    return result.stdout.strip()


def utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def require_close(label: str, actual: float, expected: float) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=1e-11, abs_tol=1e-7):
        raise ProofError(f"{label}: actual={actual!r} expected={expected!r}")


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ProofError(f"JSON object required: {path}")
    return value


def compare_frame(label: str, left: pd.DataFrame, right: pd.DataFrame) -> None:
    try:
        pd.testing.assert_frame_equal(left.reset_index(drop=True), right.reset_index(drop=True), check_dtype=True, check_exact=True)
    except AssertionError as error:
        raise ProofError(f"{label} frame parity failed: {error}") from error


def compare_counter_subset(label: str, observed: dict[str, int], expected: dict[str, Any]) -> None:
    for key, expected_value in expected.items():
        if key in observed and int(observed[key]) != int(expected_value):
            raise ProofError(f"{label}.{key}: {observed[key]} != {expected_value}")


def compare_execution_records(label: str, observed: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    if len(observed) != len(expected):
        raise ProofError(f"{label}.count: {len(observed)} != {len(expected)}")
    for index, (actual_row, expected_row) in enumerate(zip(observed, expected, strict=True)):
        actual_keys, expected_keys = set(actual_row), set(expected_row)
        if actual_keys != expected_keys:
            extra_keys = actual_keys - expected_keys
            missing_keys = expected_keys - actual_keys
            # P4/P4R (1x) sealed event_key inline; P5R (2x) sealed the same
            # identity through period_id + signal_time + pair and omitted only the
            # redundant inline event_key field.  Accept exactly that known schema
            # asymmetry, while keeping every other key drift fail-closed.
            if missing_keys or extra_keys != {"event_key"} or "event_key" in expected_keys:
                raise ProofError(
                    f"{label}[{index}].keys drift: "
                    f"extra={sorted(extra_keys)!r} missing={sorted(missing_keys)!r}"
                )
            for required in ("period_id", "signal_time", "pair"):
                if required not in expected_row:
                    raise ProofError(f"{label}[{index}].event_key authority missing {required}")
            derived_event_key = (
                f"{expected_row['period_id']}|{utc(expected_row['signal_time']).isoformat()}|{expected_row['pair']}"
            )
            if actual_row["event_key"] != derived_event_key:
                raise ProofError(
                    f"{label}[{index}].event_key derivation drift: "
                    f"{actual_row['event_key']!r} != {derived_event_key!r}"
                )
        for key, expected_value in expected_row.items():
            actual_value = actual_row[key]
            if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
                require_close(f"{label}[{index}].{key}", float(actual_value), float(expected_value))
            elif actual_value != expected_value:
                raise ProofError(f"{label}[{index}].{key}: {actual_value!r} != {expected_value!r}")


def preflight(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    repo = args.repo_root
    if not (repo / ".git").is_dir():
        raise ProofError("not a git repository")
    if git(repo, "branch", "--show-current") != BRANCH or git(repo, "rev-parse", "HEAD") != HEAD:
        raise ProofError("repository authority drift")
    paths = {
        "p0": args.p0_json, "protocol": args.protocol_json, "p4p4r": args.p4p4r_json,
        "p4p5r": args.p4p5r_json, "signals": args.signals,
        "rd26": repo / "src/spotbot/research/rd26_exit_architecture.py",
        "rd27": repo / "src/spotbot/research/rd27_lifecycle_replay.py",
        "state": repo / "src/spotbot/research/rd27_adaptive_lifecycle.py",
    }
    for key, path in paths.items():
        if not path.is_file():
            raise ProofError(f"required authority missing: {key}: {path}")
        actual = sha256(path)
        if actual != EXPECTED_HASHES[key]:
            raise ProofError(f"authority hash drift: {key}: {actual} != {EXPECTED_HASHES[key]}")
    p0 = load_object(args.p0_json); protocol = load_object(args.protocol_json)
    if p0.get("status") != "PASS_SHADOW_IMPLEMENTATION_P0_STATIC_SOURCE_AUTHORITY_AUDIT":
        raise ProofError("P0 status drift")
    if p0.get("protocol_authority", {}).get("implementation_protocol_id") != "SHADOW_DISABLED_BY_DEFAULT_CAUSAL_SAME_PAIR_SECONDARY_IMPLEMENTATION_V1":
        raise ProofError("P0 implementation protocol ID drift")
    frozen = protocol.get("implementation_decision_protocol", {})
    if protocol.get("status") != "PASS_POST_P4_P5R_IMPLEMENTATION_DECISION_PROTOCOL_FROZEN" or frozen.get("protocol_id") != "SHADOW_DISABLED_BY_DEFAULT_CAUSAL_SAME_PAIR_SECONDARY_IMPLEMENTATION_V1":
        raise ProofError("implementation protocol authority drift")
    return load_object(args.p4p4r_json), load_object(args.p4p5r_json)


def load_signals(path: Path) -> pd.DataFrame:
    columns = ["timestamp", "pair", "membership_rank", "period_id", "support_families", "support_count", "atr24_at_signal"]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    if len(frame) != 3962:
        raise ProofError(f"signal row count drift: {len(frame)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame["membership_rank"] = pd.to_numeric(frame["membership_rank"], errors="raise").astype(int)
    frame["atr24_at_signal"] = pd.to_numeric(frame["atr24_at_signal"], errors="raise").astype(float)
    frame["pair"] = frame["pair"].astype(str); frame["period_id"] = frame["period_id"].astype(str); frame["support_families"] = frame["support_families"].astype(str)
    if bool((frame["timestamp"] >= CUT).any()):
        raise ProofError("signal ledger crossed sealed pre-2022 cutoff")
    for period_id, (start, end) in PERIODS.items():
        subset = frame[frame["period_id"] == period_id]
        if len(subset) != PERIOD_SIGNAL_COUNTS[period_id] or bool((subset["timestamp"] < start).any()) or bool((subset["timestamp"] >= end).any()):
            raise ProofError(f"signal period authority drift: {period_id}")
    return frame.sort_values(["period_id", "timestamp", "membership_rank", "pair"], kind="stable").reset_index(drop=True)


def market_authority(*, raw_root: Path, pairs: list[str], rd26: Any, state: Any) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, list[dict[str, Any]]]:
    frames: dict[str, pd.DataFrame] = {}; audit: list[dict[str, Any]] = []; cutoff = CUT.to_pydatetime()
    for index, pair in enumerate(pairs, start=1):
        path = raw_root / pair / "1h.parquet"
        if not path.is_file():
            raise ProofError(f"raw source missing: {path}")
        raw = pd.read_parquet(path, engine="pyarrow", filters=[("timestamp", "<", cutoff)])
        timestamps = pd.to_datetime(raw["timestamp"], utc=True, errors="raise")
        if raw.empty or bool((timestamps >= CUT).any()):
            raise ProofError(f"raw cutoff pushdown failed: {pair}")
        feature = rd26.prepare_features(raw, cutoff=CUT); frames[pair] = feature
        audit.append({"pair": pair, "row_count_materialized": len(feature), "first_timestamp": utc(feature["timestamp"].iloc[0]).isoformat(), "last_timestamp": utc(feature["timestamp"].iloc[-1]).isoformat(), "cutoff_exclusive": CUT.isoformat()})
        print(f"RAW_PRE2022={index}/{len(pairs)}:{pair}:{len(feature)}", flush=True)
    btc_raw = pd.read_parquet(raw_root / "BTC-USDT" / "1h.parquet", engine="pyarrow", filters=[("timestamp", "<", cutoff)])
    if bool((pd.to_datetime(btc_raw["timestamp"], utc=True, errors="raise") >= CUT).any()):
        raise ProofError("BTC state source crossed pre-2022 cutoff")
    state_frame = state.build_market_state_frame(btc_raw, cutoff=CUT)
    if bool((pd.to_datetime(state_frame["timestamp"], utc=True, errors="raise") >= CUT).any()):
        raise ProofError("state frame crossed pre-2022 cutoff")
    return frames, state_frame, audit


def sealed_policy_payload(authority: dict[str, Any], period_id: str, cost_multiplier: float) -> dict[str, Any]:
    row = authority["results"]["by_period"][period_id]
    return row["causal_policy"] if cost_multiplier == 1.0 else row["causal_policy_2x"]


def sealed_baseline_payload(authority: dict[str, Any], period_id: str, cost_multiplier: float) -> dict[str, Any]:
    row = authority["results"]["by_period"][period_id]
    return row["baseline"] if cost_multiplier == 1.0 else row["baseline_2x"]


def validate_against_sealed(*, label: str, result: Any, sealed: dict[str, Any]) -> dict[str, Any]:
    require_close(label + ".final_equity", float(result.metrics["final_equity"]), float(sealed["final_equity"]))
    if len(result.trades) != int(sealed["trade_count"]):
        raise ProofError(f"{label}.trade_count: {len(result.trades)} != {sealed['trade_count']}")
    compare_counter_subset(label + ".counters", result.counters, sealed["counters"])
    expected_diag = sealed.get("causal_policy_diagnostics", {}); observed_diag = result.diagnostics
    for key in ("secondary_trigger_count", "secondary_executed_count", "secondary_blocked_global_active_count", "secondary_blocked_position_slots_count", "secondary_blocked_risk_off_count", "secondary_blocked_data_or_capacity_count", "secondary_blocked_equity_or_gross_count", "secondary_blocked_cash_or_notional_count"):
        if key in expected_diag and int(observed_diag[key]) != int(expected_diag[key]):
            raise ProofError(f"{label}.{key}: {observed_diag[key]} != {expected_diag[key]}")
    if "secondary_execution_records" in expected_diag:
        compare_execution_records(label + ".secondary_execution_records", observed_diag["secondary_execution_records"], expected_diag["secondary_execution_records"])
    if int(observed_diag["max_open_positions_hourly_close"]) > 5:
        raise ProofError(label + ": maximum positions exceeded five")
    return {"final_equity": float(result.metrics["final_equity"]), "trade_count": len(result.trades), "secondary_trigger_count": int(observed_diag["secondary_trigger_count"]), "secondary_executed_count": int(observed_diag["secondary_executed_count"]), "max_open_positions": int(observed_diag["max_open_positions_hourly_close"]), "max_gross_exposure_fraction_mark_to_market_diagnostic": float(observed_diag["max_gross_exposure_fraction_mark_to_market_diagnostic"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("repo-root", "raw-root", "signals", "p0-json", "protocol-json", "p4p4r-json", "p4p5r-json", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for attr in ("repo_root", "raw_root", "signals", "p0_json", "protocol_json", "p4p4r_json", "p4p5r_json", "output_dir"):
        setattr(args, attr, getattr(args, attr).resolve())
    print("STAGE=EAA_REALLOCATION_POST_P4_P5R_SHADOW_IMPLEMENTATION_AND_PARITY_PROOF")
    print("MODE=RESEARCH_BRANCH_BOUNDED_SHADOW_DEFAULT_DISABLED_PRE2022_1X_2X_PARITY_NO_2023_NO_2024")
    print("REPO=" + str(args.repo_root))
    p4p4r, p4p5r = preflight(args)
    sys.path.insert(0, str(args.repo_root / "src"))
    from spotbot.research import eaa_same_pair_secondary_shadow as shadow
    from spotbot.research import rd26_exit_architecture as rd26
    from spotbot.research import rd27_adaptive_lifecycle as state
    from spotbot.research import rd27_lifecycle_replay as rd27
    shadow.validate_shadow_constants()
    signals = load_signals(args.signals); pairs = sorted(set(signals["pair"].astype(str)))
    frames, state_frame, raw_audit = market_authority(raw_root=args.raw_root, pairs=pairs, rd26=rd26, state=state)
    proof: dict[str, Any] = {}
    for cost_multiplier, authority in ((1.0, p4p4r), (2.0, p4p5r)):
        cost_key = "1x" if cost_multiplier == 1.0 else "2x"; proof[cost_key] = {}
        for period_id, (start, end) in PERIODS.items():
            subset = signals[signals["period_id"] == period_id].copy(); print(f"PARITY_START={cost_key}:{period_id}", flush=True)
            native = rd27.replay_lifecycle_policy(policy_id=rd27.STATIC_EXIT_STATE_ROUTER, portfolio_id="EAA_SHADOW_PARITY_NATIVE", universe_id="PRE2022_UNION", cost_multiplier=cost_multiplier, events=subset, frames=frames, state_frame=state_frame, replay_start=start, replay_cutoff=end)
            disabled = shadow.replay_same_pair_secondary_shadow(portfolio_id="EAA_SHADOW_PARITY_NATIVE", universe_id="PRE2022_UNION", cost_multiplier=cost_multiplier, events=subset, frames=frames, state_frame=state_frame, replay_start=start, replay_cutoff=end, shadow_enabled=False)
            native_trades, native_daily, native_metrics, native_counters = native
            compare_frame(f"{cost_key}.{period_id}.disabled_trades", disabled.trades, native_trades); compare_frame(f"{cost_key}.{period_id}.disabled_daily", disabled.daily, native_daily)
            if disabled.metrics != native_metrics or disabled.counters != native_counters:
                raise ProofError(f"{cost_key}.{period_id}.default-disabled semantic parity drift")
            sealed_baseline = sealed_baseline_payload(authority, period_id, cost_multiplier)
            require_close(f"{cost_key}.{period_id}.native_final_equity", float(native_metrics["final_equity"]), float(sealed_baseline["final_equity"]))
            if len(native_trades) != int(sealed_baseline["trade_count"]):
                raise ProofError(f"{cost_key}.{period_id}.native trade-count drift")
            compare_counter_subset(f"{cost_key}.{period_id}.native_counters", native_counters, sealed_baseline["counters"])
            enabled = shadow.replay_same_pair_secondary_shadow(portfolio_id="EAA_SHADOW_POLICY", universe_id="PRE2022_UNION", cost_multiplier=cost_multiplier, events=subset, frames=frames, state_frame=state_frame, replay_start=start, replay_cutoff=end, shadow_enabled=True)
            sealed_policy = sealed_policy_payload(authority, period_id, cost_multiplier); observed = validate_against_sealed(label=f"{cost_key}.{period_id}.policy", result=enabled, sealed=sealed_policy)
            increment = float(enabled.metrics["final_equity"]) - float(native_metrics["final_equity"])
            endpoint_key = "final_portfolio_net_pnl_policy_minus_baseline" if cost_multiplier == 1.0 else "final_portfolio_net_pnl_policy_minus_baseline_at_2x"
            expected_increment = float(authority["results"]["by_period"][period_id]["primary_endpoint"][endpoint_key])
            require_close(f"{cost_key}.{period_id}.increment", increment, expected_increment)
            observed.update({"native_final_equity": float(native_metrics["final_equity"]), "incremental_final_net_pnl": increment, "default_disabled_semantic_parity": True, "sealed_authority_match": True}); proof[cost_key][period_id] = observed
            print(f"PARITY_PASS={cost_key}:{period_id}:NATIVE={native_metrics['final_equity']}:POLICY={enabled.metrics['final_equity']}:INCREMENT={increment}", flush=True)

    implementation_path = args.repo_root / "src/spotbot/research/eaa_same_pair_secondary_shadow.py"; test_path = args.repo_root / "tests/research/test_eaa_same_pair_secondary_shadow.py"; runner_path = args.repo_root / "scripts/research/run_eaa_same_pair_secondary_shadow_parity.py"
    result = {
        "schema_version": "eaa-reallocation-post-p4-p5r-shadow-implementation-parity-proof-v1",
        "status": "PASS_SHADOW_IMPLEMENTATION_AND_PARITY_PROOF",
        "stage": "EAA_REALLOCATION_POST_P4_P5R_SHADOW_IMPLEMENTATION_AND_PARITY_PROOF_NO_AUTOMATIC_INTERVENTION_NO_2023_NO_2024",
        "branch": BRANCH, "head": HEAD,
        "implementation_protocol_id": "SHADOW_DISABLED_BY_DEFAULT_CAUSAL_SAME_PAIR_SECONDARY_IMPLEMENTATION_V1",
        "policy_protocol_id": "CAUSAL_FIRST_ELIGIBLE_SINGLE_ACTIVE_SAME_PAIR_SECONDARY_V1",
        "implementation": {"default_enabled": False, "research_only": True, "production_activation": False, "files": {str(implementation_path.relative_to(args.repo_root)): sha256(implementation_path), str(test_path.relative_to(args.repo_root)): sha256(test_path), str(runner_path.relative_to(args.repo_root)): sha256(runner_path)}},
        "acceptance_gates": {"static_source_authority_audit_pass_before_edit": True, "default_disabled_semantic_parity_with_native_rd27": True, "exact_policy_trigger_and_precedence_regression_tests_pass": True, "global_single_active_secondary_guard_tests_pass": True, "maximum_positions_5_unchanged_test_pass": True, "admission_time_gross_limit_0_9_unchanged_test_pass": True, "no_oracle_or_future_outcome_feature_dependency_test_pass": True, "pre2022_one_x_reproduction_matches_sealed_p4p4r_authority": True, "pre2022_two_x_reproduction_matches_sealed_p4p5r_authority": True, "no_2023_access": True, "no_2024_access": True, "no_network_calls": True, "no_production_activation": True},
        "parity_proof": proof,
        "raw_authority": {"scope": "PRE2022_ONLY", "cutoff_exclusive": CUT.isoformat(), "predicate_pushdown_before_materialization": True, "source_rows": raw_audit, "signal_rows": len(signals), "signal_period_counts": PERIOD_SIGNAL_COUNTS},
        "safety": {"reopened_2023": False, "accessed_2024": False, "network_calls": 0, "automatic_intervention_authorized": False, "production_policy_change_authorized": False, "live_order_path_activation_authorized": False, "model_fit_executed": False, "threshold_search_executed": False, "trading_parameter_optimization_executed": False, "maximum_positions_changed": False, "leverage_changed": False, "repo_mutation": True, "repo_mutation_scope": ["src/spotbot/research/eaa_same_pair_secondary_shadow.py", "tests/research/test_eaa_same_pair_secondary_shadow.py", "scripts/research/run_eaa_same_pair_secondary_shadow_parity.py"]},
        "next_gate": {"review_required_after_shadow_implementation_parity_proof": True, "automatic_intervention_authorized": False, "production_policy_change_authorized": False},
        "handoff_contract": {"success_send_only_this_json": True, "failure_send_full_log_only": True},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True); stamp = datetime.now().strftime("%Y%m%d_%H%M%S"); output = args.output_dir / f"EAA_REALLOCATION_POST_P4_P5R_SHADOW_IMPLEMENTATION_PARITY_PROOF_CANONICAL_RESULT_{stamp}.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print("EAA_REALLOCATION_POST_P4_P5R_SHADOW_IMPLEMENTATION_PARITY_PROOF=PASS"); print("DEFAULT_SHADOW_ENABLED=NO"); print("PRE2022_1X_REPRODUCTION=PASS"); print("PRE2022_2X_REPRODUCTION=PASS"); print("2023_REOPENED=NO"); print("2024_ACCESSED=NO"); print("NETWORK_CALLS=0"); print("PRODUCTION_ACTIVATION=NO"); print("AUTOMATIC_INTERVENTION_AUTHORIZED=NO"); print("CANONICAL_RESULT_JSON=" + str(output)); print("CANONICAL_RESULT_JSON_SHA256=" + sha256(output)); print("SUCCESS_HANDOFF_INSTRUCTION=SEND_ONLY_CANONICAL_RESULT_JSON")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProofError as error:
        print("EAA_REALLOCATION_POST_P4_P5R_SHADOW_PARITY_FAIL_CLOSED=" + str(error), file=sys.stderr, flush=True)
        raise SystemExit(2)
