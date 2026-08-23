"""Campaign 4: BUY-AND-SELL strategies judged over realistic horizons.

The investor's horizon is 5-10 years, not 30. Every strategy is therefore
evaluated over ALL rolling 5y and 10y monthly-DCA windows (1000 EUR/month
for the window, final wealth vs the buy-and-hold ESE null started the same
month). Selling is allowed (PEA: no tax inside the wrapper); every position
change pays the 0.5% fee on the traded fraction.

Mechanics: each strategy is expressed as a daily self-financing return
series (asset/cash/2x sleeves with weight changes traded at the bar, fee
on turnover). Because all capital follows the same weights, DCA wealth of
a window [m..T] is sum over contributions of B * P_T / P_m — exact.

Decision cadence: monthly (first bar), signals from the previous close.
Judged on: % of windows beating the null, median and 5th-percentile excess.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from dataset import load
from lev import build_lev_pair

FEE = 0.005


def build_inputs() -> pd.DataFrame:
    pair = build_lev_pair()  # base (ESE frame), lev (2x synth)
    df = pd.DataFrame(
        {
            "r_base": pair["base"].pct_change().fillna(0.0),
            "r_lev": pair["lev"].pct_change().fillna(0.0),
        },
        index=pair.index,
    )
    r3m = load("EUR003M Index")["PX_LAST"].reindex(df.index).ffill().fillna(3.0) / 100.0
    df["r_cash"] = r3m / 252
    base = pair["base"]
    df["sma200_up"] = (base > base.rolling(200).mean()).astype(float)
    sma10m = base.resample("M").last().rolling(10).mean()
    faber = (base.resample("M").last() > sma10m).astype(float)
    df["faber_up"] = faber.reindex(df.index).ffill()
    df["tsmom_up"] = (base.pct_change(231).shift(21) > 0).astype(float)
    vol = df["r_base"].rolling(63).std() * np.sqrt(252)
    df["vt20_w"] = (0.20 / vol).clip(0, 1)
    vix = load("VIX Index")["PX_LAST"].reindex(df.index).ffill()
    vix3m = load("VIX3M Index")["PX_LAST"].reindex(df.index).ffill()
    df["vix_calm"] = (vix / vix3m < 1.0).astype(float)
    hy = load("LF98OAS Index")["PX_LAST"].reindex(df.index).ffill()
    df["credit_calm"] = (hy.diff(21) < 0.5).astype(float)
    mmf = load("MMFA")["PX_LAST"].reindex(df.index).ffill()
    df["mmf_calm"] = (mmf.pct_change(65) < 0.04).astype(float)
    return df


def strat_returns(df: pd.DataFrame, w_asset_fn, asset_col: str = "r_base") -> pd.Series:
    """Monthly-rebalanced weight in the risky sleeve; rest in cash; fee on turnover."""
    month = df.index.to_period("M")
    is_dep = np.r_[True, month[1:] != month[:-1]]
    w_target = w_asset_fn(df)  # daily series of desired weight (from prev close)
    w = 0.0
    out = np.zeros(len(df))
    ra = df[asset_col].to_numpy()
    rc = df["r_cash"].to_numpy()
    wt = w_target.to_numpy()
    for i in range(len(df)):
        if is_dep[i] and np.isfinite(wt[i]):
            new_w = float(np.clip(wt[i], 0.0, 1.0))
            cost = abs(new_w - w) * FEE
            w = new_w
        else:
            cost = 0.0
        out[i] = w * ra[i] + (1 - w) * rc[i] - cost
    return pd.Series(out, index=df.index)


def rolling_dca(price: pd.Series, null_price: pd.Series, years: int) -> dict:
    """All rolling <years>-year monthly DCA windows: excess final wealth vs null."""
    monthly_p = price.resample("M").last().dropna()
    monthly_n = null_price.reindex(price.index).resample("M").last().dropna()
    both = pd.concat([monthly_p, monthly_n], axis=1, keys=["s", "n"]).dropna()
    h = years * 12
    exc = []
    for start in range(0, len(both) - h):
        w = both.iloc[start : start + h + 1]
        ws = (w["s"].iloc[-1] / w["s"].iloc[:-1]).sum()
        wn = (w["n"].iloc[-1] / w["n"].iloc[:-1]).sum()
        exc.append(ws / wn - 1)
    exc = np.array(exc)
    return {
        "windows": len(exc),
        "win_rate": round(float((exc > 0).mean()), 3),
        "median": round(float(np.median(exc)), 4),
        "p5": round(float(np.percentile(exc, 5)), 4),
        "p95": round(float(np.percentile(exc, 95)), 4),
    }


def main() -> None:
    df = build_inputs()
    S = {
        "hold_ese": lambda d: pd.Series(1.0, index=d.index),
        "trend200_sell": lambda d: d["sma200_up"].shift(1),
        "faber_10m_sell": lambda d: d["faber_up"].shift(1),
        "tsmom_12_1_sell": lambda d: d["tsmom_up"].shift(1),
        "voltarget20_sell": lambda d: d["vt20_w"].shift(1),
        "vix_ts_sell": lambda d: d["vix_calm"].shift(1),
        "credit_sell": lambda d: d["credit_calm"].shift(1),
        "mmf_sell": lambda d: d["mmf_calm"].shift(1),
        "combo_trend_vix": lambda d: (d["sma200_up"] * d["vix_calm"]).shift(1),
    }
    LEV = {
        "hold_lev100": lambda d: pd.Series(1.0, index=d.index),
        "lev_trend200": lambda d: d["sma200_up"].shift(1),
        "lev_faber": lambda d: d["faber_up"].shift(1),
        "lev_voltarget25": lambda d: (0.25 * (d["vt20_w"] / 0.20)).clip(0, 1).shift(1),
    }
    prices = {}
    for name, fn in S.items():
        prices[name] = (1 + strat_returns(df, fn, "r_base")).cumprod()
    for name, fn in LEV.items():
        prices[name] = (1 + strat_returns(df, fn, "r_lev")).cumprod()
    null = prices["hold_ese"]
    out = []
    for name, p in prices.items():
        row = {"name": name}
        for yrs in (5, 10):
            row[f"{yrs}y"] = rolling_dca(p, null, yrs)
        out.append(row)
    json.dump(out, open(Path(__file__).parent / "results_rolling.json", "w"), indent=1)
    for yrs in (5, 10):
        print(f"\n=== rolling {yrs}y DCA windows vs buy-and-hold ESE ===")
        print(f"{'strategy':20s} {'win%':>6} {'median':>8} {'p5':>8} {'p95':>8} {'n':>5}")
        for r in sorted(out, key=lambda r: -r[f"{yrs}y"]["median"]):
            k = r[f"{yrs}y"]
            print(
                f"{r['name']:20s} {k['win_rate']:>6.0%} {k['median']:>+8.2%} "
                f"{k['p5']:>+8.2%} {k['p95']:>+8.2%} {k['windows']:>5}"
            )


if __name__ == "__main__":
    main()
