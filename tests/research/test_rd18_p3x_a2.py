from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd16c_features import FeatureDataError
from spotbot.research.rd18_p3x_a2_generator import (
    COMPRESSION_ENGINE_ID,
    COMPRESSION_FAMILY_ID,
    FORBIDDEN_OUTCOME_COLUMNS,
    TREND_ENGINE_ID,
    TREND_FAMILY_ID,
    A2GeneratorError,
    classify_enriched_candidates,
    generate_symbol,
    validate_eligibility_ledger,
)


def _eligibility(
    *,
    symbol: str = "AAA/USDT",
    eligible: bool = True,
    reason: str | None = None,
) -> pd.DataFrame:
    resolved_reason = reason or ("ELIGIBLE" if eligible else "BELOW_LIQUIDITY_PERCENTILE")
    return pd.DataFrame(
        {
            "month_start": ["2024-01-01T00:00:00+00:00"],
            "symbol": [symbol],
            "eligible": [eligible],
            "reason": [resolved_reason],
            "input_window_sha256": ["a" * 64],
        }
    )


def _row(
    *,
    family_id: str,
    signal_close: str = "2024-01-10T01:00:00+00:00",
    symbol: str = "AAA/USDT",
    market_regime: str = "STRONG_BULL",
    volatility_regime: str = "NORMAL_VOLATILITY",
    fee_ready: bool = True,
) -> dict[str, object]:
    signal = pd.Timestamp(signal_close)
    if family_id == TREND_FAMILY_ID:
        close = 100.0
        prior = 99.0 if fee_ready else 99.9
        atr = 0.2
        prior_high24 = prior
        prior_high12 = 99.0
        range_1h = 1.0
    else:
        close = 101.0
        prior_high12 = 100.0 if fee_ready else 100.9
        prior_high24 = 100.0
        atr = 1.0
        range_1h = 1.2

    return {
        "family_id": family_id,
        "symbol": symbol,
        "signal_close": signal,
        "entry_open_time": signal,
        "entry_bar_close": signal + pd.Timedelta(hours=1),
        "entry_price": close,
        "atr14_at_signal": atr,
        "signal_low": close - 1.0,
        "signal_high": close + 1.0,
        "market_regime": market_regime,
        "volatility_regime": volatility_regime,
        "4h_context_close": signal,
        "1d_context_close": signal,
        "1w_context_close": signal,
        "f_open": close - 0.2,
        "f_high": close + 0.5,
        "f_low": close - 0.5,
        "f_close": close,
        "f_volume": 100.0,
        "f_ema20": close - 0.2,
        "f_atr14": atr,
        "f_prior_high24": prior_high24,
        "f_volume_median20": 100.0,
        "f_4h_close": close,
        "f_4h_ema20": 101.0,
        "f_4h_ema50": 100.0,
        "f_prior_high12": prior_high12,
        "f_range_1h": range_1h,
        "f_4h_atr_ratio": 0.8,
        "f_prior_low12": close - 2.0,
    }


def _classify(
    rows: list[dict[str, object]],
    *,
    family_id: str,
    eligibility: pd.DataFrame | None = None,
    excluded: frozenset[str] = frozenset(),
):
    return classify_enriched_candidates(
        pd.DataFrame(rows),
        eligibility=eligibility if eligibility is not None else _eligibility(),
        excluded_pairs=excluded,
        family_id=family_id,
    )


def test_trend_strong_bull_waives_fee_buffer_before_router() -> None:
    candidates, audit = _classify(
        [
            _row(
                family_id=TREND_FAMILY_ID,
                fee_ready=False,
                market_regime="STRONG_BULL",
            )
        ],
        family_id=TREND_FAMILY_ID,
    )
    assert len(candidates) == 1
    assert bool(candidates.iloc[0]["fee_buffer_ready"]) is False
    assert candidates.iloc[0]["engine_id"] == TREND_ENGINE_ID
    assert audit.iloc[0]["rejection_reason"] == "SELECTED_PRE_ROUTER"


def test_trend_non_strong_bull_requires_fee_buffer() -> None:
    candidates, audit = _classify(
        [
            _row(
                family_id=TREND_FAMILY_ID,
                fee_ready=False,
                market_regime="BULL",
            )
        ],
        family_id=TREND_FAMILY_ID,
    )
    assert candidates.empty
    assert audit.iloc[0]["rejection_reason"] == "FEE_BUFFER"


def test_compression_applies_24_hour_signal_cooldown() -> None:
    rows = [
        _row(
            family_id=COMPRESSION_FAMILY_ID,
            signal_close="2024-01-10T01:00:00+00:00",
        ),
        _row(
            family_id=COMPRESSION_FAMILY_ID,
            signal_close="2024-01-10T12:00:00+00:00",
        ),
        _row(
            family_id=COMPRESSION_FAMILY_ID,
            signal_close="2024-01-11T02:00:00+00:00",
        ),
    ]
    candidates, audit = _classify(
        rows,
        family_id=COMPRESSION_FAMILY_ID,
    )
    assert len(candidates) == 2
    assert set(candidates["engine_id"]) == {COMPRESSION_ENGINE_ID}
    reasons = audit["rejection_reason"].tolist()
    assert reasons == [
        "SELECTED_PRE_ROUTER",
        "ENGINE_COOLDOWN_24H",
        "SELECTED_PRE_ROUTER",
    ]


