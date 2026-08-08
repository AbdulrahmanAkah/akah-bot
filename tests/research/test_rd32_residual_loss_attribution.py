from __future__ import annotations

import pandas as pd
import pytest

from spotbot.research import rd32_residual_loss_attribution as rd32


def _trade(
    universe: str = "C2",
    *,
    pair: str = "AAA/USDT",
    entry: str = "2022-05-01T00:00:00Z",
    exit_: str = "2022-05-05T00:00:00Z",
    pnl: float = -100.0,
    support: str = rd32.FAMILY_MB,
    context: str = "SUPPORTIVE",
    state: str = "OPEN",
    reason: str = "TIME_FAILURE_72H_CLOSE_NOT_ABOVE_ENTRY",
    policy: str = rd32.POLICY_ID,
    portfolio: str = rd32.PORTFOLIO_ID,
    cost: float = rd32.COST_MULTIPLIER,
    period: str = rd32.PERIOD_ID,
) -> dict[str, object]:
    return {
        "policy_id": policy,
        "portfolio_id": portfolio,
        "universe_id": universe,
        "cost_multiplier": cost,
        "pair": pair,
        "entry_time": entry,
        "exit_time": exit_,
        "period_id": period,
        "net_pnl": pnl,
        "support_families": support,
        "entry_market_context": context,
        "entry_governor_state": state,
        "exit_reason": reason,
    }


def _det(
    trade: dict[str, object],
    *,
    post: float = -80.0,
    first_lock: str = "2022-05-03T00:00:00Z",
) -> dict[str, object]:
    return {key: trade[key] for key in rd32.JOIN_KEY} | {
        "post_lock_net_contribution": post,
        "first_lock_time": first_lock,
    }


