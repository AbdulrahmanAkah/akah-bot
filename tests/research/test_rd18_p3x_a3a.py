from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd18_p3x_a3a_membership import (
    EXPECTED_DECISIONS,
    A3AMembershipError,
    apply_hysteresis,
    build_replacement_ledger,
    coverage_fraction,
    historical_gap_rows,
    inventory_maps,
    materialize_committed_membership,
    normalize_ranking,
)


def dates() -> pd.DatetimeIndex:
    return pd.date_range(
        "2019-04-01",
        periods=EXPECTED_DECISIONS,
        freq="7D",
        tz="UTC",
    )


def inventory() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "canonical_product_id": ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
            "pair": [f"{value}-USDT" for value in "ABCDEFGHI"],
            "variant_c2_presence": [True] * 9,
            "variant_d2_presence": [True] * 8 + [False],
        }
    )


def ranking(
    *,
    universe: str = "C2",
    count: int = 9,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for decision in dates():
        for rank, asset in enumerate("ABCDEFGHI"[:count], start=1):
            rows.append(
                {
                    "decision_time": decision,
                    "canonical_asset_id": asset,
                    "rank": rank,
                    "universe_id": universe,
                }
            )
    return pd.DataFrame.from_records(rows)


def test_inventory_maps_are_strict_subsets() -> None:
    mapping, c2, d2 = inventory_maps(inventory())
    assert mapping["A"] == "A-USDT"
    assert len(c2) == 9
    assert len(d2) == 8
    assert d2.issubset(c2)


def test_normalize_ranking_maps_pairs() -> None:
    mapping, c2, _ = inventory_maps(inventory())
    normalized = normalize_ranking(
        ranking().drop(columns=["universe_id"]),
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2,
    )
    assert normalized["pair"].iloc[0] == "A-USDT"
    assert normalized["rank"].max() == 9


def test_d2_recomputes_rank_after_filtering() -> None:
    mapping, _, d2 = inventory_maps(inventory())
    source = ranking().drop(columns=["universe_id"])
    normalized = normalize_ranking(
        source,
        mapping=mapping,
        universe_id="D2",
        allowed_pairs=d2,
        recompute_rank=True,
    )
    first = normalized.loc[normalized["decision_time"] == dates()[0]]
    assert first["rank"].tolist() == list(range(1, 9))


def test_hysteresis_materializes_all_301_decisions() -> None:
    mapping, c2, _ = inventory_maps(inventory())
    normalized = normalize_ranking(
        ranking().drop(columns=["universe_id"]),
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2,
    )
    built = apply_hysteresis(
        normalized,
        universe_id="C2",
        source="TEST",
    )
    assert built.membership["decision_time"].nunique() == 301
    assert built.membership.groupby("decision_time").size().max() <= 8


def test_hysteresis_retains_rank_seven_incumbent() -> None:
    source = ranking().drop(columns=["universe_id"])
    second = dates()[1]
    mask = (source["decision_time"] == second) & (source["canonical_asset_id"] == "A")
    source.loc[mask, "rank"] = 7
    mask_g = (source["decision_time"] == second) & (source["canonical_asset_id"] == "G")
    source.loc[mask_g, "rank"] = 1
    source = source.sort_values(
        ["decision_time", "rank", "canonical_asset_id"],
        kind="stable",
    )
    mapping, c2, _ = inventory_maps(inventory())
    normalized = normalize_ranking(
        source,
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2,
    )
    built = apply_hysteresis(
        normalized,
        universe_id="C2",
        source="TEST",
    )
    second_members = set(
        built.membership.loc[
            built.membership["decision_time"] == second,
            "pair",
        ]
    )
    assert "A-USDT" in second_members


def test_committed_membership_requires_301_decisions() -> None:
    mapping, _, _ = inventory_maps(inventory())
    committed = ranking(count=6).drop(columns=["universe_id"])
    committed["pair"] = committed["canonical_asset_id"].map(mapping)
    committed["member"] = True
    built = materialize_committed_membership(
        committed,
        mapping=mapping,
        universe_id="E2",
        source="TEST",
    )
    assert built.membership["decision_time"].nunique() == 301


def test_coverage_counts_top6_slots() -> None:
    mapping, c2, _ = inventory_maps(inventory())
    normalized = normalize_ranking(
        ranking().drop(columns=["universe_id"]),
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2,
    )
    membership = apply_hysteresis(
        normalized,
        universe_id="C2",
        source="TEST",
    ).membership
    fraction, covered, total = coverage_fraction(
        membership,
        generated_pairs=frozenset({"A-USDT", "B-USDT", "C-USDT"}),
    )
    assert covered == EXPECTED_DECISIONS * 3
    assert total == EXPECTED_DECISIONS * 6
    assert fraction == 0.5


def test_replacement_uses_highest_ranked_available_nonmember() -> None:
    mapping, c2, _ = inventory_maps(inventory())
    normalized = normalize_ranking(
        ranking().drop(columns=["universe_id"]),
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2,
    )
    membership = apply_hysteresis(
        normalized,
        universe_id="C2",
        source="TEST",
    ).membership
    ledger = build_replacement_ledger(
        membership,
        normalized,
        ready_pairs=c2,
        excluded_pairs=frozenset(),
    )
    first = ledger.iloc[0]
    assert first["replacement_pair"] == "G-USDT"
    assert bool(first["replacement_ready"]) is True


def test_historical_gap_rows_are_explicit() -> None:
    mapping, c2, _ = inventory_maps(inventory())
    normalized = normalize_ranking(
        ranking().drop(columns=["universe_id"]),
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2,
    )
    membership = apply_hysteresis(
        normalized,
        universe_id="C2",
        source="TEST",
    ).membership
    rows = historical_gap_rows(
        membership,
        historical_pairs=frozenset({"A-USDT"}),
    )
    assert len(rows) == 1
    assert rows.iloc[0]["affected_decisions"] == 301


def test_missing_decision_fails_closed() -> None:
    mapping, c2, _ = inventory_maps(inventory())
    source = ranking().drop(columns=["universe_id"])
    source = source.loc[source["decision_time"] != dates()[-1]]
    normalized = normalize_ranking(
        source,
        mapping=mapping,
        universe_id="C2",
        allowed_pairs=c2,
    )
    with pytest.raises(A3AMembershipError, match="expected 301"):
        apply_hysteresis(
            normalized,
            universe_id="C2",
            source="TEST",
        )
