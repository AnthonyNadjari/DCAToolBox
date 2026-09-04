"""Block-bootstrap Monte-Carlo of the production rule (conception-doc step 9.5).

The trend gate's entire payout case rests on ONE historical episode
(2000-09 double bear, seen through the synthetic 2x backfill). Rolling
windows overlap (~7 independent 5y windows in 37 years). This bootstrap
generates alternative histories by resampling the JOINT daily return vector
(r_base, r_lev, r_cash, r_spx) in 42-trading-day blocks, so volatility
clustering and the leverage/drag linkage survive but the crash calendar is
shuffled: synthetic histories contain different numbers, shapes and orders
of bears.

On each synthetic history the full machine is replayed:
- gate = synthetic SPX vs its own 200dma, signal from prev close,
- monthly check every 21 bars (bootstrap destroys the calendar),
- weights: production off=25% rule, 0.5% fee per traded leg,
- DCA: deposit every 21 bars, windows of 60 deposits (5y),
- nulls: hold 1x, hold ungated 2x, same machine.

Questions answered:
1. P(gated 2x beats 1x on 5y windows) across histories — is the insurance
   verdict robust to crash-shape luck?
2. P(gated beats UNGATED 2x) — the net of premium vs payout, unconditional.
3. Distribution of maxDD for the three policies.

Usage::

    python research_bbg/bootstrap.py [--paths 500] [--seed 7]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from dataset import load
from rolling import FEE, build_inputs

BLOCK = 42  # ~2 months, per the conception doc
MONTH = 21  # synthetic "month" in bars


def make_frame() -> pd.DataFrame:
    df = build_inputs()[["r_base", "r_lev", "r_cash"]]
    spx = load("SPX Index")["PX_LAST"].dropna()
    df["r_spx"] = spx.reindex(df.index).ffill().pct_change().fillna(0.0)
    fx = load("EURUSD Curncy")["PX_LAST"]
    xau = load("XAU Curncy")["PX_LAST"].dropna()
    gold_eur = xau / fx.reindex(xau.index).ffill()
    df["r_gold"] = gold_eur.pct_change().reindex(df.index).ffill().fillna(0.0)
    return df.dropna()


def resample(df: pd.DataFrame, rng: np.random.Generator, block: int = BLOCK) -> np.ndarray:
    """One bootstrap path: joint rows resampled in block-length blocks."""
    n = len(df)
    starts = rng.integers(0, n - block, size=int(np.ceil(n / block)) + 1)
    idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
    return df.to_numpy()[idx]


def machine(cols: np.ndarray, off_keep: float) -> dict:
    """Replay the production machine on one synthetic history."""
    r_base, r_lev, r_cash, r_spx, r_gold = cols.T
    n = len(cols)

    # gate on the synthetic SPX path (prev close vs its own 200dma)
    spx = np.cumprod(1.0 + r_spx)
    sma = pd.Series(spx).rolling(200).mean().to_numpy()
    with np.errstate(invalid="ignore"):
        on = spx > sma  # False during warm-up (NaN average)
    gate = np.concatenate([[False], on[:-1]])  # day t uses close of t-1

    is_check = np.zeros(n, dtype=bool)
    is_check[::MONTH] = True

    def strat_returns(r_risky: np.ndarray, gated: bool) -> np.ndarray:
        w_t = (off_keep + (1 - off_keep) * gate) if gated else np.ones(n)
        w = 0.0
        out = np.zeros(n)
        for i in range(n):
            cost = 0.0
            if is_check[i]:
                nw = w_t[i]
                cost = abs(nw - w) * FEE
                w = nw
            out[i] = w * r_risky[i] + (1 - w) * r_cash[i] - cost
        return out

    rets = {
        "hold1x": r_base,
        "ungated2x": strat_returns(r_lev, gated=False),
        "gated": strat_returns(r_lev, gated=True),
        "gold": r_gold,
    }

    out = {}
    prices = {k: np.cumprod(1.0 + v) for k, v in rets.items()}
    n_months = n // MONTH
    h = 60  # 5y in synthetic months
    for name, p in prices.items():
        pm = p[MONTH - 1 :: MONTH][: n_months + 1]  # month-end prices
        if len(pm) <= h + 1:
            out[name] = {"win5": np.nan, "med5": np.nan, "p5_5": np.nan, "maxdd": np.nan}
            continue
        # DCA window wealth per unit contribution: sum of P_end/P_dep over deposits
        wins = np.array([np.sum(pm[i + h] / pm[i : i + h]) for i in range(len(pm) - h)])
        out[name] = {"wins5": (1 - FEE) * wins / h}
        dd = p / np.maximum.accumulate(p) - 1.0
        out[name]["maxdd"] = float(dd.min())

    def excess_w(a: np.ndarray, b: np.ndarray) -> dict:
        m = min(len(a), len(b))
        exc = a[:m] / b[:m] - 1.0
        return {
            "win5": float((exc > 0).mean()),
            "med5": float(np.median(exc)),
            "p5_5": float(np.percentile(exc, 5)),
        }

    def stats_w(w: np.ndarray) -> dict:
        return {
            "p_below": float((w < 1).mean()),
            "p5": float(np.percentile(w, 5)),
            "median": float(np.median(w)),
        }

    mix = 0.7 * out["gated"]["wins5"] + 0.3 * out["gold"]["wins5"]
    return {
        "gated_vs_1x": excess_w(out["gated"]["wins5"], out["hold1x"]["wins5"]),
        "gated_vs_ungated": excess_w(out["gated"]["wins5"], out["ungated2x"]["wins5"]),
        "ungated_vs_1x": excess_w(out["ungated2x"]["wins5"], out["hold1x"]["wins5"]),
        "mix_vs_1x": excess_w(mix, out["hold1x"]["wins5"]),
        "mix_vs_gated": excess_w(mix, out["gated"]["wins5"]),
        "wins_gated": stats_w(out["gated"]["wins5"]),
        "wins_mix": stats_w(mix),
        "maxdd_1x": out["hold1x"]["maxdd"],
        "maxdd_ungated": out["ungated2x"]["maxdd"],
        "maxdd_gated": out["gated"]["maxdd"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", type=int, default=500)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--off", type=float, default=0.25, help="leverage kept when gate off")
    ap.add_argument("--block", type=int, default=BLOCK, help="bootstrap block length in bars")
    args = ap.parse_args()

    df = make_frame()
    print(f"source frame: {df.index[0].date()} -> {df.index[-1].date()} ({len(df)} bars)")
    rng = np.random.default_rng(args.seed)

    keys = None
    acc: dict[str, list] = {}
    for b in range(args.paths):
        res = machine(resample(df, rng, args.block), args.off)
        if keys is None:
            keys = list(res.keys())
            acc = {k: [] for k in keys}
        for k in keys:
            acc[k].append(res[k])
        if (b + 1) % 100 == 0:
            print(f"  {b + 1}/{args.paths} paths")

    summary: dict = {"paths": args.paths, "block": args.block, "off_keep": args.off}
    print(f"\n=== {args.paths} bootstrap histories, off={args.off:.0%}, 5y DCA windows ===")
    for k in ("gated_vs_1x", "ungated_vs_1x", "gated_vs_ungated", "mix_vs_1x", "mix_vs_gated"):
        w = pd.DataFrame(acc[k])
        summary[k] = {
            "P(win>50%)": round(float((w["win5"] > 0.5).mean()), 3),
            "median_win": round(float(w["win5"].median()), 3),
            "median_med": round(float(w["med5"].median()), 4),
            "p10_med": round(float(w["med5"].quantile(0.1)), 4),
        }
        print(
            f"{k:18s} P(win-rate>50%)={summary[k]['P(win>50%)']:5.1%} "
            f"median win-rate={summary[k]['median_win']:5.1%} "
            f"median excess={summary[k]['median_med']:+7.1%} "
            f"p10 excess={summary[k]['p10_med']:+7.1%}"
        )
    for k in ("wins_gated", "wins_mix"):
        w = pd.DataFrame(acc[k])
        summary[k] = {
            "P(p_below<10%)": round(float((w["p_below"] < 0.10).mean()), 3),
            "median_p_below": round(float(w["p_below"].median()), 3),
            "median_p5": round(float(w["p5"].median()), 3),
            "median_med": round(float(w["median"].median()), 3),
        }
        print(
            f"{k:18s} median P<1={summary[k]['median_p_below']:5.1%} "
            f"P(P<1 under 10%)={summary[k]['P(p_below<10%)']:5.1%} "
            f"median p5-mult={summary[k]['median_p5']:5.2f} "
            f"median mult={summary[k]['median_med']:5.2f}"
        )
    for k in ("maxdd_1x", "maxdd_ungated", "maxdd_gated"):
        arr = np.array(acc[k])
        summary[k] = {
            "median": round(float(np.median(arr)), 3),
            "p90": round(float(np.quantile(arr, 0.9)), 3),
        }
        print(f"{k:18s} median={summary[k]['median']:6.1%}  p90(worst)={summary[k]['p90']:6.1%}")

    out_name = f"results_bootstrap_b{args.block}_off{int(args.off * 100)}.json"
    json.dump(summary, open(Path(__file__).parent / out_name, "w"), indent=1)


if __name__ == "__main__":
    main()
