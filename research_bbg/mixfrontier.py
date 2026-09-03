"""Campaign 5B: the FIXED-MIX frontier on the dispersed universe.

Campaign 3A killed flow ROTATION (switching subtracts value), but judged
fixed mixes only on single-path final wealth, IS/OOS. The open question for
a standing allocation: which FIXED flow mix — pre-registered, never
rebalanced by signal — is best judged on rolling 3y/5y/10y monthly-DCA
windows with savings metrics, across the dispersed EUR universe PLUS the
leveraged gated sleeve (the production rule) as one of the sleeves.

Discipline: the menu below is written BEFORE any result is read. ~14 mixes,
round numbers, each with an a-priori story. Judged vs the 100% SPX null.
A mix is a candidate only if it beats the incumbent (70/30 spx/ndx and/or
the gated-2x production sleeve) on BOTH the full sample and the 2009+ era
with sane neighbors; otherwise it is frontier information, not a pick.

Sleeves (EUR total return, daily, 1999-2026, from the Bloomberg caches):
spx, ndx, eur (Stoxx 600), em, r2k, jpn, gold, cash, lev2x (synthetic,
ungated), gated (synthetic 2x with the production 200dma/25%-off rule).

Flow-splitting across sleeves is exact (each sleeve is its own account,
compounding at its own realised return, nothing sold inside a sleeve).
Fee 0.5% on each risky purchase (production reality); the gated sleeve's
internal switching fees are already in its return stream.

Usage::

    python research_bbg/mixfrontier.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from alloc import build_panel
from gate_lab import add_signals, run, ZERO
from rolling import build_inputs

FEE = 0.005
CONTRIB = 1000.0
HORIZONS = (3, 5, 10)

# --- pre-registered menu (written before results; do not extend after) ---
MENU = {
    "spx100": {"spx": 1.0},
    "spx70_ndx30": {"spx": 0.7, "ndx": 0.3},
    "ew7": {"spx": 1 / 7, "ndx": 1 / 7, "eur": 1 / 7, "em": 1 / 7, "r2k": 1 / 7, "jpn": 1 / 7, "gold": 1 / 7},
    "spx60_em20_gold20": {"spx": 0.6, "em": 0.2, "gold": 0.2},
    "spx50_eur20_em15_gold15": {"spx": 0.5, "eur": 0.2, "em": 0.15, "gold": 0.15},
    "spx80_gold20": {"spx": 0.8, "gold": 0.2},
    "spx50_ndx20_em15_gold15": {"spx": 0.5, "ndx": 0.2, "em": 0.15, "gold": 0.15},
    "maxdisp": {"spx": 0.4, "ndx": 0.2, "em": 0.1, "r2k": 0.1, "eur": 0.1, "gold": 0.1},
    "lev100_nogate": {"lev2x": 1.0},
    "gated100": {"gated": 1.0},
    "gated70_gold30": {"gated": 0.7, "gold": 0.3},
    "gated50_spx25_gold25": {"gated": 0.5, "spx": 0.25, "gold": 0.25},
    "gated70_em15_gold15": {"gated": 0.7, "em": 0.15, "gold": 0.15},
    "gated50_spx50": {"gated": 0.5, "spx": 0.5},
}


def build_sleeves() -> pd.DataFrame:
    """Daily sleeve returns on the dispersed panel's calendar."""
    panel = build_panel()
    sleeves = panel.pct_change().fillna(0.0)

    lev = add_signals(build_inputs())
    wl = lambda d: 0.25 + 0.75 * d["g_trend"].shift(1)  # noqa: E731
    lev["r_gated"] = run(lev, wl, ZERO)
    for col, out in (("r_lev", "lev2x"), ("r_gated", "gated")):
        sleeves[out] = lev[col].reindex(panel.index).ffill().fillna(0.0)
    return sleeves.dropna()


def dca_windows(rets: np.ndarray, years: int) -> np.ndarray:
    """Final wealth per unit of monthly contribution, all rolling windows."""
    h = years * 12
    n = len(rets)
    if n < h:
        return np.array([])
    g = np.cumprod(1.0 + rets)
    inv2 = np.concatenate([[1.0], 1.0 / g])
    cum2 = np.concatenate([[0.0], np.cumsum(inv2)])
    ends = g[h - 1 :]
    sums = cum2[h : n + 1] - cum2[: n - h + 1]
    return (1 - FEE) * ends * sums / h


def score_mix(sleeves: pd.DataFrame, w: dict) -> pd.Series:
    """Monthly return series of the flow-mix portfolio (exact flow splitting)."""
    r = sum(sleeves[k] * v for k, v in w.items())
    return r.resample("M").apply(lambda x: (1 + x).prod() - 1)


def main() -> None:
    sleeves = build_sleeves()
    print(f"sleeves: {sleeves.index[0].date()} -> {sleeves.index[-1].date()}")
    monthly = pd.DataFrame({name: score_mix(sleeves, w) for name, w in MENU.items()}).dropna()
    dates = monthly.index
    era2009 = dates >= "2009-01-01"

    null = dca_windows(monthly["spx100"].to_numpy(), 5)
    out = []
    for name in MENU:
        r = monthly[name].to_numpy()
        row = {"name": name}
        for era, mask in (("all", np.ones(len(r), bool)), ("post09", era2009)):
            rr = r[mask]
            row[era] = {}
            for yrs in HORIZONS:
                wins = dca_windows(rr, yrs)
                if len(wins) == 0:
                    continue
                nw = dca_windows(monthly["spx100"].to_numpy()[mask], yrs)
                m = min(len(wins), len(nw))
                exc = wins[:m] / nw[:m] - 1.0
                row[era][f"y{yrs}"] = {
                    "median": round(float(np.median(wins)), 3),
                    "p5": round(float(np.percentile(wins, 5)), 3),
                    "p_below": round(float((wins < 1).mean()), 3),
                    "win_vs_spx": round(float((exc > 0).mean()), 3),
                    "exc_median": round(float(np.median(exc)), 4),
                }
        out.append(row)
    json.dump(out, open(Path(__file__).parent / "results_mixfrontier.json", "w"), indent=1)

    for era in ("all", "post09"):
        print(f"\n=== {era} — rolling 5y windows (multiple of contributions) ===")
        print(f"{'mix':24s} {'med':>6} {'p5':>6} {'P<1':>6} {'win%':>6} {'exc-med':>8}")
        for r in sorted(out, key=lambda r: -r[era].get("y5", {}).get("median", 0)):
            k = r[era].get("y5")
            if not k:
                continue
            print(
                f"{r['name']:24s} {k['median']:6.2f} {k['p5']:6.2f} {100 * k['p_below']:5.0f}% "
                f"{100 * k['win_vs_spx']:5.0f}% {k['exc_median']:>+8.1%}"
            )


if __name__ == "__main__":
    main()
