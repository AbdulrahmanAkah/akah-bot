from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spotbot.research.rd48_cross_venue_price_level_basis import (  # noqa: E402
    AXIS_BASIS_DISPERSION,
    AXIS_MEAN_BASIS,
    DATA_CUTOFF,
    DATA_START,
    MAINTENANCE_END,
    MAINTENANCE_START,
    PERIODS,
    aggregate_binance_hours,
    attach_features,
    kucoin_hour_lookup,
    qualify_transport_support,
    reconstruct_decision_rows,
    risk_set_parity,
    support_census,
)

BRANCH = "research/rd48-cross-venue-price-level-basis-direct-utility-v1"

P1_FREEZE = "3f1a85599f782889cc6bc81f5dcee5121c5ddc8b"
P1_PROTOCOL = Path(
    "data/research/rd48_p1/"
    "rd48-p1-cross-venue-price-level-basis-information-source-"
    "preregistration-v1.json"
)
P1_PROTOCOL_BLOB = "b31df5d95fc7d4552337e25fe5da2997072cdfe1"
P1_PROTOCOL_SHA256 = "c1f590ae7c3bf7702b4719bd1dd3643db8614e141510a4fd1f402e01689e1b24"
P1_AUDIT = Path("data/research/rd48_p1/rd48-p1-preregistration-audit-v1.json")
P1_AUDIT_BLOB = "0f2d86bc32e7f745906cdf404699667b809002a8"

RD37_AUDIT = Path("data/research/rd37_p1_runtime/source-file-audit.csv")
RD37_AUDIT_BLOB = "da9fbf2b70cd4f648d7acf71be31f5efdc9eb77a"
RD37_MAINT = Path("data/research/rd37_p1e_runtime/semantic-maintenance-evidence.json")
RD37_MAINT_BLOB = "8ac2608898a3719056eab014a7b41dfaf5a83ab7"
RD37_PROTOCOL = Path(
    "data/research/rd37_p2/"
    "rd37-p2-causal-1m-to-hour-stress-transforms-and-thresholds-"
    "preregistration-v1.json"
)
RD37_PROTOCOL_BLOB = "bcd576f1ae737c796279bbdfe2d13e6182e256ac"

RD26 = Path("src/spotbot/research/rd26_exit_architecture.py")
RD26_BLOB = "f00adb9825b0f6d8483b069045dcf82b029d6a29"

RISK = Path("data/research/rd41_p2_runtime/full-control-risk-set-ledger.csv")
RISK_BLOB = "12ead9da3c3f1d0df4eb33ca2e03f06f207ccbd8"
AGE = Path("data/research/rd41_p2_runtime/risk-set-by-year-universe-age.csv")
AGE_BLOB = "c8165284aea23c7667b6b8e1390fd7e55ba5c863"
TARGET = Path("data/research/rd41_p4_runtime/target-ledger.csv")
TARGET_BLOB = "c05773164b753aca2b1eb07d668888e1d05b0dae"

KUCOIN_ROOT = Path("data/raw/rd16b/kucoin")
BINANCE_ROOT = Path("data/raw/rd37/binance_spot_1m")
OUT = Path("data/research/rd48_p2_runtime")

EXPECTED_RISK_ROWS = 1996

OUTPUTS = (
    "cross-venue-price-level-basis-ledger.csv",
    "cross-venue-price-level-basis-data-quality-summary.csv",
    "cross-venue-price-level-basis-support-census.csv",
    "landmark-risk-set-parity.csv",
    "source-hour-parity.json",
    "qualified-cross-venue-price-level-basis-support-freeze.json",
    "output-manifest.json",
)


class RunnerError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode:
        raise RunnerError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
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


def verify_blob(repo: Path, path: Path, expected: str) -> None:
    actual = git(repo, "rev-parse", f"HEAD:{path.as_posix()}")
    if actual != expected:
        raise RunnerError(f"blob drift {path}: {actual} != {expected}")


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    raise RunnerError(f"unparseable boolean: {value!r}")


