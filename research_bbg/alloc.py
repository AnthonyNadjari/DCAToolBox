"""Campaign 3A: monthly FLOW ALLOCATION across a dispersed universe.

The timing question is closed; this asks WHERE each month's 1000 EUR goes.
Universe (all converted to EUR total-return): S&P 500, Nasdaq-100, Europe
(Stoxx 600), MSCI EM, Russell 2000, MSCI Japan, gold, and EUR 3M cash.
Buy-only, never sell, fee 0.5% on every risky purchase (cash sleeve free).

Discipline (lesson of the July momentum autopsy): every dynamic rule is
judged BOTH against the null (100% S&P) AND against the fixed mix with the
same realized average weights -- a rotation that loses to its own average
mix is a beta choice wearing a costume, not a signal.

IS: 1999 -> 2013-09-15 | OOS: real-fund era 2013-09-16 ->.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dataset import load

FEE = 0.005
BUDGET = 1000.0
IS_END = pd.Timestamp("2013-09-15")

RISKY = {
    "spx": ("SPXT Index", True),      # (ticker, is_usd)
    "ndx": ("XNDX Index", True),
    "eur": ("SXXR Index", False),
    "em": ("NDUEEGF Index", True),
    "r2k": ("RU20INTR Index", True),
    "jpn": ("NDDUJN Index", True),
    "gold": ("XAU Curncy", True),
}


def build_panel() -> pd.DataFrame:
    fx = load("EURUSD Curncy")["PX_LAST"]
    cols = {}
    for name, (tk, usd) in RISKY.items():
        s = load(tk)["PX_LAST"]
        if usd:
            s = s / fx.reindex(s.index).ffill()
        cols[name] = s
    panel = pd.DataFrame(cols).dropna(how="any")
    r3m = load("EUR003M Index")["PX_LAST"].reindex(panel.index).ffill() / 100.0
    panel["cash"] = (1 + r3m / 252).cumprod()
    return panel


def simulate_flow(panel: pd.DataFrame, weight_fn, seg: slice) -> dict:
    """weight_fn(i, panel) -> dict asset->weight (sums to 1). Fills at bar i."""
    px = panel.to_numpy(dtype=float)
    dates = panel.index[seg]
    lo = seg.start or 0
    month = dates.to_period("M")
    is_dep = np.r_[True, month[1:] != month[:-1]]
    names = list(panel.columns)
    shares = np.zeros(len(names))
    wsum = np.zeros(len(names))
    ndep = 0
    for j in range(len(dates)):
        if not is_dep[j]:
            continue
        i = lo + j
        w = weight_fn(i, panel)
        ndep += 1
        for k, nm in enumerate(names):
            f = w.get(nm, 0.0)
            if f <= 0:
                continue
            fee = 0.0 if nm == "cash" else FEE
            shares[k] += BUDGET * f * (1 - fee) / px[i, k]
            wsum[k] += f
    final = float((shares * px[(seg.stop or len(panel)) - 1]).sum())
    avg_w = {nm: round(wsum[k] / max(ndep, 1), 3)
             for k, nm in enumerate(names) if wsum[k] > 0.001}
    return {"final": round(final), "avg_w": avg_w, "months": ndep}


def fixed(weights: dict):
    return lambda i, p: weights


def make_strategies(panel: pd.DataFrame) -> dict:
    risky = [c for c in panel.columns if c != "cash"]
    logp = np.log(panel[risky])
    mom = logp.shift(21) - logp.shift(252)                # 12-1 momentum
    vol = panel[risky].pct_change().rolling(63).std()
    sma200 = panel[risky] / panel[risky].rolling(200).mean() - 1
    cash_12m = panel["cash"].pct_change(231).shift(21)
    abs_ok = panel[risky].pct_change(231).shift(21).sub(cash_12m, axis=0)

    def dual_top(n):
        def f(i, p):
            m = mom.iloc[i - 1]
            if m.isna().any():
                return {"spx": 1.0}
            w = {}
            for nm in m.nlargest(n).index:
                ok = abs_ok.iloc[i - 1][nm]
                key = nm if (np.isfinite(ok) and ok > 0) else "cash"
                w[key] = w.get(key, 0.0) + 1.0 / n
            return w
        return f

    def rel_top(n):
        def f(i, p):
            m = mom.iloc[i - 1]
            if m.isna().any():
                return {"spx": 1.0}
            return {nm: 1.0 / n for nm in m.nlargest(n).index}
        return f

    def inv_vol(i, p):
        v = vol.iloc[i - 1]
        if v.isna().any():
            return {"spx": 1.0}
        iv = 1.0 / v
        return (iv / iv.sum()).to_dict()

    def trend_each(i, p):
        t = sma200.iloc[i - 1]
        if t.isna().any():
            return {"spx": 1.0}
        w = {}
        share = 1.0 / len(risky)
        for nm in risky:
            key = nm if t[nm] > 0 else "cash"
            w[key] = w.get(key, 0.0) + share
        return w

    def mom_rank(i, p):
        m = mom.iloc[i - 1]
        if m.isna().any():
            return {"spx": 1.0}
        r = m.rank()
        return (r / r.sum()).to_dict()

    return {
        "FIX_spx100": fixed({"spx": 1.0}),
        "FIX_spx70_ndx30": fixed({"spx": 0.7, "ndx": 0.3}),
        "FIX_ew7": fixed({nm: 1.0 / 7 for nm in risky}),
        "FIX_spx60_em20_gold20": fixed({"spx": 0.6, "em": 0.2, "gold": 0.2}),
        "FIX_spx50_eur20_em15_gold15": fixed({"spx": 0.5, "eur": 0.2, "em": 0.15, "gold": 0.15}),
        "FIX_spx80_gold20": fixed({"spx": 0.8, "gold": 0.2}),
        "dual_mom_top1": dual_top(1),
        "dual_mom_top2": dual_top(2),
        "rel_mom_top1": rel_top(1),
        "rel_mom_top2": rel_top(2),
        "inv_vol": inv_vol,
        "trend_gate_each": trend_each,
        "mom_rank_weight": mom_rank,
    }


def main() -> None:
    panel = build_panel()
    cut = int(panel.index.searchsorted(IS_END, side="right"))
    segs = {"is": slice(0, cut), "oos": slice(cut, len(panel))}
    out = []
    for name, fn in make_strategies(panel).items():
        row = {"name": name}
        for s, sl in segs.items():
            row[s] = simulate_flow(panel, fn, sl)
        out.append(row)
    ref = {s: next(r for r in out if r["name"] == "FIX_spx100")[s]["final"] for s in segs}
    for r in out:
        for s in segs:
            r[s]["vs_spx"] = round(r[s]["final"] / ref[s] - 1, 4)
    json.dump(out, open(Path(__file__).parent / "results_alloc.json", "w"), indent=1)
    print(f"panel {panel.index[0].date()} -> {panel.index[-1].date()}\n")
    print(f"{'strategy':30s} {'IS final':>10} {'vs spx':>8} {'OOS final':>10} {'vs spx':>8}")
    for r in sorted(out, key=lambda r: -r["oos"]["vs_spx"]):
        print(f"{r['name']:30s} {r['is']['final']:>10,} {r['is']['vs_spx']:>+8.2%} "
              f"{r['oos']['final']:>10,} {r['oos']['vs_spx']:>+8.2%}")
    print("\nrealized avg weights (OOS):")
    for r in out:
        if not r["name"].startswith("FIX"):
            print(f"  {r['name']:26s} {r['oos']['avg_w']}")


if __name__ == "__main__":
    main()
