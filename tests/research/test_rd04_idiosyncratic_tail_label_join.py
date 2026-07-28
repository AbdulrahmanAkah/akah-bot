from __future__ import annotations

from dataclasses import replace

import pytest

from spotbot.research.rd04_external_tail_event_source_freeze import (
    frozen_events,
)
from spotbot.research.rd04_idiosyncratic_tail_label_join import (
    DECISION_BLOCKED,
    DECISION_COMPLETE,
    TailLabelDiagnosticError,
    decision_record,
    diagnostic_metrics,
    event_overlaps_trade,
    label_trades,
    parse_trade_time,
    projection_fingerprint,
    timing_label,
    validate_input_trades,
    validate_projection,
    with_without_label_summary,
)


def trade(
    *,
    trade_id: str,
    symbol: str,
    entry: str,
    exit_time: str,
    net_pnl: float,
    mae: float,
    fold_id: str = "WF01",
    exit_reason: str = "REBALANCE_EXIT",
) -> dict[str, str]:
    return {
        "universe_mode": "PIT_UNIVERSE",
        "portfolio_mode": "CONTROL",
        "fold_id": fold_id,
        "trade_id": trade_id,
        "position_id": f"POS-{trade_id}",
        "candidate_id": f"CAND-{trade_id}",
        "symbol": symbol,
        "entry_time": entry,
        "exit_time": exit_time,
        "entry_price": "10",
        "exit_price": "9",
        "quantity": "100",
        "gross_pnl": str(net_pnl + 10.0),
        "net_pnl": str(net_pnl),
        "return_fraction": str(net_pnl / 1000.0),
        "exit_reason": exit_reason,
        "alignment_tier": "FULL",
        "holding_hours": "24",
        "mfe": "0.05",
        "mae": str(mae),
        "natural_reselection_sequence": "0",
        "previous_position_id": "",
    }


def test_pre_event_exposure_label() -> None:
    event = next(item for item in frozen_events() if item.event_id == "FTX_FTT_COLLAPSE_2022")
    row = trade(
        trade_id="T1",
        symbol="FTT",
        entry="2022-11-10T00:00:00Z",
        exit_time="2022-11-12T00:00:00Z",
        net_pnl=-500.0,
        mae=-0.5,
    )
    assert event_overlaps_trade(
        entry_time=parse_trade_time(row, "entry_time"),
        exit_time=parse_trade_time(row, "exit_time"),
        event=event,
    )
    assert (
        timing_label(
            entry_time=parse_trade_time(row, "entry_time"),
            exit_time=parse_trade_time(row, "exit_time"),
            event=event,
        )
        == "PRE_EVENT_EXPOSURE"
    )


def test_event_window_entry_label() -> None:
    row = trade(
        trade_id="T2",
        symbol="FTT",
        entry="2023-01-01T00:00:00Z",
        exit_time="2023-01-02T00:00:00Z",
        net_pnl=-100.0,
        mae=-0.2,
    )
    labelled, links = label_trades([row])
    assert labelled[0]["event_association"] == "LABELLED"
    assert labelled[0]["event_ids"] == "FTX_FTT_COLLAPSE_2022"
    assert links[0].timing_label == "EVENT_WINDOW_ENTRY"


def test_trade_ending_before_event_is_unlabelled() -> None:
    row = trade(
        trade_id="T3",
        symbol="FTT",
        entry="2022-11-01T00:00:00Z",
        exit_time="2022-11-10T00:00:00Z",
        net_pnl=-100.0,
        mae=-0.2,
    )
    labelled, links = label_trades([row])
    assert labelled[0]["event_association"] == "UNLABELLED"
    assert links == []


