from __future__ import annotations

from ams_v5_native_support import panel, row, run


def test_end_of_fold_is_an_explicit_fill_and_leaves_no_position() -> None:
    result = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, open_price=100, high=103, low=96, close=102),
        )
    )
    assert result.fills[-1].fill_type == "END_OF_FOLD_EXIT"
    assert result.open_positions_after_fold == 0
    assert result.status == "PASS"
    assert result.reconciliation.status == "PASS"


def test_candidate_and_fill_ids_are_unique_and_order_is_deterministic() -> None:
    frame = panel(
        row(0, symbol="BBB", family="SHALLOW_PULLBACK_RECLAIM", score=80),
        row(0, symbol="AAA", family="SHALLOW_PULLBACK_RECLAIM", score=80),
        row(1, symbol="BBB"),
        row(1, symbol="AAA"),
    )
    first = run(frame, fold_id="ORDER")
    second = run(frame, fold_id="ORDER")
    assert [fill.symbol for fill in first.fills[:2]] == ["AAA", "BBB"]
    assert [fill.fill_id for fill in first.fills] == [fill.fill_id for fill in second.fills]
    assert len({item.candidate_id for item in first.candidates}) == len(first.candidates)
    assert len({item.fill_id for item in first.fills}) == len(first.fills)


def test_venue_exit_is_explicit_and_precedes_later_activity() -> None:
    until = row(2)["bar_open_time"]
    result = run(
        panel(
            row(
                0,
                family="SHALLOW_PULLBACK_RECLAIM",
                overrides={"tradable_until": until},
            ),
            row(1, overrides={"tradable_until": until}),
            row(2, overrides={"tradable_until": until}),
        )
    )
    assert result.fills[-1].fill_type == "VENUE_EXIT"
    assert result.open_positions_after_fold == 0
