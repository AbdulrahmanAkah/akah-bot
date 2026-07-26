from __future__ import annotations

import pandas as pd

from spotbot.research.ams_md01_momentum import select_assets, target_weight, variant_spec


def test_tsm_caps_five_and_xsm_dual_cap_three() -> None:
    ranked = pd.DataFrame(
        {
            "symbol": [f"S{index}" for index in range(8)],
            "momentum_return": [0.8 - index / 10 for index in range(8)],
            "percentile_rank": [1 - index / 7 for index in range(8)],
        }
    )
    clusters = {symbol: f"CL-{symbol}" for symbol in ranked["symbol"]}
    tsm, _ = select_assets(ranked, variant=variant_spec("MD01-M01"), clusters=clusters)
    xsm, _ = select_assets(ranked, variant=variant_spec("MD01-M03"), clusters=clusters)
    dual, _ = select_assets(ranked, variant=variant_spec("MD01-M05"), clusters=clusters)
    assert len(tsm) == 5
    assert len(xsm) == 3
    assert len(dual) == 3


def test_cluster_cap_skips_third_and_continues_ranking() -> None:
    ranked = pd.DataFrame(
        {
            "symbol": ["A", "B", "C", "D"],
            "momentum_return": [0.4, 0.3, 0.2, 0.1],
            "percentile_rank": [1.0, 0.66, 0.33, 0.0],
        }
    )
    selected, decisions = select_assets(
        ranked,
        variant=variant_spec("MD01-M03"),
        clusters={"A": "CL-1", "B": "CL-1", "C": "CL-1", "D": "CL-2"},
    )
    assert selected == ["A", "B", "D"]
    rejected = next(item for item in decisions if item["symbol"] == "C")
    assert rejected["decision"] == "CLUSTER_BLOCKED"


def test_alignment_weight_is_not_renormalised() -> None:
    tsm = variant_spec("MD01-M01")
    xsm = variant_spec("MD01-M03")
    assert target_weight(tsm, selected_count=2, alignment_multiplier=1.0) == 0.20
    assert target_weight(xsm, selected_count=3, alignment_multiplier=0.67) == 0.1675
    assert target_weight(xsm, selected_count=3, alignment_multiplier=0.33) == 0.0825
