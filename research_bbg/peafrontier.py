"""Campaign 5C: the fixed-mix frontier priced on REAL PEA wrappers.

Campaign 5B ran on indices. This re-prices it on what the investor actually
buys: every sleeve's index return minus the true wrapper TER (IS_PEA-verified
via Bloomberg on 2026-09-03). The splice method (index minus TER for the
pre-fund era) is the one validated on ESE at 26bp/yr (dataset.py).

PEA-verified universe (IS_PEA = Y): ESE 0.14, PUST 0.30, PANX 0.30, CW8 0.38,
C50 0.09, ETZ 0.19, PAEEM 0.30, RS2K 0.35, CL2 0.50, LQQ 0.60.
NOT PEA (IS_PEA = N): GDX FP (gold miners), JPN FP — both excluded here.
Japan therefore DROPS OUT of the PEA frontier; gold stays index-only as a
clearly-flagged non-implementable reference.

Pre-registered menu: the PEA-real versions of every mix that mattered in 5B,
plus CW8 as the popular one-line alternative, plus the PEA-implementable
cousin of the gold mix (EM + Russell 2000 as the diversifiers).

Usage::

    python research_bbg/peafrontier.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from alloc import build_panel
from gate_lab import add_signals, run, ZERO
from mixfrontier import dca_windows
from rolling import build_inputs

FEE = 0.005
HORIZONS = (5, 10)

# index sleeve -> (PEA wrapper, TER %/yr). jpn/gold have NO wrapper.
WRAPPERS = {
    "spx": ("ESE", 0.0014),
    "ndx": ("PUST", 0.0030),
    "eur": ("ETZ", 0.0019),
    "em": ("PAEEM", 0.0030),
    "r2k": ("RS2K", 0.0035),
}

MENU = {
    "ese100": {"spx": 1.0},
    "ese70_pust30": {"spx": 0.7, "ndx": 0.3},
    "cw8_vs_ese": {"world": 1.0},  # CW8 real prices, 2009+ only
    "ew_pea": {"spx": 0.2, "ndx": 0.2, "eur": 0.2, "em": 0.2, "r2k": 0.2},
    "ese50_etz20_em15_r2k15": {"spx": 0.5, "eur": 0.2, "em": 0.15, "r2k": 0.15},
    "lev100_nogate": {"lev2x": 1.0},
    "gated100": {"gated": 1.0},
    "gated70_em15_r2k15": {"gated": 0.7, "em": 0.15, "r2k": 0.15},
    "gated70_gold30_idx": {"gated": 0.7, "gold": 0.3},  # NON-PEA reference
    "gold30_idx_spx70": {"spx": 0.7, "gold": 0.3},  # NON-PEA reference
}


def build_sleeves() -> pd.DataFrame:
    panel = build_panel()  # index levels, EUR
    rets = pd.DataFrame(index=panel.index)
    for name, (wrapper, ter) in WRAPPERS.items():
        rets[name] = panel[name].pct_change().fillna(0.0) - ter / 252
    rets["gold"] = panel["gold"].pct_change().fillna(0.0)  # index, no wrapper
    rets["world"] = np.nan  # filled from real CW8 prices below

    lev = add_signals(build_inputs())
    wl = lambda d: 0.25 + 0.75 * d["g_trend"].shift(1)  # noqa: E731
    lev["r_gated"] = run(lev, wl, ZERO)
    rets["lev2x"] = lev["r_lev"].reindex(panel.index).fillna(0.0)
    rets["gated"] = lev["r_gated"].reindex(panel.index).fillna(0.0)

    from dataset import load

    cw8 = load("CW8 FP Equity")["TOT_RETURN_INDEX_GROSS_DVDS"].dropna()
    rets["world"] = cw8.pct_change().reindex(panel.index)
    return rets


def main() -> None:
    sleeves = build_sleeves()
    print(f"panel: {sleeves.index[0].date()} -> {sleeves.index[-1].date()}")

    out = []
    for name, w in MENU.items():
        r = sum(sleeves[k] * v for k, v in w.items())
        m = ((1 + r).resample("M").prod() - 1).dropna()
        r_all = m.to_numpy()
        null = ((1 + sleeves["spx"]).resample("M").prod() - 1).reindex(m.index).to_numpy()
        row = {"name": name, "from": str(m.index[0].date())}
        for era, mask in (
            ("all", np.ones(len(m), bool)),
            ("post09", m.index >= "2009-01-01"),
        ):
            row[era] = {}
            for y in HORIZONS:
                wv, nw = dca_windows(r_all[mask], y), dca_windows(null[mask], y)
                if len(wv) < 10 or len(nw) < 10:
                    continue
                n = min(len(wv), len(nw))
                exc = wv[:n] / nw[:n] - 1.0
                row[era][f"y{y}"] = {
                    "median": round(float(np.median(wv)), 3),
                    "p5": round(float(np.percentile(wv, 5)), 3),
                    "p_below": round(float((wv < 1).mean()), 3),
                    "win_vs_ese": round(float((exc > 0).mean()), 3),
                    "exc_median": round(float(np.median(exc)), 4),
                }
        out.append(row)
    json.dump(out, open(Path(__file__).parent / "results_peafrontier.json", "w"), indent=1)

    for era in ("all", "post09"):
        print(f"\n=== {era} — rolling 5y, real PEA wrapper costs ===")
        print(f"{'mix':24s} {'from':>10} {'med':>6} {'p5':>6} {'P<1':>6} {'win%':>6} {'exc-med':>8}")
        for r in sorted(out, key=lambda r: -r[era].get("y5", {}).get("exc_median", -9)):
            k = r[era].get("y5")
            if not k:
                continue
            print(
                f"{r['name']:24s} {r['from']:>10} {k['median']:6.2f} {k['p5']:6.2f} "
                f"{100 * k['p_below']:5.0f}% {100 * k['win_vs_ese']:5.0f}% {k['exc_median']:>+8.1%}"
            )


if __name__ == "__main__":
    main()
