from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import spotbot.research.ams_v2_f01_trend_momentum as f01
from spotbot.research.ams_v2_f01_trend_momentum import (
    F01_ENGINE_EXECUTION_STATUS,
    F01_ENGINE_VERSION,
    F01TrendMomentumConfigurationError,
    F01TrendMomentumDataError,
    F01TrendMomentumPolicy,
    assert_f01_core_not_trial_executable,
    build_f01_trend_momentum_signals,
    run_f01_trend_momentum_engine_core,
)
from spotbot.research.ams_v2_walk_forward_orchestrator import (
    load_json_object,
)

ROOT = Path(__file__).resolve().parents[1]

LEDGER_PATH = (
    ROOT
    / "reports/research/"
    "ams-v2-experiment-ledger-v1.json"
)


def experiment_ledger() -> dict[str, Any]:
    return load_json_object(
        LEDGER_PATH
    )


def f01_configurations() -> list[dict[str, Any]]:
    configurations = experiment_ledger()[
        "alpha_configurations"
    ]

    return [
        copy.deepcopy(configuration)
        for configuration in configurations
        if configuration["family_id"]
        == "AMS-V2-F01"
    ]


def policy() -> F01TrendMomentumPolicy:
    return (
        F01TrendMomentumPolicy
        .from_registered_configuration(
            f01_configurations()[0],
            research_start=datetime(
                2022,
                1,
                1,
                tzinfo=UTC,
            ),
            research_end_exclusive=datetime(
                2023,
                1,
                1,
                tzinfo=UTC,
            ),
        )
    )


def test_contract_and_all_16_translations() -> None:
    assert F01_ENGINE_VERSION == (
        "AMS_V2_F01_TREND_MOMENTUM_ENGINE_CORE_V1"
    )

    assert F01_ENGINE_EXECUTION_STATUS == (
        "CORE_REGISTERED_NOT_TRIAL_EXECUTABLE"
    )

    assert_f01_core_not_trial_executable()

    configurations = f01_configurations()

    assert len(configurations) == 16

    translated = [
        F01TrendMomentumPolicy
        .from_registered_configuration(
            configuration,
            research_start=datetime(
                2021,
                7,
                20,
                tzinfo=UTC,
            ),
            research_end_exclusive=datetime(
                2025,
                1,
                1,
                tzinfo=UTC,
            ),
        )
        for configuration in configurations
    ]

    assert {
        item.breakout_lookback_days
        for item in translated
    } == {
        20,
        55,
    }

    assert {
        item.momentum_lookback_days
        for item in translated
    } == {
        20,
        60,
    }

    assert {
        item.trailing_stop_atr
        for item in translated
    } == {
        3.0,
        4.0,
    }

    assert {
        item.turnover_expansion_minimum
        for item in translated
    } == {
        1.2,
        1.5,
    }

    for translated_policy in translated:
        translated_policy.to_momentum_policy()
        translated_policy.to_breakout_policy()


def test_non_f01_configuration_is_rejected() -> None:
    configuration = next(
        item
        for item in experiment_ledger()[
            "alpha_configurations"
        ]
        if item["family_id"]
        == "AMS-V2-F02"
    )

    with pytest.raises(
        F01TrendMomentumConfigurationError,
        match="not registered as AMS-V2-F01",
    ):
        (
            F01TrendMomentumPolicy
            .from_registered_configuration(
                configuration,
                research_start=datetime(
                    2022,
                    1,
                    1,
                    tzinfo=UTC,
                ),
                research_end_exclusive=datetime(
                    2023,
                    1,
                    1,
                    tzinfo=UTC,
                ),
            )
        )


def test_locked_2025_access_is_rejected() -> None:
    with pytest.raises(
        F01TrendMomentumConfigurationError,
        match="locked 2025",
    ):
        F01TrendMomentumPolicy(
            research_start=datetime(
                2022,
                1,
                1,
                tzinfo=UTC,
            ),
            research_end_exclusive=datetime(
                2025,
                1,
                2,
                tzinfo=UTC,
            ),
            breakout_lookback_days=20,
            initial_stop_atr=2.5,
            maximum_holding_days=60,
            maximum_positions=2,
            momentum_lookback_days=20,
            ranking_maximum=8,
            trailing_stop_atr=3.0,
            transaction_cost_fraction=0.002,
            turnover_expansion_minimum=1.2,
        )