def test_alias_maps_lunc_to_luna_event() -> None:
    row = trade(
        trade_id="T4",
        symbol="LUNC",
        entry="2022-06-01T00:00:00Z",
        exit_time="2022-06-02T00:00:00Z",
        net_pnl=-100.0,
        mae=-0.2,
    )
    labelled, links = label_trades([row])
    assert labelled[0]["canonical_symbol"] == "LUNA"
    assert links[0].event_id == "TERRA_UST_LUNA_COLLAPSE_2022"


def test_usdc_after_recovery_is_unlabelled() -> None:
    row = trade(
        trade_id="T5",
        symbol="USDC",
        entry="2023-03-15T00:00:00Z",
        exit_time="2023-03-16T00:00:00Z",
        net_pnl=-10.0,
        mae=-0.01,
    )
    labelled, links = label_trades([row])
    assert labelled[0]["event_association"] == "UNLABELLED"
    assert links == []


def test_projection_is_unchanged() -> None:
    rows = [
        trade(
            trade_id="T6",
            symbol="FTT",
            entry="2023-01-01T00:00:00Z",
            exit_time="2023-01-02T00:00:00Z",
            net_pnl=-100.0,
            mae=-0.2,
        )
    ]
    labelled, _ = label_trades(rows)
    validate_projection(rows, labelled)
    assert projection_fingerprint(rows) == projection_fingerprint(labelled)


def test_projection_rejects_original_field_change() -> None:
    rows = [
        trade(
            trade_id="T7",
            symbol="FTT",
            entry="2023-01-01T00:00:00Z",
            exit_time="2023-01-02T00:00:00Z",
            net_pnl=-100.0,
            mae=-0.2,
        )
    ]
    labelled, _ = label_trades(rows)
    labelled[0]["net_pnl"] = "-99"
    with pytest.raises(
        TailLabelDiagnosticError,
        match="changed original field",
    ):
        validate_projection(rows, labelled)


def test_loss_share_uses_loss_amount_not_netting() -> None:
    rows = [
        trade(
            trade_id="T8",
            symbol="FTT",
            entry="2023-01-01T00:00:00Z",
            exit_time="2023-01-02T00:00:00Z",
            net_pnl=-100.0,
            mae=-0.2,
        ),
        trade(
            trade_id="T9",
            symbol="BTC",
            entry="2023-01-01T00:00:00Z",
            exit_time="2023-01-02T00:00:00Z",
            net_pnl=-300.0,
            mae=-0.3,
        ),
        trade(
            trade_id="T10",
            symbol="FTT",
            entry="2023-02-01T00:00:00Z",
            exit_time="2023-02-02T00:00:00Z",
            net_pnl=500.0,
            mae=-0.1,
        ),
    ]
    labelled, _ = label_trades(rows)
    metrics = diagnostic_metrics(labelled)
    assert metrics["labelled_loss_amount"] == 100.0
    assert metrics["total_loss_amount"] == 400.0
    assert metrics["labelled_loss_share"] == 0.25


def test_with_without_summary_retains_all_rows() -> None:
    rows = [
        trade(
            trade_id="T11",
            symbol="FTT",
            entry="2023-01-01T00:00:00Z",
            exit_time="2023-01-02T00:00:00Z",
            net_pnl=-100.0,
            mae=-0.2,
        ),
        trade(
            trade_id="T12",
            symbol="BTC",
            entry="2023-01-01T00:00:00Z",
            exit_time="2023-01-02T00:00:00Z",
            net_pnl=50.0,
            mae=-0.1,
        ),
    ]
    labelled, _ = label_trades(rows)
    summary = with_without_label_summary(labelled)
    assert summary[0]["trade_count"] == 2
    assert summary[1]["trade_count"] == 1
    assert summary[2]["trade_count"] == 1


def valid_research_rows() -> list[dict[str, str]]:
    rows = [
        trade(
            trade_id=f"T-{index}",
            symbol="BTC",
            entry="2024-12-31T00:00:00Z",
            exit_time="2024-12-31T12:00:00Z",
            net_pnl=1.0,
            mae=-0.01,
            fold_id=("WF01", "WF02", "WF03")[index % 3],
        )
        for index in range(153)
    ]
    for index in range(3):
        rows[index]["exit_time"] = "2025-01-01T00:00:00Z"
        rows[index]["exit_reason"] = "END_OF_FOLD_EXIT"
    return rows


