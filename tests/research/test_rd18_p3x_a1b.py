from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research.rd18_p3x_a1b_asset_gate import (
    FAMILY_IDS,
    A1BError,
    GateConfig,
    build_monthly_gate,
    eligibility_mask,
)


def _frame(
    *,
    start: str = "2023-01-01T01:00:00+00:00",
    periods: int = 17_544,
    turnover: float = 100.0,
) -> pd.DataFrame:
    timestamp = pd.date_range(
        start=start,
        periods=periods,
        freq="h",
        tz="UTC",
    )
    close = pd.Series(10.0, index=range(periods))
    volume = pd.Series(turnover / 10.0, index=range(periods))
    return pd.DataFrame(
        {
            "timestamp": timestamp,
            "close": close,
            "volume": volume,
        }
    )


def _build(
    frames: dict[str, pd.DataFrame | None],
    *,
    actions: dict[str, str] | None = None,
    identities: dict[str, bool] | None = None,
    config: GateConfig | None = None,
):
    symbols = set(frames)
    resolved_actions = actions or {symbol: "READY_LOCAL" for symbol in symbols}
    resolved_identities = identities or {symbol: True for symbol in symbols}
    kwargs = {}
    if config is not None:
        kwargs["config"] = config
    return build_monthly_gate(
        frames=frames,
        source_actions=resolved_actions,
        identity_ready=resolved_identities,
        **kwargs,
    )


def test_future_rows_cannot_change_earlier_decision() -> None:
    base = _frame(periods=9_000)
    cutoff_row = pd.Timestamp("2024-01-01T00:00:00+00:00")
    earlier = base.loc[base["timestamp"] <= cutoff_row].copy()
    future = pd.concat(
        [
            earlier,
            pd.DataFrame(
                {
                    "timestamp": pd.date_range(
                        "2024-01-01T01:00:00+00:00",
                        periods=100,
                        freq="h",
                        tz="UTC",
                    ),
                    "close": 10.0,
                    "volume": 1_000_000.0,
                }
            ),
        ],
        ignore_index=True,
    )

    first = _build({"A/USDT": earlier}).eligibility
    second = _build({"A/USDT": future}).eligibility
    month = "2024-01-01T00:00:00+00:00"
    first_row = first.loc[first["month_start"] == month].reset_index(drop=True)
    second_row = second.loc[second["month_start"] == month].reset_index(drop=True)

    pd.testing.assert_frame_equal(first_row, second_row)


def test_insufficient_warmup_is_explicit() -> None:
    result = _build({"A/USDT": _frame(periods=1_000)})
    row = result.eligibility.iloc[-1]
    assert bool(row["eligible"]) is False
    assert row["reason"] == "INSUFFICIENT_WARMUP"


def test_cross_sectional_threshold_uses_contemporaneous_peers() -> None:
    frames = {f"S{index}/USDT": _frame(turnover=float(index)) for index in range(1, 6)}
    result = _build(frames)
    final_month = result.thresholds.iloc[-1]
    assert final_month["peer_count"] == 5
    assert final_month["liquidity_threshold"] == pytest.approx(1.8)

    month = final_month["month_start"]
    rows = result.eligibility.loc[result.eligibility["month_start"] == month].set_index("symbol")
    assert bool(rows.loc["S1/USDT", "eligible"]) is False
    assert rows.loc["S1/USDT", "reason"] == "BELOW_LIQUIDITY_PERCENTILE"
    assert bool(rows.loc["S2/USDT", "eligible"]) is True


def test_missing_hours_are_not_interpreted_as_no_signal() -> None:
    frame = _frame()
    decision = pd.Timestamp("2024-01-01T00:00:00+00:00")
    missing = pd.date_range(
        decision - pd.Timedelta(hours=20),
        periods=20,
        freq="h",
        tz="UTC",
    )
    frame = frame.loc[~frame["timestamp"].isin(missing)].copy()
    result = _build({"A/USDT": frame})
    row = result.eligibility.loc[
        result.eligibility["month_start"] == "2024-01-01T00:00:00+00:00"
    ].iloc[0]
    assert row["reason"] == "INSUFFICIENT_CONTINUITY"


def test_unresolved_identity_and_historical_source_are_explicit() -> None:
    frames = {
        "ETN/USDT": None,
        "OLD/USDT": None,
        "READY/USDT": _frame(),
    }
    actions = {
        "ETN/USDT": "CORPORATE_ACTION_POLICY_REQUIRED",
        "OLD/USDT": "HISTORICAL_MARKET_SOURCE_REQUIRED",
        "READY/USDT": "READY_LOCAL",
    }
    identities = {
        "ETN/USDT": False,
        "OLD/USDT": True,
        "READY/USDT": True,
    }
    result = _build(
        frames,
        actions=actions,
        identities=identities,
    )
    final = result.eligibility.loc[
        result.eligibility["month_start"] == result.eligibility["month_start"].max()
    ].set_index("symbol")
    assert final.loc["ETN/USDT", "reason"] == "CORPORATE_ACTION_IDENTITY_NOT_STRATEGY_READY"
    assert final.loc["OLD/USDT", "reason"] == "HISTORICAL_MARKET_SOURCE_REQUIRED"


def test_same_mask_is_used_for_every_family() -> None:
    frames = {
        "A/USDT": _frame(turnover=100.0),
        "B/USDT": _frame(turnover=1.0),
    }
    result = _build(frames)
    candidates = pd.DataFrame(
        {
            "symbol": ["A/USDT", "B/USDT"],
            "signal_close": [
                "2024-01-15T12:00:00+00:00",
                "2024-01-15T12:00:00+00:00",
            ],
        }
    )
    masks = [
        eligibility_mask(
            candidates,
            eligibility=result.eligibility,
            family_id=family,
        )
        for family in FAMILY_IDS
    ]
    for mask in masks[1:]:
        pd.testing.assert_series_equal(masks[0], mask)


def test_post_cutoff_rows_fail_closed() -> None:
    frame = _frame()
    frame.loc[len(frame)] = {
        "timestamp": pd.Timestamp("2025-01-01T01:00:00+00:00"),
        "close": 10.0,
        "volume": 10.0,
    }
    with pytest.raises(A1BError, match="post-cutoff"):
        _build({"A/USDT": frame})


def test_nonfinite_metrics_fail_closed() -> None:
    frame = _frame()
    frame.loc[0, "volume"] = float("nan")
    with pytest.raises(A1BError, match="non-finite"):
        _build({"A/USDT": frame})


def test_config_validation_is_fail_closed() -> None:
    with pytest.raises(A1BError, match="trailing_hours"):
        GateConfig(trailing_hours=0).validate()


def test_report_prohibits_strategy_and_return_execution() -> None:
    result = _build({"A/USDT": _frame()})
    authorizations = result.report["authorizations"]
    assert isinstance(authorizations, dict)
    assert authorizations["strategy_candidate_generation"] is False
    assert authorizations["strategy_replay"] is False
    assert authorizations["return_calculation"] is False
    assert result.report["identical_rule_across_families"] is True
