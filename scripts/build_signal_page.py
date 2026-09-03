"""Build web/data.json for the signal page from the local Bloomberg caches.

Run locally (needs data_bbg/, i.e. a machine that has pulled the data):

    PYTHONPATH=research_bbg python scripts/build_signal_page.py

The GitHub Pages workflow never runs this — data.json is committed, so the
public build stays Bloomberg-free.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_bbg"))
from dataset import load  # noqa: E402
from rolling import build_inputs, rolling_dca, strat_returns  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "web" / "data.json"


def month_ends(s: pd.Series) -> pd.Series:
    return s.resample("M").last().dropna()


def main() -> None:
    # --- the production signal: SPX close vs its 200-day SMA ---
    spx = load("SPX Index")["PX_LAST"].dropna()
    sma = spx.rolling(200).mean()
    up = spx > sma
    state = bool(up.iloc[-1])
    crosses = up.astype(int).diff().fillna(0) != 0
    since = up.index[crosses][-1] if crosses.any() else up.index[0]
    signal = {
        "asof": str(spx.index[-1].date()),
        "spx": round(float(spx.iloc[-1]), 2),
        "sma200": round(float(sma.iloc[-1]), 2),
        "gap_pct": round(float(spx.iloc[-1] / sma.iloc[-1] - 1) * 100, 2),
        "state": "ON" if state else "OFF",
        "since": str(since.date()),
        "days_in_state": int((spx.index[-1] - since).days),
    }

    # --- quick indicators for the dashboard strip ---
    vix = load("VIX Index")["PX_LAST"].dropna()
    ese = load("ESE FP Equity")
    spread_bp = ((ese["PX_ASK"] - ese["PX_BID"]) / ese["PX_LAST"] * 1e4).dropna()
    # distance the SPX would have to fall to flip the gate today
    signal["flip_level"] = round(float(sma.iloc[-1]), 2)
    indicators = {
        "vix": round(float(vix.iloc[-1]), 2),
        "vix_pctl_1y": round(float(vix.tail(252).rank(pct=True).iloc[-1]) * 100, 0),
        "spread_bp_last": round(float(spread_bp.iloc[-1]), 1),
        "spread_bp_med_60d": round(float(spread_bp.tail(60).median()), 1),
        "spx_chg_1m": round(float(spx.iloc[-1] / spx.iloc[-22] - 1) * 100, 2),
    }

    # --- 3y daily gate chart series ---
    tail = spx.tail(756)
    gate_series = {
        "dates": [str(d.date()) for d in tail.index],
        "spx": [round(float(v), 2) for v in tail],
        "sma": [round(float(v), 2) for v in sma.reindex(tail.index)],
    }

    # --- strategy equity curves (monthly DCA wealth, 1000 EUR/month) ---
    df = build_inputs()
    fx = load("EURUSD Curncy")["PX_LAST"].reindex(df.index).ffill()
    r_ndx = (load("XNDX Index")["PX_LAST"].reindex(df.index).ffill() / fx).pct_change().fillna(0.0)
    df["r_ndx"] = r_ndx
    df["r_levndx"] = 2 * r_ndx - df["r_cash"] - 0.006 / 252
    hold = lambda d: pd.Series(1.0, index=d.index)  # noqa: E731
    # production gate (addendum 7): SPX < 200dma at the monthly check -> keep
    # 25% of the leveraged sleeve, park the rest; recross -> redeploy.
    trend = lambda d: 0.25 + 0.75 * d["sma200_up"].shift(1)  # noqa: E731
    P = {
        "ese": (1 + strat_returns(df, hold, "r_base")).cumprod(),
        "ndx": (1 + strat_returns(df, hold, "r_ndx")).cumprod(),
        "cl2t": (1 + strat_returns(df, trend, "r_lev")).cumprod(),
        "lqqt": (1 + strat_returns(df, trend, "r_levndx")).cumprod(),
        "cl2": (1 + strat_returns(df, hold, "r_lev")).cumprod(),
        "lqq": (1 + strat_returns(df, hold, "r_levndx")).cumprod(),
    }
    MIX = {
        "strategy": {"cl2t": 0.7, "lqqt": 0.3},
        "lev_nogate": {"cl2": 0.7, "lqq": 0.3},
        "mix7030": {"ese": 0.7, "ndx": 0.3},
        "ese": {"ese": 1.0},
    }
    month = df.index.to_period("M")
    dep = np.r_[True, month[1:] != month[:-1]]
    curves = {}
    for name, w in MIX.items():
        tot = np.zeros(len(df))
        for k, wt in w.items():
            p = P[k].to_numpy()
            sh = 0.0
            vals = np.zeros(len(df))
            for i in range(len(df)):
                if dep[i]:
                    sh += 1000 * wt * (1 - 0.005) / p[i]
                vals[i] = sh * p[i]
            tot += vals
        curves[name] = month_ends(pd.Series(tot, index=df.index))
    eq_idx = curves["strategy"].index
    equity = {"dates": [str(d.date()) for d in eq_idx]}
    for name, s in curves.items():
        equity[name] = [round(float(v)) for v in s.reindex(eq_idx)]
    invested = pd.Series(dep, index=df.index).resample("M").sum().cumsum().reindex(eq_idx) * 1000
    equity["invested"] = [round(float(v)) for v in invested]

    # --- gate-off shading periods over the equity window ---
    base = (1 + df["r_base"]).cumprod()
    up_b = (base > base.rolling(200).mean()).astype(int)
    ch = up_b.diff().fillna(0)
    offs, cur = [], None
    for d, v in ch.items():
        if v == -1:
            cur = d
        elif v == 1 and cur is not None:
            offs.append([str(cur.date()), str(d.date())])
            cur = None
    if cur is not None:
        offs.append([str(cur.date()), str(df.index[-1].date())])

    # --- rolling-window stats vs the unlevered 70/30 ---
    pm = {k: (v / v.iloc[0]) for k, v in P.items()}

    def mixprice(w):
        r = sum(pm[k].pct_change().fillna(0) * wt for k, wt in w.items())
        return (1 + r).cumprod()

    null_p = mixprice(MIX["mix7030"])
    rolling = []
    for name in ("strategy", "lev_nogate", "ese"):
        p = mixprice(MIX[name])
        row = {"name": name}
        for yrs in (5, 10):
            row[f"y{yrs}"] = rolling_dca(p, null_p, yrs)
        rolling.append(row)

    # --- monthly sleeve returns: the dashboard recomputes policies from these ---
    # Each curve is a monthly DCA accumulation, so its own return series is
    # W_t / (W_{t-1} + C(1-fee)) - 1. Shipping the returns (rather than one
    # precomputed path per policy) lets the browser mix any flow allocation.
    contrib = np.diff(np.r_[0.0, np.asarray(equity["invested"], dtype=float)])
    sleeve_r = {}
    for name in MIX:
        w = np.asarray(equity[name], dtype=float)
        prev = np.r_[0.0, w[:-1]]
        sleeve_r[name] = [round(float(v), 8) for v in (w / (prev + contrib * (1 - 0.005)) - 1.0)]
    on_month = up.reindex(eq_idx, method="ffill").astype(int)
    cash_m = month_ends((1 + df["r_cash"]).cumprod()).reindex(eq_idx).pct_change().fillna(0.0)
    sleeves = {
        "dates": equity["dates"],
        "risk_on": [int(v) for v in on_month],
        "cash": [round(float(v), 8) for v in cash_m],
        "fee": 0.005,
        "contribution": 1000.0,
        "r": sleeve_r,
    }

    payload = {
        "generated": str(date.today()),
        "signal": signal,
        "indicators": indicators,
        "gate_series": gate_series,
        "equity": equity,
        "off_periods": offs,
        "rolling": rolling,
        "sleeves": sleeves,
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(
        f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB) — signal {signal['state']} "
        f"(gap {signal['gap_pct']:+.2f}%, asof {signal['asof']})"
    )


if __name__ == "__main__":
    main()