def preflight(repo: Path, expected_freeze: str) -> dict[str, Any]:
    if git(repo, "diff", "--cached", "--name-only", "--"):
        raise RunnerError("staged tracked changes before runtime")
    if git(repo, "diff", "--name-only", "--"):
        raise RunnerError("unstaged tracked changes before runtime")
    if git(repo, "branch", "--show-current") != BRANCH:
        raise RunnerError("wrong RD48 branch")
    if git(repo, "rev-parse", "HEAD") != expected_freeze:
        raise RunnerError("runtime HEAD differs from frozen engine commit")
    if git(repo, "rev-parse", "HEAD^") != P1_FREEZE:
        raise RunnerError("engine freeze parent differs from RD48-P1")

    for path, blob in (
        (P1_PROTOCOL, P1_PROTOCOL_BLOB),
        (P1_AUDIT, P1_AUDIT_BLOB),
        (RD37_AUDIT, RD37_AUDIT_BLOB),
        (RD37_MAINT, RD37_MAINT_BLOB),
        (RD37_PROTOCOL, RD37_PROTOCOL_BLOB),
        (RD26, RD26_BLOB),
        (RISK, RISK_BLOB),
        (AGE, AGE_BLOB),
        (TARGET, TARGET_BLOB),
    ):
        verify_blob(repo, path, blob)

    if sha256(repo / P1_PROTOCOL) != P1_PROTOCOL_SHA256:
        raise RunnerError("P1 protocol SHA drift")

    protocol = json.loads((repo / P1_PROTOCOL).read_text(encoding="utf-8-sig"))
    if protocol["information_source"] != "CROSS_VENUE_PRICE_LEVEL_BASIS_STATE":
        raise RunnerError("P1 information source drift")

    axes = [item["axis_id"] for item in protocol["canonical_independent_axes"]]
    if axes != [AXIS_MEAN_BASIS, AXIS_BASIS_DISPERSION]:
        raise RunnerError(f"canonical axes drift: {axes}")

    contract = protocol["future_p2_target_blind_reconstruction_contract"]
    if contract["expected_risk_decision_row_count"] != EXPECTED_RISK_ROWS:
        raise RunnerError("risk row contract drift")
    if contract["target_ledger_loading"] != "FORBIDDEN":
        raise RunnerError("P2 target loading not forbidden")
    if contract["rcv_value_loading"] != "FORBIDDEN":
        raise RunnerError("P2 RCV loading not forbidden")
    if contract["transport_support_rule"] != (
        "LANDMARK_ADVANCES_ONLY_IF_SUPPORT_PASS_IN_AT_LEAST_2_OF_3_UNIVERSES_IN_BOTH_2022_AND_2023"
    ):
        raise RunnerError("transport support rule drift")

    return {
        "p1_freeze_commit": P1_FREEZE,
        "target_ledger_git_blob_verified_not_loaded": TARGET_BLOB,
        "target_rows_loaded": False,
        "rcv_values_loaded": False,
        "rcv_associations_computed": False,
        "2024_accessed": False,
    }


def load_kucoin(
    repo: Path,
    symbol: str,
) -> tuple[dict[int, float], dict[str, Any]]:
    path = repo / KUCOIN_ROOT / symbol / "1h.parquet"
    if not path.is_file():
        raise RunnerError(f"missing KuCoin source: {path}")

    raw = pd.read_parquet(
        path,
        engine="pyarrow",
        columns=["timestamp", "close"],
        filters=[
            ("timestamp", ">=", DATA_START.to_pydatetime()),
            ("timestamp", "<", DATA_CUTOFF.to_pydatetime()),
        ],
    )

    ts = pd.to_datetime(raw["timestamp"], utc=True, errors="raise")
    if bool((ts >= DATA_CUTOFF).any()):
        raise RunnerError(f"2024+ KuCoin row loaded: {symbol}")

    lookup = kucoin_hour_lookup(raw)
    return lookup, {
        "record_type": "KUCOIN_SYMBOL",
        "venue": "KUCOIN_SPOT",
        "symbol": symbol,
        "source_path": str(path.relative_to(repo)),
        "loaded_row_count": int(len(raw)),
        "available_valid_close_hour_count": int(len(lookup)),
        "status": "READY",
    }


