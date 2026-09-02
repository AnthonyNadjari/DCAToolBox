"""Gate lab: find insurance that costs less premium without losing the payout.

The 200dma → cash gate charges ~9pp/yr post-2009 (whipsaw, missed rebounds)
for its 2000-2013 payout. This lab scores gate DESIGNS on both eras at once:

- PREMIUM era: 2009-07 → 2026-08, real CL2/LQQ prices. Cost = CAGR gap vs
  the ungated 70/30 CL2/LQQ mix.
- PAYOUT era: 2002-06 → 2013-09 (VIX3M/HY-OAS availability, ends at real-ESE
  splice), synthetic 2x on the ESE frame. Protection = CAGR and maxDD vs the
  ungated 2x, which did -1.7%/yr and -85% there.

Design axes (all monthly-check, signal from prev close, production SPX gate):
1. Destination when OFF: cash | unlevered ESE | half-leverage.
2. Condition: price>200dma | 200dma slope | trend OR slope (stay-in bias) |
   trend AND credit stress (HY OAS above its 200d avg) — exit only when both
   price trend and credit agree.
3. Two-tier: trend off → ESE; trend off AND credit stress → cash.

Fees: 0.5% per traded leg (lev→cash = 1 trade; lev→ese = 2 trades).
Cash refuge modeled at EUR 3M (money-market ETF; its own 0.5%x2 roughly
cancels the yield vs leaving PEA liquidités at 0%).

Overfitting guard: no variant is selected on one era; the deliverable is the
premium/payout frontier, and any winner must beat the base gate on BOTH eras
with sane neighbors, or it is reported as frontier information only.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from dataset import load
from post2009 import build_inputs_real
from rolling import FEE, build_inputs


def add_signals(df: pd.DataFrame) -> pd.DataFrame:
    spx = load("SPX Index")["PX_LAST"].dropna()
    sma = spx.rolling(200).mean()
    up = (spx > sma).astype(float)
    slope = (sma > sma.shift(21)).astype(float)
    hy = load("LF98OAS Index")["PX_LAST"].dropna()
    stress = (hy > hy.rolling(200).mean()).astype(float)
    idx = df.index
    df = df.copy()
    df["g_trend"] = up.reindex(idx).ffill()
    df["g_slope"] = slope.reindex(idx).ffill()
    df["g_stress"] = stress.reindex(idx).ffill()
    return df


def run(df: pd.DataFrame, w_lev_fn, w_base_fn) -> pd.Series:
    """Monthly-rebalanced (deposit-day) weights across lev/base/cash sleeves.

    Fee charged per traded leg: 0.5% x |change| on lev and on base.
    """
    month = df.index.to_period("M")
    is_dep = np.r_[True, month[1:] != month[:-1]]
    wl_t = w_lev_fn(df).to_numpy()
    wb_t = w_base_fn(df).to_numpy()
    rl = df["r_lev"].to_numpy()
    rb = df["r_base"].to_numpy()
    rc = df["r_cash"].to_numpy()
    wl = wb = 0.0
    out = np.zeros(len(df))
    for i in range(len(df)):
        cost = 0.0
        if is_dep[i] and np.isfinite(wl_t[i]) and np.isfinite(wb_t[i]):
            nl = float(np.clip(wl_t[i], 0, 1))
            nb = float(np.clip(wb_t[i], 0, 1 - nl))
            cost = (abs(nl - wl) + abs(nb - wb)) * FEE
            wl, wb = nl, nb
        out[i] = wl * rl[i] + wb * rb[i] + (1 - wl - wb) * rc[i] - cost
    return pd.Series(out, index=df.index)


ZERO = lambda d: pd.Series(0.0, index=d.index)  # noqa: E731
ONE = lambda d: pd.Series(1.0, index=d.index)  # noqa: E731

VARIANTS = {
    # name: (w_lev_fn, w_base_fn)
    "nogate": (ONE, ZERO),
    "trend_to_cash": (lambda d: d["g_trend"].shift(1), ZERO),
    "trend_to_ese": (lambda d: d["g_trend"].shift(1), lambda d: 1 - d["g_trend"].shift(1)),
    "trend_to_half": (lambda d: 0.5 + 0.5 * d["g_trend"].shift(1), ZERO),
    "slope_to_cash": (lambda d: d["g_slope"].shift(1), ZERO),
    "slope_to_ese": (lambda d: d["g_slope"].shift(1), lambda d: 1 - d["g_slope"].shift(1)),
    "trend_or_slope_cash": (
        lambda d: (d[["g_trend", "g_slope"]].max(axis=1)).shift(1),
        ZERO,
    ),
    "trend_or_slope_ese": (
        lambda d: (d[["g_trend", "g_slope"]].max(axis=1)).shift(1),
        lambda d: 1 - (d[["g_trend", "g_slope"]].max(axis=1)).shift(1),
    ),
    "trend_and_credit_cash": (
        lambda d: (1 - (1 - d["g_trend"]) * d["g_stress"]).shift(1),
        ZERO,
    ),
    "trend_and_credit_ese": (
        lambda d: (1 - (1 - d["g_trend"]) * d["g_stress"]).shift(1),
        lambda d: ((1 - d["g_trend"]) * d["g_stress"]).shift(1),
    ),
    "two_tier": (
        # on: full lev; trend off: ESE; trend off + credit stress: cash
        lambda d: d["g_trend"].shift(1),
        lambda d: ((1 - d["g_trend"]) * (1 - d["g_stress"])).shift(1),
    ),
}


def score(df: pd.DataFrame, label: str) -> list[dict]:
    yrs = (df.index[-1] - df.index[0]).days / 365.25
    rows = []
    for name, (fl, fb) in VARIANTS.items():
        p = (1 + run(df, fl, fb)).cumprod()
        dd = float((p / p.cummax() - 1).min())
        rows.append(
            {
                "era": label,
                "name": name,
                "cagr": round(float(p.iloc[-1] ** (1 / yrs) - 1), 4),
                "maxdd": round(dd, 3),
            }
        )
    return rows


def main() -> None:
    # premium era: real funds
    real = add_signals(build_inputs_real())
    real["r_lev"] = real["r_mix_lev"]  # 70/30 CL2/LQQ is the levered sleeve
    rows = score(real, "2009-2026 real")

    # payout era: synthetic 2x on ESE frame
    full = add_signals(build_inputs())
    pay = full.loc["2002-06-01":"2013-09-15"]
    rows += score(pay, "2002-2013 payout")

    json.dump(rows, open(Path(__file__).parent / "results_gate_lab.json", "w"), indent=1)

    byname: dict[str, dict] = {}
    for r in rows:
        byname.setdefault(r["name"], {})[r["era"]] = r
    print(f"{'variant':22s} {'09+ cagr':>9} {'09+ dd':>7} {'02-13 cagr':>11} {'02-13 dd':>9}")
    base = byname["nogate"]
    for name, d in sorted(byname.items(), key=lambda kv: -kv[1]["2009-2026 real"]["cagr"]):
        a, b = d["2009-2026 real"], d["2002-2013 payout"]
        print(f"{name:22s} {a['cagr']:>9.1%} {a['maxdd']:>7.0%} {b['cagr']:>11.1%} {b['maxdd']:>9.0%}")
    print(
        f"\npremium = CAGR below {base['2009-2026 real']['cagr']:.1%} (ungated, 09+); "
        f"payout = above {base['2002-2013 payout']['cagr']:.1%} / {base['2002-2013 payout']['maxdd']:.0%} dd (ungated, 02-13)"
    )


if __name__ == "__main__":
    main()
