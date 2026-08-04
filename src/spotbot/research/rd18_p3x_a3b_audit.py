from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.research.rd16c_common import dataframe_content_hash
from spotbot.research.rd16c_features import FeatureDataError, build_feature_frame
from spotbot.research.rd18_p3x_a1 import (
    SEALED_CUTOFF,
    load_json,
    sha256_path,
    symbol_to_pair,
)
from spotbot.research.rd18_p3x_a3a_membership import (
    inventory_maps,
    normalize_ranking,
)

STAGE: Final = "RD18_P3X_A3B_CONTROL_AND_COMPLETED_BAR_AUDIT_AUTHORIZATION"
PRIMARY_START: Final = pd.Timestamp("2019-04-01T00:00:00+00:00")
CUTOFF: Final = pd.Timestamp(SEALED_CUTOFF)
EXPECTED_DECISIONS: Final = 301
EXPECTED_MEMBERSHIP_ROWS: Final = 5_418
EXPECTED_CONTROL_ROWS: Final = {
    "candidates": 688,
    "evaluated": 688,
    "trades": 567,
}
CONTROL_SYMBOLS: Final = (
    "BTC/USDT",
    "ETH/USDT",
    "SOL/USDT",
    "LINK/USDT",
    "AVAX/USDT",
    "NEAR/USDT",
)
NAMED_OMISSIONS: Final = frozenset({"BCHSV-USDT", "PEPE-USDT"})
TIMEFRAMES: Final = ("1h", "4h", "1d", "1w")

EFFECTIVE_MEMBERSHIP_FIELDS: Final = (
    "universe_id",
    "decision_time",
    "effective_end",
    "original_pair",
    "original_canonical_asset_id",
    "original_rank",
    "top6",
    "effective_pair",
    "effective_canonical_asset_id",
    "effective_rank",
    "replacement_applied",
    "replacement_reason",
    "completed_bar_count",
)

OMISSION_FIELDS: Final = (
    "universe_id",
    "decision_time",
    "effective_end",
    "omitted_pair",
    "omitted_completed_bar_count",
    "replacement_pair",
    "replacement_canonical_asset_id",
    "replacement_rank",
    "replacement_ready",
    "omission_resolution_ready",
    "resolution_mode",
    "capacity_after_omission",
    "completed_bar_count",
    "reason",
)

HISTORICAL_FIELDS: Final = (
    "universe_id",
    "decision_time",
    "effective_end",
    "original_pair",
    "replacement_pair",
    "replacement_rank",
    "completed_bar_count",
    "resolved",
    "reason",
)

AUDIT_FIELDS: Final = (
    "audit_id",
    "universe_id",
    "decision_time",
    "effective_end",
    "original_pair",
    "effective_pair",
    "replacement_applied",
    "signal_close",
    "decision",
    "raw_signal_count",
    "selected_candidate_count",
    "selected_candidate_ids",
    "raw_family_ids",
    "rejection_reasons",
    "source_partition_audit_sha256",
    "source_partition_candidates_sha256",
    "source_1h_sha256",
)


class A3BAuditError(RuntimeError):
    """Raised when A3B evidence cannot be materialized causally."""


@dataclass(frozen=True, slots=True)
class PairEvidence:
    pair: str
    symbol: str
    completed_times: pd.DatetimeIndex
    audit_by_time: pd.DataFrame
    partition_audit_sha256: str
    partition_candidates_sha256: str
    source_1h_sha256: str


@dataclass(frozen=True, slots=True)
class ReplacementBuild:
    effective_membership: pd.DataFrame
    omission_readiness: pd.DataFrame
    historical_resolution: pd.DataFrame


def _times(values: pd.Series | pd.Index, *, name: str) -> pd.DatetimeIndex:
    parsed = pd.to_datetime(values, utc=True, errors="raise")
    index = pd.DatetimeIndex(parsed)
    if bool(index.isna().any()):
        raise A3BAuditError(f"{name} contains null timestamps")
    return index


