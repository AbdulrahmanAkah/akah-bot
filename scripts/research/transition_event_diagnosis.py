"""Frozen descriptive attribution of P19/P38 direct sets, not rule discovery."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path

import pandas as pd
from p43_transition_authority import key

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "governance/transition_event_diagnosis_v1"
OLD = ROOT / "governance/p43_transition_exact_authority"


def load(path):
    return pd.read_csv(path, float_precision="round_trip")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def distribution(values):
    x = pd.Series(values, dtype=float).dropna()
    if x.empty:
        return {"count": 0}
    return {
        "count": len(x),
        "mean": float(x.mean()),
        "min": float(x.min()),
        "max": float(x.max()),
        **{f"p{int(q * 100)}": float(x.quantile(q)) for q in [0.1, 0.25, 0.5, 0.75, 0.9]},
    }


def stats(frame):
    pnl = frame.net_pnl
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    positive = math.fsum(wins)
    negative = math.fsum(losses)
    ordered = frame.sort_values(["net_pnl", "pair", "entry_time"])
    net = math.fsum(pnl)
    return {
        "count": len(frame),
        "net_pnl": net,
        "mean_pnl": net / len(frame) if len(frame) else None,
        "pnl_distribution": distribution(pnl),
        "wins": len(wins),
        "losses": len(losses),
        "zeros": int(pnl.eq(0).sum()),
        "win_rate": len(wins) / len(frame) if len(frame) else None,
        "winner_contribution": positive,
        "loser_contribution": negative,
        "mean_win": float(wins.mean()) if len(wins) else None,
        "mean_loss": float(losses.mean()) if len(losses) else None,
        "profit_factor": positive / -negative if negative else None,
        "profit_factor_zero_loss_denominator": negative == 0,
        "holding_hours": distribution(frame.holding_hours),
        "entry_notional": distribution(frame.entry_notional),
        "normalized_net_return": distribution(frame.net_pnl / frame.entry_notional),
        "top_bottom": {
            str(n): {
                "top_pnl": math.fsum(ordered.tail(n).net_pnl),
                "bottom_pnl": math.fsum(ordered.head(n).net_pnl),
                "net_without_top": math.fsum(ordered.iloc[:-n].net_pnl),
                "net_without_bottom": math.fsum(ordered.iloc[n:].net_pnl),
                "top_share_of_gross_winners": math.fsum(ordered.tail(n).net_pnl) / positive
                if positive
                else None,
                "top_to_signed_net_ratio": math.fsum(ordered.tail(n).net_pnl) / net
                if net
                else None,
            }
            for n in [1, 3, 5]
        },
        "largest_winners": ordered.tail(5)
        .iloc[::-1][["pair", "entry_time", "net_pnl", "exit_reason", "holding_hours"]]
        .to_dict("records"),
        "largest_losers": ordered.head(5)[
            ["pair", "entry_time", "net_pnl", "exit_reason", "holding_hours"]
        ].to_dict("records"),
    }


def grouped(frame, field):
    result = []
    for label, group in frame.groupby(field, dropna=False, sort=True):
        value = stats(group)
        result.append({"group": str(label), **value})
    assert sum(v["count"] for v in result) == len(frame)
    assert abs(math.fsum(v["net_pnl"] for v in result) - math.fsum(frame.net_pnl)) < 1e-8
    return result


def shapley_mean(a, b):
    def factors(f):
        p = float(f.net_pnl.gt(0).mean())
        return [
            p,
            float(f.loc[f.net_pnl > 0, "net_pnl"].mean()),
            float(f.loc[f.net_pnl <= 0, "net_pnl"].mean()),
        ]

    def evaluate(x):
        return x[0] * x[1] + (1 - x[0]) * x[2]

    x, y = factors(a), factors(b)
    out = [0.0, 0.0, 0.0]
    for order in itertools.permutations(range(3)):
        state = x.copy()
        for i in order:
            before = evaluate(state)
            state[i] = y[i]
            out[i] += (evaluate(state) - before) / 6
    assert abs(sum(out) - (evaluate(y) - evaluate(x))) < 1e-10
    return dict(zip(["win_probability", "mean_win", "mean_nonwin"], out, strict=True))


def main():
    parity = json.loads((OUT / "parity.json").read_text())
    assert parity["status"] == "PASS"
    contract = json.loads((OUT / "execution_contract.json").read_text())
    d22 = load(OLD / "direct_2022.csv")
    c23 = load(OUT / "control_trades_2023.csv")
    trace = load(OUT / "treatment_trace_rows_2023.csv")
    assert len(c23) == 237 and abs(math.fsum(c23.net_pnl) - 15663.044356264174) < 1e-7
    assert list(c23.columns) == list(load(OLD / "p13_control_trades.csv").columns)
    assert not key(trace).duplicated().any()
    direct_keys = set(key(trace.loc[trace.decision.eq("TRANSITION_ADMISSION_ABLATED")]))
    d23 = c23.loc[key(c23).isin(direct_keys)].copy()
    assert len(d22) == 173 and abs(math.fsum(d22.net_pnl) + 8163.217282531882) < 1e-8
    assert len(d23) == 131 and abs(math.fsum(d23.net_pnl) - 1489.0311650100994) < 1e-8
    direct = {2022: d22.copy(), 2023: d23}
    summaries = {}
    available_context = {}
    for year, frame in direct.items():
        assert frame.entry_market_state.eq("TRANSITION").all()
        assert not frame[["pair", "entry_time"]].isna().any().any()
        assert not frame.duplicated(["pair", "entry_time"]).any()
        time = pd.to_datetime(frame.entry_time, utc=True)
        assert time.dt.year.eq(year).all()
        frame["event_key"] = key(frame)
        frame["calendar_month"] = time.dt.strftime("%Y-%m")
        frame["calendar_quarter"] = time.dt.year.astype(str) + "Q" + time.dt.quarter.astype(str)
        frame["entry_hour_utc"] = time.dt.hour
        frame["entry_atr_fraction"] = frame.atr24_at_signal / frame.entry_price
        trace_path = (
            Path(contract["sources"]["--p13-trace"]["path"])
            if year == 2022
            else OUT / "control_trace_rows_2023.csv"
        )
        if year == 2022:
            assert digest(trace_path) == contract["sources"]["--p13-trace"]["sha256"]
        context = load(trace_path)
        assert not context.event_key.duplicated().any()
        columns = [c for c in context.columns if c.endswith("_before_event")]
        joined = frame.merge(
            context[["event_key", *columns]], on="event_key", how="left", validate="one_to_one"
        )
        assert len(joined) == len(frame)
        assert not joined[columns].isna().any().any()
        frame = joined.sort_values(["entry_time", "pair"]).reset_index(drop=True)
        direct[year] = frame
        frame.to_csv(
            OUT / f"direct_{year}.csv", index=False, lineterminator="\n", float_format="%.17g"
        )
        groups = {
            field: grouped(frame, field)
            for field in [
                "pair",
                "calendar_month",
                "calendar_quarter",
                "entry_hour_utc",
                "exit_reason",
                "exit_market_state",
                "support_families",
                "support_count",
            ]
        }
        summaries[str(year)] = {
            **stats(frame),
            "groups": groups,
            "entry_time_min": str(time.min()),
            "entry_time_max": str(time.max()),
        }
        fields = [
            "atr24_at_signal",
            "entry_atr_fraction",
            "membership_rank",
            "support_count",
            *columns,
        ]
        available_context[str(year)] = {
            col: distribution(pd.to_numeric(frame[col], errors="coerce")) for col in fields
        }
    a, b = direct[2022], direct[2023]
    common = sorted(set(a.pair) & set(b.pair))
    composition = {}
    for label, symbols in [
        ("common", common),
        ("only_2022", sorted(set(a.pair) - set(b.pair))),
        ("only_2023", sorted(set(b.pair) - set(a.pair))),
    ]:
        composition[label] = {
            "symbols": symbols,
            "2022": stats(a[a.pair.isin(symbols)]),
            "2023": stats(b[b.pair.isin(symbols)]),
        }
    within = mix = 0.0
    for symbol in common:
        x, y = a[a.pair.eq(symbol)], b[b.pair.eq(symbol)]
        within += (len(x) + len(y)) / 2 * (y.net_pnl.mean() - x.net_pnl.mean())
        mix += (x.net_pnl.mean() + y.net_pnl.mean()) / 2 * (len(y) - len(x))
    common_delta = (
        composition["common"]["2023"]["net_pnl"] - composition["common"]["2022"]["net_pnl"]
    )
    assert abs(within + mix - common_delta) < 1e-8
    composition["common_symmetric_decomposition"] = {
        "within_symbol_mean": within,
        "count_composition": mix,
        "delta": common_delta,
    }
    mean22, mean23 = math.fsum(a.net_pnl) / len(a), math.fsum(b.net_pnl) / len(b)
    excluded = c23.loc[c23.entry_market_state.eq("TRANSITION") & ~key(c23).isin(direct_keys)].copy()
    excluded["treatment_decision"] = key(excluded).map(
        dict(zip(key(trace), trace.decision, strict=True))
    )
    result = {
        "status": "PASS",
        "2022_direct_set_proven": True,
        "2023_direct_set_proven": True,
        "years": summaries,
        "available_entry_context": available_context,
        "common_vs_changing_symbols": composition,
        "mean_pnl_shapley_accounting": shapley_mean(a, b),
        "count_quality_accounting": {
            "delta": math.fsum(b.net_pnl) - math.fsum(a.net_pnl),
            "count_at_2022_mean": (len(b) - len(a)) * mean22,
            "quality_at_2023_count": len(b) * (mean23 - mean22),
        },
        "excluded_2023_entry_transition": excluded[
            ["pair", "entry_time", "net_pnl", "treatment_decision"]
        ].to_dict("records"),
        "all_2023_entry_transition_count": int(c23.entry_market_state.eq("TRANSITION").sum()),
        "causal_inference_limit": (
            "Accounting/descriptive attribution; no causal attribution to symbol, year, "
            "holding time, or exit state."
        ),
        "missing_fields": [
            "entry component scores",
            "entry liquidity/spread",
            "independent entry momentum/relative-strength measures",
            "frozen MFE",
            "frozen MAE",
        ],
        "governance": {
            "2024_access": False,
            "2025_access": False,
            "candidate_search": False,
            "production_change": False,
        },
        "artifacts": [
            {"path": str(p.relative_to(ROOT)), "sha256": digest(p)}
            for p in sorted(OUT.glob("*.csv"))
        ],
    }
    (OUT / "diagnostic_measurements.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                year: {k: v for k, v in s.items() if k not in ["groups"]}
                for year, s in summaries.items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
