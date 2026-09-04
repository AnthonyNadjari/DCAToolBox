"""Pre-registered counter-experiment: VIX futures term-structure slope timing.

Proposed by an external adversarial audit as the single experiment most likely
to overturn the "nothing beats immediate deployment" conclusion. The slope of
the VIX term structure (proxied by spot VIX / VIX3M — CBOE 3-month volatility
index, live since 2006-07) is the one volatility feature the fear-timing
campaign never touched: backwardation (VIX > VIX3M) marks acute stress with
documented incremental predictive power over the spot VIX level.

Pre-registered BEFORE any result is computed (this commit):

- Data: SPY 2006-07 -> 2026-07 (~20y), ^VIX and ^VIX3M closes. Feature
  ``vix_ts`` = VIX/VIX3M; ``vix_ts_pctl`` = 5y rolling percentile rank.
  Both lagged one day like every feature in the lab.
- Split: IS ends 2016-12-31 (contains the 2008-09 bear and 2011); OOS is
  2017-01 -> 2026-07 (contains 2018, 2020, 2022). ~19y total sits AT the
  credibility floor (>= 2 bear/recovery cycles) — a win here justifies a
  forward test, not an immediate doctrine change.
- Mechanics: identical to signal_lab (monthly BUDGET while cash waits,
  63-bar time-stop, fees 0.1% + slippage 0.05%, fills at open).
- Candidates (all three fixed now, no tuning afterwards):
    1. ts_p90    — deploy all when vix_ts_pctl > 0.90 (the audit's
                   "slope below its 10th percentile" = deepest backwardation).
    2. ts_abs    — deploy all when vix_ts > 1.0 (pure backwardation,
                   zero fitted parameters).
    3. ts_prop   — the audit's monotone sizing: each day deploy a fraction
                   f = clip(2*(vix_ts_pctl - 0.5), 0, 1) of waiting cash
                   (0 below the median, linear to all-in at the top);
                   the 63-bar time-stop still forces full deployment.
- Controls: CONTROL_now (immediate deployment — the structural null) and
  CONTROL_dca26, both on the same window.
- Read-out rule: a candidate is only read OOS if it beats CONTROL_now IS.
  A positive finding requires beating CONTROL_now IS AND OOS and surviving
  fees x2. Anything else confirms the null.

Usage::

    PYTHONPATH=. python scripts/vix_ts_experiment.py [--fee-mult 2]
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
IS_END = "2016-12-31"


def _load(ticker: str) -> pd.DataFrame:
    raw = json.loads((DATA / f"{ticker}.json").read_text())
    idx = pd.DatetimeIndex(pd.to_datetime(raw["dates"]), name="date")
    return pd.DataFrame({k: raw[k] for k in ("open", "close")}, index=idx)


def build() -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """SPY frame restricted to the VIX3M era + lagged term-structure features."""
    spy = _load("SPY")
    vix = _load("^VIX")["close"].reindex(spy.index).ffill()
    v3m = _load("^VIX3M")["close"].reindex(spy.index)
    spy = spy[v3m.notna()]
    ts = (vix / v3m).dropna().reindex(spy.index)
    pctl = ts.rolling(1260, min_periods=252).rank(pct=True)
    # Signals use the PREVIOUS close only.
    return spy, ts.shift(1).to_numpy(float), pctl.shift(1).to_numpy(float)


def simulate(spy: pd.DataFrame, frac: np.ndarray, seg: slice, fee: float) -> float:
    """Reserve-release with a per-day deployable FRACTION of waiting cash."""
    dates = spy.index[seg]
    op = spy["open"].to_numpy(float)[seg]
    cl = spy["close"].to_numpy(float)[seg]
    fr = frac[seg]
    month = dates.to_period("M")
    is_deposit = np.r_[True, month[1:] != month[:-1]]
    cash = shares = 0.0
    waiting = 0
    for i in range(len(dates)):
        if is_deposit[i]:
            cash += BUDGET
        if cash > 1.0:
            waiting += 1
            f = 1.0 if waiting >= MAX_HOLD else (fr[i] if np.isfinite(fr[i]) else 0.0)
            spend = cash * f
            if spend > 1.0:
                shares += spend * (1 - fee) / (op[i] * (1 + SLIP))
                cash -= spend
                if cash <= 1.0:
                    waiting = 0
        else:
            waiting = 0
    return float(shares * cl[-1] + cash)


def main() -> None:
    """Run the pre-registered candidates and controls over IS and OOS."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--fee-mult", type=float, default=1.0)
    args = ap.parse_args()
    fee = 0.001 * args.fee_mult

    spy, ts, pctl = build()
    n = len(spy)
    cut = spy.index.searchsorted(pd.Timestamp(IS_END), side="right")
    segs = {"is": slice(0, cut), "oos": slice(cut, n)}

    day26 = (spy.index.day >= 26).astype(float)
    candidates = {
        "CONTROL_now": np.ones(n),
        "CONTROL_dca26": day26,
        "ts_p90": (pctl > 0.90).astype(float),
        "ts_abs": (ts > 1.0).astype(float),
        "ts_prop": np.clip(2 * (pctl - 0.5), 0.0, 1.0),
    }
    print(f"window {spy.index[0].date()} -> {spy.index[-1].date()}  IS_END {IS_END}  fee {fee:.4f}")
    base = {s: simulate(spy, candidates["CONTROL_now"], sl, fee) for s, sl in segs.items()}
    for name, frac in candidates.items():
        row = {s: simulate(spy, frac, sl, fee) for s, sl in segs.items()}
        rel = {s: 100 * (row[s] / base[s] - 1) for s in segs}
        print(
            f"{name:14s} IS {row['is']:>10.0f} ({rel['is']:+.2f}%)"
            f"   OOS {row['oos']:>10.0f} ({rel['oos']:+.2f}%)"
        )


if __name__ == "__main__":
    main()
