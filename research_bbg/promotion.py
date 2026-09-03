"""Promotion pipeline for the mixfrontier survivors (conception-doc step 9).

Candidates that looked better than the incumbent on the dispersed panel are
re-tested here at a higher evidentiary standard before they may touch the
production rule:

1. LONGER SAMPLE — gold and the gated sleeve both reach 1989 (the dispersed
   panel started 1999). 1989-2026 adds the early-90s and the full dot-com
   top. EM candidates stay 1999+ (data limit).
2. WRAPPER COST — XAU spot is frictionless; a real gold sleeve would cost.
   Scored at 0% and 0.3%/yr drag.
3. CHECK-DAY ROBUSTNESS — the gated component inside the mix is re-checked
   on the 5th/10th/15th/20th trading day of the month (finding A: day-0 is
   flattered). A candidate must hold up across phases.
4. Eras: full / pre-2009 starts / post-2009 starts; rolling 3y/5y/10y
   monthly-DCA windows, savings metrics, win vs the 100% SPX null.

Menu (survivors + incumbents as references; nothing else added):
gated100 (production), lev100_nogate, gated70_gold30, gated70_em15_gold15,
gated50_spx25_gold25.

Usage::

    python research_bbg/promotion.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from alloc import build_panel
from dataset import load
from mixfrontier import dca_windows
from rolling import FEE, build_inputs

GOLD_DRAG = 0.003  # realistic gold-wrapper cost sensitivity
HORIZONS = (3, 5, 10)
CHECK_DAYS = (0, 5, 10, 15, 20)

CANDIDATES = ("gated100", "lev100_nogate", "gated70_gold30", "gated70_em15_gold15", "gated50_spx25_gold25")


def gated_series(idx: pd.DatetimeIndex, check_day: int) -> pd.Series:
    """Production-rule (200dma, off keeps 25%) daily returns, phase-shifted check."""
    df = build_inputs()
    spx = load("SPX Index")["PX_LAST"].dropna()
    up = (spx > spx.rolling(200).mean()).astype(float)
    g = up.reindex(df.index).ffill()
    wl_t = (0.25 + 0.75 * g.shift(1)).to_numpy()

    s = pd.Series(df.index, index=df.index)
    pos = s.groupby(df.index.to_period("M")).cumcount()
    size = s.groupby(df.index.to_period("M")).transform("size")
    mask = (pos == np.minimum(check_day, size - 1)).to_numpy()

    rl = df["r_lev"].to_numpy()
    rc = df["r_cash"].to_numpy()
    wl = 0.0
    out = np.zeros(len(df))
    for i in range(len(df)):
        cost = 0.0
        if mask[i] and np.isfinite(wl_t[i]):
            nl = float(np.clip(wl_t[i], 0, 1))
            cost = abs(nl - wl) * FEE
            wl = nl
        out[i] = wl * rl[i] + (1 - wl) * rc[i] - cost
    return pd.Series(out, index=df.index).reindex(idx).fillna(0.0)


def sleeves_1989(idx: pd.DatetimeIndex, check_day: int, gold_drag: float) -> pd.DataFrame:
    """Long-sample sleeves on the ESE-frame calendar: gated, lev2x, spx, gold."""
    df = build_inputs()
    out = pd.DataFrame(index=idx)
    out["gated"] = gated_series(idx, check_day)
    out["lev2x"] = df["r_lev"].reindex(idx).fillna(0.0)
    out["spx"] = df["r_base"].reindex(idx).fillna(0.0)
    fx = load("EURUSD Curncy")["PX_LAST"]
    xau = load("XAU Curncy")["PX_LAST"].dropna()
    gold_eur = xau / fx.reindex(xau.index).ffill()
    out["gold"] = (gold_eur.pct_change() - gold_drag / 252).reindex(idx).ffill().fillna(0.0)
    return out


def windows_report(r: np.ndarray, null: np.ndarray) -> dict:
    rep = {}
    for y in HORIZONS:
        w, nw = dca_windows(r, y), dca_windows(null, y)
        if len(w) < 10:
            continue
        m = min(len(w), len(nw))
        exc = w[:m] / nw[:m] - 1.0
        rep[f"y{y}"] = {
            "median": round(float(np.median(w)), 3),
            "p5": round(float(np.percentile(w, 5)), 3),
            "p_below": round(float((w < 1).mean()), 3),
            "win_vs_spx": round(float((exc > 0).mean()), 3),
            "exc_median": round(float(np.median(exc)), 4),
        }
    return rep


def main() -> None:
    # --- long-sample frame: ESE calendar 1989+ ---
    df0 = build_inputs()
    idx = df0.index
    panel = build_panel()  # for the EM candidate (1999+)

    out = []
    for check_day in CHECK_DAYS:
        for gold_drag in (0.0, GOLD_DRAG):
            sl = sleeves_1989(idx, check_day, gold_drag)
            monthly = (1 + sl).resample("M").prod() - 1
            monthly = monthly.dropna()
            mixes = {
                "gated100": monthly["gated"],
                "lev100_nogate": monthly["lev2x"],
                "gated70_gold30": 0.7 * monthly["gated"] + 0.3 * monthly["gold"],
                "gated50_spx25_gold25": 0.5 * monthly["gated"] + 0.25 * monthly["spx"] + 0.25 * monthly["gold"],
            }
            for name, m in mixes.items():
                r_all = m.to_numpy()
                for era, mask in (
                    ("all", np.ones(len(m), bool)),
                    ("pre09", (m.index < "2009-01-01")),
                    ("post09", (m.index >= "2009-01-01")),
                ):
                    out.append(
                        {
                            "name": name,
                            "check_day": check_day,
                            "gold_drag": gold_drag,
                            "era": era,
                            **{
                                k: v
                                for k, v in windows_report(
                                    r_all[mask], monthly["spx"].to_numpy()[mask]
                                ).items()
                            },
                        }
                    )

        # --- EM candidate: 1999+ only (panel data limit), same machinery ---
        pidx = panel.index
        p_monthly = pd.DataFrame(
            {
                "gated": gated_series(pidx, check_day),
                "gold": (panel["gold"].pct_change() - gold_drag / 252).fillna(0.0),
                "em": panel["em"].pct_change().fillna(0.0),
                "spx": panel["spx"].pct_change().fillna(0.0),
            }
        )
        p_monthly = ((1 + p_monthly).resample("M").prod() - 1).dropna()
        m = 0.7 * p_monthly["gated"] + 0.15 * p_monthly["em"] + 0.15 * p_monthly["gold"]
        for era, mask in (
            ("all", np.ones(len(m), bool)),
            ("post09", (m.index >= "2009-01-01")),
        ):
            out.append(
                {
                    "name": "gated70_em15_gold15",
                    "check_day": check_day,
                    "gold_drag": gold_drag,
                    "era": era,
                    **windows_report(m.to_numpy()[mask], p_monthly["spx"].to_numpy()[mask]),
                }
            )
    json.dump(out, open(Path(__file__).parent / "results_promotion.json", "w"), indent=1)

    # readable view: 5y windows, all eras, per check day, drag 0.3%
    for era in ("all", "post09", "pre09"):
        print(f"\n=== {era} — rolling 5y (gold drag 0.3%/yr) ===")
        print(f"{'candidate':22s} {'day':>4} {'med':>6} {'p5':>6} {'P<1':>6} {'win%':>6} {'exc-med':>8}")
        for r in out:
            if r["era"] != era or r["gold_drag"] != GOLD_DRAG or "y5" not in r:
                continue
            k = r["y5"]
            print(
                f"{r['name']:22s} {r['check_day']:4d} {k['median']:6.2f} {k['p5']:6.2f} "
                f"{100 * k['p_below']:5.0f}% {100 * k['win_vs_spx']:5.0f}% {k['exc_median']:>+8.1%}"
            )


if __name__ == "__main__":
    main()