def _base_frames(
    *,
    crossed_per_universe: int = 10,
    post: float = -80.0,
    pre: float = -20.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades: list[dict[str, object]] = []
    det: list[dict[str, object]] = []
    for universe in rd32.UNIVERSES:
        for idx in range(crossed_per_universe):
            day = 1 + idx
            row = _trade(
                universe,
                pair=f"A{idx:02d}/USDT",
                entry=f"2022-05-{day:02d}T00:00:00Z",
                exit_=f"2022-05-{day:02d}T12:00:00Z",
                pnl=pre + post,
            )
            trades.append(row)
            det.append(
                _det(
                    row,
                    post=post,
                    first_lock=f"2022-05-{day:02d}T06:00:00Z",
                )
            )
    return pd.DataFrame(trades), pd.DataFrame(det)


def test_registry_and_thresholds_are_exact() -> None:
    assert rd32.UNIVERSES == ("C2", "D2", "E2")
    assert rd32.POST_LOCK_DAMAGE_THRESHOLD == 0.50
    assert rd32.MINIMUM_CROSSED_TRADE_COUNT == 10
    assert rd32.PERIOD_ID == "ROBUSTNESS_2022"


def test_contract_is_pre_execution_and_io_free() -> None:
    contract = rd32.contract_summary()
    assert contract["canonical_input_only"] is True
    assert contract["filesystem_io"] is False
    assert contract["network_io"] is False
    assert contract["raw_market_data"] is False
    assert contract["economic_replay"] is False
    assert contract["actual_rd31_attribution_execution"] is False
    assert contract["2024_access"] is False
    assert contract["post_2024_access"] is False
    assert contract["production_authorized"] is False
    assert contract["forced_exit_counterfactual_decision_evidence"] is False


def test_trade_missing_required_column_fails() -> None:
    trades, _ = _base_frames()
    with pytest.raises(rd32.RD32Error, match="missing canonical columns"):
        rd32.validate_trades(trades.drop(columns=["net_pnl"]))


def test_deterioration_missing_required_column_fails() -> None:
    _, det = _base_frames()
    with pytest.raises(rd32.RD32Error, match="missing canonical columns"):
        rd32.validate_deterioration(det.drop(columns=["first_lock_time"]))


def test_invalid_trade_timestamp_fails() -> None:
    trades, _ = _base_frames()
    trades.loc[0, "entry_time"] = "not-a-time"
    with pytest.raises(rd32.RD32Error, match="invalid timestamps"):
        rd32.validate_trades(trades)


def test_invalid_deterioration_timestamp_fails() -> None:
    _, det = _base_frames()
    det.loc[0, "first_lock_time"] = "not-a-time"
    with pytest.raises(rd32.RD32Error, match="invalid timestamps"):
        rd32.validate_deterioration(det)


def test_trade_exit_before_entry_fails() -> None:
    trades, _ = _base_frames()
    trades.loc[0, "exit_time"] = "2022-04-01T00:00:00Z"
    with pytest.raises(rd32.RD32Error, match="precedes entry_time"):
        rd32.validate_trades(trades)


def test_first_lock_before_entry_fails() -> None:
    _, det = _base_frames()
    det.loc[0, "first_lock_time"] = "2022-04-01T00:00:00Z"
    with pytest.raises(rd32.RD32Error, match="precedes trade entry_time"):
        rd32.validate_deterioration(det)


def test_first_lock_after_exit_fails() -> None:
    _, det = _base_frames()
    det.loc[0, "first_lock_time"] = "2022-12-01T00:00:00Z"
    with pytest.raises(rd32.RD32Error, match="exceeds trade exit_time"):
        rd32.validate_deterioration(det)


def test_non_finite_trade_pnl_fails() -> None:
    trades, _ = _base_frames()
    trades.loc[0, "net_pnl"] = float("inf")
    with pytest.raises(rd32.RD32Error, match="non-finite"):
        rd32.validate_trades(trades)


def test_non_finite_post_lock_fails() -> None:
    _, det = _base_frames()
    det.loc[0, "post_lock_net_contribution"] = float("nan")
    with pytest.raises(rd32.RD32Error, match="NaN"):
        rd32.validate_deterioration(det)


def test_duplicate_trade_key_fails() -> None:
    trades, _ = _base_frames()
    trades = pd.concat([trades, trades.iloc[[0]]], ignore_index=True)
    with pytest.raises(rd32.RD32Error, match="duplicate trade join key"):
        rd32.validate_trades(trades)


def test_duplicate_deterioration_key_fails() -> None:
    _, det = _base_frames()
    det = pd.concat([det, det.iloc[[0]]], ignore_index=True)
    with pytest.raises(rd32.RD32Error, match="duplicate deterioration join key"):
        rd32.validate_deterioration(det)


def test_family_bucket_mb() -> None:
    assert rd32.family_bucket(rd32.FAMILY_MB) == "MB"


def test_family_bucket_rs() -> None:
    assert rd32.family_bucket(rd32.FAMILY_RS) == "RS"


def test_family_bucket_overlap_order_independent() -> None:
    raw = f"{rd32.FAMILY_RS}|{rd32.FAMILY_MB}"
    assert rd32.family_bucket(raw) == "OVERLAP"


def test_family_bucket_sequence_overlap() -> None:
    assert rd32.family_bucket([rd32.FAMILY_MB, rd32.FAMILY_RS]) == "OVERLAP"


def test_unknown_family_fails() -> None:
    with pytest.raises(rd32.RD32Error, match="unknown support family"):
        rd32.family_bucket("UNKNOWN")


def test_duplicate_family_fails() -> None:
    raw = f"{rd32.FAMILY_MB}|{rd32.FAMILY_MB}"
    with pytest.raises(rd32.RD32Error, match="duplicate support family"):
        rd32.family_bucket(raw)


def test_primary_requires_all_three_universes() -> None:
    trades, det = _base_frames()
    trades = trades.loc[trades["universe_id"] != "E2"]
    det = det.loc[det["universe_id"] != "E2"]
    with pytest.raises(rd32.RD32Error, match="every frozen universe"):
        rd32.execute_attribution(trades, det)


def test_unmatched_primary_deterioration_fails() -> None:
    trades, det = _base_frames()
    extra = det.iloc[[0]].copy()
    extra["pair"] = "UNMATCHED/USDT"
    det = pd.concat([det, extra], ignore_index=True)
    with pytest.raises(rd32.RD32Error, match="unmatched primary deterioration"):
        rd32.execute_attribution(trades, det)


def test_non_primary_deterioration_is_ignored() -> None:
    trades, det = _base_frames()
    extra = det.iloc[[0]].copy()
    extra["policy_id"] = "OTHER_POLICY"
    extra["pair"] = "IGNORED/USDT"
    det = pd.concat([det, extra], ignore_index=True)
    result = rd32.execute_attribution(trades, det)
    assert len(result.trade_attribution) == len(trades)


def test_non_primary_trades_are_ignored() -> None:
    trades, det = _base_frames()
    extra = trades.iloc[[0]].copy()
    extra["policy_id"] = "OTHER_POLICY"
    extra["pair"] = "IGNORED/USDT"
    trades = pd.concat([trades, extra], ignore_index=True)
    result = rd32.execute_attribution(trades, det)
    assert len(result.trade_attribution) == len(trades) - 1


def test_crossed_trade_classification_and_accounting() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    row = result.trade_attribution.iloc[0]
    assert row["classification"] == rd32.CLASS_CROSSED
    assert row["post_lock_net_contribution"] == -80.0
    assert row["pre_lock_net_contribution"] == -20.0
    assert row["final_trade_net_pnl"] == -100.0


def test_no_cross_trade_semantics_are_frozen() -> None:
    trades, det = _base_frames()
    key = trades.iloc[0][list(rd32.JOIN_KEY)].to_dict()
    mask = pd.Series(True, index=det.index)
    for column, value in key.items():
        mask &= det[column] == value
    det = det.loc[~mask].copy()
    result = rd32.execute_attribution(trades, det)
    row = result.trade_attribution.loc[
        result.trade_attribution["pair"] == trades.iloc[0]["pair"]
    ].iloc[0]
    assert row["classification"] == rd32.CLASS_NO_CROSS
    assert row["post_lock_net_contribution"] == 0.0
    assert row["pre_lock_net_contribution"] == row["final_trade_net_pnl"]
    assert row["first_lock_transition_episode"] == "NONE"
    assert row["crisis_tag"] == "NONE"


def test_accounting_identity_holds() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    frame = result.trade_attribution
    reconstructed = frame["pre_lock_net_contribution"] + frame["post_lock_net_contribution"]
    assert (
        (reconstructed - frame["final_trade_net_pnl"]).abs() <= rd32.IDENTITY_ABS_TOLERANCE
    ).all()


def test_primary_metrics_have_one_row_per_universe() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert result.primary_metrics["universe_id"].tolist() == ["C2", "D2", "E2"]


def test_damage_fraction_exact() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert set(result.primary_metrics["post_lock_damage_fraction_of_total_loss"]) == {0.8}


def test_damage_fraction_clamps_positive_post_lock_to_zero() -> None:
    trades, det = _base_frames(post=20.0, pre=-120.0)
    result = rd32.execute_attribution(trades, det)
    assert set(result.primary_metrics["post_lock_damage_fraction_of_total_loss"]) == {0.0}


def test_supported_decision_when_every_universe_passes() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert result.decision == rd32.DECISION_SUPPORTED
    overall = result.gate_evaluation.loc[
        result.gate_evaluation["gate_id"] == "ALL_PREREGISTERED_DERISKING_ROUTE_GATES"
    ]
    assert overall["passed"].all()


def test_crossed_count_gate_failure_rejects() -> None:
    trades, det = _base_frames(crossed_per_universe=9)
    result = rd32.execute_attribution(trades, det)
    assert result.decision == rd32.DECISION_NOT_SUPPORTED


def test_damage_fraction_gate_failure_rejects() -> None:
    trades, det = _base_frames(post=-40.0, pre=-60.0)
    result = rd32.execute_attribution(trades, det)
    assert result.decision == rd32.DECISION_NOT_SUPPORTED


def test_median_post_lock_gate_failure_rejects() -> None:
    trades, det = _base_frames(post=20.0, pre=-120.0)
    result = rd32.execute_attribution(trades, det)
    assert result.decision == rd32.DECISION_NOT_SUPPORTED


def test_one_universe_failure_rejects_all() -> None:
    trades, det = _base_frames()
    mask = det["universe_id"] == "E2"
    det.loc[mask, "post_lock_net_contribution"] = -20.0
    result = rd32.execute_attribution(trades, det)
    assert result.decision == rd32.DECISION_NOT_SUPPORTED


def test_pair_diagnostic_exists() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert "pair" in result.diagnostics
    assert "pair" in result.diagnostics["pair"].columns


def test_family_diagnostic_maps_exactly() -> None:
    trades, det = _base_frames()
    trades.loc[0, "support_families"] = f"{rd32.FAMILY_MB}|{rd32.FAMILY_RS}"
    result = rd32.execute_attribution(trades, det)
    buckets = set(result.diagnostics["family_bucket"]["family_bucket"])
    assert "OVERLAP" in buckets


def test_context_diagnostic_exists() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert "entry_market_context" in result.diagnostics


def test_governor_state_diagnostic_exists() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert "entry_governor_state" in result.diagnostics


def test_episode_is_derived_from_exact_first_lock_time() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    crossed = result.trade_attribution.iloc[0]
    assert crossed["first_lock_transition_episode"].startswith("LOCK@2022-")


def test_exit_reason_diagnostic_exists() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert "exit_reason" in result.diagnostics


@pytest.mark.parametrize(
    ("lock_time", "expected"),
    [
        ("2022-05-06T00:00:00Z", "TERRA_UST_DEPEG"),
        ("2022-05-09T00:00:00Z", "TERRA_UST_DEPEG"),
        ("2022-05-12T00:00:00Z", "TERRA_UST_DEPEG"),
    ],
)
def test_crisis_window_inclusive_boundaries(
    lock_time: str,
    expected: str,
) -> None:
    assert rd32._crisis_tag(pd.Timestamp(lock_time)) == expected


def test_crisis_window_outside_is_none() -> None:
    assert rd32._crisis_tag(pd.Timestamp("2022-05-12T01:00:00Z")) == "NONE"


def test_transition_episode_diagnostic_exists() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert "first_lock_transition_episode" in result.diagnostics


def test_crisis_diagnostic_exists() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    assert "crisis_tag" in result.diagnostics


def test_input_frames_are_not_mutated() -> None:
    trades, det = _base_frames()
    trades_before = trades.copy(deep=True)
    det_before = det.copy(deep=True)
    rd32.execute_attribution(trades, det)
    pd.testing.assert_frame_equal(trades, trades_before)
    pd.testing.assert_frame_equal(det, det_before)


def test_result_order_is_deterministic() -> None:
    trades, det = _base_frames()
    shuffled_trades = trades.sample(frac=1.0, random_state=7).reset_index(drop=True)
    shuffled_det = det.sample(frac=1.0, random_state=9).reset_index(drop=True)
    left = rd32.execute_attribution(trades, det)
    right = rd32.execute_attribution(shuffled_trades, shuffled_det)
    pd.testing.assert_frame_equal(left.trade_attribution, right.trade_attribution)
    pd.testing.assert_frame_equal(left.primary_metrics, right.primary_metrics)
    pd.testing.assert_frame_equal(left.gate_evaluation, right.gate_evaluation)


def test_timezone_offsets_normalize_to_utc() -> None:
    trades, det = _base_frames()
    trades.loc[0, "entry_time"] = "2022-05-01T03:00:00+03:00"
    det.loc[0, "entry_time"] = "2022-05-01T03:00:00+03:00"
    result = rd32.execute_attribution(trades, det)
    match = result.trade_attribution.loc[
        (result.trade_attribution["universe_id"] == "C2")
        & (result.trade_attribution["pair"] == "A00/USDT")
    ].iloc[0]
    assert match["entry_time"] == pd.Timestamp("2022-05-01T00:00:00Z")


def test_period_outside_primary_is_ignored() -> None:
    trades, det = _base_frames()
    extra = trades.iloc[[0]].copy()
    extra["period_id"] = "ROBUSTNESS_2023"
    extra["pair"] = "OTHERPERIOD/USDT"
    trades = pd.concat([trades, extra], ignore_index=True)
    result = rd32.execute_attribution(trades, det)
    assert "OTHERPERIOD/USDT" not in set(result.trade_attribution["pair"])


def test_wrong_cost_multiplier_is_ignored() -> None:
    trades, det = _base_frames()
    extra = trades.iloc[[0]].copy()
    extra["cost_multiplier"] = 1.0
    extra["pair"] = "COST1X/USDT"
    trades = pd.concat([trades, extra], ignore_index=True)
    result = rd32.execute_attribution(trades, det)
    assert "COST1X/USDT" not in set(result.trade_attribution["pair"])


def test_gate_registry_has_six_rows_per_universe() -> None:
    trades, det = _base_frames()
    result = rd32.execute_attribution(trades, det)
    counts = result.gate_evaluation.groupby("universe_id").size().to_dict()
    assert counts == {"C2": 6, "D2": 6, "E2": 6}


def test_no_cross_does_not_inflate_post_lock_sum() -> None:
    trades, det = _base_frames()
    row = _trade(
        "C2",
        pair="NOCROSS/USDT",
        entry="2022-08-01T00:00:00Z",
        exit_="2022-08-02T00:00:00Z",
        pnl=-500.0,
    )
    trades = pd.concat([trades, pd.DataFrame([row])], ignore_index=True)
    result = rd32.execute_attribution(trades, det)
    metric = result.primary_metrics.loc[result.primary_metrics["universe_id"] == "C2"].iloc[0]
    assert metric["post_lock_net_contribution_sum"] == -800.0
    assert metric["no_lock_cross_trade_count"] == 1


def test_entry_context_and_state_are_required_canonical_enrichment() -> None:
    trades, _ = _base_frames()
    for column in ("entry_market_context", "entry_governor_state"):
        with pytest.raises(rd32.RD32Error, match="missing canonical columns"):
            rd32.validate_trades(trades.drop(columns=[column]))
