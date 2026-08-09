from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd26_exit_architecture import (  # noqa: E402
    BASE_ROUND_TRIP_COST,
)
from spotbot.research.rd37_exit_shadow_ablation import (  # noqa: E402
    CONTROL_POLICY,
    CONTROL_PORTFOLIO,
    CONTROL_VARIANT,
    COST_MULTIPLIERS,
    DATA_CUTOFF,
    DATA_START,
    FAILURE_DECISION,
    FAILURE_NEXT,
    PERIODS,
    SUCCESS_DECISION,
    SUCCESS_NEXT,
    UNION_VARIANT,
    UNIVERSES,
    VARIANT_FAMILIES,
    VARIANTS,
    attribution_table,
    build_episode_index,
    control_net_pnl_recomputed,
    earliest_trigger,
    metric_table,
    normalize_episode_ledger,
    qualification_tables,
    shadow_pnl,
    utc,
    validate_constants,
)

P4_FREEZE = "1aad70b4a64b6303c864ee1a8f400f2d3c858a2d"
P3_RESULTS = "0ecb07a494a1b67cf545821bd928593e10b86a5f"

P4_PROTOCOL = Path(
    "data/research/rd37_p4/rd37-p4-kucoin-native-exit-brain-shadow-ablation-preregistration-v1.json"
)
P4_PROTOCOL_BLOB = "76f6cea888268b9d01a1b0a70369cf6c4080cd91"
P4_PROTOCOL_SHA256 = "841b310c3406894cb1e67ae8f0d62776e8db592ff3d2f7c15337058b63b5bb31"
P4_AUDIT = Path("data/research/rd37_p4/rd37-p4-preregistration-audit-v1.json")
P4_AUDIT_BLOB = "287417852d483b576f3f5c8c8867e1381f0d1618"

P3_EPISODES = Path("data/research/rd37_p3_runtime/episode-ledger.csv")
P3_EPISODES_BLOB = "f02a2bf0cd9211db9656df630afd9773f951b3f6"

RD32_TRADES = Path("data/research/rd32_p3_runtime/trade-ledger.csv")
RD32_TRADES_BLOB = "6749de85cb14733388e0f76a6557124d3212398b"
RD32_TRADES_FROZEN_SHA256 = "07f49e0e9235f736f54ee9dd59142c16fc4e7b99e83781b1ee26b9338def117e"
RD33_PARITY = Path("data/research/rd33_p1_runtime/control-parity-vs-rd32.json")
RD33_PARITY_BLOB = "8df58c1f7ea451f7c891f7fc3444d5f330d7852a"

RD26_ENGINE = Path("src/spotbot/research/rd26_exit_architecture.py")
RD26_ENGINE_BLOB = "f00adb9825b0f6d8483b069045dcf82b029d6a29"
RD31_REPLAY = Path("src/spotbot/research/rd31_regime_governed_replay.py")
RD31_REPLAY_BLOB = "0a8a56904b0dc200ad516666a0749c3472e59e91"
RD30_EXIT = Path("src/spotbot/research/rd30_family_specialist_state.py")
RD30_EXIT_BLOB = "285caf6b4a2a17903c2d0584229802ac15871d85"

KUCOIN_ROOT = Path("data/raw/rd16b/kucoin")
OUTPUT = Path("data/research/rd37_p5_runtime")

OUTPUT_NAMES = (
    "input-and-conformance-audit.json",
    "control-trade-summary.csv",
    "shadow-trade-ledger.csv",
    "shadow-run-metrics.csv",
    "shadow-period-metrics.csv",
    "trigger-family-attribution.csv",
    "support-family-attribution.csv",
    "control-exit-reason-attribution.csv",
    "participation-context-attribution.csv",
    "qualification-evaluation.csv",
    "primary-union-selection-freeze.json",
    "rd37-p5-exit-brain-shadow-ablation-report-v1.json",
)


class RunnerError(RuntimeError):
    pass


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--repo-root", type=Path, required=True)
    value.add_argument("--execute", action="store_true")
    value.add_argument("--validate-only", action="store_true")
    value.add_argument("--expected-freeze-commit", default=None)
    return value


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RunnerError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RunnerError(f"JSON object expected: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def verify_blob(
    repo: Path,
    path: Path,
    expected: str,
    label: str,
) -> None:
    actual = git(repo, "rev-parse", f"HEAD:{path.as_posix()}")
    if actual != expected:
        raise RunnerError(f"{label} blob drift: {actual} != {expected}")


