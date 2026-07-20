"""Pre-registered experiment: macro/credit signal families never tested before.

The nine prior campaigns covered price, volume, VIX, realized vol, T-bill and
the VIX term structure. Five families were never touched; public equivalents of
the Bloomberg series now close the gap:

    CREDIT  = Moody's Baa yield - 10Y Treasury (DBAA - DGS10), daily 1986-
              (long-history proxy of the HY OAS, correlation ~0.8)
    QUALITY = Baa - Aaa (DBAA - DAAA), daily 1986-
    CURVE   = 10Y - 3M Treasury (T10Y3M), daily 1982-
    MOVE    = ICE BofA rate volatility, daily 2002- (short: flagged)
    NFCI    = Chicago Fed financial conditions, weekly 1971-
              (revised history -> any positive is an UPPER BOUND, flagged)

Pre-registered BEFORE any result is computed (this commit) — 13 candidates,
thresholds fixed, no grid:

    credit_p85       CREDIT 5y-pctl > 0.85          (stress -> deploy)
    credit_p95       CREDIT 5y-pctl > 0.95
    credit_z15       CREDIT 3y z-score > 1.5
    credit_easing    CREDIT 63d change < 0          (improving credit -> deploy)
    quality_p90      QUALITY 5y-pctl > 0.90
    curve_inverted   CURVE < 0                      (inversion -> deploy)
    curve_p05        CURVE 5y-pctl < 0.05
    curve_resteepen  CURVE > 0 and CURVE(-63) < 0   (re-steepening after inversion)
    move_p90         MOVE 5y-pctl > 0.90
    move_p20         MOVE 5y-pctl < 0.20            (calm tape -> deploy)
    nfci_tight       NFCI > 0                       (tight conditions -> deploy)
    nfci_z10         NFCI 3y z-score > 1.0
    nfci_easing      NFCI > 0 and NFCI 63d change < 0

Mechanics identical to every prior campaign: 1000/month arrives and WAITS in
reserve; deploys entirely into SPY (total-return) at the next open when the
signal fires; 63-bar time-stop; fees 0.1% + slippage 0.05%. Null = immediate
deployment (CONTROL_now); CONTROL_dca26 shown for reference.

Publication lags (signals must be knowable at the fill): FRED daily series are
published T+1 -> lagged 2 business days. MOVE (exchange close) -> 1 day.
NFCI (weekly, published the following Wednesday) -> 7 business days.

Split: IS ends 2012-12-31, OOS 2013-01 -> today, read once. Read-out rule: a
candidate must beat CONTROL_now IS to be read OOS; a positive finding must beat
it IS AND OOS and survive fees x2. MOVE's IS is short (2007-2012 after warmup)
and NFCI's history is revised — both noted in the verdict regardless of outcome.

Usage::

    PYTHONPATH=. python scripts/macro_signals_experiment.py [--fee-mult 2]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("data_real")
SLIP = 0.0005
BUDGET = 1000.0
MAX_HOLD = 63
IS_END = "2012-12-31"


def _fred(name: str) -> pd.Series:
    df = pd.read_csv(DATA / "macro" / f"{name}.csv")
    df.columns = ["date", "value"]
    s = pd.Series(
        pd.to_numeric(df["value"], errors="coerce").to_numpy(),
        index=pd.DatetimeIndex(pd.to_datetime(df["date"])),
        name=name,
    )
    return s.dropna()


def _spy() -> pd.DataFrame:
    raw = json.loads((DATA / "SPY.json").read_text())
    idx = pd.DatetimeIndex(pd.to_datetime(raw["dates"]))
    return pd.DataFrame({"open": raw["open"], "close": raw["close"]}, index=idx)


def build() -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """SPY frame + lagged macro features aligned on its calendar."""
    spy = _spy()
    idx = spy.index

    def align(s: pd.Series, lag_bd: int) -> pd.Series:
        return s.reindex(idx.union(s.index)).ffill().reindex(idx).shift(lag_bd)

    credit = align(_fred("DBAA") - _fred("DGS10"), 2)
    quality = align(_fred("DBAA") - _fred("DAAA"), 2)
    curve = align(_fred("T10Y3M"), 2)
    move = align(_fred("MOVE"), 1)
    nfci = align(_fred("NFCI"), 7)

    def pctl(s: pd.Series) -> pd.Series:
        return s.rolling(1260, min_periods=252).rank(pct=True)

    def z(s: pd.Series, n: int = 756) -> pd.Series:
        return (s - s.rolling(n, min_periods=252).mean()) / s.rolling(n, min_periods=252).std()

    f = {
        "credit_p85": pctl(credit) > 0.85,
        "credit_p95": pctl(credit) > 0.95,
        "credit_z15": z(credit) > 1.5,
        "credit_easing": credit.diff(63) < 0,
        "quality_p90": pctl(quality) > 0.90,
        "curve_inverted": curve < 0,
        "curve_p05": pctl(curve) < 0.05,
        "curve_resteepen": (curve > 0) & (curve.shift(63) < 0),
        "move_p90": pctl(move) > 0.90,
        "move_p20": pctl(move) < 0.20,
        "nfci_tight": nfci > 0,
        "nfci_z10": z(nfci) > 1.0,
        "nfci_easing": (nfci > 0) & (nfci.diff(63) < 0),
    }
    return spy, {k: v.fillna(False).to_numpy() for k, v in f.items()}


def simulate(spy: pd.DataFrame, fired: np.ndarray, seg: slice, fee: float) -> float:
    dates = spy.index[seg]
    op = spy["open"].to_numpy(float)[seg]
    cl = spy["close"].to_numpy(float)[seg]
    fr = fired[seg]
    month = dates.to_period("M")
    is_deposit = np.r_[True, month[1:] != month[:-1]]
    cash = shares = 0.0
    waiting = 0
    for i in range(len(dates)):
        if is_deposit[i]:
            cash += BUDGET
        if cash > 1.0:
            waiting += 1
            if fr[i] or waiting >= MAX_HOLD:
                shares += cash * (1 - fee) / (op[i] * (1 + SLIP))
                cash = 0.0
                waiting = 0
        else:
            waiting = 0
    return float(shares * cl[-1] + cash)


def main() -> None:
    """Run the 13 pre-registered candidates plus controls over IS and OOS."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee-mult", type=float, default=1.0)
    args = ap.parse_args()
    fee = 0.001 * args.fee_mult

    spy, feats = build()
    n = len(spy)
    cut = spy.index.searchsorted(pd.Timestamp(IS_END), side="right")
    segs = {"is": slice(0, cut), "oos": slice(cut, n)}
    always = np.ones(n, dtype=bool)
    day26 = (spy.index.day >= 26).to_numpy()

    base = {s: simulate(spy, always, sl, fee) for s, sl in segs.items()}
    print(f"SPY {spy.index[0].date()} -> {spy.index[-1].date()}  IS_END {IS_END}  fee {fee:.4f}")
    print(f"{'candidate':>16} {'IS':>10} {'IS%':>7} {'OOS':>10} {'OOS%':>7}")
    rows = [("CONTROL_now", always), ("CONTROL_dca26", day26)] + list(feats.items())
    for name, arr in rows:
        w = {s: simulate(spy, arr, sl, fee) for s, sl in segs.items()}
        print(
            f"{name:>16} {w['is']:>10.0f} {100 * (w['is'] / base['is'] - 1):+6.2f}%"
            f" {w['oos']:>10.0f} {100 * (w['oos'] / base['oos'] - 1):+6.2f}%"
        )


if __name__ == "__main__":
    main()
