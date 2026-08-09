from __future__ import annotations

import numpy as np
import pandas as pd

from spotbot.research.rd36_cross_venue_flow_state import (
    FAMILY_ACCELERATING_FLOW_RISK_OFF,
    FAMILY_BUY_FLOW_EXHAUSTION,
    FAMILY_CONSENSUS_FLOW_RISK_OFF,
    FAMILY_ORDER,
    FAMILY_SELL_FLOW_EXHAUSTION_CONTROL,
    HORIZONS,
    KNOWN_GAP,
    market_state_frame,
    prepare_symbol_features,
    state_entry_ledger,
    target_markout,
    target_open_lookup,
    validate_constants,
)


def source_frame(
    *,
    periods: int = 500,
    gap: pd.Timestamp | None = None,
    imbalance: float = 0.2,
) -> pd.DataFrame:
    index = pd.date_range(
        "2023-03-10T00:00:00Z",
        periods=periods,
        freq="h",
        tz="UTC",
    )
    if gap is not None:
        index = index[index != gap]
    quote = np.full(len(index), 1000.0)
    taker = quote * (imbalance + 1.0) / 2.0
    return pd.DataFrame(
        {
            "timestamp": index,
            "quote_volume": quote,
            "number_of_trades": np.arange(len(index)) + 1000.0,
            "taker_buy_quote_volume": taker,
        }
    )


def test_constants_are_frozen() -> None:
    validate_constants()
    assert HORIZONS == (6, 24, 72)
    assert FAMILY_ORDER == (
        FAMILY_CONSENSUS_FLOW_RISK_OFF,
        FAMILY_ACCELERATING_FLOW_RISK_OFF,
        FAMILY_BUY_FLOW_EXHAUSTION,
        FAMILY_SELL_FLOW_EXHAUSTION_CONTROL,
    )


def test_pressure_resets_after_gap() -> None:
    raw = source_frame(gap=KNOWN_GAP, imbalance=-0.2)
    features = prepare_symbol_features(raw, symbol="BTCUSDT")

    after = features.loc[features["timestamp"] > KNOWN_GAP].reset_index(drop=True)
    assert after.loc[:22, "pressure_24"].isna().all()
    assert pd.notna(after.loc[23, "pressure_24"])
    assert after.loc[:70, "pressure_72"].isna().all()
    assert pd.notna(after.loc[71, "pressure_72"])


def test_imbalance_formula_is_exact_for_constant_input() -> None:
    raw = source_frame(periods=100, imbalance=0.30)
    features = prepare_symbol_features(raw, symbol="ETHUSDT")
    ready = features["pressure_24"].dropna()
    assert len(ready)
    assert np.allclose(ready.to_numpy(), 0.30)


def test_market_state_definitions() -> None:
    btc = source_frame(periods=260, imbalance=-0.20)
    eth = source_frame(periods=260, imbalance=-0.20)
    market = market_state_frame(btc, eth)
    ready = market["btc_pressure_24"].notna() & market["eth_pressure_24"].notna()
    assert market.loc[ready, FAMILY_CONSENSUS_FLOW_RISK_OFF].all()
    assert not market.loc[ready, FAMILY_BUY_FLOW_EXHAUSTION].any()


def test_state_ledger_uses_false_to_true_entries_only() -> None:
    market = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2023-01-01T00:00:00Z",
                periods=4,
                freq="h",
                tz="UTC",
            ),
            FAMILY_CONSENSUS_FLOW_RISK_OFF: [False, True, True, False],
            FAMILY_ACCELERATING_FLOW_RISK_OFF: [False, False, False, False],
            FAMILY_BUY_FLOW_EXHAUSTION: [False, False, False, False],
            FAMILY_SELL_FLOW_EXHAUSTION_CONTROL: [False, False, False, False],
            "btc_pressure_24": [0.0, -0.2, -0.2, 0.0],
            "eth_pressure_24": [0.0, -0.2, -0.2, 0.0],
            "market_pressure_6": [0.0, -0.2, -0.2, 0.0],
            "market_pressure_24": [0.0, -0.2, -0.2, 0.0],
            "market_pressure_72": [0.0, -0.2, -0.2, 0.0],
            "market_acceleration": [0.0, 0.0, 0.0, 0.0],
            "market_participation_shock": [0.0, 0.0, 0.0, 0.0],
            "flow_dispersion_24": [0.0, 0.0, 0.0, 0.0],
            "participation_elevated": [False, False, False, False],
        }
    )
    ledger = state_entry_ledger(market)
    assert len(ledger) == 1
    assert ledger.iloc[0]["source_time"] == pd.Timestamp("2023-01-01T01:00:00Z")
    assert ledger.iloc[0]["reference_time"] == pd.Timestamp("2023-01-01T02:00:00Z")


def test_target_markout_uses_kucoin_open_at_reference_and_exit() -> None:
    target = pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2023-01-01T00:00:00Z",
                periods=40,
                freq="h",
                tz="UTC",
            ),
            "open": np.arange(40, dtype=float) + 100.0,
        }
    )
    lookup = target_open_lookup(target)
    result = target_markout(
        pair="BTC-USDT",
        reference_time=pd.Timestamp("2023-01-01T05:00:00Z"),
        horizon_hours=6,
        lookup=lookup,
    )
    assert result is not None
    assert result["entry_price"] == 105.0
    assert result["exit_price"] == 111.0
    assert np.isclose(result["forward_return"], 111.0 / 105.0 - 1.0)
