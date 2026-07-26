from __future__ import annotations

import pytest
from ams_v5_native_support import panel, row, run

from spotbot.research.ams_v5_native_engine import (
    V5NativeError,
    reconcile_native_fold_from_fills,
)


def test_fill_ledger_rebuilds_cash_quantity_fees_turnover_and_pnl() -> None:
    result = run(
        panel(
            row(0, family="SHALLOW_PULLBACK_RECLAIM"),
            row(1, open_price=100, high=103, low=96, close=102),
            row(2, open_price=102, high=104, low=94, close=95),
        )
    )
    rebuilt = reconcile_native_fold_from_fills(
        result.fills,
        initial_capital=result.initial_capital,
        engine_final_cash=result.final_cash,
        engine_fees=result.reconciliation.fees,
        engine_turnover=result.reconciliation.turnover,
        engine_realised_pnl=sum(trade.realised_pnl for trade in result.trades),
    )
    assert rebuilt.status == "PASS"
    assert rebuilt.open_quantities == {}
    assert rebuilt.final_cash == pytest.approx(result.final_cash)


def test_reconciliation_detects_tampered_cash_chain() -> None:
    result = run(
        panel(row(0, family="SHALLOW_PULLBACK_RECLAIM"), row(1), row(2, low=94))
    )
    tampered = list(result.fills)
    object.__setattr__(tampered[-1], "cash_after", tampered[-1].cash_after + 1)
    with pytest.raises(V5NativeError, match="cash_after"):
        reconcile_native_fold_from_fills(tampered, initial_capital=100_000)
