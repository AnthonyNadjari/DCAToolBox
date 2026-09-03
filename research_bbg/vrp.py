"""Campaign 5A: the variance-risk-premium sleeve vs the leverage architectures.

The one family the whole program never tested (Block B of the Bloomberg data
request): option-overlay strategy indices. PUT (cash-secured put write),
BXM/BXY (covered calls), WPUT (weekly put write), PPUT (protective put),
CLL (collar) — Cboe official total-return benchmarks, USD, converted to EUR
at the daily close, minus a modeled 0.5%/yr fund cost. This is a DIFFERENT
risk architecture from daily-reset leverage: it harvests the vol premium
with equity-like crash beta but lower vol, instead of amplifying beta.

PRE-REGISTERED menu (written before results; do not extend after reading):
single sleeves, flow mixes with ESE and with the leveraged sleeves, and —
the interesting structural idea — the trend gate whose OFF destination is
the put-write sleeve instead of the money market (the vol premium is
fattest exactly when the gate is off).

Judged like the rest of the program: rolling 5y/10y monthly-DCA windows,
multiple-of-contributions metrics, win/median/p5 vs the 100% ESE null,
eras full-sample / starts<2009 / starts 2009+, fee 0.5% per risky purchase,
gated series carry their internal switching fees. Nulls: hold ESE,
ungated 2x, and the production rule (200dma gate, off keeps 25%).

Caveats stated up front: Cboe indices pre-live-date are backfilled
(frictionless, no fund existed); no PEA-eligible put-write fund is known —
a winner here would need a CTO wrapper, which changes the tax math.

Usage::

    python research_bbg/vrp.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from dataset import build_asset_frame, load
from gate_lab import add_signals, run, ZERO
from rolling import FEE, build_inputs

FUND_COST = 0.005  # modeled annual cost of a real put-write wrapper
HORIZONS = (5, 10)


def build_sleeves() -> pd.DataFrame:
    """Daily EUR sleeve returns on the ESE-frame calendar."""
    asset = build_asset_frame()
    idx = asset.index
    fx = load("EURUSD Curncy")["PX_LAST"]

    out = pd.DataFrame(index=idx)
    out["ese"] = asset["close"].pct_change().fillna(0.0)

    lev = add_signals(build_inputs())
    wl = lambda d: 0.25 + 0.75 * d["g_trend"].shift(1)  # noqa: E731
    lev["r_gated"] = run(lev, wl, ZERO)
    out["lev2x"] = lev["r_lev"].reindex(idx).fillna(0.0)
    out["gated"] = lev["r_gated"].reindex(idx).fillna(0.0)

    for name, ticker in (
        ("putw", "PUT Index"),
        ("bxm", "BXM Index"),
        ("bxy", "BXY Index"),
        ("wput", "WPUT Index"),
        ("pput", "PPUT Index"),
        ("cll", "CLL Index"),
    ):
        try:
            s = load(ticker)["PX_LAST"].dropna()
        except FileNotFoundError:
            continue
        eur = s / fx.reindex(s.index).ffill()
        out[name] = (eur.pct_change() - FUND_COST / 252).reindex(idx)
    out["cash"] = lev["r_cash"].reindex(idx).fillna(0.0)
    return out.dropna(subset=["putw"])


def gate_machine(df: pd.DataFrame, w_lev: pd.Series, dest_col: str) -> pd.Series:
    """Daily returns: w_lev in lev2x when checked, rest in dest_col; fee per leg."""
    month = df.index.to_period("M")
    is_dep = np.r_[True, month[1:] != month[:-1]]
    wl_t = w_lev.to_numpy()
    rl = df["lev2x"].to_numpy()
    rd = df[dest_col].to_numpy()
    wl = 0.0
    out = np.zeros(len(df))
    for i in range(len(df)):
        cost = 0.0
        if is_dep[i] and np.isfinite(wl_t[i]):
            nl = float(np.clip(wl_t[i], 0, 1))
            cost = abs(nl - wl) * FEE
            wl = nl
        out[i] = wl * rl[i] + (1 - wl) * rd[i] - cost
    return pd.Series(out, index=df.index)


def build_candidates(s: pd.DataFrame) -> dict[str, pd.Series]:
    """The pre-registered menu: name -> daily return series."""
    g = s["g_trend"] if "g_trend" in s else None
    cands = {
        "hold_ese": s["ese"],
        "hold_lev2x": s["lev2x"],
        "production_gated": s["gated"],
        "putw100": s["putw"],
        "putw50_ese50": 0.5 * s["putw"] + 0.5 * s["ese"],
        "putw70_lev30": 0.7 * s["putw"] + 0.3 * s["lev2x"],
        "putw30_gated70": 0.3 * s["putw"] + 0.7 * s["gated"],
    }
    for opt in ("bxm", "bxy", "wput", "pput", "cll"):
        if opt in s:
            cands[f"{opt}100"] = s[opt]
            cands[f"{opt}50_ese50"] = 0.5 * s[opt] + 0.5 * s["ese"]
    # gate with put-write as the OFF destination (production off-dose 25% kept)
    spx = load("SPX Index")["PX_LAST"].dropna()
    up = (spx > spx.rolling(200).mean()).astype(float)
    s = s.assign(g_trend=up.reindex(s.index).ffill())
    wl0 = (0.25 + 0.75 * s["g_trend"].shift(1)).fillna(0.25)
    cands["gate_dest_putw"] = gate_machine(s, wl0, "putw")
    cands["gate_dest_cash_ctrl"] = gate_machine(s, wl0, "cash")
    if "bxm" in s:
        cands["gate_dest_bxm"] = gate_machine(s, wl0, "bxm")
    return cands


def dca_windows(rets: np.ndarray, years: int) -> np.ndarray:
    """Final wealth per unit of monthly contribution, all rolling windows.

    Window of h deposits: deposit j grows to the window end by g[end]/g[j-1]
    with g[-1] := 1, so wealth = g[s+h-1] * sum_j 1/g[j-1].
    """
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


def score_candidate(name: str, daily: pd.Series, null_m: pd.Series) -> dict:
    """Score one candidate on its own history (short series keep their window)."""
    m = daily.resample("M").apply(lambda x: (1 + x).prod() - 1).dropna()
    r_all = m.to_numpy()
    p = (1 + m).cumprod()
    yrs = (m.index[-1] - m.index[0]).days / 365.25
    row = {
        "name": name,
        "from": str(m.index[0].date()),
        "cagr": round(float(p.iloc[-1] ** (1 / yrs) - 1), 4),
        "maxdd": round(float((p / p.cummax() - 1).min()), 3),
    }
    eras = {
        "all": np.ones(len(m), bool),
        "pre09": (m.index < "2009-01-01"),
        "post09": (m.index >= "2009-01-01"),
    }
    for era, mask in eras.items():
        r = r_all[mask]
        row[era] = {}
        null = null_m.reindex(m.index).ffill().to_numpy()[mask]
        for y in HORIZONS:
            w, nw = dca_windows(r, y), dca_windows(null, y)
            if len(w) < 10 or len(nw) < 10:
                continue
            n = min(len(w), len(nw))
            exc = w[:n] / nw[:n] - 1.0
            row[era][f"y{y}"] = {
                "median": round(float(np.median(w)), 3),
                "p5": round(float(np.percentile(w, 5)), 3),
                "p_below": round(float((w < 1).mean()), 3),
                "win_vs_ese": round(float((exc > 0).mean()), 3),
                "exc_median": round(float(np.median(exc)), 4),
            }
    return row


def main() -> None:
    s = build_sleeves()
    print(f"frame: {s.index[0].date()} -> {s.index[-1].date()} ({len(s)} bars)")
    cands = build_candidates(s)
    null_m = cands["hold_ese"].resample("M").apply(lambda x: (1 + x).prod() - 1).dropna()

    out = [score_candidate(n, r, null_m) for n, r in cands.items()]
    json.dump(out, open(Path(__file__).parent / "results_vrp.json", "w"), indent=1)

    for era in ("all", "post09"):
        print(f"\n=== {era} — rolling 5y DCA windows vs hold ESE ===")
        print(f"{'candidate':22s} {'cagr':>7} {'maxDD':>6} {'med':>6} {'p5':>6} {'P<1':>6} {'win%':>6} {'exc-med':>8}")
        for r in sorted(out, key=lambda r: -r[era].get("y5", {}).get("exc_median", -9)):
            k = r[era].get("y5")
            if not k:
                continue
            print(
                f"{r['name']:22s} {r['cagr']:>7.1%} {r['maxdd']:>6.0%} {k['median']:6.2f} "
                f"{k['p5']:6.2f} {100 * k['p_below']:5.0f}% {100 * k['win_vs_ese']:5.0f}% {k['exc_median']:>+8.1%}"
            )


if __name__ == "__main__":
    main()