def test_composite_candidate_requires_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = datetime(
        2022,
        2,
        1,
        tzinfo=UTC,
    )

    momentum = pd.DataFrame(
        {
            "snapshot_time": [
                snapshot,
                snapshot,
                snapshot,
            ],
            "symbol": [
                "BTC/USDT",
                "ETH/USDT",
                "SOL/USDT",
            ],
            "candidate": [
                True,
                False,
                True,
            ],
            "signal_score": [
                4.0,
                3.0,
                2.0,
            ],
        }
    )

    breakout = pd.DataFrame(
        {
            "snapshot_time": [
                snapshot,
                snapshot,
                snapshot,
            ],
            "symbol": [
                "BTC/USDT",
                "ETH/USDT",
                "SOL/USDT",
            ],
            "candidate": [
                True,
                True,
                False,
            ],
            "rank_within_snapshot": [
                1,
                2,
                3,
            ],
            "turnover_expansion_h01": [
                1.5,
                1.4,
                1.3,
            ],
        }
    )

    monkeypatch.setattr(
        f01,
        "build_momentum_reacceleration_signals",
        lambda history, ranking, *, policy: (
            momentum.copy()
        ),
    )

    monkeypatch.setattr(
        f01,
        "build_volatility_breakout_signals",
        lambda history, ranking, *, policy: (
            breakout.copy()
        ),
    )

    result = build_f01_trend_momentum_signals(
        pd.DataFrame(),
        pd.DataFrame(),
        policy=policy(),
    )

    observed = {
        row.symbol: bool(row.candidate)
        for row in result.itertuples()
    }

    assert observed == {
        "BTC/USDT": True,
        "ETH/USDT": False,
        "SOL/USDT": False,
    }

    score = result.loc[
        result["symbol"] == "BTC/USDT",
        "f01_composite_signal_score",
    ].iloc[0]

    assert score == pytest.approx(5.5)


def test_duplicate_signal_keys_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = datetime(
        2022,
        2,
        1,
        tzinfo=UTC,
    )

    momentum = pd.DataFrame(
        {
            "snapshot_time": [
                snapshot,
                snapshot,
            ],
            "symbol": [
                "BTC/USDT",
                "BTC/USDT",
            ],
            "candidate": [
                True,
                True,
            ],
            "signal_score": [
                2.0,
                2.0,
            ],
        }
    )

    breakout = pd.DataFrame(
        {
            "snapshot_time": [
                snapshot,
            ],
            "symbol": [
                "BTC/USDT",
            ],
            "candidate": [
                True,
            ],
            "rank_within_snapshot": [
                1,
            ],
            "turnover_expansion_h01": [
                1.5,
            ],
        }
    )

    monkeypatch.setattr(
        f01,
        "build_momentum_reacceleration_signals",
        lambda history, ranking, *, policy: (
            momentum.copy()
        ),
    )

    monkeypatch.setattr(
        f01,
        "build_volatility_breakout_signals",
        lambda history, ranking, *, policy: (
            breakout.copy()
        ),
    )

    with pytest.raises(
        F01TrendMomentumDataError,
        match="duplicate snapshot/symbol",
    ):
        build_f01_trend_momentum_signals(
            pd.DataFrame(),
            pd.DataFrame(),
            policy=policy(),
        )


def test_engine_pipeline_uses_composite_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = datetime(
        2022,
        2,
        1,
        tzinfo=UTC,
    )

    signals = pd.DataFrame(
        {
            "snapshot_time": [snapshot],
            "symbol": ["BTC/USDT"],
            "candidate": [True],
        }
    )

    weights = pd.DataFrame(
        {
            "snapshot_time": [snapshot],
            "symbol": ["BTC/USDT"],
            "target_weight": [0.5],
        }
    )

    trades = pd.DataFrame(
        {
            "trade_id": ["SYNTHETIC-T1"],
        }
    )

    daily = pd.DataFrame(
        {
            "snapshot_time": [snapshot],
            "equity": [1.0],
        }
    )

    observed: dict[str, object] = {}

    monkeypatch.setattr(
        f01,
        "build_f01_trend_momentum_signals",
        lambda history, ranking, *, policy: (
            signals.copy()
        ),
    )

    def fake_weights(
        history: pd.DataFrame,
        input_signals: pd.DataFrame,
        *,
        policy: object,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        observed["signals"] = (
            input_signals.copy()
        )

        return (
            weights.copy(),
            trades.copy(),
        )

    def fake_backtest(
        history: pd.DataFrame,
        target_weights: pd.DataFrame,
        *,
        policy: object,
    ) -> pd.DataFrame:
        observed["weights"] = (
            target_weights.copy()
        )

        return daily.copy()

    monkeypatch.setattr(
        f01,
        "build_volatility_breakout_weights",
        fake_weights,
    )

    monkeypatch.setattr(
        f01,
        "run_daily_portfolio_backtest",
        fake_backtest,
    )

    artifacts = (
        run_f01_trend_momentum_engine_core(
            pd.DataFrame(),
            pd.DataFrame(),
            policy=policy(),
        )
    )

    assert observed["signals"].equals(
        signals
    )

    assert observed["weights"].equals(
        weights
    )

    assert artifacts.to_summary() == {
        "signal_rows": 1,
        "weight_rows": 1,
        "trade_rows": 1,
        "daily_rows": 1,
    }