def read_binance_zip(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path, "r") as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise RunnerError(f"expected one CSV in {path}, got {csv_names}")
        with zf.open(csv_names[0], "r") as raw_handle:
            data = raw_handle.read()

    frame = pd.read_csv(
        io.BytesIO(data),
        header=None,
        usecols=[0, 4],
        names=["open_time", "close"],
        low_memory=False,
    )

    if len(frame) and str(frame.iloc[0]["open_time"]).strip().lower() in {"open_time", "open time"}:
        frame = frame.iloc[1:].reset_index(drop=True)

    return frame


def load_binance(
    repo: Path,
) -> tuple[dict[str, dict[int, float]], list[dict[str, Any]]]:
    audit = pd.read_csv(repo / RD37_AUDIT, low_memory=False)
    required = {
        "symbol",
        "month",
        "filename",
        "archive_sha256",
        "archive_bytes",
        "row_count",
        "checksum_verified",
        "archive_present",
        "schema_pass",
        "timestamp_parse_pass",
    }
    missing = sorted(required.difference(audit.columns))
    if missing:
        raise RunnerError(f"RD37 audit schema drift: missing {missing}")

    audit = audit.loc[
        audit["symbol"].astype(str).isin(["BTCUSDT", "ETHUSDT"])
        & audit["month"].astype(str).str.match(r"^202[23]-\d\d$")
    ].copy()

    if len(audit) != 48:
        raise RunnerError(f"RD37 audit expected 48 symbol-month rows, got {len(audit)}")
    if audit[["symbol", "month"]].duplicated().any():
        raise RunnerError("duplicate RD37 symbol-month rows")

    for col in (
        "checksum_verified",
        "archive_present",
        "schema_pass",
        "timestamp_parse_pass",
    ):
        if not audit[col].map(as_bool).all():
            raise RunnerError(f"RD37 audit contains false {col}")

    by_symbol: dict[str, dict[int, float]] = {
        "BTCUSDT": {},
        "ETHUSDT": {},
    }
    quality: list[dict[str, Any]] = []

    for row in audit.sort_values(["symbol", "month"], kind="stable").itertuples(index=False):
        symbol = str(row.symbol)
        filename = str(row.filename)
        expected_filename = f"{symbol}-1m-{row.month}.zip"
        if filename != expected_filename:
            raise RunnerError(
                f"RD37 filename drift {symbol} {row.month}: {filename} != {expected_filename}"
            )

        path = repo / BINANCE_ROOT / symbol / filename
        if not path.is_file():
            raise RunnerError(f"missing verified Binance archive: {path}")

        actual_sha = sha256(path)
        expected_sha = str(row.archive_sha256).strip().lower()
        if actual_sha != expected_sha:
            raise RunnerError(f"Binance archive SHA drift {path}: {actual_sha} != {expected_sha}")
        if path.stat().st_size != int(row.archive_bytes):
            raise RunnerError(f"Binance archive byte-size drift: {path}")

        frame = read_binance_zip(path)
        numeric = pd.to_numeric(frame["open_time"], errors="raise")
        ts = pd.to_datetime(numeric, unit="ms", utc=True, errors="raise")
        frame = frame.loc[(ts >= DATA_START) & (ts < DATA_CUTOFF)].reset_index(drop=True)

        lookup, stats = aggregate_binance_hours(frame)
        overlap = set(by_symbol[symbol]).intersection(lookup)
        if overlap:
            raise RunnerError(f"duplicate Binance hours across archives: {symbol} {len(overlap)}")
        by_symbol[symbol].update(lookup)

        quality.append(
            {
                "record_type": "BINANCE_SYMBOL_MONTH",
                "venue": "BINANCE_SPOT",
                "symbol": symbol,
                "month": str(row.month),
                "source_path": str(path.relative_to(repo)),
                "archive_sha256_verified": True,
                "archive_bytes_verified": True,
                "audit_row_count": int(row.row_count),
                **stats,
                "status": "READY",
            }
        )

    return by_symbol, quality


