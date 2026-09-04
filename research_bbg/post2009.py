"""Post-2009 re-run: every campaign-4 strategy evaluated only on 2009-07 → 2026-08.

Rationale: the investor's usable history starts where the real funds start
(CL2 FP 2009-06-29, LQQ FP 2009-01-02). Pre-2009 evidence mixes synthetics
and a regime (2000-09 double bear) that dominates the trend gate's payoff.
This run answers: on REAL fund prices only, in the post-GFC regime, what do
the same rules deliver?

Everything real: CL2/LQQ/ESE Paris prices in EUR (ESE backfilled 2009-13 from
SPXT/EURUSD with the validated splice). Fees: 0.5% on every trade, buys and
sells alike (BoursoBank PEA standard rate; sells are never free).

Judged exactly like campaign 4: all rolling 5y monthly-DCA windows (10y also
reported) — final wealth vs the same-start null.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from dataset import build_asset_frame, load
from rolling import FEE, rolling_dca, strat_returns

START = "2009-07-01"


def build_inputs_real() -> pd.DataFrame:
    """Daily EUR return frame from real fund prices, START onward."""
    base = build_asset_frame()["close"]  # ESE frame (real from 2013, splice before)
    cl2 = load("CL2 FP Equity")["PX_LAST"].dropna()
    lqq = load("LQQ FP Equity")["PX_LAST"].dropna()
    idx = base.index.intersection(cl2.index).intersection(lqq.index)
    idx = idx[idx >= START]
    df = pd.DataFrame(
        {
            "r_base": base.reindex(idx).pct_change().fillna(0.0),
            "r_cl2": cl2.reindex(idx).ffill().pct_change().fillna(0.0),
            "r_lqq": lqq.reindex(idx).ffill().pct_change().fillna(0.0),
        },
        index=idx,
    )
    r3m = load("EUR003M Index")["PX_LAST"].reindex(idx).ffill().fillna(0.0) / 100.0
    df["r_cash"] = r3m.clip(lower=0.0) / 252  # PEA money-market floor at 0
    # production gate: SPX (USD) vs its own 200-DMA, known at prev close
    spx = load("SPX Index")["PX_LAST"].dropna()
    up = (spx > spx.rolling(200).mean()).astype(float)
    df["sma200_up"] = up.reindex(idx).ffill()
    # alt gates, computed on full history then cut (no warm-up loss)
    b_full = base
    sma10m = b_full.resample("M").last().rolling(10).mean()
    faber = (b_full.resample("M").last() > sma10m).astype(float)
    df["faber_up"] = faber.reindex(idx).ffill()
    vix = load("VIX Index")["PX_LAST"].reindex(idx).ffill()
    vix3m = load("VIX3M Index")["PX_LAST"].reindex(idx).ffill()
    df["vix_calm"] = (vix / vix3m < 1.0).astype(float)
    df["r_mix_lev"] = 0.7 * df["r_cl2"] + 0.3 * df["r_lqq"]
    return df


def main() -> None:
    df = build_inputs_real()
    print(f"frame: {df.index[0].date()} → {df.index[-1].date()}  ({len(df)} bars)")

    hold = lambda d: pd.Series(1.0, index=d.index)  # noqa: E731
    trend = lambda d: d["sma200_up"].shift(1)  # noqa: E731
    faber = lambda d: d["faber_up"].shift(1)  # noqa: E731
    vixg = lambda d: d["vix_calm"].shift(1)  # noqa: E731

    STRATS = {
        # unlevered
        "hold_ese": ("r_base", hold),
        "ese_trend200": ("r_base", trend),
        # single levered sleeves
        "cl2_hold": ("r_cl2", hold),
        "cl2_trend200": ("r_cl2", trend),
        "lqq_hold": ("r_lqq", hold),
        "lqq_trend200": ("r_lqq", trend),
        # the plan and its variants
        "mix_lev_hold": ("r_mix_lev", hold),
        "mix_lev_trend200": ("r_mix_lev", trend),
        "mix_lev_faber": ("r_mix_lev", faber),
        "mix_lev_vix": ("r_mix_lev", vixg),
    }
    prices = {
        name: (1 + strat_returns(df, fn, col)).cumprod() for name, (col, fn) in STRATS.items()
    }
    null = prices["hold_ese"]

    # gate diagnostics: time on, switches/yr, state in the two post-2009 bears
    for gname, g in [("trend200", df["sma200_up"]), ("faber", df["faber_up"]), ("vix", df["vix_calm"])]:
        mo = g.resample("M").last().dropna()
        sw = (mo.diff().abs() > 0).sum() / (len(mo) / 12)
        cov20 = g.loc["2020-02-20":"2020-04-30"].mean()
        yr22 = g.loc["2022-01-01":"2022-12-31"].mean()
        print(
            f"gate {gname:9s}: on {g.mean():.0%} of days, {sw:.1f} switches/yr, "
            f"on {cov20:.0%} of COVID crash, on {yr22:.0%} of 2022"
        )

    out = []
    for name, p in prices.items():
        row = {"name": name}
        yrs_tot = (df.index[-1] - df.index[0]).days / 365.25
        row["cagr"] = round(float(p.iloc[-1] ** (1 / yrs_tot) - 1), 4)
        dd = p / p.cummax() - 1
        row["maxdd"] = round(float(dd.min()), 3)
        for yrs in (5, 10):
            row[f"{yrs}y"] = rolling_dca(p, null, yrs)
        out.append(row)
    json.dump(out, open(Path(__file__).parent / "results_post2009.json", "w"), indent=1)

    print(f"\nfee={FEE:.3%} per trade, both directions")
    for yrs in (5, 10):
        print(f"\n=== 2009+ rolling {yrs}y DCA windows vs hold_ese ===")
        print(f"{'strategy':18s} {'cagr':>7} {'maxDD':>7} {'win%':>6} {'median':>8} {'p5':>8} {'p95':>8} {'n':>4}")
        for r in sorted(out, key=lambda r: -r[f"{yrs}y"]["median"]):
            k = r[f"{yrs}y"]
            print(
                f"{r['name']:18s} {r['cagr']:>7.1%} {r['maxdd']:>7.0%} {k['win_rate']:>6.0%} "
                f"{k['median']:>+8.2%} {k['p5']:>+8.2%} {k['p95']:>+8.2%} {k['windows']:>4}"
            )


if __name__ == "__main__":
    main()
