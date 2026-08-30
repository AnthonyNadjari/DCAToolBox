"""Sensitivity of the trend gate to its moving-average window.

The production rule uses a 200-day simple moving average on the S&P 500 price
index. 200 is a convention, not a result: this sweeps the window and the way
the rule is applied, so the choice can be judged rather than inherited.

Because the gate is evaluated on daily closes, this cannot be done from the
monthly sleeve returns the dashboard ships. The daily series are rebuilt from
public data:

    ^GSPC     S&P 500 price index      — the gate input (matches SPX Index)
    ^SP500TR  S&P 500 total return     — the 1x sleeve, 1988-
    ^IRX      13-week T-bill           — financing on the borrowed leg, and
                                         the money-market return when out

The 2x sleeve is the standard daily-reset synthetic:
``r_2x = 2*r_1x - overnight - TER/252`` with TER 0.50%/yr. This is a USD,
S&P-only reconstruction — the production plan is EUR and 70/30 CL2/LQQ — so
absolute wealth differs from the published backtest, though it lands close on
the ungated sleeve (53x contributions here vs 49x in the EUR study, a good
calibration check). What transfers is the comparison ACROSS windows.

Anti-look-ahead: the signal on day t uses closes through t-1. Every whole-pot
switch pays the same 0.50% as a contribution, which is what makes the
check frequency matter more than the window length.

Variants swept: window length, simple vs exponential average, a re-entry
buffer (exit below the average, re-enter only above average*(1+b)), and
checking the signal every day versus only on deposit day.

Usage::

    python research_bbg/sma_window.py [--out research_bbg/results_sma.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CACHE = Path("/tmp/claude-0/-home-user-DCAToolBox/41247d1c-12dc-50ad-a387-08ea6345237a/scratchpad")
FEE = 0.005
CONTRIB = 1000.0
TER = 0.005
WINDOWS = (50, 100, 125, 150, 175, 200, 225, 250, 300, 400)
HORIZONS_Y = (3, 5, 10)


def _load(name: str) -> pd.Series:
    raw = json.loads((CACHE / f"{name}.json").read_text())["chart"]["result"][0]
    idx = pd.DatetimeIndex(pd.to_datetime(raw["timestamp"], unit="s").date)
    return pd.Series(raw["indicators"]["quote"][0]["close"], index=idx, name=name).dropna()


def build() -> pd.DataFrame:
    """Daily frame: 1x and 2x sleeve returns, cash return, gate input."""
    spx, tr, irx = _load("GSPC"), _load("SP500TR"), _load("IRX")
    df = pd.DataFrame({"spx": spx, "tr": tr}).dropna()
    rate = (irx.reindex(df.index).ffill() / 100.0).clip(lower=0.0)
    df["r1x"] = df["tr"].pct_change().fillna(0.0)
    df["cash"] = rate / 252.0
    df["r2x"] = 2 * df["r1x"] - df["cash"] - TER / 252.0
    return df


def gate_state(df: pd.DataFrame, window: int, kind: str, buffer_pct: float) -> np.ndarray:
    """Risk-on state per day from closes through the PREVIOUS session."""
    px = df["spx"]
    avg = (
        px.ewm(span=window, min_periods=window).mean()
        if kind == "ema"
        else px.rolling(window).mean()
    )
    ratio = (px.shift(1) / avg.shift(1)).to_numpy()
    on = np.zeros(len(df), dtype=bool)
    state = False
    for i, v in enumerate(ratio):
        if np.isfinite(v):
            state = v > 1.0 + buffer_pct if not state else v > 1.0
        on[i] = state
    return on


def strategy_returns(
    df: pd.DataFrame, on: np.ndarray, monthly_check: bool
) -> tuple[np.ndarray, int, np.ndarray]:
    """Daily return of the gated sleeve, with the switch cost charged in.

    Holding the whole pot in one sleeve makes the policy a pure return series:
    the DCA on top of it is then exact for any window.
    """
    month = df.index.to_period("M")
    deposit = np.r_[True, month[1:] != month[:-1]]
    r2x, cash = df["r2x"].to_numpy(), df["cash"].to_numpy()
    held = on if not monthly_check else np.where(deposit, on, np.nan)
    if monthly_check:  # state only changes on deposit days
        held = pd.Series(held).ffill().fillna(False).to_numpy().astype(bool)
    ret = np.where(held, r2x, cash)
    switch = np.r_[False, held[1:] != held[:-1]]
    ret = np.where(switch, (1 + ret) * (1 - FEE) - 1, ret)
    return ret, int(switch.sum()), deposit


def score(ret: np.ndarray, deposit: np.ndarray) -> dict:
    """Full-period DCA plus fresh-start rolling windows, all from one series.

    Wealth of a DCA is sum over deposits of C(1-fee) * G[end]/G[deposit], so
    one cumulative-growth vector scores every window exactly.
    """
    growth = np.cumprod(1.0 + ret)
    inv_growth = 1.0 / growth
    dep_idx = np.flatnonzero(deposit)
    cum_inv = np.cumsum(inv_growth[dep_idx])

    # full period path (for the drawdown of the accumulating pot)
    wealth = np.empty(len(ret))
    acc = 0.0
    j = 0
    for i in range(len(ret)):
        if j < len(dep_idx) and dep_idx[j] == i:
            acc += CONTRIB * (1 - FEE) * inv_growth[i]
            j += 1
        wealth[i] = acc * growth[i]
    peak = np.maximum.accumulate(wealth)
    out = {
        "mult": round(float(wealth[-1] / (CONTRIB * len(dep_idx))), 3),
        "mdd": round(float((wealth / peak - 1).min()), 4),
    }

    for years in HORIZONS_Y:
        months = years * 12
        if len(dep_idx) <= months:
            continue
        starts = np.arange(0, len(dep_idx) - months)
        ends = dep_idx[starts + months]
        sums = cum_inv[starts + months - 1] - np.where(starts > 0, cum_inv[starts - 1], 0.0)
        mults = (1 - FEE) * growth[ends] * sums / months
        out[f"y{years}"] = {
            "median": round(float(np.median(mults)), 3),
            "p5": round(float(np.percentile(mults, 5)), 3),
            "worst": round(float(mults.min()), 3),
            "p_below": round(float((mults < 1).mean()), 4),
            "n": int(mults.size),
        }
    return out


def main() -> None:
    """Sweep the window and the application rule."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research_bbg/results_sma.json")
    args = ap.parse_args()
    df = build()
    print(f"daily frame {df.index[0].date()} -> {df.index[-1].date()} ({len(df)} sessions)\n")

    rows = []
    always = np.ones(len(df), dtype=bool)
    for label, frame in (("2x sans filtre", df), ("1x buy & hold", df.assign(r2x=df["r1x"]))):
        ret, sw, dep = strategy_returns(frame, always, monthly_check=False)
        rows.append({"variant": label, "window": 0, "switches": sw, **score(ret, dep)})

    for w in WINDOWS:
        for kind, buf, monthly, label in (
            ("sma", 0.0, False, "SMA quotidien"),
            ("sma", 0.0, True, "SMA mensuel"),
            ("sma", 0.02, True, "SMA mensuel +2% tampon"),
            ("ema", 0.0, True, "EMA mensuel"),
        ):
            on = gate_state(df, w, kind, buf)
            ret, sw, dep = strategy_returns(df, on, monthly_check=monthly)
            rows.append({"variant": label, "window": w, "switches": sw, **score(ret, dep)})

    Path(args.out).write_text(json.dumps(rows, indent=1, default=float))

    def show(rs: list[dict], title: str) -> None:
        print(f"=== {title} ===")
        print(
            f"{'fen.':>5} {'mult':>6} {'maxDD':>6} {'bascul':>7} "
            f"{'3y méd':>7} {'3y p5':>6} {'3y P<1':>7} {'5y méd':>7} {'5y p5':>6} {'5y P<1':>7}"
        )
        for r in rs:
            print(
                f"{r['window']:5d} {r['mult']:6.1f} {100 * r['mdd']:5.0f}% {r['switches']:7d} "
                f"{r['y3']['median']:7.2f} {r['y3']['p5']:6.2f} {100 * r['y3']['p_below']:6.0f}% "
                f"{r['y5']['median']:7.2f} {r['y5']['p5']:6.2f} {100 * r['y5']['p_below']:6.0f}%"
            )
        print()

    for label in ("SMA mensuel", "SMA quotidien", "SMA mensuel +2% tampon", "EMA mensuel"):
        show([r for r in rows if r["variant"] == label], label)
    for r in rows[:2]:
        print(
            f"{r['variant']:16s} mult {r['mult']:6.1f}  maxDD {100 * r['mdd']:4.0f}%  "
            f"3y méd {r['y3']['median']:.2f} P<1 {100 * r['y3']['p_below']:.0f}%  "
            f"5y méd {r['y5']['median']:.2f} P<1 {100 * r['y5']['p_below']:.0f}%"
        )
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
