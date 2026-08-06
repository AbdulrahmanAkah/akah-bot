"""RD18-P3E LOYO and LOAO sensitivity helpers."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pandas as pd

from spotbot.data.store import ParquetCandleStore
from spotbot.research.rd16c_features import FeatureDataError, build_feature_frame
from spotbot.research.rd16d_metrics import build_equity_curve, performance_metrics
from spotbot.research.rd18_p3e_cash_feasibility import (
    CashRouteResult,
    route_cash_feasible_candidates,
)
from spotbot.research.rd18_p3e_replay import (
    PRIMARY_START,
    SEALED_CUTOFF,
    load_pair_candidates,
    normalize_hourly_bars,
    primary_timeline,
)

UNIVERSE_IDS: Final = ("C2", "D2", "E2")
COST_MULTIPLIERS: Final = (1.0, 2.0)
OMITTED_YEARS: Final = (2019, 2020, 2021, 2022, 2023, 2024)
NAMED_OMISSIONS: Final = ("BCHSV-USDT", "PEPE-USDT")
EXPECTED_DECISIONS: Final = 301
BASE_MEMBERS_PER_DECISION: Final = 6
TIMEFRAMES: Final = ("1h", "4h", "1d", "1w")


class SensitivityError(RuntimeError):
    """Raised when sensitivity evidence cannot be produced safely."""


@dataclass(frozen=True, slots=True)
class CounterfactualMembership:
    universe_id: str
    omitted_pair: str
    membership: pd.DataFrame
    resolution_rows: list[dict[str, object]]
    affected_decisions: int
    replacement_decisions: int
    capacity_reduction_decisions: int
    membership_sha256: str


@dataclass(frozen=True, slots=True)
class SensitivityExecution:
    record: dict[str, object]
    route: CashRouteResult


def _timestamp(value: object) -> pd.Timestamp:
    parsed = pd.Timestamp(cast(Any, value))
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def _finite(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise SensitivityError(f"{name} cannot be boolean")
    try:
        result = float(cast(str | int | float, value))
    except (TypeError, ValueError) as exc:
        raise SensitivityError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise SensitivityError(f"{name} must be finite")
    return result


def _boolean_series(values: pd.Series, *, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.astype(bool)
    normalized = values.astype(str).str.strip().str.lower()
    allowed = {"true", "false", "1", "0"}
    observed = set(normalized.dropna().unique())
    if not observed.issubset(allowed):
        raise SensitivityError(f"{name} contains invalid booleans: {sorted(observed)}")
    return normalized.isin({"true", "1"})


def frame_content_hash(
    frame: pd.DataFrame,
    *,
    columns: Sequence[str],
    sort_by: Sequence[str],
) -> str:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise SensitivityError(f"hash columns missing: {missing}")
    working = frame.loc[:, list(columns)].copy()
    for column in working.columns:
        if pd.api.types.is_datetime64_any_dtype(working[column]):
            working[column] = pd.to_datetime(
                working[column],
                utc=True,
                errors="raise",
            ).map(lambda value: value.isoformat())
        elif pd.api.types.is_bool_dtype(working[column]):
            working[column] = working[column].astype(bool)
    working = working.sort_values(
        list(sort_by),
        kind="stable",
    ).reset_index(drop=True)
    payload = working.to_json(
        orient="records",
        date_format="iso",
        double_precision=15,
        force_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_base_membership(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
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
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise SensitivityError(f"effective membership columns missing: {missing}")
    working = frame.copy()
    working["universe_id"] = working["universe_id"].astype(str)
    for column in ("decision_time", "effective_end"):
        working[column] = pd.to_datetime(
            working[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
    for column in ("original_pair", "effective_pair"):
        working[column] = working[column].astype(str)
    for column in (
        "original_rank",
        "effective_rank",
        "completed_bar_count",
    ):
        working[column] = pd.to_numeric(
            working[column],
            errors="raise",
        ).astype(int)
    working["replacement_applied"] = _boolean_series(
        working["replacement_applied"],
        name="replacement_applied",
    )
    working["top6"] = _boolean_series(
        working["top6"],
        name="top6",
    )
    if set(working["universe_id"].unique()) != set(UNIVERSE_IDS):
        raise SensitivityError("membership universe set drifted")
    if len(working) != 5418:
        raise SensitivityError(f"effective membership rows drifted: {len(working)}")
    if bool(working.duplicated(["universe_id", "decision_time", "effective_pair"]).any()):
        raise SensitivityError("effective membership contains duplicate effective pairs")
    for universe_id in UNIVERSE_IDS:
        selected = working.loc[working["universe_id"] == universe_id]
        if selected["decision_time"].nunique() != EXPECTED_DECISIONS:
            raise SensitivityError(f"{universe_id} membership decision count drifted")
        sizes = selected.groupby("decision_time", sort=True).size()
        if not bool((sizes == BASE_MEMBERS_PER_DECISION).all()):
            raise SensitivityError(f"{universe_id} base membership is not fixed at six")
    return working.sort_values(
        [
            "universe_id",
            "decision_time",
            "effective_rank",
            "effective_pair",
        ],
        kind="stable",
    ).reset_index(drop=True)


def normalize_omission_readiness(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "universe_id",
        "decision_time",
        "effective_end",
        "omitted_pair",
        "replacement_pair",
        "replacement_canonical_asset_id",
        "replacement_rank",
        "replacement_ready",
        "omission_resolution_ready",
        "resolution_mode",
        "capacity_after_omission",
        "completed_bar_count",
        "reason",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise SensitivityError(f"omission readiness columns missing: {missing}")
    working = frame.copy()
    working["universe_id"] = working["universe_id"].astype(str)
    for column in ("decision_time", "effective_end"):
        working[column] = pd.to_datetime(
            working[column],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
    for column in (
        "omitted_pair",
        "replacement_pair",
        "replacement_canonical_asset_id",
        "resolution_mode",
        "reason",
    ):
        working[column] = working[column].fillna("").astype(str)
    for column in (
        "replacement_rank",
        "capacity_after_omission",
        "completed_bar_count",
    ):
        working[column] = pd.to_numeric(
            working[column],
            errors="raise",
        ).astype(int)
    for column in (
        "replacement_ready",
        "omission_resolution_ready",
    ):
        working[column] = _boolean_series(
            working[column],
            name=column,
        )
    if len(working) != 5418:
        raise SensitivityError(f"omission readiness rows drifted: {len(working)}")
    if not bool(working["omission_resolution_ready"].all()):
        raise SensitivityError("omission readiness contains unresolved rows")
    if bool(working.duplicated(["universe_id", "decision_time", "omitted_pair"]).any()):
        raise SensitivityError("omission readiness keys are duplicated")
    return working.sort_values(
        ["universe_id", "decision_time", "omitted_pair"],
        kind="stable",
    ).reset_index(drop=True)


def generated_pairs(a2_runtime: Path) -> frozenset[str]:
    path = a2_runtime / "symbol-generation-summary.csv"
    if not path.is_file():
        raise SensitivityError(f"A2 generation summary missing: {path}")
    frame = pd.read_csv(path, low_memory=False)
    required = {"pair", "generation_status"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise SensitivityError(f"A2 generation columns missing: {missing}")
    result = frozenset(
        frame.loc[
            frame["generation_status"].astype(str) == "GENERATED",
            "pair",
        ].astype(str)
    )
    if len(result) != 339:
        raise SensitivityError(f"generated pair count drifted: {len(result)}")
    return result


def pair_symbol_map(a1_runtime: Path) -> dict[str, str]:
    path = a1_runtime / "full-c2-hourly-acquisition-plan.csv"
    if not path.is_file():
        raise SensitivityError(f"A1 plan missing: {path}")
    frame = pd.read_csv(path, low_memory=False)
    required = {"pair", "symbol"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise SensitivityError(f"A1 plan columns missing: {missing}")
    if bool(frame["pair"].astype(str).duplicated().any()):
        raise SensitivityError("A1 plan pair keys are duplicated")
    return dict(
        zip(
            frame["pair"].astype(str),
            frame["symbol"].astype(str),
            strict=True,
        )
    )


class A2CandidateCache:
    def __init__(self, a2_runtime: Path) -> None:
        self.a2_runtime = a2_runtime
        self._cache: dict[str, pd.DataFrame] = {}

    def get(self, pair: str) -> pd.DataFrame:
        cached = self._cache.get(pair)
        if cached is None:
            cached = load_pair_candidates(self.a2_runtime, pair)
            self._cache[pair] = cached
        return cached


class HourlyBarCache:
    def __init__(
        self,
        *,
        repo: Path,
        symbol_by_pair: Mapping[str, str],
    ) -> None:
        self.store = ParquetCandleStore(repo / "data/raw/rd16b")
        self.symbol_by_pair = dict(symbol_by_pair)
        self._frames: dict[str, pd.DataFrame] = {}

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def get_symbol(self, symbol: str) -> pd.DataFrame:
        cached = self._frames.get(symbol)
        if cached is not None:
            return cached
        path = self.store.dataset_path(
            exchange_id="kucoin",
            symbol=symbol,
            timeframe="1h",
        )
        metadata_path = self.store.metadata_path(path)
        if not path.is_file() or not metadata_path.is_file():
            raise SensitivityError(f"sealed 1h source or metadata missing: {symbol}")
        metadata = json_load(metadata_path)
        expected = metadata.get("sha256")
        if not isinstance(expected, str):
            raise SensitivityError(f"sealed 1h metadata SHA missing: {symbol}")
        if self._sha256(path) != expected:
            raise SensitivityError(f"sealed 1h source hash mismatch: {symbol}")
        frame = pd.read_parquet(
            str(path),
            engine="pyarrow",
            filters=[
                (
                    "timestamp",
                    "<",
                    SEALED_CUTOFF.to_pydatetime(),
                )
            ],
        )
        normalized = normalize_hourly_bars(frame)
        self._frames[symbol] = normalized
        return normalized

    def get_pair(self, pair: str) -> pd.DataFrame:
        symbol = self.symbol_by_pair.get(pair)
        if symbol is None:
            raise SensitivityError(f"pair lacks A1 symbol mapping: {pair}")
        return self.get_symbol(symbol)

    def frames_for_candidates(
        self,
        candidates: pd.DataFrame,
    ) -> dict[str, pd.DataFrame]:
        symbols = sorted(candidates["symbol"].astype(str).unique())
        return {symbol: self.get_symbol(symbol) for symbol in symbols}


class IntervalReadinessCache:
    def __init__(
        self,
        *,
        repo: Path,
        symbol_by_pair: Mapping[str, str],
        generated: frozenset[str],
    ) -> None:
        self.store = ParquetCandleStore(repo / "data/raw/rd16b")
        self.symbol_by_pair = dict(symbol_by_pair)
        self.generated = generated
        self._completed: dict[str, pd.DatetimeIndex] = {}

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def _load(self, pair: str) -> pd.DatetimeIndex:
        if pair not in self.generated:
            raise SensitivityError(f"readiness pair is not GENERATED: {pair}")
        symbol = self.symbol_by_pair.get(pair)
        if symbol is None:
            raise SensitivityError(f"readiness pair lacks symbol mapping: {pair}")
        frames: dict[str, pd.DataFrame] = {}
        for timeframe in TIMEFRAMES:
            path = self.store.dataset_path(
                exchange_id="kucoin",
                symbol=symbol,
                timeframe=timeframe,
            )
            metadata_path = self.store.metadata_path(path)
            if not path.is_file() or not metadata_path.is_file():
                raise SensitivityError(f"readiness source missing: {pair}:{timeframe}")
            metadata = json_load(metadata_path)
            expected = metadata.get("sha256")
            if not isinstance(expected, str):
                raise SensitivityError(f"readiness metadata SHA missing: {pair}:{timeframe}")
            if self._sha256(path) != expected:
                raise SensitivityError(f"readiness source hash mismatch: {pair}:{timeframe}")
            frame = pd.read_parquet(
                str(path),
                engine="pyarrow",
                filters=[
                    (
                        "timestamp",
                        "<",
                        SEALED_CUTOFF.to_pydatetime(),
                    )
                ],
            )
            frame["timestamp"] = pd.to_datetime(
                frame["timestamp"],
                utc=True,
                errors="raise",
            ).astype("datetime64[ns, UTC]")
            if bool((frame["timestamp"] >= SEALED_CUTOFF).any()):
                raise SensitivityError(
                    f"post-2024 readiness row entered memory: {pair}:{timeframe}"
                )
            frames[timeframe] = frame.sort_values(
                "timestamp",
                kind="stable",
            ).reset_index(drop=True)
        try:
            feature = build_feature_frame(frames, symbol=symbol)
        except FeatureDataError as exc:
            raise SensitivityError(f"cannot build readiness features: {pair}: {exc}") from exc
        completed = pd.DatetimeIndex(
            pd.to_datetime(
                feature["timestamp"],
                utc=True,
                errors="raise",
            )
        )
        completed = completed[
            (completed >= PRIMARY_START) & (completed < SEALED_CUTOFF)
        ].sort_values()
        if completed.has_duplicates:
            raise SensitivityError(f"readiness feature times duplicate: {pair}")
        self._completed[pair] = completed
        return completed

    def interval_count(
        self,
        pair: str,
        start: pd.Timestamp,
        end: pd.Timestamp,
    ) -> int:
        times = self._completed.get(pair)
        if times is None:
            times = self._load(pair)
        left = int(times.searchsorted(start, side="left"))
        right = int(times.searchsorted(end, side="left"))
        return max(0, right - left)


def json_load(path: Path) -> dict[str, Any]:
    value = __import__("json").loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise SensitivityError(f"JSON object expected: {path}")
    return value


class CounterfactualMembershipBuilder:
    def __init__(
        self,
        *,
        base_membership: pd.DataFrame,
        omission_readiness: pd.DataFrame,
        rankings: pd.DataFrame,
        generated: frozenset[str],
        readiness: IntervalReadinessCache,
    ) -> None:
        self.base = normalize_base_membership(base_membership)
        self.omissions = normalize_omission_readiness(omission_readiness)
        self.rankings = rankings.copy()
        self.rankings["universe_id"] = self.rankings["universe_id"].astype(str)
        self.rankings["decision_time"] = pd.to_datetime(
            self.rankings["decision_time"],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
        self.rankings["pair"] = self.rankings["pair"].astype(str)
        self.rankings["rank"] = pd.to_numeric(
            self.rankings["rank"],
            errors="raise",
        ).astype(int)
        self.generated = generated
        self.readiness = readiness
        self._omission_lookup = {
            (
                str(row.universe_id),
                pd.Timestamp(row.decision_time),
                str(row.omitted_pair),
            ): row
            for row in self.omissions.itertuples(index=False)
        }
        self._ranking_lookup = {
            (str(universe), pd.Timestamp(decision)): group.sort_values(
                ["rank", "canonical_asset_id"],
                kind="stable",
            )
            for (universe, decision), group in self.rankings.groupby(
                ["universe_id", "decision_time"],
                sort=True,
            )
        }

    def _generic_replacement(
        self,
        *,
        universe_id: str,
        decision: pd.Timestamp,
        effective_end: pd.Timestamp,
        excluded: set[str],
    ) -> tuple[str, str, int, int] | None:
        ranked = self._ranking_lookup.get((universe_id, decision))
        if ranked is None or ranked.empty:
            raise SensitivityError(f"ranking missing: {universe_id}:{decision}")
        for row in ranked.itertuples(index=False):
            pair = str(row.pair)
            if pair in excluded or pair not in self.generated:
                continue
            count = self.readiness.interval_count(
                pair,
                decision,
                effective_end,
            )
            if count <= 0:
                continue
            return (
                pair,
                str(row.canonical_asset_id),
                int(row.rank),
                count,
            )
        return None

    def build(
        self,
        *,
        universe_id: str,
        omitted_pair: str,
    ) -> CounterfactualMembership:
        if universe_id not in UNIVERSE_IDS:
            raise SensitivityError(f"unsupported universe: {universe_id}")
        source = self.base.loc[self.base["universe_id"] == universe_id].copy()
        result_rows: list[dict[str, object]] = []
        resolution_rows: list[dict[str, object]] = []
        affected_decisions = 0
        replacement_decisions = 0
        capacity_reduction_decisions = 0

        for decision, group in source.groupby(
            "decision_time",
            sort=True,
        ):
            decision_time = pd.Timestamp(decision)
            end_values = pd.DatetimeIndex(group["effective_end"].unique())
            if len(end_values) != 1:
                raise SensitivityError(
                    f"inconsistent membership end: {universe_id}:{decision_time}"
                )
            effective_end = pd.Timestamp(end_values[0])
            original_pairs = set(group["original_pair"].astype(str))
            affected = group.loc[
                (group["original_pair"].astype(str) == omitted_pair)
                | (group["effective_pair"].astype(str) == omitted_pair)
            ].copy()
            if affected.empty:
                result_rows.extend(
                    cast(
                        list[dict[str, object]],
                        group.to_dict(orient="records"),
                    )
                )
                resolution_rows.append(
                    {
                        "universe_id": universe_id,
                        "decision_time": decision_time,
                        "effective_end": effective_end,
                        "omitted_pair": omitted_pair,
                        "affected": False,
                        "removed_original_pair": "",
                        "removed_effective_pair": "",
                        "replacement_pair": "",
                        "resolution_mode": "NO_EFFECT",
                        "capacity_after_omission": len(group),
                        "completed_bar_count": 0,
                        "resolution_source": "BASE_MEMBERSHIP",
                    }
                )
                continue

            affected_decisions += 1
            remaining = group.drop(index=affected.index).copy()
            if len(affected) > 1:
                raise SensitivityError(
                    "one omitted asset affected multiple membership "
                    f"slots: {universe_id}:{decision_time}:"
                    f"{omitted_pair}"
                )
            removed = affected.iloc[0].to_dict()
            excluded = (
                original_pairs | set(remaining["effective_pair"].astype(str)) | {omitted_pair}
            )
            replacement: tuple[str, str, int, int] | None = None
            mode = ""
            source_name = ""
            reason = ""
            original_pair = str(removed["original_pair"])
            if original_pair == omitted_pair:
                ledger = self._omission_lookup.get((universe_id, decision_time, omitted_pair))
                if ledger is None:
                    raise SensitivityError(
                        f"omission ledger row missing: {universe_id}:{decision_time}:{omitted_pair}"
                    )
                if bool(ledger.replacement_ready):
                    candidate_pair = str(ledger.replacement_pair)
                    if candidate_pair and candidate_pair not in excluded:
                        replacement = (
                            candidate_pair,
                            str(ledger.replacement_canonical_asset_id),
                            int(ledger.replacement_rank),
                            int(ledger.completed_bar_count),
                        )
                        mode = "REPLACEMENT"
                        source_name = "A3B_OMISSION_LEDGER"
                        reason = str(ledger.reason)
                    else:
                        source_name = "A3B_LEDGER_DUPLICATE_FALLBACK"
                else:
                    mode = str(ledger.resolution_mode)
                    source_name = "A3B_OMISSION_LEDGER"
                    reason = str(ledger.reason)
            else:
                source_name = "EFFECTIVE_OPERATIONAL_REPLACEMENT_OMISSION"

            if replacement is None and not mode.endswith("CAPACITY_REDUCTION"):
                replacement = self._generic_replacement(
                    universe_id=universe_id,
                    decision=decision_time,
                    effective_end=effective_end,
                    excluded=excluded,
                )
                if replacement is not None:
                    mode = "REPLACEMENT"
                    source_name = (f"{source_name}|GENERIC_RANKED_FALLBACK").strip("|")
                    reason = "HIGHEST_RANKED_INTERVAL_READY_GENERATED_NONMEMBER"
                else:
                    mode = "INTERVAL_CAPACITY_REDUCTION"
                    source_name = (f"{source_name}|GENERIC_CAPACITY_REDUCTION").strip("|")
                    reason = "NO_INTERVAL_READY_GENERATED_NONMEMBER"

            replacement_pair = ""
            completed_count = 0
            if replacement is not None:
                (
                    replacement_pair,
                    replacement_id,
                    replacement_rank,
                    completed_count,
                ) = replacement
                replacement_row = dict(removed)
                replacement_row["effective_pair"] = replacement_pair
                replacement_row["effective_canonical_asset_id"] = replacement_id
                replacement_row["effective_rank"] = replacement_rank
                replacement_row["replacement_applied"] = True
                replacement_row["replacement_reason"] = "LOAO_" + reason
                replacement_row["completed_bar_count"] = completed_count
                remaining = pd.concat(
                    [
                        remaining,
                        pd.DataFrame([replacement_row]),
                    ],
                    ignore_index=True,
                )
                replacement_decisions += 1
            else:
                capacity_reduction_decisions += 1

            if len(remaining) not in {5, 6}:
                raise SensitivityError(
                    f"invalid LOAO capacity: {universe_id}:{decision_time}:{len(remaining)}"
                )
            if bool(remaining["effective_pair"].astype(str).duplicated().any()):
                raise SensitivityError(
                    f"duplicate LOAO effective pair: {universe_id}:{decision_time}"
                )
            result_rows.extend(
                cast(
                    list[dict[str, object]],
                    remaining.to_dict(orient="records"),
                )
            )
            resolution_rows.append(
                {
                    "universe_id": universe_id,
                    "decision_time": decision_time,
                    "effective_end": effective_end,
                    "omitted_pair": omitted_pair,
                    "affected": True,
                    "removed_original_pair": original_pair,
                    "removed_effective_pair": str(removed["effective_pair"]),
                    "replacement_pair": replacement_pair,
                    "resolution_mode": mode,
                    "capacity_after_omission": len(remaining),
                    "completed_bar_count": completed_count,
                    "resolution_source": source_name,
                }
            )

        membership = pd.DataFrame.from_records(result_rows)
        membership["decision_time"] = pd.to_datetime(
            membership["decision_time"],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
        membership["effective_end"] = pd.to_datetime(
            membership["effective_end"],
            utc=True,
            errors="raise",
        ).astype("datetime64[ns, UTC]")
        if membership["decision_time"].nunique() != EXPECTED_DECISIONS:
            raise SensitivityError(f"LOAO decision count drifted: {universe_id}:{omitted_pair}")
        sizes = membership.groupby(
            "decision_time",
            sort=True,
        ).size()
        if not bool(sizes.isin({5, 6}).all()):
            raise SensitivityError(
                f"LOAO membership capacity invalid: {universe_id}:{omitted_pair}"
            )
        membership = membership.sort_values(
            [
                "decision_time",
                "effective_rank",
                "effective_pair",
            ],
            kind="stable",
        ).reset_index(drop=True)
        digest = frame_content_hash(
            membership,
            columns=(
                "universe_id",
                "decision_time",
                "effective_end",
                "original_pair",
                "effective_pair",
                "effective_rank",
                "replacement_applied",
                "completed_bar_count",
            ),
            sort_by=(
                "universe_id",
                "decision_time",
                "effective_rank",
                "effective_pair",
            ),
        )
        return CounterfactualMembership(
            universe_id=universe_id,
            omitted_pair=omitted_pair,
            membership=membership,
            resolution_rows=resolution_rows,
            affected_decisions=affected_decisions,
            replacement_decisions=replacement_decisions,
            capacity_reduction_decisions=(capacity_reduction_decisions),
            membership_sha256=digest,
        )


def select_counterfactual_a2_candidates(
    *,
    membership: pd.DataFrame,
    universe_id: str,
    cache: A2CandidateCache,
) -> pd.DataFrame:
    if membership.empty:
        raise SensitivityError("counterfactual membership is empty")
    parts: list[pd.DataFrame] = []
    for row in membership.itertuples(index=False):
        pair = str(row.effective_pair)
        candidates = cache.get(pair)
        if candidates.empty:
            continue
        interval = candidates.loc[
            (candidates["signal_close"] >= pd.Timestamp(row.decision_time))
            & (candidates["signal_close"] < pd.Timestamp(row.effective_end))
            & (candidates["signal_close"] >= PRIMARY_START)
        ].copy()
        if interval.empty:
            continue
        interval["universe_id"] = universe_id
        interval["membership_decision_time"] = pd.Timestamp(row.decision_time)
        interval["membership_effective_end"] = pd.Timestamp(row.effective_end)
        interval["membership_original_pair"] = str(row.original_pair)
        interval["membership_effective_pair"] = pair
        interval["membership_replacement_applied"] = bool(row.replacement_applied)
        parts.append(interval)
    if not parts:
        raise SensitivityError(f"{universe_id} counterfactual selected no candidates")
    result = pd.concat(parts, ignore_index=True)
    if bool(result["candidate_id"].astype(str).duplicated().any()):
        raise SensitivityError(f"{universe_id} counterfactual candidate IDs duplicate")
    return result.sort_values(
        [
            "entry_open_time",
            "engine_priority",
            "symbol",
            "signal_close",
            "candidate_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def filter_loyo_candidates(
    candidates: pd.DataFrame,
    *,
    omitted_year: int,
) -> pd.DataFrame:
    if omitted_year not in OMITTED_YEARS:
        raise SensitivityError(f"unsupported omitted year: {omitted_year}")
    signal = pd.to_datetime(
        candidates["signal_close"],
        utc=True,
        errors="raise",
    )
    result = candidates.loc[signal.dt.year != omitted_year].copy()
    if result.empty:
        raise SensitivityError(f"LOYO {omitted_year} removed every candidate")
    if bool(
        (
            pd.to_datetime(
                result["signal_close"],
                utc=True,
                errors="raise",
            ).dt.year
            == omitted_year
        ).any()
    ):
        raise SensitivityError(f"LOYO {omitted_year} retained omitted admissions")
    return result.reset_index(drop=True)


def execute_sensitivity(
    *,
    candidates: pd.DataFrame,
    universe_id: str,
    cost_multiplier: float,
    hourly_cache: HourlyBarCache,
    run_type: str,
    omitted_value: str,
) -> SensitivityExecution:
    route = route_cash_feasible_candidates(
        candidates,
        universe_id=universe_id,
        cost_multiplier=cost_multiplier,
    )
    hourly_frames = hourly_cache.frames_for_candidates(route.trades)
    curve = build_equity_curve(
        route.trades,
        hourly_frames=hourly_frames,
        timeline=primary_timeline(),
        cost_multiplier=cost_multiplier,
    )
    metrics = performance_metrics(
        curve,
        route.trades,
        cost_multiplier=cost_multiplier,
    )
    checks = {
        "cash_route_feasible": route.cash_feasible,
        "route_minimum_cash_nonnegative": (route.minimum_cash >= -1e-6),
        "metric_capital_feasible": bool(metrics["capital_feasible"]),
        "metric_minimum_cash_nonnegative": (
            _finite(
                metrics["minimum_cash"],
                name="metric_minimum_cash",
            )
            >= -1e-6
        ),
        "maximum_positions_respected": (route.maximum_positions_observed <= 5),
        "maximum_open_risk_respected": (
            route.maximum_open_risk_fraction_observed <= 0.0225 + 1e-12
        ),
        "final_cash_equity_reconciled": abs(
            route.final_cash - _finite(metrics["final_equity"], name="final_equity")
        )
        <= max(
            1e-6,
            abs(route.final_cash) * 1e-10,
        ),
    }
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise SensitivityError(
            f"sensitivity run checks failed: "
            f"{run_type}:{universe_id}:{omitted_value}:"
            f"{cost_multiplier}x:{failed}"
        )
    net_return = _finite(
        metrics["net_return"],
        name="net_return",
    )
    profit_factor = _finite(
        metrics["profit_factor"],
        name="profit_factor",
    )
    base_conclusion = net_return > 0.0 and profit_factor >= 1.0
    candidate_hash = frame_content_hash(
        candidates,
        columns=(
            "v3_candidate_id",
            "signal_close",
            "entry_open_time",
            "symbol",
            "engine_id",
            "risk_budget",
            "quantity",
            "notional",
            "exit_bar_close",
            "exit_price",
        ),
        sort_by=(
            "entry_open_time",
            "symbol",
            "signal_close",
            "v3_candidate_id",
        ),
    )
    trade_hash = frame_content_hash(
        route.trades,
        columns=(
            "source_cash_router_candidate_id",
            "entry_open_time",
            "symbol",
            "quantity",
            "notional",
            "exit_bar_close",
            "exit_price",
        ),
        sort_by=(
            "entry_open_time",
            "symbol",
            "source_cash_router_candidate_id",
        ),
    )
    decision_counts = (
        route.evaluated["router_decision"].astype(str).value_counts().sort_index().to_dict()
    )
    record: dict[str, object] = {
        "schema_version": "rd18-p3e-sensitivity-run-v1",
        "run_type": run_type,
        "universe_id": universe_id,
        "omitted_value": omitted_value,
        "cost_multiplier": cost_multiplier,
        "candidate_rows": len(candidates),
        "evaluated_rows": len(route.evaluated),
        "trade_count": int(metrics["trade_count"]),
        "candidate_sha256": candidate_hash,
        "trade_identity_sha256": trade_hash,
        "net_return": net_return,
        "cagr": _finite(metrics["cagr"], name="cagr"),
        "monthly_geometric_return": _finite(
            metrics["monthly_geometric_return"],
            name="monthly_geometric_return",
        ),
        "profit_factor": profit_factor,
        "maximum_drawdown": _finite(
            metrics["maximum_drawdown"],
            name="maximum_drawdown",
        ),
        "minimum_cash": _finite(
            metrics["minimum_cash"],
            name="minimum_cash",
        ),
        "final_equity": _finite(
            metrics["final_equity"],
            name="final_equity",
        ),
        "win_rate": _finite(
            metrics["win_rate"],
            name="win_rate",
        ),
        "expectancy_per_trade": _finite(
            metrics["expectancy_per_trade"],
            name="expectancy_per_trade",
        ),
        "capital_feasible": bool(metrics["capital_feasible"]),
        "sensitivity_conclusion_passed": base_conclusion,
        "positive_net_return": net_return > 0.0,
        "profit_factor_at_least_one": profit_factor >= 1.0,
        "maximum_positions_observed": (route.maximum_positions_observed),
        "maximum_open_risk_fraction_observed": (route.maximum_open_risk_fraction_observed),
        "maximum_open_notional_fraction_observed": (route.maximum_open_notional_fraction_observed),
        "insufficient_cash_rejections": (route.insufficient_cash_rejections),
        "router_decision_counts": decision_counts,
        "checks": checks,
        "network_requests": 0,
        "post_2024_accessed": False,
        "production_authorized": False,
    }
    return SensitivityExecution(record=record, route=route)


def sensitivity_gate_summary(
    *,
    loyo_rows: Sequence[Mapping[str, object]],
    loao_rows: Sequence[Mapping[str, object]],
    named_rows: Sequence[Mapping[str, object]],
    corrected_base_rows: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    one_x_loyo = [row for row in loyo_rows if float(cast(Any, row["cost_multiplier"])) == 1.0]
    one_x_loao = [row for row in loao_rows if float(cast(Any, row["cost_multiplier"])) == 1.0]
    base_map = {
        (
            str(row["universe_id"]),
            float(cast(Any, row["cost_multiplier"])),
        ): (
            _finite(row["net_return"], name="base_net_return") > 0.0
            and _finite(
                row["profit_factor"],
                name="base_profit_factor",
            )
            >= 1.0
        )
        for row in corrected_base_rows
    }
    reversal_rows: list[dict[str, object]] = []
    for row in named_rows:
        key = (
            str(row["universe_id"]),
            float(cast(Any, row["cost_multiplier"])),
        )
        base_conclusion = base_map[key]
        omission_conclusion = bool(row["sensitivity_conclusion_passed"])
        reversal_rows.append(
            {
                "pair": str(row["omitted_value"]),
                "universe_id": key[0],
                "cost_multiplier": key[1],
                "base_conclusion": base_conclusion,
                "omission_conclusion": omission_conclusion,
                "reversal": (base_conclusion != omission_conclusion),
            }
        )
    checks = {
        "loyo_one_x_all_positive": all(bool(row["positive_net_return"]) for row in one_x_loyo),
        "loyo_one_x_profit_factor_minimum": all(
            bool(row["profit_factor_at_least_one"]) for row in one_x_loyo
        ),
        "loao_one_x_all_positive": all(bool(row["positive_net_return"]) for row in one_x_loao),
        "loao_one_x_profit_factor_minimum": all(
            bool(row["profit_factor_at_least_one"]) for row in one_x_loao
        ),
        "named_omission_conclusion_reversal_absent": all(
            not bool(row["reversal"]) for row in reversal_rows
        ),
        "bchsv_executed": any(str(row["omitted_value"]) == "BCHSV-USDT" for row in named_rows),
        "pepe_executed": any(str(row["omitted_value"]) == "PEPE-USDT" for row in named_rows),
    }
    return {
        "checks": checks,
        "named_omission_reversal_rows": reversal_rows,
        "passed": all(checks.values()),
        "two_x_loyo_failures": sum(
            not bool(row["sensitivity_conclusion_passed"])
            for row in loyo_rows
            if float(cast(Any, row["cost_multiplier"])) == 2.0
        ),
        "two_x_loao_failures": sum(
            not bool(row["sensitivity_conclusion_passed"])
            for row in loao_rows
            if float(cast(Any, row["cost_multiplier"])) == 2.0
        ),
    }


__all__ = [
    "A2CandidateCache",
    "COST_MULTIPLIERS",
    "CounterfactualMembership",
    "CounterfactualMembershipBuilder",
    "HourlyBarCache",
    "IntervalReadinessCache",
    "NAMED_OMISSIONS",
    "OMITTED_YEARS",
    "SensitivityError",
    "SensitivityExecution",
    "UNIVERSE_IDS",
    "execute_sensitivity",
    "filter_loyo_candidates",
    "frame_content_hash",
    "generated_pairs",
    "normalize_base_membership",
    "normalize_omission_readiness",
    "pair_symbol_map",
    "select_counterfactual_a2_candidates",
    "sensitivity_gate_summary",
]
