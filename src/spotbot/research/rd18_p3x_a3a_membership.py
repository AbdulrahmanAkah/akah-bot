# mypy: disable-error-code="arg-type"
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

import pandas as pd

PRIMARY_START: Final = pd.Timestamp("2019-04-01T00:00:00+00:00")
SEALED_CUTOFF: Final = pd.Timestamp("2025-01-01T00:00:00+00:00")
EXPECTED_DECISIONS: Final = 301
ENTRY_RANK: Final = 6
RETENTION_RANK: Final = 8

MEMBERSHIP_FIELDS: Final = (
    "universe_id",
    "decision_time",
    "effective_end",
    "pair",
    "canonical_asset_id",
    "rank",
    "member",
    "top6",
    "membership_source",
)

REPLACEMENT_FIELDS: Final = (
    "universe_id",
    "decision_time",
    "omitted_pair",
    "replacement_pair",
    "replacement_rank",
    "replacement_ready",
    "reason",
)


class A3AMembershipError(ValueError):
    """Raised when canonical membership evidence is malformed."""


@dataclass(frozen=True, slots=True)
class MembershipBuild:
    membership: pd.DataFrame
    ranking: pd.DataFrame


def _column(
    columns: Iterable[str],
    *preferred: str,
    contains: str | None = None,
) -> str:
    available = list(columns)
    for name in preferred:
        if name in available:
            return name
    if contains is not None:
        matches = [name for name in available if contains.lower() in name.lower()]
        if len(matches) == 1:
            return matches[0]
    raise A3AMembershipError(
        f"required column is missing; preferred={preferred}, "
        f"contains={contains!r}, available={available}"
    )