def _bool_series(values: pd.Series, *, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    allowed = {"true", "false", "1", "0"}
    observed = set(normalized.dropna().unique())
    if not observed.issubset(allowed):
        raise A3BAuditError(f"{name} contains invalid booleans: {sorted(observed)}")
    return normalized.isin({"true", "1"})


def _join_unique(values: pd.Series) -> str:
    return "|".join(sorted({str(value) for value in values if str(value)}))


def _manifest_digest(files: list[dict[str, object]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(files, key=lambda item: str(item["path"])):
        digest.update(str(record["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(record["sha256"]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def deterministic_manifest(
    base: Path,
    names: list[str],
    *,
    schema_version: str,
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for name in sorted(names):
        path = base / name
        if not path.is_file():
            raise A3BAuditError(f"manifest output is missing: {path}")
        files.append(
            {
                "path": name,
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
            }
        )
    return {
        "schema_version": schema_version,
        "files": files,
        "deterministic_hash": _manifest_digest(files),
        "network_requests": 0,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


def load_memberships(input_dir: Path) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for universe in ("C2", "D2", "E2"):
        path = input_dir / f"{universe.lower()}-operational-membership.csv"
        if not path.is_file():
            raise A3BAuditError(f"membership input is missing: {path}")
        frame = pd.read_csv(path, low_memory=False)
        required = {
            "universe_id",
            "decision_time",
            "effective_end",
            "pair",
            "canonical_asset_id",
            "rank",
            "member",
            "top6",
        }
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise A3BAuditError(f"{universe} membership columns missing: {missing}")
        frame = frame.copy()
        frame["decision_time"] = _times(
            frame["decision_time"],
            name=f"{universe}.decision_time",
        )
        frame["effective_end"] = _times(
            frame["effective_end"],
            name=f"{universe}.effective_end",
        )
        frame["member"] = _bool_series(frame["member"], name=f"{universe}.member")
        frame["top6"] = _bool_series(frame["top6"], name=f"{universe}.top6")
        frame["rank"] = pd.to_numeric(frame["rank"], errors="raise").astype(int)
        if set(frame["universe_id"].astype(str).unique()) != {universe}:
            raise A3BAuditError(f"{universe} membership universe drift")
        if not bool(frame["member"].all()):
            raise A3BAuditError(f"{universe} membership contains nonmembers")
        if int(frame["decision_time"].nunique()) != EXPECTED_DECISIONS:
            raise A3BAuditError(f"{universe} decision count differs from 301")
        if len(frame) != EXPECTED_DECISIONS * 6:
            raise A3BAuditError(f"{universe} membership rows differ from 1806")
        if bool(frame.duplicated(["decision_time", "pair"]).any()):
            raise A3BAuditError(f"{universe} duplicate decision/pair rows")
        parts.append(frame)
    combined = pd.concat(parts, ignore_index=True)
    if len(combined) != EXPECTED_MEMBERSHIP_ROWS:
        raise A3BAuditError("combined membership rows differ from 5418")
    return combined.sort_values(
        ["universe_id", "decision_time", "rank", "pair"],
        kind="stable",
    ).reset_index(drop=True)


def build_full_rankings(repo: Path) -> pd.DataFrame:
    inventory = pd.read_csv(
        repo / "data/research/rd18_p1r2/raw-inventory-classification.csv",
        low_memory=False,
    )
    mapping, c2_pairs, d2_pairs = inventory_maps(inventory)
    c2_source = pd.read_csv(
        repo / "data/research/rd18_p1r2/corrected-weekly-rankings.csv",
        low_memory=False,
    )
    c2 = normalize_ranking(
        c2_source,
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2_pairs,
        recompute_rank=False,
        include_warmup=True,
    )
    c2 = c2.loc[(c2["decision_time"] >= PRIMARY_START) & (c2["decision_time"] < CUTOFF)].copy()
    d2 = normalize_ranking(
        c2_source,
        mapping=mapping,
        universe_id="D2",
        allowed_pairs=d2_pairs,
        recompute_rank=True,
    )
    e2_source = pd.read_csv(
        repo / "data/research/rd18_p2u2/weekly-e10-ranking.csv",
        low_memory=False,
    )
    e2 = normalize_ranking(
        e2_source,
        mapping=mapping,
        universe_id="E2",
        allowed_pairs=c2_pairs,
        recompute_rank=False,
    )
    rankings = pd.concat([c2, d2, e2], ignore_index=True)
    rankings["decision_time"] = _times(
        rankings["decision_time"],
        name="ranking.decision_time",
    )
    if set(rankings["universe_id"].astype(str).unique()) != {"C2", "D2", "E2"}:
        raise A3BAuditError("ranking universe set differs")
    for universe in ("C2", "D2", "E2"):
        count = int(
            rankings.loc[
                rankings["universe_id"] == universe,
                "decision_time",
            ].nunique()
        )
        if count != EXPECTED_DECISIONS:
            raise A3BAuditError(f"{universe} full ranking decisions differ: {count}")
    if bool(rankings.duplicated(["universe_id", "decision_time", "pair"]).any()):
        raise A3BAuditError("full rankings contain duplicate decision/pair rows")
    return rankings.sort_values(
        ["universe_id", "decision_time", "rank", "canonical_asset_id"],
        kind="stable",
    ).reset_index(drop=True)


def generated_pairs(a2_runtime: Path) -> frozenset[str]:
    summary_path = a2_runtime / "symbol-generation-summary.csv"
    report_path = a2_runtime / "rd18-p3x-a2-runtime-report-v1.json"
    if not summary_path.is_file() or not report_path.is_file():
        raise A3BAuditError("A2 summary or report is missing")
    report = load_json(report_path)
    if report.get("passed") is not True:
        raise A3BAuditError("A2 report is not passed")
    if report.get("generator_scope") != "PRE_ROUTER_SIGNAL_CANDIDATES":
        raise A3BAuditError("A2 generator scope drifted")
    if report.get("sealed_cutoff") != CUTOFF.isoformat():
        raise A3BAuditError("A2 sealed cutoff drifted")
    summary = pd.read_csv(summary_path, low_memory=False)
    generated = frozenset(
        summary.loc[
            summary["generation_status"].astype(str) == "GENERATED",
            "pair",
        ]
        .astype(str)
        .tolist()
    )
    if len(generated) != 339:
        raise A3BAuditError(f"expected 339 generated pairs, found {len(generated)}")
    return generated


def pair_symbol_map(a1_runtime: Path) -> dict[str, str]:
    path = a1_runtime / "full-c2-hourly-acquisition-plan.csv"
    if not path.is_file():
        raise A3BAuditError(f"A1 plan is missing: {path}")
    plan = pd.read_csv(path, low_memory=False)
    required = {"pair", "symbol"}
    missing = sorted(required.difference(plan.columns))
    if missing:
        raise A3BAuditError(f"A1 plan columns missing: {missing}")
    if bool(plan["pair"].duplicated().any()):
        raise A3BAuditError("A1 plan pairs are duplicated")
    mapping = dict(
        zip(
            plan["pair"].astype(str),
            plan["symbol"].astype(str),
            strict=True,
        )
    )
    for pair, symbol in mapping.items():
        if symbol_to_pair(symbol) != pair:
            raise A3BAuditError(f"A1 plan pair/symbol mismatch: {pair}, {symbol}")
    return mapping


class EvidenceCache:
    def __init__(
        self,
        *,
        repo: Path,
        a1_runtime: Path,
        a2_runtime: Path,
        generated: frozenset[str],
    ) -> None:
        self.repo = repo
        self.a2_runtime = a2_runtime
        self.generated = generated
        self.symbol_by_pair = pair_symbol_map(a1_runtime)
        self.store = ParquetCandleStore(repo / "data/raw/rd16b")
        self._cache: dict[str, PairEvidence] = {}

    def _load(self, pair: str) -> PairEvidence:
        if pair not in self.generated:
            raise A3BAuditError(f"pair lacks an A2 GENERATED partition: {pair}")
        symbol = self.symbol_by_pair.get(pair)
        if symbol is None:
            raise A3BAuditError(f"pair lacks an A1 symbol mapping: {pair}")
        frames = {
            timeframe: self.store.load(
                exchange_id="kucoin",
                symbol=symbol,
                timeframe=timeframe,
                verify_integrity=True,
            )
            for timeframe in TIMEFRAMES
        }
        for timeframe, frame in frames.items():
            timestamps = _times(
                frame["timestamp"],
                name=f"{pair}.{timeframe}.timestamp",
            )
            if bool((timestamps > CUTOFF).any()):
                raise A3BAuditError(f"post-2024 source row detected: {pair} {timeframe}")
        try:
            feature_frame = build_feature_frame(frames, symbol=symbol)
        except FeatureDataError as exc:
            raise A3BAuditError(f"{pair} cannot build causal features: {exc}") from exc
        completed = _times(
            feature_frame["timestamp"],
            name=f"{pair}.feature.timestamp",
        )
        completed = completed[(completed >= PRIMARY_START) & (completed < CUTOFF)].sort_values()
        if completed.has_duplicates:
            raise A3BAuditError(f"{pair} causal feature times are duplicated")
        if len(completed) == 0:
            raise A3BAuditError(f"{pair} has no completed causal feature bars")

        partition = self.a2_runtime / "partitions" / pair
        audit_path = partition / "audit.parquet"
        candidates_path = partition / "candidates.parquet"
        summary_path = partition / "summary.json"
        if not audit_path.is_file() or not candidates_path.is_file() or not summary_path.is_file():
            raise A3BAuditError(f"A2 partition files are incomplete: {pair}")
        summary = load_json(summary_path)
        if summary.get("generation_status") != "GENERATED":
            raise A3BAuditError(f"A2 partition is not GENERATED: {pair}")

        audit = pd.read_parquet(audit_path)
        candidates = pd.read_parquet(candidates_path)
        if audit.empty:
            aggregated = pd.DataFrame(
                columns=[
                    "signal_close",
                    "raw_signal_count",
                    "selected_candidate_count",
                    "selected_candidate_ids",
                    "raw_family_ids",
                    "rejection_reasons",
                ]
            )
        else:
            required = {
                "candidate_id",
                "family_id",
                "signal_close",
                "selected_pre_router",
                "rejection_reason",
            }
            missing = sorted(required.difference(audit.columns))
            if missing:
                raise A3BAuditError(f"{pair} A2 audit columns missing: {missing}")
            audit = audit.copy()
            audit["signal_close"] = _times(
                audit["signal_close"],
                name=f"{pair}.audit.signal_close",
            )
            audit["selected_pre_router"] = _bool_series(
                audit["selected_pre_router"],
                name=f"{pair}.audit.selected_pre_router",
            )
            if bool((audit["signal_close"] >= CUTOFF).any()):
                raise A3BAuditError(f"{pair} A2 audit crosses the sealed cutoff")
            feature_set = set(completed)
            audit_set = set(pd.DatetimeIndex(audit["signal_close"]))
            if not audit_set.issubset(feature_set):
                raise A3BAuditError(f"{pair} A2 audit contains nonfeature timestamps")
            selected_ids = set(
                audit.loc[
                    audit["selected_pre_router"],
                    "candidate_id",
                ].astype(str)
            )
            candidate_ids = set(candidates["candidate_id"].astype(str))
            if selected_ids != candidate_ids:
                raise A3BAuditError(f"{pair} A2 selected audit/candidate IDs differ")
            grouped = audit.groupby("signal_close", sort=True)
            aggregated = grouped.agg(
                raw_signal_count=("candidate_id", "size"),
                selected_candidate_count=("selected_pre_router", "sum"),
                selected_candidate_ids=(
                    "candidate_id",
                    lambda values: _join_unique(
                        audit.loc[
                            values.index,
                            :,
                        ].loc[
                            lambda frame: frame["selected_pre_router"],
                            "candidate_id",
                        ]
                    ),
                ),
                raw_family_ids=("family_id", _join_unique),
                rejection_reasons=("rejection_reason", _join_unique),
            ).reset_index()
            aggregated["selected_candidate_count"] = aggregated["selected_candidate_count"].astype(
                int
            )

        source_1h = self.store.dataset_path(
            exchange_id="kucoin",
            symbol=symbol,
            timeframe="1h",
        )
        evidence = PairEvidence(
            pair=pair,
            symbol=symbol,
            completed_times=completed,
            audit_by_time=aggregated,
            partition_audit_sha256=sha256_path(audit_path),
            partition_candidates_sha256=sha256_path(candidates_path),
            source_1h_sha256=sha256_path(source_1h),
        )
        return evidence

    def get(self, pair: str) -> PairEvidence:
        evidence = self._cache.get(pair)
        if evidence is None:
            evidence = self._load(pair)
            self._cache[pair] = evidence
        return evidence

    def interval_count(
        self,
        pair: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> int:
        times = self.get(pair).completed_times
        left = int(times.searchsorted(start, side="left"))
        right = int(times.searchsorted(end, side="left"))
        return max(0, right - left)

    def interval_times(
        self,
        pair: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> pd.DatetimeIndex:
        times = self.get(pair).completed_times
        left = int(times.searchsorted(start, side="left"))
        right = int(times.searchsorted(end, side="left"))
        return times[left:right]


def _ranked_candidates(
    rankings: pd.DataFrame,
    *,
    universe: str,
    decision: pd.Timestamp,
) -> pd.DataFrame:
    selected = rankings.loc[
        (rankings["universe_id"].astype(str) == universe) & (rankings["decision_time"] == decision)
    ].copy()
    if selected.empty:
        raise A3BAuditError(f"ranking is empty: {universe} {decision.isoformat()}")
    return selected.sort_values(
        ["rank", "canonical_asset_id"],
        kind="stable",
    )


def _replacement_candidate(
    ranked: pd.DataFrame,
    *,
    excluded: set[str],
    generated: frozenset[str],
    cache: EvidenceCache,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[str, str, int, int] | None:
    for row in ranked.itertuples(index=False):
        pair = str(row.pair)
        if pair in excluded or pair not in generated:
            continue
        count = cache.interval_count(pair, start, end)
        if count <= 0:
            continue
        return (
            pair,
            str(row.canonical_asset_id),
            int(row.rank),
            count,
        )
    return None


def build_replacements(
    memberships: pd.DataFrame,
    rankings: pd.DataFrame,
    *,
    generated: frozenset[str],
    cache: EvidenceCache,
) -> ReplacementBuild:
    effective_rows: list[dict[str, object]] = []
    omission_rows: list[dict[str, object]] = []
    historical_rows: list[dict[str, object]] = []

    grouped = memberships.groupby(
        ["universe_id", "decision_time"],
        sort=True,
    )
    for (raw_universe, raw_decision), group in grouped:
        universe = str(raw_universe)
        decision = pd.Timestamp(raw_decision)
        effective_end_values = pd.DatetimeIndex(group["effective_end"].unique())
        if len(effective_end_values) != 1:
            raise A3BAuditError(f"{universe} {decision.isoformat()} has inconsistent effective_end")
        effective_end = pd.Timestamp(effective_end_values[0])
        ranked = _ranked_candidates(
            rankings,
            universe=universe,
            decision=decision,
        )
        original_members = set(group["pair"].astype(str))

        # LOAO readiness means deterministic omission resolution.  Prefer the
        # highest-ranked interval-ready GENERATED nonmember.  If none exists,
        # the counterfactual remains executable with one fewer member.
        ranked_nonmembers = ranked.loc[~ranked["pair"].astype(str).isin(original_members)].copy()
        generated_nonmembers = ranked_nonmembers.loc[
            ranked_nonmembers["pair"].astype(str).isin(generated)
        ].copy()
        for member in group.sort_values(["rank", "pair"], kind="stable").itertuples(index=False):
            omitted_pair = str(member.pair)
            omitted_count = 0
            if omitted_pair in generated:
                omitted_count = cache.interval_count(
                    omitted_pair,
                    decision,
                    effective_end,
                )
            candidate = _replacement_candidate(
                ranked,
                excluded=original_members,
                generated=generated,
                cache=cache,
                start=decision,
                end=effective_end,
            )
            if candidate is not None:
                (
                    replacement_pair,
                    replacement_id,
                    replacement_rank,
                    bar_count,
                ) = candidate
                replacement_ready = True
                resolution_mode = "REPLACEMENT"
                capacity_after_omission = len(original_members)
                reason = "NEXT_RANKED_INTERVAL_READY_GENERATED_NONMEMBER"
            else:
                replacement_pair = ""
                replacement_id = ""
                replacement_rank = 0
                bar_count = 0
                replacement_ready = False
                capacity_after_omission = max(0, len(original_members) - 1)
                if omitted_count == 0:
                    resolution_mode = "EMPTY_DOMAIN_CAPACITY_REDUCTION"
                    reason = "NO_COMPLETED_BAR_DOMAIN_CAPACITY_REDUCTION_READY"
                elif ranked_nonmembers.empty:
                    resolution_mode = "STRUCTURAL_CAPACITY_REDUCTION"
                    reason = "NO_RANKED_NONMEMBER_CAPACITY_REDUCTION_READY"
                elif generated_nonmembers.empty:
                    resolution_mode = "STRUCTURAL_CAPACITY_REDUCTION"
                    reason = "NO_GENERATED_NONMEMBER_CAPACITY_REDUCTION_READY"
                else:
                    resolution_mode = "INTERVAL_CAPACITY_REDUCTION"
                    reason = "NO_INTERVAL_READY_GENERATED_NONMEMBER_CAPACITY_REDUCTION_READY"
            omission_rows.append(
                {
                    "universe_id": universe,
                    "decision_time": decision,
                    "effective_end": effective_end,
                    "omitted_pair": omitted_pair,
                    "omitted_completed_bar_count": omitted_count,
                    "replacement_pair": replacement_pair,
                    "replacement_canonical_asset_id": replacement_id,
                    "replacement_rank": replacement_rank,
                    "replacement_ready": replacement_ready,
                    "omission_resolution_ready": True,
                    "resolution_mode": resolution_mode,
                    "capacity_after_omission": capacity_after_omission,
                    "completed_bar_count": bar_count,
                    "reason": reason,
                }
            )

        # Operational repair replaces only members without a GENERATED partition.
        # A generated member with zero completed causal bars has an empty audit
        # domain for the interval; zero bars are not evidence of unavailable data.
        chosen: set[str] = set()
        ordered = group.sort_values(["rank", "pair"], kind="stable")
        for member in ordered.itertuples(index=False):
            original_pair = str(member.pair)
            if original_pair in generated:
                effective_pair = original_pair
                effective_id = str(member.canonical_asset_id)
                effective_rank = int(member.rank)
                replacement_applied = False
                bar_count = cache.interval_count(
                    original_pair,
                    decision,
                    effective_end,
                )
                replacement_reason = (
                    "ORIGINAL_INTERVAL_READY"
                    if bar_count > 0
                    else "ORIGINAL_GENERATED_EMPTY_COMPLETED_BAR_DOMAIN"
                )
            else:
                candidate = _replacement_candidate(
                    ranked,
                    excluded=original_members | chosen,
                    generated=generated,
                    cache=cache,
                    start=decision,
                    end=effective_end,
                )
                if candidate is None:
                    raise A3BAuditError(
                        "no deterministic operational replacement for "
                        f"{universe} {decision.isoformat()} {original_pair}"
                    )
                effective_pair, effective_id, effective_rank, bar_count = candidate
                replacement_applied = True
                replacement_reason = "ORIGINAL_NOT_GENERATED"
            if effective_pair in chosen:
                raise A3BAuditError(
                    f"duplicate effective pair: {universe} {decision} {effective_pair}"
                )
            chosen.add(effective_pair)
            effective_rows.append(
                {
                    "universe_id": universe,
                    "decision_time": decision,
                    "effective_end": effective_end,
                    "original_pair": original_pair,
                    "original_canonical_asset_id": str(member.canonical_asset_id),
                    "original_rank": int(member.rank),
                    "top6": bool(member.top6),
                    "effective_pair": effective_pair,
                    "effective_canonical_asset_id": effective_id,
                    "effective_rank": effective_rank,
                    "replacement_applied": replacement_applied,
                    "replacement_reason": replacement_reason,
                    "completed_bar_count": bar_count,
                }
            )
            if original_pair not in generated or original_pair == "BCHSV-USDT":
                historical_rows.append(
                    {
                        "universe_id": universe,
                        "decision_time": decision,
                        "effective_end": effective_end,
                        "original_pair": original_pair,
                        "replacement_pair": effective_pair,
                        "replacement_rank": effective_rank,
                        "completed_bar_count": bar_count,
                        "resolved": bool(
                            replacement_applied and effective_pair in generated and bar_count > 0
                        ),
                        "reason": replacement_reason,
                    }
                )

    effective = pd.DataFrame.from_records(
        effective_rows,
        columns=EFFECTIVE_MEMBERSHIP_FIELDS,
    )
    omissions = pd.DataFrame.from_records(
        omission_rows,
        columns=OMISSION_FIELDS,
    )
    historical = pd.DataFrame.from_records(
        historical_rows,
        columns=HISTORICAL_FIELDS,
    )

    if len(effective) != EXPECTED_MEMBERSHIP_ROWS:
        raise A3BAuditError("effective membership rows differ from 5418")
    if len(omissions) != EXPECTED_MEMBERSHIP_ROWS:
        raise A3BAuditError("omission readiness rows differ from 5418")
    if not bool(omissions["omission_resolution_ready"].astype(bool).all()):
        raise A3BAuditError("omission ledger contains unresolved rows")
    replacement_rows = omissions["resolution_mode"].astype(str) == "REPLACEMENT"
    if bool((replacement_rows != omissions["replacement_ready"].astype(bool)).any()):
        raise A3BAuditError("replacement readiness and resolution mode disagree")
    if bool(effective["completed_bar_count"].astype(int).lt(0).any()):
        raise A3BAuditError("effective membership contains negative bar counts")
    if not set(effective["effective_pair"].astype(str)).issubset(generated):
        raise A3BAuditError("effective membership contains a non-GENERATED pair")
    if bool(effective.duplicated(["universe_id", "decision_time", "effective_pair"]).any()):
        raise A3BAuditError("effective membership contains duplicate effective pairs")
    return ReplacementBuild(
        effective_membership=effective.sort_values(
            ["universe_id", "decision_time", "original_rank", "original_pair"],
            kind="stable",
        ).reset_index(drop=True),
        omission_readiness=omissions.sort_values(
            ["universe_id", "decision_time", "omitted_pair"],
            kind="stable",
        ).reset_index(drop=True),
        historical_resolution=historical.sort_values(
            ["universe_id", "decision_time", "original_pair"],
            kind="stable",
        ).reset_index(drop=True)
        if not historical.empty
        else historical,
    )


def build_completed_bar_audit(
    effective_membership: pd.DataFrame,
    *,
    cache: EvidenceCache,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for row in effective_membership.itertuples(index=False):
        start = pd.Timestamp(row.decision_time)
        end = pd.Timestamp(row.effective_end)
        pair = str(row.effective_pair)
        evidence = cache.get(pair)
        times = cache.interval_times(pair, start, end)
        if len(times) != int(row.completed_bar_count):
            raise A3BAuditError(f"{pair} interval count changed during audit")
        base = pd.DataFrame({"signal_close": times})
        aggregate = evidence.audit_by_time.copy()
        if not aggregate.empty:
            aggregate["signal_close"] = _times(
                aggregate["signal_close"],
                name=f"{pair}.aggregate.signal_close",
            )
        merged = base.merge(
            aggregate,
            on="signal_close",
            how="left",
            validate="one_to_one",
            sort=False,
        )
        merged["raw_signal_count"] = merged["raw_signal_count"].fillna(0).astype(int)
        merged["selected_candidate_count"] = (
            merged["selected_candidate_count"].fillna(0).astype(int)
        )
        for column in (
            "selected_candidate_ids",
            "raw_family_ids",
            "rejection_reasons",
        ):
            merged[column] = merged[column].fillna("").astype(str)
        merged["decision"] = (
            merged["selected_candidate_count"].gt(0).map({True: "SIGNAL", False: "NO_SIGNAL"})
        )
        decision_iso = start.isoformat()
        merged["audit_id"] = [
            (
                f"A3B::{row.universe_id}::{decision_iso}::"
                f"{row.original_pair}::{pair}::{pd.Timestamp(value).isoformat()}"
            )
            for value in merged["signal_close"]
        ]
        merged["universe_id"] = str(row.universe_id)
        merged["decision_time"] = start
        merged["effective_end"] = end
        merged["original_pair"] = str(row.original_pair)
        merged["effective_pair"] = pair
        merged["replacement_applied"] = bool(row.replacement_applied)
        merged["source_partition_audit_sha256"] = evidence.partition_audit_sha256
        merged["source_partition_candidates_sha256"] = evidence.partition_candidates_sha256
        merged["source_1h_sha256"] = evidence.source_1h_sha256
        parts.append(merged.loc[:, list(AUDIT_FIELDS)])
    audit = pd.concat(parts, ignore_index=True)
    if len(audit) != int(effective_membership["completed_bar_count"].astype(int).sum()):
        raise A3BAuditError("dense audit row count differs from interval denominator")
    if bool(audit["audit_id"].duplicated().any()):
        raise A3BAuditError("dense audit IDs are duplicated")
    if bool(
        audit.duplicated(
            [
                "universe_id",
                "decision_time",
                "original_pair",
                "signal_close",
            ]
        ).any()
    ):
        raise A3BAuditError("dense audit domain keys are duplicated")
    if set(audit["decision"].astype(str).unique()) - {"SIGNAL", "NO_SIGNAL"}:
        raise A3BAuditError("dense audit contains unsupported decisions")
    if bool((_times(audit["signal_close"], name="audit.signal_close") >= CUTOFF).any()):
        raise A3BAuditError("dense audit crosses the sealed cutoff")
    return audit.sort_values(
        [
            "universe_id",
            "decision_time",
            "original_pair",
            "signal_close",
        ],
        kind="stable",
    ).reset_index(drop=True)


def control_parity_evidence(
    repo: Path,
    a1_runtime: Path,
) -> dict[str, dict[str, object]]:
    control_dir = a1_runtime / "control"
    report_path = control_dir / "control-parity-report.json"
    if not report_path.is_file():
        raise A3BAuditError(f"A1 control report is missing: {report_path}")
    report = load_json(report_path)
    if report.get("schema_version") != "rd18-p3x-a1-control-parity-v1":
        raise A3BAuditError("A1 control schema drifted")
    if report.get("passed") is not True:
        raise A3BAuditError("A1 control parity is not passed")
    if tuple(report.get("control_symbols", [])) != CONTROL_SYMBOLS:
        raise A3BAuditError("A1 control symbol set drifted")
    if report.get("control_hash_authority") != (
        "RD16L manifest hashes plus complete regenerated column/value parity"
    ):
        raise A3BAuditError("A1 control hash authority drifted")
    erratum = report.get("p3r_hash_erratum")
    if not isinstance(erratum, dict):
        raise A3BAuditError("A1 control P3R erratum is missing")
    if erratum.get("classification") != (
        "P3R_LEDGER_HASH_METADATA_UNREPRODUCIBLE_FROM_DOCUMENTED_CONTRACT"
    ):
        raise A3BAuditError("A1 P3R erratum classification drifted")
    if erratum.get("strategy_or_market_data_changed") is not False:
        raise A3BAuditError("A1 P3R erratum indicates strategy/data change")
    if erratum.get("upstream_p3r_modified") is not False:
        raise A3BAuditError("A1 P3R erratum indicates upstream mutation")
    committed_erratum = repo / str(erratum.get("committed_erratum", ""))
    if not committed_erratum.is_file():
        raise A3BAuditError("committed P3R hash erratum is missing")

    raw_ledgers = report.get("ledgers")
    if not isinstance(raw_ledgers, dict):
        raise A3BAuditError("A1 control ledger evidence is missing")
    result: dict[str, dict[str, object]] = {}
    for name in ("candidates", "evaluated", "trades"):
        raw = raw_ledgers.get(name)
        if not isinstance(raw, dict):
            raise A3BAuditError(f"A1 control evidence missing: {name}")
        path = control_dir / f"control-{name}.parquet"
        if not path.is_file():
            raise A3BAuditError(f"A1 regenerated control ledger missing: {path}")
        frame = pd.read_parquet(path)
        content_hash = dataframe_content_hash(frame)
        expected_rows = EXPECTED_CONTROL_ROWS[name]
        passed = all(
            (
                len(frame) == expected_rows,
                raw.get("actual_rows") == expected_rows,
                raw.get("registered_expected_rows") == expected_rows,
                raw.get("row_count_match") is True,
                raw.get("column_and_value_parity") is True,
                raw.get("local_content_hash_match") is True,
                raw.get("rd16l_manifest_content_hash_match") is True,
                raw.get("registered_content_hash_match") is True,
                raw.get("registered_hash_authority") == "RD16L_LOCAL_LEDGER_MANIFEST",
                content_hash == raw.get("actual_local_content_hash"),
                content_hash == raw.get("rd16l_manifest_content_hash"),
            )
        )
        result[name] = {
            "schema_version": f"rd18-p3x-a3b-legacy-control-{name}-parity-v1",
            "ledger": name,
            "passed": passed,
            "rows": len(frame),
            "expected_rows": expected_rows,
            "authoritative_content_sha256": content_hash,
            "hash_authority": "RD16L_LOCAL_LEDGER_MANIFEST",
            "column_and_value_parity": raw.get("column_and_value_parity") is True,
            "p3r_recorded_content_sha256": raw.get("p3r_recorded_content_hash"),
            "p3r_recorded_hash_match": raw.get("p3r_recorded_hash_match") is True,
            "p3r_hash_erratum_applied": True,
            "control_only_replay_previously_executed": True,
            "strategy_replay_executed": False,
            "return_calculation_executed": False,
            "source_file_sha256": sha256_path(path),
        }
        if not passed:
            raise A3BAuditError(f"A1 authoritative control parity failed: {name}")
    return result


def coverage_summary(
    effective_membership: pd.DataFrame,
    audit: pd.DataFrame,
) -> dict[str, object]:
    expected = int(effective_membership["completed_bar_count"].astype(int).sum())
    observed = len(audit)
    coverage = observed / expected if expected else 0.0
    return {
        "schema_version": "rd18-p3x-a3b-selected-member-coverage-v1",
        "membership_slots": len(effective_membership),
        "expected_completed_bar_decisions": expected,
        "materialized_completed_bar_decisions": observed,
        "member_evaluation_audit_coverage": coverage,
        "signal_decisions": int((audit["decision"].astype(str) == "SIGNAL").sum()),
        "no_signal_decisions": int((audit["decision"].astype(str) == "NO_SIGNAL").sum()),
        "audit_content_sha256": dataframe_content_hash(audit),
        "dense_signal_or_no_signal_domain": True,
        "passed": bool(expected > 0 and observed == expected and coverage == 1.0),
    }


def evidence_decision(
    *,
    controls: Mapping[str, Mapping[str, object]],
    coverage: Mapping[str, object],
    historical_complete: bool,
    omission_ready: bool,
    named_omission_replacements_ready: bool,
    effective_membership: pd.DataFrame,
) -> dict[str, object]:
    checks = {
        "legacy_control_candidate_parity": (controls["candidates"].get("passed") is True),
        "legacy_control_evaluated_parity": (controls["evaluated"].get("passed") is True),
        "legacy_control_trade_parity": (controls["trades"].get("passed") is True),
        "member_evaluation_audit_coverage_1": (
            float(coverage.get("member_evaluation_audit_coverage", 0.0)) == 1.0
        ),
        "historical_gap_resolution_complete": historical_complete,
        "omission_resolution_ready": omission_ready,
        "named_omission_actual_replacements_ready": (named_omission_replacements_ready),
        "effective_membership_rows_5418": (len(effective_membership) == EXPECTED_MEMBERSHIP_ROWS),
        "effective_bar_counts_nonnegative": bool(
            effective_membership["completed_bar_count"].astype(int).ge(0).all()
        ),
        "effective_audit_domain_nonempty": bool(
            effective_membership["completed_bar_count"].astype(int).sum() > 0
        ),
        "no_strategy_replay": True,
        "no_portfolio_routing": True,
        "no_exit_simulation": True,
        "no_return_calculation": True,
        "no_post_2024_access": True,
        "no_network_requests": True,
        "production_not_authorized": True,
    }
    passed = all(checks.values())
    return {
        "schema_version": "rd18-p3x-a3b-authorization-decision-v1",
        "stage": STAGE,
        "decision": (
            "RD18_P3X_A3B_EVIDENCE_COMPLETE" if passed else "RD18_P3X_A3B_EVIDENCE_INCOMPLETE"
        ),
        "passed": passed,
        "authorized_for_a3_reauthorization": passed,
        "replay_authorized": False,
        "next_stage": (
            "RD18_P3X_A3_REAUTHORIZATION_REVIEW" if passed else "RD18_P3X_A3B_REMEDIATION"
        ),
        "checks": dict(sorted(checks.items())),
        "network_requests": 0,
        "control_only_replay_previously_executed": True,
        "strategy_replay_executed": False,
        "portfolio_routing_executed": False,
        "exit_simulation_executed": False,
        "return_calculation_executed": False,
        "post_2024_accessed": False,
        "production_authorized": False,
    }


__all__ = [
    "A3BAuditError",
    "AUDIT_FIELDS",
    "CUTOFF",
    "EFFECTIVE_MEMBERSHIP_FIELDS",
    "EXPECTED_CONTROL_ROWS",
    "EXPECTED_DECISIONS",
    "EXPECTED_MEMBERSHIP_ROWS",
    "HISTORICAL_FIELDS",
    "EvidenceCache",
    "NAMED_OMISSIONS",
    "OMISSION_FIELDS",
    "PRIMARY_START",
    "ReplacementBuild",
    "STAGE",
    "build_completed_bar_audit",
    "build_full_rankings",
    "build_replacements",
    "control_parity_evidence",
    "coverage_summary",
    "deterministic_manifest",
    "evidence_decision",
    "generated_pairs",
    "load_memberships",
]