def verify_lineage(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes before P5")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before P5")

    head = git(repo, "rev-parse", "HEAD")
    if head != expected_freeze_commit:
        raise RunnerError(f"P5 HEAD {head} != freeze {expected_freeze_commit}")
    if git(repo, "rev-parse", "HEAD^") != P4_FREEZE:
        raise RunnerError("P5 engine-freeze parent is not P4 freeze")

    for path, blob, label in (
        (P4_PROTOCOL, P4_PROTOCOL_BLOB, "P4 protocol"),
        (P4_AUDIT, P4_AUDIT_BLOB, "P4 audit"),
        (P3_EPISODES, P3_EPISODES_BLOB, "P3 episodes"),
        (RD32_TRADES, RD32_TRADES_BLOB, "RD32 trades"),
        (RD33_PARITY, RD33_PARITY_BLOB, "RD33 parity"),
        (RD26_ENGINE, RD26_ENGINE_BLOB, "RD26 cost engine"),
        (RD31_REPLAY, RD31_REPLAY_BLOB, "RD31 replay"),
        (RD30_EXIT, RD30_EXIT_BLOB, "RD30 exit engine"),
    ):
        verify_blob(repo, path, blob, label)

    protocol = load_json(repo / P4_PROTOCOL)
    audit = load_json(repo / P4_AUDIT)
    if protocol.get("status") != "FROZEN_PRE_ECONOMIC_ABLATION":
        raise RunnerError("P4 protocol is not frozen")
    if protocol.get("next_stage") != (
        "RD37_P5_FREEZE_AND_RUN_KUCOIN_NATIVE_EXIT_BRAIN_SHADOW_ABLATION_2022_2023_ONCE"
    ):
        raise RunnerError("P4 next-stage drifted")
    if (
        protocol.get("lineage", {}).get("rd32_trade_ledger_frozen_sha256")
        != RD32_TRADES_FROZEN_SHA256
    ):
        raise RunnerError("RD32 trade-ledger frozen SHA drifted")
    if protocol.get("p5_reporting", {}).get("primary_variant") != UNION_VARIANT:
        raise RunnerError("P4 primary variant drifted")
    if audit.get("protocol_sha256") != P4_PROTOCOL_SHA256:
        raise RunnerError("P4 protocol SHA reference drifted")
    if audit.get("freed_capital_reuse_allowed") is not False:
        raise RunnerError("P4 unexpectedly permits capital reuse")

    validate_constants()
    if not math.isclose(BASE_ROUND_TRIP_COST, 0.0025):
        raise RunnerError("RD26 cost contract drifted")

    return {
        "runner_freeze_commit": expected_freeze_commit,
        "p4_freeze_commit": P4_FREEZE,
        "p4_protocol_git_blob": P4_PROTOCOL_BLOB,
        "p4_audit_git_blob": P4_AUDIT_BLOB,
        "p3_episode_ledger_git_blob": P3_EPISODES_BLOB,
        "rd32_trade_ledger_git_blob": RD32_TRADES_BLOB,
        "rd32_trade_ledger_frozen_sha256": (RD32_TRADES_FROZEN_SHA256),
        "rd26_cost_engine_git_blob": RD26_ENGINE_BLOB,
        "base_round_trip_cost": BASE_ROUND_TRIP_COST,
    }