def _bool_series(series: pd.Series, *, name: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    allowed = {"true", "false", "1", "0"}
    observed = set(normalized.dropna().unique())
    if not observed.issubset(allowed):
        raise A3AMembershipError(f"{name} contains non-boolean values: {sorted(observed)}")
    return normalized.isin({"true", "1"})


def _times(series: pd.Series, *, name: str) -> pd.Series:
    parsed = pd.to_datetime(series, utc=True, errors="raise")
    if parsed.isna().any():
        raise A3AMembershipError(f"{name} contains null timestamps")
    return parsed.astype("datetime64[ns, UTC]")



def _sealed(frame: pd.DataFrame, *, time_column: str) -> pd.DataFrame:
    working = frame.copy()
    working[time_column] = _times(
        working[time_column],
        name=time_column,
    )
    return working.loc[working[time_column] < SEALED_CUTOFF].copy()


def _primary(frame: pd.DataFrame, *, time_column: str) -> pd.DataFrame:
    working = _sealed(frame, time_column=time_column)
    return working.loc[working[time_column] >= PRIMARY_START].copy()

def inventory_maps(
    inventory: pd.DataFrame,
) -> tuple[dict[str, str], frozenset[str], frozenset[str]]:
    canonical_column = _column(
        inventory.columns,
        "canonical_product_id",
        "canonical_asset_id",
    )
    pair_column = _column(inventory.columns, "pair")
    c2_column = _column(
        inventory.columns,
        "variant_c2_presence",
    )
    d2_column = _column(
        inventory.columns,
        "variant_d2_presence",
    )

    working = inventory.copy()
    working[c2_column] = _bool_series(
        working[c2_column],
        name=c2_column,
    )
    working[d2_column] = _bool_series(
        working[d2_column],
        name=d2_column,
    )
    working[canonical_column] = working[canonical_column].astype(str).str.strip()
    working[pair_column] = working[pair_column].astype(str).str.strip()

    ordinary = working.loc[working[c2_column]].copy()
    if ordinary[canonical_column].duplicated().any():
        duplicates = sorted(
            ordinary.loc[
                ordinary[canonical_column].duplicated(keep=False),
                canonical_column,
            ]
            .astype(str)
            .unique()
        )
        raise A3AMembershipError(f"canonical inventory IDs are not unique: {duplicates}")

    mapping = dict(
        zip(
            ordinary[canonical_column].astype(str),
            ordinary[pair_column].astype(str),
            strict=True,
        )
    )
    c2_pairs = frozenset(ordinary[pair_column].astype(str).tolist())
    d2_pairs = frozenset(working.loc[working[d2_column], pair_column].astype(str).tolist())
    if not d2_pairs.issubset(c2_pairs):
        raise A3AMembershipError("D2 inventory is not a C2 subset")
    return mapping, c2_pairs, d2_pairs



def normalize_ranking(
    ranking: pd.DataFrame,
    *,
    mapping: dict[str, str],
    universe_id: str,
    allowed_pairs: frozenset[str] | None = None,
    recompute_rank: bool = False,
    include_warmup: bool = False,
) -> pd.DataFrame:
    time_column = _column(
        ranking.columns,
        "decision_time",
        "week_start",
    )
    canonical_column = _column(
        ranking.columns,
        "canonical_asset_id",
        "canonical_product_id",
        "asset_id",
    )
    rank_column = _column(
        ranking.columns,
        "rank",
        "liquidity_rank",
        "corrected_rank",
        "adjusted_rank",
        contains="rank",
    )
    pair_column = "pair" if "pair" in ranking.columns else None

    working = (
        _sealed(ranking, time_column=time_column)
        if include_warmup
        else _primary(ranking, time_column=time_column)
    )
    working[canonical_column] = (
        working[canonical_column].astype(str).str.strip()
    )
    if pair_column is None:
        working["pair"] = working[canonical_column].map(mapping)
        if working["pair"].isna().any():
            missing = sorted(
                working.loc[
                    working["pair"].isna(),
                    canonical_column,
                ]
                .astype(str)
                .unique()
            )
            raise A3AMembershipError(
                f"{universe_id} ranking has unmapped IDs: {missing}"
            )
        pair_column = "pair"
    else:
        working[pair_column] = (
            working[pair_column].astype(str).str.strip()
        )

    working[rank_column] = pd.to_numeric(
        working[rank_column],
        errors="raise",
    )
    if allowed_pairs is not None:
        working = working.loc[
            working[pair_column].isin(allowed_pairs)
        ].copy()

    working = working.sort_values(
        by=[time_column, rank_column, canonical_column],
        kind="stable",
    ).reset_index(drop=True)
    if recompute_rank:
        working["normalized_rank"] = (
            working.groupby(time_column, sort=False).cumcount() + 1
        )
    else:
        working["normalized_rank"] = working[rank_column].astype(int)

    duplicate_keys = working.duplicated(
        [time_column, canonical_column],
        keep=False,
    )
    if duplicate_keys.any():
        raise A3AMembershipError(
            f"{universe_id} ranking has duplicate decision/assets"
        )

    normalized = pd.DataFrame(
        {
            "universe_id": universe_id,
            "decision_time": working[time_column],
            "pair": working[pair_column].astype(str),
            "canonical_asset_id": (
                working[canonical_column].astype(str)
            ),
            "rank": working["normalized_rank"].astype(int),
        }
    )
    return normalized.sort_values(
        ["decision_time", "rank", "canonical_asset_id"],
        kind="stable",
    ).reset_index(drop=True)


def apply_hysteresis(
    ranking: pd.DataFrame,
    *,
    universe_id: str,
    source: str,
) -> MembershipBuild:
    required = {
        "universe_id",
        "decision_time",
        "pair",
        "canonical_asset_id",
        "rank",
    }
    missing = sorted(required.difference(ranking.columns))
    if missing:
        raise A3AMembershipError(
            f"{universe_id} ranking columns missing: {missing}"
        )

    working_ranking = ranking.copy()
    working_ranking["decision_time"] = _times(
        working_ranking["decision_time"],
        name="decision_time",
    )
    records: list[dict[str, object]] = []
    incumbent: set[str] = set()
    decisions = sorted(working_ranking["decision_time"].unique())
    primary_decisions = [
        pd.Timestamp(decision)
        for decision in decisions
        if PRIMARY_START <= pd.Timestamp(decision) < SEALED_CUTOFF
    ]
    if len(primary_decisions) != EXPECTED_DECISIONS:
        raise A3AMembershipError(
            f"{universe_id} expected {EXPECTED_DECISIONS} primary "
            f"decisions, found {len(primary_decisions)}"
        )

    for index, raw_time in enumerate(decisions):
        decision = pd.Timestamp(raw_time)
        current = working_ranking.loc[
            working_ranking["decision_time"] == decision
        ].copy()
        current = current.sort_values(
            ["rank", "canonical_asset_id"],
            kind="stable",
        )
        rank_by_pair = dict(
            zip(
                current["pair"].astype(str),
                current["rank"].astype(int),
                strict=True,
            )
        )
        retained = {
            pair
            for pair in incumbent
            if rank_by_pair.get(pair, RETENTION_RANK + 1)
            <= RETENTION_RANK
        }
        if len(retained) > ENTRY_RANK:
            raise A3AMembershipError(
                f"{universe_id} retained more than {ENTRY_RANK} members at "
                f"{decision.isoformat()}"
            )

        members = set(retained)
        for pair in current["pair"].astype(str):
            if len(members) >= ENTRY_RANK:
                break
            members.add(pair)

        expected_members = min(ENTRY_RANK, len(current))
        if len(members) != expected_members:
            raise A3AMembershipError(
                f"{universe_id} expected {expected_members} members at "
                f"{decision.isoformat()}, found {len(members)}"
            )
        if not members:
            raise A3AMembershipError(
                f"{universe_id} has no members at {decision.isoformat()}"
            )

        effective_end = (
            pd.Timestamp(decisions[index + 1])
            if index + 1 < len(decisions)
            else SEALED_CUTOFF
        )
        subset = current.loc[current["pair"].isin(members)].copy()
        for row in subset.itertuples(index=False):
            records.append(
                {
                    "universe_id": universe_id,
                    "decision_time": decision,
                    "effective_end": effective_end,
                    "pair": str(row.pair),
                    "canonical_asset_id": str(row.canonical_asset_id),
                    "rank": int(row.rank),
                    "member": True,
                    "top6": int(row.rank) <= ENTRY_RANK,
                    "membership_source": source,
                }
            )
        incumbent = members

    membership = _primary(
        pd.DataFrame.from_records(
            records,
            columns=MEMBERSHIP_FIELDS,
        ),
        time_column="decision_time",
    )
    primary_ranking = _primary(
        working_ranking,
        time_column="decision_time",
    )
    validate_membership(membership, universe_id=universe_id)
    return MembershipBuild(
        membership=membership.reset_index(drop=True),
        ranking=primary_ranking.reset_index(drop=True),
    )

def materialize_committed_membership(
    source_frame: pd.DataFrame,
    *,
    mapping: dict[str, str],
    universe_id: str,
    source: str,
) -> MembershipBuild:
    time_column = _column(
        source_frame.columns,
        "decision_time",
    )
    member_column = _column(source_frame.columns, "member")
    canonical_column = _column(
        source_frame.columns,
        "canonical_asset_id",
        "canonical_product_id",
    )
    pair_column = "pair" if "pair" in source_frame.columns else None
    rank_column = _column(
        source_frame.columns,
        "adjusted_rank",
        "rank",
        "liquidity_rank",
        contains="rank",
    )

    working = _primary(source_frame, time_column=time_column)
    working[member_column] = _bool_series(
        working[member_column],
        name=member_column,
    )
    working = working.loc[working[member_column]].copy()
    working[canonical_column] = working[canonical_column].astype(str).str.strip()
    if pair_column is None:
        working["pair"] = working[canonical_column].map(mapping)
        if working["pair"].isna().any():
            raise A3AMembershipError(f"{universe_id} committed membership has unmapped IDs")
        pair_column = "pair"
    working[rank_column] = pd.to_numeric(
        working[rank_column],
        errors="raise",
    ).astype(int)

    decisions = sorted(working[time_column].unique())
    if len(decisions) != EXPECTED_DECISIONS:
        raise A3AMembershipError(
            f"{universe_id} committed membership expected "
            f"{EXPECTED_DECISIONS} decisions, found {len(decisions)}"
        )
    next_by_time = {
        pd.Timestamp(decision): (
            pd.Timestamp(decisions[index + 1]) if index + 1 < len(decisions) else SEALED_CUTOFF
        )
        for index, decision in enumerate(decisions)
    }
    membership = pd.DataFrame(
        {
            "universe_id": universe_id,
            "decision_time": working[time_column],
            "effective_end": working[time_column].map(next_by_time),
            "pair": working[pair_column].astype(str),
            "canonical_asset_id": working[canonical_column].astype(str),
            "rank": working[rank_column].astype(int),
            "member": True,
            "top6": working[rank_column].astype(int) <= ENTRY_RANK,
            "membership_source": source,
        }
    )
    ranking = pd.DataFrame(
        {
            "universe_id": universe_id,
            "decision_time": working[time_column],
            "pair": working[pair_column].astype(str),
            "canonical_asset_id": working[canonical_column].astype(str),
            "rank": working[rank_column].astype(int),
        }
    )
    validate_membership(membership, universe_id=universe_id)
    return MembershipBuild(
        membership=membership.sort_values(
            ["decision_time", "rank", "pair"],
            kind="stable",
        ).reset_index(drop=True),
        ranking=ranking.sort_values(
            ["decision_time", "rank", "pair"],
            kind="stable",
        ).reset_index(drop=True),
    )


def validate_membership(
    membership: pd.DataFrame,
    *,
    universe_id: str,
) -> None:
    missing = sorted(set(MEMBERSHIP_FIELDS).difference(membership.columns))
    if missing:
        raise A3AMembershipError(f"{universe_id} membership columns missing: {missing}")
    decisions = pd.to_datetime(
        membership["decision_time"],
        utc=True,
        errors="raise",
    )
    unique = sorted(decisions.unique())
    if len(unique) != EXPECTED_DECISIONS:
        raise A3AMembershipError(f"{universe_id} membership decision count differs: {len(unique)}")
    if any(pd.Timestamp(value).weekday() != 0 for value in unique):
        raise A3AMembershipError(f"{universe_id} decisions are not all Monday UTC")
    if membership.duplicated(
        ["decision_time", "pair"],
        keep=False,
    ).any():
        raise A3AMembershipError(f"{universe_id} membership has duplicate decision/pair rows")
    counts = membership.groupby("decision_time").size()
    if bool((counts > RETENTION_RANK).any()):
        raise A3AMembershipError(f"{universe_id} membership exceeds retention limit")
    if bool((counts <= 0).any()):
        raise A3AMembershipError(f"{universe_id} membership contains empty decisions")


def build_replacement_ledger(
    membership: pd.DataFrame,
    ranking: pd.DataFrame,
    *,
    ready_pairs: frozenset[str],
    excluded_pairs: frozenset[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    available = ready_pairs.difference(excluded_pairs)
    for (universe, decision), group in membership.groupby(
        ["universe_id", "decision_time"],
        sort=True,
    ):
        ranked = ranking.loc[
            (ranking["universe_id"] == universe) & (ranking["decision_time"] == decision)
        ].sort_values(
            ["rank", "canonical_asset_id"],
            kind="stable",
        )
        members = set(group["pair"].astype(str))
        replacement_candidates = [
            (str(row.pair), int(row.rank))
            for row in ranked.itertuples(index=False)
            if str(row.pair) not in members and str(row.pair) in available
        ]
        for omitted in sorted(members):
            if replacement_candidates:
                replacement, replacement_rank = replacement_candidates[0]
                ready = True
                reason = "NEXT_RANKED_AVAILABLE_NONMEMBER"
            else:
                replacement = ""
                replacement_rank = 0
                ready = False
                reason = "NO_AVAILABLE_NONMEMBER_REPLACEMENT"
            rows.append(
                {
                    "universe_id": str(universe),
                    "decision_time": pd.Timestamp(decision),
                    "omitted_pair": omitted,
                    "replacement_pair": replacement,
                    "replacement_rank": replacement_rank,
                    "replacement_ready": ready,
                    "reason": reason,
                }
            )
    return pd.DataFrame.from_records(
        rows,
        columns=REPLACEMENT_FIELDS,
    )


def coverage_fraction(
    memberships: pd.DataFrame,
    *,
    generated_pairs: frozenset[str],
) -> tuple[float, int, int]:
    top6 = memberships.loc[_bool_series(memberships["top6"], name="top6")]
    total = len(top6)
    if total == 0:
        raise A3AMembershipError("Top-6 membership slots are empty")
    covered = int(top6["pair"].astype(str).isin(generated_pairs).sum())
    return covered / total, covered, total


def historical_gap_rows(
    memberships: pd.DataFrame,
    *,
    historical_pairs: frozenset[str],
) -> pd.DataFrame:
    selected = memberships.loc[memberships["pair"].astype(str).isin(historical_pairs)].copy()
    if selected.empty:
        return pd.DataFrame(
            columns=(
                "pair",
                "universe_id",
                "affected_decisions",
                "first_decision",
                "last_decision",
                "resolution",
            )
        )
    rows: list[dict[str, object]] = []
    for (pair, universe), group in selected.groupby(
        ["pair", "universe_id"],
        sort=True,
    ):
        times = pd.to_datetime(
            group["decision_time"],
            utc=True,
            errors="raise",
        )
        rows.append(
            {
                "pair": str(pair),
                "universe_id": str(universe),
                "affected_decisions": int(times.nunique()),
                "first_decision": times.min(),
                "last_decision": times.max(),
                "resolution": "HISTORICAL_SOURCE_REQUIRED",
            }
        )
    return pd.DataFrame.from_records(rows)


__all__ = [
    "A3AMembershipError",
    "ENTRY_RANK",
    "EXPECTED_DECISIONS",
    "MEMBERSHIP_FIELDS",
    "MembershipBuild",
    "PRIMARY_START",
    "REPLACEMENT_FIELDS",
    "RETENTION_RANK",
    "SEALED_CUTOFF",
    "apply_hysteresis",
    "build_replacement_ledger",
    "coverage_fraction",
    "historical_gap_rows",
    "inventory_maps",
    "materialize_committed_membership",
    "normalize_ranking",
    "validate_membership",
]