def test_a1b_rejection_is_explicit() -> None:
    candidates, audit = _classify(
        [_row(family_id=TREND_FAMILY_ID)],
        family_id=TREND_FAMILY_ID,
        eligibility=_eligibility(
            eligible=False,
            reason="BELOW_LIQUIDITY_PERCENTILE",
        ),
    )
    assert candidates.empty
    assert audit.iloc[0]["rejection_reason"] == ("A1B::BELOW_LIQUIDITY_PERCENTILE")


def test_a1c_exclusion_is_explicit() -> None:
    candidates, audit = _classify(
        [
            _row(
                family_id=TREND_FAMILY_ID,
                symbol="ETN/USDT",
            )
        ],
        family_id=TREND_FAMILY_ID,
        eligibility=_eligibility(symbol="ETN/USDT"),
        excluded=frozenset({"ETN-USDT"}),
    )
    assert candidates.empty
    assert audit.iloc[0]["rejection_reason"] == ("A1C_CORPORATE_ACTION_EXCLUSION")


def test_future_context_fails_closed() -> None:
    row = _row(family_id=TREND_FAMILY_ID)
    row["1d_context_close"] = pd.Timestamp(row["signal_close"]) + pd.Timedelta(hours=1)
    with pytest.raises(A2GeneratorError, match="future context"):
        _classify([row], family_id=TREND_FAMILY_ID)


def test_duplicate_candidate_identity_fails_closed() -> None:
    row = _row(family_id=TREND_FAMILY_ID)
    with pytest.raises(A2GeneratorError, match="candidate IDs"):
        _classify([row, dict(row)], family_id=TREND_FAMILY_ID)


def test_missing_symbol_month_decision_fails_closed() -> None:
    with pytest.raises(Exception, match="explicit symbol-month decision"):
        _classify(
            [_row(family_id=TREND_FAMILY_ID)],
            family_id=TREND_FAMILY_ID,
            eligibility=_eligibility(symbol="OTHER/USDT"),
        )


def test_selected_candidates_contain_no_outcome_columns() -> None:
    candidates, _ = _classify(
        [_row(family_id=TREND_FAMILY_ID)],
        family_id=TREND_FAMILY_ID,
    )
    assert FORBIDDEN_OUTCOME_COLUMNS.isdisjoint(candidates.columns)


def test_eligibility_ledger_rejects_duplicate_symbol_month() -> None:
    duplicated = pd.concat([_eligibility(), _eligibility()], ignore_index=True)
    with pytest.raises(A2GeneratorError, match="duplicate"):
        validate_eligibility_ledger(duplicated)


def test_eligibility_reason_contract_is_fail_closed() -> None:
    with pytest.raises(A2GeneratorError, match="reason ELIGIBLE"):
        validate_eligibility_ledger(
            _eligibility(
                eligible=True,
                reason="BELOW_LIQUIDITY_PERCENTILE",
            )
        )


def test_unknown_family_is_rejected() -> None:
    with pytest.raises(A2GeneratorError, match="unsupported family"):
        classify_enriched_candidates(
            pd.DataFrame([_row(family_id=TREND_FAMILY_ID)]),
            eligibility=_eligibility(),
            excluded_pairs=frozenset(),
            family_id="UNKNOWN",
        )


def _raise_no_feature_rows(
    _frames,
    *,
    symbol: str,
):
    raise FeatureDataError(f"{symbol}: no rows remain after feature warm-up.")


def test_no_feature_rows_are_explicit_when_a1b_rejects_all_months(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "spotbot.research.rd18_p3x_a2_generator.build_feature_frame",
        _raise_no_feature_rows,
    )
    result = generate_symbol(
        {
            "1h": pd.DataFrame(),
            "4h": pd.DataFrame(),
            "1d": pd.DataFrame(),
            "1w": pd.DataFrame(),
        },
        symbol="LATE/USDT",
        eligibility=_eligibility(
            symbol="LATE/USDT",
            eligible=False,
            reason="INSUFFICIENT_WARMUP",
        ),
        excluded_pairs=frozenset(),
    )

    assert result.candidates.empty
    assert result.audit.empty
    assert result.summary["generation_status"] == ("NO_FEATURE_ROWS_AFTER_CAUSAL_WARMUP")
    assert result.summary["generation_reason"] == ("NO_ROWS_AFTER_RD16C_CAUSAL_FEATURE_WARMUP")


def test_no_feature_rows_conflict_with_a1b_eligible_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "spotbot.research.rd18_p3x_a2_generator.build_feature_frame",
        _raise_no_feature_rows,
    )
    with pytest.raises(
        A2GeneratorError,
        match="A1B authorizes months",
    ):
        generate_symbol(
            {
                "1h": pd.DataFrame(),
                "4h": pd.DataFrame(),
                "1d": pd.DataFrame(),
                "1w": pd.DataFrame(),
            },
            symbol="LATE/USDT",
            eligibility=_eligibility(
                symbol="LATE/USDT",
                eligible=True,
            ),
            excluded_pairs=frozenset(),
        )


def _load_a2_validator_for_regression():
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    path = root / "scripts/research/validate_rd18_p3x_a2.py"
    name = "rd18_p3x_a2_validator_regression"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(name)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    return module


def test_validator_accepts_consistent_audit_selection_mapping() -> None:
    candidates, audit = _classify(
        [
            _row(
                family_id=TREND_FAMILY_ID,
                fee_ready=True,
                market_regime="STRONG_BULL",
            )
        ],
        family_id=TREND_FAMILY_ID,
    )
    validator = _load_a2_validator_for_regression()

    counts = validator._validate_audit_partition(
        audit,
        candidates,
    )

    assert sum(counts.values()) == len(audit)
