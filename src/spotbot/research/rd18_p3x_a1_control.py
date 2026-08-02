"""Exact six-symbol COMPOSITE_ALPHA_V3 regeneration for RD18-P3X-A1.

The control path deliberately reuses the frozen RD16 implementation modules.
It does not generalize the historical pilot-only asset gate.  C2 breadth stays
blocked until a causal replacement for that gate is preregistered.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.research.rd16c_common import dataframe_content_hash
from spotbot.research.rd16c_families import REGISTRY_BY_ID, build_candidate_frame
from spotbot.research.rd16c_features import build_feature_frame
from spotbot.research.rd16c_smoke import _admit_trades, _evaluate_candidate
from spotbot.research.rd16d_metrics import enrich_trades
from spotbot.research.rd16e_components import apply_variant, attach_signal_features
from spotbot.research.rd16h_expansion import (
    COMPRESSION_FULL_COMPONENT,
    COMPRESSION_STRUCTURE_COMPONENT,
    TREND_DIAGNOSTIC_COMPONENT,
    TREND_FULL_COMPONENT,
    TREND_STRUCTURE_COMPONENT,
    build_expansion_candidates,
    build_variant_sources,
)
from spotbot.research.rd16h_expansion import (
    VARIANT_BY_ID as H_VARIANT_BY_ID,
)
from spotbot.research.rd16i_architecture import route_v2_candidates
from spotbot.research.rd16k_remediation import (
    VARIANT_BY_ID as K_VARIANT_BY_ID,
)
from spotbot.research.rd16k_remediation import (
    rebuild_candidate_paths,
    route_remediation_candidates,
)
from spotbot.research.rd16l_architecture import prepare_v3_ledgers
from spotbot.research.rd18_p3x_a1 import (
    CONTROL_SYMBOLS,
    EXPECTED_CONTROL_COUNTS,
    P3R_RECORDED_CONTROL_CONTENT_HASHES,
    load_json,
    sha256_path,
    write_json,
)

TREND_FAMILY: Final = "MTF_TREND_BREAKOUT"
COMPRESSION_FAMILY: Final = "MTF_COMPRESSION_EXPANSION"
CONTEXT_TIMEFRAMES: Final = ("1h", "4h", "1d", "1w")
H_VARIANT: Final = "EVIDENCE_COMPOSITE_EXPANSION"
K_VARIANT: Final = "STRONG_BULL_HOLD_96"


class A1ControlError(RuntimeError):
    """Raised when exact legacy-control regeneration cannot be proved."""


def _bar_positions(frame: pd.DataFrame) -> dict[pd.Timestamp, int]:
    return {
        pd.Timestamp(value): position for position, value in enumerate(frame["timestamp"].tolist())
    }


def _load_control_frames(
    repo_root: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    store = ParquetCandleStore(repo_root / "data/raw/rd16b")
    hourly: dict[str, pd.DataFrame] = {}
    features: dict[str, pd.DataFrame] = {}
    for symbol in CONTROL_SYMBOLS:
        frames = {
            timeframe: store.load(
                exchange_id="kucoin",
                symbol=symbol,
                timeframe=timeframe,
                verify_integrity=True,
            )
            for timeframe in CONTEXT_TIMEFRAMES
        }
        hourly[symbol] = frames["1h"]
        features[symbol] = build_feature_frame(frames, symbol=symbol)
    return hourly, features


def _family_ledgers(
    family_id: str,
    *,
    hourly: Mapping[str, pd.DataFrame],
    features: Mapping[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    registration = REGISTRY_BY_ID[family_id]
    candidate_parts: list[pd.DataFrame] = []
    for symbol in CONTROL_SYMBOLS:
        candidate_parts.append(
            build_candidate_frame(
                features[symbol],
                symbol=symbol,
                registration=registration,
            )
        )
    candidates = pd.concat(candidate_parts, ignore_index=True)
    evaluated_records: list[dict[str, object]] = []
    positions = {symbol: _bar_positions(hourly[symbol]) for symbol in CONTROL_SYMBOLS}
    for raw in candidates.to_dict(orient="records"):
        candidate = cast(dict[str, object], raw)
        symbol = str(candidate["symbol"])
        evaluated = _evaluate_candidate(
            candidate,
            bars=hourly[symbol],
            registration=registration,
            bar_positions=positions[symbol],
        )
        if evaluated is not None:
            evaluated_records.append(evaluated)
    evaluated = pd.DataFrame.from_records(evaluated_records)
    trades, _ = _admit_trades(evaluated)
    if trades.empty:
        raise A1ControlError(f"{family_id} admitted no control trades")
    return {
        "candidates": candidates,
        "evaluated": evaluated,
        "trades": trades,
    }


def _component_frames(
    *,
    hourly: Mapping[str, pd.DataFrame],
    features: Mapping[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    ledgers = {
        family_id: _family_ledgers(family_id, hourly=hourly, features=features)
        for family_id in (TREND_FAMILY, COMPRESSION_FAMILY)
    }
    enriched = {
        family_id: attach_signal_features(
            enrich_trades(
                family_ledgers["trades"],
                hourly_frames=hourly,
                feature_frames=features,
            ),
            feature_frames=features,
        )
        for family_id, family_ledgers in ledgers.items()
    }
    components = {
        TREND_FULL_COMPONENT: apply_variant(
            enriched[TREND_FAMILY],
            family_id=TREND_FAMILY,
            variant_id="FULL_REMEDIATION_STACK",
        ),
        TREND_STRUCTURE_COMPONENT: apply_variant(
            enriched[TREND_FAMILY],
            family_id=TREND_FAMILY,
            variant_id="DIAGNOSTIC_PLUS_STRUCTURE",
        ),
        TREND_DIAGNOSTIC_COMPONENT: apply_variant(
            enriched[TREND_FAMILY],
            family_id=TREND_FAMILY,
            variant_id="ALL_DIAGNOSTIC_GATES",
        ),
        COMPRESSION_FULL_COMPONENT: apply_variant(
            enriched[COMPRESSION_FAMILY],
            family_id=COMPRESSION_FAMILY,
            variant_id="FULL_REMEDIATION_STACK",
        ),
        COMPRESSION_STRUCTURE_COMPONENT: apply_variant(
            enriched[COMPRESSION_FAMILY],
            family_id=COMPRESSION_FAMILY,
            variant_id="DIAGNOSTIC_PLUS_STRUCTURE",
        ),
    }
    diagnostics: dict[str, object] = {
        "base_family_candidate_counts": {
            family_id: len(value["candidates"]) for family_id, value in ledgers.items()
        },
        "base_family_trade_counts": {
            family_id: len(value["trades"]) for family_id, value in ledgers.items()
        },
        "component_counts": {name: len(frame) for name, frame in components.items()},
    }
    return components, diagnostics


def regenerate_control(repo_root: Path) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    """Regenerate the frozen six-symbol V3 ledgers through their exact lineage."""

    hourly, features = _load_control_frames(repo_root)
    components, diagnostics = _component_frames(hourly=hourly, features=features)

    source_frames, source_labels = build_variant_sources(
        components,
        H_VARIANT_BY_ID[H_VARIANT],
    )
    expansion_candidates = build_expansion_candidates(
        source_frames,
        source_labels=source_labels,
        variant_id=H_VARIANT,
    )
    v2 = route_v2_candidates(expansion_candidates)
    k_variant = K_VARIANT_BY_ID[K_VARIANT]
    rebuilt = rebuild_candidate_paths(
        v2.candidates,
        hourly_frames=hourly,
        variant=k_variant,
    )
    remediated = route_remediation_candidates(rebuilt, variant=k_variant)
    v3 = prepare_v3_ledgers(
        remediated.candidates,
        remediated.evaluated,
        remediated.trades,
    )
    ledgers = {
        "candidates": v3.candidates,
        "evaluated": v3.evaluated,
        "trades": v3.trades,
    }
    diagnostics.update(
        {
            "rd16h_candidate_count": len(expansion_candidates),
            "rd16i_candidate_count": len(v2.candidates),
            "rd16i_trade_count": len(v2.trades),
            "rd16k_candidate_count": len(remediated.candidates),
            "rd16k_trade_count": len(remediated.trades),
            "rd16l_candidate_count": len(v3.candidates),
            "rd16l_trade_count": len(v3.trades),
            "maximum_positions_observed": v3.maximum_positions_observed,
            "maximum_open_risk_fraction_observed": (v3.maximum_open_risk_fraction_observed),
        }
    )
    return ledgers, diagnostics


def _legacy_ledgers(repo_root: Path) -> dict[str, pd.DataFrame]:
    manifest = load_json(repo_root / "data/research/rd16l/local-ledger-manifest-v1.json")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, dict):
        raise A1ControlError("RD16L local ledger manifest entries are missing")
    local_root = repo_root / "data/raw/rd16l"
    frames: dict[str, pd.DataFrame] = {}
    for name in ("candidates", "evaluated", "trades"):
        raw_entry = raw_entries.get(name)
        if not isinstance(raw_entry, dict):
            raise A1ControlError(f"RD16L local manifest is missing {name}")
        relative = raw_entry.get("logical_path")
        if not isinstance(relative, str):
            raise A1ControlError(f"RD16L local path is missing for {name}")
        path = local_root / relative
        if not path.is_file():
            raise A1ControlError(f"legacy control ledger is missing: {path}")
        expected_file_hash = raw_entry.get("file_sha256")
        expected_content_hash = raw_entry.get("content_sha256")
        expected_rows = raw_entry.get("rows")
        if not isinstance(expected_file_hash, str) or sha256_path(path) != expected_file_hash:
            raise A1ControlError(f"legacy control file hash mismatch: {name}")
        frame = pd.read_parquet(path)
        if not isinstance(expected_rows, int) or len(frame) != expected_rows:
            raise A1ControlError(f"legacy control row count mismatch: {name}")
        if (
            not isinstance(expected_content_hash, str)
            or dataframe_content_hash(frame) != expected_content_hash
        ):
            raise A1ControlError(f"legacy control content hash mismatch: {name}")
        frames[name] = frame
    return frames


def _column_value_parity(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    if len(left) != len(right) or set(left.columns) != set(right.columns):
        return False
    ordered_columns = sorted(left.columns)
    left_hash = dataframe_content_hash(left.loc[:, ordered_columns])
    right_hash = dataframe_content_hash(right.loc[:, ordered_columns])
    return left_hash == right_hash


def parity_report(
    repo_root: Path,
    regenerated: Mapping[str, pd.DataFrame],
) -> dict[str, object]:
    legacy = _legacy_ledgers(repo_root)
    legacy_manifest = load_json(repo_root / "data/research/rd16l/local-ledger-manifest-v1.json")
    raw_entries = legacy_manifest.get("entries")
    if not isinstance(raw_entries, dict):
        raise A1ControlError("RD16L local ledger manifest entries are missing")

    rows: dict[str, dict[str, object]] = {}
    for name in ("candidates", "evaluated", "trades"):
        current = regenerated[name]
        expected = legacy[name]
        raw_entry = raw_entries.get(name)
        if not isinstance(raw_entry, dict):
            raise A1ControlError(f"RD16L local manifest is missing {name}")
        manifest_hash = raw_entry.get("content_sha256")
        if not isinstance(manifest_hash, str):
            raise A1ControlError(f"RD16L content hash is missing for {name}")

        current_hash = dataframe_content_hash(current)
        expected_hash = dataframe_content_hash(expected)
        p3r_recorded_hash = P3R_RECORDED_CONTROL_CONTENT_HASHES[name]
        rd16l_match = current_hash == expected_hash == manifest_hash
        value_parity = _column_value_parity(current, expected)

        rows[name] = {
            "expected_rows": len(expected),
            "actual_rows": len(current),
            "registered_expected_rows": EXPECTED_CONTROL_COUNTS[name],
            "row_count_match": (len(current) == len(expected) == EXPECTED_CONTROL_COUNTS[name]),
            "expected_local_content_hash": expected_hash,
            "actual_local_content_hash": current_hash,
            "rd16l_manifest_content_hash": manifest_hash,
            "local_content_hash_match": current_hash == expected_hash,
            "rd16l_manifest_content_hash_match": rd16l_match,
            "registered_content_hash_match": rd16l_match,
            "registered_hash_authority": "RD16L_LOCAL_LEDGER_MANIFEST",
            "column_and_value_parity": value_parity,
            "p3r_recorded_content_hash": p3r_recorded_hash,
            "p3r_recorded_hash_match": current_hash == p3r_recorded_hash,
        }

    passed = all(
        bool(row["row_count_match"])
        and bool(row["local_content_hash_match"])
        and bool(row["rd16l_manifest_content_hash_match"])
        and bool(row["column_and_value_parity"])
        for row in rows.values()
    )
    p3r_matches = all(bool(row["p3r_recorded_hash_match"]) for row in rows.values())

    return {
        "schema_version": "rd18-p3x-a1-control-parity-v1",
        "control_symbols": list(CONTROL_SYMBOLS),
        "lineage": [
            "RD16C raw family candidates and exits",
            "RD16D regime enrichment",
            "RD16E retained components",
            "RD16H EVIDENCE_COMPOSITE_EXPANSION",
            "RD16I COMPOSITE_ALPHA_V2 router",
            "RD16K STRONG_BULL_HOLD_96",
            "RD16L COMPOSITE_ALPHA_V3 registration",
        ],
        "control_hash_authority": (
            "RD16L manifest hashes plus complete regenerated column/value parity"
        ),
        "p3r_hash_erratum": {
            "classification": ("P3R_LEDGER_HASH_METADATA_UNREPRODUCIBLE_FROM_DOCUMENTED_CONTRACT"),
            "committed_erratum": ("data/research/rd18_p3x_a1/p3r-ledger-hash-erratum.json"),
            "all_p3r_recorded_hashes_match": p3r_matches,
            "upstream_p3r_modified": False,
            "strategy_or_market_data_changed": False,
        },
        "ledgers": rows,
        "passed": passed,
        "broad_c2_generation_authorized": False,
        "broad_block": ("PILOT_STATIC_ASSET_GATE_REQUIRES_PREREGISTERED_GENERALIZATION"),
    }


def save_control_outputs(
    output_dir: Path,
    ledgers: Mapping[str, pd.DataFrame],
    report: Mapping[str, object],
    diagnostics: Mapping[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in ledgers.items():
        frame.to_parquet(output_dir / f"control-{name}.parquet", index=False)
    write_json(output_dir / "control-parity-report.json", report)
    write_json(output_dir / "control-lineage-diagnostics.json", diagnostics)


def run_control_parity(repo_root: Path, output_dir: Path) -> dict[str, object]:
    ledgers, diagnostics = regenerate_control(repo_root)
    report = parity_report(repo_root, ledgers)
    save_control_outputs(output_dir, ledgers, report, diagnostics)
    return report


def reject_broad_generation(symbols: Sequence[str]) -> None:
    requested = set(symbols)
    if not requested.issubset(CONTROL_SYMBOLS):
        raise A1ControlError(
            "Broad C2 generation is blocked: RD16E ALLOWED_ASSETS is a pilot-only "
            "static gate and has no preregistered causal generalization."
        )


__all__ = [
    "A1ControlError",
    "parity_report",
    "regenerate_control",
    "reject_broad_generation",
    "run_control_parity",
    "save_control_outputs",
]
