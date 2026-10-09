from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pandas.testing as pdt

from spotbot.research import rd27_lifecycle_replay as rd27
from spotbot.research.rd26_exit_architecture import DATA_START, FAMILY_MOMENTUM_BREAKOUT
from spotbot.research.rd27_adaptive_lifecycle import RISK_ON
from spotbot.research.rd27_later_trigger_v2_native_hook import (
    NativeV2ShadowHook,
    contract_summary,
)


@dataclass
class RecorderHook:
    sync_calls: int = 0
    observe_calls: int = 0
    close_calls: int = 0

    def sync_native_position(self, **kwargs):
        assert kwargs["pair"] == "AAA-USDT"
        self.sync_calls += 1

    def observe_position(self, **kwargs):
        assert kwargs["pair"] == "AAA-USDT"
        self.observe_calls += 1

    def close_position(self, **kwargs):
        assert kwargs["pair"] == "AAA-USDT"
        self.close_calls += 1


@dataclass
class FakeNativePosition:
    entry_time: pd.Timestamp
    entry_price: float
    max_exit_time: pd.Timestamp


def asset_frame(hours: int = 200) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": DATA_START + pd.Timedelta(hours=hour),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1_000_000.0,
                "trailing_24h_quote_turnover_proxy": 100_000_000.0,
            }
            for hour in range(hours)
        ]
    )


def state_frame(hours: int = 200) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [
                DATA_START + pd.Timedelta(hours=hour)
                for hour in range(hours)
            ],
            "market_state": [RISK_ON] * hours,
            "state_ready": [True] * hours,
        }
    )


def event() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": DATA_START,
                "pair": "AAA-USDT",
                "membership_rank": 1,
                "period_id": "ROBUSTNESS_2022",
                "support_families": FAMILY_MOMENTUM_BREAKOUT,
                "atr24_at_signal": 1.0,
            }
        ]
    )


def native_kwargs() -> dict:
    return {
        "policy_id": rd27.STATIC_EXIT_STATE_ROUTER,
        "portfolio_id": "TEST",
        "universe_id": "C2",
        "cost_multiplier": 1.0,
        "events": event(),
        "frames": {"AAA-USDT": asset_frame()},
        "state_frame": state_frame(),
        "replay_start": DATA_START,
        "replay_cutoff": DATA_START + pd.Timedelta(hours=180),
    }


def primitive_rows():
    return [
        {
            "symbol": "AAA-USDT",
            "source_exchange": "KUCOIN",
            "source_symbol": "AAA-USDT",
            "bar_open_time": DATA_START,
            "bar_close_time": DATA_START + pd.Timedelta(hours=4),
            "open": 101.0,
            "high": 103.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 1.0,
        },
        {
            "symbol": "AAA-USDT",
            "source_exchange": "KUCOIN",
            "source_symbol": "AAA-USDT",
            "bar_open_time": DATA_START + pd.Timedelta(hours=4),
            "bar_close_time": DATA_START + pd.Timedelta(hours=8),
            "open": 103.0,
            "high": 106.0,
            "low": 101.0,
            "close": 105.0,
            "volume": 1.0,
        },
        {
            "symbol": "AAA-USDT",
            "source_exchange": "KUCOIN",
            "source_symbol": "AAA-USDT",
            "bar_open_time": DATA_START + pd.Timedelta(hours=8),
            "bar_close_time": DATA_START + pd.Timedelta(hours=12),
            "open": 101.0,
            "high": 103.0,
            "low": 98.0,
            "close": 102.0,
            "volume": 1.0,
        },
    ]


def test_contract_is_observational_only():
    summary = contract_summary()
    assert summary["default_enabled"] is False
    assert summary["actual_exit_authority"] is False
    assert summary["native_position_mutation"] is False
    assert summary["parameter_count"] == 0


def test_sidecar_independently_preserves_v2_semantics():
    hook = NativeV2ShadowHook(
        primitive_rows(),
        symbol_bindings={"AAA-USDT": "AAA-USDT"},
    )
    native = FakeNativePosition(
        entry_time=DATA_START,
        entry_price=102.0,
        max_exit_time=DATA_START + pd.Timedelta(hours=12),
    )
    hook.sync_native_position(
        pair="AAA-USDT",
        position=native,
        fallback_observed_through=native.max_exit_time,
    )
    hook.observe_position(
        pair="AAA-USDT",
        decision_time=DATA_START + pd.Timedelta(hours=12),
    )
    diagnostics = hook.diagnostics()
    assert diagnostics["memory_count"] == 1
    assert diagnostics["candidate_count"] == 1
    assert diagnostics["actual_exit_authority"] is False


def test_native_explicit_none_is_exact_backward_compatible():
    baseline = rd27.replay_lifecycle_policy(**native_kwargs())
    explicit_none = rd27.replay_lifecycle_policy(
        **native_kwargs(),
        later_trigger_v2_shadow_hook=None,
    )
    for left, right in zip(baseline[:2], explicit_none[:2], strict=True):
        pdt.assert_frame_equal(left, right, check_exact=True)
    assert baseline[2] == explicit_none[2]
    assert baseline[3] == explicit_none[3]


def test_native_recorder_hook_is_exact_output_parity():
    baseline = rd27.replay_lifecycle_policy(**native_kwargs())
    recorder = RecorderHook()
    enabled = rd27.replay_lifecycle_policy(
        **native_kwargs(),
        later_trigger_v2_shadow_hook=recorder,
    )
    for left, right in zip(baseline[:2], enabled[:2], strict=True):
        pdt.assert_frame_equal(left, right, check_exact=True)
    assert baseline[2] == enabled[2]
    assert baseline[3] == enabled[3]
    assert recorder.sync_calls == 1
    assert recorder.observe_calls > 0
    assert recorder.close_calls == 1