def source_hour_parity(
    decisions: pd.DataFrame,
    kucoin: dict[str, dict[int, float]],
    binance: dict[str, dict[int, float]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    for period in PERIODS:
        subset = decisions.loc[decisions["period_id"].astype(str) == period]
        required = sorted(
            {
                int((pd.Timestamp(time) - pd.Timedelta(hours=1)).as_unit("ns").value)
                for time in pd.to_datetime(subset["decision_time"], utc=True)
            }
        )

        component_maps = {
            "KUCOIN_BTC": kucoin["BTC-USDT"],
            "KUCOIN_ETH": kucoin["ETH-USDT"],
            "BINANCE_BTC": binance["BTCUSDT"],
            "BINANCE_ETH": binance["ETHUSDT"],
        }

        available = {
            name: sum(key in mapping for key in required)
            for name, mapping in component_maps.items()
        }
        all_available = sum(
            all(key in mapping for mapping in component_maps.values()) for key in required
        )

        rows.append(
            {
                "period_id": period,
                "unique_required_source_hour_count": len(required),
                **{
                    f"{name}_valid_required_hour_count": int(value)
                    for name, value in available.items()
                },
                "all_four_components_valid_required_hour_count": int(all_available),
                "all_four_components_invalid_or_missing_required_hour_count": int(
                    len(required) - all_available
                ),
            }
        )

    return {
        "schema_version": "rd48-p2-source-hour-parity-v1",
        "source_hour_definition": "[t-1h,t)",
        "maintenance_blackout_start_utc": MAINTENANCE_START.isoformat(),
        "maintenance_blackout_end_exclusive_utc": MAINTENANCE_END.isoformat(),
        "same_completed_hour_across_all_four_components_required": True,
        "required_component_semantics": "POSITIVE_COMPLETED_HOUR_CLOSE_ONLY",
        "open_price_used": False,
        "high_price_used": False,
        "low_price_used": False,
        "open_to_close_return_used": False,
        "candle_geometry_used": False,
        "period_parity": rows,
    }


def manifest_for(
    out: Path,
    names: tuple[str, ...],
) -> dict[str, Any]:
    files = [
        {
            "name": name,
            "sha256": sha256(out / name),
            "bytes": (out / name).stat().st_size,
        }
        for name in names
    ]

    deterministic_hash = hashlib.sha256(
        json.dumps(
            files,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    return {
        "schema_version": "rd48-p2-output-manifest-v1",
        "files": files,
        "deterministic_hash": deterministic_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--expected-freeze-commit", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if not args.execute:
        raise RunnerError("--execute is required")

    repo = args.repo_root.resolve()
    print("RD48_P2_RUNTIME_VERSION=TARGET_BLIND_CROSS_VENUE_PRICE_LEVEL_BASIS_V1")

    lineage = preflight(repo, args.expected_freeze_commit)

    out = repo / OUT
    if out.exists():
        raise RunnerError(f"runtime output already exists; do not rerun: {out}")
    out.mkdir(parents=True, exist_ok=False)

    risk = pd.read_csv(repo / RISK, low_memory=False)
    age = pd.read_csv(repo / AGE, low_memory=False)
    decisions = reconstruct_decision_rows(risk)

    if len(decisions) != EXPECTED_RISK_ROWS:
        raise RunnerError(f"risk decision count {len(decisions)} != {EXPECTED_RISK_ROWS}")

    parity = risk_set_parity(decisions, age)
    if len(parity) != 36 or not bool(parity["parity_pass"].all()):
        raise RunnerError("frozen RD41 risk-set parity failed")

    parity.to_csv(
        out / "landmark-risk-set-parity.csv",
        index=False,
        lineterminator="\n",
    )
    print("RD48_P2_RISK_SET_PARITY=PASS;rows=1996;cells=36")

    kucoin: dict[str, dict[int, float]] = {}
    quality: list[dict[str, Any]] = []

    for symbol in ("BTC-USDT", "ETH-USDT"):
        lookup, record = load_kucoin(repo, symbol)
        kucoin[symbol] = lookup
        quality.append(record)
        print(f"RD48_P2_KUCOIN_SOURCE={symbol}:hours={len(lookup)}")

    binance, binance_quality = load_binance(repo)
    quality.extend(binance_quality)
    print(
        "RD48_P2_BINANCE_SOURCE="
        f"BTCUSDT:{len(binance['BTCUSDT'])};"
        f"ETHUSDT:{len(binance['ETHUSDT'])}"
    )

    ledger = attach_features(decisions, kucoin, binance)
    if len(ledger) != EXPECTED_RISK_ROWS:
        raise RunnerError("feature ledger row parity failed")

    ledger.to_csv(
        out / "cross-venue-price-level-basis-ledger.csv",
        index=False,
        lineterminator="\n",
    )

    quality_frame = pd.DataFrame.from_records(quality)
    if len(quality_frame) != 50:
        raise RunnerError(f"data-quality record count {len(quality_frame)} != 50")
    quality_frame.to_csv(
        out / "cross-venue-price-level-basis-data-quality-summary.csv",
        index=False,
        lineterminator="\n",
    )

    census = support_census(ledger)
    if len(census) != 36:
        raise RunnerError("support census must have 36 cells")
    census.to_csv(
        out / "cross-venue-price-level-basis-support-census.csv",
        index=False,
        lineterminator="\n",
    )

    write_json(
        out / "source-hour-parity.json",
        source_hour_parity(decisions, kucoin, binance),
    )

    qualification = qualify_transport_support(census)
    qualified = qualification["qualified_landmarks_hours"]

    if qualified:
        decision = (
            "RD48_CROSS_VENUE_PRICE_LEVEL_BASIS_SUPPORT_"
            "QUALIFIED_READY_FOR_TARGET_ASSOCIATION_PREREGISTRATION"
        )
        next_stage = (
            "RD48_P3_PREREGISTER_AND_FREEZE_CROSS_VENUE_PRICE_"
            "LEVEL_BASIS_DIRECT_UTILITY_TRANSPORT_PRE_RCV_EXPOSURE"
        )
    else:
        decision = (
            "RD48_CROSS_VENUE_PRICE_LEVEL_BASIS_INSUFFICIENT_TRANSPORT_SUPPORT_CLOSE_PRE_TARGET"
        )
        next_stage = "RD48_CLOSE_CROSS_VENUE_PRICE_LEVEL_BASIS_INSUFFICIENT_SUPPORT_NO_RCV_EXPOSURE"

    freeze = {
        "schema_version": "rd48-p2-qualified-cross-venue-price-level-basis-support-freeze-v1",
        "status": "PASS",
        "information_source": "CROSS_VENUE_PRICE_LEVEL_BASIS_STATE",
        "canonical_independent_axes": [
            AXIS_MEAN_BASIS,
            AXIS_BASIS_DISPERSION,
        ],
        **qualification,
        "decision": decision,
        "next_stage": next_stage,
        "risk_decision_row_count": int(len(ledger)),
        "valid_feature_row_count": int(ledger["feature_valid"].astype(bool).sum()),
        "invalid_feature_row_count": int((~ledger["feature_valid"].astype(bool)).sum()),
        **lineage,
        "new_features_computed": True,
        "raw_market_data_loaded": True,
        "raw_market_data_scope": "2022_2023_ONLY_FROZEN_BINANCE_KUCOIN_SOURCES",
        "model_fit_performed": False,
        "parameter_search_used": False,
        "threshold_optimization_used": False,
        "winner_selection_used": False,
        "context_selection_used": False,
        "landmark_selection_used": False,
        "window_selection_used": False,
        "lag_selection_used": False,
        "symbol_weight_selection_used": False,
        "axis_selection_used": False,
        "venue_selection_used": False,
        "action_mapping_executed": False,
        "economic_action_executed": False,
        "production_authorized": False,
    }

    write_json(
        out / "qualified-cross-venue-price-level-basis-support-freeze.json",
        freeze,
    )
    write_json(
        out / "output-manifest.json",
        manifest_for(out, OUTPUTS[:-1]),
    )

    print("RD48_P2_RUNTIME_FINAL_SUMMARY_BEGIN")
    print(json.dumps(freeze, indent=2, sort_keys=True))
    print("RD48_P2_RUNTIME_FINAL_SUMMARY_END")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