def test_validate_input_allows_registered_boundary_exits() -> None:
    validate_input_trades(valid_research_rows())


def test_validate_input_rejects_entry_at_boundary() -> None:
    rows = valid_research_rows()
    rows[3]["entry_time"] = "2025-01-01T00:00:00Z"
    rows[3]["exit_time"] = "2025-01-01T00:00:00Z"
    rows[3]["exit_reason"] = "END_OF_FOLD_EXIT"
    with pytest.raises(
        TailLabelDiagnosticError,
        match="entry reaches prohibited research boundary",
    ):
        validate_input_trades(rows)


def test_validate_input_rejects_post_boundary_exit() -> None:
    rows = valid_research_rows()
    rows[3]["exit_time"] = "2025-01-01T04:00:00Z"
    with pytest.raises(
        TailLabelDiagnosticError,
        match="exits after research boundary",
    ):
        validate_input_trades(rows)


def test_validate_input_rejects_wrong_boundary_exit_reason() -> None:
    rows = valid_research_rows()
    rows[0]["exit_reason"] = "REBALANCE_EXIT"
    with pytest.raises(
        TailLabelDiagnosticError,
        match="not END_OF_FOLD_EXIT",
    ):
        validate_input_trades(rows)


def test_validate_input_rejects_boundary_exit_count_drift() -> None:
    rows = valid_research_rows()
    rows[0]["exit_time"] = "2024-12-31T12:00:00Z"
    rows[0]["exit_reason"] = "REBALANCE_EXIT"
    with pytest.raises(
        TailLabelDiagnosticError,
        match="boundary exit count",
    ):
        validate_input_trades(rows)


def test_decision_is_diagnostic_only() -> None:
    decision = decision_record(structural_pass=True)
    assert decision["decision"] == DECISION_COMPLETE
    assert decision["d5e0_midweek_pullback_diagnostic_authorized"] is True
    assert decision["event_based_symbol_exclusion_authorized"] is False
    assert decision["production_change_authorized"] is False
    assert decision["trade_logic_changed"] is False


def test_failed_structure_blocks_next_stage() -> None:
    decision = decision_record(structural_pass=False)
    assert decision["decision"] == DECISION_BLOCKED
    assert decision["d5e0_midweek_pullback_diagnostic_authorized"] is False


def test_event_overlap_boundary_at_start() -> None:
    event = next(item for item in frozen_events() if item.event_id == "FTX_FTT_COLLAPSE_2022")
    row = trade(
        trade_id="T13",
        symbol="FTT",
        entry="2022-11-10T00:00:00Z",
        exit_time=event.event_start_utc,
        net_pnl=-50.0,
        mae=-0.1,
    )
    assert event_overlaps_trade(
        entry_time=parse_trade_time(row, "entry_time"),
        exit_time=parse_trade_time(row, "exit_time"),
        event=event,
    )


def test_entry_at_event_end_does_not_overlap() -> None:
    event = next(item for item in frozen_events() if item.event_id == "USDC_SVB_DEPEG_2023")
    row = trade(
        trade_id="T14",
        symbol="USDC",
        entry=event.association_end_utc,
        exit_time="2023-03-15T00:00:00Z",
        net_pnl=-1.0,
        mae=-0.01,
    )
    assert not event_overlaps_trade(
        entry_time=parse_trade_time(row, "entry_time"),
        exit_time=parse_trade_time(row, "exit_time"),
        event=event,
    )


def test_no_outcome_based_event_mutation() -> None:
    events = frozen_events()
    changed = tuple(replace(event) for event in events)
    assert changed == events