def load_control_trades(repo: Path) -> pd.DataFrame:
    frame = pd.read_csv(repo / RD32_TRADES, low_memory=False)
    required = {
        "policy_id",
        "portfolio_id",
        "universe_id",
        "cost_multiplier",
        "pair",
        "signal_time",
        "entry_time",
        "exit_time",
        "holding_hours",
        "exit_reason",
        "entry_price",
        "exit_price",
        "quantity",
        "entry_notional",
        "exit_notional",
        "entry_cost",
        "exit_cost",
        "gross_pnl",
        "net_pnl",
        "period_id",
        "membership_rank",
        "support_families",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise RunnerError(f"RD32 trade ledger missing frozen fields: {missing}")

    frame = frame.loc[
        (frame["policy_id"].astype(str) == CONTROL_POLICY)
        & (frame["portfolio_id"].astype(str) == CONTROL_PORTFOLIO)
        & frame["universe_id"].astype(str).isin(UNIVERSES)
        & pd.to_numeric(frame["cost_multiplier"], errors="coerce").isin(COST_MULTIPLIERS)
    ].copy()
    if frame.empty:
        raise RunnerError("frozen control trade set is empty")

    for column in ("signal_time", "entry_time", "exit_time"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise").dt.as_unit("ns")
    for column in (
        "cost_multiplier",
        "entry_price",
        "exit_price",
        "quantity",
        "entry_notional",
        "entry_cost",
        "net_pnl",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)

    if frame["entry_time"].min() < DATA_START:
        raise RunnerError("pre-2022 control trade entered P5")
    if frame["exit_time"].max() >= DATA_CUTOFF:
        raise RunnerError("2024+ control exit entered P5")
    if not bool((frame["entry_time"] < frame["exit_time"]).all()):
        raise RunnerError("invalid control holding interval")
    if not set(frame["period_id"].astype(str)).issubset(PERIODS):
        raise RunnerError("unexpected control period")
    if not set(frame["universe_id"].astype(str)).issubset(UNIVERSES):
        raise RunnerError("unexpected control universe")

    recomputed = frame.apply(
        lambda row: control_net_pnl_recomputed(
            row,
            base_round_trip_cost=BASE_ROUND_TRIP_COST,
        ),
        axis=1,
    )
    errors = np.abs(recomputed.to_numpy(dtype=float) - frame["net_pnl"].to_numpy(dtype=float))
    maximum_error = float(errors.max()) if len(errors) else 0.0
    if maximum_error > 1e-6:
        raise RunnerError(f"control net-PnL parity failed: {maximum_error}")

    frame = frame.sort_values(
        [
            "universe_id",
            "cost_multiplier",
            "entry_time",
            "pair",
            "exit_time",
        ],
        kind="stable",
    ).reset_index(drop=True)
    frame["control_trade_id"] = np.arange(len(frame), dtype=np.int64)
    return frame


def load_episodes(repo: Path) -> pd.DataFrame:
    raw = pd.read_csv(repo / P3_EPISODES, low_memory=False)
    return normalize_episode_ledger(raw)


def load_target_lookups(
    repo: Path,
    pairs: list[str],
) -> dict[str, dict[int, float]]:
    start = DATA_START.to_pydatetime()
    cutoff = DATA_CUTOFF.to_pydatetime()
    lookups: dict[str, dict[int, float]] = {}

    for index, pair in enumerate(pairs, start=1):
        path = repo / KUCOIN_ROOT / pair / "1h.parquet"
        if not path.is_file():
            raise RunnerError(f"KuCoin target missing: {path}")
        frame = pd.read_parquet(
            path,
            columns=["timestamp", "open"],
            engine="pyarrow",
            filters=[
                ("timestamp", ">=", start),
                ("timestamp", "<", cutoff),
            ],
        )
        frame["timestamp"] = pd.to_datetime(
            frame["timestamp"], utc=True, errors="raise"
        ).dt.as_unit("ns")
        frame["open"] = pd.to_numeric(frame["open"], errors="raise").astype(float)
        frame = frame.sort_values("timestamp", kind="stable").reset_index(drop=True)
        if frame["timestamp"].duplicated().any():
            raise RunnerError(f"duplicate KuCoin target timestamp: {pair}")
        if bool((frame["open"] <= 0.0).any()):
            raise RunnerError(f"non-positive KuCoin open: {pair}")
        lookups[pair] = {
            int(timestamp): float(price)
            for timestamp, price in zip(
                frame["timestamp"].astype("int64").tolist(),
                frame["open"].tolist(),
                strict=True,
            )
        }
        print(
            f"RD37_P5_TARGET={index}/{len(pairs)}:{pair}:rows={len(frame)}",
            flush=True,
        )
    return lookups


def support_bucket(value: Any) -> str:
    families = {item for item in str(value).split("|") if item}
    if families == {"MOMENTUM_BREAKOUT"}:
        return "MB"
    if families == {"RELATIVE_STRENGTH_ROTATION"}:
        return "RS"
    if families == {
        "MOMENTUM_BREAKOUT",
        "RELATIVE_STRENGTH_ROTATION",
    }:
        return "OVERLAP"
    return "OTHER"


def build_shadow_ledger(
    control: pd.DataFrame,
    episodes: pd.DataFrame,
    lookups: dict[str, dict[int, float]],
) -> pd.DataFrame:
    episode_index = build_episode_index(episodes)
    rows: list[dict[str, Any]] = []

    for control_row in control.to_dict(orient="records"):
        pair = str(control_row["pair"])
        entry = utc(control_row["entry_time"])
        control_exit = utc(control_row["exit_time"])
        lookup = lookups[pair]

        for variant in VARIANTS:
            trigger = earliest_trigger(
                episode_index,
                allowed_families=VARIANT_FAMILIES[variant],
                entry_time=entry,
                control_exit_time=control_exit,
            )

            if variant == CONTROL_VARIANT or trigger is None:
                triggered = False
                evaluable = True
                trigger_time = pd.NaT
                trigger_families = ""
                participation = False
                shadow_exit_time = control_exit
                shadow_exit_price = float(control_row["exit_price"])
                shadow_net = float(control_row["net_pnl"])
                delta = 0.0
                exit_advance = 0
            else:
                triggered = True
                trigger_time = utc(trigger["reference_time"])
                trigger_families = "|".join(trigger["trigger_families"])
                participation = bool(trigger["participation_burst_active"])
                shadow_exit_time = trigger_time
                price = lookup.get(int(trigger_time.as_unit("ns").value))
                if price is None:
                    evaluable = False
                    shadow_exit_price = np.nan
                    shadow_net = np.nan
                    delta = np.nan
                else:
                    evaluable = True
                    shadow_exit_price = float(price)
                    pnl = shadow_pnl(
                        control_row,
                        shadow_exit_price=shadow_exit_price,
                        base_round_trip_cost=BASE_ROUND_TRIP_COST,
                    )
                    shadow_net = float(pnl["shadow_net_pnl"])
                    delta = float(pnl["delta_net_pnl"])
                exit_advance = int((control_exit - shadow_exit_time).total_seconds() // 3600)
                if exit_advance <= 0:
                    raise RunnerError("shadow trigger did not advance control exit")

            rows.append(
                {
                    "variant_id": variant,
                    "control_trade_id": int(control_row["control_trade_id"]),
                    "universe_id": str(control_row["universe_id"]),
                    "cost_multiplier": float(control_row["cost_multiplier"]),
                    "period_id": str(control_row["period_id"]),
                    "pair": pair,
                    "signal_time": control_row["signal_time"],
                    "entry_time": entry,
                    "control_exit_time": control_exit,
                    "control_exit_reason": str(control_row["exit_reason"]),
                    "control_exit_price": float(control_row["exit_price"]),
                    "quantity": float(control_row["quantity"]),
                    "entry_notional": float(control_row["entry_notional"]),
                    "entry_cost": float(control_row["entry_cost"]),
                    "control_net_pnl": float(control_row["net_pnl"]),
                    "support_families": str(control_row["support_families"]),
                    "support_family_bucket": support_bucket(control_row["support_families"]),
                    "triggered": bool(triggered),
                    "evaluable": bool(evaluable),
                    "trigger_time": trigger_time,
                    "trigger_family_set": trigger_families,
                    "participation_burst_at_trigger": bool(participation),
                    "shadow_exit_time": shadow_exit_time,
                    "shadow_exit_price": shadow_exit_price,
                    "exit_advance_hours": int(exit_advance),
                    "shadow_net_pnl": shadow_net,
                    "delta_net_pnl": delta,
                    "slot_escrow_release_time": control_exit,
                    "capital_reuse_allowed": False,
                }
            )

    result = pd.DataFrame.from_records(rows)
    expected_rows = len(control) * len(VARIANTS)
    if len(result) != expected_rows:
        raise RunnerError("shadow ledger row-count drift")
    return result


def control_summary(control: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    grouped = control.groupby(
        ["universe_id", "cost_multiplier", "period_id"],
        sort=False,
    )
    for key, part in grouped:
        universe, cost, period = key
        rows.append(
            {
                "universe_id": universe,
                "cost_multiplier": cost,
                "period_id": period,
                "control_trade_count": len(part),
                "control_net_pnl": float(part["net_pnl"].sum()),
                "pair_count": int(part["pair"].astype(str).nunique()),
            }
        )
    return pd.DataFrame.from_records(rows)


def execute(
    repo: Path,
    expected_freeze_commit: str,
) -> dict[str, Any]:
    lineage = verify_lineage(repo, expected_freeze_commit)
    if (repo / OUTPUT).exists():
        raise RunnerError("P5 runtime already exists; preserve and recover/validate")

    control = load_control_trades(repo)
    episodes = load_episodes(repo)
    pairs = sorted(control["pair"].astype(str).unique())
    lookups = load_target_lookups(repo, pairs)

    shadow = build_shadow_ledger(
        control,
        episodes,
        lookups,
    )
    runs = metric_table(shadow, by_period=False)
    periods = metric_table(shadow, by_period=True)
    qualification, family, union_qualified = qualification_tables(
        runs,
        periods,
    )

    decision = SUCCESS_DECISION if union_qualified else FAILURE_DECISION
    next_stage = SUCCESS_NEXT if union_qualified else FAILURE_NEXT

    output = repo / OUTPUT
    output.mkdir(parents=True, exist_ok=False)

    maximum_control_pnl_error = float(
        np.max(
            np.abs(
                control.apply(
                    lambda row: control_net_pnl_recomputed(
                        row,
                        base_round_trip_cost=BASE_ROUND_TRIP_COST,
                    ),
                    axis=1,
                ).to_numpy(dtype=float)
                - control["net_pnl"].to_numpy(dtype=float)
            )
        )
    )
    unevaluable_primary = int(
        (
            (shadow["variant_id"] == UNION_VARIANT)
            & shadow["triggered"].astype(bool)
            & ~shadow["evaluable"].astype(bool)
        ).sum()
    )

    audit = {
        "schema_version": "rd37-p5-input-and-conformance-audit-v1",
        "stage": "RD37_P5_KUCOIN_NATIVE_EXIT_BRAIN_SHADOW_ABLATION_2022_2023",
        "status": "PASS",
        "lineage": lineage,
        "control_policy": CONTROL_POLICY,
        "control_portfolio": CONTROL_PORTFOLIO,
        "control_trade_count": len(control),
        "control_pair_count": len(pairs),
        "episode_row_count": len(episodes),
        "variant_count": len(VARIANTS),
        "expected_shadow_row_count": len(control) * len(VARIANTS),
        "actual_shadow_row_count": len(shadow),
        "maximum_control_net_pnl_recompute_error": (maximum_control_pnl_error),
        "primary_union_unevaluable_triggered_trade_count": (unevaluable_primary),
        "all_primary_union_triggered_fills_available": (unevaluable_primary == 0),
        "source_control_trade_set_fixed": True,
        "entries_fixed": True,
        "quantities_fixed": True,
        "admissions_fixed": True,
        "slot_escrow_until_control_exit": True,
        "freed_capital_reuse": False,
        "raw_binance_reloaded": False,
        "rd37_features_recomputed": False,
        "rd37_episodes_recomputed": False,
        "kucoin_local_prices_loaded": True,
        "network_access_performed": False,
        "shadow_economic_counterfactual_executed": True,
        "full_dynamic_portfolio_replay_executed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "return_ranking_used": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "input-and-conformance-audit.json",
        audit,
    )

    control_summary(control).to_csv(
        output / "control-trade-summary.csv",
        index=False,
        lineterminator="\n",
    )
    shadow.to_csv(
        output / "shadow-trade-ledger.csv",
        index=False,
        lineterminator="\n",
    )
    runs.to_csv(
        output / "shadow-run-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    periods.to_csv(
        output / "shadow-period-metrics.csv",
        index=False,
        lineterminator="\n",
    )
    attribution_table(
        shadow,
        column="trigger_family_set",
        slice_type="TRIGGER_FAMILY",
    ).to_csv(
        output / "trigger-family-attribution.csv",
        index=False,
        lineterminator="\n",
    )
    attribution_table(
        shadow,
        column="support_family_bucket",
        slice_type="SUPPORT_FAMILY_BUCKET",
    ).to_csv(
        output / "support-family-attribution.csv",
        index=False,
        lineterminator="\n",
    )
    attribution_table(
        shadow,
        column="control_exit_reason",
        slice_type="CONTROL_EXIT_REASON",
    ).to_csv(
        output / "control-exit-reason-attribution.csv",
        index=False,
        lineterminator="\n",
    )
    attribution_table(
        shadow,
        column="participation_burst_at_trigger",
        slice_type="PARTICIPATION_CONTEXT_DESCRIPTIVE_ONLY",
    ).to_csv(
        output / "participation-context-attribution.csv",
        index=False,
        lineterminator="\n",
    )
    qualification.to_csv(
        output / "qualification-evaluation.csv",
        index=False,
        lineterminator="\n",
    )

    selection = {
        "schema_version": "rd37-p5-primary-union-selection-freeze-v1",
        "status": "PASS",
        "primary_variant": UNION_VARIANT,
        "qualified": bool(union_qualified),
        "decision": decision,
        "next_stage": next_stage,
        "individual_family_variants_can_rescue_failure": False,
        "participation_context_can_rescue_failure": False,
        "return_ranking_used": False,
        "winner_selection_used": False,
        "threshold_optimization_used": False,
        "parameter_search_used": False,
        "full_dynamic_portfolio_replay_executed": False,
        "production_authorized": False,
    }
    write_json(
        output / "primary-union-selection-freeze.json",
        selection,
    )

    report = {
        "schema_version": "rd37-p5-exit-brain-shadow-ablation-report-v1",
        "stage": "RD37_P5_KUCOIN_NATIVE_EXIT_BRAIN_SHADOW_ABLATION_2022_2023",
        "status": "PASS",
        "runner_freeze_commit": expected_freeze_commit,
        "source_p4_freeze_commit": P4_FREEZE,
        "control_policy": CONTROL_POLICY,
        "control_portfolio": CONTROL_PORTFOLIO,
        "primary_variant": UNION_VARIANT,
        "control_trade_count": len(control),
        "shadow_trade_row_count": len(shadow),
        "qualified": bool(union_qualified),
        "decision": decision,
        "next_stage": next_stage,
        "all_primary_union_triggered_fills_available": (unevaluable_primary == 0),
        "slot_escrow_until_control_exit": True,
        "freed_capital_reuse": False,
        "raw_binance_reloaded": False,
        "rd37_features_recomputed": False,
        "rd37_episodes_recomputed": False,
        "kucoin_local_prices_loaded": True,
        "network_access_performed": False,
        "shadow_economic_counterfactual_executed": True,
        "full_dynamic_portfolio_replay_executed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "return_ranking_used": False,
        "winner_selection_used": False,
        "2024_accessed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    write_json(
        output / "rd37-p5-exit-brain-shadow-ablation-report-v1.json",
        report,
    )

    files: dict[str, dict[str, Any]] = {}
    for name in OUTPUT_NAMES:
        path = output / name
        files[name] = {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
    canonical = json.dumps(
        files,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    write_json(
        output / "output-manifest.json",
        {
            "schema_version": "rd37-p5-output-manifest-v1",
            "file_count": len(files),
            "files": files,
            "deterministic_hash": hashlib.sha256(canonical).hexdigest(),
            "decision": decision,
            "runner_freeze_commit": expected_freeze_commit,
        },
    )

    return validate_outputs(repo)


def validate_outputs(repo: Path) -> dict[str, Any]:
    output = repo / OUTPUT
    if not output.is_dir():
        raise RunnerError("P5 runtime missing")

    expected = sorted((*OUTPUT_NAMES, "output-manifest.json"))
    observed = sorted(path.name for path in output.iterdir() if path.is_file())
    if observed != expected:
        raise RunnerError(f"P5 output registry drift: {observed} != {expected}")

    report = load_json(output / "rd37-p5-exit-brain-shadow-ablation-report-v1.json")
    selection = load_json(output / "primary-union-selection-freeze.json")
    shadow = pd.read_csv(
        output / "shadow-trade-ledger.csv",
        low_memory=False,
    )
    runs = pd.read_csv(
        output / "shadow-run-metrics.csv",
        low_memory=False,
    )
    periods = pd.read_csv(
        output / "shadow-period-metrics.csv",
        low_memory=False,
    )
    qualification = pd.read_csv(
        output / "qualification-evaluation.csv",
        low_memory=False,
    )

    expected_run_cells = len(VARIANTS) * len(UNIVERSES) * len(COST_MULTIPLIERS)
    expected_period_cells = expected_run_cells * len(PERIODS)
    if len(runs) != expected_run_cells:
        raise RunnerError("P5 run-metric cell count drifted")
    if len(periods) != expected_period_cells:
        raise RunnerError("P5 period-metric cell count drifted")
    if len(qualification) != 7:
        raise RunnerError("P5 qualification row count drifted")

    if len(shadow):
        entries = pd.to_datetime(shadow["entry_time"], utc=True, errors="raise")
        exits = pd.to_datetime(shadow["control_exit_time"], utc=True, errors="raise")
        if entries.min() < DATA_START or exits.max() >= DATA_CUTOFF:
            raise RunnerError("P5 shadow ledger accessed outside 2022-2023")

    qualified = bool(selection.get("qualified"))
    expected_decision = SUCCESS_DECISION if qualified else FAILURE_DECISION
    expected_next = SUCCESS_NEXT if qualified else FAILURE_NEXT

    if report.get("decision") != expected_decision:
        raise RunnerError("P5 decision mismatch")
    if report.get("next_stage") != expected_next:
        raise RunnerError("P5 next-stage mismatch")
    if selection.get("decision") != expected_decision:
        raise RunnerError("P5 selection freeze mismatch")

    for field in (
        "freed_capital_reuse",
        "raw_binance_reloaded",
        "rd37_features_recomputed",
        "rd37_episodes_recomputed",
        "network_access_performed",
        "full_dynamic_portfolio_replay_executed",
        "parameter_search_used",
        "threshold_optimization_used",
        "return_ranking_used",
        "winner_selection_used",
        "2024_accessed",
        "post_2024_accessed",
        "production_authorized",
    ):
        if report.get(field) is not False:
            raise RunnerError(f"prohibited P5 report flag: {field}")

    manifest = load_json(output / "output-manifest.json")
    if manifest.get("file_count") != len(OUTPUT_NAMES):
        raise RunnerError("P5 manifest count drifted")
    if manifest.get("decision") != expected_decision:
        raise RunnerError("P5 manifest decision drifted")

    union_runs = runs.loc[runs["variant_id"] == UNION_VARIANT].copy()
    union_periods = periods.loc[periods["variant_id"] == UNION_VARIANT].copy()

    compact_runs = []
    for row in union_runs.to_dict(orient="records"):
        compact_runs.append(
            {
                "universe_id": row["universe_id"],
                "cost_multiplier": float(row["cost_multiplier"]),
                "triggered_trade_count": int(row["triggered_trade_count"]),
                "total_delta_net_pnl": float(row["total_delta_net_pnl"]),
                "minimum_loao_total_delta_net_pnl": float(
                    row["minimum_leave_one_asset_out_total_delta_net_pnl"]
                ),
            }
        )

    compact_periods = []
    for row in union_periods.to_dict(orient="records"):
        compact_periods.append(
            {
                "universe_id": row["universe_id"],
                "cost_multiplier": float(row["cost_multiplier"]),
                "period_id": row["period_id"],
                "triggered_trade_count": int(row["triggered_trade_count"]),
                "total_delta_net_pnl": float(row["total_delta_net_pnl"]),
            }
        )

    return {
        "status": "PASS",
        "qualified": qualified,
        "decision": expected_decision,
        "next_stage": expected_next,
        "control_trade_count": int(report["control_trade_count"]),
        "shadow_trade_row_count": int(report["shadow_trade_row_count"]),
        "primary_variant": UNION_VARIANT,
        "all_primary_union_triggered_fills_available": bool(
            report["all_primary_union_triggered_fills_available"]
        ),
        "union_run_metrics": compact_runs,
        "union_period_metrics": compact_periods,
        "slot_escrow_until_control_exit": True,
        "freed_capital_reuse": False,
        "full_dynamic_portfolio_replay_executed": False,
        "2024_accessed": False,
        "production_authorized": False,
    }


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    if not (repo / ".git").exists():
        raise RunnerError(f"not a git repository: {repo}")

    if args.validate_only:
        print(
            json.dumps(
                validate_outputs(repo),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        )
        return 0

    if not args.execute:
        raise RunnerError("P5 requires explicit --execute")
    if not args.expected_freeze_commit:
        raise RunnerError("--expected-freeze-commit is required")

    print(
        json.dumps(
            execute(repo, args.expected_freeze_commit),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
